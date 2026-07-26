##############################################################################
# app/streamlit_app/database.py
#
# Database connection pooling and query helpers for Streamlit.
##############################################################################

import asyncio
import streamlit as st
from datetime import datetime
import asyncpg
from typing import List, Dict, Any, Optional
import logging

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONNECTION POOL (singleton, reused across sessions)
# ─────────────────────────────────────────────────────────────

_pool = None

async def get_pool():
    """Get or create connection pool."""
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                min_size=5,
                max_size=20,
            )
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    return _pool

# ─────────────────────────────────────────────────────────────
# HELPER: Run async function in sync context (Streamlit)
# ─────────────────────────────────────────────────────────────

def run_async(coro):
    """Execute async function from Streamlit sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# ─────────────────────────────────────────────────────────────
# QUERY HELPERS
# ─────────────────────────────────────────────────────────────

class Database:
    """Database query interface for Streamlit app."""

    @staticmethod
    async def get_user(email: str) -> Optional[Dict[str, Any]]:
        """Fetch user by email."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1",
                email,
            )
            return dict(row) if row else None

    @staticmethod
    async def create_user(email: str, role: str) -> Dict[str, Any]:
        """Create new user."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, role, status, created_at)
                VALUES ($1, $2, 'active', NOW())
                RETURNING *
                """,
                email, role,
            )
            return dict(row)

    @staticmethod
    async def get_analyses(
        researcher_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Fetch analyses with pagination."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Build query
            where_clause = ""
            params = []
            if researcher_id:
                where_clause = "WHERE researcher_id = $1"
                params = [researcher_id]

            # Get total count
            count_query = f"SELECT COUNT(*) FROM analyses {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            query = f"""
                SELECT * FROM analyses
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${"$2" if researcher_id else "$1"}
                OFFSET ${"$3" if researcher_id else "$2"}
            """
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)
            
            return [dict(row) for row in rows], total

    @staticmethod
    async def get_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single analysis."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM analyses WHERE analysis_id = $1",
                analysis_id,
            )
            return dict(row) if row else None

    @staticmethod
    async def get_signals(
        analysis_id: Optional[str] = None,
        status: Optional[str] = None,
        agent_name: Optional[str] = None,
        confidence_min: float = 0.0,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Fetch signals with filtering."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Build dynamic query
            where_parts = ["confidence >= $5"]
            params = [confidence_min]
            param_idx = 6

            if analysis_id:
                where_parts.append(f"analysis_id = ${param_idx}")
                params.insert(0, analysis_id)
                param_idx += 1

            if status:
                where_parts.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            if agent_name:
                where_parts.append(f"agent_name = ${param_idx}")
                params.append(agent_name)
                param_idx += 1

            where_clause = "WHERE " + " AND ".join(where_parts)

            # Get total count
            count_query = f"SELECT COUNT(*) FROM signals {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            query = f"""
                SELECT * FROM signals
                {where_clause}
                ORDER BY confidence DESC, created_at DESC
                LIMIT ${param_idx}
                OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)

            return [dict(row) for row in rows], total

    @staticmethod
    async def get_signal(signal_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single signal."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM signals WHERE signal_id = $1",
                signal_id,
            )
            return dict(row) if row else None

    @staticmethod
    async def approve_signal(
        signal_id: str,
        reviewed_by: str,
        comment: str = "",
    ) -> Dict[str, Any]:
        """Approve a signal."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE signals
                SET status = 'approved',
                    reviewed_by = $2,
                    reviewed_at = NOW(),
                    reviewer_comment = $3,
                    updated_at = NOW()
                WHERE signal_id = $1
                RETURNING *
                """,
                signal_id, reviewed_by, comment,
            )
            return dict(row)

    @staticmethod
    async def reject_signal(
        signal_id: str,
        reviewed_by: str,
        comment: str = "",
    ) -> Dict[str, Any]:
        """Reject a signal."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE signals
                SET status = 'rejected',
                    reviewed_by = $2,
                    reviewed_at = NOW(),
                    reviewer_comment = $3,
                    updated_at = NOW()
                WHERE signal_id = $1
                RETURNING *
                """,
                signal_id, reviewed_by, comment,
            )
            return dict(row)

    @staticmethod
    async def get_sponsor_profile(sponsor_name: str) -> Optional[Dict[str, Any]]:
        """Fetch sponsor credibility profile."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sponsor_profiles WHERE sponsor_name = $1",
                sponsor_name,
            )
            return dict(row) if row else None

    @staticmethod
    async def get_sponsor_trials(
        sponsor_name: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch all trials for a sponsor."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.*, COUNT(sig.signal_id) as signal_count
                FROM studies s
                LEFT JOIN signals sig ON s.nct_id = sig.nct_id
                WHERE s.sponsor = $1
                GROUP BY s.nct_id
                ORDER BY s.registration_date DESC
                LIMIT $2
                """,
                sponsor_name, limit,
            )
            return [dict(row) for row in rows]

    @staticmethod
    async def search_studies(
        query: str,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search studies by NCT ID, title, or sponsor."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM studies
                WHERE nct_id ILIKE $1
                   OR title ILIKE $1
                   OR sponsor ILIKE $1
                ORDER BY registration_date DESC
                LIMIT $2
                """,
                f"%{query}%", limit,
            )
            return [dict(row) for row in rows]

    @staticmethod
    async def get_analytics() -> Dict[str, Any]:
        """Fetch system-wide analytics."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Total studies
            total_studies = await conn.fetchval("SELECT COUNT(*) FROM studies")

            # Total signals
            total_signals = await conn.fetchval("SELECT COUNT(*) FROM signals")

            # Signals by status
            status_breakdown = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM signals
                GROUP BY status
            """)
            status_breakdown = {row["status"]: row["count"] for row in status_breakdown}

            # Signals by agent
            agent_breakdown = await conn.fetch("""
                SELECT agent_name, COUNT(*) as count
                FROM signals
                GROUP BY agent_name
                ORDER BY count DESC
            """)
            agent_breakdown = {row["agent_name"]: row["count"] for row in agent_breakdown}

            # Approval rate
            total_reviewed = await conn.fetchval(
                "SELECT COUNT(*) FROM signals WHERE status IN ('approved', 'rejected')"
            )
            total_approved = await conn.fetchval(
                "SELECT COUNT(*) FROM signals WHERE status = 'approved'"
            )
            approval_rate = (total_approved / total_reviewed * 100) if total_reviewed > 0 else 0

            return {
                "total_studies": total_studies,
                "total_signals": total_signals,
                "status_breakdown": status_breakdown,
                "agent_breakdown": agent_breakdown,
                "approval_rate": approval_rate,
                "total_reviewed": total_reviewed,
            }
