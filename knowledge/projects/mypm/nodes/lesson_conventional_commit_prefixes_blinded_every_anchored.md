---
id: lesson_conventional_commit_prefixes_blinded_every_anchored
type: lesson
title: conventional-commit prefixes blinded every anchored typing rule until the prefix
  was split off as a hint
scope: project:mypm
status: active
confidence: medium
source:
  type: benchmark
tags:
- bootstrap
- extraction
- parsing
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
takeaway: split the conventional prefix off, use it as a typing hint, and run the
  content rules against the remainder
root_cause: column-0 anchored verb regexes never fire past a 'PERF:'-style prefix;
  'replace' at column 7 is invisible to ^-anchored rules
trigger: 'scipy stress test: ''PERF: replace spsolve with CG'' was not recognized
  as a supersession'
---

conventional-commit prefixes blinded every anchored typing rule until the prefix was split off as a hint
