# cortex-backlog-ready parity fixtures

Golden-replay fixtures for `tests/test_cortex_backlog_ready_parity.py`.

## Fixture cases

| Case | argv | Description |
|------|------|-------------|
| `ready_only` | (none) | Basic call with no args against a synthetic backlog; verifies ready-set JSON output |
| `include_blocked` | `--include-blocked` | Includes ineligible items with reason/rejection; exercises external-blocker path |
| `missing_backlog_dir` | (none) | No `cortex/backlog/` dir present; verifies JSON error contract (exit 1) |

## Synthetic backlog snapshot

Each active-path case (`ready_only`, `include_blocked`) is run against a
synthetic backlog constructed in a `tmp_path` directory by the test harness.
The synthetic records are defined in `test_cortex_backlog_ready_parity.py`
under `_FIXTURE_RECORDS` and `_ACTIVE_RECORDS`. No live backlog state is
read; fixtures are stable across repo changes.

The `missing_backlog_dir` case is run in an empty `tmp_path` with no
`cortex/backlog/` directory present.

## Determinism harness

- `LC_ALL=C` set during capture
- `TZ=UTC` set during capture
- jq version: N/A (this script is Python-only; no jq dependency)
- Timestamps: no timestamps in stdout or stderr for any fixture case
- Non-deterministic content: none; the module emits only deterministic
  JSON derived from the synthetic backlog snapshot

## Named tolerance categories

stdout: `["key-reorder", "unicode-escape", "number-format"]` (JSON output)
stderr: `["error-formatter-shape"]` (error paths only; normal paths have empty stderr)

The `missing_backlog_dir` case uses `error-formatter-shape` tolerance for
stderr (empty in both bash and Python for the error-contract path) and
`key-reorder` for stdout (JSON error envelope).
