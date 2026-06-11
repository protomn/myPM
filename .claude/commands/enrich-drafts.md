---
description: Enrich pending myPM drafts with evidence from git history — fills fields, never promotes
allowed-tools: Bash, Read, Grep, Glob
---

# Enrich myPM drafts from repository evidence

Pending myPM drafts (from `mypm bootstrap`, the PR hook, or the live observer)
are blocked at Gate 2 on fields a commit subject can't supply: `root_cause`,
`alternatives`, `consequences`, `rationale`. You have what the extraction rules
don't: tools. The source commit sha is in every draft's provenance line — go
read the actual change and fill in what the evidence supports.

## Procedure

1. Run `mypm review list` to see the pending drafts and what each is missing.
2. For each draft (work oldest-first; stop after ~20 and report — don't grind
   the whole backlog in one pass):
   a. Read the draft file (`knowledge/projects/<id>/nodes/<draft>.md` or
      `knowledge/global/nodes/`). The body's `_Source:` line carries the
      commit sha and PR number if there is one.
   b. Investigate the evidence: `git show --stat -p <sha>` (truncate huge
      diffs — the first ~200 lines usually carry the intent), the commit body,
      and `gh pr view <N> --comments` when a PR ref exists.
   c. Fill ONLY what the evidence supports, citing it inside the field text:

      ```
      mypm review fill <draft-id> \
        --field root_cause="the CSR index buffer was reallocated without updating nnz (per diff of a1b2c3d4)" \
        --field consequences="iterative solver tolerance becomes a tunable (PR #25138 discussion)"
      ```

      List-valued fields use `;` separators:
      `--field alternatives="banded Cholesky (rejected in PR thread); keep spsolve"`
   d. If you notice the draft relates to another existing node, propose the
      edge: `--link relates_to:<node_id>` (it stays a proposal until promotion).

## Non-negotiable rules

- **Use `mypm review fill` ONLY. Never run `approve`, `supersede`, `reject`,
  `merge`, or `distill`.** Promotion is the human's act of authorship — your
  job ends at evidence-backed fields.
- **An empty field is correct when the evidence is absent.** A fabricated
  `root_cause` is worse than a missing one: it looks authoritative and poisons
  the graph. If the diff doesn't show why, leave it and say so in your report.
- **`alternatives` only when actually named** — in the diff, the commit body,
  or the PR discussion. "Things that hypothetically could have been done" are
  not alternatives, they are fiction.
- Cite the evidence (sha or PR#) inside every field you fill, so the human can
  spot-check in seconds at approval time.

## Report

End with a short table: draft id → fields filled / left empty (and why), so the
human knows exactly what to review before running `mypm distill`.
