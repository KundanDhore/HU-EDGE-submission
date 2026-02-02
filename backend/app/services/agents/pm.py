from __future__ import annotations

import os
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ...core.logging import get_logger
from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG

logger = get_logger(__name__)


def make_pm_agent_node():
    def node(state: ChatAgentState) -> Dict[str, Any]:
        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        persona_mode = cfg.get("persona_mode", "both")
        if not cfg.get("enable_pm_agent", True) or persona_mode not in ("pm", "both"):
            return {"pm_answer": "", "agent_trace": ["pm:skipped"]}

        logger.info("=== AGENT: PMAgent ===")
        verbosity = cfg.get("doc_verbosity", "medium")

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

        prompt = (
            "You are a product manager assistant. Produce a business-focused answer.\n"
            "Use the technical analysis inputs but translate into capabilities, risks, and user impact.\n"
            f"Verbosity: {verbosity}.\n\n"
            f"User question:\n{state['question']}\n\n"
            f"Retrieved code context (vector search):\n{state.get('retrieved_context','')}\n\n"
            f"Key structure:\n{state.get('file_structure','')}\n\n"
            f"Key APIs/features:\n{state.get('api_signatures','')}\n\n"
            f"Web findings:\n{state.get('web_findings','')}\n\n"
            "Return a structured response with:\n"
            "- What it does (in plain language)\n- User value\n- Risks/unknowns\n- Recommended product actions\n"
        )

        config = {"callbacks": [state.get("langfuse_handler")]} if state.get("langfuse_handler") else {}
        resp = llm.invoke([HumanMessage(content=prompt)], config=config)
        return {"pm_answer": resp.content, "agent_trace": ["pm:done"]}

    return node

