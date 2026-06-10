"""retrieve() — the Recall phase (docs/architecture/storage.md).

scope -> seed -> expand (pull edges) -> resolve supersession -> assemble bundle.
Reads from the derived index, not by scanning files. The seed step is a real
lexical scorer; the embedding-based seeder is the documented upgrade seam.
"""

from __future__ import annotations

import re

from . import constraints, ranking, embeddings
from .index import IndexReader
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
    """Real lexical seed score: weighted term overlap (title counts double)."""
    title_t = set(_tokens(row["title"]))
    body_t = set(_tokens(row["search_text"]))
    if not task_tokens:
        return 0.0
    hits = sum((2.0 if t in title_t else 0.0) + (1.0 if t in body_t else 0.0)
               for t in task_tokens)
    return hits / (2.0 * len(task_tokens))


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
             semantic_weight=None):
    idx = IndexReader(store)
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