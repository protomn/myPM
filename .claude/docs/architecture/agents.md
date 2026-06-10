# myPM — Agents

## Why agents

A single general-purpose AI doing "reason" produces a monologue. It decides,
explores, critiques, and measures all at once, in one voice, which means it does
none of them with depth and never argues with itself. Real engineering judgment
does not come from one mind being clever. It comes from distinct stances in
tension: someone proposing, someone exploring alternatives, someone trying to
break it, someone checking the numbers, someone guarding consistency, someone
extracting the lesson afterward.

Agents are the specialized reasoning roles that turn the Reason and Distill phases
of the Golden Loop from a monologue into a deliberation. They stand in the same
relationship to engineering *reasoning* that the six entities stand in to
engineering *knowledge*: an orthogonal, complete set. The entities are the
irreducible kinds of thing worth remembering. The agents are the irreducible
modes of thinking worth separating:

```
decide   explore   attack   measure   gate    learn
   │        │         │        │        │        │
Principal Research  Advers.  Perf.   OSS Mtnr  Reflection
```

Six stances, no overlap, nothing essential left out. Add a seventh and it
collapses into one of these; remove one and a mode of engineering thought goes
dark.

Each agent reads a specific slice of the graph, produces specific entity types,
and creates specific edges. None of them works in isolation; all of them work on
the same graph the rest of the architecture defines.


## The shared contract

Every agent inherits one contract, the way every node inherits the Memory Node
envelope and every link inherits the Edge record.

**Agents propose; they never finalize.** Everything an agent produces enters as a
`draft`, authored by the agent and approved by the human. This is the philosophy's
"the human authors; the AI reads" made operational at the agent layer. An agent
that could commit `active` knowledge on its own is how the graph poisons itself.

**Agents declare their I/O.** Each one names the entities it reads during Recall
and the entities and edges it writes during Capture. An agent that reaches outside
its declared inputs is reasoning from context it was not given, and an agent that
writes outside its declared outputs is overstepping its mandate.

**Agents cite their sources.** Every output stamps `source` provenance and
references the nodes it reasoned from, so any conclusion can be traced back to the
graph state that produced it. An uncited agent conclusion is an unfalsifiable one.

**Agents stay in their lane and hand off.** When work exceeds an agent's mandate,
it escalates to the right agent rather than improvising. The boundaries below are
not suggestions; they are what keep the deliberation orthogonal.


## The six roles

### Principal Engineer

```
phase    : Reason (decide)
reads    : Component, Decision(active), Pattern, Preference, Lesson
produces : Decision  +edges: affects→Component, applies|establishes→Pattern,
           builds_on|supersedes→Decision   consumes: influences←Preference, motivates←Lesson
```

The decisive voice. It asks: *given everything we know and everything we need,
what should we do, and what does committing to it cost us?* It consumes a curated
solution landscape, weighs the options against the real forces and constraints of
the project, and produces a justified choice with its consequences spelled out.

Its method is tradeoff reasoning, not exploration. It does not survey the field
(it receives that from Research) and it does not implement. Its discipline is
honesty about alternatives and consequences: a Decision that records no genuine
rejected options and no real costs is a rubber stamp wearing a decision's clothes,
and the Adversarial Reviewer exists partly to catch exactly that.

It receives the landscape from Research and hands its decision to the Adversarial
Reviewer and Performance Engineer to be attacked before it is allowed to harden.

---

### Research Engineer

```
phase    : Reason (explore)
reads    : problem framing, Component, Decision(to avoid re-treading), Lesson, external sources
produces : Decision.alternatives, draft Pattern(known approaches), draft Lesson(external cautions),
           Component(external dependencies)   source: external | web
```

The divergent voice, working before commitment. It asks: *what are all the
credible ways to do this, and what is the state of the art outside our walls?* It
widens the option space, surveys prior art and libraries, and lays out the
tradeoff axes along which a choice will eventually be made.

Its method is breadth without premature pruning. It must surface options it
personally dislikes, because the Principal Engineer cannot weigh an alternative it
was never shown. It checks the graph first so it does not re-research a dead end
the project already rejected, and it stamps external provenance on every outside
claim so the Principal knows what is verified versus assumed.

It explicitly does *not* choose. The moment a Research Engineer recommends, it has
quietly become a Principal Engineer with none of the accountability. It hands a
structured landscape to the Principal and stops.

---

### Adversarial Reviewer

```
phase    : Reason (attack)
reads    : Decision|design under review, Component(affected), Lesson(prior failures),
           Pattern(anti-patterns), conflicts_with
produces : Lesson(anticipated failure modes), recorded objections→Decision.consequences,
           conflicts_with edges
```

Institutionalized dissent. It asks: *how does this break, what assumption is
unstated, and where is the optimism hiding?* It red-teams the design for
correctness, robustness, security, race conditions, hidden coupling, and
operational risk, and it produces concrete failure scenarios, not vague unease.

Its method is qualitative destruction. It checks the design against the Lessons of
past failures (has this exact mistake bitten us before?) and the catalog of
anti-patterns, and it raises objections the Principal Engineer must either answer
or accept as recorded consequences. Forward-looking failure modes it identifies
become Lessons even before any incident occurs, because an anticipated failure is
knowledge worth keeping.

Its discipline is specificity and restraint. "This might not scale" is not an
objection; "this retries unboundedly and will herd under a downstream timeout" is.
And it surfaces risk, it does not set risk tolerance. The human decides what is
acceptable; the Reviewer only makes sure the risk was seen.

---

### Performance Engineer

```
phase    : Reason (measure)
reads    : Component(hot path) + depends_on chain, Decision(perf-affecting),
           Lesson(perf incidents), Pattern(scaling)
produces : Lesson(bottlenecks, perf profile), Pattern(scaling), Component(perf annotations),
           concerns edges
```

The empirical voice. It asks: *where does this get slow, expensive, or fall over
under load, and at what numbers?* It walks the hot path and its `depends_on` chain
where latency and cost compound, identifies the scaling cliffs, and reasons in
concrete figures: latency budgets, throughput ceilings, memory footprint, dollar
cost per request.

It is distinct from the Adversarial Reviewer along a clean axis. The Reviewer asks
*is the idea sound?*; the Performance Engineer asks *will it scale, and what does
it cost?* One hunts correctness failures, the other hunts quantitative limits.
Where they overlap (a robustness failure that only appears under load), they
collaborate rather than duplicate.

Its discipline is the number. It does not advocate optimization everywhere; it
flags the specific places where the measurements say it matters, and it leaves
everything else alone. Premature optimization is its own failure mode, and a
Performance Engineer that decorates cold paths is no better than one that misses a
hot one.

---

### OSS Maintainer

```
phase    : Reason (gate)
reads    : Decision(active), Pattern(active), Component(touched), Preference, Lesson(regressions)
produces : review verdict, drift flags → reject change | supersedes→Decision,
           Component(reconciled to reality), Lesson(recurring review issue)
```

The gatekeeper, and the agent that connects the graph to concrete code. It asks:
*does this change respect what we have already decided, the patterns we follow,
and the actual shape of the system?* It reviews a diff or a pull request against
the recorded standards, the active Decisions and Patterns that are the law of the
codebase, and the Lessons that say which mistakes must not return.

It is distinct from the Adversarial Reviewer by its input. The Reviewer attacks a
*design* for whether the idea will fail; the Maintainer inspects a *change* for
whether the implementation conforms and integrates. The Reviewer asks "is this
sound?"; the Maintainer asks "does this fit the house?"

Its sharpest job is detecting drift, and routing it correctly. When a change
contradicts an active Decision, exactly one of two things is true: the change is
wrong, or the Decision is now wrong. The Maintainer never silently picks one. It
either rejects the change or proposes a `supersedes` on the stale Decision and
sends it to the Principal Engineer. It also notices when reality has drifted from
the recorded Components and proposes the Capture updates that bring the graph back
in line with the code.

---

### Reflection Analyst

```
phase    : Distill
reads    : draft nodes from the episode, work/incident record, existing Lesson & Pattern,
           conflicts_with
distills : draft→active, observation→Lesson→Pattern (derived_from), supersedes,
           conflicts_with, prune noise   preserves: provenance + supersession history
```

The only agent whose home is the Distill phase rather than Reason, and therefore
the agent that makes the Golden Loop actually loop. It asks: *what did this episode
teach us that should outlive it, and how does it connect to everything we already
know?* It works only from what actually happened, never from imagination.

Its method is consolidation. It promotes drafts to `active`, hardens raw
observations into Lessons, and detects when a Lesson has now recurred across enough
episodes or projects to be promoted into a Pattern, wiring the `derived_from` edge
back to the evidence. It supersedes knowledge that the latest experience has
overturned, surfaces contradictions the work exposed, and retires the noise so
that "less, but relevant" stays true and Recall does not silently degrade.

Its discipline is preservation. It is the custodian of the supersession trail and
the provenance chain, and it never destroys history, only marks it superseded. It
generates no new design ideas; the moment a Reflection Analyst starts inventing
rather than distilling, the record stops being a faithful account of what was
learned and becomes fiction.


## How they compose

The agents are not a menu of independent tools. They run as two choreographed
movements that map directly onto the Golden Loop.

**The Council** runs the Reason phase as a deliberation:

```
Research ──> Principal ──> ┌─ Adversarial ─┐ ──> Principal ──> OSS Maintainer
 (diverge)   (decide)      └─ Performance ─┘     (revise)        (gate change)
                              (attack/measure,
                               in parallel)
```

Research widens the field; the Principal commits; the Adversarial Reviewer and
Performance Engineer attack the commitment from their two angles in parallel; the
Principal revises against what survives; the Maintainer gates the resulting change
against the standards. Knowledge is *spent* here, and freshly *produced* as
drafts.

**The Consolidation** runs the Distill phase on the slow cadence. The Reflection
Analyst takes the drafts the Council produced and the record of what actually
happened, and turns them into durable, connected, deduplicated knowledge that the
next Council's Recall will read.

The unifying artifact is the Decision node, the council's shared canvas. Research
fills its `alternatives`. The Principal fills its `choice` and `rationale`. The
Adversarial Reviewer and Performance Engineer fill its `consequences`. The
Maintainer verifies the change that `affects` it. The Reflection Analyst later
distills the whole episode around it. One record, co-authored by six specialists,
each writing only the part its mandate covers.


## Productive tension is a feature

The Adversarial Reviewer exists to oppose the Principal Engineer, and that
opposition is designed in, not tolerated. A system where the proposer also judges
its own proposal produces confident, brittle decisions. myPM forces a
decision to survive a dedicated attacker and a dedicated measurer before it is
allowed to harden into `active` record. The friction is the quality mechanism.
Remove the dissent to make the loop smoother and you have optimized the system for
producing mistakes faster.


## The human conducts

The agents are advisors and drafters. The human is the conductor and the author of
record. The human invokes the agents, sequences the Council, decides risk
tolerance when the Adversarial Reviewer raises it, picks the surviving belief when
the Reflection Analyst surfaces a contradiction, and approves every draft before it
becomes `active`. No agent finalizes knowledge, none acts outside its mandate, and
none speaks for the engineer. They make the engineer's reasoning deeper, faster,
and harder to fool. They do not replace the engineer who owns it.