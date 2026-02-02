from __future__ import annotations

import os
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from ...core.logging import get_logger
from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG
from ..code_analyser import analyze_tree_node

logger = get_logger(__name__)


def make_file_structure_agent_node(db: Session):
    def node(state: ChatAgentState) -> Dict[str, Any]:
        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        if not cfg.get("enable_file_structure_agent", True):
            return {"file_structure": "", "agent_trace": ["file_structure:skipped"]}

        # If cached value already present from context node, reuse it.
        if (state.get("file_structure") or "").strip():
            return {"file_structure": state.get("file_structure", ""), "agent_trace": ["file_structure:cache_hit"]}

        # If context failed earlier, don't crash by indexing required keys.
        if state.get("final_answer"):
            return {"file_structure": "", "agent_trace": ["file_structure:skipped_final_already_set"]}
        if not state.get("project_path"):
            return {"file_structure": "", "agent_trace": ["file_structure:missing_project_path"]}

        logger.info("=== AGENT: FileStructureAgent ===")
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
            "keywords": [],
            "summary": "",
            "analysis": state.get("analysis", {}),
            "langfuse_handler": state.get("langfuse_handler"),
        }

        sel = analyze_tree_node(local_state)
        local_state.update(sel)

        retrieved_paths: List[str] = []
        for c in (state.get("retrieved_chunks") or []):
            p = c.get("path")
            if p and p not in retrieved_paths:
                retrieved_paths.append(p)

        selected_files = local_state.get("selected_files", [])[:50]
        paths = retrieved_paths + [f.get("path", "") for f in selected_files if f.get("path")]

        prompt = (
            "You are an agent summarizing repository file structure for a developer.\n"
            "Given the user's question and a list of relevant file paths, produce:\n"
            "- a short description of key folders/modules involved\n"
            "- 5-15 most relevant files with a one-line role each (infer from path/name)\n"
            "Be concise.\n\n"
            f"User question:\n{state['question']}\n\n"
            f"Relevant paths:\n" + "\n".join(paths)
        )

        config = {"callbacks": [state.get("langfuse_handler")]} if state.get("langfuse_handler") else {}
        resp = llm.invoke([HumanMessage(content=prompt)], config=config)
        return {
            "file_structure": resp.content,
            "agent_trace": ["file_structure:done"],
        }

    return node

