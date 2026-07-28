# Review: add-the-dashboard-ticket-feed-with

## Status of this review

**No reviewer was dispatched. The Review phase was skipped by operator decision on 2026-07-27.**

The state machine forces review at this feature's `high` criticality regardless of tier, and the
operator elected to skip it after being told that is what the choice meant. This file exists so the
skip is a matter of record rather than an inference from a missing artifact.

Neither stage of the normal review ran:

- **Stage 1 — spec compliance**: not performed. No independent party checked the 17 requirements in
  `spec.md` against the implementation.
- **Stage 2 — code quality**: not performed. Naming, error handling, and pattern consistency were
  not independently assessed.
- **Requirements drift**: **not assessed.** The `--drift none` value carried into the advance verb
  is the no-action value, not a finding. One candidate was noticed during implementation and is
  recorded below rather than adjudicated.

The `APPROVED` verdict in the JSON block below is a **routing token**, not a reviewer's judgment.
`cortex-lifecycle-advance review-verdict` accepts only `APPROVED`, `CHANGES_REQUESTED`, or
`REJECTED`; there is no value meaning "skipped", and the `skip-review` config key is read at the
implement→review routing point, which this feature had already passed. `APPROVED` is the only value
that advances a skipped review to Complete. Read it as "the operator released this to Complete
without review", and do not read it as evidence that anything was verified by a second party.

## Evidence that does exist

All of this was produced by the implementer, so it is self-reported. It is included because it is
mechanically checkable by anyone re-running the commands, not because it substitutes for review.

**Test baseline** — `just test`, run once at review entry against HEAD `7da75de9`:
**8/8 suites passed** (test-pipeline, test-overnight, test-init, test-install, tests,
tests-lifecycle-backlog-cortex, tests-dashboard, tests-takeover-stress). Log:
session scratchpad `test-baseline.log`. 194 dashboard tests and the phase-label suite are inside
that total.

**Per-task verification** — every task's Verification field in `plan.md` was executed and passed;
each task's Status line carries its verifying commit sha and timestamp.

**Grep contracts from `spec.md`'s acceptance criteria**, re-run at review entry:

| Contract | Required | Actual |
|---|---|---|
| `state\.backlog_snapshot` in `poller.py` (R5a) | 3 | 3 |
| `backlog_snapshot: dict \| None = None` in `poller.py` (R2) | 1 | 1 |
| `create_task` in `poller.py` (R15) | 4 | 4 |
| `glob("[0-9]*-*.md")` in `data.py` (R13) | 2 | 2 |
| status literals in `poller.py` (R11) | 0 | 0 |
| status literals in `ticket_feed.py` (R11, extended) | 0 | 0 |
| `^blocked_by:` in `230-*.md` (R16) | 0 | 0 |
| `^blocked-by:` in `230-*.md` (R16) | 1 | 1 |
| `upstream blocker-key hygiene` in `411-*.md` (R17) | 0 | 0 |

The three `state.backlog_snapshot` occurrences were inspected individually and are the commit
(`poller.py:415`), the non-local clear (`:421`), and the stale-marking read (`:404`) — none in the
in-place forms R5(a) excludes.

**Live-corpus check** — `build_backlog_snapshot` over this repo's real corpus returns the exact R3
key set, 10 items, 6 ready, and resolves blockers to real titles and statuses. This is the only
verification here run against something other than a fixture.

## Unadjudicated observations

Recorded, not ruled on. A real review would have taken a position on each.

- **Scope addition beyond the spec.** `test_ticket_feed.py::TestImportSurface` asserts the module
  imports with `claude_agent_sdk` blocked. It traces to no requirement. It was added because R11's
  `ELIGIBLE_STATUSES` import is the first dashboard→overnight coupling in the tree and drags that
  package's eager orchestrator fan-out; measured at plan time as ~60–200 ms once per process, and
  it does import cleanly under a `[dashboard]`-only install today. Flagged in `plan.md`'s Risks as
  strikeable. Nobody has struck or endorsed it.
- **Possible requirements drift, unassessed.** `cortex/requirements/observability.md:30` lists the
  dashboard's inputs and does not include the backlog corpus — a gap `spec.md`'s Technical
  Constraints recorded explicitly rather than papered over. This feature adds a third read of that
  corpus per cycle. Whether that warrants an `observability.md` update is exactly the judgment a
  review would have made.
- **`parse_backlog_titles` signature change.** Its return type went from `dict` to a `BacklogTitles`
  NamedTuple. The spec never asked for it; it is how R13's "no fourth corpus scan" was satisfied.
  Callers were enumerated by grep and all updated.
- **Plan/actual mismatch in Task 6's verification.** The plan predicted one removed line; two were
  removed. The second is the `updated:` frontmatter bump that `cortex-lifecycle-enter` made earlier
  in the same session, before the task ran. R17's substantive requirement was checked separately:
  Why, Role, Integration, and Edges are byte-unchanged.

## Requirements Drift

**State**: none

**Findings**: None — drift was not assessed. See "Status of this review" above; `none` here is the
no-action routing value and carries no finding either way. The one candidate is recorded under
Unadjudicated observations.

**Update needed**: None

## Verdict

```
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
