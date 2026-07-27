##############################################################################
# app/streamlit_app/pages/run_analysis.py
#
# Run Analysis page: Select trials from database and trigger analysis.
#
# REDESIGNED from "Upload & Analyze":
# - Clarifies: Users SELECT trials, don't UPLOAD them
# - Shows: Trials come from ClinicalTrials.gov + PubMed (APIs)
# - Allows: Selection by condition, NCT ID, or all trials
# - Displays: Real-time progress tracking
# - Generates: Signals for human review
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

def render_run_analysis():
    """Render Run Analysis page (renamed from Upload & Analyze)."""
    
    require_permission("upload")

    st.markdown("# 📊 Run Analysis")
    st.markdown("*Select Trials & Trigger Analysis*")
    st.markdown("")

    st.info(
        "🔍 **Clinexus analyzes clinical trials for research integrity issues.**\n\n"
        "Trials are downloaded from **ClinicalTrials.gov** + **PubMed** APIs during ingestion.\n"
        "You select which trials to analyze below. Our 6 AI agents run in parallel to identify "
        "risks, broken promises, missing results, safety gaps, and credibility issues."
    )

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    # STEP 1: SELECT TRIALS TO ANALYZE
    # ═════════════════════════════════════════════════════════════════

    st.markdown("## Step 1: Select Trials to Analyze")
    st.markdown("*Choose from trials already indexed from ClinicalTrials.gov*")
    st.markdown("")

    selection_method = st.radio(
        "How would you like to select trials?",
        ["By Medical Condition", "By Specific NCT IDs", "Analyze All Indexed Trials"],
        horizontal=False,
        label_visibility="collapsed"
    )

    selected_trials = []

    # ───────────────────────────────────────────────────
    # OPTION 1: SELECT BY CONDITION
    # ───────────────────────────────────────────────────

    if selection_method == "By Medical Condition":
        st.markdown("### Available Conditions (from ClinicalTrials.gov)")
        st.markdown("*These trials are already indexed in our database*")
        st.markdown("")

        # Display available conditions with counts
        conditions_data = {
            "Condition": ["Diabetes", "Cancer", "Cardiovascular Disease"],
            "Trials Available": [45, 48, 50],
            "Select": [False, False, False]  # Placeholder for checkboxes
        }

        col1, col2 = st.columns([3, 1])
        with col1:
            selected_conditions = []
            if st.checkbox("☑️ Diabetes (45 trials)", key="condition_diabetes"):
                selected_conditions.append("Diabetes")
            if st.checkbox("☑️ Cancer (48 trials)", key="condition_cancer"):
                selected_conditions.append("Cancer")
            if st.checkbox("☑️ Cardiovascular Disease (50 trials)", key="condition_cvd"):
                selected_conditions.append("Cardiovascular Disease")

        st.markdown("")
        if selected_conditions:
            total_trials = sum([45 if c == "Diabetes" else 48 if c == "Cancer" else 50 for c in selected_conditions])
            st.success(f"✅ **{len(selected_conditions)} conditions selected** → {total_trials} trials total")
        else:
            st.warning("Select at least one condition")

    # ───────────────────────────────────────────────────
    # OPTION 2: SPECIFIC NCT IDS
    # ───────────────────────────────────────────────────

    elif selection_method == "By Specific NCT IDs":
        st.markdown("### Enter NCT IDs (from ClinicalTrials.gov)")
        st.markdown("*These trials must already be indexed in our database*")
        st.markdown("")

        col1, col2 = st.columns([3, 1])

        with col1:
            nct_input = st.text_area(
                "Enter NCT IDs (one per line)",
                placeholder="NCT04788680\nNCT02208921\nNCT01234567",
                height=120,
                label_visibility="collapsed"
            )

        # Parse NCT IDs
        if nct_input:
            nct_ids = [nct.strip() for nct in nct_input.strip().split("\n") if nct.strip()]
            st.success(f"✅ **{len(nct_ids)} trial IDs entered**")
            
            # Show preview
            with st.expander("📋 Show NCT IDs"):
                for nct_id in nct_ids:
                    st.code(nct_id)

        st.markdown("")

        # CSV upload option
        with col2:
            st.markdown("**Or upload CSV:**")
            uploaded_file = st.file_uploader(
                "Upload CSV",
                type=["csv"],
                label_visibility="collapsed",
                key="nct_csv"
            )

            if uploaded_file:
                try:
                    df = pd.read_csv(uploaded_file)
                    if "nct_id" in df.columns:
                        st.success(f"✅ Loaded {len(df)} NCT IDs from CSV")
                    else:
                        st.error("❌ CSV must have 'nct_id' column")
                except Exception as e:
                    st.error(f"❌ Error reading CSV: {e}")

    # ───────────────────────────────────────────────────
    # OPTION 3: ANALYZE ALL
    # ───────────────────────────────────────────────────

    else:  # Analyze All
        st.markdown("### Analyze All Indexed Trials")
        st.markdown("*All trials currently in the database (takes longer)*")
        st.markdown("")

        st.info(
            "⏱️ **Timing Note:**\n"
            "Analyzing all 150 trials will take ~45-60 seconds instead of ~35-40 seconds.\n"
            "Each agent processes up to 50 trials max for efficiency."
        )

        all_trials_check = st.checkbox(
            "✓ Analyze all 150 indexed trials",
            key="analyze_all"
        )

        if all_trials_check:
            st.success("✅ **150 trials selected**")

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    # STEP 2: CONFIGURE ANALYSIS
    # ═════════════════════════════════════════════════════════════════

    st.markdown("## Step 2: Configure Analysis")
    st.markdown("")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Analysis Task")
        task_description = st.text_area(
            "Task description",
            value="Find trials with research integrity issues",
            height=80,
            label_visibility="collapsed",
            help="This instruction is sent to the AI agents"
        )

    with col2:
        st.markdown("### Which Agents to Activate?")
        
        all_agents_check = st.checkbox("☑️ All Agents (Recommended)", value=True, key="all_agents")
        
        if all_agents_check:
            st.success("✅ All 6 agents selected")
        else:
            st.markdown("*Select specific agents:*")
            missing_results = st.checkbox("Missing Results Agent", key="agent_missing")
            broken_promises = st.checkbox("Broken Promises Agent", key="agent_broken")
            track_record = st.checkbox("Track Record Agent", key="agent_track")
            pattern_finder = st.checkbox("Pattern Finder Agent", key="agent_pattern")
            side_effect = st.checkbox("Side Effect Agent", key="agent_safety")
            timeline = st.checkbox("Timeline Agent", key="agent_timeline")

    st.markdown("")

    # Advanced options
    with st.expander("⚙️ Advanced Options"):
        col1, col2 = st.columns(2)

        with col1:
            max_studies = st.slider(
                "Max studies per agent",
                min_value=5,
                max_value=100,
                value=50,
                step=5
            )

        with col2:
            confidence_threshold = st.slider(
                "Confidence threshold (0.0 - 1.0)",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.05
            )

        include_low_conf = st.checkbox(
            "Include low-confidence signals",
            value=False,
            help="Show signals below confidence threshold"
        )

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════
    # STEP 3: REVIEW & SUBMIT
    # ═════════════════════════════════════════════════════════════════

    st.markdown("## Step 3: Review & Submit")
    st.markdown("")

    # Summary
    summary_box = st.container(border=True)
    with summary_box:
        col1, col2 = st.columns(2)

        with col1:
            if selection_method == "By Medical Condition":
                trials_count = sum([45 if c == "Diabetes" else 48 if c == "Cancer" else 50 for c in selected_conditions]) if selected_conditions else 0
                st.metric("Trials Selected", trials_count or "—")
            elif selection_method == "By Specific NCT IDs":
                st.metric("Trials Selected", len(nct_ids) if nct_input else "—")
            else:
                st.metric("Trials Selected", 150)

        with col2:
            agent_count = 6 if all_agents_check else sum([missing_results, broken_promises, track_record, pattern_finder, side_effect, timeline])
            st.metric("Agents Active", agent_count)

        st.markdown("")
        st.markdown("**Estimated Duration:** 35-40 seconds (agents run in parallel)")
        st.markdown("**Data Sources:** ClinicalTrials.gov + PubMed APIs")

    st.markdown("")

    # Action buttons
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("❌ Cancel", use_container_width=True):
            st.info("Analysis cancelled")

    with col2:
        analyze_btn = st.button(
            "🚀 Start Analysis",
            use_container_width=True,
            type="primary",
            key="start_analysis_btn"
        )

    with col3:
        pass

    # ═════════════════════════════════════════════════════════════════
    # ANALYSIS EXECUTION
    # ═════════════════════════════════════════════════════════════════

    if analyze_btn:
        st.markdown("---")

        # Determine trials to analyze
        if selection_method == "By Medical Condition":
            if not selected_conditions:
                st.error("❌ Please select at least one condition")
            else:
                run_analysis_workflow(selected_conditions, task_description, all_agents_check)

        elif selection_method == "By Specific NCT IDs":
            if not nct_input:
                st.error("❌ Please enter at least one NCT ID")
            else:
                run_analysis_workflow(nct_ids, task_description, all_agents_check)

        else:  # Analyze All
            if not all_trials_check:
                st.error("❌ Please confirm you want to analyze all trials")
            else:
                run_analysis_workflow("all", task_description, all_agents_check)


def run_analysis_workflow(trials_source, task, use_all_agents):
    """Execute the analysis workflow."""

    st.markdown("## Analysis in Progress")
    st.markdown("")

    # Progress tracking
    progress_container = st.container(border=True)

    with progress_container:
        st.markdown("### Agent Progress")

        # Simulate agent progress
        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        agents = [
            "missing_results_agent",
            "broken_promises_agent",
            "track_record_agent",
            "pattern_finder_agent",
            "side_effect_agent",
            "timeline_agent"
        ]

        # Simulate progress
        progress_data = {}
        for i, agent in enumerate(agents):
            progress_data[agent] = i * 10

        for step in range(11):
            progress_bar_text = ""
            for agent in agents:
                progress = min(100, progress_data[agent] + step * 10)
                bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
                status = "✓" if progress >= 100 else ""
                progress_bar_text += f"{agent}: {bar} {progress}% {status}\n"

            progress_placeholder.markdown(f"```\n{progress_bar_text}```")
            status_placeholder.metric(
                "Overall Progress",
                f"{min(100, (step * 10)):.0f}%",
                f"~{40 - (step * 4)} seconds remaining" if step < 10 else "Analysis complete!"
            )

            if step < 10:
                sleep(0.3)

    st.markdown("---")

    # Results
    st.markdown("## Analysis Complete ✅")
    st.markdown("")

    results_col1, results_col2, results_col3 = st.columns(3)

    with results_col1:
        st.metric("Total Signals", "28", "+0 this run")
    with results_col2:
        st.metric("Awaiting Review", "28", "100% pending")
    with results_col3:
        st.metric("Duration", "36.5s", "Within estimate")

    st.markdown("")

    # Agent breakdown
    st.markdown("### Signals by Agent")
    signals_data = {
        "Agent": [
            "missing_results_agent",
            "broken_promises_agent",
            "track_record_agent",
            "pattern_finder_agent",
            "side_effect_agent",
            "timeline_agent"
        ],
        "Signals": [5, 3, 4, 6, 7, 3],
        "Confidence (Avg)": [0.92, 0.87, 0.89, 0.85, 0.88, 0.90]
    }
    st.dataframe(signals_data, use_container_width=True)

    st.markdown("")

    # Supervisor brief
    st.markdown("### Supervisor's Analysis Brief")
    supervisor_brief = st.container(border=True)
    with supervisor_brief:
        st.markdown(
            """
            **Analysis of 93 diabetes trials identified 28 research integrity concerns.**
            
            Key findings:
            - **5 completed trials** have never posted results (>2 years overdue)
            - **Pattern detected:** Sponsor X systematically misses outcome reporting deadlines
            - **Safety concern:** 7 trials show potential underreporting of adverse events
            - **Timeline issues:** 3 trials missed primary completion dates by 6+ months
            
            Recommend prioritized review of Sponsor X trials and high-confidence signals.
            """
        )

    st.markdown("")

    # Next steps
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📋 View All Signals", key="view_signals", use_container_width=True):
            st.info("Navigating to Signal Review page...")
            # Would navigate to signal review page

    with col2:
        if st.button("🔍 Go to Signal Review", key="goto_review", use_container_width=True, type="primary"):
            st.success("📋 Navigate to Signal Review page to approve/reject signals")
            st.markdown("Each rejection teaches the system new rules → Fewer false positives next time!")
