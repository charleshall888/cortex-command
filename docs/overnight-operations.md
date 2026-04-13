[← Back to overnight.md](overnight.md)

# Overnight: Operations and Architecture

**For:** operators and contributors debugging overnight. **Assumes:** familiarity with how to run overnight.

> **Jump to:** [Architecture](#architecture) | [Code Layout](#code-layout) | [Tuning](#tuning) | [Observability](#observability) | [Security and Trust Boundaries](#security-and-trust-boundaries) | [Internal APIs](#internal-apis)

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

### --dangerously-skip-permissions and sandbox surface

### Tool bound at the SDK level (_ALLOWED_TOOLS)

### Dashboard binds 0.0.0.0, unauthenticated

### Keychain prompt as session-blocking failure mode

### Auth Resolution (apiKeyHelper and env-var fallback order)

---

## Internal APIs

### orchestrator_io re-export surface
