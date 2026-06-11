"""/reflect — closes the Capture phase by running Gate 1.

Reads observations from the inbox, applies the Gate 1 admission test, and writes
the survivors to disk as `draft` nodes (docs/architecture/capture.md). Proposing
the type and fields is delegated to a proposer (the agent-layer seam); the GATE
itself — the policy that decides what is allowed into the graph — is real and
lives here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .schemas import SCHEMAS, coerce_fields
from .models import Node, make_node_id, now_iso
from .proposer import get_proposer
from .validator import DUP_SIMILARITY, _DUP_STOP


def _content_tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _DUP_STOP and len(w) > 2}

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
    held_path: str | None = None     # where a failing observation was quarantined


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


def reflect(store, proposer=None, dedupe_against=None, retry_held=False):
    proposer = proposer or get_proposer()
    nodes_by_id = store.nodes_by_id()
    existing_ids = set(dedupe_against or nodes_by_id.keys())
    results = []

    if retry_held:
        store.release_held()

    new_tokens = {}              # nodes written THIS run, for collision checks

    for obs, path in store.all_observations():
        proposal = proposer.propose(obs)
        if proposal.get("type") in SCHEMAS:
            proposal["fields"] = coerce_fields(proposal["type"],
                                               proposal.get("fields"))
        ok, reasons = _future_recall_test(obs, proposal)

        # id is a clean stable handle: explicit id wins, else slug, else title
        node_id = proposal.get("id") or make_node_id(
            proposal["type"], proposal.get("slug") or proposal["title"])
        # non-redundant. A colliding id is only redundancy when the CONTENT is
        # the same knowledge; two different lessons that happen to share their
        # first six words are a slug accident, not a restatement, so the id is
        # suffixed (content-hashed: idempotent on re-runs) instead of held.
        if node_id in existing_ids:
            obs_toks = _content_tokens(
                " ".join([proposal["title"],
                          *(str(v) for v in proposal["fields"].values()),
                          proposal.get("body", "")]))
            prior = nodes_by_id.get(node_id)
            prior_toks = (_content_tokens(prior.search_text()) if prior
                          else new_tokens.get(node_id))
            similar = (prior_toks is None or not obs_toks or not prior_toks or
                       len(obs_toks & prior_toks) / len(obs_toks | prior_toks)
                       >= DUP_SIMILARITY)
            if similar:
                ok = False
                reasons.append(f"FAIL non-redundant: {node_id} already exists")
            else:
                suffix = hashlib.sha256(obs.text.encode("utf-8")).hexdigest()[:6]
                node_id = f"{node_id}_{suffix}"
                if node_id in existing_ids:        # identical text re-captured
                    ok = False
                    reasons.append(f"FAIL non-redundant: {node_id} already exists")
                else:
                    reasons.append(f"ok non-redundant (slug collision; "
                                   f"id suffixed to {node_id})")
        else:
            reasons.append("ok non-redundant")

        if not ok:
            # quarantine: stop re-processing (and re-billing) this observation
            # on every run; the engineer edits it and uses --retry-held
            held = store.hold_observation(obs, path, reasons)
            results.append(Gate1Result(obs.id, False, None, reasons, held))
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
        new_tokens[node_id] = _content_tokens(node.search_text())
        store.remove_observation(path)   # observation graduated into the graph
        results.append(Gate1Result(obs.id, True, node_id, reasons))

    return results