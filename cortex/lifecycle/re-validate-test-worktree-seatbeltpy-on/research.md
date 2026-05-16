# Research: Re-validate `tests/test_worktree_seatbelt.py` on a recurring sandbox-active path

Clarified intent: re-validate `tests/test_worktree_seatbelt.py` on every overnight session start so that a regression in `resolve_worktree_root()` that breaks Seatbelt-writability surfaces automatically rather than only on manual re-run. The user picked Shape A (inject pytest into the smoke runner's orchestrator prompt). Research returned three premise-invalidating findings; the shape choice and the test itself both require reconsideration before Spec proceeds.

## Codebase Analysis

### Files implicated

- `cortex_command/overnight/smoke_test.py` — Shape A's intended surface. **Smoke does NOT spawn a `claude -p` orchestrator session.** `main()` calls `run_batch(config)` (line 265) which goes through `execute_feature → retry_task → pipeline.dispatch.dispatch_task` — the SDK path with `ClaudeAgentOptions`, not the `claude -p` subprocess. The `claude -p` orchestrator at `cortex_command/overnight/runner.py:1030-1049` is only invoked by the full overnight `run()` loop. "Inject pytest into the smoke runner's orchestrator prompt" as stated in the backlog ticket is a category error.
- `cortex_command/overnight/smoke_test.py:173, 253` — Latent bug: both call sites use `os.environ.get(...)` but the file does not `import os`. Introduced by commit `e78c226f` ("Add CLAUDE_CODE_OAUTH_TOKEN support to overnight runner"). Reachable in the OAuth-token / auth-fallback paths. **The smoke runner raises `NameError: name 'os' is not defined` on first invocation in those branches.** Smoke is not a working baseline today.
- `cortex_command/overnight/smoke_test.py:203` — Legacy `.claude/worktrees/{FEATURE_NAME}/.claude/settings.local.json` residue that escaped the R13 sweep of the parent lifecycle's worktree-root rewrite.
- `cortex_command/overnight/runner.py:1030-1049` — Canonical `claude -p --settings <tempfile> --dangerously-skip-permissions --max-turns N --output-format=json` spawn. Stdout redirected to a file (`stdout_path`); no `--allowed-tools` is passed, so CLI defaults apply.
- `cortex_command/pipeline/dispatch.py:542` — **`ClaudeAgentOptions.env` explicitly sets `"CLAUDECODE": ""`** with the comment "Clear CLAUDECODE so the sub-agent doesn't hit the nested-session guard." Implication: any env-var-based gating from inside the SDK dispatch path that selects on `CLAUDECODE` is stripped before the worker runs.
- `cortex_command/pipeline/dispatch.py:597` — `LIFECYCLE_SESSION_ID` defaults to literal `"manual"` when unset. Smoke runs leave it unset.
- `cortex_command/overnight/sandbox_settings.py:106-253` — Reusable library: `build_orchestrator_deny_paths`, `build_sandbox_settings_dict`, `write_settings_tempfile`. `failIfUnavailable: true` at line 195; flipped to `false` only by `CORTEX_SANDBOX_SOFT_FAIL=1` env-var.
- `cortex_command/overnight/orchestrator.py:97-128` — `BatchConfig` defaults: `overnight_state_path = cortex/lifecycle/overnight-state.json`, `pipeline_events_path = cortex/lifecycle/pipeline-events.log`. `session_dir` derives from `overnight_state_path.parent = cortex/lifecycle` — **smoke has no `cortex/lifecycle/sessions/<id>/` directory.**
- `cortex_command/overnight/cli_handler.py:517` — Full overnight session sets `events_path = session_dir / "overnight-events.log"`; smoke does not follow this path.
- `cortex_command/overnight/events.py:90-148` — Gated `log_event` variant with `EVENT_TYPES` allowlist. `f_row_evidence` is NOT in the tuple. The ungated `cortex_command/pipeline/state.py:288 log_event` is the bypass.
- `cortex_command/overnight/feature_executor.py:568` — `IMPLEMENT_TEMPLATE` render site (Shape C blast-radius surface).
- `cortex_command/overnight/prompts/orchestrator-round.md:1-30` — "Thin orchestrator" constraint: "You read state files and status codes only. Do NOT accumulate implementation details in your context." Running pytest as primary work would violate this prose contract.
- `tests/test_worktree_seatbelt.py` — Two `def test_` functions, both gated on `pytest.mark.skipif(os.environ.get("CLAUDE_CODE_SANDBOX") != "1", ...)`. **The env-var name does not match what Claude Code documents as set (see Web Research).**
- `cortex/lifecycle/restore-worktree-root-env-prefix/spec.md:36, 115` — R10 acceptance and F-row schema: `{ts, event=f_row_evidence, feature, test_file, outcome, claude_code_sandbox, pytest_exit_code, pytest_summary, stdout_sha256, ts_recorded_by}`. R10 demands `pytest_summary == "passed=2,failed=0,skipped=0"` as a literal — brittle to test-count drift.
- `cortex/lifecycle/restore-worktree-root-env-prefix/events.log:14` — The single existing `f_row_evidence` event, hand-written by the implementer (`ts_recorded_by: implement-task-11`). No production code emits it; no auditor has re-hashed it; the raw stdout was not preserved.
- `bin/.events-registry.md` — `f_row_evidence` is NOT registered. Adding the literal `"event": "f_row_evidence"` to any skill prompt or `cortex_command/overnight/prompts/*.md` would trip `bin/cortex-check-events-registry`. Python source emissions are `scan_coverage: manual` and do not trip the gate.
- `bin/cortex-check-parity` (sandbox preflight gate watch-list at lines 113-133) — watches `dispatch.py`, `runner.py`, `sandbox_settings.py`, `pyproject.toml`. Smoke_test.py edits do not trip preflight.
- `pyproject.toml:41` — `cortex-smoke-test = "cortex_command.overnight.smoke_test:main"`. Justfile recipe `overnight-smoke-test` at `justfile:77-79`.
- `docs/overnight-operations.md:97, 605` — Documents smoke as "pre-launch toolchain sanity check." Line 605: "Sandbox enforcement is macOS-Seatbelt-only ... behavior under Linux/bwrap is undefined."

### Existing patterns to follow

- **Stdout-to-file, not pipe** (`runner.py:1029`): the `claude -p` orchestrator stdout is captured to a file to avoid Popen pipe-buffer deadlock. Any new probe spawn should follow this.
- **Per-spawn sandbox settings** (`dispatch.py:592-602`, `runner.py:1015-1049`): build dict → write tempfile (mode 0o600, atomic) → pass `--settings <tempfile>`. Already-published contract.
- **JSONL append with atomic write** (`cortex_command.common.atomic_write`, `cortex_command/pipeline/state.py:288`): the established pattern for events.log writes.
- **Cleanup of per-spawn tempfiles** (per `pipeline.md:158`): `atexit.register` on clean shutdown + startup-scan in runner-init for SIGKILL/OOM crash paths.

### Conventions to follow

- Atomic JSON writes for evidence artifacts (`common.atomic_write`).
- Session_id scoping for per-spawn artifacts under `cortex/lifecycle/sessions/{session_id}/`.
- Event-emission literals from prompts must be registered in `bin/.events-registry.md`; emissions from Python source are `scan_coverage: manual`.
- Smoke today is a Python subprocess (not a Claude Code session); to reuse the documented `claude -p --settings <tempfile>` pattern, a new spawn site is required.

## Web Research

### `CLAUDE_CODE_SANDBOX` is not a documented env var

The test's skipif gate (`tests/test_worktree_seatbelt.py:48, 67`) is `os.environ.get("CLAUDE_CODE_SANDBOX") != "1"`. The official Claude Code env-vars reference (`https://code.claude.com/docs/en/env-vars`) documents three closely-named-but-distinct variables, none of which is `CLAUDE_CODE_SANDBOX`:

1. **`CLAUDECODE=1`** — set by Claude Code in shell environments it spawns (Bash tool, tmux sessions). Documented contract: "Use to detect when a script is running inside a shell spawned by Claude Code." Confirmed independently by `anthropics/claude-agent-sdk-python` issue #573, which describes a bug where SDK-spawned subprocesses inherit `CLAUDECODE=1` from the parent Claude Code process.
2. **`CLAUDE_CODE_SANDBOXED`** (with -ED suffix) — a USER-set var that tells Claude Code to skip the trust dialog ("sandbox-already-active" hint, added v2.1.94). NOT injected by Claude Code into Bash.
3. **`IS_SANDBOX`** — internal; gates `--dangerously-skip-permissions` per `setup.ts:406`. Not set inside Bash.

The Cortex code's only support for the `CLAUDE_CODE_SANDBOX` name is `cortex/lifecycle/restore-worktree-root-env-prefix/research.md:106` citing `anthropics/claude-code` issue #10952 — but reading #10952, it is `platform:linux` and demonstrates the var inside bwrap (Linux), not Seatbelt (macOS). The official macOS sandboxing docs (`https://code.claude.com/docs/en/sandboxing`) describe OS-level enforcement but make no claim about what env vars are injected. Cortex runs on macOS; the cited evidence is for the platform Cortex does not target.

**Implication**: a pytest test gated on `CLAUDE_CODE_SANDBOX=1` will skip in every Claude-Code-spawned automation context on macOS Seatbelt. The smoke runner's `passed=2` assertion cannot distinguish "sandbox correctly enforces" from "test silently skipped" — exactly the failure mode the parent lifecycle's `critical-review-residue.json` flagged.

### `--dangerously-skip-permissions` does NOT disable Seatbelt (premise check claim confirmed)

Confirmed by official sandboxing docs: sandbox restrictions "are enforced at the OS level (Seatbelt on macOS, bubblewrap on Linux), so they apply to all subprocess commands." `dangerously-skip-permissions` and Seatbelt are explicitly orthogonal layers. Issue #52322 reinforces: even with a writable path in `allowWrite`, the Seatbelt kernel policy can still reject `unlink` with `Operation not permitted`.

### Settings JSON sandbox schema (premise check confirmed)

Canonical schema at `https://code.claude.com/docs/en/settings`:

- `sandbox.enabled: boolean` (default false).
- `sandbox.failIfUnavailable: boolean` (default false) — "Intended for managed settings deployments that require sandboxing as a hard gate." Matches Cortex's `failIfUnavailable: true` use.
- `sandbox.filesystem.{allowWrite, denyWrite, denyRead, allowRead}: string[]` — merged across settings scopes.

macOS uses Seatbelt for enforcement (`https://code.claude.com/docs/en/sandboxing`).

### `claude -p` headless invocation guidance

From `https://code.claude.com/docs/en/headless`:

- `--output-format json` returns a structured envelope with `result` (text), `session_id`, metadata. Extract via `jq -r '.result'`.
- `--bare` flag (will become `-p` default) skips auto-discovery of hooks/skills/plugins/MCP/CLAUDE.md. Recommended for scripted/CI use. In bare mode default tools are Bash, Read, Edit. Auth via `ANTHROPIC_API_KEY` or `apiKeyHelper`.
- `--max-turns` is the documented circuit-breaker for runaway agentic loops.

### Known gotchas

- **No hot-reload of settings.json mid-session** — each new `claude` invocation re-reads fresh; fine for one-shot probe; mid-session settings change will not propagate.
- **Issue #36139**: `--permission-mode bypassPermissions` / `--dangerously-skip-permissions` does not work as expected with `claude -p --resume`; write tools can stay blocked. Fresh-each-time avoids this.
- **Issue #33249**: Claude Code may unilaterally propose disabling the sandbox via `dangerouslyDisableSandbox: true` when commands fail. To block this, set `"allowUnsandboxedCommands": false` in settings — otherwise a failing test can be retried unsandboxed and a misleading "passed" gets reported.
- **Issue #26616**: Sandbox is Bash-only — Read/Write/Edit/Glob/Grep run outside Seatbelt in the parent. Pytest invocation via Bash is therefore the right invocation channel.
- **RAXE-2026-059 (CVE-2026-39861)**: known Seatbelt-escape symlink-following bypass. Treat `passed=2` as not absolute proof of containment.

### Key URLs

- `https://code.claude.com/docs/en/sandboxing`
- `https://code.claude.com/docs/en/settings`
- `https://code.claude.com/docs/en/env-vars`
- `https://code.claude.com/docs/en/headless`
- `https://github.com/anthropics/claude-code/issues/52322`
- `https://github.com/anthropics/claude-code/issues/36139`
- `https://github.com/anthropics/claude-code/issues/26616`
- `https://github.com/anthropics/claude-code/issues/33249`
- `https://github.com/anthropic-experimental/sandbox-runtime`

## Requirements & Constraints

### Smoke gate's requirements footprint is thin

- `pipeline.md:150` — one Dependencies line: "Smoke test gate (`cortex_command/overnight/smoke_test.py`) — post-merge verification." No functional-requirement section, no acceptance criteria, no input/output contract.
- `observability.md:144` — classifies `python3 -m cortex_command.overnight.smoke_test` as a non-install-mutation invocation.
- `docs/overnight-operations.md:97` and `docs/overnight.md:95, 247, 265` describe smoke as a "pre-launch sanity check that verifies worker commit round-trip." Docs framing, not a requirement.
- No requirement specifies *what runs* during smoke (no 1-line-markdown-write constraint, no pytest-forbidden constraint). The current behavior is implementation, not requirement.

### Architectural constraints touched by any shape

- **`multi-agent.md:23` (must-have, Agent Spawning)**: every `claude -p` orchestrator spawn AND every per-feature dispatch MUST pass `--settings <tempfile>` with the sandbox dict. Permission mode is always `bypassPermissions`. `CORTEX_SANDBOX_SOFT_FAIL=1` downgrades `failIfUnavailable` to `false`; activation is unconditionally surfaced in the morning report. Smoke does not currently spawn `claude -p`; if it grows one (Shape A) or a new probe is added (Shape B), the new spawn MUST comply.
- **`pipeline.md:158`**: per-spawn sandbox-settings tempfiles live at `cortex/lifecycle/sessions/{session_id}/sandbox-settings/cortex-sandbox-*.json` (mode 0o600, atomic). Created by `_spawn_orchestrator` AND per-dispatch in `dispatch.py`. Cleaned via `atexit.register` + startup-scan. Smoke has no session_id today (`dispatch.py:597` defaults to `"manual"`).
- **`multi-agent.md:77`**: `resolve_worktree_root()` in `cortex_command/pipeline/worktree.py` is the single chokepoint for same-repo and cross-repo worktree paths. This is the regression target the ticket guards against.
- **`pipeline.md:129`**: audit trail is `cortex/lifecycle/pipeline-events.log` (append-only JSONL).
- **Events registry (`bin/.events-registry.md`)**: gate-enforced for every `"event": "<name>"` literal in skill prompts and `cortex_command/overnight/prompts/*.md`. `f_row_evidence` is unregistered today. Closest precedent is `auth_probe` (added 2026-05-12) with both `overnight-events-log` and `per-feature-events-log` targets.
- **`pipeline.md:24` (morning report)**: written to `cortex/lifecycle/sessions/{session_id}/morning-report.md` (per-session archive) AND `cortex/lifecycle/morning-report.md` (tracked latest). The morning report is the precedent surface for "unconditionally surface this state to the operator."
- **`project.md:31`**: "New events register in `bin/.events-registry.md`."
- **`project.md:39`**: "Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface." Reinforces every spawn must carry `--settings`.

### Parent lifecycle residue (corroborates this ticket's purpose)

`cortex/lifecycle/restore-worktree-root-env-prefix/critical-review-residue.json` (2026-05-16T02:25:25Z) flagged this exact failure mode at plan time:

> Task 11 plan text says `CLAUDE_CODE_SANDBOX=1` is set by the harness but provides no precondition check — if implementer runs from a non-sandbox shell and pytest reports skipped, nothing instructs them to inspect output before writing `outcome:passed`.

That residue did not block plan approval. This ticket is the durable fix. Web Research findings (wrong env-var name) and Adversarial Review findings (single implementer-attested event with no raw-stdout preservation) suggest the parent lifecycle's existing `f_row_evidence` event itself is a candidate for the failure mode it claims to defeat.

### Direct conflicts with Shape A as proposed in the ticket

1. **Smoke does not spawn `claude -p`.** `multi-agent.md:23`'s per-spawn-settings contract requires it for any new spawn. Shape A's "inject into the smoke orchestrator's prompt" has no surface to inject into.
2. **`pipeline.md:158` session-id discipline.** Per-spawn settings tempfiles must live under `cortex/lifecycle/sessions/{session_id}/sandbox-settings/`. Smoke's `LIFECYCLE_SESSION_ID` is unset → defaults to `"manual"` → pollutes a shared `sessions/manual/` namespace.
3. **`bin/.events-registry.md` gate.** Shape A's event-emission literal in a prompt requires a registry row. Shape B writes from Python (manual scan-coverage, no gate trip) — easier path.
4. **`orchestrator-round.md:1-7` "thin orchestrator" prose constraint.** Running pytest as primary work inside an orchestrator session contradicts the existing prose contract.
5. **`pipeline.md:150` reframing.** Shape A turns smoke from "post-merge verification" into "session-start re-validation." Scope expansion requires an explicit acceptance-criterion addition in `pipeline.md`.

## Tradeoffs & Alternatives

### Shape A (chosen pre-research): inject pytest into the smoke runner's task description

The ticket's stated "inject into the smoke runner's orchestrator prompt" does not match the code: smoke calls `run_batch` in-process, dispatching the worker via the SDK (not `claude -p`). The realistic interpretation is "modify the smoke feature's dispatched task description so the worker runs pytest" — i.e., a per-feature dispatch prompt modification, not an orchestrator modification. ~30–60 LOC in `smoke_test.py:56-81` and the smoke runner.

**Pros**: tight LOC delta; reuses smoke's existing dispatch path; couples evidence cadence to smoke schedule.

**Cons**:
- Surface confusion (the ticket described a surface that doesn't exist).
- Stdout-grep is brittle to multi-turn refactors and to `--output-format=json` envelope shape.
- `tests/test_worktree_seatbelt.py` writability from inside the dispatched worker (worktree is in the allow-set) is a prompt-injection risk: a future feature dispatch that modifies the test could forge passes.
- Couples smoke gate to seatbelt regression — a sandbox-runtime upgrade or kernel quirk that breaks the test blocks the morning report from merging, far beyond ticket intent.
- "passed=2" literal-equality on a test with two functions is brittle to test-count drift.

### Shape B (alternative — strongest fit on the merits): standalone `cortex-seatbelt-probe`

A new `cortex_command/overnight/seatbelt_probe.py` + `[project.scripts]` entry + justfile recipe (`just seatbelt-probe`). Spawns `claude -p "uv run pytest tests/test_worktree_seatbelt.py -v" --settings <tempfile> --dangerously-skip-permissions --max-turns 4 --output-format=json --bare`. Reuses `sandbox_settings.{build_*, write_settings_tempfile}` library verbatim. Parses the JSON envelope for the pytest summary; appends an F-row event to a top-level `cortex/lifecycle/seatbelt-probe.log`. ~80–120 LOC.

**Pros**:
- Direct instantiation of `multi-agent.md:23`'s `claude -p --settings <tempfile>` per-spawn pattern.
- Top-level `seatbelt-probe.log` accumulates indefinitely — best evidence-durability fit (matches the ticket's `evidence-durability` tag).
- Decouples seatbelt from smoke; pytest flakiness doesn't break smoke, smoke breakage doesn't suppress probe signal.
- Python-source emission of `f_row_evidence` is `scan_coverage: manual` in the events registry — no gate trip.
- Testable from a maintainer terminal in isolation.

**Cons**:
- Needs cadence wiring (cron, pre-merge hook, or a session-start hook in the overnight runner). Without it, the probe runs only on demand.
- Session-less artifact home: if the probe reuses `dispatch.py`'s session_id default, tempfiles pollute `cortex/lifecycle/sessions/manual/`. Mitigation: probe takes an explicit `--session-id` (e.g., `seatbelt-probe-{YYYY-MM-DD}`), writing its tempfile to `cortex/lifecycle/sessions/<probe-session-id>/sandbox-settings/` per pipeline.md:158 taxonomy.

### Shape C (alternative): per-feature orchestrator prompt prefix

Modify `IMPLEMENT_TEMPLATE` (`feature_executor.py:568`) to prefix every per-feature dispatch with the seatbelt test invocation. ~20–40 LOC. Highest signal density but highest blast radius and self-referential risk when a feature edits `resolve_worktree_root()` itself. Violates the documented "orchestrator's primary task work shouldn't be infrastructure validation" framing.

### Comparative assessment

| Dimension | Shape A | Shape B | Shape C |
|---|---|---|---|
| Implementation complexity | ~30–60 LOC, 1 file | ~80–120 LOC, 1 new file + entry-point + recipe | ~20–40 LOC, 2 files, touches every dispatch implicitly |
| Maintainability (drift surface) | Stdout-grep brittle; mixes smoke + seatbelt | Reuses `sandbox_settings.py`; isolated | Self-referential on worktree-resolver edits |
| Performance (critical path) | Adds pytest time to smoke (~5–15s) | Zero overhead on overnight critical path | ~5–15s × N features per batch |
| Alignment with `claude -p --settings` pattern | Inherits incidentally | **Direct instantiation** | Doesn't extend spawn pattern |
| Evidence durability | Per-session events.log (archived) | **Top-level seatbelt-probe.log accumulates indefinitely** | F-rows scatter across many events.logs |
| Events-registry gate compliance | Trips gate if emission literal lives in a prompt | Bypasses gate (Python source emission) | Trips gate (every per-feature prompt) |

**Recommended approach**: Shape B (overrides the user's Shape A choice on the merits). The ticket's own Recommendation block (lines 50–52) said "Shape B is the best fit for `should-have` priority" — research re-validates that pick across maintainability, pattern-alignment, evidence-durability, and registry-gate compliance. The Shape A pick was made on a false premise (a smoke orchestrator surface that does not exist). To affirm Shape A anyway, the rationale would have to be "I want pytest failure to BLOCK the smoke gate (and thereby the morning-report merge)" — a defensible stance, but one that should be made consciously rather than by accident.

## Adversarial Review

### Failure modes and edge cases

1. **`CLAUDECODE` is explicitly cleared in the SDK dispatch path.** `cortex_command/pipeline/dispatch.py:542` sets `"CLAUDECODE": ""` in `ClaudeAgentOptions.env` with the comment "Clear CLAUDECODE so the sub-agent doesn't hit the nested-session guard." Implication: Web Research's recommended fix (gate the test on `CLAUDECODE`) is empirically broken in this codebase. Any env-var-based gate that survives dispatch.py:542 requires an env-var the dispatch path does NOT clear — and the dispatch path's clearing list is itself silent and undocumented. The robust gate is a kernel-level capability probe (attempt write to a known denyWrite path → assert EPERM), not env-var introspection.

2. **The single existing `f_row_evidence` event is a candidate for the failure mode it claims to defeat.** Implementer-attested (`ts_recorded_by: implement-task-11`), single source, no auditor re-hash, raw stdout not preserved. If `CLAUDE_CODE_SANDBOX=1` was not actually set by Seatbelt on macOS when the event was recorded (Web Research says no documented contract supports this), the test silently skipped and the F-row recorded `outcome:passed` falsely. The parent lifecycle's R10/R11 evidence chain may be a Potemkin gate; the existing event should be re-replayed under a kernel-probe gate before being trusted.

3. **Smoke is broken today.** The `os` import bug at smoke_test.py:173, 253 (introduced by commit `e78c226f`) raises `NameError` on first invocation in OAuth-token / auth-fallback paths. No shape is implementable until this is fixed. This is a P0 prerequisite, not a shape question.

4. **Stdout-grep is structurally fragile.** `claude -p --output-format=json` returns a JSON envelope where the pytest summary line is buried inside `messages[].content[].text` or the top-level `result`. Parsing it as a literal `grep "passed=2"` requires the model not to wrap, summarize, paraphrase, or omit the pytest output in its turn-final summary. Multi-turn refactors of the orchestrator prompt (already on the agenda) will routinely change envelope shape.

5. **`f_row_evidence` is unregistered.** Shape A and C trip `bin/cortex-check-events-registry` (prompts are gate-scanned). Shape B does not (Python-source emissions are `scan_coverage: manual`). Independent of shape, the event should be registered if it is to be a durable convention.

6. **Test-count drift breaks R10's literal-equality assertion.** R10 demands `pytest_summary == "passed=2,failed=0,skipped=0"`. Adding a third test function silently flips the gate to fail-closed with no diagnostic. The integrity check should match `passed >= 2 AND failed == 0 AND skipped == 0 AND error == 0`, or the literal-2 must be documented as a coupled constant.

7. **Session-less probes pollute `sessions/manual/`.** A Shape B probe that reuses `dispatch.py`'s helpers would write its sandbox-settings tempfile under `cortex/lifecycle/sessions/manual/sandbox-settings/` (because `LIFECYCLE_SESSION_ID` is unset). Mitigation: probe takes an explicit `--session-id` arg defaulting to a unique probe-session ID (e.g., `seatbelt-probe-{YYYY-MM-DDTHH-MM-SSZ}`).

### Security concerns and anti-patterns

8. **Prompt-injection forgery of the F-row.** The dispatched worker context has the worktree in the writable allow-set, which includes `tests/`. A future dispatched feature that modifies `tests/test_worktree_seatbelt.py` could change the test body and still report `passed=2`. The kernel-probe gate (mitigation below) eliminates env-var spoofing but not test-body modification. Mitigation: hash the test file as part of the F-row event so a later auditor can detect drift.

9. **Forgery-friendly integrity binding.** `stdout_sha256` and `pytest_summary` are recorded by the same agent that runs pytest; the raw stdout is hashed but not preserved. The auditor's re-hash defense (`plan.md:119`) is empty without source bytes. Mitigation: dump raw pytest stdout to a sibling artifact at `cortex/lifecycle/<probe-session-id>/seatbelt-stdout.txt` and reference it by path + content-hash in the F-row.

10. **`allowUnsandboxedCommands: false` is not set on Cortex's sandbox-settings dict today.** Claude Code can propose `dangerouslyDisableSandbox: true` on command failure (issue #33249). If pytest fails inside a Shape A/B/C session and Claude retries with the sandbox disabled, the test then passes and the F-row records "passed" — a silent false positive. The sandbox-settings dict must include `"allowUnsandboxedCommands": false` to make `dangerouslyDisableSandbox` ignored.

### Assumptions that may not hold

- **"The smoke orchestrator session is where `CLAUDE_CODE_SANDBOX=1` is set."** No smoke orchestrator exists; the env-var name is not documented on macOS.
- **"The existing F-row evidence is trustworthy."** Single implementer-attested data point; raw stdout not preserved; auditor re-hash not possible.
- **"Shape choice is the high-priority decision."** It is not. The P0 prerequisites (fix `os` import; replace env-var gate with kernel probe; register the event) make any shape implementable; without them, no shape works.
- **"`CLAUDE_CODE_SANDBOX` is a stable Anthropic env-var contract."** It is undocumented and unrelated to any documented var. Tests gated on it are brittle to sandbox-runtime evolution.

### Recommended mitigations

1. **Fix `cortex_command/overnight/smoke_test.py`'s missing `import os` as a P0 prerequisite** — one-line commit, decoupled from any shape decision.
2. **Replace env-var gating in `tests/test_worktree_seatbelt.py` with a kernel-level capability probe.** Attempt to write a sentinel under a known-denied path (e.g., `~/.bashrc`-equivalent under repo, or `/etc/passwd`); if the write succeeds, `pytest.skip("sandbox not active (probe wrote to denyWrite path)")`. Robust to env-var renaming, dispatch-path clearing, and platform differences (Seatbelt vs bwrap). This subsumes Web Research's recommendation.
3. **Register `f_row_evidence` (or a successor name) in `bin/.events-registry.md`** with target = `cortex/lifecycle/seatbelt-probe.log` (top-level) plus per-session `events.log` if Shape B emits to both. Avoids gate trips and documents the consumer surface.
4. **Adopt Shape B with an explicit session-id.** `cortex-seatbelt-probe` console script taking `--session-id <id>` (defaulting to `seatbelt-probe-{YYYY-MM-DDTHHMMSSZ}`). Sandbox-settings tempfile under `cortex/lifecycle/sessions/<probe-session-id>/sandbox-settings/`. F-row emission to top-level `cortex/lifecycle/seatbelt-probe.log` + per-session `events.log`. Raw pytest stdout dumped to `cortex/lifecycle/sessions/<probe-session-id>/seatbelt-stdout.txt` and referenced from the F-row.
5. **Add `"allowUnsandboxedCommands": false` to the sandbox-settings dict** for the probe spawn (and consider for all Cortex spawns; out of scope for this ticket but a follow-up).
6. **Cadence**: minimum viable is a `just seatbelt-probe` recipe (operator-runnable) plus a probe invocation at overnight session-start (in the runner's pre-orchestrator-spawn pre-flight, alongside `auth_probe`). Cron and pre-commit hooks deferred to follow-up.
7. **Re-replay the existing `f_row_evidence` event under the kernel-probe gate** before treating any future event as evidence. The parent lifecycle's R10/R11 chain should be re-attested with the gate fix in place.
8. **Hash the test file** as part of the F-row (e.g., `test_file_sha256`) so future auditors can detect drift from a known-good version.

## Open Questions

1. **Resolved (user, 2026-05-16)**: Switch from Shape A to Shape B. Standalone `cortex-seatbelt-probe` console script, direct instantiation of `multi-agent.md:23`'s `claude -p --settings <tempfile>` per-spawn pattern.

2. **Resolved (user, 2026-05-16)**: P0 test-correctness fixes (kernel-probe gate in `tests/test_worktree_seatbelt.py`, `os` import fix in `smoke_test.py`, `f_row_evidence` row in `bin/.events-registry.md`) are in scope for this ticket. Recurring re-validation is not achievable without them.

3. **Resolved (user, 2026-05-16)**: same as Q2 — `smoke_test.py` `os` import fix is in scope for this ticket.

4. **Resolved (user, 2026-05-16)**: Cadence is built-in at overnight session-start in the runner pre-flight (alongside `auth_probe`). Every overnight session re-validates Seatbelt-writability; F-row evidence accumulates per overnight cycle.

5. **Deferred to Spec**: Whether the probe writes to per-session `events.log` in addition to the top-level `seatbelt-probe.log` is a Spec-phase design question. Default leaning is dual emission for symmetry with `auth_probe`; the Spec phase will confirm with the user during the structured interview.

6. **Deferred to Spec**: Whether `"allowUnsandboxedCommands": false` is scoped to the probe spawn only or rolled into `build_sandbox_settings_dict()` for all Cortex spawns is a Spec-phase scope question. Default leaning is probe-only with a follow-up note in `bin/.events-registry.md` / `docs/overnight-operations.md`; the broader rollout is out-of-scope for this ticket.

7. **Deferred to Spec**: Treatment of the existing `f_row_evidence` event in `cortex/lifecycle/restore-worktree-root-env-prefix/events.log:14` (retroactive annotation vs. overwrite-on-next-probe vs. quarantine) is a Spec-phase scope question. Default leaning is overwrite-on-next-probe (the next built-in pre-flight probe produces a kernel-probe-gated event that supersedes the implementer-attested one); explicit re-attestation is out-of-scope.
