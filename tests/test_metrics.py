"""Tests for review telemetry (mypm metrics) — the time-to-approve metric.

Runnable with `python tests/test_metrics.py`.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MYPM_NO_SEMANTIC", "1")
os.environ.setdefault("MYPM_NO_LLM", "1")

from mypm import metrics, review
from mypm.store import Store
from mypm.models import Node


def _store(tmp_path):
    s = Store(str(tmp_path / "knowledge"))
    s.ensure_layout()
    return s


def _project(s, pid="svc"):
    s.write_node(Node(id=f"project_{pid}", type="project", title=pid,
                      scope=f"project:{pid}", status="active",
                      fields={"name": pid, "description": "test"}))


def _draft_lesson(s, nid="lesson_gc_pauses"):
    s.write_node(Node(
        id=nid, type="lesson", title="GC pauses dominated tail latency",
        scope="project:svc", status="draft",
        body="p99 spikes traced to GC",
        fields={"takeaway": "watch allocation rate on hot paths",
                "trigger": "p99 latency incident"},
        proposed_links=[{"type": "relates_to", "to": "project_svc"}],
    ))


# ---- event logging -----------------------------------------------------------

def test_fill_and_approve_log_events(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    review.fill(s, "lesson_gc_pauses", fields={"root_cause": "alloc storm"})
    ok, reasons, _ = review.approve(s, "lesson_gc_pauses")
    assert ok, reasons
    events = metrics.read_events(s)
    assert [e["event"] for e in events] == ["fill", "approve"]
    assert events[0]["fields"] == ["root_cause"]
    assert events[1]["filled_before"] is True
    assert events[1]["fields_typed"] == []      # human typed nothing


def test_bare_approve_logs_unfilled_with_typed_fields(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    ok, _, _ = review.approve(s, "lesson_gc_pauses",
                              fields={"root_cause": "alloc storm"})
    assert ok
    (e,) = metrics.read_events(s)
    assert e["event"] == "approve" and e["ok"] is True
    assert e["filled_before"] is False
    assert e["fields_typed"] == ["root_cause"]


def test_blocked_approve_logs_ok_false(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    ok, _, _ = review.approve(s, "lesson_gc_pauses")    # root_cause missing
    assert not ok
    (e,) = metrics.read_events(s)
    assert e["event"] == "approve" and e["ok"] is False


def test_reject_and_supersede_log_their_own_verbs(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    review.reject(s, "lesson_gc_pauses")
    s.write_node(Node(
        id="decision_old", type="decision", title="Use Redis",
        scope="project:svc", status="active",
        fields={"context": "queues", "choice": "redis",
                "alternatives": ["rabbitmq"], "rationale": "familiar",
                "consequences": "redis dep"}))
    s.write_node(Node(
        id="decision_new", type="decision", title="Replace Redis with NSQ",
        scope="project:svc", status="draft",
        fields={"choice": "NSQ", "rationale": "lost messages"}))
    ok, reasons, _ = review.supersede(
        s, "decision_new", "decision_old",
        fields={"alternatives": "keep redis", "consequences": "migration"})
    assert ok, reasons
    verbs = [e["event"] for e in metrics.read_events(s)]
    assert verbs == ["reject", "supersede"]


# ---- stats ---------------------------------------------------------------------

def test_stats_pairs_shown_with_decision(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    metrics.log_event(s, "shown", "lesson_gc_pauses")
    ok, _, _ = review.approve(s, "lesson_gc_pauses",
                              fields={"root_cause": "alloc storm"})
    assert ok
    report = metrics.stats(s)
    assert report["decisions"] == 1
    c = report["unfilled"]
    assert c["n"] == 1 and c["timed"] == 1
    assert c["median_s"] is not None and c["median_s"] >= 0
    assert c["mean_fields_typed"] == 1.0


def test_stats_splits_cohorts_by_fill(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s, "lesson_a")
    _draft_lesson(s, "lesson_b")
    review.fill(s, "lesson_a", fields={"root_cause": "x"})
    assert review.approve(s, "lesson_a")[0]
    assert review.approve(s, "lesson_b", fields={"root_cause": "y"})[0]
    report = metrics.stats(s)
    assert report["filled"]["n"] == 1
    assert report["unfilled"]["n"] == 1
    assert report["by_verb"] == {"approve": 2}


def test_stats_ignores_unpaired_and_stale_shown(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    # a shown event from an abandoned session, far outside the pairing window
    metrics.log_event(s, "shown", "lesson_gc_pauses")
    path = metrics.log_path(s)
    with open(path) as f:
        rec = json.loads(f.read())
    rec["ts"] = "2020-01-01T00:00:00+00:00"
    with open(path, "w") as f:
        f.write(json.dumps(rec) + "\n")
    assert review.approve(s, "lesson_gc_pauses",
                          fields={"root_cause": "alloc storm"})[0]
    report = metrics.stats(s)
    assert report["unfilled"]["n"] == 1
    assert report["unfilled"]["timed"] == 0      # stale shown not paired


def test_corrupt_log_line_does_not_kill_stats(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    assert review.approve(s, "lesson_gc_pauses",
                          fields={"root_cause": "alloc storm"})[0]
    with open(metrics.log_path(s), "a") as f:
        f.write("{not json\n")
    report = metrics.stats(s)
    assert report["decisions"] == 1


def test_logging_failure_never_blocks_promotion(tmp_path):
    s = _store(tmp_path)
    _project(s)
    _draft_lesson(s)
    # a FILE where the .metrics dir should be makes every log write fail
    with open(os.path.join(s.root, ".metrics"), "w") as f:
        f.write("in the way")
    ok, reasons, _ = review.approve(s, "lesson_gc_pauses",
                                    fields={"root_cause": "alloc storm"})
    assert ok, reasons
    assert s.nodes_by_id()["lesson_gc_pauses"].status == "active"


def test_stats_empty_log(tmp_path):
    s = _store(tmp_path)
    report = metrics.stats(s)
    assert report["decisions"] == 0
    assert report["filled"]["median_s"] is None


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
