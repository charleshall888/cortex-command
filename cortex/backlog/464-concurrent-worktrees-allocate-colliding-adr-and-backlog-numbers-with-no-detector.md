---
schema_version: "1"
uuid: 54f7683e-a79a-4e22-b3d6-44d52f0d0deb
title: Concurrent worktrees allocate colliding ADR and backlog numbers with no detector
status: complete
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-07
complexity: moderate
criticality: low
spec: cortex/lifecycle/concurrent-worktrees-allocate-colliding-adr-and/spec.md
areas: ['docs', 'backlog']
lifecycle_phase: complete
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
   observed in `cortex/adr/` at read time. `detect_duplicates`
   (`cortex_command/adr_citation_audit.py:128-142`, backlog #304) already emits a
   `duplicate_number` finding for exactly this case — the gap is not detection, it's that
   the audit is report-only and manually invoked, so nothing runs it before or during the
   merge that lands the collision.
2. **The race is decided at plan time in the home repo, not across worktrees.** Concurrent
   plan-gen sub-agents (dispatched in Step 3b, results handled in Step 3c —
   `cortex_command/overnight/prompts/orchestrator-round.md:474`) run in parallel against
   the one shared home-repo `cortex/adr/`, each globbing it to pick the next number before
   any per-feature worktree exists; the runner does not commit `plan.md` into each
   feature's own integration worktree until after the round returns
   (`orchestrator-round.md:483`). Both sub-agents read the same unchanged directory and
   both bake `0080` into their plan text — a TOCTOU race on one shared glob at plan time,
   not two directories each blind to the other.

Backlog IDs are better off but not solved. `_get_next_id()`
(`cortex_command/backlog/create_item.py:83`) is at least a tool-owned allocator, and every
item carries a `uuid:` frontmatter field, so identity survives a display-ID collision. But
the allocation itself is still `max(glob(...)) + 1` over a per-worktree directory — two
concurrent overnight features filing tickets will both land on the same NNN. The UUID
means the collision is recoverable rather than silent data loss; it does not prevent it.

So: **no existing prevention for either.** ADRs have no allocator and no *enforced*
detector — `detect_duplicates` exists but nothing arms it automatically; backlog has an
allocator with the same race plus a UUID safety net.

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

## Rejected approaches

Five candidate fixes were considered and rejected. Recorded here with the measurement
that killed each, so a future session does not re-derive and re-reject them.

- spec-time **claim-by-creating** (write a stub ADR file at spec time to reserve the
  number): inverts gate-then-emit — the untracked stub itself blocks the merge that
  later lands the real, filled-in ADR under the same path.
- **post-merge allocation** with citation rewrite (let numbers collide, then renumber and
  rewrite citations after the merge): the rewriting scanner covers `.md`/`.py` only, so
  it half-applies and leaves thousands of `.gd`/`.json` citations pointing at the wrong
  number.
- arming the existing detector as-is: across two repos it currently produces 631
  findings, 0 actioned, 5 of them sanctioned false positives — arming it unmodified would
  fail merges on noise, not on the real defect class.
- **slug-primary** or date/hash identity (drop the sequential NNN as the primary key):
  permanently mixes the corpus's identity scheme, and the date-keyed variant does not
  even prevent same-run collisions — two sub-agents in the same round still glob the same
  date.
- a blocking gate (fail the merge on any duplicate number): contradicts #304's ratified
  report-only posture for ADR tooling.

## Touch-points

- Precedent: backlog #027 (complete) — `O_EXCL` fix for the deferral-ID race
- Related: backlog #304 — report-only ADR citation auditor
- Source incident: wild-light `overnight-2026-08-07-0252`, PR #30, commit `7ebc1ded`
