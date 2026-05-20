# cortex-check-parity golden-replay fixtures

This directory holds pre-deletion captures of `bin/cortex-check-parity`
(originally `#!/usr/bin/env python3`) for the parity test that guards its
Python port (`cortex_command.parity_check`).

Each test case is stored as five flat sibling files:

```
<case>.argv      one argv element per line (line 1 is sys.argv[1] of the script)
<case>.stdin     literal bytes piped to stdin (empty for current cases)
<case>.stdout    literal bytes captured from stdout
<case>.stderr    literal bytes captured from stderr
<case>.exitcode  the exit status as a single decimal integer + trailing newline
```

## Cases captured

| Case                | Scenario                                                      | cwd              | exit |
|---------------------|---------------------------------------------------------------|------------------|------|
| `self_test`         | `--self-test` — all inline cases pass                         | repo root        | 0    |
| `all_green`         | `--json` against mini-repo with wired bin script              | mini-repo (tmp)  | 0    |
| `orphan_bin`        | `--json` against mini-repo with un-wired bin script (W003)    | mini-repo (tmp)  | 1    |
| `wired_allowlisted` | `--json` against mini-repo: script wired AND allowlisted (W005) | mini-repo (tmp) | 1   |

Cases were chosen to exercise:
- `self_test`: all R5/R6/R7/R8 inline self-test cases, all-pass path
- `all_green`: linter running against a clean mini-repo (no violations)
- `orphan_bin`: W003 detection (deployed script without wiring signal)
- `wired_allowlisted`: W005 detection (allowlist-superfluous: script is wired AND allowlisted)

## Determinism harness

The fixtures were captured under a controlled environment so the parity test
can replay them deterministically. The Python port must run under the same
environment when compared.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time. The
  module does not invoke `jq`, but pinning the version here matches the
  convention from the cortex-log-invocation README for cross-test consistency.
- **`LC_ALL=C`**: forces byte-deterministic collation and number formatting in
  any subprocesses the module may shell out to.
- **`TZ=UTC`**: set during capture; the module itself does not emit wall-clock
  timestamps in the three captured cases.
- **Timestamp handling**: none of the three captured cases emit timestamps on
  stdout or stderr; the byte-identical comparison is exact.

## Named-tolerance categories the parity test consumes

- **`trailing-newline`**: the module terminates lines with `\n`; `--json`
  output from `json.dumps` also ends with a trailing newline from `print()`.
  Either rendering is accepted.
- **`unicode-escape`**: JSON output from `json.dumps(ensure_ascii=True)` may
  escape non-ASCII characters; the bash-era output used the same Python path
  so both sides agree, but the tolerance is declared as a safety net.

`key-reorder` and `error-formatter-shape` are NOT opted into for this
fixture set: the JSON violations are produced by a Python list + `json.dumps`,
and the `self_test` case emits a plain string with no JSON.

## How to recapture

If the module is updated and fixtures need refreshing:

```bash
LC_ALL=C TZ=UTC python3 -m cortex_command.parity_check --self-test \
    > tests/fixtures/cortex-check-parity/self_test.stdout \
    2> tests/fixtures/cortex-check-parity/self_test.stderr
echo $? > tests/fixtures/cortex-check-parity/self_test.exitcode
```

For the `all_green` and `orphan_bin` cases, set up the appropriate mini-repo
as cwd (see `tests/test_cortex_check_parity_parity.py` for the exact structure)
and capture with `--json`.
