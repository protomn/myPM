"""The council runner — agent doctrines executed as real Claude calls.

docs/agents/council.md defines six agents with exclusive mandates and a fast
loop that threads their reasoning. v0.1 shipped the doctrines as documentation;
this runs them. Each agent:

  1. Recalls a ContextBundle biased to its declared reads (agents.py + ranking),
  2. reasons under its full doctrine as the system prompt, with the recalled
     knowledge and any prior agents' output as context,
  3. produces a draft proposal in the form its doctrine specifies.

The runner never writes active knowledge and never auto-orchestrates beyond the
sequence it is given — the human conducts and authors (council.md → The human's
role). It requires the optional `anthropic` dependency and an API key; absent
either, the caller is told to install/configure rather than silently degrading,
because the whole value of this path is the model.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import agents, claude
from .retriever import retrieve

# Council assembly presets (council.md → Council assembly). The default is the
# "minimum viable council for any non-trivial Decision: Principal + Adversarial".
PRESETS = {
    "minimal":  ["principal", "adversarial"],
    "decision": ["research", "principal", "adversarial", "performance"],
    "full":     ["research", "principal", "adversarial", "performance", "oss"],
    "review":   ["oss"],
    "research": ["research"],
    "reflect":  ["reflection"],
}
DEFAULT_PRESET = "minimal"

# Appended to every agent's doctrine, distilling the council's non-negotiables so
# a single-agent call still respects the mandate boundaries (council.md).
_GUARDRAILS = """

---
Operating rules for this run:
- Stay strictly within your mandate. Do not perform another agent's job.
- You produce DRAFTS and findings only. Never mark anything active or final;
  the human authors every promotion by merging a PR.
- Ground every claim in the recalled ContextBundle or the stated task. Do not
  invent lessons, decisions, or evidence that the record does not contain.
- If the recalled context already settles part of the task, say so and cite the
  node id rather than re-deriving it."""


@dataclass
class AgentTurn:
    agent: str
    mandate: str
    command: str
    output: str
    bundle: dict


def _doctrine_text(agent) -> str | None:
    """Locate an agent's doctrine: installed copy first (the user may have edited
    it), then the repo docs, then the bundled template."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (
        os.path.join(os.path.abspath("."), ".claude", "agents", agent.doctrine),
        os.path.join(os.path.abspath("."), ".claude", "docs", "agents", agent.doctrine),
        os.path.join(here, "templates", "agents", agent.doctrine),
    ):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return None


def resolve_agents(agents_csv=None, preset=None):
    """Turn a --agents list or --preset into a validated, ordered agent list."""
    if agents_csv:
        names = [a.strip() for a in agents_csv.split(",") if a.strip()]
    elif preset:
        if preset not in PRESETS:
            raise ValueError(f"unknown preset '{preset}'; choose from {sorted(PRESETS)}")
        names = list(PRESETS[preset])
    else:
        names = list(PRESETS[DEFAULT_PRESET])
    unknown = [n for n in names if n not in agents.AGENTS]
    if unknown:
        raise ValueError(f"unknown agent(s): {unknown}; "
                         f"choose from {list(agents.AGENT_NAMES)}")
    return names


def _build_user(task, bundle, prior):
    parts = [f"# Task\n{task}", ""]
    if prior:
        parts.append("# Prior council output (for your reference, not to repeat)")
        for name, output in prior:
            parts.append(f"## {name}\n{output}")
        parts.append("")
    parts.append("# Recalled knowledge (ContextBundle)")
    parts.append("This is the slice of the graph relevant to the task, ranked and "
                 "biased to your declared reads. Treat its nodes as settled context.")
    parts.append("```json")
    parts.append(json.dumps(bundle, indent=2))
    parts.append("```")
    return "\n".join(parts)


def run_agent(store, agent_name, task, project=None, client=None, prior=None):
    """Run one agent: recall -> reason under doctrine -> draft proposal."""
    agent = agents.get(agent_name)
    if agent is None:
        raise ValueError(f"unknown agent '{agent_name}'")
    client = client or claude.ClaudeClient()

    bundle = retrieve(store, task, project=project, agent=agent_name).to_dict()
    doctrine = _doctrine_text(agent) or (
        f"You are the {agent.name} agent. Mandate: {agent.mandate}.")
    system = doctrine + _GUARDRAILS
    output = client.complete(system=system, user=_build_user(task, bundle, prior))
    return AgentTurn(agent_name, agent.mandate, agent.command, output, bundle)


def run_council(store, task, agent_names, project=None, client=None):
    """Run agents in sequence, threading each one's output to the next (the fast
    loop's hand-offs). Returns one AgentTurn per agent."""
    client = client or claude.ClaudeClient()
    turns, prior = [], []
    for name in agent_names:
        turn = run_agent(store, name, task, project=project, client=client, prior=prior)
        turns.append(turn)
        prior.append((name, turn.output))
    return turns
