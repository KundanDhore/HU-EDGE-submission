from __future__ import annotations

import operator
from typing import Any, Annotated, Dict, List, TypedDict


class ChatAgentState(TypedDict, total=False):
    project_id: int
    user_id: int
    session_id: int
    question: str
    # Optional per-turn configuration selection
    config_id: int
    # Execution mode: "chat" or "documentation"
    mode: str
    # Force persona mode for this run (sde|pm|both)
    persona_mode_override: str
    analysis_config: Dict[str, Any]
    # repo context
    project_path: str
    repo_tree: Dict
    all_files: List[Dict]
    analysis: Dict
    global_context: str
    selected_files: List[Dict]
    parsed_files: List[Dict]
    # retrieved chunk context (pgvector)
    retrieved_chunks: List[Dict[str, Any]]
    retrieved_context: str
    # agent outputs
    file_structure: str
    api_signatures: str
    web_findings: str
    sde_answer: str
    pm_answer: str
    final_answer: str
    # IMPORTANT: multiple parallel nodes append to this.
    # Use a reducer so concurrent writes are merged instead of erroring.
    agent_trace: Annotated[List[str], operator.add]
    # langfuse
    langfuse_handler: object


DEFAULT_CHAT_CONFIG: Dict[str, Any] = {
    "analysis_depth": "standard",  # quick|standard|deep
    "doc_verbosity": "medium",  # minimal|medium|detailed
    "enable_file_structure_agent": True,
    "enable_api_agent": True,
    "enable_web_augmented": False,
    "enable_sde_agent": True,
    "enable_pm_agent": True,
    "persona_mode": "both",  # sde|pm|both
    "web_max_results": 3,
    "agent_settings": {},
}

