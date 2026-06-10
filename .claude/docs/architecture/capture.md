# myPM — Capture

## Where Capture sits

Of the four phases of the Golden Loop, three are now concrete. Recall is the
retrieval pipeline in `storage.md`. Reason is the council of agents. Distill is
mostly defined, owned by the Reflection Analyst. Capture is the one still waving
its hands: knowledge "enters the graph" somehow, "the AI proposes and the human
authors," and the specifics were left for later. Later is now.

Capture is the phase that decides what is worth remembering and at what cost. Get
it wrong in one direction and nothing is captured, the loop never closes, and the
system decays into a read-only archive. Get it wrong in the other and everything
is captured, the graph becomes the hoard the metrics doc rejects, and Recall
drowns. This document defines the discipline that avoids both: exactly what
creates a node, exactly what becomes a node, and exactly what it takes to promote
raw experience into reusable knowledge.

When this is defined, the architecture is complete and the system is buildable.


## The principle: friction belongs at promotion, not at capture

Every capture system faces one tension. Capturing must be nearly free, or a busy
engineer in the middle of real work will not do it, and uncaptured knowledge is
lost knowledge. But enshrining must be expensive, or every passing thought becomes
permanent "knowledge" and the graph fills with noise that no longer recalls
anything useful.

The resolution is to put the friction in the right place. Observing costs almost
nothing — a stray remark in conversation is captured automatically, with no
ceremony and no commitment. Enshrining costs judgment — turning that remark into
recallable knowledge, and especially into a reusable rule, requires passing
deliberate gates. Friction at the bottom of the ladder kills capture. Friction at
the top of the ladder is the entire point: it is the mechanism that enforces
"less, but relevant."


## The capture ladder

Knowledge climbs a ladder. The rungs are tiers of maturity; the spaces between
them are gates that cost judgment to cross.

```
   INBOX  · · · · · · · · ·│· · · · · · · · · · · · THE GRAPH · · · · · · · · · · · · ·
                           │
   Observation ──Gate 1──> draft node ──Gate 2──> active node ──Gate 3──> Pattern
   untyped, raw,  admit &  typed, in    verify,    recallable,  recurs &  reusable
   near-free      type     graph, not   approve    spendable    general-  prescriptive
                           yet recalled            knowledge    izes      rule
                                                                (Lessons only)
```

**An Observation is not a seventh entity.** This is the crucial reconciliation
with `core-model.md`, which states that everything *in the graph* is one of the
six types. An Observation is not in the graph. It is a raw, untyped capture that
lives in a staging inbox *before* it becomes anything. The graph still holds only
Projects, Components, Decisions, Patterns, Lessons, and Preferences. The inbox
holds the not-yet-knowledge from which some of those nodes will be born and most
of which will, correctly, evaporate.

This adds exactly one element to the storage layout from `storage.md`:

```
knowledge/
├── inbox/            # NEW: raw observations, untyped, append-only, pre-graph
│   └── 2026-02-11.md
├── global/nodes/     # the graph: only the six types live here
├── projects/<id>/nodes/
└── edges/
```

An observation is a single cheap line, not a document:

```
# knowledge/inbox/2026-02-11.md
- 09:12Z [conversation] allocator overhead is terrible — serializer hot path
- 14:40Z [benchmark]    stack buffer cut p99 from 1.8ms to 0.4ms
```

The inbox is exempt from the build validation that governs `nodes/` and `edges/`,
because it is not yet structured. It is the one place in the system where raw,
unjudged text is allowed to land.


## The three gates

This is the heart of the document, and the part the rest of the architecture has
been pointing at. Each gate is a threshold with a named test. The agent proposes
at every gate; the human authorizes at every gate. Promotion is never automatic,
because automatic promotion is how a memory system launders noise and
hallucination into permanent record.

### Gate 1 — Observation becomes a draft node

The question: *does this raw signal deserve to enter the graph at all, and as
what?*

The test is the **Future-Recall Test**: would I, or another engineer, or another
project, want this surfaced at some future moment of relevance? If the honest
answer is no, it stays an observation and is allowed to evaporate. Supporting
criteria, all required:

- **Specific** — it names a real thing, not a mood. "Allocator overhead is
  terrible" is a mood. "Allocator overhead dominates the serializer hot path" is
  specific.
- **Durable** — it will still be true and relevant tomorrow, and on a different
  project. Transient frustration is not durable.
- **Typeable** — it fits one of the six entity types. The agent proposes the type;
  if nothing fits, it is not graph material.
- **Non-redundant** — it is not already a node. Capture dedupes against the graph
  before admitting.
- **Minimally structured** — it carries at least the skeleton its type demands. A
  Lesson needs a takeaway; a Decision needs a choice and a rationale. The source
  must supply this or the observation is not ready.

Pass, and the observation is typed and written as a `draft` node, linked to what
it relates to. This is the work of `/reflect`. It is the close of the Capture
phase.

### Gate 2 — Draft becomes active

The question: *is this true, complete, and connected enough to be trusted by
Recall?*

The test is the **Substantiation Test**. A draft is a claim; an active node is a
claim that has earned its place. Required:

- **Approved by the human** — the author of record has reviewed the draft, as the
  git PR they review and merge. This is "the human authors" made literal.
- **Substantiated** — the claim is established, not guessed. A Lesson's root cause
  is actually diagnosed; a benchmark Lesson carries its numbers; a Decision
  records real alternatives and real consequences.
- **Well-formed** — it passes the schema and validity checks from `storage.md`.
- **Linked** — it is wired into the graph by its edges. An unlinked node is nearly
  unrecallable, an orphan no traversal will ever reach. Connection is not optional
  metadata; it is the difference between knowledge and a buried note.

Until a draft passes, it stays a draft and is excluded from general Recall, per
the lifecycle in `storage.md`. This and the next gate are the work of `/distill`.

### Gate 3 — Lesson becomes Pattern

The question: *has this happened enough, in enough places, to become a rule?*

This is the gate the user called "literally where learning happens," and it is.
The test is the **Recurrence Test**, and the signal is repetition:

- **Recurrence** — the same lesson-shape has appeared at least twice, or, far more
  powerfully, across at least two projects. One occurrence is a Lesson. Repetition
  is a Pattern. Cross-project recurrence is the gold standard, because it is the
  exact thing the cross-project metric in `success-metrics.md` is built to reward:
  a mistake made at most once across a career rather than once per project.
- **Prescriptive** — it can be restated as a rule, "when you face X, do Y," rather
  than a story about one time something happened.
- **Stable** — it has held up and has not been superseded.

Pass, and the Reflection Analyst proposes a new Pattern, wires `derived_from` back
to the source Lessons as its evidence, and scopes it `global` if it crossed
project lines. The human confirms. The defaults — two occurrences, two projects —
are tunable thresholds, not constants; the right numbers come from real traffic,
not from this document.


## A worked example

Walk the user's own example, "allocator overhead is terrible," up the entire
ladder. This is the system end to end.

1. **Conversation.** The engineer says it mid-work. Ambient capture writes it to
   the inbox as an **Observation**. It is not a Lesson. It is not a draft. It is a
   line of raw text that cost nothing to keep.

2. **`/reflect`, Gate 1.** The Reflection Analyst surfaces the observation. On its
   own, "allocator overhead is terrible" fails the Future-Recall Test: it is a
   mood, not a fact. But it pairs with the benchmark observation from the same
   session — p99 fell from 1.8ms to 0.4ms when heap allocation became a stack
   buffer. Together they are specific, durable, and substantiated. The Analyst
   proposes a **draft Lesson**, `lesson_allocator_overhead`, with a real
   trigger, root cause, and takeaway, linked by `concerns` to the serializer
   Component. The human confirms the type.

3. **`/distill`, Gate 2.** The human reviews the draft, the numbers check out, the
   edges are wired. It is promoted to **active**. It is now recallable, and the
   next time anyone touches that hot path, Recall surfaces it.

4. **`/distill`, Gate 3.** Months later, a benchmark on a *different* project
   produces the same finding. The Reflection Analyst detects the recurrence across
   two projects and proposes promotion to a **Pattern**: "benchmark allocations
   before optimizing any hot path," scoped `global`, `derived_from` both Lessons.
   The human confirms. From now on, every hot-path optimization on every project
   recalls the rule for free.

That is the whole loop, and the answer to the original question. "Allocator
overhead is terrible" is an Observation. It earns its way to a Lesson, and then,
by recurring across projects, to a Pattern. Nothing was forced into the graph
prematurely, and nothing was lost.


## What creates nodes: the sources

Capture has many mouths. They differ in one decisive way: the rung at which their
output enters the ladder. A passing remark enters at the bottom as an observation.
A postmortem, a benchmark, a council review arrive already substantiated and enter
directly as drafts, skipping the inbox, because the ceremony of the source has
already done Gate 1's work.

```
SOURCE                ENTERS AS     TYPICAL OUTPUT                       DRIVEN BY
Conversation          observation   raw signals, most evaporate          ambient (automatic)
PR / Commit           draft         Decision (the "why"), Component edit  /review (OSS Maintainer)
Incident              draft         Lesson (trigger/root cause/takeaway)  /reflect
Benchmark session     draft         Lesson (numbers), Component perf note  /reflect
Architecture review   draft         Decision (council canvas), objections  /architect (the Council)
Research              draft         alternatives, draft Patterns/Components /research
Reflection            (operates the gates, does not itself originate)     /reflect, /distill
```

The principle: **ceremony at the source sets the entry rung.** The more deliberate
and substantiated the source, the higher up the ladder its output enters. Only the
ambient stream of conversation lands in the inbox; everything that arrives through
a deliberate act arrives as a draft. This is why conversation needs the gates most
and a postmortem needs them least.


## Ambient versus deliberate capture

Two modes, cleanly split by who initiates and how much it costs.

**Ambient capture** is automatic and frictionless. As the agent works alongside
the engineer, it writes observations to the inbox without being asked, and a git
hook can propose a draft Decision from a merged PR or a draft Lesson from a closed
incident. The AI is always listening, but listening is cheap and nothing it hears
is yet knowledge.

**Deliberate capture** is the gates, invoked by command. `/reflect` and `/distill`
are where a human sits with the Reflection Analyst and decides what graduates.
This is where judgment is spent and where authorship lives.

The rule across both: **the AI proposes at every tier; the human authorizes at
every gate.** Observations are AI-cheap because they are not knowledge. Nodes are
human-authored because they are. This is the philosophy's authorship principle
made operational at the finest grain.


## The command surface

The architecture becomes user actions here. Five commands, and they are not an
arbitrary menu — they are the Golden Loop made operable. Recall runs
automatically before each one, assembling the agent-appropriate bundle from
`storage.md`.

```
COMMAND     AGENT(S)                  PHASE     PRODUCES / OPERATES
/research   Research Engineer         Reason    solution landscape: alternatives,
                                                draft Patterns, external Components
/architect  Principal + the Council   Reason    a draft Decision as the shared canvas;
                                                convenes Adversarial + Performance
/review     OSS Maintainer / Advers.  Reason    verdict on a change or design; drift
                                                flags; supersede proposals
/reflect    Reflection Analyst        Capture   Gate 1 — admits and types the session's
                                                observations into draft nodes
/distill    Reflection Analyst        Distill   Gates 2 & 3 — promotes drafts to active,
                                                generalizes recurring Lessons to Patterns,
                                                supersedes the stale, prunes the noise
```

Read down the phase column and the loop is right there. `/research`, `/architect`,
and `/review` are Reason, the council deliberating. `/reflect` closes Capture by
running Gate 1 at the end of a work session — the fast loop, every task.
`/distill` runs the Distill phase on the slow cadence, operating Gates 2 and 3 —
the consolidation pass. The split between `/reflect` and `/distill` is exactly the
two cadences from `golden-loop.md`: reflect extracts from a single session,
distill consolidates across many.

This also sharpens the Capture/Distill boundary that `golden-loop.md` left soft.
Typing an observation into a draft (Gate 1) is Capture and belongs to `/reflect`.
Verifying a draft into active knowledge (Gate 2) and generalizing a Lesson into a
Pattern (Gate 3) are Distill and belong to `/distill`.


## What Capture is not

Capture is not transcription. The inbox is not a chat log dumped into the graph;
it is a deliberately thin staging area, and most of what lands there is meant to
evaporate. A capture system that keeps everything has captured nothing useful.

Capture is not autonomous. No observation promotes itself, no draft activates
itself, no Lesson declares itself a Pattern. The AI proposes at every gate and the
human authorizes at every gate, because the moment promotion goes automatic the
record stops being trustworthy and the whole graph is poisoned downstream.

Capture is not measured by volume. The point of the gates is to admit less, not
more. A day that produces fifty observations and one active Lesson was a good day.
A day that produces fifty Lessons produced noise.


## The architecture is complete

```
Core Model        ✓   the six things knowledge can be
Relationships     ✓   how they connect, and how an agent traverses them
Storage           ✓   how it all lives as portable files, and how Recall reads them
Agents            ✓   the six modes of reasoning that spend and produce knowledge
Golden Loop       ✓   the cycle that makes the system learn
Capture           ✓   how knowledge enters: the ladder, the gates, the commands
```

Every phase of the loop is now concrete. Recall retrieves, the agents Reason,
Capture admits, Distill matures, and the commands give a human the verbs to drive
all of it. There is no remaining hand-wave between the idea and the build. The
next document is not a document. It is code.