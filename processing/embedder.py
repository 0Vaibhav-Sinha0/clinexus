##############################################################################
# processing/embedder.py
#
# Converts TextChunks into vector embeddings using OpenAI's
# text-embedding-3-small model. Batches requests for efficiency
# and retries on transient failures.
##############################################################################


import asyncio
from dataclasses import dataclass

from openai import AsyncOpenAI

from processing.chunker import TextChunk

from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

BATCH_SIZE = 50
RETRY_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 2


# ─────────────────────────────────────────────────────────────
# THE EmbeddedChunk DATACLASS
# ─────────────────────────────────────────────────────────────

@dataclass
class EmbeddedChunk:
    """
    A TextChunk enriched with its vector embedding (1536 dimensions).
    This is what gets saved to the Cloud SQL chunks table.
    """

    chunk_id:    str
    nct_id:      str
    chunk_text:  str
    chunk_index: int
    source:      str
    word_count:  int
    embedding:   list[float]


# ─────────────────────────────────────────────────────────────
# THE EMBEDDER CLASS
# ─────────────────────────────────────────────────────────────

class Embedder:
    """
    Converts TextChunks into EmbeddedChunks using OpenAI's
    text-embedding-3-small model.

    Processes chunks in batches for efficiency and automatically
    retries failed API calls.

    Usage:
        embedder = Embedder()
        embedded = await embedder.embed_chunks(list_of_text_chunks)
    """

    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model

        logger.info(
            f"Embedder initialised | model={self._model}"
        )

    # ── CORE METHOD: EMBED A LIST OF CHUNKS ───────────────────

    async def embed_chunks(
        self,
        chunks: list[TextChunk],
    ) -> list[EmbeddedChunk]:
        """
        Converts a list of TextChunks into EmbeddedChunks.

        Splits input into batches and processes each with one OpenAI
        API call. Much more efficient than one call per chunk.

        Args:
            chunks: List of TextChunk objects from chunker.py

        Returns:
            List of EmbeddedChunk objects. Any chunk that fails to
            embed is skipped (not fatal to the pipeline).
        """

        batches = self._create_batches(chunks)

        logger.info(
            f"Starting embedding | "
            f"total_chunks={len(chunks)} | "
            f"batch_size={BATCH_SIZE} | "
            f"num_batches={len(batches)}"
        )

        all_embedded: list[EmbeddedChunk] = []

        for batch_num, batch in enumerate(batches):
            logger.info(
                f"Embedding batch {batch_num + 1}/{len(batches)} | "
                f"chunks_in_batch={len(batch)}"
            )

            embedded_batch = await self._embed_batch_with_retry(
                batch=batch,
                batch_num=batch_num,
            )

            all_embedded.extend(embedded_batch)

            if batch_num < len(batches) - 1:
                await asyncio.sleep(0.5)

        logger.info(
            f"Embedding complete | "
            f"total_embedded={len(all_embedded)} | "
            f"total_input={len(chunks)} | "
            f"skipped={len(chunks) - len(all_embedded)}"
        )

        return all_embedded

    # ── PRIVATE METHOD: CREATE BATCHES ────────────────────────

    def _create_batches(
        self,
        chunks: list[TextChunk],
    ) -> list[list[TextChunk]]:
        """
        Splits a flat list of chunks into smaller batches.

        Args:
            chunks: The full list of chunks to split.

        Returns:
            A list of lists, each inner list is one batch.
        """

        return [
            chunks[i : i + BATCH_SIZE]
            for i in range(0, len(chunks), BATCH_SIZE)
        ]

    # ── PRIVATE METHOD: EMBED ONE BATCH WITH RETRY ────────────

    async def _embed_batch_with_retry(
        self,
        batch: list[TextChunk],
        batch_num: int,
    ) -> list[EmbeddedChunk]:
        """
        Embeds one batch of chunks, retrying on failure.

        Args:
            batch:     One batch of TextChunks to embed.
            batch_num: The batch number (for logging).

        Returns:
            List of EmbeddedChunks for this batch, or empty list if
            all retries failed.
        """

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                return await self._embed_batch(batch=batch)

            except Exception as e:
                if attempt < RETRY_ATTEMPTS:
                    logger.warning(
                        f"Embedding failed | "
                        f"batch={batch_num + 1} | "
                        f"attempt={attempt}/{RETRY_ATTEMPTS} | "
                        f"error={e} | "
                        f"retrying in {RETRY_SLEEP_SECONDS}s..."
                    )
                    await asyncio.sleep(RETRY_SLEEP_SECONDS)

                else:
                    logger.error(
                        f"Embedding failed after {RETRY_ATTEMPTS} attempts | "
                        f"batch={batch_num + 1} | "
                        f"error={e} | "
                        f"skipping this batch"
                    )
                    return []

        return []

    # ── PRIVATE METHOD: EMBED ONE BATCH ───────────────────────

    async def _embed_batch(
        self,
        batch: list[TextChunk],
    ) -> list[EmbeddedChunk]:
        """
        Makes one OpenAI API call to embed an entire batch of chunks.

        Args:
            batch: One batch of TextChunks (up to BATCH_SIZE).

        Returns:
            List of EmbeddedChunks with embeddings attached.

        Raises:
            Exception: If the OpenAI API call fails.
        """

        texts = [chunk.chunk_text for chunk in batch]

        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )

        embedded_chunks: list[EmbeddedChunk] = []

        for i, chunk in enumerate(batch):
            embedding_vector = response.data[i].embedding

            embedded_chunk = EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                nct_id=chunk.nct_id,
                chunk_text=chunk.chunk_text,
                chunk_index=chunk.chunk_index,
                source=chunk.source,
                word_count=chunk.word_count,
                embedding=embedding_vector,
            )

            embedded_chunks.append(embedded_chunk)

        logger.info(
            f"Batch embedded successfully | "
            f"chunks={len(embedded_chunks)} | "
            f"embedding_dims={len(embedded_chunks[0].embedding) if embedded_chunks else 0}"
        )

        return embedded_chunks