# cortex-lifecycle-counters golden-replay fixtures

This directory holds synthetic fixture captures for `bin/cortex-lifecycle-counters`
(now a dual-channel wrapper over `cortex_command.lifecycle.counters`) for the parity
test that guards its Python port.

Each test case is stored as five flat sibling files plus optional sidecar input files:

```
<case>.argv        one argv element per line (line 1 is argv[1] of the script)
<case>.stdin       literal bytes piped to stdin (empty for all cases)
<case>.stdout      literal bytes captured from stdout
<case>.stderr      literal bytes captured from stderr
<case>.exitcode    the exit status as a single decimal integer + trailing newline
<case>.plan_md     (optional) content to place in plan.md for the case
<case>.review_md   (optional) content to place in review.md for the case
<case>.events_log  (optional) content to place in events.log for the case
                   (ignored by counters; present to verify counters do not read it)
```

## Cases captured

| Case | Scenario | plan.md | review.md | events.log | stdout | exit |
|------|----------|---------|-----------|------------|--------|------|
| `zero-lifecycle` | No plan.md or review.md exist | absent | absent | absent | `{"tasks_total": 0, "tasks_checked": 0, "rework_cycles": 0}` | 0 |
| `multiple-phases` | plan.md with 5 tasks (3 checked, 2 pending), review.md with 2 verdicts | 5 tasks | 2 verdicts | absent | `{"tasks_total": 5, "tasks_checked": 3, "rework_cycles": 2}` | 0 |
| `malformed-events-log` | plan.md with 2 tasks (1 checked), no review.md, malformed events.log (ignored) | 2 tasks | absent | torn line 2 | `{"tasks_total": 2, "tasks_checked": 1, "rework_cycles": 0}` | 0 |

## Fixture semantics

### `zero-lifecycle`

No `plan.md` or `review.md` exist in the feature directory. Both files are absent
(the feature directory itself may not exist). The counters script defaults all
three fields to 0.

### `multiple-phases`

`plan.md` contains 5 tasks at different phases: 3 with `**Status**: [x]` (complete)
and 2 with `**Status**: [ ]` (pending). `review.md` contains 2 verdict entries
(`REWORK` and `APPROVED`). Exercises the full counter path for all three fields.

### `malformed-events-log`

`plan.md` contains 2 tasks (1 checked). No `review.md`. `events.log` contains a
malformed (non-JSON) line in the middle. Since `cortex-lifecycle-counters` reads
only `plan.md` and `review.md` (never `events.log`), the malformed line has no
effect on output. This fixture verifies that the Python port does not accidentally
read `events.log` and that the malformed content does not cause any error.

## Counter regex contract

Regexes are pinned to match `cortex_command/common.py:182-183` exactly:

| Counter | Regex |
|---------|-------|
| `tasks_total` | `\*\*Status\*\*:.*\[[ x]\]` |
| `tasks_checked` | `\*\*Status\*\*:.*\[x\]` |
| `rework_cycles` | `"verdict"\s*:\s*"[A-Z_]+"` |

## Applicable parity tolerances per fixture

The parity test (`tests/test_cortex_lifecycle_counters_parity.py`) uses
`assert_structurally_equivalent` with `key-reorder` tolerance for stdout,
since jq emits keys in insertion order and Python's `json.dumps` also uses
insertion order (both produce `tasks_total, tasks_checked, rework_cycles`)
but the tolerance is declared defensively.

| Fixture | Tolerance categories | Notes |
|---------|---------------------|-------|
| `zero-lifecycle` | `key-reorder` | All values are 0; key order is the only diff class |
| `multiple-phases` | `key-reorder` | Integer values; key order is the only diff class |
| `malformed-events-log` | `key-reorder` | Same; events.log is ignored entirely |

## Determinism harness

Fixtures were synthesized against the Python port directly (the bash+jq script
has been replaced by the dual-channel wrapper). The Python port runs under:

- `LC_ALL=C` — byte-deterministic collation
- `TZ=UTC` — consistent timezone (script does not emit timestamps)
- `LIFECYCLE_SESSION_ID` unset — telemetry shim is a no-op

The feature slugs (`feat-zero-lifecycle`, `feat-multiple-phases`,
`feat-malformed-events`) are synthetic and do not exist in the real
`cortex/lifecycle/` tree.
