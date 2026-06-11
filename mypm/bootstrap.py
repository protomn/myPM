"""mypm bootstrap — seed the graph from existing history (the cold-start fix).

A deployment mode of the candidate-extraction core: point it at a repo's git
log, turn high-signal commits/merges into typed candidate *observations*, dedup
them against the graph and each other, and write the survivors to the inbox
ONLY — never a node. Day-1 Recall stops being empty; the human still authors
every promotion (capture is abundant, promotion is scarce).

Cost discipline is built in. The default pass is fully offline: rule-based typing
plus free lexical dedup (Recall used as a capture filter). The model is consulted
only with `enrich=True`, and only on candidates that survive the pre-filter AND
the dedup — never on noise, never on duplicates. The live Observer is the same
machinery pointed at a stream instead of history.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import githook
from .models import Observation, slugify
from .schemas import SCHEMAS
from .validator import _DUP_STOP, DUP_SIMILARITY

# Low-signal commits — documentation, formatting, renames, dead-code cleanup.
# Generic patterns only (not tuned to any one repo), so real misses show honestly.
_CHORE_RE = re.compile(
    r"^\s*("
    r"typo|formatt?ing|whitespace|lint|"
    r"fix(ed)?\s+(typo|formatting|lint|whitespace|indentation)|"
    r"updat(e|ed)\s+(the\s+)?(readme|\.?gitignore|changelog|docs?|license)|"
    r"add(ed)?\s+(the\s+)?(readme|license|changelog)|"
    r"(docs?|chore|style|test|ci|build|refactor)\s*:|"
    r"comment|clarif|document(ed|ing|s)?|explain(ed|ing|s)?|"
    r"renamed?|moved?|reformat|"
    r"(remov|eliminat|delet)(e|ed|ing)\s+(unused|redundant|dead|extra)|"
    r"merge\s+branch|bump\s|version\s+bump"
    r")", re.I)

# Vague "mood" commits with no specific finding — the Gate-1 specificity test.
_VAGUE_RE = re.compile(
    r"^\s*(minor|misc|small|various|some|final|more)?\s*"
    r"(bug\s?fixe?s?|fixe?s?|clean\s?ups?|updates?|tweaks?|changes?|"
    r"improvements?|wip|stuff|edits?)\s*$", re.I)

_LESSON_RE = re.compile(r"^\s*(bug\s?fix|fix(ed)?|hotfix|revert|regress|broke|crash|"
                        r"leak|race|deadlock|corrupt|overflow|underflow)", re.I)

# A Decision needs CHOICE or CONSTRAINT language, not mere ACTION language.
# Fresh adoption: "chose/adopted/downloaded X" — a new pick with no prior.
_ADOPTION_RE = re.compile(r"^\s*(use[sd]?|using|chose|choose|prefer|adopt|"
                          r"download(ed)?|integrat|vendor)", re.I)
# Supersession: "switched/replaced/migrated" — a prior decision is being overturned.
# These survive the Jaccard dedup even when similar to an existing node; they become
# "supersession" candidates that carry a probable `supersedes` pointer.
_SUPERSESSION_RE = re.compile(r"^\s*(switch|replac|migrat)", re.I)
# "asserted/clamped/required/added a safety check" = a constraint was imposed.
_CONSTRAINT_RE = re.compile(r"(assert(ed)?|enforc|clamp(ed)?|bound|guard|invariant|"
                            r"require(d|ment)?|safety\s?check|sanit|validat|"
                            r"limit(ed)?\b|cap(ped)?\b|restrict)", re.I)
# Deliberately NOT decisions: implement/add/create/write/define a thing — that is
# work happening, not a choice. It falls to --enrich, which can judge whether it
# warrants a Component node.

# Conventional commit prefixes — numpy/scipy/pandas style ("MAINT:", "TST:",
# "PERF:") and conventional-commits ("feat:", "perf:"). The prefix is signal,
# but it also sits at column 0 and blinds every ^-anchored rule above: "PERF:
# replace spsolve with CG" carries a supersession that "replace" at column 7
# never matches. So the prefix is split off and used as a typing HINT, and the
# content rules run against the remainder.
_CONV_RE = re.compile(r"^\s*([a-z]{2,8}(?:/[a-z]{2,8})?)\s*:\s*", re.I)
_LESSON_PREFIXES = {"fix", "fixes", "bug", "hotfix", "regr"}
_CHORE_PREFIXES = {"doc", "docs", "sty", "style", "ci", "tst", "test", "tests",
                   "bld", "build", "dev", "rel", "chore", "wip", "lint", "typ",
                   "fmt", "deps", "release"}


def _split_conventional(subject):
    """('maint', 'use boost for hyp1f1') from 'MAINT: use boost for hyp1f1';
    (None, subject) when no recognized prefix. 'MAINT/TST:' keeps the first."""
    m = _CONV_RE.match(subject or "")
    if not m:
        return None, subject
    return m.group(1).lower().split("/")[0], subject[m.end():].strip()


@dataclass
class Candidate:
    sha: str
    subject: str
    source: str                  # "commit" | "pr"
    status: str                  # "kept" | "dropped" | "duplicate"
    reason: str = ""             # why dropped, or what it duplicates
    proposal: dict | None = None
    obs_path: str | None = None


def _tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _DUP_STOP and len(w) > 2}


def graph_dedup_seed(store):
    """(seen, project_node_ids) for Recall-as-the-capture-filter, read from
    the derived index instead of parsing every node file — the observer runs
    this inside the Stop hook on every session end, so it must stay cheap as
    the graph grows."""
    from .index import IndexReader
    seen = {}
    project_nodes = set()
    idx = IndexReader(store)
    try:
        for status in ("draft", "active"):
            for r in idx.candidates(idx.scopes(), status=status):
                seen.setdefault(r["type"], []).append(
                    (r["id"], _tokens(f'{r["title"]}\n{r["search_text"] or ""}')))
                if r["type"] == "project":
                    project_nodes.add(r["id"])
    finally:
        idx.close()
    return seen, project_nodes


def _commits(repo_dir, limit, run_git):
    sep, rec = "\x1f", "\x1e"
    out = run_git(["log", f"-n{int(limit)}", f"--format=%H{sep}%s{sep}%P{sep}%b{rec}"],
                  cwd=repo_dir)
    for raw in out.split(rec):
        raw = raw.strip("\n")
        if not raw.strip():
            continue
        parts = (raw.split(sep) + ["", "", "", ""])[:4]
        sha, subject, parents, body = parts
        yield {"sha": sha, "subject": subject.strip(),
               "parents": parents.split(), "body": body.strip()}


def _prefilter(subject, body):
    """Return a drop reason, or None to keep. The cheap gate that runs before any
    typing or model call."""
    if _CHORE_RE.search(subject):
        return "chore/docs (low signal)"
    if _VAGUE_RE.match(subject) and not body:
        return "too vague (no specific finding)"
    if len(_tokens(f"{subject} {body}")) < 3:
        return "too thin to extract"
    return None


def _typed(title, body, source, ref):
    """Content-based typing, prefix-aware. Returns a proposal dict or None."""
    prefix, rest = _split_conventional(title)

    # A chore prefix (TST:, DOC:, BLD:, ...) is presumed routine unless the
    # remainder itself carries decision language ("TST: use xp-assertions
    # instead of ..." is an infrastructure choice; "TST: add tests" is not).
    if prefix in _CHORE_PREFIXES and not (
            _SUPERSESSION_RE.match(rest) or _ADOPTION_RE.match(rest)
            or _CONSTRAINT_RE.search(rest)):
        return None

    if prefix in _LESSON_PREFIXES or _LESSON_RE.match(rest):
        return {"type": "lesson", "title": title, "source": source, "ref": ref,
                "fields": {"takeaway": rest or title,
                           "trigger": body or title}}  # root_cause left empty
    if _SUPERSESSION_RE.match(rest):
        return {"type": "decision", "title": title, "source": source, "ref": ref,
                "is_supersession": True,
                "fields": {"choice": rest or title, "rationale": body or title}}
    if _ADOPTION_RE.match(rest) or _CONSTRAINT_RE.search(rest):
        return {"type": "decision", "title": title, "source": source, "ref": ref,
                "fields": {"choice": rest or title, "rationale": body or title}}
    return None


def _rule_proposal(commit):
    """Deterministic typing from the commit's structure. Conservative: returns
    None rather than forcing a type onto something that isn't clearly one.

    A merged PR is treated as provenance, not as proof of a decision: on
    GitHub-flow repos every commit lands via a PR, so blanket-typing merges
    floods the inbox with routine maintenance (observed on scipy: 40% of
    history became "decisions"). The PR title must still carry decision or
    lesson language to be typed — the live post-merge hook (githook.capture_pr)
    deliberately stays more credulous, because there a human just chose to
    merge that one PR. Bulk credulity is what bootstrap must not have."""
    desc = githook.parse_merge(commit["subject"], commit["body"], commit["parents"])
    if desc:
        ref = f"PR #{desc['pr']}" if desc["pr"] else commit["sha"][:8]
        return _typed(desc["title"], desc["rationale"], "pr", ref)

    subj, body = commit["subject"], commit["body"]
    # A vague subject ("fixes", "bug fix") that survived the prefilter did so on
    # the strength of its body — so the body's first line is the real finding,
    # not the mood-word subject.
    if _VAGUE_RE.match(subj) and body:
        subj = body.splitlines()[0].strip()
    return _typed(subj, body, "commit", commit["sha"][:8])


def _llm_proposal(commit, proposer):
    """Rich typing via the LLM proposer — only called on novel survivors."""
    text = commit["subject"] if not commit["body"] else \
        f"{commit['subject']}\n\n{commit['body']}"
    p = proposer.propose(Observation(id="_boot", text=text, source="commit", proposed={}))
    p["source"] = "commit"
    p["ref"] = commit["sha"][:8]
    return p


def _dup_of(tokens, ntype, seen):
    """Highest-overlap same-type match at/above the dup threshold, or ''."""
    if not tokens:
        return ""
    best, best_j = "", 0.0
    for handle, toks in seen.get(ntype, []):
        if not toks:
            continue
        j = len(tokens & toks) / len(tokens | toks)
        if j >= DUP_SIMILARITY and j > best_j:
            best, best_j = handle, j
    return best


def bootstrap(store, repo_dir=".", limit=20, project=None, enrich=False,
              write=False, proposer=None, model=None, run_git=githook.run_git):
    """Walk the repo's last `limit` commits into deduped candidate observations.
    Returns every commit's Candidate record (kept/dropped/duplicate) for review."""
    # Seed the dedup index with what the graph already knows (Recall as a filter),
    # and locate the project node so candidates can link to it — without at least
    # one edge a draft can never pass Gate 2, and unrecallable candidates would
    # defeat bootstrap's whole purpose.
    seen, project_nodes = graph_dedup_seed(store)
    project_node_id = (f"project_{project}"
                       if project and f"project_{project}" in project_nodes
                       else None)

    if enrich and proposer is None:
        from .proposer import get_proposer
        proposer = get_proposer(prefer_llm=True, model=model)

    out = []
    for c in _commits(repo_dir, limit, run_git):
        reason = _prefilter(c["subject"], c["body"])
        if reason:
            out.append(Candidate(c["sha"][:8], c["subject"], "commit", "dropped", reason))
            continue

        proposal = _rule_proposal(c)
        llm_rescued = False
        if proposal is None:
            # The rules demand choice/lesson VERBS; feature- and release-style
            # subjects ("v0.3: live observer — Stop hooks ...") carry decisions
            # the rules cannot see. With --enrich, the model gets exactly these
            # prefilter survivors — the free pass alone can honestly yield zero
            # on such histories, which defeats bootstrap's purpose.
            if enrich:
                proposal = _llm_proposal(c, proposer)
                required = SCHEMAS.get(proposal.get("type"), {}).get(
                    "required_draft", [])
                if not proposal.get("type") or any(
                        not proposal.get("fields", {}).get(f) for f in required):
                    out.append(Candidate(c["sha"][:8], c["subject"], "commit",
                                         "dropped", "LLM could not type honestly"))
                    continue
                llm_rescued = True
            else:
                out.append(Candidate(c["sha"][:8], c["subject"], "commit",
                                     "dropped", "no clear decision/lesson"))
                continue

        toks = _tokens(proposal["title"] + " " + " ".join(map(str, proposal["fields"].values())))
        dup = _dup_of(toks, proposal["type"], seen)
        if dup and not proposal.get("is_supersession"):
            out.append(Candidate(c["sha"][:8], c["subject"], proposal["source"],
                                 "duplicate", f"~ {dup}", proposal))
            continue

        if dup:  # is_supersession=True — tag the probable target, don't drop
            proposal = dict(proposal)
            proposal["supersedes"] = dup

        # Novel or supersession: the only place the model is consulted, and only if asked.
        if enrich and not llm_rescued:
            enriched = _llm_proposal(c, proposer)
            if proposal.get("supersedes"):     # survives enrichment
                enriched["supersedes"] = proposal["supersedes"]
            proposal = enriched

        seen.setdefault(proposal["type"], []).append((c["sha"][:8], toks))
        if proposal.get("supersedes"):
            status = "supersession"
            reason = f"→ supersedes {proposal['supersedes']}"
        else:
            status, reason = "kept", ""
        cand = Candidate(c["sha"][:8], c["subject"], proposal["source"], status,
                         reason, proposal)
        if write:
            cand.obs_path = _write_candidate(store, c, proposal, project,
                                             project_node_id)
        out.append(cand)
    return out


def _write_candidate(store, commit, proposal, project, project_node_id=None):
    ref = proposal.get("ref", commit["sha"][:8])
    body = (proposal.get("body") or commit["body"] or commit["subject"]).rstrip()
    provenance = f"\n\n_Source: bootstrap from commit {commit['sha'][:8]} ({ref})."
    if proposal.get("supersedes"):
        provenance += f" Probably supersedes `{proposal['supersedes']}`."
    provenance += "_"
    # Anchor the candidate to the graph: relates_to is legal ANY->ANY, so this one
    # edge satisfies Gate 2's "linked" requirement once the draft is substantiated.
    links = list(proposal.get("links") or [])
    if project_node_id and not links:
        links.append({"type": "relates_to", "to": project_node_id,
                      "note": "bootstrap candidate from this project's history"})
    proposed = {
        "type": proposal["type"], "title": proposal["title"],
        "fields": proposal["fields"],
        "tags": list(proposal.get("tags") or []) + ["from-bootstrap"],
        "body": body + provenance,
        "links": links,
    }
    obs = Observation(
        id=f"obs_boot_{commit['sha'][:8]}_{slugify(proposal['title'], 3)}",
        text=commit["subject"], source=proposal["source"],
        project=project, proposed=proposed)
    return store.write_observation(obs)
