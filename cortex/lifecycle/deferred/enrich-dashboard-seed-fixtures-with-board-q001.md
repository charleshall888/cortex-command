# Deferred Question: enrich-dashboard-seed-fixtures-with-board #001

**Severity**: blocking
**Created**: 2026-07-28T12:58:57.529025+00:00

## Context
Review cycle 0 returned verdict: ERROR

## Question
Feature enrich-dashboard-seed-fixtures-with-board received ERROR during overnight review. Issues need human triage.

## Options Considered
- Address review feedback and re-submit
- Override review verdict and mark complete
- Revise specification and re-implement

## What the Pipeline Tried
Overnight review agent returned ERROR at cycle 0.

Issues:
- (no issues listed)

## User Answer (2026-07-28)

The ERROR verdict is void — it is not review feedback. The review agent ran out of
turns (num_turns 31 against max_turns 30, stop_reason `tool_use`), which makes the
`claude` CLI exit 1; the SDK surfaced only "Command failed with exit code 1" with
empty child stderr, and the harness classified it `unknown`, which the review gate
treats as could-not-run. That is why this file lists no issues: no review was ever
produced. The same session's implement dispatch hit the same limit at 21 of 20 turns.

The implementation itself was never judged. Its work is intact on
`pipeline/enrich-dashboard-seed-fixtures-with-board` (ADR-0033, `seed.py` containment,
allocator changes, a new test module) — it was merged into the integration branch and
then reverted solely because of this false ERROR.

Disposition: re-review the existing branch. Do not re-implement, and do not merge
unreviewed — Phase 2 touches `create_item.py`'s ID allocator, which the spec's own
recorded dissent says to review hardest.

Harness fix landed in commit `8b48da5b`: this failure mode is now classified
`turn_limit_exhausted` with retry recovery instead of `unknown`, and `dispatch_error`
events carry `num_turns`/`max_turns`/`stop_reason`.
