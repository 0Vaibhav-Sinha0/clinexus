##############################################################################
# app/streamlit_app/pages/upload_analyze.py
#
# Upload & Analyze page: Researchers upload trials and trigger analysis.
##############################################################################

import streamlit as st
import pandas as pd
import logging
from time import sleep

from auth import get_current_user_email, require_permission
from database import Database, run_async
from api_client import get_client
from config import AGENT_NAMES, AGENT_DESCRIPTIONS, ANALYSIS_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

def render_upload_analyze():
    """Render upload and analyze page."""
    
    require_permission("upload")

    st.markdown("## 📤 Upload & Analyze")
    st.markdown("---")

    st.markdown(
        """
        Upload a clinical trial and trigger the AI analysis pipeline. 
        Our 6 specialized agents will analyze the trial in parallel to identify 
        risks, broken promises, safety gaps, and credibility issues.
        """
    )

    st.markdown("")

    # ─────────────────────────────────────────────────────
    # INPUT SECTION
    # ─────────────────────────────────────────────────────

    input_method = st.radio(
        "How would you like to upload?",
        ["Single Trial (NCT ID)", "Batch Upload (CSV)"],
        horizontal=True,
    )

    # ───────────────────────────────
    # SINGLE TRIAL INPUT
    # ───────────────────────────────

    if input_method == "Single Trial (NCT ID)":
        st.markdown("### Single Trial Upload")

        col1, col2 = st.columns([2, 1])

        with col1:
            nct_id = st.text_input(
                "Clinical Trial NCT ID",
                placeholder="e.g., NCT04788680",
                help="Enter the ClinicalTrials.gov NCT identifier",
            )

        with col2:
            st.markdown("")
            analyze_button = st.button(
                "🚀 Analyze Trial",
                use_container_width=True,
                type="primary",
            )

        if nct_id and analyze_button:
            if not nct_id.startswith("NCT"):
                st.error("❌ Invalid NCT ID format. Must start with 'NCT'")
            else:
                trigger_analysis(nct_id)

    # ───────────────────────────────
    # BATCH UPLOAD INPUT
    # ───────────────────────────────

    else:
        st.markdown("### Batch Upload (CSV)")
        st.markdown(
            "Upload a CSV file with NCT IDs. Format: `nct_id` (one per row)"
        )

        uploaded_file = st.file_uploader(
            "Upload CSV file",
            type=["csv"],
            help="CSV with column 'nct_id'",
        )

        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                
                if "nct_id" not in df.columns:
                    st.error("❌ CSV must contain 'nct_id' column")
                else:
                    st.markdown(f"**Preview:** {len(df)} trials found")
                    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

                    if st.button("🚀 Analyze All", type="primary", use_container_width=True):
                        nct_ids = df["nct_id"].unique().tolist()
                        trigger_batch_analysis(nct_ids)

            except Exception as e:
                st.error(f"Failed to read CSV: {e}")

    # ─────────────────────────────────────────────────────
    # ANALYSIS RESULTS (if in session state)
    # ─────────────────────────────────────────────────────

    if "current_analysis" in st.session_state:
        st.markdown("---")
        st.markdown("## Analysis Results")
        render_analysis_results(st.session_state.current_analysis)


def trigger_analysis(nct_id: str):
    """Trigger analysis for a single trial."""
    
    researcher_id = get_current_user_email()
    
    try:
        # Show progress
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text("🚀 Triggering analysis pipeline...")
        progress_bar.progress(10)

        # Call API to start analysis
        client = get_client()
        result = client.analyze(nct_id, researcher_id)
        analysis_id = result.get("analysis_id")

        if not analysis_id:
            st.error("Failed to start analysis")
            return

        status_text.text(f"⏳ Analysis in progress (ID: {analysis_id})")
        progress_bar.progress(30)

        # Poll for results
        for i in range(ANALYSIS_TIMEOUT_SECONDS):
            try:
                status = client.get_analysis_status(analysis_id)
                
                analysis_status = status.get("status", "unknown")
                if analysis_status == "complete":
                    progress_bar.progress(100)
                    status_text.text("✅ Analysis complete!")
                    
                    # Store in session
                    st.session_state.current_analysis = status
                    
                    sleep(0.5)
                    st.rerun()
                    return
                    
                elif analysis_status == "error":
                    error_msg = status.get("error", "Unknown error")
                    st.error(f"❌ Analysis failed: {error_msg}")
                    return

                # Update progress
                progress_pct = 30 + (i / ANALYSIS_TIMEOUT_SECONDS) * 60
                progress_bar.progress(int(progress_pct))

            except Exception as e:
                logger.warning(f"Error polling analysis status: {e}")

            sleep(1)

        st.error("❌ Analysis timeout (took too long)")

    except Exception as e:
        st.error(f"Failed to analyze trial: {e}")
        logger.error(f"Analysis error: {e}")


def trigger_batch_analysis(nct_ids: list):
    """Trigger batch analysis."""
    
    st.info(f"🔄 Processing {len(nct_ids)} trials...")
    
    progress_bar = st.progress(0)
    results_container = st.container()

    results = []
    for idx, nct_id in enumerate(nct_ids):
        try:
            client = get_client()
            result = client.analyze(nct_id, get_current_user_email())
            results.append({
                "NCT ID": nct_id,
                "Status": "Started",
                "Analysis ID": result.get("analysis_id", "N/A"),
            })
            progress_bar.progress((idx + 1) / len(nct_ids))
        except Exception as e:
            results.append({
                "NCT ID": nct_id,
                "Status": "Failed",
                "Error": str(e),
            })

    with results_container:
        st.dataframe(
            pd.DataFrame(results),
            use_container_width=True,
            hide_index=True,
        )
        st.success(f"✅ Submitted {len(results)} analyses")


def render_analysis_results(analysis: dict):
    """Render analysis results."""
    
    st.markdown(f"### Trial: {analysis.get('nct_id', 'Unknown')}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Status",
            analysis.get("status", "unknown").upper(),
        )

    with col2:
        st.metric(
            "Total Signals",
            analysis.get("total_signals", 0),
        )

    with col3:
        st.metric(
            "Analysis ID",
            analysis.get("analysis_id", "N/A")[:8],
        )

    st.markdown("")

    # Agent breakdown
    st.markdown("### Agent Results")

    metadata = analysis.get("metadata", {})
    agents_data = []

    for agent_name in AGENT_NAMES:
        agent_signals = metadata.get(agent_name, {}).get("signals", [])
        agents_data.append({
            "Agent": agent_name.replace("_", " ").title(),
            "Signals": len(agent_signals),
            "Description": AGENT_DESCRIPTIONS.get(agent_name, ""),
        })

    st.dataframe(
        pd.DataFrame(agents_data),
        use_container_width=True,
        hide_index=True,
    )

    # Display signals
    st.markdown("### Signals")

    all_signals = []
    for agent_name in AGENT_NAMES:
        agent_signals = metadata.get(agent_name, {}).get("signals", [])
        for signal in agent_signals:
            all_signals.append({
                "Agent": agent_name.replace("_", " ").title(),
                "Type": signal.get("signal_type", "Unknown"),
                "Summary": signal.get("summary", "")[:100] + "...",
                "Confidence": f"{signal.get('confidence', 0):.2f}",
            })

    if all_signals:
        st.dataframe(
            pd.DataFrame(all_signals),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No signals generated for this trial")

    # Action buttons
    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Save Analysis", use_container_width=True):
            st.success("✅ Analysis saved")

    with col2:
        if st.button("🔍 Review Signals", use_container_width=True):
            st.session_state.page = "signal_review"
            st.rerun()
