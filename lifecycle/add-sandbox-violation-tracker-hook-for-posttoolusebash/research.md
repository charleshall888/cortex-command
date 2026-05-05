# Research: Add sandbox-violation tracker hook for PostToolUse(Bash)

> Backlog: [[164-add-sandbox-violation-tracker-hook-for-posttooluse-bash]]
> Parent epic: 162 (Sandbox overnight agents at the OS layer)
> Blocker (defines what's denied at kernel level): #163
> Discovery: `research/sandbox-overnight-child-agents/research.md` (RQ6, RQ8, DR-5)

## Codebase Analysis

### Files that will change

| Path | Change | Why |
|------|--------|-----|
| `claude/hooks/cortex-sandbox-violation-tracker.sh` | **Create** | New PostToolUse(Bash) hook (canonical source) |
| `plugins/cortex-overnight-integration/hooks/cortex-sandbox-violation-tracker.sh` | **Create (auto, via `just build-plugin`)** | Plugin mirror — DO NOT hand-edit |
| `plugins/cortex-overnight-integration/hooks/hooks.json` | **Modify** lines 23–32 | Register new hook in PostToolUse array |
| `justfile` | **Modify** the `HOOKS=(...)` manifest at line ~487 | Without this, `just build-plugin` will not sync the canonical hook into the plugin tree → pre-commit dual-source check fails |
| `cortex_command/overnight/report.py` | **Modify** | Add aggregation for sandbox-denial telemetry — exact lines depend on chosen approach (A or D, see Tradeoffs) |
| `docs/overnight-operations.md` | **Modify** Observability section | New "Sandbox-Violation Telemetry" subsection per ticket AC |
| `tests/` | **Add** | Hook unit test + positive-control acceptance test (see Adversarial #3) |

### Relevant existing patterns

- **Canonical hook model**: `claude/hooks/cortex-tool-failure-tracker.sh` (89 lines). Demonstrates: PostToolUse JSON payload parsing via `jq -r '.field // empty'`; session keying with fallback to date; safe directory creation (`mkdir -p ... 2>/dev/null || true`); structured YAML-like log appends; threshold-N additionalContext emission; unconditional `exit 0` (non-blocking advisory). **Note**: this hook is NOT gated on `CORTEX_RUNNER_CHILD` — fires for all sessions including interactive.
- **Sibling-hook precedent**: `claude/hooks/cortex-skill-edit-advisor.sh` is a standalone sibling to the failure tracker — confirms cortex's pattern is "one hook, one responsibility" rather than "extend the tracker."
- **Hook registration**: `plugins/cortex-overnight-integration/hooks/hooks.json` lines 23–31 — multiple `type: command` entries fire sequentially on PostToolUse(Bash). `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin install dir.
- **Spawn-time env injection** (where `CORTEX_RUNNER_CHILD=1` is set): `cortex_command/overnight/runner.py:921` (orchestrator spawn) and `runner.py:1132` (per-feature dispatch via `cortex_command/pipeline/dispatch.py`).
- **Morning report aggregator**: `cortex_command/overnight/report.py`. Existing pattern — `collect_tool_failures()` reads `/tmp/claude-tool-failures-{session_id}/`; `render_tool_failures()` emits a count line; `generate_report()` conditionally appends the section.
- **Overnight session events stream**: `lifecycle/sessions/{overnight-id}/overnight-events.log` (JSONL append log, written via `cortex_command/overnight/events.py:log_event()`). Path is registered in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` by `cortex init`.
- **events.log consumers (verified)**: `cortex_command/dashboard/data.py:325-327` (`parse_events`) and `cortex_command/overnight/runner.py:325-334` (`read_events`). Both filter on **explicit named event types** — `feature_start`, `feature_complete`, `phase_transition`, `session_start`, `dispatch_start`, etc. **No wildcards.** Adding a `sandbox_denial` event type does NOT auto-surface anywhere except wherever a new consumer is wired. **The morning-report count line is the only documented consumer.**

### Dual-source enforcement (correction to common assumption)

`bin/cortex-check-parity` does NOT scan `plugins/*/hooks/*.sh` — its `SCAN_GLOBS` covers `claude/hooks/cortex-*.sh` and top-level `hooks/cortex-*.sh` only. The mirror is enforced via:
1. `just build-plugin` rsync logic at `justfile:498-500` — copies canonical sources into plugin trees.
2. `.githooks/pre-commit` Phase 4 runs `just build-plugin` and then `git diff --quiet -- "plugins/$p/"` to detect drift.

**Implication for the spec**: edit ONLY `claude/hooks/cortex-sandbox-violation-tracker.sh`; the plugin mirror is auto-generated. The `HOOKS=(...)` manifest in `justfile:487` for `cortex-overnight-integration` MUST be updated to include the new hook, otherwise `just build-plugin` won't sync it and pre-commit will block.

### Latent bug discovered (impacts approach choice)

The existing `cortex-tool-failure-tracker.sh` writes to `/tmp/claude-tool-failures-${INPUT.session_id}/` where `INPUT.session_id` is the **Claude SDK UUID** (e.g., `1a029692-a434-47f4-935a-b2ff351f017a`) per the documented PostToolUse payload schema. But `cortex_command/overnight/report.py:200-205` calls `collect_tool_failures(data.session_id)` where `data.session_id` is `state.session_id` (e.g., `overnight-2026-04-21-1708`, set in `state.py:255`). **These two namespaces never coincide** — the morning report's `tool_failures` aggregation reads paths the hook never writes to and is silently always empty. **Cloning this pattern for sandbox denials reproduces the bug.** Spec must resolve session-id namespace before ship.

### New-hook vs extend-existing-hook (factual analysis)

**Sibling-hook structural fit (Alternative A in Tradeoffs)**:
- Matches local convention (skill-edit-advisor.sh is a standalone sibling).
- Clean report bifurcation: separate `collect_sandbox_denials()` / `render_sandbox_denials()`.
- Threshold-3 incompatibility: tool-failure-tracker fires additionalContext at exactly N=3; sandbox denials want N=1 (every attempt is signal). Mixing under one hook's threshold logic is awkward.
- Cost: one extra hook fork+exec per Bash call (~20–60ms on macOS).

**Extend-existing-hook structural fit (Alternative B)**:
- ~15 LOC delta inside cortex-tool-failure-tracker.sh.
- Mixes concerns; the existing tracker is currently ungated, conditionally gating only the new branch on `CORTEX_RUNNER_CHILD=1` produces awkward branching.
- Single hook invocation (no extra fork).

Recommendation deferred to Tradeoffs section.

## Web Research

### PostToolUse hook payload (canonical)

Source: https://code.claude.com/docs/en/hooks. Verbatim shape:

```json
{
  "session_id": "abc123",                    // SDK UUID — NOT cortex overnight-id
  "transcript_path": "/Users/.../*.jsonl",
  "cwd": "/Users/my-project",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "npm test",
    "description": "Run test suite",
    "timeout": 120000,
    "run_in_background": false
  },
  "tool_response": {
    "exit_code": 0,
    "stdout": "...",
    "stderr": ""
  }
}
```

Optional `agent_id` / `agent_type` only when the hook fires inside a sub-agent.

### Sandbox-denial stderr signatures (the critical finding)

**macOS Seatbelt**: the structured denial line `Sandbox: <process>(<PID>) deny(1) <op> <path>` (e.g., `Sandbox: bash(28961) deny(1) file-write-create /Users/.../foo.txt`) goes to the **macOS unified log** (`log stream --predicate 'process == "sandbox-exec"' --style syslog`), **NOT to the Bash subprocess's stderr**. The shell-visible stderr from a sandbox-denied write is the bare POSIX `Operation not permitted` message — indistinguishable from chmod/ACL/SIP/EROFS denial without additional context.

**Linux bwrap**: runtime denials produce pure POSIX EPERM in stderr with NO `bwrap:` prefix marker (only setup failures get bwrap-prefixed). Additional asymmetry: on Linux, mandatory deny only blocks files that ALREADY EXIST (bind-mount overlay limitation).

**sandbox-runtime denial side channel**: `@anthropic-ai/sandbox-runtime` (used by Claude Code) does NOT expose a documented structured filesystem-denial channel — there is a `SandboxViolationStore` symbol in source but its API is undocumented. macOS detection requires tailing the unified log; Linux has no equivalent. **Pure-stderr classification is the only cross-platform mechanism currently feasible without taking an internal-API dependency.**

### `additionalContext` shape and pitfalls

Confirmed: `{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: "..."}}` on stdout, exit 0. Hard size cap **10,000 characters** for additionalContext / systemMessage / stdout; over-cap → auto-spilled to a file with a path+preview returned. Exit-code semantics:
- Exit 0 → JSON parsed, context injected.
- Exit 2 → **BLOCKING error**, stderr shown to Claude, JSON ignored, tool result NOT added to context. **Wrong for an audit hook.**
- Other non-zero → first line of stderr in transcript as non-blocking notice.

### Hook env-var propagation gap (critical for the proposed gate)

**anthropics/claude-code#9447**: `CLAUDE_PROJECT_DIR` does NOT propagate when hooks are configured in a plugin's `hooks.json` (only `CLAUDE_PLUGIN_ROOT` is populated there). Issue is closed but no resolution comment captured. Custom env vars (`CORTEX_RUNNER_CHILD=1`) are not addressed in docs and not covered by either of the open env-propagation issues. **Custom env propagation through plugin-hook spawn is NOT guaranteed.** This is the surface the proposed hook lives on. Verification path: deploy a 5-line probe hook in the plugin's hooks.json that writes `${CORTEX_RUNNER_CHILD:-UNSET}` to a tmpfile; spawn one orchestrator child; inspect.

### Documented anti-pattern (openai/codex#18711)

Codex's `is_likely_sandbox_denied` did substring matching for `sandbox` / `permission denied` / `operation not permitted` against **merged stdout+stderr** and produced false positives:
- Project paths containing the word "sandbox".
- `find` partial-permission errors emitting `Operation not permitted` on otherwise-successful runs.
- Successful results merged into stderr field before scanning.

**Recommendations from that thread (translate directly to #164)**:
- Stderr-only, never merged streams.
- Bare `Operation not permitted` is **NOT** a reliable sandbox marker — overlaps chmod/ACL/SIP/EROFS/etc.
- Anchor regex on stable platform markers (`^Sandbox: \S+\(\d+\) deny\(\d+\)` for macOS, `bwrap:` for Linux setup) — but those markers are in the **unified log on macOS, not stderr**, so a stderr-only classifier has a coverage gap on macOS.
- Combine with explicit deny-list path matching against `tool_input.command` for high-precision classification.

### Prior art

- **disler/claude-code-hooks-multi-agent-observability** — closest reference. Captures all 12 hook events, ships them to a Bun server + SQLite, dedicated `post_tool_use_failure.py` per event type. Validates the typed-event observability shape but uses an HTTP-and-DB stack cortex deliberately rejects (file-based state per requirements/project.md).
- **disler/claude-code-hooks-mastery** — payload schema reference.
- Sandboxing docs: https://code.claude.com/docs/en/sandboxing — note `allowUnsandboxedCommands: false` setting that disables the `dangerouslyDisableSandbox` escape hatch.

### Sources

- https://code.claude.com/docs/en/hooks (canonical hook schema, additionalContext shape, exit-code semantics)
- https://code.claude.com/docs/en/sandboxing (sandbox model)
- https://github.com/anthropic-experimental/sandbox-runtime
- https://deepwiki.com/anthropic-experimental/sandbox-runtime/6.2-macos-sandboxing
- https://github.com/anthropics/claude-code/issues/9447 (CLAUDE_PROJECT_DIR plugin-hook propagation gap)
- https://github.com/anthropics/claude-code/issues/9567 (CLAUDE_TOOL_INPUT empty bug)
- https://github.com/openai/codex/issues/18711 (substring-match anti-pattern + Seatbelt regex recommendation)
- https://github.com/disler/claude-code-hooks-multi-agent-observability
- https://developer.apple.com/forums/thread/750031 (Seatbelt deny-line format)

## Requirements & Constraints

### From `requirements/project.md`

- **File-based state** (line 25): "Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter). No database or server." → events stream + denial logs are flat files.
- **Defense-in-depth for permissions** (lines 34–35): "The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution." → #163 is the enforcement layer; #164 is the observability layer for what it catches.
- **Complexity must earn its place** (line 19): "When in doubt, the simpler solution is correct." → applied in Tradeoffs to Alternative D.

### From `requirements/observability.md`

- **No-writes constraint** (line 93): "All three subsystems are read-only with respect to session state files." Applies specifically to **statusline / dashboard / notifications** — not to hooks. Hooks are a separate distribution surface. This is a definitional clarification, not a conflict.
- **Latency** (line 91): explicit SLA of <500ms applies to statusline; **no explicit SLA for hooks**. Hooks fire synchronously in the agent's tool-call critical path — implicit budget required.

### From `requirements/multi-agent.md`

- `CORTEX_RUNNER_CHILD=1` is exported at both overnight spawn sites (orchestrator + per-feature dispatch). Used to identify overnight-spawned children. **However**, env-var propagation through plugin-hook spawn is not currently verified (see Web Research). This is an empirical question, not a requirements one.

### From `requirements/pipeline.md`

- Session state paths (`lifecycle/sessions/{session_id}/...`) are registered in `sandbox.filesystem.allowWrite` by `cortex init`. The hook can write to this path tree from the host shell (hooks run at trust level, outside the agent's sandbox).
- `pipeline-events.log` is JSONL append-only. `cortex_command/overnight/events.py:log_event()` is the canonical writer for typed events.

### From `CLAUDE.md`

- **MUST-escalation policy**: post-Opus-4.7 default to soft positive-routing phrasing for new authoring; existing MUST language is grandfathered. This spec should AVOID introducing MUST/CRITICAL/REQUIRED unless it carries the evidence-link required by the policy.
- **Overnight docs source of truth**: `docs/overnight-operations.md` owns the round loop and orchestrator behavior; ticket #164's doc subsection lives there.

## Tradeoffs & Alternatives

### Alternative A — Ticket's suggested approach (separate sibling hook)

`claude/hooks/cortex-sandbox-violation-tracker.sh`, ~50 LOC, stderr-regex classifier, gated on `CORTEX_RUNNER_CHILD=1`, emits typed `sandbox_denial` event into the overnight session's events stream.

| Dimension | Assessment |
|-----------|-----------|
| Implementation complexity | Low — mirrors existing tracker pattern. ~50 LOC + hooks.json edit + justfile manifest edit + report.py extension. |
| Maintainability | Medium — stderr regex breaks silently when sandbox-runtime changes the EPERM message. Debug surface is small (one file, one regex, one event type). |
| Performance | Acceptable per-call (~20–60ms macOS fork+exec); ~10–30s cumulative across a 500-Bash-call session. Stacks with other PostToolUse hooks. |
| Alignment | High with the existing tracker. **Diverges** on env-var gate (existing tracker is ungated) and on threshold (every attempt vs N=3). |

### Alternative B — Extend existing failure tracker

Add a sandbox-classification branch inside `cortex-tool-failure-tracker.sh`.

| Dimension | Assessment |
|-----------|-----------|
| Implementation complexity | Lowest — ~15 LOC delta, no new files. |
| Maintainability | Low — mixes generic failure tracking + sandbox classification in one file. Conditional gating only the new branch on `CORTEX_RUNNER_CHILD=1` is awkward (existing tracker is ungated). Modifies a load-bearing path for one new sub-category. |
| Performance | Same as A (single fork). |
| Alignment | Diverges from sibling-hook precedent (`cortex-skill-edit-advisor.sh`). |

### Alternative C — High-precision classification via deny-list lookup

Hook reads the spawn's `--settings` JSON or a sidecar file (written by ticket #163's spawn site), parses `tool_input.command` for write targets, matches against the deny-list.

| Dimension | Assessment |
|-----------|-----------|
| Implementation complexity | Medium-high — ~120–200 LOC. Requires: (a) #163 to expose deny-list path via env var or known location; (b) hook to parse arbitrary Bash command syntax (redirections, `cd && ...`, here-docs, env-var expansion) — partial parser at best. |
| Maintainability | Low — couples observability hook to #163's spawn shape. Bash-command-target parsing is its own correctness surface. Higher 6-month debug cost. |
| Performance | Worst — JSON parse + command parse per call. Likely sub-50ms but order-of-magnitude worse than A. |
| Alignment | Sharply diverges — no existing cortex hook reads `--settings` or sidecar files. |

### Alternative D — Defer classification to morning-report aggregator

Hook stays generic (existing `cortex-tool-failure-tracker.sh` already captures stderr); aggregator does post-hoc stderr-classification at report-render time in `cortex_command/overnight/report.py`.

| Dimension | Assessment |
|-----------|-----------|
| Implementation complexity | Lowest-shipped — ~30 LOC of Python in `report.py`. Zero new shell files. Reuses existing `/tmp` log infrastructure (subject to the latent session-id bug — Alternative D must also fix that). |
| Maintainability | Highest — classification logic in Python (testable), not shell-regex (untestable in isolation). 6-month debugger reads one Python function. |
| Performance | Best — zero hot-path cost. Classification runs once at morning-report time. |
| Alignment | Highest — existing aggregator pattern (`render_tool_failures`) is exactly where typed-failure subcategorization belongs. |
| Cost | Loses the typed-event signal in `events.log`. **Verified above**: events.log has zero non-morning-report consumers — so the typed-event surface has no downstream beneficiary today. |

### Alternative E — Telemetry via sandbox-runtime side channel

UNVERIFIED — likely not feasible today. `@anthropic-ai/sandbox-runtime` exposes audit-logging for **network requests** but no documented filesystem-denial structured channel. macOS unified log is the only structured signal and requires a long-lived `log stream` helper. Mark as deferred follow-up; revisit if sandbox-runtime ships a filesystem audit channel.

### Alternative F — Skip ticket; rely on generic failure-tracker

Defensible only if signal-to-noise of dedicated classification doesn't beat the generic surface. Discovery RQ6 explicitly notes "no morning-report visibility" today — under-delivers on the value the ticket exists to capture.

### Recommendation (research recommendation, not final decision)

**Alternative D is structurally the strongest given the evidence.** Rationale:

1. **No second consumer.** Verified that the typed `sandbox_denial` event in `events.log` has zero consumers beyond the morning-report count line (Codebase Analysis). The typed-event surface in A is overhead with no current downstream beneficiary.
2. **Avoids 4 of 5 critical risks.** D sidesteps the env-var propagation gap (#2 in Adversarial), the shell-regex maintainability question (#1), the threshold-cadence question (#5), and the hot-path latency tax (#6). Python at report-render time is more testable, isolated to cold path, and has no env-propagation question.
3. **Still requires the same fixes.** D must still resolve the latent session-id namespace bug in `report.py:201` (since it would inherit the existing tracker's storage), include a positive-control test, and disclose Bash-only scope in morning-report wording. These are spec requirements regardless of approach.
4. **A is the right ship if a typed events.log signal is genuinely load-bearing for a future consumer.** The ticket cites no second consumer; but if a dashboard/metrics surface is planned that needs typed `sandbox_denial` events, A becomes correct.

**Spec phase must answer the deciding question explicitly with the user**: is the typed `sandbox_denial` event in events.log load-bearing for a future consumer beyond the morning-report count line, or is the morning-report count line the load-bearing surface?

If load-bearing → Alternative A.
If not load-bearing → Alternative D.

This is a load-bearing scope question for the spec, not a hand-wave. Both options are documented above so spec can reject one explicitly with citation.

## Adversarial Review

### Critical concerns (block ship without resolution)

#### A1. Latent session-id namespace bug in the precedent

**Real concern.** The existing `cortex-tool-failure-tracker.sh:23,44` writes to `/tmp/claude-tool-failures-${INPUT.session_id}/` using the Claude SDK UUID; `report.py:200-205`'s `collect_tool_failures(data.session_id)` reads using `state.session_id` (`overnight-YYYY-MM-DD-HHMM`). **These namespaces never coincide** — the existing morning-report `tool_failures` aggregation is silently empty. Cloning this pattern reproduces the bug.

**Spec MUST**: resolve session-id namespace explicitly. Either (a) hook reads `lifecycle/overnight-state.json` to discover `overnight-<date>-<time>` and writes to a path keyed on that, OR (b) Alternative D (Python at report-render time keys directly off the SDK UUID dirs the hook writes today, since report.py already has access to the transcript and can correlate). Pick one; document the other as rejected. Optional: file a sibling ticket to fix the existing tracker bug separately.

#### A2. Stderr-only classification is structurally weak on macOS

**Real concern.** Per Web Research, the structured Seatbelt denial marker (`Sandbox: bash(PID) deny(1) ...`) goes to the **macOS unified log, NOT stderr**. Stderr only contains bare POSIX `Operation not permitted` — indistinguishable from chmod/ACL/SIP/EROFS denial. Bare-EPERM as sandbox-denial is the documented anti-pattern (openai/codex#18711). False-positive scenarios on a real overnight session: `gpg --sign` against a read-only `~/.gnupg/` ACL, link errors during `cargo build` in a no-write target, `chmod +x` on ACL-restricted file. The dominant bucket would be `other_eperm`, making the count line semantically misleading.

**Spec MUST**: specify how the hook resolves the deny-list. Options:
- (a) Hook reads spawn's `--settings` JSON (requires #163 to expose path via env var or known location).
- (b) Hook reads `lifecycle/sessions/<id>/sandbox-deny-list.json` written by the runner pre-spawn.
- (c) Hook does NOT classify; emits a generic `bash_eperm` event with raw stderr/command, and Python at report-render time classifies (Alternative D).

Bare-stderr regex is permitted only as last-resort with an `unclassified_eperm` bucket SEPARATE from `sandbox_denial`. Spec must reject the precision-vs-noise trade-off explicitly.

#### A3. Env-var propagation gap kills the gate (or gives false positives)

**Real concern.** anthropics/claude-code#9447 reports that custom env vars (specifically `CLAUDE_PROJECT_DIR`) do NOT propagate to plugin-hook spawn (only `CLAUDE_PLUGIN_ROOT` is populated). The proposed hook lives in `plugins/cortex-overnight-integration/hooks/hooks.json` — exactly the surface the bug names. The existing `cortex-tool-failure-tracker.sh` is ungated for this likely reason.

If the gate fails:
- "Closed" (no signal → no fire): hook never produces signal regardless of overnight context — telemetry broken.
- "Open" (env passes): hook fires for interactive sessions too, polluting the count.

**Spec MUST**: include a pre-implementation env-var verification test. A 5-line probe hook deployed via the plugin's `hooks.json` writing `${CORTEX_RUNNER_CHILD:-UNSET}` to a tmpfile during one orchestrator-spawn smoke test. If `UNSET`, the gate must be redesigned (e.g., presence of `lifecycle/sessions/<active>/runner.lock` as filesystem marker) before any code lands.

#### A4. No positive control for #163's enforcement

**Real concern.** "Morning report shows 0 sandbox denials" is uninterpretable — could mean enforcement worked + no agent attempted denied write (good), enforcement silently no-op'd (bad), hook never fired (bad), or hook fired but regex never matched (bad). The DR-7 acceptance test verifies #163's kernel-level EPERM, not the #164 telemetry surface.

**Spec MUST**: include a deliberately-induced sandbox denial smoke test. Concrete shape: a test that spawns a child with a deny-list including `<tmp>/.git/refs/heads/main`, runs a Bash command that attempts `echo x > <tmp>/.git/refs/heads/main`, asserts exactly one `sandbox_denial` event is recorded with classification `home_repo_refs`. Without this, the hook's silence is uninterpretable.

#### A5. Threshold-3 aggregation is wrong for sandbox denials

**Real concern.** The existing tracker fires `additionalContext` only at exactly N=3 (`cortex-tool-failure-tracker.sh:78`: `if (( CURRENT == 3 ))`). Threshold-3 makes sense for transient/flake failures where one occurrence might be noise. Sandbox denials are not flake — they are policy-shaped intent, and a single attempt is the signal of where the agent tried to go. Threshold-3 would suppress single-shot signal entirely.

**Spec MUST**: require N=1 logging cadence. Every sandbox_denial event is logged at occurrence; aggregation happens at report-render time, not in the hot-path hook. additionalContext nudge to the agent (if any) fires at N=1 because the value is the agent's behavior change, not threshold awareness.

### Real but bounded concerns

#### A6. Plugin-hook fork overhead

**Partially valid.** Per-call cost ~20–60ms on macOS for a hook that does bash startup + jq invocations + file IO. 500-Bash-call session = 10–30s cumulative — not catastrophic but not free. PostToolUse hooks fire synchronously and serially, so each adds latency to the agent's tool-loop.

**Spec SHOULD**: quantify per-call latency budget (suggest <50ms median, <200ms p99). If Alternative D is chosen, this concern collapses entirely.

#### A7. `/tmp` is the wrong storage home

**Real concern.** macOS `/tmp` → `/private/tmp` is system-cleaned (`/etc/periodic/daily/*`); multi-day overnight sessions cross cleanup cycles. For the existing tracker the impact is bounded ("missed signal"); for sandbox denials the entire purpose IS the signal.

**Spec MUST**: persist under `lifecycle/sessions/<overnight-id>/` (covered by `~/.claude/settings.local.json` `allowWrite`). Hook MUST exit 0 unconditionally on write failure (non-blocking observability invariant).

#### A8. additionalContext 10K char cap

**Bounded.** Over-cap content is auto-spilled to a file with path+preview returned. But morning-report path doesn't read those overflow files, and the agent sees a fragmented "see file X" reference per overflow.

**Spec SHOULD**: cap additionalContext per-event budget at ~150 chars × max 50 entries = 7.5K, well under cap. Format: `denied: <path-suffix> (N of M this session)`.

#### A9. Write/Edit/MCP escapes invisible to PostToolUse(Bash) — false reassurance risk

**Real, surfaced in parent research but unaddressed in this ticket's wording.** Per #163's threat-model boundary, Write/Edit/MCP escape paths bypass the sandbox. The hook only sees Bash. "0 sandbox denials" in the morning report is FALSE REASSURANCE when an agent escaped via Write tool.

**Spec MUST**: require morning-report wording to disclose Bash-only scope. Concrete: "Bash sandbox denials: N (Write/Edit/MCP escapes not surfaced — see #163 V1 scope)" or equivalent caveat tied to research.md OQ7.

### Concerns not validated by adversarial review

#### A10. Build-mirror enforcement

**Partially valid.** Agent 1's claim that the canonical-source-with-plugin-mirror pattern applies is correct, but the enforcement mechanism is `just build-plugin` rsync + `.githooks/pre-commit` Phase 4 — NOT `bin/cortex-check-parity`. **Spec MUST**: include `justfile` HOOKS manifest update for `cortex-overnight-integration` (line ~487). Without it, `just build-plugin` won't sync the canonical hook into the plugin tree and pre-commit will block.

### Failure modes the spec MUST address (concise list)

1. Session-id namespace mismatch (A1).
2. Classification deny-list source (A2).
3. Env-var gate verification before ship (A3).
4. Positive-control smoke test (A4).
5. N=1 logging cadence (A5).
6. Storage under `lifecycle/sessions/`, not `/tmp/` (A7).
7. additionalContext budget (A8).
8. Bash-only scope disclosure in morning-report wording (A9).
9. `justfile` HOOKS manifest update (A10).

### Anti-patterns to avoid

- **Stderr substring matching as classification primitive** (codex#18711). Spec must require deny-list-aware classification, not bare-stderr regex.
- **Cloning a buggy precedent**. The existing tool-failure-tracker has the session-id-namespace bug; spec must require a fresh design for the path key, not a copy.
- **Plugin-hook env-var trust** without verification.
- **Threshold-aggregation for policy-shaped signal** (every attempt is the signal, not "3 attempts").

## Open Questions

The Spec phase will resolve all of these via the structured interview (specify.md §2/§3). Listed here for traceability.

- **OQ1** — Is the typed `sandbox_denial` event in `events.log` load-bearing for a future consumer beyond the morning-report count line, or is the morning-report count line the load-bearing surface? *Deferred: will be resolved in Spec by asking the user. The answer determines Alternative A vs Alternative D and is the load-bearing scope decision.*

- **OQ2** — How does the hook resolve the deny-list for classification? *Deferred: will be resolved in Spec by asking the user. Options enumerated in Adversarial #A2.*

- **OQ3** — Pre-implementation env-var probe — does `CORTEX_RUNNER_CHILD=1` propagate to plugin-hook spawn in this installed Claude Code version? *Deferred: spec will require a 5-line behavioral probe test as a pre-implementation gate per Adversarial #A3. Result is empirical, not a user decision.*

- **OQ4** — Session-id namespace: hook keys writes off SDK UUID; aggregator keys reads off `state.session_id`. *Resolved (research direction): spec must resolve via either (a) hook reads `lifecycle/overnight-state.json` to discover `overnight-<id>` for path keying, OR (b) aggregator correlates SDK UUID to `overnight-<id>` via existing transcript/state cross-reference. User picks; if Alternative D is chosen, (b) is natural.*

- **OQ5** — additionalContext emission policy: emit per-denial nudge to the agent (visibility in transcript), only on first denial, or never (events.log only)? *Deferred: will be resolved in Spec by asking the user. Tradeoff is agent-behavior-change-pressure vs. budget consumption.*

- **OQ6** — Should this ticket also fix the latent session-id bug in the existing `cortex-tool-failure-tracker.sh`, or file a sibling ticket? *Deferred: will be resolved in Spec by asking the user. Bundling fixes a real bug discovered during research; splitting keeps scope narrow.*

- **OQ7** — Does this ticket land before or after #163 ships? `blocked-by: [163]` indicates execution ordering. Does refining now (#164's spec) presume a #163 design that may change? *Resolved: refining now is sound. The hook design is independent of #163's exact deny-list contents — it consumes the deny-list at runtime and works against whatever #163 ships. The only spec contingency is OQ2's deny-list source path, which is parameterized.*
