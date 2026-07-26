##############################################################################
# tools/search_tools.py
#
# Defines tools that agents use to interact with the database, memory layer,
# and vector search system. Tools are called autonomously by agents based on
# what they need to find out.
##############################################################################


import asyncio
import json

from langchain_core.tools import tool

from processing.vector_store import VectorStore
from memory.episodic_store import EpisodicStore
from memory.semantic_store import SemanticStore

from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# SHARED STORE INSTANCES
# ─────────────────────────────────────────────────────────────

_vector_store   = VectorStore()
_episodic_store = EpisodicStore()
_semantic_store = SemanticStore()


def _run_async(coroutine):
    """Runs an async coroutine synchronously for LangGraph tool calls."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coroutine)


# ─────────────────────────────────────────────────────────────
# TOOL 1: search_studies_by_meaning
# ─────────────────────────────────────────────────────────────

@tool
def search_studies_by_meaning(
    query: str,
    top_k: int = 5,
    source_filter: str = "study",
) -> str:
    """
    Search clinical trial studies using semantic similarity.

    Use this to find studies related to a specific topic, condition,
    sponsor behaviour, or research integrity issue by MEANING rather
    than exact keywords.

    Args:
        query:         What to search for (natural language).
        top_k:         How many results to return. Default 5.
        source_filter: "study" or "paper". Default "study".

    Returns:
        JSON string with matching study chunks and similarity scores.
    """

    logger.info(
        f"Tool called: search_studies_by_meaning | "
        f"query='{query[:60]}' | top_k={top_k}"
    )

    try:
        results = _run_async(
            _vector_store.search(
                query_embedding=query,
                top_k=top_k,
                source_filter=source_filter,
            )
        )

        if not results:
            return json.dumps({
                "results": [],
                "message": "No relevant studies found for this query.",
                "query":   query,
            })

        return json.dumps({
            "results": results,
            "count":   len(results),
            "query":   query,
        }, indent=2, default=str)

    except Exception as e:
        logger.error(f"search_studies_by_meaning failed | error={e}")
        return json.dumps({"error": str(e), "results": []})


# ─────────────────────────────────────────────────────────────
# TOOL 2: search_past_episodes
# ─────────────────────────────────────────────────────────────

@tool
def search_past_episodes(
    query: str,
    agent_name: str | None = None,
    top_k: int = 3,
) -> str:
    """
    Search past agent reasoning sessions by meaning.

    Use this to ask "have I investigated something similar before?"
    Agents call this at the start of every run to get context from
    previous sessions.

    Args:
        query:      What to search for in past episodes.
        agent_name: Optional — search only this agent's episodes.
        top_k:      How many results to return.

    Returns:
        JSON string with matching past episodes and similarity.
    """

    logger.info(
        f"Tool called: search_past_episodes | "
        f"query='{query[:60]}' | agent_name={agent_name}"
    )

    try:
        episodes = _run_async(
            _episodic_store.search_episodes(
                query=query,
                agent_name=agent_name,
                top_k=top_k,
            )
        )

        if not episodes:
            return json.dumps({
                "episodes": [],
                "message": "No past episodes found for this query.",
                "query":   query,
            })

        return json.dumps({
            "episodes": episodes,
            "count":    len(episodes),
        }, indent=2, default=str)

    except Exception as e:
        logger.error(f"search_past_episodes failed | error={e}")
        return json.dumps({"error": str(e), "episodes": []})


# ─────────────────────────────────────────────────────────────
# TOOL 3: save_episode
# ─────────────────────────────────────────────────────────────

@tool
def save_episode(
    agent_name: str,
    content: str,
    outcome: str,
    nct_id: str | None = None,
) -> str:
    """
    Save one agent reasoning session as an episode for future memory.

    Use this at the end of an analysis to record what was found and
    what conclusion was reached. Future sessions can search these
    episodes to learn from past investigations.

    Args:
        agent_name: Which agent ran this session.
        content:    What the agent found/reasoned about.
        outcome:    "signal_generated", "no_signal", etc.
        nct_id:     Optional — which study this relates to.

    Returns:
        JSON with the saved episode ID.
    """

    logger.info(
        f"Tool called: save_episode | agent={agent_name} | outcome={outcome}"
    )

    try:
        episode_id = _run_async(
            _episodic_store.save_episode(
                agent_name=agent_name,
                content=content,
                outcome=outcome,
                nct_id=nct_id,
            )
        )

        return json.dumps({
            "success":    True,
            "episode_id": episode_id,
            "agent_name": agent_name,
            "outcome":    outcome,
        }, indent=2)

    except Exception as e:
        logger.error(f"save_episode failed | agent={agent_name} | error={e}")
        return json.dumps({"error": str(e), "success": False})


# ─────────────────────────────────────────────────────────────
# TOOL 4: get_sponsor_profile
# ─────────────────────────────────────────────────────────────

@tool
def get_sponsor_profile(sponsor: str) -> str:
    """
    Retrieve the credibility profile for a research sponsor.

    Use this to get a sponsor's track record: compliance history,
    credibility score, broken promises count, and timing patterns.

    Args:
        sponsor: The sponsor's name (e.g., "Novo Nordisk").

    Returns:
        JSON with complete sponsor profile or null if not found.
    """

    logger.info(f"Tool called: get_sponsor_profile | sponsor={sponsor}")

    try:
        profile = _run_async(
            _semantic_store.get_sponsor_profile(sponsor=sponsor)
        )

        if not profile:
            return json.dumps({
                "sponsor": sponsor,
                "found":   False,
                "message": f"No profile found for {sponsor}. "
                           "This sponsor may be new to our database.",
            })

        return json.dumps({
            "sponsor": profile,
            "found":   True,
        }, indent=2, default=str)

    except Exception as e:
        logger.error(f"get_sponsor_profile failed | sponsor={sponsor} | error={e}")
        return json.dumps({"error": str(e), "found": False})


# ─────────────────────────────────────────────────────────────
# TOOL 5: update_sponsor_profile
# ─────────────────────────────────────────────────────────────

@tool
def update_sponsor_profile(
    sponsor: str,
    results_posted: bool | None = None,
    had_broken_promise: bool = False,
    delay_days: int | None = None,
) -> str:
    """
    Update a sponsor's profile after analysing a study.

    Use this to record findings about a sponsor's behavior. Updates
    are accumulated — the sponsor's credibility score recalculates
    after each update.

    Args:
        sponsor:            The sponsor to update.
        results_posted:     True if results were posted on time.
        had_broken_promise: True if outcome switching detected.
        delay_days:         Days late on timeline if applicable.

    Returns:
        JSON confirming the update was saved.
    """

    logger.info(
        f"Tool called: update_sponsor_profile | sponsor={sponsor}"
    )

    try:
        success = _run_async(
            _semantic_store.update_sponsor_knowledge(
                sponsor=sponsor,
                results_posted=results_posted,
                had_broken_promise=had_broken_promise,
                delay_days=delay_days,
            )
        )

        if success:
            return json.dumps({
                "success": True,
                "sponsor": sponsor,
                "message": "Sponsor profile updated successfully.",
            })
        else:
            return json.dumps({
                "success": False,
                "sponsor": sponsor,
                "error":   "Failed to update sponsor profile.",
            })

    except Exception as e:
        logger.error(
            f"update_sponsor_profile failed | sponsor={sponsor} | error={e}"
        )
        return json.dumps({"error": str(e), "success": False})


# ─────────────────────────────────────────────────────────────
# TOOL 6: get_low_credibility_sponsors
# ─────────────────────────────────────────────────────────────

@tool
def get_low_credibility_sponsors(
    threshold: float = 0.6,
    min_studies: int = 3,
) -> str:
    """
    Get all sponsors whose credibility is below the threshold.

    Use this to identify problematic sponsors or for pattern analysis.

    Args:
        threshold:   Credibility below this qualifies as "low".
        min_studies: Minimum studies needed before flagging.

    Returns:
        JSON with list of low-credibility sponsors.
    """

    logger.info(
        f"Tool called: get_low_credibility_sponsors | threshold={threshold}"
    )

    try:
        sponsors = _run_async(
            _semantic_store.get_low_credibility_sponsors(
                threshold=threshold,
                min_studies=min_studies,
            )
        )

        if not sponsors:
            return json.dumps({
                "sponsors": [],
                "message":  f"No sponsors found below credibility {threshold} "
                            f"with at least {min_studies} studies.",
                "count":    0,
            }, indent=2)

        return json.dumps({
            "sponsors": sponsors,
            "count":    len(sponsors),
            "threshold": threshold,
        }, indent=2, default=str)

    except Exception as e:
        logger.error(f"get_low_credibility_sponsors failed | error={e}")
        return json.dumps({"error": str(e), "sponsors": []})


# ─────────────────────────────────────────────────────────────
# TOOL 7: search_study_chunks_by_nct_id
# ─────────────────────────────────────────────────────────────

@tool
def search_study_chunks_by_nct_id(
    nct_id: str,
    query:  str = "",
) -> str:
    """
    Retrieve all text chunks for one specific study by its NCT ID.

    Use this when you know WHICH study to examine in detail and need
    to read its full content.

    Args:
        nct_id: The specific study's NCT ID.
        query:  Optional — if provided, returns only the most relevant
                chunk for this study.

    Returns:
        JSON with all chunks from this study.
    """

    logger.info(
        f"Tool called: search_study_chunks_by_nct_id | nct_id={nct_id}"
    )

    try:
        if query:
            results = _run_async(
                _vector_store.search(
                    query_embedding=query,
                    top_k=5,
                    nct_id_filter=nct_id,
                )
            )
        else:
            results = _run_async(
                _vector_store.get_chunks_for_study(nct_id=nct_id)
            )

        if not results:
            return json.dumps({
                "nct_id":  nct_id,
                "chunks":  [],
                "message": f"No chunks found for study {nct_id}.",
            })

        return json.dumps({
            "nct_id": nct_id,
            "chunks": results,
            "count":  len(results),
        }, indent=2, default=str)

    except Exception as e:
        logger.error(
            f"search_study_chunks_by_nct_id failed | nct_id={nct_id} | error={e}"
        )
        return json.dumps({"error": str(e), "chunks": []})


# ─────────────────────────────────────────────────────────────
# TOOL 8: search_papers_by_meaning
# ─────────────────────────────────────────────────────────────

@tool
def search_papers_by_meaning(
    query: str,
    top_k: int = 5,
) -> str:
    """
    Search PubMed research papers using semantic similarity.

    Use this to find published research papers related to a specific
    topic, drug, or safety concern.

    Args:
        query: What to search for in published papers.
        top_k: How many results to return.

    Returns:
        JSON string with matching paper chunks and similarity scores.
    """

    logger.info(
        f"Tool called: search_papers_by_meaning | query='{query[:60]}'"
    )

    try:
        results = _run_async(
            _vector_store.search(
                query_embedding=query,
                top_k=top_k,
                source_filter="paper",
            )
        )

        if not results:
            return json.dumps({
                "results": [],
                "message": "No relevant papers found for this query.",
                "query":   query,
            })

        return json.dumps({
            "results": results,
            "count":   len(results),
            "query":   query,
        }, indent=2, default=str)

    except Exception as e:
        logger.error(f"search_papers_by_meaning failed | error={e}")
        return json.dumps({"error": str(e), "results": []})


# ─────────────────────────────────────────────────────────────
# TOOL REGISTRY
# ─────────────────────────────────────────────────────────────

ALL_SEARCH_TOOLS = [
    search_studies_by_meaning,
    search_past_episodes,
    save_episode,
    get_sponsor_profile,
    update_sponsor_profile,
    get_low_credibility_sponsors,
    search_study_chunks_by_nct_id,
    search_papers_by_meaning,
]