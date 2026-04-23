---
schema_version: "1"
uuid: f5a6b7c8-d9e0-1234-fab0-345678901234
id: "022"
title: "Fix non-atomic state writes in overnight runner"
type: chore
status: complete
priority: high
parent: "018"
blocked-by: []
tags: [overnight, reliability, state, bugs]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/harness-design-long-running-apps/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: fix-non-atomic-state-writes-in-overnight-runner
complexity: complex
criticality: high
spec: lifecycle/fix-non-atomic-state-writes-in-overnight-runner/spec.md
areas: [overnight-runner]
---

# Fix non-atomic state writes in overnight runner

## Context from discovery

Deep research identified two non-atomic write patterns that can corrupt session state on crash. Both affect the overnight runner which runs unattended — there is no human present to notice or recover.

**Bug 1 — orchestrator prompt instructs raw `write_text` for `overnight-state.json`**

`cortex_command/overnight/prompts/orchestrator-round.md` Steps 0d, 3c, and 4a all contain Python pseudocode that writes `overnight-state.json` via `Path(...).write_text(json.dumps(state, indent=2))`. The rest of the system uses `save_state()`, which does an atomic tempfile + `os.replace` swap with a `BaseException` cleanup block. A crash mid-write via `write_text` leaves a truncated or zero-byte JSON file. Every subsequent Python component that reads it raises `json.JSONDecodeError` and the session dies with no recovery path.

**Bug 2 — `batch-{N}-results.json` written non-atomically**

`cortex_command/overnight/batch_runner.py` lines ~1956–1963 write the batch results file via `result_path.write_text(...)`. If `batch_runner.py` is killed during this write, `map_results.py` receives a truncated JSON file, raises `json.JSONDecodeError`, and falls through to `_handle_missing_results()` which marks every feature in the batch as failed — including ones that successfully merged.

**Secondary issues also found**:
- `escalations.jsonl` appends have no fsync; a crash between write and read causes a partial JSON line that is silently skipped — the escalation is permanently lost, never surfaced for human review
- `recovery_attempts` increments are saved at the end of `run_batch()`, not per-feature; a mid-batch kill loses the increment, causing the repair agent to be re-dispatched for a feature that already used its budget

## What to fix

Fix each write site to use the same atomic tempfile + `os.replace` pattern already implemented in `save_state()`. The orchestrator prompt should instruct the agent to call `save_state()` and `update_feature_status()` rather than constructing raw JSON writes.
