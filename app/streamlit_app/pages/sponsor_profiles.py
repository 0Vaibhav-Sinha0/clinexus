##############################################################################
# app/streamlit_app/pages/sponsor_profiles.py
#
# Sponsor Profiles page: View sponsor credibility and history.
##############################################################################

import streamlit as st
import pandas as pd
import logging

from database import Database, run_async

logger = logging.getLogger(__name__)

def render_sponsor_profiles():
    """Render sponsor profiles page."""
    
    st.markdown("## 🏢 Sponsor Profiles")
    st.markdown("Search and view sponsor credibility profiles")
    st.markdown("---")

    # ─────────────────────────────────────────────────────
    # SEARCH
    # ─────────────────────────────────────────────────────

    sponsor_name = st.text_input(
        "Search Sponsor",
        placeholder="e.g., Novo Nordisk",
    )

    if sponsor_name:
        try:
            profile = run_async(
                Database.get_sponsor_profile(sponsor_name)
            )

            if profile:
                render_sponsor_detail(profile, sponsor_name)
            else:
                trials = run_async(
                    Database.get_sponsor_trials(sponsor_name)
                )

                if trials:
                    st.markdown(f"### {sponsor_name}")
                    st.markdown(f"**Trials found:** {len(trials)}")

                    trial_df = pd.DataFrame({
                        "NCT ID": [t.get("nct_id") for t in trials],
                        "Title": [t.get("title", "N/A")[:50] + "..." for t in trials],
                        "Signals": [t.get("signal_count", 0) for t in trials],
                    })

                    st.dataframe(trial_df, use_container_width=True, hide_index=True)
                else:
                    st.info(f"No data found for sponsor: {sponsor_name}")

        except Exception as e:
            st.error(f"Failed to load sponsor profile: {e}")


def render_sponsor_detail(profile: dict, sponsor_name: str):
    """Render sponsor detail view."""
    
    st.markdown(f"### {sponsor_name}")

    col1, col2, col3 = st.columns(3)

    with col1:
        credibility = profile.get("credibility_score", 0)
        st.metric("Credibility Score", f"{credibility:.0f}/100")

    with col2:
        total_trials = profile.get("total_trials", 0)
        st.metric("Total Trials", total_trials)

    with col3:
        results_posted_rate = profile.get("results_posted_rate", 0)
        st.metric("Results Posted Rate", f"{results_posted_rate:.1f}%")

    st.markdown("")
    st.info("📌 Full sponsor profile view coming soon")
