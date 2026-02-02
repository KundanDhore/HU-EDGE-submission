"""
Milestone 4: Multi-agent chat orchestration using LangGraph.

Implements at least 5 distinct agent roles for chat responses:
- FileStructureAgent: summarize repo structure relevant to question
- APISignatureAgent: extract API/route signatures relevant to question
- WebResearchAgent: fetch best-practices online (Tavily) when enabled
- SDEAgent: produce technical engineering response
- PMAgent: produce business-focused response

The graph runs analysis agents (file structure + API) in parallel where possible,
then optional web research, then persona-specific generation.
"""
from __future__ import annotations

import os
import operator
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from ..core.logging import get_logger
from ..core.config import settings
from ..models import Project, AnalysisConfiguration
from ..utils.langfuse_config import get_langfuse_handler_for_trace
from .chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG
from .code_analyser import fetch_repo_metadata_node, global_context_node, analyze_tree_node, fetch_and_parse_node
from .agents.vector_context import make_vector_context_node
from .agents.file_structure import make_file_structure_agent_node
from .agents.api_signatures import make_api_signature_agent_node
from .agents.web_research import make_web_research_agent_node
from .agents.sde import make_sde_agent_node
from .agents.pm import make_pm_agent_node
from .agents.final_aggregator import make_final_aggregator_node
from .agents.documentation_aggregator import make_documentation_aggregator_node

logger = get_logger(__name__)

# In-memory caches to avoid recomputing project-static context each chat turn.
# Keyed by (project_id, project_uuid) so re-uploaded/reindexed projects invalidate naturally.
_PROJECT_CONTEXT_CACHE: Dict[Tuple[int, str], Dict[str, Any]] = {}
# Keyed by (session_id, project_uuid) for per-session cached agent outputs.
_SESSION_ARTIFACT_CACHE: Dict[Tuple[int, str], Dict[str, Any]] = {}

def _config_to_dict(cfg: AnalysisConfiguration) -> Dict[str, Any]:
    return {
        "analysis_depth": cfg.analysis_depth,
        "doc_verbosity": cfg.doc_verbosity,
        "enable_file_structure_agent": cfg.enable_file_structure_agent,
        "enable_api_agent": cfg.enable_api_agent,
        "enable_web_augmented": cfg.enable_web_augmented,
        "enable_sde_agent": cfg.enable_sde_agent,
        "enable_pm_agent": cfg.enable_pm_agent,
        "persona_mode": cfg.persona_mode or "both",
        "agent_settings": cfg.agent_settings or {},
        "web_max_results": int((cfg.agent_settings or {}).get("web_max_results", 3)),
    }


def _load_analysis_config(db: Session, user_id: int, config_id: Optional[int] = None) -> Dict[str, Any]:
    """Load config by id (if provided) else user's default; fall back to defaults."""
    cfg: Optional[AnalysisConfiguration] = None
    if config_id is not None:
        cfg = (
            db.query(AnalysisConfiguration)
            .filter(
                AnalysisConfiguration.id == int(config_id),
                AnalysisConfiguration.user_id == user_id,
            )
            .first()
        )
        if cfg:
            return _config_to_dict(cfg)

    cfg = (
        db.query(AnalysisConfiguration)
        .filter(
            AnalysisConfiguration.user_id == user_id,
            AnalysisConfiguration.is_default == True,
        )
        .first()
    )
    if not cfg:
        return dict(DEFAULT_CHAT_CONFIG)
    return _config_to_dict(cfg)


def load_project_persona_mode(db: Session, project_id: int) -> str:
    """
    Derive persona_mode (sde|pm|both) from Project.personas.
    Used to enforce persona constraints for documentation generation.
    """
    import json

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return "both"
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


def _project_analysis_from_db(project: Project) -> Dict[str, Any]:
    """Construct analysis dict similar to code_analyser QA workflow."""
    import json

    analysis = {}
    if project.analysis_metadata:
        analysis_meta = json.loads(project.analysis_metadata)
        analysis = {
            "repository_type": project.repository_type,
            "framework": project.framework,
            "entry_points": json.loads(project.entry_points) if project.entry_points else [],
            "total_files": project.total_files,
            "total_lines_of_code": project.total_lines_of_code,
            "languages_breakdown": json.loads(project.languages_breakdown) if project.languages_breakdown else {},
            "dependencies": json.loads(project.dependencies) if project.dependencies else [],
            "api_endpoints_count": project.api_endpoints_count,
            "models_count": project.models_count,
            **analysis_meta,
        }
    return analysis


def _ensure_repo_context_node(db: Session):
    """Create node that loads project + config and prepares repo context."""

    def node(state: ChatAgentState) -> Dict[str, Any]:
        # If a previous step already produced a final answer, do not continue.
        # (Prevents downstream agents from crashing when required context is missing.)
        if state.get("final_answer"):
            return {"agent_trace": ["context:skipped_final_already_set"]}

        project_id = state["project_id"]
        user_id = state["user_id"]
        question = state["question"]
        session_id = state.get("session_id")

        logger.info(f"=== CHAT CONTEXT NODE | project={project_id} user={user_id} ===")

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {
                "final_answer": "Project not found.",
                "agent_trace": ["context:project_not_found"],
            }

        analysis_config = _load_analysis_config(db, user_id, state.get("config_id"))
        # Allow per-run override (used by documentation generation / project personas).
        if state.get("persona_mode_override") in ("sde", "pm", "both"):
            analysis_config["persona_mode"] = state["persona_mode_override"]

        # Resolve project path like code_analyser: backend/files/projects/{project_id}_{uuid}
        from pathlib import Path

        files_dir = Path(settings.PROJECT_FILES_DIR)
        project_dirs = list(files_dir.glob(f"{project_id}_*"))
        if not project_dirs:
            return {
                "final_answer": "Project directory not found on disk. Re-upload or re-index the project.",
                "agent_trace": ["context:project_dir_missing"],
            }

        project_path = project_dirs[0]

        analysis = _project_analysis_from_db(project)

        # Reuse cached repo_tree/all_files/global_context across chat turns for this project version.
        cache_key = (project_id, str(project.uuid))
        cached = _PROJECT_CONTEXT_CACHE.get(cache_key)

        # Create a new Langfuse trace per user request.
        # All agent LLM calls will be spans under this trace via shared handler.
        langfuse_handler = state.get("langfuse_handler")
        if not langfuse_handler:
            # Fallback: create a handler with a fresh trace id
            trace_id = str(uuid.uuid4())
            langfuse_handler = get_langfuse_handler_for_trace(trace_id, update_trace=True)

        if cached:
            repo_tree = cached.get("repo_tree", {})
            all_files = cached.get("all_files", [])
            global_ctx = cached.get("global_context", analysis.get("global_context", ""))
            agent_trace = ["context:cache_hit"]
        else:
            # Build minimal state for code_analyser nodes
            base_state: Dict[str, Any] = {
                "messages": [HumanMessage(content=question)],
                "project_id": project_id,
                "project_path": str(project_path),
                "repo_tree": {},
                "global_context": analysis.get("global_context", ""),
                "selected_files": [],
                "parsed_files": [],
                "all_files": [],
                "intent": "chat",
                "keywords": [],
                "summary": "",
                "analysis": analysis,
                "langfuse_handler": langfuse_handler,
            }

            # Fetch file metadata and global context (expensive on big repos)
            t0 = time.time()
            tree_result = fetch_repo_metadata_node(base_state)  # returns repo_tree, all_files
            base_state.update(tree_result)

            ctx_result = global_context_node(base_state)
            base_state.update(ctx_result)
            logger.info(f"Context built (uncached) in {(time.time()-t0):.2f}s | project={project_id}")

            repo_tree = base_state.get("repo_tree", {})
            all_files = base_state.get("all_files", [])
            global_ctx = base_state.get("global_context", "")

            _PROJECT_CONTEXT_CACHE[cache_key] = {
                "repo_tree": repo_tree,
                "all_files": all_files,
                "global_context": global_ctx,
            }
            agent_trace = ["context:cache_miss_built"]

        # Attach cached per-session artifacts if present (file_structure/api_signatures).
        if session_id:
            sess_key = (int(session_id), str(project.uuid))
            sess_cached = _SESSION_ARTIFACT_CACHE.get(sess_key, {})
        else:
            sess_key = None
            sess_cached = {}

        return {
            "analysis_config": analysis_config,
            "project_path": str(project_path),
            "analysis": analysis,
            "repo_tree": repo_tree,
            "all_files": all_files,
            "global_context": global_ctx,
            "langfuse_handler": langfuse_handler,
            "file_structure": sess_cached.get("file_structure", ""),
            "api_signatures": sess_cached.get("api_signatures", ""),
            "agent_trace": agent_trace,
        }

    return node


def _vector_context_node(db: Session):
    return make_vector_context_node(db)


def _file_structure_agent_node(db: Session):
    return make_file_structure_agent_node(db)


def _api_signature_agent_node(db: Session):
    return make_api_signature_agent_node(db)


def _web_research_agent_node():
    return make_web_research_agent_node()


def _sde_agent_node():
    return make_sde_agent_node()


def _pm_agent_node():
    return make_pm_agent_node()


def _final_aggregator_node():
    return make_final_aggregator_node()

def _documentation_aggregator_node():
    return make_documentation_aggregator_node()

def build_multi_agent_chat_graph(db: Session):
    """
    Build and compile the multi-agent chat graph.

    Uses a closure over `db` for DB access in the context node.
    """
    workflow = StateGraph(ChatAgentState)

    workflow.add_node("context", _ensure_repo_context_node(db))
    workflow.add_node("vector_context", _vector_context_node(db))

    # Parallel analysis agents
    workflow.add_node("file_structure", _file_structure_agent_node(db))
    workflow.add_node("api", _api_signature_agent_node(db))

    # Web research, then persona agents
    workflow.add_node("web", _web_research_agent_node())
    workflow.add_node("sde", _sde_agent_node())
    workflow.add_node("pm", _pm_agent_node())
    workflow.add_node("final", _final_aggregator_node())
    workflow.add_node("doc_final", _documentation_aggregator_node())

    workflow.add_edge(START, "context")

    # Retrieve vector context once, then fan-out to analysis agents
    workflow.add_edge("context", "vector_context")
    workflow.add_edge("vector_context", "file_structure")
    workflow.add_edge("vector_context", "api")

    # Fan-in: web research waits for both
    workflow.add_edge("file_structure", "web")
    workflow.add_edge("api", "web")

    # Then persona agents (sequential; they can be parallelized later if needed)
    workflow.add_edge("web", "sde")
    workflow.add_edge("sde", "pm")
    # Choose final synthesis based on mode.
    def _final_router(state: ChatAgentState) -> str:
        return "doc_final" if state.get("mode") == "documentation" else "final"

    workflow.add_conditional_edges("pm", _final_router, {"final": "final", "doc_final": "doc_final"})
    workflow.add_edge("final", END)
    workflow.add_edge("doc_final", END)

    return workflow.compile()


def run_multi_agent_chat(
    db: Session,
    project_id: int,
    user_id: int,
    session_id: Optional[int],
    question: str,
    config_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute the multi-agent chat workflow and return response + metadata."""
    graph = build_multi_agent_chat_graph(db)

    trace_id = uuid.uuid4().hex
    langfuse = get_client()
    with langfuse.start_as_current_observation(
        as_type="span",
        name="multi_agent_chat",
        trace_context={"trace_id": trace_id},
        input=question,
    ) as root_span:
        handler = CallbackHandler(
            trace_context={"trace_id": trace_id, "parent_span_id": root_span.id},
            update_trace=True,
        )
        handler.trace_name = "multi_agent_chat"
        handler.user_id = str(user_id)
        if session_id is not None:
            handler.session_id = str(session_id)
        handler.metadata = {
            "project_id": project_id,
            "user_id": user_id,
            "analysis_depth": None,
            "persona_mode": None,
        }
        handler.tags = ["multi-agent", "chat", "milestone-4"]

        initial_state: ChatAgentState = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": int(session_id) if session_id is not None else None,
            "question": question,
            "config_id": int(config_id) if config_id is not None else None,
            "mode": "chat",
            "persona_mode_override": None,
            "agent_trace": [],
            "langfuse_handler": handler,
        }

        final_state = graph.invoke(initial_state)
        root_span.update(output=final_state.get("final_answer", ""))

    # Store per-session artifacts for reuse on subsequent turns.
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project and session_id is not None:
            sess_key = (int(session_id), str(project.uuid))
            _SESSION_ARTIFACT_CACHE[sess_key] = {
                "file_structure": final_state.get("file_structure", ""),
                "api_signatures": final_state.get("api_signatures", ""),
            }
    except Exception:
        # Cache is a best-effort optimization; never fail chat because of it.
        pass

    return {
        "answer": final_state.get("final_answer", ""),
        "agent_trace": final_state.get("agent_trace", []),
        "file_structure": final_state.get("file_structure", ""),
        "api_signatures": final_state.get("api_signatures", ""),
        "web_findings": final_state.get("web_findings", ""),
        "sde_answer": final_state.get("sde_answer", ""),
        "pm_answer": final_state.get("pm_answer", ""),
    }


def run_multi_agent_documentation(
    *,
    db: Session,
    project_id: int,
    user_id: int,
    question: str,
    config_id: Optional[int] = None,
    persona_mode_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute the same multi-agent graph in documentation mode.
    """
    graph = build_multi_agent_chat_graph(db)
    trace_id = uuid.uuid4().hex
    langfuse = get_client()
    with langfuse.start_as_current_observation(
        as_type="span",
        name="multi_agent_documentation",
        trace_context={"trace_id": trace_id},
        input=question,
    ) as root_span:
        handler = CallbackHandler(
            trace_context={"trace_id": trace_id, "parent_span_id": root_span.id},
            update_trace=True,
        )
        handler.trace_name = "multi_agent_documentation"
        handler.user_id = str(user_id)
        handler.metadata = {
            "project_id": project_id,
            "user_id": user_id,
            "analysis_depth": None,
            "persona_mode": persona_mode_override,
        }
        handler.tags = ["multi-agent", "documentation", "milestone-4"]

        initial_state: ChatAgentState = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": None,
            "question": question,
            "config_id": int(config_id) if config_id is not None else None,
            "mode": "documentation",
            "persona_mode_override": persona_mode_override,
            "agent_trace": [],
            "langfuse_handler": handler,
        }
        final_state = graph.invoke(initial_state)
        root_span.update(output=final_state.get("final_answer", ""))
    return {
        "answer": final_state.get("final_answer", ""),
        "agent_trace": final_state.get("agent_trace", []),
        "file_structure": final_state.get("file_structure", ""),
        "api_signatures": final_state.get("api_signatures", ""),
        "web_findings": final_state.get("web_findings", ""),
        "sde_answer": final_state.get("sde_answer", ""),
        "pm_answer": final_state.get("pm_answer", ""),
    }

