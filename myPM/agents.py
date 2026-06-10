"""The agent registry — the six council mandates as data.

docs/agents/council.md defines six agents, each with an exclusive mandate, a
cognitive mode, an invoking command, and a declared set of node types it reads
during Recall (its "declared reads"). This module is the machine-readable form
of those doctrines: the single source of truth that ranking (role weighting) and
the council runner consume, so the prose and the code cannot drift — the same
discipline constraints.py applies to the edge model.

`reads` is ordered by priority. The first type is the agent's primary input, as
each doctrine states at the top of its Recall section; later types are secondary.
Ranking turns that order into a graded role-fit weight (see ranking.role_weight).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Agent:
    name: str          # registry key / stable handle
    mandate: str       # the one-line cognitive mode from council.md
    command: str       # the slash command that invokes this agent
    reads: tuple       # node types in Recall-priority order (primary first)
    doctrine: str      # filename under .claude/docs/agents/


# Reads transcribed from each doctrine's "Recall" section, primary input first.
# (docs/agents/*.md). Order is meaningful: it drives role_weight grading.
AGENTS = {
    "research": Agent(
        "research", "explores the option space", "/research",
        ("decision", "lesson", "pattern", "component"),
        "research-engineer.md"),
    "principal": Agent(
        "principal", "decides among named options", "/architect",
        ("decision", "pattern", "component", "lesson", "preference"),
        "principal-engineer.md"),
    "adversarial": Agent(
        "adversarial", "attacks the proposed design", "/architect",
        ("lesson", "pattern", "decision", "component"),
        "adversarial-reviewer.md"),
    "performance": Agent(
        "performance", "measures cost and scaling", "/architect",
        ("component", "lesson", "decision", "pattern"),
        "performance-engineer.md"),
    "oss": Agent(
        "oss", "gates change against the graph", "/review",
        ("decision", "pattern", "component", "preference", "lesson"),
        "oss-maintainer.md"),
    "reflection": Agent(
        "reflection", "distills what actually happened", "/reflect",
        ("lesson", "pattern", "component", "decision"),
        "reflection-analyst.md"),
}

AGENT_NAMES = tuple(AGENTS.keys())


def get(name: str) -> Agent | None:
    """Look up an agent by registry key. Returns None for unknown/unset names."""
    return AGENTS.get(name) if name else None


def reads_of(name: str) -> tuple:
    """The declared reads of an agent, or () if the agent is unknown/unset."""
    agent = get(name)
    return agent.reads if agent else ()
