"""
HU Edge Frontend - Main Application Entry Point
"""
import streamlit as st
from core.logging import get_logger
from core.session import init_session_state, is_authenticated
from config.settings import settings
from pages.auth_page import render_auth_page
from pages.dashboard import render_dashboard
from pages.admin_page import render_admin_page

logger = get_logger(__name__)
logger.info("Frontend application starting...")

def render_home():
    """
    Default landing page (/).
    - Admin users see the admin panel
    - Regular users see the normal dashboard
    """
    role = st.session_state.get("role", "user")
    if role == "admin":
        render_admin_page()
    else:
        render_dashboard()


def main():
    """Main application entry point"""
    logger.info("Main application function started")
    
    # Configure page
    st.set_page_config(
        page_title=settings.PAGE_TITLE,
        page_icon=settings.PAGE_ICON,
        layout=settings.LAYOUT
    )
    
    # Initialize session state
    init_session_state()
    
    # Route to appropriate page based on authentication
    if not is_authenticated():
        logger.debug("User not authenticated - showing login/signup")
        render_auth_page()
    else:
        user_email = st.session_state.get('email')
        user_role = st.session_state.get('role', 'user')
        logger.debug(f"Authenticated user session | email: {user_email} | role: {user_role}")

        # Multipage routing with explicit URL paths.
        pages = {
            "Home": [
                # Default page must be declared with default=True (url_path \"\" is not allowed otherwise).
                st.Page(render_home, title="Home", icon="🏠", default=True),
            ],
            "Admin": [
                # Always register /admin; the page itself will enforce role-based access.
                st.Page(render_admin_page, title="Admin Panel", icon="🛡️", url_path="admin"),
            ],
        }

        nav = st.navigation(pages, position="sidebar", expanded=True)
        nav.run()


if __name__ == "__main__":
    main()
