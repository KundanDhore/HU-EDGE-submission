"""
Chat API endpoints.
"""
import streamlit as st
from typing import List, Dict, Optional
from core.logging import get_logger
from api.client import get_client, handle_http_error

logger = get_logger(__name__)


def create_chat_session(project_id: int, title: str = "New Chat") -> Optional[Dict]:
    """
    Create a new chat session.
    
    Args:
        project_id: Project ID
        title: Chat session title
    
    Returns:
        Session dictionary or None
    """
    user_email = st.session_state.get("email", "unknown")
    logger.info(f"Creating chat session | project: {project_id} | user: {user_email}")
    try:
        with get_client() as client:
            response = client.post(
                f"/chat/projects/{project_id}/sessions",
                json={"project_id": project_id, "title": title}
            )
            response.raise_for_status()
            session = response.json()
        logger.info(f"Chat session created | session_id: {session['id']}")
        return session
    except Exception as e:
        error_msg = handle_http_error(e, "Create chat session", logger)
        st.error(error_msg)
        return None


def get_chat_sessions(project_id: int) -> List[Dict]:
    """
    Get all chat sessions for a project.
    
    Args:
        project_id: Project ID
    
    Returns:
        List of session dictionaries
    """
    user_email = st.session_state.get("email", "unknown")
    logger.debug(f"Fetching chat sessions | project: {project_id} | user: {user_email}")
    try:
        with get_client() as client:
            response = client.get(f"/chat/projects/{project_id}/sessions")
            response.raise_for_status()
            sessions = response.json()
        logger.info(f"Retrieved {len(sessions)} chat sessions")
        return sessions
    except Exception as e:
        logger.error(f"Error fetching chat sessions: {e}", exc_info=True)
        return []


def get_chat_session(session_id: int) -> Optional[Dict]:
    """
    Get a specific chat session with messages.
    
    Args:
        session_id: Session ID
    
    Returns:
        Session dictionary or None
    """
    user_email = st.session_state.get("email", "unknown")
    logger.debug(f"Fetching chat session | session_id: {session_id} | user: {user_email}")
    try:
        with get_client() as client:
            response = client.get(f"/chat/sessions/{session_id}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching chat session: {e}", exc_info=True)
        return None


def send_chat_message(session_id: int, message: str, config_id: Optional[int] = None) -> Optional[Dict]:
    """
    Send a message in a chat session.
    
    Args:
        session_id: Session ID
        message: Message content
        config_id: Optional analysis configuration ID to apply for this chat turn
    
    Returns:
        Response dictionary or None
    """
    user_email = st.session_state.get("email", "unknown")
    logger.info(f"Sending chat message | session_id: {session_id} | user: {user_email}")
    try:
        with get_client(timeout=200.0) as client:
            payload: Dict[str, object] = {"message": message}
            if config_id is not None:
                payload["config_id"] = int(config_id)
            response = client.post(
                f"/chat/sessions/{session_id}/messages",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
        logger.info(f"Chat message sent successfully")
        return result
    except Exception as e:
        error_msg = handle_http_error(e, "Send chat message", logger)
        st.error(error_msg)
        return None


def delete_chat_session(session_id: int) -> bool:
    """
    Delete a chat session.
    
    Args:
        session_id: Session ID
    
    Returns:
        True if successful, False otherwise
    """
    user_email = st.session_state.get("email", "unknown")
    logger.info(f"Deleting chat session | session_id: {session_id} | user: {user_email}")
    try:
        with get_client() as client:
            response = client.delete(f"/chat/sessions/{session_id}")
            response.raise_for_status()
        logger.info(f"Chat session deleted successfully")
        return True
    except Exception as e:
        error_msg = handle_http_error(e, "Delete chat session", logger)
        st.error(error_msg)
        return False
