"""
Configuration tab for managing analysis/chat agent settings (Milestone 4).

This is the "Configuration page" referenced by the chat tab.
"""
from __future__ import annotations

import streamlit as st
from typing import Dict

from api.analysis_configs import (
    create_analysis_config,
    delete_analysis_config,
    get_analysis_configs,
    set_default_analysis_config,
)


def render_config_tab():
    st.subheader("⚙️ Configuration")
    st.write("Create and manage reusable agent configurations for chat and analysis.")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        _render_create_form()

    with col_right:
        _render_saved_configs()


def _render_create_form():
    st.markdown("### Create Configuration")

    with st.form("analysis_config_create", clear_on_submit=False):
        name = st.text_input("Configuration Name *", placeholder="e.g., Deep + High Verbosity")

        st.markdown("#### Core Settings")
        analysis_depth = st.selectbox("Analysis Depth", ["quick", "standard", "deep"], index=1)
        doc_verbosity = st.selectbox("Verbosity", ["minimal", "medium", "detailed"], index=1)
        persona_mode = st.selectbox("Persona Mode", ["both", "sde", "pm"], index=0)

        st.markdown("#### Agents")
        col1, col2 = st.columns(2)
        with col1:
            enable_file_structure_agent = st.checkbox("File Structure Agent", value=True)
            enable_api_agent = st.checkbox("API Signature Agent", value=True)
            enable_web_augmented = st.checkbox("Web-Augmented Agent (Tavily)", value=False)
        with col2:
            enable_sde_agent = st.checkbox("SDE Output Agent", value=True)
            enable_pm_agent = st.checkbox("PM Output Agent", value=True)

        is_default = st.checkbox("Set as default", value=True)

        submitted = st.form_submit_button("💾 Save Configuration", type="primary", use_container_width=True)

    if not submitted:
        return

    if not name.strip():
        st.error("Please provide a configuration name.")
        return

    payload: Dict = {
        "name": name.strip(),
        "is_default": is_default,
        "analysis_depth": analysis_depth,
        "doc_verbosity": doc_verbosity,
        "persona_mode": persona_mode,
        "enable_file_structure_agent": enable_file_structure_agent,
        "enable_api_agent": enable_api_agent,
        "enable_web_augmented": enable_web_augmented,
        "enable_sde_agent": enable_sde_agent,
        "enable_pm_agent": enable_pm_agent,
        "agent_settings": {},
    }

    created = create_analysis_config(payload)
    if created:
        st.success(f"Saved configuration: {created.get('name')}")
        st.rerun()
    else:
        st.error("Failed to create configuration.")


def _render_saved_configs():
    st.markdown("### Saved Configurations")
    configs = get_analysis_configs()

    if not configs:
        st.info("No saved configurations yet.")
        return

    for cfg in configs:
        title = f"{'⭐ ' if cfg.get('is_default') else ''}{cfg.get('name', 'Untitled')}"
        with st.expander(title, expanded=False):
            st.caption(f"Depth: {cfg.get('analysis_depth')} | Verbosity: {cfg.get('doc_verbosity')} | Persona: {cfg.get('persona_mode')}")

            agents = []
            if cfg.get("enable_file_structure_agent"):
                agents.append("FileStructure")
            if cfg.get("enable_api_agent"):
                agents.append("API")
            if cfg.get("enable_web_augmented"):
                agents.append("Web")
            if cfg.get("enable_sde_agent"):
                agents.append("SDE")
            if cfg.get("enable_pm_agent"):
                agents.append("PM")
            st.caption("Agents: " + ", ".join(agents))

            col1, col2 = st.columns(2)
            with col1:
                if not cfg.get("is_default") and st.button("⭐ Set Default", key=f"set_default_{cfg['id']}", use_container_width=True):
                    if set_default_analysis_config(cfg["id"]):
                        st.success("Default updated.")
                        st.rerun()
                    else:
                        st.error("Failed to set default.")
            with col2:
                if st.button("🗑️ Delete", key=f"del_cfg_{cfg['id']}", use_container_width=True):
                    if delete_analysis_config(cfg["id"]):
                        st.success("Deleted.")
                        st.rerun()
                    else:
                        st.error("Failed to delete.")

