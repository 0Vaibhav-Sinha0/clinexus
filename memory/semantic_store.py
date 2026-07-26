##############################################################################
# memory/semantic_store.py
#
# Manages the sponsor knowledge base — credibility profiles built up over
# time as Clinexus analyses more studies. Tracks compliance and behavior
# patterns for every research sponsor.
##############################################################################


import asyncpg
from datetime import datetime
from typing import Any

from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


class SemanticStore:
    """
    Manages sponsor knowledge base — credibility profiles built up over
    time as Clinexus analyses more studies.

    Each sponsor gets ONE profile row that is updated (never replaced)
    every time new information about that sponsor is discovered.

    Usage:
        store = SemanticStore()

        profile = await store.get_sponsor_profile("Novo Nordisk")

        await store.update_sponsor_knowledge(
            sponsor="Novo Nordisk",
            results_posted=True,
            had_broken_promise=False,
            delay_days=5
        )
    """

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        logger.info("SemanticStore initialised")

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
        )

        logger.info("SemanticStore pool created")

    # ──────────────────────────────────────────────────────────
    # CORE METHOD: get_sponsor_profile
    # ──────────────────────────────────────────────────────────

    async def get_sponsor_profile(
        self,
        sponsor: str,
    ) -> dict[str, Any] | None:
        """
        Retrieves everything we know about a specific sponsor.

        Returns the sponsor's full profile including credibility score,
        compliance history, and timing metrics.

        Args:
            sponsor: The sponsor name to look up.

        Returns:
            Dictionary with all profile fields, or None if not found.
        """

        await self._ensure_pool()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    sponsor,
                    credibility_score,
                    total_studies,
                    results_posted,
                    results_missing,
                    broken_promises,
                    avg_delay_days,
                    last_updated
                FROM sponsor_profiles
                WHERE sponsor = $1
                """,
                sponsor,
            )

        if not row:
            return None

        return {
            "sponsor":           row["sponsor"],
            "credibility_score": float(row["credibility_score"] or 0.0),
            "total_studies":     int(row["total_studies"] or 0),
            "results_posted":    int(row["results_posted"] or 0),
            "results_missing":   int(row["results_missing"] or 0),
            "broken_promises":   int(row["broken_promises"] or 0),
            "avg_delay_days":    float(row["avg_delay_days"] or 0.0),
            "last_updated":      str(row["last_updated"]),
        }

    # ──────────────────────────────────────────────────────────
    # CORE METHOD: update_sponsor_knowledge
    # ──────────────────────────────────────────────────────────

    async def update_sponsor_knowledge(
        self,
        sponsor: str,
        results_posted: bool | None = None,
        had_broken_promise: bool | None = None,
        delay_days: int | None = None,
    ) -> bool:
        """
        Updates a sponsor's profile after analysing a study.

        Creates a new profile if the sponsor doesn't exist yet.
        Recalculates the credibility score based on compliance history.

        Args:
            sponsor:             The sponsor to update.
            results_posted:      True if results were posted on time.
            had_broken_promise:  True if outcome switching detected.
            delay_days:          Days late on timeline if applicable.

        Returns:
            True if successful, False otherwise.
        """

        await self._ensure_pool()

        try:
            async with self._pool.acquire() as conn:
                existing = await conn.fetchrow(
                    "SELECT credibility_score FROM sponsor_profiles WHERE sponsor = $1",
                    sponsor,
                )

                if not existing:
                    await conn.execute(
                        """
                        INSERT INTO sponsor_profiles
                        (sponsor, credibility_score, total_studies, results_posted,
                         results_missing, broken_promises, avg_delay_days, last_updated)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        sponsor,
                        0.5,
                        0,
                        0,
                        0,
                        0,
                        0.0,
                        datetime.utcnow(),
                    )

                updates = {}
                if results_posted is not None:
                    if results_posted:
                        updates["results_posted"] = "results_posted + 1"
                    else:
                        updates["results_missing"] = "results_missing + 1"

                if had_broken_promise:
                    updates["broken_promises"] = "broken_promises + 1"

                if delay_days is not None and delay_days > 0:
                    updates["avg_delay_days"] = (
                        "(avg_delay_days * total_studies + $delay) / (total_studies + 1)"
                    )

                updates["total_studies"] = "total_studies + 1"
                updates["last_updated"] = "NOW()"

                set_clause = ", ".join(
                    f"{k} = {v}" if not k.startswith("$") else f"{k} = {v}"
                    for k, v in updates.items()
                )

                sql = f"""
                    UPDATE sponsor_profiles
                    SET {set_clause}
                    WHERE sponsor = $1
                """

                params = [sponsor]
                if delay_days is not None:
                    params.append(delay_days)

                await conn.execute(sql, *params)

            logger.info(
                f"Sponsor knowledge updated | "
                f"sponsor={sponsor} | "
                f"results_posted={results_posted} | "
                f"broken_promise={had_broken_promise}"
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to update sponsor knowledge | "
                f"sponsor={sponsor} | error={e}"
            )
            return False

    # ──────────────────────────────────────────────────────────
    # UTILITY METHOD: get_low_credibility_sponsors
    # ──────────────────────────────────────────────────────────

    async def get_low_credibility_sponsors(
        self,
        threshold: float = 0.6,
        min_studies: int = 3,
    ) -> list[dict]:
        """
        Returns all sponsors whose credibility is below the threshold.

        Args:
            threshold:   Credibility below this score qualifies as "low".
            min_studies: Minimum studies needed before flagging a sponsor.

        Returns:
            List of sponsor profile dicts ordered by credibility ascending.
        """

        await self._ensure_pool()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    sponsor,
                    credibility_score,
                    total_studies,
                    results_posted,
                    results_missing,
                    broken_promises,
                    avg_delay_days,
                    last_updated
                FROM sponsor_profiles
                WHERE credibility_score < $1
                  AND total_studies >= $2
                ORDER BY credibility_score ASC
                """,
                threshold,
                min_studies,
            )

        sponsors = [
            {
                "sponsor":           row["sponsor"],
                "credibility_score": float(row["credibility_score"] or 0.0),
                "total_studies":     int(row["total_studies"] or 0),
                "results_posted":    int(row["results_posted"] or 0),
                "results_missing":   int(row["results_missing"] or 0),
                "broken_promises":   int(row["broken_promises"] or 0),
                "avg_delay_days":    float(row["avg_delay_days"] or 0.0),
                "last_updated":      str(row["last_updated"]),
            }
            for row in rows
        ]

        logger.info(
            f"Low credibility sponsors found | "
            f"count={len(sponsors)} | "
            f"threshold={threshold} | "
            f"min_studies={min_studies}"
        )

        return sponsors

    # ──────────────────────────────────────────────────────────
    # UTILITY METHOD: get_all_sponsor_profiles
    # ──────────────────────────────────────────────────────────

    async def get_all_sponsor_profiles(
        self,
        limit: int = 50,
    ) -> list[dict]:
        """
        Returns all sponsor profiles ordered by credibility.

        Args:
            limit: Maximum profiles to return.

        Returns:
            List of all sponsor profiles, lowest credibility first.
        """

        await self._ensure_pool()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    sponsor,
                    credibility_score,
                    total_studies,
                    results_posted,
                    results_missing,
                    broken_promises,
                    avg_delay_days,
                    last_updated
                FROM sponsor_profiles
                ORDER BY credibility_score ASC
                LIMIT $1
                """,
                limit,
            )

        return [
            {
                "sponsor":           row["sponsor"],
                "credibility_score": float(row["credibility_score"] or 0.0),
                "total_studies":     int(row["total_studies"] or 0),
                "results_posted":    int(row["results_posted"] or 0),
                "results_missing":   int(row["results_missing"] or 0),
                "broken_promises":   int(row["broken_promises"] or 0),
                "avg_delay_days":    float(row["avg_delay_days"] or 0.0),
                "last_updated":      str(row["last_updated"]),
            }
            for row in rows
        ]

    # ──────────────────────────────────────────────────────────
    # UTILITY METHOD: sponsor_exists
    # ──────────────────────────────────────────────────────────

    async def sponsor_exists(self, sponsor: str) -> bool:
        """
        Checks if a sponsor profile already exists in the database.

        Args:
            sponsor: The sponsor name to check.

        Returns:
            True if a profile exists, False if this is a new sponsor.
        """

        await self._ensure_pool()

        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM sponsor_profiles WHERE sponsor = $1",
                sponsor,
            )

        return (count or 0) > 0

    # ──────────────────────────────────────────────────────────
    # CLEANUP METHOD: close
    # ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Closes the connection pool gracefully."""

        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("SemanticStore pool closed")