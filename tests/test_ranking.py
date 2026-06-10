"""Tests for ContextBundle ranking (centrality, recency, agent-role weighting).

Unit tests pin the four ranking signals; integration tests prove the signals
actually reorder a retrieved bundle. Runnable with `python tests/test_ranking.py`.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from myPM import agents, ranking
from myPM.store import Store
from myPM.models import Node
from myPM.retriever import retrieve


# ---- unit: recency ------------------------------------------------------

def test_recency_fresh_is_high():
    now = datetime(2026, 6, 10, tzinfo=timezone.utc)
    fresh = now.isoformat()
    assert ranking.recency_score(fresh, now=now) > 0.99


def test_recency_one_halflife_is_half():
    now = datetime(2026, 6, 10, tzinfo=timezone.utc)
    old = (now - timedelta(days=ranking.RECENCY_HALFLIFE_DAYS)).isoformat()
    assert abs(ranking.recency_score(old, now=now) - 0.5) < 0.01


def test_recency_missing_is_neutral():
    assert ranking.recency_score("") == 0.5
    assert ranking.recency_score(None) == 0.5
    assert ranking.recency_score("not-a-date") == 0.5


# ---- unit: centrality ---------------------------------------------------

def test_centrality_normalizes_to_max():
    assert ranking.centrality_score(0, 4) == 0.0
    assert ranking.centrality_score(2, 4) == 0.5
    assert ranking.centrality_score(4, 4) == 1.0


def test_centrality_no_edges_is_zero():
    assert ranking.centrality_score(0, 0) == 0.0


# ---- unit: role fit -----------------------------------------------------

def test_role_weight_primary_is_one():
    # adversarial reads lesson first (docs/agents/adversarial-reviewer.md)
    assert ranking.role_weight("lesson", "adversarial") == 1.0


def test_role_weight_secondary_decays():
    w_primary = ranking.role_weight("lesson", "adversarial")
    w_last = ranking.role_weight("component", "adversarial")   # last in reads
    assert w_primary == 1.0
    assert 0.39 < w_last < 0.41
    assert w_last < w_primary


def test_role_weight_unread_type_is_zero():
    # adversarial does not read preferences
    assert ranking.role_weight("preference", "adversarial") == 0.0


def test_role_weight_no_agent_is_inert():
    assert ranking.role_weight("lesson", None) == 0.0


def test_registry_matches_doctrines():
    # every registry agent points at a doctrine file that exists
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    doctrines = os.path.join(here, ".claude", "docs", "agents")
    for a in agents.AGENTS.values():
        assert os.path.exists(os.path.join(doctrines, a.doctrine)), a.doctrine
        assert a.reads, f"{a.name} reads nothing"


# ---- integration: signals reorder a real bundle -------------------------

def _active(s, node_id, ntype, title, body, scope, updated_at, tags):
    s.write_node(Node(
        id=node_id, type=ntype, title=title, scope=scope, status="active",
        body=body, tags=tags, updated_at=updated_at,
        fields=_min_fields(ntype, body)))


def _min_fields(ntype, body):
    if ntype == "lesson":
        return {"trigger": body, "root_cause": body, "takeaway": body}
    if ntype == "decision":
        return {"context": body, "choice": body, "alternatives": ["x"],
                "rationale": body, "consequences": body}
    return {}


def test_agent_role_bias_reorders(tmp_path):
    """Two equally relevant nodes of different types; the active agent's
    primary-read type should rank first."""
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    ts = "2026-06-01T00:00:00+00:00"
    _active(s, "lesson_cache_stampede", "lesson", "cache stampede",
            "cache stampede under load", "global", ts, ["cache"])
    _active(s, "decision_cache_layer", "decision", "cache stampede layer",
            "cache stampede mitigation choice", "global", ts, ["cache"])

    # adversarial reads lesson first -> lesson should lead
    b_adv = retrieve(s, "cache stampede", agent="adversarial")
    assert b_adv.agent == "adversarial"
    assert b_adv.nodes[0]["id"] == "lesson_cache_stampede"

    # oss reads decision before lesson -> decision should lead
    b_oss = retrieve(s, "cache stampede", agent="oss")
    assert b_oss.nodes[0]["id"] == "decision_cache_layer"


def test_recency_breaks_ties(tmp_path):
    """Same type, same relevance; the fresher node ranks first."""
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    _active(s, "lesson_retry_storm_old", "lesson", "retry storm",
            "retry storm incident", "global", old, ["retry"])
    _active(s, "lesson_retry_storm_new", "lesson", "retry storm",
            "retry storm incident", "global", new, ["retry"])
    b = retrieve(s, "retry storm")
    assert b.nodes[0]["id"] == "lesson_retry_storm_new"


if __name__ == "__main__":
    import tempfile, pathlib
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            if fn.__code__.co_argcount:
                with tempfile.TemporaryDirectory() as d:
                    fn(pathlib.Path(d))
            else:
                fn()
            print(f"  ok  {name}")
            passed += 1
    print(f"\n{passed} tests passed.")
