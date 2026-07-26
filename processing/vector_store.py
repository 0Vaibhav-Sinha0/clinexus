##############################################################################
# processing/vector_store.py
#
# Saves EmbeddedChunks to Cloud SQL and enables semantic search via pgvector's
# cosine similarity operator. Registers custom codec to handle VECTOR type
# conversion between Python lists and PostgreSQL.
##############################################################################


import asyncio
import asyncpg
import json

from typing import Any

from processing.embedder import EmbeddedChunk

from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

POOL_MIN_SIZE = 2
POOL_MAX_SIZE = 10
TOP_K_DEFAULT = 5


# ─────────────────────────────────────────────────────────────
# THE VECTOR STORE CLASS
# ─────────────────────────────────────────────────────────────

class VectorStore:
    """
    Saves EmbeddedChunks to Cloud SQL and enables semantic search
    over them using pgvector's cosine similarity operator.

    LIFECYCLE — use as async context manager:
        async with VectorStore() as vs:
            await vs.save_embedded_chunks(chunks)
            results = await vs.search(query_embedding)
    """

    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    # ── ASYNC CONTEXT MANAGER SUPPORT ─────────────────────────

    async def __aenter__(self) -> "VectorStore":
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ── INITIALISE THE CONNECTION POOL ────────────────────────

    async def init(self) -> None:
        """
        Creates the asyncpg connection pool and registers the pgvector
        codec so Python can read and write VECTOR columns.

        MUST be called before any other method.
        """

        logger.info(
            f"Connecting to Cloud SQL | "
            f"host={settings.db_host} | "
            f"database={settings.db_name}"
        )

        self._pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=int(settings.db_port),
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            init=self._init_connection,
        )

        logger.info("Connection pool created successfully")

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """
        Runs on every new database connection. Registers the pgvector
        codec — the translator between Python lists and PostgreSQL VECTORs.

        WITHOUT THIS: TypeError or UndefinedTypeError on VECTOR operations
        WITH THIS: Automatic transparent conversion
        """

        await conn.set_type_codec(
            "vector",
            encoder=lambda v: json.dumps(v),
            decoder=json.loads,
            schema="public",
        )

    async def close(self) -> None:
        """Closes the connection pool and releases all connections."""
        if self._pool:
            await self._pool.close()
            logger.info("Connection pool closed")

    # ── SAVE EMBEDDED CHUNKS TO CLOUD SQL ──────────────────────

    async def save_embedded_chunks(
        self,
        chunks: list[EmbeddedChunk],
    ) -> int:
        """
        Saves a list of EmbeddedChunks to the Cloud SQL chunks table.

        Uses ON CONFLICT DO NOTHING so re-runs do not duplicate data.

        Args:
            chunks: List of EmbeddedChunk objects to save.

        Returns:
            Number of chunks successfully saved.
        """

        if not chunks:
            logger.warning("No chunks to save")
            return 0

        logger.info(f"Saving {len(chunks)} chunks to Cloud SQL...")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for chunk in chunks:
                    await conn.execute(
                        """
                        INSERT INTO chunks
                        (chunk_id, nct_id, chunk_text, chunk_index, source, word_count, embedding)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (chunk_id) DO NOTHING
                        """,
                        chunk.chunk_id,
                        chunk.nct_id,
                        chunk.chunk_text,
                        chunk.chunk_index,
                        chunk.source,
                        chunk.word_count,
                        chunk.embedding,
                    )

        logger.info(f"Chunks saved | saved={len(chunks)}")
        return len(chunks)

    # ── SAVE STUDY METADATA TO CLOUD SQL ───────────────────────

    async def save_study(
        self,
        study_data: dict[str, Any],
    ) -> bool:
        """
        Saves study metadata to the Cloud SQL studies table.

        Args:
            study_data: Dictionary with study fields (nct_id, title, etc).

        Returns:
            True if successful, False otherwise.
        """

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO studies
                    (nct_id, title, sponsor, phase, status, conditions, interventions,
                     primary_outcome, secondary_outcomes, start_date, completion_date,
                     results_posted, enrollment, gcs_path)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (nct_id) DO UPDATE SET
                        title              = EXCLUDED.title,
                        sponsor            = EXCLUDED.sponsor,
                        phase              = EXCLUDED.phase,
                        status             = EXCLUDED.status,
                        conditions         = EXCLUDED.conditions,
                        interventions      = EXCLUDED.interventions,
                        primary_outcome    = EXCLUDED.primary_outcome,
                        secondary_outcomes = EXCLUDED.secondary_outcomes,
                        start_date         = EXCLUDED.start_date,
                        completion_date    = EXCLUDED.completion_date,
                        results_posted     = EXCLUDED.results_posted,
                        enrollment         = EXCLUDED.enrollment,
                        gcs_path           = EXCLUDED.gcs_path
                    """,
                    study_data.get("nct_id"),
                    study_data.get("title"),
                    study_data.get("sponsor"),
                    study_data.get("phase"),
                    study_data.get("status"),
                    study_data.get("conditions", []),
                    study_data.get("interventions", []),
                    study_data.get("primary_outcome"),
                    study_data.get("secondary_outcomes", []),
                    study_data.get("start_date"),
                    study_data.get("completion_date"),
                    study_data.get("results_posted"),
                    study_data.get("enrollment"),
                    study_data.get("gcs_path"),
                )
            return True

        except Exception as e:
            logger.error(
                f"Failed to save study | nct_id={study_data.get('nct_id')} | error={e}"
            )
            return False

    # ── SEMANTIC SEARCH ───────────────────────────────────────

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = TOP_K_DEFAULT,
        source_filter: str | None = None,
        nct_id_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Finds the most semantically similar chunks to a query embedding.

        Uses pgvector's cosine distance operator (<=>).

        Args:
            query_embedding:  The search query as 1536 numbers.
            top_k:            How many results to return.
            source_filter:    Optional filter by source type ("study", "paper").
            nct_id_filter:    Optional filter by specific study.

        Returns:
            List of dictionaries with nct_id, chunk_text, chunk_index,
            source, and distance (0=identical, 2=opposite).
        """

        conditions = []
        params: list[Any] = [query_embedding]
        param_count = 1

        if source_filter:
            param_count += 1
            conditions.append(f"source = ${param_count}")
            params.append(source_filter)

        if nct_id_filter:
            param_count += 1
            conditions.append(f"nct_id = ${param_count}")
            params.append(nct_id_filter)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        param_count += 1
        params.append(top_k)

        query = f"""
            SELECT
                nct_id,
                chunk_text,
                chunk_index,
                source,
                embedding <=> $1 AS distance
            FROM chunks
            {where_clause}
            ORDER BY distance ASC
            LIMIT ${param_count}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        results = [dict(row) for row in rows]

        logger.info(
            f"Semantic search complete | "
            f"results_found={len(results)} | "
            f"top_k={top_k} | "
            f"source_filter={source_filter} | "
            f"nct_id_filter={nct_id_filter}"
        )

        return results

    # ── CHECK HOW MANY CHUNKS ARE STORED ──────────────────────

    async def get_chunk_count(self) -> int:
        """
        Returns the total number of chunks currently in the database.

        Returns:
            Total count of rows in the chunks table.
        """

        async with self._pool.acquire() as conn:
            result = await conn.fetchval("SELECT COUNT(*) FROM chunks")

        logger.info(f"Total chunks in database: {result}")
        return result

    # ── CHECK IF A STUDY HAS ALREADY BEEN PROCESSED ───────────

    async def study_exists(self, nct_id: str) -> bool:
        """
        Checks if a study already has chunks saved in the database.

        Args:
            nct_id: The study to check.

        Returns:
            True if chunks exist, False otherwise.
        """

        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM chunks WHERE nct_id = $1",
                nct_id,
            )

        return count > 0