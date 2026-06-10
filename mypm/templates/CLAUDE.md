# Engineering Memory — myPM

This project uses myPM for persistent engineering memory. The knowledge graph
holds what you have decided, why, what broke, and how you like to work.

## Before starting work

Retrieve the relevant context before any significant task:

```
mypm retrieve --task "<describe the task>" --project <project-id>
```

## Commands

```
mypm bootstrap --limit 100 --write          seed candidates from git history (dedup vs the graph)
mypm capture --text "..." --project <id>   record a raw observation
mypm reflect [--retry-held]                 Gate 1: type observations into draft nodes
mypm distill                                Gates 2+3: promote drafts, wire edges, rebuild index
mypm review [list|approve|reject|merge|supersede]   per-draft approval surface
mypm retrieve --task "..." --project <id>  recall context for a task
mypm council --task "..."                   run agent doctrines as Claude calls
mypm hook install                           auto-capture draft Decisions from merged PRs
mypm validate                               run the build/lint pass
```

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
Knowledge that enters the loop compounds across every project that follows.
