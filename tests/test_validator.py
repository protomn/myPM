"""Tests for the validator improvements: near-duplicate detection and scope
drift warnings. Runnable with `python tests/test_validator.py`.

These are warnings, never errors — they inform human judgment and must not block
the distill build gate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mypm import validator
from mypm.store import Store
from mypm.models import Node, Edge, make_edge_id


def _lesson(node_id, title, body, scope="global"):
    return Node(id=node_id, type="lesson", title=title, scope=scope, status="active",
                body=body, fields={"trigger": body, "root_cause": body, "takeaway": body})


def _warnings(store):
    _, warnings = validator.validate_all(store)
    return [str(w) for w in warnings]


def test_near_duplicate_flagged(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_lesson("lesson_alloc_overhead_a",
        "allocator overhead dominates serializer hot path",
        "allocator overhead dominated the serializer hot path under load"))
    s.write_node(_lesson("lesson_alloc_overhead_b",
        "allocator overhead dominates the serializer hot path",
        "the serializer hot path was dominated by allocator overhead under load"))
    warns = _warnings(s)
    assert any("near-duplicate" in w for w in warns), warns


def test_distinct_nodes_not_flagged(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_lesson("lesson_alloc_overhead",
        "allocator overhead dominates serializer hot path",
        "stack buffers cut allocation cost in the serializer"))
    s.write_node(_lesson("lesson_retry_storm",
        "unbounded retries caused a thundering herd",
        "exponential backoff and jitter prevented the herd from reforming"))
    assert not any("near-duplicate" in w for w in _warnings(s))


def test_duplicate_is_warning_not_error(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_lesson("lesson_dup_a", "same finding here",
                         "the same finding restated almost identically here now"))
    s.write_node(_lesson("lesson_dup_b", "same finding here",
                         "the same finding restated almost identically here too"))
    errors, warnings = validator.validate_all(s)
    assert errors == []
    assert any("near-duplicate" in str(w) for w in warnings)


def test_cross_project_edge_flagged(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(_lesson("lesson_a_finding", "finding in project a",
                         "a distinct finding about caching", scope="project:alpha"))
    s.write_node(_lesson("lesson_b_finding", "finding in project b",
                         "an unrelated finding about logging", scope="project:beta"))
    eid = make_edge_id("lesson_a_finding", "relates_to", "lesson_b_finding")
    s.write_edge(Edge(id=eid, type="relates_to",
                      from_id="lesson_a_finding", to_id="lesson_b_finding"))
    assert any("cross-project edge" in w for w in _warnings(s)), _warnings(s)


def test_global_node_naming_project_flagged(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    # register a project scope via a project-scoped node
    s.write_node(_lesson("lesson_local", "local finding",
                         "local detail", scope="project:binary_serializer"))
    # a global node that names that project
    s.write_node(_lesson("lesson_global_drift", "general caching lesson",
                         "this was learned while working on binary_serializer specifically"))
    assert any("names project 'binary_serializer'" in w for w in _warnings(s)), _warnings(s)


if __name__ == "__main__":
    import tempfile, pathlib
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                fn(pathlib.Path(d))
            print(f"  ok  {name}")
            passed += 1
    print(f"\n{passed} tests passed.")
