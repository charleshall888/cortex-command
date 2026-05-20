# cortex-lifecycle-state golden-replay fixtures

This directory holds the pre-deletion capture of `bin/cortex-lifecycle-state`
(bash+jq) for the parity test that guards its Python port
(`cortex_command.lifecycle_state`).

Each test case is stored as five flat sibling files plus an optional input file:

```
<case>.argv        one argv element per line (line 1 is argv[1] of the script)
<case>.stdin       literal bytes piped to stdin (empty for all cases — input comes from file)
<case>.stdout      literal bytes captured from stdout
<case>.stderr      literal bytes captured from stderr
<case>.exitcode    the exit status as a single decimal integer + trailing newline
<case>.events.log  the events.log content staged in cortex/lifecycle/<feature>/ for replay
                   (absent for missing-events-log, which tests the no-file path)
```

## Accepted `--field` set

The bash script's `case "$field" in` block accepts exactly two non-empty values:

| `--field` value | Effect |
|-----------------|--------|
| `criticality`   | Output `{"criticality": "<value>"}` or `{}` if no criticality event was found |
| `tier`          | Output `{"tier": "<value>"}` or `{}` if no tier event was found |

Any other value exits 2 with `cortex-lifecycle-state: --field must be 'criticality' or 'tier' (got: <value>)`.
Omitting `--field` outputs the full `{"criticality":..., "tier":...}` object.

Source: `bin/cortex-lifecycle-state` lines 61–67 (canonical bash, captured 2026-05-20).

## Cases captured

| Case | Scenario | events.log shape | --field | stdout | exit |
|------|----------|-----------------|---------|--------|------|
| `basic-ok` | lifecycle_start only (tier=simple, criticality=medium) | valid JSONL, 4 lines | none | `{"criticality":"medium","tier":"simple"}` | 0 |
| `complexity-override` | lifecycle_start + complexity_override (tier promoted simple→complex) | valid JSONL, 3 lines | none | `{"criticality":"medium","tier":"complex"}` | 0 |
| `criticality-override` | lifecycle_start + complexity_override + criticality_override | valid JSONL, 4 lines | none | `{"criticality":"high","tier":"complex"}` | 0 |
| `field-criticality` | same events as criticality-override, filtered to criticality field | valid JSONL, 4 lines | `criticality` | `{"criticality":"high"}` | 0 |
| `field-tier` | same events as criticality-override, filtered to tier field | valid JSONL, 4 lines | `tier` | `{"tier":"complex"}` | 0 |
| `missing-events-log` | no events.log file exists for the feature | absent | none | `{}` | 0 |
| `no-start-event` | events.log present but no lifecycle_start or override events | valid JSONL, 2 lines | none | `{}` | 0 |
| `torn-line` | events.log has a truncated/malformed JSON line in the middle | torn line 2 of 3 | none | `null` | 0 |

Cases cross-cut: missing file, empty-accumulator, valid-field-filter, override
precedence (complexity_override supersedes lifecycle_start.tier; criticality_override
supersedes lifecycle_start.criticality), and malformed-input.

## Torn-line behavior — actual bash+jq output

The bash script's comment says it "silently skips torn or malformed lines", but
**the actual jq behavior is different**. When `fromjson?` produces no output for a
line, the `as $r` binding produces `null` instead of skipping the iteration, and
jq's `reduce` body becomes empty for that iteration. With jq-1.8.1, a `reduce`
whose body produces empty for any iteration outputs `null` for the entire reduce.

Concrete result: if ANY line in events.log fails `fromjson?`, the reduce exits with
accumulator `null` rather than the partially-accumulated object. Then:
- Without `--field`: `null | .` = `null`, printed as `null\n`.
- With `--field criticality` or `--field tier`: `null | has("criticality")` = `false`,
  so the output is `{}`.

The `torn-line` fixture captures this jq-1.8.1 behavior. The Python port (Task 21)
must replicate this behavior OR apply the `error-formatter-shape` tolerance carve-out
(see below).

## Applicable parity tolerances per fixture

The parity test (`tests/test_cortex_lifecycle_state_parity.py`, Task 21) imports
the `@pytest.mark.structural_equivalence` decorator from `tests/test_parity_contract.py`
and declares an explicit, opt-in tolerance set per fixture.

| Fixture | Tolerance categories | Notes |
|---------|---------------------|-------|
| `basic-ok` | `key-reorder` | jq emits keys in insertion order; Python dict may differ |
| `complexity-override` | `key-reorder` | same |
| `criticality-override` | `key-reorder` | same |
| `field-criticality` | none | single-key object; key-reorder is vacuous |
| `field-tier` | none | single-key object; key-reorder is vacuous |
| `missing-events-log` | none | output is `{}` — trivially byte-identical |
| `no-start-event` | none | output is `{}` — trivially byte-identical |
| `torn-line` | `error-formatter-shape`, `key-reorder` | see below |

### Named-tolerance categories

- **`key-reorder`** — intra-object JSON key reordering. jq emits keys in the order
  they were assigned in the reduce; Python `dict` insertion order may differ. Any key
  permutation with identical values is accepted.

- **`unicode-escape`** — ASCII-escape form (`\uXXXX`) vs raw UTF-8 byte form. Not
  applicable to these fixtures (all values are ASCII).

- **`number-format`** — integer-valued floats (`1` vs `1.0`). Not applicable — all
  values are strings.

- **`error-formatter-shape`** — Carve-out for jq's diagnostic messages on malformed
  input. The Python port (`json.JSONDecodeError`) cannot byte-replicate jq's
  diagnostic stderr text. The parity test accepts equivalent behavior: the Python port
  must produce the same stdout AND same exit code as the bash fixture, but stderr
  content may differ when `error-formatter-shape` is opted in. For `torn-line`, bash
  produces empty stderr and exit 0 with `null` on stdout; the Python port must also
  produce `null` on stdout and exit 0 (reproducing the reduce-to-null behavior), but
  may emit a different (or empty) stderr message. If the Python port instead silently
  skips malformed lines (producing `{"criticality":"high","tier":"complex"}` instead
  of `null`), that is a parity failure — the Python must match the bash reduce-to-null
  behavior, not the script comment's stated intent.

## Determinism harness

Fixtures were captured under a controlled environment so the parity test can replay
them deterministically. The Python port must run under the same environment when
compared.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time (2026-05-20).
  All jq-dependent behaviors (reduce semantics, fromjson? error handling) are pinned
  to this version.
- **`LC_ALL=C`**: set during capture to force byte-deterministic collation and number
  formatting.
- **`TZ=UTC`**: set during capture. This script does not emit timestamps on stdout,
  so this is a belt-and-suspenders measure for consistency with other captured scripts.
- **Timestamp handling**: `cortex-lifecycle-state` reads timestamps from the input
  events.log but does not emit them on stdout or stderr. The captured fixtures contain
  no timestamp bytes in `.stdout` or `.stderr`. No freezing or normalization is
  required for the stdout/stderr comparison.
- **`cortex-log-invocation` side-effect**: the script invokes `cortex-log-invocation`
  as a fail-open telemetry shim. During capture, `LIFECYCLE_SESSION_ID` was unset,
  so `cortex-log-invocation` returned 0 with no side effects. The parity test should
  similarly leave `LIFECYCLE_SESSION_ID` unset (or set `CORTEX_REPO_ROOT` to a scratch
  dir) to keep the telemetry side-effect out of the parity comparison.
- **Feature slug isolation**: each fixture uses a synthetic feature slug
  (`feat-basic-ok`, `feat-torn-line`, etc.) that does not exist in the real
  `cortex/lifecycle/` tree. The parity test stages the fixture's `.events.log` into a
  scratch `cortex/lifecycle/<slug>/` directory before invoking the script.

## How to recapture

If the bash script is restored from history and needs to be recaptured:

```bash
LC_ALL=C TZ=UTC bash -c '
  cd /path/to/scratch/dir
  mkdir -p cortex/lifecycle/feat-basic-ok
  cp tests/fixtures/cortex-lifecycle-state/basic-ok.events.log \
     cortex/lifecycle/feat-basic-ok/events.log
  bin/cortex-lifecycle-state --feature feat-basic-ok \
      > tests/fixtures/cortex-lifecycle-state/basic-ok.stdout \
      2> tests/fixtures/cortex-lifecycle-state/basic-ok.stderr
  echo $? > tests/fixtures/cortex-lifecycle-state/basic-ok.exitcode
  # repeat for each fixture case
'
```

The `.argv` files encode the exact arguments passed; the parity test replays them
as `argv[1:]` to the script/module under test.
