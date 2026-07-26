##############################################################################
# processing/run_processing.py
#
# Main entry point for the processing pipeline. Reads cleaned studies from
# GCS, chunks them, embeds them via SentenceTransformers (local, free),
# and stores everything in Cloud SQL.
#
# Run from terminal:
#   python3 processing/run_processing.py
##############################################################################

import asyncio

from ingestion.document_parser import ParsedStudy
from ingestion.gcs_store import GCSStore
from processing.chunker import Chunker
from processing.embedder import Embedder
from processing.vector_store import VectorStore

from config.logging_config import setup_logging

logger = setup_logging(__name__)


async def run_processing():
    """
    Runs the complete processing pipeline from start to finish.

    Reads cleaned studies from GCS, chunks them, embeds them via
    SentenceTransformers (local, free), and stores everything in Cloud SQL for agent search.
    """

    gcs_store = GCSStore()
    chunker = Chunker()
    embedder = Embedder()

    logger.info("Loading parsed studies from GCS...")

    nct_ids = await gcs_store.list_processed_studies()
    logger.info(f"Found {len(nct_ids)} studies in GCS")

    studies : list[ParsedStudy] = []
    for nct_id in nct_ids:
        study = await gcs_store.load_parsed_study(nct_id)
        if study:
            studies.append(study)

    logger.info(f"Loaded {len(studies)} studies successfully")

    # ── OPEN THE DATABASE CONNECTION ───────────────────────────
    async with VectorStore() as vector_store:

        # ── STEP 2: SAVE STUDY METADATA TO CLOUD SQL ──────────
        logger.info("Saving study metadata to Cloud SQL...")

        studies_saved = 0
        for study in studies:
            success = await vector_store.save_study(
                study_data={
                    "nct_id":             study.nct_id,
                    "title":              study.title,
                    "sponsor":            study.sponsor,
                    "phase":              study.phase,
                    "status":             study.status,
                    "conditions":         study.conditions,
                    "interventions":      study.interventions,
                    "primary_outcome":    study.primary_outcome,
                    "secondary_outcomes": study.secondary_outcomes,
                    "start_date":         study.start_date,
                    "completion_date":    study.completion_date,
                    "results_posted":     study.results_posted,
                    "enrollment":         study.enrollment,
                    "gcs_path":           f"processed/studies/{study.nct_id}.json",
                }
            )
            if success:
                studies_saved += 1

        logger.info(
            f"Studies saved to Cloud SQL | "
            f"saved={studies_saved} | "
            f"total={len(studies)}"
        )

        # ── STEP 3: CHUNK ALL STUDIES ──────────────────────────
        logger.info("Chunking studies...")

        all_chunks = chunker.chunk_studies(studies)
        logger.info(f"Total chunks created: {len(all_chunks)}")

        # ── STEP 4: EMBED ALL CHUNKS ───────────────────────────
        logger.info("Embedding chunks via SentenceTransformers (local, free)...")

        embedded_chunks = await embedder.embed_chunks(all_chunks)
        logger.info(f"Total chunks embedded: {len(embedded_chunks)}")

        # ── STEP 5: SAVE CHUNKS TO CLOUD SQL ──────────────────
        logger.info("Saving embedded chunks to Cloud SQL...")

        chunks_stored = await vector_store.save_embedded_chunks(embedded_chunks)

        # ── FINAL SUMMARY ──────────────────────────────────────
        logger.info("=" * 60)
        logger.info("Processing complete")
        logger.info(f"Studies processed : {len(studies)}")
        logger.info(f"Chunks created    : {len(all_chunks)}")
        logger.info(f"Chunks embedded   : {len(embedded_chunks)}")
        logger.info(f"Chunks stored     : {chunks_stored}")
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_processing())