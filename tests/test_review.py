"""Tests for the approval surface (mypm review) and the Gate-1 quarantine.

Runnable with `python tests/test_review.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MYPM_NO_SEMANTIC", "1")
os.environ.setdefault("MYPM_NO_LLM", "1")

from mypm import review
from mypm.store import Store
from mypm.models import Node, Observation
from mypm.reflect import reflect
from mypm.retriever import retrieve


def _store(tmp_path):
    s = Store(str(tmp_path / "knowledge"))
    s.ensure_layout()
    return s


def _project(s, pid="svc"):
    s.write_node(Node(id=f"project_{pid}", type="project", title=pid,
                      scope=f"project:{pid}", status="active",
                      fields={"name": pid, "description": "test"}))


def _draft_lesson(s, nid="lesson_gc_pauses", links=None):
    s.write_node(Node(
        id=nid, type="lesson", title="GC pauses dominated tail latency",
        scope="project:svc", status="draft",
        body="p99 spikes traced to GC",
        fields={"takeaway": "watch allocation rate on hot paths",
                "trigger": "p99 latency incident"},
        proposed_links=links if links is not None
        else [{"type": "relates_to", "to": "project_svc"}],
    ))


# ---- pending --------------------------------------------------------------

def test_pending_lists_missing_fields_and_linkage(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    drafts = review.pending(s)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.node_id == "lesson_gc_pauses"
    assert d.missing_fields == ["root_cause"]
    assert d.linked is True


def test_pending_empty_when_no_drafts(tmp_path):
    s = _store(tmp_path)
    _project(s)
    assert review.pending(s) == []


# ---- approve ---------------------------------------------------------------

def test_approve_fills_fields_and_promotes(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    ok, reasons, created = review.approve(
        s, "lesson_gc_pauses", fields={"root_cause": "unbounded per-request allocations"})
    assert ok, reasons
    node = s.nodes_by_id()["lesson_gc_pauses"]
    assert node.status == "active"
    assert node.fields["root_cause"] == "unbounded per-request allocations"
    assert created                          # relates_to edge materialized
    # and it is now recallable
    bundle = retrieve(s, "tail latency gc allocation", project="svc")
    assert any(n["id"] == "lesson_gc_pauses" for n in bundle.nodes)


def test_approve_blocked_still_saves_fields(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s, links=[])              # unlinked -> Gate 2 must block
    ok, reasons, _ = review.approve(
        s, "lesson_gc_pauses", fields={"root_cause": "alloc storm"})
    assert not ok
    node = s.nodes_by_id()["lesson_gc_pauses"]
    assert node.status == "draft"
    assert node.fields["root_cause"] == "alloc storm"   # progress not lost


def test_approve_coerces_list_fields(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(
        id="decision_use_nsq", type="decision", title="Use NSQ for fanout",
        scope="project:svc", status="draft",
        fields={"choice": "NSQ", "rationale": "simpler ops"},
        proposed_links=[{"type": "relates_to", "to": "project_svc"}],
    ))
    ok, reasons, _ = review.approve(
        s, "decision_use_nsq",
        fields={"alternatives": "kafka; rabbitmq", "consequences": "new infra"})
    assert ok, reasons
    node = s.nodes_by_id()["decision_use_nsq"]
    assert node.fields["alternatives"] == ["kafka", "rabbitmq"]


def test_approve_rejects_non_draft(tmp_path):
    s = _store(tmp_path)
    _project(s)
    try:
        review.approve(s, "project_svc")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# ---- reject ----------------------------------------------------------------

def test_reject_removes_draft(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    path = review.reject(s, "lesson_gc_pauses")
    assert not os.path.exists(path)
    assert "lesson_gc_pauses" not in s.nodes_by_id()


# ---- merge -----------------------------------------------------------------

def test_merge_folds_into_target(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(
        id="lesson_alloc", type="lesson", title="Allocation storms hurt p99",
        scope="project:svc", status="active", body="original finding",
        tags=["latency"],
        fields={"takeaway": "bound allocations", "root_cause": "alloc storm"},
    ))
    _draft_lesson(s)                        # restates the same ground
    target = review.merge(s, "lesson_gc_pauses", "lesson_alloc")
    assert target == "lesson_alloc"
    nodes = s.nodes_by_id()
    assert "lesson_gc_pauses" not in nodes
    merged = nodes["lesson_alloc"]
    assert "Merged from draft `lesson_gc_pauses`" in merged.body
    assert merged.fields["trigger"] == "p99 latency incident"   # empty field filled
    assert merged.fields["root_cause"] == "alloc storm"          # existing kept


def test_merge_refuses_type_mismatch(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    try:
        review.merge(s, "lesson_gc_pauses", "project_svc")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# ---- supersede ---------------------------------------------------------------

def test_supersede_promotes_and_retires_old(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(
        id="decision_use_redis", type="decision", title="Use Redis for queues",
        scope="project:svc", status="active",
        fields={"context": "queueing", "choice": "redis",
                "alternatives": ["rabbitmq"], "rationale": "familiar",
                "consequences": "redis dependency"},
    ))
    s.write_node(Node(
        id="decision_replace_redis", type="decision", title="Replace Redis with NSQ",
        scope="project:svc", status="draft",
        fields={"choice": "NSQ", "rationale": "redis queues kept losing messages"},
        proposed_links=[],
    ))
    ok, reasons, created = review.supersede(
        s, "decision_replace_redis", "decision_use_redis",
        fields={"alternatives": "keep redis; kafka", "consequences": "migration work"})
    assert ok, reasons
    nodes = s.nodes_by_id()
    assert nodes["decision_replace_redis"].status == "active"
    assert nodes["decision_use_redis"].status == "superseded"
    assert any("supersedes" in e for e in created)
    # recall resolves to the living head only
    bundle = retrieve(s, "redis queue decision", project="svc")
    ids = [n["id"] for n in bundle.nodes]
    assert "decision_use_redis" not in ids


# ---- quarantine -------------------------------------------------------------

def test_failed_observation_is_quarantined(tmp_path):
    s = _store(tmp_path)
    s.write_observation(Observation(
        id="obs_vague", text="it's so slow", source="conversation"))
    res = reflect(s)
    assert not res[0].admitted
    assert res[0].held_path and os.path.exists(res[0].held_path)
    assert s.all_observations() == []       # gone from the live inbox
    # a second reflect run does not re-process it
    assert reflect(s) == []


def test_retry_held_reenters_the_gate(tmp_path):
    import yaml
    s = _store(tmp_path)
    s.write_observation(Observation(
        id="obs_thin", text="it's so slow", source="conversation"))
    res = reflect(s)
    held = res[0].held_path
    # the engineer fixes the observation in place
    with open(held) as f:
        d = yaml.safe_load(f)
    d["text"] = "serializer hot path is slow because of per-call allocations"
    d["proposed"] = {"type": "lesson",
                     "fields": {"takeaway": "avoid per-call allocations"}}
    with open(held, "w") as f:
        yaml.safe_dump(d, f)
    res2 = reflect(s, retry_held=True)
    assert len(res2) == 1 and res2[0].admitted, res2


if __name__ == "__main__":
    import tempfile, pathlib
    passed = failed = 0
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
