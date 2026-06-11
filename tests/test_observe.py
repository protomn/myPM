"""Tests for the live Observer: mypm-capture block parsing, dedup-filtered
inbox capture, transcript scanning, idempotency, and the council runner's use
of the same contract.

Runnable with `python tests/test_observe.py`.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MYPM_NO_SEMANTIC", "1")
os.environ.setdefault("MYPM_NO_LLM", "1")

from mypm import observe, council, agents
from mypm.store import Store
from mypm.models import Node


BLOCK = """Some reasoning prose before the trailer.

```mypm-capture
type: lesson
title: GC pauses dominated tail latency in the ingest path
project: svc
fields:
  takeaway: watch allocation rate on hot paths
  trigger: p99 latency incident
tags: [gc, latency, ingest]
```
"""


def _store(tmp_path):
    s = Store(str(tmp_path / "knowledge"))
    s.ensure_layout()
    return s


def _project(s, pid="svc"):
    s.write_node(Node(id=f"project_{pid}", type="project", title=pid,
                      scope=f"project:{pid}", status="active",
                      fields={"name": pid, "description": "test"}))


# ---- block parsing -----------------------------------------------------

def test_extract_blocks_finds_wellformed_and_skips_malformed():
    text = BLOCK + """
```mypm-capture
type: decision
title: Use NSQ
fields: {choice: NSQ, rationale: simpler ops}
```

```mypm-capture
:[ this is not yaml at all }{
```
"""
    blocks = observe.extract_blocks(text)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "lesson"
    assert blocks[1]["title"] == "Use NSQ"


def test_extract_blocks_empty_text():
    assert observe.extract_blocks("") == []
    assert observe.extract_blocks(None) == []


# ---- capture_blocks ------------------------------------------------------

def test_capture_writes_observation_with_provenance(tmp_path):
    s = _store(tmp_path)
    _project(s)
    results = observe.capture_blocks(s, BLOCK, agent="reflection",
                                     session="abcdef1234")
    assert len(results) == 1 and results[0].status == "captured"
    obs, _ = s.all_observations()[0]
    assert obs.proposed["type"] == "lesson"
    assert obs.proposed["fields"]["takeaway"]
    assert "from-observer" in obs.proposed["tags"]
    assert "agent reflection" in obs.proposed["body"]
    assert "session abcdef12" in obs.proposed["body"]
    # anchored to the project node so Gate 2's linked test can pass
    assert obs.proposed["links"][0]["to"] == "project_svc"


def test_capture_without_project_node_has_no_link(tmp_path):
    s = _store(tmp_path)                       # no project node written
    results = observe.capture_blocks(s, BLOCK)
    assert results[0].status == "captured"
    obs, _ = s.all_observations()[0]
    assert obs.proposed["links"] == []


def test_capture_is_idempotent(tmp_path):
    """The same block re-scanned (Stop hook firing repeatedly) rewrites the
    same file — content-addressed ids, no inbox multiplication."""
    s = _store(tmp_path)
    _project(s)
    observe.capture_blocks(s, BLOCK)
    observe.capture_blocks(s, BLOCK + "\nmore prose\n")
    assert len(s.all_observations()) == 1


def test_capture_deduped_against_existing_graph_node(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(
        id="lesson_gc_tail", type="lesson",
        title="GC pauses dominated tail latency in the ingest path",
        scope="project:svc", status="active",
        body="GC pauses dominated tail latency in the ingest path",
        fields={"takeaway": "watch allocation rate on hot paths",
                "trigger": "p99 latency incident",
                "root_cause": "alloc storm"}))
    results = observe.capture_blocks(s, BLOCK)
    assert results[0].status == "duplicate"
    assert "lesson_gc_tail" in results[0].reason
    assert s.all_observations() == []


def test_invalid_type_and_missing_title_rejected(tmp_path):
    s = _store(tmp_path)
    text = """```mypm-capture
type: epiphany
title: not a real type
```

```mypm-capture
type: lesson
fields: {takeaway: no title given}
```
"""
    results = observe.capture_blocks(s, text)
    assert [r.status for r in results] == ["invalid", "invalid"]
    assert s.all_observations() == []


# ---- transcript scanning ---------------------------------------------------

def _write_transcript(path, *messages):
    """messages: (role, text) tuples in Claude Code JSONL shape."""
    with open(path, "w") as f:
        for role, text in messages:
            f.write(json.dumps({
                "type": role,
                "message": {"content": [{"type": "text", "text": text}]},
            }) + "\n")
        f.write("not json at all\n")          # defensive-parsing check


def test_observe_scans_assistant_messages_only(tmp_path):
    s = _store(tmp_path)
    _project(s)
    transcript = str(tmp_path / "session.jsonl")
    _write_transcript(
        transcript,
        ("user", BLOCK),                       # user text must NOT be captured
        ("assistant", "thinking out loud, no trailer"),
        ("assistant", BLOCK),
    )
    results = observe.observe(s, transcript, session="deadbeef")
    captured = [r for r in results if r.status == "captured"]
    assert len(captured) == 1
    assert len(s.all_observations()) == 1


def test_observe_missing_transcript_is_noop(tmp_path):
    s = _store(tmp_path)
    assert observe.observe(s, str(tmp_path / "nope.jsonl")) == []


# ---- council runner shares the contract -------------------------------------

class _TrailerClient:
    def complete(self, system, user, max_tokens=12000):
        return "My principal-engineer reasoning.\n\n" + BLOCK


def test_run_agent_captures_trailer_blocks(tmp_path):
    s = _store(tmp_path)
    _project(s)
    turn = council.run_agent(s, "principal", "pick a queue", project="svc",
                             client=_TrailerClient())
    assert turn.captured and turn.captured[0].status == "captured"
    obs, _ = s.all_observations()[0]
    assert "agent principal" in obs.proposed["body"]
    assert obs.source == "council"


def test_guardrails_mention_capture_contract():
    assert "mypm-capture" in council._GUARDRAILS


# ---- doctrines are valid for both runtimes ----------------------------------

def test_doctrines_have_subagent_frontmatter_and_strip_cleanly():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for a in agents.AGENTS.values():
        path = os.path.join(here, "mypm", "templates", "agents", a.doctrine)
        with open(path) as f:
            text = f.read()
        meta, body = Store.parse_frontmatter(text)
        assert meta.get("name"), f"{a.doctrine}: missing frontmatter name"
        assert meta.get("description"), f"{a.doctrine}: missing description"
        assert "mypm-capture" in body, f"{a.doctrine}: missing capture contract"
        assert f"--agent {a.name}" in body, f"{a.doctrine}: recall cmd missing"
        assert not body.startswith("---"), f"{a.doctrine}: frontmatter not stripped"


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
