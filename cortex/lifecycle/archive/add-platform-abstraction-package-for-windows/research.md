# Research: Windows platform abstraction package for cortex_command (#216)

## Epic Reference

This ticket is the first child of epic [[215-add-native-windows-host-support-for-the-agentic-harness]] (suggested-sequencing ranks it #1 alongside #218 and #219 as "Windows v1"). Epic-level discovery research lives at [`cortex/research/windows-support/research.md`](../../research/windows-support/research.md) and covers the broader port across all four Windows-support workstreams; this ticket-specific research narrows to the platform abstraction package only.

## Codebase Analysis

### Verified touch-point inventory (HEAD, 2026-05-15)

All 14 backlog touch points exist; line numbers below supersede the inventory snapshot's tilde-prefixed pointers.

| File | Verified callsite | Notes |
|------|-------------------|-------|
| `cortex_command/init/settings_merge.py` | `import fcntl` L32; `_acquire_lock` L75–85 (`os.open` POSIX flags + `fcntl.flock(LOCK_EX)`) | Imports `from cortex_command.common import atomic_write` |
| `cortex_command/init/handler.py` | `tmpdir = os.environ.get("TMPDIR", "/tmp")` L207–211 | Worktree-root sandbox-registration skip |
| `cortex_command/auth/bootstrap.py` | `import fcntl` L22; `os.open` + `fcntl.flock` L200–204; release L267 | Already imports `durable_fsync` from common L31 |
| `cortex_command/overnight/ipc.py` | `import fcntl` L18, `import psutil` L26; `_acquire_takeover_lock` L100–150 (LOCK_EX\|LOCK_NB poll, 5s budget); release L116, L292 | Defines `ConcurrentRunnerError` / `ConcurrentRunnerLockTimeoutError` |
| `cortex_command/overnight/runner.py` | `import fcntl` L24, `import signal` L27, `import psutil` L38; `os.killpg` L284, L295; `signal.signal(SIGTERM, _handle_sigterm)` L188; `start_new_session=True` L1045 + L1256; lock release L773, L787, L868; TMPDIR fallback L1444 | `os.getpgid` L823 inside `try/ProcessLookupError` |
| `cortex_command/overnight/sandbox_settings.py` | `import fcntl` L22; `record_soft_fail_event` L379–407 (`os.open` + `fcntl.flock` L381, release L405); existing `if sys.platform == "darwin":` guard L353 | Sandbox is Darwin-only by design |
| `cortex_command/overnight/scheduler/lock.py` | `import fcntl` L24; `schedule_lock` ctxmgr L98–110 (`open("a")` + `fcntl.flock` L100, release L105) | Different shape — `open("a")`+flock vs peers' `os.open`+flock |
| `cortex_command/overnight/cli_handler.py` | `import fcntl` L18, `import signal` L21; `start_new_session=True` L382; `os.killpg` L280, L292, L1124 | All wrapped in `try/except (ProcessLookupError, PermissionError, OSError)` |
| `cortex_command/overnight/runner_primitives.py` | `_SHUTDOWN_SIGNALS: tuple[int,...] = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)` L39 (private); used L184, L222 | **Module-level SIGHUP reference — fails import on Windows** |
| `cortex_command/pipeline/conflict.py` | `tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))` L122 | merge_with_repair worktree creation |
| `cortex_command/pipeline/worktree.py` | TMPDIR fallback L156; `lsof` callsite L348–360 (NOT 349–353) | Comment L348 explicitly says `(macOS: lsof)` |
| `plugins/cortex-overnight/server.py` | `import fcntl` L40, `import signal` L44; `_acquire_install_flock` L396–429; `_acquire_update_flock` L1419–1461; `ps -p <pid> -o lstart=` L498–510 | **PEP 723 venv excludes psutil per L443–446** — cannot import `cortex_command.platform` |
| `cortex_command/common.py` | `durable_fsync` L651–670 with `import fcntl` lazy-loaded inside `if sys.platform == "darwin":` L665 | 9 importers; module-level imports do NOT include `fcntl` |
| `cortex_command/dashboard/app.py` | `_resolve_pid_path` L198–213; reads `XDG_CACHE_HOME` L210; cached call L216 | Single-source-of-truth path shared across CLI dashboard verb, FastAPI app, runner liveness probe, justfile recipe |

### Existing platform-conditional patterns

The project has exactly **one** lazy-import-inside-conditional pattern (the cleanest reference for the new package):

```python
# cortex_command/common.py:665-670
if sys.platform == "darwin":
    import fcntl
    fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
else:
    os.fsync(fd)
```

Other `sys.platform`/`platform.system` sites (all macOS-conditional, none Windows-conditional):
- `cortex_command/overnight/auth.py:100` — `if platform.system() != "Darwin":` (uses stdlib `platform`)
- `cortex_command/overnight/sandbox_settings.py:97, 342, 353` — sandbox is Darwin-only
- `cortex_command/overnight/scheduler/dispatch.py:9-10, 63` — scheduler dispatch to `macos.py`
- `cortex_command/overnight/scheduler/macos.py:385` — `is_supported` returns Darwin check

**No existing `if sys.platform == "win32"` or `WINDOWS = …` constant exists.** No `try: import fcntl; except ImportError:` anywhere. No `filelock` / `portalocker` / `platformdirs` — all greenfield.

### Additional POSIX callsites missed by the inventory

**TMPDIR fallback (`os.environ.get("TMPDIR", "/tmp")`) at unlisted sites:**
- `cortex_command/overnight/plan.py:363, 426`
- `cortex_command/overnight/outcome_router.py:173`
- `cortex_command/overnight/report.py:1188` — `claude-tool-failures-{session_id}` dir
- `cortex_command/overnight/sandbox_settings.py:162` — `$TMPDIR` substitution in sandbox allowlist (different from lock callsite)
- `cortex_command/overnight/scheduler/macos.py:615` — `tmpdir = os.environ.get("TMPDIR") or "/tmp"` (different idiom — `or` not default)
- `cortex_command/pipeline/dispatch.py:543` — already uses `tempfile.gettempdir()` fallback (correct pattern)

Total ~12 TMPDIR sites, not 3. Inventory undercounted significantly.

**`os.killpg` at unlisted runner_primitives sites:**
- `cortex_command/overnight/runner_primitives.py:148, 161` — peer of runner.py and cli_handler.py

### Dual-source enforcement

`cortex_command/` itself is NOT subject to dual-source enforcement. The only Python file that IS dual-sourced today is `cortex_command/install_guard.py` → `plugins/cortex-overnight/install_guard.py` via `just sync-install-guard` (justfile L671–747). The marker block `# BEGIN sync-install-guard:check_in_flight_install_core` … `# END` defines the extracted segment; `tests/test_install_guard_parity.py` enforces at commit time.

**Implication for #216**: a new `cortex_command/platform/` package is not subject to existing dual-source enforcement. But the plugin (`plugins/cortex-overnight/server.py`) cannot import the new package because its PEP 723 venv intentionally excludes psutil — see server.py L443–446 ("plugin venv intentionally excludes psutil to keep the surface minimal"). The plugin will need its own duplicated lock helper for Windows, paralleling existing `_plugin_active_session_path` (L521–534) and `_plugin_pid_verifier` (L440–518) duplication. Whether to vendor the new package via the install_guard precedent or hand-maintain a sibling is an open spec decision.

### Naming-collision warning

`cortex_command/platform/` shadows the **stdlib `platform`** module. `cortex_command/overnight/auth.py:28` already does `import platform; platform.system()` (stdlib). Once the new subpackage exists, any future `cortex_command/foo.py` doing `import platform` resolves to the subpackage, not stdlib. Worth resolving in Spec — candidates include `_platform/` (leading underscore signals internal), `compat/`, or `sysplat/`.

### Conventions

- **Package layout**: mirrors `auth/`, `init/`, `overnight/`, `pipeline/`, `dashboard/` — directory with `__init__.py`, optional `tests/` subdir, topic-named modules.
- **`__init__.py` exports**: top-level `cortex_command/__init__.py` and most subpackages have empty `__init__.py` (no re-exports). Consumers import directly: `from cortex_command.platform.lock import file_lock`. (`common.py` is the exception with top-level functions.)
- **Type hints**: `from __future__ import annotations` + PEP 604 unions (`Path | None`), Python ≥ 3.12 per `pyproject.toml:8`.
- **Tests**: per-subsystem `tests/` subdir; pytest, invoked via `just test-<subsystem>`. New package would add `just test-platform`.
- **Exception classes**: domain-prefixed per subsystem (e.g., `SettingsMergeError`, `ConcurrentRunnerError`); no shared `cortex_command.exceptions` module. New package should define its own (e.g., `LockTimeoutError`, `UnsupportedPlatformError`).
- **Naming**: snake_case modules; `_leading_underscore` for private constants.

## Web Research

### Library decisions

**`filelock`** — de-facto cross-platform Python file-lock library (used by tox, virtualenv, pre-commit). Auto-selects `fcntl.flock` on POSIX, `msvcrt.locking` on Windows. Context-manager API with timeout. Process-level (inter-process), advisory semantics matching `fcntl.flock`. Bare `FileLock` does NOT track holder PIDs — stale-lock detection must layer separately. Same `tox-dev` org as platformdirs.

**`platformdirs.user_cache_dir(appname="cortex-command", appauthor=False, ensure_exists=True)`** — returns `~/.cache/cortex-command` (Linux, honors `XDG_CACHE_HOME`), `~/Library/Caches/cortex-command` (macOS), `%LOCALAPPDATA%\cortex-command\Cache` (Windows). ~50M downloads/week, vendored by pip. `user_runtime_dir` for runtime/lockfile state.

**`msvcrt.locking`** — stdlib but lower-level: byte-range, no timeout, mandatory (kernel-enforced) not advisory. Direct use forces hand-rolled platform-detection branches and a hand-rolled context manager. Use only if dep-minimization becomes a hard constraint.

### Detached process spawn

```python
if sys.platform == "win32":
    kwargs = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
else:
    kwargs = {"start_new_session": True}
subprocess.Popen([...], **kwargs)
```

Gotchas:
- **Console pop-up bug** ([cpython#85785](https://github.com/python/cpython/issues/85785)) — `DETACHED_PROCESS` can pop a console window. Mitigation: pass `startupinfo` with `STARTF_USESHOWWINDOW | SW_HIDE`, or `CREATE_NO_WINDOW`.
- `CREATE_NEW_PROCESS_GROUP` required for later `os.kill(pid, signal.CTRL_BREAK_EVENT)` delivery; ignored if `CREATE_NEW_CONSOLE` is also set.
- Detached children survive parent exit (no orphan-reaping needed on Windows; kernel handles cleanup).
- Need `subprocess.DEVNULL` redirects for true console detachment.

### Process-tree kill

`os.killpg` does not exist on Windows. Two substitutes:

1. **`psutil.Process(pid).children(recursive=True)` + iterate `.kill()`** — cross-platform, single implementation. Works identically POSIX/Windows. Loses POSIX's atomic-PG-signal guarantee (snapshot-then-iterate is racy on PIDs spawned during iteration). On Windows, `Process.terminate()` and `Process.kill()` are equivalent (both call `TerminateProcess`).
2. **`taskkill /F /T /PID <pid>`** (Windows-only) — subprocess shell-out, `/T` walks tree, `/F` forces.

Cortex use case (cancel overnight session + descendants) maps to option 1, but the consolidated API loses the POSIX atomicity. See Adversarial Review §4 below.

### SIGHUP on Windows

`signal.SIGHUP` is Unix-only. Bare `signal.signal(signal.SIGHUP, h)` raises `AttributeError` at attribute access — module-level reference fails import. Patterns:

```python
# Pattern A (most common)
if hasattr(signal, "SIGHUP"):
    signal.signal(signal.SIGHUP, handler)

# Pattern B
if not IS_WINDOWS:
    signal.signal(signal.SIGHUP, handler)

# Pattern C (separate _signals_posix.py / _signals_windows.py modules)
from ._signals import register_hangup_handler
```

Windows has no SIGHUP analogue. `CTRL_BREAK_EVENT` is for `os.kill()` delivery, not for `signal.signal()` registration.

### Stale-lock detection — psutil hazards on Windows

`psutil.process_iter(['open_files'])` is the cross-platform equivalent of `lsof <lockfile>`. **Windows hazards**:

- **`Process.open_files()` is documented "unsafe API" on Windows** ([psutil#1967](https://github.com/giampaolo/psutil/issues/1967)) — underlying `NtQuerySystemInformation` can hang. psutil mitigates by spawning a thread killed after 100ms; if killed mid-C-runtime-lock, can deadlock the Python process.
- **Permission**: enumerating other-user / system-process handles requires admin.
- **Performance**: 200–500ms full sweep on busy hosts.

**Recommended substitute**: store holder PID in the lockfile body at acquisition; check `psutil.pid_exists(pid)` (cheap, reliable) on stale check. Avoids `open_files()` entirely. Fallback to graceful no-op if pidfile body is empty/corrupted.

### macOS `durable_fsync` background

`os.fsync` on macOS only flushes to drive cache, not platter. The durable equivalent is `fcntl(fd, F_FULLFSYNC)`. Tracked at [bpo-3512](https://bugs.python.org/issue3512) / [Discuss #79332](https://discuss.python.org/t/call-f-fullfsync-in-os-fsync-for-macos/79332). RocksDB and SQLite ship explicit `F_FULLFSYNC` calls. Linux `fsync` is platter-durable; Windows `os.fsync` calls `_commit` → `FlushFileBuffers` (durable). So `durable_fsync` only needs to branch macOS:

```python
def durable_fsync(fd):
    if sys.platform == "darwin":
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)
```

Fits naturally in the `_posix.py` side of the package split.

### Hybrid pattern survey

| Surface | Pattern | Example |
|---|---|---|
| Single callsite, 1–2 lines | Inline `if IS_WINDOWS:` | pip vendored compat shims |
| Several related calls, same domain | Single `_compat.py` with branches inside each function | most pypa code |
| Substantial platform-specific implementation | `_posix.py` + `_windows.py` modules; `__init__.py` selects at import time | watchdog observers, virtualenv creators, CPython's `os.py` (`from posix import *` / `from nt import *`) |

Six primitives put cortex on the boundary; watchdog-style split is cleanest.

### Platform detection idiom

`sys.platform == "win32"` (or `os.name == "nt"`) is the established constant. Preferred over `platform.system()` because no shell-out and known at interpreter-build time. `sys.platform == "darwin"` for macOS branch.

## Requirements & Constraints

### Cross-platform support

The only explicit platform statements are scoped to subsystems, NOT the framework as a whole:

- `remote-access.md:41` — "macOS is the primary and only supported platform for session persistence (Ghostty dependency). Linux/Windows are not supported."
- `pipeline.md:28` — "The `schedule` verb is macOS-only (LaunchAgent backend; non-darwin invocations exit with a 'scheduling requires macOS' error)."

`project.md` Overview describes cortex as an "Agentic workflow toolkit for AI-assisted software development on Claude Code" with no platform restriction. **Requirements are silent on whether the framework as a whole supports Windows.**

### File-based state architecture

`project.md:27` — "**File-based state**: Lifecycle, backlog, pipeline, sessions in plain files (markdown/JSON/YAML). No database."

`project.md:28` — "`cortex init` additively adds the repo's `cortex/` umbrella to `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite` — the only write cortex-command makes in `~/.claude/`. `fcntl.flock` serialized."

`pipeline.md:134` — "**State file locking**: State file reads are not protected by locks by design. Writers use atomic `os.replace()`; readers may observe a state mid-mutation, but forward-only transitions make this safe. This is a permanent architectural constraint."

`pipeline.md:157` — "`~/.cache/cortex-command/scheduled-launches.lock` — companion `fcntl.LOCK_EX` lockfile held across the GC + plist install + `launchctl bootstrap` + verify + sidecar-write critical section to serialize concurrent `cortex overnight schedule` invocations."

Locking is named in two places (`project.md:28`, `pipeline.md:157`), both via `fcntl` (POSIX-only). Requirements are silent on whether locking must be POSIX-specific or could be abstracted.

### Sandbox / file-mode invariants

`project.md:28` (additive merge + `fcntl.flock` serialization).

`observability.md:87` — "`settings.local.json` arrays replace (not merge with) `settings.json` arrays."

`pipeline.md:151` — `runner.pid` envelope schema (`{schema_version, magic, pid, pgid, start_time, session_id, session_dir, repo_path}`, **mode 0o600**, atomic write). The `pgid` field implies process-group signalling; `mode 0o600` assumes POSIX file-mode semantics.

`pipeline.md:158` — per-spawn sandbox-settings tempfiles also `mode 0o600`.

### Skill-helper rule does NOT apply

`project.md:31` — "**Skill-helper modules**: when a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry. Promoted modules expose a `[project.scripts]` console-script entry…"

Scoped to skill-helper modules backing SKILL.md dispatches. **A pure platform-abstraction package is not a skill-helper** and doesn't need a `[project.scripts]` entry. Requirements are silent on layout for non-skill internal packages, though `cortex_command/overnight/`, `cortex_command/pipeline/`, etc. set the established precedent.

### CLI/plugin version contract

`project.md:32` — "The cortex CLI wheel and the cortex-overnight plugin ship via independent channels … They couple through (a) `plugins/cortex-overnight/server.py`'s `CLI_PIN` tuple and (b) the `cortex --print-root --format json` envelope's `version` (PEP 440) and `schema_version` (M.m floor) fields. Schema-floor majors are forever-public-API."

**Implication**: anything the platform package exposes through the JSON envelope or that becomes part of the CLI_PIN-coupled surface is forever-public-API. If the package is purely internal (called only by `cortex_command.*` modules and not surfaced through the JSON envelope), it doesn't interact with the contract.

### Maintainability + Solution horizon

`project.md:19` — "**Complexity**: Must earn its place by solving a real problem now. When in doubt, simpler wins."

`project.md:21` — "Before suggesting a fix, ask: do I already know this needs redoing (follow-up planned, **patch applies in multiple known places**, sidesteps a known constraint)? If yes, propose the durable version or surface both with tradeoff."

The "patch applies in multiple known places" trigger directly applies to consolidating per-callsite `sys.platform` branching.

`project.md:37` — "**Maintainability through simplicity**: Complexity is managed by iteratively trimming skills/workflows."

### Defense-in-depth + Windows-permissions silence

`project.md:39` — "**Defense-in-depth for permissions**: `settings.json` ships minimal allow, comprehensive deny, sandbox on. … Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface."

**Requirements are silent on Windows-specific permissions** (NTFS ACLs, file-mode equivalents). The `mode 0o600` constraints assume POSIX semantics with no documented Windows analogue.

### Project boundaries

`project.md:42–56` — In Scope: workflow orchestration, overnight execution, dashboard, conflict resolution pipeline, remote access, multi-agent, observability. Out of Scope: dotfiles/machine-config, application code, "Published packages or reusable modules for others — out of scope; cortex ships as a non-editable wheel."

Internal infrastructure (the new platform package) stays in scope. Whether Windows itself is in scope is unstated — neither in In Scope nor Out of Scope.

### Silent areas (relevant to spec)

1. Framework-wide cross-platform support stance.
2. Whether locking must be POSIX-specific or may be abstracted.
3. Third-party dependency policy (no general rule on adding `platformdirs`, `filelock`).
4. Package layout for non-skill internal packages.
5. Signal-handling primitives (`start_new_session`, `killpg`, `SIGHUP` are not named in requirements).
6. Windows-specific permissions / NTFS ACLs.
7. Whether Windows is in or out of scope.

## Tradeoffs & Alternatives

### Architecture: hybrid (A) vs all-in-one (B) vs per-callsite try/except (C) vs vendored compat shim (D)

| Option | Implementation complexity | Maintainability | Performance | Pattern alignment | Verdict |
|---|---|---|---|---|---|
| **A. Hybrid `cortex_command/platform/` package + `WINDOWS` flag in `common.py`** | Medium — two layered patterns, each matches existing precedent (`durable_fsync` macOS conditional + watchdog-style backend split) | High — hot syscalls in canonical `_posix.py`/`_windows.py`; thin glue stays at callsite | Negligible (constant-time check) | Strongest — research artifact line 7 explicitly names this | **Recommended** |
| **B. All-in-one `cortex_command/platform.py`** | Lowest initial; degrades as primitives accrete | Worst as size grows; mixes concerns | Identical to A | Diverges from psutil precedent | Reject |
| **C. Per-callsite try/except ImportError** | Lowest per site, highest aggregate (14 reimplementations of the same shim that drift) | Worst — 14-way decision instead of 1 | Identical | Anti-pattern relative to `durable_fsync` | Reject |
| **D. Vendored compat layer (monkey-patch `fcntl`/`signal` to be importable)** | Hidden moderate — forked stdlib surface | Worst — silent no-op locks dangerous; semantics hidden behind name | Identical | Contradicts "prescribe What and Why" | Reject |

### Lock backend: filelock-only vs filelock-on-Windows + raw-fcntl-on-POSIX vs msvcrt vs portalocker

| Option | Notes | Verdict |
|---|---|---|
| **1. `filelock` everywhere (Windows + POSIX)** | One library, one set of edge cases, one upstream to track for CVEs. POSIX backend wraps `fcntl.flock` with same advisory semantics — no semantic loss. Adversarial review §11 favors this. | **Recommended (per Adversarial)** |
| **2. `portalocker`** | Smaller community than filelock. Equivalent feature set. No reason to prefer over filelock. | Reject |
| **3. `msvcrt.locking` (stdlib only on Windows)** | Saves one dep but trades for ongoing semantic maintenance (byte-range, mandatory, no timeout). | Reject unless dep-minimization becomes a hard constraint |
| **4. filelock-on-Windows + raw-fcntl-on-POSIX** | Tradeoffs agent originally recommended this for "preserves POSIX behavior exactly." Adversarial counter: path-dependence, not engineering — these locks aren't hot paths. | Lose to option 1 after Adversarial review |

### Stale-lock detection: psutil-iterate (α) vs no-op (β) vs sidecar pidfile (γ)

| Option | Notes | Verdict |
|---|---|---|
| **α. `psutil.process_iter(['open_files'])`** | Closest functional parity to `lsof`. **Documented unsafe on Windows (psutil#1967, can deadlock Python).** Permission-restricted. 200–500ms full sweep. | Reject for Windows path |
| **β. Graceful no-op on Windows** | Trivial. Loses safety net but matches "best-effort" framing. Hung Windows process holding lock requires manual cleanup. | Acceptable initial Windows posture |
| **γ. Sidecar pidfile written at acquisition** | Cheapest stale check (file read + `psutil.pid_exists`). Cross-platform single code path. Mild scope creep — changes POSIX acquire contract. **Adversarial flagged race conditions (PID recycling, atomic-write window).** | **Recommended with explicit race-handling, β as fallback** |

### Cache-dir: platformdirs (i) vs inline conditional (ii)

| Option | Notes | Verdict |
|---|---|---|
| **i. `platformdirs`** | Lowest callsite complexity. ~50M downloads/week. Survives future OS conventions. Replaces dashboard's hand-rolled `_resolve_pid_path`. | **Recommended** |
| **ii. Inline three-way conditional** | Spreads logic across consumers; drift-prone. Saves ~30KB dep at the cost of every future change being multi-file. | Reject |

### Contract-surface design

- **`acquire_lock` as context manager** — every existing callsite already uses try/finally; context-manager collapses boilerplate. Raise project-defined `LockTimeoutError`, callers translate to domain exceptions.
- **Stale-lock detection: explicit, separate function** — `find_stale_lock_holder(path) -> int | None` standalone. Cleanup is policy not mechanism; only the worktree-recovery path wants it. Burying it inside `acquire_lock` would be wrong for the schedule lock that expects to wait.
- **`spawn_detached` API** — Adversarial §4 challenges the "single `.kill_tree(timeout)`" recommendation as quietly weakening POSIX's atomic-PG-signal guarantee. Counter-recommendation: expose distinct `terminate_process_group(pgid)` (POSIX-only) and `terminate_process_tree(pid)` (cross-platform via psutil). Preserve the runner's distinct inner (DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS=6s) and outer (12s SIGKILL) budgets — do not collapse them into one timeout knob.

## Adversarial Review

The 5th-agent adversarial pass surfaced **10 substantive concerns** that the spec must address. Summarized; see `## Open Questions` for the spec-blocking decisions.

1. **Selectively-uniform contract**: `plugins/cortex-overnight/server.py` runs in a PEP 723 venv that excludes psutil → cannot import `cortex_command.platform`. Has 4 duplicated lock helpers today (`_acquire_install_flock`, `_acquire_update_flock`, `_plugin_pid_verifier`, plus L1644). Without applying the `install_guard`-style byte-identical vendoring or accepting hand-maintained drift, the package's "uniform contract" silently sets up multi-year drift between CLI and plugin.
2. **Naming collision is not theoretical**: `cortex_command/overnight/auth.py:28` already does `import platform` (stdlib). Once `cortex_command/platform/` exists, future `import platform` in any `cortex_command/foo.py` resolves to the subpackage. Rename to `_platform/`, `compat/`, or `sysplat/` before code lands.
3. **Sidecar pidfile races**: (a) holder writes PID, gets flock, crashes 10ms later → next acquirer sees stale PID (potentially recycled). (b) Cannot atomically write PID body under same flock without a window where another process sees an empty body. (c) flock is advisory — a process ignoring the flock and reading the body sees mid-write bytes. Existing `verify_runner_pid` uses `psutil.create_time` ±2s tolerance to mitigate the recycle problem; sidecar-only loses that mitigation.
4. **`.kill_tree(timeout=...)` over-promises**: `os.killpg` is a single atomic-delivery syscall reaching mid-fork processes; psutil's snapshot-then-iterate is racy. `runner.py:107-157` already uses psutil's recursive children walk on macOS as a *complement* to killpg, not a replacement (comment notes psutil reaches grandchildren killpg cannot signal). Consolidating into one `.kill_tree()` API forces a choice that drops one of the two semantics. The runner's distinct 6s/12s budgets (per critical-review tuning) get erased into one timeout knob.
5. **TMPDIR sites have three semantic classes**: (a) `pipeline/dispatch.py:543` already uses correct `tempfile.gettempdir()` pattern. (b) Most use `Path(os.environ.get("TMPDIR", "/tmp"))` — hardcoded `/tmp` is wrong on Windows even with WINDOWS flag. (c) `sandbox_settings.py:162` substitutes `$TMPDIR` into a literal-prefix-match allowlist — needs concrete expanded path. The right fix is mechanical: replace every `os.environ.get("TMPDIR", "/tmp")` with `tempfile.gettempdir()` (already honors `TMPDIR` on POSIX, `%TEMP%` on Windows). The WINDOWS flag is unnecessary at these sites.
6. **`psutil>=5.9` floor is a Windows liability**: 5.9.x had Windows-specific bugs (Process.open_files unsafe per #1967, performance regressions, signed-installer issues fixed in 6.x). Bump to `psutil>=6.0` and validate against existing `wait_procs` (runner.py:148) and `create_time` (ipc.py:431) callsites that have had behavior changes 5→6.
7. **SIGHUP at module load is a latent crash**: `runner_primitives.py:39` declares `_SHUTDOWN_SIGNALS = (SIGINT, SIGTERM, SIGHUP)` at module top-level. `from cortex_command.overnight import runner_primitives` raises AttributeError at import on Windows, before any platform-discriminator can run. Order of work matters: (a) audit and gate every module-level `signal.SIG*` reference, (b) audit every module-level `import fcntl`, (c) **then** introduce the package.
8. **README-only enforcement is performative**: CLAUDE.md says "Prefer structural separation over prose-only enforcement." A README that says "use WINDOWS for inline glue, package for hot syscalls" enforces nothing. Recommended: a CI lint that fails when `if WINDOWS:` or `sys.platform == "win"` appears outside the package directory and a documented inline-glue allowlist.
9. **Test-surface gap**: `_posix.py`/`_windows.py` split lets you import-substitute on macOS, but cannot execute Windows code paths without a Windows host. `validate.yml:9` is `runs-on: ubuntu-latest` (single-OS). Adding Windows CI is a multi-week project of its own (path separators in tests, line endings, shell differences, the `bash`-rooted launcher ecosystem). The ticket as scoped does not acknowledge this hidden cost.
10. **install_guard precedent vs the README's "plugins keep duplicated helpers" rule**: `cortex_command/install_guard.py` ↔ `plugins/cortex-overnight/install_guard.py` is byte-identically vendored via `.githooks/pre-commit` + `just sync-install-guard` for *exactly* the reason the new platform package exists (plugin venv can't import psutil). Either the platform package follows that precedent (vendored byte-identically into plugin) or the plugin keeps a sibling (in which case install_guard's vendoring becomes the *exception*).

### Security concerns

- **NTFS ACLs**: `mode 0o600` is a no-op on Windows. The `runner.pid` file is read by `install_guard` to decide whether to block reinstall — on Windows it lands with default ACLs (typically Users-readable), allowing a non-admin local user to read it and potentially modify it to bypass the guard. Mitigation: use `pywin32` to set explicit ACLs (Windows-only dep), OR document "Windows file permissions are advisory; do not run cortex on a shared Windows host."

### Assumptions that may not hold

- **psutil API is "cross-platform"**: it is *mostly* cross-platform but `Process.children(recursive=True)` is much slower on Windows; `Process.create_time()` returns different epoch precision. The `±2s tolerance` at `ipc.py:_START_TIME_TOLERANCE_SECONDS` may need to widen for Windows. Cross-cutting because that constant is vendored byte-identically into the plugin.
- **Windows users want `~/.local/share/overnight-sessions/active-session.json`**: install_guard hardcodes `Path.home() / ".local" / "share" / ...`. On Windows this resolves to `C:\Users\name\.local\share\...` which is non-idiomatic. platformdirs migration would change this — but the install_guard's vendored copy in the plugin must migrate in lockstep, OR the plugin keeps the legacy path and they diverge.
- **PEP 723 venv constraint is permanent**: server.py:443-446 deliberately excludes psutil. If the team revisits that constraint (because the platform package's value justifies it), several concerns dissolve. Worth surfacing as an explicit decision rather than implicit constraint.

## Open Questions

These are spec-blocking decisions that must be resolved before Plan can produce concrete tasks. Each is either (a) a substantive design choice with no clear right answer, or (b) a scope decision that materially changes the ticket's size.

1. **Package name** (resolves naming collision with stdlib `platform`): one of `cortex_command/_platform/` (leading-underscore = internal), `cortex_command/compat/`, `cortex_command/sysplat/`, `cortex_command/platsupport/`. Recommend `_platform/` for minimal cognitive load (still says "platform"; underscore signals internal).

2. **Plugin-venv duplication strategy**: extend the `install_guard` byte-identical-vendoring precedent (apply `just sync-install-guard`-style enforcement to the new package's lock helper), OR accept hand-maintained sibling in `plugins/cortex-overnight/server.py` (with documented "do not import" comment). The first is more work but eliminates drift; the second is less work but risks multi-year drift between CLI and plugin Windows behavior.

3. **Lock backend**: `filelock` everywhere (one library, one test surface, Adversarial-recommended) OR dual-backend (`filelock` on Windows, raw `fcntl` on POSIX, Tradeoffs-recommended). The filelock-everywhere path simplifies but requires migrating 7 existing `fcntl.flock` callsites to the new context-manager API even on POSIX.

4. **Stale-lock detection on Windows**: graceful no-op (β, lowest-risk initial Windows posture, accepts manual cleanup of hung locks) OR sidecar pidfile + `psutil.pid_exists` (γ, cross-platform single code path with race-handling required). γ is more work and the Adversarial agent flagged real PID-recycle and atomic-write races; β preserves the existing POSIX `lsof` path and only short-circuits on Windows.

5. **`spawn_detached` API**: single `.kill_tree(timeout=...)` API (Tradeoffs-recommended, Adversarial-rejected) OR distinct `terminate_process_group()` (POSIX-only) and `terminate_process_tree()` (cross-platform via psutil) preserving runner's existing 6s/12s budgets. The latter requires more code on the consumer side but preserves the killpg atomicity guarantee that critical-review tuning depends on.

6. **TMPDIR sweep scope**: include the mechanical replacement of all `os.environ.get("TMPDIR", "/tmp")` sites with `tempfile.gettempdir()` in this ticket (~12 sites, eliminates ~10 of them from needing the WINDOWS flag) OR defer to a separate prerequisite ticket that lands before the platform package. Doing it here keeps the work atomic; deferring keeps this ticket smaller.

7. **Module-level POSIX-import sweep scope**: include the audit and gating of every module-level `signal.SIGHUP` and `import fcntl` reference (so `from cortex_command.overnight import runner_primitives` doesn't crash on Windows import) in this ticket OR defer to a prerequisite ticket. The Adversarial agent argued the order must be (a) sweep imports, (b) introduce package — doing them out of order means the package itself is unimportable on Windows.

8. **Windows CI matrix**: include adding `windows-latest` to `validate.yml:9`'s job matrix in this ticket (multi-week effort: path separators, line endings, bash launcher rewrites) OR explicitly defer to a separate ticket and accept that this ticket lands without Windows execution evidence. The latter is the lower-risk near-term path; it pushes the "does it actually work?" verification to a follow-up but lets this ticket land without blocking on CI infrastructure.

9. **Windows file ACLs**: add `pywin32` dependency and set explicit owner-only ACLs on lock and pid files (Windows-only dep, parity with POSIX `0o600`) OR document "Windows file permissions are advisory; cortex assumes single-user host" in `cortex/requirements/project.md` (and `security-review` skill expectations need updating).

10. **psutil floor bump**: bump `psutil>=5.9` → `psutil>=6.0` in this ticket (validates against existing `wait_procs` and `create_time` callsites), noting that 5.9.x had Windows-specific bugs the platform package's Windows path would inherit.

## Considerations Addressed

(No `research-considerations` were passed because no Apply'd alignment findings emerged from clarify-critic — all 6 critic findings were dispositioned Dismiss.)
