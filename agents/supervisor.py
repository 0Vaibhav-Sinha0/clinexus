##############################################################################
# agents/supervisor.py
#
# Coordinates all specialist agents and compiles their findings
# into a final research integrity brief.
##############################################################################

import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from graph.state import MosaicState
from config.settings import settings
from config.logging_config import setup_logging

logger = setup_logging(__name__)


async def supervisor_route(state: MosaicState) -> dict:
    """Initial supervisor node — routes to all specialist agents."""

    logger.info("Supervisor routing to specialist agents")
    return state


async def supervisor_compile(state: MosaicState) -> dict:
    """Supervisor compilation node — reads signals and writes final brief."""

    logger.info("Supervisor compiling final brief from specialist signals")

    signals = state.get("signals", [])
    task    = state.get("task", "Research integrity analysis")

    if not signals:
        final_brief = f"""
CLINEXUS RESEARCH INTEGRITY BRIEF
==================================

Task: {task}

Result: No research integrity signals detected across all specialist agents.

This does not mean the studies are perfect — it means no clear violations
were identified in the analysis. Absence of evidence is not evidence of absence.

All data has been logged to procedural memory for pattern identification
in future analyses.
"""
    else:
        signals_text = _format_signals_for_brief(signals)

        llm = ChatGroq(
            model=settings.groq_model,
            temperature=0.1,
            api_key=settings.groq_api_key,
        )

        system_prompt = """You are the compilation agent for Clinexus.

Your task: Read the research integrity signals from all 6 specialist agents
and write a concise, executive-level research integrity brief.

The brief should:
1. Summarize the key findings (high-confidence signals only)
2. Group signals by type (outcome switching, missing results, safety gaps, etc)
3. Highlight any patterns across studies (same sponsor, same condition)
4. Rate overall risk level: Critical / High / Medium / Low
5. Recommend next steps for human review

Be direct and clear. Use plain language. Assume the reader is a regulator
or compliance officer who needs to make a decision.

Format the brief as structured text, not JSON."""

        human_message = f"""
Please compile the following signals into a research integrity brief:

{signals_text}

Write the brief now.
"""

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_message),
        ])

        final_brief = response.content or "Error generating brief"

    return {
        "final_brief":  final_brief,
        "run_complete": True,
    }


def _format_signals_for_brief(signals: list) -> str:
    if not signals:
        return "No signals found."

    grouped = {}
    for signal in signals:
        signal_type = signal.get("signal_type", "unknown")
        if signal_type not in grouped:
            grouped[signal_type] = []
        grouped[signal_type].append(signal)

    output = []
    for signal_type, type_signals in grouped.items():
        output.append(f"\n{signal_type.upper()} ({len(type_signals)} signals):")
        for signal in type_signals:
            confidence = signal.get("confidence", 0)
            summary    = signal.get("summary", "")
            evidence   = signal.get("evidence", [])
            agent      = signal.get("agent", "")

            output.append(f"  [{agent}] Confidence {confidence:.2f}")
            output.append(f"    Summary: {summary}")
            if evidence:
                output.append(f"    Evidence: {', '.join(evidence[:2])}")

    return "\n".join(output)