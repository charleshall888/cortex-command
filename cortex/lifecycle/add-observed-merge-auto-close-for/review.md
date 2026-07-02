# Review: add-observed-merge-auto-close-for

## Stage 1: Spec Compliance

### Requirement 1: Upgrade the §6 step-2 "PR already merged" advisory to be fetch-first, ticket-specific, and actionable
- **Expected**: At the `state == "MERGED"` exit, the advisory must (a) state local `main` may be behind after an out-of-band merge (§6a sync skipped) and instruct `git fetch origin main` (or pull) **first** before checking any ticket; (b) identify this session's completed-feature backlog tickets (the completed-feature list / zero-padded `backlog_id`s already surfaced in Section 2 from `overnight-state.json`) as the set to check; (c) instruct that any such ticket still open **after** the fetch is closed via §6b's closer, then pushed. Soft declarative phrasing only. Acceptance: `grep -iE "git fetch|git pull"` matches in the span, span references this session's completed-feature tickets and points to §6b, and `just test` exits 0.
- **Actual**: The revised span (canonical L461–464) reads: "This exit skips Section 6a's post-merge sync, so local `main` may lag the out-of-band merge — run `git fetch origin main` (or pull) first, before checking any ticket." (satisfies a). "If this session completed any features, check each one's backlog ticket (the completed-feature list and its zero-padded `backlog_id`s already surfaced in Section 2 from `overnight-state.json`)" (satisfies b). "For any still open after the fetch, close it via Section 6b's backlog closer, then push." (satisfies c). The edge case is handled: "With no completed features this session, there is nothing to check." Span greps: `git fetch|git pull` = 1, `Section 6b` = 1, `MUST|CRITICAL|REQUIRED` = 0 (soft phrasing preserved). `just test` exits 0 (7/7 suite groups passed).
- **Verdict**: PASS
- **Notes**: All three sub-elements and the zero-features edge case are present; phrasing is soft declarative with no escalation tokens.

### Requirement 2: Preserve the #342 closure-ordering guard by not embedding the close literal in the pre-`gh pr merge` region
- **Expected**: The §6 step-2 span must not contain `cortex-update-item`, `update_item`, or a `--status complete` close command — it references §6b's closer by section. Acceptance: `grep -nE "update[-_]item"` over the span returns no match; `tests/test_morning_review_status_close_ordering.py` exits 0.
- **Actual**: Span grep `update[-_]item|--status complete` = 0 (no close literal in the span). Positional check confirms ordering integrity: MERGED-exit line at L461, first `gh pr merge` literal at L487, first `cortex-update-item` at L574 — the close literal still appears after the merge literal, and the revised advisory references "Section 6b's backlog closer" by name. `tests/test_morning_review_status_close_ordering.py` passes (part of the 68 tests green across the two named suites).
- **Verdict**: PASS
- **Notes**: The section-reference approach (rather than a command literal) simultaneously satisfies the ordering guard, the MUST-escalation policy, and avoids the contract checker's E101/E103 on flagless inline `cortex-*` tokens.

### Requirement 3: Regenerate the dual-source mirror in the same commit
- **Expected**: Canonical `skills/morning-review/` edit requires the `plugins/cortex-overnight/skills/morning-review/` mirror regenerated and staged in the same commit. Acceptance: `git diff --exit-code` between canonical and mirror shows byte-parity; `tests/test_dual_source_reference_parity.py` exits 0.
- **Actual**: `cmp` of canonical vs mirror `walkthrough.md` exits 0 (byte-identical). `git show f889c8c7 --name-only` lists both paths in the one commit. `tests/test_dual_source_reference_parity.py` passes (green in the named-suite run).
- **Verdict**: PASS
- **Notes**: Commit `f889c8c7` carries both files; mirror is a clean regeneration with no hand edits (identical diff span in both).

## Stage 2: Code Quality

- **Naming conventions**: N/A for executable naming — this is advisory prose in a `references/walkthrough.md` step. The advisory refers to "Section 6b's backlog closer" by section, matching the document's established section-reference convention rather than inlining a command.
- **Error handling**: N/A — no code path. The advisory is soft and non-blocking (consistent with #342's Req-6/7 notes): if the operator declines to fetch, review completes normally and the ticket simply stays open (visible, not silently wrong), matching the spec's Edge Cases.
- **Test coverage**: The plan's verification steps were executed and pass — span greps (`git fetch|git pull` ≥1, `update[-_]item|--status complete` =0, `Section 6b` ≥1), `cmp` parity, both-paths-in-commit, the two named suites (`test_morning_review_status_close_ordering.py` + `test_dual_source_reference_parity.py`, 68 passed), and the full `just test` (7/7 suite groups, exit 0). No new tests were required or added (spec Non-Requirements: does not modify the ordering test).
- **Pattern consistency**: The diff is surgical — it touches only the four-line advisory span at the MERGED exit, leaving §6a, §6b, and the three-arm gate untouched (per Non-Requirements). Fetch-first ordering and section-reference-over-literal are consistent with the surrounding walkthrough style and #342's soft-advisory precedent.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
