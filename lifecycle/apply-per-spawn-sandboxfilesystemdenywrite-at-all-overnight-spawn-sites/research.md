# Research: Apply real OS-level write-sandbox enforcement at every overnight Claude spawn site

**Topic**: Apply real OS-level write-sandbox enforcement at every overnight Claude spawn site — orchestrator spawn (broad deny on home-repo + cross-repo `.git/refs/heads/*`), per-feature dispatch (narrow allow-list, fixing the current silent-no-op shape at `dispatch.py:546`), and the cross-repo allowlist-inversion bug at `feature_executor.py:603` — so the session-1708 `cd $REPO_ROOT && git commit` Bash-tool escape is blocked at the kernel layer.

**Lifecycle slug**: `apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites`
**Tier**: complex | **Criticality**: critical | **Backlog**: #163 (parent epic #162)
**Discovery research**: `research/sandbox-overnight-child-agents/research.md` (DR-1 r3, DR-2, DR-3, DR-6 r2, DR-7 r3, R1-A1, R4-B, R2-C)

---

## Codebase Analysis

### Files that will change (with paths and line numbers)

**Modified:**
- `cortex_command/overnight/runner.py:930-974` — `_spawn_orchestrator()`. Currently issues `claude -p ... --dangerously-skip-permissions --max-turns N --output-format=json` with **no** `--settings` flag. Lines 944-963 are the surgical site for adding a `--settings <value>` argument. The function signature (`filled_prompt, coord, spawned_procs, stdout_path`) needs to accept `state` (to enumerate cross-repo features for the deny set) and `session_dir` (to scope tempfile lifetime alongside other session artifacts). Cleanup hook at `runner.py:2417-2426` (the `finally:` block in the main loop iterating `spawned_procs` to kill any still-alive PGIDs).
- `cortex_command/pipeline/dispatch.py:536-549` — the `_write_allowlist` construction site. Currently writes settings into `ClaudeAgentOptions(settings=_worktree_settings, …)` (line 567), passing JSON as a stringly-typed parameter through the SDK rather than an OS file. **Critical mechanism note**: the SDK at `claude_agent_sdk/_internal/transport/subprocess_cli.py:111-163` accepts `settings` as either a JSON string OR a filepath, distinguished by the `startswith("{") and endswith("}")` heuristic, then concatenates with sandbox settings (if present) and passes the result to `claude --settings <value>` as a CLI arg. So the SDK and CLI paths land in the same `--settings` flag — merge semantics ARE identical because the SDK is a thin shim over the CLI flag.
- `cortex_command/overnight/feature_executor.py:603-604` — the `dispatch_task(integration_base_path=Path.cwd())` call. The bug is unconditional `Path.cwd()`, which uses the **home-repo cwd** even for cross-repo features. `repo_path` IS already in scope on line 604 (passed as `repo_root`). Fix is conditional: same-repo → `Path.cwd()`; cross-repo → `state.integration_worktrees[_normalize_repo_key(str(repo_path))]`. Use the canonical normalization helper `_effective_merge_repo_path` in `outcome_router.py:115-195`, **not** a re-implementation.
- `cortex_command/init/settings_merge.py:139-202` (`register()`) — currently writes the **correct** shape `sandbox.filesystem.allowWrite` (lines 184-186). Per `requirements/project.md:26`, this is the user-scope additive-merge layer. **No change to this file** — it is the canonical reference shape. The dispatch.py shape (`sandbox.write.allowOnly`) is the OUTLIER.

**Created (new):**
- A new helper module — likely `cortex_command/overnight/sandbox_settings.py` — to centralize tempfile lifecycle, broad-deny construction, and per-feature narrow-allow construction. There is no existing module for this; tempfile patterns are scattered.
- A new test file `tests/test_runner_sandbox.py` (or `cortex_command/overnight/tests/test_sandbox_settings.py`) for behavior-level tests including kernel-EPERM acceptance.

### Relevant existing patterns

**Tempfile lifecycle.** No existing pattern matches "tempfile that lives for the duration of a subprocess." Closest analogues:
- `cortex_command/common.py:498-522` — `atomic_write()` uses `tempfile.mkstemp()` + `os.replace()`. The tempfile is short-lived (rename onto target), not spawn-scoped.
- `cortex_command/dashboard/app.py:237` — `atexit.register(lambda: _pid_file.unlink(missing_ok=True))` — atexit is the closest precedent for spawn-scoped tempfile cleanup.
- `cortex_command/overnight/ipc.py:164-175` — `delete=False` + manual cleanup pattern.

**Sandbox JSON shape — three different shapes in the codebase today:**
- `cortex_command/init/settings_merge.py:184-197`: `sandbox.filesystem.allowWrite` (CORRECT — matches Claude Code documented schema)
- `cortex_command/pipeline/dispatch.py:543-549`: `sandbox.write.allowOnly` (WRONG — granular shape, undocumented as a settings input, structurally a silent no-op per the ticket)
- System-reminder sandbox JSON at top of conversation: `sandbox.filesystem.{read,write}.allowOnly` etc. (yet another internal shape)

The shape divergence is itself a load-bearing finding — the spec must standardize on `sandbox.filesystem.{allowWrite,denyWrite}` per Claude Code's canonical schema.

**Dispatch flow `dispatch_task` callers:**
- `cortex_command/overnight/feature_executor.py:603` (the call site with the bug)
- `cortex_command/pipeline/retry.py` (retry loop wrapper)
- `repo_root` keyword is already plumbed in elsewhere (line 487 in feature_executor.py: `repo_root=repo_path` for the repair path).

**Cross-repo state machinery.** `cortex_command/overnight/state.py:228-230` documents `integration_worktrees: Keys are absolute repo paths (strings); values are absolute worktree paths`. `OvernightFeatureStatus.repo_path: Optional[str]` (line 135) is `None` for home-repo features and a string path for cross-repo features. `outcome_router.py:115-195` (`_effective_merge_repo_path`) is the canonical pattern for `repo_path → worktree` resolution; it normalizes via `_normalize_repo_key()`, checks the cache, and lazily creates if missing.

**Default-branch resolution.** No helper exists. Closest reference is `runner.py:489` (`["git", "symbolic-ref", "--quiet", "HEAD"]`). Net-new wiring required.

**Spawn-site dependencies.** `_spawn_orchestrator` takes `coord` (RunnerCoordination, holds state_lock) and `spawned_procs` (list mutated to register the proc for crash-path cleanup at line 2420). Tempfile path attachment options: (a) extend tuple to `(proc, label, tempfile_path)`, or (b) use `atexit.register` patterned on `dashboard/app.py:237`. Crash paths (SIGKILL, OOM) are not covered by atexit alone — need a startup-scan to clean stale `/tmp/cortex-sandbox-*.json`.

### Conventions to follow

- **Atomic writes** (`requirements/pipeline.md:21,126`): tempfile + `os.replace()` — no partial-write corruption. The per-spawn settings tempfile must follow this pattern even though it's read-only after write.
- **Settings-merge discipline** (`cortex_command/init/settings_merge.py:174-202`): `cortex_command.common.atomic_write` (tempfile + `os.replace` + `durable_fsync`); lock discipline via `fcntl.flock` on a sibling lockfile.
- **Pre-deploy no-active-runner check** (`requirements/multi-agent.md:51`): sandbox-related runner edits must be deployed when no overnight session is active.
- **Doc-source ownership** (`CLAUDE.md:50`): `docs/overnight-operations.md` owns orchestrator behavior + threat-model boundary; `docs/pipeline.md` owns dispatch.py shape; `docs/sdk.md` cross-links rather than duplicates.
- **Test patterns**: `cortex_command/pipeline/tests/test_dispatch.py:267-639` is the active sandbox test file — JSON-shape-only assertions, no kernel-enforcement tests, no real-claude-subprocess sandbox tests, no `--settings <tempfile>` fixture exists. Behavior-level testing is greenfield.

### Pinned versions / tooling

- `pyproject.toml:10`: `claude-agent-sdk>=0.1.46,<0.1.47` (locked at 0.1.46 in `uv.lock:112-124`).
- No `@anthropic-ai/sandbox-runtime` reference anywhere in `pyproject.toml`, `uv.lock`, `package.json`, or docs.
- claude CLI is PATH-lookup (`claude_path = "claude"`), no version pinning.
- Active dev environment: Darwin 25.4.0 (macOS Seatbelt). Parent epic #162 explicitly drops Linux scope.

---

## Web Research

### Schema confirmation

`@anthropic-ai/sandbox-runtime` (https://github.com/anthropic-experimental/sandbox-runtime) and Claude Code sandboxing docs (https://code.claude.com/docs/en/sandboxing) confirm the schema is **only** `filesystem.{allowWrite, denyWrite, allowRead, denyRead}`. The granular `write.{allowOnly, denyWithinAllow}` shape that `dispatch.py:546` uses today is **not** a documented settings-input shape — confirming the ticket's silent-no-op claim. Per the runtime README: *"By default, the sandbox runtime looks for configuration at `~/.srt-settings.json`. You can specify a custom path using the `--settings` flag."*

### `--settings` flag semantics

Per Claude Code CLI reference (https://code.claude.com/docs/en/cli-reference): `--settings` accepts **either a path or a JSON string inline** — *"Path to a settings JSON file or a JSON string to load additional settings from"*, example `claude --settings ./settings.json`. There is also `--setting-sources` (`user,project,local`) for limiting which scopes load.

### Multi-scope merge

Per Claude Code settings docs (https://code.claude.com/docs/en/settings): precedence (highest → lowest) is **Managed → CLI args → `.claude/settings.local.json` → `.claude/settings.json` → `~/.claude/settings.json`**. Critically: *"Array settings merge across scopes (concatenated and deduplicated), not replaced."* And from sandboxing docs: *"When `allowWrite` (or `denyWrite`/`denyRead`/`allowRead`) is defined in multiple settings scopes, the arrays are merged, meaning paths from every scope are combined, not replaced."*

This means a per-spawn `--settings` carrying ONLY the deny set is sufficient — you do not need to re-state user/project allows. The merge happens runtime-side.

### Precedence: `denyWrite > allowWrite`

Documented verbatim in the runtime README and sandboxing docs: *"Precedence is intentionally opposite for reads vs writes: allowRead overrides denyRead, while denyWrite overrides allowWrite."* And: *"denyWrite creates exceptions within allowed paths (deny takes precedence)."* The ticket's central correctness pivot is documented and stable.

### `failIfUnavailable: true` semantics + open bugs

Documented: *"By default, if the sandbox cannot start (missing dependencies or unsupported platform), Claude Code shows a warning and runs commands without sandboxing. To make this a hard failure instead, set `sandbox.failIfUnavailable` to `true`."*

**Open Anthropic bugs to be aware of:**
- https://github.com/anthropics/claude-code/issues/53085 — regression in 2.1.120 where `--continue/--resume` fails with "sandbox required but unavailable" even when `sandbox.enabled=false`.
- https://github.com/anthropics/claude-code/issues/53683 — "Sandbox unavailable error when sandbox.failIfUnavailable is enabled."
- https://github.com/anthropics/claude-code/issues/53615 — `claude --continue` aborts on Linux 2.1.120.

cortex's `_spawn_orchestrator` at `runner.py:946-963` does NOT use `--continue` or `--resume`, so it's not directly affected by #53085. But per-feature dispatches via the SDK may use `resume_session` semantics internally during retry flows — spec must verify.

### macOS Seatbelt EPERM signal

Verified across multiple sources (aminroosta.github.io, bdash.net.nz, michaelneale/agent-seatbelt-sandbox): *"violating a sandbox policy results in the system call... failing with EPERM (operation not permitted)"*; *"errno: 1 corresponds to EPERM (Operation not permitted)"*; *"This is kernel-enforced — cat, python, node, any process gets Operation not permitted."*

**Empirical-test assertion shape: expect `errno == 1` (EPERM) and stderr containing `"Operation not permitted"`.** Subprocesses inherit the Seatbelt profile (kernel-enforced); trace propagation differs but enforcement does propagate.

### Issue #29048 — Bash-vs-Write/Edit asymmetry

https://github.com/anthropics/claude-code/issues/29048 confirms the ticket's threat-model carve-out is real Anthropic-acknowledged behavior. Per sandboxing docs: *"Built-in file tools: Read, Edit, and Write use the permission system directly rather than running through the sandbox."* Closed as duplicate. The ticket scope is correctly limited to **Bash-tool Write escapes** (e.g. `cd $REPO_ROOT && git commit`); Write/Edit tool escapes need a separate permission-rules-based defense layer.

### Documented escape hatches (ticket gaps)

Per sandboxing docs:
- `allowUnsandboxedCommands: false` — *"When a command fails due to sandbox restrictions...Claude is prompted to analyze the failure and may retry the command with the `dangerouslyDisableSandbox` parameter."* For the threat model, the per-spawn settings MUST set `allowUnsandboxedCommands: false`, otherwise Claude can self-route around the deny.
- `enableWeakerNestedSandbox: false`, `enableWeakerNetworkIsolation: false` — additional documented escape hatches; per-spawn settings should explicitly set both to false.

### Subagent / child-process inheritance

Per sandboxing docs: *"These OS-level restrictions ensure that all child processes spawned by Claude Code's commands inherit the same security boundaries."* Bash subprocess inheritance is explicit. Task-tool spawned subagents inherit Seatbelt profile (process-level), but if the orchestrator's prompt asks Claude to spawn `claude` subprocesses via Bash for nested tasks, those processes load their OWN settings stack — they would NOT include the orchestrator's per-spawn `--settings` tempfile unless cortex threads it through (currently almost certainly not).

### Prior art

- Deno `--allow-write[=path1,path2,...]` — explicit allowlist, no per-process tempfile.
- Node 20+ `--experimental-permission` + `--allow-fs-write` — opt-in, in-process check, **does not control child processes**.
- `node-safe`: *"uses native sandboxing features baked into the OS, with restrictions that apply to all child processes as well"* — the load-bearing prior-art lesson: **OS-level kernel enforcement covers child processes; in-process JS/Py checks do not**.

---

## Requirements & Constraints

### Project-level (`requirements/project.md`)

- **Defense-in-depth for permissions** (line 34): *"The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution."* — **This ticket IS the work that hardens the load-bearing critical security surface.**
- **Per-repo sandbox registration** (line 26): cortex-init writes `sandbox.filesystem.allowWrite` for `lifecycle/` into `~/.claude/settings.local.json`. Per-spawn deny-set must coexist via documented `denyWrite > allowWrite` precedence.
- **Distribution** (line 7, 55; CLAUDE.md:5,22): CLI-first via `uv tool install`; plugins via `/plugin install`. Sandbox config cannot ship via plugin manifest (only `agent`/`subagentStatusLine` keys allowed) — DR-2's `--settings` distribution is the only feasible layer.
- **Destructive-state preservation** (line 36): cleanup scripts SKIP rather than destroy on unexpected state. Tempfile cleanup must be defensively wired.

### Pipeline-level (`requirements/pipeline.md`)

- **Atomic writes** (lines 21, 126): tempfile + `os.replace()` — applies to per-spawn settings tempfile.
- **Dry-run test affordance** (line 27): `cortex overnight start --dry-run` has byte-identical stdout snapshot test (`tests/fixtures/dry_run_reference.txt`). Sandbox-tempfile creation may interact — must verify snapshot doesn't regress.

### Multi-agent (`requirements/multi-agent.md`)

- **bypassPermissions hardcoded** (line 23): cortex cannot remove `--dangerously-skip-permissions`; sandbox is layered UNDER, not in place of.
- **`$TMPDIR` worktree placement** (line 76): cross-repo worktrees go to `$TMPDIR` to avoid sandbox restrictions. Cross-repo allowlist fix at `feature_executor.py:603` must respect this.
- **Pre-deploy no-active-runner** (line 51): sandbox-related runner edits must be deployed when no overnight session is active.

### Observability (`requirements/observability.md:79-87`)

`settings.local.json` mutations: *"Existing `sandbox.filesystem.allowWrite` entries in `settings.local.json` are preserved (arrays replace, not merge)"* — this is **about cortex's tool that updates `settings.local.json`** (file-rewrite semantics), distinct from Claude Code's runtime multi-scope merge (which DOES merge arrays per Web research). Two different layers; not a contradiction.

### CLAUDE.md governance

- **MUST-escalation policy** (lines 52-60): governs MUST/CRITICAL/REQUIRED prose in user-facing rules; NOT sandbox runtime config flag values like `failIfUnavailable: true`. Policy not implicated by config-flag values, but applies to any directive language added to spec or docs.
- **Doc-source convention** (line 50): `docs/overnight-operations.md` owns threat-model + orchestrator behavior; `docs/pipeline.md` owns dispatch.py shape; cross-link, don't duplicate.
- **100-line cap** (line 68): CLAUDE.md is at 68 lines; new policy entry could trigger extraction to `docs/policies.md` (does NOT yet exist).

### Existing doc state

- `docs/overnight-operations.md:23`: currently says *"spawn orchestrator agent (--max-turns 50, no permissions sandbox)"* — needs update post-V1.
- `docs/overnight-operations.md:547-552`: names sandbox as "the critical security surface" but documents no per-spawn enforcement today. Threat-model boundary section currently says nothing about Bash-vs-Write/Edit asymmetry.
- `docs/pipeline.md`: NO documentation of `dispatch.py`'s current `sandbox.write.allowOnly` shape — nothing to "update," only to add (post-conversion narrative).
- `docs/sdk.md:199`: *"The sandbox write allowlist restricts which file paths the SDK itself can write to, but it does not constrain what a Bash subprocess can do."* — **WRONG post-V1**. Per #29048 inversion: Bash IS sandboxed; Write/Edit is the bypass. Needs corrective edit.

### Discovery research load-bearing decision records

From `research/sandbox-overnight-child-agents/research.md`:
- **DR-1 r3 (schema)**: `sandbox.filesystem.{allowWrite,denyWrite}` is the only consumed input shape; granular `write.{allowOnly,denyWithinAllow}` is runtime-internal IR. dispatch.py:546's granular write IS structurally a silent no-op today.
- **DR-2 (distribution)**: per-spawn `--settings <path>` JSON is the canonical mechanism; plugin manifests infeasible; managed-settings too heavyweight. No `--sandbox` CLI flag in v2.1.126 — activation is `sandbox.enabled: true` in JSON.
- **DR-3 (V1 scope)**: cross-repo IS in V1 scope. Enumerate via `state.features.values()` filtered by non-None `repo_path`; cache in state.
- **DR-6 r2 (per-feature audit)**: V4 (folded into #163) addresses two compounded bugs: (a) `dispatch.py:546` granular silent-no-op conversion, (b) `feature_executor.py:603` cross-repo allowlist inversion.
- **DR-7 r3 (acceptance test gate)**: V1 AC = per-spawn `--settings` denying `<home_repo>/.git/refs/heads/main` blocks Bash-tool `echo > <ref>` with kernel EPERM under `claude -p ... --dangerously-skip-permissions`. Test runs in `just test`.
- **R1-A1, R4-B, R2-C** (critical review): granular shape unverified → DR-1 r3 simplified-shape pivot; cross-repo enumeration must be in V1; threat-model boundary must be explicit.

---

## Tradeoffs & Alternatives

### Alternative A — Managed-settings file at `~/Library/Application Support/ClaudeCode/managed-settings.json`

**Pros**: Highest precedence (cannot be overridden by an attacking agent writing to its own `settings.local.json`); single install eliminates per-spawn JSON construction.

**Cons**: **Scope mismatch is fatal.** Managed-settings is global per host — would apply the deny-set to every Claude Code session the user runs interactively, not just overnight spawns. An interactive `git commit` to main from inside Claude Code would also be blocked, breaking normal developer workflow. Cortex would need conditional deny entries keyed off some env-var or path discriminator, which the managed-settings JSON schema does not support. Writing to `/Library/Application Support/` requires elevated privileges. **DR-2's "too heavyweight" rejection remains structurally load-bearing.** Confirm rejection.

### Alternative B — Plugin-shipped settings via `cortex-overnight-integration`

**Pros**: Clean distribution if feasible.

**Cons**: **Structurally infeasible** — plugin manifests support only `agent` and `subagentStatusLine` keys per Claude Code v2.1.126 plugin reference. Even if feasible, plugin-shipped settings would apply at user/project scope merge time, returning the scope-mismatch problem of Alt A. Confirm DR-2 rejection.

### Alternative C — `--add-dir` removal + permission deny rules

**Pros**: Permission-rule system has more documentation.

**Cons**: **The orchestrator runs `--dangerously-skip-permissions`** which bypasses permission rules entirely. Per #29048 and Anthropic's sandbox boundary, sandbox enforcement and permission rules are distinct layers — sandbox survives `bypassPermissions` for Bash; permission rules do not. **Reject.**

### Alternative D — Native OS-sandbox wrapping (`sandbox-exec`)

**Pros**: Independent of Claude Code's sandbox-runtime version drift; orthogonal to `--dangerously-skip-permissions`.

**Cons**: `sandbox-exec` deprecated since macOS 10.15 (still functional as of Darwin 25.4); SBPL profile language undocumented; profiles brittle (misnamed predicate causes silent no-op or full open); duplicates enforcement Claude Code already does internally; loses `failIfUnavailable` semantic and documented merge with cortex-init's user-scope `allowWrite`. **Keep as fallback contingency only** if Claude Code drops `--settings` honoring or changes shape.

### Alternative E — One-time install of deny-set into `~/.claude/settings.local.json`

**Pros**: Reuses existing `settings_merge.py` flock-protected additive merge; no per-spawn tempfile lifecycle.

**Cons**: **Scope mismatch repeats** — user-scope deny-set applies to every Claude Code session, blocking interactive `git commit`. Cortex would need a runtime discriminator (`CORTEX_RUNNER_CHILD=1`), but Claude Code's settings JSON does not support env-var-conditional entries. Forces either (a) constant deny that breaks interactive use, or (b) per-session install/uninstall with race conditions and lifecycle-state-coupling.

### Recommended approach

**The ticket's per-spawn `--settings` approach is correct.** Of the five alternatives:
- A and E both fail on the same axis: user-/system-scope distribution applies the deny-set to interactive sessions, breaking normal workflow. Per-spawn scope is load-bearing.
- B is structurally infeasible today.
- C is bypassed by `--dangerously-skip-permissions` at both spawn sites.
- D is the only viable fallback if Claude Code drops `--settings`, but introduces deprecated tooling.

The approach aligns cleanly with **existing patterns**: `cortex_command/common.py:482` has `atomic_write` (tempfile + `os.replace`); `dispatch.py:567` already passes `settings=` via `ClaudeAgentOptions` (just with the wrong shape — the ticket fixes that); cortex-init's `settings_merge.py` already validates `sandbox.filesystem` shape.

**Fallback contingency**: if Claude Code drops `--settings` honoring or changes the `sandbox.filesystem` shape (DR-7 OQ1 residual risk), Alt D becomes a sibling ticket. Ship #163 as scoped; do not implement D preemptively.

---

## Adversarial Review

### A. Mechanism asymmetry — the SDK and CLI paths land in the same `--settings` flag

**Verified via SDK source** (`claude_agent_sdk/_internal/transport/subprocess_cli.py:111-163, :279-282`): the SDK accepts `settings` as JSON-string-or-filepath via the `startswith("{") and endswith("}")` heuristic, then concatenates with sandbox settings (if present) and passes the result to `claude --settings <value>` as a CLI arg. **Merge semantics are identical** between the SDK and orchestrator paths because the SDK is a thin shim over the CLI flag.

**New failure modes:**
1. **JSON heuristic fragility**: if cortex generates settings JSON with leading whitespace, comment, or wrapper that doesn't `startswith("{")`, the SDK silently treats it as a filepath, hits `Path.exists() == False`, emits a warning, and settings go missing entirely. Spec must mandate `json.dumps()` output without prepending or wrapping.
2. **Path collision**: if cortex constructs a tempfile path containing `{` and `}` (e.g. `/tmp/foo{bar}/...`), the heuristic misroutes. Implausible but documentable.
3. **Sandbox-key-only path**: SDK has a typed `SandboxSettings` field at `types.py:1683` (`options.sandbox`); cortex bypasses this typed field and stuffs sandbox into `settings` directly. Spec should consider migrating to `options.sandbox=` for type safety.

### B. Dispatch.py is currently force-injecting the entire merged project settings

`_load_project_settings` at `dispatch.py:84-112` loads `.claude/settings.json` and `settings.local.json`, deep-merges, and dumps the entire blob via `json.dumps`. If those files contain hooks, env, statusLine, ANY non-sandbox key — they all get re-injected via the SDK's `--settings` arg at the highest precedence layer.

**This means cortex is ALREADY sending the project's full settings stack** (hooks + env + permissions + sandbox.write.allowOnly) on every dispatch. After the shape conversion, the entire project settings.json gets force-applied at top precedence. **Spec must extract only sandbox keys from the merged settings**, not pass the whole blob.

### C. Cross-repo default-branch enumeration: the ticket's framing is broken

`.git/HEAD` is the **currently checked-out branch**, not the **default branch**. Real answers:
- `git symbolic-ref refs/remotes/origin/HEAD` returns the default branch IF `git remote set-head` was run (common but not universal).
- For local-only repos with no `origin`: there is no default-branch concept. Fall back to `init.defaultBranch` config or give up.
- Detached HEAD: `git symbolic-ref HEAD` errors. Must use `--quiet --short` and tolerate non-zero exit.
- Renamed mid-session: stale; session-long cache acceptable.
- Packed refs: `git symbolic-ref` handles transparently.
- Missing `refs/remotes/origin/HEAD`: common on fresh clones — would need `git ls-remote --symref origin HEAD` (network-aware fallback) but overnight context may not have connectivity.

**Reframe**: deny ALL non-current-feature paths under repo roots, then explicitly `allowWrite` the specific feature worktree. The "default branch" framing was always a distractor.

### D. ARG_MAX is fine but `ps`-disclosure is a real concern

macOS `ARG_MAX = 1048576` (1MB), well above 256KB. With 50 cross-repo features × ~200 bytes each = 10KB, nowhere near cap. **However**: long argv values appear in `ps -ef`, leaking the whole sandbox config to any local user — small information disclosure. **Spec should prefer filepath form** with `tempfile.mkstemp(prefix="cortex-sandbox-", suffix=".json")` (0600 perms) over inline JSON for this reason — **contradicting Web-research recommendation #7**.

### E. `failIfUnavailable: true` + open Anthropic regressions

Issue #53085 confirms regression for `--continue/--resume`. cortex's `_spawn_orchestrator` does NOT use these flags (verified runner.py:946-963). **But** per-feature dispatches via the SDK may use `resume_session` semantics during retry/escalation flows. Spec must verify that retried dispatches don't trigger #53085. Issue #53683 is a broader `failIfUnavailable` brittleness.

**Recommendation**: default `failIfUnavailable: false` initially with structured stderr-grep for "sandbox" tokens to detect drop-to-no-sandbox without hard-failing the overnight session. Hard-fail-on-unavailable is too aggressive given open regressions.

### F. `allowUnsandboxedCommands` gap is real and load-bearing

Verified via official sandboxing docs: `dangerouslyDisableSandbox` is a documented per-command parameter Claude can self-emit when it judges a command needs to run outside the sandbox. **Escape hatch is enabled by default.** Without `"allowUnsandboxedCommands": false`, the orchestrator's in-process Claude can prompt-engineer around the deny set on its own initiative — exactly the session-1708 vector but bypassing the deny instead of routing into the wrong CWD.

**This is an acceptance-criterion-level gap**, not a nice-to-have. Spec MUST add `allowUnsandboxedCommands: false`. Also `enableWeakerNestedSandbox: false` and `enableWeakerNetworkIsolation: false`.

### G. Subagent inheritance — verified

Sandboxing docs: *"all child processes spawned by Claude Code's commands inherit the same security boundaries."* Bash subprocess inheritance is explicit. Task-tool spawned subagents inherit the orchestrator's Seatbelt profile via process-tree inheritance. **But** if the orchestrator's prompt template asks Claude to spawn `claude` subprocesses via Bash for nested tasks, those processes load their OWN settings stack and would NOT include the per-spawn `--settings` tempfile unless cortex threads it through (currently does not).

**Spec must answer**: does the orchestrator's prompt template include instructions to thread `--settings` through any nested `claude` calls? Likely needs prompt-template edit.

### H. `Path.cwd()` is just plain wrong

CWD shifts via shell `cd` do NOT propagate to the parent Python process. The `feature_executor.py:603` bug is more boring than it seems: it's "wrong base path resolution at first call" because the runner is launched from a path that may or may not be the integration worktree. Spec uses `state.integration_worktrees[feature]` per Codebase agent recommendation. No "freezing" needed.

### I. Tempfile lifecycle TOCTOU

`tempfile.mkstemp` creates with O_EXCL and 0600, sufficient against concurrent-write attacks. **However**: cleanup at `runner.py:2417-2426` runs only on normal exit. Crash paths (SIGKILL, OOM, kernel panic) leak tempfiles into `/tmp` permanently. Spec must use `tempfile.NamedTemporaryFile(delete=False)` with `atexit`-registered unlink AND a startup-scan that cleans `/tmp/cortex-sandbox-*.json` older than the runner-start timestamp (precedent: `dashboard/app.py:237` PID-file pattern).

### J. Pre-flight test softening

Ticket says "Pre-flight (recommended, non-blocking)." A non-blocking acceptance criterion is not an acceptance criterion. If empirical Seatbelt enforcement testing isn't blocking, the implementation can ship with the deny set being a no-op (e.g., shape regression repeats) and nobody catches it.

**Spec must promote pre-flight to blocking acceptance criterion** OR remove it entirely and rely on a `tests/` integration test that spawns a real `claude -p` with a known-bad write target and asserts EPERM. The middle ground is unstable.

### K. Pre-existing dispatch flows post-shape-conversion may break

If `sandbox.write.allowOnly` is currently a no-op (confirmed), then existing dispatched features write wherever they want. After conversion to `sandbox.filesystem.allowWrite` (real enforcement), **previously silently-passing tests that legitimately wrote to `/tmp/foo`** will now hit EPERM.

**Spec must enumerate test fixtures and feature implementations that write outside the worktree** (e.g., `/tmp/cortex-*` test artifacts, `/var/folders/...` Python tempfile output, `~/.cache/uv` for SDK package install during retry-resolve). The migration is observably-breaking; needs a soak period.

### L. `state.features` population timing

Features are added to `state.features` during planning phase, AFTER orchestrator spawn. **The deny-set computed at orchestrator-spawn-time is stale** for features added later in the session.

**Spec must either** (a) compute the deny-set per-dispatch, not per-orchestrator-spawn, OR (b) mandate that all features are loaded before orchestrator spawn. (b) is structurally false today.

### M. Other claude-spawn sites?

`grep` should verify: any `subprocess.run(["claude", ...])` outside `_spawn_orchestrator`? Spec should audit.

---

## Open Questions

All items resolved or explicitly deferred to Spec. Status of each:

1. **`failIfUnavailable: true` vs `false`** — **Resolved (user, 2026-05-04)**: `failIfUnavailable: true` with a `CORTEX_SANDBOX_SOFT_FAIL=1` kill-switch env var that flips it to `false` on demand. Documented in `docs/overnight-operations.md` so the user has a clean recovery path without code changes if Anthropic regressions #53085/#53683 fire spuriously.

2. **Tempfile vs inline JSON for `--settings`** — **Resolved (user + critical-think, 2026-05-04)**: filepath via `tempfile.mkstemp(prefix="cortex-sandbox-", suffix=".json")` (0600 perms). Rationale: (a) the `@anthropic-ai/sandbox-runtime` README documents `~/.srt-settings.json` (a filepath) as the default convention — Anthropic has no "officially recommended" stance between filepath and inline, but the documented default form is filepath; (b) cortex-init already uses filepath form for `~/.claude/settings.local.json`; (c) `ps -ef` argv-disclosure hygiene per Adversarial D. User approved "I'm okay with the tempfile" with delegation to think critically about Anthropic-recommended form.

3. **Pre-flight test status** — **Resolved (user, 2026-05-04)**: promote to blocking acceptance criterion. Implementation cannot merge until the pre-flight test runs in a clean non-sandboxed terminal and asserts kernel EPERM. The blocking `tests/test_runner_sandbox.py` kernel-EPERM tests in `just test` STILL run as a separate gate; pre-flight verifies end-to-end mechanism before any code change ships.

4. **Cross-repo default-branch reframe** — **Deferred to Spec**: spec applies the reframe (deny entire repo root; allowWrite only the specific feature worktree) without asking the user. The ticket's `git symbolic-ref refs/remotes/origin/HEAD` + `.git/HEAD` fallback misframes the problem — `.git/HEAD` is current-branch not default-branch; the fallback chain has too many holes to reliably resolve "the default branch" across local-only repos, fresh clones, and detached HEAD. The reframe sidesteps the entire branch-resolution problem.

5. **Allowlist-extraction from project settings** — **Deferred to Spec**: spec specifies extraction logic. Currently `dispatch.py:84-112` force-injects the entire merged project settings.json (hooks, env, permissions, statusLine) as `--settings` at top precedence. Spec extracts only sandbox keys (`sandbox.*` subtree) after deep-merge.

6. **Pre-existing flow audit** — **Deferred to Spec**: spec enumerates test fixtures and feature implementations that write outside the worktree (`~/.cache/uv`, `/var/folders/...`, `/tmp/cortex-*`, etc.) and either widens the per-feature `allowWrite` set to include them or migrates writers to use worktree-internal paths. Migration is observably-breaking; spec defines a soak/rollback window.

7. **`state.features` timing** — **Resolved by research**: spec adopts (a) per-dispatch deny-set recompute. (b) "all features loaded pre-spawn" is structurally false today (planning phase populates state.features after orchestrator spawn). The deny-set MUST be recomputed at each dispatch site, not frozen at orchestrator-spawn time.

8. **Subagent thread-through** — **Deferred to Spec**: spec confirms whether the orchestrator's prompt template needs to instruct Claude to thread `--settings` through nested `claude -p` calls. Bash-tool subprocesses inherit the orchestrator's Seatbelt profile via process-tree inheritance (no thread-through needed for that path); but if the orchestrator spawns FRESH `claude -p` invocations via Bash, those would reload settings from scratch and miss the per-spawn deny. Spec phase greps the orchestrator prompt template at `cortex_command/overnight/templates/orchestrator.md` (or equivalent) to determine.

9. **Migrate to typed `ClaudeAgentOptions(sandbox=SandboxSettings(...))`** — **Resolved (user, 2026-05-04)**: migrate. Catches shape regressions at SDK boundary via mypy/runtime validation. Spec ALSO removes the `dispatch.py:84-112` blob-injection bug (entire merged project settings force-applied at top precedence — see #5).

10. **CLAUDE.md 100-line cap** — **Deferred to Spec**: spec checks the line count when writing any policy entry. CLAUDE.md is at 68 lines today; adding a sandbox-policy entry that crosses 100 must extract OQ3+OQ6+new entry into `docs/policies.md` (which does not yet exist) and leave a one-line pointer in CLAUDE.md.

### Resolved during research (no spec-phase decision needed)

- `--settings` flag merge semantics: arrays merge across scopes (concat + dedup), not replace. Per-spawn deny-set carrying ONLY denies is sufficient.
- `denyWrite > allowWrite` precedence: documented verbatim, stable across runtime versions.
- macOS Seatbelt EPERM signal shape: `errno == 1`, stderr `"Operation not permitted"`. Subprocesses inherit Seatbelt profile.
- Issue #29048 carve-out grounding: real Anthropic-acknowledged behavior.
- `allowUnsandboxedCommands: false`, `enableWeakerNestedSandbox: false`, `enableWeakerNetworkIsolation: false`: must be set in per-spawn settings (load-bearing security gap in original ticket — applied to spec without further question).
- Schema standardization: `sandbox.filesystem.{allowWrite,denyWrite}` is the canonical shape; cortex-init already correct; dispatch.py is the outlier.
- `Path.cwd()` fix: use `state.integration_worktrees[feature]` per `_effective_merge_repo_path` normalization (no mid-session-CWD-shift concern).
- Recommended approach: ticket's per-spawn `--settings` is correct; alternatives A/B/C/D/E rejected with clear rationale.
