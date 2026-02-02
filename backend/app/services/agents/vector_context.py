from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from ...core.logging import get_logger
from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG

logger = get_logger(__name__)


def make_vector_context_node(db: Session):
    """Retrieve vector-based code context once per question."""

    def node(state: ChatAgentState) -> Dict[str, Any]:
        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        agent_settings = cfg.get("agent_settings") or {}
        top_k = int(agent_settings.get("vector_top_k", 12))

        try:
            from ..vector_store import vector_search_project, format_chunks_for_prompt

            chunks = vector_search_project(db=db, project_id=state["project_id"], query=state["question"], k=top_k)
            context = format_chunks_for_prompt(chunks, max_chars=int(agent_settings.get("vector_max_chars", 12000)))

            chunk_dicts = [
                {
                    "id": c.id,
                    "path": c.path,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "score": c.score,
                }
                for c in chunks
            ]
            return {
                "retrieved_chunks": chunk_dicts,
                "retrieved_context": context,
                "agent_trace": ["vector_context:done"],
            }
        except Exception as e:
            logger.warning(f"Vector context retrieval failed: {e}", exc_info=True)
            return {
                "retrieved_chunks": [],
                "retrieved_context": "",
                "agent_trace": ["vector_context:failed"],
            }

    return node

