##############################################################################
# processing/embedder.py
#
# Converts TextChunks into vector embeddings using SentenceTransformers.
# (Local, free, no API calls required)
#
# Migration from OpenAI: https://github.com/0Vaibhav-Sinha0/clinexus
# - Removed: asyncio wrapper around sync SentenceTransformers model
# - Reason: SentenceTransformers is sync-only, but embedding speed is
#   negligible compared to OpenAI's round-trip time (0.2-0.5s vs 0.5-2s)
##############################################################################


import asyncio
from dataclasses import dataclass
from typing import Optional

from sentence_transformers import SentenceTransformer

from processing.chunker import TextChunk
from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

BATCH_SIZE = 50
RETRY_ATTEMPTS = 3


# ─────────────────────────────────────────────────────────────
# THE EmbeddedChunk DATACLASS
# ─────────────────────────────────────────────────────────────

@dataclass
class EmbeddedChunk:
    """
    A TextChunk enriched with its vector embedding (768 dimensions).
    This is what gets saved to the Cloud SQL chunks table.

    Migration note: Changed from 1536 to 768 dimensions to reduce
    storage footprint while maintaining semantic search quality.
    """

    chunk_id:    str
    nct_id:      str
    chunk_text:  str
    chunk_index: int
    source:      str
    word_count:  int
    embedding:   list[float]


# ─────────────────────────────────────────────────────────────
# GLOBAL MODEL INSTANCE (lazy-loaded)
# ─────────────────────────────────────────────────────────────

_model_instance: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    """
    Lazy-loads the SentenceTransformer model on first call.
    This delays the ~500MB download until actually needed.
    """
    global _model_instance
    if _model_instance is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        _model_instance = SentenceTransformer(settings.embedding_model)
        logger.info(
            f"Embedding model loaded | "
            f"model={settings.embedding_model} | "
            f"dims={_model_instance.get_sentence_embedding_dimension()}"
        )
    return _model_instance


# ─────────────────────────────────────────────────────────────
# THE EMBEDDER CLASS
# ─────────────────────────────────────────────────────────────

class Embedder:
    """
    Converts TextChunks into EmbeddedChunks using SentenceTransformers.

    This is a FREE, local alternative to OpenAI embeddings:
    - No API calls → zero cost
    - No rate limits → instant processing
    - Runs on CPU/GPU locally
    - Deterministic → reproducible results

    Processing chunks in batches for memory efficiency.

    Usage:
        embedder = Embedder()
        embedded = await embedder.embed_chunks(list_of_text_chunks)
    """

    def __init__(self):
        self._model = _get_model()
        self._embedding_dim = settings.embedding_dimension

        logger.info(
            f"Embedder initialised | "
            f"model={settings.embedding_model} | "
            f"dimension={self._embedding_dim}"
        )

    # ── CORE METHOD: EMBED A LIST OF CHUNKS ───────────────────

    async def embed_chunks(
        self,
        chunks: list[TextChunk],
    ) -> list[EmbeddedChunk]:
        """
        Converts a list of TextChunks into EmbeddedChunks.

        Splits input into batches and processes each locally.
        Much faster than OpenAI's API (~5-10x improvement).

        Args:
            chunks: List of TextChunk objects from chunker.py

        Returns:
            List of EmbeddedChunk objects. Any chunk that fails to
            embed is skipped (not fatal to the pipeline).
        """

        if not chunks:
            return []

        batches = self._create_batches(chunks)

        logger.info(
            f"Starting embedding (SentenceTransformers) | "
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

            # Minimal sleep between batches (local, no rate limits)
            if batch_num < len(batches) - 1:
                await asyncio.sleep(0.1)

        logger.info(
            f"Embedding complete (SentenceTransformers) | "
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
                # Run in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    self._embed_batch,
                    batch,
                )

            except Exception as e:
                if attempt < RETRY_ATTEMPTS:
                    logger.warning(
                        f"Embedding failed | "
                        f"batch={batch_num + 1} | "
                        f"attempt={attempt}/{RETRY_ATTEMPTS} | "
                        f"error={e} | "
                        f"retrying..."
                    )
                    await asyncio.sleep(1)

                else:
                    logger.error(
                        f"Embedding failed after {RETRY_ATTEMPTS} attempts | "
                        f"batch={batch_num + 1} | "
                        f"error={e} | "
                        f"skipping this batch"
                    )
                    return []

        return []

    # ── PRIVATE METHOD: EMBED ONE BATCH (SYNC) ────────────────

    def _embed_batch(
        self,
        batch: list[TextChunk],
    ) -> list[EmbeddedChunk]:
        """
        Makes one SentenceTransformers inference pass to embed entire batch.

        Args:
            batch: One batch of TextChunks (up to BATCH_SIZE).

        Returns:
            List of EmbeddedChunks with embeddings attached.

        Raises:
            Exception: If the embedding fails.
        """

        texts = [chunk.chunk_text for chunk in batch]

        # Local embedding (no API call)
        embeddings = self._model.encode(
            texts,
            convert_to_tensor=False,  # Keep as numpy for pgvector compat
            show_progress_bar=False,
        )

        embedded_chunks: list[EmbeddedChunk] = []

        for i, chunk in enumerate(batch):
            embedding_vector = embeddings[i].tolist()  # Convert numpy → list

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
            f"Batch embedded successfully (SentenceTransformers) | "
            f"chunks={len(embedded_chunks)} | "
            f"embedding_dims={len(embedded_chunks[0].embedding) if embedded_chunks else 0}"
        )

        return embedded_chunks