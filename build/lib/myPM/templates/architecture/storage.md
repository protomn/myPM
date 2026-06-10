# myPM — Storage Model

## Where storage sits

The Knowledge, Relationship, Agent, and Reasoning models are conceptual. They say
what a node *is*, how nodes *relate*, who *reasons* over them, and how the loop
*turns*. None of them says where a single byte lives. This document is the
substrate beneath all four: the physical layer where an abstract graph becomes
files on a disk and in a git history.

Storage introduces no new concepts. It has exactly one job, and it is a job of
fidelity: to realize the four models losslessly, so that every rule they assert is
true of the bytes as well as the ideas. A storage layer that quietly drops the
supersession trail, or makes reverse traversal expensive, or traps the graph in a
proprietary format, has not stored myPM. It has stored something that
resembles it and betrays it.

This is also the layer where the philosophy's central promise is kept or broken.
"Plain, portable, inspectable files that outlive the model" is rhetoric until
something here makes it physically so. Everything below is in service of that
sentence.


## Principles

**The files are the database of record.** A node is a file. An edge is a file.
The complete, authoritative state of the system is a directory tree you can read
with `cat`, search with `grep`, diff with `git`, and open in any editor. There is
no hidden state, no canonical binary blob, nothing that requires the application
to interpret. If myPM the program vanished tomorrow, the knowledge would
still be there, readable by a human and parseable by the next tool.

**The index is a cache, never the truth.** Retrieval at any real scale needs an
index, and there is one. But it is *derived* from the files and is disposable by
construction: delete it and it rebuilds from source. It is never committed, never
authoritative, never the thing you back up. The files outlive the index the way
they outlive the model. This single discipline is what lets the index be a fast,
disposable SQLite database today and something else entirely in five years
without migrating a single byte of actual knowledge.

**Format is the portability promise made physical.** Nodes are Markdown with YAML
frontmatter. Edges are small YAML records. Both are text, both are git-native,
both render and diff anywhere. The choice is not aesthetic. It is the difference
between knowledge you own and knowledge you rent.


## How a node is stored

A node is one Markdown file: YAML frontmatter for the structured fields the
machine reads, and a Markdown body for the prose a human and an agent read. The
`body` field from the Memory Node envelope *is* that Markdown content; everything
else lives in frontmatter.

`knowledge/projects/binary_serializer/nodes/lesson_allocator_overhead.md`

```markdown
---
id: lesson_allocator_overhead
type: lesson
title: Allocator overhead dominates latency
scope: project:binary_serializer
status: active
confidence: high
source:
  type: incident
  ref: bench/2026-02-allocator-profile
tags: [performance, allocation, latency]
created_at: 2026-02-11T09:30:00Z
updated_at: 2026-02-11T09:30:00Z
# entity-specific structured fields (Lesson)
trigger: serialization optimization effort
root_cause: allocator cost dominated runtime
takeaway: benchmark allocations before optimizing anything else
---

Replacing heap allocations with stack buffers reduced latency substantially
because allocator overhead dominated runtime. The hot path allocated per call;
moving to a reused stack buffer removed the allocator from the inner loop.
```

Two refinements on the sketch, both deliberate. The `body` is the Markdown content
below the frontmatter, not a YAML field, so it renders, diffs, and carries code
blocks and links naturally. And the entity-specific fields (`trigger`,
`root_cause`, `takeaway` for a Lesson; `context`, `choice`, `alternatives`,
`rationale`, `consequences` for a Decision) live *in* the frontmatter, because
they are structured semantics the machine must read, not free narrative.

A Decision realizes the same envelope with its own fields:

```markdown
---
id: decision_stack_buffers
type: decision
title: Use reused stack buffers over per-call heap allocation
scope: project:binary_serializer
status: active
confidence: high
source: { type: pr, ref: serializer#214 }
tags: [performance, allocation]
created_at: 2026-02-12T14:00:00Z
updated_at: 2026-02-12T14:00:00Z
context: serializer hot path allocated on every call; latency budget exceeded
choice: reuse a per-thread stack buffer; allocate only on overflow
alternatives: [arena allocator, custom pool allocator, leave as-is]
rationale: removes allocator from the inner loop with the least machinery
consequences: buffer sizing is now a tuning parameter; overflow path must be tested
---

The benchmark in lesson_allocator_overhead showed allocator cost dominating
runtime. A reused stack buffer removes it without the complexity of a pool.
```

The remaining four entity schemas are defined in `core-model.md`; their storage
form follows the same rule without exception. Frontmatter is the typed record.
Markdown is the narrative.


## Where nodes and edges live

```
knowledge/
├── global/
│   └── nodes/                                  # cross-project knowledge
│       ├── pattern_fail_closed_limiter.md
│       └── preference_redis_counters.md
├── projects/
│   └── binary_serializer/
│       ├── project.md                          # the Project node itself
│       └── nodes/                              # nodes scoped to this project
│           ├── component_serializer_core.md
│           ├── decision_stack_buffers.md
│           └── lesson_allocator_overhead.md
├── edges/                                       # ALL edges, scope-free, one file each
│   ├── lesson_allocator_overhead--motivates--decision_stack_buffers.yml
│   └── decision_stack_buffers--affects--component_serializer_core.yml
└── .index/                                      # derived, gitignored, rebuildable
    └── graph.db
```

The load-bearing decision is the split between nodes and edges, and it falls
directly out of `relationships.md`: **scope is a property of nodes; edges are
scope-free.** A node's knowledge belongs somewhere — to a project or to the global
commons. A relationship belongs nowhere; it is a fact about two nodes. So nodes are
filed by scope under `global/` or `projects/<id>/`, and every edge, including the
many that cross project boundaries, lives in one flat `edges/` directory.

This is the only layout that cleanly answers the question the sketch could not: a
Lesson in one project that `motivates` a Decision in another has a perfectly
ordinary home, because its edge was never going to live in a project directory in
the first place. "The graph is global; scope is a filter, not a wall" is, at the
storage layer, exactly this directory structure.

**A node's directory is authoritative for its scope.** A file under
`projects/binary_serializer/nodes/` is scoped to that project, full stop. The
`scope` field in frontmatter mirrors the location for readability and is validated
against it at build time; if they disagree, the build fails. Re-scoping a node is
therefore a `git mv`, which is precisely the honest, reviewable operation it should
be.


## How a node is identified

A node ID is `<type>_<slug>`: human-readable, greppable, and stable. The filename
derives from the ID. Two rules make IDs trustworthy as the handle that edges point
at:

**The ID is immutable; the title is not.** `title` is the human label and may be
revised freely. `id` is the permanent handle, and edges reference it. If IDs could
change, every edge would be a dangling pointer waiting to happen. This is exactly
why the Memory Node envelope separated the two fields, and storage enforces the
separation: renaming the title is an edit, "renaming" the ID is forbidden (you
supersede the node with a new one instead).

**Edge IDs are deterministic.** An edge's ID is derived from its endpoints and
type: `<from>--<type>--<to>`. This makes edges *idempotent* — asserting the same
relationship twice produces the same file, not a duplicate — and *merge-safe* —
two engineers who independently record the same link generate byte-identical files
that git merges without conflict. The sketch's `edge_001` counter is replaced for
both reasons: a sequential counter is a merge-conflict magnet and carries no
meaning.


## How an edge is stored

An edge is a small YAML record, one file each, in `edges/`. Edges have no
narrative, so they need no Markdown body, only an optional `note`.

`knowledge/edges/lesson_allocator_overhead--motivates--decision_stack_buffers.yml`

```yaml
id: lesson_allocator_overhead--motivates--decision_stack_buffers
type: motivates
from: lesson_allocator_overhead
to: decision_stack_buffers
created_at: 2026-02-12T14:00:00Z
source: { type: conversation }
note: the benchmark finding drove the switch to stack buffers
```

Edges are stored as their own files, not inside node frontmatter, because
`relationships.md` requires them to be first-class: queryable from both ends, with
their own provenance and metadata. A `links:` array buried in a node would make
"which Decisions does this Lesson motivate?" cheap and "which Lessons motivated
this Decision?" expensive, and would leave the edge nowhere to record *why* it
exists. The flat edge directory makes both directions symmetric and gives every
relationship a place to keep its reasons.


## How versioning works in practice

The four states from the lifecycle — `draft`, `active`, `superseded`,
`deprecated` — were defined but never implemented. Here they are made physical.

`status` is a frontmatter field, so a state transition is a one-line edit captured
as a git commit. The history of a node's status *is* its git history, which means
the audit trail comes free and is tamper-evident.

**Superseding is two operations and no migration.** When node B supersedes node A:
write the `supersedes` edge (`from: B, to: A`), and flip `A.status` to
`superseded`. That is all. Per `relationships.md`, A's other edges are *not*
migrated to B — A keeps them as a snapshot of the world as it was, and B asserts
its own. This is the difference between "what is true now" and "what was true
then," preserved in the bytes.

**Resolving a supersession chain** is a forward walk along the inverse of
`supersedes`:

```
resolve_head(a):
    cur = a
    loop:
        replacements = edges(type=supersedes, to=cur).map(e -> node(e.from))
        active_repl  = replacements.filter(status == active)
        if active_repl.empty:   return cur            # cur is the living head
        if active_repl.one:     cur = active_repl[0]   # follow the chain
        else:                   return active_repl     # split: surface all heads
```

A linear chain (`A <- B <- C`) resolves to its single living head. The M:N cases
from `relationships.md` — a merge collapsing several old nodes into one, or a split
fanning one into many — fall out naturally: a merge has one head, a split returns
the set, and the caller is shown all of them rather than a silently chosen one.

**Drafts are visible only in context.** A `draft` node exists as a file (capture
must persist immediately) but is excluded from general Recall. It is visible to the
agent and human working the session that produced it, and it becomes generally
recallable only when Distill promotes it to `active`. **Deprecated** nodes are
end-of-life with no successor; they are never pulled, only reachable on demand as
history. This is the lifecycle from the Golden Loop, enforced at the point of
retrieval.


## The index

Source files are the truth; the index is the read-optimization that makes
retrieval fast. It is built by scanning the tree and is rebuildable at any time. A
single-file SQLite database (`.index/graph.db`, gitignored) holds three things:

- a **node table** — `id, type, scope, status, head_id, tags, embedding`, where
  `head_id` is the precomputed living head of each node's supersession chain;
- an **adjacency index** — forward (`from -> [(type, to)]`) and reverse
  (`to -> [(type, from)]`), so traversal in either direction is a lookup, not a
  scan;
- a **search index** — full-text over title/body/tags plus the vector embeddings
  for semantic seed selection.

Because it is derived, the index format is a private implementation detail that
can change without touching a single node or edge file. Because it is gitignored,
it never causes a merge conflict and never needs reconciling across machines; each
clone rebuilds its own.


## Integrity and the build pass

Plain files are only trustworthy if something enforces the model's rules on them.
A build/lint pass runs on write and in CI, and it is where `relationships.md`'s
constraints stop being documentation and become guarantees:

- **Schema validation** — every node's frontmatter conforms to its type's schema;
  every edge has valid endpoints.
- **Edge validity** — every edge satisfies the legal `(from-type, edge, to-type)`
  triples from the constraint table. A `depends_on` from a Preference to a
  Component is rejected at write time, not discovered in production.
- **Referential integrity** — no dangling edges; every `from` and `to` resolves to
  a node file. A node that other edges point at cannot be deleted, only superseded
  or deprecated.
- **Acyclicity** — `supersedes`, `part_of`, and `builds_on` must form DAGs and a
  cycle fails the build; a `depends_on` cycle is *flagged* rather than rejected,
  because it may reflect real architecture worth recording, and is surfaced as a
  candidate Lesson.


## The write path is a git workflow

Capture, from the Golden Loop, lands here as ordinary version control. An agent
proposes by writing `draft` node and edge files; the human reviews them as a git
diff or pull request; approval is the act of merging and flipping `status` to
`active` during Distill. "The human authors; the AI reads" is, at the storage
layer, simply this: the AI opens the PR, the human is the one who merges it.
Authorship of record is git authorship of record, with all the attribution,
review, and revert that implies, for free.


## Retrieval

This is the section the founder's question lives in. When someone asks "how do you
actually retrieve context," this is the concrete answer, end to end. It implements
the contract sketched in `relationships.md` and the Recall phase of the Golden
Loop, parameterized by the requesting agent.

```
retrieve(task, agent, project) -> ContextBundle:

    # 1 — SCOPE: select the candidate node set
    scope      = { "project:" + project, "global" }
    candidates = index.nodes(scope in scope, status = active)

    # 2 — SEED: hybrid relevance, biased by the agent's I/O contract
    seeds = index.search(
        query   = embed(task),          # semantic similarity (primary)
        text    = keywords(task),        # lexical match (recall safety net)
        within  = candidates,
        type_in = agent.reads,           # role bias from agents.md
        k       = SEED_K,
    )

    # 3 — EXPAND: follow pull-policy edges, bounded, lifecycle-gated
    bundle = set(seeds); frontier = seeds
    for depth in 1 .. MAX_DEPTH:         # depends_on: 1 hop; others: 1 hop
        next = []
        for n in frontier:
            for (etype, m) in index.out_edges(n) + index.in_edges(n):
                if policy(etype) != PULL: continue
                m = resolve_head(m)               # 4 — supersession, inline
                if m.status == active and m not in bundle:
                    bundle.add(m); next.add(m)
        frontier = next

    # surface, do not resolve, conflicts crossed during expansion
    conflicts = edges(type = conflicts_with, touching = bundle)   # FLAG policy

    # 5 — ASSEMBLE: rank, token-budget, compact
    out = ContextBundle(scope = scope, agent = agent.role)
    for n in rank(bundle, by = relevance_and_centrality):
        if out.tokens + n.summary_tokens > BUDGET: break          # breadth over depth
        out.add(id=n.id, type=n.type, title=n.title,
                summary=n.body, why=n.inclusion_reason, source=n.source)
    out.conflicts = conflicts
    out.followups = link_edges(bundle)        # LINK policy: available on demand

    # 6 — FEED: hand to the agent as recalled context
    return out
```

Each step, in plain terms:

1. **Scope.** The current project plus `global` defines the candidate set. Edges
   are scope-free and all available; the filter is on nodes. Only `active` nodes
   are candidates — drafts and deprecated knowledge are excluded here.
2. **Seed.** Relevance is hybrid: vector similarity against the task is primary,
   lexical match is the safety net for exact terms embeddings miss, and the
   agent's declared `reads` narrow the types (the Performance Engineer seeds on
   hot-path Components, the Adversarial Reviewer on Lessons and anti-patterns).
   `k` is bounded by the token budget.
3. **Expand.** From each seed, follow only `pull`-policy edges, one hop, in both
   directions. `link` edges (supersedes, builds_on, influences, relates_to) are
   not followed; `flag` edges (conflicts_with) are not followed for content.
4. **Resolve supersession.** Every node reached is resolved to the living head of
   its chain before inclusion, so the bundle never contains stale knowledge unless
   the query is explicitly historical.
5. **Assemble.** Rank by relevance and graph centrality, then fill a token budget,
   dropping the weakest first and preferring breadth of distinct knowledge over
   depth on one node. Each entry carries only the node's `body` summary plus its
   provenance, so the agent can reason and cite without the full file. Conflicts
   are attached as explicit warnings; `link` edges are listed as follow-ups the
   agent may pull if the question turns to "why."
6. **Feed.** The bundle is the agent's recalled context — the input to Reason.

The shape handed back:

```
ContextBundle {
  scope        [ "project:<id>", "global" ]
  agent        role
  nodes        [ { id, type, title, summary, why_included, source } ]
  conflicts    [ { a, b, note } ]            # flagged, never silently resolved
  followups    [ { edge, to, reason } ]      # link-policy edges, available on demand
  token_count  int
  generated_at timestamp
}
```

The founder's answer, in one breath: we filter the graph to the project and the
global commons, find the most relevant nodes by meaning and keyword and the
agent's role, walk one hop out along the edges marked worth pulling, replace
anything stale with its current version, flag any contradictions instead of hiding
them, and pack the result into a token-budgeted bundle of compact summaries with
provenance. The files are the truth; an index makes it fast; the bundle is what
the agent thinks with.


## What storage is not

Storage is not a new model. Anything it appears to introduce — the directory
split, the index, the build pass — exists only to realize the four conceptual
models faithfully. If a storage decision and a model rule ever conflict, the model
wins and the storage is wrong.

Storage is not the index. The index is a convenience that can be deleted and
rebuilt; mistaking it for the system is how a portable, owned knowledge base
quietly becomes a proprietary database lock-in. The files are the product. The
index just makes them quick.