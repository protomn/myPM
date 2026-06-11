---
id: decision_capture_from_ai_sessions_is_guaranteed
type: decision
title: capture from AI sessions is guaranteed by Stop/SubagentStop hooks running mypm
  observe because prompt compliance is hope, not a mechanism
scope: project:mypm
status: active
confidence: medium
source:
  type: conversation
tags:
- observer
- hooks
- capture
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
choice: Stop/SubagentStop hooks scan the transcript for mypm-capture blocks; agents
  emit blocks while reasoning is hot
rationale: hooks fire whether or not the model remembers; content-addressed observation
  ids make re-scans idempotent
alternatives:
- instruct agents to run mypm capture themselves
- mine raw transcripts offline
consequences: the hook environment must resolve the executable — settings.json pins
  sys.executable (bare 'mypm' fails silently in venv installs, found 2026-06-11)
---

capture from AI sessions is guaranteed by Stop/SubagentStop hooks running mypm observe because prompt compliance is hope, not a mechanism
