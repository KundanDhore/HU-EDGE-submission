"""
Main dashboard page.
"""
import streamlit as st
from core.logging import get_logger
from components.sidebar import render_sidebar
from pages.tabs.projects_tab import render_projects_tab
from pages.tabs.create_project_tab import render_create_project_tab
from pages.tabs.chat_tab import render_chat_tab
from pages.tabs.config_tab import render_config_tab
from pages.tabs.documentation_tab import render_documentation_tab

logger = get_logger(__name__)


def render_dashboard():
    """Render the main dashboard"""
    logger.debug(f"Rendering dashboard for user: {st.session_state.get('email')}")
    
    # Render sidebar
    render_sidebar()
    
    # Main content
    st.title("Dashboard")
    
    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Create Project", 
        "My Projects", 
        "💬 Chat with Code",
        "📄 Documentation",
        "⚙️ Configuration",
    ])
    
    with tab1:
        render_create_project_tab() 
    
    with tab2:
        render_projects_tab()
    
    with tab3:
        render_chat_tab()

    with tab4:
        render_documentation_tab()

    with tab5:
        render_config_tab()
