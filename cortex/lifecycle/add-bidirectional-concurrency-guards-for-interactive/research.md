# Research: Add bidirectional concurrency guards for interactive worktree mode

> **Loop-back research** (round 2): the original research.md was invalidated by spec-phase critical-review findings — three load-bearing assumptions failed (`ps` is sandbox-blocked; in-memory filter doesn't reach orchestrator/feature_executor; recorded PID may be the wrong process under wrappers). This round investigates the empirically-verified Claude Code execution model, sandbox-safe identification mechanisms, and the actual cross-process IPC paths.

Extend the interactive worktree mode with bidirectional concurrency guards via three coherent components: per-feature interactive lock written at dispatch and read at preflight; overnight-active rejection mirror on the interactive path; inverse-direction overnight startup scan that skips features with live interactive owners. At most one live interactive owner and one overnight runner per feature.

## Codebase Analysis

### Claude Code env-var contract (empirical, in-repo)

Confirmed via live `env` dump under the Bash tool:

| Env var | Source | Stability |
|---|---|---|
| `CLAUDE_CODE_SESSION_ID` | Claude Code v2.1.132+ | Documented in env-vars page; rotates on `/clear`; preserves across `--resume` |
| `CLAUDECODE=1` | Claude Code | Cleared by `cortex_command/pipeline/dispatch.py:534-542` when spawning sub-agents |
| `CLAUDE_CODE_ENTRYPOINT=cli` | Claude Code | Observed |
| `CLAUDE_CODE_EXECPATH` | Claude Code | Observed |
| `CLAUDE_CODE_TMPDIR` | Claude Code | Observed |
| `CLAUDE_EFFORT` | Claude Code | Observed |
| `LIFECYCLE_SESSION_ID` | Harness-set (`hooks/cortex-scan-lifecycle.sh:10`) | Stable for cortex skill consumption |
| `CORTEX_REPO_ROOT` | Harness-set | Stable for cortex skill consumption |
| `SANDBOX_RUNTIME=1` | Anthropic sandbox-runtime | Observed |

**Key finding**: `CLAUDE_CODE_SESSION_ID` is the documented mechanism for session identification. It matches the `session_id` JSON field passed to hooks (`hooks/cortex-scan-lifecycle.sh:8`). The harness mirror is `LIFECYCLE_SESSION_ID` at `cortex_command/overnight/runner.py:2019`.

**Sub-agent forwarding caveat**: `cortex_command/pipeline/dispatch.py:534-548` explicitly clears `CLAUDECODE` and selectively forwards `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `LIFECYCLE_SESSION_ID`, `TMPDIR`, `CORTEX_REPO_ROOT`. **`CLAUDE_CODE_SESSION_ID` is NOT in the forward list**. Sub-agent context behavior is undefined — see OQ-B below.

### macOS Seatbelt sandbox semantics (empirical + Anthropic sandbox-runtime source)

Default profile (from `anthropic-experimental/sandbox-runtime/src/sandbox/macos-sandbox-utils.ts`):
- `(allow process-exec)`, `(allow process-fork)`
- `(allow process-info* (target same-sandbox))` — **same-sandbox scoping**
- `(allow signal (target same-sandbox))` — **same-sandbox scoping**
- `(allow sysctl-read <allowlist>)` — `kern.proc.*`, `kern.boottime`, common patterns

| Mechanism | Sandbox-compatible? | Notes |
|---|---|---|
| `os.getppid()` | **Yes always** — no Seatbelt gate | Returns immediate parent; under default zsh-wrapping, that's claude when bash is the direct child of zsh which is direct child of claude (empirically PPID=40547 = `claude --dangerously-skip-permissions`) |
| `ps` exec | **No** — `/bin/ps` exec blocked by file-read deny | Confirmed: `(eval):1: operation not permitted: ps` |
| psutil same-sandbox | **Yes** | `process-info*` + `sysctl-read` both allowed for same-sandbox |
| psutil cross-sandbox (introspecting claude CLI which is outside the sandbox) | **Likely fails** | parent is not `(target same-sandbox)`; `Process(ppid).name()` may return generic info or AccessDenied |
| `os.kill(ppid, 0)` cross-sandbox | **Unverified empirically** | POSIX kill 0 is permission-checked, may succeed cross-sandbox; needs probe before relying on it |
| sysctl via ctypes for walking parent chain | **Partially** — first hop works, walking returns `ppid=0` past sandbox boundary | Cannot walk beyond immediate parent under default sandbox |
| `/proc/<pid>/stat` | **N/A** — macOS has no procfs | Linux-only |

**Critical implication**: Under default sandbox, a Python helper invoked via `uv run cortex-interactive-lock` has parent chain `claude → zsh → uv → python`. `os.getppid()` from the helper returns uv's PID. Walking up beyond immediate parent is blocked. **Therefore PPID-walking cannot reliably reach the claude CLI PID.** The env-var mechanism (`CLAUDE_CODE_SESSION_ID`) is the only sandbox-safe identification primitive.

### runner.py state mutation flow (line refs verified)

`cortex_command/overnight/runner.py`:
- Line 2019: `os.environ["LIFECYCLE_SESSION_ID"] = session_id` — mirror of session id
- Line 2032–2038: startup state load via `_start_session(...)` (non-dry-run); `_start_session` at line 816 calls `load_state(state_path)` and returns unchanged state
- Line 2045: dry-run-only `state = state_module.load_state(state_path)`
- Line 2120–2128: round-loop entry — consumes `state.current_round`, `state.integration_branch`
- Line 2151: in-loop `state = state_module.load_state(state_path)` with comment "Reload state to pick up mid-round mutations by peer modules"
- Lines 1037–1056 (`_spawn_orchestrator`) and 1242 (`_spawn_batch_runner`): subprocess spawns

**`load_state` semantics** (`cortex_command/overnight/state.py:349-418`): fresh `state_path.read_text()` every call — no caching.

**`save_state` semantics** (`state.py:421-464`): tempfile + `durable_fsync` + `os.close` + `os.replace` — atomic. `_save_state_locked` in `runner.py:345-360` wraps in `coord.state_lock` + `deferred_signals` so SIGINT/SIGTERM/SIGHUP cannot interrupt.

**Cross-process consumers**:
- `cortex_command/overnight/orchestrator.py:182` — `load_state(config.overnight_state_path)` fresh disk read
- `cortex_command/overnight/feature_executor.py:381` — `load_state(config.overnight_state_path)` fresh disk read
- `feature_executor.py:464-466` flags a "concurrency hazard: two concurrent features on the repair path may race on overnight-state.json" (pre-existing, unrelated)

**Verified**: If runner.py calls `save_state(filtered_state, ...)` between startup load and round-loop entry, the atomic os.replace propagates to all subsequent `load_state` calls in runner.py (line 2151), orchestrator.py (line 182), feature_executor.py (line 381). **The persist-via-save_state mechanism mechanically works.**

**However**: there is no "un-filter" path. If overnight persists `state.features` minus Feature X (because X has a live interactive owner at startup), and X's owner exits 10 minutes later, the next runner restart loads the persisted-filtered state (X missing) — the scan re-runs and sees no interactive.pid for X, but X is not in `state.features` to re-add. **The filter leaks features permanently.** Mitigation: the scan must also be capable of *re-adding* features to `state.features` if they exist in `cortex/backlog/` (or another source-of-truth list) but not in current `state.features` AND have no live interactive owner. Equivalent: build the filtered list as `master_plan.features - scan_filtered_features`, not `state.features - scan_filtered_features`. See OQ-F.

### Worktree CWD vs main-repo write path (critical concern)

Under DR-3 Variant A (active session `cd`s into worktree), the lifecycle skill's CWD is `$TMPDIR/cortex-worktrees/{slug}/`. Per CLAUDE.md and ADR-0003, `cortex init` registers the repo's `cortex/` umbrella path in `~/.claude/settings.local.json::sandbox.filesystem.allowWrite`. **But the registration is keyed to the original repo path** — does it match writes from the worktree CWD?

- Sandbox `allowWrite` paths in `~/.claude/settings.local.json` are absolute paths. The cortex umbrella registered is the **main repo's** `cortex/` path (e.g., `/Users/.../Workspaces/cortex-command/cortex/`).
- A worktree at `$TMPDIR/cortex-worktrees/{slug}/cortex/lifecycle/{slug}/interactive.pid` is a **different absolute path** — likely NOT covered by the existing `allowWrite` entry.
- **However**, the lock file should be written to the **main repo's** `cortex/lifecycle/{slug}/interactive.pid` (NOT the worktree's), so that the overnight runner (CWD=main repo) can scan it. This means the write site must absolutize the path to the main repo via `_resolve_user_project_root()` (`cortex_command/common.py:55-103`) — not use a CWD-relative path.

**Conclusion**: The interactive lock path must be derived from the **main repo root**, not the worktree CWD. The Python helper resolves this via `_resolve_user_project_root()` (which terminates on `.git` — a worktree's `.git` file resolves up to the main repo via its `gitdir:` pointer). Need to verify the resolver behaves correctly under Variant A's worktree CWD — see OQ-G.

### Existing patterns to mirror

- **`runner.pid` IPC contract** (`pipeline.md:151`): JSON `{schema_version, magic, pid, pgid, start_time, session_id, session_dir, repo_path}`, mode 0o600, atomic write, PID-reuse defense via `psutil.Process.create_time()` ±2s.
- **`verify_runner_pid`** (`ipc.py:392-437`): canonical liveness pattern with start_time check.
- **`install_guard.check_in_flight_install_core`** (`install_guard.py:150-248`): canonical read-pointer → read-runner.pid → verify-liveness sequence with self-heal-on-stale.
- **`scheduled-launches.lock`** (`pipeline.md:157`): `fcntl.LOCK_EX` precedent for serializing critical sections.

### Existing skill prose for overnight-active rejection (§1a.iii typo)

`skills/lifecycle/references/implement.md` §1a.iii step 3 references `cat {session_dir}/.runner.lock` but the actual file per `ipc.py:284` is `runner.pid`. This ticket should fix the typo in §1a.iii AND mirror the corrected pattern in the new interactive-path guard.

## Web Research

### Claude Code `CLAUDE_CODE_SESSION_ID` (authoritative)

From `anthropics/claude-code/CHANGELOG.md`:

```
## 2.1.132
- Added `CLAUDE_CODE_SESSION_ID` environment variable to the Bash tool subprocess environment, matching the `session_id` passed to hooks
```

Documented at https://code.claude.com/docs/en/env-vars. Key behaviors:
- **Rotates on `/clear`** — new session = new ID
- **Survives `--resume`** — same session reattaches with same ID
- Set in Bash + PowerShell tool subprocesses
- Matches the `session_id` JSON field passed to hooks (`hooks/cortex-scan-lifecycle.sh:8`'s `jq -r '.session_id'` extraction)

### macOS sandbox-safe PID identification

From `anthropic-experimental/sandbox-runtime` source + sandbox documentation:
- `getppid()` always allowed — no Seatbelt gate
- `(allow process-info* (target same-sandbox))` — psutil works for same-sandbox children, NOT for cross-sandbox parent (claude CLI runs outside the sandbox)
- `(allow signal (target same-sandbox))` — same-sandbox kill OK; cross-sandbox kill 0 likely succeeds at POSIX layer but unverified
- `kern.boottime` sysctl in default allowlist — useful for boot-correlation
- IPC files under `~/.local/share/` or `~/cortex-command/lifecycle/` (allowWrite paths) work

### Skip-vs-reject prior art

- **Jenkins Lockable Resources `skipIfLocked: true`** — silent skip, build marked successful but body unexecuted (https://plugins.jenkins.io/lockable-resources). Direct prior art for the inverse-scan skip semantics.
- **git's `.lock` pattern** — file existence is the lock; no PID; manual `rm` for stale recovery.

### Key references

- https://code.claude.com/docs/en/env-vars
- https://code.claude.com/docs/en/sandboxing
- https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md (CLAUDE_CODE_SESSION_ID v2.1.132)
- https://github.com/anthropic-experimental/sandbox-runtime
- https://github.com/anthropics/claude-agent-sdk-python/issues/573 (CLAUDECODE=1 inheritance bug)
- https://docs.python.org/3/library/fcntl.html
- https://plugins.jenkins.io/lockable-resources (skipIfLocked)

## Requirements & Constraints

### Relevant clauses (re-verified from loop-back round)

**`cortex/requirements/project.md`**:
- Line 42: "Destructive operations preserve uncommitted state: Cleanup scripts ... SKIP on uncommitted state."
- Line 38: "Graceful partial failure: ... fails gracefully — completing the rest."
- Line 15: "Failure handling: Surface failures in the morning report; keep working unless blocked."
- Line 41: "Defense-in-depth for permissions: settings.json ships minimal allow, comprehensive deny, sandbox on. ... Overnight runs --dangerously-skip-permissions; sandbox is the critical surface."

**`cortex/requirements/pipeline.md`**:
- Line 21/126: "All state writes are atomic (tempfile + os.replace())."
- Line 127/134: "State file reads are not protected by locks by design. ... forward-only transitions make this safe. This is a permanent architectural constraint."
- Line 151: `runner.pid` IPC contract (JSON schema with start_time, mode 0o600, atomic write).
- Line 152: `~/.local/share/overnight-sessions/active-session.json` host-global pointer schema.
- Line 28: cancel-side PID verification uses `psutil.Process.create_time` ±2s of recorded start_time.
- **Line 130 (DIRECTLY RELEVANT)**: "When the orchestrator resolves an escalation or makes a non-obvious feature selection decision (e.g., skipping a feature, reordering rounds), the relevant events.log entry should include a `rationale` field."
- Line 40: "One feature's failure does not block other features in the same round (fail-forward model)."

**`cortex/requirements/multi-agent.md`**:
- Line 23: `CORTEX_SANDBOX_SOFT_FAIL=1` precedent for sandbox-runtime regression env var.
- Line 77: Worktrees at `$TMPDIR/cortex-worktrees/{feature}/` — **transient**; cortex/ umbrella state lives under main repo root.
- Line 52: Pre-deploy no-active-runner check consults active-session.json — operator discipline today.

**`cortex/requirements/observability.md`**:
- Line 117: "Stale PID in `.runner.lock`: ... `kill -0` returns non-zero; status CLI reports 'dead (stale PID)' rather than 'alive'."
- Lines 9/93: Statusline/dashboard are read-only.
- Line 22/91: Statusline < 500ms.

### ADRs

- **ADR-0001 (file-based state)**: lock files plain JSON; no daemon/database.
- **ADR-0002 (CLI wheel)**: if active-session.json or runner.pid schema is extended, bump M.m schema floor.
- **ADR-0003 (per-repo sandbox registration)**: `cortex init` additively registers `cortex/` in `sandbox.filesystem.allowWrite` of main repo. Worktree CWD interaction with this registration is the critical unknown (see Codebase Analysis above + OQ-G).

### Events-registry conventions (`bin/.events-registry.md`)

- Schema: `event_name | target | scan_coverage | producers | consumers | category | added_date | deprecation_date | rationale | owner`.
- Snake_case naming; `<scope>_skipped` pattern for skip events.
- `consumer: TBD` allowed under named-at-the-same-time-as-producer rule.
- Must pass `cortex-check-events-registry --staged` and `--audit` gates.

### Env-var contract status

No requirement declares env-var contracts as stable APIs. `CLAUDE_CODE_SESSION_ID` is documented by Anthropic but not in cortex's "stable contract" tier (runner.pid IPC + wheel/plugin schema are the only formally stable). Treat as **best-available primitive with documented fallback**.

## Tradeoffs & Alternatives

### Dimension 1 — Identity primitive for the lock

- **A. `CLAUDE_CODE_SESSION_ID` from env (PRIMARY) + auxiliary PID+start_time**
  - Pros: Zero sandbox interaction (pure env read); resilient to all wrapper invocations (`sh -c claude`, exec wrappers); survives `--resume`; sandbox-safe by construction; cleanly disambiguates which claude session owns the lock when multiple claude processes run concurrently.
  - Cons: Rotates on `/clear` (a stale-recovery trigger — must be designed for); not declared as a stable Anthropic API (mitigation: fallback path on absence); doesn't directly give a PID for liveness (mitigation: also record auxiliary PID+start_time as best-effort hint).
- **B. PID via psutil-via-uv-run helper**
  - Pros: No env-var dependency; mirrors runner.pid pattern.
  - Cons (load-bearing): under `uv run`, `os.getppid()` returns uv's PID (which exits within milliseconds) — born-stale; PPID walking past immediate parent is sandbox-blocked; helper records uv's PID, not claude's; lock looks perpetually stale, all checks return "stale", infinite re-acquisition loop, bidirectional guard collapses.
- **C. File-existence-only lock (git-style)**
  - Pros: Simplest; no PID/sandbox concerns.
  - Cons: No auto-recovery on Mac-standby/Claude-crash; reverses the spec's self-recovery contract.

**Recommended: A.** The env-var path is the only mechanism that survives all wrapper-invocation paths AND is sandbox-safe AND identifies the right session. The auxiliary PID+start_time is recorded as a hint (cross-checkable but not authoritative — explicitly demoted from "primary key" to "liveness probe").

### Dimension 2 — Liveness check mechanism

Given primary identity = `CLAUDE_CODE_SESSION_ID`:
- **A. Enumerate processes for env-var match** — scan `psutil.process_iter()` for any process whose `environ()` contains `CLAUDE_CODE_SESSION_ID=<stored>`. Cons: `Process.environ()` requires entitlements on macOS, raises `AccessDenied` frequently.
- **B. Auxiliary PID + start_time check** — `os.kill(stored_pid, 0)` AND `psutil.Process(stored_pid).create_time()` matches stored start_time ±2s. Cons: stored_pid may be uv (born-stale); cross-sandbox kill 0 unverified.
- **C. Sidecar file written by long-lived claude process** — claude itself writes a session-PID file at `~/.claude/sessions/{session_id}/` (if such a file exists) and the helper reads it. Cons: assumes Claude Code maintains such a file (undocumented).

**Recommended: B with caveat.** Use auxiliary PID+start_time as the liveness probe, treating any of (ESRCH, AccessDenied, start_time mismatch, EPERM) as "stale or unverifiable → recover." The stored PID may be the immediate Bash-tool parent (zsh under default invocation, claude under non-uv invocation paths) — recorded as best-effort. If the auxiliary check fails BUT the env-var primary key still matches a live claude session (verified by an alternative path), the lock is live but the auxiliary PID is stale. This needs Spec resolution — see OQ-H.

### Dimension 3 — Filter persistence

User preselected save_state. Adversarial findings show this contradicts R10 AND requires un-filter logic.

- **A. save_state + un-filter on every restart** — runner persists filtered `state.features`. On every startup, scan re-derives "what should be in state.features": load `master_plan.features` (NOT current `state.features`), filter by interactive owners, save_state. This is the "rebuild-from-source" pattern.
  - Pros: single source of truth (state.json); existing IPC channel.
  - Cons: R10 must be inverted; un-filter logic must be carefully designed (use master_plan.features as the authoritative source, not state.features).
- **B. Sidecar `skip-features.json`** — separate file, threaded through fill_prompt template and feature_executor config.
  - Pros: preserves R10 invariant; cleaner semantic separation.
  - Cons: new IPC channel; two consumer-side wiring changes; new file to keep in sync.

**Recommended: A** (per user pre-selection, with un-filter logic addressing the leak risk). Concretely: the inverse scan runs at startup; computes `interactive_owned_features = {f for f in master_plan.features if has_live_interactive_owner(f)}`; sets `state.features = [f for f in master_plan.features if f.name not in interactive_owned_features]`; calls `save_state`. R10 inverts to: "scan rebuilds state.features from master_plan.features on every restart; persist via save_state."

### Dimension 4 — Inverse-scan placement (carried from round 1)

**Recommended: A** (runner.py at line 2045-2050, after _start_session, before Phase A auth). Unchanged from round 1.

### Dimension 5 — Lock-vs-worktree-creation ordering (carried from round 1)

**Recommended: A** (after worktree creation, before task dispatch). git layer handles correctness; ordering is about cost-of-losing-race; after-worktree gives the diagnostic event payload the worktree path to reference. Unchanged from round 1.

## Adversarial Review

### Failure modes (load-bearing)

- **F1: `CLAUDE_CODE_SESSION_ID` env-var rotation on `/clear`** — user running `/clear` mid-feature gets new session-id; helper observes mismatch on next preflight read. Decision needed: is session-id in the verification predicate? If yes: `/clear` is a stale-recovery trigger; re-acquire under new id. If no: session-id is recorded but only PID+start_time gates liveness; `/clear` is harmless. See **OQ-A**.

- **F2: Cross-sandbox `kill 0` semantics unverified** — Web research says POSIX kill 0 typically succeeds cross-sandbox, but `(allow signal (target same-sandbox))` may deny. Treat `EPERM` as "process exists" (conservative; mirrors `daytime_pipeline.py:86-104`). Acceptance criterion needs a sandbox-probe before merge.

- **F3: `psutil.create_time()` precision drift** — Linux clock-ticks vs macOS µs-precision; ±2s tolerance may be wider than fast-PID-reuse on fork-heavy systems but tighter than NTP-step-during-Mac-sleep. Inherit runner.pid's ±2s by precedent; document explicitly as "best-known compromise" rather than "defeats PID reuse."

- **F4: Recorded PID identity under uv-run wrapper** — born-stale problem. Mitigation: env-var is the primary key; recorded PID is auxiliary best-effort. Acceptance criterion must verify under the actual sandboxed `uv run` invocation chain.

- **F5: save_state un-filter requirement** — without un-filter logic, features leak permanently. Mitigation: rebuild state.features from master_plan.features on every restart (Dimension 3 Recommended).

- **F6: Worktree CWD vs main-repo write path** — interactive session's CWD is the worktree under Variant A; lock must be written to main-repo's cortex/lifecycle/{slug}/. Path resolution via `_resolve_user_project_root()`. Sandbox allowWrite registration is keyed to main-repo absolute path — needs verification that worktree-CWD writes to main-repo absolute path are allowed. See **OQ-G**.

- **F7: Sub-agent context for lock acquisition** — `CLAUDE_CODE_SESSION_ID` not explicitly forwarded by `dispatch.py:534-548`. Sub-agents either inherit parent's session-id (wrong owner identity) or see nothing. Spec should declare: sub-agents do NOT participate in the interactive-lock contract (the parent session's lock implicitly covers them). See **OQ-B**.

- **F8: Magic-string DoS vector** — user can spoof an `interactive.pid` to deny overnight. Acceptable risk: same surface as any cortex/-area artifact spoofing; not a new vector created by this ticket.

- **F9: TOCTOU between scan and feature dispatch** — overnight scan sees no live owner at T; interactive owner re-acquires at T+1; feature_executor dispatches at T+N. Mitigations: (a) accept blast radius; (b) add per-feature gate in feature_executor (defense-in-depth; spec Non-Requirements out-of-scoped this previously). See **OQ-I**.

- **F10: `Path("cortex/lifecycle").glob(...)` is CWD-relative** — if runner.py's CWD has drifted, scan reads wrong directory. Mitigation: use `_resolve_user_project_root() / "cortex/lifecycle"` for the scan base.

- **F11: SessionEnd hook on SIGKILL** — does not fire on hard kill. Mitigation: stale-PID detection via start_time-mismatch is the load-bearing recovery path; SessionEnd is opportunistic-cleanup-only. Spec should declare this explicitly.

## Open Questions

- **OQ-A**: Is `CLAUDE_CODE_SESSION_ID` in the liveness-verification predicate? Two paths: (i) verify (then `/clear` triggers stale-recovery; same claude process re-acquires); (ii) record-but-not-verify (then `/clear` is harmless; PID+start_time gate liveness). **Spec must decide.**

- **OQ-B**: Sub-agent context — do dispatched sub-agents (where `CLAUDECODE` is cleared by `dispatch.py:534-548`) participate in the interactive-lock contract? Recommended: NO — sub-agents inherit parent's lock claim implicitly; spec declares sub-agents as out-of-scope for direct lock acquisition. **Spec must declare.**

- **OQ-G**: Worktree CWD sandbox-write — verify that under Variant A (active session `cd`s into worktree), writes to `_resolve_user_project_root() / "cortex/lifecycle/{slug}/interactive.pid"` (main-repo absolute path, NOT worktree-relative) succeed under default sandbox. May require empirical seatbelt-probe; alternative: write lock to a sandbox-guaranteed path like `~/.local/share/cortex-interactive/{repo_id}/{slug}.pid`. **Verify in Spec or empirically.**

- **OQ-H**: Liveness probe semantics — if auxiliary PID+start_time check fails (uv's PID died) but env-var primary key suggests session still alive, what's the verdict? Recommended: treat env-var as authoritative; auxiliary PID is best-effort hint that does NOT downgrade verdict to "stale" if it fails. Spec needs to specify the predicate composition. **Spec must specify.**

- **OQ-I**: TOCTOU between scan and dispatch — accept blast radius (interactive collision discovered at create_worktree time) or add per-feature gate in feature_executor (defense-in-depth, previously out-of-scoped)? **Spec must decide.**

## Considerations Addressed

- **Investigate Claude Code's environment-variable contract for spawned subprocesses**: Found and verified `CLAUDE_CODE_SESSION_ID` (v2.1.132+) as the primary documented mechanism. Listed full env-var inventory observed empirically. Identified that `CLAUDECODE` is cleared by `dispatch.py:534-548` but `CLAUDE_CODE_SESSION_ID` is not in the forward list (sub-agent behavior undefined — OQ-B).

- **Reproduce the Bash-tool subprocess parent chain empirically under default macOS Seatbelt sandbox**: Empirically observed: bash defaults to zsh; `$PPID` from zsh = claude's PID (PPID=40547); `ps` blocked; sysctl walks blocked beyond immediate parent; under `uv run`, the chain is `claude → zsh → uv → python` and helper's `os.getppid()` returns uv's PID (born-stale problem — Dimension 1B rejected). Conclusion: env-var is the only reliable identification primitive.

- **Trace runner.py's startup-to-round-loop state mutation flow**: Verified line refs (2032 startup load, 2120 round-loop entry, 2151 reload). `load_state` is fresh `read_text` every call (no caching). `save_state` is atomic os.replace. If runner calls save_state between startup and round-loop, the reload at 2151 sees it. Verified orchestrator.py:182 and feature_executor.py:381 also load_state from disk. Persist-via-save_state mechanically works; un-filter logic needed to avoid permanent feature leak (Dimension 3 Recommended).

- **Confirm orchestrator.py and feature_executor.py state-read paths**: Both use fresh `load_state` from `config.overnight_state_path`. No shared memory; no fd caching. Save_state mutations propagate cleanly across process boundaries. Sidecar (Tradeoffs Agent's alternative B) is a valid alternative but contradicts the user's pre-selection; Recommended A is save_state + un-filter logic.
