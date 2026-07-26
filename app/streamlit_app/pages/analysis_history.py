##############################################################################
# app/streamlit_app/pages/analysis_history.py
#
# Analysis History page: Browse past analyses and their results.
##############################################################################

import streamlit as st
import pandas as pd
import logging

from auth import get_current_user_email, get_current_user_role
from database import Database, run_async
from config import UserRole

logger = logging.getLogger(__name__)

def render_analysis_history():
    """Render analysis history page."""
    
    st.markdown("## 📋 Analysis History")
    st.markdown("Browse past clinical trial analyses")
    st.markdown("---")

    # ─────────────────────────────────────────────────────
    # FILTERS
    # ─────────────────────────────────────────────────────

    with st.sidebar:
        st.markdown("### Filters")

        status_filter = st.multiselect(
            "Status",
            options=["pending", "complete", "error"],
            default=["complete"],
        )

        limit = st.slider(
            "Results per page",
            min_value=10,
            max_value=100,
            value=25,
        )

    # ─────────────────────────────────────────────────────
    # FETCH ANALYSES
    # ─────────────────────────────────────────────────────

    try:
        # Researchers only see their own analyses
        role = get_current_user_role()
        researcher_id = None
        if role == UserRole.RESEARCHER:
            researcher_id = get_current_user_email()

        analyses, total = run_async(
            Database.get_analyses(
                researcher_id=researcher_id,
                limit=limit,
                offset=0,
            )
        )

    except Exception as e:
        st.error(f"Failed to load analyses: {e}")
        return

    # ─────────────────────────────────────────────────────
    # DISPLAY ANALYSES
    # ─────────────────────────────────────────────────────

    if analyses:
        st.markdown(f"### {len(analyses)} Analysis/Analyses")

        analysis_df = pd.DataFrame({
            "NCT ID": [a.get("nct_id") for a in analyses],
            "Status": [a.get("status", "unknown").upper() for a in analyses],
            "Signals": [a.get("total_signals", 0) for a in analyses],
            "Created": [str(a.get("created_at", ""))[:10] for a in analyses],
            "Researcher": [a.get("researcher_id", "N/A")[:30] for a in analyses],
        })

        st.dataframe(
            analysis_df,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info("📭 No analyses found")

    st.markdown("")
    st.info("📌 Click on a row to view detailed results")
