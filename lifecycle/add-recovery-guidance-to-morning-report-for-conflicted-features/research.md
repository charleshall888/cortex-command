# Research: Add recovery guidance to morning report for conflicted features

## Epic Reference

Background context: `research/overnight-merge-conflict-prevention/research.md` — discovery covering the full overnight merge-conflict prevention epic (tickets 014–017). This ticket (016) is the recovery guidance layer that sits on top of ticket 015's conflict detail rendering. Ticket 015 surfaced conflicted files and conflict summary inline; 016 adds the branch name so the user knows where their work lives.

---

## Codebase Analysis

### Current state of `render_failed_features` after ticket 015

File: `claude/overnight/report.py`, function `render_failed_features` (lines 748–828).

After 015, the failed-feature block for a conflicted feature renders as:

```
### feature-name: merge conflict in src/foo.py
- Retry attempts: 0
- Circuit breaker: not triggered
- **Conflict summary**: 2 file(s) conflicted: src/foo.py, src/bar.py
- **Conflicted files**: `src/foo.py`, `src/bar.py`
- Learnings: `lifecycle/feature-name/learnings/progress.txt`
- **Last recovery attempt**: ... (if any)
**Cost**: $0.12 (if any)
- **Suggested next step**: Resolve conflict manually, then retry
- **Last worker output**: ... (if any)
```

015 added the `conflict_info` dict (lines 781–787) and the conflict summary/files rendering block (lines 796–803). The `_suggest_next_step()` function (lines 962–971) pre-existed 015 and already handles the conflict case: `"Resolve conflict manually, then retry"` for errors containing `"merge conflict"` or `"conflict"`.

### What 016 adds

The **branch name** is the one recovery piece not yet shown. After a conflict pause, the user needs to know which branch holds their in-progress work before they can act on the "Suggested next step" message.

### Branch name derivation

Branch name: `f"pipeline/{name}"` where `name` is the key from `data.state.features`.

Confirmed in two places:
- `claude/pipeline/merge.py:199`: `branch = branch if branch is not None else f"pipeline/{feature}"`
- `claude/pipeline/conflict.py:236`: `feature_branch = f"pipeline/{feature}"`

No state field lookup required — the branch name is deterministically constructible from the feature name in the render loop.

### Event data and `conflict_info` structure

`batch_runner.py:1355–1364` writes the `merge_conflict_classified` event via `overnight_log_event` with `details` nesting:
```python
overnight_log_event(
    "merge_conflict_classified",
    config.batch_id,
    feature=name,
    details={
        "conflicted_files": merge_result.classification.conflicted_files,
        "conflict_summary": merge_result.classification.conflict_summary,
    },
    log_path=config.overnight_events_path,
)
```

`report.py` already reads this correctly: `details = evt.get("details", {})`.

**Note**: `merge.py`'s internal `_log` writes flat fields to the pipeline events path (separate from `overnight-events.log`). This is a different log — no discrepancy with `report.py`'s reader.

### `ConflictClassification` schema — no type/category field

`claude/pipeline/conflict.py:33–38`:
```python
@dataclass
class ConflictClassification:
    conflicted_files: list[str]
    conflict_summary: str
```

Only two fields. The `conflict_summary` is a descriptive string (e.g., `"2 file(s) conflicted: src/foo.py, src/bar.py"`) — not a semantic type/category. The ticket's "contextually appropriate guidance based on conflict classification" is not feasible with existing data. A single fixed message is correct given the available data.

### `_suggest_next_step` already provides conflict action guidance

Lines 962–971:
```python
def _suggest_next_step(error: str) -> str:
    error_lower = error.lower()
    if "merge conflict" in error_lower or "conflict" in error_lower:
        return "Resolve conflict manually, then retry"
    ...
```

This already fires for conflicted features and says "Resolve conflict manually, then retry". 016 should not replace or alter this — it complements it by telling the user *which branch* to checkout to do so.

### Exact insertion point

The branch name line belongs inside the `if conflict is not None:` block, after the conflicted-files line (line 803) and before the `- Learnings:` line (line 804). This groups all conflict-specific recovery info together.

Current block (lines 796–804):
```python
conflict = conflict_info.get(name)
if conflict is not None:
    conflict_summary = conflict.get("conflict_summary", "")
    lines.append(f"- **Conflict summary**: {conflict_summary}")
    conflicted_files = conflict.get("conflicted_files", [])
    if conflicted_files:
        files_str = ", ".join(f"`{f}`" for f in conflicted_files)
        lines.append(f"- **Conflicted files**: {files_str}")
lines.append(f"- Learnings: ...")
```

Add `lines.append(f"- **Recovery branch**: \`pipeline/{name}\`")` immediately after the conflicted-files block, still inside the `if conflict is not None:` guard.

### Test file

`claude/overnight/tests/test_report.py` already has helpers `_pytest_make_state` and `_pytest_make_data`, and tests for `render_failed_features` were added in 015. New test: inject a `merge_conflict_classified` event into `ReportData` and assert the rendered output contains `- **Recovery branch**: \`pipeline/feature-name\``.

---

## Tradeoffs

### Approach A: Add branch name inside `if conflict is not None:` block (Recommended)

Add one line inside the existing conflict block. Branch name is `f"pipeline/{name}"` — no new data needed.

**Pros**: Minimal diff, mirrors ticket description ("recovery block"), consistent with 015's approach. Branch line only appears for conflicted features (guarded by `if conflict is not None:`).

**Cons**: None.

### Approach B: Update `_suggest_next_step` to include the branch name

Change `_suggest_next_step(error)` to accept a `feature: str` param and return `"Checkout \`pipeline/{feature}\`, resolve conflict, then retry"`.

**Pros**: More actionable single line.

**Cons**: Changes a shared utility function signature. `_suggest_next_step` is called for all failed features — the function would need to accept an optional `feature` param and handle the non-conflict case. More diff, more risk to existing "Suggested next step" behavior for non-conflict failures. Not needed when the branch name is already shown as a separate line.

---

## Open Questions

_None — all questions resolved during research._
