# Specification: Reconcile judgment.md with batch-brain.md

## Problem Statement

The overnight runner's post-failure triage system contains an orphaned prompt file, `judgment.md`, that was superseded by `batch-brain.md` when `brain.py` replaced the prior judgment-based module. `judgment.md` has zero call sites anywhere in the codebase, a semantic vocabulary mismatch with the current system (it exposes a `retry` action that `BrainAction` no longer supports, and omits the `pause` action that `brain.py` produces), and lacks two of the seven context variables that `batch-brain.md` uses. Additionally, the `JUDGMENT_FAILED` event constant in `events.py` is a dead artifact from the same era with no emitters. The prompt file is a false-affordance trap: future authors could incorrectly assume it is connected to `error_summary` construction in `report.py` or wire it into a new code path, inheriting a semantically broken triage prompt. Removing both artifacts eliminates the trap and reduces maintenance surface without affecting any live behavior.

## Requirements

All requirements are must-have. This is a dead-code removal with no optional scope.

1. **[Must-have] Delete `claude/overnight/prompts/judgment.md`**: The file is removed from the repository.
   - Acceptance criteria: `judgment.md` does not exist at `claude/overnight/prompts/judgment.md`; `grep -rn "judgment" claude/ --include="*.py" --include="*.sh"` returns no matches

2. **[Must-have] Remove `JUDGMENT_FAILED` from `events.py`** — both the constant definition (`JUDGMENT_FAILED = "judgment_failed"`) and its entry in the `EVENT_TYPES` tuple are deleted in a single edit. These are two separate removals that must happen atomically.
   - Acceptance criteria (R2a): `events.py` contains no line matching `JUDGMENT_FAILED = "judgment_failed"`; `import events; hasattr(events, "JUDGMENT_FAILED")` returns `False`
   - Acceptance criteria (R2b): the string `"judgment_failed"` is not present in the `EVENT_TYPES` tuple; `log_event("judgment_failed", ...)` raises `ValueError`

3. **[Must-have] Add a regression test for `events.py`** that verifies both R2a and R2b. Write a new test file `tests/test_events.py` with at minimum:
   - A test asserting `not hasattr(events, "JUDGMENT_FAILED")`
   - A test asserting `log_event("judgment_failed", ...)` raises `ValueError`
   - Acceptance criteria: the new test file exists; `just test` includes it and it passes

4. **[Must-have] All existing tests pass**: No regressions introduced.
   - Acceptance criteria: `just test` exits with status 0

## Non-Requirements

- **No changes to `batch-brain.md`** — it is the authoritative triage prompt and its empty-value handling is already correct
- **No changes to `brain.py`** — its dispatch logic is correct; `_default_decision()` PAUSE fallback covers all failure modes
- **No changes to `batch_runner.py`** — it has no direct reference to either prompt file
- **No fallback hardening in `batch-brain.md`** — all seven context variables are populated upstream before template rendering; no additional defensive handling is needed
- **No removal of the duplicate `_render_template()` in `batch_runner.py`** — that function is used only for implementation templates; its cleanup is a separate concern
- **Not creating any replacement for `judgment.md`** — `batch-brain.md` is the complete and correct replacement; there is no scenario where `judgment.md` would be resurrected

## Edge Cases

- **Existing session log files containing `judgment_failed` events**: `read_events()` in `events.py` does not validate event names against `EVENT_TYPES` — it reads event name strings from JSON and returns them without validation. Old log files with `judgment_failed` events parse correctly after removal. No migration of log files is needed.
- **Stale imports referencing `JUDGMENT_FAILED` by name**: If any code imports `from events import JUDGMENT_FAILED`, that import will fail after removal with `ImportError`. Research confirmed no such imports exist. R2a's acceptance criteria guard against this regressing.
- **Partial removal (constant deleted but tuple entry left)**: `log_event()` enforces `EVENT_TYPES` membership at runtime — leaving `"judgment_failed"` in the tuple without the constant symbol means `log_event` still accepts the event string. This is the primary partial-removal risk; R2b and R3's new test guard against it.

## Technical Constraints

- R2's two removals (constant definition and `EVENT_TYPES` tuple entry) **must be made in a single atomic edit** — do not remove the constant definition in one edit and the tuple entry in a separate edit. Navigate to each removal by searching for the symbol name `JUDGMENT_FAILED`, not by line number (line numbers shift after the first removal).
- The test in R3 must call `log_event()` with a real session ID and event type to exercise the actual validation path, not just inspect the `EVENT_TYPES` tuple directly — the tuple inspection verifies R2b structurally, but the `log_event` call verifies the enforcement behavior.
- Commit using `/commit` skill per project conventions
