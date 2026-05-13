# Plan: harden-autonomous-dispatch-path-for-interactive

## Overview
Land a four-phase, parity-by-construction hardening of the autonomous-dispatch path: Phase 1 introduces a single shared auth resolver+probe consumed by both `runner.py` and `daytime_pipeline.py`; Phase 2 introduces a single worktree-root resolver consulted by `cortex init` (registration) and dispatch (creation+probe); Phase 3 promotes every `python3 -m cortex_command.*` callsite to a `[project.scripts]` console-script and wires a recurring audit gate against regression; Phase 4 fuses both probes into `verify_dispatch_readiness()` and freezes the named F1/F2/F3 failure modes via a stub-SDK CI test plus an opt-in real-launchd matrix.
**Architectural Pattern**: pipeline
<!-- The dispatch path is a linear preflight pipeline: ensure_sdk_auth → keychain probe → resolve_worktree_root → worktree probe → entry-point launch. This plan adds shared resolver stages and a fused readiness check at the pipeline's head, replacing the divergent ad-hoc patches that exist today. -->

## Outline

### Phase 1: Auth resolution + probe (tasks: 1, 2, 3, 4)
**Goal**: Shared auth-vector resolver + presence-only Keychain probe consumed identically by `runner.py` and `daytime_pipeline.py`; misleading messaging removed; `auth_probe` event registered.
**Checkpoint**: `pytest cortex_command/overnight/tests/test_auth.py tests/test_runner_auth.py -q` exits 0; `grep -c ANTHROPIC_AUTH_TOKEN cortex_command/overnight/auth.py` ≥ 1; `grep -i 'will use Keychain' cortex_command/overnight/auth.py` returns no match; both `runner.py:2042-2045` and `daytime_pipeline.py:336-352` invoke the same helper.

### Phase 2: Sandbox-friendly worktree wiring (tasks: 5, 6, 7, 8, 9)
**Goal**: Single `resolve_worktree_root()` in `cortex_command/pipeline/worktree.py` consulted by `cortex init` registration, `worktree.py:create_worktree`, and `daytime_pipeline.py:_worktree_path`; `probe_worktree_writable()` available for dispatch-time use; `.vscode`/`.idea` constraint documented.
**Checkpoint**: `pytest tests/test_worktree.py tests/test_worktree_probe.py tests/test_init_worktree_registration.py -q` exits 0; `grep -rn 'os\.environ\.get(.CORTEX_WORKTREE_ROOT.)' cortex_command/` ≤ 1 hit (resolver-internal); after `cortex init` in a test repo, `jq '.sandbox.filesystem.allowWrite' ~/.claude/settings.local.json` includes the resolved worktree root.

### Phase 3: Console-script sweep + recurring gate (tasks: 10, 11, 12, 13a, 13b, 13c, 14, 15, 16)
**Goal**: Every audited `python3 -m cortex_command.*` callsite promoted to a `cortex-*` console-script and every callsite renamed; recurring `--audit-bare-python-m-callsites` gate prevents silent re-introduction; dev-clone install path documented; CHANGELOG entry for v0.1.0 → v0.2.0 reinstall requirement.
**Checkpoint**: `grep -rn 'python3 -m cortex_command\.' skills/ hooks/ claude/ bin/ docs/ justfile tests/` returns no hits except inside `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/audit-callsites.md`; `bin/cortex-check-parity --staged` exits 0; `just check-bare-python-callsites` exits 0 on a clean tree; `bin/cortex-check-parity --audit-bare-python-m-callsites` exits 0.

### Phase 4: Dispatch preflight fuse + parity test surface (tasks: 17, 18, 19, 20)
**Goal**: `verify_dispatch_readiness()` fuses the auth + worktree probes inside `run_daytime` Phase A; stub-SDK CI test freezes the named F1/F2/F3 failure modes under both launchd-shaped and Bash-tool-shaped synthetic env dicts; opt-in `just test-dispatch-parity-launchd-real` recipe added; sandbox preflight artifact present and current.
**Checkpoint**: `pytest tests/test_dispatch_parity.py cortex_command/overnight/tests/test_dispatch_readiness.py -q` exits 0; `just --list | grep test-dispatch-parity-launchd-real` matches; `bin/cortex-check-parity --staged` exits 0 with `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/preflight.md` staged.

## Tasks

### Task 1: Extend `ensure_sdk_auth` resolution chain with `ANTHROPIC_AUTH_TOKEN`
- **Files**: `cortex_command/overnight/auth.py`, `cortex_command/overnight/tests/test_auth.py`
- **What**: Add `ANTHROPIC_AUTH_TOKEN` as a recognized vector between the cloud-provider env vars and `ANTHROPIC_API_KEY` in `ensure_sdk_auth`'s resolution chain (R1). When set non-empty, resolves to `vector="auth_token"` and the value is exported to subprocess env for inheritance.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `auth.py` line 2 docstring states stdlib-only constraint (load-bearing — module runs as `python3 -m cortex_command.overnight.auth --shell` pre-venv). Existing `ensure_sdk_auth` resolution chain order: cloud-provider env → `ANTHROPIC_API_KEY` → `apiKeyHelper` → `CLAUDE_CODE_OAUTH_TOKEN` → none. `_build_event` (lines 160-166) returns `{ts, event, vector, message}`. Documented SDK chain: https://code.claude.com/docs/en/authentication. Test pattern: `test_auth.py` already covers R1–R8 vectors — add a parallel `test_auth_token_vector` covering both env-shape and resolution-precedence cases.
- **Verification**: run `pytest cortex_command/overnight/tests/test_auth.py -q` — pass if exit 0; AND `grep -c ANTHROPIC_AUTH_TOKEN cortex_command/overnight/auth.py` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 2: Add stdlib `probe_keychain_presence()` to `auth.py`
- **Files**: `cortex_command/overnight/auth.py`, `cortex_command/overnight/tests/test_auth.py`
- **What**: Add `probe_keychain_presence() -> Literal["present", "absent", "unavailable"]` (R2). Probes canonical service name `"Claude Code-credentials"` via `subprocess.run(["security", "find-generic-password", "-s", <name>], stdout=DEVNULL, stderr=DEVNULL).returncode`. Exit-code-only — never `-w` (no secret retrieval, no ACL prompt). `"unavailable"` covers non-Darwin and Darwin-but-search-list-unavailable (locked login keychain in launchd pre-unlock). Stdlib-only.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Service name source: https://github.com/anthropics/claude-code/issues/9403. Behavior contract documented in spec.md R2 and Edge Cases (first-after-reboot Keychain unlock, v2.0.14 service-name aliasing, ACL trust mismatch). Function signature returns a string literal; use `platform.system()` to detect Darwin without importing third-party libs. Stdlib-only — no `keyring`, no `subprocess32`. Test must cover (a) Darwin + present, (b) Darwin + absent, (c) non-Darwin → "unavailable", (d) Darwin + search-list-unavailable → "unavailable" (mock `subprocess.run` to simulate exit 36 / `errSecInteractionNotAllowed`).
- **Verification**: run `pytest cortex_command/overnight/tests/test_auth.py::test_keychain_presence_probe -q` — pass if exit 0.
- **Status**: [x] complete

### Task 3: Shared auth resolver+probe helper; converge `runner.py` and `daytime_pipeline.py`; remove patches; replace messaging
- **Files**: `cortex_command/overnight/auth.py`, `cortex_command/overnight/daytime_pipeline.py`, `cortex_command/overnight/runner.py`, `cortex_command/overnight/tests/test_daytime_auth.py`, `tests/test_runner_auth.py`
- **What**: Introduce a single resolver function in `auth.py` (e.g. `resolve_and_probe(feature: str | None) -> AuthProbeResult`) that consumes `ensure_sdk_auth` + `probe_keychain_presence()` and applies the spec's R3 policy: `vector != "none"` → continue; `vector == "none"` AND probe in `{"present", "unavailable"}` → continue with `auth_probe` event recording probe result; `vector == "none"` AND probe `"absent"` → return failure with `result="absent"`. Replace the uncommitted soft-fall-through patch at `daytime_pipeline.py:336-352` and the bare `try/except: pass` at `runner.py:2042-2045` with calls to the same helper. Replace the misleading "claude -p will use Keychain auth if available" message text in `auth.py` with probe-outcome-driven wording (R5).
- **Depends on**: [1, 2, 4]
- **Complexity**: complex
- **Context**: Both callsites today diverge: `daytime_pipeline.py:336-352` hard-fails (`startup_failure`); `runner.py:2042-2045` swallows. Parity by construction means a single helper, one call site of policy. Event shape (per Task 4 registration): `{ts, event: "auth_probe", feature, vector: "<resolved>" | "none", keychain: "resolved" | "absent" | "unavailable", result: "ok" | "absent", source: "ensure_sdk_auth"}`. Failure path slots into existing `_top_exc` / `_terminated_via="startup_failure"` / `_outcome="failed"` machinery in `daytime_pipeline.py:496-554`. Event logging targets: `cortex/lifecycle/pipeline-events.log` (runner path) and `cortex/lifecycle/{feature}/events.log` (daytime path). Existing message text grep: `grep -n 'will use Keychain' cortex_command/overnight/auth.py`. `_build_event` and `_now_iso` byte-equivalence with `pipeline.state.log_event` is load-bearing — reuse them.
- **Verification**: run `pytest cortex_command/overnight/tests/test_auth.py cortex_command/overnight/tests/test_daytime_auth.py tests/test_runner_auth.py -q` — pass if exit 0; AND `grep -c 'try:\s*$' cortex_command/overnight/runner.py | head -n1` — manual check that lines 2042-2045's bare `try/except: pass` is gone (alternative: `grep -A 1 'ensure_sdk_auth' cortex_command/overnight/runner.py | grep -c 'except: pass'` = 0); AND `grep -i 'will use Keychain' cortex_command/overnight/auth.py` — pass if no match.
- **Status**: [ ] pending

### Task 4: Register `auth_probe` event in `bin/.events-registry.md`
- **Files**: `bin/.events-registry.md`
- **What**: Add the `auth_probe` event entry with the schema defined in spec.md R4: `{ts, event: "auth_probe", feature, vector: "<resolved>" | "none", keychain: "resolved" | "absent" | "unavailable", result: "ok" | "absent", source: "ensure_sdk_auth"}` (R4).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing registry file has one entry per event with field-list and producer. Follow the established row shape. The events-registry parity check is `bin/cortex-check-events-registry`. Task 3 emits the event from `auth.py` (source: `ensure_sdk_auth`); registration must precede or accompany the emit-site landing.
- **Verification**: run `bin/cortex-check-events-registry` — pass if exit 0; AND `grep -c 'auth_probe' bin/.events-registry.md` — pass if count ≥ 1.
- **Status**: [x] complete

### Task 5: Add `resolve_worktree_root()` resolver in `pipeline/worktree.py`
- **Files**: `cortex_command/pipeline/worktree.py`, `tests/test_worktree.py`
- **What**: Add `resolve_worktree_root(feature: str, session_id: str | None) -> Path` (R6) with this resolution order: (a) `CORTEX_WORKTREE_ROOT` env var (after `$TMPDIR` expansion); (b) registered path from `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite` (cortex-registered entry); (c) default `.claude/worktrees/<feature>/` for same-repo; (d) `$TMPDIR/overnight-worktrees/<session_id>/<feature>/` for cross-repo.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Today's reads happen inline at `worktree.py:11-14, 102-109` and `daytime_pipeline.py:116-126`. Cross-repo convention is in `cortex/requirements/multi-agent.md` ("Cross-repo worktrees go to `$TMPDIR` to avoid sandbox restrictions"). `$TMPDIR` expansion: `os.path.expandvars(os.environ.get("CORTEX_WORKTREE_ROOT", ""))`. "Cortex-registered entry" is identified by reading `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite` and matching a path that contains `worktrees/` (or equivalent stable marker — keep this private to the resolver). Test must cover each branch in isolation via `monkeypatch.setenv`.
- **Verification**: run `pytest tests/test_worktree.py -q` — pass if exit 0; AND `grep -c 'def resolve_worktree_root' cortex_command/pipeline/worktree.py` — pass if count = 1.
- **Status**: [x] complete

### Task 6: Wire `cortex init` to register the resolved worktree root in `~/.claude/settings.local.json`
- **Files**: `cortex_command/init/handler.py`, `cortex_command/init/settings_merge.py`, `tests/test_init_worktree_registration.py`
- **What**: Extend `cortex_command/init/handler.py` to call `resolve_worktree_root()` and register the result via the existing `settings_merge.register_path` machinery in `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite` (R7). Cross-repo paths (those resolving to `$TMPDIR/...`) skip registration — they're already sandbox-writable per existing convention. Uses the same `fcntl.flock`-serialized additive append already in use for the `cortex/` umbrella.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: `settings_merge.register_path` is the canonical helper; it is idempotent and additive — pre-existing manual entries are preserved (per spec Edge Cases). The `fcntl.flock` lock file convention is already in place. Handler entry point is the `cortex init` command's main flow in `handler.py:138-198`. Cross-repo detection: any path whose resolved value starts with `$TMPDIR` (after expansion) skips registration. Test must cover (a) same-repo path is registered, (b) cross-repo `$TMPDIR` path is NOT registered, (c) `cortex init` is idempotent (re-run does not duplicate the entry).
- **Verification**: run `pytest tests/test_init_worktree_registration.py -q` — pass if exit 0.
- **Status**: [ ] pending

### Task 7: Add `probe_worktree_writable()` to `pipeline/worktree.py`
- **Files**: `cortex_command/pipeline/worktree.py`, `tests/test_worktree_probe.py`
- **What**: Add `probe_worktree_writable(root: Path) -> ProbeResult` (R8) performing two checks in order: (a) no-op file create + delete under `root` (catches sandbox-blocked roots); (b) no-op `git worktree add <root>/cortex-probe-<uuid> <throwaway-branch>` + cleanup (catches `.vscode/`/`.idea/` hardcoded denies). On failure, returns a `ProbeResult` with a `cause` field naming the likely root cause and a `remediation_hint` field. On success, the function returns a success `ProbeResult` and leaves no artifacts behind.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Hardcoded-deny prior art: https://github.com/anthropics/claude-code/issues/51303. The throwaway branch can be derived from `uuid.uuid4().hex[:8]` to avoid collisions. Cleanup must succeed even if either probe step fails (use a `finally` block — but cleanup itself must not raise). `ProbeResult` shape: `@dataclass class ProbeResult: ok: bool; cause: str | None; remediation_hint: str | None`. Test must cover (i) writable root (success), (ii) sandbox-blocked root simulated via a read-only fixture path (failure with cause naming sandbox), (iii) fixture repo with a tracked `.vscode/` directory (`git worktree add` failure with cause naming hardcoded deny).
- **Verification**: run `pytest tests/test_worktree_probe.py -q` — pass if exit 0.
- **Status**: [ ] pending

### Task 8: Worktree-creation callsites consult the resolver
- **Files**: `cortex_command/pipeline/worktree.py`, `cortex_command/overnight/daytime_pipeline.py`
- **What**: Replace inline `os.environ.get("CORTEX_WORKTREE_ROOT", ...)` reads in `worktree.py:create_worktree` and `daytime_pipeline.py:_worktree_path` with calls to `resolve_worktree_root()` (R9). All other env-var reads of `CORTEX_WORKTREE_ROOT` outside the resolver itself are removed.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Today's two callsites diverge in subtle ways (`$TMPDIR` expansion not consistent). Routing through one resolver eliminates drift. The resolver's signature requires `feature` and (optionally) `session_id`; `create_worktree` already takes a feature name; `_worktree_path` already takes a feature and has session context.
- **Verification**: run `grep -rn 'os\.environ\.get(.CORTEX_WORKTREE_ROOT.)' cortex_command/` — pass if at most 1 hit (the resolver itself); AND `pytest tests/test_worktree.py -q` — pass if exit 0.
- **Status**: [ ] pending

### Task 9: Document `.vscode`/`.idea` hardcoded denies
- **Files**: `docs/overnight-operations.md`, `cortex/requirements/pipeline.md`
- **What**: Add an "Edge Cases" section (or extend an existing one) to `docs/overnight-operations.md` documenting that Claude Code's binary has hardcoded sandbox denies for `.vscode/` and `.idea/` overriding `sandbox.filesystem.allowWrite` (R11). Document three workarounds: sparse-checkout (untrack the directory), `excludedCommands` to let `git` run outside the sandbox, or `dangerouslyDisableSandbox` (last resort). Cross-link from `cortex/requirements/pipeline.md` "Edge Cases".
- **Depends on**: none
- **Complexity**: simple
- **Context**: Source for the upstream issue: https://github.com/anthropics/claude-code/issues/51303. Prose should describe What and Why (the deny is hardcoded in the binary's `_SBX` module and not configurable via settings) without prescribing implementation details. Cross-link wording can be terse — one sentence per document.
- **Verification**: run `grep -c vscode docs/overnight-operations.md` — pass if count ≥ 1; AND `grep -c vscode cortex/requirements/pipeline.md` — pass if count ≥ 1.
- **Status**: [x] complete

### Task 10: Produce `audit-callsites.md` source-of-truth deliverable
- **Files**: `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/audit-callsites.md`
- **What**: Run `grep -rn 'python3 -m cortex_command\.'` across `skills/`, `hooks/`, `claude/`, `bin/`, `docs/`, `justfile`, `tests/`, and optionally `Justfile.local`. Compile every hit into `audit-callsites.md` with one line per callsite: `{file}:{line} → cortex_command.{module} → {proposed-console-script-name}` (R12 part a). Include a header listing the audit date, the grep command used, and a one-paragraph rationale for the chosen naming convention (kebab-case, prefixed `cortex-`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Naming convention for promotions is in spec.md R13: kebab-case, prefixed `cortex-` (e.g., `cortex-daytime-pipeline`, `cortex-critical-review`). Research.md lines 32-46 enumerates 13 candidate modules with their `_main`/`main` callables (`daytime_pipeline:_run`, `daytime_dispatch_writer:main`, `daytime_result_reader:main`, `report:main`, `integration_recovery:main`, `interrupt:main`, `complete_morning_review_session:main`, `critical_review:main`, `discovery:main`, `common:main`, `backlog.ready:main`, `pipeline.metrics:main`, `overnight.auth:_main`). The audit may discover additional callsites; expand the candidate list as the grep finds them. Each chosen console-script name must clear a collision check via `command -v <name>` against a clean PATH (Edge Cases note in spec).
- **Verification**: state the file exists with at least one callsite row — `[ -f cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/audit-callsites.md ]` exits 0 AND `grep -cE 'cortex_command\.' cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/audit-callsites.md` ≥ 13.
- **Status**: [x] complete

### Task 11: Wire `--audit-bare-python-m-callsites` mode + allowlist + just recipe
- **Files**: `bin/cortex-check-parity`, `bin/.audit-bare-python-m-allowlist.md`, `justfile`
- **What**: Extend `bin/cortex-check-parity` with an `--audit-bare-python-m-callsites` mode (R12 part c) that re-runs the F14 grep over `skills/`, `hooks/`, `claude/`, `bin/`, `docs/`, `justfile`, `tests/` and fails on any hit not allowlisted in `bin/.audit-bare-python-m-allowlist.md`. Allowlist file uses the same closed-enum-category schema as `bin/.parity-exceptions.md` (R12 part d). Add a `just check-bare-python-callsites` recipe wired to the new mode (R12 part e). The mode is off the pre-commit critical path; it is invoked via morning-review or the just recipe.
- **Depends on**: [10, 13a, 13b, 13c]
- **Complexity**: simple
- **Context**: Two-mode gate precedent: `bin/cortex-check-parity` already has `--staged` (pre-commit critical path) and `--audit` (repo-wide off-critical-path) modes (research.md citation). The audit mode pattern reuses existing argument-parsing in the script. Allowlist file schema: `## <Category>` headings (closed enum) followed by entries `- {path}:{line} — {rationale ≥30 chars}` mirroring `.parity-exceptions.md`. Initial allowlist starts empty (or includes only entries justified by Task 10's audit). Recipe should be a `#!/usr/bin/env bash`-style block in the justfile invoking the script with the new flag.
- **Verification**: run `bin/cortex-check-parity --audit-bare-python-m-callsites` — pass if exit 0; AND `just --list | grep check-bare-python-callsites` — pass if match found; AND `[ -f bin/.audit-bare-python-m-allowlist.md ]` — pass if file exists.
- **Status**: [ ] pending

### Task 12: Promote audited modules to `[project.scripts]` in `pyproject.toml`
- **Files**: `pyproject.toml`
- **What**: For each module in `audit-callsites.md`, add a `[project.scripts]` entry mapping the promoted console-script name to `<module>:<callable>` (R13). Modules without a top-level `main()` (or `_main()`) callable get a one-line wrapper added in their module file (e.g. `def main(): _run()` — those line-edits happen here as side touches on the module file, but the wrapper is a single one-line `def`).
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Existing `[project.scripts]` block in `pyproject.toml:18-24` has 6 entries — extend additively. Module-level callable forms allowed: `module:main`, `module:_main`. Audit list source-of-truth is Task 10's `audit-callsites.md`. The plugin parity gate `bin/cortex-check-parity` already first-class-supports entry-point names via `gather_entry_point_names` (research.md citation) — strictly additive; no gate logic change. Spec Edge Case "Console-script name collision": verify each chosen name via `command -v` against a clean PATH before commit. Note: this task may touch >1 file when modules need a `main()` wrapper added — keep wrapper edits to the strict minimum (one `def main(): _run()` line per module). If wrapper additions push file count above 5, split per phase boundary in the audit (e.g., 12a overnight modules, 12b skill modules).
- **Verification**: run `bin/cortex-check-parity --staged` — pass if exit 0; AND for each script name `<name>` listed in audit-callsites.md, run `python -c "import importlib; m = importlib.import_module('cortex_command.<module>'); assert callable(getattr(m, 'main', None) or getattr(m, '_main', None))"` — pass if exit 0 for each.
- **Status**: [ ] pending

### Task 13a: Update lifecycle-skill callsites + implement.md §1a launch rewrite (R14 + R10)
- **Files**: `skills/lifecycle/references/implement.md`, `skills/lifecycle/SKILL.md`
- **What**: Replace every `python3 -m cortex_command.<x>` callsite in the lifecycle skill with the promoted console-script name. `skills/lifecycle/references/implement.md:78-100` §1a Step 3 launch line removes its `CORTEX_WORKTREE_ROOT=...` prefix (cortex init registration makes the default work under sandbox now) AND uses the new `cortex-daytime-pipeline` console-script name for the dispatch (R10). Skill prose describes the What and Why without prescribing the env-var mechanism. The dual-source plugin mirror at `plugins/cortex-core/skills/lifecycle/...` is auto-regenerated by the pre-commit hook.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Specific callsite anchors from research.md: `skills/lifecycle/references/implement.md` lines 83, 91, 99, 119; `skills/lifecycle/SKILL.md:80`. Console-script names come from the audit (Task 10's `audit-callsites.md`). Per spec R10: the new launch line uses the promoted console-script for `cortex-daytime-pipeline` and drops the env-prefix. R10 and R14 share the same source-of-truth check — both verify via the parity gate. Reference-before-deployment is permitted by the wiring co-location rule: references can land before `[project.scripts]` entries — the parity gate flags `W003: deployed but not referenced`, not the reverse.
- **Verification**: run `grep -rn 'python3 -m cortex_command\.' skills/lifecycle/` — pass if no hits; AND `grep -c 'python3 -m cortex_command' skills/lifecycle/references/implement.md` — pass if count = 0; AND `bin/cortex-check-parity --staged` — pass if exit 0.
- **Status**: [ ] pending

### Task 13b: Update remaining skill-tree callsites (R14)
- **Files**: `skills/critical-review/SKILL.md`, `skills/critical-review/references/verification-gates.md`, `skills/morning-review/SKILL.md`, `skills/morning-review/references/walkthrough.md`, `skills/discovery/SKILL.md`
- **What**: Replace every `python3 -m cortex_command.<x>` callsite in critical-review, morning-review, and discovery skills with the promoted console-script name (R14). Mechanical search-replace per audited name. The dual-source plugin mirror at `plugins/cortex-core/skills/...` is auto-regenerated.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Callsite anchors from research.md cover the five files in this task's Files field. The audit (Task 10) drives the exact list of names to substitute. If audit-callsites.md surfaces additional skill-tree callsites beyond this set, split into a 13b-bis task or fold into 13c if they land outside `skills/`.
- **Verification**: run `grep -rn 'python3 -m cortex_command\.' skills/critical-review/ skills/morning-review/ skills/discovery/` — pass if no hits; AND `bin/cortex-check-parity --staged` — pass if exit 0.
- **Status**: [ ] pending

### Task 13c: Update non-skill callsites (`hooks/`, `docs/`, `justfile`, `tests/`, `bin/`)
- **Files**: `hooks/cortex-scan-lifecycle.sh`, `docs/overnight-operations.md`, `justfile`, plus any `tests/` and `bin/` files surfaced by the Task 10 audit (target ≤5 files total — if audit surfaces more, split into 13c-bis)
- **What**: Replace every `python3 -m cortex_command.<x>` callsite in the non-skill file groups with the promoted console-script name (R14 remainder). Mechanical search-replace per name. The dual-source plugin mirror at `plugins/cortex-core/hooks/...` and `plugins/cortex-core/bin/...` is auto-regenerated.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: `hooks/cortex-scan-lifecycle.sh:425` is the named overnight scan-lifecycle hook callsite. `docs/overnight-operations.md` references `python3 -m cortex_command.overnight.daytime_pipeline` in install/walkthrough text. Tests directory callsites may include `tests/test_*` files invoking `subprocess.run(["python3", "-m", "cortex_command.<x>", ...])` — those become `subprocess.run(["cortex-<name>", ...])` or stay on `python3 -m` if the test is exercising the module-execution pathway specifically (allowlist those in Task 11's allowlist with rationale).
- **Verification**: run `grep -rn 'python3 -m cortex_command\.' hooks/ docs/ justfile tests/ bin/` — pass if no hits except inside `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/audit-callsites.md` (audit log self-reference) or inside `bin/.audit-bare-python-m-allowlist.md` (allowlisted callsites with rationale); AND `bin/cortex-check-parity --staged` — pass if exit 0.
- **Status**: [ ] pending

### Task 14: Update skill-helper-modules clause in `cortex/requirements/project.md`
- **Files**: `cortex/requirements/project.md`
- **What**: Update the skill-helper-modules clause at `cortex/requirements/project.md:35` to acknowledge console-script invocation as the recommended idiom for promoted modules, with `python3 -m cortex_command.<skill>` retained for ad-hoc invocation (R15).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing clause language: "the ceremony may be collapsed into atomic subcommands of a skill-specific module at `cortex_command/<skill>.py`, invoked from SKILL.md prose via `python3 -m cortex_command.<skill> <subcommand>`" (research.md citation). Updated prose mentions both invocation forms — console-script as recommended and `python3 -m` as readable fallback.
- **Verification**: run `grep -E 'console.script|cortex-<' cortex/requirements/project.md` — pass if match found; AND `grep -c 'python3 -m cortex_command' cortex/requirements/project.md` — pass if count ≥ 1 (the `python3 -m` form is still mentioned as alternative).
- **Status**: [x] complete

### Task 15: Update `skills/overnight/references/new-session-flow.md:3` for dev-clone install path
- **Files**: `skills/overnight/references/new-session-flow.md`
- **What**: Update line 3 (the dev-clone path expectation) to document the dev workflow as `uv pip install -e . --no-deps` against the active `.venv` (R16). Acknowledge that `uv tool install --reinstall` is hostile during partial active sessions (in-flight install guard) and that the existing carve-outs (pytest, `CORTEX_RUNNER_CHILD=1`, dashboard, cancel-force) are unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Why this matters: F3's promotion to console scripts requires reinstall to propagate; the in-flight install guard blocks `--reinstall` during partial active sessions; therefore the dev loop is `uv pip install -e . --no-deps`. The carve-outs are already in place — no new carve-out is added.
- **Verification**: run `grep -c 'uv pip install -e' skills/overnight/references/new-session-flow.md` — pass if count ≥ 1.
- **Status**: [x] complete

### Task 16: Add CHANGELOG.md migration entry for `uv tool install --reinstall`
- **Files**: `CHANGELOG.md`
- **What**: Add an entry to `CHANGELOG.md` documenting that v0.1.0 users must run `uv tool install --reinstall git+<url>@<next-tag>` to pick up the new console-script entries (R17). Note the in-flight install-guard interaction (must not have an active session; carve-outs apply).
- **Depends on**: none
- **Complexity**: simple
- **Context**: CHANGELOG format follows existing entries — version header, prose-line summary, bullet list of changes. The reinstall requirement applies once per v0.1.0 → v0.2.0 upgrade; the carve-out reference is the existing in-flight install-guard documented in `cortex/requirements/pipeline.md`.
- **Verification**: run `grep -c reinstall CHANGELOG.md` — pass if count ≥ 1; AND `grep -A 3 reinstall CHANGELOG.md | grep -ciE 'install.guard|in-flight'` — pass if count ≥ 1.
- **Status**: [x] complete

### Task 17: Add `verify_dispatch_readiness()` fuse called from `run_daytime` Phase A
- **Files**: `cortex_command/overnight/daytime_pipeline.py` (or new `cortex_command/overnight/readiness.py` if cleaner), `cortex_command/overnight/tests/test_dispatch_readiness.py`
- **What**: Add `verify_dispatch_readiness(feature: str) -> ReadinessResult` fusing in order: (a) the auth resolver+probe from Task 3; (b) `probe_worktree_writable(resolve_worktree_root(feature, session_id))` from Tasks 5 + 7. Call from `run_daytime` Phase A immediately after the existing CWD check. On failure, populate `_top_exc` / `_terminated_via="startup_failure"` / `_outcome="failed"` with a structured `error` field naming the failed check (R18). Entry-point importability is intentionally NOT checked — rationale documented in code comment and spec.
- **Depends on**: [3, 7]
- **Complexity**: complex
- **Context**: Spec R18 details the rationale for the two-check (not three-check) design: a `find_spec("claude_agent_sdk")` check is informationally vacuous (the surrounding `daytime_pipeline` module is already imported); a `shutil.which("cortex-daytime-pipeline")` check tests a future invocation's launcher health, not the current dispatch — failing on `which=None` would abort successful launches while passing broken launches. F3 surfaces at process start via Python's normal import-error path or `command not found`. `ReadinessResult` shape: `@dataclass class ReadinessResult: ok: bool; failed_check: Literal["auth", "worktree"] | None; cause: str | None; remediation_hint: str | None`. `daytime-result.json` must include the structured `error` on failed-readiness runs (existing contract at `daytime_pipeline.py:496-554`).
- **Verification**: run `pytest cortex_command/overnight/tests/test_dispatch_readiness.py -q` — pass if exit 0; AND `grep -c 'def verify_dispatch_readiness' cortex_command/overnight/daytime_pipeline.py cortex_command/overnight/readiness.py 2>/dev/null` — pass if count ≥ 1 (whichever location holds the function).
- **Status**: [ ] pending

### Task 18: Add `tests/test_dispatch_parity.py` with acceptance-bar honesty docstring
- **Files**: `tests/test_dispatch_parity.py`
- **What**: Add a CI test that runs `run_daytime` under two synthetic env dicts via `subprocess.run(env={...})`: (a) launchd-shaped env derived from `cortex_command/overnight/scheduler/macos.py:_OPTIONAL_ENV_KEYS` + `PATH`, mirroring `launcher.sh`; (b) Bash-tool-shaped env (sandbox-clean PATH, no `CORTEX_*` snapshot, no preset `ANTHROPIC_API_KEY`) (R19). Uses `cortex_command/tests/_stubs._install_sdk_stub` for hermetic CI. Both invocations against a fixture plan with one trivial task must reach Phase B without `startup_failure`. The module docstring must state explicitly: "This test is a regression freeze of the named F1/F2/F3 failure modes from backlog 208. It uses the SDK stub and synthetic env dicts; it does NOT verify that future Claude Code updates (sandbox profile changes, Bash-tool env-passing changes) preserve dispatch-path parity. For that, run `just test-dispatch-parity-launchd-real` against a real environment." (R21).
- **Depends on**: [12, 17]
- **Complexity**: complex
- **Context**: `_OPTIONAL_ENV_KEYS` lives at `cortex_command/overnight/scheduler/macos.py:53-62` (research.md citation). `_install_sdk_stub` installed by `cortex_command/overnight/tests/conftest.py:33-35`. Existing fixture pattern: `cortex_command/overnight/tests/test_daytime_auth.py` for CWD pinning, env preservation, hermetic fixtures. Phase B detection: after `run_daytime` returns or after the dispatch loop logs the `phase_b_start` (or equivalent) event — assert against `events.log` content rather than internal state. The fixture trivial-task plan can be a one-line scratch plan.md in a `pytest.TempPathFactory`-managed dir.
- **Verification**: run `pytest tests/test_dispatch_parity.py -q` — pass if exit 0; AND `grep -A 5 'regression freeze' tests/test_dispatch_parity.py` — pass if the exact wording from spec R21 appears in the docstring.
- **Status**: [ ] pending

### Task 19: Add `just test-dispatch-parity-launchd-real` opt-in recipe
- **Files**: `justfile`
- **What**: Add a justfile recipe (NOT in the default `just test` aggregator) that fires a real `launchctl bootstrap` against a fixture and compares reach-Phase-B with a Bash-tool invocation in the same shell (R20). macOS-only with platform guard (`[[ "$(uname)" == "Darwin" ]]`, exits 0 with skip message on other platforms). Requires active subscription or `ANTHROPIC_API_KEY`; recipe announces this at invocation start.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Pattern reference: existing justfile recipes around lines 405-417 (`test-overnight`, `test-pipeline`). The launchctl flow uses the existing `cortex_command/overnight/scheduler/macos.py` machinery — recipe body wraps a shell script that schedules a one-shot fire, waits for completion, captures result, then runs the same fixture from a Bash-tool-shaped env in the same shell and compares the two `daytime-result.json` outcomes.
- **Verification**: run `just --list | grep test-dispatch-parity-launchd-real` — pass if match found; AND `grep -A 5 test-dispatch-parity-launchd-real justfile | grep -c uname` — pass if count ≥ 1 (platform guard present).
- **Status**: [x] complete

### Task 20: Produce sandbox preflight artifact `preflight.md`
- **Files**: `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/preflight.md`
- **What**: Generate the sandbox preflight artifact per the gate schema (R22). Includes current `commit_hash`, `claude --version`, and the file list this lifecycle modifies (union of files touched by Tasks 1–19). The file must validate against the parity gate's YAML schema. The artifact regenerates at the end of each phase that extends the touched-file list — this task is the final regeneration; per-phase intermediate regenerations are implementer's responsibility at each phase commit.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13a, 13b, 13c, 14, 15, 16, 17, 18, 19]
- **Complexity**: simple
- **Context**: Gate logic lives in `bin/cortex-check-parity` (`_check_sandbox_preflight_gate`, lines 84-109). Sandbox-source files this lifecycle touches that trip the gate: `pyproject.toml` (Task 12), `cortex_command/pipeline/worktree.py` (Tasks 5, 7, 8 — though this file is NOT in `SANDBOX_WATCHED_FILES`, verify), `cortex_command/overnight/runner.py` (Task 3 — verify watched-files membership), plus any others surfaced during implementation. The exact schema is enforced by the gate's YAML validator — produce a file that matches the existing preflight.md examples elsewhere in the repo. The file list in preflight.md must be a superset of (or equal to) the union of files modified by Tasks 1–19.
- **Verification**: run `bin/cortex-check-parity --staged` — pass if exit 0 with the preflight file staged; AND `[ -f cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/preflight.md ]` — pass if file exists.
- **Status**: [ ] pending

## Risks

- **Tier marking divergence**: `research.md` declares this work `tier=complex`, but no `lifecycle_start` event was emitted during refine, so the canonical state resolves to `tier=simple`. Consequence: §3b critical-review of this plan is skipped, and §1b competing-plans was skipped (criticality=medium anyway). If the user wants critical-review run on this plan, they should emit a `complexity_override` event before approval.
- **Dev-clone install workflow (A6 tension)**: F3's console-script promotion only takes effect for end-users after `uv tool install --reinstall`. For dev iteration, the documented dev loop becomes `uv pip install -e . --no-deps` against the active `.venv` (Task 15) rather than the more obvious `uv tool install --reinstall`, because the in-flight install guard blocks `--reinstall` during partial sessions. Spec deliberately did NOT add a `--during-dev` escape hatch — if contributors find the `uv pip install -e .` loop friction-y, a follow-up may be warranted.
- **R10/R14 reference-before-deployment ordering**: Tasks 13a/13b/13c land prose references to console-script names (e.g., `cortex-daytime-pipeline`) before Task 12 promotes them in `pyproject.toml`, which is permitted by the wiring co-location rule (`W003` flags "deployed but not referenced" only). However, an end-user who pulls between Tasks 13* and Task 12 sees broken `command not found` errors. Mitigation: land the full Phase 3 set as one PR or land Task 12 first.
- **Stub-SDK parity test scope (A8)**: `tests/test_dispatch_parity.py` (Task 18) freezes the current env shape. If Claude Code ships an update that changes the sandbox profile or Bash-tool env-passing, the stubbed test still passes but real dispatch may break. The acceptance-bar-honesty docstring (R21) makes this scope explicit. The opt-in `just test-dispatch-parity-launchd-real` (Task 19) provides the durable mitigation but is NOT in CI default — it requires API key + macOS.
- **Worktree resolver persistence (Q2 sub-question)**: Spec resolved that the resolver lives in `cortex_command/pipeline/worktree.py` and is consulted by `cortex init` (registration) and dispatch (creation+probe), but did NOT lock whether the canonical choice is committed to a config file (e.g., `cortex/lifecycle.config.md` frontmatter) or derived purely from env at runtime. This plan goes with env-derived runtime resolution; if drift becomes a recurring failure mode, a config-persistence follow-up may be needed.
- **Tasks 1+2 in same file**: Task 1 and Task 2 both modify `cortex_command/overnight/auth.py`. They are listed as independent (`Depends on: none`) to enable parallel decomposition, but in practice the implementer may merge them into one edit if running serially. The parity gate is indifferent — both produce additive changes.
