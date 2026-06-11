---
id: decision_retrieval_is_lexical_first_semantic_embeddings
type: decision
title: retrieval is lexical-first; semantic embeddings blend in at 0.2 weight because
  semantic is recall rescue, not primary retrieval
scope: project:mypm
status: active
confidence: medium
source:
  type: conversation
tags:
- retrieval
- ranking
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
choice: lexical term-overlap seed, semantic cosine at 0.2 weight when the optional
  embedder is installed
rationale: a node with any lexical hit always outranks a purely semantic match; deterministic
  and offline by default
alternatives:
- semantic-primary with lexical fallback
- pure lexical
- hosted embedding API
consequences: synonym-phrased tasks miss without the [semantic] extra; behavior stays
  predictable without torch installed
---

retrieval is lexical-first; semantic embeddings blend in at 0.2 weight because semantic is recall rescue, not primary retrieval
