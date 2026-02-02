from __future__ import annotations

import os
from typing import Any, Dict, List

from ...core.logging import get_logger
from ..chat_state import ChatAgentState, DEFAULT_CHAT_CONFIG

logger = get_logger(__name__)


def make_web_research_agent_node():
    def node(state: ChatAgentState) -> Dict[str, Any]:
        cfg = state.get("analysis_config", DEFAULT_CHAT_CONFIG)
        if not cfg.get("enable_web_augmented", False):
            return {"web_findings": "", "agent_trace": ["web:skipped"]}

        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            return {
                "web_findings": "Web research skipped: missing TAVILY_API_KEY.",
                "agent_trace": ["web:missing_api_key"],
            }

        logger.info("=== AGENT: WebResearchAgent ===")
        from tavily import TavilyClient

        analysis = state.get("analysis", {})
        framework = (analysis.get("framework") or "").strip()
        repo_type = (analysis.get("repository_type") or "").strip()

        topics: List[str] = []
        if framework:
            topics.append(f"{framework} best practices {state['question']}")
            topics.append(f"{framework} recommended patterns {repo_type}")
        else:
            topics.append(f"software best practices {state['question']}")

        max_results = int(cfg.get("web_max_results", 3))
        client = TavilyClient(api_key=api_key)
        results_text: List[str] = []

        for topic in topics[:2]:
            try:
                res = client.search(topic, max_results=max_results)
                items = res.get("results", []) if isinstance(res, dict) else res
                results_text.append(f"Topic: {topic}")
                for item in (items or [])[:max_results]:
                    title = item.get("title", "Source")
                    url = item.get("url", "")
                    content = (item.get("content") or "")[:400]
                    results_text.append(f"- {title} ({url})\n  {content}")
            except Exception as e:
                results_text.append(f"Topic: {topic}\n- Error: {e}")
        logger.info(f"=== AGENT: WebResearchAgen Executed === {results_text}")

        return {
            "web_findings": "\n".join(results_text),
            "agent_trace": ["web:done"],
        }

    return node

