# Review: add-vendor-endorsement-value-gating-to-discovery-decompose-phase

## Stage 1: Spec Compliance

### Requirement R1: Authoring-time norm
- **Expected**: One-line constraint in decompose.md stating vendor guidance, best practices, and industry standards are not sufficient Value alone; Value must state what problem this solves in *this* codebase. Acceptance: `grep -c "not sufficient Value"` >= 1.
- **Actual**: `decompose.md:146` under `## Constraints`: `- **Codebase-grounded Value**: Vendor guidance, best practices, and industry standards are not sufficient Value on their own — the Value field must state what problem this solves in *this* codebase.` Grep returns 1.
- **Verdict**: PASS
- **Notes**: Placement matches spec's "Changes to Existing Behavior" guidance (constraints block) and test `test_r1_norm_in_constraints` asserts section placement, not just presence.

### Requirement R2: Flag detection at §2 Value field
- **Expected**: Two-check flag detection (R2(a) local `[file:line]` grounding + R2(b) research-side premise check with both `premise-unverified` and absence-of-citation branches), plus non-gating surface-pattern helper listing vendor/authority phrasings. Acceptance: `[file:line]`, `premise-unverified`, and `canonical pattern|best practice|recommended` each >= 1.
- **Actual**: `decompose.md:23-27` expanded Value bullet contains R2(a) local grounding (line 24), R2(b) with both (i) `[premise-unverified: not-searched]` adjacent-to-claim branch and (ii) absence-of-citation branch with E1 base-rate note (line 25), E9 ad-hoc fallback stated explicitly (line 26), and the non-exhaustive surface-pattern helper listing 10 phrasings including `canonical pattern in $framework`, `industry best practice`, `recommended approach`, `standard pattern`, `widely adopted`, `accepted convention`, `Anthropic says`, `CrewAI docs`, `vendor X recommends`, `current conventions suggest` (line 27). Lexical-check caveat present. Greps return 2 / 1 / 3.
- **Verdict**: PASS
- **Notes**: The surface-pattern helper explicitly states it is non-gating ("do NOT by themselves flag the item"), matching spec's "surface-pattern match alone does **not** flag the item" wording. E1 base-rate ("dominant path for the current research corpus") and TC6 lexical limitation both documented.

### Requirement R3: Per-item acknowledgment with item-specific content
- **Expected**: When items flagged, present via `AskUserQuestion` one at a time, each prompt (a) quotes Value verbatim, (b) states R2 branch that flagged it (plus originating-Value surfacing for merged items via R5), (c) offers at minimum three choices: "Acknowledge and proceed", "Drop this item", "Return to research". Acceptance: `AskUserQuestion` >=1; three choices enumerated; quote Value + premise language present; merged-item origin surfaced.
- **Actual**: `decompose.md:37-42` under "(ii) Per-item acknowledgment": uses `AskUserQuestion`, requires each prompt to quote Value string verbatim, state the R2 branch (`R2(a)-no-grounding`, `R2(b)-research-absent`, or `both`), and offer exactly the three spec-named choices. Drop/Return-to-research/Acknowledge branches documented at line 42. Merged-item originating-input surfacing is documented at §3 R5 (line 70, clause iii): the R3 ack prompt for a merged flagged item must surface the originating flagged input's Value + premise. Grep returns 1 for AskUserQuestion.
- **Verdict**: PASS
- **Notes**: All three spec-named choices appear verbatim. The originating-Value surfacing requirement lives in the R5 paragraph at §3 rather than in the §2 ack prompt description, but the protocol text does describe the behavior as required — the §3 placement is appropriate because the merged-item case only arises after consolidation.

### Requirement R4: Cap-and-escalate
- **Expected**: Cap fires when >3 items flagged in pre-consolidation set OR all items flagged with N>=2. Halt with escalation message naming pre-consolidation count; choices "return to research" or "proceed anyway" (which resumes per-item ack). Acceptance: `pre-consolidation|before Consolidation` >=1 AND `more than 3|all items are flagged` >=1.
- **Actual**: `decompose.md:35` under "(i) R4 cap check (pre-consolidation)": cap fires when EITHER "more than 3" items flagged in pre-consolidation set OR "all items are flagged" with N>=2; halt message matches spec ("{N} of {total} flagged items (pre-consolidation) — recommend re-running research with premise verification"); offers "Return to research" or "Proceed anyway" (the latter resumes the per-item ack flow in (ii)). Grep returns 2 / 1.
- **Verdict**: PASS
- **Notes**: Pre-consolidation evaluation explicit. "Proceed anyway" correctly resumes ack flow (not skips to ticket creation), matching spec.

### Requirement R5: Flag propagation across §3 Consolidation
- **Expected**: Merged item carries flag if any input carried a flag; R4 cap evaluates pre-consolidation count; R3 ack for merged item surfaces originating input's Value + premise; E10 invariant (consolidation cannot zero the flagged set). Acceptance: propagation anchor >=1 AND ack-shows-originating-input text.
- **Actual**: `decompose.md:70` contains a dedicated R5 paragraph with four numbered clauses: (i) "merged item carries the flag" for R3 ack-display purposes — explicit propagation language; (ii) R4 cap on pre-consolidation count, not post-consolidation; (iii) R3 ack surfaces **originating** flagged input's Value string + R2 premise (branch and basis), with E5 cross-reference; (iv) E10 invariant stated as "consolidation cannot reduce the flagged set to zero". Greps return 1 / 1.
- **Verdict**: PASS
- **Notes**: E5 and E10 both explicitly called out within the R5 paragraph.

### Requirement R6: No disruption to unflagged path
- **Expected**: Unflagged items continue through the existing batch user-approval step. Acceptance: `grep -c "Present the proposed work items"` >= 1.
- **Actual**: `decompose.md:44` under "(iii) Unflagged items — batch review": `Present the proposed work items to the user for review before creating tickets. Unflagged items (including flagged items the user acknowledged in (ii)) continue through this existing batch-review behavior unchanged.` Grep returns 1.
- **Verdict**: PASS
- **Notes**: Original sentence preserved inside the new flow rather than removed — matches spec intent. "Flagged items the user acknowledged" correctly re-enter this batch flow.

### Requirement R7: Event logging for flag/ack/drop
- **Expected**: Three event shapes (`decompose_flag`, `decompose_ack`, `decompose_drop`) appended to existing research-topic event stream (same stream as `orchestrator-review.md:22-30`); skip-silent if no stream exists. Acceptance: each event name >=1.
- **Actual**: `decompose.md:46-52` block "(iv) Event logging (R7)": references the same event stream as `orchestrator-review.md:22-30`, names `research/{topic}/events.log` as an example path, states skip-silent-if-no-stream, and lists the three JSON shapes verbatim matching spec exactly (ISO 8601 ts, phase "decompose", item title, reason codes R2(a)/R2(b)/both for flag and drop). Greps return 1 / 1 / 1.
- **Verdict**: PASS
- **Notes**: Event schemas match spec character-for-character. "No new infrastructure" invariant documented (N3 compliance).

### Requirement R8: Tests
- **Expected**: Protocol-level test parsing updated decompose.md and asserting R1–R7 rule presence; `just test` exits 0.
- **Actual**: `tests/test_decompose_rules.py` is 258 lines with 20 discrete test functions covering R1 (constraints placement), R2 (`[file:line]`, `premise-unverified`, `canonical pattern`, absence-of-citation anchor, ad-hoc fallback anchor — each in §2), R3/R4/R6 (`AskUserQuestion`, `pre-consolidation`, `more than 3`, `all items flagged`, `Return to research`, `Present the proposed work items`, `flagged item` — each in §2), R7 (three event names in §2), R5 (propagation/originating/invariant anchors in §3), and R9 (`## Dropped Items` subsection heading within §6). Test module parses sections by `##`/`###` headings, strips HTML comments with `re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)`, and handles fenced code blocks so literal `##`/`###` lines in templates do not split sections. Running `.venv/bin/pytest tests/test_decompose_rules.py -v` returns exit 0, 20 passed in 0.02s.
- **Verdict**: PASS
- **Notes**: Exceeds the spec minimum (spec asks for grep assertions; test is **section-aware** — it asserts strings appear **within the expected heading's body**, not merely anywhere in the file). HTML-comment stripping closes the critical-review concern that rule text stranded in comments could satisfy a grep-only gate. One minor observation: `test_r9_dropped_items_subsection_in_write_decomposition_record` matches on `## Dropped Items` literal — this works because the fenced-code-block fence detection keeps the template lines inside the §6 body rather than being parsed as a new top-level section, which the test correctly handles.

### Requirement R9: Dropped-items subsection in §6 Decomposition Record
- **Expected**: `research/{topic}/decomposed.md` template extended with `## Dropped Items` listing title, reason (R2 branch), originating Value; omit when empty. Acceptance: `grep -c "Dropped Items|## Dropped"` >= 1.
- **Actual**: `decompose.md:114-118` in the §6 template: `## Dropped Items` heading with table header `| Title | Reason (R2 branch) | Originating Value |` and an omit-when-empty note: "Include this subsection only when items were dropped at R3's ack prompt; omit when no drops occurred." Grep returns 1.
- **Verdict**: PASS
- **Notes**: All three columns present. Omit-when-empty behavior documented. E6 linkage implicit via the "items dropped at R3's ack prompt" phrasing.

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `tests/test_decompose_rules.py` matches the project's `tests/test_*.py` convention (e.g., `tests/test_skill_contracts.py` cited in plan Context). Function names follow `test_<rule>_<anchor>_in_<section>` pattern, which reads as a failure-message-first convention — a failing assertion immediately names the rule and expected section. Constants (`REPO_ROOT`, `DECOMPOSE_MD`) use module-level uppercase, matching Python conventions.
- **Error handling**: Appropriate for a prose-edit + protocol-presence test. Module-level `DECOMPOSE_MD.exists()` assertion in the `sections` fixture prevents silent-pass when the target file is missing. `_find_section` uses `pytest.fail` with an informative message (includes the list of actual headings) when the expected keyword is not found, so a mis-named section produces a legible failure rather than a `KeyError`. Fenced-code-block tracking prevents false section splits on literal `##`/`###` lines inside templates.
- **Test coverage**: Strong. Spec R8 asks for "grep assertions on the strings named in each R's acceptance row" — implementation exceeds this by (a) stripping HTML comments before assertion, closing the stranded-comment loophole; (b) asserting each rule string appears within its expected section (section-aware placement), closing the wrong-section loophole where a later edit could move rule text to an unrelated section; (c) splitting assertions into 20 discrete tests so failures name the specific rule and expected section. Every R1–R7 and R9 acceptance anchor has a dedicated test. R8 (tests) is self-referential — the passing test file *is* the R8 deliverable. Runtime behavior (actual AskUserQuestion flow, event-log writes) is interactive/session-dependent per TC7 and accepted out-of-scope for automated verification.
- **Pattern consistency**: New prose follows the style of sibling skill references. `specify.md`'s §2a Research Confidence Check (cited in plan TC5 as the precedent) uses AskUserQuestion for signal-driven per-item gating — decompose.md's R3 ack flow follows this precedent. `orchestrator-review.md:22-30` documents event JSON shapes inside the section that emits them — decompose.md's R7 event block at §2 line 46-52 follows this precedent rather than introducing a separate subsection. Bullet formatting, `**bold**` emphasis, and backtick code fences match the rest of decompose.md.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
