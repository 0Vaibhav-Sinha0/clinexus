##############################################################################
# app/streamlit_app/config.py
#
# Configuration, constants, and styling for the Streamlit app.
##############################################################################

import os
from enum import Enum

# ─────────────────────────────────────────────────────────────
# ENVIRONMENT & DEPLOYMENT
# ─────────────────────────────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "clinical_trial_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# ─────────────────────────────────────────────────────────────
# APP CONFIGURATION
# ─────────────────────────────────────────────────────────────

APP_TITLE = "Clinexus"
APP_ICON = "🔬"
APP_DESCRIPTION = "AI-Powered Clinical Trial Intelligence Platform"

PAGE_CONFIG = {
    "page_title": f"{APP_TITLE} - Clinical Trial Analysis",
    "page_icon": APP_ICON,
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# ─────────────────────────────────────────────────────────────
# USER ROLES
# ─────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    ADMIN = "admin"

ROLE_PERMISSIONS = {
    UserRole.RESEARCHER: ["upload", "analyze", "view_own_analyses", "search"],
    UserRole.REVIEWER: ["review_signals", "approve_signals", "view_all_analyses", "search", "view_sponsors"],
    UserRole.ADMIN: ["upload", "analyze", "review_signals", "approve_signals", "view_all_analyses", "search", "view_sponsors", "manage_users", "view_logs"],
}

# ─────────────────────────────────────────────────────────────
# SIGNAL STATUSES
# ─────────────────────────────────────────────────────────────

class SignalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MARKED_FALSE_POSITIVE = "marked_false_positive"

SIGNAL_STATUS_COLORS = {
    SignalStatus.PENDING: "#FFA500",      # Orange
    SignalStatus.APPROVED: "#28A745",     # Green
    SignalStatus.REJECTED: "#DC3545",     # Red
    SignalStatus.MARKED_FALSE_POSITIVE: "#6C757D",  # Gray
}

SIGNAL_STATUS_LABELS = {
    SignalStatus.PENDING: "⏳ Pending Review",
    SignalStatus.APPROVED: "✅ Approved",
    SignalStatus.REJECTED: "❌ Rejected",
    SignalStatus.MARKED_FALSE_POSITIVE: "⚪ False Positive",
}

# ─────────────────────────────────────────────────────────────
# AGENT NAMES & COLORS
# ─────────────────────────────────────────────────────────────

AGENT_NAMES = [
    "missing_results_agent",
    "broken_promises_agent",
    "track_record_agent",
    "pattern_finder_agent",
    "side_effect_agent",
    "timeline_agent",
]

AGENT_COLORS = {
    "missing_results_agent": "#FF6B6B",
    "broken_promises_agent": "#4ECDC4",
    "track_record_agent": "#45B7D1",
    "pattern_finder_agent": "#FFA07A",
    "side_effect_agent": "#98D8C8",
    "timeline_agent": "#F7DC6F",
}

AGENT_DESCRIPTIONS = {
    "missing_results_agent": "Identifies unreported trial outcomes",
    "broken_promises_agent": "Detects unfulfilled commitments",
    "track_record_agent": "Evaluates sponsor credibility",
    "pattern_finder_agent": "Discovers recurring sponsor patterns",
    "side_effect_agent": "Analyzes adverse event reporting gaps",
    "timeline_agent": "Detects recruitment and completion delays",
}

# ─────────────────────────────────────────────────────────────
# SIGNAL TYPES
# ─────────────────────────────────────────────────────────────

SIGNAL_TYPES = {
    "timeline_delay": "Timeline Delay",
    "broken_promise": "Broken Promise",
    "missing_results": "Missing Results",
    "safety_gap": "Safety Gap",
    "inconsistency": "Inconsistency",
    "pattern": "Recurring Pattern",
}

# ─────────────────────────────────────────────────────────────
# SPONSOR CREDIBILITY RISK LEVELS
# ─────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

RISK_LEVEL_COLORS = {
    RiskLevel.LOW: "#28A745",      # Green
    RiskLevel.MEDIUM: "#FFC107",   # Yellow
    RiskLevel.HIGH: "#FF6B6B",     # Red
    RiskLevel.CRITICAL: "#8B0000", # Dark Red
}

def get_risk_level(credibility_score: float) -> RiskLevel:
    """Convert credibility score (0-100) to risk level."""
    if credibility_score >= 80:
        return RiskLevel.LOW
    elif credibility_score >= 60:
        return RiskLevel.MEDIUM
    elif credibility_score >= 40:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL

# ─────────────────────────────────────────────────────────────
# UI STYLING
# ─────────────────────────────────────────────────────────────

STREAMLIT_THEME = {
    "primaryColor": "#4ECDC4",
    "backgroundColor": "#FFFFFF",
    "secondaryBackgroundColor": "#F0F2F6",
    "textColor": "#262730",
    "font": "sans serif",
}

# ─────────────────────────────────────────────────────────────
# PAGINATION & LIMITS
# ─────────────────────────────────────────────────────────────

ITEMS_PER_PAGE = 25
MAX_BATCH_UPLOAD = 100
ANALYSIS_TIMEOUT_SECONDS = 300  # 5 minutes

# ─────────────────────────────────────────────────────────────
# CACHE SETTINGS
# ─────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 300  # 5 minutes for expensive queries
