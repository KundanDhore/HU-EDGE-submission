from __future__ import annotations

import os
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG


def make_documentation_aggregator_node():
    """
    Documentation-specific final synthesis.
    Produces long-form Markdown documentation (not a Q&A answer).
    """

    def node(state: ChatAgentState) -> Dict[str, Any]:
        if state.get("final_answer"):
            return {"final_answer": state["final_answer"], "agent_trace": ["doc_final:skipped_existing_answer"]}

        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        persona_mode = cfg.get("persona_mode", "both")
        verbosity = cfg.get("doc_verbosity", "medium")

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

        retrieved_context = state.get("retrieved_context", "")
        file_structure = state.get("file_structure", "")
        api_signatures = state.get("api_signatures", "")
        web_findings = state.get("web_findings", "")
        global_context = state.get("global_context", "")

        prompt = f"""You are generating project documentation in Markdown.

PersonaMode: {persona_mode}
Verbosity: {verbosity} (minimal=concise, medium=balanced, detailed=very detailed)

Write a complete documentation page with these sections (use Markdown headings):
1. Overview
2. Architecture (high-level)
3. Key modules/components (what they do)
4. API/endpoints summary (if applicable)
5. Data flow / execution flow
6. Setup & run instructions (infer from repository context)
7. Configuration (important knobs)
8. Risks / limitations
9. Next steps

Rules:
- Prefer concrete references to files/modules when you can infer them from the context.
- Do not invent details not supported by context; call out unknowns explicitly.
- If persona_mode includes SDE, include engineering details; if PM, include value/risk framing.

Context:
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
"""

        config = {"callbacks": [state.get("langfuse_handler")]} if state.get("langfuse_handler") else {}
        resp = llm.invoke([HumanMessage(content=prompt)], config=config)
        return {"final_answer": resp.content.strip(), "agent_trace": ["doc_final:done"]}

    return node

