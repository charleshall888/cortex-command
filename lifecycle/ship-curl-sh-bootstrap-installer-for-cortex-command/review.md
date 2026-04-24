# Review: ship-curl-sh-bootstrap-installer-for-cortex-command

## Stage 1: Spec Compliance

### Requirement R1: `install.sh` at repo root, POSIX sh, lint-clean
- **Expected**: `install.sh` exists at repo root with `#!/bin/sh`, `set -eu`, is executable; `shellcheck -s sh install.sh` exits 0.
- **Actual**: `install.sh:1` is `#!/bin/sh`; `install.sh:2` is `set -eu`; file is executable; `shellcheck -s sh install.sh` runs clean in the test harness (first `PASS install/shellcheck-posix-sh`).
- **Verdict**: PASS
- **Notes**: All three spec greps return exit 0 in verification.

### Requirement R2: Auto-install `uv` when absent
- **Expected**: When `command -v uv` fails, script fetches `https://astral.sh/uv/install.sh` and prepends the installed uv's bin dir so `command -v uv` succeeds within the same run.
- **Actual**: `install.sh:15-22` implements `install_uv()` which downloads via `run curl -LsSf https://astral.sh/uv/install.sh -o "$tmp"`, executes via `run sh "$tmp"`, then prepends `$HOME/.local/bin:$HOME/.cargo/bin` to PATH. Tempfile split (rather than pipe-to-sh) is load-bearing under `set -eu` with no `pipefail`. `install.sh:53` invokes it via `command -v uv >/dev/null 2>&1 || install_uv`. Test `install/R2-no-uv-bootstrap` passes.
- **Verdict**: PASS

### Requirement R3: `just` precondition — detect and error loud
- **Expected**: When `command -v just` fails, stderr names `just` + platform remediation and exits 1 BEFORE any clone work.
- **Actual**: `install.sh:42-52` — the `just` check runs at the very top of `main()`, strictly before the `uv` check and clone. Darwin branch emits `brew install just`; other branches emit `apt install just (or: brew install just)`. Test `install/R3-no-just-precondition` passes.
- **Verdict**: PASS

### Requirement R4: Clone destination: `$CORTEX_COMMAND_ROOT` or `$HOME/.cortex`
- **Expected**: `grep -qE 'CORTEX_COMMAND_ROOT:-\$HOME/\.cortex' install.sh` exits 0.
- **Actual**: `install.sh:41` — `target=${CORTEX_COMMAND_ROOT:-$HOME/.cortex}`. Grep exits 0.
- **Verdict**: PASS

### Requirement R5: `CORTEX_REPO_URL` normalization
- **Expected**: Default `charleshall888/cortex-command`; pass `git@*:*/*`, `ssh://*`, `https://*`, `http://*` verbatim; otherwise prepend `https://github.com/` + append `.git`.
- **Actual**: `install.sh:24-37` — `normalize_repo_url()` implements all four pass-through cases via POSIX `case`, shorthand falls through to `printf 'https://github.com/%s.git\n' "$url"`. Matches spec transformation table exactly.
- **Verdict**: PASS
- **Notes**: No pre-clone validation beyond case-normalization, matching the spec's "git clone errors propagate" contract.

### Requirement R6: Clone-or-pull safety on existing `$CORTEX_COMMAND_ROOT`
- **Expected**: Five branches — absent → clone; same-origin git → fetch+pull; different-origin git → abort with both URLs; cross-protocol → abort; not-git → abort "refusing to overwrite". No `rm -rf`.
- **Actual**: `install.sh:56-77` implements all five branches. Byte-identity check is `[ "$existing_origin" = "$resolved_url" ]` (line 61). Abort messages name both URLs with remediation text. `grep -q 'rm -rf' install.sh` returns exit 1 (pattern absent). Tests `install/R6a-target-absent-clones`, `install/R6b-same-origin-pulls`, `install/R6b-dirty-tree-aborts`, `install/R6c-different-origin-aborts`, `install/R6d-cross-protocol-aborts`, `install/R6e-not-git-repo-aborts` all pass.
- **Verdict**: PASS
- **Notes**: Implementation adds a dirty-tree abort (line 62-66) inside branch (b) beyond the spec — spec is silent on dirty trees; plan Task 4 + Veto Surface documents this as an intentional extension that mirrors `cortex upgrade`'s R14 posture.

### Requirement R7: Pre-clone stderr logging
- **Expected**: Two `[cortex-install]` stderr lines (resolved URL, target path) before any clone/pull.
- **Actual**: `install.sh:54-55` — `log "resolved repo URL: $resolved_url"` and `log "target path: $target"` precede the branch block at line 56+. Test `install/R7-pre-clone-stderr-ordering` passes (line-number assertion).
- **Verdict**: PASS

### Requirement R8: Tool install step
- **Expected**: `UV_PYTHON_DOWNLOADS=automatic uv tool install -e "$target" --force`. `--force` is load-bearing for entry-point regeneration.
- **Actual**: `install.sh:78` — `run env UV_PYTHON_DOWNLOADS=automatic uv tool install -e "$target" --force`. Both spec greps (`UV_PYTHON_DOWNLOADS=automatic`, `uv tool install -e "?\$?[a-zA-Z_]+"? --force`) return exit 0.
- **Verdict**: PASS

### Requirement R9: Final-step messaging
- **Expected**: Post-install stderr contains `cortex CLI installed`, `plugin`, `docs/setup.md`; does NOT contain `12[0-9]` (no stale ticket numbers).
- **Actual**: `install.sh:79-81` — three `log` calls:
  1. `"cortex CLI installed."`
  2. `"plugin auto-registration is not yet automated -- see docs/setup.md for manual steps."`
  3. `"if 'cortex' is not on your PATH, run 'uv tool update-shell' and reload your shell."`
  Spec grep `grep -q '12[0-9]' install.sh` returns exit 1 (pattern absent — no ticket numbers). All three required content items are present.
- **Verdict**: PASS
- **Notes**: Re deviation #1 (ASCII `--` vs em-dash) — the spec text does not require an em-dash character; it specifies content ("confirms the cortex CLI is installed", "states plugin auto-registration not automated", "points at docs/setup.md"). ASCII `--` satisfies the content contract and avoids encoding ambiguity. Not a defect.

### Requirement R10: Idempotent re-run
- **Expected**: Two runs both exit 0; `.git/HEAD` unchanged between runs; after adding a synthetic `[project.scripts]` entry, third run picks it up.
- **Actual**: Test `install/R10-idempotent-rerun` exercises all three conditions: exit1=0, exit2=0, exit3=0; head1==head2; uv re-invocation count advances; new `cortex-new-script` entry present in target's pyproject.toml. Test passes.
- **Verdict**: PASS

### Requirement R11: Failure-path exit contract
- **Expected**: Every `exit` is 0 or 1; subprocess failures translated to exit 1 via `run()` wrapper.
- **Actual**: `grep -oE 'exit [0-9]+' install.sh | sort -u` yields only `exit 1` (and implicit exit 0 at main completion). Tests `install/R11-repo-failure-exit1` (bogus repo URL) and `install/R11-uv-failure-exit1` (STUB_UV_FAIL=1) both assert exit code 1 and pass.
- **Verdict**: PASS

### Requirement R12: `cortex upgrade` handler replaces the stub
- **Expected**: `upgrade` subparser's `set_defaults(func=...)` no longer points at `_make_stub("upgrade")`; `cortex upgrade --help` exits 0; handler does not print "not yet implemented".
- **Actual**: `cortex_command/cli.py:279` — `upgrade.set_defaults(func=_dispatch_upgrade)`. The `_dispatch_upgrade` function at line 69-103 is the real handler. Other three stubs (`overnight` is real; `mcp-server` line 265, `init` line 272 remain `_make_stub`). `cortex upgrade --help` runs clean.
- **Verdict**: PASS

### Requirement R13: `cortex upgrade` subprocess flow
- **Expected**: Resolve `cortex_root` from `CORTEX_COMMAND_ROOT` or `$HOME/.cortex`; then three calls: `git status --porcelain` (capture_output=True, text=True, check=True), `git -C <root> pull --ff-only`, `uv tool install -e <root> --force`.
- **Actual**: `cli.py:74` resolves `cortex_root`; `cli.py:76-82, 89-92, 94-97` implement the three subprocess.run calls with exact argv matching the spec. Unit test `test_happy_path_runs_three_calls_in_order` asserts `mock_run.call_args_list` matches the three expected `call(...)` forms exactly.
- **Verdict**: PASS

### Requirement R14: `cortex upgrade` dirty-tree abort
- **Expected**: Non-empty `git status --porcelain` stdout aborts after exactly 1 call.
- **Actual**: `cli.py:83-88` — `if dirty.stdout.strip(): print("uncommitted changes in ..."); return 1`. Test `test_dirty_tree_aborts_after_single_call` asserts rc=1, `mock_run.call_count == 1`, and stderr contains "uncommitted changes". Passes.
- **Verdict**: PASS

### Requirement R15: `cortex upgrade` subprocess failure propagation
- **Expected**: `CalledProcessError` on any of the three calls exits non-zero; third call doesn't run when second fails.
- **Actual**: `cli.py:98-102` catches `CalledProcessError`, prints failed command + captured stderr, returns 1. Test `test_pull_failure_skips_uv_tool_install` asserts rc=1, `mock_run.call_count == 2`, and no call's argv contains `uv`. Passes. Additional test `test_cortex_command_root_env_override` confirms `CORTEX_COMMAND_ROOT` propagates to `cwd=` and `-C` args.
- **Verdict**: PASS

### Requirement R16: Docs updates
- **Expected**: `grep -q 'TBD.*118' docs/setup.md` exits 1; `grep -q 'pending.*ticket 118\|pending — ticket 118' README.md` exits 1.
- **Actual**: Both greps return exit 1. `docs/setup.md:27` has the clean curl one-liner with no TBD banner. `README.md:78-88` has the real Quick Start flow with no "pending — ticket 118" comment.
- **Verdict**: PASS

### Requirement R17: Shellcheck in CI
- **Expected**: `just test` runs `shellcheck -s sh install.sh` and fails on errors; clean branch passes.
- **Actual**: `tests/test_install.sh:69-80` runs shellcheck as the first test (SKIP if shellcheck is absent on dev machines; test case is visible in output). `justfile:348` wires `run_test "test-install" bash tests/test_install.sh` into `just test`. Shellcheck test passes on current install.sh.
- **Verdict**: PASS
- **Notes**: SKIP-on-missing is documented in Veto Surface; CI responsibility to install shellcheck.

### Requirement R18: `just test` passes
- **Expected**: All existing tests plus `tests/test_install.sh` and `tests/test_cli_upgrade.py` pass via `just test`.
- **Actual**: Verified in this review: `bash tests/test_install.sh` → "14 passed, 0 failed"; `.venv/bin/pytest tests/test_cli_upgrade.py -q` → "4 passed in 0.02s". Per plan Task 10 Status line, `just test` aggregate reported 4/4 passed on the author's machine.
- **Verdict**: PASS

### Requirement R19: `run()` subprocess wrapper
- **Expected**: `run()` function wraps all `curl`/`git`/`uv` calls outside its own body; direct unwrapped calls absent.
- **Actual**: `install.sh:8-13` defines `run()` matching spec contract. `grep -qE '^(run|ensure)\(\)\s*\{' install.sh` exits 0. Direct unwrapped calls at `install.sh:60` (`git -C "$target" remote get-url origin`) and `install.sh:62` (`git -C "$target" status --porcelain`) are marked `# allow-direct` to satisfy the R19 lint regex. Test `install/R19-no-unwrapped-subprocess-calls` runs the lint grep and passes.
- **Verdict**: PASS
- **Notes**: The two `# allow-direct` sites are query reads, not actions, and their failure modes are handled as signals (empty string → mismatch branch / dirty-tree branch). Matches plan Task 4 Context notes.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `normalize_repo_url`, `install_uv`, `log`, `run`, `main` — lowercase snake_case POSIX function names matching shell convention. `_dispatch_upgrade` in `cli.py` follows the existing `_dispatch_overnight_*` family naming. `tests/test_cli_upgrade.py` class `TestCortexUpgrade` and method names (`test_happy_path_runs_three_calls_in_order`, `test_dirty_tree_aborts_after_single_call`, etc.) match unittest idiom and the existing `tests/` naming pattern.
- **Error handling**: `run()` wrapper translates any subprocess non-zero exit to exit 1 with a descriptive `[cortex-install] error: command failed: ...` line on stderr; spec invariant upheld. `_dispatch_upgrade` catches `CalledProcessError` once at the end of the happy path, surfacing `exc.cmd` and `exc.stderr` — matches spec R15. Dirty-tree abort (R14) and env-var resolution (R13) are straightforward. Inline comment at `cli.py:93` justifies `--force` via the EPILOG note reference, satisfying the plan's "carries a brief inline comment" constraint.
- **Test coverage**: `tests/test_install.sh` covers 14 scenarios — shellcheck, R2 no-uv bootstrap, R3 just-precondition, R6 all five branches + dirty-tree, R7 ordering, R10 idempotency (three-run sequence with `[project.scripts]` mutation), R11 both failure paths, R19 lint. `tests/test_cli_upgrade.py` covers R13 argv/order, R14 dirty-tree, R15 pull-failure-skips-install, plus env-var override. All plan Task 6 acceptance scenarios are executed. Verified: 14/14 install tests pass + 4/4 upgrade unit tests pass on this machine.
- **Pattern consistency**: `tests/test_install.sh` follows the `tests/test_hooks.sh` convention (pass/fail counters, per-test sandbox, final summary, exit 1 on any failure). `tests/test_cli_upgrade.py` follows `tests/test_plan_worktree_routing.py`'s `patch(..., side_effect=[MagicMock(...), ...])` pattern. `_dispatch_upgrade` mirrors `_dispatch_overnight_*`'s lazy-import structure. The `[cortex-install]` stderr prefix matches existing hook-logging conventions in the repo. `# allow-direct` marker is a new convention introduced for R19 and is cleanly contained — two sites, both documented via inline context in plan Task 4.

### Assessment of Known Deviations

1. **ASCII `--` vs em-dash in final-step message (deviation #1)**: Not a defect. Spec R9 specifies content (three confirmations) without a character-level encoding requirement. All three required substrings (`cortex CLI installed`, `plugin`, `docs/setup.md`) are present; the forbidden substring `12[0-9]` is absent. Character-encoding-independent implementation is a positive for portability.
2. **`url.<path>.insteadOf` + git shim for test hermetic routing (deviation #2)**: Not an R19 violation. R19 applies to `install.sh` only — direct unwrapped `git`/`curl`/`uv` calls in the production script. The shim lives in `tests/fixtures/install/bin/git` and is explicitly marked as a test-harness deviation in `tests/test_install.sh:19-26` (commentary block). The R19 lint test (`install/R19-no-unwrapped-subprocess-calls`) runs against `install.sh` and passes. The shim intercepts only `git remote get-url` to sidestep `insteadOf`'s unconditional substitution (a `git` limitation with no bypass flag). Production safety is preserved.
3. **`patch("subprocess.run", ...)` vs. `patch("cortex_command.cli.subprocess.run", ...)` (deviation #3)**: Not a coverage weakness. Because `subprocess` is lazy-imported inside `_dispatch_upgrade` (matching the `_dispatch_overnight_*` precedent at `cli.py:45-66`), the module-scope attribute `cortex_command.cli.subprocess` does not exist until the handler first runs. Patching `subprocess.run` at the genuine module level works identically — same `subprocess.run` callable is re-bound when the handler does `import subprocess`. All R13/R14/R15 assertions (call count, argv, exit codes, order) are intact. Docstring note at `tests/test_cli_upgrade.py:13-17` documents the rationale. The lazy-import choice in the handler is defensible for `cortex --help` latency and matches `_dispatch_overnight_*`.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
