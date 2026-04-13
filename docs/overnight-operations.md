[← Back to overnight.md](overnight.md)

# Overnight: Operations and Architecture

**For:** operators and contributors debugging overnight. **Assumes:** familiarity with how to run overnight.

> **Jump to:** [Architecture](#architecture) | [Code Layout](#code-layout) | [Tuning](#tuning) | [Observability](#observability) | [Security and Trust Boundaries](#security-and-trust-boundaries) | [Internal APIs](#internal-apis)

This doc applies the **progressive disclosure** model from `claude/reference/claude-skills.md` to human-facing docs rather than to agent skill loading. `docs/overnight.md` stays compact for a reader whose access pattern is "how do I run overnight tonight?" — landing via the README, a peer recommendation, or a getting-started cross-link — and they get Quick-Start plus a one-paragraph pointer here. `docs/overnight-operations.md` is the single source of truth for mechanics, debugging, and recovery for a reader whose access pattern is "something broke at 2am" — landing via a stack trace, a retro back-reference, or a deep cross-link from `pipeline.md` — and they find the complete picture in one file rather than bouncing between two. The split optimizes which doc each reader hits first: new operators hit `overnight.md`; debuggers hit this file. See `CLAUDE.md` under `## Conventions` for the source-of-truth rule that partitions overnight mechanics, pipeline internals, and SDK mechanics across docs.

---

## Architecture

### The Round Loop and orchestrator_io

### Post-Merge Review (review_dispatch)

After a feature merges to the integration branch, `batch_runner.execute_feature()` consults `requires_review(tier, criticality)` in `claude/common.py` — review fires when `tier == "complex"` or `criticality in ("high", "critical")`. Gated features invoke `dispatch_review()` in `claude/pipeline/review_dispatch.py`, which loads `claude/pipeline/prompts/review.md` via `_load_review_prompt()` and runs a review agent against the merged state on the integration branch.

**Files**: `claude/pipeline/review_dispatch.py` (`dispatch_review`, `parse_verdict`, `_write_review_deferral`), `claude/pipeline/prompts/review.md`, `claude/common.py` (`requires_review`), `claude/pipeline/batch_runner.py` (`execute_feature` owns the review/rework loop).

**Inputs**: integration branch HEAD at merge time; feature metadata; prior orchestrator notes at `lifecycle/{feature}/learnings/orchestrator-note.md`.

The verdict is parsed from a ```json``` block inside the review agent's `review.md` artifact — `APPROVED`, `CHANGES_REQUESTED`, or `REJECTED`. The review agent writes only `review.md`; `batch_runner` owns every `events.log` write (`phase_transition`, `review_verdict`, `feature_complete`) so review artifacts and state transitions never interleave.

The rework cycle is single-shot:

- **Cycle 1 `CHANGES_REQUESTED`**: feedback is appended to `lifecycle/{feature}/learnings/orchestrator-note.md`, HEAD SHA is captured as a circuit-breaker baseline, a fix agent is dispatched, the SHA circuit breaker verifies new work landed, and the feature is re-merged with `ci_check=False` (the test gate already passed pre-review). A cycle-2 review then runs.
- **Cycle 2 non-`APPROVED` or any `REJECTED`**: `_write_review_deferral()` emits a blocking `DeferralQuestion` and the feature stops. There is no cycle 3.

Forward-only phase transitions hold throughout: `planning → executing → complete`, or any phase → `paused`. State writes use tempfile + `os.replace()` so a crash mid-review leaves either the pre-merge or post-merge state on disk, never a torn record.

### Per-Task Agent Capabilities (allowed_tools)

Every task-level agent dispatched by `claude/pipeline/dispatch.py` is bound to a fixed tool allowlist at the SDK level. The list is passed as `allowed_tools=_ALLOWED_TOOLS` into `ClaudeAgentOptions` — enforcement is by omission: `Agent`, `Task`, `AskUserQuestion`, `WebFetch`, and `WebSearch` are simply absent, so the subprocess has no capability to invoke them. There is no separate deny list.

```python
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
```

Source of truth: `claude/pipeline/dispatch.py` (`_ALLOWED_TOOLS`). A pytest under `tests/` asserts the documented list above equals `claude.pipeline.dispatch._ALLOWED_TOOLS` as a set, so any drift between code and docs fails CI.

Two corollaries of enforce-by-omission:

- **No peer-agent spawning.** `Agent` and `Task` are withheld so dispatched workers cannot fan out to child agents; the orchestrator owns parallelism and agents never spawn peer agents. `claude/overnight/prompts/repair-agent.md` reinforces this in prose, but the SDK-level bound is the load-bearing constraint.
- **No network I/O from tasks.** `WebFetch` and `WebSearch` are withheld. Anything a task needs from the network must be fetched by the orchestrator and written into the worktree before dispatch.

`dispatch.py` also clears `CLAUDECODE` from the subprocess environment before launching the agent, so the SDK does not trip the nested-session guard when overnight is itself launched from a Claude Code session.

See [Security and Trust Boundaries](#security-and-trust-boundaries) for how `_ALLOWED_TOOLS` relates to `--dangerously-skip-permissions` (they are orthogonal).

### brain.py — post-retry triage (SKIP/DEFER/PAUSE)

### Conflict Recovery (trivial fast-path and repair fallback)

### Cycle-breaking for repeated escalations

Workers raise escalations to the Escalation System by appending entries to `lifecycle/escalations.jsonl` — an append-only JSONL log whose writer is `write_escalation()` in `claude/overnight/deferral.py` (re-exported via `claude/overnight/orchestrator_io.py`). Each record carries an `escalation_id` of form `{feature}-{round}-q{N}` and a `type` field — one of `"escalation"` (worker asked), `"resolution"` (orchestrator answered), or `"promoted"` (cycle broken, see below). N is chosen by `_next_escalation_n()`, which counts existing `"escalation"` entries for the same feature+round; a TOCTOU race is acknowledged in code comments and is safe under the per-feature single-coroutine dispatch invariant.

**Files**: `claude/overnight/deferral.py` (`EscalationEntry`, `write_escalation`, `_next_escalation_n`), `claude/overnight/orchestrator_io.py` (re-export), `claude/overnight/prompts/orchestrator-round.md` (Step 0a–0d — the cycle-breaking logic lives in the prompt, not Python).

**Inputs**: `lifecycle/escalations.jsonl`; prior orchestrator feedback at `lifecycle/{feature}/learnings/orchestrator-note.md`.

Cycle-breaking fires when a worker re-asks a question the orchestrator already answered. The orchestrator prompt's Step 0d scans `escalations.jsonl` at round start: if ≥1 `"type": "resolution"` entry exists for the same `feature` and a new worker escalation raises a sufficiently similar question, the orchestrator treats the feature as stuck rather than answering again. The concrete action is:

- Delete `lifecycle/{feature}/learnings/orchestrator-note.md` (the feedback channel clearly did not land — do not accumulate stale guidance).
- Append a `"type": "promoted"` entry to `escalations.jsonl` recording the promotion.
- Call `write_deferral()` to file a blocking deferral for human review at morning.
- Do **not** re-queue the feature for this session.

This keeps a stuck worker from consuming budget round after round on the same question. Because the detector is prompt-implemented, do not quote line numbers from `orchestrator-round.md` — the prompt is edited for clarity routinely; refer to it by filename and step heading only.

### Test Gate and integration_health

### Startup Recovery (interrupt.py)

### Runner Lock (.runner.lock)

### Scheduled Launch subsystem

---

## Code Layout

### claude/pipeline/prompts — per-task dispatched prompts

`claude/pipeline/prompts/` holds prompts that are dispatched into per-feature worktrees by `claude/pipeline/dispatch.py` and `claude/pipeline/review_dispatch.py`. These agents operate on a single feature's code at a time and run under `_ALLOWED_TOOLS`.

**Files**: `claude/pipeline/prompts/implement.md` (implementation agent), `claude/pipeline/prompts/review.md` (post-merge review agent loaded by `_load_review_prompt()`).

**Inputs**: feature metadata and worktree path supplied by the caller; no session-level state.

The naming convention is "per-task, per-feature" — one prompt file per role an orchestrated agent can play inside a worktree.

### claude/overnight/prompts — orchestrator/session-level prompts

`claude/overnight/prompts/` holds prompts loaded by `runner.sh` and overnight subsystems that operate at the session or orchestrator level — not inside a per-feature worktree. These agents reason about the whole session, read session-scoped state files (`overnight-strategy.json`, `escalations.jsonl`), and coordinate work across features.

**Files**: `claude/overnight/prompts/orchestrator-round.md` (the round-loop orchestrator prompt, including the escalations Step 0a–0d cycle-breaking logic), `claude/overnight/prompts/batch-brain.md` (the `brain.py` post-retry triage prompt rendered with `{feature, task_description, retry_count, learnings, spec_excerpt, has_dependents, last_attempt_output}`), `claude/overnight/prompts/repair-agent.md` (conflict-repair and integration-repair agent prose).

**Inputs**: session state loaded by the orchestrator; escalation history; strategy file; feature-level learnings directories.

The two directories are kept separate because their audiences differ: `pipeline/prompts` agents never see session state, and `overnight/prompts` agents never edit a single feature's code directly — they route work through `pipeline/dispatch.py`. Keeping them in sibling trees makes the scope boundary visible from an import path alone.

---

## Tuning

### --tier concurrency (Concurrency Tuning)

The `--tier` CLI flag on `batch_runner.py` selects a throttle profile. Accepted values: `max_5`, `max_100`, `max_200`. Default (flag omitted or unrecognized) is `max_100`.

| Tier | Runners | Workers |
|------|---------|---------|
| `max_5` | 1 | 1 |
| `max_100` | 2 | 2 |
| `max_200` | 3 | 3 |

Defaults live in `claude/overnight/throttle.py` (`load_throttle_config`); the tier value is wired through `BatchConfig.throttle_tier` and consumed by `ConcurrencyManager`. The limit is a hard ceiling — agents cannot raise it at runtime (orchestrator owns parallelism; agents never spawn peer agents).

Adaptive downshift: `report_rate_limit()` prunes a 300-second sliding window; after 3 rate-limit events the effective concurrency drops by 1 (floor of 1). `report_success()` restores the shift after 10 consecutive successes. The escalation ladder itself (haiku → sonnet → opus) does not downgrade.

Tune by matching your API plan's parallelism ceiling to the tier. Picking `max_200` on a plan only capable of `max_5` throughput starves into the adaptive downshift before the first round finishes.

### Test Gate and integration_health tuning

The [Test Gate and integration_health](#test-gate-and-integration_health) subsection under Architecture documents the flow; this subsection calls out the *tunable surfaces*:

- **`--test-command`** (passed to `runner.sh` / `batch_runner.py`). This is the command run after every merge onto the integration branch — a non-zero exit invokes `python3 -m claude.overnight.integration_recovery`. Choosing a slow or flaky command multiplies every round's wall-clock cost; choosing a fast-but-shallow command narrows what the gate catches before repair dispatch.
- **`integration_health` in `overnight-strategy.json`**. `healthy` is the implicit baseline; `degraded` is set by `runner.sh` when `integration_recovery` fails (alongside `INTEGRATION_DEGRADED=true` and a warning file prepended to the PR body). Downstream rounds consult this field in conflict-recovery decisions.
- **Repair dispatch is unconditional** on gate failure — there is no suppression flag. If you need to skip repair, skip the gate (set `--test-command` to a no-op) rather than trying to gate the repair.

### Model selection matrix (tier × criticality → role)

This document owns tier × criticality → role *dispatch*; detailed per-role SDK model configuration lives in [sdk.md](sdk.md) — that file is the source of truth for model IDs, fallback chains, and `ClaudeAgentOptions` plumbing.

| Tier | Criticality | Review required? | Repair role |
|------|-------------|------------------|-------------|
| `simple` | `low`, `medium` | No | Sonnet (first attempt) |
| `simple` | `high`, `critical` | Yes | Sonnet → Opus on escalation |
| `complex` | any | Yes | Sonnet → Opus on escalation |

Review gating is implemented by `requires_review(tier, criticality)` in `claude/common.py`: review runs when `tier == "complex" or criticality in ("high", "critical")`. The escalation ladder is one-directional (haiku → sonnet → opus, no downgrade); see [sdk.md](sdk.md) for the concrete model IDs wired into each role.

### Repair caps

The runner has **two distinct repair caps** with different numbers. They are intentionally *not unified* — the codepaths, artifacts, and recovery semantics differ enough that a single number would hide the divergence.

- **Merge-conflict repair: single Sonnet→Opus escalation.** One attempt at Sonnet, then one escalation to Opus, then give up and defer. Rationale: merge-conflict repair operates on a git-index snapshot; a second Sonnet attempt on the same snapshot is unlikely to succeed where the first failed, so the cap spends its second slot climbing the model ladder rather than retrying at the same tier. Codepath: `claude/pipeline/conflict.py` and `claude/pipeline/merge_recovery.py`.
- **Test-failure repair: max 2 attempts.** Two full repair cycles for the integration test gate. Rationale: test failures often expose a different error on the second attempt (the first fix unblocks the next assertion), so a retry at the same tier has meaningful information gain that a merge-conflict retry does not. Codepath: `claude/overnight/integration_recovery.py`.

Do not describe these as "the repair cap" in prose — collapsing them to one number misleads readers at 2am when observed behavior does not match.

### lifecycle.config.md fields and absence behavior

### overnight-strategy.json contents and mutators

---

## Observability

### Log Disambiguation (events.log, pipeline-events.log, agent-activity.jsonl)

### Escalation System (escalations.jsonl)

### Morning Report Generation (report.py)

### Dashboard Polling and dashboard state

### Session Hooks (SessionStart, SessionEnd, notification hooks)

---

## Security and Trust Boundaries

Overnight runs autonomously against a live working tree on a developer workstation. The trust boundaries below are enumerated once here; safety notes are not scattered elsewhere in this doc.

- **`--dangerously-skip-permissions`.** Overnight launches `claude` subprocesses with this flag, which disables the permission-prompt layer entirely. Threat model: any tool the subprocess is allowed to invoke runs without confirmation against the local filesystem and shell — sandbox configuration (the filesystem/network allowlist applied to the subprocess) becomes the critical security surface for autonomous execution.
- **`_ALLOWED_TOOLS` — SDK-level tool bound.** Task agents dispatched by `claude/pipeline/dispatch.py` are bound to `_ALLOWED_TOOLS` at the SDK layer, orthogonal to `--dangerously-skip-permissions`. Threat model: a compromised or confused task agent cannot reach `WebFetch`, `WebSearch`, `Agent`, `Task`, or `AskUserQuestion` — they are not loaded, not merely denied — so it cannot spawn peer agents or exfiltrate via the web even under skipped permissions.
- **Dashboard binds `0.0.0.0`, unauthenticated, by design.** The dashboard is read-only and listens on all interfaces without auth. Threat model: anyone on the same layer-2 broadcast domain can read session state, feature names, and log excerpts; do not expose to the public internet and do not treat "local network" as equivalent to "home network" — hotel Wi-Fi, coworking Wi-Fi, and shared office VLANs are all "local" to the dashboard and are not trusted peers.
- **macOS keychain prompt as a session-blocking failure mode.** If authentication resolution (see [Internal APIs — Auth Resolution](#auth-resolution-apikeyhelper-and-env-var-fallback-order)) falls through to keychain-backed credentials, the first subprocess spawn may trigger a macOS keychain-access dialog. Threat model: the "runs while you sleep" premise breaks silently — the prompt blocks subprocess spawn until acknowledged, the round stalls, and no notification fires because the failure is pre-notification. Resolve by setting `ANTHROPIC_API_KEY` or configuring `apiKeyHelper` before the session starts.
- **"Local network" ≠ "home network".** This is a corollary of the dashboard boundary but is called out as its own item because the framing trap bites at 2am. Threat model: a reader who conflates the two will expose session state to whatever shared network they happen to be on; the dashboard's design assumes a trusted L2 peer set, which is only true on a network the operator controls end-to-end.

---

## Internal APIs

### orchestrator_io re-export surface

`claude/overnight/orchestrator_io.py` is the sanctioned import boundary for orchestrator-callable I/O primitives. The module itself holds no logic — it re-exports a small, deliberately curated set of functions from `claude.overnight.state` and `claude.overnight.deferral` so the orchestrator prompt's Step 0 file-I/O calls can be imported from one module rather than reaching into internals. See `__all__` in `claude/overnight/orchestrator_io.py` for the sanctioned surface; do not enumerate it here because the list is expected to grow and a doc-side enumeration would rot on the next addition.

**Files**: `claude/overnight/orchestrator_io.py` (source of truth — `__all__`), consumed by `claude/overnight/prompts/orchestrator-round.md`.

Convention: any new orchestrator-callable I/O primitive is added here rather than imported directly from `claude.overnight.state` or `claude.overnight.deferral` by the orchestrator. This keeps the orchestrator's blast radius for internal refactors bounded to one file.

### lifecycle.config.md consumers and absence behavior

`lifecycle.config.md` is a per-project config file (template at `skills/lifecycle/assets/lifecycle.config.md`). There is no centralized Python loader — each consumer reads it directly — so the contract is "template is source of truth for fields; each consumer decides its own absence behavior." Fields include `type`, `test-command`, `demo-command` / `demo-commands`, `default-tier`, `default-criticality`, `skip-specify`, `skip-review`, and `commit-artifacts`.

**Files**: `skills/lifecycle/assets/lifecycle.config.md` (template — source of truth for the field list), plus the consumers in `skills/lifecycle/`, `skills/critical-review/`, and `skills/morning-review/`.

Absence behavior per consumer (what happens when the project has no `lifecycle.config.md`):

- **morning-review**: skips Section 2a (the demo-commands walkthrough) and continues the rest of the review.
- **lifecycle complete**: skips the test step with a note that no `test-command` was configured.
- **critical-review**: omits the `## Project Context` section of the generated review.
- **lifecycle specify/plan**: reads optional defaults (`default-tier`, `default-criticality`, `skip-specify`, `skip-review`) and falls back to skill-level defaults when absent.

Because field drift across consumers is possible, the template is the one place to check before assuming a field exists; do not enumerate fields in more than one doc.

### Auth Resolution (apiKeyHelper and env-var fallback order)

`runner.sh` resolves Anthropic authentication in a strict 4-step fallback order before spawning any subprocess. Each step short-circuits on success.

1. **`ANTHROPIC_API_KEY` already in the environment** — use it as-is and stop. This is the common CI/dev path.
2. **`apiKeyHelper` configured in `~/.claude/settings.json` or `~/.claude/settings.local.json`** — execute the helper command and export its stdout as `ANTHROPIC_API_KEY`. This is the recommended path for machines that keep the key out of shell profiles.
3. **No helper AND no `CLAUDE_CODE_OAUTH_TOKEN`** — try `~/.claude/personal-oauth-token`; if non-empty, export its contents as `CLAUDE_CODE_OAUTH_TOKEN`. This covers OAuth-style authentication for `claude -p` / SDK usage.
4. **Fall through to keychain-backed auth** — print a warning and proceed; the first subprocess spawn may block on a macOS keychain-access prompt (see [Security and Trust Boundaries](#security-and-trust-boundaries)).

**Files**: `claude/overnight/runner.sh` (the fallback logic), `claude/pipeline/dispatch.py` (re-exports both `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` into SDK subprocesses).

Propagation: `dispatch.py` forwards both variables into SDK subprocesses. Note the asymmetry — `CLAUDE_CODE_OAUTH_TOKEN` works only for `claude -p` and the SDK; standalone tools (including most scripts invoked from within a task) still need `ANTHROPIC_API_KEY`. If a worker subprocess reports auth errors but the orchestrator is fine, inspect which variable is reaching it.
