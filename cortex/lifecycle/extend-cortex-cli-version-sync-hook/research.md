# Research: extend cortex-cli-version-sync hook to perform background reinstall on drift

## Codebase Analysis

### Files that will change

- `plugins/cortex-overnight/hooks/cortex-cli-version-sync.sh` — the visibility-only drift detector. Today: stdlib Python in a `bash + heredoc` shape; emits `additionalContext` and exits 0. The extension fires a background install on drift detection.
- `plugins/cortex-overnight/server.py` — source of `CLI_PIN` (line 106), `_ensure_cortex_installed` (~775), `_run_install_and_verify` (~580-772), `_acquire_install_flock` / `_release_install_flock` (~397), `_NDJSON_ERROR_STAGES` (~1101-1114), `_append_error_ndjson` (~1140-1145), `_recent_install_failed_sentinel` (~342), `_enforce_plugin_root` (~52-84). The install logic is the source-of-truth to either factor or duplicate.
- `plugins/cortex-overnight/hooks/hooks.json` — current SessionStart array has two hooks (`cortex-scan-lifecycle.sh`, `cortex-cli-version-sync.sh`). May gain a third entry depending on the sync-vs-async-split decision (see Open Questions).
- `docs/internals/auto-update.md` — owning doc for the two-layer auto-update architecture. The Bash-tool subprocess carve-out section (lines 37-41) and Component map need amendment.
- `cortex/backlog/263-…md` — already created; will be updated with `status: refined` after spec approval.
- Tests: new coverage for the install path under SessionStart. The existing `tests/test_mcp_auto_update_real_install.py` covers the MCP-call branch; a parallel `tests/test_cli_version_sync_hook_install.py` (or extension of an existing test) covers the SessionStart-triggered branch.
- `justfile` mirror set (~566-598) and `.githooks/pre-commit` (Phase 1.95 / Phase 4) — if a new shared `install_core.py` is vendored, the parity machinery grows by one file.

### Files the change reads or depends on

- `plugins/cortex-overnight/cli_pin.py` — side-effect-free `CLI_PIN` carrier (already extracted under #235's Phase 1; verify the file exists and contains only the literal).
- `plugins/cortex-overnight/install_guard.py` — vendored `check_in_flight_install_core` (byte-identical mirror of `cortex_command/install_guard.py`). The new install path must call this to honor the in-flight session guard.
- `cortex_command/install_guard.py` — canonical source for the mirror.
- `~/.local/state/cortex-command/` state dir: `last-version-check` (existing throttle sentinel), `install.lock` (existing flock), `install-failed.<ts>` (existing failure sentinel), and new files for the background-install path (see Tradeoffs Decision 3).
- `~/.local/share/overnight-sessions/active-session.json` — in-flight session pointer consulted by `check_in_flight_install_core`.

### Existing patterns to follow

1. **Inline-Python-in-bash heredoc with error containment** (current hook lines 51-260):
   ```bash
   set +e
   python3 - <<'PY'
   # ... stdlib Python
   sys.exit(0)
   PY
   set -e
   ```
   The single-quoted `<<'PY'` delimiter prevents shell expansion. `set +e` containment ensures non-zero Python exits cannot crash the hook.

2. **Skip-predicate ordering** (server.py:1201-1255; hook lines 188-191): `CORTEX_DEV_MODE=1` (cheapest, no subprocess) → `git status --porcelain` (dirty-tree) → `git rev-parse --abbrev-ref HEAD != "main"` (branch). Predicates fire BEFORE sentinel writes so changing state retries on next session.

3. **Mtime-based throttle sentinel** (hook lines 26-35): `stat -f %m` (BSD) / `stat -c %Y` (GNU) cross-platform mtime check; 1800s window; ~10µs hit-path via `stat(2)`.

4. **Install argv** (server.py:626-635): `uv tool install --reinstall --refresh-package cortex-command git+https://github.com/charleshall888/cortex-command.git@<CLI_PIN[0]>`. The `--refresh-package` flag invalidates uv's named-package cache; whether it invalidates git-tag→commit resolution is challenged in §Adversarial F3.

5. **Flock + in-flight guard sequence** (server.py:337-430): `_acquire_install_flock` uses `fcntl.flock(LOCK_EX | LOCK_NB)` polled with a 60s wait budget. Before install: consult `check_in_flight_install_core` against the active-session pointer; if a runner is live, skip with stderr remediation.

6. **NDJSON audit emission** (server.py:1140-1145): `_append_error_ndjson(stage, error, context)` writes one line to `${XDG_STATE_HOME}/cortex-command/last-error.log`. Stages must appear in the `_NDJSON_ERROR_STAGES` frozenset allowlist.

7. **In-place schema-floor gate** (server.py:1827, hook lines 213-234): wheel-install-only (test: `(Path(cortex_root) / ".git").is_dir()` false), uses `<` comparison on major version, mirrors a single stderr remediation line.

8. **Background subprocess detach** (existing project pattern, not yet in this hook):
   - `cortex_command/overnight/runner.py:1052,1263`, `seatbelt_probe.py:207`, `cli_handler.py:382` — `subprocess.Popen(..., start_new_session=True)` is the canonical Python form.
   - `cortex_command/overnight/scheduler/launcher.sh:144-159` — `setsid nohup CMD &` with `</dev/null >/dev/null 2>&1` redirects as the bash form, fallback to `nohup … &` + `disown` when `setsid` is unavailable.

### Integration points and dependencies

- **Plugin-imports-zero-cortex-modules contract** (ADR-0002, `docs/internals/mcp-contract.md:3`). The hook and any new install logic must NOT `import cortex_command`. Verified: server.py and install_guard.py mirror have zero such imports.
- **PEP 723 venv vs hook stdlib**: `server.py` uses PEP 723 inline metadata (line 7) listing `packaging`, `fastmcp`, `pydantic`. The hook's Python is the system `python3` from PATH (no PEP 723 resolution at hook invocation). Any shared module called from both must use stdlib only — no `from packaging.version import Version`. The existing hook uses a `version_tuple()` helper for stdlib comparison; the same shape must apply to a shared install module.
- **Mirror parity enforcement**: `.githooks/pre-commit` Phase 1.95 runs `just sync-install-guard --check` against the install_guard pair. A new vendored `install_core.py` would extend this set; a factored approach does not.
- **`build-plugin` recipe** (`justfile:566-598`): rsyncs canonical `hooks/*.sh` into `plugins/cortex-overnight/hooks/`. Pre-commit Phase 4 (lines 311-338) fails on drift.

### Conventions that constrain the design

- The hook is **stdlib-only**. No `from cortex_command import …`. No third-party imports.
- **Defensive `exit 0` on every error path** in the visibility surface — hook errors must never brick Claude Code launch.
- **Skip-then-sentinel ordering** — never write the throttle sentinel before evaluating skip predicates; otherwise dogfooders never retry after un-dirtying.
- **30-minute throttle window** is per-user (XDG state), not per-repo.
- **`cortex --print-root` envelope is forever-public-API** (`docs/internals/mcp-contract.md:22-28`): `version`, `schema_version`, `root`, `package_root`, `remote_url`, `head_sha` are stable in type and meaning.

---

## Web Research

### Critical findings

1. **Claude Code Issue [#43123](https://github.com/anthropics/claude-code/issues/43123)** — a SessionStart hook that backgrounded `caffeinate -s &` HUNG Claude Code v2.1.87+. Root cause: the background process inherits the parent's stdin/stdout fds, which Claude Code uses for stream-json IPC with the Desktop App; the child holding them open caused indefinite wait. Documented fix: `nohup CMD </dev/null >/dev/null 2>&1 &`. **The load-bearing primitive is explicit fd closure on stdin/stdout/stderr, not `nohup` per se.**

2. **Claude Code has first-class async hook support** ([docs](https://code.claude.com/docs/en/hooks)):
   - `"async": true` — "If true, runs in the background without blocking."
   - `"asyncRewake": true` — "If true, runs in the background and wakes Claude on exit code 2. Implies async."
   - **Limitation**: async hooks cannot emit `additionalContext` (only sync hooks with exit code 0 do that).
   - "On macOS and Linux, command hooks run in their own session without a controlling terminal as of v2.1.139" — Claude Code already calls `setsid`-equivalent before invoking hooks on current versions.

3. **`setsid(1)` is NOT on default macOS** ([Apple man pages archive](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/setsid.2.html)). The syscall exists; the CLI wrapper doesn't ship by default. Python's `subprocess.Popen(..., start_new_session=True)` calls `os.setsid()` in the child via `posix_spawn`/`fork` — portable equivalent. **The project already uses this pattern at four callsites.**

4. **`flock(1)` is NOT on default macOS** ([discoteq/flock](https://github.com/discoteq/flock)). Must use Python's `fcntl.flock` from the inline Python heredoc — which server.py already does at line 397.

5. **uv `--refresh-package` and git cache** ([uv #7866](https://github.com/astral-sh/uv/issues/7866), [uv cache concepts](https://docs.astral.sh/uv/concepts/cache/)): "For Git dependencies, uv caches based on the fully-resolved Git commit hash." Issue #7866 reports `--reinstall` failing to refresh git cache for force-pushed-tag-like scenarios; `--refresh-package` was tried and also did not fix it. **The cache key for git deps is the resolved commit SHA, not the package name** — so `--refresh-package cortex-command` operates downstream of the tag-resolve cache. This is a real correctness gap for force-pushed release tags. Mitigations: (a) `--refresh` (whole-cache invalidation, cost penalty), (b) resolve tag→SHA upstream via `git ls-remote` and pass `git+…@<sha>`.

6. **In-place binary replacement safety** ([Arch BBS](https://bbs.archlinux.org/viewtopic.php?id=249818)): POSIX semantics — already-exec'd processes hold the old inode for the executable text segment; new openers see the new inode. **However**: this guarantee covers only the executable, not the venv's Python modules. uv's tool-install does NOT use atomic rename-into-place at the venv level (per docs.astral.sh/uv/concepts/tools/). Files inside `~/.local/share/uv/tools/cortex-command/lib/python*/site-packages/` may be overwritten in place during install; long-running Python processes that have those modules loaded via `sys.path` injection (e.g., a Claude Code MCP server process holding `cortex_command.*` mid-import) could see corruption.

### Prior art (self-updaters in adjacent tools)

- **Homebrew core**: foreground only, with `HOMEBREW_AUTO_UPDATE_SECS` gate before install commands. Background updating is a separately-installed tap (`homebrew-autoupdate`) that uses **launchd**, not shell backgrounding.
- **rustup**: `auto-self-update = enable|disable|check-only`. Inline foreground when triggered by `rustup update`; no background daemonization.
- **Claude Code native installs**: "automatically update in the background to keep you on the latest version" — internal to the Claude Code binary, not a shell hook pattern.
- **lazy.nvim**: async checker uses Neovim's libuv event loop, not shell daemonization.

### Anti-patterns surfaced

- **Bare `&` backgrounding without fd redirection** — exactly the #43123 footgun.
- **Relying on `flock(1)` on macOS** — must use Python's `fcntl.flock` or an O_CREAT|O_EXCL lockfile.
- **Assuming `--reinstall` clears git cache** — per #7866 in current uv versions, it doesn't; `--refresh` or upstream SHA resolution is required.
- **Assuming in-place binary replacement is universally safe** — true for the running executable, NOT for mmap'd modules in the venv that long-running processes hold open.
- **`setsid nohup … &` as a portable one-liner** — non-portable to default macOS without `brew install util-linux`.

---

## Requirements & Constraints

### From `cortex/requirements/project.md`

- **Day/night split** (lines 11-12): "Daytime is iterative collaboration; overnight is handoff; morning is strategic review." A stale daytime CLI breaks the daytime collaboration loop — directly served by this work.
- **Solution horizon** (line 21): "A deliberately-scoped phase of a multi-phase lifecycle is not a stop-gap (stop-gap means unplanned-redo)." Ticket #235's visibility-only scope was deliberate; this ticket is the next deliberate phase, not a redo.
- **Complexity earn its place** (line 19): "Must earn its place by solving a real problem now. When in doubt, simpler wins." The daytime-only-user failure mode is the "real problem now."
- **Graceful partial failure** (line 45): The new install path must fail gracefully — install failure cannot brick the hook or block the session.
- **Defense-in-depth for permissions** (line 48): The background install path must not require sandbox elevation it doesn't already have.
- **Destructive operations preserve uncommitted state** (line 49): Reinstalling a wheel is not destructive of user state, but the dirty-tree skip predicate exists to protect editable installs (`uv tool install -e .`). Must be preserved.

### From `cortex/adr/0002-cli-wheel-plus-plugin-distribution.md`

- Plugin/CLI version coupling via `CLI_PIN` is the load-bearing contract. The new hook code MUST respect plugin-imports-zero-cortex-modules.
- CLI evolves at independent cadence; the schema-floor major is the forever-public-API gate.

### From `docs/internals/auto-update.md`

- **Two-layer architecture**: Layer 1 = marketplace fast-forward (Anthropic-owned); Layer 2 = MCP-tool-call-gated reinstall via `_ensure_cortex_installed`. This ticket adds a third coordination point at SessionStart.
- **Bash-tool subprocess carve-out** (lines 37-41) is exactly the gap this ticket closes for daytime-only users.
- **Component map** rows that the new feature must coordinate with: `_ensure_cortex_installed` (R4), `_schema_floor_violated` (R13), `_NDJSON_ERROR_STAGES` registry, `check_in_flight_install_core`, and the existing `cortex-cli-version-sync.sh` (#235).

### From `docs/internals/mcp-contract.md`

- `cortex --print-root` envelope is forever-public-API; new code can rely on `version` (PEP 440 string), `schema_version` (M.m string), `root` (absolute path).
- Schema major bumps are breaking; minor bumps are additive.
- Plugin's sole interface to CLI is `subprocess.run(["cortex", ...])` + JSON parsing.

### From prior ticket #235 (`cortex/lifecycle/trigger-cortex-cli-reinstall-at-sessionstart/`)

The Non-Requirements section of that spec.md explicitly named these as out-of-scope; this ticket **reverses each one**:
- "The hook does not execute `uv tool install --reinstall`" → now in scope
- "The hook does not consult the in-flight install guard" → now in scope
- "The hook does not acquire the install flock" → now in scope
- "The hook does not write NDJSON audit records" → now in scope

Constraints carried forward (still load-bearing):
- Plugin-imports-zero-cortex-modules contract
- Stdlib-only Python in hook (no PEP 723 venv at hook invocation)
- Defensive `exit 0` on errors
- 30-minute freshness throttle for the probe
- Dev-mode / dirty-tree / non-main-branch skip predicates
- Schema-floor gate parity with `_schema_floor_violated`
- `cortex --print-root` envelope as the version-source contract

### Constraints superseded by this ticket

The prior research's central conclusion (`cortex/lifecycle/trigger-cortex-cli-reinstall-at-sessionstart/research.md:265-282`) — "Alternative F (visibility-only) over Alternative A (reinstall)" — rests on five rationale points, three of which are dissolved by the new framing:

| Rationale | Status now |
|---|---|
| (1) No streaming UI at SessionStart | **Moot** — design no longer attempts to stream; background install completes silently. |
| (2) Probe cost 10× optimistic | **Already mitigated** — the 30-min throttle sentinel shipped under #235. |
| (3) Marketplace race fragile | **Still load-bearing** — design must detect-and-correct, not bet on ordering. Composite already does this. |
| (4) MCP-call covers gap | **Invalidated** — daytime-only users are now a recognized population. |
| (5) F is much smaller | **Still true** — this work is larger. Justified by (4). |

### Fallback applied

Backlog #263 has `tags: []` → project.md only loaded per the tag-based loading protocol's fallback. No area docs apply.

---

## Tradeoffs & Alternatives

### Decision 1 — Factor vs vendor vs duplicate the install logic

- **1A Factor** into `plugins/cortex-overnight/install_core.py` (stdlib-only sibling of server.py). server.py and hook both import from it. Strongest maintainability; one substantial refactor cost.
- **1B Vendor** a byte-identical mirror in the plugin paired with a canonical source in `cortex_command/`. Mechanically matches `install_guard.py` precedent but conceptually awkward — install logic's natural home is the plugin (knows `CLI_PIN`), not the CLI.
- **1C Duplicate** in the hook (either direct bash `uv tool install` or a parallel single-file Python script). Lowest implementation cost; highest drift risk over time; bypasses the flock/sentinel discipline that exists for correctness reasons.

**Recommended: 1A factor**, with the caveat that the factor produces three plugin-local sibling files (`cli_pin.py`, `install_guard.py`, `install_core.py`) all stdlib-only, plus a third pre-commit parity gate. Real obstacles surfaced in §Adversarial A1: `packaging`-dependency removal (use stdlib `version_tuple`), import-time `_enforce_plugin_root()` placement, mcp/pydantic imports must NOT bleed into the new module.

### Decision 2 — Background install mechanism

- **2A** `nohup … &` + `disown` inline in bash. Simple. Requires explicit `</dev/null >/dev/null 2>&1` per #43123. `disown` is bash-builtin; adds nothing on top of fd-closure.
- **2B** `setsid` (Linux) / `caffeinate` (macOS) wrapped. Stronger pgroup detachment. Cross-platform shim adds complexity. `setsid` unavailable on default macOS.
- **2C** Separate `cortex-bg-install` launcher script. Adds a new bin for one use case. Hard to justify.
- **2D** Python `subprocess.Popen(..., start_new_session=True)` from inside the hook's existing inline Python. Matches existing project pattern at 4 callsites. `start_new_session=True` does `os.setsid()` in the child, portable to macOS without `brew install util-linux`.

**Both Agent 4 and the adversarial review converge here**: 2D is the right mechanism *for an in-hook detach*. However, §Adversarial F2 raises a fundamentally different shape — **split the hook into a sync hook (existing visibility) + an async hook (install)** — that bypasses the detach question entirely by using Claude Code's native `async: true` field. See §Open Questions Q1.

### Decision 3 — Logging surface

- **3A** New NDJSON file (`install.log`)
- **3B** Plain-text rolling (`last-install.log`, truncated)
- **3C** Both
- **3D** Extend existing `last-error.log` NDJSON via new `_NDJSON_ERROR_STAGES` entries (`session_start_first_install`, `session_start_reinstall`, `session_start_reinstall_parse_failure`, `session_start_reinstall_blocked_by_inflight_session`, `session_start_reinstall_flock_timeout`).

**Recommended: 3D for the NDJSON audit, plus a separate plain-text `~/.local/state/cortex-command/last-install-uv.log` (truncated per attempt) for uv's progress stdout/stderr.** Two separate concerns, two separate files — NDJSON for audit, plain text for human debug of the most recent attempt. §Adversarial F9 verified zero downstream consumers will break on new allowlist entries.

### Decision 4 — Throttle behavior on reinstall

- **4A** Reuse `last-version-check` for both probe and reinstall (single 30-min knob).
- **4B** Separate sentinel for reinstall attempts with independent window.
- **4C** Reuse `install-failed.<ts>` mechanism but with different window at the hook layer.

§Adversarial F6 challenges 4C's "shared file with window parameter" shape — the MCP path's 60s sentinel and the SessionStart path's 30-min sentinel are semantically different (per-task hot-retry suppression vs. cross-session backoff). They should be **separate files** (e.g., `session-install-failed.<ts>` distinct from `install-failed.<ts>`), not a shared file.

**Recommended: refine 4C to separate sentinels with parallel filenames.** Probe throttle stays on `last-version-check` (unchanged). MCP failure-throttle stays on `install-failed.<ts>` with 60s window (unchanged). Hook adds `session-install-failed.<ts>` with 30-min window. No exponential backoff in V1 — file follow-up if 30-min retries prove noisy.

### Decision 5 — First-install case (probe says "not installed")

- **5A** Auto-install matching the MCP-call first-install branch.
- **5B** Warn-only via `additionalContext`; user must run install manually.
- **5C** Skip entirely.

§Adversarial F7 is decisive here. **The hook fires on every SessionStart in every repo where the cortex-overnight plugin is enabled.** A user with the plugin installed who opens Claude in `~/Workspaces/some-react-app` (no cortex usage intended) would get unsolicited `uv tool install` of cortex-command. That is hostile behavior — the plugin install does not constitute per-repo opt-in.

**Recommended: 5B (warn-only) for SessionStart-driven first-install.** Keep the MCP-call-gated `_ensure_cortex_installed` first-install path unchanged — it only fires when the user actively invokes overnight tools, which is the consent signal. SessionStart should be reinstall-on-drift only; first-install requires affirmative user action.

### Recommended composite (after adversarial integration)

1. **Factor** (1A) into `install_core.py` with `cli_pin.py` as the shared CLI_PIN source. Three plugin-local stdlib-only siblings: `cli_pin.py`, `install_guard.py`, `install_core.py`. Pre-commit parity gate covers all three.
2. **Background detach** TBD — see Open Questions Q1 (sync-hook-with-Popen-detach vs. two-hook async-split).
3. **Logging** (3D) — NDJSON audit into `last-error.log` via extended `_NDJSON_ERROR_STAGES`, plus separate `last-install-uv.log` plain-text for uv's own output.
4. **Throttle** (4C refined) — separate `session-install-failed.<ts>` sentinel with 30-min window.
5. **First-install** (5B) — SessionStart warn-only via `additionalContext`; reinstall-on-drift is the SessionStart automation; first-install stays MCP-call-gated.
6. **Under-lock re-check** — after acquiring the install flock, re-probe installed version and bail early if it now matches `CLI_PIN[0]` (closes §Adversarial F4's "5 instances all reinstall" hazard).
7. **Tag→SHA pinning** — `CLI_PIN` adds a SHA element so the install argv pins to the commit, not the tag. Closes §Adversarial F3 (uv git-cache staleness) and §Adversarial S1 (force-push attack surface). Requires release process change.
8. **Narrow dirty-tree predicate** — skip only when `cwd` is inside the cortex-command repo itself (per §Adversarial F8).
9. **Previous-failure surfacing** — sync hook reads recent `session-install-failed.*` sentinels and surfaces them via `additionalContext`.
10. **`UV_NO_PROGRESS=1`** in the background install environment to neuter any TTY-coupled uv child behavior.
11. **`_enforce_plugin_root()` re-invocation** at the top of `install_core.py` to close the confused-deputy surface when the install path runs outside server.py's process.

---

## Adversarial Review

### Failure modes and edge cases

- **F1: fd-closure is the load-bearing primitive, not `nohup`.** Issue #43123's root cause is fd inheritance. `start_new_session=True` is defense-in-depth; the actual fix is `stdin=DEVNULL, stdout=log, stderr=STDOUT` on Popen (or `</dev/null >/dev/null 2>&1` in bash). `uv` may spawn TTY-coupled subprocesses (indicatif progress); set `UV_NO_PROGRESS=1` defensively.

- **F2: `async: true` is the harness-native solution, but cannot emit `additionalContext`.** This forces a two-hook split: sync hook (existing) keeps emitting visibility warnings on drift; async hook (new) fires the install. The two hooks share an `install_core.py` import but cannot share a process. This is **structurally cleaner than rolling our own Popen-detach** and aligns with project guidance to avoid fighting the harness — but introduces a new architectural shape (two-hook split with shared library). See §Open Questions Q1.

- **F3: `--refresh-package cortex-command` does NOT invalidate uv's git tag→SHA resolution.** Per uv issue #7866 and the uv cache docs ("uv caches based on the fully-resolved Git commit hash"), the cache key is the SHA, not the package name. Force-pushed release tags can pull stale commits. **Mitigations**: (a) add `--refresh` (whole-cache invalidation, cost penalty), (b) resolve tag→SHA via `git ls-remote` in the release ritual and ship `CLI_PIN = (tag, sha, schema)` so the argv pins `git+…@<sha>` (preferred — disciplined release-train model).

- **F4: Multiple concurrent SessionStarts produce redundant 30s installs.** `_run_install_and_verify`'s under-lock re-check fires only for the `first_install` stage (server.py:624). For `version_mismatch_reinstall`, no re-check. With 5 simultaneous Claude Code instances: instance 1 acquires lock and installs; instances 2-5 wait up to 60s for the lock, then run their own reinstalls against the now-current version. **Mitigation**: add `version_mismatch_reinstall` and `session_start_reinstall` to the under-lock re-check branch — re-probe and bail if version now matches `CLI_PIN[0]`.

- **F5: Background install mid-window can corrupt the venv for concurrent bash `cortex …` calls.** uv's tool-install is not atomic at the venv level; per-file overwrites can produce a half-replaced site-packages tree. A Claude bash subprocess running `cortex …` during the install window may hit `ImportError` / `AttributeError`. **Mitigation**: during install, the visibility hook's `additionalContext` must escalate from "drift detected" to "install in progress; bash `cortex …` may fail until next session." Strongest fix: visibility hook reads a "background-install-in-progress" marker file (the flock itself or a separate `install.in-progress` sentinel) and adjusts the warning accordingly.

- **F6: Sentinel-window-parameter sharing is wrong.** MCP-path 60s and SessionStart-path 30-min sentinels have different semantics (per-task hot-retry suppression vs. cross-session backoff). They should be **separate files** (`install-failed.<ts>` vs. `session-install-failed.<ts>`), not a parameterized share. Already integrated into the composite as 4C-refined.

- **F7: First-install on every cortex-overnight-plugin-enabled repo is hostile.** Plugin install is global, not per-repo. A user opening Claude in a non-cortex repo would get unsolicited `uv tool install`. **Mitigation**: drop first-install from SessionStart (5B); keep it MCP-call-gated. Already integrated.

- **F8: Dirty-tree predicate is too coarse.** Today the hook skips on any dirty tree, regardless of repo. A dogfooder with uncommitted work in a non-cortex repo would never get auto-installs. **Mitigation**: narrow the predicate to `cwd within cortex-command repo` (test via `git rev-parse --show-toplevel` matching the cortex-command remote). Already integrated.

- **F9: NDJSON stage allowlist additions are zero-risk.** Verified by reading `tests/test_mcp_auto_update_orchestration.py` and `tests/test_mcp_auto_update_real_install.py`. No downstream consumer enumerates the stage set. Safe to extend.

- **F10: Install-failure-after-session-close is silent.** Composite's V1 design accepts this; the recommended fix is for the next SessionStart's sync hook to read recent failure sentinels and surface them via `additionalContext`. Integrated into composite point 9.

### Security concerns

- **S1: Unattended `uv tool install` widens the supply-chain attack window 50-100x.** Today the install runs only when the user invokes overnight tools; tomorrow it runs every session. Trust assumptions:
  1. GitHub TLS endpoint is honest.
  2. `v2.10.0` tag points to a benign commit (force-push attack defeats this).
  3. `--refresh-package` re-pulls on tag movement (F3 — it doesn't reliably).
  4. Arbitrary Python from wheel setup hooks runs at install time.
  - **Mitigation**: pin to commit SHA, not tag (F3 + S1 single fix). Additional optional: SHA-256 wheel verification against a value in `CLI_PIN`; `CORTEX_AUTO_INSTALL_REVIEW=1` env var for `additionalContext`-only mode. Document trust model explicitly in `docs/internals/auto-update.md`.

- **S2: `_enforce_plugin_root()` only protects server.py.** The new install path's child process needs the same protection — `install_core.py` should re-run `_enforce_plugin_root()` at module load to close the confused-deputy surface when a manipulated `${CLAUDE_PLUGIN_ROOT}` points at attacker-controlled paths. Integrated into composite point 11.

- **S3: `python3 -c` invocation must use `sys.executable`, not bare `python3`.** Hook resolves to system Python; bare `python3` could resolve to a shadowed interpreter. Use `sys.executable` + explicit `PYTHONPATH` pinned to `plugins/cortex-overnight/`.

### Assumptions that may not hold

- **A1: Clean factor of `_run_install_and_verify`.** Real obstacles enumerated in §Adversarial A1: `packaging` PEP 723 dep (use stdlib `version_tuple`); `from mcp.server.fastmcp import FastMCP` top-level import in server.py (must NOT bleed into install_core); `_enforce_plugin_root()` global invocation (re-run in install_core); `CLI_PIN` already extracted (or pending extraction) to `cli_pin.py`. The ~400 LOC of install code itself is encapsulated and has no hidden coupling to FastMCP lifecycle.

- **A2: Claude Code v2.1.139+ sessionizes hooks.** Hook docs confirm. `start_new_session=True` is defensive belt-and-suspenders for older clients. Keep it — free.

- **A3: "30-second install" is optimistic.** Real range is 10s warm-cache → 5 minutes on cold cache or slow network. The 300s `_INSTALL_SUBPROCESS_TIMEOUT_SECONDS` ceiling at server.py:296 is the real bound. Plan for the tail in UX (additionalContext warning duration, install-failed sentinel windows).

### Recommended mitigations integrated into composite

Items 6-11 of the recommended composite above directly address §Adversarial findings F3, F4, F5, F7, F8, F10, S1, S2.

---

## Open Questions

### Q1. Sync-hook-with-Popen-detach vs. two-hook async-split

This is the central design decision and must be resolved with the user at Spec.

**Option A — single sync hook with Popen detach** (Agent 4's composite): existing hook extends to call `subprocess.Popen(..., start_new_session=True, stdin=DEVNULL, ...)` on drift. Hook emits `additionalContext` and exits before install completes.

- Pros: minimal change to hook structure; one hook entry; no new shape.
- Cons: re-implements what Claude Code's native `async: true` provides; "fights the harness" per project guidance; carries fd-inheritance risk if Popen redirects are ever wrong.

**Option B — two-hook split** (§Adversarial F2): keep existing sync hook for `additionalContext`-only visibility; add a new `cortex-cli-background-install.sh` entry with `"async": true` in `hooks.json` that does the install. Both hooks import the shared `install_core.py`.

- Pros: harness-native, structurally clean, Claude Code handles backgrounding; future-proof against Claude Code hook execution changes; no Popen-detach gymnastics needed; cleaner separation of concerns.
- Cons: new architectural shape (two-hook split with shared library); `async: true` cannot emit `additionalContext`, so async hook is silent on success/failure; sync hook becomes responsible for surfacing prior-attempt outcomes via `additionalContext`.

**Recommendation**: Option B (two-hook async-split). Rationale: aligns with project guidance (CLAUDE.md "harness-native" preference), reduces our maintenance surface (Claude Code owns backgrounding semantics), eliminates fd-inheritance risk by construction. The "async cannot emit additionalContext" limitation is acceptable because the sync hook still owns the visibility surface — it's already where prior-failure surfacing belongs.

### Q2. Tag→SHA pinning in `CLI_PIN` requires a release process change

Per §Adversarial F3 and S1, the durable fix for both uv git-cache staleness and force-push supply-chain risk is pinning `CLI_PIN` to a commit SHA, not a tag. This requires:
- `bin/cortex-rewrite-cli-pin` to compute the SHA at release time (already has access to it via `git rev-list -1 <tag>`).
- `CLI_PIN` literal shape change from `(tag, schema)` to `(tag, sha, schema)`.
- Backwards-compat reads if any consumer parses the 2-tuple shape.

**Defer to Spec**: is this in scope for #263, or a separate follow-up ticket? It's a clean separate concern from the SessionStart hook itself, but it's required to make the SessionStart hook secure under force-push.

### Q3. Surfacing background-install completion to the same Claude session

The background install completes 10s-5min after the SessionStart hook returns. The user's current Claude session doesn't see "install complete" — only the next SessionStart's `cortex --print-root` shows the new version. The composite accepts this as residual.

Alternative: use `asyncRewake: true` instead of plain `async: true`. The async hook would exit 2 on successful install completion, waking Claude with a notification. Pros: closes the loop in the same session. Cons: spurious wake noise if installs are frequent; not all Claude Code launches use a foreground Claude instance.

**Defer to Spec**: pick `async` vs `asyncRewake`. Recommend `async` for V1 — simpler, no wake noise; revisit if user feedback says "I want to know when it finished."

### Q4. Install-in-progress marker mechanism

Per §Adversarial F5, during the install window, bash `cortex …` calls may break. The visibility hook needs to detect "install in progress" and adjust its `additionalContext`. Two mechanisms:

- **(a) Read the flock state** — try `LOCK_SH | LOCK_NB`; if it fails, install is in progress. Issue: the visibility hook would have to acquire-then-release on every probe, adding latency.
- **(b) Separate marker file** — async hook writes `install.in-progress` before install starts and removes it after. Visibility hook stats the file. Simpler, atomic, costs one `stat(2)`.

**Defer to Spec**: pick the mechanism. Recommend (b) — cheaper, atomic, no flock contention from the visibility path.

### Q5. CORTEX_AUTO_INSTALL=0 carve-out scope

The existing carve-out at server.py:826 disables auto-install for the MCP-call path. Should it also disable the SessionStart background install? Intuitively yes — the env var means "I'm managing CLI versions manually, don't touch it." But the composite did not explicitly extend the carve-out to the new path.

**Recommendation**: extend `CORTEX_AUTO_INSTALL=0` to gate the SessionStart install path as well. Document the env var explicitly in `docs/internals/auto-update.md` under the new SessionStart layer. No spec interaction required — clean addition.

### Q6. Documenting the new trust model

§Adversarial S1 flags a 50-100x widening of the supply-chain attack window. The Spec should require an update to `docs/internals/auto-update.md` that explicitly documents:
- The trust model (TLS to GitHub + tag/SHA trust)
- The mitigations (SHA pinning if Q2 lands, `CORTEX_AUTO_INSTALL_REVIEW` if introduced)
- The recommended user posture (review the cortex-command source before installing the plugin; trust delegated to the maintainer's GitHub account)

**Mark as required-in-spec, not deferred.**
