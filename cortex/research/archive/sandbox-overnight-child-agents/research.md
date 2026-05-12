# Research: Per-spawn sandbox enforcement for overnight-spawned Claude Code agents

**Date**: 2026-05-04 (revision 3 after critical review + sandbox-runtime documentary verification)
**Topic**: Use Claude Code's `sandbox.filesystem.denyWrite` (per-session settings JSON) as a **Bash-subprocess-level OS enforcement boundary** for what overnight-runner-spawned child Claude Code agents can write — narrowing the Bash-tool-routed escape vector that produced session 1708's `cd $REPO_ROOT && git commit` accident, replacing the **Bash-tool-routed-commit subset** of what the reverted ticket-128 git-pre-commit-hook approach previously covered.

**Threat model**: Accidental escapes by well-intentioned agents during overnight runs. Adversarial actors are explicitly out of scope.

**Threat-model boundary — what V1 covers and what it does NOT cover**: V1's enforcement applies to **Bash subprocesses only**. The following accidental-escape paths remain UNCOVERED by V1 and are addressed (if at all) by the V2 observability ticket or out-of-scope follow-ups:

- **Write-tool calls** to home-repo paths including `<home_repo>/.git/refs/heads/main` (a one-line ref file containing a commit SHA — a natural Write target) and tracked working-tree files. Per [anthropics/claude-code#29048], Write/Edit tools execute in-process and bypass sandbox in `bypassPermissions` mode (which the orchestrator uses via `--dangerously-skip-permissions`).
- **Edit-tool calls** to tracked files in the home-repo working tree.
- **MCP-server-routed subprocess writes** — per RQ5, plugin monitors and MCP servers run unsandboxed at hook trust level; agent action routed through an MCP server's `subprocess.run()` escapes Bash sandboxing entirely.
- **Plumbing-level commit construction** (e.g., `git update-ref`, `commit-tree` written via Write tool to a script and then invoked through Bash) when the ref-mutation step itself uses Write rather than Bash.

Compared to the reverted ticket-128's pre-commit hook: that hook fired at the git layer below all tool routing, so any Bash, MCP-routed-`git`, or plumbing-via-Bash invocation that ultimately produced a `git commit` to main was caught. V1 covers only the Bash-tool-routed subset of that surface. **V1 does not "cleanly replace" ticket-128 — it covers the dominant historical observed vector (session 1708) within a strict subset of ticket-128's threat-model coverage.** Restoration of ticket-128's broader coverage, or layered defenses combining V1 with a tool-permission denyList for Write/Edit on `.git/refs/heads/*`, is out of V1 scope and could be a separate-track follow-up.

## Research Questions

1. **JSON schema and CLI override** → **Two shapes exist; only the simplified shape is verified as a consumed settings input.** The Claude Code public docs prominently document `sandbox.filesystem.{allowWrite,denyWrite,allowRead,denyRead}` as the user-facing settings input shape (https://code.claude.com/docs/en/sandboxing, https://code.claude.com/docs/en/settings). The user's live `~/.claude/settings.json` uses ONLY this simplified shape — confirmed by inspection. The runtime sandbox enforcement layer uses a more granular shape `{read,write}.{allowOnly,denyOnly,allowWithinDeny,denyWithinAllow}` (visible in this session's runtime sandbox reminder), which appears to be the **internal IR the runtime synthesizes from the simplified settings input + hardcoded protections + permissions rules** — NOT a user-facing settings input shape. Whether the granular shape is *also* accepted as a settings-file input is **`[unverified: not-tested]`** and should not be relied upon. cortex's existing `cortex_command/pipeline/dispatch.py:546` writes the granular shape via `ClaudeAgentOptions.settings`; it does not error, but no test in `tests/test_dispatch.py:306-637` verifies that the JSON's deny/allow entries cause kernel-layer enforcement — only that the JSON is written. **For new authoring, use the documented simplified shape.** **Path matching**: documented as path-prefix (`/abs/path`, `~/path`, `./relative`); `**` glob support is documented for some permission rules but not explicitly for `sandbox.filesystem.*` arrays. The `--settings <path-or-json>` CLI flag is documented at https://code.claude.com/docs/en/cli-reference. Whether `--settings` JSON containing `sandbox.filesystem.denyWrite` is honored end-to-end at the kernel layer when paired with `--dangerously-skip-permissions` (without `--sandbox`) is **`[unverified: not-tested]`** and is the load-bearing pre-decompose verification gate (see OQ1 and DR-7 below).

2. **Git filesystem writes during a worktree commit** → **Empirically traced** (Agent C, git 2.54.0): a normal `git commit` from inside a worktree writes to `<home_repo>/.git/objects/<hash>/<rest>` (new objects), `<home_repo>/.git/refs/heads/<branch>` (shared ref), `<home_repo>/.git/logs/refs/heads/<branch>` (shared reflog), `<home_repo>/.git/worktrees/<id>/COMMIT_EDITMSG`, `<home_repo>/.git/worktrees/<id>/index`, `<home_repo>/.git/worktrees/<id>/logs/HEAD`. Lockfiles (`index.lock`, `<branch>.lock`, `worktrees/<id>/HEAD.lock`) are written and unlinked atomically. **Per-worktree vs shared split** (canonical from `gitrepository-layout(5)`): index, HEAD, COMMIT_EDITMSG, logs/HEAD, ORIG_HEAD live in `<home_repo>/.git/worktrees/<id>/`; objects, refs/heads/*, packed-refs, hooks, config live in shared `<home_repo>/.git/`.

3. **Maintenance ops interaction** → `git commit` can transitively trigger `gc --auto` (default thresholds: 6700 loose objects, 50 packs, per `git-gc(1)`). Auto-gc writes `objects/pack/*.{pack,idx}` and (when `gc.packRefs=true`, default) `packed-refs`. With `gc.autoDetach=true` (default) gc runs in background; failures surface as `gc.log` accumulating, not as commit failures. Denying `packed-refs` would not break foreground commits. `git pack-refs`, `git fsck`, `git repack`, `git prune` are not invoked from agent context for a single feature commit.

4. **Symlink resolution** → **Path-based at the sandbox enforcement layer** ([anthropics/claude-code#23960], closed not-planned). Bash subprocesses that internally use `fs.realpath` (git, prettier, etc.) resolve to the canonical path before writing — so allowlists must canonicalize via `os.path.realpath`. `dispatch.py:538,542` already does this. CVE-2026-39861 (fixed in Claude Code 2.1.64) addressed the inverse direction: pre-2.1.64 sandboxed processes could create symlinks pointing outside the workspace and the unsandboxed Claude app would follow them. **Worktree-internal symlinks**: `cortex_command/pipeline/worktree.py:179` symlinks `<worktree>/.venv → <home_repo>/.venv`; `.claude/settings.local.json` is COPIED (line 174: `shutil.copy2`), not symlinked — the user-invocation premise of a `.claude/settings.local.json` symlink is **incorrect**.

5. **Child process inheritance** → **One-way inheritance on macOS Seatbelt** (children narrow but cannot widen) — confirmed by prior research (`research/overnight-runner-sandbox-launch/research.md:7`). Anthropic's sandboxing doc states "every child process spawned by a sandboxed command inherits the same restrictions" applying to "all subprocess commands." For `bash → git → gpg → ...` subprocess chains, the entire tree is sandboxed. **Critical caveat — Write/Edit and MCP bypass sandbox** ([anthropics/claude-code#29048]): in `bypassPermissions` mode (which the orchestrator uses via `--dangerously-skip-permissions`), Write and Edit tools execute in-process and are NOT sandbox-enforced. Only Bash subprocesses are enforced. Plugin monitors and MCP servers also run unsandboxed at hook trust level (https://code.claude.com/docs/en/plugins-reference). **This shapes V1's threat-model boundary explicitly** (see boundary section above). **Linux**: bubblewrap (`bwrap`) + socat required; if missing, Claude Code "shows a warning and runs commands without sandboxing" — fails open silently unless `sandbox.failIfUnavailable: true` is set. **Windows**: not supported.

6. **Failure surfacing for legitimate denied commits** → Three-layer surface, all weak today: (a) **agent's view**: `Operation not permitted` (EPERM) in stderr with non-zero Bash exit; agent cannot distinguish sandbox denial from chmod/ACL denial. (b) **runner's view**: `claude -p` typically exits 0 if the *agent* completed its turn; sandbox-denied work surfaces as silent forward-progress in tool transcripts only. (c) **user's view (morning report)**: no signal today. Existing `claude/hooks/cortex-tool-failure-tracker.sh` fires on any non-zero Bash exit and emits `additionalContext` warnings + per-session `/tmp` logs at the 3rd failure — sandbox denials are caught generically but not classified.

7. **Distribution alternatives to per-spawn `--settings`** → **Per-spawn `--settings` is the cleanest layer.** Plugin-shipped `settings.json` **cannot** carry sandbox config: per https://code.claude.com/docs/en/plugins-reference, plugin manifests support only `agent` and `subagentStatusLine` keys. `.claude/managed-settings.json` works (system-wide enterprise/MDM scope) but is too heavyweight. Environment-variable-driven sandbox config is not documented. **Verdict**: per-spawn `--settings <path-or-json>` is the canonical mechanism. Settings array merging (per docs) means per-spawn additions combine cleanly with `~/.claude/settings.local.json` from `cortex init`.

8. **Sandbox-violation observability hook** → **Feasible with ~50 lines of shell**, modeled on `claude/hooks/cortex-tool-failure-tracker.sh`. PostToolUse(Bash) payload includes `tool_name`, `tool_input.command`, `tool_response.{exit_code,stdout,stderr}`, `session_id`. Distinguishability of sandbox vs other EPERM is imperfect in stderr alone; high-precision approach requires the hook to parse the command for write targets and check membership against the spawn's `--settings` allowlist. Low-precision regex on stderr catches the session-1708 archetype directly. **Observability, not enforcement.**

9. **Minimum-viable v1 scope** → **V1a (denyWrite for home-repo main + cross-repo mains) using simplified `sandbox.filesystem.denyWrite` shape.** See DR-3. Cross-repo enumeration is in V1 scope (not deferred) per critical-review finding R4-B.

10. **Interaction with `cortex init`'s settings.local.json mutations** → **No conflict.** Per docs, multi-scope `allowWrite`/`denyWrite` arrays merge across scopes. Per-spawn additions combine with cortex init's user-scope entries; `denyWrite` precedence over `allowWrite` per docs preserves V1's deny semantics across the merge. **`[unverified: not-tested]`** whether deny precedence holds correctly across the simplified-vs-granular boundary if cortex init writes simplified and per-spawn writes granular — sidestepped by V1's pivot to using only the simplified shape (DR-1 revision 2).

## Codebase Analysis

**Two overnight spawn sites with asymmetric sandbox surface:**

- **Orchestrator spawn** [`cortex_command/overnight/runner.py:905-922`] — direct `subprocess.Popen([claude_path, "-p", filled_prompt, "--dangerously-skip-permissions", "--max-turns", N, "--output-format=json"], env={**os.environ, "CORTEX_RUNNER_CHILD": "1"})`. **No `--settings`, no `--add-dir`, no `--sandbox`, no `cwd` override** — runs from runner's CWD (the home repo). This is the spawn that exhibited session-1708's `cd && git commit` escape; it has no per-spawn sandbox narrowing today, only inherits global `~/.claude/settings.json` `sandbox.filesystem.allowWrite` (`~/cortex-command/lifecycle/sessions/`, `~/.cache/uv`).

- **Batch runner spawn** [`cortex_command/overnight/runner.py:1107-1133`] — direct `subprocess.Popen(["cortex-batch-runner", ...])`. This is **not** `claude -p`; it's a Python console script. It internally uses `pipeline/dispatch.py` to spawn per-feature claude agents. The user's invocation framing of "claude -p subprocesses at runner.py:905 and runner.py:1124" is partly inaccurate — only `:905` is direct `claude -p`.

**Per-feature dispatch already attempts sandbox narrowing** [`cortex_command/pipeline/dispatch.py:536-549`]:
```python
_allowlist_entries = [
    str(worktree_path),
    os.path.realpath(str(worktree_path)),
]
if integration_base_path is not None:
    _allowlist_entries.append(str(integration_base_path))
    _allowlist_entries.append(os.path.realpath(str(integration_base_path)))
_write_allowlist = list(dict.fromkeys(_allowlist_entries))
if repo_root is not None:
    base_settings = _load_project_settings(repo_root)
    _deep_merge(base_settings, {"sandbox": {"write": {"allowOnly": _write_allowlist}}})
    _worktree_settings = json.dumps(base_settings)
...
options = ClaudeAgentOptions(..., settings=_worktree_settings, ...)
```
**This uses the granular shape (`sandbox.write.allowOnly`), which per RQ1 is `[unverified: not-tested]` as a settings input.** The pattern may be silently no-op'd today; no test confirms enforcement. V1 must verify this before relying on the existing pattern, and must use the simplified shape for new authoring (DR-1).

**Cross-repo dispatch allowlist inversion** [`cortex_command/overnight/feature_executor.py:603`]: passes `integration_base_path=Path.cwd()` to `dispatch_task`. For a cross-repo feature, `Path.cwd()` is the home repo (the runner runs from home-repo cwd). `dispatch.py:540` unconditionally appends `integration_base_path` to `_write_allowlist`. **Net effect**: a cross-repo dispatch's write allowlist includes the home repo, granting cross-repo work write access to the home repo's working tree — the inverse of multi-repo isolation intent. **Sibling ticket required** to fix (R4-B).

**Worktree symlinks** [`cortex_command/pipeline/worktree.py:170-179`]: Only one symlink installed — `<worktree>/.venv → <home_repo>/.venv`. `.claude/settings.local.json` is COPIED (line 174: `shutil.copy2`), not symlinked.

**`CORTEX_RUNNER_CHILD` env var** is exported at both spawn sites [`runner.py:921, 1132`].

**Runner-process direct commits** confirmed sandbox-bypass-clean [`runner.py:407-498` (`_commit_followup_in_worktree`), `runner.py:501-592` (`_commit_morning_report_in_repo`)] — both run in the runner's Python process, not Claude-Code-launched, so OS-level sandbox doesn't apply.

**Cross-repo features** tracked via `OvernightFeatureStatus.repo_path` [`cortex_command/overnight/state.py:127`]. `state.features.values()` iterated 5+ places in `runner.py` (lines 305, 312, 1155, 1172, 1257) — enumeration cost for V1 cross-repo extension is trivial.

**Plugin distribution coupling** [`plugins/cortex-overnight-integration/.claude-plugin/plugin.json`, `hooks/cortex-scan-lifecycle.sh:26-29`]: SessionStart hook fails closed if `cortex_command` is not importable.

## Web & Documentation Research

**Authoritative sources** (current to early-to-mid 2026, Claude Code v2.1.x):
- https://code.claude.com/docs/en/sandboxing — schema (simplified shape), platform coverage, child inheritance
- https://code.claude.com/docs/en/settings — settings precedence, array merging
- https://code.claude.com/docs/en/cli-reference — `--settings`, `--sandbox`, `--add-dir`, `--dangerously-skip-permissions`
- https://code.claude.com/docs/en/plugins-reference — plugin manifest schema (limited to `agent`/`subagentStatusLine`)
- https://code.claude.com/docs/en/hooks — PostToolUse(Bash) payload

**Key issues**:
- [anthropics/claude-code#22155] — proposed `read.allowOnly`/`write.allowOnly` as new settings-input fields; **closed as not-planned**. Strong signal that the granular shape is NOT a supported settings input. The runtime IR uses these names internally (visible in this session's sandbox reminder), but the settings-input shape per docs and per the closed-not-planned issue is the simplified `allowWrite/denyWrite/allowRead/denyRead`.
- [anthropics/claude-code#23960] — sandbox allowlist doesn't resolve symlinks; closed not-planned.
- [anthropics/claude-code#29048] — Write/Edit tools execute in-process and bypass sandbox in `bypassPermissions` mode; only Bash is sandbox-enforced. **Load-bearing for V1's threat-model boundary.**
- [anthropics/claude-code#32814] — VS Code/Cursor extension does not pass `--sandbox`; hints `--sandbox` is the documented activator. Practical implication: V1's `--settings` JSON should be paired with `--sandbox` to ensure activation. **`[unverified: not-tested]`** whether `--sandbox` is required separately when `sandbox.enabled: true` is in the settings JSON.
- CVE-2026-39861 — Symlink-target validation fix in Claude Code 2.1.64. Sets the version floor.

## Domain & Prior Art

**macOS Seatbelt** (`sandbox-exec`) provides one-way inheritance — children narrow, never widen. The `subpath` predicate is the recursive directory match. Claude Code's sandbox layer translates user-facing path entries to `subpath` predicates internally.

**Linux bubblewrap** is bind-mount-based; granularity at directory level.

**Prior cortex research**:
- `research/overnight-runner-sandbox-launch/research.md` — established Seatbelt one-way inheritance; **revision 2 of that file demonstrates the local norm of empirical-pre-decompose verification** for sandbox-mechanism claims (the revision flipped Option D from primary-recommended to rejected after verification). **This V1 ticket must respect that norm — see DR-7.**
- `research/orchestrator-worktree-escape/research.md` — established session-1708 escape mechanics; produced ticket-128 (now reverted).
- `research/gpg-signing-claude-code-sandbox/research.md` — established `sandbox.filesystem` field structure and `git:*`-excluded behavior.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **V1 — `sandbox.filesystem.denyWrite` for home-repo + per-feature cross-repo main branches** | M | Catches Bash-tool escapes only (Write/Edit/MCP bypass per #29048; threat-model boundary explicit). `--settings` honoring `sandbox.filesystem.denyWrite` end-to-end with `--dangerously-skip-permissions` is `[unverified: not-tested]` — DR-7 pre-decompose gate required. | DR-7 empirical verification PASSED before decompose ships V1 ticket. |
| **V2 — PostToolUse(Bash) sandbox-violation tracker hook** | S | Telemetry only, no enforcement; stderr-classification imperfect. | V1 shipped (so violations have meaning). |
| **V3 — Linux bwrap preflight + `failIfUnavailable: true`** | S | Hard-failure semantics on Linux without bwrap is a behavior change; `[premise-unverified: not-searched]` whether any current Linux/WSL2 cortex users would be affected. | V1 shipped. |
| **V4 — Audit/fix per-feature dispatch sandbox enforcement (dispatch.py:546 + feature_executor.py:603)** | M | Two issues compounded: (a) granular shape may be silently no-op'd at dispatch.py:546 (per RQ1); (b) `integration_base_path=Path.cwd()` at feature_executor.py:603 admits home repo into cross-repo allowlist. | V1 shipped (so the simplified-shape pattern is established). |
| **V5 — Documentation + migration** | S | Update `docs/overnight-operations.md`, `docs/setup.md`. | V1 shipped. |

**Note**: Worktree-placement to `$TMPDIR` (the user's invocation flagged this as "in scope as secondary measure") is **deferred as non-ticket** per DR-8 — marginal benefit small once V1 lands. Confirm with user during decompose.

## Decision Records

### DR-1 (revision 3): Schema shape — simplified `sandbox.filesystem.denyWrite` (NOT granular `write.denyWithinAllow`)

- **Context**: Critical review (R1-A1, R1-C1) established that the granular shape `sandbox.write.{allowOnly,denyWithinAllow}` was unverified as a user-facing settings input. **Revision 3 documentary verification confirms it is NOT a consumed input shape**: the open-source [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime) (the underlying enforcement package) accepts ONLY `filesystem.{allowRead, denyRead, allowWrite, denyWrite}` — `write.allowOnly`/`denyWithinAllow` are the runtime's internal IR after merging permissions rules + Edit toolName rules + simplified-shape settings, not a settings input shape. [anthropics/claude-code#22155] closed-not-planned for proposed granular settings input. **Implication**: cortex's existing `dispatch.py:546` granular-shape write IS structurally a silent no-op today. V4 ticket must convert it.
- **Options considered**:
  1. Granular `write.denyWithinAllow` shape (revision 1 recommendation; now retracted as unverified).
  2. **Simplified `sandbox.filesystem.denyWrite` shape** (documented; user's live settings use this; runtime is observed enforcing this).
  3. Both shapes as defense (redundant if (2) works; no harm if granular is silently dropped).
- **Recommendation**: **Simplified shape `sandbox.filesystem.denyWrite`**. Cleanest single-shape design; uses only documented-and-verified-consumed input.
- **Trade-offs**: The simplified shape's `denyWrite` is a flat list (no allow-region carve-out semantics). Acceptable for V1's deny-list-only design (V1 doesn't introduce per-feature allow scoping; it only adds denies for known-dangerous paths).

### DR-2: Distribution mechanism — per-spawn `--settings` JSON file at orchestrator spawn

- **Context**: Three candidate distribution layers — (a) per-spawn `--settings` JSON, (b) plugin-shipped settings.json via cortex-overnight-integration, (c) `.claude/managed-settings.json` system-wide.
- **Options considered**:
  - (a) `--settings` per spawn: precise scope; matches existing dispatch.py pattern (modulo shape pivot per DR-1).
  - (b) plugin settings: **infeasible today** — plugin manifest only supports `agent` and `subagentStatusLine` keys.
  - (c) managed-settings: too heavyweight; affects all Claude Code sessions.
- **Recommendation**: **Per-spawn `--settings <path>` JSON**, written to a tempfile and passed as additional argv at the orchestrator spawn site `runner.py:905`. **No `--sandbox` flag exists** in `claude --help` v2.1.126 or the CLI reference docs — sandbox activation is via `sandbox.enabled: true` in the JSON itself. DR-7 revision-3 documentary verification confirms this. (Revision-2 had recommended pairing with `--sandbox` based on a misread of issue [#32814]; that recommendation is retracted.)
- **Trade-offs**: Tempfile lifecycle (clean up after spawn exits); JSON build complexity. Both tractable.

### DR-3: V1 scope — denyWrite for home-repo main + cross-repo mains (cross-repo IN scope, not deferred)

- **Context**: Critical review R4-B established that OQ3's home-repo-only deferral relies on a non-existent safety net (`feature_executor.py:603` admits home repo into cross-repo allowlists, inverting expected scope). User invocation explicitly framed cross-repo enumeration as in-scope.
- **Options considered**:
  - V1-narrow (home repo only): simpler diff, but leaves cross-repo mains exposed at the same vector.
  - **V1-full (home + cross-repo enumeration via state.features)**: ~10 additional lines; matches user-invocation scope and threat surface.
  - V1-deferred (cross-repo as follow-up): rejected per R4-B analysis.
- **Recommendation**: **V1-full**. JSON shape:
  ```json
  {
    "sandbox": {
      "enabled": true,
      "filesystem": {
        "denyWrite": [
          "<home_repo>/.git/refs/heads/main",
          "<home_repo>/.git/HEAD",
          "<home_repo>/.git/packed-refs",
          "<cross_repo_1>/.git/refs/heads/<default_branch_1>",
          "<cross_repo_1>/.git/HEAD",
          "<cross_repo_2>/.git/refs/heads/<default_branch_2>",
          "<cross_repo_2>/.git/HEAD"
        ]
      },
      "failIfUnavailable": true
    }
  }
  ```
  with cross-repo entries enumerated from `state.features.values()` filtered by non-None `repo_path`. Default branch resolved per cross-repo via `git symbolic-ref refs/remotes/origin/HEAD` (or fallback to reading `.git/HEAD`) at session-start time, cached in state.
- **Trade-offs**: V1's diff grows from ~10 to ~25 lines; requires default-branch-resolution helper. Mechanics are tractable; state.features is already iterated in 5+ places.

### DR-4: Cross-platform handling — `failIfUnavailable: true` + Linux bwrap preflight

- **Context**: macOS Seatbelt is built-in; Linux requires `bwrap`+`socat` install and silently fails open if missing.
- **Options considered**: (1) accept silent fall-open on Linux; (2) `failIfUnavailable: true`; (3) preflight check at runner startup.
- **Recommendation**: **(2) and (3)**. Add `sandbox.failIfUnavailable: true` to the per-spawn JSON. Add a runner preflight check that warns/exits if `bwrap` is missing on Linux. Document in `docs/setup.md`.
- **Trade-offs**: Hard-failure semantics on Linux without bwrap is a behavior change. cortex-command's primary user base is macOS — `[premise-unverified: not-searched]` whether any Linux users currently exist; check before shipping V3.

### DR-5: Observability hook scope — separate ticket V2

- **Context**: PostToolUse(Bash) hook to track sandbox-violation attempts is feasible but not load-bearing for V1.
- **Recommendation**: **Separate ticket V2**, after V1 lands.

### DR-6 (revision 2): Two spawn sites + per-feature audit explicitly required

- **Context**: `runner.py:905` (orchestrator, direct `claude -p`) is the V1 target. `runner.py:1124` (`cortex-batch-runner`) internally uses `pipeline/dispatch.py`, which **claims** sandbox narrowing but is itself unverified at the enforcement layer (RQ1, DR-1). Critical review R1-A1 raised the same concern from the schema angle.
- **Options considered**: (1) sandbox both sites uniformly in V1; (2) sandbox only orchestrator in V1, audit per-feature in V4; (3) bundle V1 + V4.
- **Recommendation**: **(2)**. V1 lands the orchestrator deny-set. V4 audits per-feature dispatch (dispatch.py:546's granular shape may be silently no-op'd; feature_executor.py:603's `integration_base_path=Path.cwd()` admits home repo into cross-repo allowlists). V4 ticket converts dispatch.py:546 to the simplified shape (per DR-1) AND fixes feature_executor.py:603 — **two distinct bugs in the per-feature path that V4 must address jointly**.
- **Trade-offs**: V1 lands narrower than ideal; V4 carries the broader cleanup. Sequencing reduces V1 risk.

### DR-7 (revision 3): V1 acceptance-test gate (downgraded from pre-decompose blocker)

- **Context — revision history**:
  - **Revision 1** (initial draft): OQ1 deferred verification to V1 implementation as "low-risk diligence."
  - **Revision 2** (post critical review): R3-A1 + R3-A2 escalated to pre-decompose blocking gate, citing prior-research norm and cost asymmetry.
  - **Revision 3 (current)**: documentary verification gathered (see below) reduces residual risk substantially. Downgraded to V1 acceptance test.

- **Documentary evidence gathered (2026-05-04)**:
  1. **Open-source [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime)** — the package Claude Code uses internally — **accepts ONLY the simplified shape** `filesystem.{allowRead, denyRead, allowWrite, denyWrite}`. `write.allowOnly` / `denyWithinAllow` are NOT recognized config inputs. This **corroborates R1-A1**: cortex's existing `dispatch.py:546` granular-shape write is structurally a silent no-op (V4 ticket dependency confirmed).
  2. **Production config evidence**: real-world `sandbox.filesystem.denyWrite` deployments exist (e.g., paths like `~/.claude/settings.json`, `~/.claude/credentials.json`, `~/.claude/hooks` denied). Confirms simplified-shape input IS consumed end-to-end.
  3. **CLI docs (https://code.claude.com/docs/en/cli-reference)**: `--settings` is "Path to a settings JSON file or a JSON string to load **additional settings from**" (explicit: merges, not replaces).
  4. **Settings docs (https://code.claude.com/docs/en/sandboxing)**: "When `allowWrite` (or `denyWrite`/`denyRead`/`allowRead`) is defined in multiple settings scopes, the arrays are **merged**" — applies to all scopes including `--settings`.
  5. **NO `--sandbox` CLI flag exists** in `claude --help` v2.1.126 or in https://code.claude.com/docs/en/cli-reference. Activation is `sandbox.enabled: true` in JSON. Reviewer 3's "pair with --sandbox" recommendation was a misread; DR-2 corrected to remove that requirement.
  6. **denyWrite > allowWrite precedence** explicit in docs.
  7. **Issue [#26616](https://github.com/anthropics/claude-code/issues/26616)** ("Sandbox should isolate all tool execution, not just Bash") confirms current state: Write/Edit are NOT sandbox-isolated. Reinforces V1's threat-model boundary explicitly stated in topic line.

- **Residual uncertainty (V1 acceptance test)**:
  - Does the per-spawn `--settings` merge actually fire at kernel level for `claude -p` orchestrator subprocesses (vs. interactive sessions or SDK)?
  - Does the merge correctly accumulate user-scope simplified shape with per-spawn simplified shape (vs. one shadowing the other)?
  - These are bounded "does the documented merge mechanism work for this specific spawn shape" questions, not "does the schema exist" structural questions.

- **Recommendation (revision 3)**: **Proceed to decompose**. V1 ticket includes the empirical verification as an explicit acceptance test:
  - V1 AC: "Per-spawn `--settings` JSON containing `sandbox.filesystem.denyWrite` for `<home_repo>/.git/refs/heads/main` is verified to block a Bash tool's `echo > <home_repo>/.git/refs/heads/main` from a `claude -p ... --dangerously-skip-permissions` spawn with EPERM at the kernel layer. Test added to `tests/test_runner_sandbox.py` (or equivalent) and runs in `just test`."
  - If the V1 acceptance test fails: V1 PR is blocked at review; mechanism flip via the existing test scaffolding; downstream tickets (V2-V5) auto-block on V1 acceptance.

- **Trade-offs**: revision 3 accepts a small residual structural-flip risk in exchange for proceeding without a manual pre-decompose human verification round-trip. Mitigated by: (a) shape correctness now triple-corroborated (sandbox-runtime + production config + cortex's own user settings.json); (b) merge documentation is explicit in two doc sources; (c) V1 ticket acceptance test catches any residual gap before merge. The original revision-2 "pre-decompose human empirical test" remains the gold standard if a human is available to run `claude -p` from a non-sandboxed terminal — included as recommended-but-not-blocking pre-flight in V1 spec phase.

### DR-8: Worktree placement secondary measure — non-ticket

- **Context**: User invocation flagged worktree placement (`.claude/worktrees/` vs `$TMPDIR`) as in-scope-as-secondary. Marginal benefit is small once V1 lands.
- **Recommendation**: **Non-ticket**; current placement fine. Confirm with user during decompose.

## Open Questions

- **OQ1 (revision 3 — V1 acceptance test gate)**: Does `--settings` JSON containing `sandbox.filesystem.denyWrite` honor end-to-end at the kernel layer for `claude -p ... --dangerously-skip-permissions` orchestrator subprocesses? **Documentary corroboration**: schema is verified (sandbox-runtime accepts it), production usage is verified (real configs), merge semantics are documented. **Residual unknown**: does the per-spawn merge fire correctly at kernel layer for this spawn shape? **Resolution per DR-7 revision 3**: V1 acceptance test (not pre-decompose blocker). The original ` --sandbox` flag concern from revision 2 is retracted: no `--sandbox` flag exists in v2.1.126.

- **OQ2**: Per-spawn deny precedence over user-scope allow across the merge — `[unverified: not-tested]` but lower-stakes than OQ1. Same DR-7 test can extend to verify (set user `~/.claude/settings.local.json` allowWrite for `<home_repo>/.git/`, set per-spawn `denyWrite` for `<home_repo>/.git/refs/heads/main`, verify deny wins).

- **OQ3 (RESOLVED, was deferred)**: Cross-repo deny set parameterization → V1 includes cross-repo enumeration via `state.features.values()`. Per DR-3.

- **OQ4**: Orchestrator spawn cwd = home repo — sandbox JSON does the constraint work, not cwd change.

- **OQ5**: Worktree placement (`$TMPDIR` vs `.claude/worktrees/`) — DR-8 non-ticket. Confirm with user.

- **OQ6**: Audit other runner-process operations for sub-process spawns that should be sandboxed → V4 ticket.

- **OQ7 (NEW)**: Layered-defense option — combining V1 (Bash-subprocess sandbox) with a tool-permission denyList for Write/Edit on `.git/refs/heads/*` paths would close the Write-tool ref-mutation escape that V1 alone leaves uncovered. Out of V1 scope; potential follow-up if observability data (V2) shows Write-tool escape attempts. **Not part of V1 decompose unless user requests.**

---

**Synthesis (revision 2)**: The discovery establishes that per-spawn sandbox enforcement of overnight-spawned Claude Code agents is feasible IF the empirical pre-decompose verification gate (DR-7) passes for the simplified `sandbox.filesystem.denyWrite` shape. V1's threat-model coverage is **a strict subset of the reverted ticket-128's coverage** — it catches Bash-tool-routed writes, not Write/Edit-tool or MCP-routed writes (per #29048). Within that boundary V1 directly addresses the session-1708 vector (the dominant historical observed escape) and extends to cross-repo main branches (per R4-B). V4 audits and fixes the per-feature dispatch path's two compounded bugs (granular-shape silent-no-op + feature_executor.py:603 home-repo-allowlist inversion). The decompose phase produces 5 tickets (V1, V2, V3, V4, V5) under a new epic, gated on DR-7 verification. Layered-defense alternatives that would close the Write-tool escape gap (OQ7) are noted but out of V1 scope.
