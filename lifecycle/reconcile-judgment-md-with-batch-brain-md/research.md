# Research: Reconcile judgment.md with batch-brain.md

## Epic Reference

This ticket is part of epic [018 — Harness Quality Improvements](../../backlog/018-harness-quality-improvements-epic.md). The broader epic research at [`research/harness-design-long-running-apps/research.md`](../../research/harness-design-long-running-apps/research.md) established that `brain.py` is the post-failure triage module dispatching `SKIP/DEFER/PAUSE` verdicts after retry budget exhaustion — this ticket focuses specifically on the orphaned `judgment.md` prompt that predates that module.

---

## Codebase Analysis

### Files involved

| File | Role |
|------|------|
| `claude/overnight/prompts/judgment.md` | Orphaned prompt — dead code, zero call sites |
| `claude/overnight/prompts/batch-brain.md` | Active triage prompt — the only path used by `brain.py` |
| `claude/overnight/brain.py` | Sole module that loads a triage prompt |
| `claude/overnight/events.py` | Contains `JUDGMENT_FAILED` constant (line 46) and `EVENT_TYPES` tuple entry (line 88) — both dead |
| `claude/overnight/batch_runner.py` | Calls `request_brain_decision()` from `brain.py`; no direct prompt file reference |

### Content comparison

**`judgment.md` (32 lines)**
- Template variables: `{feature}`, `{task_description}`, `{error_summary}`, `{retry_count}`, `{learnings}`, `{spec_excerpt}`
- Actions: `retry | skip | defer` — includes RETRY, omits PAUSE
- Output: minimal JSON `{"action", "reasoning", "severity", "confidence"}`
- Missing: `{has_dependents}`, `{last_attempt_output}`, structured calibration, worked examples, `question` field

**`batch-brain.md` (109 lines)**
- Template variables: `{feature}`, `{task_description}`, `{retry_count}`, `{learnings}`, `{spec_excerpt}`, `{last_attempt_output}`, `{has_dependents}`
- Actions: `skip | defer | pause` — no RETRY (correct for post-exhaustion context)
- Output: full JSON with `{"action", "reasoning", "question", "severity", "confidence"}` plus field definitions table and three worked examples

### Call sites

**`judgment.md`**: Zero call sites in any Python file, shell script, or template. The only references exist in documentation and backlog artifacts (this backlog item, the epic item, the discovery research).

**`batch-brain.md`**: Exactly one call site — `claude/overnight/brain.py:103`:
```python
_BRAIN_TEMPLATE = Path(__file__).resolve().parent / "prompts/batch-brain.md"
```
Used unconditionally in `request_brain_decision()` via `_render_template(_BRAIN_TEMPLATE, {...})`.

### brain.py dispatch logic

There is no branching between the two prompts. `_BRAIN_TEMPLATE` is a module-level constant pointing to `batch-brain.md`. There is no conditional path, no config parameter, and no fallback that would reach `judgment.md`. The module docstring states: **"Replaces judgment.py with a unified SKIP/DEFER/PAUSE decision model."**

### Template variable population at call site

All seven variables that `batch-brain.md` uses are populated in `request_brain_decision()` before rendering. Empty-value cases are handled upstream:
- `last_attempt_output`: coerced to `''` if falsy (batch_runner.py line 485)
- `learnings`: `_read_learnings()` returns `"(No prior learnings.)"` on empty file
- `spec_excerpt`: `_read_spec_excerpt()` returns `"(No specification file found.)"` on missing file
- `has_dependents`: always a Python bool, always populated

`judgment.md`'s unique variable `{error_summary}` is constructed in `report.py` for the morning report narrative — it is never passed to any prompt rendering function.

### JUDGMENT_FAILED in events.py

- `JUDGMENT_FAILED = "judgment_failed"` is defined at line 46
- It is listed in `EVENT_TYPES` at line 88
- No Python file imports or calls `log_event(JUDGMENT_FAILED, ...)` anywhere in the codebase
- No `judgment_failed` events exist in any session log
- `log_event()` enforces membership in `EVENT_TYPES` at runtime — removing the constant without also removing the tuple entry would leave a dangling valid-but-unused slot

### Failure-mode check for removal

- No dynamic path construction or config keys reference `judgment.md`
- No shell scripts source or reference it
- `batch-brain.md` unavailability does not fall back to `judgment.md` — it falls back to `_default_decision()` (PAUSE, confidence=0.3) inside `request_brain_decision()`
- `_render_template()` in `batch_runner.py` is a separate duplicate used only for implementation templates — not a hidden call site for `judgment.md`
- `{error_summary}` placeholder in `judgment.md` is not mapped to any call site — removing the file eliminates a false-affordance trap (future authors seeing `error_summary` in `report.py` might incorrectly infer a connection)

### Conventions

- Always commit using `/commit` skill
- No changes to `batch-brain.md` or `brain.py` are required — they are correct as-is
- Both changes in `events.py` (constant definition line 46 AND tuple entry line 88) must ship together

---

## Web Research

Industry consensus on this exact pattern (two prompt files for the same decision, one with no callers):

- A two-prompt split is legitimate **only when an explicit routing rule exists** — e.g., "use lightweight prompt when `has_dependents` is unavailable; use full-signal prompt when it is." Without a routing rule, the lighter prompt is redundant.
- Standard resolution for a superseded prompt is deletion with a commit message documenting the supersession — no automated mechanism exists; this is a manual audit step.
- **Anti-pattern explicitly called out**: duplicating shared instructions across files without a shared base causes drift. Both files will diverge on shared logic over time. The fix is extraction or consolidation, not documentation.
- The Anthropic context engineering principle applies: "start with the minimal token set and add only based on observed failure modes." `batch-brain.md` was built by adding to the signal that `judgment.md` lacked — it is the evolved, authoritative version.

Sources: Anthropic context engineering guidance, PromptLayer modular architecture post, agenta.ai prompt versioning guide, LangSmith prompt management docs.

---

## Requirements & Constraints

- **Philosophy**: "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." — `requirements/project.md`. Dead code has no place to earn; deletion is correct.
- **Graceful partial failure**: The `_default_decision()` PAUSE fallback in `brain.py` ensures failed features surface to the human rather than silently skipping — this is the safety net that covers all edge cases, not `judgment.md`.
- **Action vocabulary mismatch**: `BrainAction` enum in `brain.py` defines `SKIP`, `DEFER`, `PAUSE` only. `judgment.md` exposes `retry` as a valid action — this is a semantic incompatibility that would cause a parsing error if `judgment.md` were ever accidentally invoked.
- **Scope boundaries**: No changes to `batch-brain.md` content, `brain.py` logic, or any other overnight runner component. This is a dead-code cleanup, not a behavioral change.
- **Out of scope**: Truncating `last_attempt_output` in `batch-brain.md` (ticket 023), modifying brain dispatch logic (ticket 020).

---

## Tradeoffs & Alternatives

| Option | When correct | Verdict |
|--------|-------------|---------|
| **A: Remove `judgment.md`** | It has no live call sites | ✅ **Correct** — confirmed by codebase analysis |
| **B: Reconcile `judgment.md`** | It IS called in live paths but missing fields | ✗ Not applicable — zero call sites |
| **C: Document the relationship** | The split is intentional by design | ✗ Documents a known-bad pattern; inapplicable since file is dead |
| **A + batch-brain.md hardening** | judgment.md dead AND batch-brain.md lacks empty-value handling | ✗ Not needed — empty-value handling already correct |

Option A is the correct and complete resolution. No `batch-brain.md` hardening is needed — all seven context variables are populated before rendering, and empty-value cases are handled upstream in Python.

---

## Adversarial Review

The adversarial agent validated the resolution with the following nuances:

- **Duplicate `_render_template()` in `batch_runner.py`**: A separate copy of the render function exists, but its only caller passes `IMPLEMENT_TEMPLATE`, not anything in the prompts directory. Not a current issue, but a latent risk if future callers use it with arbitrary paths.
- **`events.py` removal requires two edits**: The constant definition (line 46) AND the `EVENT_TYPES` tuple entry (line 88) must both be removed. Removing only the constant leaves a dormant valid-event-type slot — `log_event()` would still accept `"judgment_failed"` as a valid event string, which is misleading.
- **Docstring evidence is corroborating, not primary**: The "Replaces judgment.py" docstring refers to the old Python module, not specifically the prompt file. The definitive evidence is the zero-call-sites grep finding.
- **Pre-existing observability gap (out of scope)**: The `BRAIN_DECISION` event does not distinguish genuine PAUSE decisions from fallback-to-default PAUSE. `brain_unavailable` is logged separately, so forensic analysis is possible. Not introduced by this change.

No blocking failure modes found.

---

## Open Questions

None — the codebase analysis was definitive. The resolution is remove `judgment.md` and clean up the dead `JUDGMENT_FAILED` constant in `events.py`.
