"""
Authentication page (Login/Signup).
"""
import streamlit as st
from core.logging import get_logger
from api.auth import login_user, register_user

logger = get_logger(__name__)

def _is_valid_email(value: str) -> bool:
    value = (value or "").strip()
    if "@" not in value:
        return False
    local, _, domain = value.partition("@")
    if not local or "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return True


def render_auth_page():
    """Render login/signup page"""
    logger.debug("Rendering authentication page")
    
    st.sidebar.title("Navigation")
    menu = st.sidebar.radio("Authentication", ["Login", "Signup"])
    
    if menu == "Login":
        render_login()
    elif menu == "Signup":
        render_signup()


def render_login():
    """Render login form"""
    st.subheader("Login")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")
    
    if st.button("Login"):
        if email and password:
            if not _is_valid_email(email):
                st.warning("Please enter a valid email address.")
                return
            login_user(email, password)
        else:
            st.warning("Please enter both email and password.")


def render_signup():
    """Render signup form"""
    st.subheader("Signup")
    email = st.text_input("Email", key="signup_email")
    password = st.text_input("Password", type="password", key="signup_password")
    
    if st.button("Signup"):
        if email and password:
            if not _is_valid_email(email):
                st.warning("Please enter a valid email address.")
                return
            register_user(email, password)
        else:
            st.warning("Please enter both email and password.")
