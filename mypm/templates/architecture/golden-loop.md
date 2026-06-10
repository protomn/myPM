# myPM — The Golden Loop

## Why this is the heart

Everything built so far is inert on its own. The six entities are a vocabulary.
The edges are a grammar. The philosophy is a reason. None of them, by themselves,
makes the system *learn*. A memory store that you only ever read from is a filing
cabinet, and a filing cabinet does not get smarter when you open it.

The Golden Loop is what makes it get smarter. It is the cycle that converts the
act of *using* myPM into new knowledge, structures that knowledge so it
compounds with everything already there, and feeds it back so the next use starts
from a better place than the last. It is the mechanism behind the one promise in
the mission statement that is otherwise just a slogan: a *continuously learning*
collaborator. The collaborator learns continuously because this loop turns,
continuously.

Every other part of the architecture exists to make one turn of this loop happen
well.


## The loop

```
        ┌─────────────────────────────────────────────────────────────┐
        │                                                              │
        ▼                                                              │
   ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐  │
   │  RECALL  │ ───> │  REASON  │ ───> │ CAPTURE  │ ───> │ DISTILL  │ ─┘
   └──────────┘      └──────────┘      └──────────┘      └──────────┘
   system reads      you + AI work     work becomes      knowledge
   the relevant      with knowledge    structured,       matures, links,
   slice into        in hand           linked memory     supersedes,
   context                                               reconciles
```

Four phases. The output of the fourth is a richer graph, which is the input to
the next Recall. The loop closes, and closing is the whole point.


## The four phases

### 1. Recall — the system reads

Before work begins, the reasoning layer assembles the relevant slice of memory
and loads it into the AI's context. This is the retrieval contract from
`relationships.md` made operational: filter by scope (current project plus
`global`), select a seed by relevance, expand along `pull` edges, resolve
supersession chains to their living head, and flag any conflicts crossed. The AI
arrives at the task already knowing your decisions, your components, the lessons
you paid for, and the patterns you trust.

*Who acts:* the system, automatically. *Consumes:* the graph. *Produces:* a
small, current, internally consistent context. This is the only phase that does
not consume the human's attention, and it is the phase that makes the other three
worth doing.

### 2. Reason — you and the AI work

The actual engineering happens here, now informed rather than ignorant. The AI
applies the patterns it recalled, respects the decisions already made, and steers
around the failures recorded as lessons. This is the payoff phase: the single
moment where accumulated knowledge is spent rather than gathered. If the prior
loops did their job, the AI does not re-derive your conclusions or re-make your
mistakes. It builds on them.

*Who acts:* the human and the AI together. *Consumes:* the recalled context.
*Produces:* engineering work, and — as a byproduct — the raw material for the
next phase.

### 3. Capture — work becomes knowledge

Real work produces new knowledge whether or not anyone records it. A decision got
made. A surprise was discovered. A component changed shape. Capture is the act of
turning that exhaust into structured memory: each new fact is typed as one of the
six entities, scoped, and linked to what already exists, entering as a `draft`.

Authorship matters here, exactly as the philosophy insists. The AI, which was
present for the work, *proposes* the captures — it drafts the decision record,
suggests the lesson, points at the components touched. The human is the author of
record who approves, corrects, or discards. This is where the loop stays
trustworthy. An unsupervised capture phase is how a memory system poisons itself.

*Who acts:* the AI proposes, the human authors. *Consumes:* the work. *Produces:*
new draft nodes and edges.

### 4. Distill — knowledge matures

Raw captures are not yet good knowledge; they are notes. Distillation is the
consolidation step that makes them durable: drafts are promoted to `active`,
observations harden into lessons, and lessons that recur are promoted into
patterns (`derived_from` the evidence that produced them). Stale nodes are
superseded by the truth that replaced them, and contradictions surfaced by
`conflicts_with` are reconciled by a human deciding which belief survives.

This is the phase that enforces "less, but relevant." Without it, Capture just
grows a hoard and every future Recall gets noisier. Distillation is where the
signal is kept and the noise is retired.

*Who acts:* the human, with the AI suggesting promotions and flagging conflicts.
*Consumes:* draft and aging nodes. *Produces:* a smaller, sharper, more connected
graph.


## Two cadences

The loop runs at two speeds, and conflating them is a common way to get it wrong.

The **fast loop** is Recall → Reason → Capture. It runs every task, every
session, in the flow of work. It must be cheap and nearly frictionless, or people
stop closing it and the system decays into a read-only archive.

The **slow loop** is Distill. It runs periodically — at the end of a project, on
a weekly review, when a pattern starts to repeat — as a deliberate consolidation
pass. It is allowed to be slower and more thoughtful, because its job is judgment:
what generalizes, what is now wrong, what two beliefs cannot both be true.

The analogy is to how memory actually works. You act and record in the moment;
you consolidate later. myPM separates the two on purpose.


## Why it compounds

Each turn of the loop leaves the graph with more `active`, better-linked, more
distilled knowledge than it had before. Because Recall reads that graph, the next
turn begins with a richer context. Better context produces better reasoning,
better reasoning produces sharper captures, and sharper captures distill into
more reusable patterns. The loop is *golden* because every revolution makes the
next one more valuable. This is a flywheel, not a treadmill.

And because the graph is global with scope as a filter, the compounding crosses
project boundaries. A pattern proven on one system is recalled on the next for
free. A mistake made once becomes a lesson that is recalled everywhere, so it is
made at most once across an entire career. This is the north star expressed as a
mechanism: knowledge that survives, compounds across projects, and arrives in
context at the moment it is needed.


## How it breaks

The loop is golden only when it is complete. Each phase guards against a specific
failure, and skipping one lets that failure back in.

Skip **Recall** and the AI is amnesiac again — every session starts from zero, and
nothing the system holds is ever spent. You are back to re-explaining your world
each morning.

Skip **Capture** and the loop never closes. You read from memory but never write
to it, so nothing compounds. The flywheel is disconnected; the system is a static
archive that ages out of date.

Skip **Distill** and you get the hoard the philosophy warns about. Captures
accumulate faster than they are refined, noise outgrows signal, conflicts pile up
unresolved, and Recall slowly degrades until the relevant fact is buried under
ten thousand drafts.

Reason **without honoring** what was recalled — the AI ignores the lesson it was
handed — and the knowledge is present but unused, which is worse than absent,
because it teaches the engineer that the system can be ignored.

The four phases are not a pipeline of conveniences. They are a set of mutual
guarantees. Each one is the reason another one is safe to trust.


## A single turn

A concrete pass, to make the abstraction land. The task: add rate limiting to the
public API.

- **Recall.** The system loads the `public-api` Component, the Decision that
  settled on the current gateway, a Lesson from a past incident where unbounded
  retries caused a thundering herd, the global Pattern that says limiters should
  fail closed, and the engineer's standing Preference for Redis-backed counters.
- **Reason.** With the thundering-herd lesson in hand, the AI proposes a
  token-bucket limiter on Redis that fails closed under error. It does not
  reinvent the incident, because it was reminded of it.
- **Capture.** The work yields a new Decision ("token bucket over sliding window,
  for these reasons") that `affects` the gateway Component and `applies` the
  fail-closed Pattern. The AI drafts it; the engineer approves it.
- **Distill.** Weeks later a second service needs the same thing. The recurring
  approach is promoted into a new Pattern, "standard rate-limiting setup,"
  `derived_from` both decisions and scoped `global`.

The next time any API work begins, that pattern surfaces in Recall, and a third
service inherits the whole hard-won approach for free. One turn of the loop;
knowledge that has crossed three projects and will cross every one after.


## The one line

> The Golden Loop is the cycle by which using myPM makes myPM
> worth using more.

Recall, Reason, Capture, Distill, and around again. The collaborator learns
continuously because this is the thing that never stops turning.