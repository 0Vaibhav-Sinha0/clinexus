##############################################################################
# memory/procedural_store.py
#
# Manages agent reasoning rules — default rules plus learned rules from
# human feedback. Implements the learning loop where human corrections
# permanently change agent behaviour.
##############################################################################


import asyncpg
import json
from datetime import datetime

from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# DEFAULT RULES
# ─────────────────────────────────────────────────────────────

DEFAULT_RULES = {
    "missing_results_agent": [
        "Flag a study as missing results ONLY if status is COMPLETED "
        "and results_posted is False and more than 12 months have "
        "passed since the completion date.",

        "Do NOT flag studies with status TERMINATED as missing results. "
        "Terminated trials are not legally required to post results "
        "in all circumstances.",

        "If enrollment was zero or very low (under 10 participants), "
        "note this in the signal but reduce confidence to 0.5.",

        "Always check the sponsor's track record before assigning "
        "a confidence score.",
    ],

    "broken_promises_agent": [
        "Flag outcome switching ONLY when the PRIMARY outcome changes "
        "after enrollment has begun.",

        "A change in outcome MEASUREMENT METHOD is different from a "
        "change in the outcome itself. Flag method changes at MEDIUM "
        "confidence, not HIGH.",

        "If a protocol amendment was filed BEFORE enrollment began, "
        "the outcome change is less suspicious.",

        "Always note the date of the change relative to the "
        "enrollment start date.",
    ],

    "track_record_agent": [
        "A credibility score below 0.6 should trigger a LOW_CREDIBILITY signal.",

        "Weight recent behaviour more heavily than old behaviour.",

        "If a sponsor has fewer than 3 studies in our database, "
        "reduce confidence to 0.5.",

        "Always check whether this is a first-time violation or "
        "a repeat pattern.",
    ],
}


class ProceduralStore:
    """
    Manages agent reasoning rules — defaults plus learned rules from
    human feedback.

    Each agent starts with DEFAULT_RULES. When a human rejects a signal
    and explains why, that explanation becomes a new rule stored in the
    database. On the next run, the agent loads BOTH defaults and learned
    rules, reasoning differently based on human feedback.

    Usage:
        store = ProceduralStore()

        rules = await store.get_procedures("missing_results_agent")

        procedure_id = await store.learn_from_feedback(
            agent_name="missing_results_agent",
            rejection_reason="This trial was terminated early due to COVID"
        )
    """

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        logger.info("ProceduralStore initialised")

    # ──────────────────────────────────────────────────────────
    # PRIVATE HELPER: _ensure_pool
    # ──────────────────────────────────────────────────────────

    async def _ensure_pool(self) -> None:
        """Creates the connection pool if it does not exist yet."""

        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=int(settings.db_port),
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=1,
            max_size=5,
            init=self._init_connection,
        )

        logger.info("ProceduralStore pool created")

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Placeholder for future codec registration if needed."""
        pass

    # ──────────────────────────────────────────────────────────
    # CORE METHOD: get_procedures
    # ──────────────────────────────────────────────────────────

    async def get_procedures(self, agent_name: str) -> list[str]:
        """
        Returns all reasoning rules for an agent — defaults plus learned rules.

        The agent loads these at the start of every session and applies
        them during reasoning. Each string is a rule in plain English
        that the agent reads directly.

        Args:
            agent_name: Which agent's rules to return.

        Returns:
            List of rule text strings, in order.
        """

        await self._ensure_pool()

        rules = list(DEFAULT_RULES.get(agent_name, []))

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT rule_text
                FROM procedures
                WHERE agent_name = $1
                ORDER BY created_at ASC
                """,
                agent_name,
            )

        for row in rows:
            rules.append(row["rule_text"])

        logger.info(
            f"Procedures loaded | "
            f"agent={agent_name} | "
            f"defaults={len(DEFAULT_RULES.get(agent_name, []))} | "
            f"learned={len(rows)}"
        )

        return rules

    # ──────────────────────────────────────────────────────────
    # CORE METHOD: learn_from_feedback
    # ──────────────────────────────────────────────────────────

    async def learn_from_feedback(
        self,
        agent_name: str,
        rejection_reason: str,
    ) -> str:
        """
        Adds a new learned rule from a human rejection.

        When a human reviewer rejects an agent's signal, they explain
        why. That explanation is saved as a new rule. From this point
        forward, every time this agent runs, it will load and apply
        this new rule.

        Args:
            agent_name:       Which agent to add the rule to.
            rejection_reason: The human's explanation of what was wrong.

        Returns:
            procedure_id — the unique ID of the new rule.
        """

        await self._ensure_pool()

        async with self._pool.acquire() as conn:
            procedure_id = await conn.fetchval(
                """
                INSERT INTO procedures (
                    agent_name,
                    rule_text,
                    rule_type,
                    source
                )
                VALUES ($1, $2, $3, $4)
                RETURNING procedure_id
                """,
                agent_name,
                rejection_reason,
                "learned",
                "hitl_rejection",
            )

        logger.info(
            f"Procedure learned from feedback | "
            f"agent={agent_name} | "
            f"rule_preview='{rejection_reason[:80]}...' | "
            f"procedure_id={procedure_id}"
        )

        return str(procedure_id)

    # ──────────────────────────────────────────────────────────
    # UTILITY METHOD: get_all_procedures_for_api
    # ──────────────────────────────────────────────────────────

    async def get_all_procedures_for_api(
        self,
        agent_name: str,
    ) -> list[dict]:
        """
        Returns all procedures for an agent WITH full metadata.

        Used by the API to display what rules the agent follows,
        which are built-in vs learned, and when each was added.

        Args:
            agent_name: Which agent's procedures to return.

        Returns:
            List of procedure dictionaries with full metadata.
        """

        await self._ensure_pool()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    procedure_id,
                    agent_name,
                    rule_text,
                    rule_type,
                    source,
                    created_at
                FROM procedures
                WHERE agent_name = $1
                ORDER BY created_at ASC
                """,
                agent_name,
            )

        return [
            {
                "procedure_id": str(row["procedure_id"]),
                "agent_name":   row["agent_name"],
                "rule_text":    row["rule_text"],
                "rule_type":    row["rule_type"],
                "source":       row["source"],
                "created_at":   str(row["created_at"]),
            }
            for row in rows
        ]

    # ──────────────────────────────────────────────────────────
    # CLEANUP METHOD: close
    # ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Closes the connection pool gracefully."""

        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("ProceduralStore pool closed")