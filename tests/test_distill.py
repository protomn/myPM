"""Tests for distill's Gate 2 edge handling: illegal proposed links must block
promotion (not promote past the failure), real edges must satisfy the linked
requirement, and a materialized supersedes edge must retire the old node.

Runnable with `python tests/test_distill.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mypm.store import Store
from mypm.models import Node, Edge, make_edge_id
from mypm.distill import distill


def _active_decision(nid="decision_use_redis", title="Use Redis for queues"):
    return Node(
        id=nid, type="decision", title=title,
        scope="global", status="active", body=title,
        fields={"context": "queue backend needed", "choice": title,
                "alternatives": ["rabbitmq"], "rationale": "ops familiarity",
                "consequences": "redis becomes a hard dependency"},
    )


def _draft_decision(nid, title, links):
    return Node(
        id=nid, type="decision", title=title,
        scope="global", status="draft", body=title,
        fields={"context": "ctx", "choice": title,
                "alternatives": ["other"], "rationale": "why",
                "consequences": "what follows"},
        proposed_links=links,
    )


def test_illegal_edge_blocks_promotion(tmp_path):
    """A draft with an illegal proposed link must stay a draft — previously it
    landed in BOTH blocked and promoted."""
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_active_decision())
    # 'concerns' is lesson->component; decision->decision is illegal
    s.write_node(_draft_decision("decision_bad_link", "Switch to NSQ",
                                 [{"type": "concerns", "to": "decision_use_redis"}]))
    rep = distill(s)
    assert "decision_bad_link" not in rep.promoted
    blocked_ids = [nid for nid, _ in rep.blocked]
    assert "decision_bad_link" in blocked_ids
    assert s.nodes_by_id()["decision_bad_link"].status == "draft"


def test_real_edge_satisfies_linked_requirement(tmp_path):
    """A draft with a materialized edge but no proposed links passes 'linked'."""
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_active_decision())
    s.write_node(_draft_decision("decision_successor", "Adopt NSQ", links=[]))
    edge = Edge(id=make_edge_id("decision_successor", "builds_on", "decision_use_redis"),
                type="builds_on", from_id="decision_successor",
                to_id="decision_use_redis")
    s.write_edge(edge)
    rep = distill(s)
    assert "decision_successor" in rep.promoted, rep.blocked


def test_supersedes_edge_retires_old_node(tmp_path):
    """Materializing a supersedes link flips the superseded node to 'superseded'."""
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_active_decision())
    s.write_node(_draft_decision(
        "decision_replace_redis_with_nsq", "Replace Redis with NSQ",
        [{"type": "supersedes", "to": "decision_use_redis"}]))
    rep = distill(s)
    assert "decision_replace_redis_with_nsq" in rep.promoted, rep.blocked
    nodes = s.nodes_by_id()
    assert nodes["decision_use_redis"].status == "superseded"
    assert nodes["decision_replace_redis_with_nsq"].status == "active"


def test_promoted_node_clears_proposed_links(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_active_decision())
    s.write_node(_draft_decision("decision_clean", "Adopt NSQ for fanout",
                                 [{"type": "builds_on", "to": "decision_use_redis"}]))
    rep = distill(s)
    assert "decision_clean" in rep.promoted
    assert s.nodes_by_id()["decision_clean"].proposed_links == []


if __name__ == "__main__":
    import tempfile, pathlib
    passed = 0
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                with tempfile.TemporaryDirectory() as d:
                    fn(pathlib.Path(d))
                print(f"  ok  {name}")
                passed += 1
            except Exception as e:
                print(f"FAIL  {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed.")
    if failed:
        sys.exit(1)
