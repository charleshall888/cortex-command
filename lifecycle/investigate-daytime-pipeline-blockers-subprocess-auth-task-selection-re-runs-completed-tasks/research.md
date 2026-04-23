# Research: Investigate daytime pipeline blockers (subprocess auth + task-selection re-runs completed tasks)

> Ticket: [[140-investigate-daytime-pipeline-blockers-subprocess-auth-task-selection-re-runs-completed-tasks]]
> Clarified intent: Root-cause and fix both daytime-pipeline blockers — (1) `claude_agent_sdk` subprocess returns "Not logged in · Please run /login" despite parent Claude Code session being authenticated, and (2) the pipeline's task-selection path dispatches tasks whose Status field reads `[x] complete`. The overnight runner works — a key input is what's different about its launch context versus `claude/overnight/daytime_pipeline.py` invoked from an interactive session.

## Summary (read this first)

- **Problem 1 (auth) is real.** `claude/overnight/runner.sh:42-87` runs a 4-step auth bootstrap (`ANTHROPIC_API_KEY` → `apiKeyHelper` → `~/.claude/personal-oauth-token` → keychain fallback). `claude/overnight/daytime_pipeline.py` has no equivalent. When launched from an interactive Claude Code session, the parent's keychain-based auth is not env-exported, so `claude/pipeline/dispatch.py:401-405` forwards an empty env to the SDK subprocess. macOS Keychain ACLs also prevent a child `claude` binary from reading the parent's stored OAuth token. Fix path: port the runner.sh auth bootstrap to Python inside `daytime_pipeline.py` so both launch contexts resolve auth identically.

- **Problem 2 as described is user-error on the reproducer.** In `lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/plan.md`: Task 2's heading (line 52) is `### Task 2: Capture baseline commit SHA and reference-file line counts [x]` — `[x]` is a literal suffix in the title. Task 2's actual Status field (line 70) is `- **Status**: [ ] pending`. The pipeline correctly selected a pending task. `_parse_field_status` (parser.py:385), `parse_feature_plan → _parse_tasks` (parser.py:234-326), and `compute_dependency_batches` (common.py:287-288) all function correctly.

- **However, the research surfaced a real parser-hardening concern** that the adversarial agent argues should ship with the auth fix: the `[x]` the author put in the heading title bleeds through `task.description` into the agent's prompt at `feature_executor.py:588`, which can mislead the dispatched agent into believing the task is already done. Additional latent issues in the parser/writer: greedy regex in `_parse_field_status`, case-asymmetry between parser (accepts `[X]`) and writer (emits `[ ]`).

- **Scope decision needed**: ticket 140 said "fix both issues." Problem 2's literal premise is wrong. Options are presented in `## Open Questions` below.

## Codebase Analysis

### Problem 1 — subprocess auth propagation

**Launcher delta (overnight vs daytime):**

`claude/overnight/runner.sh:26-87` performs two bootstrap steps that `daytime_pipeline.py` does NOT:

1. **Venv activation + PYTHONPATH** (`runner.sh:26-40`): resolves `REPO_ROOT` (worktree-safe via `git rev-parse --git-common-dir`), sources `$REPO_ROOT/.venv/bin/activate`, exports `PYTHONPATH=$REPO_ROOT`.
2. **Auth resolution** (`runner.sh:45-87`): 4-step fallback:
   - (a) honor existing `ANTHROPIC_API_KEY`
   - (b) run `apiKeyHelper` from `~/.claude/settings.json` or `settings.local.json`
   - (c) read `~/.claude/personal-oauth-token` (exists on this machine, 108 bytes) and export as `CLAUDE_CODE_OAUTH_TOKEN`
   - (d) warn and rely on Keychain (real macOS fallback)

The skill launch line at `skills/lifecycle/references/implement.md:71` is `DAYTIME_DISPATCH_ID={uuid} python3 -m cortex_command.overnight.daytime_pipeline --feature {slug} > lifecycle/{feature}/daytime.log 2>&1` — no venv, no auth bootstrap. The interactive Claude Code parent does not export `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` (confirmed: parent uses Keychain auth which is not env-exported; `~/.claude/settings.json` has no `apiKeyHelper`).

**claude_agent_sdk invocation site:**

- `claude/pipeline/dispatch.py:20-31` — imports the SDK
- `claude/pipeline/dispatch.py:397-440` — builds `ClaudeAgentOptions` including the `env` option
- `claude/pipeline/dispatch.py:401-405` — reads `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` from `os.environ` into the SDK's `env` option; no fallback to `apiKeyHelper` or `personal-oauth-token` here
- `claude/pipeline/dispatch.py:461` — `async for message in query(prompt=task, options=options)` (the failing line)

**Env/config vectors in play:**

- `ANTHROPIC_API_KEY` (API-key billing path)
- `CLAUDE_CODE_OAUTH_TOKEN` (subscription path — what runner.sh sets from the token file)
- `~/.claude/personal-oauth-token` (file, read by runner.sh only)
- `apiKeyHelper` field in `~/.claude/settings.json` / `settings.local.json` (runner.sh only)
- `CLAUDECODE` (explicitly cleared to `""` in `dispatch.py:401` to bypass the SDK's nested-session guard)
- `PYTHONPATH=$REPO_ROOT` (runner.sh only)

**Files likely to change:**

- `claude/overnight/daytime_pipeline.py` — add startup auth bootstrap (before `execute_feature`)
- Possibly `skills/lifecycle/references/implement.md:71` — update launch line if a wrapper approach is chosen

Candidate shape: extract runner.sh's auth block into a reusable Python helper (e.g., `claude/overnight/auth.py::resolve_sdk_auth()`) that both daytime and overnight call. Alternative: inline port into `daytime_pipeline.py::run_daytime` as `_ensure_sdk_auth()` before line 396 (`execute_feature`).

**Integration points:**

- `docs/overnight-operations.md:512-523` — "Auth Resolution" section documents the 4-step fallback and says runner.sh owns it, `dispatch.py` re-exports. Needs update to reflect daytime parity once fix lands.
- `docs/setup.md:147-159` — describes `~/.claude/personal-oauth-token`.
- `claude/overnight/smoke_test.py:167-208` — `_check_auth_pre_flight` is a model for a daytime pre-flight warning.

### Problem 2 — task-selection path

**Task-selection call chain (end-to-end):**

1. `claude/overnight/daytime_pipeline.py:396` — `execute_feature(feature, worktree_info.path, config, deferred_dir=deferred_dir)`
2. `claude/overnight/feature_executor.py:518-521` — reads `lifecycle/{feature}/plan.md` (CWD-relative, repo root) and calls `parse_feature_plan(plan_path)`
3. `claude/pipeline/parser.py:234-264` — `parse_feature_plan` → `_parse_tasks` (line 262)
4. `claude/pipeline/parser.py:299-326` — per-task: captures `description = match.group(2).strip()` (line 301; this is the raw heading title, INCLUDING any trailing `[x]` in the title), then `_parse_field_status(task_body)` at line 317 parses the `- **Status**:` bullet line
5. `claude/pipeline/parser.py:385-396` — returns `"done"` if the Status remainder has `[x]` (case-insensitive via `re.search(r"\[x\]", raw, re.IGNORECASE)`), else `"pending"`
6. `claude/overnight/feature_executor.py:535` — `batches = compute_dependency_batches(feature_plan.tasks)`
7. `claude/common.py:268-304` — `compute_dependency_batches`: line 287 filters `pending = [t for t in tasks if t.status != "done"]`, line 288 seeds `done_numbers` from tasks with `status == "done"`
8. `claude/overnight/feature_executor.py:543-646` — iterates batches, dispatches each task via `_run_task → retry_task → dispatch_task`

**plan.md read path**: repo-root-relative every call, no caching, read symmetric with `mark_task_done_in_plan` writes. No staleness.

**Hypothesis ranking vs the ticket's three candidates:**

- (a) "not calling `_parse_field_status`" → **NO**, it is called (parser.py:317)
- (b) "calling it and ignoring `done`" → **NO**, `compute_dependency_batches` honors `status != "done"` (common.py:287)
- (c) "stale/different plan.md" → **NO**, read fresh from repo-root path every call

**Actual explanation of the event-log evidence:** Task 2's heading (line 52 of the reproducer's plan.md) is `### Task 2: Capture baseline commit SHA and reference-file line counts [x]` — the author put `[x]` inside the title. Task 2's Status field (line 70) is `- **Status**: [ ] pending` — genuinely pending. The pipeline correctly dispatched a pending task. The `[x]` showing up in `task_description` in events.log is the heading text captured verbatim by `match.group(2)` at parser.py:301 — it's the title, not the Status signal.

**Files that could change if the hardening subset ships (see adversarial findings + Open Questions):**

- `claude/pipeline/parser.py:299-301` — strip trailing `\s*\[[xX ]\]\s*$` from captured description
- `claude/pipeline/parser.py:385-396` — anchor `[x]` match to start of Status-field remainder (eliminate false-positive class)
- `claude/pipeline/tests/test_parser.py` — regression tests
- `claude/common.py:327-331` — `mark_task_done_in_plan` regex could accept `[X]` for parser/writer symmetry

### Shared conventions / cross-cutting

- **Event logging**: dispatch events (`dispatch_start`, `dispatch_progress`, `dispatch_complete`, `dispatch_error`, `task_output`, `task_git_state`, `task_idempotency_*`) are written by `claude.pipeline.state.log_event` to two parallel streams: `lifecycle/{feature}/pipeline-events.log` (per-task mechanics) and `lifecycle/{feature}/events.log` (batch-level, via `pipeline_log_event` in `feature_executor.py:603-640`).
- **Idempotency**: `feature_executor.py:282-339` — `_make_idempotency_token` hashes `<feature>:<task_number>:<plan_hash>` (verified at :289). Editing plan.md invalidates all completion tokens; Status-field gate precedes idempotency gate. Description text is NOT part of the idempotency key.
- **Test stubbing**: `claude/tests/_stubs.py::install_sdk_stub` replaces `sys.modules["claude_agent_sdk"]` with a fake; used across `claude/pipeline/tests/conftest.py` and `claude/overnight/tests/conftest.py`.
- **Smoke-test auth precedent**: `claude/overnight/smoke_test.py:167-208` warns if no OAuth token AND no apiKeyHelper AND no API key, with a settings.local.json-in-worktree edge case at lines 251-257.
- **Documentation ownership** (per CLAUDE.md): `docs/overnight-operations.md` owns round-loop/orchestrator behavior including auth resolution; `docs/pipeline.md` owns pipeline internals; `docs/sdk.md` owns model selection.

## Web Research

### Claude Agent SDK auth model

The SDK spawns the bundled `claude` CLI as a subprocess and **inherits the parent process environment** — it does not validate auth itself; auth resolution happens inside the spawned `claude` CLI. The SDK bundles its own CLI by default; overridable with `ClaudeAgentOptions(cli_path=...)`.

Anthropic's stated policy: Agent SDK is designed for API-key auth; third-party agents should not use claude.ai login for rate limits. But the CLI does honor `CLAUDE_CODE_OAUTH_TOKEN` if set in the SDK-handed-down env (SDK issue #559 confirms this path works).

### claude CLI auth precedence (from `code.claude.com/docs/en/authentication`)

1. Cloud provider (`CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX` / `CLAUDE_CODE_USE_FOUNDRY`)
2. `ANTHROPIC_AUTH_TOKEN` — `Authorization: Bearer` (for LLM gateways)
3. `ANTHROPIC_API_KEY` — `X-Api-Key`. **In non-interactive mode (`-p`), the key is always used when present.**
4. `apiKeyHelper` script output
5. `CLAUDE_CODE_OAUTH_TOKEN` — long-lived token from `claude setup-token`; Pro/Max/Team/Enterprise. `--bare` mode does NOT read this variable.
6. Subscription OAuth credentials from `/login` (default for Pro/Max/Team/Enterprise users).

**Credential storage:**
- macOS → encrypted Keychain (service `"Claude Code-credentials"`)
- Linux/Windows → `~/.claude/.credentials.json` (mode 0600), or `$CLAUDE_CONFIG_DIR/.credentials.json`

**"Not logged in · Please run /login"** is emitted when none of the six sources yield a usable credential.

### Subprocess inheritance — the primary root-cause candidate

The dominant documented failure pattern matching this report is **macOS Keychain ACL isolation**:

- On macOS the OAuth token from `/login` is stored in the Keychain under service `Claude Code-credentials`. Keychain ACLs require GUI session + matching binary identity.
- Non-GUI-launched subprocesses (SSH, LaunchAgent, spawned-by-non-GUI-parent) get their own Security session; Security.framework returns `errSecInteractionNotAllowed` (exit 36), CLI reports "Not logged in".
- `claude-code` issue #29816 documents this for SSH; analogous to the daytime-pipeline-from-interactive-session case — the interactive parent ran `/login` but the SDK-spawned `claude` child cannot read that entry.
- Parent-process auth does NOT automatically propagate to a child `claude` subprocess via Keychain. A child gets its own Security session; ACLs may deny based on binary code signature/identity.

Documented env-var anti-patterns:
- Stale `ANTHROPIC_AUTH_TOKEN` / `CLAUDE_CODE_OAUTH_TOKEN` silently overrides `/login` credentials (issues #16238, #7855).
- `CLAUDE_CODE_OAUTH_TOKEN` silently overrides `~/.claude/.credentials.json` with no warning.
- Fix precedent: `unset ANTHROPIC_AUTH_TOKEN; unset CLAUDE_CODE_OAUTH_TOKEN; rm -f ~/.claude/settings.json` then set `ANTHROPIC_API_KEY`.

### Sources

- [Authentication - Claude Code Docs](https://code.claude.com/docs/en/authentication) — authoritative precedence, storage, `claude setup-token`, `--bare` caveat
- [Error reference - Claude Code Docs](https://code.claude.com/docs/en/errors) — exact "Not logged in · Please run /login" semantics
- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) — SDK uses `ANTHROPIC_API_KEY`; policy note on subscription auth
- [Agent SDK support for Max plan billing (#559)](https://github.com/anthropics/claude-agent-sdk-python/issues/559) — confirmed `CLAUDE_CODE_OAUTH_TOKEN` workaround
- [SDK + CLAUDE_CODE_OAUTH_TOKEN (#6536)](https://github.com/anthropics/claude-code/issues/6536) — CLI vs SDK auth distinction
- [Silent env-var override (#16238)](https://github.com/anthropics/claude-code/issues/16238) — silent-override failure + macOS diagnosis
- [Env-var interference with interactive mode (#7855)](https://github.com/anthropics/claude-code/issues/7855)
- [SSH Keychain ACL (#29816)](https://github.com/anthropics/claude-code/issues/29816) — non-GUI Keychain failure; LaunchAgent/ACP analogue cited
- [Managing API key environment variables](https://support.claude.com/en/articles/12304248-managing-api-key-environment-variables-in-claude-code)

## Requirements & Constraints

### Problem 1 (auth) — relevant requirements

- `requirements/multi-agent.md:84` — `ANTHROPIC_API_KEY` environment variable (forwarded to each agent). Only normative auth-vector statement. Directional ("forwarded to each agent") but does not specify the propagation mechanism (SDK arg vs. `os.environ` inheritance vs. explicit `env=` on subprocess).
- `requirements/multi-agent.md:15` — "Individual agents are spawned via the Claude Agent SDK (`claude_agent_sdk.query()`)". Binds dispatch vehicle; does not constrain how auth flows through it.
- `requirements/multi-agent.md:22` — "Permission mode is always `bypassPermissions` for overnight agents". Normative only for overnight; silent on daytime.
- **Silence**: no requirement distinguishes daytime-pipeline agent invocation from overnight-runner invocation. No requirement addresses auth inheritance under an interactive Claude Code parent.

### Problem 2 (task selection) — relevant requirements

- **Silence**: no requirement in `requirements/*.md` specifies semantics for `[x]`/`[ ]` checkbox markers in `plan.md`. `pipeline.md:36` describes feature-level status transitions (`pending → running → merged | paused | deferred | failed`) but not task-level selection.
- **Silence**: no requirement defines the contract for `claude/pipeline/parser.py` or any plan-parser component. "Status field" does not appear in any requirements doc.
- `requirements/multi-agent.md:68` — "Sessions that resume after interruption skip features already merged (plan hash + task ID used as idempotency tokens)". Feature-level idempotency; task-level `[x]`-skip is plausible extrapolation but NOT explicitly stated. Any fix codifying task-level `[x]`-skip writes new contract.
- `requirements/pipeline.md:16` / `:143` — `lifecycle/{feature}/plan.md` listed as pipeline input; establishes it as a contract surface but does not specify parsing semantics.

### Architectural constraints

- **File-based state** (`project.md:25`): No DB; plain files only.
- **Atomic writes** (`pipeline.md:21,125`): tempfile + `os.replace()`.
- **State file locking design** (`pipeline.md:133`): reads unprotected by locks; forward-only transitions make this safe.
- **Idempotency of re-reads** (`pipeline.md:126`): task-selection safe to re-execute on same state.
- **Agent spawning boundary** (`multi-agent.md:74`): parallelism decisions are orchestrator's, not individual agents'.
- **Simplicity doctrine** (`project.md:19`): complexity must earn its place; when in doubt, simpler is correct.

### Scope boundaries

- **In-scope** (`project.md:38-46`): overnight execution framework; multi-agent orchestration; global agent configuration (settings, hooks, reference docs). Both bugs fall inside in-scope areas.
- **Deferred** (`project.md:57`): migration from file-based state — fix may not introduce a DB as a shortcut.
- **Out-of-scope** (`project.md:50-53`): dotfiles, machine config, application code, reusable modules, setup automation. Fix should not expand into these.

### Silence notes

- No "daytime pipeline" functional spec — the word appears only philosophically at `project.md:11`. Requirements treat pipeline ≡ overnight framework. Any fix treating "daytime pipeline" as a first-class surface establishes new contract.
- No launch-context requirements.
- No subprocess-auth propagation mechanism (only "forwarded to each agent" is stated).
- No `[x]`/`[ ]` task-marker contract.
- No credentials.json handling mentioned.

## Tradeoffs & Alternatives

### Problem 1 — alternatives

**Alternative A: Inline port of runner.sh auth block into daytime_pipeline.py** (recommended by tradeoffs agent)
- Add `_ensure_sdk_auth()` at top of `run_daytime()` in `claude/overnight/daytime_pipeline.py`, before `execute_feature`. Mirror `runner.sh:50-87` — apiKeyHelper first → `~/.claude/personal-oauth-token` → `CLAUDE_CODE_OAUTH_TOKEN` export.
- Works today because `~/.claude/personal-oauth-token` exists (108 bytes).
- Pros: minimum surface; reuses `dispatch.py:401-405` unchanged; matches pattern.
- Cons: duplicates runner.sh logic (acceptable tech-debt for separate-commit follow-up).

**Alternative B: credentials.json / auth file handoff** — BLOCKED
- `~/.claude/credentials.json` does not exist on this machine (macOS stores in Keychain). The SDK does not document reading any credentials file beyond the env-var path. No code evidence.

**Alternative C: Shared Python helper extracted from runner.sh + daytime**
- C1: thin shell wrapper (`daytime_pipeline.sh`) that runs the auth block then `exec`s python. Shell-shell consistency.
- C2: extract both into a Python helper (`claude/overnight/auth.py::resolve_sdk_auth()`) that both invoke. Cleanest factoring but requires runner.sh to shell out to Python for auth (awkward pre-venv-activation).
- Pros: single source of truth; closes the parity gap `docs/overnight-operations.md:512-523` documents.
- Cons: larger diff; touches runner.sh; documentation burden.

**Alternative D: SDK `options.api_key` passthrough** — BLOCKED
- `ClaudeAgentOptions.__dataclass_fields__` on installed SDK has no `api_key` field. Fields: `env`, `settings`, `cli_path`, `extra_args`. Only viable channel is `env=` (already used at `dispatch.py:401-405`). `extra_args=["--api-key", ...]` would put credentials in argv (visible in `ps`) — worse than env.

**Alternative E: Only run daytime via LaunchAgent** — contradicts `skills/lifecycle/references/implement.md:71` (user invokes pipeline interactively by design). Not a fix.

**Recommended approach for Problem 1**: Alternative A (inline port) for minimum-surface fix; defer Alternative C2 (shared helper refactor) as a follow-up ticket. Adversarial additions (mitigations) below.

### Problem 2 — alternatives (revised after evidence-check)

Alternatives A–D (call parser / fix caller / refresh read / different path) are all **not applicable** — every link in the chain works correctly on the reproducer. The task the ticket author identified as mis-selected was in fact genuinely pending.

**Alternative E (new, fits real evidence): strip trailing `[x]`/`[ ]` from task heading description + tighten Status regex**
- E1 (parser.py:301): after `description = match.group(2).strip()`, add `description = re.sub(r'\s*\[[xX ]\]\s*$', '', description).strip()`. Prevents heading markers from bleeding into `task.description` and from there into the agent prompt at `feature_executor.py:588`.
- E2 (parser.py:394): change `re.search(r"\[x\]", raw, re.IGNORECASE)` to `re.match(r"\[[xX]\]", raw)`. Eliminates false-positive class where `[x]` appears mid-line (e.g., `- **Status**: see [x]y.txt pending` — today returns "done").
- E3 (common.py:327-331 `mark_task_done_in_plan` writer regex): accept `[X]` and `[x]` symmetrically for parser/writer symmetry.
- ~15 lines total + regression tests.
- Pros: closes the "I marked it done but the pipeline re-ran it" confusion class AND stops the agent-prompt-bleed-through (which affects dispatched agent behavior, not just log aesthetics).
- Cons: slight scope increase beyond auth fix. Easily same-commit-able.

**Recommended approach for Problem 2**: user decides (see `## Open Questions` Q1). Adversarial agent argues E1–E3 should land in the same commit as Problem 1. Tradeoffs agent recommends closing Problem 2 as "not a bug" + optional E1 follow-up.

## Adversarial Review

### Failure modes and edge cases

- **`apiKeyHelper` stderr/timeout silent-corruption hazard.** Bash version at `runner.sh:51-65` uses `2>/dev/null` to mask helper misbehavior. Python port using `subprocess.run(capture_output=True, text=True, timeout=5)` must wrap in `try/except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError)` or a new failure mode emerges in daytime that doesn't exist overnight.
- **Auth bootstrap ordering vs startup classification.** If `_ensure_sdk_auth()` runs after `daytime_pipeline.py:332-364` (plan-exists check, PID-file liveness, `_write_pid`), auth failure will be classified as `"exception"` not `"startup_failure"` because `_startup_phase` flips to `False` at line 392. Result-file `terminated_via` will mis-report the failure reason. Mitigation: place `_ensure_sdk_auth()` as the very first line of `run_daytime`, before any startup check that can raise.
- **Concurrency hazard for stateful apiKeyHelper.** Two daytime pipelines running simultaneously will each independently invoke `apiKeyHelper`. If the helper is stateful (e.g., `security find-generic-password` that prompts TouchID once per session), simultaneous invocations serialize poorly. runner.sh's `if [[ -z ... ]]` guard is in-process; no cross-process lock exists.
- **`_parse_field_status` greedy-match false positive.** `re.search(r"\[x\]", raw, re.IGNORECASE)` matches `[x]` anywhere in the Status line's remainder. `- **Status**: see [x]y.txt pending` returns "done". Unlikely in practice, but tightening to `re.match(r"\[[xX]\]", raw)` anchors correctly.
- **`mark_task_done_in_plan` writer case-sensitivity asymmetry.** Parser (`parser.py:394`) accepts `[x]` or `[X]` (IGNORECASE). Writer (`common.py:327-331`) hard-codes `[ ]` → `[x]` lowercase and requires `-\s+` (not `*\s+`). A human editing plan.md to `[X]` pending will be re-parsed as done, but the writer will fail to update the next task correctly, causing gradual write-skew.
- **Plan-hash invalidation ripple.** `_compute_plan_hash` hashes the full plan.md; `mark_task_done_in_plan` mutates it after each task. Each completion invalidates idempotency tokens of all already-completed tasks in the same run. Safe today because `compute_dependency_batches` uses `status != "done"` as the primary gate, so re-parsed "done" tasks are skipped regardless of token state. Fragile if a future refactor inverts gate order.
- **SDK `env=` merge semantics may not be additive.** `dispatch.py:401-405` passes auth vars via `options.env`. If the SDK's merge-with-os.environ contract changes, subprocess gets only those three keys — no PATH, no HOME. SDK subprocess fails to find `claude` on PATH. Mitigation: export auth vars to `os.environ` in the Python port (not only into `options.env`).
- **`task.description` `[x]` leak into agent prompt.** `task.description` flows to `feature_executor.py:588` as the `task` prompt. A dispatched agent sees `[x]` in its task description and can reasonably conclude the task is already done. This is NOT just log aesthetics — it affects dispatched agent behavior. Stripping trailing markers in `_parse_tasks` (E1 above) is more than QoL.

### Security concerns

- **`~/.claude/personal-oauth-token` is plaintext on disk (mode 600, `sk-ant-oat01-...`).** Weaker than Keychain (no ACL gating, no process-identity binding). Repo has already adopted it as overnight fallback; daytime reuse does NOT add a new attack surface but amplifies leak opportunity (any daytime invocation reads it vs. only scheduled overnight). Not a blocker.
- **Token leakage via `stderr=_on_stderr` (`dispatch.py:424-426`).** SDK CLI stderr is captured up to 100 lines into `_stderr_lines`, then may flow into `error_detail` → `log_event` → `pipeline-events.log`. If a future SDK release ever logs the token verbatim, it lands in logs. No redaction today. Mitigation: add `sk-ant-*` redaction pass on each line before append.
- **Env var exposure in `/proc/self/environ`** (Linux) or `ps -E` (macOS same-uid). Exporting to `os.environ` preserves overnight posture. The daytime fix doesn't worsen it.
- **No audit log when Python port reads `personal-oauth-token`.** runner.sh prints `"Using OAuth token from $_TOKEN_FILE" >&2`. Python port should emit an equivalent `log_event` (without the token value) so post-hoc triage knows which auth vector won. Event name candidate: `auth_bootstrap` with `vector: "env_preexisting" | "api_key_helper" | "oauth_file" | "none"`.

### Assumptions that may not hold

- **"Problem 2 is user-error; no code change needed."** Brittle — the pattern of putting `[x]` in task headings exists in this reproducer plan file on Tasks 2 and 3 and likely elsewhere. Status-field is authoritative and the pipeline is correct, BUT `task.description` (heading text) flows into the dispatched agent's prompt. Under adversarial framing, the hardening is not optional.
- **"`apiKeyHelper` is callable in any context."** Helpers often invoke Keychain queries that require GUI Login session. Under LaunchAgent or non-TTY contexts, helper may prompt interactively and fail silently. Python port must preserve bash's timeout/swallow semantics.
- **"Clearing `CLAUDECODE` is safe."** Today it is (used to bypass SDK's nested-session guard). If a future SDK release uses `CLAUDECODE` presence as an auth-path selector, clearing it could break auth resolution. Undocumented external contract.
- **"The daytime pipeline works when auth is fixed" (false-negative dispatch risk).** `compute_dependency_batches` treats any task with `status != "done"` as pending. A non-matching Status line (e.g., `- **Status**: done` without brackets, or accidental bracket-drop on edit) returns "pending" and re-dispatches a completed task. Idempotency-token path protects only if `pipeline-events.log` survives. Surface is under-tested.

### Recommended mitigations

1. Place `_ensure_sdk_auth()` as the first line of `run_daytime`, before any startup check. Classify auth-resolution failure as `"startup_failure"` for consistent result-file reporting.
2. Export auth vars to `os.environ`, not only `options.env`. Preserves runner.sh parity; survives SDK merge-semantics changes.
3. Wrap helper invocation in `try/except (subprocess.TimeoutExpired, FileNotFoundError, OSError, json.JSONDecodeError)`; log a `auth_bootstrap` event with `vector:` tag; never log token values.
4. Add `sk-ant-*` redaction in `_on_stderr` at `dispatch.py:424-426` — one-line regex before append.
5. Ship parser hardening (E1–E3) in the same commit as the auth fix — not deferred. The `task.description` heading-bleed-through is a real agent-behavior bug, not cosmetic.
6. Consider an advisory lock on `$HOME/.claude/.auth-bootstrap.lock` (Python `fcntl.flock`) around helper invocation to serialize concurrent pipelines. Cheap insurance.

### Agreements (what holds under scrutiny)

- Root cause of Problem 1 is the missing runner.sh auth bootstrap in daytime_pipeline.py. Confirmed.
- Problem 2's acute reproducer is user-error; Task 2 Status is genuinely `[ ] pending`. Confirmed.
- `_make_idempotency_token` uses `feature:task_number:plan_hash` (feature_executor.py:289); no description leak into idempotency keys.
- `compute_dependency_batches` correctly gates on `status != "done"` (common.py:287).
- Keychain-ACL isolation is the plausible mechanism for "Not logged in" — matches documented non-GUI failure pattern.
- Two-commit landing (auth urgent; parser hardening optional) is structurally defensible — adversarial disagrees only on whether hardening should be same-commit vs deferred.

## Open Questions

- **Q1 — Problem 2 scope decision**: ticket 140's literal premise ("pipeline dispatches [x] complete tasks") is not supported by evidence — the reproducer's Task 2 Status field is genuinely `[ ] pending` and the pipeline dispatched it correctly. However, adversarial review surfaced related parser hardening (E1: strip `[x]` from heading bleed-through into agent prompts; E2: anchor Status-field `[x]` regex; E3: writer case-symmetry). **Resolved (2026-04-23)**: user chose to ship auth fix + parser hardening E1–E3 in this lifecycle. Spec must cover both surfaces. Problem 2 as literally described is acknowledged as user-error and documented; the hardening work is carried forward as the actual Problem 2 scope.

- **Q2 — Auth observability**: should the auth-bootstrap path emit an `auth_bootstrap` event to `pipeline-events.log` with a `vector:` tag (`env_preexisting | api_key_helper | oauth_file | none`) for post-hoc triage? Adversarial agent recommends yes; runner.sh does equivalent via stderr. **Deferred: will be resolved in Spec; likely "yes" given existing audit-trail posture.**

- **Q3 — Concurrency guard**: should the Python auth bootstrap use `fcntl.flock` on `$HOME/.claude/.auth-bootstrap.lock` to serialize concurrent helper invocations? Adversarial agent recommends yes as cheap insurance; no evidence of concurrent-run stress today. **Deferred: will be resolved in Spec based on stress-test scenarios the user has in mind.**

- **Q4 — `options.env` vs `os.environ`**: should the port export auth vars to `os.environ` (runner.sh parity, SDK-merge-agnostic) in addition to `options.env`, or only the latter? Adversarial recommends both; tradeoffs agent did not address this layer directly. **Deferred: will be resolved in Spec; adversarial's reasoning is load-bearing, so likely "both".**

- **Q5 — SDK stderr redaction**: should `_on_stderr` at `dispatch.py:424-426` apply `sk-ant-*` redaction before appending to `_stderr_lines`? No evidence SDK currently leaks tokens, but no review of future SDK releases is in place. **Deferred: will be resolved in Spec; one-line regex is low-cost insurance.**
