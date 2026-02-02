"""
Authentication API endpoints.
"""
import streamlit as st
import httpx
from core.logging import get_logger
from core.auth import set_auth_state, clear_auth_state
from api.client import handle_http_error
from config.settings import settings

logger = get_logger(__name__)


def register_user(email: str, password: str):
    """
    Register a new user.
    
    Args:
        email: User email
        password: User password
    """
    logger.info(f"Registration attempt for email: {email}")
    try:
        response = httpx.post(
            f"{settings.FASTAPI_URL}/signup",
            json={"email": email, "password": password}
        )
        response.raise_for_status()
        logger.info(f"Registration successful for email: {email}")
        st.success("Registration successful! Please login.")
    except Exception as e:
        error_msg = handle_http_error(e, "Registration", logger)
        st.error(error_msg)


def login_user(email: str, password: str):
    """
    Login user and set authentication state.
    
    Args:
        email: User email
        password: User password
    """
    logger.info(f"Login attempt for email: {email}")
    try:
        response = httpx.post(
            f"{settings.FASTAPI_URL}/token",
            data={"username": email, "password": password}
        )
        response.raise_for_status()
        token_data = response.json()
        token = token_data["access_token"]

        # Backend /token does not return role; fetch it from /users/me using the token.
        role = "user"
        try:
            me = httpx.get(
                f"{settings.FASTAPI_URL}/users/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            me.raise_for_status()
            role = (me.json() or {}).get("role", "user")
        except Exception as e:
            logger.warning(f"Failed to fetch /users/me after login: {e}")

        set_auth_state(token, email, role or "user")
        logger.info(f"Login successful for email: {email}, role: {role or 'user'}")
        st.success("Logged in successfully!")
        st.rerun()
    except Exception as e:
        error_msg = handle_http_error(e, "Login", logger)
        st.error(error_msg)


def logout_user():
    """Logout user and clear authentication state"""
    email = st.session_state.get("email", "unknown")
    logger.info(f"User logged out: {email}")
    clear_auth_state()
    st.success("Logged out successfully.")
    st.rerun()
