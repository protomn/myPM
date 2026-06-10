# myPM — Philosophy

## The model is not the bottleneck

Today's AI models are extraordinary reasoners and near-total amnesiacs. Each
conversation begins with no memory of the last. You explain your stack, your
constraints, the thing that broke in March and why you'll never do it that way
again — and the next morning you explain all of it once more to a collaborator
who has, overnight, forgotten you exist.

The limit on how useful an AI is to a working engineer has very little to do with
how clever the model is. It has almost everything to do with how little it knows
about *your* world: what you have already decided, why, what you tried, and what
it cost you. A brilliant reasoner with no context re-derives your hard-won
conclusions from scratch, badly, every single time.

myPM exists to close that gap. It is a persistent engineering memory and
reasoning layer: the durable record of how you and your systems actually work,
structured so that a machine can reason over it, and surfaced to an AI at the
moment it is needed. It turns a stateless assistant into a collaborator that
remembers.


## What we believe

**The reasoning is the asset, not the code.** Code is the artifact a decision
leaves behind. The decision itself, the alternatives weighed, the failure that
ruled one of them out, is the scarce thing, and it is the thing that evaporates.
When an engineer leaves, the repository stays and the *understanding* walks out
the door. myPM treats that understanding as the primary asset and the
code as its downstream residue. This is why edges are first-class records: the
links between decisions, lessons, and components are themselves the knowledge,
not metadata about it.

**Structure is what makes memory usable.** The naive version of AI memory is to
save every transcript and pour it back into context. That is not memory; it is a
hoard. It is unbounded, contradictory, and noisy, and it buries the one relevant
fact under ten thousand irrelevant ones. Memory becomes useful only when it is
curated into a small set of orthogonal types with explicit relationships. The
discipline of "everything is one of these" is not bureaucracy. It is the
precondition for recall.

**Knowledge has to compound across projects.** A lesson learned in one project
that cannot be reached from another is a lesson learned once and paid for twice.
Most tooling locks knowledge inside the project that produced it. myPM
keeps a single global graph and treats project scope as a *filter*, not a wall,
so that a pattern proven in one system is available everywhere and a mistake is
made at most once across your whole career. This is the literal answer to the
question the system was built to address: how an engineer accumulates knowledge
across projects.

**Being wrong is knowledge worth keeping.** The trail of "we believed X, then
learned Y, and here is what changed our minds" is more valuable than the current
answer alone, because it is what stops you from re-litigating settled questions
and re-making buried mistakes. So nodes are never overwritten; they are
superseded, and the history stays queryable. A memory system that only remembers
its latest opinion has forgotten how it learned.

**The human authors; the AI reads.** A memory that writes itself drifts. It
accumulates plausible-sounding garbage, launders hallucination into record, and
slowly poisons every future answer. myPM is authored by the engineer.
The AI assists in capture and is the principal consumer, but the human is the
author of record, and that is where the system's trustworthiness comes from. You
can believe what the graph tells you because you can see who put it there and
why.

**Less, but relevant.** More memory is not better memory. The reasoning layer's
job is to assemble the minimal, current, internally consistent slice a task
actually needs, and to leave everything else out. Raw experience is distilled
upward — observation into lesson, lesson into pattern — and retrieval pulls only
what is load-bearing, follows history only when asked, and resolves stale chains
to their living head. Compression and relevance are the product. Volume is the
failure mode.

**Contradictions are surfaced, not hidden.** A memory system that silently
reconciles two conflicting beliefs is lying to you. When the graph disagrees with
itself, that disagreement is information, and the honest move is to put it in
front of you rather than to quietly pick a side. This is why conflicts are
flagged rather than resolved away.

**The memory outlives the model.** Your accumulated engineering knowledge is
yours. It should not be trapped inside one vendor's chat product, gone the day
you switch tools or the day they sunset the feature. myPM is plain,
portable, inspectable files that live in your repository and your version
control. Models are interchangeable and improving monthly; the memory is
permanent. The layer is designed to outlast every model that reads from it.


## What it is not

myPM is not a collection of prompt shortcuts or a chatbot wrapper. It is
not "AI helpers." Those optimize a single conversation; this accrues an asset
across years.

It is not a second brain, a wiki, or a notes app. It holds engineering knowledge
specifically, with types and relationships chosen for that domain. General
note-taking has no schema and therefore no recall.

It is not a task tracker. It remembers what you know and decided, not what you
have left to do. Tasks belong in an issue tracker; a node may point at one but
never owns it.

It is not autonomous AI memory. The system does not silently rewrite its own
record of your work. Authorship stays with the engineer by design, because that
is the only thing that keeps the record trustworthy.

It is not a code store. Code lives in git. The graph references reality; it does
not duplicate it.


## Why it is an OS, not an app

An operating system is the layer other software runs on top of without thinking
about it. myPM is meant to be that layer for AI-assisted engineering:
not a destination you visit, but the memory and reasoning substrate that every
agent, editor, and assistant draws from. The value is not in any one interaction
with it. The value is that, over time, everything you learn is captured once,
related to everything else you know, and made available to whatever model you are
working with, in whatever tool, on whatever project.

That is the shift it is built to cause: from an assistant that is brilliant and
forgetful, to a collaborator that is merely capable but never forgets a thing you
have taught it.


## The north star

Every entity, every edge, and every feature earns its place by one test:

> Does it help an engineer's hard-won knowledge survive, compound across
> projects, and arrive in the AI's context at the exact moment it is needed?

If it does, it belongs. If it does not, it is out of scope, no matter how clever
it is. The whole system is the disciplined pursuit of that single sentence.