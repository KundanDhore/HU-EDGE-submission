"""
Code search API endpoints.
"""
import streamlit as st
from typing import Optional, Dict
from core.logging import get_logger
from api.client import get_client, handle_http_error

logger = get_logger(__name__)


def search_code(project_id: int, query: str, top_k: int = 10, language: Optional[str] = None) -> Optional[Dict]:
    """
    Search code using Code-Analyser.
    
    Args:
        project_id: Project ID to search
        query: Search query
        top_k: Number of results
        language: Optional language filter
    
    Returns:
        Search results dictionary or None
    """
    user_email = st.session_state.get("email", "unknown")
    logger.info(f"Code-Analyser search initiated | project: {project_id} | query: '{query}' | user: {user_email}")
    try:
        params = {"query": query, "top_k": top_k}
        if language:
            params["language"] = language
        
        with get_client(timeout=60.0) as client:
            response = client.post(f"/projects/{project_id}/search", params=params)
            response.raise_for_status()
            result = response.json()
        
        files_analyzed = result.get('files_analyzed', 0)
        logger.info(f"Search completed | project: {project_id} | files analyzed: {files_analyzed}")
        return result
    except Exception as e:
        error_msg = handle_http_error(e, "Code search", logger)
        st.error(error_msg)
    return None
