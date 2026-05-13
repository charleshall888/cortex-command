# Review: requirements-skill-v2

## Verdict

```json
{
  "verdict": "CHANGES_REQUESTED",
  "cycle": 1,
  "issues": [
    "Call-graph validator failure: skills/requirements/SKILL.md lines 14, 27, 28 invoke /requirements-gather and /requirements-write programmatically, but both sub-skills carry `disable-model-invocation: true` in their frontmatter. Per scripts/validate-callgraph.py's contract (the flag also blocks the Skill tool, so a flagged skill cannot be invoked programmatically by another skill), this is a structural integration bug — the orchestrator's documented routing flow cannot actually execute at runtime. tests/test_skill_callgraph.py::test_real_tree_clean fails with 3 violations naming exactly these lines. Fix options: (a) remove `disable-model-invocation: true` from skills/requirements-gather/SKILL.md and skills/requirements-write/SKILL.md (preferred — they ARE callees), (b) add `<!-- callgraph: ignore -->` markers on the orchestrator's three invocation lines (only valid if the intent is to require human-triggered re-entry rather than agent dispatch), or (c) restructure the orchestrator to inline the sub-skill protocols rather than invoking them. R20's e2e test passes only because it simulates routing in pure Python; the real runtime contract is broken."
  ],
  "requirements_drift": "none"
}
```

## Stage 1: Spec Compliance

All 21 requirements (R1–R21) have their stated acceptance checks passing. The cross-cutting issue above does not invalidate any single R-acceptance criterion individually — it surfaces from the interaction of three skills' frontmatter with a pre-existing tree-clean test that R19/R20 did not anticipate.

- **R1 (PASS)** — `skills/lifecycle/references/load-requirements.md:5–17` documents the 5-step tag-based loading protocol with the absent/empty-tags fallback explicitly stated (line 17). Greps return ≥1 for both anchor patterns.
- **R2 (PASS)** — `skills/lifecycle/references/clarify.md:33` and `skills/lifecycle/references/specify.md:9` both delegate to `references/load-requirements.md`; the phrase "names suggest relevance" is fully removed from both files.
- **R3 (PASS)** — `skills/discovery/references/clarify.md:15` and `skills/discovery/references/research.md:27` delegate to the shared reference via `../../lifecycle/references/load-requirements.md`; heuristic phrase removed.
- **R4 (PASS)** — `skills/refine/SKILL.md:68` cites the load-requirements protocol through the refine→clarify→load-requirements chain.
- **R5 (PASS)** — 6-file union grep returns 6; `skills/critical-review/SKILL.md:41` carries the verbatim anchor "Requirements loading: deliberately exempt" with full rationale.
- **R6 (PASS)** — All 43 `cortex/lifecycle/*/index.md` files (10 backfilled + 33 already compliant) carry a `tags:` field; `find ... -exec grep -L "^tags:" {} \;` returns empty.
- **R7 (PASS)** — `skills/lifecycle/references/review.md:172–188` wires the post-dispatch validation gate with max-retry=2 and `drift_protocol_breach` emission; `cortex_command/overnight/report.py:573,654,890–912` reads and surfaces breach events; `bin/.events-registry.md` registers the event with full schema.
- **R8 (PASS)** — Commit 64e6f7eb adds `## Suggested Requirements Update` sections to 9 historical reviews; the post-Phase-2 grep for detected-drift artifacts missing the section returns 0 (better than the ≤1 soft target).
- **R9 (PASS)** — `bin/cortex-requirements-parity-audit` is executable, `--help` exits 0, `just requirements-parity-audit` recipe is listed. Live invocation produces a well-formed JSON report (audited=145, applied=20, not_applied=[]).
- **R10 (PASS)** — `cortex/requirements/project.md` measures exactly 1200 cl100k_base tokens (at the cap). All required H2 sections (Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading) are present.
- **R11 (PASS)** — `## Optional` H2 present (line 69) with first non-heading line "Content here is prunable under token pressure — skip without losing spec-required guidance" matching the prunability anchor.
- **R12 (PASS)** — `verify-conditional-loading.py` exits 0; all 4 area-doc stems (`multi-agent`, `observability`, `pipeline`, `remote-access`) appear in the Conditional Loading section.
- **R13 (PASS)** — `cortex/lifecycle/requirements-skill-v2/area-audit.md` contains 12 spot-checks (3 per area doc), 11 ✓ and 1 ✗ on `observability.md:63`. The ✗ is patched in Task 19 (commit 442049ab).
- **R14 (PASS)** — `cortex/requirements/project.md:45` reads "Discovery and backlog are documented inline (no area docs): `skills/discovery/SKILL.md`, `cortex/backlog/index.md`." Both inline-doc grep patterns match; neither `discovery.md` nor `backlog.md` was created.
- **R15 (PASS)** — `skills/requirements-gather/SKILL.md` is 73 lines (≤80). All three mattpocock anchors present: "recommend-before-asking" / "Recommended answer:" (5 matches), "codebase trumps interview" / "explore code instead" (5 matches), "lazy" / "only write when" (3 matches).
- **R16 (PASS)** — `skills/requirements-write/SKILL.md` is 49 lines (≤50). Both `project.md` and `area.md` scopes addressed (4 matches).
- **R17 (PASS, with caveat)** — `skills/requirements/SKILL.md` is 29 lines (≤30) and references both sub-skills. Caveat: the orchestrator invokes the sub-skills programmatically while they declare `disable-model-invocation: true` — see Verdict issue.
- **R18 (PASS)** — `skills/requirements/references/gather.md` is absent; recursive grep for `references/gather.md` or `requirements/references/gather` in active source (excluding the documented archive/research/backlog/test paths) returns no matches.
- **R19 (PASS)** — 29 + 73 + 49 = 151 lines (≤160 cap, 9-line headroom vs v1's 348-line baseline).
- **R20 (PASS, by simulation)** — `tests/test_requirements_skill_e2e.py` passes 11/11 tests. Simulation-based; the test mocks dispatch and proves the structural citation chain plus the area-template H2 spine is intact. Does not exercise the live `disable-model-invocation` interaction surfaced as the Verdict issue.
- **R21 (PASS)** — `plugins/cortex-core/skills/requirements-gather` and `plugins/cortex-core/skills/requirements-write` exist; `bin/cortex-check-parity` exits 0.

## Stage 2: Code Quality

Run because no requirement is FAIL. The implementation overall is clean and well-structured; the single integration bug surfaced in the Verdict is a frontmatter-vs-prose contradiction, not a code-quality defect.

- **Naming conventions**: Consistent with project patterns. Sub-skill names (`requirements-gather`, `requirements-write`) follow the kebab-case skill-name convention. The new event `drift_protocol_breach` follows the snake_case event-name convention already in `bin/.events-registry.md`. The shared reference `load-requirements.md` follows the `references/<topic>.md` convention.
- **Error handling**: The new `cortex-requirements-parity-audit` script handles missing git history, pre-#013 reviews, and unparseable sections by skipping silently and emitting structured JSON; documented in the Contract block. `remediate-historical-drift.py` supports `--dry-run` and handles per-file failures by logging and continuing. `verify-conditional-loading.py` exits non-zero on mismatch with a diff report. All of these match the appropriate failure mode for their context (informational vs gating).
- **Test coverage**: All four new test files pass.
  - `tests/test_load_requirements_protocol.py` — 9 tests covering the structural citation chain across the 6 consumers, the critical-review exemption, the 5-step protocol enumeration, and 5 protocol-simulation scenarios (tagged index, empty tags, absent tags, unmatched tag, multi-tag-one-match).
  - `tests/test_drift_enforcement_protocol.py` — 7 tests covering review.md anchors plus 6 behavioral simulations (re-dispatch fires/skips, retry caps at 2, breach event emitted on exhaustion, not emitted on late success, payload shape).
  - `tests/test_requirements_parity_audit.py` — 7 tests covering --help exit code, output schema, pre-#013 silent skip, applied counting, not-applied listing, entry schema, audited count completeness.
  - `tests/test_requirements_skill_e2e.py` — 11 tests covering structural contract verification (file presence, cross-skill references, output path, argument shape, Q&A output shape, area template H2 spine, both scopes) plus 4 e2e simulations (orchestrator routes area→gather→write, fails when sections drop, fails when path misroutes, list short-circuits).
- **Pattern consistency**: Follows existing project conventions. `cortex-requirements-parity-audit` registers via the `just` recipe (per the bin-script parity gate); the new event registers in `.events-registry.md` (per the events-registry constraint); the new sub-skills auto-mirror to `plugins/cortex-core/skills/` (per the dual-source enforcement). The orchestrator pattern (thin SKILL.md routing to sub-skills) follows the `/cortex-core:dev` precedent.

The single defect found is the call-graph validator failure described in the Verdict, which is structural rather than stylistic and warrants CHANGES_REQUESTED.

## Additional finding (informational)

`tests/test_lifecycle_references_resolve.py::test_every_lifecycle_reference_resolves` fails on prose in `cortex/lifecycle/requirements-skill-v2/research.md:171` and `:212` — the literal strings "lifecycle/discovery/pipeline" and "lifecycle/discovery/refine" appear in body prose and the regex matcher reads them as slash-path lifecycle citations against the non-existent slug `discovery`. Strictly out-of-scope for this review per the in-scope rule ("All files listed in plan.md's Task 1-28+8b Files fields"; research.md is not listed in any task's Files field — it predates plan.md by ~12 hours and was committed in 7032b1eb). Noting for visibility but not gating the verdict; cleaning up the prose to use backticks or a non-slash separator (e.g. `lifecycle/discovery/refine` → `lifecycle, discovery, and refine`) would also restore that test.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None
