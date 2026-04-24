# Specification: ship-curl-sh-bootstrap-installer-for-cortex-command

> **Epic reference**: decomposed from the overnight-layer-distribution epic. See [`research/overnight-layer-distribution/research.md`](../../research/overnight-layer-distribution/research.md) DR-4/DR-5/DR-8 for background; this spec scopes to ticket 118 only.

## Problem Statement

A fresh cortex-command user today runs five manual steps (install `uv`, install `just`, clone the repo, `uv tool install -e .`, enable plugins inside Claude). The epic research's DR-4 picked `curl | sh` wrapping `uv tool install -e .` as the primary install path — matching the 2026 norm for AI coding frameworks (opencode, Goose, aider) and language runtimes (`rustup`, `nvm`, `uv`). This ticket ships the bootstrap: a hosted `install.sh` that handles uv/clone/tool-install, plus a real `cortex upgrade` subcommand (currently a `_make_stub`). Plugin auto-registration is deferred — the `cortex-interactive@cortex-command` marketplace/plugin does not exist until tickets 120–122 land, so 118 ships the CLI bootstrap and leaves plugin wiring to a follow-up ticket.

## Requirements

1. **`install.sh` at repo root, POSIX sh, lint-clean**: The file `install.sh` exists at the repo root with `#!/bin/sh` shebang, a `set -eu` line, and is marked executable. **Acceptance**: `test -x install.sh && head -1 install.sh | grep -qx '#!/bin/sh' && grep -qE '^set -eu' install.sh` exits 0. `shellcheck -s sh install.sh` exits 0.

2. **Auto-install `uv` when absent**: When `command -v uv` fails, `install.sh` invokes uv's official installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`). After the call, `command -v uv` succeeds within the same script execution (the installed uv's bin dir is prepended to PATH for the remainder of the script). **Acceptance**: `grep -qE 'astral\\.sh/uv/install\\.sh' install.sh` exits 0; shell integration test `tests/test_install.sh` asserts that a simulated no-uv environment re-exits with uv on PATH.

3. **`just` precondition — detect and error loud**: When `command -v just` fails, `install.sh` writes a message to stderr naming `just` as required with platform-specific remediation (`brew install just` / `apt install just`) and exits 1 **before** any clone or install work. **Acceptance**: `tests/test_install.sh` runs the script in a PATH that excludes `just` (mocked) and asserts exit code 1 and stderr contains both the string `just` and `brew install just`.

4. **Clone destination: `$CORTEX_COMMAND_ROOT` or `$HOME/.cortex`**: The clone target is `${CORTEX_COMMAND_ROOT:-$HOME/.cortex}`. **Acceptance**: `grep -qE 'CORTEX_COMMAND_ROOT:-\\$HOME/\\.cortex' install.sh` exits 0.

5. **`CORTEX_REPO_URL` normalization**: The env var defaults to `charleshall888/cortex-command`. Values matching any of `git@*:*/*`, `ssh://*`, `https://*`, or `http://*` are used verbatim. All other values are treated as `owner/repo` shorthand and normalized to `https://github.com/{owner/repo}.git`. No pre-clone input validation beyond this case-normalization — `git clone` errors propagate directly. **Acceptance**: shell unit test on the normalization function verifies outputs for inputs `charleshall888/cortex-command` → `https://github.com/charleshall888/cortex-command.git`; `https://gitlab.com/me/fork.git` → unchanged; `git@github.com:me/fork.git` → unchanged; `ssh://git@github.com/me/fork.git` → unchanged.

6. **Clone-or-pull safety on existing `$CORTEX_COMMAND_ROOT`**:
   - If the target is a git repo whose `origin` remote is **byte-identical** to the resolved `$CORTEX_REPO_URL`: `git -C <target> fetch --quiet origin && git -C <target> pull --ff-only --quiet`.
   - If the target is a git repo with a different `origin` (including cross-protocol forms of the same repo — e.g., HTTPS origin vs SSH `$CORTEX_REPO_URL`, or shorthand-resolved-HTTPS vs an existing SSH clone): abort with `exit 1` and a stderr message naming both the origin URL and the resolved `$CORTEX_REPO_URL`, suggesting either `git -C <target> remote set-url origin <resolved-url>` or `mv <target> <target>.old && re-run`. No equivalence canonicalization — the spec deliberately chooses byte-identity over fuzzy matching to avoid implementing a URL-parsing subroutine in POSIX sh, and the abort message gives the user a one-command fix.
   - If the target exists and is not a git repo: abort with `exit 1` and a stderr message refusing to overwrite.
   - If the target does not exist: `git clone --quiet $CORTEX_REPO_URL $target`.

   **Critical invariant**: `install.sh` never `rm -rf`s the target. **Acceptance**: `tests/test_install.sh` covers all five branches in a temp `HOME` sandbox — (a) target absent → clone; (b) target same-repo git → pull; (c) target different-origin git → abort with remediation message containing both URLs; (d) target cross-protocol form of same repo (HTTPS origin, SSH `CORTEX_REPO_URL`) → abort (byte-identity is the contract); (e) target not a git repo → abort. Additionally: `grep -qE 'rm -rf' install.sh` exits 1 (pattern not found).

7. **Pre-clone stderr logging**: Before any `git clone` or `git pull`, `install.sh` logs two lines to stderr: the resolved repo URL and the resolved target path, each with the `[cortex-install]` prefix. **Acceptance**: `tests/test_install.sh` captures stderr of a run and asserts it contains `[cortex-install]` followed by both the URL and the target path before the clone.

8. **Tool install step**: After the clone step completes, `install.sh` runs `UV_PYTHON_DOWNLOADS=automatic uv tool install -e "$target" --force`. The `--force` flag is load-bearing — it regenerates entry points when upstream adds or renames `[project.scripts]` entries between runs. This matches `cortex upgrade`'s rebuild policy (R13.3) and `cli.py:21–23`'s EPILOG note. **Acceptance**: `grep -qE 'UV_PYTHON_DOWNLOADS=automatic' install.sh` exits 0; `grep -qE 'uv tool install -e "?\\$?[a-zA-Z_]+"? --force' install.sh` exits 0; post-install `command -v cortex` resolves and `cortex --help` exits 0.

9. **Final-step messaging**: After `uv tool install` succeeds, `install.sh` prints a post-install message to stderr that (a) confirms the `cortex` CLI is installed, (b) states that plugin auto-registration is not yet automated and points the user at `docs/setup.md` for current status and manual steps, (c) does NOT name specific ticket numbers — ticket identifiers are unstable across the epic and forks. No mention of `/plugin install` or `cortex init` as auto-run steps — those are out of scope for 118. **Acceptance**: stderr of a successful install run contains the strings `cortex CLI installed`, `plugin`, and `docs/setup.md`; does NOT contain the substring `120-` (forbidding the stale-ticket pattern). Corresponding check: `install.sh | grep -qE '12[0-9]'` exits 1 (pattern absent from the source).

10. **Idempotent re-run**: Running `install.sh` twice in succession on a healthy install both succeed (exit 0) without destructive changes, and both runs leave the installed `cortex` functional and current with the clone's `pyproject.toml`. The `--force` flag in R8 guarantees entry points are regenerated on every run — if a `git pull` between the two runs introduces a new `[project.scripts]` entry, it resolves after the second run. **Acceptance**: `tests/test_install.sh` runs the script twice in a temp sandbox and asserts (a) both runs exit 0; (b) `~/.cortex/.git/HEAD` is unchanged between runs (no re-clone); (c) after introducing a synthetic new `[project.scripts]` entry into the sandbox clone and running the script a third time, the new console script resolves on PATH.

11. **Failure-path exit contract**: All failure paths in `install.sh` exit **1** — both explicit `exit` statements and subprocess failures. Subprocess failures are translated to exit 1 via a `run()` wrapper function (see R19); raw subprocess exit codes (128, 127, 6, etc.) never surface to the caller. Stderr messages with the `[cortex-install]` prefix identify the failure mode in prose. **Acceptance**: (a) source grep — every `exit` in `install.sh` is either `exit 0` or `exit 1` (`grep -oE 'exit [0-9]+' install.sh | sort -u` yields only `exit 0` and `exit 1`); (b) runtime test — `tests/test_install.sh` runs the script with `CORTEX_REPO_URL=charleshall888/nonexistent-repo-for-test` in a temp sandbox and asserts exit code = 1 (not git's native 128); (c) runtime test — the same with a mocked failing `uv` binary asserts exit code = 1.

12. **`cortex upgrade` handler replaces the stub**: `cortex_command/cli.py` — the `upgrade` subparser at lines 70–75 no longer calls `_make_stub("upgrade")`; its `set_defaults(func=...)` points at a real handler function. The other three stubs (`overnight`, `mcp-server`, `init`) remain untouched. **Acceptance**: `cortex upgrade --help` exits 0; `cortex upgrade --dry-run` (if implemented) or a unit test confirms the handler does not print `not yet implemented`.

13. **`cortex upgrade` subprocess flow**: The handler resolves `cortex_root = os.environ.get("CORTEX_COMMAND_ROOT") or str(Path.home() / ".cortex")`, then:
    1. `subprocess.run(["git", "status", "--porcelain"], cwd=cortex_root, check=True, capture_output=True, text=True)` — if stdout non-empty, abort with exit code 1 and stderr "uncommitted changes in {cortex_root}; commit or stash before upgrading".
    2. `subprocess.run(["git", "-C", cortex_root, "pull", "--ff-only"], check=True)`.
    3. `subprocess.run(["uv", "tool", "install", "-e", cortex_root, "--force"], check=True)`.

    **Acceptance**: unit test `tests/test_cli_upgrade.py` uses `patch("cortex_command.cli.subprocess.run", side_effect=[...])` with three mocked calls, asserts argv of each call matches the above.

14. **`cortex upgrade` dirty-tree abort**: When `git status --porcelain` returns non-empty stdout, `cortex upgrade` exits non-zero without running `git pull` or `uv tool install`. **Acceptance**: unit test mocks the first `subprocess.run` to return `MagicMock(stdout="M file.py\\n", returncode=0)`; asserts exit code != 0 and that `subprocess.run` was called exactly once (not three times).

15. **`cortex upgrade` subprocess failure propagation**: If any of the three subprocess calls raises `CalledProcessError`, `cortex upgrade` exits non-zero. Stderr surfaces the failed command and its stderr (if captured). **Acceptance**: unit test mocks `subprocess.run` to raise `CalledProcessError` on the second call (git pull); asserts exit code != 0 and that the third call (uv tool install) did not run.

16. **Docs updates**: `docs/setup.md` — the `> **TBD:** ...ticket 118...` banner at the install-block immediately following the `curl -fsSL` line is removed. `README.md` — the `# 1. Bootstrap the repo clone (pending — ticket 118 provides curl | sh)` comment and the manual-clone fallback are replaced with the real one-liner. **Acceptance**: `grep -q 'TBD.*118' docs/setup.md` exits 1 (pattern not found); `grep -q 'pending.*ticket 118\\|pending — ticket 118' README.md` exits 1.

17. **Shellcheck in CI**: `just test` (or a `just lint` recipe it delegates to) runs `shellcheck -s sh install.sh` and fails on errors. This prevents future bashism drift. **Acceptance**: `just test` on a branch that intentionally introduces a bashism into `install.sh` (e.g., `[[ ]]`) fails; on a clean branch it passes.

18. **`just test` passes**: All existing tests plus the two new test files (`tests/test_install.sh`, `tests/test_cli_upgrade.py`) pass via `just test`. **Acceptance**: `just test` exits 0.

19. **`run()` subprocess wrapper**: `install.sh` defines a `run()` (or equivalently named) POSIX shell function used for every invocation of `curl`, `git`, and `uv`. Its contract: execute `"$@"`; on non-zero exit, print a `[cortex-install] error: command failed: <command>` line to stderr and `exit 1`. This is how the R11 exit-code contract is actually enforced — `set -eu` alone propagates the subprocess's native exit code (e.g., `git clone`'s 128), which violates R11. The `run()` wrapper catches and re-exits with 1. Matches the `ensure()` pattern in uv's own installer. **Acceptance**: (a) source grep — `grep -qE '^(run|ensure)\\(\\)\\s*\\{' install.sh` exits 0; (b) every subprocess call in the script goes through the wrapper — a lint test asserts that direct unwrapped calls to `git`, `curl`, or `uv` (outside of the wrapper's own body) are absent, via a grep of the form `grep -nE '^\\s*(git|curl|uv) ' install.sh | grep -v '# allow-direct' → no output`; (c) R11's runtime tests (failing `CORTEX_REPO_URL`, failing `uv`) confirm exit code = 1.

## Non-Requirements

- **Plugin auto-registration in `install.sh`** — `claude plugin marketplace add` and `claude plugin install` calls are explicitly NOT made by the bootstrap. The `cortex-interactive@cortex-command` marketplace/plugin does not exist until tickets 120–122 land. A follow-up ticket wires auto-registration once those land.
- **`cortex init` invocation** — per-repo scaffolding is ticket 119's territory. `install.sh` does not run `cortex init` anywhere.
- **`cortex setup` subcommand** — does not exist; 117 retired it. `install.sh` makes no call matching that name.
- **Homebrew tap** — ticket 125.
- **npm-global distribution** — rejected in DR-4; not in scope.
- **Windows-native support** — macOS + Linux only (WSL is transparent via bash). No `.ps1`, no `.cmd`, no Windows-specific branches.
- **GPG/signature verification of `install.sh`** — out of scope. Matches `curl | sh` prior-art norms (rustup, uv, aider, opencode, Goose).
- **Auto-install of `just`** — detected and errored; not installed by this script.
- **Release-tag-pinned install URL** — `install.sh` is served from `main`. A future ticket may migrate to `releases/vN/install.sh` if adoption grows.
- **`--force` flag on `install.sh`** — not implemented. The `clone-or-abort-on-mismatch` behavior (R6) is the safety-vs-automation trade-off; adding `--force` is a future ticket if friction proves real.
- **Auto-stash or `--rebase` in `cortex upgrade`** — not implemented. Dirty-tree aborts (R14) are the chosen trade-off.
- **`--force --reinstall` in `cortex upgrade`** — `--force` alone is used. `--reinstall` forces re-download of every dep every upgrade; unnecessary cost for a rare cache-coherency edge case.
- **URL equivalence canonicalization** — R6 uses byte-identity, not a canonicalizer. HTTPS-vs-SSH-same-repo is handled via the abort-with-remediation path, not by parsing URLs in POSIX sh. Users hitting this case run one `git remote set-url` command.
- **`dangerouslyDisableSandbox: true` handling** — the bootstrap runs outside Claude Code; not applicable.

## Edge Cases

- **`$HOME/.cortex` exists but is an unrelated tool's directory** (e.g., `cortex-cli`, Cortex XSOAR): target is not a git repo → R6 abort branch fires; install.sh exits 1 with "refusing to overwrite".
- **`$HOME/.cortex` is a clone of a different repo** (e.g., user reconfigured `CORTEX_REPO_URL` to a fork, then forgot): R6 abort branch fires; install.sh exits 1 with the mismatching URL named.
- **`$CORTEX_REPO_URL` is a typo that doesn't resolve**: R5 normalization passes (any shorthand becomes `https://github.com/{typo}.git`), then `git clone` fails with "repository not found"; install.sh exits 1 with git's stderr surfaced.
- **uv installer network failure**: R2's `curl ... | sh` exits non-zero; the R19 `run()` wrapper catches and exits 1 with stderr `[cortex-install] error: command failed: curl ...`.
- **`git pull --ff-only` on an existing clone fails** (user has local commits diverging from origin): the `run()` wrapper catches git's non-zero exit (e.g., 128) and re-exits 1; git's stderr is visible above the wrapper's error line. User runs `git -C ~/.cortex log origin/main..HEAD` to see their divergence.
- **`uv tool install -e` fails** (pyproject.toml bad, Python version unavailable, deps unresolvable): the `run()` wrapper catches uv's non-zero exit and re-exits 1; uv's stderr is visible above the wrapper's error line.
- **PATH does not include `~/.local/bin` after install**: install.sh's final-step message (R9) directs the user to run `uv tool update-shell` or consult `docs/setup.md`. Not a failure path — install succeeded; user just needs a shell reload.
- **`cortex upgrade` run when `~/.cortex` has been deleted**: `subprocess.run` on `git status --porcelain` fails with non-zero exit (not a git repo); R15 propagates as non-zero exit with stderr surfacing git's message.
- **`cortex upgrade` run when `CORTEX_COMMAND_ROOT` points at a non-existent path**: same as above — first subprocess call fails, stderr surfaces.
- **`cortex upgrade` run with no network**: `git -C ~/.cortex pull --ff-only` fails; R15 propagates as non-zero exit.
- **Forker with `CORTEX_REPO_URL=myfork/cortex-command`**: install.sh clones the fork; `cortex upgrade` pulls from the fork's origin (unchanged — origin is set at clone time). R9's final-step message points at `docs/setup.md` without naming specific ticket numbers, so it reads correctly for any fork regardless of ticket renumbering (and for upstream regardless of in-flight epic state).
- **Existing SSH clone + shorthand `CORTEX_REPO_URL` on re-run**: user first ran `CORTEX_REPO_URL=git@github.com:me/fork.git curl ... | sh`, then re-runs with `CORTEX_REPO_URL=me/fork` (shorthand). R5 normalizes shorthand to `https://github.com/me/fork.git`; R6's byte-identity check fails against the SSH origin; install.sh aborts with a remediation message naming both URLs and suggesting `git -C ~/.cortex remote set-url origin https://github.com/me/fork.git` or re-invoke with the matching SSH form. This is intentional — equivalence parsing is not implemented; the remediation message is the UX.

## Changes to Existing Behavior

- **ADDED**: `install.sh` at the repo root, served via `https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh` (already-documented URL in `docs/setup.md:27`). New first-step in the install flow.
- **MODIFIED**: `cortex_command/cli.py:70–75` — `upgrade` subparser's handler replaced from `_make_stub("upgrade")` (which prints "not yet implemented: cortex upgrade" to stderr and exits 2) to a real handler that pulls + reinstalls the tool. Changes the behavior of `cortex upgrade` from "always errors" to "updates the installed tool."
- **MODIFIED**: `docs/setup.md:27–32` — the TBD banner is removed once `install.sh` is live. The documented one-liner stops pointing at a 404.
- **MODIFIED**: `README.md:78–91` — the "pending — ticket 118" comment and manual-clone fallback are replaced with the real curl|sh invocation.
- **REMOVED** (nothing): 117 already retired the `setup` / `deploy-*` recipes and the `setup` subcommand. 118 removes nothing further.

## Technical Constraints

- **POSIX sh, no bashisms**: `install.sh` uses `#!/bin/sh` and `set -eu`. Bashisms forbidden (no `[[ ]]`, arrays, `local`, `<<<`, process substitution, `function` keyword, `pipefail`). Enforced by shellcheck `-s sh` in CI (R17).
- **Logging contract**: all progress and error messages go to stderr with the `[cortex-install]` prefix. Stdout is reserved for subprocess output that the user might want to pipe (none currently expected from `install.sh` itself).
- **`$CORTEX_COMMAND_ROOT` convention**: `install.sh` and `cortex upgrade` both honor `$CORTEX_COMMAND_ROOT` with `$HOME/.cortex` fallback. This matches the existing convention used by `skills/overnight/SKILL.md:46` and `skills/morning-review/SKILL.md:10`.
- **No new Python dependencies**: the `cortex upgrade` handler shells out to `git` and `uv` via `subprocess`. Both are already prerequisites. No additions to `pyproject.toml`.
- **Subprocess testing pattern**: `tests/test_cli_upgrade.py` follows the canonical pattern from `tests/test_plan_worktree_routing.py`: `patch("cortex_command.cli.subprocess.run", side_effect=[MagicMock(returncode=..., stdout=..., stderr=...), ...])`.
- **Shell integration testing**: `tests/test_install.sh` follows the convention of `tests/test_hooks.sh` and `tests/test_hook_commit.sh`. Wired into `just test` (new recipe `test-install` delegated from `test`, or inline in `test`).
- **Entry-point regeneration rationale in code comment**: the `cortex upgrade` handler carries a brief inline comment referencing `cli.py:21–23`'s EPILOG note that `[project.scripts]` changes require `uv tool install -e . --force` to take effect. This justifies the `--force` flag presence in the handler without needing to re-explain.
- **Non-fast-forward safety**: `git pull --ff-only` is the canonical flag for both `install.sh`'s pull branch and `cortex upgrade`. Non-fast-forward states (diverged branches, force-pushes) fail cleanly rather than silently merge.
- **No per-repo sandbox config writes**: `install.sh` must not write to `.claude/settings.local.json` in any repo. That is ticket 119 (`cortex init`) scope.
- **Subprocess wrapper pattern**: every external command invocation in `install.sh` goes through the R19 `run()` wrapper. Direct unwrapped calls to `git`/`curl`/`uv` are forbidden outside the wrapper's own body. This is how R11's single-exit-1 contract is enforced at runtime — `set -eu` propagates the subprocess's native exit code (e.g., git's 128), so the wrapper is load-bearing. Matches `ensure()` in uv's official installer.
