"""
Documentation generation service.

Reuses the multi-agent chat pipeline inputs (vector retrieval + structure/api/web + personas),
but synthesizes a long-form documentation artifact.
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from ..core.logging import get_logger
from ..models import Project
from .multi_agent_chat import run_multi_agent_documentation, load_project_persona_mode

logger = get_logger(__name__)


def _project_persona_mode(project: Project) -> str:
    """
    Derive persona_mode (sde|pm|both) from Project.personas (stored as JSON string).
    """
    try:
        personas = json.loads(project.personas or "[]") if isinstance(project.personas, str) else (project.personas or [])
    except Exception:
        personas = []
    s = {str(p).strip().lower() for p in (personas or [])}
    if "sde" in s and "pm" in s:
        return "both"
    if "sde" in s:
        return "sde"
    if "pm" in s:
        return "pm"
    return "both"


def generate_project_documentation_markdown(
    *,
    db: Session,
    project_id: int,
    user_id: int,
    config_id: Optional[int],
    persona_mode: str,
) -> str:
    """
    Generate markdown documentation for a project using the existing multi-agent pipeline.

    Implementation approach:
    - Load project and config
    - Force persona_mode to respect both: (selected persona_mode) AND (project personas)
    - Ask the multi-agent pipeline a "documentation prompt" question that produces long-form docs
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return "Project not found."

    # Persona enforcement: intersection of project personas and user selection.
    proj_mode = load_project_persona_mode(db, project_id)
    if proj_mode != "both" and persona_mode == "both":
        # Project restricts persona.
        persona_mode = proj_mode
    elif proj_mode != "both" and persona_mode != proj_mode:
        # If user selects a persona not in project, fall back to project persona.
        persona_mode = proj_mode

    # Documentation prompt. This drives the same pipeline but yields long-form output.
    question = (
        "Generate detailed project documentation.\n\n"
        "Requirements:\n"
        "- Provide an overview of what the project does\n"
        "- Describe architecture and main modules\n"
        "- Summarize key data flows and main APIs/endpoints\n"
        "- Explain how to run/setup (infer from repo context)\n"
        "- Include risks/limitations and next steps\n"
        "- Be consistent with the selected persona(s)\n"
        "- Output in Markdown with clear headings\n"
    )

    # Run the pipeline without persisting chat messages.
    # We pass config_id so the pipeline uses the selected saved config.
    # We also include an explicit persona hint in the question.
    question = f"{question}\nPersonaMode: {persona_mode}\n"

    # Use documentation mode, but force persona override via the graph state by embedding a tag in the prompt.
    # Persona is also enforced by the context node via persona_mode_override in the graph state (set below).
    result = run_multi_agent_documentation(
        db=db,
        project_id=project_id,
        user_id=user_id,
        question=question,
        config_id=config_id,
        persona_mode_override=persona_mode,
    )
    doc = (result.get("answer") or "").strip()
    return doc or "No documentation generated."

