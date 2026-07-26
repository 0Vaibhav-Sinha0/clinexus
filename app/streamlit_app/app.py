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
    render_login_page,
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
    
    # Header with user info
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        st.markdown("# 🔬 **Clinexus**")
    with col3:
        email = get_current_user_email()
        role = get_current_user_role()
        st.markdown(f"**{email}** | {role.value.title()}")
        if st.button("🚪 Logout", key="logout_btn"):
            logout()
            st.rerun()

    st.markdown("---")

    # Sidebar navigation with role-based menu
    with st.sidebar:
        st.markdown("# Navigation")
        
        # Build menu items based on role
        role = get_current_user_role()
        
        menu_items = [
            ("🏠 Home", "home"),
        ]

        if role in [UserRole.RESEARCHER, UserRole.ADMIN]:
            menu_items.append(("📤 Upload & Analyze", "upload_analyze"))

        if role in [UserRole.REVIEWER, UserRole.ADMIN]:
            menu_items.append(("🔍 Signal Review", "signal_review"))

        menu_items.extend([
            ("📊 Analytics", "analytics"),
            ("🏢 Sponsor Profiles", "sponsor_profiles"),
            ("🔎 Search", "search"),
            ("📋 Analysis History", "analysis_history"),
        ])

        if role == UserRole.ADMIN:
            menu_items.append(("⚙️ Settings", "settings"))

        # Render option menu
        selected = option_menu(
            menu_primary="Menu",
            options=[item[0] for item in menu_items],
            icons=[item[0].split()[0] for item in menu_items],
            menu_icon="cast",
            default_index=0,
            key="main_menu",
        )

        # Map selected menu item to page key
        page_key = next(
            (item[1] for item in menu_items if item[0] == selected),
            "home"
        )

    # ─────────────────────────────────────────────────────────
    # PAGE ROUTING
    # ─────────────────────────────────────────────────────────

    if page_key == "home":
        from pages.home import render_home
        render_home()

    elif page_key == "upload_analyze":
        from pages.upload_analyze import render_upload_analyze
        render_upload_analyze()

    elif page_key == "signal_review":
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

    elif page_key == "analysis_history":
        from pages.analysis_history import render_analysis_history
        render_analysis_history()

    elif page_key == "settings":
        from pages.settings import render_settings
        render_settings()

    else:
        st.error("Unknown page")

# ─────────────────────────────────────────────────────────────
# APP ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if is_authenticated():
        render_main_app()
    else:
        render_login_page()
