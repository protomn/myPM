# Council

## The six mandates

```
Research    explores.
Principal   decides.
Adversarial attacks.
Performance measures.
OSS         gates.
Reflection  learns.
```

Each mandate is exclusive. No agent performs another's. This is not a
preference; it is the structural guarantee that makes the deliberation
orthogonal. An agent that performs two mandates performs both of them worse
than a dedicated agent would, and — more dangerously — makes the council's
output harder to audit, because one voice is now doing two jobs under one name.

The council works because these six cognitive modes are in genuine tension.
Research widens; the Principal narrows. The Adversarial Reviewer destroys; the
Principal must defend or revise. The Performance Engineer measures; the
Principal must accept or reject the implications. The OSS Maintainer holds the
line; the Principal must have authorized what crosses it. Reflection learns from
the whole episode; the Principal will reason better for having that learning the
next time around. Remove any one of these tensions and a dimension of engineering
judgment goes dark.


## The mandate boundaries

The most common and most damaging council failures are mandate violations: an
agent drifting into another's role while appearing to perform its own. They are
named here so they can be recognized.

**Research recommending.** Research surfaces the option space; it does not
advocate for one option. The moment Research says "I recommend option A," it has
produced a verdict without having been attacked or measured. The Principal
Engineer cannot weigh a landscape that has already been tilted. Research's output
ends with tradeoff axes and a complete set of options. It does not end with a
preferred choice.

**The Adversarial Reviewer blocking.** The Reviewer surfaces failure modes and
records them. It does not set risk tolerance. "I will not approve this until X is
fixed" is the OSS Maintainer's sentence, not the Reviewer's. The Reviewer hands
findings to the Principal and to the human; the Principal and human decide what
they mean for the Decision. An Adversarial Reviewer that blocks rather than
informs has become a veto, and vetoes without accountability are how councils
stop deliberating and start negotiating.

**The Principal deciding before Research has run.** The Principal's mandate is to
decide, but the Principal decides *among named options*. A Principal who forms a
view before Research has mapped the space has constrained the landscape before
the engineer saw it. The Principal's authority is over commitment; Research's
authority is over completeness. Both must be honored in sequence.

**The OSS Maintainer reviewing correctness.** The Maintainer inspects systemic
fit — does this change conform to active Decisions and Patterns? It does not
review whether the code is correct in its own terms. That is testing's job and,
where relevant, the Adversarial Reviewer's. An OSS Maintainer who slides into
correctness review is doing a different job less well than the right tool.

**The Reflection Analyst inventing.** Reflection distills what actually happened.
It does not propose new designs, new approaches, or new knowledge not grounded
in the actual record of the episode. An Analyst who starts generating Lessons
from imagination rather than from the work has poisoned the graph: fiction,
labeled as experience, will be recalled as fact.

**Any agent finalizing knowledge.** Every agent produces drafts. The human
approves. Always. An agent that writes `status: active` on its own output has
severed the authorship principle that the entire system's trustworthiness depends
on.


## The Golden Loop

The loop is the whole system in motion. It has two cadences — the fast loop that
runs per significant decision, and the slow loop that consolidates across many
decisions. Both are required. A system that only runs the fast loop accumulates
drafts without distilling them. A system that only runs the slow loop has nothing
to distill.

### The fast loop

```
  RECALL
    │
    ├─ ContextBundle assembled from active graph
    │  (scoped: project + global; agent-reads biased; pull edges expanded)
    │
    ▼
  RESEARCH  (/research)
    │
    ├─ checks graph for prior art first
    ├─ maps the full option space (≥3 options, tradeoff axes, confidence tiers)
    ├─ produces: Decision.alternatives, draft Patterns, draft Lessons
    │
    ▼
  PRINCIPAL  (/architect)
    │
    ├─ frames the real choice (not the problem — the choice)
    ├─ commits to choice + rationale (conditional on context)
    ├─ produces: draft Decision (choice, rationale, proposed edges)
    │
    ▼
  ADVERSARIAL + PERFORMANCE  (parallel, /architect continues)
    │
    ├─ Adversarial: primary failure mode, mechanism named, assumption surfaced
    ├─ Performance: scaling cliff, measurement tier labeled, measurement needed
    ├─ both produce: findings → Decision.consequences
    ├─ both produce: draft Lessons (failures anticipated, performance findings)
    │
    ▼
  PRINCIPAL  (revision pass)
    │
    ├─ integrates findings: answer in rationale, or accept in consequences
    ├─ no finding is silently discarded
    ├─ draft Decision is complete when consequences reflects the attack
    │
    ▼
  HUMAN  (approval)
    │
    ├─ reviews draft Decision: real alternatives? conditional rationale?
    │  honest consequences? attack phase findings present?
    ├─ merges the PR → node status becomes active
    │
    ▼
  OSS MAINTAINER  (/review)
    │
    ├─ checks implementing change against active Decision
    ├─ detects drift in both directions (code ahead of graph, graph ahead of code)
    ├─ produces: verdict, draft Decisions for undocumented choices,
    │  Component updates, supersedes proposals
    ├─ BLOCK + DECISION if change makes undocumented architectural choice
    │
    ▼
  CAPTURE
    │
    ├─ observations written to inbox throughout the above
    ├─ draft nodes produced by all agents during the episode
    │
    ▼  (feeds the slow loop)
```

### The slow loop

```
  REFLECTION ANALYST  (/reflect — per session, Gate 1)
    │
    ├─ surfaces inbox; applies Future-Recall Test to each observation
    ├─ admits: specific, durable, typeable, non-redundant, minimally structured
    ├─ produces: draft nodes (typed, proposed links)
    ├─ evaporates: moods, transients, redundancies (most observations)
    │
    ▼
  REFLECTION ANALYST  (/distill — cross-session, Gates 2 + 3)
    │
    ├─ Gate 2: substantiation + linked requirement → draft to active
    ├─ Gate 3: recurrence across ≥2 occurrences or ≥2 projects → draft Pattern
    ├─ supersedes stale knowledge; surfaces contradictions to human
    ├─ rebuilds SQLite index
    ├─ produces: active nodes, Pattern proposals, supersedes edges,
    │  conflicts_with flags
    │
    ▼
  FUTURE RECALL
    │
    └─ the active nodes from this distillation cycle become the ContextBundle
       ingredients for the next fast loop
       → Research checks the graph and finds prior art it would have missed
       → Principal recalls a Lesson that changes the choice
       → Adversarial Reviewer cites a prior failure Lesson rather than re-deriving it
       → the loop has compounded
```

The loop closes when: a Lesson or Pattern produced by Reflection appears in a
future agent's ContextBundle and changes the direction of a future Decision. That
event — a piece of distilled knowledge preventing a mistake or informing a better
choice in a different context — is the unit of value the system is built to
produce. Everything else is infrastructure for that to happen.

### What each stage produces

```
Stage              Node(s) produced              Edges materialized
─────────────────────────────────────────────────────────────────────────
Research           Decision.alternatives         (none — populates a field)
                   draft Pattern                 (none at draft)
                   draft Lesson                  (none at draft)

Principal          draft Decision                proposed: affects, builds_on,
                                                 supersedes, applies, establishes

Adversarial        findings → consequences       draft Lesson: concerns→Component
Performance        findings → consequences       draft Lesson: concerns→Component

OSS Maintainer     verdict                       draft Decision: affects
                   draft Component (updates)     supersedes proposal
                   draft Lesson (recurring)

Reflection /reflect  draft nodes (typed)         proposed_links (not yet materialized)

Reflection /distill  active nodes                concerns, motivates, derived_from,
                   Pattern proposals             relates_to, supersedes, conflicts_with
```

No stage produces `active` nodes directly. Active status is set by the human
approving the PR. This column is not empty for any stage; if an agent produces
nothing traceable in the graph, it did not run.


## Conflict resolution

The council is designed to produce tension. The resolution rules below are not
escape valves for when the tension becomes uncomfortable; they are the rules for
routing that tension to the right decision-maker. Tension that is not routed
correctly accumulates silently, surfaces as architectural drift, and costs more
to resolve later than it would have at the time.

### Research vs Principal

**Principal wins.**

Research maps the option space; the Principal commits. If Research surfaces an
option after the Principal has committed, the Principal integrates it or explains
why it does not change the choice. Research may push back by surfacing additional
evidence, proposing an alternative framing, or noting that a prior graph node was
not considered. Research may not block.

The rationale: someone must decide, and the Principal is accountable for the
Decision in a way Research is not. Research's authority ends at the landscape;
the Principal's authority begins at the choice. Allowing Research to override the
Principal inverts the accountability structure without clarifying who owns the
outcome.

If Research believes the Principal has committed to a narrowed landscape — an
option space that was constrained before Research finished — this is not a
conflict between Research and Principal. It is a sequencing failure: the Principal
ran before Research was done. Restart the fast loop from Research.

### Adversarial vs Principal

**Human adjudicates.**

The Adversarial Reviewer has identified a failure mode the Principal believes is
acceptable risk. Neither can resolve this unilaterally:

- If the Principal could override the Reviewer, the attack phase is a formality.
  The Principal proposes and also judges the objections to the proposal. The
  council becomes a monologue.
- If the Reviewer could block the Principal, a sufficiently adversarial reviewer
  blocks everything. The Reviewer has no accountability for the cost of inaction.

The human holds the authority that neither agent has: the authority to set risk
tolerance. The human is shown the Principal's rationale and the Reviewer's primary
finding, side by side. The human decides: "I accept this risk" or "I do not; revise
the Decision." Either outcome is valid and both are recorded in `consequences`.
The finding appears in the node regardless of which way the human decides. What
is not allowed is for the finding to disappear without a recorded disposition.

### Performance vs Principal

**Human adjudicates.**

The same structure as Adversarial vs Principal, applied to quantitative risk. The
Performance Engineer has found a scaling ceiling or cost implication the Principal
believes is acceptable given the project's current load or budget. The human
decides whether that assumption is sound, what monitoring would surface the
problem before it becomes an incident, and whether the constraint should be a
named precondition in the Decision.

The Performance Engineer's finding goes into `consequences` with its measurement
tier label regardless of outcome. Future Recall will surface it to whoever next
touches the affected Component; they will see the known ceiling whether or not the
original human chose to act on it.

### OSS Maintainer vs Principal

**Block until resolved.**

The OSS Maintainer has found that an implementing change contradicts an active
Decision. This conflict has exactly two valid resolutions and no third option:

1. **The change is wrong.** The implementation should conform to the active
   Decision. The change is revised until it does.

2. **The Decision is now wrong.** Reality has moved on; the Decision is stale.
   The change is blocked; a `supersedes` proposal is routed back to the Principal
   Engineer; `/architect` runs to produce a new Decision that reflects the current
   intent; the OSS Maintainer re-reviews against the new Decision.

There is no "accept the risk and ship anyway" path for this conflict. Code that
ships while contradicting an active Decision is not a known risk; it is a silent
inconsistency between the graph and the codebase. That inconsistency will be
recalled by future agents as if it were not there, producing advice based on a
graph that no longer describes the system. The cost of that divergence compounds
with every future Decision that builds on the stale record.

The block holds until one of the two resolutions is complete.

### Reflection vs Existing Knowledge

**Human adjudicates.**

The Reflection Analyst has found that a new experience contradicts an existing
active node. A new Lesson says X; an existing active Lesson says not-X. Both are
based on real experience; one may reflect a changed context, an edge case, or a
genuinely overturned prior belief.

The Analyst does not resolve this. It surfaces both sides to the human with the
contradiction clearly stated and three resolution options:

1. **New supersedes old.** The new experience overturns the prior. A `supersedes`
   edge is added; the old node becomes `superseded`; its content is preserved in
   the record.

2. **Old holds; new is an exception.** The prior knowledge is correct for the
   general case; the new experience is a bounded edge case. The new Lesson is
   scoped narrowly and a `relates_to` edge connects both; the exception is
   documented rather than promoted.

3. **Genuine unresolved tension.** Both sides represent real knowledge about a
   genuinely complex domain. A `conflicts_with` edge connects them; both stay
   active; future agents are surfaced the contradiction explicitly. Some
   contradictions in engineering are real and worth preserving.

The human picks one. The Analyst records the outcome. What the Analyst never does
is quietly pick one, because the system's trustworthiness depends on the human
seeing the contradictions the graph contains, not on the AI presenting a cleaned-up,
consistent version of reality that may not exist.


## Council assembly

Not every task requires the full council. The configuration depends on what
kind of work is in front of you.

```
Task                              Agents invoked
───────────────────────────────────────────────────────────────────────────
Major architectural decision       Full council: Research → Principal →
                                   Adversarial + Performance → Human → OSS
New feature with known approach    Principal + Adversarial + OSS (Research
                                   optional if landscape is familiar)
Performance investigation          Performance → Principal (if Decision needed)
Code review                        OSS Maintainer only
End-of-sprint reflection           Reflection Analyst (/reflect + /distill)
Incident postmortem                Adversarial → Reflection (/reflect)
Research spike                     Research only (no Decision yet)
```

The human decides which configuration to invoke. Invoking the full council for
a trivial change wastes the system's credibility — if everything is a major
decision, the council stops being taken seriously. Skipping the attack agents
on a genuinely major decision creates exactly the confident, brittle commitment
the council was built to prevent.

The minimum viable council for any non-trivial Decision: Principal + Adversarial.
The human can extend from there. The minimum viable distillation: Reflection
Analyst after any significant episode. A system that never distills accumulates
drafts indefinitely and its Recall degrades.


## The human's role

The human is not one of the six agents. The human is the **conductor** — the
authority the council reports to, the author of record for all active knowledge,
and the entity whose judgment replaces the council's when the council reaches
the boundary of what it can resolve.

**The human invokes.** Which agents run, in what order, on which problem — these
are engineering judgment calls. The human makes them. An automated orchestrator
that decides which agents to invoke is making those calls without the human's
context, accountability, or ability to recognize when the standard configuration
is wrong for the current situation.

**The human adjudicates.** When the Adversarial Reviewer and the Principal
disagree, when new experience contradicts existing knowledge, when a performance
ceiling becomes a design question — these resolutions require someone who can set
risk tolerance and own the outcome. That person is the human.

**The human authors.** Every active node in the graph was approved by the human.
The agents propose; the human merges the PR and becomes the author of record.
This is not a rubber stamp step — it is the authorship principle the entire
system's trustworthiness depends on. A graph populated by autonomous agents
is not a record of the engineer's knowledge; it is a record of the AI's
proposals. The engineer should not confuse one for the other.

**The human does not do the agents' jobs.** When the Principal is deciding,
the human receives the Decision; the human does not produce the alternatives
and rationale themselves. When the Adversarial Reviewer is attacking, the human
listens to the finding; the human does not simultaneously generate the failure
mode. The point of the council is to give the human agents whose specialized
reasoning extends their own — not to give the agents a human who does their work
for them.


## Council health signals

These are the leading indicators that the council is working as designed, and
the failure signatures that indicate it has drifted.

**Healthy signals:**
- Decision nodes consistently contain real alternatives, conditional rationale,
  and consequences that include the Adversarial Reviewer's primary finding.
- The Adversarial Reviewer finds something non-trivial on most council sessions
  for non-trivial decisions. A council that never produces findings is either
  reviewing trivial decisions or not running the attack phase with force.
- Cross-project recurrence rate is rising: knowledge distilled in one project
  is being recalled and applied in another. This is the system compounding.
- When an incident occurs, the relevant Decision's `consequences` field contains
  the failure mode. The engineer was not surprised; the system warned them.
- Git blame is rarely the answer to "why does the code do X?"

**Failure signatures:**
- Decision nodes with empty `alternatives` or context-free rationale. The council
  is producing rubber stamps.
- The attack phase finds nothing, session after session. Either the decisions are
  genuinely trivial (then they should not be Decisions) or the attack is being
  run softly to avoid friction.
- Graph size grows linearly with time but cross-project recurrence rate is flat.
  The Reflection Analyst is admitting too much; Recall is degrading.
- OSS Maintainer approves changes without citing a Decision. The gate is open.
- The human is adjudicating every conflict. The council is not resolving what it
  should be resolving; agents are escalating rather than working.
- The human is adjudicating no conflicts. Either the system is never producing
  genuine tension (healthy councils do) or tension is being resolved silently
  before reaching the human (the most dangerous failure mode).


## What the council is not

The council is not a pipeline. A pipeline has a single throughput that processes
uniformly. The council has two cadences, multiple configurations, and different
agents invoked for different tasks. Treating it as a pipeline that must run in
full for every change is how the council becomes a burden rather than a lever.

The council is not a committee. A committee reaches consensus. The council
produces a single Decision node authored by the Principal, attacked by the
Reviewer and Performance Engineer, gated by the Maintainer, and learned from by
the Analyst. The goal is not that everyone agrees; the goal is that the final
Decision survived rigorous, orthogonal scrutiny from agents with irreconcilable
mandates. Agreement is a side effect of a Decision that survives the attack, not
a prerequisite for producing one.

The council is not autonomous. No agent orchestrates the others. No agent
self-sequences. No agent finalizes knowledge. The human conducts, adjudicates,
and authors. The agents extend the human's reasoning; they do not replace the
human's judgment. The moment the council operates without the human in that role,
it is not the council — it is six AI agents making engineering decisions and
recording them as if a human had made them. That is the failure mode the entire
architecture exists to prevent.