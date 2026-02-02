"""
Create Project tab component.
"""
import streamlit as st
import httpx
from api.projects import create_project
from api.client import get_client, handle_http_error
from core.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


def render_create_project_tab():
    """Render the create project tab"""
    st.subheader("Create New Project")
    
    project_title = st.text_input("Project Title")
    project_description = st.text_area("Project Description")

    upload_type = st.radio("Upload Project By:", ("ZIP File", "GitHub URL"))
    zip_file = None
    github_url = None

    if upload_type == "ZIP File":
        st.caption(f"Max ZIP upload size: {settings.MAX_FILE_SIZE / (1024 * 1024):.0f} MB.")
        zip_file = st.file_uploader("Upload ZIP File", type=["zip"])
    else:
        st.caption("Max GitHub repo size: 100 MB.")
        github_url = st.text_input(
            "GitHub Repository URL",
            placeholder="e.g., https://github.com/owner/repo.git"
        )

    personas_options = ["SDE", "PM"]
    selected_personas = st.multiselect(
        "Select Personas for Documentation",
        options=personas_options,
        default=personas_options
    )

    if st.button("Create Project", type="primary"):
        if project_title:
            if upload_type == "ZIP File" and zip_file is None:
                st.warning("Please upload a ZIP file.")
            elif upload_type == "GitHub URL" and not github_url:
                st.warning("Please enter a GitHub URL.")
            else:
                # Create project and show live progress
                project_response = create_project_with_progress(
                    project_title, 
                    project_description, 
                    selected_personas, 
                    zip_file, 
                    github_url
                )
        else:
            st.warning("Project title cannot be empty.")


def create_project_with_progress(title: str, description: str, personas: list, zip_file=None, github_url: str = None):
    """Create a project and display live progress"""
    import json
    
    user_email = st.session_state.get("email", "unknown")
    source_type = "ZIP" if zip_file else "GitHub URL" if github_url else "none"
    logger.info(f"Project creation started | user: {user_email} | title: {title} | source: {source_type}")
    
    files = {}
    data = {
        "title": title,
        "description": description,
        "personas": json.dumps(personas)
    }

    if zip_file:
        file_size_mb = zip_file.size / (1024 * 1024)
        logger.debug(f"ZIP file selected: {zip_file.name} | size: {file_size_mb:.2f}MB")
        
        if zip_file.size > settings.MAX_FILE_SIZE:
            logger.warning(f"ZIP file too large: {file_size_mb:.2f}MB | user: {user_email}")
            st.error(f"File too large. Max size is {settings.MAX_FILE_SIZE / (1024 * 1024)} MB.")
            return
        files = {"zip_file": (zip_file.name, zip_file.getvalue(), zip_file.type)}
    elif github_url:
        logger.debug(f"GitHub URL provided: {github_url}")
        data["github_url"] = github_url

    try:
        # Create project
        with st.spinner("Creating project..."):
            with get_client(timeout=600.0) as client:
                logger.info(f"Sending project creation request to backend | user: {user_email}")
                response = client.post("/projects/", data=data, files=files)
                response.raise_for_status()
                project_data = response.json()
        
        project_id = project_data.get('id')
        logger.info(f"Project created successfully | user: {user_email} | title: {title} | id: {project_id}")
        st.success(f"✅ Project '{title}' created! (ID: {project_id})")
        
        # Show live progress monitoring
        st.markdown("### 🔄 Live Processing Progress")
        st.info("Watch your project being analyzed in real-time...")
        
        from components.progress_viewer import render_progress_viewer
        render_progress_viewer(project_id, auto_close=True)
        
        st.success("🎉 All done! Go to the 'Your Projects' tab to see your project.")
        
        return project_data
        
    except Exception as e:
        error_msg = handle_http_error(e, "Project creation", logger)
        st.error(error_msg)
