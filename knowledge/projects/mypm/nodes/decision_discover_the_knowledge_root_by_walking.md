---
id: decision_discover_the_knowledge_root_by_walking
type: decision
title: discover the knowledge root by walking up from cwd like git does because a
  cwd-relative default fabricated empty graphs
scope: project:mypm
status: active
confidence: medium
source:
  type: conversation
tags:
- cli
- roots
- architecture
created_at: '2026-06-11T11:28:14+00:00'
updated_at: '2026-06-11T11:28:14+00:00'
choice: resolve the root as explicit --root > MYPM_ROOT > walk-up discovery; never
  mkdir on read paths
rationale: a memory that answers wrongly depending on your cwd is worse than no memory;
  git solved this with .git discovery decades ago
alternatives:
- keep cwd-relative default with a warning
- require --root always
- config file per repo
consequences: init is the only creating command; rootless invocations error with a
  remedy; hooks resolve silently
---

discover the knowledge root by walking up from cwd like git does because a cwd-relative default fabricated empty graphs
