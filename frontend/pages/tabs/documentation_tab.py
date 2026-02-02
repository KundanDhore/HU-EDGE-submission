"""
Documentation tab component.

Generates persona-aware project documentation using backend multi-agent pipeline,
persists results, and supports PDF export from the frontend.
"""

from __future__ import annotations

import re
import textwrap
import io
from typing import Dict, List, Optional, Tuple

import streamlit as st

from api.projects import get_projects
from api.analysis_configs import get_analysis_configs
from api.documentation import (
    generate_project_documentation,
    list_project_documentations,
    get_documentation,
    delete_documentation,
)
from core.logging import get_logger

logger = get_logger(__name__)


def render_documentation_tab():
    st.subheader("📄 Documentation")
    st.write("Generate persona-aware documentation for your project and export it as PDF.")

    # Initialize state
    st.session_state.setdefault("doc_selected_project_id", None)
    st.session_state.setdefault("doc_selected_config_id", None)
    st.session_state.setdefault("doc_selected_persona_mode", None)  # "sde"|"pm"|"both"
    st.session_state.setdefault("doc_current_doc_id", None)
    st.session_state.setdefault("doc_current_markdown", "")

    projects = get_projects()
    if not projects:
        st.info("You don't have any projects yet. Create one first!")
        return

    project_id = _render_project_selector(projects)
    if not project_id:
        return

    cfg_id = _render_config_selector()

    persona_mode = _render_persona_selector(projects, project_id)

    st.divider()
    _render_generate_controls(project_id=project_id, config_id=cfg_id, persona_mode=persona_mode)

    st.divider()
    _render_saved_docs(project_id=project_id)

    st.divider()
    _render_doc_viewer_and_export()


def _render_project_selector(projects: List[Dict]) -> Optional[int]:
    opts: List[Tuple[str, int]] = []
    for p in projects:
        label = f"{p.get('title', 'Untitled')} (ID: {p.get('id')})"
        if p.get("preprocessing_status") and p.get("preprocessing_status") != "completed":
            label += f" [{p.get('preprocessing_status')}]"
        opts.append((label, int(p["id"])))

    labels = [o[0] for o in opts]
    ids = [o[1] for o in opts]

    if st.session_state.get("doc_selected_project_id") not in ids:
        st.session_state["doc_selected_project_id"] = ids[0]

    idx = ids.index(int(st.session_state["doc_selected_project_id"]))
    selected_label = st.selectbox("Select Project", labels, index=idx, key="doc_project_select")
    selected_id = ids[labels.index(selected_label)]
    st.session_state["doc_selected_project_id"] = selected_id
    return selected_id


def _render_config_selector() -> Optional[int]:
    configs = get_analysis_configs()
    if not configs:
        st.info("No saved configurations yet. Create one in the Configuration tab.")
        st.session_state["doc_selected_config_id"] = None
        return None

    labels: List[str] = []
    ids: List[int] = []
    for cfg in configs:
        if cfg.get("id") is None:
            continue
        cfg_id = int(cfg["id"])
        labels.append(f"{'⭐ ' if cfg.get('is_default') else ''}{cfg.get('name','Untitled')} (ID: {cfg_id})")
        ids.append(cfg_id)

    if not ids:
        st.session_state["doc_selected_config_id"] = None
        return None

    default_id = next((int(c["id"]) for c in configs if c.get("is_default") and c.get("id") is not None), ids[0])
    if st.session_state.get("doc_selected_config_id") not in ids:
        st.session_state["doc_selected_config_id"] = default_id

    idx = ids.index(int(st.session_state["doc_selected_config_id"]))
    selected_label = st.selectbox("Select Configuration", labels, index=idx, key="doc_config_select")
    selected_id = ids[labels.index(selected_label)]
    st.session_state["doc_selected_config_id"] = selected_id

    selected_cfg = next((c for c in configs if int(c.get("id", -1)) == selected_id), None)
    if selected_cfg:
        st.caption(
            f"Depth: {selected_cfg.get('analysis_depth')} | "
            f"Verbosity: {selected_cfg.get('doc_verbosity')} | "
            f"Persona: {selected_cfg.get('persona_mode')}"
        )
    return selected_id


def _render_persona_selector(projects: List[Dict], project_id: int) -> str:
    proj = next((p for p in projects if int(p.get("id", -1)) == int(project_id)), {})
    personas = proj.get("personas") or []
    # Normalize e.g. ["SDE","PM"] -> {"sde","pm"}
    persona_set = {str(x).strip().lower() for x in personas if str(x).strip()}
    default_mode = "both" if {"sde", "pm"} <= persona_set else ("sde" if "sde" in persona_set else ("pm" if "pm" in persona_set else "both"))

    if st.session_state.get("doc_selected_persona_mode") not in ("sde", "pm", "both"):
        st.session_state["doc_selected_persona_mode"] = default_mode

    st.caption(f"Project personas: {', '.join(personas) if personas else 'None'}")

    mode = st.radio(
        "Generate documentation for",
        options=["sde", "pm", "both"],
        index=["sde", "pm", "both"].index(st.session_state["doc_selected_persona_mode"]),
        horizontal=True,
        key="doc_persona_mode_radio",
    )
    st.session_state["doc_selected_persona_mode"] = mode
    return mode


def _render_generate_controls(project_id: int, config_id: Optional[int], persona_mode: str) -> None:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("### Generate documentation")
        st.write("Produce long-form documentation.")
    with col2:
        if st.button("Generate", type="primary", use_container_width=True):
            try:
                with st.spinner("Generating documentation..."):
                    result = generate_project_documentation(
                        project_id=project_id,
                        config_id=config_id,
                        persona_mode=persona_mode,
                    )
                if result:
                    st.session_state["doc_current_doc_id"] = result.get("id")
                    st.session_state["doc_current_markdown"] = result.get("content_markdown", "") or ""
                    st.success("Documentation generated.")
                    st.rerun()
            except Exception as e:
                logger.error(f"Documentation generation failed: {e}", exc_info=True)
                st.error(f"Failed to generate documentation: {e}")


def _render_saved_docs(project_id: int) -> None:
    st.markdown("### Saved documentations")
    docs = list_project_documentations(project_id)
    if not docs:
        st.info("No saved documentations yet. Click Generate to create one.")
        return

    # Newest first
    options: List[Tuple[str, int]] = []
    for d in docs:
        doc_id = int(d["id"])
        persona = d.get("persona_mode", "both")
        cfg_id = d.get("analysis_config_id")
        created = d.get("created_at", "")
        label = f"Doc {doc_id} | persona={persona} | cfg={cfg_id if cfg_id is not None else 'default'} | {created}"
        options.append((label, doc_id))

    labels = [o[0] for o in options]
    ids = [o[1] for o in options]

    if st.session_state.get("doc_current_doc_id") not in ids:
        st.session_state["doc_current_doc_id"] = ids[0]

    idx = ids.index(int(st.session_state["doc_current_doc_id"]))
    selected_label = st.selectbox("Select saved documentation", labels, index=idx, key="doc_saved_select")
    selected_id = ids[labels.index(selected_label)]

    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("Load", use_container_width=True):
            doc = get_documentation(selected_id)
            if doc:
                st.session_state["doc_current_doc_id"] = selected_id
                st.session_state["doc_current_markdown"] = doc.get("content_markdown", "") or ""
                st.rerun()
    with colB:
        if st.button("Delete", use_container_width=True):
            if delete_documentation(selected_id):
                if st.session_state.get("doc_current_doc_id") == selected_id:
                    st.session_state["doc_current_doc_id"] = None
                    st.session_state["doc_current_markdown"] = ""
                st.success("Deleted.")
                st.rerun()


def _render_doc_viewer_and_export() -> None:
    st.markdown("### Documentation viewer")
    md = st.session_state.get("doc_current_markdown", "") or ""
    if not md.strip():
        st.info("Generate or load a documentation to view it here.")
        return

    st.markdown(md)

    st.markdown("### Export")
    st.caption("Export uses the currently displayed documentation.")
    try:
        pdf_bytes = _markdown_to_pdf_bytes(md)
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=f"{_safe_filename('documentation')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as e:
        logger.error(f"PDF export failed: {e}", exc_info=True)
        st.error(f"PDF export failed: {e}")


def _safe_filename(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_")
    return text[:80] or "documentation"


def _markdown_to_plain_text(markdown: str) -> str:
    """
    Best-effort markdown -> plain text conversion (no extra deps).
    """
    parts: List[str] = []
    for btype, content, level in _parse_markdown_blocks(markdown):
        if btype == "heading":
            parts.append(content.strip())
            parts.append("")
        elif btype == "bullet":
            parts.append("- " + content.strip())
        elif btype == "codeblock":
            parts.append(content.rstrip("\n"))
            parts.append("")
        elif btype == "paragraph":
            parts.append(content.strip())
            parts.append("")
        elif btype == "blank":
            parts.append("")
    out = "\n".join(parts)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _markdown_to_pdf_bytes(markdown: str) -> bytes:
    """
    Create a PDF from markdown using ReportLab (reliable, non-blank).
    """
    try:
        return _markdown_to_pdf_bytes_reportlab(markdown)
    except Exception:
        # Fallback to plain text if anything goes wrong.
        text = _markdown_to_plain_text(markdown)
        return _text_to_pdf_bytes(text)


def _markdown_to_pdf_bytes_reportlab(markdown: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, ListFlowable, ListItem
    from reportlab.lib import colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Documentation",
    )

    styles = getSampleStyleSheet()
    style_body = styles["BodyText"]
    style_body.wordWrap = "CJK"

    style_h = {
        1: styles["Heading1"],
        2: styles["Heading2"],
        3: styles["Heading3"],
        4: styles["Heading4"],
        5: styles["Heading5"],
        6: styles["Heading6"],
    }

    code_style = ParagraphStyle(
        name="CodeBlock",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=9,
        leading=11,
        backColor=colors.whitesmoke,
        borderColor=colors.lightgrey,
        borderWidth=0.5,
        borderPadding=6,
        leftIndent=0,
        rightIndent=0,
        spaceBefore=6,
        spaceAfter=6,
    )

    story: List[object] = []

    bullet_items: List[ListItem] = []

    def flush_bullets():
        nonlocal bullet_items
        if not bullet_items:
            return
        story.append(ListFlowable(bullet_items, bulletType="bullet", leftIndent=18))
        story.append(Spacer(1, 6))
        bullet_items = []

    for btype, content, level in _parse_markdown_blocks(markdown):
        if btype == "blank":
            flush_bullets()
            story.append(Spacer(1, 8))
            continue

        if btype == "heading":
            flush_bullets()
            lvl = int(level or 2)
            story.append(Paragraph(_md_inline_to_rl_html(content.strip()), style_h.get(lvl, styles["Heading2"])))
            story.append(Spacer(1, 6))
            continue

        if btype == "codeblock":
            flush_bullets()
            story.append(Preformatted(content or "", code_style))
            continue

        if btype == "bullet":
            # keep bullets grouped
            bullet_items.append(ListItem(Paragraph(_md_inline_to_rl_html(content.strip()), style_body)))
            continue

        if btype == "paragraph":
            flush_bullets()
            story.append(Paragraph(_md_inline_to_rl_html(content.strip()), style_body))
            story.append(Spacer(1, 6))
            continue

    flush_bullets()

    doc.build(story)
    return buf.getvalue()


def _md_inline_to_rl_html(text: str) -> str:
    """
    Convert a small subset of markdown inline syntax to ReportLab Paragraph HTML.
    Supports:
    - **bold**
    - `code`
    """
    # Escape XML-ish chars first
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Inline code: `...`
    text = re.sub(r"`([^`]+)`", r"<font face=\"Courier\">\1</font>", text)
    # Bold: **...**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


class _Run:
    __slots__ = ("text", "font", "size")

    def __init__(self, text: str, font: str, size: int):
        self.text = text
        self.font = font
        self.size = size


def _markdown_to_pdf_bytes_formatted(markdown: str) -> bytes:
    page_w, page_h = 612, 792  # Letter
    margin = 72
    max_w = page_w - 2 * margin

    # Fonts (standard PDF fonts)
    FONT_REG = "F1"  # Helvetica
    FONT_BOLD = "F2"  # Helvetica-Bold
    FONT_CODE = "F3"  # Courier

    base_size = 11
    heading_sizes = {1: 20, 2: 16, 3: 14, 4: 12, 5: 11, 6: 11}
    leading = 14
    code_leading = 14

    lines: List[List[_Run]] = []
    for btype, content, level in _parse_markdown_blocks(markdown):
        if btype == "blank":
            if lines and lines[-1]:
                lines.append([])
            continue

        if btype == "heading":
            size = heading_sizes.get(int(level or 2), 16)
            if lines and lines[-1]:
                lines.append([])
            lines.extend(_wrap_runs([_Run(content.strip(), FONT_BOLD, size)], max_w))
            lines.append([])
            continue

        if btype == "codeblock":
            if lines and lines[-1]:
                lines.append([])
            for ln in (content or "").splitlines() or [""]:
                # No wrapping for code; keep as-is (but still fit on page with crude wrap if extremely long)
                lines.extend(_wrap_runs([_Run(ln, FONT_CODE, base_size)], max_w))
            lines.append([])
            continue

        if btype == "bullet":
            runs = [_Run("- ", FONT_REG, base_size)] + _text_to_styled_runs(
                content.strip(), base_size, FONT_REG, FONT_BOLD, FONT_CODE
            )
            lines.extend(_wrap_runs(runs, max_w))
            lines.append([])
            continue

        if btype == "paragraph":
            runs = _text_to_styled_runs(content.strip(), base_size, FONT_REG, FONT_BOLD, FONT_CODE)
            if runs:
                lines.extend(_wrap_runs(runs, max_w))
                lines.append([])
            continue

    # Trim trailing empty lines
    while lines and not lines[-1]:
        lines.pop()

    return _runs_to_pdf_bytes(
        lines=lines,
        page_w=page_w,
        page_h=page_h,
        margin=margin,
        leading=leading,
        code_leading=code_leading,
        fonts={
            FONT_REG: "Helvetica",
            FONT_BOLD: "Helvetica-Bold",
            FONT_CODE: "Courier",
        },
    )


def _text_to_styled_runs(
    text: str,
    base_size: int,
    font_reg: str,
    font_bold: str,
    font_code: str,
) -> List[_Run]:
    # Very small inline parser:
    # - **bold**
    # - `code`
    out: List[_Run] = []
    i = 0
    bold = False
    code = False
    buf: List[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        s = "".join(buf)
        buf = []
        if s:
            font = font_code if code else (font_bold if bold else font_reg)
            out.append(_Run(s, font, base_size))

    while i < len(text):
        if text.startswith("**", i):
            flush()
            bold = not bold
            i += 2
            continue
        if text[i] == "`":
            flush()
            code = not code
            i += 1
            continue
        buf.append(text[i])
        i += 1
    flush()
    return out


def _parse_markdown_blocks(markdown: str) -> List[Tuple[str, str, int]]:
    """
    Parse markdown into blocks without external deps.
    Returns list of (block_type, content, level).
    block_type: heading|paragraph|bullet|codeblock|blank
    """
    lines = markdown.splitlines()
    out: List[Tuple[str, str, int]] = []
    i = 0

    def is_heading(s: str) -> Optional[Tuple[int, str]]:
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if not m:
            return None
        return (len(m.group(1)), m.group(2))

    def is_bullet(s: str) -> Optional[str]:
        m = re.match(r"^\s*[-*+]\s+(.*)$", s)
        return m.group(1) if m else None

    while i < len(lines):
        line = lines[i]

        if line.strip() == "":
            out.append(("blank", "", 0))
            i += 1
            continue

        if line.lstrip().startswith("```"):
            fence = line.lstrip()
            i += 1
            code_lines: List[str] = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            # skip closing fence if present
            if i < len(lines) and lines[i].lstrip().startswith("```"):
                i += 1
            out.append(("codeblock", "\n".join(code_lines), 0))
            continue

        hd = is_heading(line.strip())
        if hd:
            lvl, txt = hd
            out.append(("heading", txt.strip(), lvl))
            i += 1
            continue

        b = is_bullet(line)
        if b is not None:
            out.append(("bullet", b.strip(), 0))
            i += 1
            continue

        # paragraph: collect until blank or special
        para: List[str] = [line.strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if nxt.strip() == "":
                break
            if nxt.lstrip().startswith("```"):
                break
            if is_heading(nxt.strip()):
                break
            if is_bullet(nxt) is not None:
                break
            para.append(nxt.strip())
            i += 1
        out.append(("paragraph", " ".join(para).strip(), 0))

    return out


def _wrap_runs(runs: List[_Run], max_w: float) -> List[List[_Run]]:
    """
    Wrap runs into lines, approximating character widths.
    Splits only on spaces for simplicity.
    """
    lines: List[List[_Run]] = []
    cur: List[_Run] = []
    cur_w = 0.0

    def run_width(r: _Run) -> float:
        # crude width approximation per font
        per = 0.55
        if r.font == "F2":
            per = 0.58
        elif r.font == "F3":
            per = 0.60
        return len(r.text) * r.size * per

    def flush():
        nonlocal cur, cur_w
        lines.append(cur)
        cur = []
        cur_w = 0.0

    # Expand runs into space-separated chunks while keeping style
    chunks: List[_Run] = []
    for r in runs:
        if r.text == "\n":
            chunks.append(r)
            continue
        # preserve spaces as separators
        parts = re.split(r"(\s+)", r.text)
        for p in parts:
            if p == "":
                continue
            chunks.append(_Run(p, r.font, r.size))

    for ch in chunks:
        if ch.text == "\n":
            if cur or (lines and lines[-1]):
                flush()
            else:
                lines.append([])
            continue

        w = run_width(ch)
        if cur and cur_w + w > max_w and not ch.text.isspace():
            flush()
        cur.append(ch)
        cur_w += w

    if cur:
        flush()

    # Trim trailing whitespace-only runs per line
    for ln in lines:
        while ln and ln[-1].text.isspace():
            ln.pop()
    return lines


def _runs_to_pdf_bytes(
    *,
    lines: List[List[_Run]],
    page_w: int,
    page_h: int,
    margin: int,
    leading: int,
    code_leading: int,
    fonts: Dict[str, str],
) -> bytes:
    max_lines_per_page = int((page_h - 2 * margin) / leading)
    if max_lines_per_page <= 0:
        max_lines_per_page = 1

    pages: List[List[List[_Run]]] = []
    for i in range(0, len(lines), max_lines_per_page):
        pages.append(lines[i : i + max_lines_per_page])
    if not pages:
        pages = [[[]]]

    def esc_pdf(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Objects: 1 catalog, 2 pages, 3+ fonts, then page/content objects
    objects: List[bytes] = [b""]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")  # pages placeholder

    font_obj_ids: Dict[str, int] = {}
    for name, base in fonts.items():
        font_obj_ids[name] = len(objects)
        objects.append((f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} >>").encode("ascii"))

    page_obj_ids: List[int] = []

    for page_lines in pages:
        # Build content stream for this page
        y_start = page_h - margin
        stream_parts: List[str] = []
        stream_parts.append("BT")
        stream_parts.append(f"{margin} {y_start} Td")
        stream_parts.append(f"{leading} TL")

        first_line = True
        for ln in page_lines:
            if not first_line:
                stream_parts.append("T*")
            first_line = False

            # Start each line at left margin
            stream_parts.append(f"{-9999} 0 Td")  # reset hack
            stream_parts.append(f"{9999} 0 Td")   # reset hack
            stream_parts.append(f"{-9999} 0 Td")
            stream_parts.append(f"{9999} 0 Td")
            # Actually reset by setting absolute position via Tm
            # (a reliable reset, independent of the above)
            stream_parts.append(f"1 0 0 1 {margin} 0 Tm")

            x_adv = 0.0
            for r in ln:
                txt = esc_pdf(r.text)
                # Select font
                stream_parts.append(f"/{r.font} {r.size} Tf")
                # Move to x offset on the current line
                stream_parts.append(f"1 0 0 1 {margin + x_adv} 0 Tm")
                stream_parts.append(f"({txt}) Tj")
                # Advance (approx)
                per = 0.55
                if r.font == "F2":
                    per = 0.58
                elif r.font == "F3":
                    per = 0.60
                x_adv += len(r.text) * r.size * per

        stream_parts.append("ET")
        stream = ("\n".join(stream_parts) + "\n").encode("utf-8")

        content_id = len(objects)
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream")

        page_id = len(objects)
        page_obj_ids.append(page_id)

        # Font resources
        font_map = " ".join([f"/{fname} {obj_id} 0 R" for fname, obj_id in font_obj_ids.items()]).encode("ascii")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            + b"/Resources << /Font << " + font_map + b" >> >> "
            + b"/Contents " + str(content_id).encode("ascii") + b" 0 R >>"
        )

    kids = " ".join([f"{pid} 0 R" for pid in page_obj_ids]).encode("ascii")
    objects[2] = b"<< /Type /Pages /Kids [ " + kids + b" ] /Count " + str(len(page_obj_ids)).encode("ascii") + b" >>"

    # Emit PDF + xref
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: List[int] = [0]
    for obj_id in range(1, len(objects)):
        offsets.append(len(out))
        out.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        out.extend(objects[obj_id])
        out.extend(b"\nendobj\n")

    xref_start = len(out)
    out.extend(b"xref\n")
    out.extend(f"0 {len(objects)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, len(objects)):
        out.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))

    out.extend(b"trailer\n")
    out.extend(b"<< /Size " + str(len(objects)).encode("ascii") + b" /Root 1 0 R >>\n")
    out.extend(b"startxref\n")
    out.extend(f"{xref_start}\n".encode("ascii"))
    out.extend(b"%%EOF\n")
    return bytes(out)


def _text_to_pdf_bytes(text: str) -> bytes:
    # PDF page size: US Letter 612x792 points.
    page_w, page_h = 612, 792
    margin = 72
    font_size = 11
    leading = 14
    max_lines_per_page = int((page_h - 2 * margin) / leading)

    # Rough wrap (Helvetica ~ 0.55em avg width)
    wrap_width = 90
    raw_lines: List[str] = []
    for para in text.splitlines():
        if not para.strip():
            raw_lines.append("")
            continue
        raw_lines.extend(textwrap.wrap(para, width=wrap_width, replace_whitespace=False, drop_whitespace=False))

    pages: List[List[str]] = []
    for i in range(0, len(raw_lines), max_lines_per_page):
        pages.append(raw_lines[i : i + max_lines_per_page])
    if not pages:
        pages = [[""]]

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects: List[bytes] = [b""]  # obj 0 placeholder

    # 1: catalog, 2: pages, 3: font
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # pages object filled after page objects are known; placeholder for now
    objects.append(b"")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_obj_ids: List[int] = []
    content_obj_ids: List[int] = []

    for page_lines in pages:
        page_id = len(objects)
        content_id = page_id + 1
        page_obj_ids.append(page_id)
        content_obj_ids.append(content_id)

        # Content stream
        stream_lines: List[str] = []
        stream_lines.append("BT")
        stream_lines.append(f"/F1 {font_size} Tf")
        stream_lines.append(f"{margin} {page_h - margin} Td")
        stream_lines.append(f"{leading} TL")
        first = True
        for ln in page_lines:
            if not first:
                stream_lines.append("T*")
            first = False
            stream_lines.append(f"({esc(ln)}) Tj")
        stream_lines.append("ET")
        stream = ("\n".join(stream_lines) + "\n").encode("utf-8")
        objects.append(
            (
                b"<< /Length "
                + str(len(stream)).encode("ascii")
                + b" >>\nstream\n"
                + stream
                + b"endstream"
            )
        )

        # Page object references content
        objects.append(
            (
                b"<< /Type /Page /Parent 2 0 R "
                b"/MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 3 0 R >> >> "
                + b"/Contents "
                + str(content_id).encode("ascii")
                + b" 0 R >>"
            )
        )

        # Swap order: we appended content then page; but page_id assumed current.
        # Fix by swapping last two objects to match ids.
        objects[-1], objects[-2] = objects[-2], objects[-1]

    # Now fill pages object (2)
    kids = " ".join([f"{pid} 0 R" for pid in page_obj_ids]).encode("ascii")
    objects[2] = b"<< /Type /Pages /Kids [ " + kids + b" ] /Count " + str(len(page_obj_ids)).encode("ascii") + b" >>"

    # Build full PDF with xref
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: List[int] = [0]
    for i in range(1, len(objects)):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(objects[i])
        out.extend(b"\nendobj\n")

    xref_start = len(out)
    out.extend(b"xref\n")
    out.extend(f"0 {len(objects)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for i in range(1, len(objects)):
        out.extend(f"{offsets[i]:010d} 00000 n \n".encode("ascii"))

    out.extend(b"trailer\n")
    out.extend(b"<< /Size " + str(len(objects)).encode("ascii") + b" /Root 1 0 R >>\n")
    out.extend(b"startxref\n")
    out.extend(f"{xref_start}\n".encode("ascii"))
    out.extend(b"%%EOF\n")
    return bytes(out)

