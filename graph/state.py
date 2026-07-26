##############################################################################
# graph/state.py
#
# Defines the MosaicState TypedDict and reducer functions for LangGraph.
##############################################################################

from typing import Any, TypedDict, Annotated
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


def _merge_lists(a: list, b: list) -> list:
    """Reducer that appends lists instead of replacing them."""
    return (a or []) + (b or [])


class SignalOutput(TypedDict):
    agent:       str
    signal_type: str
    nct_id:      str
    summary:     str
    evidence:    list
    confidence:  float


class MosaicState(TypedDict):

    task:        str
    nct_ids:     list[str]
    max_studies: int

    messages: Annotated[list[BaseMessage], add_messages]

    signals:          Annotated[list[SignalOutput], _merge_lists]
    agents_activated: Annotated[list[str], _merge_lists]
    error_log:        Annotated[list, _merge_lists]

    final_brief:  str
    run_complete: bool

    run_id: str