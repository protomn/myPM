"""Composite ranking for the Recall phase (docs/architecture/golden-loop.md).

The seed step scores each candidate by relevance to the task (lexical today,
semantic later). Ranking is the second judgment: once relevant nodes are pulled
in, the token budget forces a choice about which earn a place in the bundle.
Four signals are blended:

    relevance   how well the node matches the task        (from the seeder)
    centrality  how connected the node is in the graph    (degree, normalized)
    recency     how fresh the knowledge is                (age decay)
    role_fit    whether the node's type is what the        (agent registry)
                active agent reads

Relevance dominates — a node off-topic but central and fresh should not outrank
a node that actually answers the task. The other three break ties and surface
load-bearing, current, role-appropriate knowledge first. All weights live here as
data so they are tunable and inspectable without touching retrieval logic, the
same way constraints.py holds the edge model.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from . import agents

# Blend weights. relevance is the anchor (1.0); the rest are tie-breakers whose
# magnitudes say how much each may perturb the relevance ordering.
WEIGHTS = {
    "relevance": 1.0,
    "centrality": 0.25,
    "recency": 0.20,
    "role_fit": 0.40,
}

# Knowledge half-life: a node loses half its recency contribution every this many
# days. Long, because engineering knowledge ages slowly — a Decision from a year
# ago is usually still the law of the codebase (docs/agents/oss-maintainer.md).
RECENCY_HALFLIFE_DAYS = 180.0

# Neutral score for a node missing a timestamp — neither rewarded nor penalized.
_NEUTRAL_RECENCY = 0.5


def _parse_iso(ts: str):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def recency_score(updated_at: str, now: datetime | None = None) -> float:
    """Exponential age decay in [0, 1]. Fresh -> ~1, one half-life old -> 0.5."""
    dt = _parse_iso(updated_at)
    if dt is None:
        return _NEUTRAL_RECENCY
    now = now or datetime.now(timezone.utc)
    age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    return math.pow(0.5, age_days / RECENCY_HALFLIFE_DAYS)


def centrality_score(degree: int, max_degree: int) -> float:
    """Degree centrality normalized against the most-connected node in the bundle.

    Normalizing per-bundle (not globally) keeps the signal meaningful for small
    graphs, where an absolute degree threshold would never fire.
    """
    if max_degree <= 0:
        return 0.0
    return min(1.0, degree / max_degree)


def role_weight(node_type: str, agent_name: str | None) -> float:
    """Graded role fit in [0, 1] from the agent's declared reads (agents.py).

    The agent's primary read scores 1.0; secondary reads decay linearly to 0.4;
    a type the agent does not read scores 0.0. With no active agent, role_fit is
    inert (every node scores 0.0 and the weight contributes nothing).
    """
    reads = agents.reads_of(agent_name)
    if node_type not in reads:
        return 0.0
    if len(reads) == 1:
        return 1.0
    rank = reads.index(node_type)
    return 1.0 - 0.6 * (rank / (len(reads) - 1))


def score(*, relevance: float, degree: int, max_degree: int,
          updated_at: str, node_type: str, agent_name: str | None = None,
          now: datetime | None = None) -> float:
    """The composite score retrieve() ranks the bundle by."""
    return (
        WEIGHTS["relevance"] * relevance
        + WEIGHTS["centrality"] * centrality_score(degree, max_degree)
        + WEIGHTS["recency"] * recency_score(updated_at, now)
        + WEIGHTS["role_fit"] * role_weight(node_type, agent_name)
    )
