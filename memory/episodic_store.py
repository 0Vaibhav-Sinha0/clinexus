##############################################################################
# memory/episodic_store.py
#
# Stores and retrieves agent reasoning sessions as episodes. Each episode
# is embedded and stored so future sessions can search through past findings
# by meaning.
##############################################################################


import json
import uuid
import asyncio
from datetime import datetime

from sentence_transformers import SentenceTransformer
import asyncpg

from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


# Global model instance (lazy-loaded)
_model_instance: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazy-loads the SentenceTransformer model."""
    global _model_instance
    if _model_instance is None:
        logger.info(f"Loading embedding model for EpisodicStore: {settings.embedding_model}")
        _model_instance = SentenceTransformer(settings.embedding_model)
    return _model_instance


class EpisodicStore:
    """
    Stores and retrieves agent reasoning sessions as episodes.

    Each episode is one agent's reasoning session — what it investigated,
    what it found, and what it concluded. Episodes are embedded and stored
    so future sessions can search through past findings by meaning.

    Uses SentenceTransformers for FREE local embeddings (no OpenAI API costs).

    Usage:
        store = EpisodicStore()

        await store.save_episode(
            agent_name="missing_results_agent",
            nct_id="NCT04788680",
            content="Novo Nordisk trial completed 2019. Results never posted.",
            outcome="signal_generated"
        )

        past = await store.search_episodes(
            query="sponsor never posted results",
            agent_name="missing_results_agent",
            top_k=3
        )
    """

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._model = _get_model()
        self._embedding_dim = settings.embedding_dimension

        logger.info(
            f"EpisodicStore initialised | "
            f"model={settings.embedding_model} | "
            f"dimension={self._embedding_dim}"
        )

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

        logger.info("EpisodicStore pool created")

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Registers the pgvector codec for VECTOR type conversion."""

        await conn.set_type_codec(
            "vector",
            encoder=lambda v: json.dumps(v),
            decoder=json.loads,
            schema="public",
        )

    # ──────────────────────────────────────────────────────────
    # CORE METHOD: save_episode
    # ──────────────────────────────────────────────────────────

    async def save_episode(
        self,
        agent_name: str,
        content: str,
        outcome: str,
        nct_id: str | None = None,
    ) -> str:
        """
        Saves one agent reasoning session as an episode.

        Embeds the content into 1536-number vector and stores it
        along with metadata for future semantic search.

        Args:
            agent_name: Which agent ran this session.
            content:    What the agent found/reasoned.
            outcome:    "signal_generated", "no_signal", etc.
            nct_id:     Optional — which study this relates to.

        Returns:
            episode_id — the unique ID of the saved episode.
        """

        await self._ensure_pool()

        embedding = await self._embed_text(content)

        episode_id = str(uuid.uuid4())

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO episodes
                (episode_id, agent_name, nct_id, content, outcome, embedding, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                episode_id,
                agent_name,
                nct_id,
                content,
                outcome,
                embedding,
                datetime.utcnow(),
            )

        logger.info(
            f"Episode saved | "
            f"episode_id={episode_id} | "
            f"agent={agent_name} | "
            f"outcome={outcome}"
        )

        return episode_id

    # ──────────────────────────────────────────────────────────
    # CORE METHOD: search_episodes
    # ──────────────────────────────────────────────────────────

    async def search_episodes(
        self,
        query: str,
        agent_name: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Finds past episodes by semantic similarity to a query.

        Uses pgvector's cosine distance to compare query embedding
        against all stored episode embeddings.

        Args:
            query:      Natural language search query.
            agent_name: Optional — search only this agent's episodes.
            top_k:      Number of results to return.

        Returns:
            List of episode dicts with similarity scores.
        """

        await self._ensure_pool()

        query_embedding = await self._embed_text(query)

        conditions = []
        params: list = [query_embedding]
        param_count = 1

        if agent_name:
            param_count += 1
            conditions.append(f"agent_name = ${param_count}")
            params.append(agent_name)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        param_count += 1
        params.append(top_k)

        sql = f"""
            SELECT
                episode_id,
                agent_name,
                nct_id,
                content,
                outcome,
                embedding <=> $1 AS similarity,
                created_at
            FROM episodes
            {where_clause}
            ORDER BY similarity ASC
            LIMIT ${param_count}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        episodes = [
            {
                "episode_id": row["episode_id"],
                "agent_name": row["agent_name"],
                "nct_id":     row["nct_id"],
                "content":    row["content"],
                "outcome":    row["outcome"],
                "similarity": round(float(row["similarity"]), 3),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

        logger.info(
            f"Episode search complete | "
            f"query='{query[:50]}...' | "
            f"agent_filter={agent_name} | "
            f"results_found={len(episodes)}"
        )

        return episodes

    # ──────────────────────────────────────────────────────────
    # UTILITY METHOD: get_recent_episodes
    # ──────────────────────────────────────────────────────────

    async def get_recent_episodes(
        self,
        agent_name: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Returns the most recent episodes, newest first.

        Args:
            agent_name: Optional — filter to one agent's episodes.
            limit:      Maximum number of episodes to return.

        Returns:
            List of episode dicts ordered newest first.
        """

        await self._ensure_pool()

        if agent_name:
            sql = """
                SELECT episode_id, agent_name, nct_id,
                       content, outcome, created_at
                FROM episodes
                WHERE agent_name = $1
                ORDER BY created_at DESC
                LIMIT $2
            """
            params = [agent_name, limit]
        else:
            sql = """
                SELECT episode_id, agent_name, nct_id,
                       content, outcome, created_at
                FROM episodes
                ORDER BY created_at DESC
                LIMIT $1
            """
            params = [limit]

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [
            {
                "episode_id": row["episode_id"],
                "agent_name": row["agent_name"],
                "nct_id":     row["nct_id"],
                "content":    row["content"],
                "outcome":    row["outcome"],
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    # ──────────────────────────────────────────────────────────
    # UTILITY METHOD: count_episodes
    # ──────────────────────────────────────────────────────────

    async def count_episodes(
        self,
        agent_name: str | None = None,
    ) -> int:
        """
        Returns the total number of episodes stored.

        Args:
            agent_name: Optional — count only this agent's episodes.

        Returns:
            Integer count.
        """

        await self._ensure_pool()

        async with self._pool.acquire() as conn:
            if agent_name:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM episodes WHERE agent_name = $1",
                    agent_name,
                )
            else:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM episodes"
                )

        return count or 0

    # ──────────────────────────────────────────────────────────
    # PRIVATE HELPER: _embed_text
    # ──────────────────────────────────────────────────────────

    async def _embed_text(self, text: str) -> list[float]:
        """
        Converts text to a vector embedding using SentenceTransformers (local, free).

        Args:
            text: The text to embed.

        Returns:
            List of floats (dimension = settings.embedding_dimension, default 768).
        """

        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: self._model.encode(text, convert_to_tensor=False),
        )

        return embedding.tolist()  # Convert numpy array to list

    # ──────────────────────────────────────────────────────────
    # CLEANUP METHOD: close
    # ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Closes the connection pool gracefully."""

        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("EpisodicStore pool closed")