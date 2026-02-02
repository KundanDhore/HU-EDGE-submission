"""
PGVector-backed chunk store for project code.

This module:
- Ensures a `project_code_chunks` table exists (using pgvector).
- Splits project files into overlapping chunks.
- Creates OpenAI embeddings for chunks and stores them in Postgres.
- Performs vector similarity search to retrieve chunks as chat context.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logging import get_logger
from psycopg2.extras import execute_values  # type: ignore

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional Tree-sitter support (syntax-aware chunking)
# ---------------------------------------------------------------------------
try:
    from tree_sitter import Language, Parser  # type: ignore

    import tree_sitter_c_sharp  # type: ignore
    import tree_sitter_cpp  # type: ignore
    import tree_sitter_go  # type: ignore
    import tree_sitter_java  # type: ignore
    import tree_sitter_javascript  # type: ignore
    import tree_sitter_python  # type: ignore
    import tree_sitter_rust  # type: ignore
    import tree_sitter_typescript  # type: ignore

    TREE_SITTER_AVAILABLE = True
except Exception:
    TREE_SITTER_AVAILABLE = False
    Parser = None  # type: ignore


# ---------------------------------------------------------------------------
# Optional LangChain RecursiveCharacterTextSplitter (universal fallback)
# ---------------------------------------------------------------------------
try:
    # Newer LangChain versions
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore

    LANGCHAIN_SPLITTER_AVAILABLE = True
except Exception:
    try:
        # Older LangChain versions
        from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore

        LANGCHAIN_SPLITTER_AVAILABLE = True
    except Exception:
        RecursiveCharacterTextSplitter = None  # type: ignore
        LANGCHAIN_SPLITTER_AVAILABLE = False


@dataclass
class ChunkRow:
    id: int
    path: str
    start_line: Optional[int]
    end_line: Optional[int]
    content: str
    score: float


def _vector_literal(vec: Sequence[float]) -> str:
    # pgvector accepts a string like: '[0.1, 0.2, ...]'
    return "[" + ", ".join(f"{float(x):.8f}" for x in vec) + "]"


def ensure_pgvector_schema(conn: Connection, *, embedding_dim: int) -> None:
    """
    Create extension/table/indexes if missing.
    Safe to call repeatedly.
    """
    t0 = time.time()
    logger.debug(f"Ensuring pgvector schema (embedding_dim={int(embedding_dim)})")
    # Extension (in docker this is already created, but this makes local runs safer)
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    # Table
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS project_code_chunks (
              id BIGSERIAL PRIMARY KEY,
              project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              chunk_index INTEGER NOT NULL,
              start_line INTEGER,
              end_line INTEGER,
              content TEXT NOT NULL,
              content_sha256 TEXT,
              embedding VECTOR({int(embedding_dim)}) NOT NULL,
              created_at TIMESTAMPTZ DEFAULT now(),
              UNIQUE(project_id, path, chunk_index)
            );
            """
        )
    )

    # Basic indexes
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pcc_project_id ON project_code_chunks(project_id);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pcc_project_path ON project_code_chunks(project_id, path);"))

    # Vector index (prefer HNSW if available; fall back silently if not supported)
    try:
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_pcc_embedding_hnsw
                ON project_code_chunks
                USING hnsw (embedding vector_cosine_ops);
                """
            )
        )
        logger.debug("Ensured HNSW index idx_pcc_embedding_hnsw exists (or created)")
    except Exception as e:
        # Older pgvector may not support HNSW; we'll rely on exact scan or user can add ivfflat.
        logger.warning(f"HNSW index creation skipped/failed: {e}")
    finally:
        logger.debug(f"ensure_pgvector_schema done in {(time.time() - t0):.3f}s")


def delete_project_chunks(db: Session, *, project_id: int) -> int:
    res = db.execute(text("DELETE FROM project_code_chunks WHERE project_id = :project_id"), {"project_id": project_id})
    # SQLAlchemy 2 returns a Result; rowcount is available.
    return int(getattr(res, "rowcount", 0) or 0)


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _chunk_spans(content: str, *, chunk_chars: int, chunk_overlap: int) -> List[Tuple[int, int]]:
    """
    Return list of (start_idx, end_idx) spans into content.
    Simple character-based splitting with overlap.
    """
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")

    n = len(content)
    if n == 0:
        return []

    step = max(1, chunk_chars - chunk_overlap)
    spans: List[Tuple[int, int]] = []
    start = 0
    while start < n:
        end = min(n, start + chunk_chars)
        spans.append((start, end))
        if end >= n:
            break
        start = start + step
    return spans


def _line_number_at(newline_positions: List[int], idx: int) -> int:
    # Count of '\n' strictly before idx, plus 1.
    import bisect

    return bisect.bisect_left(newline_positions, idx) + 1


def _file_ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _get_separators_for_file(file_ext: str) -> List[str]:
    """
    Provide separators for recursive chunking. This is used by the universal
    fallback splitter (LangChain or internal implementation).
    """
    # Code files - respect code structure
    code_separators = ["\n\n", "\n", "; ", ", ", " ", ""]

    # Text / docs
    text_separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]

    # Markup / structured
    markup_separators = ["\n\n", "\n# ", "\n## ", "\n### ", "\n", ". ", " ", ""]

    if file_ext in {".md", ".markdown", ".rst", ".txt"}:
        return markup_separators
    if file_ext in {".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css"}:
        return ["\n\n", "\n", ",", " ", ""]
    if file_ext in {".csv", ".tsv", ".log"}:
        return ["\n", ",", " ", ""]
    return code_separators


def _tree_sitter_language_for_ext(file_ext: str):
    if not TREE_SITTER_AVAILABLE:
        return None

    language_map = {
        ".py": tree_sitter_python.language(),
        ".pyw": tree_sitter_python.language(),
        ".js": tree_sitter_javascript.language(),
        ".jsx": tree_sitter_javascript.language(),
        ".ts": tree_sitter_typescript.language_typescript(),
        ".tsx": tree_sitter_typescript.language_tsx(),
        ".java": tree_sitter_java.language(),
        ".go": tree_sitter_go.language(),
        ".rs": tree_sitter_rust.language(),
        ".cpp": tree_sitter_cpp.language(),
        ".cc": tree_sitter_cpp.language(),
        ".cxx": tree_sitter_cpp.language(),
        ".c": tree_sitter_cpp.language(),
        ".h": tree_sitter_cpp.language(),
        ".hpp": tree_sitter_cpp.language(),
        ".cs": tree_sitter_c_sharp.language(),
    }
    cap = language_map.get(file_ext)
    if cap is None:
        return None
    # tree_sitter_* packages expose a PyCapsule; wrap it into a Language object.
    try:
        return Language(cap)
    except Exception:
        return None


_TREE_SITTER_PARSER_CACHE: Dict[str, Any] = {}


def _get_tree_sitter_parser(file_ext: str):
    """
    Get (and cache) a Tree-sitter parser for supported languages.
    Returns None if Tree-sitter isn't available or language unsupported.
    """
    if not TREE_SITTER_AVAILABLE:
        return None
    if file_ext in _TREE_SITTER_PARSER_CACHE:
        return _TREE_SITTER_PARSER_CACHE[file_ext]

    lang = _tree_sitter_language_for_ext(file_ext)
    if not lang:
        _TREE_SITTER_PARSER_CACHE[file_ext] = None
        return None

    parser = Parser()
    # tree_sitter API differs across versions
    try:
        parser.set_language(lang)  # type: ignore[attr-defined]
    except Exception:
        parser.language = lang

    _TREE_SITTER_PARSER_CACHE[file_ext] = parser
    return parser


def _get_chunkable_node_types(file_ext: str) -> set:
    node_types_map = {
        # Python
        ".py": {"function_definition", "class_definition", "decorated_definition"},
        ".pyw": {"function_definition", "class_definition", "decorated_definition"},
        # JavaScript/TypeScript
        ".js": {"function_declaration", "class_declaration", "method_definition", "arrow_function", "function_expression"},
        ".jsx": {"function_declaration", "class_declaration", "method_definition", "arrow_function", "function_expression"},
        ".ts": {"function_declaration", "class_declaration", "method_definition", "interface_declaration", "type_alias_declaration"},
        ".tsx": {"function_declaration", "class_declaration", "method_definition", "interface_declaration", "type_alias_declaration"},
        # Java
        ".java": {"class_declaration", "method_declaration", "interface_declaration", "constructor_declaration"},
        # Go
        ".go": {"function_declaration", "method_declaration", "type_declaration", "type_spec"},
        # Rust
        ".rs": {"function_item", "impl_item", "trait_item", "struct_item", "enum_item", "mod_item"},
        # C/C++
        ".c": {"function_definition", "struct_specifier", "class_specifier"},
        ".cpp": {"function_definition", "class_specifier", "struct_specifier", "namespace_definition"},
        ".cc": {"function_definition", "class_specifier", "struct_specifier"},
        ".cxx": {"function_definition", "class_specifier", "struct_specifier"},
        ".h": {"function_definition", "class_specifier", "struct_specifier"},
        ".hpp": {"function_definition", "class_specifier", "struct_specifier"},
        # C#
        ".cs": {"class_declaration", "method_declaration", "interface_declaration", "struct_declaration", "namespace_declaration"},
    }
    return node_types_map.get(file_ext, set())


def _utf8_byte_offsets(content: str) -> List[int]:
    """
    Return a list where entry i is the UTF-8 byte offset of the i-th character.
    The last entry is total bytes (len in UTF-8).
    """
    offsets = [0]
    total = 0
    for ch in content:
        total += len(ch.encode("utf-8"))
        offsets.append(total)
    return offsets


def _char_index_from_byte(byte_offsets: List[int], byte_pos: int) -> int:
    import bisect

    if byte_pos <= 0:
        return 0
    if byte_pos >= byte_offsets[-1]:
        return len(byte_offsets) - 1
    # Tree-sitter byte positions align to UTF-8 boundaries, so exact match is expected.
    return int(bisect.bisect_left(byte_offsets, byte_pos))


def _extract_tree_sitter_chunks(
    content: str,
    *,
    parser,
    file_ext: str,
    max_chunk_chars: int = 1200,
) -> List[Tuple[int, int, str]]:
    """
    Extract code chunks using Tree-sitter AST.
    Returns list of (start_char, end_char, node_type) tuples.
    """
    if not parser:
        return []

    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception:
        return []

    root = tree.root_node
    target_types = _get_chunkable_node_types(file_ext)
    if not target_types:
        return []

    byte_offsets = _utf8_byte_offsets(content)
    chunks: List[Tuple[int, int, str]] = []

    def traverse(node) -> None:
        if node.type in target_types:
            start_char = _char_index_from_byte(byte_offsets, int(node.start_byte))
            end_char = _char_index_from_byte(byte_offsets, int(node.end_byte))
            if (end_char - start_char) <= max_chunk_chars * 2:
                chunks.append((start_char, end_char, node.type))
                return  # don't descend into children of a chosen chunk
        for child in node.children:
            traverse(child)

    traverse(root)
    chunks.sort(key=lambda x: x[0])

    # Remove chunks fully contained in another chunk
    filtered: List[Tuple[int, int, str]] = []
    for i, (start, end, node_type) in enumerate(chunks):
        contained = False
        for j, (other_start, other_end, _) in enumerate(chunks):
            if i != j and start >= other_start and end <= other_end:
                contained = True
                break
        if not contained:
            filtered.append((start, end, node_type))
    return filtered


def _fallback_recursive_split_spans(
    content: str,
    *,
    separators: Sequence[str],
    chunk_size: int,
    chunk_overlap: int,
) -> List[Tuple[int, int]]:
    """
    Internal universal recursive splitter (no external dependency).
    Returns (start_char, end_char) spans.
    """
    spans: List[Tuple[int, int]] = []

    def split_recursive(text: str, start_offset: int, seps: Sequence[str]) -> None:
        if len(text) <= chunk_size:
            if text.strip():
                spans.append((start_offset, start_offset + len(text)))
            return

        for sep in seps:
            if sep == "":
                # character-level split with overlap
                step = max(1, chunk_size - max(0, chunk_overlap))
                i = 0
                while i < len(text):
                    end = min(len(text), i + chunk_size)
                    if text[i:end].strip():
                        spans.append((start_offset + i, start_offset + end))
                    if end >= len(text):
                        break
                    i += step
                return

            if sep in text:
                # Split while preserving offsets by scanning occurrences
                parts = text.split(sep)
                # Compute piece spans (including separator except last)
                cursor = 0
                pieces: List[Tuple[int, int]] = []
                for i, part in enumerate(parts):
                    piece_start = cursor
                    piece_end = cursor + len(part) + (len(sep) if i < len(parts) - 1 else 0)
                    pieces.append((piece_start, piece_end))
                    cursor = piece_end

                cur_start = pieces[0][0]
                cur_end = pieces[0][0]
                for p_start, p_end in pieces:
                    if (p_end - cur_start) <= chunk_size:
                        cur_end = p_end
                        continue

                    if cur_end > cur_start and text[cur_start:cur_end].strip():
                        spans.append((start_offset + cur_start, start_offset + cur_end))

                    # start new chunk with overlap from previous
                    overlap_start = max(cur_start, cur_end - chunk_overlap) if chunk_overlap > 0 else cur_end
                    cur_start = overlap_start
                    cur_end = overlap_start

                    # now add current piece (may still exceed; handle by recursion with smaller separators)
                    if (p_end - cur_start) <= chunk_size:
                        cur_end = p_end
                    else:
                        split_recursive(text[p_start:p_end], start_offset + p_start, seps[seps.index(sep) + 1 :])
                        cur_start = p_end
                        cur_end = p_end

                if cur_end > cur_start and text[cur_start:cur_end].strip():
                    spans.append((start_offset + cur_start, start_offset + cur_end))
                return

        # If no separator matched, fall back to character split
        split_recursive(text, start_offset, [""])

    split_recursive(content, 0, list(separators))
    return spans


def split_text_to_code_chunks(
    *,
    path: str,
    content: str,
    chunk_chars: int = 1200,
    chunk_overlap: int = 150,
) -> List[Dict[str, Any]]:
    """
    Hybrid chunking strategy:
    - Tree-sitter for supported code languages (syntax-aware)
    - RecursiveCharacterTextSplitter for everything else (universal)

    Produces chunk dicts with required keys used by indexing:
    path, chunk_index, start_line, end_line, content, content_sha256.

    Additional metadata keys (chunk_type, splitter) are included for debugging.
    """
    file_ext = _file_ext(path)
    newline_positions = [i for i, ch in enumerate(content) if ch == "\n"]
    content_len = len(content)

    # 1) Tree-sitter for supported code languages
    parser = _get_tree_sitter_parser(file_ext)
    if parser:
        spans = _extract_tree_sitter_chunks(content, parser=parser, file_ext=file_ext, max_chunk_chars=chunk_chars)
        if spans:
            logger.debug(
                f"Chunking via tree-sitter (path={path}, ext={file_ext}, chars={content_len}, spans={len(spans)}, "
                f"chunk_chars={int(chunk_chars)}, overlap={int(chunk_overlap)})"
            )
            out: List[Dict[str, Any]] = []
            for idx, (s, e, node_type) in enumerate(spans):
                chunk_text = content[s:e].strip()
                if not chunk_text:
                    continue
                out.append(
                    {
                        "path": path,
                        "chunk_index": idx,
                        "start_line": _line_number_at(newline_positions, s) if newline_positions else 1,
                        "end_line": _line_number_at(newline_positions, e) if newline_positions else 1,
                        "content": chunk_text,
                        "content_sha256": _sha256_text(chunk_text),
                        "chunk_type": f"tree_sitter:{node_type}",
                        "splitter": "tree_sitter",
                    }
                )
            if out:
                logger.debug(f"Tree-sitter chunking produced {len(out)} chunks (path={path})")
                return out

    # 2) Universal recursive splitter fallback
    separators = _get_separators_for_file(file_ext)
    spans2: List[Tuple[int, int]] = []

    if LANGCHAIN_SPLITTER_AVAILABLE and RecursiveCharacterTextSplitter is not None:
        try:
            logger.debug(
                f"Chunking via LangChain RecursiveCharacterTextSplitter (path={path}, ext={file_ext}, chars={content_len}, "
                f"chunk_chars={int(chunk_chars)}, overlap={int(chunk_overlap)})"
            )
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=int(chunk_chars),
                chunk_overlap=int(chunk_overlap),
                separators=list(separators),
                add_start_index=True,
            )
            docs = splitter.create_documents([content])
            for d in docs:
                start = int((d.metadata or {}).get("start_index", 0))
                end = start + len(d.page_content)
                spans2.append((start, end))
        except TypeError:
            # Older splitter versions may not support add_start_index
            logger.debug(
                f"LangChain splitter missing add_start_index; using split_text fallback (path={path}, ext={file_ext})"
            )
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=int(chunk_chars),
                chunk_overlap=int(chunk_overlap),
                separators=list(separators),
            )
            parts = splitter.split_text(content)
            # Best-effort: infer spans by searching forward
            cursor = 0
            for part in parts:
                pos = content.find(part, cursor)
                if pos < 0:
                    pos = content.find(part)
                if pos < 0:
                    continue
                spans2.append((pos, pos + len(part)))
                cursor = max(pos + len(part) - max(0, int(chunk_overlap)), 0)
        except Exception:
            spans2 = []

    if not spans2:
        logger.debug(
            f"Chunking via internal recursive splitter (path={path}, ext={file_ext}, chars={content_len}, "
            f"chunk_chars={int(chunk_chars)}, overlap={int(chunk_overlap)})"
        )
        spans2 = _fallback_recursive_split_spans(
            content,
            separators=separators,
            chunk_size=int(chunk_chars),
            chunk_overlap=int(chunk_overlap),
        )

    out2: List[Dict[str, Any]] = []
    for idx, (s, e) in enumerate(spans2):
        chunk_text = content[s:e].strip()
        if not chunk_text:
            continue
        out2.append(
            {
                "path": path,
                "chunk_index": idx,
                "start_line": _line_number_at(newline_positions, s) if newline_positions else 1,
                "end_line": _line_number_at(newline_positions, e) if newline_positions else 1,
                "content": chunk_text,
                "content_sha256": _sha256_text(chunk_text),
                "chunk_type": "recursive",
                "splitter": "recursive",
            }
        )
    logger.debug(f"Recursive chunking produced {len(out2)} chunks (path={path})")
    return out2


def _openai_client():
    # openai>=1.x
    from openai import OpenAI

    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
    return OpenAI(api_key=api_key) if api_key else OpenAI()


def embed_texts_openai(
    *,
    texts: Sequence[str],
    embedding_model: str,
    batch_size: int = 64,
    max_retries: int = 3,
    retry_backoff_sec: float = 1.5,
) -> List[List[float]]:
    if not texts:
        return []

    client = _openai_client()
    out: List[List[float]] = []
    i = 0
    t0 = time.time()
    while i < len(texts):
        batch = list(texts[i : i + batch_size])
        attempt = 0
        while True:
            try:
                resp = client.embeddings.create(model=embedding_model, input=batch)
                # Ensure order is preserved
                data = sorted(resp.data, key=lambda d: d.index)
                out.extend([list(d.embedding) for d in data])
                break
            except Exception as e:
                attempt += 1
                if attempt > max_retries:
                    raise
                sleep_s = retry_backoff_sec * (2 ** (attempt - 1)) + (0.1 * attempt)
                logger.warning(f"Embedding batch failed (attempt {attempt}/{max_retries}): {e}; sleeping {sleep_s:.1f}s")
                time.sleep(sleep_s)
        i += batch_size
    logger.debug(
        f"Embeddings created (model={embedding_model}, texts={len(texts)}, batch_size={int(batch_size)}) "
        f"in {(time.time() - t0):.3f}s"
    )
    return out


def _infer_embedding_dim(embedding_model: str) -> int:
    # Best-effort: support your current default model.
    # If you change models, set VECTOR_EMBEDDING_DIM env var (optional) or update this mapping.
    env_dim = os.getenv("VECTOR_EMBEDDING_DIM", "").strip()
    if env_dim.isdigit():
        return int(env_dim)
    if embedding_model == "text-embedding-ada-002":
        return 1536
    # Unknown; we will infer by embedding a tiny string at runtime in index/search.
    return 0


def index_project_chunks_to_pgvector(
    *,
    project_id: int,
    project_root: Path,
    files: Sequence[Dict[str, Any]],
    db: Session,
    progress_tracker=None,
    embedding_model: Optional[str] = None,
    chunk_chars: int = 1200,
    chunk_overlap: int = 150,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build and store embeddings for a project's code files.
    `files` should contain entries with: path, absolute_path, ext, size.
    """
    embedding_model = embedding_model or settings.OPENAI_EMBEDDING_MODEL

    # Build chunk list
    code_files = [f for f in files if f.get("absolute_path") and f.get("path")]
    if max_files is not None:
        code_files = code_files[: max_files]

    logger.info(
        f"Indexing project chunks to pgvector (project_id={project_id}, files={len(code_files)}, "
        f"chunk_chars={int(chunk_chars)}, overlap={int(chunk_overlap)}, embedding_model={embedding_model})"
    )

    if progress_tracker:
        progress_tracker.start_stage("embedding", "Splitting files into chunks and creating embeddings...")
        progress_tracker.set_total_files(len(code_files))

    chunks: List[Dict[str, Any]] = []
    files_read = 0
    for idx, fm in enumerate(code_files, start=1):
        rel_path = str(fm["path"])
        abs_path = Path(str(fm["absolute_path"]))
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Failed to read file for embedding: {rel_path}: {e}")
            continue
        if not content.strip():
            continue
        before = len(chunks)
        chunks.extend(
            split_text_to_code_chunks(
                path=rel_path,
                content=content,
                chunk_chars=chunk_chars,
                chunk_overlap=chunk_overlap,
            )
        )
        logger.debug(f"Split file into chunks (path={rel_path}, chunks_added={len(chunks) - before})")
        files_read += 1
        if progress_tracker:
            progress_tracker.update_file_progress(rel_path, idx)

    if not chunks:
        logger.info(f"No chunks produced; skipping embedding/indexing (project_id={project_id}, files_indexed={files_read})")
        return {"success": True, "files_indexed": files_read, "chunks_written": 0, "embedding_model": embedding_model}

    logger.info(f"Chunking complete (project_id={project_id}, files_indexed={files_read}, chunks={len(chunks)})")

    # Determine embedding dimension (either known mapping or inferred from a single embedding)
    dim = _infer_embedding_dim(embedding_model)
    if dim <= 0:
        dim = len(embed_texts_openai(texts=["dimension probe"], embedding_model=embedding_model, batch_size=1)[0])
    logger.debug(f"Using embedding dim={int(dim)} (model={embedding_model})")

    # Ensure schema
    db_conn = db.connection()
    ensure_pgvector_schema(db_conn, embedding_dim=dim)

    # Full reindex strategy: delete existing rows for project
    deleted = delete_project_chunks(db, project_id=project_id)
    logger.info(f"Deleted {deleted} existing chunks for project {project_id}")

    # Embed chunks (batch)
    texts = [c["content"] for c in chunks]
    t_embed = time.time()
    vectors = embed_texts_openai(texts=texts, embedding_model=embedding_model)
    logger.info(
        f"Embedding complete (project_id={project_id}, chunks={len(chunks)}, "
        f"elapsed={(time.time() - t_embed):.3f}s, model={embedding_model})"
    )
    if len(vectors) != len(chunks):
        raise RuntimeError(f"Embedding count mismatch: got {len(vectors)} vectors for {len(chunks)} chunks")

    # Insert rows using psycopg2 execute_values for speed
    insert_sql = """
        INSERT INTO project_code_chunks
          (project_id, path, chunk_index, start_line, end_line, content, content_sha256, embedding)
        VALUES %s
    """
    rows: List[Tuple[Any, ...]] = []
    for c, v in zip(chunks, vectors):
        rows.append(
            (
                project_id,
                c["path"],
                int(c["chunk_index"]),
                c.get("start_line"),
                c.get("end_line"),
                c["content"],
                c.get("content_sha256"),
                _vector_literal(v),
            )
        )

    # Chunked insert to avoid huge payloads
    batch = 2000
    t_insert = time.time()
    dbapi_conn = db.connection().connection
    with dbapi_conn.cursor() as cursor:
        execute_values(
            cursor,
            insert_sql,
            rows,
            template="(%s,%s,%s,%s,%s,%s,%s, (%s)::vector)",
            page_size=batch,
        )
    db.commit()
    logger.info(
        f"Inserted chunks (project_id={project_id}, rows={len(rows)}, batch={batch}, elapsed={(time.time() - t_insert):.3f}s)"
    )

    return {
        "success": True,
        "files_indexed": files_read,
        "chunks_written": len(rows),
        "embedding_dim": dim,
        "embedding_model": embedding_model,
        "project_root": str(project_root),
    }


def vector_search_project(
    *,
    db: Session,
    project_id: int,
    query: str,
    k: int = 12,
    embedding_model: Optional[str] = None,
    path_prefix: Optional[str] = None,
) -> List[ChunkRow]:
    embedding_model = embedding_model or settings.OPENAI_EMBEDDING_MODEL

    t0 = time.time()
    logger.debug(
        f"Vector search start (project_id={project_id}, k={int(k)}, path_prefix={path_prefix or ''}, "
        f"query_chars={len(query)}, model={embedding_model})"
    )
    # Infer dim to ensure schema exists; if unknown, infer from query embedding.
    qvec = embed_texts_openai(texts=[query], embedding_model=embedding_model, batch_size=1)[0]
    dim = _infer_embedding_dim(embedding_model)
    if dim <= 0:
        dim = len(qvec)

    db_conn = db.connection()
    ensure_pgvector_schema(db_conn, embedding_dim=dim)

    where = ["project_id = :project_id"]
    params: Dict[str, Any] = {
        "project_id": project_id,
        "q": _vector_literal(qvec),
        "k": int(k),
    }
    if path_prefix:
        where.append("path LIKE :path_prefix")
        params["path_prefix"] = f"{path_prefix}%"

    # Use L2 distance operator (<->) for broad compatibility.
    sql = text(
        f"""
        SELECT id, path, start_line, end_line, content,
               (embedding <-> (:q)::vector) AS score
        FROM project_code_chunks
        WHERE {' AND '.join(where)}
        ORDER BY embedding <-> (:q)::vector
        LIMIT :k
        """
    )

    res = db.execute(sql, params)
    rows = res.fetchall()
    out: List[ChunkRow] = []
    for r in rows:
        out.append(
            ChunkRow(
                id=int(r[0]),
                path=str(r[1]),
                start_line=(int(r[2]) if r[2] is not None else None),
                end_line=(int(r[3]) if r[3] is not None else None),
                content=str(r[4]),
                score=float(r[5]) if r[5] is not None else math.inf,
            )
        )
    logger.debug(f"Vector search done (project_id={project_id}, results={len(out)}, elapsed={(time.time() - t0):.3f}s)")
    return out


def format_chunks_for_prompt(chunks: Sequence[ChunkRow], *, max_chars: int = 12000) -> str:
    """
    Format chunk list into a single context string (bounded by max_chars).
    """
    parts: List[str] = []
    used = 0
    for c in chunks:
        loc = c.path
        if c.start_line is not None and c.end_line is not None:
            loc = f"{loc}:{c.start_line}-{c.end_line}"
        block = f"=== {loc} (dist={c.score:.4f}) ===\n{c.content}\n"
        if used + len(block) > max_chars and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts).strip()

