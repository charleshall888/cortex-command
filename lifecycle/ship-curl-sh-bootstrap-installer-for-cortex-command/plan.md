# Plan: ship-curl-sh-bootstrap-installer-for-cortex-command

## Overview

Ship `install.sh` at the repo root (POSIX sh, shellchecked, `[cortex-install]`-prefixed stderr logging, a `run()` wrapper enforcing exit-1 contract) that handles uv auto-install, `just` precondition, repo-URL normalization, clone-or-pull safety, idempotent re-runs (`--force` regenerates entry points between runs), and a non-prescriptive final-step message. In the same feature, replace the `cortex upgrade` stub at `cortex_command/cli.py:237-242` with a real handler (dirty-tree abort → `git pull --ff-only` → `uv tool install -e --force`). Update `docs/setup.md` and `README.md` to remove the TBD banners, wire `shellcheck -s sh install.sh` into `just test`, and add two new test files (`tests/test_install.sh`, `tests/test_cli_upgrade.py`).

## Tasks

### Task 1: Scaffold `install.sh` skeleton with `run()` wrapper and logging helper
- **Files**: `install.sh`
- **What**: Create `install.sh` at the repo root with `#!/bin/sh` shebang, `set -eu`, a `log()` helper that prints to stderr with the `[cortex-install]` prefix, and a `run()` wrapper function that executes `"$@"`; on non-zero exit prints `[cortex-install] error: command failed: $*` to stderr and exits 1. Mark executable via `chmod +x install.sh`. No further logic in this task — downstream tasks fill in the body.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Shebang: `#!/bin/sh`
  - Pragma: `set -eu`
  - Helpers (POSIX functions, no `local`):
    - `log() { printf '[cortex-install] %s\n' "$*" >&2; }`
    - `run() { if ! "$@"; then printf '[cortex-install] error: command failed: %s\n' "$*" >&2; exit 1; fi; }`
  - **Invariant**: the `if ! "$@"; then ... fi` guard inside `run()` is load-bearing. Under `set -eu`, an unguarded failing command propagates its native exit code (e.g., git's 128) — `set -e` triggers on the non-zero exit before `run()` can translate it. The `if` construct suspends `set -e` inside its condition, letting `run()` capture the failure and re-exit 1 per R11. Do not simplify the guard away.
  - Mirror the `ensure()` pattern from uv's official installer for `run()`.
  - Body should end with a single call that invokes a `main()` function; `main()` is a no-op in this task and gets filled by later tasks.
- **Verification**: `test -x install.sh && head -1 install.sh | grep -qx '#!/bin/sh' && grep -qE '^set -eu' install.sh && grep -qE '^(run|ensure)\(\)[[:space:]]*\{' install.sh` — pass if exit 0. Also `shellcheck -s sh install.sh` — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Add uv auto-install and `just` precondition checks
- **Files**: `install.sh`
- **What**: In `main()`, add `command -v just >/dev/null 2>&1 || { log "'just' is required..."; ... exit 1; }` with platform-specific remediation (`brew install just` on Darwin, `apt install just` otherwise) — runs BEFORE any clone. Then add the uv-install block: `command -v uv >/dev/null 2>&1 || install_uv`, where `install_uv()` downloads the uv installer to a tempfile via `run curl -LsSf https://astral.sh/uv/install.sh -o "$tmp"` and then executes it via `run sh "$tmp"`. The tempfile split is load-bearing — a single `run sh -c "curl ... | sh"` would let the trailing `sh` mask an earlier `curl` failure (POSIX sh has no `pipefail`, forbidden bashism per spec). After the uv installer completes, prepend `$HOME/.local/bin:$HOME/.cargo/bin` to PATH and export. Use `uname` output to branch the `just`-missing remediation message; keep branches POSIX (`case "$(uname)" in ...`).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `just`-missing stderr must contain both the string `just` and `brew install just` (R3 acceptance).
  - uv installer URL: `https://astral.sh/uv/install.sh` — downloaded via `run curl -LsSf ... -o "$tmp"` where `$tmp` is `$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/cortex-uv-install.$$")`. Execute the downloaded installer via `run sh "$tmp"`, then `rm -f "$tmp"` (note: `rm -f`, NOT `rm -rf` — the R6 grep invariant forbids `rm -rf` but allows `rm -f` on single files).
  - **Why the tempfile split**: POSIX sh pipelines report only the last command's exit code; `curl | sh` with a failing curl and empty stdin yields `sh`-exits-0, which silently defeats R11. Splitting into two wrapped calls lets `run()` catch either failure independently.
  - PATH prepend: `$HOME/.local/bin` (where uv installs on Linux/macOS without `XDG_BIN_HOME` set) and `$HOME/.cargo/bin` (uv's older default) — both prepended to survive either layout.
- **Verification**: `grep -qE 'astral\.sh/uv/install\.sh' install.sh && grep -qE 'brew install just' install.sh && ! grep -qE 'curl[^|]*\|[[:space:]]*sh' install.sh` — pass if first two greps exit 0 AND the third exits 1 (no unsplit curl-to-sh pipe present).
- **Status**: [ ] pending

### Task 3: Add `CORTEX_REPO_URL` normalization function
- **Files**: `install.sh`
- **What**: Add a POSIX function `normalize_repo_url()` that reads `CORTEX_REPO_URL` (default `charleshall888/cortex-command`), passes through values matching `git@*:*/*`, `ssh://*`, `https://*`, `http://*` verbatim, and otherwise treats the value as `owner/repo` shorthand and prepends `https://github.com/` + appends `.git`. No pre-clone validation beyond this case-normalization. Call it near the top of `main()`, store result in a `resolved_url` variable.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Spec R5 input/output contracts:
    - `charleshall888/cortex-command` → `https://github.com/charleshall888/cortex-command.git`
    - `https://gitlab.com/me/fork.git` → unchanged
    - `git@github.com:me/fork.git` → unchanged
    - `ssh://git@github.com/me/fork.git` → unchanged
  - Pattern matching via POSIX `case "$url" in git@*:*/*) ...;; ssh://*|https://*|http://*) ...;; *) ...;; esac` — no `[[ ]]` bashisms.
- **Verification**: `grep -qE 'normalize_repo_url' install.sh && grep -qE 'CORTEX_REPO_URL' install.sh` — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Add clone-or-pull safety logic on existing target
- **Files**: `install.sh`
- **What**: In `main()`, resolve `target=${CORTEX_COMMAND_ROOT:-$HOME/.cortex}` and implement the five-branch clone-or-pull flow from spec R6, **using the spec's branch labels verbatim** (the labels (a)-(e) below are the spec's; do not renumber): (a) target absent → `run git clone --quiet "$resolved_url" "$target"`; (b) target is a git repo whose `origin` URL is byte-identical to `resolved_url` → FIRST check `git -C "$target" status --porcelain  # allow-direct` — if its stdout is non-empty, log a stderr message naming `$target` + `"uncommitted changes in $target; commit or stash before re-installing (or use 'cortex upgrade' after committing)"` and `exit 1`; otherwise `run git -C "$target" fetch --quiet origin && run git -C "$target" pull --ff-only --quiet`; (c) target is a git repo with a different `origin` → `log` a stderr message naming both URLs with the remediation text (`git -C "$target" remote set-url origin "$resolved_url"` OR `mv "$target" "$target.old" && re-run`) and `exit 1`; (d) target is a git repo with a cross-protocol form of the same repo (e.g., HTTPS origin when `CORTEX_REPO_URL` normalizes to SSH, or vice versa) → same abort path as (c) — byte-identity is the contract, so cross-protocol same-repo falls under "different origin"; (e) target exists but is not a git repo → log "refusing to overwrite" and `exit 1`. Before any clone/pull, emit pre-clone log lines (R7): two `log` calls, one for `resolved_url`, one for `target`. **Critical invariants**: no `rm -rf` anywhere in the file; the two unwrapped direct `git` calls (the `remote get-url origin` origin-check and the new `status --porcelain` dirty-tree check) MUST carry the `# allow-direct` trailing comment to exempt them from the R19 lint (Task 6); the dirty-tree check in branch (b) mirrors `cortex upgrade`'s Task 8 safety posture — both re-run paths refuse to touch a dirty tree.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - Detection: `[ -d "$target/.git" ]` = is-git-repo; `git -C "$target" remote get-url origin  # allow-direct` = origin URL (intentionally unwrapped since failure is a signal, not a fatal error — the `# allow-direct` comment marker keeps the R19 lint from flagging it).
  - Branch matching via nested `if` / `case` on combined state — avoid `[[ ]]`.
  - Abort message for branches (c)/(d) must name BOTH the existing origin and the resolved URL so users can see the mismatch at a glance.
  - POSIX-compatible conditional: use `[ ]` / `test`, not `[[ ]]`.
- **Verification**: `grep -qE 'CORTEX_COMMAND_ROOT:-\$HOME/\.cortex' install.sh && ! grep -qE 'rm -rf' install.sh` — pass if first grep exits 0 AND second grep exits 1 (pattern absent).
- **Status**: [ ] pending

### Task 5: Add `uv tool install -e` step and final-step messaging
- **Files**: `install.sh`
- **What**: After the clone/pull branch returns successfully, invoke `run env UV_PYTHON_DOWNLOADS=automatic uv tool install -e "$target" --force`. On success, emit a three-line stderr message via `log`: (a) "cortex CLI installed." (b) "plugin auto-registration is not yet automated — see docs/setup.md for manual steps." (c) "if `cortex` is not on your PATH, run `uv tool update-shell` and reload your shell." The message must NOT contain any literal `12[0-9]` substring (ticket numbers are unstable — R9).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - `UV_PYTHON_DOWNLOADS=automatic` is a ceremony to keep uv from prompting on fresh installs where the user's Python is too old.
  - `--force` is load-bearing: it regenerates `[project.scripts]` entry points between runs (see `cli.py:21-23` EPILOG note and spec R8).
  - Env-var invocation pattern `env VAR=value uv ...` keeps the assignment outside the `run()` wrapper's `$@` concern — `run` sees `env` as argv[0].
- **Verification**: `grep -qE 'UV_PYTHON_DOWNLOADS=automatic' install.sh && grep -qE 'uv tool install -e "?\$?[a-zA-Z_]+"? --force' install.sh && ! grep -qE '12[0-9]' install.sh` — pass if exit code matches each clause.
- **Status**: [ ] pending

### Task 6: Write `tests/test_install.sh` — shell integration tests
- **Files**: `tests/test_install.sh`, `tests/fixtures/install/` (new directory holding stub scripts + fake-repo setup helpers; expected file count 6–10, see Context)
- **What**: Write a `#!/bin/bash` integration test (bash is fine for the test harness; only `install.sh` itself must be POSIX sh) that exercises these acceptance scenarios:
  - **R2**: no-uv env simulation — hermetic (no real network).
  - **R3**: no-just PATH → exit 1, stderr names `just` and `brew install just`.
  - **R6** spec branches (a)–(e) per the verbatim labels in Task 4 (five distinct cases including the cross-protocol (d)).
  - **R6 (b) dirty-tree abort**: separate sub-case covering Task 4's dirty-tree pre-flight — pre-init `$target` as a byte-identical-origin git repo, write an uncommitted modification to a tracked file, run `install.sh`, assert exit 1 and stderr contains `uncommitted changes`. Verifies the install.sh re-run path now matches `cortex upgrade`'s safety posture (no silent interleaving of upstream commits with uncommitted edits).
  - **R7**: pre-clone stderr ordering — the two `[cortex-install]` log lines for URL and target appear before the clone call.
  - **R10**: idempotent re-run — two consecutive runs both exit 0; `$target/.git/HEAD` unchanged; after a synthetic new `[project.scripts]` entry is added to the sandbox clone's `pyproject.toml`, a third run regenerates the console script entry.
  - **R11 (×2)**: (a) failing `CORTEX_REPO_URL` → exit 1 (not git's native 128); (b) stubbed failing `uv` → exit 1 (not uv's native code).
  - **R19**: no unwrapped `git`/`curl`/`uv` calls outside the wrapper body — see lint regex in Context.

  Use PATH-mock stubs + a sandbox `HOME`; do not wire the test into `just test` here (Task 7 owns justfile wiring).
- **Depends on**: [5]
- **Complexity**: complex
- **Context**:
  - **Test file format**: follows the pass/fail-counter convention from `tests/test_hooks.sh`, extended with stderr-capture plumbing (R7 and R11 assertions need ordered stderr capture; `tests/test_hooks.sh` does not demonstrate this — the harness in `tests/test_install.sh` must add it).
  - **PATH-mocked stubs and their dispatch protocol**:
    - Stub scripts live in `tests/fixtures/install/bin/` (copied to a per-test `$tmpdir/bin` so tests can mutate without cross-test leakage). `PATH="$tmpdir/bin:/usr/bin:/bin"` for the test invocation — prepended so stubs win over system binaries.
    - **`uv` stub**: default behavior appends argv to `$tmpdir/uv.argv` and exits 0. Dispatch via env var `STUB_UV_FAIL=1` — when set, the stub writes to stderr and exits 1. R11's failing-uv test sets this; R2/R10's happy path does not.
    - **`curl` stub**: default behavior appends argv to `$tmpdir/curl.argv` and, when invoked with `-o $path`, writes a minimal stub uv-installer shell script to `$path` (the script copies a stub `uv` binary into `$HOME/.local/bin/`). Dispatch via `STUB_CURL_FAIL=1` for failure injection.
    - **`just` stub**: absence is the test — `tests/fixtures/install/bin/` does NOT contain `just`. Tests that need `just` to exist symlink a trivial `just` (`exit 0`) into `$tmpdir/bin`.
    - **`git`**: do NOT stub in most branches. Use real `git init` + `git config remote.origin.url <url>` to set up fake target repos for R6 branches (b), (c), (d). This is cheaper than a multi-subcommand stub and exercises real git. A local bare repo (`git init --bare $tmpdir/fake-upstream.git`) serves as the clone source so branch (a)'s `git clone` succeeds hermetically. For R11's clone-failure case, point `CORTEX_REPO_URL` at a nonexistent `file:///nonexistent/bogus.git` — real git fails fast with exit code that the `run()` wrapper translates to 1.
  - **R6 branch-by-branch fixture setup** (spec labels):
    - (a) target absent → `rm -rf "$target"` before the run (the test harness's cleanup, NOT `install.sh`); `CORTEX_REPO_URL=file://$tmpdir/fake-upstream.git`; assert clone succeeds.
    - (b) target is a git repo with byte-identical origin → `git init $target && git -C $target config remote.origin.url "file://$tmpdir/fake-upstream.git"`; ensure working tree is CLEAN (no uncommitted modifications) so the dirty-tree pre-flight passes; assert `pull --ff-only` runs (verify by pre-creating a commit in fake-upstream and asserting `$target/.git/HEAD`'s ref advances).
    - (b-dirty) same setup as (b), then write an uncommitted modification (e.g., `echo "local edit" > $target/pyproject.toml` after staging a baseline commit); assert exit 1 and stderr contains `uncommitted changes`. This is the test case backing Task 4's dirty-tree pre-flight.
    - (c) target is a git repo with different origin → pre-init with a mismatching origin URL; assert exit 1 and stderr contains both URLs.
    - (d) cross-protocol same repo → pre-init `$target` with an HTTPS origin (`https://github.com/charleshall888/cortex-command.git`) while setting `CORTEX_REPO_URL=git@github.com:charleshall888/cortex-command.git` (byte-different by design); assert exit 1 (same path as (c)).
    - (e) target is not a git repo → `mkdir $target` (no `.git`); assert exit 1 with "refusing to overwrite" stderr.
  - **R2 hermeticity**: for the no-uv test case, ensure `$tmpdir/bin/` does not contain `uv` (i.e., `rm -f $tmpdir/bin/uv` before that test). After install.sh runs the uv-installer path, assert that `$tmpdir/bin/uv` (or `$HOME/.local/bin/uv`, per the curl-stub writer) is now present.
  - **R19 lint regex (POSIX-portable)**: `grep -nE '^[[:space:]]*(git|curl|uv)[[:space:]]' install.sh | grep -v '# allow-direct' | grep -v '^[[:space:]]*run[[:space:]]'` — use `[[:space:]]` (POSIX character class) not `\s` (GNU extension; BSD grep on macOS does not honor it reliably in ERE mode, which would make the lint silently false-pass on the primary dev platform). The `# allow-direct` escape exempts intentional direct calls (e.g., Task 4's detection `git remote get-url`); the final grep strips lines that start with `run` so the wrapper body itself is not flagged when it contains the literal string `git`/`curl`/`uv`.
  - **Stderr-ordering assertion (R7)**: capture via `2>&1 >/dev/null` redirected to a file, then grep for line numbers using `grep -n` and assert the URL and target log lines appear before any `git clone` or `git pull` invocation line. The stubs echo their argv to a separate file (`$tmpdir/git.argv`) so stderr and invocation-log ordering are independently checkable.
- **Verification**: `bash tests/test_install.sh` — pass if exit 0 and the output contains a `PASS` line for each of R2, R3, R6(a), R6(b), R6(b-dirty), R6(c), R6(d), R6(e), R7, R10, R11-repo, R11-uv, R19 (thirteen PASS lines minimum).
- **Status**: [ ] pending

### Task 7: Wire `shellcheck` + `test-install` into `just test`
- **Files**: `tests/test_install.sh`, `justfile`
- **What**: Two edits in this task: (1) Prepend a shellcheck test case to `tests/test_install.sh` (created by Task 6) — the case invokes `shellcheck -s sh install.sh` and reports PASS on exit 0, FAIL on non-zero, or SKIP when `command -v shellcheck` fails (SKIP avoids silent false-pass on dev machines missing shellcheck; CI should install it). (2) Add `run_test "test-install" bash tests/test_install.sh` to `justfile`'s `test` recipe, between the existing `test-overnight` and `tests` lines. Do NOT create a separate top-level `test-install` recipe — invoke `bash tests/test_install.sh` directly from `test`'s `run_test` wrapper, keeping the wiring minimal.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - `shellcheck -s sh` specifically targets POSIX-sh mode, catching bashisms (`[[ ]]`, arrays, `local`, `pipefail`, etc.).
  - The shellcheck case is placed FIRST in `tests/test_install.sh` so it runs before any functional test; a bashism in `install.sh` fails fast rather than surfacing downstream as opaque stub errors.
  - SKIP semantics: add a `skip()` helper alongside `pass()`/`fail()`; SKIP increments neither the pass nor fail counter and prints a visible `SKIP` line. This preserves signal — a missing shellcheck is not silently green.
  - `just test`'s aggregator (`justfile:328-354`) uses `run_test` with a name + command; `run_test "test-install" bash tests/test_install.sh` matches the existing pattern.
- **Verification**: `just test` — pass if exit 0 and output contains a `[PASS] test-install` line. To validate shellcheck is load-bearing: introduce a temp bashism (`[[ 1 == 1 ]]`) into `install.sh`, rerun `just test`, assert the `test-install` step reports FAIL; revert.
- **Status**: [ ] pending

### Task 8: Replace `cortex upgrade` stub with real handler
- **Files**: `cortex_command/cli.py`
- **What**: Define a new handler `_dispatch_upgrade(args: argparse.Namespace) -> int` following the same lazy-import pattern used by `_dispatch_overnight_*`. The handler: (1) resolves `cortex_root = os.environ.get("CORTEX_COMMAND_ROOT") or str(Path.home() / ".cortex")`; (2) runs `subprocess.run(["git", "status", "--porcelain"], cwd=cortex_root, check=True, capture_output=True, text=True)` — if `stdout.strip()` is non-empty, print `uncommitted changes in {cortex_root}; commit or stash before upgrading` to stderr and `return 1`; (3) runs `subprocess.run(["git", "-C", cortex_root, "pull", "--ff-only"], check=True)`; (4) runs `subprocess.run(["uv", "tool", "install", "-e", cortex_root, "--force"], check=True)`; (5) on any `CalledProcessError`, print the failed command and its captured stderr (if any), `return 1`. Wire the handler via `upgrade.set_defaults(func=_dispatch_upgrade)` replacing the existing `_make_stub("upgrade")` line at line 242. Add imports for `os`, `subprocess`, and `Path`-from-`pathlib` at the top of the module (lazy-import them inside the handler to match the `_dispatch_overnight_*` pattern and keep `--help` fast — not at module top). Add a one-line comment referencing `cli.py:21-23`'s EPILOG note to justify `--force`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Existing pattern: `cortex_command/cli.py:45-66` — `_dispatch_overnight_start/status/cancel/logs` all lazy-import `cli_handler` inside the function body. Mirror this.
  - Existing stub line (line 242): `upgrade.set_defaults(func=_make_stub("upgrade"))` — replace with `upgrade.set_defaults(func=_dispatch_upgrade)`.
  - Handler signature matches other dispatchers: `def _dispatch_upgrade(args: argparse.Namespace) -> int`.
  - Import pattern inside handler:
    ```
    def _dispatch_upgrade(args: argparse.Namespace) -> int:
        import os
        import subprocess
        from pathlib import Path
        # handler body
    ```
  - The three other stubs (`mcp-server`, `init`) remain untouched — do not accidentally rewire them.
- **Verification**: `uv tool install -e . --force && cortex upgrade --help` — pass if exit 0 and output does NOT contain `not yet implemented`. Also `grep -c '_make_stub("upgrade")' cortex_command/cli.py` = 0 — pass if count = 0.
- **Status**: [ ] pending

### Task 9: Write `tests/test_cli_upgrade.py` — unit tests for the upgrade handler
- **Files**: `tests/test_cli_upgrade.py`
- **What**: Write pytest unit tests covering: (a) happy path — `subprocess.run` mocked to return non-empty `stdout=""` on call 1, no-op on calls 2 and 3; assert argv of each of the three calls matches the spec R13 contract; exit code 0; (b) dirty-tree abort — mock call 1 to return `MagicMock(stdout="M file.py\n", returncode=0)`; assert exit code 1 and `subprocess.run` was called exactly once (not three times); stderr contains `uncommitted changes`; (c) subprocess failure on call 2 (git pull) — mock call 2 to raise `CalledProcessError`; assert exit code 1 and call 3 (uv tool install) did not run; (d) `CORTEX_COMMAND_ROOT` override — set env var and assert `cwd=` argument matches the override, not `$HOME/.cortex`. Use the `patch("cortex_command.cli.subprocess.run", side_effect=[...])` pattern from `tests/test_plan_worktree_routing.py`. Tests go under `tests/` so they are picked up by `just test`'s `.venv/bin/pytest tests/ -q`.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**:
  - Reference pattern: `tests/test_plan_worktree_routing.py:17-25` — `from unittest.mock import MagicMock, patch`, `side_effect=[MagicMock(...), ...]` for consecutive `subprocess.run` calls.
  - Subprocess calls in order: [git status --porcelain, git pull --ff-only, uv tool install -e ... --force]. Mocks:
    - Call 1 (happy): `MagicMock(stdout="", returncode=0)` — `.stdout.strip()` is empty, proceed.
    - Call 1 (dirty): `MagicMock(stdout="M file.py\n", returncode=0)` — abort after this call.
  - `CalledProcessError` construction: `subprocess.CalledProcessError(returncode=128, cmd=["git", "-C", root, "pull", "--ff-only"])`.
  - Assertions on argv: `mock_run.call_args_list[0] == call(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True)`.
- **Verification**: `uv run pytest tests/test_cli_upgrade.py -q` — pass if exit 0 and all four tests pass.
- **Status**: [ ] pending

### Task 10: Update `docs/setup.md` and `README.md` — remove TBD banners, wire real one-liner
- **Files**: `docs/setup.md`, `README.md`
- **What**: In `docs/setup.md`, delete the `> **TBD:** the install.sh bootstrap script lands with ticket 118...` blockquote (spec R16 identifies it at line ~31 following the `curl -fsSL` line). In `README.md`, replace the "pending — ticket 118" comment and manual-clone fallback (spec R16 identifies lines 78-91) with the real one-liner: `curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh`. Keep the `uv tool update-shell` one-time step and the plugin-install step; remove only the manual clone + `uv tool install -e` step since the bootstrap now covers them.
- **Depends on**: [5, 8]
- **Complexity**: simple
- **Context**:
  - The `docs/setup.md` TBD block at lines 30-31 (blockquote form: `> **TBD:** ...`) is deleted outright; the curl-one-liner directly above it remains.
  - The `README.md` install block at lines 77-91 is rewritten so the three-step flow reads: step 1 = `curl | sh`; step 2 = `uv tool update-shell`; step 3 = `/plugin marketplace add` + `/plugin install` from inside Claude.
  - Do not introduce new ticket numbers in the rewritten text (R9's `12[0-9]`-pattern rule applies to the installer, not the README, but it's a good habit).
- **Verification**: `grep -q 'TBD.*118' docs/setup.md` — pass if exit 1 (pattern absent). `grep -qE 'pending.*ticket 118|pending — ticket 118' README.md` — pass if exit 1. `grep -qE 'curl -fsSL.*install\.sh.*sh' README.md` — pass if exit 0.
- **Status**: [ ] pending

### Task 11: End-to-end validation — `just test` green, smoke-test real `install.sh` against fork
- **Files**: none (verification-only; no file writes)
- **What**: Run `just test` and confirm it exits 0 with all suites passing (test-pipeline, test-overnight, test-install, tests). Separately, run the production `curl | sh` one-liner TWICE against the real `charleshall888/cortex-command` GitHub URL in a disposable `HOME=$tmpdir` sandbox (network-dependent — skip if no network available): (1) first invocation exercises the cold-install path; (2) second invocation, run back-to-back, exercises the idempotent re-run path against a live remote. Confirm both exit 0 and the installed `cortex --help` resolves after each. This catches real-world drift that the shellcheck + shell-integration tests cannot (DNS, GitHub availability, PATH layout on the real filesystem, two-run idempotence in the production fetch-then-execute flow).
- **Depends on**: [6, 7, 9, 10]
- **Complexity**: simple
- **Context**:
  - `just test` aggregate pass/fail summary in `justfile:328-354` — success means "Test suite: 4/4 passed" and exit 0 (test-pipeline + test-overnight + test-install + tests).
  - Real-world smoke test is best-effort: wrap in a try/skip if the network is unavailable or the GitHub URL 404s. Document the result in the implement phase's commit message.
  - Two-run invocation:
    ```
    HOME=$(mktemp -d) bash -c 'curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh'
    HOME=$HOME bash -c 'curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh'
    ```
    (Second invocation reuses the first's sandbox `HOME` so branch (b) of R6 fires.)
  - Do NOT run `install.sh` against the live `$HOME/.cortex` — always use a scratch `HOME`.
- **Verification**: `just test` — pass if exit 0 and output contains `Test suite: 4/4 passed`. Smoke test is interactive/session-dependent: the executor runs the two-invocation sequence manually and reports both exit codes + `cortex --help` result — no automated verification.
- **Status**: [ ] pending

## Verification Strategy

After all tasks are implemented, the feature is verified end-to-end as follows:

1. **Unit tests**: `just test` exits 0 with every suite passing (pipeline, overnight, install, general pytest). This covers R10 (idempotency), R11 (exit-1 contract), R13-R15 (`cortex upgrade` handler), R17 (shellcheck), R18.
2. **Shellcheck**: `shellcheck -s sh install.sh` exits 0 — enforces R1 (POSIX compliance) and catches bashism drift.
3. **Manual smoke test**: `bash install.sh` in a scratch `HOME` against the real GitHub URL. Confirms the installed `cortex --help` exits 0 and the post-install message matches R9.
4. **Docs check**: `grep` for the removed TBD/pending patterns returns exit 1; grep for the new `curl -fsSL ... install.sh | sh` in README returns exit 0.
5. **Upgrade flow**: `cortex upgrade --help` exits 0 without the stub message; `cortex upgrade` in a clean `$CORTEX_COMMAND_ROOT` completes successfully; `cortex upgrade` in a dirty tree aborts with the expected stderr message.

## Veto Surface

- **Shellcheck absent in local dev — SKIP vs. FAIL**: Task 7 treats missing shellcheck as a SKIP, not a failure. Alternative: make shellcheck a hard dependency (add to `docs/setup.md` prereqs list, fail if absent). The SKIP choice avoids blocking local dev on a missing lint tool at the cost of possibly merging unlinted shell drift on dev machines. CI should install shellcheck; local dev is advisory.
- **Test-install integration via `tests/test_install.sh` vs. a Python-driven test**: We chose bash-scripted integration tests matching `tests/test_hooks.sh` convention. Alternative: drive `install.sh` invocations from a Python pytest file with subprocess/tempdir fixtures. Bash-native is simpler (no cross-language boundary) and matches existing shell-testing idioms in the repo.
- **Lazy imports inside `_dispatch_upgrade` vs. module-top imports for `os`/`subprocess`/`pathlib`**: Spec allows either; we chose lazy imports inside the handler to match `_dispatch_overnight_*` precedent and keep `cortex --help` fast. Cost: minor code repetition if `cortex init` / `mcp-server` handlers land later and need the same imports.
- **`rm -rf` absence is a source-grep invariant, not a runtime property**: R6's acceptance of "never rm -rf" is enforced via `grep -qE 'rm -rf' install.sh` → exit 1. Alternative: runtime assertion via audit logging. The grep is simpler and strictly enforceable; the trade-off is someone could obfuscate the pattern (`rm -r -f`, `rm --recursive --force`, etc.). The spec accepts the grep; we follow it.
- **Idempotent re-run edge: what if `install.sh` is updated on `main` between runs?**: The re-run pulls the latest `install.sh` into `~/.cortex` via `git pull`, but the user is running the OLD `install.sh` they curled earlier. If the script's contract changes meaningfully, the second run may diverge. We accept this — users curl-install when they want fresh bits; existing users run `cortex upgrade`, which does NOT re-run `install.sh`. Matches rustup/uv convention.
- **install.sh re-run vs. `cortex upgrade` — consistent dirty-tree posture**: Task 4's branch (b) now runs the same `git status --porcelain` pre-flight abort that Task 8's `cortex upgrade` does. Both re-run paths refuse to pull over uncommitted modifications. This extends the spec R6 wording (silent on dirty-tree behavior) to close a data-integrity hole for users with local patches in `~/.cortex` (forks, customizations). Prior art (rustup, uv) does not check dirty-tree; we diverge intentionally because `$CORTEX_REPO_URL` exists specifically to support forks, making the forker journey first-class rather than edge.

## Scope Boundaries

The following are explicitly excluded from this feature (maps to spec §Non-Requirements):

- Plugin auto-registration (`claude plugin marketplace add` / `claude plugin install`) — deferred to a follow-up ticket after 120-122 land.
- `cortex init` invocation — ticket 119.
- `cortex setup` subcommand — retired in ticket 117.
- Homebrew tap — ticket 125.
- npm-global distribution — rejected in DR-4.
- Windows-native support — macOS + Linux only; WSL is transparent via bash.
- GPG/signature verification of `install.sh`.
- Auto-install of `just` — detected and errored, not installed.
- Release-tag-pinned install URL — served from `main`.
- `--force` flag on `install.sh` — not implemented; safety-via-abort is the chosen trade-off.
- Auto-stash or `--rebase` in `cortex upgrade` — dirty-tree aborts.
- `--reinstall` in `cortex upgrade` — `--force` alone.
- URL equivalence canonicalization — byte-identity only.
