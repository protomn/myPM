# myPY — Core Model

## Purpose

myPM is a persistent engineering memory and reasoning layer. It exists
to answer one question:

> How does an engineer accumulate knowledge across projects, and make AI aware
> of it?

The answer is a typed knowledge graph. An engineer's accumulated knowledge is
captured as discrete nodes, each scoped to a context and linked to related
nodes. An agent retrieves the relevant subset on demand, so it reasons with your
history instead of from a blank slate.

This document defines the **core entities**. Everything in the system is one of
these. If a piece of knowledge does not fit cleanly into exactly one entity, the
model is wrong and should be revised — not the knowledge bent to fit.


## Design principles

The model is deliberately small. Six concrete entities, one shared base. The set
is chosen to be **orthogonal** (any given fact belongs to exactly one type) and
**complete** (every kind of engineering knowledge worth remembering has a home).

Each entity is distinguished by its *epistemic kind* — what kind of claim it
makes about the world:

- **Component** is descriptive. It says what exists.
- **Decision** is intentional and historical. It says what we chose, and why, at
  a point in time.
- **Pattern** is prescriptive. It says how something should be done.
- **Lesson** is empirical. It says what experience taught us.
- **Preference** is subjective and standing. It says how the engineer likes to
  work by default.
- **Project** is contextual. It scopes everything else.

Two facts about the same real-world thing can legitimately produce nodes of
different types — that the auth service uses JWTs (Component), the choice to use
JWTs over sessions (Decision), the rule "issue short-lived tokens" (Pattern).
These are linked, not merged. Keeping them separate is what lets the system
answer "what is it" and "why is it that way" as independent queries.

Knowledge is append-mostly. Nodes are not deleted when they go stale; they are
*superseded* or *deprecated*, preserving the trail of why a position changed.
That trail is the substance of the reasoning layer.


## The base entity: Memory Node

Every entity inherits a common envelope. Concrete types add their own fields on
top.

```
MemoryNode {
  id          string        // stable unique identifier
  type        EntityType    // project | component | decision | pattern | lesson | preference
  title       string        // short human label
  body        string        // the content, written to be read by both humans and an agent
  scope       Scope         // project:<id> | global
  status      Status        // draft | active | superseded | deprecated
  confidence  Confidence    // low | medium | high  (how settled this knowledge is)
  source      Source        // where it came from: conversation | commit | pr | incident | manual | external
  tags        string[]
  links       Edge[]        // typed relationships to other nodes (see Relationships)
  created_at  timestamp
  updated_at  timestamp
}
```

`body` is the field an agent reads. Write it as a compact, self-contained
summary so it can be injected into context cheaply, not as a sprawling document.

`source` is provenance, not the content itself. myPM stores a pointer
to the originating commit / PR / conversation, never a copy of raw logs.


## The six core entities

### 1. Project

A bounded engineering context that scopes knowledge — a repository, a service, a
product surface, or a client engagement. Every other node belongs either to a
Project or to the special `global` scope (knowledge that applies everywhere).

The Project node itself carries identity and a high-level description: purpose,
stack, key repositories, and lifecycle status.

It answers: *what context am I in, and what is it?*

It is **not** a task board, sprint, or backlog. myPM remembers; it does
not track work.

```
Project extends MemoryNode {
  name        string
  description string        // what this project is and why it exists
  stack       string[]      // primary languages, frameworks, infra
  repos       string[]      // references, not contents
  lifecycle   active | maintenance | archived
}
```

### 2. Component

A descriptive fact about something that exists in a system: a service, module,
data store, interface, or external dependency. The map of the territory.

It answers: *what exists, and how is it wired?*

It is **not** the reason something is built that way (that is a Decision), and
**not** a rule for how to build such things (that is a Pattern). A Component
describes current reality; it makes no recommendation.

```
Component extends MemoryNode {
  name        string
  kind        service | module | datastore | interface | dependency | infra
  description string        // role and behavior
  location    string        // repo path or URL reference
  // depends_on relationships expressed via links
}
```

### 3. Decision

A recorded intentional choice: the situation, the options considered, the option
taken, and the rationale — captured at a point in time and given a lifecycle.
This is the classic architecture decision record.

It answers: *why is it this way?*

It is **not** a standing personal stance (that is a Preference, which is
subjective and cross-project), and **not** a statement of current state (that is
a Component). A Decision is justified by the specific tradeoffs of its context.

```
Decision extends MemoryNode {
  context       string      // the forces and constraints at the time
  choice        string      // what was decided
  alternatives  string[]    // options considered and rejected
  rationale     string      // why this option won
  consequences  string      // what this commits us to
  decided_at    timestamp
  // supersedes / superseded_by relationships expressed via links
}
```

### 4. Pattern

A prescriptive, reusable solution shape: "when you face situation X, do Y." A
convention or recipe distilled from repeated practice.

It answers: *how should I do this here?*

It is **not** a one-time choice tied to a single context (that is a Decision),
and **not** a description of how things currently happen to be (that is a
Component). A Pattern prescribes; it is meant to be reapplied.

```
Pattern extends MemoryNode {
  applicability string      // when this pattern applies
  solution      string      // what to do
  example       string      // a concrete instance
  anti_patterns string[]    // what this pattern replaces or warns against
  // derived_from relationships to Lessons expressed via links
}
```

### 5. Lesson

Empirical knowledge gained from experience, often corrective. This is where
incidents, postmortems, surprising bugs, and "I won't do that again" live. An
incident is represented as a Lesson whose `source.type` is `incident`, with the
event timeline captured in `trigger` — there is no separate Incident entity.

It answers: *what did we learn, often the hard way?*

It is **not** yet a prescription (a Lesson can *motivate* a Pattern, but the
Pattern is a distinct, promoted node), and **not** a deliberate choice.

```
Lesson extends MemoryNode {
  trigger     string        // what happened: the incident, mistake, or surprise
  root_cause  string        // why it happened
  takeaway    string        // the durable learning
  // motivates (Decision | Pattern), concerns (Component) via links
}
```

### 6. Preference

A standing, subjective stance about how the engineer likes to work. Usually
`global`, occasionally overridden per Project. Tooling choices, style defaults,
workflow habits.

It answers: *how do I want things done by default?*

It is **not** justified by project-specific tradeoffs (that would make it a
Decision), and it makes no claim to objective correctness. It is a default that a
local Decision can override.

```
Preference extends MemoryNode {
  statement   string        // the stance, e.g. "prefer pnpm over npm"
  strength    strong | weak | default
  rationale   string        // optional
  overridable boolean       // may a project-local Decision override this?
}
```


## Disambiguation rules

Most capture errors come from the same handful of confusions. The single axis
that resolves nearly all of them is *what kind of claim is this?*

- **Component vs. Pattern** — descriptive vs. prescriptive. "Our API uses
  cursor pagination" is a Component (it states current reality). "Use cursor
  pagination for list endpoints" is a Pattern (it tells you what to do). The
  same topic, two nodes, linked.

- **Component vs. Decision** — state vs. the reason for the state. "Auth uses
  JWTs" is a Component. "We chose JWTs over server sessions because we run
  stateless edge workers" is a Decision. The Decision links to the Component it
  affects.

- **Decision vs. Preference** — local-and-justified vs. standing-and-subjective.
  A Decision is bound to a context and defends itself with tradeoffs. A
  Preference is a cross-project default with no obligation to justify itself. A
  Preference *influences* Decisions; it does not replace them.

- **Lesson vs. Pattern** — what happened vs. what to do about it. A Lesson is a
  past event and its takeaway. When a Lesson recurs or generalizes, you *promote*
  it into a Pattern and record the `derived_from` link. Keep both: the Lesson is
  the evidence, the Pattern is the rule.

- **Where incidents go** — a Lesson with `source.type = incident`. If your team
  later decides incidents need their own first-class lifecycle (on-call rotation,
  severity, action items), promote Incident to a seventh entity then. Until that
  need is real, folding it into Lesson keeps the core orthogonal.


## Relationships

Edges are what make this a reasoning layer rather than a filing cabinet. An agent
expands from a relevant node along these edges to assemble context.

```
belongs_to     : Node      -> Project | global
depends_on     : Component  -> Component
affects        : Decision   -> Component
concerns       : Lesson     -> Component
applies        : Decision   -> Pattern
derived_from   : Pattern    -> Lesson
motivates      : Lesson     -> Decision | Pattern
influences     : Preference -> Decision
supersedes     : Node       -> Node        (same type)
relates_to     : Node       -> Node        (generic, use sparingly)
```

`supersedes` is the backbone of evolution: the new node points back at the one it
replaces, the old node is marked `superseded`, and the history stays queryable.


## What is not in the model

Defining the boundary is as important as defining the entities. The following are
explicitly out of scope:

- **Tasks, tickets, TODOs, sprints.** myPM is memory, not a tracker.
  Those live in your issue tracker; a node may reference one, but never owns it.
- **Secrets and credentials.** These belong in a secret manager. The system may
  note *that* a secret exists, never its value.
- **General world knowledge.** Facts the model already knows (how TCP works, what
  `EAGAIN` means) are not stored. The system holds *your* contextual, accumulated
  knowledge, not the public corpus.
- **Source code.** Code lives in git. A Component *references* code by location;
  it does not duplicate it.
- **Raw conversation or log transcripts.** Captured only as `source` pointers,
  never copied in full.


## Lifecycle and capture

Nodes move through `draft -> active -> superseded | deprecated`.

- **draft** — captured quickly, possibly mid-conversation, not yet reviewed.
- **active** — settled knowledge an agent should treat as current.
- **superseded** — replaced by a newer node; retained for the why-we-changed
  trail.
- **deprecated** — no longer true and not replaced; retained as history.

Capture can be manual or semi-automatic. A merged PR can emit a draft Decision; a
resolved incident can emit a draft Lesson; recurring Lessons suggest promotion to
a Pattern. Promotion (Lesson → Pattern, draft → active) is where the system does
its "learning": raw experience is distilled into reusable knowledge over time.


## How AI becomes aware

An agent does not load the whole store. It retrieves a working set:

1. **Scope filter** — the current Project plus `global`.
2. **Relevance** — semantic and tag match against the task at hand.
3. **Graph expansion** — follow edges out from matched nodes (a matched Component
   pulls in the Decisions that `affect` it and the Lessons that `concern` it).

The selected nodes' `body` fields are injected into the agent's context. Because
each `body` is written as a compact summary with provenance attached, the agent
reasons over your accumulated history at a controllable token cost — and can cite
where each piece of knowledge came from.

That is the whole point: a stateless assistant becomes a collaborator that
remembers what you decided, why, what broke, and how you like to work.