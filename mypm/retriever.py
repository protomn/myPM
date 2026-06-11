"""retrieve() — the Recall phase (docs/architecture/storage.md).

scope -> seed -> expand (pull edges) -> resolve supersession -> assemble bundle.
Reads from the derived index, not by scanning files. The seed step is a real
lexical scorer; the embedding-based seeder is the documented upgrade seam.
"""

from __future__ import annotations

import re

from . import constraints, ranking, embeddings
from .index import IndexReader, CombinedIndex
from .models import ContextBundle, BundleEntry

SEED_K = 8
MAX_DEPTH = 1            # depends_on/others followed 1 hop by default
TOKEN_BUDGET = 2000

# Seed blend when a semantic embedder is enabled. myPM is lexical-first: semantic
# is recall *rescue*, not primary retrieval. With these weights a node with any
# lexical hit (>=0.8 * its lexical score) always outranks a purely-semantic match
# (<=0.2), so semantic only decides ranking where lexical is weak or absent — the
# synonym-miss case it is good at. Override per call with --semantic-weight.
# (lexical = 1 - semantic; summing to 1 keeps combined relevance in [0,1].)
SEMANTIC_WEIGHT = 0.2

_STOP = set("the a an is are was were be to of in on at for and or with this that "
            "it its as from by we i you they our how do you".split())


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _STOP and len(w) > 2]


def _approx_tokens(text):
    return max(1, len(text) // 4)


def _relevance(task_tokens, row):
    """Real lexical seed score: weighted term overlap (title counts double).
    Normalized by the 3.0 max per-token contribution (title 2 + body 1) so the
    score genuinely lives in [0,1] — the semantic blend's weights assume it."""
    title_t = set(_tokens(row["title"]))
    body_t = set(_tokens(row["search_text"]))
    if not task_tokens:
        return 0.0
    hits = sum((2.0 if t in title_t else 0.0) + (1.0 if t in body_t else 0.0)
               for t in task_tokens)
    return hits / (3.0 * len(task_tokens))


def _semantic_scores(embedder, store, task, candidates):
    """Cosine similarity of the task against each candidate, in [0,1]. Candidate
    vectors are content-addressed and cached on disk, so each distinct node is
    embedded once per model (embeddings.EmbeddingCache)."""
    cache = embeddings.EmbeddingCache(store.embeddings_dir, embedder.model_name)
    texts = [f'{r["title"]}\n{r["search_text"] or ""}' for r in candidates]
    node_vecs = cache.embed_cached(texts, embedder.embed)
    qvec = embedder.embed([task])[0]            # the query is transient, not cached
    return {r["id"]: max(0.0, embeddings.cosine(qvec, v))
            for r, v in zip(candidates, node_vecs)}


def retrieve(store, task, project=None, agent=None, k=SEED_K,
             budget=TOKEN_BUDGET, max_depth=MAX_DEPTH, embedder=None,
             semantic_weight=None, global_store=None):
    idx = IndexReader(store)
    if global_store is not None:
        # the shared commons rides along as a second source of global-scope
        # nodes; project scopes stay strictly local (index.CombinedIndex)
        idx = CombinedIndex(idx, IndexReader(global_store))
    try:
        # 1 — SCOPE. The active agent (if any) biases ranking, not membership:
        # every in-scope type is a candidate; role-fit reweights at assembly,
        # per docs/agents/council.md ("agent-reads biased", not filtered).
        scopes = ["global"] + ([f"project:{project}"] if project else [])
        candidates = idx.candidates(scopes, status="active")

        # 2 — SEED. Lexical term overlap, blended with semantic cosine when an
        # embedder is enabled; pure lexical otherwise (v0.1 behavior). Semantic
        # is a second entry point into the graph, never a replacement for it.
        task_tokens = _tokens(task)
        relevance = {r["id"]: _relevance(task_tokens, r) for r in candidates}
        if embedder is None:
            embedder = embeddings.load_embedder()
        if getattr(embedder, "enabled", True) and candidates:
            sw = SEMANTIC_WEIGHT if semantic_weight is None else semantic_weight
            lw = 1.0 - sw
            semantic = _semantic_scores(embedder, store, task, candidates)
            relevance = {nid: lw * relevance[nid] + sw * semantic.get(nid, 0.0)
                         for nid in relevance}
        scored = sorted(((relevance[r["id"]], r) for r in candidates),
                        key=lambda x: x[0], reverse=True)
        seeds = [(s, r) for s, r in scored if s > 0][:k]
        score_by_id = {r["id"]: s for s, r in seeds}
        in_bundle = {r["id"]: r for _, r in seeds}
        why = {r["id"]: f"seed (relevance {s:.2f})" for s, r in seeds}

        # 3 — EXPAND along pull edges, bounded, lifecycle-gated
        frontier = list(in_bundle.keys())
        for _ in range(max_depth):
            nxt = []
            for nid in frontier:
                edges = idx.out_edges(nid) + idx.in_edges(nid)
                for e in edges:
                    if constraints.policy_of(e["type"]) != "pull":
                        continue
                    neighbor = e["to_id"] if e["from_id"] == nid else e["from_id"]
                    row = idx.get_node(neighbor)
                    if not row:
                        continue
                    # 4 — resolve supersession to living head
                    head = idx.get_node(row["head_id"]) or row
                    if head["status"] != "active" or head["id"] in in_bundle:
                        continue
                    in_bundle[head["id"]] = head
                    score_by_id[head["id"]] = 0.5 * score_by_id.get(nid, 0.5)
                    why[head["id"]] = f"pulled via {e['type']} from {nid}"
                    nxt.append(head["id"])
            frontier = nxt

        # flag conflicts touching the bundle (never pulled, only surfaced)
        conflicts = []
        for nid in in_bundle:
            for e in idx.out_edges(nid) + idx.in_edges(nid):
                if e["type"] == "conflicts_with":
                    pair = tuple(sorted((e["from_id"], e["to_id"])))
                    if pair not in [tuple(sorted((c["a"], c["b"]))) for c in conflicts]:
                        conflicts.append({"a": e["from_id"], "b": e["to_id"],
                                          "note": "flagged contradiction"})

        # 5 — ASSEMBLE: composite rank (relevance + centrality + recency +
        # agent role-fit), then fill the token budget in rank order.
        degrees = {r["id"]: idx.degree(r["id"]) for r in in_bundle.values()}
        max_degree = max(degrees.values(), default=0)
        ranked = sorted(
            in_bundle.values(),
            key=lambda r: ranking.score(
                relevance=score_by_id.get(r["id"], 0.0),
                degree=degrees[r["id"]], max_degree=max_degree,
                updated_at=r["updated_at"], node_type=r["type"], agent_name=agent),
            reverse=True,
        )
        bundle = ContextBundle(scope=scopes, task=task, agent=agent)
        used = 0
        followups = []
        for r in ranked:
            summary = r["body"] or r["title"]
            cost = _approx_tokens(summary)
            if used + cost > budget:
                continue
            used += cost
            import json
            bundle.nodes.append(BundleEntry(
                id=r["id"], type=r["type"], title=r["title"],
                summary=summary.strip(), why_included=why.get(r["id"], "included"),
                source=json.loads(r["source"]),
            ).__dict__)
            # offer link-policy edges as on-demand follow-ups
            for e in idx.out_edges(r["id"]):
                if constraints.policy_of(e["type"]) == "link":
                    followups.append({"edge": e["type"], "to": e["to_id"],
                                      "reason": "history/lineage, on demand"})

        bundle.conflicts = conflicts
        bundle.followups = followups
        bundle.token_count = used
        return bundle
    finally:
        idx.close()


def render_text(bundle) -> str:
    """The human-readable face of a ContextBundle — JSON is for models."""
    lines = [f"task: {bundle.task}",
             f"scope: {', '.join(bundle.scope)}"
             + (f"   agent: {bundle.agent}" if bundle.agent else ""), ""]
    if not bundle.nodes:
        lines.append("(nothing relevant recalled — the graph may not cover "
                     "this yet, or the wording shares no terms with it)")
    for n in bundle.nodes:
        d = n if isinstance(n, dict) else n.__dict__
        lines.append(f"- [{d['type']}] {d['id']} — {d['title']}")
        lines.append(f"    {d['why_included']}")
        summary = " ".join((d.get("summary") or "").split())
        if summary:
            lines.append(f"    {summary[:300]}")
    if bundle.conflicts:
        lines.append("")
        for c in bundle.conflicts:
            lines.append(f"! conflict flagged: {c['a']} <-> {c['b']}")
    lines.append("")
    lines.append(f"({len(bundle.nodes)} node(s), ~{bundle.token_count} tokens"
                 f"; {len(bundle.followups)} on-demand follow-up edge(s))")
    return "\n".join(lines)


# Orient: the SessionStart payload. No task exists yet, so relevance is mute;
# centrality and recency pick the load-bearing slice. Budget is deliberately
# small — orientation, not a download of the graph.
ORIENT_PER_TYPE = 5
ORIENT_CHAR_BUDGET = 4500

_TYPE_ORDER = ("decision", "pattern", "preference", "component", "lesson")
_TYPE_BLURB = {
    "decision": "Decisions (the law of this codebase)",
    "pattern": "Patterns (how it should be done)",
    "preference": "Preferences (how this engineer works)",
    "component": "Components",
    "lesson": "Lessons (what already broke or surprised)",
}


def orient(store, project=None, global_store=None) -> str:
    """A compact orientation bundle for the start of a session. Returns ''
    when there is nothing to say (hook-safe: silence over noise)."""
    idx = IndexReader(store)
    try:
        rows = idx.candidates(idx.scopes(), status="active")
        drafts = idx.candidates(idx.scopes(), status="draft")
    finally:
        idx.close()
    if global_store is not None:
        gidx = IndexReader(global_store)
        try:
            seen_ids = {r["id"] for r in rows}
            rows += [r for r in gidx.candidates(["global"], status="active")
                     if r["id"] not in seen_ids]
        finally:
            gidx.close()
    if project:
        rows = [r for r in rows
                if r["scope"] in ("global", f"project:{project}")]
    if not rows:
        return ""

    projects = [r for r in rows if r["type"] == "project"]
    knowledge = [r for r in rows if r["type"] != "project"]

    out = ["<myPM>  # persistent engineering memory for this repository", ""]
    for p in projects:
        desc = " ".join((p["body"] or p["title"]).split())[:200]
        out.append(f"project `{p['scope'].split(':', 1)[-1]}`: {desc}")
    out.append("")

    idx = IndexReader(store)
    try:
        degrees = idx.degrees()
    finally:
        idx.close()
    max_deg = max(degrees.values(), default=0)

    by_type = {}
    for r in knowledge:
        by_type.setdefault(r["type"], []).append(r)
    for t in _TYPE_ORDER:
        rows_t = by_type.get(t)
        if not rows_t:
            continue
        # no task yet, so relevance is mute: load-bearing (degree) and fresh
        # (recency) decide what a session should know before it starts
        rows_t.sort(key=lambda r: ranking.score(
            relevance=0.0, degree=degrees.get(r["id"], 0), max_degree=max_deg,
            updated_at=r["updated_at"], node_type=r["type"]), reverse=True)
        out.append(f"{_TYPE_BLURB[t]}:")
        for r in rows_t[:ORIENT_PER_TYPE]:
            title = " ".join(r["title"].split())[:90]
            out.append(f"- `{r['id']}` — {title}")
        if len(rows_t) > ORIENT_PER_TYPE:
            out.append(f"  (+{len(rows_t) - ORIENT_PER_TYPE} more)")
        out.append("")

    pid = projects[0]["scope"].split(":", 1)[-1] if projects else "<id>"
    out.append(f"recall for a task: mypm retrieve --task \"...\" --project {pid}")
    out.append("inspect a node:    mypm show <id>")
    if drafts:
        out.append(f"pending review:    {len(drafts)} draft(s) — mypm review")
    out.append("</myPM>")

    text = "\n".join(out)
    return text[:ORIENT_CHAR_BUDGET]