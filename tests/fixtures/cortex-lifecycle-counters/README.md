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
                   (no longer read for rework_cycles; kept to prove review.md
                   is not the source)
<case>.events_log  (optional) content to place in events.log for the case
                   (the rework_cycles source: count of review_verdict events
                   with verdict == "CHANGES_REQUESTED")
```

## Cases captured

| Case | Scenario | plan.md | review.md | events.log | stdout | exit |
|------|----------|---------|-----------|------------|--------|------|
| `zero-lifecycle` | No plan.md or events.log exist | absent | absent | absent | `{"tasks_total": 0, "tasks_checked": 0, "rework_cycles": 0}` | 0 |
| `multiple-phases` | plan.md with 5 tasks (3 checked, 2 pending); events.log with 1 CHANGES_REQUESTED + 1 APPROVED review_verdict (= 1 rework); review.md present but not read | 5 tasks | 2 verdicts (not read) | 1 CHANGES_REQUESTED + 1 APPROVED | `{"tasks_total": 5, "tasks_checked": 3, "rework_cycles": 1}` | 0 |
| `malformed-events-log` | plan.md with 2 tasks (1 checked), no review.md, events.log with a torn line and zero review_verdict events (per-line tolerance) | 2 tasks | absent | torn line 2, 0 verdicts | `{"tasks_total": 2, "tasks_checked": 1, "rework_cycles": 0}` | 0 |

## Fixture semantics

### `zero-lifecycle`

No `plan.md` or `events.log` exist in the feature directory. Both files are absent
(the feature directory itself may not exist). The counters script defaults all
three fields to 0.

### `multiple-phases`

`plan.md` contains 5 tasks at different phases: 3 with `**Status**: [x]` (complete)
and 2 with `**Status**: [ ]` (pending). `events.log` contains 2 `review_verdict`
events — one `CHANGES_REQUESTED` and one `APPROVED` — so `rework_cycles` is 1
(only the `CHANGES_REQUESTED` verdict counts). `review.md` is also present and
contains 2 verdict entries, but it is **no longer read** for `rework_cycles`;
keeping it here positively proves the counter is sourced from `events.log` (which
yields 1) and not from `review.md` (which would yield 2). Exercises the full
counter path for all three fields.

### `malformed-events-log`

`plan.md` contains 2 tasks (1 checked). No `review.md`. `events.log` contains a
malformed (non-JSON) line in the middle and zero `review_verdict` events. Because
`count_rework_cycles` now reads `events.log` line-by-line and parses each line
defensively, the malformed line is skipped (not raised on) and `rework_cycles` is
0. This fixture asserts the per-line tolerance of the events.log reader.

## Counter contract

The `plan.md` task counters are regex-based; `rework_cycles` is sourced from
`events.log` (no regex):

| Counter | Source | Rule |
|---------|--------|------|
| `tasks_total` | `plan.md` | regex `\*\*Status\*\*:.*\[[ x]\]` |
| `tasks_checked` | `plan.md` | regex `\*\*Status\*\*:.*\[x\]` |
| `rework_cycles` | `events.log` | count of `review_verdict` events with `verdict == "CHANGES_REQUESTED"` (lines parsed defensively; malformed lines skipped) |

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
| `malformed-events-log` | `key-reorder` | Same; events.log read with per-line tolerance (torn line skipped) |

## Determinism harness

Fixtures were synthesized against the Python port directly (the bash+jq script
has been replaced by the dual-channel wrapper). The Python port runs under:

- `LC_ALL=C` — byte-deterministic collation
- `TZ=UTC` — consistent timezone (script does not emit timestamps)
- `LIFECYCLE_SESSION_ID` unset — telemetry shim is a no-op

The feature slugs (`feat-zero-lifecycle`, `feat-multiple-phases`,
`feat-malformed-events`) are synthetic and do not exist in the real
`cortex/lifecycle/` tree.
