"""
Session state management utilities.
"""
import streamlit as st


def init_session_state():
    """Initialize session state variables"""
    if 'search_results' not in st.session_state:
        st.session_state['search_results'] = None
    if 'last_search_query' not in st.session_state:
        st.session_state['last_search_query'] = ""
    if 'current_chat_session' not in st.session_state:
        st.session_state['current_chat_session'] = None
    if 'chat_messages' not in st.session_state:
        st.session_state['chat_messages'] = []


def clear_session_state():
    """Clear all session state"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def is_authenticated() -> bool:
    """Check if user is authenticated"""
    return "token" in st.session_state and st.session_state["token"] is not None


def get_current_user():
    """Get current user information"""
    return {
        "email": st.session_state.get("email"),
        "role": st.session_state.get("role", "user"),
        "token": st.session_state.get("token")
    }
