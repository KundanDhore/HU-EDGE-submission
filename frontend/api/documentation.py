"""
API client for project documentation generation and retrieval.
"""

from typing import Dict, List, Optional

import streamlit as st

from api.client import get_client, handle_http_error
from core.logging import get_logger

logger = get_logger(__name__)


def generate_project_documentation(
    *,
    project_id: int,
    config_id: Optional[int] = None,
    persona_mode: str = "both",
) -> Optional[Dict]:
    user_email = st.session_state.get("email", "unknown")
    logger.info(
        f"Generate documentation | project={project_id} | config_id={config_id} | persona={persona_mode} | user={user_email}"
    )
    try:
        payload: Dict[str, object] = {"persona_mode": persona_mode}
        if config_id is not None:
            payload["config_id"] = int(config_id)
        with get_client(timeout=180.0) as client:
            resp = client.post(f"/documentation/projects/{int(project_id)}/generate", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Generate documentation", logger))
        return None


def list_project_documentations(project_id: int) -> List[Dict]:
    try:
        with get_client() as client:
            resp = client.get(f"/documentation/projects/{int(project_id)}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "List documentations", logger))
        return []


def get_documentation(doc_id: int) -> Optional[Dict]:
    try:
        with get_client() as client:
            resp = client.get(f"/documentation/{int(doc_id)}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Get documentation", logger))
        return None


def delete_documentation(doc_id: int) -> bool:
    try:
        with get_client() as client:
            resp = client.delete(f"/documentation/{int(doc_id)}")
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(handle_http_error(e, "Delete documentation", logger))
        return False

