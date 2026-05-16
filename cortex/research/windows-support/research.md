# Research: Add Windows support for this agentic harness

## Headline Finding

Native Windows host support is feasible for cortex-command's full surface (interactive skills + hooks, `bin/cortex-*` CLI utilities, overnight runner + pipeline, dashboard + notifications). Claude Code is generally available on native Windows (PowerShell/CMD/WinGet installers; `v2.1.120` removed the Git-Bash hard requirement; `v2.1.143` enables the PowerShell tool by default for several providers), `~/.claude` paths resolve to `%USERPROFILE%\.claude\`, and hooks have a documented execution surface (Git Bash by default, PowerShell fallback, per-hook `shell: powershell` opt-in). The port reduces to five real workstreams matched to five pieces below: (1) a platform-abstraction seam in `cortex_command/` covering `fcntl.flock`, `start_new_session`/`killpg`, SIGHUP/SIGTERM traps, and the dashboard's `asyncio` event-loop policy; (2) an overnight scheduler Windows port (sibling to the existing `scheduler/macos.py`); (3) a hook execution strategy that begins with an empirical W6 validation (does the Python `[project.scripts]` `.exe` shim work as Claude Code exec-form `command:` on Windows?) and resolves into per-hook rewrites; (4) an `install.ps1` mirror of `install.sh` validated on a Windows VM; (5) a posture-surface piece bundling the `README`/`setup.md`/`project.md` "best-effort Windows" caveat, a runtime sandbox-warning in `cortex init`/runner startup, and an advisory Windows-smoke CI job.

Two findings shape what "support" means and belong up front. **First**, Claude Code does not yet sandbox on native Windows ([Setup table](https://code.claude.com/docs/en/setup): "Sandboxing: Not supported"), but Anthropic has explicitly committed to this on the roadmap ([Sandboxing docs Limitations](https://code.claude.com/docs/en/sandboxing): "Native Windows support is planned"). The gap is **transitional, not architectural** — the port adopts a "warn loudly + proceed; inherit Claude Code's sandbox when it ships" posture rather than committing to a permanent high-friction runtime stance (full DR-2). **Second**, the architectural seam is hybrid: one `WINDOWS = sys.platform == "win32"` flag in `cortex_command/common.py` for thin Python glue (Poetry pattern), plus a `cortex_command/platform/` package with `lock.py` + `process.py` (psutil pattern) for the overnight runner's lock/spawn hot spot where `fcntl` literally does not import on Windows. This pattern subsumes the existing macOS-conditional `durable_fsync` in `common.py:651-670` that already follows the same shape (full DR-1).

## Research Questions

1. **Does Claude Code itself run on native Windows in a way that supports MCP, hooks, plugins, and slash-command skills?** → **Yes, generally available.** Documented at [docs.claude.com Setup](https://code.claude.com/docs/en/setup). Three installer channels (PowerShell `irm | iex`, CMD installer, WinGet `Anthropic.ClaudeCode`). Native installer GA on 2025-10-31. Two delta caveats: native-Windows sandboxing is "Not supported" today but **planned** ([Sandboxing docs](https://code.claude.com/docs/en/sandboxing) Limitations: "Native Windows support is planned"); the `bfs`/`ugrep` embedded Glob/Grep replacement is macOS/Linux-only ("Windows and npm-installed builds unchanged" per CHANGELOG). Plugin marketplace install works (OneDrive `EEXIST` bug fixed; false-positive `cmd /c npx` warning removed).

2. **What POSIX-specific code paths exist in this repo, and how load-bearing is each?** → **Inventory in Codebase Analysis below.** Line numbers reflect the inventory-snapshot tree and may shift; verify against current HEAD before implementation. Highest density is the overnight runner: `fcntl.flock` in 7 modules; `start_new_session=True` + `os.killpg` for orchestrator isolation; SIGTERM/SIGHUP/SIGINT traps in `runner_primitives.py`; `launcher.sh` chains `caffeinate -i`, `osascript`, and `/dev/null` stdin redirection. The dashboard (`cortex_command/dashboard/`, ~3000 LOC FastAPI + asyncio polling) also needs platform attention — `asyncio` defaults to `ProactorEventLoop` on Windows (3.8+), which lacks `add_reader`/`add_writer` for Unix-domain sockets; the dashboard's uvicorn entry binds 127.0.0.1 so this likely works out of the box but should be explicitly validated. Outside those: `terminal-notifier` and tmux are documentation-only in this repo (no Python invocation); `cortex_command/` uses `pathlib.Path` consistently with no hardcoded `/` joins; one symlink site at `pipeline/worktree.py` for `.venv` shadowing; one existing macOS-conditional `durable_fsync` in `common.py:651-670` that already does the `if sys.platform == "darwin":` guard pattern.

3. **Does `uv tool install git+<url>@<tag>` work on native Windows, and what's the install bootstrap?** → **Yes, with caveats.** uv produces real `.exe` shims for `[project.scripts]` console scripts on Windows (default `%USERPROFILE%\.local\bin`, copied not symlinked). Requires `git.exe` on PATH (Git for Windows). Five gotchas to mitigate (issues [#17331](https://github.com/astral-sh/uv/issues/17331) PATH broadcast — fixed; [#14693](https://github.com/astral-sh/uv/issues/14693) PATH detection contradictions — open; [#15011](https://github.com/astral-sh/uv/issues/15011) Defender false positive; [#10030](https://github.com/astral-sh/uv/issues/10030) "Access denied" mid-multi-shim install; [#16877](https://github.com/astral-sh/uv/issues/16877) symlink-needs-admin). Official Windows bootstrap is `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. Cortex's `install.sh` does only (a) uv-if-missing, (b) `uv tool install git+…`, (c) print next steps — replaceable end-to-end by an `install.ps1` sibling; no hidden bootstrap state.

4. **How does cortex's `~/.claude/settings.local.json` write resolve on Windows (path + locking)?** → **Path resolves cleanly to `%USERPROFILE%\.claude\settings.local.json`** per [settings docs](https://code.claude.com/docs/en/settings). Locking is the open problem: `cortex_command/init/settings_merge.py` uses `fcntl.flock(LOCK_EX)` on a sibling lockfile — `fcntl` does not import on Windows. The constraint the write encodes (sandbox `allowWrite` registration) is currently inert on native Windows because Claude Code does not enforce sandboxing there yet — but the planned native-Windows sandbox support means the field will become live when Claude Code adds it, so the write is forward-compatible and should be preserved as-is. Lock substitute: `msvcrt.locking` or the `filelock` PyPI library (cross-platform).

5. **How does Claude Code execute hooks on Windows?** → **Three working invocation modes; one empirically unverified pivot.** Per [hooks docs](https://code.claude.com/docs/en/hooks): (a) `command:` is passed to Git Bash by default if Git for Windows is installed, else PowerShell — so `.sh` shebangs work via Git Bash; (b) `"shell": "powershell"` opts into PowerShell per-hook; (c) `.cmd`/`.bat` work in shell form but not exec form (because they're not real executables). **Empirically unverified**: whether a Python `[project.scripts]` entry point like `cortex-validate-commit` works as `command:` on Windows in exec form. Modern `uv`/`pip` produce `.exe` shims, so it likely works, but no Anthropic doc confirms — this is the first deliverable of Piece (3) (run the test on a Windows VM, takes <1 hour). `[premise-unverified: not-searched]` for whether `#!/usr/bin/env python3` shebangs route via Git Bash or fail on the PowerShell fallback.

6. **Which POSIX primitives does the overnight runner depend on, and can it degrade?** → **Five hot spots, all with documented Windows equivalents:** (i) `fcntl.flock` — substitute with `msvcrt.locking` or `filelock`; (ii) `subprocess.Popen(start_new_session=True)` — substitute with `creationflags=CREATE_NEW_PROCESS_GROUP` (Python 3.7+, stdlib); (iii) `os.killpg(pgid, SIGTERM)` — substitute with `subprocess.Popen.send_signal(CTRL_BREAK_EVENT)` (Windows process-group equivalent); (iv) `signal.SIGHUP` — silently absent on Windows; signal handlers must guard or skip; (v) `launcher.sh` daemonization via `caffeinate -i` + `osascript` + `/dev/null` — Windows Task Scheduler handles process detachment, `SetThreadExecutionState` or `powercfg` replaces `caffeinate`, PowerShell `BurntToast`/`msg.exe` replaces `osascript`. **tmux is documentation-only in this repo** — no Python invocation; the runner expects to run inside a user-managed tmux session. So tmux is a *user-environment* concern (Windows Terminal panes work as substitute), not a code-port concern. Additionally: `pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` ships `launcher.sh` inside the wheel — including the Windows wheel where it's never invoked. Build config should conditionally force-include the platform-appropriate launcher only.

7. **Should Windows support land as scattered conditionals or a platform-abstraction layer?** → **Hybrid, following Poetry + psutil precedent.** Poetry uses one `WINDOWS = sys.platform == "win32"` constant in `src/poetry/utils/_compat.py` with ~60 inline import sites — works because the delta is thin Python glue. psutil uses a separate `_pswindows.py`/`_pslinux.py`/`_psosx.py` split with module-load-time dispatch — works because the entire backend diverges. For cortex-command: one `WINDOWS` constant in `cortex_command/common.py` covers most of the codebase (TMPDIR fallback, settings.local.json path resolution, line-ending normalization); a `cortex_command/platform/` package with `lock.py` + `process.py` implemented via `_posix.py` + `_windows.py` covers the overnight runner where `fcntl` won't import at all. The existing `durable_fsync` macOS conditional in `common.py:651-670` already demonstrates the pattern at file-conditional scope and should be folded into the new package. GitPython's deprecation of its abstraction layer ([git/compat.py](https://github.com/gitpython-developers/GitPython/blob/main/git/compat.py)) is direct evidence that over-abstraction has a cost when the platform delta is thin.

## Codebase Analysis

Line numbers reflect the inventory-snapshot tree at scan time and may shift in current HEAD; treat as approximations and verify before implementation. Where Reviewer B's audit identified specific drift, the entry below is annotated.

### File locking — `fcntl.flock`
- `cortex_command/init/settings_merge.py` — `fcntl.flock(LOCK_EX)` on `~/.claude/.settings.local.json.lock` sibling lockfile; load-bearing per project.md constraint.
- `cortex_command/auth/bootstrap.py` — `fcntl.flock` on token-file writes; load-bearing for concurrent auth bootstrap.
- `cortex_command/overnight/ipc.py` — `fcntl.flock(LOCK_EX|LOCK_NB)` on runner PID state-management locks.
- `cortex_command/overnight/runner.py` — `fcntl.flock()` calls for state mutations; load-bearing for signal-safe writes during shutdown.
- `cortex_command/overnight/sandbox_settings.py` — `fcntl.flock(LOCK_EX)` on event-log writes.
- `cortex_command/overnight/scheduler/lock.py` — `fcntl.flock(LOCK_EX)` on schedule lockfile.
- `plugins/cortex-overnight/server.py:207-215` — `fcntl.flock(LOCK_EX|LOCK_NB)` with 60s blocking acquire + 30s non-blocking timeout; load-bearing for runner-session coordination.
- `NOT_FOUND(query="portalocker|filelock", scope="**/*.py")` — no existing cross-platform lock library; clean greenfield for a `cortex_command/platform/lock.py` introduction.

### Existing macOS conditional — `fcntl.fcntl(fd, F_FULLFSYNC)`
- `cortex_command/common.py:651-670` — `durable_fsync` wraps `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` on macOS, falls back to `os.fsync(fd)` elsewhere via existing `if sys.platform == "darwin":` guard. Called by ~7 critical-write sites including `auth/bootstrap.py`, `overnight/ipc.py`, `overnight/deferral.py`, `overnight/state.py`. **Already works on Windows** (fallback path) but should be folded into the new `cortex_command/platform/` package to consolidate the platform-conditional pattern.

### Process / signal primitives
- `cortex_command/overnight/runner.py` — `os.kill(os.getpid(), signum)` in signal-handler cleanup; load-bearing for canonical signal-death exit codes (130/143/129).
- `cortex_command/overnight/runner.py` — `subprocess.Popen(..., start_new_session=True)` for orchestrator + batch-runner (2 sites); load-bearing for detached process-group isolation.
- `cortex_command/overnight/runner.py` — `os.killpg(pgid, signal.SIGTERM/SIGKILL)` tree-walker; load-bearing for graceful shutdown escalation.
- `cortex_command/overnight/runner_primitives.py` — `_SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)`; load-bearing. SIGHUP is absent on Windows — handler must guard.
- `cortex_command/overnight/runner.py` — `signal.signal(signal.SIGTERM, _handle_sigterm)`.
- `cortex_command/overnight/cli_handler.py` — `subprocess.Popen(..., start_new_session=True)` for async runner spawn.
- `cortex_command/overnight/cli_handler.py` — `os.killpg(pgid, SIGTERM/SIGKILL)` in `overnight_cancel`.
- `cortex_command/overnight/daytime_pipeline.py` — `os.kill(pid, 0)` liveness probe; trivially replaceable cross-platform.
- `plugins/cortex-overnight/server.py` (probe block ~lines 479-510 in current HEAD) — `os.kill(pid, 0)` + `ps -p lstart=` parse; `ps lstart` is macOS-specific. Replace with `psutil.Process.create_time()` (psutil already a transitive dep).
- `cortex_command/overnight/runner_primitives.py` — `psutil.Process(os.getpid()).children(recursive=True)`; cross-platform via psutil, no change.

### `os.open` POSIX flags + mode bits
- `cortex_command/init/settings_merge.py`, `cortex_command/auth/bootstrap.py`, `plugins/cortex-overnight/server.py` — three sites use `os.open(..., os.O_CLOEXEC, 0o600)`. On Windows, `os.O_CLOEXEC` exists as a constant but is silently ineffective for child-fd inheritance semantics (CPython's `_winapi.CreateFile` defaults supersede it), and POSIX mode bits (`0o600`) are ignored — files inherit parent-directory ACLs instead. Cosmetic on a single-user laptop; flag in `docs/setup.md` Windows section.

### Dashboard subsystem (added per Reviewer B)
- `cortex_command/dashboard/` is ~3000 LOC FastAPI + uvicorn + asyncio polling, launched via `_dispatch_dashboard` in `cortex_command/cli.py` calling `uvicorn.run("cortex_command.dashboard.app:app", host="127.0.0.1", port=port, log_level="info")`. Modules: `app.py`, `poller.py`, `data.py`, `seed.py`, `alerts.py`.
- **Windows considerations**: (i) `asyncio` defaults to `ProactorEventLoop` on Windows 3.8+; uvicorn handles this transparently. (ii) `_resolve_pid_path()` in `dashboard/app.py` resolves via `XDG_CACHE_HOME` — an XDG/Linux construct; on Windows the conventional location is `%LOCALAPPDATA%\cortex` (Python's `platformdirs.user_cache_dir()` handles this cross-platform). (iii) Port-binding to `127.0.0.1` and browser-launch via `webbrowser.open` are cross-platform.
- Most of the dashboard works on Windows out of the box; only the XDG cache-path resolution needs a platform-aware substitute. Folds into Piece (1) `cortex_command/platform/`'s thin-glue surface (paths-module or just inline conditional).

### tmux / mosh
- Documentation-only. `cortex/research/archive/overnight-runner-sandbox-launch/research.md`, `cortex/requirements/remote-access.md`, `docs/setup.md`. No active Python or shell invocation of `tmux` or `mosh` was found.
- `NOT_FOUND(query="tmux.*spawn|tmux new-session", scope="**/*.py")`. User-environment concern, not a code-port concern. Windows Terminal / ConEmu work as substitutes.

### terminal-notifier
- Documentation-only references in `docs/setup.md` and `cortex/requirements/observability.md`.
- `NOT_FOUND(query="terminal.notifier|notify.sh", scope="**/*.py")`.

### Shell scripts and PowerShell scripts (revised per Reviewer B)
The original "10 `.sh` files" enumeration was an undercount. The accurate inventory excluding `.git/`, `.claude/worktrees/`, `.venv/`:

**Shipped hooks/scripts (load-bearing):**
- `install.sh` (install-time bootstrap)
- `claude/statusline.sh` (statusline renderer; `.ps1` sibling already present)
- `hooks/cortex-validate-commit.sh`, `hooks/cortex-scan-lifecycle.sh`, `hooks/cortex-cleanup-session.sh`
- `claude/hooks/cortex-tool-failure-tracker.sh`, `claude/hooks/cortex-skill-edit-advisor.sh`, `claude/hooks/cortex-permission-audit-log.sh`, `claude/hooks/cortex-worktree-create.sh`, `claude/hooks/cortex-worktree-remove.sh`
- `cortex_command/overnight/scheduler/launcher.sh` (force-included in wheel via pyproject.toml)
- Plugin-tree mirrors under `plugins/cortex-core/hooks/` (auto-regenerated from the canonical sources above by the dual-source pre-commit hook)
- `plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` (optional)

**Test scripts (block CI verification):**
- `tests/test_hook_commit.sh`, `tests/test_hooks.sh`, `tests/test_install.sh`, `tests/test_tool_failure_tracker.sh`, `tests/test_drift_enforcement.sh`, `tests/test_check_parity_first_run_green.sh`, `tests/test_skill_edit_advisor_scope.sh`, `tests/test_skill_behavior.sh` (8 test scripts; `justfile`'s `test` recipe invokes 3 directly via `bash tests/test_*.sh`)
- `tests/fixtures/*.sh` (5 stub fixtures referenced by tests)

**Contributor bootstrap:**
- `.githooks/pre-commit` (~13.6KB bash script; activated via `just setup-githooks` per CLAUDE.md). Runs under Git for Windows' bundled bash on Windows clones.

Total: ~30 `.sh` files in the canonical roots, not 10. This corrects Piece (3) effort sizing.

**PowerShell:** `claude/statusline.ps1` is the only `.ps1` present today. Sets a precedent: a `.ps1` sibling alongside `.sh` is an acceptable pattern in this repo.

### `justfile` itself (added per Reviewer B)
- 17 recipes contain `#!/usr/bin/env bash` shebangs, including `python-setup`, `setup-tmux-socket`, `backlog-index`, `dashboard`, and the `test` aggregator (which calls `bash tests/test_hook_commit.sh` directly). `just` itself runs on Windows (it has native Windows builds), but the recipe bodies depend on Git for Windows' bash. CLAUDE.md mandates `just` as the project's standard interface, so contributor workflows on Windows route through bash. Worth a Windows-section note in `docs/setup.md`.

### Hardcoded Unix paths
- 8 sites use `os.environ.get("TMPDIR", "/tmp")` — all in `cortex_command/`. Trivially replaceable with `tempfile.gettempdir()` repo-wide. Inline conditional fix.
- `cortex_command/overnight/scheduler/launcher.sh:83` — `/usr/bin/osascript` (macOS notifications on launch failure); no Windows analogue, document as macOS-only.
- `cortex_command/overnight/scheduler/launcher.sh:145,152` — `/usr/bin/caffeinate -i` (prevent idle-sleep); Windows alternatives: `powercfg /requestsoverride`, `SetThreadExecutionState` Win32 API, or accept that the host may sleep.
- `cortex_command/overnight/scheduler/launcher.sh:148,155` — `/dev/null` stdin redirection for POSIX daemonization; PowerShell equivalent is `$null`.
- `NOT_FOUND(query="/var/|/usr/lib|/opt/", scope="**/*.py")` — no other hardcoded Unix paths in Python.

### Path-separator assumptions
- `cortex_command/` uses `pathlib.Path` consistently (43+ occurrences); no hardcoded `/` joins found.
- `cortex_command/overnight/report.py` — `os.path.join` + `os.sep` for git ref-path traversal; cross-platform safe.

### Symlinks
- `cortex_command/pipeline/worktree.py` — `Path.symlink_to(repo_venv)` for `.venv` in overnight worktrees (Reviewer B confirms current line is ~266, not the earlier inventory's :199). Load-bearing for venv activation. **Windows hazard**: symlink creation requires admin or Developer Mode on Windows; on supported Windows versions Developer Mode is the standard fix.
- `claude/hooks/cortex-worktree-create.sh` — `ln -sf "$CWD/.venv" "$WORKTREE_PATH/.venv"`; same purpose, same hazard.

### Line-ending assumptions
- `cortex_command/overnight/sandbox_settings.py` — the JSONL event-log writer uses `os.write(fd, (json.dumps(entry) + "\n").encode("utf-8"))` on a raw `os.open` fd; text-mode `\n→\r\n` translation does NOT apply because it's a bytes-mode write. Correct on Windows as-is.
- `cortex_command/discovery.py` — JSONL pattern: same bytes-mode write, same conclusion.
- `cortex_command/discovery.py` — `if existing and not existing.endswith(b"\n"): existing += b"\n"` — binary-mode append; explicit `\n` is correct regardless of platform.
- **Commit-hook CRLF risk** (added per Reviewer B): `hooks/cortex-validate-commit.sh` does `INPUT=$(cat)` then regex-matches `\.$` against the first line. Under Git Bash on Windows with `core.autocrlf=true` (default), embedded `\r` may silently shift the trailing-period rule. Flag as a risk in Piece (3) hook strategy; Python rewrite eliminates entirely.

### ANSI / terminal
- `claude/statusline.sh` and `claude/statusline.ps1` — both render ANSI via `\x1b[…` / `[char]27`. Modern Windows Terminal and ConPTY support ANSI by default.
- `NOT_FOUND(query="tput|termios|tty module", scope="**/*.py")` — no Python-side terminal manipulation.

### Build config (added per Reviewer B)
- `pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` ships `cortex_command/overnight/scheduler/launcher.sh` inside every wheel including the Windows wheel (~3KB of dead weight + confusion in `site-packages`). Piece (2) should add the Windows-equivalent `launcher.ps1` (or `.bat`) and conditionally force-include only the platform-appropriate launcher, or pragmatically ship both and let the runtime select.

## Web & Documentation Research

### Claude Code on Windows — GA posture
- [Setup docs](https://code.claude.com/docs/en/setup) list "macOS 13.0+ / Windows 10 1809+ or Windows Server 2019+ / Ubuntu 20.04+" as equal-tier system requirements.
- Three native Windows installers: PowerShell `irm https://claude.ai/install.ps1 | iex`, CMD `curl … install.cmd && install.cmd`, and `winget install Anthropic.ClaudeCode`.
- Windows binary is code-signed: "signed by 'Anthropic, PBC'. Verify with `Get-AuthenticodeSignature .\claude.exe`."
- Documented platform deltas: native Windows sandboxing is "Not supported" **today** but [planned](https://code.claude.com/docs/en/sandboxing) ("Native Windows support is planned"); `bfs`/`ugrep` Glob/Grep replacements are macOS/Linux only; the PowerShell tool was a preview through `v2.1.120`, default-on for Bedrock/Vertex/Foundry users as of `v2.1.143`.
- [CHANGELOG v2.1.120](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) — "Git for Windows is no longer required — when absent, Claude Code uses PowerShell as the shell tool."

### Sandboxing on Windows — current state and roadmap
- [Sandboxing docs](https://code.claude.com/docs/en/sandboxing) "OS-level enforcement": "macOS: Seatbelt. Linux: bubblewrap. WSL2: bubblewrap, same as Linux."
- [Sandboxing docs](https://code.claude.com/docs/en/sandboxing) Limitations: "Platform support: Supports macOS, Linux, and WSL2. WSL1 is not supported. **Native Windows support is planned.**"
- Implication: cortex-command's runtime `sandbox.filesystem.allowWrite` registration in `~/.claude/settings.local.json` is currently inert on native Windows but **forward-compatible** — once Anthropic ships native-Windows sandbox enforcement, the existing write will be honored automatically. The cortex-side change is to add a startup warning (today) that will become a no-op (post-Anthropic-release).

### Hook execution on Windows
- [Hooks docs](https://code.claude.com/docs/en/hooks): "The `command` string is passed to a shell: `sh -c` on macOS and Linux, Git Bash on Windows, or PowerShell when Git Bash isn't installed." Per-hook `"shell": "powershell"` opts into PowerShell explicitly.
- Exec form requires a real `.exe`; `.cmd`/`.bat` shims work only in shell form.
- **Unresolved by docs** (Piece 3's first deliverable): whether Python `[project.scripts]` console-script `.exe` shims work as `command:` in exec form. Modern wheel installers produce `.exe` stubs so it likely works, but no Anthropic doc confirms.
- **`[premise-unverified: not-searched]`**: behavior of `#!/usr/bin/env python3` shebangs when Claude Code falls back to PowerShell. Under Git Bash they work; under PowerShell-only the shebang is just a comment.

### `~/.claude` settings resolution on Windows
- [Settings docs](https://code.claude.com/docs/en/settings): "On Windows, paths shown as `~/.claude` resolve to `%USERPROFILE%\.claude`."
- User settings: `%USERPROFILE%\.claude\settings.json`. Project settings: `.claude\settings.json` and `.claude\settings.local.json`. Managed settings: `C:\Program Files\ClaudeCode\managed-settings.json`.
- MCP servers: user-scope at `%USERPROFILE%\.claude.json`; project-scope at `.mcp.json`. Plugin-supplied MCP servers receive `CLAUDE_PROJECT_DIR` env var as of `v2.1.139`.

### `uv tool install` on Windows
- [uv tools concept](https://docs.astral.sh/uv/concepts/tools/): "Tool executables include all console entry points, script entry points, and binary scripts." On Windows, "symlinked into the executable directory on Unix and **copied on Windows**."
- Default Windows executable dir: `%USERPROFILE%\.local\bin`. PATH propagation requires `uv tool update-shell` and often a session restart.
- Git-source install requires `git.exe` on PATH (Git for Windows). uv shells out to system git; no embedded git.
- Five known Windows gotchas: [#17331](https://github.com/astral-sh/uv/issues/17331) PATH `WM_SETTINGCHANGE` broadcast (fixed); [#14693](https://github.com/astral-sh/uv/issues/14693) PATH detection contradiction (open); [#15011](https://github.com/astral-sh/uv/issues/15011) Defender false positive (closed); [#10030](https://github.com/astral-sh/uv/issues/10030) "Access denied" mid-multi-shim install — cortex installs many shims (`cortex`, `cortex-discovery`, `cortex-update-item`, etc.), so this is the highest-risk gotcha; [#16877](https://github.com/astral-sh/uv/issues/16877) `--link-mode=symlink` requires admin (cortex defaults to copy).
- Official uv installer for Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.

## Domain & Prior Art

- **pipx** — centralized `is_windows()` helper in [src/pipx/constants.py](https://github.com/pypa/pipx/blob/main/src/pipx/constants.py) wrapping `platform.system()`, with inline `if WINDOWS:` checks at call sites. No `_windows.py` split.
- **Poetry** — one-line `WINDOWS = sys.platform == "win32"` constant in [src/poetry/utils/_compat.py](https://github.com/python-poetry/poetry/blob/main/src/poetry/utils/_compat.py); ~60 inline import sites. Hot spot is the virtualenv shim layer.
- **mise** — Rust `#[cfg(windows)]` attribute gates plus selective separate files: [src/fake_asdf_windows.rs](https://github.com/jdx/mise/blob/main/src/fake_asdf_windows.rs), [src/plugins/core/ruby_windows.rs](https://github.com/jdx/mise/blob/main/src/plugins/core/ruby_windows.rs). Vs. asdf ([mise comparison page](https://mise.jdx.dev/dev-tools/comparison-to-asdf.html)): "asdf is written in bash … does not run on Windows at all." Language rewrite was the enabling move. **Implication for cortex's ~30 bash scripts**: bash-script density is the actual Windows blocker.
- **GitPython** — inline `sys.platform == "win32"` checks heavily concentrated in [git/cmd.py](https://github.com/gitpython-developers/GitPython/blob/main/git/cmd.py). [git/compat.py](https://github.com/gitpython-developers/GitPython/blob/main/git/compat.py) **deprecated** older `is_win`/`is_posix` aliases — actively moved *away* from a thin abstraction.
- **psutil** — separate-file-per-platform: [psutil/__init__.py](https://github.com/giampaolo/psutil/blob/main/psutil/__init__.py) selects `_psplatform` from `_pslinux.py`, `_pswindows.py`, `_psosx.py`. Justified because platform abstraction *is* the product.
- **CPython stdlib** — `Lib/subprocess.py` uses one `_mswindows` flag + ~15 inline sites; heavy lifting delegated to **separate C extensions** (`_winapi` vs `_posixsubprocess`). Convention: unified Python interface, split native backend.
- **Conventional wisdom**: `NOT_FOUND(query="when to abstract platforms vs inline conditionals Python guidance PEP", scope="peps.python.org, devguide.python.org")` — no PEP-level prescription. Closest written guidance is [mypy #10054](https://github.com/python/mypy/issues/10054) on `sys.platform` type-narrowing — a tooling constraint.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A — Inline conditionals only** (one `WINDOWS` flag, no abstraction package) | M | `fcntl` won't import at module top-level on Windows even guarded by `if WINDOWS:` unless the import itself is conditional; risks scatter that resists later cleanup. | Audit every `fcntl` import site to guard at import time. |
| **B — Hybrid: flag + `cortex_command/platform/` package for runner hot spots** (Poetry + psutil hybrid) | L | Two patterns coexist; reviewers must know which to use where. Mitigation: document the rule "abstract when the syscall doesn't import; inline otherwise." | Decide what lives in `platform/`: `lock.py` (definite), `process.py` (definite — currently scheduler-only consumer but generalizes naturally), fold existing `durable_fsync` in. |
| **C — Full abstraction layer for all platform concerns** (psutil pattern everywhere) | XL | Over-engineering for thin glue; GitPython removed exactly this pattern. | Reorganization of `cortex_command/` to fit the model. |
| **D — Require WSL 2 on Windows; don't port to native** | XS | Contradicts user's "native host" choice; documentation-only fix. | None. |

Recommended: **B**.

### Workstream-level effort (assuming B)

| Workstream | Effort | Risks | Prerequisites |
|------------|--------|-------|---------------|
| W1: `cortex_command/platform/` package (`lock.py`, `process.py`, fold `durable_fsync`) + `WINDOWS` flag in `common.py` + dashboard XDG-path substitute | M | Cleanly testable; psutil already a transitive dep; `filelock` is well-maintained. `process` primitives currently have only Piece (2) as Windows consumer; module is still right home because scheduler is one of two subsystems and the contract generalizes. | Pick `filelock` vs. `msvcrt.locking` direct. |
| W2: Overnight scheduler Windows port (`scheduler/windows.py` sibling to `scheduler/macos.py`; Task Scheduler instead of launchd; `launcher.ps1` sibling) | L | Task Scheduler's CLI surface (`schtasks`/`Register-ScheduledTask`) is verbose; XML vs. PowerShell trade-off. `caffeinate` substitute is non-trivial. **Safety-posture risk**: scheduling `--dangerously-skip-permissions` runs on a sandbox-absent host until Anthropic ships native-Windows sandbox — mitigated by the Piece (5) runtime warning. `pyproject.toml` force-include of `launcher.sh` should add `launcher.ps1`. | W1 done. |
| W3: Hook execution validation + strategy — empirical W6 test (does Python entry-point `.exe` shim work as exec-form `command:`?) followed by per-hook rewrite. ~30 `.sh` files in scope (not 10); priority is the ~9 cortex-shipped hooks, not the test scripts. | M-L | Validation is <1 hour on a Windows VM. Implementation depends on outcome: shim-works → rewrite cortex-* hooks to use `command: cortex-validate-commit` directly (no `.sh`); shim-fails → author `.ps1` siblings. Statusline already has `.ps1` (proof of pattern). Justfile recipes (17 bash shebangs) are a contributor concern, not a Claude-Code-runtime concern; defer to docs note. | None (validation is the prerequisite, done within the workstream). |
| W4: `install.ps1` sibling to `install.sh` + Windows-troubleshooting section in `docs/setup.md` + validate `cortex init` runs cleanly on Windows VM | S-M | uv has known PATH-broadcast gotchas; document workaround. `cortex init` Windows behavior is the second half of the W6 empirical test. | None. |
| W5: Posture surface — README/setup.md/project.md "best-effort Windows" caveat (separating safety-property delta from ergonomic deltas) + `cortex init`/runner startup sandbox-warning (transitional until Anthropic ships native sandbox) + advisory Windows-smoke CI job (`cortex --version` + `cortex init --dry-run`) | S | Touches `cortex/requirements/project.md` (sensitive policy file). Warning text must read "transitional" so users understand it'll go away once native-Windows sandbox ships. | User approval of the posture wording. |

## Architecture

### Pieces

1. **Platform abstraction seam** — `cortex_command/platform/` package: `lock.py` (cross-platform advisory lock wrapping `filelock` or `msvcrt.locking`), `process.py` (cross-platform `start_new_session` ↔ `CREATE_NEW_PROCESS_GROUP`, `killpg` ↔ `send_signal(CTRL_BREAK_EVENT)`, SIGHUP-absent guard); fold the existing macOS-conditional `durable_fsync` in `common.py:651-670` into the package; plus one `WINDOWS = sys.platform == "win32"` constant in `cortex_command/common.py` for thin glue (TMPDIR fallback, settings.local.json path, dashboard's `XDG_CACHE_HOME` → `platformdirs.user_cache_dir()` substitute). Role: hide platform-specific syscalls behind a uniform contract for the overnight runner and absorb the existing scattered platform conditionals; do not abstract concerns Python already handles cross-platform.

2. **Overnight scheduler Windows port** — `cortex_command/overnight/scheduler/windows.py` sibling to the existing `scheduler/macos.py`, registering a Windows Task Scheduler entry for the cortex round loop; `launcher.ps1` sibling to `launcher.sh` adapting the daemonization sequence (Task Scheduler handles process detachment; `SetThreadExecutionState` via ctypes or `powercfg` replaces `caffeinate`; PowerShell `BurntToast` toast notifications or `msg.exe` replace `osascript`); `pyproject.toml` updated to ship `launcher.ps1` alongside `launcher.sh` in the wheel. Role: make scheduled overnight runs work on Windows; the rest of the runner subsystem inherits cross-platform behavior from Piece (1).

3. **Hook execution validation + strategy** — Two-step deliverable executed within one ticket. Step A (validation, <1 hour): on a Windows VM with `uv tool install`-installed cortex and Claude Code installed, configure one hook with `command: "cortex-validate-commit"` (the Python `[project.scripts]` entry point as exec-form `command:`) and verify it fires correctly. Also verify `#!/usr/bin/env python3` shebang behavior under the PowerShell fallback. Step B (implementation, contingent on Step A outcome): if shim works → rewrite the ~9 cortex-shipped `.sh` hooks that already shell out to `cortex-*` entry points as direct `command:` invocations and delete the `.sh` files; if shim fails → author `.ps1` siblings for each (statusline pattern). Test-script `.sh` files (~13 under `tests/`) stay bash-only and are documented as requiring Git for Windows to run the test suite on Windows. Role: ensure `~/.claude/settings.json` hooks fire correctly on Windows under either Git-Bash-present or PowerShell-fallback regimes; eliminate the `.sh` wrapper layer where possible.

4. **Installer + bootstrap port** — `install.ps1` sibling to `install.sh` running (a) `irm https://astral.sh/uv/install.ps1 | iex` if uv missing, (b) `uv tool install git+…@<tag>`, (c) `uv tool update-shell`, (d) next-steps message; plus a Windows-troubleshooting subsection in `docs/setup.md` documenting the five uv gotchas; plus empirical verification that `cortex init` runs cleanly on Windows VM (the second half of W6 validation). Role: deliver a `curl-then-install`-equivalent first-run experience on Windows.

5. **Posture surface — docs, runtime warning, and advisory CI** — `README.md:14`, `docs/setup.md:337`, and `cortex/requirements/project.md` updated to read "macOS-primary; Windows best-effort," with the caveat list explicitly separating the **transitional safety-property delta** (sandbox not yet enforced on native Windows; planned by Anthropic; cortex's runtime emits a startup warning until then) from **ergonomic deltas** (tmux is user-managed; `caffeinate`/`osascript` are macOS-only with no-op fallbacks; justfile recipes assume Git for Windows). Plus a `cortex init` and overnight-runner startup warning printing "WARNING: Claude Code does not yet enforce sandboxing on native Windows. `--dangerously-skip-permissions` runs without a safety boundary on this host. See [link to Anthropic roadmap]." Plus an advisory `.github/workflows/windows-smoke.yml` running `runs-on: windows-latest` to install the wheel and execute `cortex --version` + `cortex init --dry-run` (non-blocking on PRs). Role: materialize the project's "best-effort Windows" posture as a coherent surface — what we say (docs), what we do at runtime (warning), and what we verify (CI smoke).

### Integration shape

- (1) is the foundation. (2) consumes `process.spawn_detached`/`signal_group` from (1); (3) and (4) consume `WINDOWS` from (1) for thin glue; (5) is the only Windows consumer that does not directly depend on (1) for code (the runtime warning is a one-line `print()`).
- (4) is the install-time entry point that puts the cortex CLI on PATH; (3)'s Step A empirical test requires (4) to have run successfully on a Windows VM.
- (5)'s runtime warning text is shaped by (1) (the `WINDOWS` flag triggers the warning) but the deliverable is the warning + docs + CI, not platform primitives.

Named contract surfaces:
- `cortex_command.platform.lock.acquire(path, blocking=True, timeout=None) -> ContextManager` — used by Piece (1), called by `init/settings_merge.py`, `auth/bootstrap.py`, `overnight/ipc.py`, `overnight/runner.py`, `overnight/sandbox_settings.py`, `overnight/scheduler/lock.py`, `plugins/cortex-overnight/server.py`.
- `cortex_command.platform.process.spawn_detached(argv, ...)` and `signal_group(proc, sig)` — used by Pieces (1) and (2), called by `overnight/runner.py` (orchestrator + batch-runner) and `overnight/cli_handler.py`.
- `cortex_command.platform.WINDOWS: bool` — used by Pieces (1), (3), (4), (5) for thin glue and warning triggers.
- `cortex/requirements/project.md` Architectural Constraints + Quality Attributes sections — modified by Piece (5).
- `docs/setup.md` Dependencies + Notifications + Windows-troubleshooting sections — modified by Pieces (4) and (5).
- `pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` — modified by Piece (2).
- `.github/workflows/windows-smoke.yml` — created by Piece (5).

### Seam-level edges

- **(1) edges**: depends on Python stdlib (`fcntl`, `msvcrt`, `signal`, `subprocess`) and optionally `filelock` PyPI. Lands edges on every `fcntl.flock`, `start_new_session`, and `os.killpg` callsite in `cortex_command/` plus the existing `durable_fsync` in `common.py:651-670`, plus the `XDG_CACHE_HOME` resolution in `dashboard/app.py`.
- **(2) edges**: depends on (1). Lands edges on a new `cortex_command/overnight/scheduler/windows.py`, a new `launcher.ps1`, and on the build config in `pyproject.toml`. No edge to the rest of the runner.
- **(3) edges**: depends on Claude Code's hook resolver (external). Lands edges on `hooks/`, `claude/hooks/`, plus the auto-regenerated plugin mirrors. If shim-works: deletes `.sh` files and updates the hook `command:` strings in `claude/settings.json` + `plugins/cortex-core/claude-plugin/hooks/*.json`.
- **(4) edges**: depends on `uv` and Git for Windows. Lands edges on a new top-level `install.ps1`, on `docs/setup.md` Quickstart, and on the Windows-VM smoke validation step.
- **(5) edges**: depends only on (1) for the `WINDOWS` flag. Lands edges on `README.md`, `docs/setup.md`, `cortex/requirements/project.md`, `cortex_command/init/handler.py` (startup warning), `cortex_command/overnight/runner.py` startup (warning), and `.github/workflows/windows-smoke.yml`.

### Why N pieces

piece_count = 5, so the falsification gate does not fire (threshold is piece_count > 5). The earlier 7-piece set collapsed to 5 by (a) merging the prior "posture docs," "sandbox carve-out," and "CI" pieces into one Posture-surface piece because they share the `cortex/requirements/project.md` contract surface and one coherent "what does best-effort mean operationally" framing, and (b) folding the empirical W6 validation into Piece (3) and Piece (4) where the test is part of the deliverable rather than a separate piece. The Piece (1) ↔ Piece (2) split is preserved because (2)'s scheduler-specific surface (Task Scheduler XML/PowerShell registration, launcher daemonization) does not generalize back into (1)'s reusable primitives, even though (2) is currently the only Windows-port consumer of (1)'s `process` module — the contract is forward-looking.

## Decision Records

### DR-1: Architectural seam — hybrid (flag + per-subsystem package for hot spot)

- **Context**: `fcntl` does not import on Windows; the overnight runner uses it in 7 modules; the existing `durable_fsync` in `common.py:651-670` already demonstrates a macOS-conditional pattern at file scope. Other platform deltas are thin glue that Python already handles cross-platform.
- **Options considered**: A) inline `if WINDOWS:` everywhere (pipx, Poetry pattern); B) full `_windows.py`/`_posix.py` split everywhere (psutil pattern); C) hybrid — flag for glue, `cortex_command/platform/` package for runner hot spot.
- **Recommendation**: **C — hybrid.** Poetry's pattern is correct for ~80% of the cortex codebase where `pathlib` and stdlib already abstract platform; psutil's pattern is correct for the overnight runner's lock/spawn primitives where `fcntl` literally cannot import. GitPython's deprecation of its abstraction layer is direct evidence that over-abstraction has a cost when the platform delta is thin.
- **Trade-offs**: Reviewers must learn the rule "abstract when the syscall doesn't import; inline otherwise." Mitigated by a one-paragraph `cortex_command/platform/README.md` documenting the rule.

### DR-2: Sandbox-on-Windows posture — transitional warn-and-proceed

- **Context**: As of 2026-05-15, Claude Code does not enforce sandboxing on native Windows ([Setup table](https://code.claude.com/docs/en/setup): "Sandboxing: Not supported"). However, Anthropic explicitly commits to it ([Sandboxing Limitations](https://code.claude.com/docs/en/sandboxing): "Native Windows support is planned"). The gap is transitional. Today, `cortex init`'s `sandbox.filesystem.allowWrite` write is inert; once Anthropic ships, it becomes live without any cortex-side change. The cortex-side decision is what to do during the transitional window — both for `cortex init` and (more importantly) for the overnight runner, which runs with `--dangerously-skip-permissions` and currently treats the sandbox as the critical safety surface (`cortex/requirements/project.md` Quality Attributes: "Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface").
- **Options considered**:
  - A) `cortex init`: write the field anyway (no-op today, forward-compatible — chosen). Overnight runner: silent.
  - B) `cortex init`: skip the write with a notice. Overnight runner: silent.
  - C) `cortex init`: refuse on native Windows; require WSL 2.
  - D) Overnight runner: refuse to start on native Windows until Anthropic ships sandbox.
  - E) Overnight runner: drop `--dangerously-skip-permissions` on Windows (run permissioned).
  - F) **Warn loudly + proceed** (chosen): `cortex init` writes the field as forward-compatible state; both `cortex init` and overnight runner startup print a clear transitional warning on native Windows; the warning text references Anthropic's planned native-Windows-sandbox support so users understand the warning will become unnecessary.
- **Recommendation**: **F — warn loudly + proceed.** Preserves overnight autonomy now (matching the user's "personal use, all four subsystems, best-effort" stance); names the gap honestly at the surface where the exposure actually occurs (runner startup, not just init); inherits Claude Code's sandbox enforcement automatically once it ships natively. Option A's forward-compatible JSON write is preserved as part of F.
- **Trade-offs**: The runtime warning is moderately verbose; it can be silenced via `CORTEX_SUPPRESS_WINDOWS_SANDBOX_WARNING=1` for users who acknowledge the gap. The warning will become a no-op once Anthropic releases native-Windows sandbox enforcement — at that point the cortex-side change is to delete the warning emission, with no other code changes required.

### DR-3: Hook execution strategy — empirically gated within the piece

- **Context**: ~9 cortex-shipped `.sh` hooks in `hooks/` and `claude/hooks/`. Claude Code on Windows runs `command:` strings through Git Bash by default (if installed), PowerShell fallback otherwise, or `"shell": "powershell"` per-hook opt-in. The empirically open question is whether `[project.scripts]`-installed `.exe` shims (e.g. `cortex-validate-commit.exe`) work as exec-form `command:` on Windows.
- **Options considered**: A) write `.ps1` siblings for every `.sh` hook (statusline pattern); B) rewrite cortex-* hooks as Python and invoke the entry point via `command:` directly (no shell required); C) require Git for Windows and document `.sh` hooks as Git-Bash-only on Windows.
- **Recommendation**: **B if the exec-form shim test passes, A as fallback**. The test is part of Piece (3) Step A; the implementation is Piece (3) Step B. Validation cost is <1 hour on a Windows VM; implementation cost varies by outcome (B is fewer artifacts to maintain; A is more PowerShell to write). Modern wheel installers produce `.exe` stubs so B is the likely outcome.
- **Trade-offs**: Coupling validation and implementation in one piece keeps the empirical question accountable (it gets answered as part of the work, not deferred indefinitely). If both A and B turn out to have issues, fall back to C and document explicitly — but C is the highest user-friction option and should be avoided.

### DR-4: CI matrix — advisory Windows smoke under best-effort posture

- **Context**: User chose "macOS-primary, Windows best-effort." Best-effort can mean periodic manual smoke OR a minimal CI smoke job.
- **Options considered**: A) Windows CI job blocking merge (full first-class); B) Windows CI job advisory (runs on PRs but doesn't gate); C) no Windows CI; periodic manual smoke each minor release.
- **Recommendation**: **B — advisory CI job** running `cortex --version` + `cortex init --dry-run`. Lowest cost to add (free on `windows-latest` for public repos); surfaces breakage early without changing release discipline. Folded into Piece (5).
- **Trade-offs**: Test minimums are subjective. If the smoke job consistently red-flags issues that get ignored, it becomes noise. Mitigation: scope it to literally "does the wheel install and run `cortex --version`," and revisit scope after observing several runs.

## Open Questions

- **W6 empirical validation (within Piece 3 Step A)**: Do Python `[project.scripts]` console-script `.exe` shims work as Claude Code hook `command:` strings in exec form on Windows? Answered within the piece; <1 hour on a Windows VM. Determines whether Piece (3) Step B follows Path B (Python rewrite) or Path A (`.ps1` siblings).
- **W6 empirical validation (within Piece 4)**: Does `cortex init` run cleanly under `uv tool install`-installed cortex on native Windows 10/11? Answered within Piece (4); ~30 minutes on the same Windows VM session.
- **Effort sequencing**: should W1 (platform layer) and W4 (installer) ship in one release together with W5 (posture surface), or in separate releases with W2 (scheduler) lagging behind? Recommendation: W1 + W4 + W5 in one release as the "Windows port v1" milestone; W2 + W3 in a follow-up since they're the deeper subsystem work. This sequence delivers a usable interactive cortex on Windows without overnight-runner support, then adds overnight-runner support once the platform primitives have shaken out.
- **Line-number drift**: the inventory above was scanned at a snapshot tree; Reviewer B verified that some line numbers have drifted in current HEAD (`pipeline/worktree.py:199` → ~266; `plugins/cortex-overnight/server.py:280-288` ps-probe → ~479-510). Treat all line citations as approximations; verify against current HEAD before implementation. The surfaces and modules cited are accurate; only the specific line numbers may have shifted.
