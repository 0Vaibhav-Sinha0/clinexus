##############################################################################
# ingestion/gcs_store.py
#
# Handles reading/writing data to Google Cloud Storage.
# Implements raw/processed dual-save pattern for data safety.
# Consumed by run_ingestion.py; not intended to be run directly.
#
# NOTE: Uses asyncio.to_thread() to wrap Google's synchronous storage
# library, keeping the async pipeline non-blocking.
##############################################################################


import json
import asyncio

from typing import Any

from google.cloud import storage

from config.settings import settings
from config.logging_config import setup_logging
from ingestion.document_parser import ParsedStudy, ParsedPaper

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# FOLDER PATHS INSIDE BUCKET
# ─────────────────────────────────────────────────────────────

PREFIX_RAW_STUDIES       = "raw/studies"
PREFIX_RAW_PAPERS        = "raw/papers"
PREFIX_PROCESSED_STUDIES = "processed/studies"
PREFIX_PROCESSED_PAPERS  = "processed/papers"


class GCSStore:
    """
    Handles saving to and loading from Google Cloud Storage.
    Implements the raw/processed dual-save pattern.
    """

    def __init__(self):
        self._client = storage.Client(project=settings.gcp_project_id)
        self._bucket = self._client.bucket(settings.gcs_bucket_name)

        logger.info(
            f"GCSStore initialised | "
            f"bucket={settings.gcs_bucket_name} | "
            f"project={settings.gcp_project_id}"
        )

    # ── SAVE A RAW STUDY ───────────────────────────────────────

    async def save_raw_study(
        self,
        nct_id: str,
        data: dict[str, Any],
    ) -> str:
        """
        Saves the exact, untouched API response for one study.
        Call immediately after API fetch, before any parsing.

        Args:
            nct_id: Study ID, used as the filename.
            data:   Raw study dictionary.

        Returns:
            The GCS path where the file was saved.
        """

        gcs_path = f"{PREFIX_RAW_STUDIES}/{nct_id}.json"
        await self._upload_json(path=gcs_path, data=data)
        logger.info(f"Saved raw study | nct_id={nct_id} | path={gcs_path}")
        return gcs_path

    # ── SAVE A RAW PAPER ───────────────────────────────────────

    async def save_raw_paper(
        self,
        pmid: str,
        data: dict[str, Any],
    ) -> str:
        """
        Saves the exact, untouched data for one PubMed paper.

        Args:
            pmid: PubMed ID, used as the filename.
            data: Raw paper dictionary.

        Returns:
            The GCS path where the file was saved.
        """

        gcs_path = f"{PREFIX_RAW_PAPERS}/{pmid}.json"
        await self._upload_json(path=gcs_path, data=data)
        logger.info(f"Saved raw paper | pmid={pmid} | path={gcs_path}")
        return gcs_path

    # ── SAVE A CLEANED (PARSED) STUDY ────────────────────────

    async def save_parsed_study(self, study: ParsedStudy) -> str:
        """
        Saves the cleaned version of a study.

        Args:
            study: A ParsedStudy object.

        Returns:
            The GCS path where the file was saved.
        """

        gcs_path = f"{PREFIX_PROCESSED_STUDIES}/{study.nct_id}.json"

        await self._upload_json(
            path=gcs_path,
            data=study.model_dump(),
        )

        logger.info(
            f"Saved parsed study | nct_id={study.nct_id} | path={gcs_path}"
        )
        return gcs_path

    # ── SAVE A CLEANED (PARSED) PAPER ─────────────────────────

    async def save_parsed_paper(self, paper: ParsedPaper) -> str:
        """
        Saves the cleaned version of a paper.

        Args:
            paper: A ParsedPaper object.

        Returns:
            The GCS path where the file was saved.
        """

        gcs_path = f"{PREFIX_PROCESSED_PAPERS}/{paper.pmid}.json"

        await self._upload_json(
            path=gcs_path,
            data=paper.model_dump(),
        )

        logger.info(
            f"Saved parsed paper | pmid={paper.pmid} | path={gcs_path}"
        )
        return gcs_path

    # ── LOAD A CLEANED STUDY BACK FROM GCS ────────────────────

    async def load_parsed_study(self, nct_id: str) -> ParsedStudy | None:
        """
        Loads a previously saved, cleaned study back from GCS.

        Args:
            nct_id: Which study to load, by its NCT ID.

        Returns:
            A ParsedStudy object if found, None otherwise.
        """

        gcs_path = f"{PREFIX_PROCESSED_STUDIES}/{nct_id}.json"
        data = await self._download_json(path=gcs_path)

        if not data:
            return None

        return ParsedStudy(**data)

    # ── LIST ALL STUDIES WE HAVE ALREADY PROCESSED ────────────

    async def list_processed_studies(self) -> list[str]:
        """
        Returns a list of every study's NCT ID currently saved
        in the processed folder.

        Returns:
            A list of NCT ID strings.
        """

        blobs = await asyncio.to_thread(
            self._bucket.list_blobs,
            prefix=PREFIX_PROCESSED_STUDIES,
        )

        nct_ids = []
        for blob in blobs:
            filename = blob.name.split("/")[-1]
            nct_id = filename.replace(".json", "")

            if nct_id:
                nct_ids.append(nct_id)

        logger.info(f"Listed processed studies | count={len(nct_ids)}")
        return nct_ids

    # ── PRIVATE HELPER: UPLOAD ANY DICT AS A JSON FILE ────────

    async def _upload_json(
        self,
        path: str,
        data: dict[str, Any],
    ) -> None:
        """
        Shared internal method for uploading dictionaries as JSON.
        All save_* methods eventually call this.

        Args:
            path: Destination path inside the GCS bucket.
            data: Dictionary to save as JSON.
        """

        json_bytes = json.dumps(data, indent=2, default=str).encode("utf-8")

        blob = self._bucket.blob(path)

        await asyncio.to_thread(
            blob.upload_from_string,
            json_bytes,
            content_type="application/json",
        )

    # ── PRIVATE HELPER: DOWNLOAD A JSON FILE BACK AS A DICT ───

    async def _download_json(
        self,
        path: str,
    ) -> dict[str, Any] | None:
        """
        Shared internal method for downloading and parsing JSON from GCS.

        Args:
            path: Path inside the GCS bucket to download from.

        Returns:
            A Python dictionary if the file was found, None otherwise.
        """

        try:
            blob = self._bucket.blob(path)
            json_bytes = await asyncio.to_thread(blob.download_as_bytes)
            return json.loads(json_bytes.decode("utf-8"))

        except Exception as e:
            if "404" in str(e) or "Not Found" in str(e):
                logger.warning(f"File not found in GCS | path={path}")
            else:
                logger.error(
                    f"Failed to download from GCS | path={path} | error={e}"
                )
            return None