---
id: decision_review_fill_saves_evidence_backed_fields
type: decision
title: review fill saves evidence-backed fields but can never promote, while approve
  promotes, because the authorship boundary must be enforced by verbs, not instructions
scope: project:mypm
status: active
confidence: medium
source:
  type: conversation
tags:
- review
- authorship
- gates
created_at: '2026-06-11T11:26:41+00:00'
updated_at: '2026-06-11T11:26:41+00:00'
choice: split the enrichment verb (fill) from the authorship verb (approve)
rationale: a session that only runs fill cannot author knowledge no matter what it
  writes; promotion stays a human act by API construction
alternatives:
- let sessions approve with an audit trail
- trust prompt-level rules
consequences: enrich-drafts sessions are safe by construction; the review UI must
  show body and evidence inline or fast approval becomes a rubber stamp (fixed 2026-06-11)
---

review fill saves evidence-backed fields but can never promote, while approve promotes, because the authorship boundary must be enforced by verbs, not instructions
