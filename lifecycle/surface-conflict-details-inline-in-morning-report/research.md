# Research: Surface conflict details inline in morning report

## Epic Reference

Background context: `research/overnight-merge-conflict-prevention/research.md` — a discovery covering the full overnight merge-conflict prevention epic (tickets 014–017). This ticket is Approach C from that research: extract `conflict_summary` and `conflicted_files` from the `merge_conflict_classified` event and surface them inline in the morning report. The epic research already contains the critical DR-3 decision record and blocking risk identification; this ticket-level research provides the precise implementation detail.

---

## Codebase Analysis

### Files that will change

- `claude/overnight/report.py` — `render_failed_features()` is the only production file that needs to change
- `claude/overnight/tests/test_report.py` — new tests required (blocking per DR-3; currently only tests `render_completed_features`)

### Exact function name

The function is **`render_failed_features`** (no leading underscore). The backlog item and epic research both use `_render_failed_features` — this is incorrect. The function is public.

### Existing event loop in `render_failed_features` (lines 774–778)

```python
retry_counts: dict[str, int] = {}
for evt in data.events:
    if evt.get("event") == "retry_attempt":
        feat = evt.get("feature", "")
        retry_counts[feat] = retry_counts.get(feat, 0) + 1
```

This is the exact pattern to follow for conflict event extraction. The main render loop uses `retry_counts.get(name, 0)` where `name` is the key from `data.state.features`.

### Feature name key format

Keys in `data.state.features` are lowercase hyphenated lifecycle slugs (e.g. `"cache-player-array-eliminate-per-frame-group-lookup"`). They come from the master plan's Features table (`MasterPlanFeature.name`) parsed verbatim — no `slugify()` is applied during parsing. Same strings are used as lifecycle directory names.

### Feature name in `merge_conflict_classified` events

At `batch_runner.py:1358`:
```python
overnight_log_event(
    "merge_conflict_classified",
    config.batch_id,
    feature=name,
    ...
)
```
`name` originates from `feature_names = [f.name for f in master_plan.features]` — the same raw cell text that becomes the state dict key. **Both originate from the same table cell: no normalization divergence by construction.** The feature name in events and the key in `data.state.features` are identical strings.

### Event availability: is `merge_conflict_classified` guaranteed?

**Yes.** `classify_conflict()` in `claude/pipeline/merge.py` never returns `None`: it either returns a populated `ConflictClassification` or catches all exceptions and returns `ConflictClassification(conflicted_files=[], conflict_summary="classification failed")`. The guard `if merge_result.conflict and merge_result.classification is not None` at `batch_runner.py:1354` is defensive but never false when `conflict=True`. Therefore `merge_conflict_classified` is always written before `feature_paused` for every conflict — they are guaranteed paired events.

### `data.events` structure

`list[dict[str, Any]]` (JSONL parsed into dicts). Each event:
```json
{
  "v": 1,
  "ts": "2026-04-01T21:22:09.146485+00:00",
  "event": "merge_conflict_classified",
  "session_id": "<id>",
  "round": 1,
  "feature": "feature-slug",
  "details": {
    "conflicted_files": ["src/foo.py", "src/bar.py"],
    "conflict_summary": "Both branches modified the same function signature"
  }
}
```

Events are in chronological (append-only) order. The constant is `events.py:60` — `MERGE_CONFLICT_CLASSIFIED = "merge_conflict_classified"`.

### Existing tests

None for `render_failed_features` or `collect_report_data`. `test_report.py` only tests `render_completed_features`. New tests go in `claude/overnight/tests/test_report.py` using existing helpers `_pytest_make_state` and `_pytest_make_data`.

### Integration pattern (already established)

```python
# In render_failed_features(), add after retry_counts loop:
conflict_info: dict[str, dict] = {}
for evt in data.events:
    if evt.get("event") == "merge_conflict_classified":
        feat = evt.get("feature", "")
        conflict_info[feat] = evt.get("details", {})

# In main render loop:
info = conflict_info.get(name)  # None for non-conflict pauses
if info:
    for f in info.get("conflicted_files", []):
        lines.append(f"  - `{f}`")
    lines.append(f"  - Conflict summary: {info.get('conflict_summary', '')}")
```

---

## Web Research

### Join pattern precedent in this codebase

The `retry_counts` dict (events → dict by feature, used in `render_failed_features`) and `files_by_feature` dict (`batch_results` → dict by feature, used in `render_completed_features`) are direct precedents. The conflict enrichment follows the same structure. Last-wins semantics on the dict build matches the existing `batch_runner.py:654` behavior.

### SIEM/log correlation model

The established pattern (Splunk, Graylog, SIEM) maps directly: `data.state.features` is the primary entity dict; `data.events` contains enrichment data. Join key is the feature name string. This is the "enrich at render time from pre-loaded events" pattern.

### Output format: markdown, not Rich

The morning report is a `.md` file written to `lifecycle/sessions/{session_id}/morning-report.md`. The existing `render_failed_features` appends to `lines: list[str]` and joins with `"\n"`. The Rich library is not applicable — use the existing markdown list pattern.

### Silent join failure remains the primary risk

Even though both keys originate from the same code path (eliminating normalization divergence), the defensive mitigation is an automated test — not a normalization layer. If a future code path ever diverges, the test catches it; a normalization layer would mask the divergence silently.

---

## Requirements & Constraints

- **"Surface every failure clearly in the morning report — no silent skips."** (`requirements/project.md`) Morning is strategic review — the reviewer must be able to act without opening log files. This requirement directly mandates inline conflict details.
- **File-based state only** (`requirements/project.md`): No database. The event log is the authoritative record for conflict details. `data.events` is the only access path.
- **No schema change to `OvernightFeatureStatus`** (backlog 015 findings, DR-3): changes live entirely in `report.py`.
- **Blocking requirement — automated test** (DR-3): "The implementation must include an automated test (not just manual inspection) that verifies the feature name in `merge_conflict_classified` events matches the key in `data.state.features` for a representative conflict scenario."
- **Morning report is read by `/morning-review` skill** (`docs/overnight.md`): structural changes to the failed features section must remain parseable by that workflow. The report is consumed top-to-bottom: executive summary → completed features → deferred questions → failed features.
- **Ticket 016 depends on this work**: ticket 016 (recovery guidance in morning report) explicitly states "this ticket depends on the event log join work in 015." The `conflict_info` dict built here may be reused or extended for 016's recovery block.
- **Ticket 002 is adjacent** (no-commit failure root causes): also targets `render_failed_features()`. These may be combined or tracked separately — no explicit dependency declared.

---

## Tradeoffs & Alternatives

### Approach A: Pre-pass dict build before render loop (Recommended)

Add a second `for evt in data.events` loop immediately after the existing `retry_counts` loop, building `conflict_info: dict[str, dict]`. In the main render loop, `conflict_info.get(name)` provides details or `None`.

**Pros**: Mirrors the `retry_counts` pattern exactly — same structure, same idiom, ~6–10 lines total. Single-purpose loop is self-describing. Easiest to test (inject events into `ReportData`, call function, assert output). Zero risk to existing rendering. Graceful degradation (silent omission) identical to existing behavior.

**Cons**: Two separate event-scan loops (vs. one combined). Minor — they filter for different event types; combined would be harder to read.

### Approach B: Fold into existing retry-count loop

Add a second branch inside the existing loop body.

**Pros**: Marginally fewer lines (2–3).

**Cons**: Makes a focused single-purpose loop multi-purpose. Harder to reason about and test in isolation. A future maintainer adding a third event type makes the loop a multi-purpose accumulator. Not recommended.

### Approach C: Move join upstream into `collect_report_data()`

Add `conflict_details: dict[str, dict]` field to `ReportData`, populate in `collect_report_data()`.

**Pros**: Better unit-test isolation for the join logic. Correct architecture if conflict details are needed in multiple render functions.

**Cons**: Modifies `ReportData` schema, `collect_report_data`, and the renderer — three change sites. `collect_report_data` currently doesn't interpret event content (treats `events` as a raw log), so this would be the first case. Over-architected for a single-consumer use case. Refactor to C makes sense if/when 016 or another ticket needs the same data; not now.

### Graceful degradation

`conflict_info.get(name)` returns `None` when no `merge_conflict_classified` event exists for a feature (non-conflict pauses, or future code path divergence). The conflict block is simply not rendered; `fs.error` remains the only failure description. No crash, no corrupt output.

---

## Open Questions

_None — all questions resolved during research._

> `/morning-review` presents the failed-features section verbatim to the reviewer (Step 3, references/walkthrough.md). No structural parsing. Free readable markdown is correct.
