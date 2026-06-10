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


def _rule_proposal(commit):
    """Deterministic typing from the commit's structure. Conservative: returns
    None rather than forcing a type onto something that isn't clearly one."""
    desc = githook.parse_merge(commit["subject"], commit["body"], commit["parents"])
    if desc:
        ref = f"PR #{desc['pr']}" if desc["pr"] else commit["sha"][:8]
        return {"type": "decision", "title": desc["title"], "source": "pr", "ref": ref,
                "fields": {"choice": desc["title"], "rationale": desc["rationale"]}}

    subj, body = commit["subject"], commit["body"]
    # A vague subject ("fixes", "bug fix") that survived the prefilter did so on
    # the strength of its body — so the body's first line is the real finding,
    # not the mood-word subject.
    if _VAGUE_RE.match(subj) and body:
        subj = body.splitlines()[0].strip()

    if _LESSON_RE.match(subj):
        return {"type": "lesson", "title": subj, "source": "commit",
                "ref": commit["sha"][:8],
                "fields": {"takeaway": subj, "trigger": body or subj}}  # root_cause left empty
    if _SUPERSESSION_RE.match(subj):
        return {"type": "decision", "title": subj, "source": "commit",
                "ref": commit["sha"][:8], "is_supersession": True,
                "fields": {"choice": subj, "rationale": body or subj}}
    if _ADOPTION_RE.match(subj) or _CONSTRAINT_RE.search(subj):
        return {"type": "decision", "title": subj, "source": "commit",
                "ref": commit["sha"][:8],
                "fields": {"choice": subj, "rationale": body or subj}}
    return None


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
    seen = {}
    project_node_id = None
    for n in store.all_nodes():
        if n.status in ("draft", "active"):
            seen.setdefault(n.type, []).append((n.id, _tokens(n.search_text())))
        if project and n.type == "project" and n.id == f"project_{project}":
            project_node_id = n.id

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
        if proposal is None:
            out.append(Candidate(c["sha"][:8], c["subject"], "commit", "dropped",
                                 "no clear decision/lesson"))
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
        if enrich:
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
