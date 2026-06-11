---
id: preference_no_pytest_every_test_file_is
type: preference
title: 'no pytest: every test file is a self-running harness executed by tests/run_all.py
  in its own process'
scope: project:mypm
status: active
confidence: medium
source:
  type: conversation
tags:
- testing
- conventions
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
statement: tests are dependency-free self-running harnesses; python tests/run_all.py
  is the one entry point
strength: strong
rationale: zero test dependencies, per-file process isolation so import-time env tweaks
  never leak
---

no pytest: every test file is a self-running harness executed by tests/run_all.py in its own process
