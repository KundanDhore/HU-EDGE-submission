"""
Re-index pgvector code chunks for one or more projects.

This rebuilds `project_code_chunks` by:
- scanning the project folder on disk
- splitting into chunks (Tree-sitter first, recursive fallback)
- embedding chunks
- deleting existing rows for that project_id and inserting the new rows

Usage:
  python scripts/reindex_pgvector.py                 # reindex all projects
  python scripts/reindex_pgvector.py 1               # reindex project 1
  python scripts/reindex_pgvector.py 1 2 3           # reindex multiple projects
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.db.session import SessionLocal
from app import models
from app.services.vector_store import index_project_chunks_to_pgvector


SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    "coverage",
    ".pytest_cache",
    ".egg-info",
    ".tox",
    ".mypy_cache",
}

SKIP_EXTENSIONS = {
    ".min.js",
    ".map",
    ".lock",
    ".log",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".woff",
    ".ttf",
}

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".cs",
    ".md",
    ".json",
    ".yaml",
    ".yml",
}


def _resolve_project_root(project_id: int, project_uuid: str) -> Optional[Path]:
    base = Path(settings.PROJECT_FILES_DIR)
    preferred = base / f"{project_id}_{project_uuid}"
    if preferred.exists():
        return preferred

    # Fallback: find any folder matching "<id>_*" and pick most recently modified.
    if base.exists():
        matches = sorted(
            base.glob(f"{project_id}_*"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        if matches:
            return matches[0]

    # Last fallback: sometimes older code used just "<id>"
    legacy = base / str(project_id)
    if legacy.exists():
        return legacy

    return None


def _scan_project_files(project_root: Path) -> List[Dict]:
    out: List[Dict] = []
    for file_path in project_root.rglob("*"):
        if not file_path.is_file():
            continue

        # Skip if in ignored directories
        if any(part in SKIP_DIR_NAMES for part in file_path.parts):
            continue

        ext = file_path.suffix.lower()
        if ext in SKIP_EXTENSIONS:
            continue
        if ext not in CODE_EXTENSIONS:
            continue

        try:
            size = file_path.stat().st_size
        except Exception:
            size = 0

        rel_path = file_path.relative_to(project_root)
        out.append(
            {
                "path": str(rel_path),
                "absolute_path": str(file_path),
                "ext": ext,
                "size": size,
            }
        )
    return out


def main(argv: List[str]) -> int:
    ids: List[int] = []
    for a in argv[1:]:
        try:
            ids.append(int(a))
        except ValueError:
            print(f"Invalid project id: {a}", file=sys.stderr)
            return 2

    db = SessionLocal()
    try:
        q = db.query(models.Project).order_by(models.Project.id)
        if ids:
            q = q.filter(models.Project.id.in_(ids))
        projects = q.all()
        if not projects:
            print("No matching projects found.")
            return 1

        for p in projects:
            root = _resolve_project_root(p.id, p.uuid)
            if not root:
                print(f"[project {p.id}] skipped: could not locate project folder for uuid={p.uuid}")
                continue

            files = _scan_project_files(root)
            print(f"[project {p.id}] indexing from {root} | files={len(files)}")
            res = index_project_chunks_to_pgvector(
                project_id=p.id,
                project_root=root,
                files=files,
                db=db,
            )
            print(
                f"[project {p.id}] done | chunks_written={res.get('chunks_written')} | "
                f"embedding_model={res.get('embedding_model')} | dim={res.get('embedding_dim')}"
            )

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

