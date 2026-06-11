---
id: lesson_a_cwd_relative_default_root_made
type: lesson
title: a cwd-relative default root made mypm silently fabricate empty graphs from
  repo subdirectories
scope: project:mypm
status: active
confidence: medium
source:
  type: incident
tags:
- cli
- roots
- correctness
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
takeaway: discover the root by walking up like git does; never mkdir on a read path;
  error with a remedy when nothing is found
root_cause: --root defaulted relative to cwd and ensure_layout ran on every command
  including reads
trigger: 'audit probe: retrieve from repo/src/deep returned zero nodes with no warning
  and littered a stray knowledge/ tree there'
---

a cwd-relative default root made mypm silently fabricate empty graphs from repo subdirectories
