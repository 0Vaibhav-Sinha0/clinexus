##############################################################################
# app/streamlit_app/app.py
#
# Main entry point for Clinexus Streamlit application.
# Multi-page app with role-based access control.
##############################################################################

import streamlit as st
from streamlit_option_menu import option_menu
import logging

from config import PAGE_CONFIG, UserRole
from auth import (
    init_session_state,
    is_authenticated,
    get_current_user_email,
    get_current_user_role,
    logout,
    require_role,
)

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

st.set_page_config(**PAGE_CONFIG)

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize session state
init_session_state()

# ─────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────

def render_main_app():
    """Render authenticated main application."""
    
    # Header with user info and logout
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        st.markdown("# 🔬 **Clinexus**")
        st.markdown("*Clinical Trial Intelligence Platform*")
    with col3:
        email = get_current_user_email()
        role = get_current_user_role()
        st.markdown(f"**{email}**")
        st.markdown(f"*{role.value.title()}*")
        if st.button("🚪 Logout", key="logout_btn", use_container_width=True):
            logout()
            st.rerun()

    st.markdown("---")

    # Sidebar navigation with role-based menu (REDESIGNED)
    with st.sidebar:
        st.markdown("## 📋 Navigation")
        st.markdown("*Role-based access*")
        st.markdown("")
        
        # Get current role
        role = get_current_user_role()
        
        # Build menu items based on role and data source clarity
        menu_items = [
            ("🏠 Home", "home", "Dashboard & metrics"),
        ]

        # ADMIN ONLY: Data Management (NEW)
        if role == UserRole.ADMIN:
            menu_items.append(("🔬 Data Management", "data_management", "Ingestion & processing"))

        # ADMIN & RESEARCHER: Run Analysis (RENAMED from Upload & Analyze)
        if role in [UserRole.RESEARCHER, UserRole.ADMIN]:
            menu_items.append(("📊 Run Analysis", "run_analysis", "Select trials & analyze"))

        # ADMIN & REVIEWER: Signal Review
        if role in [UserRole.REVIEWER, UserRole.ADMIN]:
            menu_items.append(("🔍 Signal Review", "signal_review", "HITL approval gate"))

        # ALL USERS: Analytics, Search, Sponsor Intelligence
        menu_items.extend([
            ("📈 Analytics", "analytics", "Metrics & trends"),
            ("🏢 Sponsor Intelligence", "sponsor_profiles", "Risk profiles"),
            ("🔎 Search & Explore", "search", "Trial discovery"),
        ])

        # ADMIN ONLY: Settings
        if role == UserRole.ADMIN:
            menu_items.append(("⚙️ Settings", "settings", "System config"))

        # Render option menu with descriptions
        selected = option_menu(
            menu_primary="Menu",
            options=[item[0] for item in menu_items],
            icons=[item[0].split()[0] for item in menu_items],
            menu_icon="cast",
            default_index=0,
            key="main_menu",
        )

        # Show description of selected page
        st.markdown("---")
        description = next(
            (item[2] for item in menu_items if item[0] == selected),
            ""
        )
        if description:
            st.caption(f"📝 {description}")

        # Map selected menu item to page key
        page_key = next(
            (item[1] for item in menu_items if item[0] == selected),
            "home"
        )

    # ─────────────────────────────────────────────────────────
    # PAGE ROUTING (REDESIGNED)
    # ─────────────────────────────────────────────────────────

    if page_key == "home":
        from pages.home import render_home
        render_home()

    elif page_key == "data_management":
        # NEW PAGE: Data management (admin only)
        require_role(UserRole.ADMIN)
        from pages.data_management import render_data_management
        render_data_management()

    elif page_key == "run_analysis":
        # RENAMED from "upload_analyze" - Select trials to analyze
        require_role(UserRole.ADMIN, UserRole.RESEARCHER)
        from pages.run_analysis import render_run_analysis
        render_run_analysis()

    elif page_key == "signal_review":
        # HITL gate - Approve/reject signals
        require_role(UserRole.ADMIN, UserRole.REVIEWER)
        from pages.signal_review import render_signal_review
        render_signal_review()

    elif page_key == "analytics":
        from pages.analytics import render_analytics
        render_analytics()

    elif page_key == "sponsor_profiles":
        from pages.sponsor_profiles import render_sponsor_profiles
        render_sponsor_profiles()

    elif page_key == "search":
        from pages.search import render_search
        render_search()

    elif page_key == "settings":
        # Admin only
        require_role(UserRole.ADMIN)
        from pages.settings import render_settings
        render_settings()

    else:
        st.error("Unknown page")

# ─────────────────────────────────────────────────────────────
# APP ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Auto-authenticate as Admin (skip login page)
    # In production, use OAuth2 or SSO for proper auth
    if not is_authenticated():
        # Set default admin user
        st.session_state.user_id = "admin@clinexus.local"
        st.session_state.email = "admin@clinexus.local"
        st.session_state.role = UserRole.ADMIN
        st.session_state.is_authenticated = True
    
    render_main_app()
