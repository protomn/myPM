---
id: lesson_the_free_bootstrap_pass_produced_zero
type: lesson
title: the free bootstrap pass produced zero candidates from myPM's own nine-commit
  history during the 2026-06-11 audit
scope: project:mypm
status: active
confidence: medium
source:
  type: incident
tags:
- bootstrap
- extraction
- cold-start
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
takeaway: --enrich must be able to rescue rule-dropped prefilter survivors, and an
  empty run must say why and quote the escape hatch with a cost estimate
root_cause: the rule pass requires choice/lesson verbs in the subject; feature- and
  release-style subjects carry decisions without ever naming a verb the rules know
trigger: 'audit probe: every commit including ''v0.3: live observer'' dropped as no-clear-decision'
---

the free bootstrap pass produced zero candidates from myPM's own nine-commit history during the 2026-06-11 audit
