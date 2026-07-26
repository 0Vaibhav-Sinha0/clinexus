##############################################################################
# app/streamlit_app/auth.py
#
# Simple authentication and authorization for Streamlit app.
# For MVP: email-based login (no password required for demo).
# For production: integrate OAuth2 (Google, GitHub, etc).
##############################################################################

import streamlit as st
from typing import Optional, List
import logging

from config import UserRole, ROLE_PERMISSIONS
from database import Database, run_async

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────

def init_session_state():
    """Initialize session state on first load."""
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "email" not in st.session_state:
        st.session_state.email = None
    if "role" not in st.session_state:
        st.session_state.role = None
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False

# ─────────────────────────────────────────────────────────────
# LOGIN / LOGOUT
# ─────────────────────────────────────────────────────────────

def login(email: str, role: str = UserRole.RESEARCHER) -> bool:
    """
    Authenticate user by email (MVP version - no password).
    Creates user if doesn't exist.
    """
    try:
        # Check if user exists
        user = run_async(Database.get_user(email))
        
        if user:
            st.session_state.user_id = user["email"]
            st.session_state.email = user["email"]
            st.session_state.role = user["role"]
        else:
            # Create new user
            user = run_async(Database.create_user(email, role))
            st.session_state.user_id = user["email"]
            st.session_state.email = user["email"]
            st.session_state.role = user["role"]

        st.session_state.is_authenticated = True
        logger.info(f"User logged in: {email} (role: {st.session_state.role})")
        return True

    except Exception as e:
        logger.error(f"Login failed for {email}: {e}")
        return False

def logout():
    """Log out current user."""
    st.session_state.user_id = None
    st.session_state.email = None
    st.session_state.role = None
    st.session_state.is_authenticated = False
    logger.info("User logged out")

# ─────────────────────────────────────────────────────────────
# AUTHORIZATION CHECKS
# ─────────────────────────────────────────────────────────────

def is_authenticated() -> bool:
    """Check if user is logged in."""
    return st.session_state.get("is_authenticated", False)

def get_current_user_email() -> Optional[str]:
    """Get current user's email."""
    return st.session_state.get("email")

def get_current_user_role() -> Optional[UserRole]:
    """Get current user's role."""
    return st.session_state.get("role")

def has_permission(permission: str) -> bool:
    """Check if current user has permission."""
    role = get_current_user_role()
    if not role:
        return False
    
    permissions = ROLE_PERMISSIONS.get(role, [])
    return permission in permissions

def require_authentication():
    """Redirect to login if not authenticated."""
    if not is_authenticated():
        st.warning("⚠️ Please log in to access this page")
        st.stop()

def require_role(*allowed_roles: UserRole):
    """Check if user has one of the allowed roles."""
    require_authentication()
    
    current_role = get_current_user_role()
    if current_role not in allowed_roles:
        st.error(f"❌ Access denied. Required role: {', '.join([r.value for r in allowed_roles])}")
        st.stop()

def require_permission(permission: str):
    """Check if user has specific permission."""
    require_authentication()
    
    if not has_permission(permission):
        st.error(f"❌ Access denied. You don't have permission: {permission}")
        st.stop()

# ─────────────────────────────────────────────────────────────
# LOGIN PAGE
# ─────────────────────────────────────────────────────────────

def render_login_page():
    """Render login page."""
    st.set_page_config(
        page_title="Clinexus - Login",
        page_icon="🔬",
        layout="centered",
    )

    # Centering container
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("---")
        st.markdown("# 🔬 **Clinexus**")
        st.markdown("### Clinical Trial Intelligence Platform")
        st.markdown("---")
        st.markdown("")

        # Email input
        email = st.text_input(
            "Email Address",
            placeholder="your@email.com",
            help="Enter your email to log in (MVP: no password required)",
        )

        # Role selector
        role = st.selectbox(
            "Your Role",
            options=[r.value for r in UserRole],
            format_func=lambda x: x.replace("_", " ").title(),
        )

        st.markdown("")
        st.markdown("")

        # Login button
        if st.button("🚀 Log In", use_container_width=True, type="primary"):
            if not email:
                st.error("❌ Please enter your email")
            elif "@" not in email:
                st.error("❌ Please enter a valid email")
            else:
                if login(email, role):
                    st.success("✅ Login successful!")
                    st.rerun()
                else:
                    st.error("❌ Login failed. Please try again.")

        st.markdown("")
        st.markdown("---")
        st.markdown(
            """
            **MVP Demo Mode:** 
            - Use any email to login
            - Roles: Researcher, Reviewer, Admin
            - Data persisted in database
            """
        )
