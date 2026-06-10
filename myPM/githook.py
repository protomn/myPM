"""Git hook capture: a merged PR becomes a draft Decision observation.

docs/architecture/core-model.md: "A merged PR can emit a draft Decision." A merge
is the most reliable event marking that an architectural choice was committed, so
it is the natural place to automate the Capture phase. Discipline is preserved:
the hook writes an *observation* to the inbox, never an active node. The draft it
becomes carries only Gate-1 structure (choice + rationale); `alternatives` and
`consequences` stay empty, so Gate 2 correctly holds it until the human authors
them. The hook proposes; the engineer still authors (docs/agents/council.md).

Merge-commit parsing is pure and unit-testable (`parse_merge`); the git
invocation is the one impure seam (`run_git`), injectable for tests.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys

from .models import Observation, slugify

# GitHub's two merge shapes, plus a plain `git merge branch`.
_PR_MERGE_RE = re.compile(r"merge pull request #(\d+)", re.I)   # merge-commit subject
_PR_SQUASH_RE = re.compile(r"\(#(\d+)\)\s*$")                   # squash/rebase subject
_MERGE_FROM_RE = re.compile(r"from (\S+)", re.I)
_MERGE_BRANCH_RE = re.compile(r"merge branch ['\"]([^'\"]+)['\"]", re.I)

HOOK_MARKER = "# myPM: auto-capture draft Decisions from merged PRs"


def run_git(args, cwd=None):
    """Run a git command and return stripped stdout (the impure seam)."""
    return subprocess.run(["git", *args], cwd=cwd,
                          capture_output=True, text=True).stdout.strip()


def parse_merge(subject, body, parents, allow_plain=False):
    """Pure: turn commit metadata into a PR-merge descriptor, or None to skip.

    Recognizes GitHub merge commits ("Merge pull request #N from owner/branch",
    where the body holds the PR title) and squash/rebase merges ("Title (#N)").
    Plain branch merges ("Merge branch 'x'") are captured only when `allow_plain`
    is set, since post-merge also fires on routine `git pull` and we do not want
    to flood the inbox with non-decisions. Returns {title, pr, branch, rationale}.
    """
    subject = (subject or "").strip()
    body = (body or "").strip()
    is_merge = len(parents) >= 2

    m = _PR_MERGE_RE.search(subject)
    if m:
        fm = _MERGE_FROM_RE.search(subject)
        title = body.splitlines()[0] if body else subject
        return {"title": title, "pr": m.group(1),
                "branch": fm.group(1) if fm else None,
                "rationale": body or title}

    m = _PR_SQUASH_RE.search(subject)
    if m:
        title = _PR_SQUASH_RE.sub("", subject).strip()
        return {"title": title, "pr": m.group(1), "branch": None,
                "rationale": body or title}

    if allow_plain and is_merge:
        bm = _MERGE_BRANCH_RE.search(subject)
        branch = bm.group(1) if bm else None
        title = f"Merge {branch}" if branch else subject
        return {"title": title, "pr": None, "branch": branch,
                "rationale": body or title}

    return None


def capture_pr(store, project=None, commit="HEAD", allow_plain=False,
               _run_git=run_git):
    """Read `commit`'s merge metadata and, if it's a PR merge, write a draft
    Decision observation to the inbox. Returns the path written, or None if the
    commit is not a capturable merge."""
    fmt = _run_git(["log", "-1", "--format=%H%n%s%n%P%n%b", commit])
    if not fmt:
        return None
    sha, subject, parents_line, *body_lines = fmt.splitlines()
    parents = parents_line.split()
    body = "\n".join(body_lines)

    desc = parse_merge(subject, body, parents, allow_plain=allow_plain)
    if desc is None:
        return None

    ref = f"PR #{desc['pr']}" if desc["pr"] else (desc["branch"] or sha[:8])
    provenance = f"_Source: merge {sha[:8]}" + \
                 (f" (PR #{desc['pr']})" if desc["pr"] else "") + "._"
    context = f"Introduced by {ref}" + \
              (f" from branch {desc['branch']}" if desc["branch"] else "")

    handle = desc["pr"] or sha[:8]
    proposed = {
        "type": "decision",
        "title": desc["title"],
        "fields": {
            "choice": desc["title"],
            "rationale": desc["rationale"],
            "context": context,
        },
        "body": f"{desc['rationale']}\n\n{provenance}",
        "tags": ["from-pr"],
    }
    obs = Observation(
        id=f"obs_pr_{handle}_{slugify(desc['title'], 3)}",
        text=f"Merged: {desc['title']}", source="pr",
        project=project, proposed=proposed,
    )
    return store.write_observation(obs)


# ---- hook installation ---------------------------------------------------

def repo_root(cwd=None, _run_git=run_git):
    top = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return top or None


def hook_path(root_dir):
    return os.path.join(root_dir, ".git", "hooks", "post-merge")


def _hook_script(knowledge_root):
    # Pin the installing interpreter so the hook works regardless of PATH/venv.
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARKER}\n"
        f'"{sys.executable}" -m myPM --root "{knowledge_root}" capture-pr || true\n'
    )


def install_hook(repo_dir, knowledge_root, force=False):
    """Write the post-merge hook. Refuses to clobber a foreign hook unless forced.
    Returns (path, action) where action is 'installed' | 'updated' | 'skipped'."""
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise ValueError(f"not a git repository: {repo_dir}")
    path = hook_path(repo_dir)
    action = "installed"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
        if HOOK_MARKER in existing:
            action = "updated"
        elif not force:
            return path, "skipped"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_hook_script(knowledge_root))
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path, action


def uninstall_hook(repo_dir):
    """Remove our post-merge hook if it is ours. Returns 'removed' | 'absent' |
    'foreign' (left untouched because it isn't the myPM hook)."""
    path = hook_path(repo_dir)
    if not os.path.exists(path):
        return "absent"
    with open(path, "r", encoding="utf-8") as f:
        if HOOK_MARKER not in f.read():
            return "foreign"
    os.remove(path)
    return "removed"
