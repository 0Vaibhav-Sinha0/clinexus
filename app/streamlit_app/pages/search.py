##############################################################################
# app/streamlit_app/pages/search.py
#
# Search & Filter page: Global search across studies, sponsors, signals.
##############################################################################

import streamlit as st
import pandas as pd
import logging

from database import Database, run_async

logger = logging.getLogger(__name__)

def render_search():
    """Render search page."""
    
    st.markdown("## 🔎 Search & Filter")
    st.markdown("Search across all clinical trials, sponsors, and signals")
    st.markdown("---")

    # ─────────────────────────────────────────────────────
    # SEARCH BAR
    # ─────────────────────────────────────────────────────

    search_query = st.text_input(
        "Search",
        placeholder="NCT ID, sponsor name, condition...",
        help="Search across studies, sponsors, and signals",
    )

    search_type = st.radio(
        "Search by",
        ["All", "NCT ID", "Sponsor", "Condition"],
        horizontal=True,
    )

    if search_query:
        try:
            results = run_async(
                Database.search_studies(search_query, limit=50)
            )

            if results:
                st.markdown(f"### {len(results)} Result(s)")

                result_df = pd.DataFrame({
                    "NCT ID": [r.get("nct_id") for r in results],
                    "Title": [r.get("title", "N/A")[:60] + "..." for r in results],
                    "Sponsor": [r.get("sponsor", "N/A") for r in results],
                    "Status": [r.get("status", "N/A") for r in results],
                })

                st.dataframe(result_df, use_container_width=True, hide_index=True)
            else:
                st.info(f"No results found for: {search_query}")

        except Exception as e:
            st.error(f"Search failed: {e}")

    else:
        st.info(
            """
            💡 **Try searching for:**
            - NCT IDs (e.g., "NCT04788680")
            - Sponsor names (e.g., "Novo Nordisk")
            - Medical conditions (e.g., "Type 2 Diabetes")
            """
        )
