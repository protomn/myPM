# Engineering Memory — myPM

This project uses myPM for persistent engineering memory. The knowledge graph
holds what you have decided, why, what broke, and how you like to work.

## Before starting work

Retrieve the relevant context before any significant task:

```
mypm retrieve --task "<describe the task>" --project <project-id>
```

## Commands

The root is discovered (walk-up from cwd, like git); run these from anywhere
in the repo. Only `mypm init` creates a root.

```
mypm bootstrap --limit 100 --write          seed candidates from git history (dedup vs the graph)
                                            (--enrich lets Claude type what the rules can't)
mypm capture --text "..." --project <id>   record a raw observation (auto-links to the project node)
mypm reflect [--retry-held]                 Gate 1: type observations into draft nodes
mypm distill                                Gates 2+3: promote drafts, wire edges, rebuild index
mypm review [list|fill|approve|reject|merge|supersede]   per-draft approval surface
                                            (fill saves evidence-backed fields, never promotes —
                                             the verb LLM sessions may use; see /enrich-drafts)
mypm review approve --all                   bulk-promote every draft already passing Gate 2
mypm review stats                           time-to-decision report, filled vs bare drafts
mypm retrieve --task "..." --project <id>  recall context for a task (--format text for humans)
mypm orient                                 compact session-start bundle (SessionStart hook payload)
mypm show <id> / mypm search <terms>        read the graph without cat/grep archaeology
mypm feedback good|bad                      rate the last recall (the Recall Win Rate KPI)
mypm stats                                  both loops measured: review cost + recall win/citation rate
mypm doctor                                 diagnose wiring: root, index, hooks, extras
mypm hook install                           auto-capture draft Decisions from merged PRs
mypm observe --transcript <path>            capture mypm-capture blocks from a session
                                            (auto-wired: Stop/SubagentStop hooks in .claude/settings.json)
mypm council --task "..."                   EXPERIMENTAL: doctrines as sequential Claude calls
mypm validate [--errors-only]               run the build/lint pass (warnings grouped + capped)
```

Set `MYPM_GLOBAL_ROOT` to a shared knowledge repo and its global-scope nodes
(patterns, preferences) join every recall here — the mechanism for knowledge
to compound across repositories.

## Knowledge layout

```
knowledge/
├── inbox/               raw observations (pre-graph; most evaporate at Gate 1)
├── global/nodes/        cross-project patterns and preferences
├── projects/<id>/
│   ├── project.md       the Project node — root context and ownership boundary
│   └── nodes/           project-scoped nodes: components, decisions, lessons
└── edges/               typed relationships between nodes (scope-free)
```

The index at `knowledge/.index/` is a derived cache — gitignored and rebuildable.

## Agents and governance

- `.claude/council.md` — the six agents, their mandates, and conflict-resolution rules
- `.claude/agents/` — per-agent doctrines: invocation, recall contract, output format
- `.claude/architecture/` — full architecture documentation

**The Golden Loop**: Recall → Reason → Capture → Distill → repeat.
Knowledge that enters the loop is meant to compound across every project
that follows — the bet this tool exists to test.
