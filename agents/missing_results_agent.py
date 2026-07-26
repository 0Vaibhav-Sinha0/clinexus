##############################################################################
# agents/missing_results_agent.py
#
# Detects clinical trials that have failed to post required results.
##############################################################################

import json
import re
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from graph.state import MosaicState, SignalOutput
from memory.procedural_store import ProceduralStore
from memory.episodic_store import EpisodicStore
from tools.search_tools import (
    search_studies_by_meaning,
    search_past_episodes,
    save_episode,
    get_sponsor_profile,
    update_sponsor_profile,
)
from tools.clinical_tools import fetch_study_details, check_results_posted
from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)

AGENT_NAME  = "missing_results_agent"
SIGNAL_TYPE = "missing_results"

AGENT_TOOLS = [
    search_studies_by_meaning,
    search_past_episodes,
    save_episode,
    get_sponsor_profile,
    update_sponsor_profile,
    fetch_study_details,
    check_results_posted,
]

_procedural = ProceduralStore()
_episodic   = EpisodicStore()

_llm = ChatGroq(
    model=settings.groq_model,
    temperature=0.1,
    api_key=settings.groq_api_key,
).bind_tools(AGENT_TOOLS)


async def missing_results_node(state: MosaicState) -> dict:
    """Detects trials with unreported results past their deadline."""

    logger.info(f"{AGENT_NAME} | Starting analysis")

    try:
        procedures = await _procedural.get_procedures(AGENT_NAME)
        procedures_text = "\n".join(f"- {r}" for r in procedures)

        system_prompt = f"""You are the Missing Results Agent for Clinexus.

YOUR MISSION:
Identify clinical trials where results should have been posted but are missing.

By law, trial sponsors must post summary results within 12 months of trial
completion. This agent finds trials where that legal obligation has been missed.

YOUR REASONING RULES:
{procedures_text}

YOUR WORKFLOW:
1. Search past episodes for previous missing results investigations
2. Search for studies past their completion date
3. Fetch full study details to confirm completion date
4. Check results posted status with check_results_posted
5. For trials >12 months past completion with no results, generate signal
6. Update sponsor profile — track pattern of non-compliance

CONFIDENCE SCORING:
- 0.9+ : >24 months past completion, no results posted, sponsor repeats pattern
- 0.8  : 12-24 months past completion, no results posted
- 0.7  : 12 months past completion, no results, first-time offender
- Below 0.65: Borderline timing — send to human review

OUTPUT FORMAT:
{{
  "nct_id": "NCT_ID",
  "signal_type": "missing_results",
  "summary": "How many months overdue, sponsor pattern if applicable",
  "evidence": ["completion date was X", "required posting by Y", "still missing"],
  "confidence": 0.80
}}

If no missing results found, say "NO_SIGNALS_FOUND".
"""

        task    = state.get("task", "Find trials with missing results")
        nct_ids = state.get("nct_ids", [])

        human_message = f"""
ANALYSIS TASK: {task}
SPECIFIC STUDIES: {nct_ids if nct_ids else "Search broadly"}

Begin investigation now. Focus on trials past their 12-month posting deadline.
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_message),
        ]

        signals_found  = []
        max_iterations = 10

        for iteration in range(max_iterations):
            response = await _llm.ainvoke(messages)
            messages.append(AIMessage(content=response.content or ""))

            if not response.tool_calls:
                logger.info(f"{AGENT_NAME} | Analysis complete | iteration={iteration+1}")
                signals_found = _parse_signals(response.content, AGENT_NAME)
                break

            for tool_call in response.tool_calls:
                tool_result = await _execute_tool(tool_call, AGENT_TOOLS)
                messages.append(
                    HumanMessage(content=f"Tool result for {tool_call['name']}:\n{tool_result}")
                )

        await _episodic.save_episode(
            agent_name=AGENT_NAME,
            content=f"Task: {task}. Found {len(signals_found)} missing results signals.",
            outcome="signal_generated" if signals_found else "no_signal",
        )

        logger.info(f"{AGENT_NAME} | Complete | signals_found={len(signals_found)}")

        return {
            "signals":          state.get("signals", []) + signals_found,
            "agents_activated": state.get("agents_activated", []) + [AGENT_NAME],
        }

    except Exception as e:
        logger.error(f"{AGENT_NAME} | Error | {e}")
        return {
            "error_log":        state.get("error_log", []) + [f"{AGENT_NAME}: {str(e)}"],
            "agents_activated": state.get("agents_activated", []) + [AGENT_NAME],
        }


def _parse_signals(response_text: str, agent_name: str) -> list[SignalOutput]:
    signals = []
    if not response_text or "NO_SIGNALS_FOUND" in response_text:
        return signals
    json_pattern = re.compile(r'\{[^{}]*"signal_type"[^{}]*\}', re.DOTALL)
    for match in json_pattern.findall(response_text):
        try:
            data = json.loads(match)
            signals.append({
                "agent":       agent_name,
                "signal_type": data.get("signal_type", SIGNAL_TYPE),
                "nct_id":      data.get("nct_id", ""),
                "summary":     data.get("summary", ""),
                "evidence":    data.get("evidence", []),
                "confidence":  float(data.get("confidence", 0.5)),
            })
        except (json.JSONDecodeError, ValueError):
            continue
    return signals


async def _execute_tool(tool_call: dict, available_tools: list) -> str:
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("args", {})
    tool_func = next((t for t in available_tools if t.name == tool_name), None)
    if tool_func is None:
        return f"Error: Tool '{tool_name}' not found."
    try:
        return str(tool_func.invoke(tool_args))
    except Exception as e:
        return f"Error executing '{tool_name}': {str(e)}"