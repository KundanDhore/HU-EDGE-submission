"""
Chat with Code tab component.
"""
import streamlit as st
from api.projects import get_projects
from api.chat import (
    create_chat_session,
    get_chat_sessions,
    get_chat_session,
    send_chat_message,
    delete_chat_session
)
from api.analysis_configs import get_analysis_configs


def render_chat_tab():
    """Render the chat with code tab"""
    st.subheader("💬 Chat with Your Code")
    st.write("Ask questions about your code using AI-powered conversational search.")

    with st.expander("⚙️ Chat Configuration", expanded=False):
        render_chat_config_selector()
    
    # Initialize session state for chat
    if 'current_chat_session' not in st.session_state:
        st.session_state['current_chat_session'] = None
    if 'chat_messages' not in st.session_state:
        st.session_state['chat_messages'] = []
    
    # Get all projects
    projects = get_projects()
    
    if not projects:
        st.info("You don't have any projects yet. Create one first!")
        return
    
    # Project selection and new chat button
    render_chat_header(projects)
    
    # Get chat sessions for selected project
    selected_project_label = st.session_state.get('chat_project_select')
    if selected_project_label:
        project_options = {f"{p['title']} (ID: {p['id']})": p['id'] for p in projects}
        selected_project_id = project_options[selected_project_label]
        chat_sessions = get_chat_sessions(selected_project_id)
        
        # Display chat sessions sidebar
        if chat_sessions:
            render_chat_sessions_list(chat_sessions)
        
        st.divider()
        
        # Chat interface
        render_chat_interface()


def render_chat_header(projects):
    """Render project selector and new chat button"""
    col_proj, col_sess = st.columns([2, 1])
    
    with col_proj:
        project_options = {f"{p['title']} (ID: {p['id']})": p['id'] for p in projects}
        selected_project_label = st.selectbox(
            "Select Project",
            list(project_options.keys()),
            key="chat_project_select"
        )
        selected_project_id = project_options[selected_project_label]
    
    with col_sess:
        if st.button("➕ New Chat", type="primary"):
            new_session = create_chat_session(selected_project_id, "New Chat")
            if new_session:
                st.session_state['current_chat_session'] = new_session['id']
                st.session_state['chat_messages'] = []
                st.success("New chat session created!")
                st.rerun()


def render_chat_sessions_list(chat_sessions):
    """Render list of chat sessions"""
    st.divider()
    st.caption("💾 Previous Chats")
    
    cols_per_row = 3
    for i in range(0, len(chat_sessions), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, session in enumerate(chat_sessions[i:i+cols_per_row]):
            with cols[j]:
                session_title = session['title'][:30] + "..." if len(session['title']) > 30 else session['title']
                
                button_col, delete_col = st.columns([4, 1])
                with button_col:
                    if st.button(
                        f"📝 {session_title}",
                        key=f"load_session_{session['id']}",
                        use_container_width=True
                    ):
                        st.session_state['current_chat_session'] = session['id']
                        # Load messages
                        session_data = get_chat_session(session['id'])
                        if session_data:
                            st.session_state['chat_messages'] = session_data.get('messages', [])
                        st.rerun()
                
                with delete_col:
                    if st.button("🗑️", key=f"delete_session_{session['id']}"):
                        if delete_chat_session(session['id']):
                            if st.session_state.get('current_chat_session') == session['id']:
                                st.session_state['current_chat_session'] = None
                                st.session_state['chat_messages'] = []
                            st.success("Chat deleted!")
                            st.rerun()


def render_chat_interface():
    """Render the main chat interface"""
    if st.session_state['current_chat_session']:
        current_session_id = st.session_state['current_chat_session']
        
        # Display chat messages
        chat_container = st.container()
        with chat_container:
            if st.session_state['chat_messages']:
                for msg in st.session_state['chat_messages']:
                    if msg['role'] == 'user':
                        with st.chat_message("user"):
                            st.write(msg['content'])
                    elif msg['role'] == 'assistant':
                        with st.chat_message("assistant"):
                            st.write(msg['content'])
            else:
                st.info("👋 Start a conversation! Ask me anything about your code.")
        
        # Chat input
        user_input = st.chat_input("Ask a question about your code...", key="chat_input")
        
        if user_input:
            # Display user message immediately
            with st.chat_message("user"):
                st.write(user_input)
            
            # Add to session state
            st.session_state['chat_messages'].append({
                'role': 'user',
                'content': user_input
            })
            
            # Send message and get response
            with st.spinner("🤔 Thinking..."):
                response = send_chat_message(
                    current_session_id,
                    user_input,
                    config_id=st.session_state.get("chat_config_id"),
                )
            
            if response:
                # Display assistant response
                with st.chat_message("assistant"):
                    st.write(response['message']['content'])
                    
                    # Show retrieved chunks if available
                    if response.get('retrieved_chunks'):
                        with st.expander("📚 Retrieved Code Chunks"):
                            for idx, chunk in enumerate(response['retrieved_chunks'], 1):
                                st.text(f"Chunk {idx}:")
                                st.text(chunk)
                                st.divider()
                
                # Add to session state
                st.session_state['chat_messages'].append({
                    'role': 'assistant',
                    'content': response['message']['content']
                })
                
                st.rerun()
    
    else:
        st.info("👈 Click '➕ New Chat' to start a conversation, or select a previous chat session.")


def render_chat_config_selector():
    """Read-only config selector: pick from saved configurations."""
    configs = get_analysis_configs()
    if not configs:
        st.info("No saved configurations yet. Create one in the Configuration tab.")
        st.session_state["chat_config_id"] = None
        return

    # Build options (backend returns default first).
    labels = []
    ids = []
    for cfg in configs:
        cfg_id = cfg.get("id")
        if cfg_id is None:
            continue
        label = f"{'⭐ ' if cfg.get('is_default') else ''}{cfg.get('name', 'Untitled')} (ID: {cfg_id})"
        labels.append(label)
        ids.append(int(cfg_id))

    if not ids:
        st.info("No usable configurations returned from server.")
        st.session_state["chat_config_id"] = None
        return

    default_id = next((int(c["id"]) for c in configs if c.get("is_default") and c.get("id") is not None), ids[0])

    # Initialize / repair selection if config was deleted.
    if st.session_state.get("chat_config_id") not in ids:
        st.session_state["chat_config_id"] = default_id

    selected_id = int(st.session_state["chat_config_id"])
    try:
        selected_index = ids.index(selected_id)
    except ValueError:
        selected_index = 0
        st.session_state["chat_config_id"] = ids[0]

    selected_label = st.selectbox("Select configuration", labels, index=selected_index, key="chat_config_select")
    st.session_state["chat_config_id"] = ids[labels.index(selected_label)]

    # Show details (read-only).
    selected_cfg = next((c for c in configs if int(c.get("id", -1)) == int(st.session_state["chat_config_id"])), None)
    if not selected_cfg:
        return

    st.caption(
        f"Depth: {selected_cfg.get('analysis_depth')} | "
        f"Verbosity: {selected_cfg.get('doc_verbosity')} | "
        f"Persona: {selected_cfg.get('persona_mode')}"
    )
    agents = []
    if selected_cfg.get("enable_file_structure_agent"):
        agents.append("FileStructure")
    if selected_cfg.get("enable_api_agent"):
        agents.append("API")
    if selected_cfg.get("enable_web_augmented"):
        agents.append("Web")
    if selected_cfg.get("enable_sde_agent"):
        agents.append("SDE")
    if selected_cfg.get("enable_pm_agent"):
        agents.append("PM")
    st.caption("Agents: " + (", ".join(agents) if agents else "None"))
