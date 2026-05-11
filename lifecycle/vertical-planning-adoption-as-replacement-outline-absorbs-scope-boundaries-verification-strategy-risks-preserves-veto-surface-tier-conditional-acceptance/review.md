# Review: vertical-planning-adoption-as-replacement-outline-absorbs-scope-boundaries-verification-strategy-risks-preserves-veto-surface-tier-conditional-acceptance

## Stage 1: Spec Compliance

### Requirement R1: `## Outline` section in plan.md template
- **Expected**: `## Outline` ABOVE `## Tasks` with `### Phase N: <name> (tasks: ...)` H3 headings, each with `**Goal**` and `**Checkpoint**` fields; ≥1 phase tolerance for simple, ≥2 for complex.
- **Actual**: `skills/lifecycle/references/plan.md:149` adds `## Outline`; H3 examples `### Phase 1:` (line 152) and `### Phase 2:` (line 156) each include `**Goal**` and `**Checkpoint**` fields; HTML comment at line 150 documents the ≥1/≥2 tolerance rule.
- **Verdict**: PASS
- **Notes**: Acceptance greps (Outline header + H3 phase headings) match.

### Requirement R2: `## Risks` section (rename from `## Veto Surface`)
- **Expected**: Rename `## Veto Surface` → `## Risks`; add retro-anchor prose; update dispatch.py:271 and test_dispatch.py:943 docstrings; no `Veto Surface` in canonical template or mirror.
- **Actual**: `plan.md:182` has `## Risks`; retro-anchor prose at line 137 and HTML-comment form at line 184; `grep -n "Veto Surface" cortex_command/pipeline/dispatch.py cortex_command/pipeline/tests/test_dispatch.py` returns nothing; `grep "^## Veto Surface$"` on canonical + mirror returns nothing.
- **Verdict**: PASS

### Requirement R3: Tier-conditional `## Acceptance` section
- **Expected**: Top-level `## Acceptance` section populated only when `complexity=complex`; explicit `complexity=complex` token in template prose.
- **Actual**: `plan.md:186-188` adds `## Acceptance` with HTML-comment instruction "Populate ONLY when `complexity=complex` (the Clarify §4-resolved tier dimension). Omit this section entirely on `complexity=simple` plans."
- **Verdict**: PASS

### Requirement R4: DELETE `## Scope Boundaries` from plan.md template
- **Expected**: Hard delete from canonical and mirror.
- **Actual**: `grep "^## Scope Boundaries$"` returns nothing for both canonical and plugin mirror.
- **Verdict**: PASS

### Requirement R5: DELETE `## Verification Strategy` from plan.md template
- **Expected**: Hard delete from canonical and mirror.
- **Actual**: `grep "^## Verification Strategy$"` returns nothing for both canonical and plugin mirror.
- **Verdict**: PASS

### Requirement R6: Provenance disclosure note in plan.md §3
- **Expected**: Prose paragraph above `## Outline` covering CRISPY/QRSPI, community-derived, practitioner-grade evidence, human-skim primary justification, and explicit non-quoting of the "more reliable than any prompt instruction" superlative; not propagated into authored plans.
- **Actual**: `plan.md:135` contains the prose paragraph with all four elements (CRISPY/QRSPI v2 HumanLayer, community-derived, practitioner-grade 1/5, human-skim, explicit non-quote of the superlative).
- **Verdict**: PASS

### Requirement R7: `## Phases` section + per-requirement Phase tags in spec.md
- **Expected**: `## Phases` section after `## Problem Statement`; per-requirement `**Phase**:` tag inline.
- **Actual**: `specify.md:118` has `## Phases` and `:124-125` show example requirements with inline `**Phase**:` tags.
- **Verdict**: PASS

### Requirement R8: Orchestrator-review gate P9 (plan outline)
- **Expected**: P9 row with Outline/Goal/Checkpoint criteria, soft positive-routing phrasing (no MUST/CRITICAL/REQUIRED).
- **Actual**: `orchestrator-review.md:167` row P9 contains `## Outline`, `**Goal**`, `**Checkpoint**`. No MUST/CRITICAL/REQUIRED in P9.
- **Verdict**: PASS

### Requirement R9: Orchestrator-review gate S7 (spec phases)
- **Expected**: S7 row with `## Phases` and `**Phase**` tag criteria; soft phrasing.
- **Actual**: `orchestrator-review.md:151` row S7 references `## Phases` section and `**Phase**` tag. No MUST/CRITICAL/REQUIRED in S7.
- **Verdict**: PASS

### Requirement R10: Orchestrator-review gate P10 (complex Acceptance)
- **Expected**: P10 row gated on `complexity=complex`, references `## Acceptance` section; soft phrasing; no `criticality=critical` regression.
- **Actual**: `orchestrator-review.md:168` row P10 contains `complexity=complex` and references `## Acceptance`; `awk` confirms no MUST/CRITICAL/REQUIRED across P9/P10/S7; no `criticality=critical` in P10 row.
- **Verdict**: PASS

### Requirement R11: `metrics.py:221` alias-lookup hardening
- **Expected**: Module-level `_VERDICT_FIELD_ALIASES = ("verdict", "review_verdict", "decision")`; helper `_extract_verdict()` iterating the tuple and returning first present value or None.
- **Actual**: `metrics.py:140` defines `_VERDICT_FIELD_ALIASES: tuple[str, ...] = ("verdict", "review_verdict", "decision")`; `_extract_verdict()` at line 143 iterates aliases and returns the first present value or None; line 249 uses it via generator expression filtering None.
- **Verdict**: PASS

### Requirement R12: Plan parser regression test
- **Expected**: Three test methods covering (a) Outline above Tasks parses cleanly, (b) H3 Phase headings do not truncate task bodies, (c) `## SomeOther` H2 truncates prior task body (lock-in of current H2-anchor behavior).
- **Actual**: `test_parser.py:353` adds `TestOutlineSectionAndH3PhasesRegression` class with all three tests. Tests pass (verified via `pytest`).
- **Verdict**: PASS

### Requirement R13: `report.py` tier-conditional verification reader
- **Expected**: `_read_tier`, `_read_acceptance`, `_read_last_phase_checkpoint` helpers; tier-conditional fallback chain in `_render_feature_block`; default-tier policy of "simple" on missing/malformed events; walk-backward Checkpoint logic; HYBRID-plan new-shape-wins precedence; nine-fixture integration test.
- **Actual**: `report.py:746-778` implements `_read_tier` with the documented event scan and "simple" default; `_read_acceptance` (line 781) uses the section-regex pattern; `_read_last_phase_checkpoint` (line 798) parses Outline, splits by `### Phase N:`, walks reversed phase blocks. The branch at `report.py:535-546` matches the spec: complex → acceptance → last-phase-checkpoint → legacy; simple → last-phase-checkpoint → legacy. Fallback chain naturally produces HYBRID new-shape-wins behavior.
- **Verdict**: PASS

### Requirement R14: Plugin-mirror parity test
- **Expected**: New pytest comparing canonical files to plugin mirrors byte-for-byte; identifies drifted file on failure.
- **Actual**: `tests/test_plugin_mirror_parity.py` parametrizes on the three filenames, reads bytes from canonical and mirror, asserts equality with a clear drift message; tests pass.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Underscore-prefixed private helpers (`_read_tier`, `_read_acceptance`, `_read_last_phase_checkpoint`, `_extract_verdict`) match the surrounding module patterns in both `report.py` and `metrics.py`. Constant naming (`_VERDICT_FIELD_ALIASES`) follows the existing module-constant convention.
- **Error handling**: `_read_tier` wraps `read_events` in `try/except Exception` per the spec's malformed-log fallback; missing files return "simple" early. `_read_acceptance` / `_read_last_phase_checkpoint` return empty strings on missing-file and no-match, enabling the documented fallback chain. `_extract_verdict` returns `None` on no-alias which feeds the existing `if v is not None` filter at the call site.
- **Test coverage**: All four verification surfaces (parser, metrics, report, parity) pass under pytest — 88 passed + 1 xpassed. Report tests cover all ten documented fixtures plus the T-A / T-B key-name assertion tests for `_read_tier`. Metrics tests cover the four R11 cases (canonical, alias-only, missing, multi-alias precedence). Parser tests cover the three R12 cases.
- **Pattern consistency**: Section-reader regex matches the existing `_read_verification_strategy` pattern (`r"^## SectionName\s*\n(.*?)(?=\n## |\Z)"`). Tier extraction uses `read_events` (the canonical events.log reader) and mirrors the `tier`-extraction style from `metrics.py:222-223`. Template restructure preserves the §3 fenced code-block convention.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
