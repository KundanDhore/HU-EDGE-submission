from __future__ import annotations

import os
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from ...core.logging import get_logger
from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG
from ..code_analyser import analyze_tree_node, fetch_and_parse_node

logger = get_logger(__name__)


def make_api_signature_agent_node(db: Session):
    def node(state: ChatAgentState) -> Dict[str, Any]:
        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        if not cfg.get("enable_api_agent", True):
            return {"api_signatures": "", "agent_trace": ["api:skipped"]}

        # If cached value already present from context node, reuse it.
        if (state.get("api_signatures") or "").strip():
            return {"api_signatures": state.get("api_signatures", ""), "agent_trace": ["api:cache_hit"]}

        # If context failed earlier, don't crash by indexing required keys.
        if state.get("final_answer"):
            return {"api_signatures": "", "agent_trace": ["api:skipped_final_already_set"]}
        if not state.get("project_path"):
            return {
                "api_signatures": "",
                "agent_trace": ["api:missing_project_path"],
            }

        logger.info("=== AGENT: APISignatureAgent ===")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

        local_state: Dict[str, Any] = {
            "messages": [HumanMessage(content=state["question"])],
            "project_id": state["project_id"],
            "project_path": state["project_path"],
            "repo_tree": state.get("repo_tree", {}),
            "global_context": state.get("global_context", ""),
            "selected_files": [],
            "parsed_files": [],
            "all_files": state.get("all_files", []),
            "intent": "chat",
            "keywords": ["api", "route", "endpoint", "controller"],
            "summary": "",
            "analysis": state.get("analysis", {}),
            "langfuse_handler": state.get("langfuse_handler"),
        }

        context = (state.get("retrieved_context") or "").strip()
        if not context:
            sel = analyze_tree_node(local_state)
            local_state.update(sel)
            parsed = fetch_and_parse_node(local_state)
            local_state.update(parsed)

            parsed_files = local_state.get("parsed_files", [])[:10]
            context_parts: List[str] = []
            for pf in parsed_files:
                content = pf.get("content", "")
                if len(content) > 8000:
                    content = content[:8000] + "\n... (truncated)"
                context_parts.append(f"=== {pf.get('path')} ===\n{content}")
            context = "\n\n".join(context_parts)

        prompt = (
            "You are an agent extracting API signatures and endpoints.\n"
            "From the code context, extract:\n"
            "- HTTP endpoints (method + path) if backend\n"
            "- Public function signatures / classes relevant to API\n"
            "- Input/output schemas if visible\n"
            "Return as bullet list grouped by file.\n\n"
            f"User question:\n{state['question']}\n\n"
            f"Code context:\n{context}"
        )

        config = {"callbacks": [state.get("langfuse_handler")]} if state.get("langfuse_handler") else {}
        resp = llm.invoke([HumanMessage(content=prompt)], config=config)
        return {
            "api_signatures": resp.content,
            "agent_trace": ["api:done"],
        }

    return node

