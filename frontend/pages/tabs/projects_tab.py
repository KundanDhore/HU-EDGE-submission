"""
Projects tab component.
"""
import streamlit as st
import time
from api.projects import get_projects, delete_project, get_project_analysis


def render_projects_tab():
    """Render the projects list tab"""
    st.subheader("Your Projects")
    projects = get_projects()

    if projects:
        for project in projects:
            render_project_card(project)
    else:
        st.info("You don't have any projects yet. Create one!")


def render_project_card(project):
    """Render a single project card"""
    # Get processing status indicator
    status = project.get('preprocessing_status', 'pending')
    status_emoji = {
        'completed': '✅',
        'processing': '⚙️',
        'failed': '❌',
        'pending': '⏳'
    }.get(status, '⏳')
    
    # Display project with status indicator
    with st.expander(f"{status_emoji} **{project['title']}** (ID: {project['id']})"):
        st.write(f"**Description:** {project.get('description') or 'None'}")
        
        # Display Repository Intelligence
        if status == 'completed' and project.get('repository_type'):
            render_repository_intelligence(project)
        elif status == 'processing':
            st.info("⚙️ Repository analysis in progress...")
            
            # Show live progress button
            if st.button(f"👁️ Watch Live Progress", key=f"watch_live_{project['id']}"):
                st.session_state[f'show_live_progress_{project["id"]}'] = True
                st.rerun()
            
            # Show progress viewer if requested
            if st.session_state.get(f'show_live_progress_{project["id"]}', False):
                st.markdown("---")
                st.markdown("### 🔄 Live Progress Monitor")
                from components.progress_viewer import render_progress_viewer
                render_progress_viewer(project['id'], auto_close=False)
                
                if st.button("❌ Stop Monitoring", key=f"stop_monitor_{project['id']}"):
                    st.session_state[f'show_live_progress_{project["id"]}'] = False
                    st.rerun()
        elif status == 'failed':
            st.error("❌ Preprocessing failed. Please try reprocessing.")
        elif status == 'pending':
            st.warning("⏳ Preprocessing pending...")
        
        # Display source information
        render_source_info(project)
        
        # Delete button with confirmation
        render_delete_section(project)


def render_repository_intelligence(project):
    """Render repository intelligence section"""
    st.markdown("### 🔍 Repository Intelligence")
    
    # Main info in columns
    col1, col2, col3 = st.columns(3)
    with col1:
        repo_type = project.get('repository_type', 'Unknown')
        st.metric("Type", repo_type)
    with col2:
        framework = project.get('framework', 'None detected')
        st.metric("Framework", framework.capitalize() if framework else 'N/A')
    with col3:
        total_files = project.get('total_files', 0)
        st.metric("Files", total_files)
    
    # Stats row
    col4, col5, col6 = st.columns(3)
    with col4:
        loc = project.get('total_lines_of_code', 0)
        st.metric("Lines of Code", f"{loc:,}")
    with col5:
        endpoints = project.get('api_endpoints_count', 0)
        st.metric("API Endpoints", endpoints)
    with col6:
        models = project.get('models_count', 0)
        st.metric("Models", models)
    
    # Language breakdown
    languages = project.get('languages_breakdown', {})
    if languages:
        st.markdown("**Language Breakdown:**")
        lang_cols = st.columns(len(languages))
        for idx, (lang, pct) in enumerate(languages.items()):
            with lang_cols[idx]:
                st.write(f"**{lang.capitalize()}:** {pct}%")
    
    # Entry points
    entry_points = project.get('entry_points', [])
    if entry_points:
        st.markdown(f"**🎯 Entry Points:** `{', '.join(entry_points)}`")
    
    # Dependencies (show first 5)
    deps = project.get('dependencies', [])
    if deps:
        deps_display = ', '.join(deps[:5])
        more_text = f" (+{len(deps) - 5} more)" if len(deps) > 5 else ""
        st.markdown(f"**📦 Dependencies:** `{deps_display}{more_text}`")
    
    # View detailed analysis button
    if st.button(f"📊 View Detailed Analysis", key=f"analysis_{project['id']}"):
        st.session_state[f'show_analysis_{project["id"]}'] = True
        st.rerun()
    
    # Show detailed analysis if requested
    if st.session_state.get(f'show_analysis_{project["id"]}', False):
        render_detailed_analysis(project)
    
    st.divider()


def render_detailed_analysis(project):
    """Render detailed repository analysis"""
    with st.container():
        st.markdown("#### 📊 Detailed Repository Analysis")
        
        analysis = get_project_analysis(project['id'])
        if analysis:
            # Architecture
            if analysis.get('architecture'):
                st.write(f"**🏗️ Architecture:** {analysis['architecture']}")
            
            # Primary Language
            if analysis.get('primary_language'):
                st.write(f"**💻 Primary Language:** {analysis['primary_language'].capitalize()}")
            
            # API Endpoints Details
            endpoints = analysis.get('api_endpoints_details', [])
            if endpoints:
                st.markdown("**🔗 API Endpoints:**")
                for ep in endpoints[:5]:
                    st.write(f"- `{ep.get('method')}` {ep.get('path')} (`{ep.get('file')}`)")
            
            # Models
            models = analysis.get('models_list', [])
            if models:
                st.markdown(f"**🗂️ Models:** {', '.join(models[:10])}")
            
            
            # All Dependencies
            all_deps = analysis.get('dependencies', [])
            if all_deps:
                st.markdown(f"**📦 All Dependencies ({len(all_deps)}):**")
                deps_text = ', '.join(all_deps)
                st.text_area("Dependencies", deps_text, height=100, disabled=True)
        
        if st.button("❌ Close Analysis", key=f"close_analysis_{project['id']}"):
            st.session_state[f'show_analysis_{project["id"]}'] = False
            st.rerun()


def render_source_info(project):
    """Render source information section"""
    st.markdown("### 📁 Source Information")
    source_type = project.get('source_type', 'Unknown').upper()
    source_value = project.get('source_value', 'N/A')
    
    if source_type == 'ZIP':
        st.write(f"**Source:** 📦 ZIP File - `{source_value}`")
    elif source_type == 'GITHUB':
        st.write(f"**Source:** 🐙 GitHub - [{source_value}]({source_value})")
    else:
        st.write(f"**Source:** {source_type} - {source_value}")
    
    st.write(f"**Personas:** {', '.join(project.get('personas', []))}")


def render_delete_section(project):
    """Render delete button and confirmation"""
    st.divider()
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button(f"🗑️ Delete", key=f"delete_project_{project['id']}", type="secondary"):
            st.session_state[f'confirm_delete_{project["id"]}'] = True
            st.rerun()
    
    # Show confirmation dialog
    if st.session_state.get(f'confirm_delete_{project["id"]}', False):
        st.warning(f"⚠️ Are you sure you want to delete **{project['title']}**?")
        st.write("This will permanently delete:")
        st.write("- All project files")
        st.write("- All chat sessions and messages")
        
        confirm_col1, confirm_col2, confirm_col3 = st.columns([1, 1, 2])
        with confirm_col1:
            if st.button("✓ Yes, Delete", key=f"confirm_yes_{project['id']}", type="primary"):
                if delete_project(project['id']):
                    st.success(f"Project '{project['title']}' deleted successfully!")
                    st.session_state.pop(f'confirm_delete_{project["id"]}', None)
                    time.sleep(1)
                    st.rerun()
        with confirm_col2:
            if st.button("✗ Cancel", key=f"confirm_no_{project['id']}"):
                st.session_state.pop(f'confirm_delete_{project["id"]}', None)
                st.rerun()
