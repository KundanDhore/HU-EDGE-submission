from __future__ import annotations

import os
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG


def make_final_aggregator_node():
    def node(state: ChatAgentState) -> Dict[str, Any]:
        # If an upstream node already produced a terminal answer (e.g. missing project dir),
        # do not overwrite it with an LLM synthesis step.
        if state.get("final_answer"):
            return {"final_answer": state["final_answer"], "agent_trace": ["final:skipped_existing_answer"]}

        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        persona_mode = cfg.get("persona_mode", "both")
        verbosity = cfg.get("doc_verbosity", "medium")

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

        retrieved_context = state.get("retrieved_context", "No code context available")
        file_structure = state.get("file_structure", "No file structure available")
        api_signatures = state.get("api_signatures", "No API signatures available")
        web_findings = state.get("web_findings", "No web findings available")
        global_context = state.get("global_context", "No global context available")
        question = state.get("question", state.get("user_query", ""))

        synth_prompt = f"""You are the final answer synthesizer for a multi-agent code assistant.

        **Your Task:**
        Generate a direct, helpful answer to the user's code-related question using the aggregated context below.

        **Guidelines:**
        - Use ONLY the provided context; cite specific files/line numbers
        - If context is insufficient, explicitly state what's missing
        - Adapt verbosity: {verbosity} (minimal=concise, medium=balanced, detailed=comprehensive)
        - Maintain technical accuracy for code explanations

        **User Question:**
        {question}

        **Available Context:**

        <retrieved_code>
        {retrieved_context}
        </retrieved_code>

        <file_structure>
        {file_structure}
        </file_structure>

        <api_signatures>
        {api_signatures}
        </api_signatures>

        <web_findings>
        {web_findings}
        </web_findings>

        <global_context>
        {global_context}
        </global_context>

        **Response Format:**
        1. Clear, actionable response
        2.Referenced files with line ranges (e.g., `path/to/file.py:L10-L25`)
        3.If applicable, show relevant snippets
        4.Concrete actions or follow-up questions

        Now provide your structured response:"""
        config = {"callbacks": [state.get("langfuse_handler")]} if state.get("langfuse_handler") else {}
        synth = llm.invoke([HumanMessage(content=synth_prompt)], config=config)

        parts: List[str] = []
        parts.append(synth.content)

        if persona_mode in ("sde", "both") and state.get("sde_answer"):
            parts.append("## SDE Answer\n" + state["sde_answer"])
        if persona_mode in ("pm", "both") and state.get("pm_answer"):
            parts.append("## PM Answer\n" + state["pm_answer"])

        return {"final_answer": "\n\n".join(parts).strip(), "agent_trace": ["final:synth_done"]}

    return node

