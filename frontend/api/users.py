"""
User management API endpoints (admin).
"""
import streamlit as st
from typing import List, Dict
from core.logging import get_logger
from api.client import get_client, handle_http_error

logger = get_logger(__name__)


def get_all_users() -> List[Dict]:
    """
    Get all users (admin only).
    
    Returns:
        List of user dictionaries
    """
    admin_email = st.session_state.get("email", "unknown")
    logger.info(f"Admin fetching all users | admin: {admin_email}")
    try:
        with get_client() as client:
            response = client.get("/users/admin/users")
            response.raise_for_status()
            users = response.json()
        logger.info(f"Retrieved {len(users)} users | admin: {admin_email}")
        return users
    except Exception as e:
        error_msg = handle_http_error(e, "Fetch users", logger)
        st.error(error_msg)
    return []
