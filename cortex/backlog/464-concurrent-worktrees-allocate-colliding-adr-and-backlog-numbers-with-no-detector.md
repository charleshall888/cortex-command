---
schema_version: "1"
uuid: 54f7683e-a79a-4e22-b3d6-44d52f0d0deb
title: Concurrent worktrees allocate colliding ADR and backlog numbers with no detector
status: should-have
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-07
---
## Why

Overnight session `overnight-2026-08-07-0252` (wild-light) produced two features that each
authored an ADR numbered **0080** against the same base commit, in separate worktrees:

- `0080-the-python-suite-runs-inside-test-command.md` (committed 02:15)
- `0080-version-train-membership-is-derived-not-authored.md` (committed 02:34)

The filenames differ, so `git merge` joined both with **no conflict and no warning**. Two
ADRs claiming one number reached the integration branch silently, and six in-tree
references cited a now-ambiguous bare "ADR-0080". It was caught by hand during morning
review, not by any gate.

This is the same defect class as the already-fixed #027 (`next_question_id()` race in
`deferral.py`) — a `max(existing) + 1` allocator read concurrently — but with two
differences that make the existing remedy inapplicable:

1. **ADRs have no allocator at all.** There is no `cortex_command` code that assigns an
   ADR number. The number is chosen by the model writing the spec, from whatever it
   observed in `cortex/adr/` at read time. `cortex-adr-citation-audit`
   (`cortex_command/adr_citation_audit.py`, backlog #304) is report-only and audits
   *citations*, not numbering — it does not detect duplicate ADR numbers.
2. **#027's `O_CREAT | O_EXCL` remedy cannot reach across worktrees.** It makes the
   filename claim atomic *within one directory*. Overnight worktrees each hold their own
   checkout of `cortex/adr/`, so two agents claiming `0080` in two different directories
   both succeed. Same-directory atomicity is structurally blind to the sibling worktree.

Backlog IDs are better off but not solved. `_get_next_id()`
(`cortex_command/backlog/create_item.py:83`) is at least a tool-owned allocator, and every
item carries a `uuid:` frontmatter field, so identity survives a display-ID collision. But
the allocation itself is still `max(glob(...)) + 1` over a per-worktree directory — two
concurrent overnight features filing tickets will both land on the same NNN. The UUID
means the collision is recoverable rather than silent data loss; it does not prevent it.

So: **no existing solution for either.** ADRs have neither an allocator nor a detector;
backlog has an allocator with the same race plus a UUID safety net.

## Role

Decide and implement how monotonic identifiers are allocated when N agents work in N
worktrees off one base. Detection and allocation are separable and can ship independently
— a detector is cheap and closes the silent-merge hole immediately.

## Integration

- `cortex_command/backlog/create_item.py` — `_get_next_id()`
- `cortex_command/adr_citation_audit.py` — nearest existing ADR-aware surface
- `cortex_command/overnight/deferral.py` — the #027 precedent to reuse or supersede
- Overnight merge path (`cortex_command/overnight/`) — where a pre-merge detector would arm

Worth evaluating: reserve-at-plan-time from the shared parent repo rather than the
worktree; content-addressed or UUID-primary ADR identity with the NNN as display only
(mirroring what backlog items already do); or a pre-merge duplicate-number check that
fails the merge instead of silently accepting both files.

Note that wild-light's CLAUDE.md already carries a partial mitigation as prose — "Cite
ADRs by meaning, not bare number" — which is why the collision was recoverable at review
time. That convention should inform, not substitute for, the fix.

## Edges

- **Non-goal**: renumbering the wild-light ADRs. Already done by hand in wild-light PR #30
  (first-claim wins; the later ADR moved to 0081).
- **Non-goal**: re-running the overnight session.
- A fix must not assume a shared filesystem lock is visible across worktrees.
- Renumbering after the fact is not free — it rewrites every citation, so allocation
  should aim to be right the first time rather than repairable.

## Touch-points

- Precedent: backlog #027 (complete) — `O_EXCL` fix for the deferral-ID race
- Related: backlog #304 — report-only ADR citation auditor
- Source incident: wild-light `overnight-2026-08-07-0252`, PR #30, commit `7ebc1ded`
