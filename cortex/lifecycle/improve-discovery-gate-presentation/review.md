# Review: improve-discovery-gate-presentation

## Stage 1: Spec Compliance

### Requirement 1: `## Headline Finding` slot with content-population obligation
- **Expected**: `skills/discovery/references/research.md` template gains `## Headline Finding` heading above `## Architecture` with a stable content-population marker phrase under the slot. Acceptance: (a) `grep -c '^## Headline Finding$' skills/discovery/references/research.md` ≥ 1; (b) structural test confirms ordering above `## Architecture`; (c) stable marker phrase under the slot.
- **Actual**: Template has `## Headline Finding` at line 84 and `## Architecture` at line 123 (correct ordering). `grep -c '^## Headline Finding$' skills/discovery/references/research.md` returns `1`. Body under the slot (lines 85–90) carries the verbatim marker phrase `State the verdict and the one or two key findings supporting it` plus additional content-population framing ("must stand on its own without requiring the reader to scan downstream sections to recover the bottom line"). The marker phrase is exercised by `test_r1_headline_finding_template_slot`, which verifies it appears in the slot body (not just the file).
- **Verdict**: PASS
- **Notes**: All three acceptance criteria (a, b, c) verified literally.

### Requirement 2: R4 gate-presentation reorder
- **Expected**: `skills/discovery/SKILL.md` R4 gate prose names `## Headline Finding` before `## Architecture` as decision criterion (not procedural sequence). Acceptance: (a) `grep -c 'Headline Finding' skills/discovery/SKILL.md` ≥ 1; (b) structural test asserts R4 gate-prose names Headline Finding before Architecture. Additionally, empty-body detector inspects the slot at gate-prompt-construction time and falls back to Architecture-first with a warning.
- **Actual**: `grep -c 'Headline Finding' skills/discovery/SKILL.md` returns `1` (single mention on line 74, the R4 gate-prose line). Line 74 reads `"The gate's first content section is \`## Headline Finding\` from research.md, followed by the \`## Architecture\` sub-sections..."`. Empty-body detection is encoded in the same sentence: `"When the \`## Headline Finding\` section is missing in research.md, or its body is empty/whitespace-only, the gate falls back to Architecture-first presentation and surfaces a warning naming the condition (heading absent vs. empty body)."` Phrasing is decision-criterion form (gate's first content section IS X, followed by Y) rather than procedural sequence.
- **Verdict**: PASS
- **Notes**: Empty-body detector is prose-encoded rather than a separate helper-module subcommand; the spec's Edge Cases section and Changes-to-Existing-Behavior list both frame it as gate-prompt-construction time prose, which matches. No new helper subcommand required.

### Requirement 3: `drop`'s gate-option description rewords to neutral terminus
- **Expected**: `drop`'s description in `skills/discovery/SKILL.md` R4 gate names both legitimate uses (research-sufficient close + abandon) without privileging either. Acceptance: (a) stable marker phrase indicating dual-use; (b) `abandon`/`failure`/`fail`/`discard` are not the only descriptors.
- **Actual**: Line 78 of SKILL.md reads: `"\`drop\` — neutral terminus: close discovery when research is sufficient and no tickets are warranted, OR abandon outright. Both uses are legitimate; the user selects \`drop\` whenever they want to exit without filing tickets, regardless of motive."` The phrase `"close discovery when research is sufficient and no tickets are warranted, OR abandon outright"` is the stable dual-use marker (pinned verbatim in `test_r3_drop_description_has_dual_use_marker`). `abandon` appears once, alongside `neutral terminus`, `close discovery`, `research is sufficient`, `exit without filing tickets`, and `regardless of motive` — `abandon` is not the only descriptor. `failure`/`fail`/`discard` do not appear in the description.
- **Verdict**: PASS
- **Notes**: The test also enforces the marker phrase lives on the `drop` bullet specifically (guard against moving the phrase to a different option).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Heading name `## Headline Finding` is title-cased and consistent with the template's other H2 sections (`## Architecture`, `## Research Questions`, `## Decision Records`, etc.). Test file name `test_discovery_gate_presentation.py` matches the surrounding `tests/test_discovery_*.py` pattern. Test function names use the `test_r{N}_...` convention that ties directly back to spec requirement numbering. Marker-phrase constants (`R1_HEADLINE_MARKER_PHRASE`, `R3_DROP_DUAL_USE_MARKER_PHRASE`) are upper-snake-case module constants — appropriate for verbatim pinned strings.
- **Error handling**: Tests use exact-line and substring matching with informative assertion messages that name the requirement, the offending line, and what the spec expects. Empty-body detection in SKILL.md prose names both failure conditions explicitly (heading absent vs. empty body). The fallback behavior (Architecture-first + warning) is documented inline rather than silently degrading.
- **Test coverage**: `.venv/bin/pytest tests/test_discovery_gate_presentation.py -v` passes all 3 tests (R1, R2, R3) in 0.01s. Literal acceptance commands from the spec match: `grep -c '^## Headline Finding$' skills/discovery/references/research.md` = 1; `grep -c 'Headline Finding' skills/discovery/SKILL.md` = 1; `awk` ordering check confirms headline (line 84) before architecture (line 123) in the template. Plugin mirrors (`plugins/cortex-core/skills/discovery/{SKILL.md,references/research.md}`) match canonical sources byte-for-byte (`diff` clean), confirming the dual-source sync ran. Runtime validation is deferred to the next applicable posture-check discovery run per spec Non-Requirements and Technical Constraints — that deferral is explicit and accepted in the spec.
- **Pattern consistency**: Gate prose uses decision-criterion encoding (`"The gate's first content section is X, followed by Y"`) rather than procedural narration, aligning with the CLAUDE.md "What and Why, not How" principle. No MUST/CRITICAL/REQUIRED tokens introduced in `skills/discovery/SKILL.md` (verified by grep), consistent with the soft positive-routing default. No new `approval_checkpoint_responded` response values, no new event types, no new `_RESPONSE_VALUES` entries, no new `bin/.events-registry.md` rows — matches the spec's "No new event types or response values" Technical Constraint. The marker-phrase-pinning pattern in the test file follows the inventory-drift-backstop pattern from the `kept pauses` parity test (`tests/test_lifecycle_kept_pauses_parity.py`) the project uses elsewhere.

## Verdict
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
