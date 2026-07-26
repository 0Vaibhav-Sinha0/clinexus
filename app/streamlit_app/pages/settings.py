##############################################################################
# app/streamlit_app/pages/settings.py
#
# Settings page: Admin-only system configuration.
##############################################################################

import streamlit as st
import logging

from auth import require_role
from config import UserRole

logger = logging.getLogger(__name__)

def render_settings():
    """Render settings page."""
    
    require_role(UserRole.ADMIN)

    st.markdown("## ⚙️ Settings")
    st.markdown("System configuration and administration")
    st.markdown("---")

    # ─────────────────────────────────────────────────────
    # CONFIGURATION SECTION
    # ─────────────────────────────────────────────────────

    st.markdown("### System Configuration")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Groq API Key Status**")
        st.success("✓ Valid")

    with col2:
        st.markdown("**Embedding Model**")
        st.info("all-mpnet-base-v2 (768D)")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Agent Parallel Execution**")
        st.success("✓ Enabled (6 agents)")

    with col2:
        st.markdown("**Analysis Timeout**")
        st.info("300 seconds (5 min)")

    st.markdown("")

    # ─────────────────────────────────────────────────────
    # USER MANAGEMENT
    # ─────────────────────────────────────────────────────

    st.markdown("### User Management")

    if st.button("➕ Add New User"):
        st.info("User management coming soon")

    st.markdown("")
    st.info("📌 User management interface coming in next phase")

    # ─────────────────────────────────────────────────────
    # SYSTEM LOGS
    # ─────────────────────────────────────────────────────

    st.markdown("### System Logs")

    st.info("📌 System logs viewer coming in next phase")

    # ─────────────────────────────────────────────────────
    # DATA EXPORT
    # ─────────────────────────────────────────────────────

    st.markdown("### Data Export")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 Export Signals (CSV)", use_container_width=True):
            st.info("Export triggered (coming soon)")

    with col2:
        if st.button("📥 Export Analytics (JSON)", use_container_width=True):
            st.info("Export triggered (coming soon)")
