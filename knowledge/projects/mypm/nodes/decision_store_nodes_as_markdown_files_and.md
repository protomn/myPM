---
id: decision_store_nodes_as_markdown_files_and
type: decision
title: store nodes as markdown files and edges as YAML files; derive a gitignored
  SQLite index because git-native text is the database of record
scope: project:mypm
status: active
confidence: medium
source:
  type: conversation
tags:
- storage
- architecture
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
choice: files are the database; SQLite index is a derived, disposable cache
rationale: plain text diffs, blames, and merges; no vendor lock-in; hand-editable
  with cat and grep
alternatives:
- SQLite as source of truth
- a vector DB
- one big JSON store
consequences: commands that skip the index pay O(N) file parses; the index needs staleness
  detection (count+mtime fingerprint) and self-heals on read
context: chosen at v0.1 when the storage layer was designed
---

store nodes as markdown files and edges as YAML files; derive a gitignored SQLite index because git-native text is the database of record
