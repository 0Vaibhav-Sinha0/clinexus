##############################################################################
# app/streamlit_app/pages/home.py
#
# Home page: Dashboard overview with system status and key metrics.
##############################################################################

import streamlit as st
import pandas as pd
from datetime import datetime
import logging

from auth import get_current_user_email, get_current_user_role
from database import Database, run_async
from config import UserRole

logger = logging.getLogger(__name__)

def render_home():
    """Render home page."""
    
    st.markdown("## 🏠 Home")
    st.markdown("---")

    # Get analytics data
    try:
        analytics = run_async(Database.get_analytics())
    except Exception as e:
        st.error(f"Failed to load analytics: {e}")
        return

    # ─────────────────────────────────────────────────────
    # KEY METRICS (Top cards)
    # ─────────────────────────────────────────────────────

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "📚 Studies Analyzed",
            analytics.get("total_studies", 0),
            help="Total clinical trials processed",
        )

    with col2:
        st.metric(
            "🚨 Signals Generated",
            analytics.get("total_signals", 0),
            help="Total AI-generated findings",
        )

    with col3:
        approval_rate = analytics.get("approval_rate", 0)
        st.metric(
            "✅ Approval Rate",
            f"{approval_rate:.1f}%",
            help="% of signals approved by reviewers",
        )

    with col4:
        pending_signals = analytics.get("status_breakdown", {}).get("pending", 0)
        st.metric(
            "⏳ Pending Review",
            pending_signals,
            help="Signals awaiting reviewer approval",
        )

    st.markdown("")

    # ─────────────────────────────────────────────────────
    # SIGNAL DISTRIBUTION
    # ─────────────────────────────────────────────────────

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Signal Status Breakdown")
        status_breakdown = analytics.get("status_breakdown", {})
        if status_breakdown:
            status_df = pd.DataFrame({
                "Status": list(status_breakdown.keys()),
                "Count": list(status_breakdown.values()),
            })
            st.bar_chart(status_df.set_index("Status"))
        else:
            st.info("No signals yet")

    with col2:
        st.markdown("### Signals by Agent")
        agent_breakdown = analytics.get("agent_breakdown", {})
        if agent_breakdown:
            agent_df = pd.DataFrame({
                "Agent": list(agent_breakdown.keys()),
                "Count": list(agent_breakdown.values()),
            })
            st.bar_chart(agent_df.set_index("Agent"))
        else:
            st.info("No signals yet")

    st.markdown("")

    # ─────────────────────────────────────────────────────
    # RECENT ANALYSES
    # ─────────────────────────────────────────────────────

    st.markdown("### Recent Analyses")

    role = get_current_user_role()
    researcher_id = None
    if role == UserRole.RESEARCHER:
        researcher_id = get_current_user_email()

    try:
        analyses, total = run_async(
            Database.get_analyses(
                researcher_id=researcher_id,
                limit=10,
                offset=0,
            )
        )

        if analyses:
            # Display as table
            display_data = []
            for analysis in analyses:
                display_data.append({
                    "NCT ID": analysis.get("nct_id", "N/A"),
                    "Status": analysis.get("status", "unknown").upper(),
                    "Signals": analysis.get("total_signals", 0),
                    "Created": analysis.get("created_at", "N/A"),
                    "Actions": "View Details",
                })

            st.dataframe(
                pd.DataFrame(display_data),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("📭 No analyses yet. Start by uploading a clinical trial.")

    except Exception as e:
        st.error(f"Failed to load recent analyses: {e}")

    # ─────────────────────────────────────────────────────
    # QUICK LINKS
    # ─────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown("### Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if role in [UserRole.RESEARCHER, UserRole.ADMIN]:
            if st.button("📤 Upload New Trial", use_container_width=True):
                st.session_state.page = "upload_analyze"
                st.rerun()

    with col2:
        if role in [UserRole.REVIEWER, UserRole.ADMIN]:
            if st.button("🔍 Review Signals", use_container_width=True):
                st.session_state.page = "signal_review"
                st.rerun()

    with col3:
        if st.button("📊 View Analytics", use_container_width=True):
            st.session_state.page = "analytics"
            st.rerun()

    # ─────────────────────────────────────────────────────
    # FOOTER INFO
    # ─────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown(
        """
        **Welcome to Clinexus!**
        
        Clinexus is an AI-powered clinical trial intelligence platform that analyzes 
        regulatory data to identify risks, inconsistencies, and credibility issues.
        
        - 🤖 **6 Specialized AI Agents** analyze trials in parallel
        - 👥 **Human-in-the-Loop** approval workflow for trustworthy findings
        - 💾 **Persistent knowledge base** of clinical trial intelligence
        """
    )
