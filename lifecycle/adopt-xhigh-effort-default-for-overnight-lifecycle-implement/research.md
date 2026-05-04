# Research: Adopt xhigh effort default for overnight lifecycle implement

## Codebase Analysis

### Files affected (absolute paths and line ranges)

| File | Lines | Role in this change |
|------|-------|---------------------|
| `cortex_command/pipeline/dispatch.py` | 127–131, 135–148, 348–419 (signature/docstring), 439, 483, 487–504, 554–575 | Effort lookup, dispatch_task signature/docstring, dispatch_complete event logging |
| `cortex_command/pipeline/retry.py` | 166–181 (signature), 256–272 (dispatch_task call) | Retry-loop signature and forwarding |
| `cortex_command/overnight/feature_executor.py` | 587–600 | Implement-phase retry_task call site |
| `cortex_command/pipeline/metrics.py` | 296–454 | Aggregator that powers the rollback trigger (no edits, but its bucketing shape constrains the trigger's faithfulness) |
| `cortex_command/tests/_stubs.py` | 56–82 | SDK stubs — must mirror real SDK shape |
| `cortex_command/pipeline/tests/test_dispatch_instrumentation.py` | ~283–301 | Asserts exact key list for dispatch events |
| `docs/overnight-operations.md`, `docs/sdk.md` | rationale-doc updates | Per CLAUDE.md, sdk.md owns SDK model-selection mechanics |

### Current EFFORT_MAP (verbatim)

```python
# cortex_command/pipeline/dispatch.py:127–131
EFFORT_MAP: dict[str, str] = {
    "trivial": "low",
    "simple":  "medium",
    "complex": "high",
}
```

Consumed at exactly one site (`dispatch.py:439`):
```python
effort = effort_override if effort_override is not None else EFFORT_MAP[complexity]
```

### Current `_MODEL_MATRIX` (verbatim)

```python
# cortex_command/pipeline/dispatch.py:135–148
_MODEL_MATRIX: dict[tuple[str, str], str] = {
    ("trivial", "low"):      "haiku",
    ("trivial", "medium"):   "haiku",
    ("trivial", "high"):     "sonnet",
    ("trivial", "critical"): "sonnet",
    ("simple",  "low"):      "sonnet",
    ("simple",  "medium"):   "sonnet",
    ("simple",  "high"):     "sonnet",
    ("simple",  "critical"): "sonnet",
    ("complex", "low"):      "sonnet",
    ("complex", "medium"):   "sonnet",
    ("complex", "high"):     "opus",
    ("complex", "critical"): "opus",
}
```

Consumed by `resolve_model()` (`dispatch.py:176–200`).

### dispatch_task signature and docstring excerpt

`dispatch_task` already accepts `effort_override` (`dispatch.py:358`). Current docstring (`dispatch.py:390–393`):

```
effort_override: If provided, use this effort level directly instead of
    resolving from the complexity tier via EFFORT_MAP.  Accepts any
    value accepted by ClaudeAgentOptions ("low", "medium", "high",
    "max").
```

`"xhigh"` is missing from the documented list — the ticket calls this out as a docstring-update deliverable.

### retry_task signature

`retry.py:166–181` — `retry_task` does NOT currently accept `effort_override`:

```python
async def retry_task(
    feature, task, worktree_path, complexity, system_prompt, learnings_dir,
    log_path=None, max_retries=3, criticality=None, activity_log_path=None,
    integration_base_path=None, repo_path=None,
    *, skill: Skill,
) -> RetryResult:
```

Sole production caller: `feature_executor.py:587–600` (passes `skill="implement"`). All other call sites are in tests (`tests/test_retry.py`, `tests/test_escalation.py`, etc.).

### All effort references

```
cortex_command/pipeline/dispatch.py:125,126,127,358,390,391,439,483,501
cortex_command/pipeline/tests/test_dispatch_instrumentation.py:283,298
cortex_command/pipeline/tests/test_metrics.py:74,837,966,986
cortex_command/tests/_stubs.py:81
```

### dispatch_complete event logging

`dispatch.py:554–575` — currently captures `cost_usd`, `duration_ms`, `num_turns`. Does NOT capture any field analogous to `stop_reason`. The current code reads `message.subtype` for budget exhaustion (`dispatch.py:556–559`):

```python
elif isinstance(message, ResultMessage):
    cost_usd = message.total_cost_usd
    if message.is_error:
        _budget_exhausted = True
        _budget_subtype = message.subtype or ""
        output_parts.append(f"[budget_exhausted: subtype={message.subtype}]")
```

### Implement-phase identification at dispatch

`skill="implement"` is hardcoded at the only production retry_task call site (`feature_executor.py:599`). At dispatch time, the `skill` parameter (a closed `Skill` Literal) carries phase-equivalent information, but **`skill="implement"` is not coextensive with "the implement phase":** during a feature's implement phase, `brain` triage and `conflict-repair` ALSO fire with their own skill names (see Adversarial Review §3).

### Six production dispatch_task call sites (one per skill)

- `feature_executor.py:599` — `skill="implement"` (via retry_task)
- `review_dispatch.py:261` — `skill="review"`
- `review_dispatch.py:393, 508` — `skill="review-fix"`
- `conflict.py:337` — `skill="conflict-repair"` (fires during implement phase)
- `merge_recovery.py:341` — `skill="merge-test-repair"`
- `integration_recovery.py:223` — `skill="integration-recovery"`
- `brain.py:232` — `skill="brain"` (fires during implement phase)

### Conventions

- Event logging via `log_event(log_path, dict)` from `pipeline.state`
- Snake_case for event names and field names
- Conditional logging only if `log_path is not None`
- Atomic state writes use `tempfile + os.replace()`; event logs are append-only JSONL (no atomic-replace contract at line level)
- Docstrings use Google-style Args/Returns/Raises
- Test stubs in `_stubs.py` must mirror real SDK shape; otherwise tests pass against fictional fields

## Web Research

### Anthropic-recommended effort defaults for Opus 4.7 (verbatim)

From [Effort docs](https://platform.claude.com/docs/en/build-with-claude/effort):

> **Start with `xhigh` for coding and agentic use cases**, and use `high` as the minimum for most intelligence-sensitive workloads.

From the [Migration guide](https://platform.claude.com/docs/en/about-claude/models/migration-guide#migrating-to-claude-opus-4-7):

> Start with the new `xhigh` effort level for coding and agentic use cases, and use a minimum of `high` effort for most intelligence-sensitive use cases.

Per-level guidance for Opus 4.7 includes for `xhigh`:

> The recommended starting point for coding and agentic work, and for exploratory tasks such as repeated tool calling, detailed web search, and knowledge-base search. **Expect meaningfully higher token usage than `high`.**

Canonical valid effort values for Opus 4.7: `low, medium, high, xhigh, max`.

### Effort applies to Opus 4.7 only

Per Anthropic: **`xhigh` is only available on Opus 4.7.** Sonnet 4.6 and Haiku 4.5 either silently downgrade or do not support `xhigh`. This is critical for retry/escalation behavior (see Adversarial Review §2).

### xhigh cost/quality (community, NOT authoritative)

- Anthropic gives no official cost multiplier; only "**meaningfully higher token usage than `high`**" qualitatively.
- Community estimates: ~1.5× tokens, ~5–6% quality boost on agentic coding (cited from MindStudio, Apiyi, Verdent — flagged as community lore).

### Anthropic migration checklist (relevant)

> If using `xhigh` or `max` effort, raise `max_tokens` to at least 64k as a starting point.

Critical caveat for this codebase: there is no path to set `max_tokens` through the harness. `ClaudeAgentOptions` has no field; `subprocess_cli.py:315–316` does not emit `--max-tokens`. The mitigation Anthropic explicitly recommends is structurally unavailable.

### Canonical stop_reason values from Anthropic Messages API

From [Handling stop reasons](https://platform.claude.com/docs/en/api/handling-stop-reasons):

`end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal`, `model_context_window_exceeded`.

`max_tokens` is the precise lowercase-underscored string for output truncation. `model_context_window_exceeded` is a sibling truncation reason that mature implementations also detect.

### Where stop_reason appears in the SDK

Per [Agent SDK / Handle the result](https://code.claude.com/docs/en/agent-sdk/agent-loop#handle-the-result), `stop_reason` is documented as `str | None` on the result. **However** — see Adversarial Review §1 — the installed SDK pin (0.1.41) does NOT expose this field on `ResultMessage`. The web docs describe a future or upstream version.

### Claude Code CLI v2.1.x

- `--effort` flag exists with options `low, medium, high, xhigh, max`.
- **No `--max-tokens` flag** — confirmed against [CLI reference](https://code.claude.com/docs/en/cli-reference).
- In-session slash command `/effort` exists.

### Python SDK Literal typing

[claude-agent-sdk-python issue #834](https://github.com/anthropics/claude-agent-sdk-python/issues/834) — `ClaudeAgentOptions.effort` Python Literal is `"low"|"medium"|"high"|"max"|None`; `xhigh` is missing from the Literal. Runtime works because `@dataclass` does not enforce `Literal`. Type-check warning only — until/unless the SDK adds `__post_init__` validation.

## Requirements & Constraints

### From `requirements/pipeline.md`

- All session state writes are atomic (`tempfile + os.replace()`)
- Event logs are append-only JSONL
- Metrics aggregator (`pipeline/metrics.py`) is computed by parsing `feature_complete` events; per-feature and tier aggregates exposed
- Repair caps fixed: merge-conflict 1× escalation, test-failure 2× attempts; intentionally not unified

### From `requirements/multi-agent.md`

- Model selection matrix is 2D `(complexity, criticality)` with escalation ladder `haiku → sonnet → opus` (forward-only)
- Concurrency limit is adaptive 1–3 (reduces by 1 after 3 rate-limit errors / 5 min, restores after 10 successes)
- Pre-deploy gating ("no-active-runner check") applies to changes that couple `runner.sh` and the orchestrator prompt — Option 3 does not couple these, so this constraint does not apply.

### From `requirements/project.md`

- "Complexity must earn its place" — narrow surface change preferred
- Quality bar: tests pass, feature works as specced
- File-based state preferred (no DB)

### From `docs/sdk.md` (source-of-truth for SDK model-selection mechanics)

- Budget caps and turn limits scale on complexity only (trivial=$5/15, simple=$25/20, complex=$50/30); criticality affects model selection
- `_MODEL_MATRIX` is the canonical 2D pattern in the codebase

### From `docs/overnight-operations.md`

- Phases are session-level: `planning → executing → complete` (with `paused` transitions)
- The ticket's "implement phase" wording is **lifecycle-feature** phase, not session phase. Lifecycle-feature phases include `plan, implement, review`, etc.

### Scope-bound directive (ticket #090)

- "Applies only to lifecycle implement phase, not every dispatch — per DR-3's scoping."
- Rollback trigger: ">2× complex-tier mean cost per dispatch" over 2-3 rounds vs pre-flip baseline (community ~1.5× ceiling).

### Open architectural ambiguity

Effort behavior under model escalation (haiku → sonnet → opus) is undefined in any documented place. The retry loop currently does not carry `effort_override`; the proposed design must specify how effort interacts with model escalation.

## Tradeoffs & Alternatives

### Option 2 — Criticality-aware 2D effort matrix

**Files affected:**
- `dispatch.py:127–131` (replace `EFFORT_MAP` with `_EFFORT_MATRIX`)
- `dispatch.py:439` (lookup change)
- New `resolve_effort()` analogue to `resolve_model()`
- Tests in `tests/test_dispatch.py`

**Pros:**
- Mirrors `_MODEL_MATRIX` precedent; centralized table reads at a glance
- Decoupled from phase information; no signature changes to `retry_task`
- Telemetry already records `effort` per dispatch_start

**Cons:**
- **Footprint mismatch with ticket scope:** silently elevates `review`, `review-fix`, `conflict-repair`, `integration-recovery`, `merge-test-repair` at complex+high/critical — the ticket explicitly says "Applies only to lifecycle implement phase, not every dispatch."
- Harder to attribute the rollback trigger when multiple skills shift simultaneously.

### Option 3 — Per-phase `effort_override` threaded through the runner

**Files affected:**
- `retry.py:166–181` (add `effort_override: Optional[str] = None` parameter)
- `retry.py:256–272` (forward to `dispatch_task`)
- `feature_executor.py:587–600` (add `effort_override="xhigh"`)
- `dispatch.py:391–393` (docstring update — required by ticket regardless of option)
- Tests in `tests/test_retry.py`, `tests/test_daytime_pipeline.py`, `tests/test_lead_unit.py`

**Pros:**
- Behavioral footprint exactly matches ticket scope (skill="implement" only)
- `dispatch_task` already accepts `effort_override`; half the wiring is done
- `model_override` is the structural twin pattern — same param shape and forwarding pattern
- Rollback is a single-line revert (delete `effort_override="xhigh"` at one call site)
- ~5–10 LOC + tests

**Cons:**
- Effort policy split across two locations (default `EFFORT_MAP`; per-call override at implement site)
- `skill="implement"` is not a complete proxy for "implement phase" — brain triage and conflict-repair fire during implement phase with different skills (see Adversarial Review §3)

### Option 4 — Constant lookup at the implement call site (variant of Option 3)

Define a named constant `_IMPLEMENT_EFFORT = "xhigh"` at the implement call site for self-documentation. Structurally identical to Option 3.

### Hybrid — 3D `(skill, complexity, criticality)` matrix

Centralized policy table that scopes to specific skills. Over-engineered for one phase distinction; reserve as a refactor target if a second per-skill effort exception ever lands.

### Recommendation

**Option 3 with the gate widened to `model == "opus"` AND the implement-phase skill set explicitly enumerated** (`skill in {"implement", "brain", "conflict-repair"}` if the user wants implement-phase coverage; or `skill == "implement"` only if they want the narrowest reading). The Adversarial Review surfaced two refinements over Agent 4's recommendation:

1. **Gate on `model == "opus"`** to avoid silently logging `effort=xhigh` for Sonnet/Haiku where xhigh is downgraded
2. **Explicitly choose** between "skill='implement' only" and "all in-implement-phase skills"

## Adversarial Review

### 1. The `stop_reason` field does not exist in the installed SDK — the ticket's mitigation is unimplementable as written

Verified directly in `.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py:670–683` (SDK pin 0.1.41 from `uv.lock`):

```python
@dataclass
class ResultMessage:
    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    result: str | None = None
    structured_output: Any = None
```

There is **no** `stop_reason` attribute. `_internal/message_parser.py:147–164` does not extract it either; even if the CLI emits `stop_reason` in its JSON, the parser would silently drop it.

The web doc claim ("`stop_reason` is on `ResultMessage`") describes the upstream Anthropic API or a future SDK version, not the installed pin. The ticket's research artifact (`research/opus-4-7-harness-adaptation/research.md` and `lifecycle/archive/measure-xhigh-vs-high-effort-cost-delta-on-representative-task/research.md:68`) appears to project the API field shape onto the SDK without verification.

**Implication:** The ticket's stated deliverable "Add detection for `stop_reason == 'max_tokens'` in the dispatch event logging" is **not a one-line patch**. Implementation requires one of:

- Upgrade the SDK pin to a version that exposes `stop_reason` (and verify the parser extracts it)
- Use `include_partial_messages=True` and parse raw `StreamEvent` payloads where API-level `stop_reason` lives in the wire format
- Watch `ResultMessage.subtype` (the existing field) for whatever string the CLI uses on max_tokens truncation — requires empirical reproduction
- Infer truncation from `usage["output_tokens"]` against a known cap

### 2. Effort silent downgrade under model escalation

`xhigh` is only supported on Opus 4.7. If `effort_override="xhigh"` is passed for a simple-tier task (e.g., `simple+implement` → Sonnet) or after a Sonnet retry on a complex+medium task, the effort is silently downgraded to `high` at runtime — but the dispatch_start event log records `effort=xhigh`. This invalidates downstream cost/quality analysis: `metrics.py` cannot distinguish "ran xhigh" from "logged xhigh, ran high."

**Mitigation:** Gate the override on `model == "opus"`, OR explicitly drop `effort_override` to `"high"` when escalating below Opus, OR document the effect.

### 3. `skill="implement"` is not a faithful proxy for "implement-phase dispatches"

During a feature's implement phase, the following skills can fire:

- `skill="implement"` (feature_executor.py:599) ✅ caught by Option 3
- `skill="brain"` (brain.py:232 from feature_executor.py:671 `_handle_failed_task`) ❌ misses xhigh
- `skill="conflict-repair"` (conflict.py:337 from feature_executor.py:474 conflict-recovery branch) ❌ misses xhigh
- `skill="merge-test-repair"` (merge_recovery.py:341) — fires during merge phase, correctly excluded
- `skill="review"`, `skill="review-fix"` — `phase_transition: implement → review` fires before dispatch, correctly excluded

The ticket's "implement phase" wording is ambiguous: time-window or skill name? `skill="implement"` is a tighter scope than the time-window reading.

### 4. Rollback trigger is structurally weak under Option 3

`metrics.py:312–454` (`pair_dispatch_events()`) buckets paired records by `(model, tier)`, not `(model, tier, skill)`. The aggregate dilutes the signal.

If `skill="implement"` is 50% of complex dispatches:
- Per-implement 1.5× regression → ~1.25× aggregate (does not trigger 2×)
- Per-implement 3× regression → ~2.0× aggregate (boundary)
- Per-implement 4× regression → ~2.5× aggregate (barely triggers)

Ticket #089 already flagged this collision: *"two runs at the same (model, tier) with different effort levels collide into the same bucket."*

**Mitigation:** Tighten the trigger threshold or extend `pair_dispatch_events` to bucket by `(model, tier, effort)` — out of scope for this ticket but should be documented.

### 5. The "works at runtime" claim is untested in the suite

The stub in `_stubs.py:81` accepts any string. No test exercises `ClaudeAgentOptions(effort="xhigh")` against the real SDK. If a future SDK adds `__post_init__` validation against the Literal, production will crash silently with no test to catch it.

**Mitigation:** Add a regression test that constructs the real `ClaudeAgentOptions(effort="xhigh")` and asserts no exception. Pin the SDK version explicitly in `pyproject.toml`.

### 6. `max_tokens >= 64k` mitigation gap

Anthropic explicitly recommends raising `max_tokens` to ≥64k when running xhigh. The harness has no path to set `max_tokens` (`ClaudeAgentOptions` has no field; CLI has no flag). The mitigation Anthropic recommends is structurally unavailable.

Combined with §1, **xhigh adoption ships without a feasible failure-detection path AND without a recovery path** as the ticket originally envisioned. The ticket does not acknowledge this stack.

### 7. Activity-log fanout under xhigh

xhigh causes more tool calls per dispatch (per Anthropic). `dispatch.py:533–541` writes per-tool-call activity events via `asyncio.to_thread`. At 5-way concurrency × xhigh tool fanout, this could measurably hit dispatch throughput. Failures are silent. Flag for awareness.

### 8. Untouched dispatch_complete consumers

Adding fields to `dispatch_complete` does NOT break `pair_dispatch_events()` (uses `evt.get(...)`), the dashboard, or seed data. **However** `tests/test_dispatch_instrumentation.py:287–301` asserts the exact key list — must update in lockstep.

## Open Questions

1. **What is the actual `max_tokens` truncation surface in SDK 0.1.41?** Per Adversarial §1, `ResultMessage.stop_reason` does not exist; the ticket's stated mitigation is unimplementable as written. Spec must decide between: (a) upgrade the SDK pin and verify the parser; (b) parse raw StreamEvent payloads via `include_partial_messages=True`; (c) watch `ResultMessage.subtype` for the CLI's max_tokens string (empirically determine); (d) accept that visibility is not feasible in this SDK pin and ship the effort flip alone with a docs note. **Deferred: will be resolved in Spec by asking the user — this is a load-bearing scope decision and must surface in the structured interview.**

2. **Should the implement-phase scope be `skill="implement"` only, or include `brain` and `conflict-repair` (which fire during implement phase with different skill names)?** Ticket framing is ambiguous. The narrower reading honors the ~1.5× cost ceiling more conservatively; the wider reading is closer to the time-window meaning of "implement phase." **Deferred: will be resolved in Spec — this is a scope decision the user owns.**

3. **How should `effort_override="xhigh"` interact with model escalation (haiku → sonnet → opus)?** Adversarial §2: Sonnet/Haiku silently downgrade `xhigh` to `high` while the event log records `xhigh`. Options: (a) gate the override on `model == "opus"` only (drop to `"high"` for Sonnet/Haiku); (b) pass `xhigh` regardless and accept logged-vs-actual divergence; (c) leave the retry loop's escalated dispatch with effort_override unchanged and rely on the `escalated=True` event flag for audit. **Deferred: will be resolved in Spec — this is a design decision affecting telemetry fidelity.**

4. **Is the rollback trigger as specified (>2× complex-tier mean cost per dispatch) load-bearing under Option 3?** Adversarial §4: aggregator collapse means a 3-4× regression on implement specifically may not cross the 2× aggregate threshold. Spec must either tighten the threshold, scope it to `skill="implement"` aggregates only, or accept that the trigger is informational rather than authoritative. **Deferred: will be resolved in Spec — informational vs authoritative is the user's call.**

5. **Does the test surface lock the `effort=xhigh` runtime contract?** Adversarial §5: no test exercises the real SDK with `effort="xhigh"`. Spec must decide whether to add a regression test (and whether to pin `claude-agent-sdk` explicitly in pyproject.toml). **Deferred: will be resolved in Spec — test coverage and version-pinning policy are user-owned.**

6. **Should this ticket ship as one commit or two sequenced changes?** Per Adversarial recommendation: (a) first resolve `stop_reason` detection feasibility; (b) then flip effort. Or accept that they ship together and document the limitation. **Deferred: will be resolved in Spec — depends on the resolution of Q1.**

7. **What is the docstring's authoritative effort vocabulary going forward?** The current docstring lists `"low", "medium", "high", "max"`. The new value list should be `"low", "medium", "high", "xhigh", "max"` and align with the Python SDK Literal once issue #834 lands. Worth a one-line note explaining `xhigh` is Opus-4.7-only. **Deferred: will be resolved in Spec — minor wording call but worth confirming.**
