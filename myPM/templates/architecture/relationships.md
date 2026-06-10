# myPM — Relationships

## Purpose

The entities in `core-model.md` are a filing system. The relationships defined
here are the reasoning layer. An agent answers "why is this built this way" or
"what will this change break" by *traversing edges*, not by reading nodes in
isolation.

This document specifies every edge type: its meaning, direction, inverse,
cardinality, cycle behavior, and — most importantly — its **traversal policy**,
which governs whether an agent pulls the neighbor into context automatically or
only when asked.

It refines the brief edge sketch in `core-model.md` and is the authoritative
source. It adds four edges that sketch did not have: `part_of`, `builds_on`,
`establishes`, and `conflicts_with`.


## Principles

**Edges are first-class records, not node attributes.** An edge has its own id,
provenance, and type-specific metadata, and is queryable from both ends. Storing
`links` inside a node would make reverse traversal ("which Decisions affect this
Component?") expensive and would give edges nowhere to record *why* they exist.

**Every edge is directed and has a defined inverse.** You assert
`Decision affects Component`; you traverse `affected_by` from the Component side.
The inverse is not a second stored edge — it is the same edge read backward.

**The graph is global; scope is a filter, not a wall.** Only `belongs_to` is
bound to a single scope. Every other edge may cross project boundaries. This is
the mechanism that makes knowledge accumulate *across* projects: a Lesson learned
in one project can motivate a Decision in another, and a global Pattern can be
applied by Decisions everywhere.

**Validity is constrained at the relational level.** Not every (type, edge,
type) triple is legal. The constraint set at the end of this document is what
enforces "everything is one of these" for edges, the same way the entity set
enforces it for nodes.

**Asserted edges are stored; derived edges are computed.** The store holds direct
edges only. Transitive closures (the full dependency tree, the current head of a
supersession chain, conflict propagation) are computed by the reasoning layer at
query time, never persisted.


## The edge record

```
Edge {
  id          string
  type        EdgeType
  from        node_id
  to          node_id
  created_at  timestamp
  source      Source        // provenance: where this link was asserted
  note        string?       // optional human explanation
  attributes  object        // type-specific (dependency kind, supersede reason, ...)
}
```


## Catalog

Quick reference. Columns: edge, signature, cardinality, inverse, cycle rule,
traversal policy. Policies are defined under [Traversal](#traversal).

```
# structural
belongs_to     Node        -> Project|global    N:1    contains         acyclic    structural
part_of        Component   -> Component          N:1    contains         acyclic    pull(parent)

# dependency
depends_on     Component   -> Component          M:N    dependents       acyclic*   pull(1 hop)
builds_on      Decision    -> Decision           M:N    extended_by      acyclic    link

# causal / provenance
motivates      Lesson      -> Decision|Pattern   M:N    motivated_by     ---        pull
derived_from   Pattern     -> Lesson             M:N    distilled_into   ---        pull
establishes    Decision    -> Pattern            1:N    established_by    acyclic    pull
influences     Preference  -> Decision|Pattern   M:N    influenced_by    ---        link

# reference
affects         Decision   -> Component          M:N    affected_by      ---        pull
concerns        Lesson     -> Component          M:N    concerned_by     ---        pull
applies         Decision   -> Pattern            M:N    applied_by       ---        pull

# versioning
supersedes      Node       -> Node (same type)   M:N†   superseded_by    acyclic    link (history)

# semantic
conflicts_with  Node      <-> Node               M:N    (symmetric)      ---        flag
relates_to      Node      <-> Node               M:N    (symmetric)      ---        link
```

`*` `depends_on` should be acyclic; a cycle is a real engineering smell that the
system flags rather than rejects (see [Cycles](#cycles)).
`†` `supersedes` is conventionally 1:1 and linear; M:N is permitted only to record
merges and splits.


## Edge definitions

### Structural

**belongs_to** — `Node -> Project | global`. The single scope assignment every
non-Project node carries. Exactly one per node. This is a partition, not a
reasoning edge: it answers "where does this live," and it is the filter the
retrieval layer applies first. Its inverse, `contains`, lets a Project enumerate
its knowledge.

**part_of** — `Component -> Component`. Composition. A module is part of a
service; a function is part of a module. Forms a containment tree (acyclic). When
an agent loads a Component, it pulls the parent for orientation but not the full
subtree. Distinct from `depends_on`: containment is "is inside," dependency is
"needs."

### Dependency

**depends_on** — `Component -> Component`. A runtime, build-time, or data
dependency. The `attributes.kind` field records which. This is the edge an agent
walks to answer "what breaks if I change this." Followed one hop by default;
full transitive closure is computed on demand. Should be acyclic — a cycle is
captured (reality matters) but surfaced as a warning worth a Lesson.

**builds_on** — `Decision -> Decision`. A later decision that presupposes an
earlier one without replacing it (choosing a service mesh builds on the prior
choice of microservices; both remain active). Contrast with `supersedes`, which
*replaces*. Acyclic. Followed on demand when an agent needs the decision lineage.

### Causal and provenance

**motivates** — `Lesson -> Decision | Pattern`. The lesson is the reason the
decision was made or the pattern was created. This is how empirical experience
becomes traceable cause: an agent reading a Decision can follow `motivated_by`
to find the incident that prompted it. Pulled into context, because the
motivating evidence is usually load-bearing for "why."

**derived_from** — `Pattern -> Lesson`. The pattern was distilled from one or
more lessons. This records the promotion path from raw experience to reusable
rule. Pulled, so the agent can cite the evidence behind a prescription.

**establishes** — `Decision -> Pattern`. A decision that *creates* a new pattern
("we will standardize on this approach everywhere"). This is the second birth
route for a Pattern; the first is `derived_from` a Lesson. Use `establishes` when
the pattern is decreed by a choice, `derived_from` when it is distilled from
experience. A pattern may have both.

**influences** — `Preference -> Decision | Pattern`. A standing personal default
shaped this decision. Followed on demand; preferences are background, not usually
load-bearing for understanding a system, but they explain "why this engineer
tends to choose X."

### Reference

**affects** — `Decision -> Component`. The decision changes or constrains this
component. The primary link between intent and reality. Pulled in both
directions: from a Decision to see what it touches, and from a Component
(`affected_by`) to see what governs it.

**concerns** — `Lesson -> Component`. The lesson is about this component. Pulled
from the Component side so that loading a service surfaces the times it bit
someone.

**applies** — `Decision -> Pattern`. The decision adopts an existing pattern.
Contrast with `establishes`, which creates one. Pulled, so an agent reading a
Decision understands which convention it is an instance of.

### Versioning

**supersedes** — `Node -> Node` (same type only). The backbone of evolution. The
new node points at the one it replaces; the old node's `status` becomes
`superseded`; the edge is permanent history. Must be acyclic. Conventionally
1:1, forming a linear chain whose head is the current truth. M:N is reserved for
consolidations (many old → one new) and splits (one old → many new), recorded in
`attributes`. Followed on demand only — superseded nodes are history and are not
pulled into normal context (see [Lifecycle](#lifecycle-interactions)).

### Semantic

**conflicts_with** — `Node <-> Node`, symmetric. Two nodes that cannot both hold
— two patterns that prescribe opposite things, a preference contradicted by a
project decision. The agent does not pull conflicting content into context; it
*flags* the conflict so the contradiction is visible rather than silently
resolved. This is how the reasoning layer avoids confidently citing two
incompatible rules at once.

**relates_to** — `Node <-> Node`, symmetric. The generic escape hatch for an
association none of the typed edges captures. Carries a mandatory `note`
explaining the link. Use sparingly; a recurring `relates_to` shape is a signal
that a new typed edge is needed.


## Cardinality

Most edges are many-to-many: a Decision affects many Components, a Component is
affected by many Decisions.

The exceptions are structural. `belongs_to` is N:1 and mandatory — every node has
exactly one scope. `part_of` is N:1 — a Component has at most one parent, forming
a tree. `establishes` is 1:N from the pattern's side — a Pattern is established by
at most one Decision, though a Decision may establish several.

`supersedes` is the subtle one. The model permits M:N, but the convention and
the default UI is strictly 1:1: one node supersedes one node, producing a clean
version chain. Many-to-many exists only so merges and splits are representable,
and any such edge should carry an `attributes.reason`.


## Cycles

| Edge | Rule |
| --- | --- |
| `belongs_to`, `part_of` | Acyclic, enforced. A containment cycle is a data error and is rejected. |
| `supersedes`, `builds_on`, `establishes` | Acyclic, enforced. A node cannot transitively supersede or build on itself. |
| `depends_on` | Acyclic *preferred*. A cycle is accepted (it may reflect real, if regrettable, architecture) but raised as a warning and is a candidate for an auto-generated Lesson. |
| `relates_to`, `conflicts_with` | Symmetric; cycle has no meaning and is ignored. |

The distinction matters: structural and versioning cycles are impossible by
definition, so the system forbids them. A dependency cycle is *possible in
reality*, so the system records it and complains, rather than refusing to capture
the truth.


## Traversal

When an agent has a task, it retrieves a seed set of nodes (scope filter plus
relevance) and then expands the graph along edges. Each edge carries one of three
policies that govern that expansion:

- **pull** — follow automatically during context assembly. The neighbor is
  load-bearing for understanding the seed node.
- **link** — do not follow automatically. Surface that the edge exists, and
  follow it only when the query is explicitly about it (typically "why did this
  change," "what is the lineage").
- **flag** — never pull content, but raise the existence of the edge as a signal.
  Reserved for `conflicts_with`.

Expansion is **bounded**. `depends_on` is followed one hop by default; the full
dependency tree is computed only on an explicit "what does this transitively
depend on" query. This keeps the assembled context economical regardless of how
large the graph grows.

Expansion **respects lifecycle**. `pull` edges follow only to `active` nodes.
Reaching a `superseded` node, the traversal resolves the supersession chain to
its head and pulls *that* instead, unless the query is historical. This is why
`supersedes` is a `link` edge: history is available, but it does not clutter
normal reasoning.

A typical assembly from a single Component seed pulls: its `part_of` parent, its
one-hop `depends_on` neighbors, the active Decisions that `affect` it, the
Lessons that `concern` it, and the Patterns those decisions `apply`. It flags any
`conflicts_with` it encounters. It does not pull superseded decisions or
influencing preferences unless asked.


## Lifecycle interactions

When a node is **superseded**, its outgoing semantic edges (`affects`, `applies`,
`concerns`) are *not* migrated to the successor. The successor asserts its own
edges; the old node keeps its edges intact as a historical record of the world as
it was. Migrating edges would erase the difference between "what is true now" and
"what was true then," which is precisely the difference the reasoning layer
exists to preserve.

The `supersedes` edge itself is permanent and is never removed.

When a node is **deprecated** (no longer true, not replaced), its edges remain but
every traversal treats them as `link` — reachable on demand, never pulled.

**Referential integrity** is strict. A node that other edges point to cannot be
hard-deleted; it must be superseded or deprecated. Hard deletion is reserved for
genuine mistakes (a node captured in error) and cascades by removing the dangling
edges with it. In practice, nodes are almost never deleted — that is the meaning
of "append-mostly."


## Validity constraints

The legal (from-type, edge, to-type) triples. Any edge outside this set is
rejected at write time. This is the relational counterpart to the entity set: it
is what makes "everything is one of these" true for connections.

```
belongs_to     : Project | Component | Decision | Pattern | Lesson | Preference  ->  Project | global
part_of        : Component                       ->  Component
depends_on     : Component                       ->  Component
builds_on      : Decision                        ->  Decision
motivates      : Lesson                          ->  Decision | Pattern
derived_from   : Pattern                         ->  Lesson
establishes    : Decision                        ->  Pattern
influences     : Preference                      ->  Decision | Pattern
affects        : Decision                        ->  Component
concerns       : Lesson                          ->  Component
applies        : Decision                        ->  Pattern
supersedes     : X                               ->  X        (same concrete type; not Project)
conflicts_with : Decision | Pattern | Preference <-> Decision | Pattern | Preference
relates_to     : any                             <-> any
```

Two deliberate exclusions worth naming. A Preference never links to a Component —
preferences are about *how the engineer works*, not about *what exists*; the path
from a preference to reality always runs through a Decision. And `supersedes`
never applies to Projects — a project is archived, not superseded, because its
knowledge stays valid history even when the project ends.


## How AI uses the graph

The retrieval contract from `core-model.md` becomes concrete here. An agent:

1. Filters by **scope** (`belongs_to` = current Project or `global`).
2. Selects a **seed** by relevance.
3. **Expands** along `pull` edges, bounded by depth and gated by lifecycle.
4. **Flags** conflicts it crosses.
5. Offers `link` edges (history, lineage, influencing preferences) as
   follow-ups the agent can pull if the question turns to "why."

The result is a small, current, internally consistent slice of your accumulated
engineering knowledge — assembled by walking the graph the way you would walk it
yourself, but instantly and without forgetting.