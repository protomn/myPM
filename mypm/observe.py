"""mypm observe — the live Observer, first deployment mode.

The extraction core (bootstrap.py) pointed at a conversation instead of git
history. Agents working under the doctrines end their replies with fenced
`mypm-capture` blocks — a form the agent fills in while the reasoning is hot,
which sidesteps raw-transcript mining (the lowest-signal extraction source).
This module is pure transport plus the same narrowing bootstrap applies:

    parse blocks -> validate type/fields -> Recall-dedup vs the graph -> inbox

Two entry points share the core:
  - `observe(store, transcript_path)`  — a Claude Code Stop/SubagentStop hook
    feeds the session transcript (JSONL); assistant text is scanned for blocks.
  - `capture_blocks(store, text)`      — the council runner feeds each agent's
    output directly.

Discipline unchanged: observations land in the inbox ONLY, idempotently (an
observation's id is a hash of its block, so re-scanning the same transcript
re-writes the same file instead of duplicating it). Promotion stays human.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass

import yaml

from .bootstrap import _tokens, _dup_of
from .models import Observation
from .schemas import ENTITY_TYPES

_TYPEABLE = tuple(t for t in ENTITY_TYPES if t != "project")

_BLOCK_RE = re.compile(r"```mypm-capture[ \t]*\n(.*?)```", re.S)


@dataclass
class ObserveResult:
    title: str
    status: str          # "captured" | "duplicate" | "invalid"
    reason: str = ""
    obs_path: str | None = None


def extract_blocks(text):
    """Parse every well-formed mypm-capture block out of free text. Malformed
    YAML or a non-dict payload is skipped silently — an agent that mangles the
    form has produced prose, not a capture."""
    out = []
    for m in _BLOCK_RE.finditer(text or ""):
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            data["_raw"] = m.group(1)
            out.append(data)
    return out


def _validate(block):
    """Return a drop reason, or None to keep."""
    if block.get("type") not in _TYPEABLE:
        return f"unknown type {block.get('type')!r}"
    if not str(block.get("title") or "").strip():
        return "missing title"
    fields = block.get("fields")
    if fields is not None and not isinstance(fields, dict):
        return "fields must be a mapping"
    return None


def capture_blocks(store, text, agent=None, session=None, source="observer"):
    """Run every mypm-capture block in `text` through validate -> dedup ->
    inbox. Returns one ObserveResult per block."""
    # Recall as the capture filter: seed dedup from what the graph holds.
    seen = {}
    project_nodes = set()
    for n in store.all_nodes():
        if n.status in ("draft", "active"):
            seen.setdefault(n.type, []).append((n.id, _tokens(n.search_text())))
        if n.type == "project":
            project_nodes.add(n.id)

    results = []
    for block in extract_blocks(text):
        reason = _validate(block)
        title = str(block.get("title") or "?").strip()
        if reason:
            results.append(ObserveResult(title, "invalid", reason))
            continue

        ntype = block["type"]
        fields = dict(block.get("fields") or {})
        toks = _tokens(title + " " + " ".join(str(v) for v in fields.values()))
        dup = _dup_of(toks, ntype, seen)
        if dup:
            results.append(ObserveResult(title, "duplicate", f"~ {dup}"))
            continue

        project = block.get("project")
        links = []
        if project and f"project_{project}" in project_nodes:
            links.append({"type": "relates_to", "to": f"project_{project}",
                          "note": "captured by the live observer"})

        provenance = "_Source: live observer"
        if agent:
            provenance += f", agent {agent}"
        if session:
            provenance += f", session {session[:8]}"
        provenance += "._"
        body = (str(block.get("body") or "").strip() or title) + f"\n\n{provenance}"

        digest = hashlib.sha256(block["_raw"].encode("utf-8")).hexdigest()[:10]
        obs = Observation(
            id=f"obs_obsv_{digest}",
            text=title, source=source, project=project,
            proposed={
                "type": ntype, "title": title, "fields": fields,
                "tags": list(block.get("tags") or []) + ["from-observer"],
                "body": body, "links": links,
            })
        path = store.write_observation(obs)
        seen.setdefault(ntype, []).append((obs.id, toks))
        results.append(ObserveResult(title, "captured", "", path))
    return results


def _assistant_text(transcript_path):
    """Concatenate the text of every assistant message in a Claude Code JSONL
    transcript. Defensive: unknown line shapes are skipped, never fatal."""
    parts = []
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            content = (entry.get("message") or {}).get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
    return "\n\n".join(p for p in parts if p)


def observe(store, transcript_path, agent=None, session=None):
    """Scan a session transcript for capture blocks. Idempotent: block ids are
    content-addressed, so re-scanning a transcript rewrites the same inbox
    files rather than multiplying them."""
    if not os.path.exists(transcript_path):
        return []
    return capture_blocks(store, _assistant_text(transcript_path),
                          agent=agent, session=session)
