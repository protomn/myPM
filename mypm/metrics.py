"""Review telemetry — pricing the human gate.

The bet behind `fill` (and /enrich-drafts) is that a pre-enriched draft
approves in seconds while a bare one costs minutes of archaeology per draft.
This module collects the evidence for that bet: every review verb appends one
JSON line to <root>/.metrics/review_log.jsonl, and `mypm review stats` splits
time-to-decision by whether fill ran on the draft first.

Events (all carry a full-precision UTC `ts` and the `node` id):

    shown      interactive review displayed the draft — starts the clock
    fill       fields/links saved without promotion — marks the draft enriched
    approve / reject / merge / supersede
               the decision; carries ok, the fields typed at decision time,
               and filled_before (computed here, never by the caller)

The log is observability, not knowledge: it never enters the graph, the
validator never sees it, and a logging failure must never block a promotion —
every write is best-effort by design.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone

DECISION_EVENTS = ("approve", "reject", "merge", "supersede")

# Pair a decision with a preceding `shown` only inside this window; a gap
# longer than this is an abandoned terminal, not a measurement.
MAX_PAIR_SECONDS = 3600.0


def log_path(store) -> str:
    return os.path.join(store.root, ".metrics", "review_log.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(store, event: str, node_id: str, **extra) -> None:
    """Append one event line. Best-effort (see module docstring)."""
    rec = {"ts": _now(), "event": event, "node": node_id}
    rec.update(extra)
    try:
        path = log_path(store)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def read_events(store) -> list:
    try:
        with open(log_path(store), "r", encoding="utf-8") as f:
            out = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue        # one corrupt line must not kill stats
            return out
    except OSError:
        return []


def was_filled(store, node_id: str) -> bool:
    return any(e.get("event") == "fill" and e.get("node") == node_id
               for e in read_events(store))


def log_decision(store, verb: str, node_id: str, ok: bool, fields=None) -> None:
    """The one entry point review verbs use for decisions: filled_before is
    derived from the log here, so no caller can get it wrong."""
    log_event(store, verb, node_id, ok=bool(ok),
              filled_before=was_filled(store, node_id),
              fields_typed=sorted(fields or {}))


def _parse_ts(ts):
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


# ---- recall telemetry --------------------------------------------------------
# The read-path twin of the review log. Three events answer the only question
# that matters about Recall: did the recalled bundle change anything?
#
#     bundle    retrieve() produced a bundle (task + node ids)
#     feedback  the human rated the most recent bundle (good | bad | partial)
#     cited     a later session's output actually referenced a bundled node
#
# Together they yield the Recall Win Rate (rated good / rated) and the citation
# rate (bundles whose nodes were later cited) — measured, not assumed.

def recall_log_path(store) -> str:
    return os.path.join(store.root, ".metrics", "recall_log.jsonl")


def _append(path, rec) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def read_recall_events(store) -> list:
    try:
        with open(recall_log_path(store), "r", encoding="utf-8") as f:
            out = []
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
            return out
    except OSError:
        return []


def log_bundle(store, bundle) -> None:
    nodes = [n["id"] if isinstance(n, dict) else n.id for n in bundle.nodes]
    _append(recall_log_path(store), {
        "ts": _now(), "event": "bundle", "task": bundle.task[:200],
        "agent": bundle.agent, "nodes": nodes})


def log_feedback(store, verdict: str, note: str = ""):
    """Attach a rating to the most recent bundle. Returns that bundle's task
    string, or None when there is nothing to rate."""
    bundles = [e for e in read_recall_events(store) if e.get("event") == "bundle"]
    if not bundles:
        return None
    last = bundles[-1]
    _append(recall_log_path(store), {
        "ts": _now(), "event": "feedback", "verdict": verdict,
        "note": note, "bundle_ts": last.get("ts")})
    return last.get("task")


def log_citations(store, node_ids, session=None) -> None:
    for nid in node_ids:
        _append(recall_log_path(store), {
            "ts": _now(), "event": "cited", "node": nid, "session": session})


def recall_stats(store) -> dict:
    events = read_recall_events(store)
    bundles = [e for e in events if e.get("event") == "bundle"]
    feedback = [e for e in events if e.get("event") == "feedback"]
    cited_ts = [(e.get("node"), _parse_ts(e.get("ts")))
                for e in events if e.get("event") == "cited"]

    verdicts = {}
    for f in feedback:
        v = f.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
    rated = verdicts.get("good", 0) + verdicts.get("bad", 0)

    used = 0
    for b in bundles:
        t0 = _parse_ts(b.get("ts"))
        ids = set(b.get("nodes") or [])
        if t0 and any(n in ids and t and t >= t0 for n, t in cited_ts):
            used += 1

    return {
        "bundles": len(bundles),
        "verdicts": verdicts,
        "win_rate": (verdicts.get("good", 0) / rated) if rated else None,
        "bundles_cited": used,
        "citation_rate": (used / len(bundles)) if bundles else None,
        "nodes_cited": len({n for n, _ in cited_ts}),
    }


def _cohort(rows: list) -> dict:
    timed = [r["duration_s"] for r in rows if r["duration_s"] is not None]
    return {
        "n": len(rows),
        "timed": len(timed),
        "median_s": statistics.median(timed) if timed else None,
        "mean_s": statistics.fmean(timed) if timed else None,
        "mean_fields_typed": (statistics.fmean(r["fields_typed"] for r in rows)
                              if rows else None),
    }


def stats(store) -> dict:
    """Aggregate logged decisions into filled/unfilled cohorts.

    Duration is shown -> decision for the same node (interactive review logs
    `shown` the moment a draft is displayed, so the duration includes the
    human's reading and typing — exactly the cost being measured). Decisions
    with no usable shown event still count; they just carry no duration.
    """
    last_shown = {}
    decisions = []
    for e in read_events(store):
        node, kind = e.get("node"), e.get("event")
        if kind == "shown":
            last_shown[node] = _parse_ts(e.get("ts"))
        elif kind in DECISION_EVENTS:
            dur = None
            t0, t1 = last_shown.pop(node, None), _parse_ts(e.get("ts"))
            if t0 is not None and t1 is not None:
                d = (t1 - t0).total_seconds()
                if 0 <= d <= MAX_PAIR_SECONDS:
                    dur = d
            decisions.append({
                "verb": kind, "node": node, "ok": e.get("ok", True),
                "filled_before": bool(e.get("filled_before")),
                "fields_typed": len(e.get("fields_typed") or []),
                "duration_s": dur,
            })

    by_verb = {}
    for d in decisions:
        by_verb[d["verb"]] = by_verb.get(d["verb"], 0) + 1
    return {
        "decisions": len(decisions),
        "by_verb": by_verb,
        "filled": _cohort([d for d in decisions if d["filled_before"]]),
        "unfilled": _cohort([d for d in decisions if not d["filled_before"]]),
    }
