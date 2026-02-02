"""
Admin panel page (admin only).

Accessible at /admin via Streamlit st.navigation url_path.
"""

from __future__ import annotations

import streamlit as st

from core.logging import get_logger
from api.admin import (
    admin_get_analytics,
    admin_list_users,
    admin_create_user,
    admin_update_user,
    admin_delete_user,
    admin_list_projects,
)

logger = get_logger(__name__)


def render_admin_page():
    """
    Admin dashboard page.
    Accessible at /admin. This function enforces role-based access.
    """
    # Access control
    if not st.session_state.get("token"):
        st.title("Admin Panel")
        st.error("Please login first.")
        return
    if st.session_state.get("role") != "admin":
        st.title("Admin Panel")
        st.error("Not authorized. Admin role required.")
        return

    st.title("Admin Panel")
    st.caption("User management, project management, and analytics.")

    analytics = admin_get_analytics() or {}
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total users", analytics.get("total_users", 0))
    with col2:
        st.metric("Total projects", analytics.get("total_projects", 0))
    with col3:
        st.metric("Active projects", analytics.get("active_projects", 0))

    tab1, tab2 = st.tabs(["Users", "Projects"])

    with tab1:
        st.subheader("Users")

        with st.expander("Create user", expanded=False):
            email = st.text_input("Email", key="admin_create_email")
            password = st.text_input("Password", type="password", key="admin_create_password")
            role = st.selectbox("Role", options=["user", "admin"], index=0, key="admin_create_role")
            if st.button("Create", type="primary", key="admin_create_btn"):
                if not email or not password:
                    st.warning("Email and password are required.")
                else:
                    created = admin_create_user(email=email, password=password, role=role)
                    if created:
                        st.success(f"Created user {created.get('email')}")
                        st.rerun()

        users = admin_list_users()
        if not users:
            st.info("No users found.")
        else:
            for u in users:
                with st.expander(f"User {u.get('id')} | {u.get('email')}"):
                    st.write(f"Role: {u.get('role')} | Active: {u.get('is_active')}")

                    new_email = st.text_input("Email", value=u.get("email", ""), key=f"admin_u_email_{u['id']}")
                    new_role = st.selectbox(
                        "Role",
                        options=["user", "admin"],
                        index=0 if u.get("role") != "admin" else 1,
                        key=f"admin_u_role_{u['id']}",
                    )
                    new_active = st.checkbox("Active", value=bool(u.get("is_active", True)), key=f"admin_u_active_{u['id']}")
                    new_password = st.text_input("New password (optional)", type="password", key=f"admin_u_pass_{u['id']}")

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Update", key=f"admin_u_update_{u['id']}", use_container_width=True):
                            updated = admin_update_user(
                                u["id"],
                                email=new_email,
                                role=new_role,
                                is_active=new_active,
                                password=new_password or None,
                            )
                            if updated:
                                st.success("Updated.")
                                st.rerun()
                    with c2:
                        if st.button("Delete", key=f"admin_u_delete_{u['id']}", use_container_width=True):
                            if admin_delete_user(u["id"]):
                                st.success("Deleted.")
                                st.rerun()

    with tab2:
        st.subheader("Projects")
        projects = admin_list_projects()
        if not projects:
            st.info("No projects found.")
        else:
            for p in projects:
                st.write(
                    f"ID: {p.get('id')} | Title: {p.get('title')} | User: {p.get('owner_id')} | "
                    f"Status: {p.get('preprocessing_status')} | Framework: {p.get('framework')}"
                )

