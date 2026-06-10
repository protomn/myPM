"""Tests for Vertical Slice #1.

Runnable with `pytest tests/` or directly with `python tests/test_slice.py`.
Covers the happy path (observation -> draft -> active -> recalled) and the parts
that must FAIL: the gates have to actually gate, and illegal edges must be rejected.
"""

import argparse
import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mypm.store import Store
from mypm.models import Node, Observation
from mypm import reflect, distill, retrieve, validator, constraints
from mypm.cli import cmd_init, cmd_migrate


@contextlib.contextmanager
def _chdir(path):
    orig = os.getcwd()
    try:
        os.chdir(str(path))
        yield
    finally:
        os.chdir(orig)


def _seed(root):
    s = Store(root)
    s.ensure_layout()
    s.write_node(Node(
        id="decision_stack_buffers", type="decision",
        title="Use reused stack buffers", scope="project:binary_serializer",
        status="active", body="Reuse a per-thread stack buffer.",
        tags=["performance"],
        fields={"context": "hot path allocated per call", "choice": "reuse stack buffer",
                "alternatives": ["arena", "pool"], "rationale": "least machinery",
                "consequences": "buffer sizing is a tuning knob"},
    ))
    return s


def _capture_allocator(s, **over):
    proposed = {
        "type": "lesson", "slug": "allocator overhead",
        "tags": ["performance", "allocation", "latency"],
        "fields": {"trigger": "serialization optimization",
                   "root_cause": "allocator cost dominated runtime",
                   "takeaway": "benchmark allocations before optimizing hot paths"},
        "links": [{"type": "motivates", "to": "decision_stack_buffers"}],
    }
    proposed.update(over)
    s.write_observation(Observation(
        id="obs_allocator", text="allocator overhead dominates serializer hot path",
        source="benchmark", project="binary_serializer", proposed=proposed))


def test_full_slice(tmp_path):
    s = _seed(str(tmp_path / "knowledge"))
    _capture_allocator(s)

    # Gate 1
    results = reflect(s)
    assert results[0].admitted
    assert results[0].node_id == "lesson_allocator_overhead"
    lesson = s.nodes_by_id()["lesson_allocator_overhead"]
    assert lesson.status == "draft"
    assert lesson.title == "allocator overhead dominates serializer hot path"

    # Gate 2 + edge + index
    rep = distill(s)
    assert "lesson_allocator_overhead" in rep.promoted
    assert "lesson_allocator_overhead--motivates--decision_stack_buffers" in rep.edges_created
    assert os.path.exists(rep.index_path) #type: ignore
    assert s.nodes_by_id()["lesson_allocator_overhead"].status == "active"

    # build pass clean
    errors, _ = validator.validate_all(s)
    assert errors == []

    # Recall
    bundle = retrieve(s, "how do I optimize the serializer hot path", project="binary_serializer")
    ids = [n["id"] for n in bundle.nodes]
    assert "lesson_allocator_overhead" in ids


def test_expansion_is_via_edge(tmp_path):
    s = _seed(str(tmp_path / "knowledge"))
    _capture_allocator(s)
    reflect(s); distill(s)
    # 'dominates'/'benchmark' exist only on the Lesson -> Decision can't seed
    bundle = retrieve(s, "what dominates the benchmark", project="binary_serializer")
    why = {n["id"]: n["why_included"] for n in bundle.nodes}
    assert "motivates" in why["decision_stack_buffers"]


def test_gate2_blocks_unlinked(tmp_path):
    s = _seed(str(tmp_path / "knowledge"))
    _capture_allocator(s, links=[])      # fully substantiated but unlinked
    reflect(s)
    rep = distill(s)
    assert rep.promoted == []
    assert any("linked" in r for _, reasons in rep.blocked for r in reasons)


def test_gate2_blocks_unsubstantiated(tmp_path):
    s = _seed(str(tmp_path / "knowledge"))
    # has a takeaway (passes Gate 1) but no root_cause (fails Gate 2)
    _capture_allocator(s, fields={"takeaway": "benchmark first"})
    res = reflect(s)
    assert res[0].admitted                 # Gate 1 lets it in as a draft
    rep = distill(s)
    assert rep.promoted == []              # Gate 2 holds it back
    assert any("substantiated" in r for _, reasons in rep.blocked for r in reasons)


def test_project_node_location(tmp_path):
    root = str(tmp_path / "knowledge")
    s = Store(root)
    s.ensure_layout()
    project_node = Node(
        id="project_mypm",
        type="project",
        title="myPM",
        scope="project:mypm",
        status="active",
        body="Engineering knowledge OS.",
        fields={
            "name": "myPM",
            "description": "Engineering knowledge OS.",
            "stack": ["python"],
            "repos": [],
            "lifecycle": "active",
        },
    )
    path = s.write_node(project_node)
    # lands at projects/mypm/project.md, not projects/mypm/nodes/project_mypm.md
    assert path.endswith(os.path.join("projects", "mypm", "project.md"))
    # visible to iter_node_paths
    assert path in list(s.iter_node_paths())
    # scope_from_path correct
    assert s.scope_from_path(path) == "project:mypm"
    # roundtrip
    loaded = s.load_node(path)
    assert loaded.id == "project_mypm"
    assert loaded.type == "project"
    assert loaded.scope == "project:mypm"


def test_init_creates_layout(tmp_path):
    (tmp_path / ".gitignore").write_text("")
    args = argparse.Namespace(root="knowledge", project="myrepo", name=None, description=None)
    with _chdir(tmp_path):
        cmd_init(args)
    # directory tree
    assert (tmp_path / "knowledge" / "inbox").is_dir()
    assert (tmp_path / "knowledge" / "global" / "nodes").is_dir()
    assert (tmp_path / "knowledge" / "projects" / "myrepo" / "nodes").is_dir()
    assert (tmp_path / "knowledge" / "edges").is_dir()
    # project node at canonical location
    proj = tmp_path / "knowledge" / "projects" / "myrepo" / "project.md"
    assert proj.exists()
    text = proj.read_text()
    assert "id: project_myrepo" in text
    assert "type: project" in text
    # .gitignore updated
    assert "knowledge/.index/" in (tmp_path / ".gitignore").read_text()
    # .claude/ populated
    assert (tmp_path / ".claude" / "CLAUDE.md").exists()
    assert (tmp_path / ".claude" / "council.md").exists()
    assert (tmp_path / ".claude" / "agents" / "reflection-analyst.md").exists()
    assert (tmp_path / ".claude" / "architecture" / "storage.md").exists()


def test_init_idempotent(tmp_path):
    args = argparse.Namespace(root="knowledge", project="myrepo", name=None, description=None)
    with _chdir(tmp_path):
        cmd_init(args)
        mtime = (tmp_path / ".claude" / "CLAUDE.md").stat().st_mtime
        cmd_init(args)
    # .claude files must not be overwritten on second run
    assert (tmp_path / ".claude" / "CLAUDE.md").stat().st_mtime == mtime
    # .gitignore entry must not be duplicated
    gi = (tmp_path / ".gitignore").read_text()
    assert gi.count("knowledge/.index/") == 1


def test_migrate_renames_root(tmp_path):
    (tmp_path / "memory" / "inbox").mkdir(parents=True)
    (tmp_path / "memory" / "global" / "nodes").mkdir(parents=True)
    (tmp_path / ".gitignore").write_text("memory/.index/\n")
    args = argparse.Namespace(root="knowledge", dry_run=False)
    with _chdir(tmp_path):
        cmd_migrate(args)
    assert not (tmp_path / "memory").exists()
    assert (tmp_path / "knowledge" / "inbox").is_dir()
    gi = (tmp_path / ".gitignore").read_text()
    assert "knowledge/.index/" in gi
    assert "memory/.index/" not in gi


def test_migrate_dry_run(tmp_path):
    (tmp_path / "memory" / "inbox").mkdir(parents=True)
    (tmp_path / ".gitignore").write_text("memory/.index/\n")
    args = argparse.Namespace(root="knowledge", dry_run=True)
    with _chdir(tmp_path):
        cmd_migrate(args)
    # nothing should have been renamed
    assert (tmp_path / "memory").exists()
    assert not (tmp_path / "knowledge").exists()
    # .gitignore unchanged
    assert "memory/.index/" in (tmp_path / ".gitignore").read_text()


def test_migrate_already_done(tmp_path):
    (tmp_path / "knowledge" / "inbox").mkdir(parents=True)
    args = argparse.Namespace(root="knowledge", dry_run=False)
    with _chdir(tmp_path):
        cmd_migrate(args)  # must not raise or corrupt
    assert (tmp_path / "knowledge" / "inbox").is_dir()


def test_illegal_edge_rejected():
    # preference -> component is explicitly forbidden by relationships.md
    ok, _ = constraints.is_legal_edge("motivates", "preference", "component")
    assert not ok
    ok, _ = constraints.is_legal_edge("motivates", "lesson", "decision")
    assert ok


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