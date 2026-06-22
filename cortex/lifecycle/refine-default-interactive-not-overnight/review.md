# Review: refine-default-interactive-not-overnight

## Stage 1: Spec Compliance

### Requirement 1: Interview assumes interactive verification, without relaxing criteria rigor
- **Expected**: In `specify.md`, (a) the Open Decision Resolution clause "the user is present during spec; implementation may run overnight without them" is rewritten to assume interactive/user-present execution while preserving the "ask the user directly" intent; (b) a §2 interview-posture note names user-present in-session verification and disclaims interrogating overnight-autonomy; the `(a)/(b)/(c)` acceptance-criteria format including the "if a command check is not possible" fallback is unchanged. Acceptance: `grep -c "may run overnight without them"` = 0; `grep -c "if a command check is not possible"` ≥ 1; posture note names user-present in-session verification.
- **Actual**: `grep -c "may run overnight without them"` = 0; `grep -c "if a command check is not possible"` = 1; `grep -ci "interactive"` = 3 (increased). The §2 posture note (L40, "Interview posture (interactive default)") states "the user is present in-session to confirm acceptance criteria" and "Do not interrogate how criteria would be verified autonomously or overnight; user-present, in-session verification is a first-class, legitimate outcome," and explicitly scopes itself to posture-only without relaxing binary-checkability. The Open Decision Resolution clause (L98) now reads "the user is present during spec; resolve open decisions now, because the implementer works from the spec…" — the "overnight without them" framing is removed and the "ask the user directly" intent is preserved (it is rule 2: "Ask the user directly"). The `(a)/(b)/(c)` format at L128 is unchanged, including the `(c)` "Interactive/session-dependent … if a command check is not possible" fallback.
- **Verdict**: PASS
- **Notes**: All three named checks pass and the posture note names user-present in-session verification as required.

### Requirement 2: refine's purpose/framing is execution-agnostic
- **Expected**: refine's purpose (L19) and Step 6 completion language no longer assert overnight as the assumed mode; purpose reads "prepares a backlog item for execution" (terse); the `outputs` line and the old "the overnight runner can plan and execute it without further human input" framing are softened. Acceptance: `grep -c "Prepares a single backlog item for execution"` ≥ 1; `grep -c "Ready for overnight execution."` = 0.
- **Actual**: `grep -c "Prepares a single backlog item for execution"` = 1 (L19); `grep -c "Ready for overnight execution."` = 0. The old framing phrases "overnight runner can plan and execute" and "without further human input" both return 0 (fully removed). The `outputs` line (L9) reads "approved specification ready for planning" with no overnight presumption. Remaining "overnight" mentions in the file (description routing keywords L3, the L53 resume warning, the L166 area-name list, the R6 advisory block, and the L212 constraint row) are legitimate non-purpose uses or required routing tokens, not assumption assertions.
- **Verdict**: PASS
- **Notes**: Purpose and completion language are execution-agnostic; the terse phrasing matches the spec's "not 'interactive or overnight'" instruction.

### Requirement 3: Routing keywords preserved AND sibling-disambiguation unbroken
- **Expected**: refine's L1 surface still contains `refine backlog item`, `prepare for overnight`, `prepare feature for execution`, and `Clarify → Research → Spec`; `test_skill_routing_disambiguation.py` passes.
- **Actual**: all four substrings present (grep count 1 each). `.venv/bin/pytest tests/test_skill_routing_disambiguation.py -q` → 22 passed, exit 0.
- **Verdict**: PASS
- **Notes**: The generic "for execution" purpose did not broaden refine's match against `dev`/`lifecycle` enough to break the disambiguation test.

### Requirement 4: L1 ratchet honored and re-capped
- **Expected**: `test_l1_surface_ratchet.py` passes; recorded refine/total budgets equal the measured surface.
- **Actual**: `bin/cortex-measure-l1-surface` → `refine 624`, `total 7177`. `_BASELINES["refine"]` = 624, `_BASELINES["total"]` = 7177 — exact match. `.venv/bin/pytest tests/test_l1_surface_ratchet.py -q` → 20 passed, exit 0. The baseline change is a *lowering* (644→624 refine, 7197→7177 total, commit df8f2587), which the cap policy permits without a re-cap rationale (only raises require one).
- **Verdict**: PASS
- **Notes**: Recorded budgets equal the measured surface exactly.

### Requirement 5: Both regenerated mirrors committed; parity holds
- **Expected**: both `plugins/cortex-core/skills/refine/SKILL.md` and `plugins/cortex-core/skills/lifecycle/references/specify.md` regenerated and byte-identical to canonical; `test_plugin_mirror_parity.py` passes.
- **Actual**: `diff -q` reports both mirrors IDENTICAL to their canonical sources. `.venv/bin/pytest tests/test_plugin_mirror_parity.py -q` → 11 passed, exit 0. `git status` shows a clean working tree for all four canonical+mirror files (committed).
- **Verdict**: PASS
- **Notes**: Both mirrors are present and byte-identical; all feature files are committed.

### Requirement 6: Advisory overnight-candidate warning at completion, scoped to standalone `/refine`
- **Expected**: Step 6 names the mechanical anchor signals (`Interactive/session-dependent`, unresolved `## Open Decisions`), states the advisory is conditional/advisory, names the no-`phase_transition` standalone guard, and uses soft phrasing (no MUST/CRITICAL/REQUIRED). Acceptance: `grep -ci "overnight candidate"` ≥ 1.
- **Actual**: `grep -ci "overnight candidate"` = 2. Step 6 (L188–206) carries the "Overnight-candidate advisory (standalone `/refine` only)" subsection. It names the no-`phase_transition` guard with a concrete `grep -c '"event": "phase_transition"'` check (0 → assess; ≥1 → stay silent). It anchors on the two mechanical signals (`Interactive/session-dependent` criterion; unresolved `## Open Decisions`) and lists the optional judgment reasons (network/credentials, human-visual/judgment verification, exploratory/under-specified scope). It states the advisory is conditional ("surface the advisory below when warranted… When none apply, say nothing"). No MUST/CRITICAL/REQUIRED appears in the added block. The warning lives in refine's Step 6, not in `specify.md`. Behavioral surface (fire/no-fire) is recorded in implement-notes.md against four fixtures, including the load-bearing lifecycle-suppression arm (case iv), all matching expectation.
- **Verdict**: PASS
- **Notes**: Soft positive-routing phrasing ("Heads up — this looks like a poor overnight candidate because …"); structural guard encoded as a grep check rather than prose-only assertion.

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The §2 posture note follows the existing bolded-label convention in `specify.md` ("**Interview posture (interactive default)**:"), and the refine Step 6 subsection header matches the file's existing `###` sub-step style. The ratchet baseline keys are unchanged in shape.
- **Error handling**: Appropriate for the context. These are prose/skill and a test-baseline edit, not runtime code; the R6 guard fails safe toward silence (no warning) on the documented edge where a standalone re-run inherits prior lifecycle `phase_transition` rows, which the spec accepts as a minor limitation.
- **Test coverage**: Verification steps executed. R3/R4/R5 suites pass (22/20/11). Both `just test` failures are confirmed external: `test_no_order_drift_against_baseline` fails on inputs "overnight watchdog"/"WATCHDOG" drifting against the concurrent session's uncommitted `tests/fixtures/predicate_a_baseline.json` (git status confirms it is modified/uncommitted and unreferenced by any feature file); `test_plugin_path_mismatch_exits_nonzero` passed on re-run with network (the sandbox-network MCP case). Neither references a file changed by this feature. The implement-notes reasoning holds. R6's behavioral surface is model-interpreted prose and is verified by the documented manual walkthrough (four fixtures) per the spec's stated protocol — not unit-testable by design.
- **Pattern consistency**: Follows project conventions. R6 uses soft positive-routing phrasing per the MUST-escalation policy (no MUST/CRITICAL/REQUIRED). The advisory prescribes the trigger and output shape while leaving the judgment-reason evaluation to the model (prescribe What/Why not How). The standalone guard is encoded as a concrete grep check (structural-over-prose) rather than relying on the model to infer the path. The ratchet lowering is consistent with the cap-policy ratchet-down rule.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
