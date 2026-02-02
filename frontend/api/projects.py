"""
Project management API endpoints.
"""
import streamlit as st
import json
import re
from typing import List, Dict, Optional
from core.logging import get_logger
from api.client import get_client, handle_http_error
from config.settings import settings

logger = get_logger(__name__)


def create_project(title: str, description: str, personas: List[str], zip_file=None, github_url: str = None):
    """
    Create a new project.
    
    Args:
        title: Project title
        description: Project description
        personas: List of persona names
        zip_file: Uploaded ZIP file
        github_url: GitHub repository URL
    """
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
        
        if not re.match(r"https://github.com/[^/]+/[^/]+", github_url):
            logger.warning(f"Invalid GitHub URL format: {github_url} | user: {user_email}")
            st.error("Invalid GitHub URL format.")
            return
        data["github_url"] = github_url

    try:
        with st.spinner("Creating project... This may take up to 2 minutes for large files or GitHub repositories."):
            with get_client(timeout=600.0) as client:
                logger.info(f"Sending project creation request to backend | user: {user_email}")
                response = client.post("/projects/", data=data, files=files)
                response.raise_for_status()
        logger.info(f"Project created successfully | user: {user_email} | title: {title}")
        st.success("Project created successfully!")
    except Exception as e:
        error_msg = handle_http_error(e, "Project creation", logger)
        st.error(error_msg)


def get_projects() -> List[Dict]:
    """
    Get all projects for current user.
    
    Returns:
        List of project dictionaries
    """
    user_email = st.session_state.get("email", "unknown")
    logger.debug(f"Fetching projects for user: {user_email}")
    try:
        with get_client() as client:
            response = client.get("/projects/")
            response.raise_for_status()
            projects = response.json()
        logger.info(f"Retrieved {len(projects)} projects for user: {user_email}")
        return projects
    except Exception as e:
        error_msg = handle_http_error(e, "Fetch projects", logger)
        st.error(error_msg)
    return []


def delete_project(project_id: int) -> bool:
    """
    Delete a project.
    
    Args:
        project_id: Project ID to delete
    
    Returns:
        True if successful, False otherwise
    """
    user_email = st.session_state.get("email", "unknown")
    logger.info(f"Deleting project | project: {project_id} | user: {user_email}")
    try:
        with get_client(timeout=30.0) as client:
            response = client.delete(f"/projects/{project_id}")
            response.raise_for_status()
        logger.info(f"Project {project_id} deleted successfully")
        return True
    except Exception as e:
        error_msg = handle_http_error(e, "Delete project", logger)
        st.error(error_msg)
    return False


def get_project_analysis(project_id: int) -> Optional[Dict]:
    """
    Get repository intelligence analysis for a project.
    
    Args:
        project_id: Project ID
    
    Returns:
        Analysis dictionary or None
    """
    user_email = st.session_state.get("email", "unknown")
    logger.debug(f"Fetching analysis for project {project_id} | user: {user_email}")
    try:
        with get_client() as client:
            response = client.get(f"/projects/{project_id}/analysis")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching project analysis: {e}", exc_info=True)
        return None


def upload_file_to_project(project_id: int, uploaded_file):
    """
    Upload a file to a project.
    
    Args:
        project_id: Project ID
        uploaded_file: Streamlit UploadedFile object
    """
    user_email = st.session_state.get("email", "unknown")
    logger.info(f"File upload initiated | project: {project_id} | file: {uploaded_file.name} | user: {user_email}")
    try:
        with st.spinner(f"Uploading '{uploaded_file.name}'..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            with get_client(timeout=120.0) as client:
                response = client.post(f"/projects/{project_id}/files/", files=files)
                response.raise_for_status()
        logger.info(f"File uploaded successfully | project: {project_id} | file: {uploaded_file.name} | user: {user_email}")
        st.success(f"File '{uploaded_file.name}' uploaded successfully to project ID {project_id}!")
    except Exception as e:
        error_msg = handle_http_error(e, "File upload", logger)
        st.error(error_msg)
