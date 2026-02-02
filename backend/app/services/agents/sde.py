from __future__ import annotations

import os
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ...core.logging import get_logger
from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG

logger = get_logger(__name__)


def make_sde_agent_node():
    def node(state: ChatAgentState) -> Dict[str, Any]:
        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        persona_mode = cfg.get("persona_mode", "both")
        if not cfg.get("enable_sde_agent", True) or persona_mode not in ("sde", "both"):
            return {"sde_answer": "", "agent_trace": ["sde:skipped"]}

        logger.info("=== AGENT: SDEAgent ===")
        verbosity = cfg.get("doc_verbosity", "medium")

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

        prompt = (
            "You are an SDE (software engineer) assistant. Produce a technical answer.\n"
            "Use the analysis from other agents: file structure, API signatures, and web findings (if present).\n"
            f"Verbosity: {verbosity} (minimal=short, medium=normal, detailed=deep).\n\n"
            f"User question:\n{state['question']}\n\n"
            f"Retrieved code context (vector search):\n{state.get('retrieved_context','')}\n\n"
            f"File structure:\n{state.get('file_structure','')}\n\n"
            f"API signatures:\n{state.get('api_signatures','')}\n\n"
            f"Web findings:\n{state.get('web_findings','')}\n\n"
            "Return a structured response with:\n"
            "- Explanation\n- Key references (files/modules)\n- Suggested next steps\n"
        )

        config = {"callbacks": [state.get("langfuse_handler")]} if state.get("langfuse_handler") else {}
        resp = llm.invoke([HumanMessage(content=prompt)], config=config)
        return {"sde_answer": resp.content, "agent_trace": ["sde:done"]}

    return node

