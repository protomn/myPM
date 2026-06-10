"""Tests for the hardening pass: index staleness, malformed-file containment,
field type validation, structural-edge enforcement, and Gate 3 scope counting.

Runnable with `python tests/test_hardening.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MYPM_NO_SEMANTIC", "1")
os.environ.setdefault("MYPM_NO_LLM", "1")

from mypm.store import Store
from mypm.models import Node
from mypm.index import build_index, IndexReader
from mypm.retriever import retrieve
from mypm import validator, constraints
from mypm.distill import _detect_pattern_candidates


def _store(tmp_path):
    s = Store(str(tmp_path / "knowledge"))
    s.ensure_layout()
    return s


def _lesson(nid, title, scope="global", **fields):
    base = {"takeaway": title, "root_cause": "because"}
    base.update(fields)
    return Node(id=nid, type="lesson", title=title, scope=scope,
                status="active", body=title, fields=base)


# ---- index staleness ------------------------------------------------------

def test_stale_index_rebuilds_on_read(tmp_path):
    """Hand-editing a node file (files are the record!) must be visible to the
    next retrieve, not silently served stale."""
    import time
    s = _store(tmp_path)
    s.write_node(_lesson("lesson_gc", "GC pauses hurt latency"))
    build_index(s)

    # hand-edit: a different title, written straight to disk
    node = s.nodes_by_id()["lesson_gc"]
    node.title = "Allocator churn hurt throughput"
    time.sleep(0.01)            # ensure the mtime moves
    s.write_node(node)

    idx = IndexReader(s)        # must notice and rebuild
    row = idx.get_node("lesson_gc")
    idx.close()
    assert row["title"] == "Allocator churn hurt throughput"


def test_fresh_index_not_rebuilt(tmp_path):
    s = _store(tmp_path)
    s.write_node(_lesson("lesson_gc", "GC pauses hurt latency"))
    build_index(s)
    first_mtime = os.stat(s.index_path).st_mtime_ns
    idx = IndexReader(s); idx.close()
    assert os.stat(s.index_path).st_mtime_ns == first_mtime


# ---- malformed file containment --------------------------------------------

def test_unterminated_frontmatter_is_an_error_not_a_crash(tmp_path):
    s = _store(tmp_path)
    s.write_node(_lesson("lesson_ok", "a valid lesson"))
    bad = os.path.join(s.global_dir, "lesson_broken.md")
    with open(bad, "w") as f:
        f.write("---\nid: lesson_broken\ntype: lesson\n")   # no closing ---
    errors, _ = validator.validate_all(s)
    assert any("unparseable" in e.message or "unterminated" in e.message
               for e in errors), [str(e) for e in errors]
    # the valid node still validated (the pass survived the bad file)
    assert not any(e.where == "lesson_ok" for e in errors)


def test_body_dashes_do_not_truncate_frontmatter(tmp_path):
    s = _store(tmp_path)
    n = _lesson("lesson_hr", "lesson with a horizontal rule")
    n.body = "before\n\n---\n\nafter the rule"
    s.write_node(n)
    loaded = s.load_node(n.path)
    assert "after the rule" in loaded.body
    assert loaded.fields["takeaway"]


# ---- field type validation ---------------------------------------------------

def test_string_where_list_belongs_is_flagged(tmp_path):
    s = _store(tmp_path)
    s.write_node(Node(
        id="decision_bad_alts", type="decision", title="Use NSQ",
        scope="global", status="active",
        fields={"context": "x", "choice": "NSQ", "rationale": "y",
                "alternatives": "kafka, rabbitmq",      # string, not list
                "consequences": "z"}))
    _, warnings = validator.validate_all(s)
    assert any("alternatives" in w.message and "list" in w.message
               for w in warnings), [str(w) for w in warnings]


# ---- structural edges ----------------------------------------------------------

def test_belongs_to_can_never_be_materialized():
    ok, reason = constraints.is_legal_edge("belongs_to", "lesson", "project")
    assert not ok
    assert "structural" in reason


# ---- Gate 3 scope counting --------------------------------------------------

def test_global_lesson_does_not_count_as_a_project(tmp_path):
    s = _store(tmp_path)
    n1 = _lesson("lesson_a", "alloc churn in svc A", scope="project:svc_a")
    n2 = _lesson("lesson_b", "alloc churn observed globally", scope="global")
    n1.tags = ["allocation"]; n2.tags = ["allocation"]
    s.write_node(n1); s.write_node(n2)
    assert _detect_pattern_candidates(s) == []     # one project + global != two projects


def test_two_projects_still_propose_a_pattern(tmp_path):
    s = _store(tmp_path)
    n1 = _lesson("lesson_a", "alloc churn in svc A", scope="project:svc_a")
    n2 = _lesson("lesson_b", "alloc churn in svc B", scope="project:svc_b")
    n1.tags = ["allocation"]; n2.tags = ["allocation"]
    s.write_node(n1); s.write_node(n2)
    proposals = _detect_pattern_candidates(s)
    assert len(proposals) == 1
    assert proposals[0]["tag"] == "allocation"


if __name__ == "__main__":
    import tempfile, pathlib
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                if fn.__code__.co_argcount:
                    with tempfile.TemporaryDirectory() as d:
                        fn(pathlib.Path(d))
                else:
                    fn()
                print(f"  ok  {name}")
                passed += 1
            except Exception as e:
                print(f"FAIL  {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed.")
    if failed:
        sys.exit(1)
