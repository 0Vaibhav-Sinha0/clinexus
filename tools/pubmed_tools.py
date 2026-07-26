##############################################################################
# tools/pubmed_tools.py
#
# Defines tools that let agents fetch LIVE research papers directly
# from PubMed during analysis runs for current publications, including
# papers published after ingestion.
##############################################################################


import json
import asyncio

from langchain_core.tools import tool

from ingestion.pubmed_client import PubMedClient
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
# TOOL 1: fetch_papers_for_trial
# ─────────────────────────────────────────────────────────────

@tool
def fetch_papers_for_trial(
    nct_id: str,
    max_papers: int = 10,
) -> str:
    """
    Fetch all published research papers that reference a specific
    clinical trial — LIVE from PubMed right now.

    Use this to find independent research about a trial and compare
    published findings against official filings.

    Args:
        nct_id:     The trial's NCT ID to search for in PubMed.
        max_papers: Maximum papers to fetch. Default 10.

    Returns:
        JSON string with papers including title, abstract, journal,
        authors, and publication date.
    """

    logger.info(
        f"Tool called: fetch_papers_for_trial | "
        f"nct_id={nct_id} | max_papers={max_papers}"
    )

    async def _fetch():
        async with PubMedClient() as client:
            papers = await client.fetch_papers_for_trial(
                nct_id=nct_id,
                max_results=max_papers,
            )
            return papers

    try:
        raw_papers = _run_async(_fetch())

        if not raw_papers:
            return json.dumps({
                "nct_id":  nct_id,
                "papers":  [],
                "count":   0,
                "message": f"No published papers found on PubMed that "
                           f"reference trial {nct_id}.",
            }, indent=2)

        parsed_papers = _parser.parse_papers(raw_papers=raw_papers)

        papers_list = []
        for paper in parsed_papers:
            paper_dict = paper.model_dump()

            papers_list.append({
                "pmid":               paper_dict["pmid"],
                "title":              paper_dict["title"],
                "abstract":           paper_dict["abstract"],
                "journal":            paper_dict["journal"],
                "pub_date":           paper_dict["pub_date"],
                "authors":            paper_dict["authors"][:5],
                "word_count":         paper_dict["word_count"],
                "nct_ids_referenced": paper_dict["nct_ids_referenced"],
            })

        return json.dumps({
            "nct_id":  nct_id,
            "papers":  papers_list,
            "count":   len(papers_list),
        }, indent=2, default=str)

    except Exception as e:
        logger.error(
            f"fetch_papers_for_trial failed | nct_id={nct_id} | error={e}"
        )
        return json.dumps({"nct_id": nct_id, "error": str(e), "papers": []})


# ─────────────────────────────────────────────────────────────
# TOOL 2: search_pubmed_by_query
# ─────────────────────────────────────────────────────────────

@tool
def search_pubmed_by_query(
    query: str,
    max_papers: int = 10,
) -> str:
    """
    Search PubMed for research papers matching a query.

    Use this to find papers by topic, drug name, or condition.
    Useful for discovering patterns across multiple trials or
    finding specific safety information.

    Args:
        query:      Natural language search query.
        max_papers: Maximum papers to return. Default 10.

    Returns:
        JSON string with matching papers and their details.
    """

    logger.info(
        f"Tool called: search_pubmed_by_query | "
        f"query='{query[:60]}' | max_papers={max_papers}"
    )

    async def _search():
        async with PubMedClient() as client:
            papers = await client.fetch_papers_for_trials(
                nct_ids=[],
                max_per_trial=max_papers,
            )
            return papers

    try:
        raw_papers = _run_async(_search())

        if not raw_papers:
            return json.dumps({
                "query":   query,
                "papers":  [],
                "count":   0,
                "message": f"No papers found on PubMed for query: '{query}'.",
            }, indent=2)

        parsed_papers = _parser.parse_papers(raw_papers=raw_papers)

        papers_list = []
        for paper in parsed_papers:
            paper_dict = paper.model_dump()

            papers_list.append({
                "pmid":               paper_dict["pmid"],
                "title":              paper_dict["title"],
                "abstract":           paper_dict["abstract"],
                "journal":            paper_dict["journal"],
                "pub_date":           paper_dict["pub_date"],
                "authors":            paper_dict["authors"][:5],
                "word_count":         paper_dict["word_count"],
                "nct_ids_referenced": paper_dict["nct_ids_referenced"],
            })

        return json.dumps({
            "query":  query,
            "papers": papers_list,
            "count":  len(papers_list),
        }, indent=2, default=str)

    except Exception as e:
        logger.error(f"search_pubmed_by_query failed | query={query} | error={e}")
        return json.dumps({"query": query, "error": str(e), "papers": []})


# ─────────────────────────────────────────────────────────────
# TOOL 3: compare_filing_vs_papers
# ─────────────────────────────────────────────────────────────

@tool
def compare_filing_vs_papers(
    nct_id: str,
    filing_summary: str,
) -> str:
    """
    Fetch papers for a trial and present alongside official filing
    for comparison.

    Use this to identify discrepancies between official filings
    and published research — the core of the Side Effect Checker agent.

    Args:
        nct_id:         The trial's NCT ID.
        filing_summary: A summary of what the official filing says.

    Returns:
        JSON with both filing summary and papers for direct comparison.
    """

    logger.info(
        f"Tool called: compare_filing_vs_papers | nct_id={nct_id}"
    )

    async def _fetch():
        async with PubMedClient() as client:
            papers = await client.fetch_papers_for_trial(
                nct_id=nct_id,
                max_results=15,
            )
            return papers

    try:
        raw_papers = _run_async(_fetch())
        parsed_papers = _parser.parse_papers(raw_papers=raw_papers or [])

        papers_list = []
        for paper in parsed_papers:
            paper_dict = paper.model_dump()
            papers_list.append({
                "pmid":     paper_dict["pmid"],
                "title":    paper_dict["title"],
                "abstract": paper_dict["abstract"],
                "journal":  paper_dict["journal"],
                "pub_date": paper_dict["pub_date"],
                "authors":  paper_dict["authors"][:3],
            })

        comparison_note = (
            "Compare the filing_summary above against each paper's abstract. "
            "Look for: (1) adverse events in papers absent from filing, "
            "(2) different severity descriptions, (3) contradictory outcomes, "
            "(4) results data when filing shows results_posted=False."
        )

        return json.dumps({
            "nct_id":          nct_id,
            "filing_summary":  filing_summary,
            "papers":          papers_list,
            "papers_count":    len(papers_list),
            "comparison_note": comparison_note,
            "has_papers": len(papers_list) > 0,
        }, indent=2, default=str)

    except Exception as e:
        logger.error(
            f"compare_filing_vs_papers failed | nct_id={nct_id} | error={e}"
        )
        return json.dumps({
            "nct_id": nct_id,
            "error":  str(e),
            "papers": [],
        })


# ─────────────────────────────────────────────────────────────
# TOOL REGISTRY
# ─────────────────────────────────────────────────────────────

ALL_PUBMED_TOOLS = [
    fetch_papers_for_trial,
    search_pubmed_by_query,
    compare_filing_vs_papers,
]