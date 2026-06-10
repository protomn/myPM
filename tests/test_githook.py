"""Tests for the git hook: merge parsing, PR capture, and hook install/uninstall.
Runnable with `python tests/test_githook.py`. No real git is invoked — the git
seam is stubbed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mypm import githook
from mypm.reflect import reflect
from mypm.distill import distill
from mypm.store import Store


# ---- unit: parse_merge --------------------------------------------------

def test_parse_github_merge_commit():
    d = githook.parse_merge(
        "Merge pull request #42 from acme/feat-rate-limit",
        "Add token-bucket rate limiter", parents=["p1", "p2"])
    assert d["pr"] == "42"
    assert d["title"] == "Add token-bucket rate limiter"
    assert d["branch"] == "acme/feat-rate-limit"


def test_parse_squash_merge():
    d = githook.parse_merge("Add token-bucket rate limiter (#42)", "", parents=["p1"])
    assert d["pr"] == "42"
    assert d["title"] == "Add token-bucket rate limiter"


def test_parse_plain_merge_requires_optin():
    assert githook.parse_merge("Merge branch 'feature/x'", "",
                               parents=["p1", "p2"]) is None
    d = githook.parse_merge("Merge branch 'feature/x'", "",
                            parents=["p1", "p2"], allow_plain=True)
    assert d["pr"] is None and d["branch"] == "feature/x"


def test_parse_non_merge_is_skipped():
    assert githook.parse_merge("fix: a normal commit", "", parents=["p1"]) is None


# ---- capture_pr writes an observation that flows through the gates -------

def _fake_git(block):
    return lambda args, cwd=None: block


def test_capture_pr_writes_observation(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    block = "abc1234deadbeef\nMerge pull request #7 from me/cache\n" \
            "p1 p2\nUse Redis-backed cache counters"
    path = githook.capture_pr(s, project="svc", _run_git=_fake_git(block))
    assert path and os.path.exists(path)
    obs = s.all_observations()[0][0]
    assert obs.source == "pr"
    assert obs.proposed["type"] == "decision"
    assert obs.proposed["fields"]["choice"] == "Use Redis-backed cache counters"
    assert obs.proposed["fields"]["rationale"]
    assert "abc1234d" in obs.proposed["body"]   # provenance pointer preserved


def test_capture_pr_draft_is_held_at_gate2(tmp_path):
    """The captured Decision has Gate-1 structure but not Gate-2 substantiation,
    so it should admit as a draft and then be held — never auto-promoted."""
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    block = "sha9999\nFeature: idempotent webhook handler (#13)\np1\nbody text"
    githook.capture_pr(s, project="svc", _run_git=_fake_git(block))

    res = reflect(s)
    assert res[0].admitted                       # Gate 1: typed into a draft Decision
    rep = distill(s)
    assert rep.promoted == []                     # Gate 2 holds it (no alternatives/consequences)
    assert any("substantiated" in r for _, reasons in rep.blocked for r in reasons)


def test_capture_pr_skips_non_merge(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    block = "sha\nchore: bump deps\np1\n"
    assert githook.capture_pr(s, _run_git=_fake_git(block)) is None
    assert s.all_observations() == []


# ---- hook install / uninstall -------------------------------------------

def _make_repo(tmp_path):
    os.makedirs(os.path.join(str(tmp_path), ".git", "hooks"))
    return str(tmp_path)


def test_install_and_uninstall(tmp_path):
    repo = _make_repo(tmp_path)
    path, action = githook.install_hook(repo, "knowledge")
    assert action == "installed"
    assert os.access(path, os.X_OK)
    with open(path) as f:
        assert githook.HOOK_MARKER in f.read()
    # idempotent: re-install updates our own hook
    _, action2 = githook.install_hook(repo, "knowledge")
    assert action2 == "updated"
    assert githook.uninstall_hook(repo) == "removed"
    assert githook.uninstall_hook(repo) == "absent"


def test_install_refuses_to_clobber_foreign_hook(tmp_path):
    repo = _make_repo(tmp_path)
    foreign = githook.hook_path(repo)
    with open(foreign, "w") as f:
        f.write("#!/bin/sh\necho someone elses hook\n")
    path, action = githook.install_hook(repo, "knowledge")
    assert action == "skipped"
    assert githook.uninstall_hook(repo) == "foreign"      # left untouched
    # --force overwrites
    _, action2 = githook.install_hook(repo, "knowledge", force=True)
    assert action2 == "installed"


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
