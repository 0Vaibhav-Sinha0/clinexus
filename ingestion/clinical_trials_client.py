##############################################################################
# ingestion/clinical_trials_client.py
#
# Async client for the ClinicalTrials.gov v2 API. Handles search with
# pagination, single-study lookups, and retry-on-transient-failure.
# Consumed by run_ingestion.py; not intended to be run directly.
#
# NOTE: requests is used instead of httpx because ClinicalTrials.gov's
# bot protection rejects httpx's TLS fingerprint with a 403. requests,
# paired with a browser-like User-Agent, is accepted. requests calls are
# wrapped in asyncio.to_thread() to keep the client async-compatible.
##############################################################################


import asyncio
import requests

from typing import Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

BASE_URL = settings.clinical_trials_base_url
PAGE_SIZE = settings.clinical_trials_page_size

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

HEADERS = {
    "Accept": "application/json",

    # Required to bypass ClinicalTrials.gov's bot protection, which blocks
    # the default requests/httpx User-Agent strings. Verified through testing.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


class ClinicalTrialsClient:
    """
    Async context-manager client for ClinicalTrials.gov.

        async with ClinicalTrialsClient() as client:
            studies = await client.search_studies(condition="cancer")
    """

    def __init__(self):
        self._session: requests.Session | None = None

    async def __aenter__(self) -> "ClinicalTrialsClient":
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        logger.info("ClinicalTrials client opened")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self._session.close()
            logger.info("ClinicalTrials client closed")

    # ── CORE METHOD: SEARCH STUDIES ───────────────────────────

    async def search_studies(
        self,
        condition: str | None = None,
        intervention: str | None = None,
        sponsor: str | None = None,
        status: list[str] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Searches ClinicalTrials.gov and returns matching study records,
        transparently paginating until max_results is reached or the
        API runs out of pages.

        Args:
            condition:   Medical condition to search for.
            intervention: Drug or treatment to search for.
            sponsor:     Organisation running the study.
            status:      List of study statuses to filter by.
            max_results: Maximum total studies to return.

        Returns:
            List of raw study dictionaries exactly as the API returned them.
        """

        all_studies: list[dict[str, Any]] = []
        next_page_token: str | None = None
        page_number = 0

        logger.info(
            f"Searching studies | "
            f"condition={condition} | "
            f"intervention={intervention} | "
            f"sponsor={sponsor} | "
            f"max_results={max_results}"
        )

        while len(all_studies) < max_results:
            page_number += 1

            params = self._build_search_params(
                condition=condition,
                intervention=intervention,
                sponsor=sponsor,
                status=status,
                page_token=next_page_token,
            )

            response_data = await self._fetch_page(params=params)

            if not response_data:
                break

            page_studies = response_data.get("studies", [])

            if not page_studies:
                logger.info("No more studies available — pagination complete")
                break

            all_studies.extend(page_studies)

            logger.info(
                f"Page {page_number} | "
                f"fetched={len(page_studies)} | "
                f"total so far={len(all_studies)}"
            )

            next_page_token = response_data.get("nextPageToken")

            if not next_page_token:
                logger.info("Last page reached — no nextPageToken in response")
                break

        all_studies = all_studies[:max_results]

        logger.info(
            f"Search complete | "
            f"total studies returned={len(all_studies)}"
        )

        return all_studies

    # ── CORE METHOD: FETCH ONE STUDY BY ID ───────────────────

    async def fetch_study(self, nct_id: str) -> dict[str, Any] | None:
        """
        Fetches the full record for a single study by its NCT ID
        (e.g. "NCT04788680").

        Returns:
            The study dictionary, or None if not found or the request failed.
        """

        logger.info(f"Fetching single study | nct_id={nct_id}")

        def _get_study():
            return self._session.get(
                f"{BASE_URL}/studies/{nct_id}",
                timeout=REQUEST_TIMEOUT,
            )

        try:
            response = await asyncio.to_thread(_get_study)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.warning(
                f"Study not found | "
                f"nct_id={nct_id} | "
                f"status={e.response.status_code}"
            )
            return None

        except Exception as e:
            logger.error(
                f"Failed to fetch study | "
                f"nct_id={nct_id} | "
                f"error={e}"
            )
            return None

    # ── PRIVATE METHOD: BUILD SEARCH PARAMETERS ───────────────

    def _build_search_params(
        self,
        condition: str | None,
        intervention: str | None,
        sponsor: str | None,
        status: list[str] | None,
        page_token: str | None,
    ) -> dict[str, Any]:
        """
        Translates client-facing search arguments into ClinicalTrials.gov v2
        query parameters. Only includes parameters that were provided.
        """

        params: dict[str, Any] = {
            "pageSize": PAGE_SIZE,
            "format": "json",
        }

        if condition:
            params["query.cond"] = condition

        if intervention:
            params["query.intr"] = intervention

        if sponsor:
            params["query.spons"] = sponsor

        if status:
            # v2 requires pipe-separated values; comma triggers a 403.
            params["filter.overallStatus"] = "|".join(status)

        if page_token:
            params["pageToken"] = page_token

        return params

    # ── PRIVATE METHOD: FETCH ONE PAGE WITH RETRY ─────────────

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(
            (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
        ),
    )
    async def _fetch_page(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """
        Fetches one page from /studies. Retries on Timeout/ConnectionError
        via tenacity; HTTP errors (4xx/5xx) are not retried since they
        won't be resolved by retrying.
        """

        def _get():
            return self._session.get(
                f"{BASE_URL}/studies",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

        try:
            response = await asyncio.to_thread(_get)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            logger.warning(
                f"Request timed out after {REQUEST_TIMEOUT}s — retrying..."
            )
            raise

        except requests.exceptions.ConnectionError:
            logger.warning("Connection error — retrying...")
            raise

        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP error from API | "
                f"status={e.response.status_code} | "
                f"url={e.response.url}"
            )
            return None

        except Exception as e:
            logger.error(
                f"Unexpected error fetching page | "
                f"error={e}"
            )
            return None