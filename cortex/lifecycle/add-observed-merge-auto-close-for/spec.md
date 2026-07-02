# Specification: add-observed-merge-auto-close-for

## Problem Statement

After #342, morning-review's "PR already merged — main is up to date" exit (`skills/morning-review/references/walkthrough.md` §6 step 2) stops with a soft advisory telling the operator to "verify this session's completed-feature tickets are `complete`." Research (this feature's `research.md`) established that a *full* observed-merge auto-close — the ticket's original premise — is the wrong fix here: §6a (post-merge sync) is structurally **skipped** on this exit, so the local checkout is **stale** relative to the just-landed out-of-band merge; there is **no push machinery** on this path to fix main; and a trustworthy closer needs a remote on-main check that does not yet exist and is shared with the deferred reconciliation work (building it here would be known-rework). Worse, #342's current advisory is itself mildly misleading — it implies a local completeness check is authoritative, but local is stale here. This feature ships the proportionate fix: a small, filter-free, fetch-first correctness tweak to the existing advisory that names the tickets to check and hands the operator a correct manual procedure — no auto-close, no new mechanism. The durable observed-merge closer, stranded-merged-work reconciliation, and the general §6b bare-ID concern are deferred to a reconciliation follow-up ticket.

## Phases
- **Phase 1: Advisory correctness tweak** — make the §6 step-2 "PR already merged" advisory fetch-first, ticket-specific, and actionable, without adding a close mechanism or tripping the #342 ordering guard.

## Requirements

1. **(Must)** **Upgrade the §6 step-2 "PR already merged" advisory to be fetch-first, ticket-specific, and actionable.** The revised advisory at the `state == "MERGED"` exit of `skills/morning-review/references/walkthrough.md` §6 step 2 must: (a) state that local `main` may be behind after an out-of-band merge (§6a sync is skipped on this path) and instruct the operator to run `git fetch origin main` (or pull) **first**, before checking any ticket; (b) identify **this session's completed-feature backlog tickets** as the set to check (the completed-feature list / `backlog_id`s already surfaced in Section 2 from `overnight-state.json`); (c) instruct that for any such ticket still open **after** the fetch, the operator closes it via §6b's documented backlog closer and pushes. Soft declarative phrasing only — no `MUST`/`CRITICAL`/`REQUIRED` tokens. **Acceptance**: in the §6 step-2 MERGED-exit span of `walkthrough.md`, `grep -iE "git fetch|git pull"` matches (fetch-first instruction present) AND the span references checking this session's completed-feature tickets AND points to §6b for the close; `just test` exits 0 (guard + parity suites green). **Phase**: Advisory correctness tweak.

2. **(Must)** **Preserve the #342 closure-ordering guard by not embedding the close literal in the pre-`gh pr merge` region.** The §6 step-2 exit physically precedes the first `gh pr merge` literal in `walkthrough.md` (~L481), and `tests/test_morning_review_status_close_ordering.py::test_status_complete_appears_after_merge_in_source_order` requires the first `cortex-update-item` occurrence to appear *after* that merge literal. Therefore the revised advisory must **not** contain the literal string `cortex-update-item` or `update_item` (nor a `… --status complete` close command) in the §6 step-2 span — it references §6b's closer by section instead. **Acceptance**: `grep -nE "update[-_]item" ` over the §6 step-2 MERGED-exit span returns no match; `tests/test_morning_review_status_close_ordering.py` exits 0 (all 7 tests, incl. the ordering and positive-control tests). **Phase**: Advisory correctness tweak.

3. **(Must)** **Regenerate the dual-source mirror in the same commit.** Canonical `skills/morning-review/` edits require the `plugins/cortex-overnight/skills/morning-review/` mirror regenerated (`just build-plugin`) and staged in the same commit (drift pre-commit hook + `tests/test_dual_source_reference_parity.py`). **Acceptance**: `git diff --exit-code` between canonical `skills/morning-review/references/walkthrough.md` and the mirror shows byte-parity; `tests/test_dual_source_reference_parity.py` exits 0. **Phase**: Advisory correctness tweak.

## Non-Requirements

- Does **NOT** add an observed-merge auto-close (no `cortex-update-item --status complete` executed by the skill on this exit) — rejected on evidence: reintroduces #342's just-removed blind-close class and closes on a merge this review did not perform.
- Does **NOT** add a local ticket-status filter to select "still-open" tickets — a local read is stale at this exit and cannot distinguish already-complete-on-main from open-on-main, so it would over-fire.
- Does **NOT** build the remote on-main check (`gh api …?ref=main`), any push automation, or a reconciliation flow — these belong in the deferred follow-up ticket.
- Does **NOT** touch §6b, its backend-routing three-arm gate, or its idempotence.
- Does **NOT** modify `tests/test_morning_review_status_close_ordering.py` or `skills/morning-review/SKILL.md` (body-only advisory change in `walkthrough.md`; the guard stays intact by Requirement 2's literal-avoidance).
- Does **NOT** address stranded-merged-work reconciliation (orphaned integration branches/PRs/worktrees + runner re-pick backoff) or the general §6b bare-ID / backlog-numbering-trust concern — split to the reconciliation follow-up ticket.

## Edge Cases

- **No completed features this session**: Section 2/6b are already skipped when there are no completed features; the §6 step-2 advisory names an empty set (or is not applicable) and adds no noise — it never instructs a fetch-and-close for zero tickets.
- **Operator declines to fetch / does nothing**: the advisory is soft and non-blocking (like #342's Req-6/7 notes); review completes normally, ticket simply stays open (visible, not silently wrong).
- **Write-back actually succeeded (the common case)**: after `git fetch`, the ticket already reads `complete` on main, so the operator closes nothing — the fetch-first ordering is exactly what prevents a spurious close against a stale local read.
- **Ticket already `complete` on the operator's post-fetch check**: no action; §6b's closer (if the operator uses it) is idempotent regardless.

## Changes to Existing Behavior

- **MODIFIED**: the §6 step-2 "PR already merged — main is up to date" advisory changes from a generic "verify this session's completed-feature tickets are `complete`" note to a fetch-first, ticket-specific procedure (fetch → check named tickets → close via §6b + push only if still open). No behavioral/code change — advisory prose only.

## Technical Constraints

- Edit canonical `skills/morning-review/references/walkthrough.md` only; regenerate the `cortex-overnight` mirror in the **same commit** (Requirement 3).
- Ordering-guard literal-collision avoidance is load-bearing (Requirement 2): keep the §6 step-2 span free of `cortex-update-item` / `update_item` / `--status complete` literals; reference §6b's closer by section.
- Soft declarative phrasing throughout; no new `MUST`/`CRITICAL`/`REQUIRED` tokens (MUST-escalation policy).
- Applies existing ADR-0004 (merge-is-terminal; #339 durability) — no new ADR. L1 surface ratchet N/A (frontmatter untouched); 500-line SKILL cap N/A (edit is in `references/walkthrough.md`, not SKILL.md).
- Commit via `/cortex-core:commit`; imperative, ≤72-char subject.

## Open Decisions

None. (Auto-close vs advisory resolved by research → minimal fetch-first advisory, user-selected. Guard-collision resolved → reference §6b, no literal in §6 step 2. Deferred concerns → reconciliation follow-up ticket, filed at Complete.)

## Proposed ADR

None considered. The advisory tweak applies existing ADR-0004; it introduces no hard-to-reverse decision, no surprising-without-context choice, and no new trade-off warranting a record.
