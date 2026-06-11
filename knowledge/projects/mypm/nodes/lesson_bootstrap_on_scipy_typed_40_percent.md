---
id: lesson_bootstrap_on_scipy_typed_40_percent
type: lesson
title: bootstrap on scipy typed 40 percent of history as decisions until merged PRs
  stopped being auto-typed
scope: project:mypm
status: active
confidence: medium
source:
  type: benchmark
tags:
- bootstrap
- extraction
- credulity
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
takeaway: bulk extraction must demand decision language in the PR title; only the
  live post-merge hook may stay credulous, because there a human just chose to merge
  that one PR
root_cause: on GitHub-flow repos every commit lands via a PR, so a merge is provenance,
  not proof of a decision
trigger: 'scipy stress test: blanket-typing PR merges flooded the inbox with routine
  maintenance'
---

bootstrap on scipy typed 40 percent of history as decisions until merged PRs stopped being auto-typed
