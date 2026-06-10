"""/reflect — closes the Capture phase by running Gate 1.

Reads observations from the inbox, applies the Gate 1 admission test, and writes
the survivors to disk as `draft` nodes (docs/architecture/capture.md). Proposing
the type and fields is delegated to a proposer (the agent-layer seam); the GATE
itself — the policy that decides what is allowed into the graph — is real and
lives here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import SCHEMAS
from .models import Node, make_node_id, now_iso
from .proposer import RuleProposer

# Evaluative words that, alone, signal a "mood" rather than a fact.
_MOOD_ONLY = re.compile(r"^\W*(it'?s |this is )?(so |really |very )?"
                        r"(terrible|bad|awful|great|good|slow|nice|ugh|annoying)\W*$",
                        re.I)


@dataclass
class Gate1Result:
    observation_id: str
    admitted: bool
    node_id: str | None
    reasons: list


def _future_recall_test(obs, proposal):
    """The Gate 1 criteria from capture.md. Returns (ok, reasons)."""
    reasons = []
    text = obs.text.strip()

    # specific: not a bare mood, has substance
    if _MOOD_ONLY.match(text) or len(text.split()) < 3:
        reasons.append("FAIL specific: reads as a mood, not a finding")
    else:
        reasons.append("ok specific")

    # typeable: proposer assigned a known type
    if proposal["type"] in SCHEMAS:
        reasons.append(f"ok typeable: {proposal['type']}")
    else:
        reasons.append(f"FAIL typeable: unknown type '{proposal['type']}'")

    # minimally structured: has the type's Gate-1 required fields
    missing = [f for f in SCHEMAS[proposal["type"]]["required_draft"]
               if not proposal["fields"].get(f)]
    if missing:
        reasons.append(f"FAIL min-structure: missing {missing}")
    else:
        reasons.append("ok min-structure")

    ok = not any(r.startswith("FAIL") for r in reasons)
    return ok, reasons


def reflect(store, proposer=None, dedupe_against=None):
    proposer = proposer or RuleProposer()
    existing_ids = set(dedupe_against or store.nodes_by_id().keys())
    results = []

    for obs, path in store.all_observations():
        proposal = proposer.propose(obs)
        ok, reasons = _future_recall_test(obs, proposal)

        # id is a clean stable handle: explicit id wins, else slug, else title
        node_id = proposal.get("id") or make_node_id(
            proposal["type"], proposal.get("slug") or proposal["title"])
        # non-redundant
        if node_id in existing_ids:
            ok = False
            reasons.append(f"FAIL non-redundant: {node_id} already exists")
        else:
            reasons.append("ok non-redundant")

        if not ok:
            results.append(Gate1Result(obs.id, False, None, reasons))
            continue

        scope = f"project:{obs.project}" if obs.project else "global"
        node = Node(
            id=node_id, type=proposal["type"], title=proposal["title"],
            scope=scope, status="draft", body=proposal.get("body", ""),
            confidence=proposal.get("confidence", "medium"),
            source={"type": obs.source}, tags=proposal["tags"],
            fields=proposal["fields"], proposed_links=proposal.get("links", []),
        )
        store.write_node(node)
        existing_ids.add(node_id)
        store.remove_observation(path)   # observation graduated into the graph
        results.append(Gate1Result(obs.id, True, node_id, reasons))

    return results