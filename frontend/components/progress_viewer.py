"""
Real-time progress viewer component using polling.
"""
import streamlit as st
import time
from typing import Optional
from core.logging import get_logger
from api.client import get_client, handle_http_error

logger = get_logger(__name__)


def render_progress_viewer(project_id: int, auto_close: bool = True):
    """
    Render real-time progress viewer for a project using polling.
    
    Args:
        project_id: Project ID to monitor
        auto_close: If True, automatically close when complete
    """
    logger.info(f"Starting progress viewer for project {project_id}")
    
    # Create containers for UI elements
    progress_container = st.container()
    
    with progress_container:
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        
        # Activity feed
        activity_expander = st.expander("📋 Activity Feed", expanded=True)
    
    # Initialize state
    if f'activity_log_{project_id}' not in st.session_state:
        st.session_state[f'activity_log_{project_id}'] = []
    
    last_id = 0
    activity_log = st.session_state[f'activity_log_{project_id}']
    poll_count = 0
    max_polls = 600  # 10 minutes at 1 second intervals
    
    try:
        while poll_count < max_polls:
            poll_count += 1
            
            # Fetch latest progress updates
            try:
                with get_client(timeout=10.0) as client:
                    response = client.get(
                        f"/projects/{project_id}/progress",
                        params={'since_id': last_id}
                    )
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                error_msg = handle_http_error(e, "Fetch progress", logger)
                st.error(f"Failed to fetch progress: {error_msg}")
                break
            
            progress_updates = data.get('progress', [])
            current_status = data.get('current_status', 'processing')
            
            # Process each update
            for update in progress_updates:
                # Update progress bar
                percentage = update.get('percentage', 0)
                progress_bar.progress(min(percentage / 100.0, 1.0))
                
                # Format status message
                stage = update.get('stage', '').replace('_', ' ').title()
                current_file = update.get('current_file')
                files_processed = update.get('files_processed', 0)
                total_files = update.get('total_files', 0)
                message = update.get('message', '')
                
                if current_file and total_files > 0:
                    status_msg = f"**{stage}**: {message} ({files_processed}/{total_files} files) - {percentage:.1f}%"
                else:
                    status_msg = f"**{stage}**: {message} - {percentage:.1f}%"
                
                status_text.markdown(status_msg)
                
                # Add to activity feed with emoji
                message_type = update.get('message_type', 'info')
                emoji_map = {
                    'info': 'ℹ️',
                    'success': '✅',
                    'warning': '⚠️',
                    'error': '❌'
                }
                emoji = emoji_map.get(message_type, 'ℹ️')
                
                timestamp = update.get('timestamp', '')
                if timestamp:
                    time_str = timestamp.split('T')[1][:8] if 'T' in timestamp else ''
                    activity_msg = f"{emoji} [{time_str}] {message}"
                else:
                    activity_msg = f"{emoji} {message}"
                
                activity_log.append(activity_msg)
                last_id = update.get('id', last_id)
            
            # Update activity feed display
            with activity_expander:
                # Show last 30 activities, newest first
                for activity in reversed(activity_log[-30:]):
                    st.text(activity)
            
            # Check if processing is complete or failed
            if current_status in ['completed', 'failed']:
                logger.info(f"Project {project_id} processing {current_status}")
                
                if current_status == 'completed':
                    progress_bar.progress(1.0)
                    status_text.markdown("**✅ Processing Complete!**")
                    st.success("🎉 Project analysis completed successfully!")
                else:
                    status_text.markdown("**❌ Processing Failed**")
                    st.error("❌ Project processing failed. Please check the logs.")
                
                # Auto-close after brief delay
                if auto_close:
                    time.sleep(2)
                break
            
            # If no updates and status is not processing, might be stuck
            if not progress_updates and current_status != 'processing':
                logger.warning(f"No progress updates for project {project_id}, status: {current_status}")
                break
            
            # Wait before next poll
            time.sleep(1)
        
        # Timeout check
        if poll_count >= max_polls:
            st.warning("⏱️ Progress monitoring timed out. Project may still be processing.")
    
    except Exception as e:
        logger.error(f"Error in progress viewer: {e}", exc_info=True)
        st.error(f"Progress monitoring error: {str(e)}")
    
    finally:
        logger.info(f"Progress viewer stopped for project {project_id}")


def show_progress_indicator(project_id: int):
    """
    Show a compact progress indicator for a project.
    Suitable for project list displays.
    
    Args:
        project_id: Project ID to monitor
    """
    try:
        with get_client(timeout=5.0) as client:
            response = client.get(f"/projects/{project_id}/progress", params={'since_id': 0})
            response.raise_for_status()
            data = response.json()
        
        progress_updates = data.get('progress', [])
        if progress_updates:
            latest = progress_updates[-1]
            percentage = latest.get('percentage', 0)
            message = latest.get('message', '')
            
            st.progress(percentage / 100.0)
            st.caption(f"{message} ({percentage:.0f}%)")
    
    except Exception as e:
        logger.error(f"Error showing progress indicator: {e}")
        st.caption("Processing...")
