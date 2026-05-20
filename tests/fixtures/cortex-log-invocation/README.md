# cortex-log-invocation golden-replay fixtures

This directory holds the pre-deletion capture of `bin/cortex-log-invocation`
(bash) for the parity test that guards its Python port
(`cortex_command.log_invocation`).

Each test case is stored as five flat sibling files:

```
<case>.argv      one argv element per line (line 1 is sys.argv[1] of the script)
<case>.stdin     literal bytes piped to stdin (empty for current cases)
<case>.stdout    literal bytes captured from stdout
<case>.stderr    literal bytes captured from stderr
<case>.exitcode  the exit status as a single decimal integer + trailing newline
```

The bash script is fail-open by contract: every invocation exits 0 with empty
stdout and stderr, regardless of inputs. The observable behavioral difference
between cases lives in a side-effect JSONL log written under
`<repo>/cortex/lifecycle/sessions/<session-id>/bin-invocations.jsonl`. The
quintuples above capture the stdout/stderr/exit-code surface; the side-effect
contract is tested separately by `tests/test_cortex_log_invocation_parity.py`
(Task 6) by running the Python port against the same argv/stdin/env and
reading the JSONL it appends to a scratch session dir.

## Cases captured

| Case            | Scenario                                                  | LIFECYCLE_SESSION_ID | CORTEX_REPO_ROOT      | cwd            | JSONL appended? |
|-----------------|-----------------------------------------------------------|----------------------|-----------------------|----------------|-----------------|
| `happy_path`    | one positional argv, valid repo + session dir             | set                  | set, valid            | scratch repo   | yes             |
| `no_session_id` | env var unset; fail-open early return                     | unset                | set, valid            | scratch repo   | no              |
| `multi_argv`    | four positional args (argv_count = 4) into valid session  | set                  | set, valid            | scratch repo   | yes             |
| `no_repo_root`  | env unset and cwd has no `.git`; fail-open                | set                  | unset                 | non-git dir    | no              |

Cases were chosen to cross-cut the bash script's four early-exit branches
(`no_session_id`, `no_repo_root`, success, success with multi-arg) so the
Python port is exercised on every fail-open path plus the happy path.

## Determinism harness

The fixtures were captured under a controlled environment so the parity test
can replay them deterministically. The Python port must run under the same
environment when compared.

- **jq version**: `jq --version` reported `jq-1.8.1` at capture time. The
  bash script does not invoke `jq` (it emits JSONL via `printf`), but jq is
  pinned because downstream parity tests for jq-based scripts (Tasks 8, 11–21)
  reuse this README's contract. Pinning the version up front prevents
  cross-test drift.
- **`LC_ALL=C`**: forces byte-deterministic collation and number formatting in
  any subprocesses the script may shell out to.
- **`TZ=UTC`**: pins the timestamp emitted by `date -u +%Y-%m-%dT%H:%M:%SZ`
  so the captured JSONL side-effect uses UTC clock format.
- **Timestamp handling**: the bash script's `ts` field is a wall-clock UTC
  timestamp. Fixture capture does NOT freeze the clock; instead the parity
  test normalizes the `ts` field of both bash-side and Python-side JSONL via
  a `sed` filter (`s/"ts":"[^"]*"/"ts":"<FROZEN>"/`) before structural
  comparison. The fixtures themselves contain no timestamp bytes because
  stdout/stderr are empty by contract.
- **`HOME` redirected to scratch**: the bash script writes a breadcrumb to
  `${HOME}/.cache/cortex/log-invocation-errors.log` on the fail-open paths.
  Captures use a scratch `HOME` so the parity test does not pollute real
  user state, and the parity test does the same.
- **Repo root substitution**: `CORTEX_REPO_ROOT` and the session-dir path
  vary between capture and replay. The parity test compares the JSONL
  schema (keys + structurally-equivalent values per the tolerance rubric
  below) rather than the literal file path.

## Named-tolerance categories the parity test consumes

The parity test (Task 6) imports the `@pytest.mark.structural_equivalence`
decorator from `tests/test_parity_contract.py` (Task 5) and declares an
explicit, opt-in tolerance set per stream. For this fixture set the relevant
named categories are:

- **`unicode-escape`** — ASCII-escape form (`\uXXXX`) vs raw UTF-8 byte form
  (`"é"` vs `"é"`). The bash script uses `printf` with no escape;
  Python's `json.dumps` defaults to `ensure_ascii=True`. Either rendering is
  accepted on JSONL stdout / side-effect.
- **`number-format`** — integer-valued floats (`1` vs `1.0`). The bash
  script writes `argv_count` with `%d`; Python's `json.dumps` of an `int`
  produces `1`, but if the port stores the count as `float` for any reason
  the value `1.0` would also be accepted. Leading-zero forms remain
  forbidden.
- **`trailing-newline`** — presence or absence of a single trailing `\n` on
  stdout/stderr. Captures end without trailing bytes; some Python `print`
  paths add one. Either is accepted.
- **`key-reorder`** — intra-object JSON key reordering, e.g.,
  `{"ts":"...","script":"...","argv_count":0,"session_id":"..."}` vs any
  permutation. The bash `printf` fixes key order; Python `dict` insertion
  order may differ. Either is accepted on the JSONL side-effect comparison.

For this fixture set, the captured stdout/stderr are empty and exit is
always 0, so the byte-level comparison is trivially exact. The named
tolerances apply when the parity test inspects the JSONL side-effect (read
back from the scratch session dir), where the Python port's `json.dumps`
output can legitimately differ from the bash `printf`-built line on the
categories above without violating the contract.

`error-formatter-shape` is NOT opted into for this fixture set: the bash
script never emits diagnostic stderr on its happy or fail-open paths.

## How to recapture

If the bash script is restored from history and re-captured, run from a clean
worktree with:

```bash
LC_ALL=C TZ=UTC HOME=/tmp/scratch-home bash -c '
    # for each case, set LIFECYCLE_SESSION_ID / CORTEX_REPO_ROOT / cwd
    # then: bin/cortex-log-invocation <argv...> > <case>.stdout 2> <case>.stderr
    # then: echo $? > <case>.exitcode
'
```

The scratch `HOME` keeps the breadcrumb log out of the developer's real
`~/.cache/cortex/`.
