##############################################################################
# api/dependencies.py
#
# Creates and manages shared resources for API endpoints.
##############################################################################

from functools import lru_cache

from graph.hitl import HITLGate
from memory.episodic_store import EpisodicStore
from memory.procedural_store import ProceduralStore
from memory.semantic_store import SemanticStore
from graph.graph_builder import mosaic_graph


@lru_cache(maxsize=1)
def get_hitl_gate() -> HITLGate:
    """
    Returns the shared HITLGate instance.

    One instance = one connection pool = efficient resource use.
    """
    return HITLGate()


@lru_cache(maxsize=1)
def get_episodic_store() -> EpisodicStore:
    """Returns the shared EpisodicStore instance."""
    return EpisodicStore()


@lru_cache(maxsize=1)
def get_procedural_store() -> ProceduralStore:
    """Returns the shared ProceduralStore instance."""
    return ProceduralStore()


@lru_cache(maxsize=1)
def get_semantic_store() -> SemanticStore:
    """Returns the shared SemanticStore instance."""
    return SemanticStore()


def get_graph():
    """
    Returns the compiled Clinexus LangGraph graph.

    Not cached because mosaic_graph is already a module-level singleton.
    """
    return mosaic_graph