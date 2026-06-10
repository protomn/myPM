# myPM

**A git-native memory layer for engineers working with AI.**

---

## The problem

Today's AI assistants are extraordinary reasoners and near-total amnesiacs.

Every session begins at zero. You explain your architecture. You explain why you made the call you made six months ago. You explain the incident that settled a question you're still trying not to re-litigate. Then tomorrow you explain all of it again — to an assistant that has, overnight, forgotten you exist.

The bottleneck on AI usefulness isn't the model's reasoning capability. It's the model's ignorance of your specific world: the decisions already made, the tradeoffs already weighed, the things that already broke.

---

## Why existing approaches don't work

**RAG over chat logs** — Dumping conversation history into a vector store is better than nothing. It's also unstructured, contradictory, and noisy. The relevant fact is present, buried under ten thousand irrelevant ones. Retrieval becomes a filtering problem instead of a recall problem.

**Static system prompts** — Useful, but they don't grow with the project, can't cross project boundaries, and require manual maintenance to stay accurate. Documentation pretending to be memory.

**Proprietary memory features** — Your knowledge lives in a vendor's database. It disappears when you switch tools, when the feature is deprecated, or when the context window fills. You don't own it.

**Plain wikis and ADRs** — No typed relationships, no traversal, no way to ask "what decisions affect this component" or "what lessons motivated this choice." A well-organized filing cabinet is still a filing cabinet.

---

## What myPM is

A typed knowledge graph that lives in your git repository.

Not a notes app. Not a second brain. Not a chat interface. A structured store of engineering knowledge — decisions, lessons, components, patterns, preferences — organized so that an AI can retrieve the most relevant slice at the moment it needs to reason.

The graph persists across sessions. It compounds across projects. It is owned by you, versioned with your code, and readable with `cat`.

---

## Architecture

### The knowledge model

Everything in myPM is one of six entities:

| Type | Epistemic kind | What it answers |
|---|---|---|
| `component` | Descriptive | What exists and how it's wired |
| `decision` | Intentional and historical | Why it's built this way |
| `pattern` | Prescriptive | How it should be done |
| `lesson` | Empirical | What experience taught us |
| `preference` | Subjective and standing | How the engineer likes to work |
| `project` | Contextual | What scope this knowledge belongs to |

This set is deliberately small and deliberately orthogonal. Any piece of engineering knowledge belongs to exactly one type. If something doesn't fit cleanly, the model is wrong — not the knowledge.

Nodes are Markdown files with YAML frontmatter. Edges are small YAML records. Both are text, both are git-native, both diff and blame cleanly. No binary format, no proprietary database, no lock-in.

Typed relationships (14 edge types: `motivates`, `affects`, `depends_on`, `derived_from`, `supersedes`, `conflicts_with`, and more) let an agent traverse from a component to the decisions that govern it to the lessons that informed those decisions. That traversal is what makes this a reasoning layer rather than a filing cabinet.

### The Golden Loop

```
RECALL → REASON → CAPTURE → DISTILL → (repeat)
```

**Recall** — Before work begins, the retrieval pipeline assembles a ContextBundle: a token-budgeted, relevance-ranked slice of the knowledge graph scoped to the current project plus the global knowledge commons. The agent starts informed instead of amnesiac.

**Reason** — Work happens with actual context. The agent doesn't re-derive conclusions you've already reached or re-make mistakes you've already recorded.

**Capture** — New knowledge lands in an inbox as raw observations: fast, free, and uncommitted. Nothing is permanent yet.

**Distill** — Two gates decide what enters the permanent graph. Gate 1 (`mypm reflect`) types observations into draft nodes. Gate 2 (`mypm distill`) promotes drafts once they're substantiated, well-formed, and linked to the rest of the graph. Gate 3 detects when a lesson has recurred across enough projects to become a reusable pattern.

The human authorizes every promotion. The AI proposes; the engineer authors. A memory that writes itself drifts. Authorship is where trustworthiness comes from.

### Storage

```
knowledge/
├── inbox/               raw observations (pre-graph; most evaporate at Gate 1)
├── global/nodes/        cross-project patterns and preferences
├── projects/<id>/
│   ├── project.md       the Project node — root context and ownership boundary
│   └── nodes/           project-scoped components, decisions, lessons
└── edges/               typed relationships (scope-free, flat directory)
```

The index at `knowledge/.index/` is a derived SQLite cache — gitignored, rebuildable from the files at any time. It is never the source of truth. The files are the database.

---

## Installation

```bash
pip install mypm-cli
```

(The distribution is `mypm-cli` on PyPI; the command and import package are `mypm`.)

Optional extras enable the reasoning layer (both degrade gracefully if absent):

```bash
pip install 'mypm-cli[semantic]'   # local embeddings for semantic retrieval
pip install 'mypm-cli[ai]'         # Claude integration (LLM proposer + council)
```

Initialize any git repository:

```bash
cd your-repo
mypm init
```

This creates the `knowledge/` directory tree, writes a Project node for the repository, updates `.gitignore`, and installs the agent doctrines and architecture documentation into `.claude/`.

Migrating from an older `memory/` layout:

```bash
mypm migrate --dry-run   # preview first
mypm migrate
```

---

## Quick start

**Bootstrap** — seed the graph from history you already have. Day-1 Recall
should never be empty:

```bash
mypm bootstrap --limit 100 --write          # scan recent commits, preview first without --write
mypm bootstrap --limit 100 --enrich --write # let Claude type the survivors (needs mypm[ai])
```

The extractor pre-filters chore/vague commits, types the rest by choice and
constraint language (a merged PR becomes a draft Decision, a bugfix becomes a
draft Lesson), and dedups every candidate against the graph *and* the other
candidates — only what is genuinely novel reaches the inbox. A commit that
replaces an earlier choice ("Replace Redis with NSQ") is recognized as a
**supersession**, not a duplicate, and carries a pointer to the decision it
probably retires. Candidates land in the inbox only; nothing becomes active
without you.

**Capture** an observation from a session, incident, or benchmark:

```bash
mypm capture \
  --text "allocator overhead dominated the serializer hot path; stack buffers cut p99 by 78%" \
  --source incident \
  --project your-project \
  --type lesson \
  --takeaway "benchmark allocations before optimizing any hot path"
```

**Reflect** — Gate 1: type observations into draft nodes:

```bash
mypm reflect
```

**Distill** — Gate 2/3: promote substantiated, linked drafts to active knowledge:

```bash
mypm distill
```

**Review** — the per-draft approval surface. `distill` is batch; `review` is how
you work through what it blocked, in seconds per item:

```bash
mypm review                                  # interactive: walk pending drafts
mypm review list                             # what's pending and what each needs
mypm review approve lesson_gc_pauses --field root_cause="unbounded allocations"
mypm review reject  lesson_noise
mypm review merge   lesson_restated --into lesson_original
mypm review supersede decision_use_nsq --replaces decision_use_redis
```

`approve` prompts for exactly the fields Gate 2 still needs, then promotes
through the same gate distill uses — no bypass. `supersede` wires the
`supersedes` edge and retires the old node in one step. Observations that fail
Gate 1 are quarantined in `inbox/held/` with their failure reasons embedded;
edit the file and run `mypm reflect --retry-held`.

**Retrieve** — assemble context for a task:

```bash
mypm retrieve \
  --task "how do I optimize the serializer hot path" \
  --project your-project
```

Returns a JSON ContextBundle: the relevant nodes, their types, why each was included, and any flagged conflicts. Feed this to whatever model you are working with. Pass `--agent <role>` (research, principal, adversarial, performance, oss, reflection) to bias ranking toward that agent's declared reads.

**Council** — run the agent doctrines as actual Claude calls (requires `mypm[ai]` + `ANTHROPIC_API_KEY`):

```bash
mypm council \
  --task "add rate limiting to the public API" \
  --project your-project \
  --preset minimal          # principal + adversarial; also: full, decision, review, research, reflect
```

Each agent recalls its own ContextBundle, reasons under its doctrine, and produces drafts for you to author. The runner never writes active knowledge.

**Auto-capture from merged PRs** — install a git hook so merges emit draft Decisions to the inbox:

```bash
mypm hook install        # drops a post-merge hook
mypm capture-pr          # or run it manually against HEAD
```

**Validate** — run the build pass:

```bash
mypm validate
```

Schema validation, edge legality, referential integrity, acyclicity. Run this before promoting anything.

---

## Roadmap

### v0.1 — The substrate ✓

- ✓ Typed knowledge graph (6 entity types, 14 edge types with validity constraints)
- ✓ Retrieval pipeline (scope filter → lexical seed → edge expansion → supersession resolution → ContextBundle)
- ✓ Gate 1: `mypm reflect` — observation to draft node
- ✓ Gate 2/3: `mypm distill` — draft to active, lesson to pattern
- ✓ Build pass — schema, edge validity, referential integrity, acyclicity
- ✓ `mypm init` — initialize any repository with one command
- ✓ `mypm migrate` — migrate from older `memory/` layout

### v0.2 — The reasoning layer ✓

- ✓ Claude integration — agent doctrines wired to actual API calls (LLM proposer + council runner), with graceful fallback to the rule-based substrate
- ✓ Semantic retrieval — pluggable embedding-based seed alongside lexical, content-addressed cache, silent lexical fallback
- ✓ ContextBundle ranking — relevance blended with degree-centrality, recency decay, and agent-role weighting
- ✓ Git hook — auto-capture draft Decisions from merged PRs
- ✓ Validator improvements — near-duplicate detection and scope-drift warnings

### v0.3 — The extraction core ✓

- ✓ `mypm bootstrap` — seed the graph from git history: pre-filter → rule/LLM typing → Recall-as-dedup-filter → inbox candidates (never auto-promoted)
- ✓ Supersession-aware dedup — "Replace X with Y" is recognized as a successor to "Use X", not a duplicate
- ✓ `mypm review` — the approval surface: approve / reject / merge-into / supersede, per draft, through the same Gate 2 distill runs
- ✓ Gate-1 quarantine — failing observations move to `inbox/held/` with reasons; no re-processing, no re-billing
- ✓ Hardening — stale-index detection, malformed-file containment, field type validation, package rename to `mypm`

### v0.4 — The compounding graph

- □ Live Observer — the bootstrap extractor pointed at a stream instead of history
- □ Recall feedback — one-key "was this useful?" on retrieve output (the Recall Win Rate KPI)
- □ Multi-repository knowledge — unified graph across multiple codebases
- □ Graph visualization — dependency chains, supersession history, conflict map

---

## Design principles

**The files are the database.** A node is a Markdown file. An edge is a YAML file. The complete state of the system is a directory tree you can read with `cat`, search with `grep`, and diff with `git`. No hidden state, nothing requiring the application to interpret.

**The index is a cache.** The SQLite index is derived from the files, disposable by construction, and never committed. Delete it and it rebuilds. It can be replaced with something faster in five years without touching a single node or edge file.

**Less, but relevant.** More knowledge is not better knowledge. Raw experience is distilled upward — observation into lesson, lesson into pattern — and retrieval pulls only what is load-bearing. Volume is the failure mode; "less, but relevant" is the discipline.

**The human authors; the AI reads.** myPM is authored by the engineer. The AI assists in capture and is the principal consumer, but the human is the author of record. That is where the system's trustworthiness comes from.

**The memory outlives the model.** Plain, portable files in your repository. Models are interchangeable and improving monthly. The memory is yours and it is permanent.

---

## Current state

v0.1 was the substrate, v0.2 the reasoning layer, v0.3 the extraction core and
the approval surface. The full loop now closes end to end: `mypm bootstrap`
seeds candidates from history you already have, the gates hold them to the same
standard as manual capture, `mypm review` is how a human moves them through
Gate 2 in seconds per item, and `mypm retrieve` recalls the result. Day-1 is
not empty, and nothing enters the active graph without an author.

- **Recall** blends a lexical seed with optional semantic embeddings, then ranks by relevance, centrality, recency, and agent-role fit. The index detects when files changed under it and rebuilds itself.
- **Capture** is abundant: bootstrap over git history, a post-merge hook for PRs, an LLM proposer at Gate 1 — all landing in the inbox, never in the graph.
- **Promotion** is scarce: Gate 2 demands substantiation and a graph link, and `mypm review` is the human's tool for supplying exactly what's missing.
- **Reason** runs the agent doctrines in `.claude/` as real Claude calls — `mypm council` recalls each agent's ContextBundle, reasons under its doctrine, and returns drafts for you to author.

Every AI-backed path is an optional extra that falls back to the deterministic substrate when no key or dependency is present — the files stay the database, and the system still runs offline.
