"""
Authentication state helpers.
"""
import streamlit as st
from core.logging import get_logger
from core.session import clear_session_state

logger = get_logger(__name__)


def set_auth_state(token: str, email: str, role: str = "user"):
    """Set authentication state"""
    st.session_state["token"] = token
    st.session_state["email"] = email
    st.session_state["role"] = role
    logger.info(f"Authentication state set | email: {email} | role: {role}")


def clear_auth_state():
    """Clear authentication state"""
    email = st.session_state.get("email", "unknown")
    logger.info(f"Clearing authentication state | user: {email}")
    clear_session_state()


def get_auth_headers():
    """Get authorization headers for API requests"""
    token = st.session_state.get("token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
