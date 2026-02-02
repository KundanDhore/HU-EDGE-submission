"""
Sidebar component.
"""
import streamlit as st
from api.auth import logout_user


def render_sidebar():
    """Render the sidebar with navigation and user info"""
    st.sidebar.title("Navigation")
    
    user_email = st.session_state.get('email')
    user_role = st.session_state.get('role', 'user')
    
    st.sidebar.write(f"Welcome, {user_email}!")
    
    # Logout button
    if st.sidebar.button("Logout"):
        logout_user()
