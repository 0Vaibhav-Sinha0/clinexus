##############################################################################
# app/streamlit_app/pages/analytics.py
#
# Analytics page: Data visualization and insights.
##############################################################################

import streamlit as st
import pandas as pd
import plotly.express as px
import logging

from database import Database, run_async

logger = logging.getLogger(__name__)

def render_analytics():
    """Render analytics page."""
    
    st.markdown("## 📊 Analytics & Insights")
    st.markdown("---")

    try:
        analytics = run_async(Database.get_analytics())
    except Exception as e:
        st.error(f"Failed to load analytics: {e}")
        return

    # ─────────────────────────────────────────────────────
    # KEY METRICS
    # ─────────────────────────────────────────────────────

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Studies", analytics.get("total_studies", 0))

    with col2:
        st.metric("Total Signals", analytics.get("total_signals", 0))

    with col3:
        approval_rate = analytics.get("approval_rate", 0)
        st.metric("Approval Rate", f"{approval_rate:.1f}%")

    with col4:
        total_reviewed = analytics.get("total_reviewed", 0)
        st.metric("Reviewed Signals", total_reviewed)

    st.markdown("")

    # ─────────────────────────────────────────────────────
    # CHARTS
    # ─────────────────────────────────────────────────────

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Signal Status Distribution")
        status_data = analytics.get("status_breakdown", {})
        if status_data:
            fig = px.pie(
                names=list(status_data.keys()),
                values=list(status_data.values()),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available")

    with col2:
        st.markdown("### Signals by Agent")
        agent_data = analytics.get("agent_breakdown", {})
        if agent_data:
            df = pd.DataFrame({
                "Agent": list(agent_data.keys()),
                "Count": list(agent_data.values()),
            })
            fig = px.bar(df, x="Agent", y="Count")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available")

    st.markdown("")
    st.info(
        """
        📌 **More analytics coming soon:**
        - Sponsor credibility trends over time
        - Signal approval trends
        - Agent performance metrics
        - Custom time period filtering
        """
    )
