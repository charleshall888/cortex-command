# Plan: wire-requirements-drift-check-into-lifecycle-review

## Overview

Two files change: `skills/lifecycle/references/review.md` (four sequential edits to protocol and artifact format) and `claude/overnight/report.py` (one new helper + two call sites). The review.md edits form a dependency chain (§1 → prompt → format → §4); the report.py tasks are independent of the review.md chain and of each other.

## Tasks

### Task 1: Update review.md §1 — structured tag-based requirements doc loading

- **Files**: `skills/lifecycle/references/review.md`
- **What**: Replace the existing freeform area doc scan in §1 with a four-step structured tag-based loading protocol. The new step determines which requirements docs are relevant before the reviewer is dispatched.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current §1 bullet (line 12): `"If requirements/project.md exists, read it. Scan requirements/ for area docs relevant to this feature and read those too. Include a requirements compliance check in Stage 1 — verify the implementation doesn't violate project or area requirements"`
  - Replace with these four steps:
    1. Read `requirements/project.md` (always)
    2. Read `lifecycle/{feature}/index.md` and extract the `tags:` array from its YAML frontmatter
    3. Read the Conditional Loading section of `requirements/project.md`; for each tag word in the tags array, check case-insensitively whether any Conditional Loading phrase contains that word; collect the area doc paths for all matches
    4. If matching area docs are found, read them too. Record the full list of loaded requirements files for injection into the reviewer prompt. If no tags match or no area docs are found, load project.md only and note: "no area docs matched for tags: {tags}; drift check covers project.md only"
  - The phrase "Include a requirements compliance check in Stage 1" is removed entirely — replaced by the drift section in Task 2.
- **Verification**: Read the updated `review.md` §1. Confirm the four-step structured loading replaces the single-line freeform scan. Confirm no mention of "requirements compliance check in Stage 1" remains. Confirm the step resolves to a list of requirements files that will be injected into the reviewer prompt.

---

### Task 2: Update review.md reviewer prompt — drift section instructions, remove Requirements Compliance

- **Files**: `skills/lifecycle/references/review.md`
- **What**: In the Reviewer Prompt Template (§2): remove the Requirements Compliance block from Stage 1 instructions; update the `## Project Requirements` section note to describe the injected file list from Task 1; add a new `## Requirements Drift` instruction block after Stage 2; add the drift section template to the "Write Review" instructions.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Remove this block from Stage 1 instructions: `"If project or area requirements were provided above, add a **Requirements Compliance** check: verify the implementation does not violate any project-level constraints or quality attributes..."`
  - Update the `## Project Requirements` section header comment in the prompt to: `"{list of requirements docs loaded in §1, each on its own line with path and summary; if only project.md loaded, note 'only project.md loaded — no area docs matched tags'}"`
  - After the Stage 2 block and before "Write Review", add:
    ```
    ### Requirements Drift
    Using the project requirements provided above, compare the implementation against stated requirements.
    Note: requirements drift does NOT influence the verdict. This is an observation only.
    - If the implementation matches all stated requirements and introduces no new behavior not reflected in them: state = none
    - If the implementation introduces behavior not captured in the requirements docs, or changes behavior in a way requirements don't reflect: state = detected; list each drifted item as a bullet; name the requirements file that needs updating
    ```
  - In the "Write Review" → "CRITICAL" block, after the verdict JSON instructions, add:
    ```
    Your review.md MUST include a ## Requirements Drift section using exactly this format:
    ## Requirements Drift
    **State**: none | detected
    **Findings**:
    - (one bullet per drifted item, or "None" if state is none)
    **Update needed**: (path to requirements file that needs updating, or "None")
    The requirements_drift value in the verdict JSON MUST match: "none" when State is none, "detected" when State is detected.
    ```
- **Verification**: Read the updated reviewer prompt template. Confirm: (1) no "Requirements Compliance" block in Stage 1; (2) `## Project Requirements` section describes the injected file list; (3) Requirements Drift instruction block exists after Stage 2; (4) "Write Review" includes the exact drift section template.

---

### Task 3: Update review.md §3 artifact format — replace Requirements Compliance with Requirements Drift, extend verdict JSON

- **Files**: `skills/lifecycle/references/review.md`
- **What**: In §3 (Review Artifact Format), remove the conditional `## Requirements Compliance` section and replace it with a mandatory `## Requirements Drift` section; add `"requirements_drift": "none"` to the verdict JSON example.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Remove from the artifact format:
    ```markdown
    ## Requirements Compliance
    <!-- Only present if project/area requirements were loaded -->

    - **{constraint}**: {assessment}
    ...
    ```
  - In its place (between Stage 1 and Stage 2), add:
    ```markdown
    ## Requirements Drift

    **State**: none | detected
    **Findings**:
    - (one bullet per drifted item, or "None" if state is none)
    **Update needed**: (path to requirements file that needs updating, or "None")
    ```
    No `<!-- Only present if... -->` guard — this section is unconditionally required.
  - Update the verdict JSON example from:
    ```json
    {"verdict": "APPROVED", "cycle": 1, "issues": []}
    ```
    to:
    ```json
    {"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
    ```
- **Verification**: Read the updated §3 artifact format. Confirm: (1) no `## Requirements Compliance` section exists; (2) `## Requirements Drift` section is present without an optional comment guard; (3) verdict JSON includes `"requirements_drift": "none"`.

---

### Task 4: Update review.md §4 — pre-event validation, review_verdict event schema, constraints table

- **Files**: `skills/lifecycle/references/review.md`
- **What**: After "review.md is confirmed on disk" and before "update lifecycle/{feature}/index.md", add a pre-event validation step that checks for the `## Requirements Drift` section. Update the review_verdict event JSON template. Add a constraints table entry for drift.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - After the sentence "After the reviewer sub-task completes and `lifecycle/{feature}/review.md` is confirmed on disk" (§4 first paragraph), add a new paragraph:
    ```
    Before proceeding, validate that review.md contains a `## Requirements Drift` section. If the section is absent (e.g., the reviewer ran out of context), re-dispatch the reviewer with this targeted instruction: "review.md is missing the ## Requirements Drift section. Read the existing review.md, then append the ## Requirements Drift section in the correct format. Do not modify any other section." If the section remains absent after one re-dispatch, escalate to the user.
    ```
  - Update the review_verdict event template from:
    ```
    {"ts": "<ISO 8601>", "event": "review_verdict", "feature": "<name>", "verdict": "APPROVED|CHANGES_REQUESTED|REJECTED", "cycle": <N>}
    ```
    to:
    ```
    {"ts": "<ISO 8601>", "event": "review_verdict", "feature": "<name>", "verdict": "APPROVED|CHANGES_REQUESTED|REJECTED", "cycle": <N>, "requirements_drift": "none|detected"}
    ```
    Where `requirements_drift` is read from the `"requirements_drift"` field in the verdict JSON block.
  - Add to the Constraints table at the bottom:
    | "Requirements drift is hard to assess without clear traceability" | Assess against the requirements docs loaded in §1. If uncertain, log `detected` with a note — false positives generate a morning report entry; false negatives silently hide drift. |
    | "Requirements drift should influence whether I approve the feature" | Drift is an observation only. The verdict reflects spec compliance and code quality. A feature with detected drift may still be APPROVED. |
- **Verification**: Read the updated §4. Confirm: (1) validation step exists before index.md update; (2) review_verdict event template includes `"requirements_drift"` field; (3) two new constraints table entries exist. Then run `grep -c 'Requirements Compliance' skills/lifecycle/references/review.md` — confirm the count is 0 (cross-location consistency check across all four tasks).

---

### Task 5: Add `_read_requirements_drift()` helper to report.py

- **Files**: `claude/overnight/report.py`
- **What**: Add a `_read_requirements_drift(feature: str)` function after `_read_verification_strategy()` (line 671). Reads the `## Requirements Drift` section from review.md and extracts the `**State**:` and `**Findings**:` values.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Insert after `_read_verification_strategy()` (after line 671).
  - Function signature: `def _read_requirements_drift(feature: str) -> dict | None`
  - Return type contract: absent file → `None`; section not found → `None`; no `**State**:` line → `{"state": "malformed", "findings": []}`; valid section → `{"state": <value>, "findings": <list of bullet strings, excluding "None">}`
  - Three-step internal flow: (1) resolve and existence-check the review.md path under `lifecycle/{feature}/`; (2) extract the `## Requirements Drift` section body by matching from the section header to the next `##` heading or end of file; (3) extract `**State**:` value and collect `**Findings**:` bullet lines.
  - Pattern to follow: mirrors `_read_verification_strategy()` exactly — Path check, read_text, regex section extraction, graceful return on missing data.
- **Verification**: Unit test by creating a temp `lifecycle/test-feature/review.md` with a `## Requirements Drift` section and calling `_read_requirements_drift("test-feature")` in a Python REPL. Confirm: absent file → `None`; valid section with `none` → `{"state": "none", "findings": []}`; valid section with `detected` and findings → `{"state": "detected", "findings": ["..."]}`. Confirm malformed section (no `**State**:`) → `{"state": "malformed", "findings": []}`.

---

### Task 6: Wire drift findings into completed features section of morning report

- **Files**: `claude/overnight/report.py`
- **What**: In `_render_feature_block(name)` (inside `render_completed_features()`), after the "Notes from learnings" block, call `_read_requirements_drift(name)` and render a "Requirements drift" entry when state is `"detected"`.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Insert after the `learnings` block (after line 559, the `lines.append("")` following Notes).
  - Call `_read_requirements_drift(name)` and store the result.
  - Three cases to handle: (1) `drift` is `None` or `state == "none"` — no output; (2) `state == "detected"` — append a bold header line `"**Requirements drift detected** — update required before next overnight:"`, then one bullet line per finding, then a blank line; (3) `state == "malformed"` — append a single line noting the section is malformed and requires manual review, then a blank line.
- **Verification**: In `render_completed_features()` unit tests or via a manual dry run: create a mock `ReportData` with a merged feature, create `lifecycle/{name}/review.md` with `State: detected` and findings, call `render_completed_features(data)`, confirm "Requirements drift detected" block appears in output.

---

### Task 7: Add `render_pending_drift()` for non-completed features and wire into report

- **Files**: `claude/overnight/report.py`
- **What**: Add a `render_pending_drift(data: ReportData) -> str` function that scans `lifecycle/*/review.md` for features not in the completed (merged) set, surfaces those with detected drift. Wire into `generate_report()` after `render_completed_features(data)`.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Add `render_pending_drift(data: ReportData) -> str` function:
    1. Get merged features: the set of feature names where `fs.status == "merged"` from `data.state.features` (empty set if `data.state` is None)
    2. Get re-implementing features: for each feature found by `lifecycle/*/review.md`, read `lifecycle/{feature}/events.log` and check whether the most recent `phase_transition` event has `"to": "implement"` — if so, the feature re-entered implement after CHANGES_REQUESTED and its review.md is stale; exclude it
    3. Scan: glob `lifecycle/*/review.md` — for each, get `feature = path.parent.name`; skip if in merged set (already rendered in completed section); skip if in re-implementing set (stale artifact from prior cycle)
    4. Call `_read_requirements_drift(feature)` for remaining features; collect those with `state == "detected"`
    5. If no detected drift: return `""`
    6. Render as `## Requirements Drift Flags` section listing each feature with detected drift and its findings bullets
  - In `generate_report()` (around line 1175): insert `render_pending_drift(data),` after `render_completed_features(data),`
  - For reading events.log: follow the `read_events()` pattern from `claude.overnight.events` already imported in report.py; read `lifecycle/{feature}/events.log` if it exists, scan for phase_transition events
- **Verification**: (1) Create lifecycle dir with detected drift for a non-merged feature in review phase; run `generate_report()`; confirm `## Requirements Drift Flags` section appears. (2) Create a second lifecycle dir simulating CHANGES_REQUESTED cycle 1 (events.log with `phase_transition to=implement` after review_verdict); confirm that feature does NOT appear in `## Requirements Drift Flags`.

## Verification Strategy

1. Run `just validate-commit` — confirm no broken hooks
2. Manually read `skills/lifecycle/references/review.md` start-to-finish:
   - §1 shows four-step tag-based loading with no freeform "Scan requirements/" language
   - Reviewer prompt has no "Requirements Compliance" block, has `## Requirements Drift` instruction
   - §3 artifact format shows `## Requirements Drift` as mandatory (no optional comment), verdict JSON includes `"requirements_drift"`
   - §4 shows pre-event validation step and updated event schema
   - Constraints table has two drift entries
3. Run `uv run python -c "from claude.overnight.report import _read_requirements_drift; print('import ok')"` — confirm no import errors
4. End-to-end smoke test: manually create `lifecycle/test-drift/review.md` with a valid drift section; run `uv run python -c "from claude.overnight.report import _read_requirements_drift; import json; print(json.dumps(_read_requirements_drift('test-drift')))"` — confirm correct dict output
5. Run `just test` — confirm existing tests pass
