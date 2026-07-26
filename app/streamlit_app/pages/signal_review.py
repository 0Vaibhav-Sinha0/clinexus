##############################################################################
# app/streamlit_app/pages/signal_review.py
#
# Signal Review page: Reviewers approve/reject signals with evidence.
# This is the Human-in-the-Loop (HITL) gate.
##############################################################################

import streamlit as st
import pandas as pd
import logging
from datetime import datetime

from auth import get_current_user_email, require_permission
from database import Database, run_async
from config import SIGNAL_STATUS_LABELS, SIGNAL_STATUS_COLORS, AGENT_COLORS

logger = logging.getLogger(__name__)

def render_signal_review():
    """Render signal review page."""
    
    require_permission("review_signals")

    st.markdown("## 🔍 Signal Review (HITL Gate)")
    st.markdown(
        "Approve or reject AI-generated signals. Your approval adds them to the knowledge base."
    )
    st.markdown("---")

    # ─────────────────────────────────────────────────────
    # FILTERS SIDEBAR
    # ─────────────────────────────────────────────────────

    with st.sidebar:
        st.markdown("### Filters")

        status_filter = st.multiselect(
            "Signal Status",
            options=["pending", "approved", "rejected"],
            default=["pending"],
        )

        agent_filter = st.multiselect(
            "Agent",
            options=[
                "missing_results_agent",
                "broken_promises_agent",
                "track_record_agent",
                "pattern_finder_agent",
                "side_effect_agent",
                "timeline_agent",
            ],
            label_visibility="collapsed",
        )

        confidence_min = st.slider(
            "Minimum Confidence",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.1,
        )

        nct_id_filter = st.text_input(
            "NCT ID",
            placeholder="e.g., NCT04788680",
            label_visibility="collapsed",
        )

    # ─────────────────────────────────────────────────────
    # FETCH SIGNALS
    # ─────────────────────────────────────────────────────

    try:
        # Build query parameters
        query_params = {
            "status": status_filter[0] if status_filter else "pending",
            "confidence_min": confidence_min,
            "limit": 25,
            "offset": 0,
        }

        if agent_filter:
            query_params["agent_name"] = agent_filter[0]

        signals, total = run_async(
            Database.get_signals(**query_params)
        )

    except Exception as e:
        st.error(f"Failed to load signals: {e}")
        return

    # ─────────────────────────────────────────────────────
    # DISPLAY SIGNALS
    # ─────────────────────────────────────────────────────

    if not signals:
        st.info(f"📭 No signals found matching filters")
        return

    st.markdown(f"### {len(signals)} Signal(s) Found")

    # Create tabs for each signal
    for signal in signals:
        with st.expander(
            f"**{signal['agent_name']}** | Confidence: {signal['confidence']:.2f} | {signal['nct_id']}"
        ):
            render_signal_detail(signal)


def render_signal_detail(signal: dict):
    """Render detailed signal view for approval/rejection."""
    
    signal_id = signal.get("signal_id")
    status = signal.get("status", "pending")

    # ─────────────────────────────────────────────────────
    # HEADER
    # ─────────────────────────────────────────────────────

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"**NCT ID:** {signal.get('nct_id', 'N/A')}")
        st.markdown(f"**Agent:** {signal.get('agent_name', 'N/A')}")

    with col2:
        st.markdown(f"**Confidence:** {signal.get('confidence', 0):.2%}")
        st.markdown(f"**Type:** {signal.get('signal_type', 'N/A')}")

    with col3:
        status_label = SIGNAL_STATUS_LABELS.get(status, status)
        st.markdown(f"**Status:** {status_label}")

    st.markdown("---")

    # ─────────────────────────────────────────────────────
    # SIGNAL CONTENT
    # ─────────────────────────────────────────────────────

    st.markdown("### Summary")
    st.markdown(signal.get("summary", "No summary available"))

    # Evidence section
    evidence = signal.get("evidence", {})
    if evidence:
        st.markdown("### Evidence")
        with st.expander("Show Evidence Details"):
            evidence_list = evidence if isinstance(evidence, list) else [evidence]
            for idx, evidence_item in enumerate(evidence_list, 1):
                st.markdown(f"**Evidence {idx}:**")
                st.markdown(f"- **Source:** {evidence_item.get('source', 'Unknown')}")
                st.markdown(f"- **Quote:** _{evidence_item.get('quote', 'N/A')}_")
                st.markdown(f"- **Relevance:** {evidence_item.get('relevance', 'N/A')}")
                st.markdown("")

    # Existing review (if already approved/rejected)
    if status != "pending":
        st.markdown("### Review History")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Reviewed by:** {signal.get('reviewed_by', 'N/A')}")

        with col2:
            reviewed_at = signal.get("reviewed_at")
            if reviewed_at:
                st.markdown(f"**Reviewed at:** {reviewed_at}")

        if signal.get("reviewer_comment"):
            st.markdown(f"**Comment:** _{signal.get('reviewer_comment')}_")

        st.markdown("")
        st.info(f"This signal has already been {status.upper()}")

    # ─────────────────────────────────────────────────────
    # APPROVAL WORKFLOW (only for pending signals)
    # ─────────────────────────────────────────────────────

    if status == "pending":
        st.markdown("---")
        st.markdown("### Your Review")

        reviewer_comment = st.text_area(
            "Add a comment (optional)",
            placeholder="Explain your decision...",
            height=100,
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "✅ Approve Signal",
                use_container_width=True,
                key=f"approve_{signal_id}",
            ):
                approve_signal(signal_id, reviewer_comment)

        with col2:
            if st.button(
                "❌ Reject Signal",
                use_container_width=True,
                key=f"reject_{signal_id}",
            ):
                reject_signal(signal_id, reviewer_comment)

        with col3:
            if st.button(
                "⚪ Mark False Positive",
                use_container_width=True,
                key=f"false_positive_{signal_id}",
            ):
                mark_false_positive(signal_id, reviewer_comment)


def approve_signal(signal_id: str, comment: str = ""):
    """Approve a signal."""
    try:
        reviewer_email = get_current_user_email()
        result = run_async(
            Database.approve_signal(signal_id, reviewer_email, comment)
        )
        st.success("✅ Signal approved!")
        st.balloons()
        # Rerun to refresh
        st.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"Failed to approve signal: {e}")
        logger.error(f"Approval error: {e}")


def reject_signal(signal_id: str, comment: str = ""):
    """Reject a signal."""
    try:
        reviewer_email = get_current_user_email()
        result = run_async(
            Database.reject_signal(signal_id, reviewer_email, comment)
        )
        st.success("❌ Signal rejected")
        st.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"Failed to reject signal: {e}")
        logger.error(f"Rejection error: {e}")


def mark_false_positive(signal_id: str, comment: str = ""):
    """Mark signal as false positive."""
    try:
        reviewer_email = get_current_user_email()
        # Note: Would need to add this to database module
        st.info("⚪ Marked as false positive (feature coming soon)")
    except Exception as e:
        st.error(f"Failed to mark signal: {e}")
