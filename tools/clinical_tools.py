##############################################################################
# tools/clinical_tools.py
#
# Defines tools that let agents fetch LIVE data directly from the
# ClinicalTrials.gov API during analysis runs for current state,
# detailed fields, or studies not in the ingestion corpus.
##############################################################################


import json
import asyncio

from langchain_core.tools import tool

from ingestion.clinical_trials_client import ClinicalTrialsClient
from ingestion.document_parser import DocumentParser

from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# SHARED INSTANCES
# ─────────────────────────────────────────────────────────────

_parser = DocumentParser()


def _run_async(coroutine):
    """Runs an async coroutine synchronously inside a LangGraph tool."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coroutine)


# ─────────────────────────────────────────────────────────────
# TOOL 1: fetch_study_details
# ─────────────────────────────────────────────────────────────

@tool
def fetch_study_details(nct_id: str) -> str:
    """
    Fetch the complete, LIVE record for one specific clinical trial
    directly from ClinicalTrials.gov API.

    Use this when you need the most current version of a study,
    fields not in the local database, or studies not in the corpus.
    Makes a LIVE API call — slightly slower than database queries.

    Args:
        nct_id: The study's unique identifier (e.g., "NCT04788680").

    Returns:
        JSON string with the complete cleaned study record.
    """

    logger.info(f"Tool called: fetch_study_details | nct_id={nct_id}")

    async def _fetch():
        async with ClinicalTrialsClient() as client:
            raw_study = await client.fetch_study(nct_id=nct_id)
            return raw_study

    try:
        raw_study = _run_async(_fetch())

        if raw_study is None:
            return json.dumps({
                "found":   False,
                "nct_id":  nct_id,
                "message": f"Study {nct_id} was not found on ClinicalTrials.gov.",
            }, indent=2)

        parsed_study = _parser.parse_study(raw=raw_study)

        if parsed_study is None:
            return json.dumps({
                "nct_id":  nct_id,
                "found":   False,
                "message": "Could not parse study data.",
            }, indent=2)

        return json.dumps({
            "found":           True,
            "nct_id":          parsed_study.nct_id,
            "title":           parsed_study.title,
            "sponsor":         parsed_study.sponsor,
            "phase":           parsed_study.phase,
            "status":          parsed_study.status,
            "conditions":      parsed_study.conditions,
            "interventions":   parsed_study.interventions,
            "primary_outcome": parsed_study.primary_outcome,
            "secondary_outcomes": parsed_study.secondary_outcomes,
            "start_date":      parsed_study.start_date,
            "completion_date": parsed_study.completion_date,
            "results_posted":  parsed_study.results_posted,
            "enrollment":      parsed_study.enrollment,
        }, indent=2, default=str)

    except Exception as e:
        logger.error(f"fetch_study_details failed | nct_id={nct_id} | error={e}")
        return json.dumps({"error": str(e), "found": False})


# ─────────────────────────────────────────────────────────────
# TOOL 2: search_studies_by_condition
# ─────────────────────────────────────────────────────────────

@tool
def search_studies_by_condition(
    condition: str,
    max_results: int = 20,
) -> str:
    """
    Search ClinicalTrials.gov for studies matching a medical condition.

    Returns current results directly from the API — finds studies
    that may not be in the local database.

    Args:
        condition:   The medical condition to search for.
        max_results: Maximum studies to return. Default 20.

    Returns:
        JSON string with matching studies and their key fields.
    """

    logger.info(
        f"Tool called: search_studies_by_condition | condition={condition}"
    )

    async def _search():
        async with ClinicalTrialsClient() as client:
            studies = await client.search_studies(
                condition=condition,
                max_results=max_results,
            )
            return studies

    try:
        raw_studies = _run_async(_search())

        if not raw_studies:
            return json.dumps({
                "condition": condition,
                "studies":   [],
                "count":     0,
                "message":   f"No studies found for condition: {condition}",
            }, indent=2)

        parsed_studies = _parser.parse_studies(raw_studies)

        studies_list = []
        for study in parsed_studies:
            studies_list.append({
                "nct_id":      study.nct_id,
                "title":       study.title,
                "sponsor":     study.sponsor,
                "status":      study.status,
                "phase":       study.phase,
                "enrollment":  study.enrollment,
            })

        return json.dumps({
            "condition": condition,
            "studies":   studies_list,
            "count":     len(studies_list),
        }, indent=2)

    except Exception as e:
        logger.error(
            f"search_studies_by_condition failed | condition={condition} | error={e}"
        )
        return json.dumps({"error": str(e), "studies": []})


# ─────────────────────────────────────────────────────────────
# TOOL 3: check_results_posted
# ─────────────────────────────────────────────────────────────

@tool
def check_results_posted(nct_id: str) -> str:
    """
    Check if a study has posted results and calculate time overdue.

    Used by the Missing Results Agent to get current results status
    and determine how long a COMPLETED study has been missing results.

    Args:
        nct_id: The study's NCT ID.

    Returns:
        JSON with results status and time overdue if applicable.
    """

    logger.info(f"Tool called: check_results_posted | nct_id={nct_id}")

    async def _fetch():
        async with ClinicalTrialsClient() as client:
            raw_study = await client.fetch_study(nct_id=nct_id)
            return raw_study

    try:
        raw_study = _run_async(_fetch())

        if raw_study is None:
            return json.dumps({"found": False, "nct_id": nct_id})

        parsed = _parser.parse_study(raw=raw_study)

        if parsed is None:
            return json.dumps({"found": False, "nct_id": nct_id})

        result = {
            "found":              True,
            "nct_id":             parsed.nct_id,
            "title":              parsed.title,
            "status":             parsed.status,
            "results_posted":     parsed.results_posted,
            "completion_date":    parsed.completion_date,
            "sponsor":            parsed.sponsor,
        }

        if not parsed.results_posted and parsed.status == "COMPLETED":
            if parsed.completion_date:
                try:
                    from datetime import datetime

                    completion = datetime.strptime(
                        parsed.completion_date[:7],
                        "%Y-%m"
                    )

                    now = datetime.utcnow()

                    months_since_completion = (
                        (now.year - completion.year) * 12
                        + (now.month - completion.month)
                    )

                    months_overdue = months_since_completion - 12

                    if months_overdue > 0:
                        result["months_overdue"] = months_overdue
                        result["years_overdue"]  = round(
                            months_overdue / 12, 1
                        )
                        result["is_violation"] = True

                except ValueError:
                    pass

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.error(
            f"check_results_posted failed | nct_id={nct_id} | error={e}"
        )
        return json.dumps({"nct_id": nct_id, "error": str(e), "found": False})


# ─────────────────────────────────────────────────────────────
# TOOL 4: get_study_amendments
# ─────────────────────────────────────────────────────────────

@tool
def get_study_amendments(nct_id: str) -> str:
    """
    Fetch the protocol amendment history for a clinical trial.

    Used by the Broken Promises Agent to investigate whether a study
    changed its primary outcomes or design mid-study.

    Args:
        nct_id: The study's NCT ID.

    Returns:
        JSON with amendment history and timing details.
    """

    logger.info(f"Tool called: get_study_amendments | nct_id={nct_id}")

    async def _fetch():
        async with ClinicalTrialsClient() as client:
            raw_study = await client.fetch_study(nct_id=nct_id)
            return raw_study

    try:
        raw_study = _run_async(_fetch())

        if raw_study is None:
            return json.dumps({
                "nct_id":     nct_id,
                "found":      False,
                "amendments": [],
            }, indent=2)

        parsed = _parser.parse_study(raw=raw_study)

        if parsed is None:
            return json.dumps({
                "nct_id":     nct_id,
                "found":      False,
                "amendments": [],
                "message":    "Could not parse study.",
            }, indent=2)

        return json.dumps({
            "nct_id":          parsed.nct_id,
            "found":           True,
            "title":           parsed.title,
            "sponsor":         parsed.sponsor,
            "start_date":      parsed.start_date,
            "completion_date": parsed.completion_date,
            "primary_outcome": parsed.primary_outcome,
            "amendments":      parsed.protocol_amendments,
            "amendment_count": len(parsed.protocol_amendments),
        }, indent=2, default=str)

    except Exception as e:
        logger.error(
            f"get_study_amendments failed | nct_id={nct_id} | error={e}"
        )
        return json.dumps({"nct_id": nct_id, "error": str(e), "found": False})


# ─────────────────────────────────────────────────────────────
# TOOL REGISTRY
# ─────────────────────────────────────────────────────────────

ALL_CLINICAL_TOOLS = [
    fetch_study_details,
    search_studies_by_condition,
    check_results_posted,
    get_study_amendments,
]