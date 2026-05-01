# Research: Fix runner.pid takeover race in ipc.py:write_runner_pid

## Codebase Analysis

### Files that will change
- **Primary**: `cortex_command/overnight/ipc.py` — `write_runner_pid` lines 140–212; the unlink-and-retry block at lines 192–212 is the bug surface.
- **Tests**: `tests/test_runner_concurrent_start_race.py` — remove `xfail` from `test_two_starters_with_stale_preexisting_lock` (lines 155–198); add stress-loop coverage.
- **Dev deps**: `pyproject.toml` — add `pytest-repeat` to dev dependencies.
- **Possibly extended scope** (decided in Spec, see Open Questions): callers of `clear_runner_pid` at `runner.py:540, 581, 1536` and `cli_handler.py:434, 456`.

### Bug surface (verbatim quote, ipc.py:192–212)
```python
# Stale claim — unlink and retry exactly once.
try:
    path.unlink()
except FileNotFoundError:
    pass

try:
    _exclusive_create_runner_pid(path, payload)
    return
except FileExistsError:
    # A third party beat us to the recreated claim. Treat as alive
    # race-loser to break the loop deterministically.
    existing = read_runner_pid(session_dir)
    if existing is not None:
        verify_runner_pid(existing)
        existing_session_id = existing.get("session_id", session_id)
        existing_pid = existing.get("pid", -1)
    else:
        existing_session_id = session_id
        existing_pid = -1
    raise ConcurrentRunnerError(existing_session_id, existing_pid)
```

The unconditional `path.unlink()` at line 194 has no compare-and-swap on file content. Two threads both reading stale content can each unlink the other's just-created live claim.

### Constants and module layout
- `ipc.py:52–55`: `_RUNNER_MAGIC = "cortex-runner-v1"`, `_SCHEMA_VERSION = 1`, `MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION = 1`, `_START_TIME_TOLERANCE_SECONDS = 2.0`.
- `ipc.py:107–138`: `_exclusive_create_runner_pid(path, payload) -> None` — canonical `O_CREAT|O_EXCL` create with mode 0o600.
- `ipc.py:215–217`: `clear_runner_pid` — unconditional unlink (no lock).
- `ipc.py:220–228`: `read_runner_pid` — `path.exists()` then `read_text` (TOCTOU but `OSError` caught → returns None).
- `ipc.py:231–276`: `verify_runner_pid` — magic, schema version, `psutil.Process(pid).create_time()` ±2s tolerance.
- `ipc.py:66–101`: `_atomic_write_json(path, payload, mode=0o600)` — `tempfile.NamedTemporaryFile` + `durable_fsync` + `os.replace` + `os.chmod`.

### Full call-site map
- **`write_runner_pid`**: `runner.py:626` only (inside `_start_session`, wrapped in `deferred_signals` context per `runner.py:625`).
- **`read_runner_pid`**: `runner.py:575` (`_check_concurrent_start`); `cli_handler.py:178` (handle_start pre-flight); `cli_handler.py:427` (handle_cancel); plus `ipc.py:186, 204` internal.
- **`clear_runner_pid`**: `runner.py:540` (interrupt-recovery), `runner.py:581` (pre-`write_runner_pid` self-heal in `_check_concurrent_start`), `runner.py:1536` (session-exit cleanup); `cli_handler.py:434, 456` (cancel paths).
- **`verify_runner_pid`**: `runner.py:578`; `cli_handler.py:181, 431`; `install_guard.py:209` (pre-install in-flight guard); plus `ipc.py:187, 206` internal.

### Existing locking primitives in the repo (load-bearing precedent)
- **`fcntl.flock` on a sibling lockfile** is already an established pattern:
  - `cortex_command/init/settings_merge.py:69–85` — `_acquire_lock(home)`: `os.open(lockfile, O_RDWR|O_CREAT, 0o600)` → `fcntl.flock(fd, fcntl.LOCK_EX)` (blocking, no timeout) → returns fd → caller releases via `flock(LOCK_UN)` + `os.close(fd)`. **Docstring rationale (lines 8–15)**: the locked file must be a sibling that survives `os.replace()` of the target — flock on the target itself would lock the new inode after replace, defeating serialization. The lockfile inode is stable; the target inode is replaced.
  - `plugins/cortex-overnight-integration/server.py:655–697` — `_acquire_update_flock(lock_path)`: non-blocking polling variant with 30s budget, catches `EWOULDBLOCK/EAGAIN` and sleeps before retry. Returns fd or None on timeout.
- **`O_CREAT|O_EXCL`** is the existing pattern in `ipc.py:_exclusive_create_runner_pid` for single-shot create; correct primitive for that operation shape.
- **No `compare-and-swap on content`** pattern exists in the repo. The unconditional unlink in the takeover path is unique.
- **Sibling `*.lock` naming** is the established convention (e.g. `.git/cortex-update.lock`, `.settings.local.json.lock`).

### Existing race tests
- `tests/test_runner_concurrent_start_race.py`:
  - `pytestmark = pytest.mark.serial` (line 37) — serialized against subprocess-spawning suites.
  - `test_two_starters_no_preexisting_lock` (lines 126–153) — passes reliably.
  - `test_two_starters_with_stale_preexisting_lock` (lines 155–198) — `@pytest.mark.xfail(reason='runner.pid takeover race — see backlog ticket 149', strict=False)`. Flakes ~20% on macOS per the ticket; Linux behavior not characterized.
  - `test_starter_against_alive_lock` (lines 200–228) — passes reliably.
- Other `runner.pid` tests: `tests/test_ipc_verify_runner_pid.py`; `tests/test_cortex_overnight_security.py:123–182`.

### Test infrastructure
- **`pytest-repeat` is NOT installed**. Stress-test target ("1000/1000 in pytest-repeat") requires adding it to `pyproject.toml` dev deps.
- **No platform-test harness** for macOS vs Linux (only `skipif sys.platform == "win32"` markers on bash-only tests).

### Atomic-write helpers
- `cortex_command/common.py:atomic_write` (lines 427–467): `tempfile.mkstemp` + `durable_fsync` + `os.replace`. No chmod (mkstemp default 0o600).
- `durable_fsync` (`common.py:401–420`): calls `fcntl.fcntl(fd, F_FULLFSYNC)` on macOS, `os.fsync(fd)` elsewhere.

## Web Research

### `fcntl.flock` vs `fcntl.fcntl(F_SETLK)` / `lockf` semantics
- **Lock owner association**: `flock()` locks attach to the open file description (kernel `struct file`); `fcntl()`/`lockf()` POSIX record locks attach to `(pid, inode)`. Closing **any** FD on a locked inode releases ALL fcntl locks — major footgun. ([apenwarr](https://apenwarr.ca/log/20101213), [gavv.net](https://gavv.net/articles/file-locks/))
- **Fork inheritance**: flock is inherited (both processes hold lock); fcntl/lockf is NOT.
- **Both auto-release on process death** — kernel-managed cleanup is the load-bearing property. ([pidlockfile PyPI](https://pypi.org/project/pidlockfile/))
- **NFS / exotic FS**: macOS `flock()` doesn't work on NFS; macOS `fcntl()` doesn't work on SMB. "There is no locking method that works reliably on all remote filesystems." ([apenwarr](https://apenwarr.ca/log/20101213))
- **Python docs' single comparative recommendation**: "the structure lay-out for the _lockdata_ variable is system dependent — therefore using the `flock()` call may be better." ([Python docs](https://docs.python.org/3/library/fcntl.html))
- **OFD locks (`F_OFD_SETLK`)**: Linux-only since 3.15; not portable to macOS. ([LWN](https://lwn.net/Articles/640404/))
- **Solaris-specific footgun**: on Solaris, `flock()` is emulated via `fcntl()`, so opening-and-closing the locked file silently drops the lock. Not relevant for cortex's macOS+Linux runners. ([infinitesque](https://infinitesque.net/articles/2010/on%20Python%20flock/))

### Compare-and-swap unlink patterns
- **No widely-cited stdlib idiom** for "verify file content, then atomically unlink only if content matches." Canonical advice is to **avoid the unlink-then-recreate sequence entirely** ([Guido Flohr, "Never Delete Your PID File!"](https://www.guido-flohr.net/never-delete-your-pid-file/), via search excerpt).
- **`linkat()` + `O_TMPFILE`** is the modern atomic-create primitive but is Linux-only.

### PID-file takeover patterns in process managers
- **systemd**: PIDFile handling is described by maintainers as "pretty close to black magic" and "still racy in many ways"; modern guidance is that PIDFiles are legacy for `Type=simple` and should only be used by `Type=forking` daemons. ([systemd#7816](https://github.com/systemd/systemd/pull/7816))
- **daemontools / runit / s6**: avoid the takeover problem by NOT using pidfiles for IPC/identity — process identity is held by the supervisor itself. ([s6 rationale](https://skarnet.org/software/s6/why.html))
- **`trbs/pid` (Python)**: holds an `fcntl` lock on the pidfile for the **entire critical section** (open `"a+"` → `_flock()` → check staleness → truncate → write). Lock-then-check ordering eliminates TOCTOU because no other process can be inside the critical section at the same time. ([trbs/pid](https://github.com/trbs/pid))
- **`pidlockfile`**: replaced predecessor specifically because the original used existence-checking advisory semantics that couldn't detect a server crash; the replacement uses `fcntl` so kernel auto-release on death does the takeover.

### Atomic rename for lock acquisition — known races
- `rename()` is atomic on the same local filesystem. NFS atomicity is filesystem-dependent.
- **flufl.lock** is the canonical Python rename/link CAS pattern: `link()` + stat-check-link-count-equals-2 for NFS-tolerance. Critical disclaimer: "Ultimately, even if [the touch optimization] fails, the lock is still guaranteed to be acquired by only one process, because the link creation operation is guaranteed to be atomic by POSIX." The atomicity of the final `link()` — not the touch — is what enforces single-winner. ([flufllock theory](https://flufllock.readthedocs.io/en/stable/theory.html))

### macOS-specific concerns
- Old macOS `fcntl()` mutex bug (per apenwarr) is fixed in current builds. Local-FS fcntl/flock are reliable on APFS.
- macOS `fcntl()` doesn't work on SMB; `flock()` doesn't work on NFS.
- APFS-specific issues exist for `F_PREALLOCATE` (irrelevant) and possibly lock-contention slowdowns under heavy concurrent load.
- APFS `rename()` atomicity is not authoritatively documented by Apple — flagged as "well-known but uncited."

### Anti-patterns identified
1. **Unlink-then-recreate the pidfile** — the exact bug.
2. **Holding `fcntl` locks across libc calls that touch the same inode** — silent lock loss.
3. **Trusting `O_EXCL` on NFS** — broken pre-NFSv3/Linux 2.6.
4. **Pre-checking with `stat()/exists()` before `unlink()`** — redundant + racy; idiomatic alternative is unlink-and-rescue-`ENOENT`.

### Sources
[apenwarr — file locking](https://apenwarr.ca/log/20101213) · [gavv.net — file locks in Linux](https://gavv.net/articles/file-locks/) · [Python fcntl docs](https://docs.python.org/3/library/fcntl.html) · [flufllock theory](https://flufllock.readthedocs.io/en/stable/theory.html) · [trbs/pid](https://github.com/trbs/pid) · [pidlockfile PyPI](https://pypi.org/project/pidlockfile/) · [Apple Developer Forums — file exclusive access](https://developer.apple.com/forums/thread/709905) · [systemd PIDFile discussion #7816](https://github.com/systemd/systemd/pull/7816) · [PEP 475 — EINTR retry](https://peps.python.org/pep-0475/)

## Requirements & Constraints

### `runner.pid` IPC contract (verbatim, `requirements/pipeline.md:151`)
> `lifecycle/sessions/{session_id}/runner.pid` — per-session IPC contract (JSON `{schema_version, magic, pid, pgid, start_time, session_id, session_dir, repo_path}`, mode 0o600, atomic write). Cleared on clean shutdown; cancel verifies magic + start_time (±2s via psutil) before signalling to close the PID-reuse race. Stable contract for the MCP control plane (versioned runner IPC).

### Distinction: PID-reuse race vs. takeover race
- The `magic + start_time` ±2s check (in `verify_runner_pid`) closes the **PID-reuse race** — a recycled PID claimed by an unrelated process.
- The **takeover race** addressed by this ticket is distinct: two concurrent `cortex overnight start` invocations both claim the same `runner.pid` while a stale entry exists. The existing check does not prevent it.

### `fcntl.flock` precedent (verbatim, `requirements/project.md:26`)
> `cortex init` additively registers the repo's `lifecycle/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. This is the only write cortex-command performs inside `~/.claude/`; it is serialized across concurrent invocations via `fcntl.flock` on a sibling lockfile.

The requirements document `fcntl.flock + sibling lockfile` as load-bearing precedent for read-modify-replace operations where the target inode is swapped. No constraint forbids using flock elsewhere.

### MCP control plane backwards-compat
- `runner.pid` schema is versioned (`_SCHEMA_VERSION = 1`); `verify_runner_pid` enforces `1 ≤ schema_version ≤ MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION`. Format must remain compatible or version must increment.
- `cortex mcp-server` is stateless; reads filesystem-grounded state. Atomicity guarantees are load-bearing.

### State-file locking (verbatim, `requirements/pipeline.md:127, 134`)
> **Concurrency safety**: State file reads are not protected by locks; the forward-only phase transition model ensures re-reading a new state is safe (idempotent transitions). [...] **State file locking**: State file reads are not protected by locks by design. Writers use atomic `os.replace()`; readers may observe a state mid-mutation, but forward-only transitions make this safe. This is a permanent architectural constraint.

This applies to the forward-only state machine (`overnight-state.json`), NOT to `runner.pid`. `runner.pid` is a **claim**, not a state transition.

### Pre-install in-flight guard (verbatim, `requirements/pipeline.md:154`)
> Pre-install in-flight guard: `cortex` aborts when an active overnight session is detected (phase != `complete` AND `verify_runner_pid` succeeds); bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export). Carve-outs: pytest, runner-spawned children (`CORTEX_RUNNER_CHILD=1`), dashboard, cancel-force invocation.

The fix must not weaken `verify_runner_pid` such that a stale claim passes verification.

### Silent on
- Takeover-path-only vs repo-wide scope.
- Sidecar lock files in `session_dir` (no prohibition; pattern of session-dir files is established).
- Cross-platform macOS-vs-Linux flock test harness.
- Stress-test infrastructure mandate (e.g., pytest-repeat).
- Filesystem type for `lifecycle/sessions/` (NFS/exotic-FS support is undocumented).

## Tradeoffs & Alternatives

### Alternative A — Takeover-lock O_EXCL sidecar
Wrap unlink-then-recreate with `O_CREAT|O_EXCL` on `runner.pid.takeover`.
- **Implementation**: ~15 LOC. Same primitive as `_exclusive_create_runner_pid`.
- **Maintainability**: **POOR.** Process death (SIGKILL, OOM, kernel panic) inside the critical section leaks the sidecar. Future starts cannot take over until manual cleanup. Trades one stale-state hazard (stale `runner.pid`) for another (stale sidecar) with worse recovery semantics.
- **Regression coverage**: closes Thread A/B but introduces stale-lock-leak-at-fixed-path — explicitly the regression mode the ticket flags as unacceptable.
- **Verdict**: rejected.

### Alternative B — Rename CAS (`os.rename(path, unique_marker)`)
Replace `path.unlink()` with `os.rename(path, ...)`; only one starter wins.
- **Implementation**: ~10 LOC.
- **Maintainability**: **FAILS.** Verify-then-rename window means thread C can write a live claim between A's verify-stale and A's rename. A's rename atomically takes over a live claim — silent corruption. No `FileExistsError` to alert on.
- **Verdict**: strictly worse than the current race. Rejected.

### Alternative C — Rename + verify-after-take + restore
Like B, plus re-verify after rename and restore via rename-back if we took a live claim.
- **Implementation**: ~30 LOC, two error-recovery branches.
- **Maintainability**: **FAILS.** Restore is itself a TOCTOU; restore-failure path is a chain of compensating actions on a race-prone primitive. Diagnosability is poor.
- **Verdict**: rejected.

### Alternative D — `fcntl.flock` on a sibling lockfile (the ticket's recommendation)
Acquire `fcntl.flock(LOCK_EX)` on a stable sibling `.runner.pid.takeover.lock` for the verify-stale-and-recreate sequence.
- **Implementation**: ~25 LOC. Mirrors `cortex_command/init/settings_merge.py:_acquire_lock`.
- **Maintainability**: **BEST.** Kernel auto-releases lock on process death — no fixed-path leak. No stale-state recovery problem. Diagnosability excellent: contention manifests as blocking (or `LOCK_NB` returning `EWOULDBLOCK`), never as silent dual-ownership. The lockfile inode is stable; `runner.pid` inode is replaced — the same shape that motivated the sibling-lockfile pattern in `settings_merge.py`.
- **Regression coverage**: **FULL.** Closes Thread A/B (one starter in critical section at a time). Closes stale-lock-leak (kernel cleanup). Closes takeover-of-live-claim (re-verify happens **under the lock**, before recreate, so no third party can intervene).
- **Cross-platform**: Linux + macOS both implement BSD `flock(2)` semantics for `fcntl.flock` — advisory, per-FD, auto-released on FD close/process death. Known macOS-vs-Linux subtleties (NFS, fork-inheritance) do not bite given the use shape: local FS, FD closed in `finally`, no fork-inheritance reliance.
- **Pattern alignment**: `ipc.py`'s `O_EXCL` is correct for single-shot create; the takeover path is read-modify-write and warrants a different primitive. `settings_merge.py` already establishes flock-sibling-lockfile in-tree for this exact operation shape.
- **Scope sensitivity**: takeover-path only — does NOT switch the repo-wide locking model. The `O_EXCL` happy path stays as-is.

### Alternative E — `os.mkdir` / SQLite WAL
Same on-crash leak as A (mkdir) or wholesale architecture change inconsistent with "file-based state" (SQLite). Not better than D. Rejected.

### Recommended approach: **Alternative D — `fcntl.flock` on `.runner.pid.takeover.lock`, takeover-path-only scope**

**Concrete shape**:
- New helper `_acquire_takeover_lock(session_dir: Path) -> int` — opens `session_dir / ".runner.pid.takeover.lock"` `O_RDWR|O_CREAT|0o600`, calls `fcntl.flock(fd, LOCK_EX | LOCK_NB)` with a polling timeout budget (modeled on `plugins/cortex-overnight-integration/server.py:_acquire_update_flock`). Returns FD on acquire; raises a deterministic timeout error on budget exhaustion.
- In `write_runner_pid`: on first `FileExistsError`, acquire the takeover lock, then re-run read+verify+unlink+recreate **inside `try/finally: os.close(lock_fd)`**. Re-verify under the lock closes the takeover-of-live-claim window.
- Lockfile naming: `.runner.pid.takeover.lock` (dot-prefix for hygiene; `.lock` suffix matches existing convention).

## Adversarial Review

The Alternative D recommendation is structurally correct and superior to A/B/C/E. **Three load-bearing refinements are required before spec.**

### LB1. Blocking `flock(LOCK_EX)` has no operator-recoverable timeout
- The `settings_merge.py` pattern uses **blocking** `LOCK_EX`. PEP 475 EINTR retry means SIGTERM during a blocked acquire is stashed (`deferred_signals`) and the syscall is retried indefinitely. If the lock-holder is alive but stuck (e.g., `psutil.Process(pid).create_time()` slow under load), the runner blocks forever. SIGTERM cannot abort it; only SIGKILL works.
- **Mitigation**: use the polling-with-budget variant from `plugins/cortex-overnight-integration/server.py:655–697` — `LOCK_EX | LOCK_NB`, sleep-and-retry, bounded total budget (~5s). On timeout, raise a deterministic error (e.g. `ConcurrentRunnerError` with `existing_pid=-1`).

### LB2. `clear_runner_pid` callers are not protected; the original TOCTOU may not be wholly closed
- The proposed scope guards only `write_runner_pid`'s second-claim retry path. `clear_runner_pid` callers (`runner.py:540, 581, 1536`; `cli_handler.py:434, 456`) hold no lock.
- The most concerning site is **`_check_concurrent_start`'s pre-`write_runner_pid` `clear_runner_pid` at `runner.py:581`**: two starters can both call `_check_concurrent_start`, both observe stale, both call `clear_runner_pid`, then both call `write_runner_pid` (whose first attempt is `O_EXCL`). The takeover-lock fix protects only the *retry path*; the first-attempt path's stale-clear-then-claim sequence is itself a race and is outside the lock.
- **Mitigation options for spec to choose between**:
  - **(2a)** Move the lock acquire up: `_check_concurrent_start` acquires the takeover lock, performs the stale-detect-and-clear, calls `write_runner_pid` under the same lock. Cleanest semantics. Larger surface change.
  - **(2b)** Have `write_runner_pid`'s first attempt also acquire the lock when it observes any pre-existing file (before the O_EXCL race). Localizes the fix to `ipc.py`. Requires re-checking the file under the lock.
  - **(2c)** Keep scope narrow but document the residual race window and prove via test that pre-`write_runner_pid` clear cannot be the cause of the observed flake. Risk: existing xfail test reproduces only this narrowed scenario; broader scenario goes unobserved.
- The xfail test exercises the *retry path* (initial O_EXCL fails, both threads see stale). LB2 may be a separate window; it requires explicit triage in spec.

### LB3. `pytest-repeat` adoption needs Linux-portable stale-PID design
- `test_runner_concurrent_start_race.py:73` uses `pid: 0` for stale payloads. `psutil.Process(0)` raises `NoSuchProcess` on macOS but returns a kernel-task representation on Linux — `verify_runner_pid` may behave differently.
- The current xfail flake is characterized only on macOS; running 1000 iterations on Linux CI may either mask the bug (if Linux happens to serialize differently) or produce different failure modes.
- **Mitigation**: use a guaranteed-never-existed PID for the stale payload — spawn a short-lived process, capture its PID, kill, wait, then use that now-dead PID. Or use a high impossible PID with `start_time` mismatch.

### Secondary refinements (non-blocking)
- **Lockfile discipline (spec note)**: "no consumer should glob/list `session_dir` and assume only known files exist"; "DO NOT write content to the lockfile"; "DO NOT unlink the lockfile"; "DO NOT call `durable_fsync` on the lockfile" (wasted I/O — the lock is kernel state, not file content).
- **NFS / non-local-FS**: spec should require `lifecycle/sessions/` on local FS; flock semantics on NFS are filesystem-version-dependent. Currently `requirements/pipeline.md` is silent.
- **Backwards compatibility**: an old in-flight runner won't unlink the new lockfile on shutdown — benign one-session leak. Worth a sentence.
- **Session-dir glob audit**: confirmed clean (no test/code path globs `session_dir/*.lock`). Future contributors must not introduce one without skipping the takeover lock.
- **`read_runner_pid`'s `path.exists()` then `read_text` is itself TOCTOU** but already catches `OSError` and returns `None` — safe-but-noisy. Not blocking.
- **Cancel + takeover overlap**: cancel is unlocked. Operator can briefly observe "no active session" while a takeover is mid-flight. Operator-perception bug, not data corruption. Acceptable; document.

### Verdict
The recommendation **does not hold up as written**; it needs three refinements before spec writes:
1. Use polling-with-budget (`LOCK_NB` + sleep + bounded retries) instead of blocking `LOCK_EX`.
2. Decide whether the takeover lock extends to `_check_concurrent_start` (LB2 options 2a/2b/2c) — this is the spec-phase user decision.
3. Replace `pid=0` stale fixture with a portable never-existed-PID idiom.

## Open Questions

- **Q1 (Spec decision)**: Does the takeover lock extend to `_check_concurrent_start`'s pre-`write_runner_pid` clear (option 2a)? Localize to `write_runner_pid`'s first-attempt path under-lock (option 2b)? Or keep scope narrow with a documented residual window (option 2c)? **Deferred: will be resolved in Spec — this is a design tradeoff the user should weigh; the current xfail test scope and the broader race window each pull in different directions.**
- **Q2 (Spec decision)**: What is the polling-budget timeout for `flock(LOCK_NB)` retries? Reference values: `settings_merge.py` uses unbounded blocking; `plugins/server.py` uses 30s. **Deferred: will be resolved in Spec; should probably be ~5s for the takeover path given two-starter contention is bounded.**
- **Q3 (Spec implementation detail)**: The portable stale-PID test fixture — spawn-and-kill a short-lived process to get a guaranteed-never-existed PID, or use a high impossible-pid with start_time mismatch? **Deferred: will be resolved in Spec; both work, choice is implementation-aesthetic.**

All other research questions from the original prompt are resolved:
- Primitive choice → `fcntl.flock` (with polling-budget, not blocking `LOCK_EX`).
- Call-site map → captured above.
- macOS vs Linux semantics → not material for the proposed use shape (local FS, FD closed in `finally`, no fork inheritance, `O_RDWR|O_CREAT` open mode).
- psutil interaction → independent (process-table query, not file op).
- Platform-test harness → not required; `settings_merge.py` already runs `fcntl.flock` on macOS+Linux without a special harness; existing `test_runner_concurrent_start_race.py` plus `pytest-repeat` is sufficient.
