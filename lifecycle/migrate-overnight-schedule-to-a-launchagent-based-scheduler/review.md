# Review: migrate-overnight-schedule-to-a-launchagent-based-scheduler

Cycle: 2
Date: 2026-05-04

## Stage 1: Spec Compliance

This is a narrow re-verification of the single PARTIAL finding from cycle 1 (R17). All other Stage 1 verdicts from cycle 1 are unchanged and not re-evaluated here; see `review.md` git history (or the cycle 1 entry below in this file's history) for the full R1–R19 evidence table.

| Req | Title (paraphrased) | Cycle 1 Verdict | Cycle 2 Verdict | Evidence |
| --- | --- | --- | --- | --- |
| R17 | `docs/overnight-operations.md` scheduling section rewritten covering usage, mechanism, caveats, cancel/list, TCC | PARTIAL | PASS | Commit `c04270f` rewrites the four cancel/list lines (242, 245, 260, 261) of `docs/overnight-operations.md` to reference `cortex overnight cancel --list` and `cortex overnight cancel <session_id>` — the actual subparser shape. Verified the cancel subparser at `cortex_command/cli.py:409-454` declares `--list` (`dest=list_only`, `:425-434`) and a positional `session_id` (`nargs='?'`, `:435-440`), so both documented commands resolve. R17 acceptance grep counts re-verified: `grep -c 'launchd\|LaunchAgent' docs/overnight-operations.md` returns 7 (≥3); `grep -c 'Full Disk Access' docs/overnight-operations.md` returns 1 (≥1). |

Regression check: `git show c04270f` confirms the commit modifies only `docs/overnight-operations.md` (1 file changed, 5 insertions, 5 deletions). The diff matches exactly the four lines flagged in cycle 1 (lines 242, 245, 260, 261) — no collateral edits to other files or other parts of the doc. Lines 242 and 245 in the **Usage** code-fence and lines 260 and 261 in the **Cancel and list** code-fence are the only changes.

## Requirements Drift

State: detected

The three drift items identified in cycle 1 are unchanged in cycle 2 (cycle 2 was doc-only and did not touch `requirements/pipeline.md`):

1. **New `cortex overnight schedule` verb.** `requirements/pipeline.md:28` enumerates the overnight CLI shape as `cortex overnight {start|status|cancel|logs}`. The implementation adds `schedule` as a fifth user-facing verb (and `list-sessions` as an MCP-support verb, also undocumented but pre-existing). The `schedule` verb is in-scope for this lifecycle and properly specified at the lifecycle level, but the project-area requirements doc still enumerates the four-verb shape.

2. **New `phase: starting` value.** `requirements/pipeline.md:152` documents the active-session pointer's `phase` enum as `"planning|executing|paused|complete"`. Spec R18 introduces `phase: starting` as the value reported by `cortex overnight status` during the spawn-handshake window. The implementation is careful: `state.py:34-41` documents that `starting` is never persisted to `overnight-state.json` and `runner.py` writes the active-session pointer with `phase="executing"` at `:836`. So the new value is observable only via `cortex overnight status` output, not via either persisted state file. Still, the four-value enum in pipeline.md is now incomplete relative to the observable output contract.

3. **New sidecar dependency `~/.cache/cortex-command/scheduled-launches.json` and lockfile.** `requirements/pipeline.md:139-156` enumerates pipeline dependencies (state file, master plan, events log, deferral dir, allowlist, etc.). The new sidecar index + companion `scheduled-launches.lock` are not listed. They are atomic-written per the existing convention (R8 acceptance + `pipeline.md:21` non-functional requirement on atomicity), but the dependency itself is undeclared.

## Suggested Requirements Update

Update `requirements/pipeline.md`:

- **Session Orchestration → Acceptance criteria**: amend the line listing the CLI shape to read `cortex overnight {start|status|cancel|logs|schedule|list-sessions}`. Note that `schedule` is macOS-only (per spec R5).
- **Active-session pointer schema (around line 152)**: amend the `phase` enum to `"planning|executing|paused|complete|starting"`, with a parenthetical that `starting` is observable only via `cortex overnight status` output and is never persisted to either the state file or the active-session pointer.
- **Dependencies (around lines 141-156)**: add `~/.cache/cortex-command/scheduled-launches.json` (sidecar index of pending LaunchAgent schedules; atomic writes per `os.replace`) and `~/.cache/cortex-command/scheduled-launches.lock` (cross-process schedule lock acquired across GC + bootstrap + verify + sidecar-write).

Optionally amend project.md `In Scope` (line 43) to mention "scheduled launch" alongside session management — currently this scope item reads "session management, scheduled launch, and morning reporting", so this is already covered.

## Stage 2: Code Quality

Cycle 2 introduced no code changes — only the four-line doc fix in `docs/overnight-operations.md`. All Stage 2 findings from cycle 1 (naming conventions, error handling, test coverage, pattern consistency, two minor non-blocker pattern issues) remain unchanged and accepted. No regressions detected: the doc fix is a pure text replacement with no structural or behavioral implications for the implementation.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 2,
  "issues": [],
  "requirements_drift": "detected"
}
```
