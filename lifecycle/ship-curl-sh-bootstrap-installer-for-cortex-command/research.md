# Research: Ship curl|sh bootstrap installer for cortex-command

## Epic Reference

This ticket decomposes from the **overnight-layer-distribution** epic. Background in [`research/overnight-layer-distribution/research.md`](../../research/overnight-layer-distribution/research.md) — see DR-4 (install path), DR-5 (`cortex setup` retired by 117), DR-8 (clone/fork tension), DR-9 (plugin marketplace split). Epic research is context only; this document scopes to ticket 118's specifics.

## Codebase Analysis

### Files to create

- `install.sh` (repo root) — hosted bootstrap script. `docs/setup.md:27` already documents `https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh` as the target URL; that URL resolves to a plain file at repo root on `main`. No GitHub Pages, no `.github/` directory, no Jekyll — the hosting infra is "commit and push."
- Test coverage for the installer and the `cortex upgrade` handler (see Conventions below).

### Files to modify

- `cortex_command/cli.py:70-75` — replace the `upgrade = subparsers.add_parser(...)` stub (currently `set_defaults(func=_make_stub("upgrade"))`) with a real handler. Keep `_make_stub` for the other three stubs (`overnight`, `mcp-server`, `init`).
- `docs/setup.md:27-32` — remove the `> **TBD:** ... ticket 118 provides ...` banner once `install.sh` lands.
- `README.md:78-91` — replace the "pending ticket 118" fallback with the real curl|sh one-liner.

### Load-bearing comment already in `cli.py`

`cli.py:21-23`:

> Adding or changing `[project.scripts]` entries requires reinstalling the tool with `uv tool install -e . --force` so the console scripts are regenerated.

This is directly load-bearing for `cortex upgrade` — the `--force` flag must be in the implementation so new or renamed subcommands take effect after `git pull`. Mirror this rationale in the handler docstring.

### 117 retirement context (see `lifecycle/build-cortex-setup-subcommand-and-retire-shareable-install-scaffolding/spec.md`)

- **Why `cortex setup` was NOT built**: once skills/hooks ship via Claude Code plugins (tickets 120–122) and machine-config owns `~/.claude/settings.json`, nothing remained for `cortex setup` to deploy. Cortex-command becomes "pure CLI-plus-plugins — no global-rules injection, no reference-doc symlinks, no settings.json ownership, no post-install command to run." 118 therefore cannot invoke `cortex setup` — that subcommand does not exist.
- **What 117 retired**: `setup`, `setup-force`, `deploy-bin`, `deploy-reference`, `deploy-skills`, `deploy-hooks`, `deploy-config`, `check-symlinks`, `verify-setup` recipes. Verified absent from the current justfile. The `justfile` now has nothing install-related beyond `python-setup` (dev venv via `uv sync`) and `upgrade-deps`.
- **What 117 left in place**: the `upgrade` subparser stub (`cli.py:70-75`). 118 swaps only the handler — the subparser entry is already wired.
- **117 explicitly flagged 118 scope** (`spec.md:63`): "118's author updates the definition when they pick up 118 (likely to `git -C ~/.cortex pull` without a setup call, or `uv tool install -e ~/.cortex --force` to rebuild the tool entry point)."

### Shell style conventions (for `install.sh`)

Existing repo scripts (`bin/git-sync-rebase.sh`, `hooks/cortex-validate-commit.sh`, `hooks/cortex-cleanup-session.sh`) use `#!/usr/bin/env bash + set -euo pipefail + log()` helpers writing to stderr with a bracketed script prefix. **However**, `install.sh` is invoked via `curl ... | sh`, which pipes into `/bin/sh` — on Debian/Ubuntu that's dash, not bash. A `#!/bin/sh` POSIX-compatible script is the correct choice (matches uv, rustup, nvm, aider prior art). Do not copy-paste bash conventions from `bin/`.

### Subprocess testing pattern (for `cortex upgrade` handler)

`tests/test_plan_worktree_routing.py:107,131,157,174,203` and `tests/test_no_commit_classification.py:31,44,58,68` establish the canonical pattern: `patch("module.subprocess.run", side_effect=[MagicMock(returncode=0, stdout="...", stderr="")])`. Use `side_effect` for ordered multi-call scenarios (`git pull` first, `uv tool install --force` second). No existing fixtures for fake `git`/`uv` binaries — subprocess-mock at the Python boundary is the pattern.

### Distribution surface today

- No existing `install.sh` / `bootstrap.sh`.
- No `.github/` directory — no Pages workflow, no Jekyll config.
- `raw.githubusercontent.com` caching: `Cache-Control: max-age=300`, served via Fastly. A malicious commit reverted 30 seconds later can still be served to installers for 5 minutes. Matches prior-art norms.

### Forker considerations — hardcoded upstream URL inventory

Files referencing `charleshall888/cortex-command` that a forker would need to understand:

| File | Lines | Context |
|---|---|---|
| `README.md` | 81 | Pre-118 manual `git clone` fallback (to be replaced by `install.sh` one-liner) |
| `docs/setup.md` | 27 | The advertised install URL |
| `docs/setup.md` | 39 | `/plugin marketplace add charleshall888/cortex-command` |
| `tests/test_runner_pr_gating.py` | 78 | Test fixture git `insteadOf` |

The ticket body specifies honoring `${CORTEX_REPO_URL:-github.com/charleshall888/cortex-command}` — this is the forker seam for `install.sh`. README/docs retain the upstream URL; forkers document their invocation in their own fork's README.

### Existing state-path convention

`$CORTEX_COMMAND_ROOT` with `$HOME/.cortex` fallback is already the convention for locating the clone (`skills/overnight/SKILL.md:46,50,226,234,249`; `skills/morning-review/SKILL.md:10,82`). Both `install.sh` and `cortex upgrade` must honor this; do not introduce a new env var.

## Web Research

### `uv tool install -e <path>` semantics

From [uv Tools docs](https://docs.astral.sh/uv/concepts/tools/) and [Storage reference](https://docs.astral.sh/uv/reference/storage/):

- **Entry points** placed in `~/.local/bin` on macOS/Linux (resolution: `$XDG_BIN_HOME` → `$XDG_DATA_HOME/../bin` → `$HOME/.local/bin`). Override: `UV_TOOL_BIN_DIR`.
- **Tool venvs** stored in `~/.local/share/uv/tools`.
- **`-e` editable flag** is available in current uv releases (issue #5436 tracked the addition; now documented).
- **Idempotence**: "If the tool was previously installed, the existing tool will generally be replaced." A re-run of `uv tool install -e <same-path>` does not error.
- **`--force`** (per [uv concepts](https://docs.astral.sh/uv/concepts/tools/)): "Force installation of the tool. Will replace any existing entry points with the same name in the executable directory." Regenerates entry points. Does NOT regenerate the venv alone — combine with `--reinstall` for a full rebuild.
- **Editable caveat**: changes to `pyproject.toml` (new `[project.scripts]` entries, new dependencies) require reinstall; ordinary source edits reflect live because the install symlinks the path.
- **Auto-installs Python**: `uv tool install` provisions an interpreter if none is available on PATH (controlled by `UV_PYTHON_DOWNLOADS=automatic|never`). No separate `uv python install` step needed.
- **`uv tool update-shell`**: idempotently adds `~/.local/bin` to `.bashrc`, `.zshrc`, `.profile`, and fish's `conf.d/*.env.fish`. Uses a sourced `~/.local/bin/env` helper so re-runs don't duplicate lines.
- **Measured warm-cache timing** (adversarial agent ran on user's machine): `uv tool install -e ~/.cortex --force` on unchanged tree = **720ms** wall clock. Cold-cache with new pyproject deps: 10–20s (dep download dominates). Detect-and-skip logic would cost ~100ms of `uv tool list` + python startup — not worth the branch complexity.

### Prior-art install scripts (direct sources)

- **[uv installer](https://releases.astral.sh/installers/uv/latest/uv-installer.sh)**: `#!/bin/sh` + `shellcheck shell=dash`. Non-interactive by design. Silent overwrite-don't-check. Env vars `UV_INSTALL_DIR`, `UV_NO_MODIFY_PATH`, `INSTALLER_NO_MODIFY_PATH`. Exit 1 on any error via `err()`. Uses colorized `tput setaf` with graceful fallback when no TTY.
- **[rustup installer](https://sh.rustup.rs/)**: `#!/bin/sh` + `shellcheck shell=dash`. Shell wrapper delegates to the `rustup-init` binary for the actual install/update decision. Reconnects a TTY via `< /dev/tty` when stdin is piped and interactive prompts are needed; non-interactive via `curl ... | sh -s -- -y`.
- **[nvm installer](https://github.com/nvm-sh/nvm/blob/master/install.sh)**: Pull-update on existing `$INSTALL_DIR/.git` via `git fetch + checkout FETCH_HEAD` — never `rm -rf` or re-clone. Profile edits are grep-before-append idempotent. Env vars: `NVM_DIR`, `NVM_SOURCE`, `NVM_INSTALL_GITHUB_REPO` (owner/repo shorthand, default `nvm-sh/nvm`; warn-but-proceed on non-default).
- **[aider installer](https://aider.chat/install.sh)** (Jan 2025): Based directly on uv's installer, adds `ensure "${_install_dir}/uv" tool install --force --python python3.12 --with pip aider-chat@latest` at the end. **Idempotence via unconditional `--force`** — no detection logic. This is the strongest precedent for cortex-command's "always force" approach.
- **[opencode installer](https://raw.githubusercontent.com/anomalyco/opencode/refs/heads/dev/install)**: Bash-specific. Version-aware idempotence (`opencode --version` vs target). Grep-before-append for profile edits. Writes to first-existing shell-config candidate only.

### `claude plugin install` — resolved

Web agent cited issue #19522 ("not planned"). Adversarial agent **verified locally** on user's `claude 2.1.119`: `claude plugin marketplace add <source>` and `claude plugin install <plugin>@<marketplace>` both work non-interactively. These are local config operations against `~/.claude/plugins/` — no auth required, no API calls. **The contradiction is resolved: the CLI form exists and is viable.** The feature request issue appears stale or referenced a different surface.

### `CORTEX_REPO_URL` — conventions

- **owner/repo shorthand** (nvm's `NVM_INSTALL_GITHUB_REPO`): shortest UX, forces GitHub + HTTPS.
- **Full URL** (rustup's `RUSTUP_UPDATE_ROOT`): supports any host, SSH transport.
- **Dual-form with normalization** (`gh` CLI): accept either; prepend `https://github.com/` if no scheme. This is the cheapest way to serve both the 90% case and the forker-with-SSH edge case.

### Clone-or-pull pattern (canonical, synthesized from nvm/rustup/npm guidance)

```sh
if [ -d "$target/.git" ]; then
    current_url=$(git -C "$target" remote get-url origin 2>/dev/null || echo "")
    if [ "$current_url" = "$repo_url" ]; then
        git -C "$target" fetch --quiet origin
        git -C "$target" pull --ff-only --quiet
    else
        err "$target exists but points to a different remote ($current_url). Remove it manually or set CORTEX_REPO_URL."
    fi
elif [ -e "$target" ]; then
    err "$target exists and is not a git repository. Refusing to overwrite."
else
    git clone --quiet "$repo_url" "$target"
fi
```

Key invariants: `git remote get-url origin` for remote-URL read; `--ff-only` to fail cleanly on non-fast-forward; **never `rm -rf` a user directory you didn't create this run** — abort loudly instead.

### Sources

- [uv Tools concepts](https://docs.astral.sh/uv/concepts/tools/), [Storage reference](https://docs.astral.sh/uv/reference/storage/), [Python versions](https://docs.astral.sh/uv/concepts/python-versions/)
- [uv installer script](https://releases.astral.sh/installers/uv/latest/uv-installer.sh)
- [uv issue #5436 — editable tool installs](https://github.com/astral-sh/uv/issues/5436), [#8067 — `--reinstall` behavior](https://github.com/astral-sh/uv/issues/8067), [#14547 — `.zshrc` creation on bash systems](https://github.com/astral-sh/uv/issues/14547)
- [rustup installer](https://sh.rustup.rs/), [nvm install.sh](https://github.com/nvm-sh/nvm/blob/master/install.sh)
- [aider uv transition post (Jan 2025)](https://aider.chat/2025/01/15/uv.html), [aider install.sh](https://aider.chat/install.sh)
- [Claude Code plugin docs](https://code.claude.com/docs/en/discover-plugins)

## Requirements & Constraints

### From `requirements/project.md`

- **Line 52 (Out of Scope)**: "Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope." **DR-8 proposed reconciling this with `curl | sh` distribution but the doc has NOT been updated.** Partial alignment applies; this ticket proceeds against DR-8's resolution.
- **Line 19 (Philosophy)**: "Complexity: Must earn its place ... When in doubt, the simpler solution is correct."
- **Line 25 (Architectural)**: "File-based state ... No database or server." Applies — installer writes only to `~/.cortex` (clone) and `~/.local/bin` (entry points via uv).
- **Line 32 (Defense-in-depth)**: sandbox + permissions apply to Claude Code–initiated work. `install.sh` runs outside Claude Code (user shell), so sandbox does not apply — but the script writes to `$HOME` paths, so the `curl | sh` trust boundary is the relevant security surface.

### From `requirements/remote-access.md:41`

"macOS is the primary and only supported platform for session persistence (Ghostty dependency). Linux/Windows are not supported." Note: this is a *runtime* constraint for overnight sessions, not for `cortex` CLI itself. The installer targets macOS + Linux (README confirms); Windows via WSL is transparent.

### From `CLAUDE.md`

- **Line 22**: "Cortex-command ships as a CLI installed via `uv tool install -e .` plus plugins installed via `/plugin install`. It no longer deploys symlinks into `~/.claude/`." Installer must end in this state.
- **Lines 34–36**: dependencies — `just`, Python 3, `uv`. Ticket 118 scope auto-installs only `uv`. `just` and Python 3 handling for fresh machines is an Open Decision (Python 3 is actually handled automatically by `uv tool install`; `just` absence is the real gap).
- **Lines 40–42 (commit convention)**: applies to the PR shipping this work.
- **Line 46 (executability)**: new scripts must be `chmod +x`.

### From `lifecycle.config.md`

- `test-command: just test`
- `skip-specify: false`, `skip-review: false`, `commit-artifacts: true`

All new Python code (e.g., `upgrade` handler) must keep `just test` green. `install.sh` is shell and lives outside the Python test suite — needs its own shell test or smoke integration wired into `just test`.

### From 117's spec (scope handoff)

Non-Requirement (`spec.md:50`): "No per-repo sandbox allowWrite setup" — that moves to ticket 119 (`cortex init`). **118's installer must NOT attempt per-repo sandbox config.**

## Tradeoffs & Alternatives

All alternatives explored stay within the parent epic's DR-4 decision (curl|sh + `uv tool install -e .`). DR-4 rejected pipx, Homebrew-primary, PyInstaller, npm, Docker — not re-litigated here.

### 1. `~/.cortex` already exists

**Recommended: pull-if-same-repo, abort-otherwise** (rustup style). Check `git -C ~/.cortex config --get remote.origin.url` vs `$CORTEX_REPO_URL`; match → `git pull --ff-only`; mismatch or non-git → abort with remediation message (`mv ~/.cortex ~/.cortex.old && re-run`). Rejected: backup-to-`.bak.{timestamp}` (litters `$HOME`), `--force`-or-abort (first-time re-runners hit a wall), manual-removal-always (worst UX). Critical safety invariant: **never `rm -rf` a user directory you didn't create this run.**

### 2. Installer's final step after `uv tool install -e`

**Recommended: print next-steps message** (Option (a) from backlog Open Decisions) — with the caveat flagged in Open Questions below. Option (b) (invoke `claude plugin install` non-interactively) is technically viable (CLI form verified) but **the marketplace and plugin it would install don't exist yet** (tickets 120–122 unlanded). Option (c) omits the plugin step — strictly worse than (a). See Open Question 1 for the scope-vs-dependency decision.

### 3. `CORTEX_REPO_URL` format

**Recommended: accept either owner/repo or full URL, normalize internally**:

```sh
case "$CORTEX_REPO_URL" in
    git@*|https://*|http://*) url="$CORTEX_REPO_URL" ;;
    *)                         url="https://github.com/$CORTEX_REPO_URL.git" ;;
esac
```

Rejected: shorthand-only (no escape for SSH/non-GitHub), full-URL-only (verbose for the 90% case).

### 4. `cortex upgrade` dirty-tree handling

**Recommended: abort with copy-pasteable remediation** (no auto-stash, no `--force` flag in v1). Forker-mid-edit friction is small (one `git stash`); silent destruction risk of auto-stash is unbounded. Defer `--force` until friction proves real.

### 5. Idempotence on re-run

**5a (repo present)**: pull, never re-clone.
**5b (tool installed)**: always `uv tool install -e . --force`. Measured 720ms warm-cache; detect-and-skip logic costs similar and misses dep updates. Adversarial finding: consider adding `--reinstall` to defend against editable-install venv drift when pyproject deps change (costs 1–2s extra, guarantees clean state). Spec to pick.

### 6. Hosting

**Recommended: keep `raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh`** (current docs pointer). Zero infra. Forker-friendly automatically (every fork's raw URL works identically). Rejected: GitHub Pages (adds publish step, drift risk), custom domain `cortex.sh` (domain + DNS + TLS cost, no forker benefit). If adoption grows: migrate to a release-tagged URL (`releases/v1/install.sh`) — flagged in Open Questions but not blocking.

### 7. Shell: `#!/bin/sh` vs `#!/usr/bin/env bash`

**Recommended: `#!/bin/sh`** — matches uv, rustup, nvm, aider. The installer's logic (detect uv, clone, `uv tool install`, print steps) needs no arrays, `[[ ]]`, or `local`. `curl ... | sh` in docs stays literally correct on every platform. Add `shellcheck -s sh install.sh` to `just test` (or CI) to catch bashism drift. Do NOT copy the `#!/usr/bin/env bash` pattern from `bin/git-sync-rebase.sh` — that convention applies to repo-internal scripts, not the hosted bootstrap.

## Adversarial Review

### Showstopper: `cortex-interactive@cortex-command` does not exist today

Adversarial agent verified:
- `~/.claude/plugins/known_marketplaces.json` registers only `claude-plugins-official` and `cortex-command-plugins`.
- `cortex-command-plugins/.claude-plugin/marketplace.json` lists `cortex-ui-extras`, `cortex-pr-review`, `cortex-dev-extras`, `android-dev-extras` — **no `cortex-interactive`**.
- The cortex-command repo has no `.claude-plugin/` directory.
- Tickets 120, 121, 122 are all `status: backlog` (122 is blocked-by 115/116/120/121).

The reference `cortex-interactive@cortex-command` in `docs/setup.md:39` and throughout the epic research is **aspirational** — the marketplace manifest and plugin scaffold for `cortex-command` (this repo as a marketplace) does not ship until ticket 122 (blocked on 120 + 121). Until those land, 118's installer has no plugin to auto-register.

**Implication**: Option (b) from the backlog's Open Decisions (invoke `claude plugin install` non-interactively) has nothing to install. Option (a) (print message with `/plugin` commands) is the only currently-viable path, and even it directs the user at a marketplace that doesn't resolve yet.

Three ways to resolve in Spec:
1. **Accept incomplete UX**: 118's installer installs the CLI and prints plugin-install instructions. Users who run it today get a half-configured state. Re-specced once 122 lands.
2. **Block 118 on 122**: don't ship 118 until plugins exist. Delays distribution work by 3+ tickets.
3. **Strip plugin mention from 118's scope**: installer installs only the CLI; a follow-up ticket (post-122) wires plugin auto-registration. This preserves 118's shipability and defers the UX integration to when it's meaningfully completable.

**Recommended for Spec**: (3) — strip plugin auto-registration from 118; print only "next: install the plugins as they land (tickets 120–122)" or similar honest messaging. 118 ships a working `cortex` CLI and a working `cortex upgrade`. The plugin-UX wiring happens when plugins exist.

### Other adversarial findings

- **Supply-chain posture**: `curl | sh` prior-art norms accepted at high (user-confirmed). Additional cheap mitigations: (i) log resolved `$CORTEX_REPO_URL` and `~/.cortex` path prominently to stderr before cloning (defense against pasted-from-chat `CORTEX_REPO_URL=attacker/fork ...`); (ii) `git pull --ff-only` in `cortex upgrade` (fail cleanly on non-fast-forward); (iii) validate `CORTEX_REPO_URL` against a permissive regex before passing to `git clone`.
- **`just` absence on fresh machine**: `uv` auto-installs Python; `just` does not. After `install.sh`, `cortex` works but `just test` / `jcc <recipe>` fail with "command not found". Recommend install.sh detects `just` absence and errors loud with remediation (`brew install just` / `apt install just`).
- **`jcc` / `update-item` / `generate-backlog-index` gap**: these lived in `bin/` (deployed via `just deploy-bin`, retired in 117). Ticket 120 migrates them to plugin `bin/` (backlog, not started). Between 118 landing and 120 landing, the installer produces a `cortex` that works but `jcc` / `update-item` that don't exist. This is a transient gap already acknowledged in CLAUDE.md:49 ("migrate to `cortex-interactive` plugin bin/ in ticket 120"). 118 scope should NOT claim "full install" post-script-run.
- **Non-TTY surface**: `install.sh` itself needs no prompts. `uv tool install` may prompt for Python download — set `UV_PYTHON_DOWNLOADS=automatic` to preempt. `uv tool update-shell` rewrites rcfiles silently — log what it did so the user sees the PATH change.
- **`uv tool install --force` without `--reinstall`**: may leave venv in inconsistent state when pyproject deps conflict across versions. Consider `--reinstall` in `cortex upgrade` (1–2s cost, full venv rebuild). Not strictly needed for first install.
- **`docs/setup.md:27` references the install URL live**: if a user runs the documented one-liner before 118 ships, `raw.githubusercontent.com/.../main/install.sh` returns 404 and `sh` silently succeeds (runs nothing). The TBD banner at `setup.md:27-32` is the only guard. Spec should verify banner placement (the curl line should not appear before the TBD note) or commit the install.sh as the very first change.
- **Broader supply-chain**: pinning to a release tag (vs `main`) is worth considering once adoption grows — not blocking for v1 given the user population is 1.

### Assumptions that may not hold

- `uv` network install is reliable: at scale-of-1 on reasonable connectivity, yes. On slow networks uv's installer is a 30–120s operation — progress output matters.
- `~/.cortex` path collisions: `cortex-cli` (Cortex XSOAR) and Cortex Brain AI both claim the `cortex` name. A user with an unrelated `~/.cortex` must be protected by the clone-or-abort check (decision 1A).
- `uv tool update-shell` edits rcfiles: fails silently if rcfiles are read-only (chezmoi/stow). Log its output so the user sees success or absence.

## Open Questions

1. **Plugin auto-registration scope vs dependency timing** — the `cortex-interactive@cortex-command` reference in `docs/setup.md:39` points at a marketplace/plugin that doesn't exist until tickets 120–122 land. Options: (a) ship 118 with print-message final step acknowledging incomplete UX; (b) block 118 on 122; (c) strip plugin mention from 118 and defer the auto-registration UX to a post-122 follow-up ticket. Deferred: will be resolved in Spec by asking the user — adversarial recommendation is (c), but this is a scope/sequencing decision with downstream commitments the user should confirm.

2. **`cortex upgrade` full-clean rebuild policy** — pick `--force` alone (fast, may leave stale deps when pyproject conflicts across versions) vs `--force --reinstall` (1–2s slower, guaranteed-clean venv). Deferred: will be resolved in Spec's R-requirement enumeration — adversarial recommends `--reinstall`, but the user may prefer the faster path for the common no-dep-change case.

3. **`just` absence handling on fresh machines** — the installer only auto-installs `uv`; `just` is a separate prerequisite. Options: (a) detect `just` absence and error loud with remediation, (b) warn and proceed, (c) auto-install via brew/apt detection. Deferred: will be resolved in Spec — recommendation is (a); Python 3 is handled automatically by `uv tool install` so only `just` needs this treatment.

4. **`CORTEX_REPO_URL` validation regex** — needs to accept `owner/repo`, `https://...`, `http://...`, `git@...` forms while rejecting shell-metacharacter injection. Deferred: will be resolved in Spec with a concrete regex and test cases.

5. **Transient-state messaging (pre-120)** — between 118 landing and 120 landing, `jcc`/`update-item`/`generate-backlog-index` do not exist on fresh installs. Deferred: will be resolved in Spec as a copy decision in the installer's final-message content; not blocking Research→Specify transition.

6. **URL pinning to release tag vs `main`** — serving `install.sh` from `main` is acceptable at single-user scale; a release-tag-pinned URL is the correct migration if adoption grows. Deferred: out of scope for 118 — will be flagged in Spec for a follow-up backlog ticket, does not block this ticket.
