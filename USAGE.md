# myPM — The Complete Usage Guide

myPM is a typed knowledge graph that lives inside your git repository. It
remembers your engineering decisions, lessons, patterns, components, and
preferences as plain text files, and serves the relevant slice back to you (or
to an AI assistant) at the moment a task needs it.

This guide covers **every feature** of the tool: how to set it up on a brand-new
repo or a repo with years of history, what each command does, and how the
pieces fit together day to day. For the *why* behind the design, see
[README.md](README.md).

---

## Table of contents

1. [The mental model](#1-the-mental-model)
2. [Installation](#2-installation)
3. [Setup on a fresh repo](#3-setup-on-a-fresh-repo)
4. [Setup on an existing repo](#4-setup-on-an-existing-repo)
5. [Core concepts](#5-core-concepts)
6. [Command reference](#6-command-reference)
   - [`mypm init`](#mypm-init)
   - [`mypm migrate`](#mypm-migrate)
   - [`mypm capture`](#mypm-capture)
   - [`mypm reflect`](#mypm-reflect--gate-1)
   - [`mypm distill`](#mypm-distill--gates-2-and-3)
   - [`mypm review`](#mypm-review--the-approval-surface) (list, interactive, fill, approve, approve --all, reject, merge, supersede, stats)
   - [`mypm retrieve`](#mypm-retrieve--recall)
   - [`mypm orient`, `mypm show`, `mypm search`](#mypm-orient-mypm-show-mypm-search--the-read-surface)
   - [`mypm feedback` and `mypm stats`](#mypm-feedback-and-mypm-stats--measuring-both-loops)
   - [`mypm doctor`](#mypm-doctor)
   - [`mypm bootstrap`](#mypm-bootstrap--seed-from-git-history)
   - [`mypm council`](#mypm-council--ai-agents-experimental)
   - [`mypm capture-pr` and `mypm hook`](#mypm-capture-pr-and-mypm-hook--pr-auto-capture)
   - [`mypm observe`](#mypm-observe--live-capture-from-claude-code)
   - [`mypm validate`](#mypm-validate--the-build-pass)
   - [`mypm index`](#mypm-index)
7. [Claude Code integration](#7-claude-code-integration)
8. [Configuration and environment variables](#8-configuration-and-environment-variables)
9. [Everyday workflows](#9-everyday-workflows)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. The mental model

Everything in myPM revolves around one cycle, the **Golden Loop**:

```
RECALL  →  REASON  →  CAPTURE  →  DISTILL  →  (repeat)
```

| Step | Command | What happens |
|---|---|---|
| **Recall** | `mypm retrieve` | Pull the relevant slice of the graph before starting a task |
| **Reason** | you / `mypm council` | Do the work, informed instead of amnesiac |
| **Capture** | `mypm capture` (and friends) | Drop raw observations into an inbox — cheap, fast, uncommitted |
| **Distill** | `mypm reflect` + `mypm distill` / `mypm review` | Gates decide what becomes permanent knowledge |

The single most important rule: **capture is abundant, promotion is scarce**.
Anything can land in the inbox — a CLI command, a git hook, a Claude session, a
history scan. But nothing becomes *active* (recallable) knowledge until it
passes the gates, and a human authorizes every promotion. The AI proposes; you
author.

Three gates stand between an observation and the permanent graph:

- **Gate 1** (`mypm reflect`) — the *future recall test*. Is the observation
  specific (a finding, not a mood)? Typeable into one of the six entity types?
  Minimally structured? Pass → it becomes a **draft node**. Fail → it is
  quarantined with reasons, never silently dropped.
- **Gate 2** (`mypm distill` or `mypm review approve`) — *substantiation and
  connection*. Does the draft have its required fields (e.g. a lesson needs a
  `root_cause`, a decision needs `alternatives` and `consequences`)? Is it
  linked to at least one other node in the graph? Pass → status flips to
  **active** and its proposed links materialize as real edges.
- **Gate 3** (runs inside `mypm distill`) — *generalization detection*. When
  similar lessons recur across multiple projects, distill flags them as a
  candidate **pattern** for you to author.

---

## 2. Installation

```bash
pip install mypm-cli
```

The PyPI distribution is `mypm-cli`; the command and import package are `mypm`.
Requires Python ≥ 3.11.

Two **optional extras** unlock the AI-backed paths. Both degrade gracefully:
without them, every command still works on the deterministic, rule-based
substrate. Nothing requires a network connection or an API key to function.

```bash
pip install 'mypm-cli[semantic]'   # local sentence-transformer embeddings for semantic retrieval
pip install 'mypm-cli[ai]'         # Anthropic SDK: LLM proposer, bootstrap --enrich, mypm council
```

For the `[ai]` extra you also need `ANTHROPIC_API_KEY` (or
`ANTHROPIC_AUTH_TOKEN`) in your environment.

Verify the install:

```bash
mypm --version
```

**Finding the root:** you never need to be in the repo's top directory. Every
command resolves the knowledge root as: explicit `--root` flag (before the
subcommand) → `$MYPM_ROOT` → a walk **up** from your cwd looking for
`knowledge/`, exactly the way git finds `.git`. Running `mypm retrieve` from
`repo/src/deep/` finds `repo/knowledge/`. Only `mypm init` ever *creates* a
root; if no root exists, every other command errors with the remedy instead of
inventing an empty graph where it stands.

```bash
mypm --root knowledge_demo review list   # explicit root, when you need one
```

---

## 3. Setup on a fresh repo

A new project has no history to mine, so setup is one command and the loop
starts immediately.

```bash
cd your-new-repo
mypm init
```

`init` does four things (it only ever **creates** files, never modifies yours):

1. Creates the `knowledge/` tree and an **active Project node** at
   `knowledge/projects/<id>/project.md`. The project id defaults to the
   directory name; override with flags:

   ```bash
   mypm init --project payments --name "Payments Service" \
             --description "Handles card processing and ledger writes"
   ```

2. Adds `knowledge/.index/` to `.gitignore` (the index is a rebuildable cache
   and must never be committed).

3. Installs the Claude Code integration into `.claude/`: a `CLAUDE.md` with
   the command crib sheet, `council.md` (governance rules for the six agents),
   `agents/*.md` (six dual-runtime agent doctrines), `architecture/*.md` (the
   full design docs), and `commands/enrich-drafts.md` (the `/enrich-drafts`
   slash command). Files that already exist are skipped, never overwritten.

4. **Generates** `.claude/settings.json` with three hooks, each pinned to the
   installing Python interpreter (a bare `mypm` in a hook resolves against
   Claude Code's PATH, not your venv's, and fails silently forever):
   `SessionStart → mypm orient` (recall pushed into every session) and
   `Stop`/`SubagentStop → mypm observe` (guaranteed capture). If you already
   have a `settings.json`, yours wins and this step is skipped.

Run `mypm doctor` after init — it verifies all of this wiring loudly.

From here, your loop on a fresh repo is simply: work, capture observations as
they happen, and run `reflect` + `review` when a few have accumulated. The
graph grows with the project from day one.

```bash
# something worth remembering just happened
mypm capture --text "switched to connection pooling; cold-start p99 fell 60%" \
             --project payments --type lesson \
             --takeaway "pool DB connections before tuning anything else"

mypm reflect          # Gate 1: observation -> draft
mypm review           # interactive: approve/reject the drafts
```

Commit the `knowledge/` directory like any other code. It diffs, blames, and
merges as plain text.

---

## 4. Setup on an existing repo

An existing repo has history worth mining. Same `init`, then **bootstrap** the
graph from your git log so day-1 recall doesn't start empty (yield depends on
your commit style; an unproductive run explains itself and offers `--enrich`).

```bash
cd your-existing-repo
mypm init
mypm bootstrap --limit 200            # PREVIEW: scan the last 200 commits, write nothing
mypm bootstrap --limit 200 --write    # land the surviving candidates in the inbox
```

Bootstrap pre-filters chores and vague commits, types the survivors by their
language (a merged PR reads like a Decision; a bugfix reads like a Lesson),
and dedups every candidate against both the existing graph and the other
candidates. A commit like "Replace Redis with NSQ" is recognized as a
**supersession** of an earlier "Use Redis" decision — not a duplicate — and
carries a pointer to the node it probably retires.

With the `[ai]` extra installed you can let Claude do the typing instead of
the rules:

```bash
mypm bootstrap --limit 200 --enrich --write              # LLM types novel survivors (costs tokens)
mypm bootstrap --limit 200 --enrich --model claude-haiku-4-5 --write
mypm bootstrap --repo ../other-checkout --project payments --limit 100 --write
```

Then run the candidates through the gates:

```bash
mypm reflect          # Gate 1: inbox -> draft nodes
mypm review list      # see what each draft still needs
```

Most bootstrapped drafts will be missing their substantiation fields (a commit
message rarely states `root_cause` or `alternatives` honestly). You have two
ways to fill them:

- **By hand**, via `mypm review` (interactive) or
  `mypm review approve <id> --field ...` — designed for seconds per draft;
  `mypm review stats` tells you what it actually costs you.
- **By a Claude Code session**, via the `/enrich-drafts` slash command: it
  reads each draft's source commit (`git show <sha>` — the sha is in every
  draft's provenance), fills fields with what the diff actually evidences, and
  uses `mypm review fill` — which can never promote. You stay the author; the
  session does the archaeology.

Finally, approve in bulk where possible and per-draft where not:

```bash
mypm distill          # batch-promote everything that now passes Gate 2
mypm review           # walk whatever distill blocked, one decision per draft
```

If your repo used the older `memory/` layout from early versions, migrate
once:

```bash
mypm migrate --dry-run    # preview the rename and .gitignore edit
mypm migrate              # memory/ -> knowledge/
```

---

## 5. Core concepts

### The six node types

Every piece of knowledge is exactly one of these. Nodes are Markdown files
with YAML frontmatter, stored under `knowledge/`.

| Type | What it answers | Gate 1 requires | Gate 2 additionally requires | Other fields |
|---|---|---|---|---|
| `decision` | Why it's built this way | `choice`, `rationale` | `alternatives`, `consequences` | `context` |
| `lesson` | What experience taught us | `takeaway` | `root_cause` | `trigger` |
| `pattern` | How it should be done | `applicability`, `solution` | — | `example`, `anti_patterns` |
| `component` | What exists and how it's wired | `kind`, `description` | — | `location` |
| `preference` | How you like to work | `statement`, `strength` | — | `rationale`, `overridable` |
| `project` | What scope knowledge belongs to | `name`, `description` | — | `stack`, `repos`, `lifecycle` |

List-typed fields are entered on the CLI with `;` as the separator:
`--field alternatives="kafka; rabbitmq"`.

Node **statuses**: `draft` → `active` → (`superseded` \| `deprecated`).
Only active nodes are recalled; superseded nodes remain as history but
retrieval always resolves to the living head of a supersession chain.

### Scope

A node is either **global** (`knowledge/global/nodes/`) or scoped to one
project (`knowledge/projects/<id>/nodes/`). Scope is determined by file
location — there is no `belongs_to` edge file. Retrieval for a project sees
that project's nodes plus the global commons, never another project's private
scope. Patterns and preferences typically live global; decisions, lessons,
and components typically live in a project.

### The 14 edge types

The relationship model defines 14 typed edges. Thirteen are materialized as
small YAML files in `knowledge/edges/`, named `<from>--<type>--<to>.yml`
(deterministic ids make them idempotent and merge-safe); the fourteenth,
`belongs_to`, is structural — scope is assigned by file location, and the
validator rejects any attempt to write it as an edge file. Each edge type has
a legality rule (which node types it may connect) and a traversal policy:

- **pull** — followed automatically during recall: `part_of`, `depends_on`
  (component→component), `motivates` (lesson→decision/pattern),
  `derived_from` (pattern→lesson), `establishes` (decision→pattern),
  `affects` (decision→component), `concerns` (lesson→component),
  `applies` (decision→pattern).
- **link** — available on demand, not auto-pulled: `builds_on`
  (decision→decision), `influences` (preference→decision/pattern),
  `supersedes` (same-type only), `relates_to` (anything→anything).
- **flag** — existence is surfaced as a warning, content never pulled:
  `conflicts_with` (decision/pattern/preference, symmetric).

`part_of`, `builds_on`, `establishes`, and `supersedes` must be acyclic (a
cycle fails the build); a `depends_on` cycle is a warning. Drafts carry
`proposed_links` in their frontmatter; Gate 2 turns legal proposals into real
edge files at promotion.

### The storage layout

```
knowledge/
├── meta.yml             layout version marker
├── inbox/               raw observations (pre-graph; most evaporate at Gate 1)
│   └── held/            quarantined observations with embedded failure reasons
├── global/nodes/        cross-project knowledge
├── projects/<id>/
│   ├── project.md       the Project node
│   └── nodes/           project-scoped nodes
├── edges/               all edges, flat and scope-free
├── .index/              derived SQLite cache — gitignored, rebuildable
└── .metrics/            review telemetry (JSONL) — not knowledge, not gitignored
```

**The files are the database.** The index is a cache that detects staleness
and rebuilds itself; delete it freely. Everything else is meant to be
committed.

---

## 6. Command reference

### `mypm init`

Initialize a repository (see §3 for the full walkthrough).

| Flag | Meaning |
|---|---|
| `--project <slug>` | project id (default: current directory name, slugified) |
| `--name <text>` | human-readable project name |
| `--description <text>` | one-line description for the Project node |

Idempotent and non-destructive: existing files are skipped and reported.

### `mypm migrate`

One-time rename of the legacy `memory/` root to `knowledge/`, including the
`.gitignore` entry. `--dry-run` previews. Refuses to act if both directories
exist (resolve manually first).

### `mypm capture`

Write one raw observation to the inbox. This is the manual capture verb — use
it the moment something durable happens (an incident conclusion, a benchmark
result, a decision made in conversation).

```bash
mypm capture \
  --text "allocator overhead dominated the serializer hot path; stack buffers cut p99 by 78%" \
  --source benchmark \
  --project payments \
  --type lesson \
  --takeaway "benchmark allocations before optimizing any hot path" \
  --trigger "p99 regression after v2.3" \
  --root-cause "per-call heap allocations in the encode loop" \
  --tags "performance,serialization" \
  --link concerns:component_serializer
```

| Flag | Meaning |
|---|---|
| `--text` (required) | the observation itself — be specific; vague text fails Gate 1 |
| `--source` | where it came from: `conversation` (default), `incident`, `benchmark`, … |
| `--project` | project scope (omit for a global observation) |
| `--type` | proposed entity type (`lesson`, `decision`, …) — helps Gate 1 |
| `--takeaway`, `--root-cause`, `--trigger` | shortcuts for the common lesson fields |
| `--field key=value` | any other proposed field (repeatable) |
| `--tags a,b,c` | comma-separated tags |
| `--motivates <node-id>` | shortcut: propose a `motivates` edge to a decision/pattern |
| `--link type:node-id` | propose any edge (repeatable) |

Capturing is free and uncommitted — nothing you capture enters the graph until
the gates run.

### `mypm reflect` — Gate 1

Process every inbox observation through the future-recall test:

- **specific** — reads as a finding, not a mood ("it's slow" fails);
- **typeable** — maps to one of the six entity types;
- **minimally structured** — has the type's `required_draft` fields;
- **non-redundant** — no node with the same identity already exists.

Passing observations become **draft nodes** in the right scope and leave the
inbox. Failing observations are **quarantined** in `inbox/held/` with their
failure reasons embedded in the file — they are not re-processed (or, with an
LLM proposer, re-billed) on later runs. Edit the held file to fix it, then:

```bash
mypm reflect --retry-held    # release quarantined observations back through the gate
```

With the `[ai]` extra and an API key, reflect uses an **LLM proposer** to type
and structure untyped observations; without it, rule-based typing runs. Same
gate either way.

### `mypm distill` — Gates 2 and 3

The batch promotion pass. For every draft node, Gate 2 checks:

1. **substantiated** — all `required_draft` + `required_active` fields present;
2. **linked** — at least one legal proposed link or existing edge connects it
   to the graph.

Drafts that pass flip to `active`, their proposed links materialize as edge
files, and the index rebuilds. Drafts that fail stay drafts, with reasons
printed — that's what `mypm review` is for. Distill also runs **Gate 3**:
lessons recurring across enough projects are flagged as candidate patterns for
you to author (never auto-created).

### `mypm review` — the approval surface

Where `distill` is batch, `review` is per-draft: it asks you for exactly what
Gate 2 still needs and nothing else. Promotion goes through the **identical**
gate code distill uses — review is a convenience, never a bypass.

```bash
mypm review              # interactive mode: walk every pending draft
mypm review list         # non-interactive: what's pending and what each needs
mypm review list --type lesson --source pr --project payments   # filter the queue
```

**Interactive mode** shows each draft's **content and provenance** — its
filled fields, body excerpt, and source — plus the Gate-2 report, and offers
one key per action: `[a]pprove` (prompts only for the missing fields, and for
a graph link when there is none, defaulting to the project node), `[r]eject`,
`[m]erge`, `[s]upersede`, `[e]dit` (opens the file in `$EDITOR`), `[k]` skip,
`[q]` quit. You see what you author; fast approval stays informed approval.

**Per-draft verbs:**

```bash
# save evidence-backed fields WITHOUT promoting — the verb LLM sessions may use
mypm review fill lesson_gc_pauses --field root_cause="unbounded per-request allocations (per a1b2c3d)"

# fill missing fields and promote through Gate 2 in one step
mypm review approve lesson_gc_pauses --field root_cause="unbounded allocations"

# delete a draft that never earned a place in the graph
mypm review reject lesson_noise

# fold a draft into an existing node of the same type (the restatement case):
# body appended with provenance, tags unioned, empty target fields filled
mypm review merge lesson_restated --into lesson_original

# promote the draft as the successor of an old node: wires the supersedes
# edge and retires the old node in one step
mypm review supersede decision_use_nsq --replaces decision_use_redis \
  --field alternatives="keep redis; kafka" --field consequences="migration work"

# bulk: promote every draft that ALREADY passes Gate 2 as it stands — the
# verb for a backlog /enrich-drafts has finished with (filters apply)
mypm review approve --all
```

Notes:

- `--field key=value` is repeatable; `;` separates list items.
- `--link type:node-id` proposes an edge (saved on the draft; materialized at
  promotion) — it works on `fill`, `approve`, and `supersede` alike.
- A blocked `approve` still **saves** the fields you supplied — progress is
  never lost — and prints the exact command that would unblock the draft
  (`fix: mypm review approve <id> --field root_cause='...' --link ...`).
- `fill` is the safety boundary for AI sessions: a session that only runs
  `fill` cannot author knowledge no matter what it writes. Promotion remains a
  human act.

**`mypm review stats`** — measures the human gate. Every review verb logs one
line of telemetry to `knowledge/.metrics/review_log.jsonl` (interactive review
also timestamps the moment each draft is shown), and `stats` reports
time-to-decision and fields-typed-at-decision, split into two cohorts: drafts
that were `fill`ed first vs bare drafts.

```
3 decision(s) logged (2 approve, 1 reject)

cohort             n  timed   median     mean  fields typed
filled first       1      1     0.3s     0.3s           0.0
bare draft         2      2    94.0s   101.3s           2.5
```

If enrichment is paying off, the filled cohort approves in seconds with
nothing typed. The log is telemetry, not knowledge: it never enters the graph,
a logging failure can never block a promotion, and unlike `.index/` it is
*not* gitignored — it's raw measurement data, not a rebuildable cache.

### `mypm retrieve` — Recall

Assemble a **ContextBundle** for a task: a token-budgeted, relevance-ranked
slice of the graph, printed as JSON.

```bash
mypm retrieve --task "how do I optimize the serializer hot path" --project payments
```

| Flag | Meaning |
|---|---|
| `--task` (required) | what you're about to do, in plain language |
| `--project <id>` | scope: this project's nodes + global (omit for global only) |
| `--agent <role>` | bias ranking toward an agent's declared reads — one of `research`, `principal`, `adversarial`, `performance`, `oss`, `reflection` |
| `--semantic-weight 0..1` | semantic share of the seed blend (default 0.2, lexical-first; only matters with the `[semantic]` extra) |
| `--format json\|text` | `json` for models (default), `text` for human eyes |

The pipeline: scope filter → lexical (+ optional semantic) seed → expansion
along **pull** edges → supersession resolution (always the living head) →
ranking by relevance, degree-centrality, recency decay, and agent-role fit →
token-budgeted bundle. The output lists each node, *why it was included*, and
any `conflicts_with` flags. Feed it to whatever model you work with — or let
the Claude Code agent doctrines run it for you. Every bundle is logged to the
recall telemetry (see [`mypm stats`](#mypm-feedback-and-mypm-stats--measuring-both-loops)).
With `MYPM_GLOBAL_ROOT` set, the shared root's global-scope nodes join the
candidate pool (local nodes win id collisions; foreign project scopes never
leak in).

### `mypm orient`, `mypm show`, `mypm search` — the read surface

**`orient`** prints a compact orientation bundle (~1k tokens): the project
description plus the most load-bearing (degree) and freshest (recency)
decisions, patterns, preferences, components, and lessons, with the recall
crib at the end. It is the payload of the `SessionStart` hook `mypm init`
wires — every Claude Code session starts already knowing the law of the
codebase. Hook-safe: outside a myPM repo, or on an empty graph, it prints
nothing and exits 0. `--project <id>` narrows multi-project roots.

**`show <node-id>`** prints one node in full: status, scope, confidence,
source, tags, every field, the body, its edges in both directions (with the
supersession head if the node has been retired), and the file path.

**`search <terms...>`** is lexical search over active nodes *and* drafts
(drafts are labeled), ranked by the same relevance scorer retrieval seeds
with. `--limit N` (default 10). Both commands also see the global root when
`MYPM_GLOBAL_ROOT` is set.

### `mypm feedback` and `mypm stats` — measuring both loops

Whether the system pays for itself is measured, not assumed, in two logs under
`knowledge/.metrics/` (telemetry, never knowledge: best-effort writes that can
never block an action).

```bash
mypm feedback good            # rate the most recent retrieve (good|bad|partial)
mypm feedback bad --note "missed the redis decision"
mypm stats                    # both loops in one report
```

`stats` reports the **write path** (the review table: time-to-decision and
fields-typed, split by whether drafts were `fill`ed first) and the **read
path**: bundles produced, the human **win rate** from `feedback`, and the
**citation rate** — the Stop hook checks each session transcript for mentions
of recently-bundled node ids, so you learn whether recalled knowledge was
actually *used*, not just produced. Citation detection is idempotent per
session.

### `mypm doctor`

Every hook in myPM is silent by design — silence is a feature in a hook and a
bug in a diagnostic. `doctor` is where the silence gets loud:

```bash
mypm doctor
```

Checks: root resolution (and what was searched), graph counts, index
freshness, the build pass, the git post-merge hook, the Claude Code
`settings.json` hooks **including whether their executables actually resolve**
(the classic venv failure: a bare `mypm` in a hook command), the AI and
semantic extras, and `MYPM_GLOBAL_ROOT` validity. Exit 1 on hard failures;
every failure prints its fix.

### `mypm bootstrap` — seed from git history

Covered in §4. Full flags:

| Flag | Meaning |
|---|---|
| `--repo <path>` | repo to read `git log` from (default: cwd) |
| `--limit <n>` | how many recent commits to scan (default 20) |
| `--project <id>` | project scope for candidates |
| `--enrich` | use Claude to type novel survivors (needs `[ai]`; costs tokens) |
| `--model <id>` | model for `--enrich` (e.g. `claude-haiku-4-5`) |
| `--write` | actually write candidates to the inbox (default: preview only) |

Always preview first. Candidates land in the **inbox** only — bootstrap never
creates active knowledge.

The free pass only types commits whose subjects carry choice/lesson verbs; on
feature- and release-style histories it can honestly keep near zero (myPM's
own history: 0 of 9). When that happens the summary says so and quotes the
escape hatch with a call-count estimate. With `--enrich`, the model also gets
the rule-dropped prefilter survivors — commits like "v0.3: live observer
rollout" that carry decisions without naming a verb — and anything the model
cannot type honestly (missing Gate-1 fields) is dropped with that reason
rather than left to quarantine later.

### `mypm council` — AI agents (EXPERIMENTAL)

Run the agent doctrines as **sequential** Claude API calls (requires `[ai]` +
`ANTHROPIC_API_KEY`; one full recall + completion per agent — mind the bill).
Each agent recalls its own ContextBundle (biased to its declared reads),
reasons under its doctrine, and returns **drafts** for you to author — the
runner never writes active knowledge. The doctrines are dual-runtime: they
also work as plain Claude Code **subagents**, which is the supported path; the
council runner exists for API-only environments and experiments.

```bash
mypm council --task "add rate limiting to the public API" --project payments
mypm council --task "..." --preset decision
mypm council --task "..." --agents principal,adversarial,performance
```

The six agents: **research** (explores the option space), **principal**
(decides among named options), **adversarial** (attacks the proposed design),
**performance** (measures cost and scaling), **oss** (gates change against the
recorded graph), **reflection** (distills what actually happened).

Presets: `minimal` (principal + adversarial — the default and the minimum
viable council for any non-trivial decision), `decision` (+ research +
performance), `full` (+ oss), `review` (oss only), `research`, `reflect`.

### `mypm capture-pr` and `mypm hook` — PR auto-capture

Merged PRs are decision-shaped, so they can capture themselves:

```bash
mypm hook install      # drops a post-merge git hook into .git/hooks/
mypm hook uninstall    # removes it (foreign hooks are left untouched)
mypm hook install --force   # replace an existing non-myPM post-merge hook
```

After install, every merge into the repo runs `mypm capture-pr`, which
inspects the merge commit and writes a **draft Decision** observation to the
inbox. Run it manually any time:

```bash
mypm capture-pr                      # inspect HEAD
mypm capture-pr --commit abc1234     # inspect a specific commit
mypm capture-pr --any-merge          # also capture plain branch merges, not just PR merges
mypm capture-pr --quiet              # say nothing when skipping (hook mode)
```

### `mypm observe` — live capture from Claude Code

The live observer closes the loop on AI sessions. The contract:

1. The agent doctrines instruct every agent to end its reply with a fenced
   ` ```mypm-capture ` block per durable finding (a small YAML observation).
2. `mypm init` installs `.claude/settings.json` with **Stop** and
   **SubagentStop** hooks that run `mypm observe` when a session or subagent
   finishes.
3. `observe` scans the session transcript for capture blocks, dedups them
   against the graph (Recall as the capture filter), and writes the survivors
   to the inbox.

Capture thereby stops depending on the model remembering to run a command —
the hook fires either way, and `mypm doctor` verifies the wiring actually
resolves on your machine. Observation ids are content-addressed, so
re-scanning the same transcript is idempotent. Outside a myPM repo the hook is
a silent no-op, and it always exits 0 so it can never block a session from
stopping.

```bash
mypm observe --transcript /path/to/transcript.jsonl   # manual run
mypm observe --quiet                                   # hook mode: reads hook JSON on stdin, never prints
```

### `mypm validate` — the build pass

Treat knowledge like code: it has a build.

```bash
mypm validate                  # warnings grouped by kind, capped per group
mypm validate --all            # every warning, uncapped
mypm validate --errors-only    # CI mode: errors decide, judgment calls don't
```

Checks, across every node and edge file: schema validity (required fields,
field types, legal status/confidence values), edge legality (the
type-pair table), referential integrity (no edge pointing at a missing node),
acyclicity (`part_of`, `builds_on`, `establishes`, `supersedes` must be DAGs;
`depends_on` cycles warn), malformed-file containment (one bad file is
reported, not fatal), near-duplicate detection (inverted-index candidate
pairing, capped at 3 reports per node so a dense graph can't flood the
output), and scope drift (a global node that names one specific project, or a
cross-project edge). Run it before committing knowledge, and in CI.

### `mypm index`

Force-rebuild the derived SQLite index at `knowledge/.index/graph.db`. You
rarely need this — retrieval detects when files changed under the index and
rebuilds automatically, and `distill`/`review` rebuild after promotion. It
exists for completeness and for scripts.

---

## 7. Claude Code integration

`mypm init` wires the repo so Claude Code participates in the loop natively:

- **`.claude/CLAUDE.md`** — tells every session to run
  `mypm retrieve --task "..." --project <id>` before significant work, and
  lists the command crib sheet.
- **`.claude/agents/*.md`** — the six doctrines are *dual-runtime*: each file
  is a valid Claude Code **subagent** (frontmatter with name/description/tools)
  *and* the system prompt `mypm council` sends over the API. One file, two
  runtimes, no drift. Under either runtime the agent recalls with
  `mypm retrieve --agent <name>` first and emits `mypm-capture` blocks last.
- **`.claude/council.md`** — the agents' mandates and conflict-resolution
  rules (e.g. adversarial findings must be addressed, not dismissed).
- **`.claude/settings.json`** — generated with the installing interpreter
  pinned: `SessionStart → mypm orient` (the graph's load-bearing slice lands
  in every session's context before the first prompt — recall you don't have
  to remember to ask for) and `Stop`/`SubagentStop → mypm observe` (the live
  observer, § observe).
- **`/enrich-drafts`** (`.claude/commands/enrich-drafts.md`) — a slash command
  that has the session walk every pending draft, research its source commit,
  and `mypm review fill` what the evidence supports, citing the sha inline and
  leaving unknowable fields empty. It fills; it never promotes. Run
  `mypm review stats` afterward to see what the enrichment saved you.

The division of labor is strict and enforced by the verbs themselves: sessions
may **retrieve**, **capture**, and **fill**; only you **approve**.

---

## 8. Configuration and environment variables

| Variable | Effect |
|---|---|
| `MYPM_ROOT` | knowledge root to use when no `--root` flag is given (beats walk-up discovery) |
| `MYPM_GLOBAL_ROOT` | a **shared** knowledge root (its own repo, created with `mypm init`); its global-scope nodes — patterns, preferences — join every local `retrieve`/`orient`/`search`/`show`. Local nodes win id collisions; other repos' project scopes never leak. This is the mechanism by which knowledge is meant to compound across repositories. |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | enables the LLM paths (proposer, `bootstrap --enrich`, council) |
| `MYPM_NO_LLM=1` | force-disable all LLM paths even if a key is present (used by tests/CI) |
| `MYPM_CLAUDE_MODEL` | override the default model (`claude-opus-4-8`) for LLM paths |
| `MYPM_NO_SEMANTIC=1` | force-disable semantic embeddings; retrieval is purely lexical |
| `MYPM_EMBED_MODEL` | override the local sentence-transformers model |
| `EDITOR` | editor used by interactive review's `[e]dit` action (default `vi`) |

**The shared-root pattern**: create one knowledge repository for yourself or
your team (`git init team-knowledge && cd team-knowledge && mypm init`), set
`export MYPM_GLOBAL_ROOT=~/team-knowledge/knowledge` in your shell profile,
and promote anything reusable to `global` scope there. Every repo you work in
recalls it from day one; `git pull` is the sync protocol. Gate 3 (lesson →
pattern recurrence) fires within a root, so recurring lessons worth
generalizing belong in the shared root's inbox.

Degradation is silent and safe by design: no key → rule-based typing; no
`sentence-transformers` → lexical retrieval; no `anthropic` SDK → council and
enrich refuse with a clear message. The deterministic substrate always works.

---

## 9. Everyday workflows

**Before a task** (or let the Claude Code session do it):

```bash
mypm retrieve --task "migrate the queue consumer to NSQ" --project payments
```

**When something durable happens:**

```bash
mypm capture --text "..." --project payments --type lesson --takeaway "..."
```

**A few times a week** — flush the funnel (inbox and drafts accumulate from
capture, hooks, sessions, and bootstrap):

```bash
mypm reflect          # inbox -> drafts (+ check inbox/held/ for quarantines)
mypm distill          # batch-promote what's complete
mypm review           # decide the rest, one draft at a time
mypm validate         # the build pass, before committing
git add knowledge/ && git commit -m "knowledge: <what was learned>"
```

**After a big bootstrap or a busy week** — let a session do the legwork, then
approve:

```
/enrich-drafts            (in Claude Code)
mypm review               (you: approve/reject each draft, evidence shown inline)
mypm review stats         (did enrichment actually save time?)
```

**For a consequential decision** — convene the council:

```bash
mypm council --task "choose the queueing system for fanout" --project payments --preset decision
```

---

## 9½. Teams and CI

The graph is plain text in git, so the team story is mostly git's story:

- **Knowledge changes are PR diffs.** A new decision node, a supersession, a
  filled `root_cause` — all reviewable line-by-line like code. Put
  `knowledge/ @your-team-leads` in `CODEOWNERS` to route them.
- **CI gates the merge.** A ready-made workflow ships at
  `mypm/templates/ci/knowledge-validate.yml` — copy it to
  `.github/workflows/`. It runs `mypm validate --errors-only` only when
  `knowledge/**` changes: schema/edge/integrity errors fail the PR; near-
  duplicate and scope-drift warnings stay advisory (they need judgment, not a
  gate).
- **Merge conflicts are rare by construction.** Edge ids are deterministic
  (`<from>--<type>--<to>`), so two branches creating the same relationship
  produce identical files; observation ids are content-addressed or
  uuid-suffixed; nodes are per-fact files, not one shared ledger.
- **The shared root is a normal repo.** Team-wide patterns and preferences
  live in the `MYPM_GLOBAL_ROOT` repository, reviewed and pulled like
  anything else (see §8).

## 10. Troubleshooting

**"nothing pending — no drafts await review."** — The funnel is empty at that
stage. Check `mypm reflect` first (observations may still be in the inbox) or
`ls knowledge/inbox/`.

**An observation keeps failing Gate 1.** — It was quarantined: read
`knowledge/inbox/held/<id>.yml`, which embeds the exact failure reasons
(`FAIL specific`, `FAIL typeable`, `FAIL min-structure`, `FAIL non-redundant`).
Edit the file, then `mypm reflect --retry-held`.

**`approve` says "still blocked at Gate 2".** — The printed reasons name the
missing fields or the missing graph link. Your supplied fields were saved;
add what's named (`--field ...` or `--link relates_to:project_<id>`) and
approve again.

**An edge won't validate.** — Check the legality table in §5: each edge type
constrains its endpoint types (`motivates` must go lesson → decision/pattern;
`supersedes` requires both ends the same type; etc.).

**Retrieval returns something stale.** — The index self-heals on staleness,
but you can always force it: `mypm index`. If a superseded node appears,
check that the `supersedes` edge exists and the old node's status is
`superseded` (`mypm validate` will flag inconsistencies).

**Something silent isn't working.** — Run `mypm doctor` first. It checks the
root, the index, the build pass, the git hook, and — the classic — whether
the executables in `.claude/settings.json` hook commands actually resolve
(a settings.json from before v0.4 used a bare `mypm`, which fails silently
under Claude Code's PATH; `rm .claude/settings.json && mypm init` regenerates
it pinned to your interpreter).

**"no knowledge root found".** — You're outside any myPM repo (discovery
walks up from cwd and found nothing). `mypm init` here, `--root <path>`, or
`export MYPM_ROOT=<path>`.

**Hooks aren't capturing.** — `mypm hook install` must run inside the git
repo (it writes `.git/hooks/post-merge`); the Claude Code observer requires
`.claude/settings.json` (re-run `mypm init` in a repo that predates it — it
only creates, never overwrites). Both are silent no-ops outside a myPM repo —
and `mypm doctor` makes their silence loud.

**Working offline / without a key.** — Everything works; AI paths fall back
to rules. Set `MYPM_NO_LLM=1` / `MYPM_NO_SEMANTIC=1` to make the fallback
explicit and deterministic (the test suite does exactly this).

**Tests** (for contributors): `python tests/run_all.py` — every test file is a
self-running harness; no pytest needed.
