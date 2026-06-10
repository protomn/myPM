# myPM — Success Metrics

## Why this is where projects die

Most systems do not fail because they were built badly. They fail because they
were measured badly, and a badly measured project optimizes itself confidently in
the wrong direction. The failure modes are specific and they are always the same
five:

Measuring **activity instead of outcome** — counting how much got captured rather
than whether anything got better. Picking **vanity numbers** that rise reliably
and mean nothing. Having **no baseline**, so any improvement is unattributable and
any claim of success is unfalsifiable. Letting a **single metric** stand alone, so
the moment it becomes a target it gets gamed (Goodhart's law is not a risk, it is
a certainty). And **never defining failure**, so the project cannot tell the
difference between "needs more time" and "does not work," and therefore runs
forever.

This document is built to fail at none of those. Every value metric is paired with
a counter-metric. Every metric is classed as leading or lagging so we know whether
we are predicting value or confirming it. The seductive vanity numbers are named
and rejected on principle. And the conditions under which we declare myPM
a failure are written down in advance, while we still have the integrity to mean
them.


## The one metric that matters

Everything reduces to one question, taken straight from the north star in
`philosophy.md`: does hard-won knowledge survive, compound across projects, and
arrive in context when it is needed?

The single metric that integrates all four is **compounding reuse**:

> The rate at which distilled knowledge (`active` Lessons and Patterns) is
> recalled at a point of need and applied in a context *other than* the one that
> created it — and whether that rate is **rising over time**.

This one number carries the whole thesis. *Survives*: only `active`, distilled
knowledge counts. *Arrives in context*: it must be recalled at the point of need,
not merely sitting in the graph. *Compounds across projects*: it must be applied
beyond its origin, which is the literal mission. And the trend, not the level, is
the verdict, because a flywheel is defined by acceleration. A reuse rate that is
high but flat describes a loop that turns without compounding — a treadmill, not a
flywheel. Success is the second derivative.

Everything below is a diagnostic. Each metric exists to explain why compounding
reuse is rising or falling, and nothing else earns the name "success metric."


## Two questions, not one

Diagnostics split cleanly in two, and conflating them is its own failure.

**Is the loop turning?** Leading indicators. Measurable now, they predict future
value. If Capture and Distill are not happening, or Recall surfaces nothing
useful, no value can compound regardless of intent. Leading metrics are an early
warning system; they go bad before the outcomes do.

**Is the loop producing value?** Lagging indicators. Measurable only later, they
confirm the value was real. Fewer repeated mistakes, faster grounded decisions,
better AI output. Lagging metrics are the truth; they are also slow, confounded,
and arrive too late to steer by alone.

A healthy reading needs both. A loop that turns furiously (leading green) while
outcomes flatline (lagging red) is busywork wearing the costume of progress, and
it is the single most common way an engineering-memory project lies to itself.


## The five outcomes, operationalized

The five aspirations in the skeleton are correct as outcomes and useless as
metrics, because not one of them is measurable as written. Here is each turned
into something a number can answer.

### 1. Important lessons are not forgotten

"Not forgotten" does not mean "stored." It means *recalled and heeded at the
moment it was relevant*. A Lesson that sits in the graph unread during the exact
work it should have informed is forgotten, regardless of the fact that it exists.

```
construct  : a relevant Lesson is surfaced and acted on at the point of need
metric     : preventable-recurrence rate — incidents for which a preventing
             Lesson already existed but was not recalled or not heeded
type       : lagging
measure    : post-incident audit; for each incident, ask "did a Lesson that
             would have prevented this already exist?" Count the yeses.
goodhart   : flood the graph with trivial "lessons" so coverage looks total;
             or over-surface everything so nothing is missed but Recall is noise
guardrail  : recall precision — fraction of surfaced nodes the engineer rates
             relevant. Push coverage up by dumping everything and precision craters.
```

The honest primary number is the lagging one, and it is brutal by design: every
preventable recurrence is a Lesson the system held and failed to deliver. Zero is
the target. The guardrail is the load-bearing half — "nothing is forgotten" is
trivially achievable by surfacing the entire graph every time, which violates
"less, but relevant" and destroys the system. Coverage and precision are measured
as a pair or not at all.

### 2. Similar mistakes become less frequent

```
construct  : a mistake made once becomes a Lesson, so it is not made again —
             and especially not in a different project
metric     : cross-project recurrence rate — recurrence of a known mistake-class
             in a project other than the one whose Lesson first recorded it
type       : lagging
measure    : tag incidents to a stable mistake-class taxonomy; track recurrence
             of a class after an active Lesson exists for it, split by project
goodhart   : narrow the definition of "same mistake" until nothing counts as a
             repeat; or claim every avoided mistake as a save with no counterfactual
guardrail  : freeze the mistake-class taxonomy; require honest attribution (below)
```

This is the most important value metric in the document after the north star,
because it tests the mission's boldest claim directly: that a mistake is made *at
most once across a career*, not once per project. Within-project recurrence
falling is good. Cross-project recurrence falling is the proof that knowledge
compounds across the walls — the thing the entire scope-as-a-filter design exists
to deliver.

### 3. Architectural decisions become easier

"Easier" splits into faster and better-grounded, and measuring only the first is
how you get fast, shallow, wrong decisions.

```
construct  : decisions are quicker AND better-grounded because prior decisions,
             alternatives, and constraints are recalled instead of re-derived
metric     : decision groundedness — share of new Decisions that link to prior
             knowledge (builds_on / applies / motivated_by edges) rather than
             being made from scratch;  plus decision lead time
type        : leading (groundedness), lagging (lead time)
measure     : read it straight off the graph — count edges from each new Decision
             back into existing nodes; time from question raised to Decision active
goodhart    : optimize speed → drop real alternatives and consequences; or spam
             edges so a shallow decision looks grounded
guardrail   : decision durability — rework rate of Decisions superseded within
             N months for being wrong (not for healthy learning). Speed must not
             buy itself with churn.
```

Groundedness is computable directly from the relationship graph, which makes it a
rare leading metric that is both cheap and hard to fake without the Adversarial
Reviewer noticing. The counter-metric, durability, is what stops "decisions got
easier" from quietly meaning "decisions got sloppier." A second honest signal is
**re-litigation rate**: how often the same architectural question is reopened.
A recorded Decision with its rationale should settle a question; if the same debate
recurs, Recall is not delivering the prior reasoning.

### 4. Project onboarding time decreases

The human version of this is real but nearly unmeasurable: small sample, long
horizon, hopelessly confounded by who the newcomer is. So the primary metric is
the AI's onboarding, which can be measured cleanly because it can be toggled.

```
construct  : a newcomer — human or AI — gets productive faster because the graph
             holds the project's accumulated context
metric     : AI cold-start quality lift — output quality on a task in a project,
             with Recall on vs Recall off, blind-rated
type        : lagging, but fast and clean (it is an ablation, see Discipline)
measure     : same task, graph-on vs graph-off, output rated by an evaluator
             blind to which condition produced it
goodhart    : stuff the graph with onboarding prose nobody reads and that does
             not match reality; count "docs" as context
guardrail   : drift / freshness — share of Components that still match current
             reality (the OSS Maintainer's beat). Stale onboarding context is
             worse than none, because it is confidently wrong.
```

A useful leading proxy is **context completeness**: for a given project, does the
graph answer the four standard onboarding questions — what is this, why is it built
this way, what breaks, how do we do X — which map exactly to Component, Decision,
Lesson, and Pattern. A project missing an entire entity type is a project whose
graph cannot onboard anyone.

### 5. AI responses improve because historical context is available

This is the cleanest causal metric in the system, because the cause can be
switched off.

```
construct  : Recall makes AI output measurably better
metric     : recall-ablation quality lift — quality with Recall on minus quality
             with Recall off;  plus AI-proposal rejection rate (drafts discarded)
type        : lagging, ablation-based
measure     : A/B the same prompts with Recall enabled and disabled; rate blind.
             Track the share of agent-proposed drafts the human rejects.
goodhart    : rate quality on fluency rather than correctness; or reward the AI
             for parroting recalled nodes without reasoning (looks grounded,
             adds nothing)
guardrail   : blind, outcome-based rating; an explicit check that recalled context
             is reasoned over, not regurgitated. A drop in proposals that violate
             an existing Decision or Pattern is the cheapest honest signal here.
```


## The pairing principle

No value metric stands alone, ever. Each is mounted to a counter-metric that goes
bad precisely when the first is being gamed: coverage against precision, decision
speed against durability, onboarding context against drift. The pair is the
metric; the single number is a target waiting to be exploited. When a reviewer
asks "what would gaming this look like," the counter-metric is the answer, and if
there is no answer the metric is not ready to use.


## Anti-metrics: what we refuse to measure

This is the section most projects need and never write. These numbers are
seductive because they always go up and are trivial to collect. Every one of them
is rejected here, on principle, with the principle named.

**Total nodes / graph size / "knowledge captured."** Rejected outright. The
philosophy is explicit that volume is the *failure mode*, not the goal. A larger
graph is not a better one; past a point it is a worse one, because it buries the
relevant node under a thousand irrelevant ones and degrades the only thing that
matters, Recall. This is the single most common metric for memory systems and it
is exactly backwards for this one.

**Capture rate / nodes added this week.** This is activity, not outcome — a
leading process input at best, and a vanity number at worst. Capturing is the cost
of the system, not its product. Rewarding it produces a tidy, growing, useless
graph.

**Agent invocations / AI interactions / time spent in the system.** Engagement
metrics, and engagement is something this system specifically does *not* want. The
philosophy refuses to foster reliance. More interactions can mean the system is
*failing* — that the engineer is re-explaining context the graph should already
hold. We do not optimize for being used more. We optimize for making the work
better and then getting out of the way.

**Coverage for its own sake.** A Decision record for every commit, a Lesson for
every bug, is not thoroughness. It is noise with good intentions, and it triggers
the same Recall-degradation as raw volume.

The test for any proposed metric: would this number rise if we filled the graph
with well-formatted garbage? If yes, it measures the garbage, not the system.


## Failure criteria

Pre-committed, because the time to define failure is before you are emotionally
invested in denying it. myPM is failing — not "needs tuning," failing —
if, after a fair runway with real baselines:

1. **Recall precision stays low.** The graph has become a hoard; Distill is not
   doing its job, and every other metric is downstream of noise.
2. **Cross-project recurrence does not fall.** The central claim — that knowledge
   compounds across projects — is empirically false for this implementation.
3. **Recall-ablation lift is within noise.** Turning the system on does not make
   the AI better. There is no there there; stop.
4. **Maintenance effort grows faster than value extracted.** A negative flywheel:
   the system costs more to feed than it returns. This is the slow death, and it
   is the one a project will rationalize the longest.
5. **Drift outruns capture.** The graph no longer matches reality and is therefore
   confidently lying, which is worse than an empty graph and corrodes the trust
   the whole system runs on.

Any one of these sustained is a kill signal. Two at once is the answer.


## Measurement discipline

**Baselines first.** Decision lead time, recurrence rate, onboarding time, AI
quality — all measured in the pre-myPM world before a single success is
claimed. A metric without a baseline is a story.

**Ablation is the master tool.** The cleanest causal lever in the entire system is
that Recall can be switched off. Several metrics above (cold-start lift, response
lift) are ablations for exactly this reason: same task, graph on versus off, rated
blind. Where a metric can be made into an ablation, it should be, because it is the
only measurement here that survives the attribution problem intact.

**Be honest about attribution.** The human-outcome metrics — onboarding time, "felt
easier" — are small-sample and badly confounded. They are treated as *directional*,
never as proof. Claiming a confounded correlation as a caused result is the same
dishonesty as a vanity metric, dressed up as rigor.

**Cadence matches type.** Leading process-health metrics are read weekly, because
they are the early-warning system and the point is to catch decay before the
outcomes turn. Lagging value metrics are read quarterly, because read more often
they are mostly noise and reading them weekly invites optimizing the noise.

**Measure what matters even when it is hard.** The easy metrics are the vanity
ones; that is *why* they are easy. The discipline of this entire document is the
refusal to substitute a number that is convenient for a number that is true.