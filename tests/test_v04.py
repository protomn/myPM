"""Tests for the v0.4 hardening pass: root discovery, the first-session traps
(auto-link, approve --link, decision typing, slug collisions), bulk approve,
orient, multi-root recall, and recall telemetry.

Runnable with `python tests/test_v04.py`.
"""

import io
import json
import os
import sys
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MYPM_NO_SEMANTIC", "1")
os.environ.setdefault("MYPM_NO_LLM", "1")
os.environ.pop("MYPM_ROOT", None)
os.environ.pop("MYPM_GLOBAL_ROOT", None)

from mypm import review, metrics, observe
from mypm.store import Store, find_root, looks_like_root
from mypm.models import Node, Observation
from mypm.proposer import RuleProposer
from mypm.reflect import reflect
from mypm.retriever import retrieve, orient, render_text
from mypm import cli


def _store(tmp_path, name="knowledge"):
    s = Store(str(tmp_path / name))
    s.ensure_layout()
    return s


def _project(s, pid="svc"):
    s.write_node(Node(id=f"project_{pid}", type="project", title=pid,
                      scope=f"project:{pid}", status="active",
                      fields={"name": pid, "description": "test"}))


@contextlib.contextmanager
def _cwd(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _main(argv):
    """Run the CLI, capturing stdout; returns (exit_code, output)."""
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            cli.main(argv)
    except SystemExit as e:
        code = e.code or 0
    return code, buf.getvalue()


# ---- root discovery ----------------------------------------------------------

def test_find_root_walks_up(tmp_path):
    _store(tmp_path)
    deep = tmp_path / "src" / "deep"
    deep.mkdir(parents=True)
    assert find_root(str(deep)) == str(tmp_path / "knowledge")


def test_find_root_returns_none_when_absent(tmp_path):
    assert find_root(str(tmp_path)) is None
    assert not looks_like_root(str(tmp_path))


def test_read_command_never_creates_a_root(tmp_path):
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    with _cwd(deep):
        code, out = _main(["review", "list"])
    assert code == 1
    assert "no knowledge root found" in out
    assert not (deep / "knowledge").exists()        # the old littering bug


def test_retrieve_from_subdir_finds_the_graph(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(id="lesson_x", type="lesson", title="queue polling burned cpu",
                      scope="project:svc", status="active",
                      fields={"takeaway": "t", "root_cause": "r"}))
    deep = tmp_path / "src" / "deep"
    deep.mkdir(parents=True)
    with _cwd(deep):
        code, out = _main(["retrieve", "--task", "queue polling cpu",
                           "--project", "svc"])
    assert code == 0
    assert "lesson_x" in out


# ---- the first-session traps ---------------------------------------------------

def test_capture_autolinks_to_project_node(tmp_path):
    s = _store(tmp_path)
    _project(s)
    with _cwd(tmp_path):
        code, _ = _main(["capture", "--text",
                         "switched to long-poll; cpu idle dropped 40 percent",
                         "--project", "svc", "--type", "lesson",
                         "--takeaway", "long-poll wins",
                         "--root-cause", "busy-wait"])
    assert code == 0
    (obs, _path), = s.all_observations()
    assert obs.proposed["links"] == [{"type": "relates_to", "to": "project_svc",
                                      "note": "captured into this project"}]
    reflect(s)
    from mypm.distill import distill
    rep = distill(s)
    assert rep.promoted, rep.blocked       # capture->reflect->distill end to end


def test_cli_approve_passes_links(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(id="lesson_unlinked", type="lesson", title="t",
                      scope="project:svc", status="draft",
                      fields={"takeaway": "t", "root_cause": "r"}))
    with _cwd(tmp_path):
        code, out = _main(["review", "approve", "lesson_unlinked",
                           "--link", "relates_to:project_svc"])
    assert code == 0, out
    assert s.nodes_by_id()["lesson_unlinked"].status == "active"


def test_blocked_approve_prints_fix_hint(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(id="lesson_bare", type="lesson", title="t",
                      scope="project:svc", status="draft",
                      fields={"takeaway": "t"}))      # no root_cause, no link
    with _cwd(tmp_path):
        code, out = _main(["review", "approve", "lesson_bare"])
    assert code == 1
    assert "fix: mypm review approve lesson_bare" in out
    assert "--field root_cause=" in out
    assert "--link relates_to:project_svc" in out


def test_rule_proposer_types_decisions(tmp_path):
    p = RuleProposer().propose(Observation(
        id="o", text="we will use SQS instead of Kafka because ops burden",
        source="conversation", proposed={"type": "decision"}))
    assert p["fields"]["choice"] == "we will use SQS instead of Kafka"
    assert p["fields"]["rationale"] == "ops burden"


def test_rule_proposer_types_preferences(tmp_path):
    p = RuleProposer().propose(Observation(
        id="o", text="always run the full suite before packaging",
        source="conversation", proposed={"type": "preference"}))
    assert p["fields"]["statement"]
    assert p["fields"]["strength"] == "default"


def test_slug_collision_suffixes_when_content_differs(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_observation(Observation(
        id="obs_1", text="fix race condition in the scheduler queue draining logic",
        source="incident", project="svc", proposed={"type": "lesson"}))
    s.write_observation(Observation(
        id="obs_2", text="fix race condition in the scheduler queue startup handshake",
        source="incident", project="svc", proposed={"type": "lesson"}))
    results = reflect(s)
    assert all(r.admitted for r in results), [r.reasons for r in results]
    ids = {r.node_id for r in results}
    assert len(ids) == 2                       # no false-redundancy hold


def test_identical_recapture_still_held_as_redundant(tmp_path):
    s = _store(tmp_path)
    _project(s)
    text = "fix race condition in the scheduler queue draining logic"
    s.write_observation(Observation(id="obs_1", text=text, source="incident",
                                    project="svc", proposed={"type": "lesson"}))
    assert reflect(s)[0].admitted
    s.write_observation(Observation(id="obs_2", text=text, source="incident",
                                    project="svc", proposed={"type": "lesson"}))
    r2 = reflect(s)[0]
    assert not r2.admitted
    assert any("non-redundant" in x for x in r2.reasons if x.startswith("FAIL"))


def test_capture_coerces_list_fields_at_reflect(tmp_path):
    """Found by dogfooding: `--field alternatives="a; b"` reached the node as a
    string because only review coerced; reflect must apply the same rule."""
    s = _store(tmp_path)
    _project(s)
    s.write_observation(Observation(
        id="obs_d", text="we will use SQS because ops", source="conversation",
        project="svc",
        proposed={"type": "decision",
                  "fields": {"choice": "sqs", "rationale": "ops",
                             "alternatives": "kafka; rabbitmq"}}))
    (r,) = reflect(s)
    assert r.admitted
    node = s.nodes_by_id()[r.node_id]
    assert node.fields["alternatives"] == ["kafka", "rabbitmq"]


# ---- review: filters + bulk approve ---------------------------------------------

def test_pending_filters(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(id="lesson_a", type="lesson", title="a", scope="project:svc",
                      status="draft", source={"type": "pr"},
                      fields={"takeaway": "t"}))
    s.write_node(Node(id="decision_b", type="decision", title="b", scope="project:svc",
                      status="draft", source={"type": "commit"},
                      fields={"choice": "c", "rationale": "r"}))
    assert [d.node_id for d in review.pending(s, type="lesson")] == ["lesson_a"]
    assert [d.node_id for d in review.pending(s, source="commit")] == ["decision_b"]
    assert len(review.pending(s, project="svc")) == 2
    assert review.pending(s, project="other") == []


def test_approve_ready_bulk(tmp_path):
    s = _store(tmp_path)
    _project(s)
    links = [{"type": "relates_to", "to": "project_svc"}]
    s.write_node(Node(id="lesson_done", type="lesson", title="complete",
                      scope="project:svc", status="draft",
                      fields={"takeaway": "t", "root_cause": "r"},
                      proposed_links=links))
    s.write_node(Node(id="lesson_gap", type="lesson", title="incomplete",
                      scope="project:svc", status="draft",
                      fields={"takeaway": "t"}, proposed_links=links))
    promoted, skipped = review.approve_ready(s)
    assert promoted == ["lesson_done"]
    assert [nid for nid, _ in skipped] == ["lesson_gap"]
    assert s.nodes_by_id()["lesson_done"].status == "active"
    assert s.nodes_by_id()["lesson_gap"].status == "draft"


# ---- orient + render_text -------------------------------------------------------

def test_orient_lists_top_knowledge_and_crib(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(id="decision_q", type="decision", title="use sqs for fanout",
                      scope="project:svc", status="active",
                      fields={"context": "x", "choice": "sqs",
                              "alternatives": ["kafka"], "rationale": "ops",
                              "consequences": "aws"}))
    text = orient(s)
    assert "decision_q" in text
    assert "mypm retrieve" in text
    assert "project `svc`" in text


def test_orient_empty_graph_is_silent(tmp_path):
    s = _store(tmp_path)
    assert orient(s) == ""


def test_render_text_mentions_nodes(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(id="lesson_x", type="lesson", title="queue polling burned cpu",
                      scope="project:svc", status="active",
                      fields={"takeaway": "t", "root_cause": "r"}))
    b = retrieve(s, "queue polling cpu", project="svc")
    out = render_text(b)
    assert "lesson_x" in out and "task:" in out


# ---- multi-root recall ------------------------------------------------------------

def test_global_root_patterns_recalled_but_foreign_projects_not(tmp_path):
    local = _store(tmp_path, "knowledge")
    _project(local, "svc")
    g = _store(tmp_path, "shared")
    g.write_node(Node(id="pattern_pool", type="pattern",
                      title="pool connections before tuning queue latency",
                      scope="global", status="active",
                      fields={"applicability": "any service",
                              "solution": "pool"}))
    g.write_node(Node(id="lesson_foreign", type="lesson",
                      title="queue latency lesson from another repo",
                      scope="project:other", status="active",
                      fields={"takeaway": "t", "root_cause": "r"}))
    b = retrieve(local, "queue latency pooling", project="svc", global_store=g)
    ids = [n["id"] for n in b.nodes]
    assert "pattern_pool" in ids               # the commons travels
    assert "lesson_foreign" not in ids         # other repos' scopes do not


def test_local_node_wins_id_collision_with_global(tmp_path):
    local = _store(tmp_path, "knowledge")
    g = _store(tmp_path, "shared")
    for st, body in ((local, "local reading"), (g, "global reading")):
        st.write_node(Node(id="pattern_x", type="pattern",
                           title="retry with backoff on queue errors",
                           scope="global", status="active", body=body,
                           fields={"applicability": "a", "solution": "s"}))
    b = retrieve(local, "retry backoff queue", global_store=g)
    entry = next(n for n in b.nodes if n["id"] == "pattern_x")
    assert entry["summary"] == "local reading"


# ---- recall telemetry ----------------------------------------------------------

def test_bundle_feedback_and_citation_loop(tmp_path):
    s = _store(tmp_path)
    _project(s)
    s.write_node(Node(id="lesson_cited", type="lesson", title="queue polling burned cpu",
                      scope="project:svc", status="active",
                      fields={"takeaway": "t", "root_cause": "r"}))
    b = retrieve(s, "queue polling cpu", project="svc")
    metrics.log_bundle(s, b)
    assert metrics.log_feedback(s, "good") == "queue polling cpu"

    # a transcript that names the recalled node -> citation detected
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text",
                                 "text": "per lesson_cited, avoid polling."}]}}) + "\n")
    observe.observe(s, str(transcript), session="abc")
    observe.observe(s, str(transcript), session="abc")   # idempotent re-scan

    r = metrics.recall_stats(s)
    assert r["bundles"] == 1
    assert r["win_rate"] == 1.0
    assert r["bundles_cited"] == 1
    cited = [e for e in metrics.read_recall_events(s) if e["event"] == "cited"]
    assert len(cited) == 1                     # not inflated by the re-scan


def test_feedback_with_no_bundle(tmp_path):
    s = _store(tmp_path)
    assert metrics.log_feedback(s, "good") is None


# ---- validate aggregation -------------------------------------------------------

def test_duplicate_warnings_capped_per_node(tmp_path):
    from mypm.validator import validate_duplicates, DUP_REPORTS_PER_NODE
    nodes = [Node(id=f"lesson_dup_{i}", type="lesson",
                  title="queue retry backoff lesson repeated verbatim",
                  scope="project:svc", status="active",
                  body="queue retry backoff jitter saturation finding",
                  fields={"takeaway": "queue retry backoff jitter",
                          "root_cause": "saturation"})
             for i in range(8)]
    issues = validate_duplicates(nodes)
    assert issues, "identical nodes must still be flagged"
    per_node = {}
    for i in issues:
        per_node[i.where] = per_node.get(i.where, 0) + 1
    assert max(per_node.values()) <= DUP_REPORTS_PER_NODE
    assert all(i.kind == "duplicate" for i in issues)


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
                import traceback
                print(f"FAIL  {name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed.")
    if failed:
        sys.exit(1)
