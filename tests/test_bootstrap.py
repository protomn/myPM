"""Tests for mypm bootstrap — candidate extraction, dedup, and inbox writing.

Runnable with `python tests/test_bootstrap.py`. No real git is invoked — the
git seam is stubbed via the `run_git` parameter.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mypm import bootstrap
from mypm.store import Store


# ---- helpers -----------------------------------------------------------

SEP, REC = "\x1f", "\x1e"


def _git_log(*commits):
    """Build a fake git log string from (sha, subject, parents, body) tuples."""
    def _fmt(sha, subj, parents="p1", body=""):
        return f"{sha}{SEP}{subj}{SEP}{parents}{SEP}{body}"
    return REC.join(_fmt(*c) for c in commits) + REC


def _fake_git(log_str):
    return lambda args, cwd=None: log_str


def _run(tmp_path, commits, *, enrich=False, write=False, project=None, proposer=None):
    s = Store(str(tmp_path / "knowledge"))
    s.ensure_layout()
    return bootstrap.bootstrap(
        s, repo_dir=".", limit=100,
        project=project, enrich=enrich, write=write,
        proposer=proposer,
        run_git=_fake_git(_git_log(*commits)),
    )


def _kept(results):
    return [c for c in results if c.status == "kept"]


def _dropped(results):
    return [c for c in results if c.status == "dropped"]


def _duped(results):
    return [c for c in results if c.status == "duplicate"]


# ---- prefilter ---------------------------------------------------------

def test_chore_commits_dropped(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "docs: update README", "p1", ""),
        ("sha2", "chore: bump version", "p1", ""),
        ("sha3", "style: fix formatting", "p1", ""),
        ("sha4", "Fixed formatting issues", "p1", ""),
    ])
    assert all(c.status == "dropped" for c in results)


def test_vague_commits_dropped(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Bug fixes", "p1", ""),
        ("sha2", "minor fixes", "p1", ""),
        ("sha3", "various updates", "p1", ""),
    ])
    assert all(c.status == "dropped" for c in results)


def test_vague_commit_with_body_survives_prefilter(tmp_path):
    # A vague subject is rescued if the body adds specifics
    results = _run(tmp_path, [
        ("sha1", "fixes", "p1", "Rewrote the parser to handle null bytes correctly"),
    ])
    # May still drop for no decision/lesson, but it isn't dropped by vague check
    assert not any(c.reason == "too vague (no specific finding)" for c in results)


def test_thin_commit_dropped(tmp_path):
    results = _run(tmp_path, [("sha1", "ok", "p1", "")])
    assert results[0].status == "dropped"
    assert results[0].reason == "too thin to extract"


# ---- rule typing -------------------------------------------------------

def test_lesson_typing_from_bugfix(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Bug fix: wrong bit mask in float decoder", "p1", ""),
    ])
    assert len(_kept(results)) == 1
    assert _kept(results)[0].proposal["type"] == "lesson"


def test_decision_typing_from_choice_verb(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Switched from libxml2 to expat for parsing", "p1", ""),
    ])
    assert len(_kept(results)) == 1
    p = _kept(results)[0].proposal
    assert p["type"] == "decision"
    assert p["fields"].get("choice")


def test_decision_typing_from_constraint(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Added bounds check on input buffer size", "p1", ""),
    ])
    assert len(_kept(results)) == 1
    assert _kept(results)[0].proposal["type"] == "decision"


def test_action_verbs_dropped(tmp_path):
    # implement/add/create are NOT choice/constraint language
    results = _run(tmp_path, [
        ("sha1", "Implemented FastDecoder pipeline", "p1", ""),
        ("sha2", "Added compression stage to pipeline", "p1", ""),
        ("sha3", "Created the benchmark harness", "p1", ""),
    ])
    assert all(c.status == "dropped" for c in results), \
        [(c.subject, c.reason) for c in results]


def test_github_merge_typed_as_decision(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Merge pull request #7 from me/use-simd", "p1 p2",
         "Use AVX2 SIMD intrinsics for the inner decode loop"),
    ])
    assert len(_kept(results)) == 1
    p = _kept(results)[0].proposal
    assert p["type"] == "decision"
    assert p["source"] == "pr"


def test_squash_merge_typed_as_decision(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Switch to zero-copy buffer strategy (#12)", "p1", ""),
    ])
    assert len(_kept(results)) == 1
    assert _kept(results)[0].proposal["type"] == "decision"


# ---- dedup (recall-as-filter) ------------------------------------------

def test_duplicate_candidate_deduped(tmp_path):
    # Near-identical subjects with same prefix share enough tokens to exceed the
    # 0.6 Jaccard threshold: {bug,fix,wrong,bit,mask,float,decoder} ∩ same+{module} = 7/8
    results = _run(tmp_path, [
        ("sha1", "Bug fix: wrong bit mask in float decoder", "p1", ""),
        ("sha2", "Bug fix: wrong bit mask in float decoder module", "p1", ""),
    ])
    kept = _kept(results)
    duped = _duped(results)
    assert len(kept) == 1
    assert len(duped) == 1


def test_different_type_not_deduped_against_each_other(tmp_path):
    # A lesson and a decision with overlapping words are different types
    results = _run(tmp_path, [
        ("sha1", "Bug fix: wrong bit mask in float decode", "p1", ""),
        ("sha2", "Use bitmask lookup table instead of shift for decode", "p1", ""),
    ])
    kept = _kept(results)
    assert len(kept) == 2


def test_existing_node_prevents_duplicate(tmp_path):
    """A node already in the graph (seeded in store) blocks a near-identical candidate."""
    from mypm.models import Node
    import datetime

    s = Store(str(tmp_path / "knowledge"))
    s.ensure_layout()

    # Write an existing lesson node that covers the same ground
    # Keep the node fields minimal so search_text tokens closely match the
    # commit subject — Jaccard needs to exceed 0.6 between candidate tokens
    # and the stored node's tokens.
    existing = Node(
        id="lesson_bitmask",
        type="lesson",
        title="Bug fix: wrong bit mask in float decoder",
        status="active",
        scope="global",
        fields={"takeaway": "wrong bit mask float decoder"},
        tags=[],
        body="Bug fix: wrong bit mask in float decoder",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
    )
    s.write_node(existing)

    results = bootstrap.bootstrap(
        s, repo_dir=".", limit=100,
        run_git=_fake_git(_git_log(
            ("sha1", "Bug fix: wrong bit mask in float decoder", "p1", ""),
        )),
    )
    assert results[0].status == "duplicate"
    assert "lesson_bitmask" in results[0].reason


# ---- write mode --------------------------------------------------------

def test_write_false_produces_no_files(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Bug fix: null pointer in header parse", "p1", ""),
    ], write=False)
    assert _kept(results)[0].obs_path is None
    inbox = tmp_path / "knowledge" / "inbox"
    assert list(inbox.iterdir()) == []


def test_write_true_creates_observation_file(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Bug fix: null pointer in header parse", "p1", ""),
    ], write=True)
    cand = _kept(results)[0]
    assert cand.obs_path is not None
    assert os.path.exists(cand.obs_path)


def test_written_observation_has_bootstrap_tag(tmp_path):
    _run(tmp_path, [
        ("sha1", "Bug fix: stack overflow in recursive decoder", "p1", ""),
    ], write=True)
    s = Store(str(tmp_path / "knowledge"))
    s.ensure_layout()
    obs_list = s.all_observations()
    assert obs_list
    obs, _ = obs_list[0]
    assert "from-bootstrap" in (obs.proposed.get("tags") or [])


def test_written_observation_has_provenance_in_body(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Used mimalloc instead of system allocator", "p1", ""),
    ], write=True)
    cand = _kept(results)[0]
    import yaml
    with open(cand.obs_path) as f:
        data = yaml.safe_load(f)
    assert "bootstrap from commit" in data["proposed"]["body"]


# ---- supersession-aware dedup ------------------------------------------

def test_supersession_verb_bypasses_dedup(tmp_path):
    # Same tail tokens, different leading verb → Jaccard = 4/6 ≈ 0.67 (above threshold).
    # Without supersession awareness the second commit would be deduped and dropped.
    results = _run(tmp_path, [
        ("sha1", "Use Redis for queue processing backend", "p1", ""),
        ("sha2", "Replace Redis for queue processing backend", "p1", ""),
    ])
    statuses = {c.sha: c.status for c in results}
    assert statuses["sha1"] == "kept"
    assert statuses["sha2"] == "supersession"


def test_supersession_carries_probable_target(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Use Redis for queue processing backend", "p1", ""),
        ("sha2", "Replace Redis for queue processing backend", "p1", ""),
    ])
    sup = next(c for c in results if c.status == "supersession")
    assert sup.proposal.get("supersedes") == "sha1"
    assert "sha1" in sup.reason


def test_adoption_verb_still_deduped_when_similar(tmp_path):
    # Fresh adoption verbs don't get supersession immunity
    results = _run(tmp_path, [
        ("sha1", "Use Redis for the job queue", "p1", ""),
        ("sha2", "Use Redis for the job queue backend", "p1", ""),
    ])
    statuses = [c.status for c in results]
    assert "supersession" not in statuses
    assert "duplicate" in statuses


def test_supersession_written_to_inbox_with_provenance(tmp_path):
    import yaml
    results = _run(tmp_path, [
        ("sha1", "Use Redis for queue processing backend", "p1", ""),
        ("sha2", "Replace Redis for queue processing backend", "p1", ""),
    ], write=True)
    sup = next(c for c in results if c.status == "supersession")
    assert sup.obs_path is not None
    with open(sup.obs_path) as f:
        data = yaml.safe_load(f)
    assert "supersedes" in data["proposed"]["body"]


def test_migrate_verb_is_supersession(tmp_path):
    # "Migrated" matches _SUPERSESSION_RE; same tail tokens → Jaccard = 4/6 ≈ 0.67
    results = _run(tmp_path, [
        ("sha1", "Use Postgres for session store data", "p1", ""),
        ("sha2", "Migrated Postgres for session store data", "p1", ""),
    ])
    statuses = {c.sha: c.status for c in results}
    assert statuses["sha2"] == "supersession"


def test_switch_verb_is_supersession(tmp_path):
    # "Switch" matches _SUPERSESSION_RE; same tail tokens → Jaccard = 4/6 ≈ 0.67
    results = _run(tmp_path, [
        ("sha1", "Use libxml2 for xml parsing library", "p1", ""),
        ("sha2", "Switch libxml2 for xml parsing library", "p1", ""),
    ])
    assert any(c.status == "supersession" for c in results)


def test_supersession_without_prior_is_just_kept(tmp_path):
    # Supersession verb with no similar existing node → ordinary kept decision
    results = _run(tmp_path, [
        ("sha1", "Replace libxml2 with expat for XML parsing", "p1", ""),
    ])
    assert results[0].status == "kept"
    assert results[0].proposal.get("supersedes") is None


# ---- enrich path (LLM proposer stubbed) --------------------------------

class _StubProposer:
    name = "stub"

    def propose(self, obs):
        return {
            "type": "lesson",
            "title": "STUB: " + obs.text[:40],
            "id": None, "slug": None,
            "tags": ["stub"],
            "fields": {"takeaway": "stub takeaway", "trigger": obs.text},
            "links": [],
            "body": obs.text,
            "confidence": "low",
            "source": "commit",
            "ref": "stub",
        }


def test_enrich_calls_proposer_on_novel_candidates(tmp_path):
    results = _run(tmp_path, [
        ("sha1", "Bug fix: incorrect mantissa shift", "p1", ""),
    ], enrich=True, proposer=_StubProposer())
    kept = _kept(results)
    assert len(kept) == 1
    assert kept[0].proposal["title"].startswith("STUB:")


def test_enrich_skips_proposer_on_dropped_commits(tmp_path):
    """Pre-filtered commits must not reach the proposer even with --enrich."""
    called = []

    class _SpyProposer(_StubProposer):
        def propose(self, obs):
            called.append(obs.text)
            return super().propose(obs)

    _run(tmp_path, [
        ("sha1", "chore: bump deps", "p1", ""),
        ("sha2", "docs: update README", "p1", ""),
    ], enrich=True, proposer=_SpyProposer())
    assert called == [], f"proposer was called unexpectedly: {called}"


def test_enrich_skips_proposer_on_duplicates(tmp_path):
    """Deduped candidates must not hit the proposer."""
    called = []

    class _SpyProposer(_StubProposer):
        def propose(self, obs):
            called.append(obs.text)
            return super().propose(obs)

    _run(tmp_path, [
        ("sha1", "Bug fix: wrong mantissa calculation", "p1", ""),
        ("sha2", "Fixed wrong mantissa calculation bug", "p1", ""),
    ], enrich=True, proposer=_SpyProposer())
    assert len(called) == 1, f"proposer called {len(called)} times, expected 1"


# ---- project link + end-to-end recall ----------------------------------

def _make_project(store, pid="ieee"):
    from mypm.models import Node
    proj = Node(id=f"project_{pid}", type="project", title=pid,
                scope=f"project:{pid}", status="active",
                fields={"name": pid, "description": "test project"})
    store.write_node(proj)
    return proj


def test_write_attaches_project_link_when_project_node_exists(tmp_path):
    import yaml
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    _make_project(s, "ieee")
    results = bootstrap.bootstrap(
        s, repo_dir=".", limit=100, project="ieee", write=True,
        run_git=_fake_git(_git_log(
            ("sha1", "Bug fix: wrong sign bit in encoder", "p1", ""),
        )))
    cand = _kept(results)[0]
    with open(cand.obs_path) as f:
        data = yaml.safe_load(f)
    links = data["proposed"]["links"]
    assert links and links[0]["type"] == "relates_to"
    assert links[0]["to"] == "project_ieee"


def test_write_without_project_node_has_no_link(tmp_path):
    import yaml
    results = _run(tmp_path, [
        ("sha1", "Bug fix: wrong sign bit in encoder", "p1", ""),
    ], write=True, project="ghost")
    cand = _kept(results)[0]
    with open(cand.obs_path) as f:
        data = yaml.safe_load(f)
    assert data["proposed"]["links"] == []


def test_enrich_preserves_supersedes(tmp_path):
    """--enrich must not wipe the supersession pointer set by the dedup pass."""
    class _DecisionStub(_StubProposer):
        def propose(self, obs):
            p = super().propose(obs)
            p["type"] = "decision"
            p["fields"] = {"choice": obs.text, "rationale": "enriched"}
            return p

    results = _run(tmp_path, [
        ("sha1", "Use Redis for queue processing backend", "p1", ""),
        ("sha2", "Replace Redis for queue processing backend", "p1", ""),
    ], enrich=True, proposer=_DecisionStub())
    sup = [c for c in results if c.status == "supersession"]
    assert len(sup) == 1, [(c.sha, c.status) for c in results]
    assert sup[0].proposal.get("supersedes") == "sha1"


def test_end_to_end_bootstrap_to_recall(tmp_path):
    """The whole loop: bootstrap --write -> reflect -> distill -> retrieve must
    surface at least one node. This is the test for the pipeline dead-end."""
    import os
    os.environ["MYPM_NO_SEMANTIC"] = "1"
    from mypm.reflect import reflect
    from mypm.distill import distill
    from mypm.retriever import retrieve
    from mypm.proposer import RuleProposer

    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    _make_project(s, "ieee")

    class _ComponentProposer:
        name = "stub"
        def propose(self, obs):
            return {"type": "component", "title": "fast_float header library",
                    "id": None, "slug": None, "tags": ["csv", "parsing"],
                    "fields": {"kind": "dependency",
                               "description": "vendored header for csv float parsing"},
                    "links": [], "body": obs.text, "confidence": "medium"}

    results = bootstrap.bootstrap(
        s, repo_dir=".", limit=100, project="ieee", enrich=True, write=True,
        proposer=_ComponentProposer(),
        run_git=_fake_git(_git_log(
            ("sha1", "Downloaded fast_float.h for quick csv parsing", "p1", ""),
        )))
    assert _kept(results)

    res = reflect(s, proposer=RuleProposer())
    assert all(r.admitted for r in res), [r.reasons for r in res]

    rep = distill(s)
    assert rep.promoted, rep.blocked
    assert rep.edges_created           # the relates_to anchor materialized

    bundle = retrieve(s, "csv float parsing dependency", project="ieee")
    assert any(n["type"] == "component" for n in bundle.nodes), bundle.nodes


# ---- summary counts ----------------------------------------------------

def test_result_counts_are_consistent(tmp_path):
    # sha5 is a dup of sha3: same "Bug fix:" prefix gives shared tokens
    # {bug,fix,division,zero,normalizer} ∩ {bug,fix,division,zero,float,normalizer} = 5/6 = 0.83
    results = _run(tmp_path, [
        ("sha1", "Used simd intrinsics for hot path", "p1", ""),
        ("sha2", "chore: reformat", "p1", ""),
        ("sha3", "Bug fix: division by zero in normalizer", "p1", ""),
        ("sha4", "docs: update contributing guide", "p1", ""),
        ("sha5", "Bug fix: division by zero in float normalizer", "p1", ""),  # dup of sha3
    ])
    assert len(results) == 5
    assert len(_kept(results)) == 2
    assert len(_dropped(results)) == 2
    assert len(_duped(results)) == 1


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
