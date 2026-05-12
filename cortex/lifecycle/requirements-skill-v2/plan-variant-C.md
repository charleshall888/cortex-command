# Plan: requirements-skill-v2

## Overview
**Architectural Pattern**: shared-state
This `shared-state` variant organizes work around the load-bearing primitives multiple components read/write (the shared loading reference, the `tags:` field, the Conditional Loading section, the events.log schema, the review.md drift fields, the parent project.md surface, the 4 area docs, and the `/requirements` skill surface) and lands each group's "writers" before its "readers," in contrast to the `pipeline` variant (which sequences by phase A→E→B→D→C and treats each phase as an independent stage) and the `layered` variant (which stratifies by abstraction tier — primitives below, consumers above, gates on top).

PR cadence recommendation: one PR per shared-primitive group (8 PRs total). Groups 1-2 may be combined into a single PR (R1 and R6 both establish loading inputs without consuming each other). Groups 3-4 must ship sequentially (Group 4 depends on Group 3's primitives being written). Groups 5-8 are independent of each other and may ship in parallel branches once Groups 1-4 land.

## Outline

### Phase 1: Consumer navigability (tasks: 1, 2, 3, 4, 5, 6, 7, 8, 9)
**Goal**: Establish the shared `load-requirements.md` primitive and the `tags:` field corpus; wire all 6 non-exempt consumers to read against them.
**Checkpoint**: Phase 1 acceptance rollup (Task 9) passes all R1-R6 grep assertions.

### Phase 2: Drift tightening (tasks: 10, 11, 12, 13, 14, 15)
**Goal**: Register `drift_protocol_breach`, enforce Suggested Update section + max-retry=2, surface breaches in morning report, remediate the 8 historical artifacts, ship the parity-audit script.
**Checkpoint**: All R7-R9 acceptance assertions pass.

### Phase 3: Parent trim + Optional partition (tasks: 16, 17, 18, 19, 20)
**Goal**: Trim parent project.md ≤1,200 cl100k_base tokens, add `## Optional` partition, clarify discovery/backlog in Project Boundaries, verify Conditional Loading intersects real tag corpus.
**Checkpoint**: All R10-R12, R14 acceptance assertions pass.

### Phase 4: Area-doc audit + patch (tasks: 21, 22, 23)
**Goal**: ≥12 spot-checks across 4 area docs; patch any drift in place; record verdicts in audit memo.
**Checkpoint**: All R13 acceptance assertions pass.

### Phase 5: Skill split + brevity (tasks: 24, 25, 26, 27, 28, 29, 30, 31)
**Goal**: Stand up `/requirements-gather` + `/requirements-write`, thin `/requirements` orchestrator, retire `references/gather.md`, hit ≤160-line budget, ship E2E test, confirm plugin-mirror auto-regeneration.
**Checkpoint**: All R15-R21 acceptance assertions pass.

## Tasks

---

### Group A — Shared primitive: `skills/lifecycle/references/load-requirements.md` (the shared loader reference)

This primitive is **created** by Task 1 and **consumed** by Tasks 2-5 (the six consumer skills). All writer tasks land before reader tasks.

### Task 1: Create shared `load-requirements.md` reference (writer for primitive A)
- **Files**: `skills/lifecycle/references/load-requirements.md` (new)
- **What**: Author the shared loader reference describing the five-step tag-based Conditional Loading protocol: (a) always read `cortex/requirements/project.md`; (b) read consumer's lifecycle `index.md` and extract `tags:` array; (c) case-insensitively match each tag word against Conditional Loading phrases in `project.md`; (d) load matched area docs with match rationale; (e) fallback when `tags:` is missing or `[]` — load `project.md` only, no error, proceed silently. Section headings: `## Protocol`, `## Fallback Behavior`, `## Output Contract`. Source content is extracted from `skills/lifecycle/references/review.md` lines 12-16 plus the fallback semantics specified in R1 Edge Cases.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R1. Reference path is canonical at `skills/lifecycle/references/` (cross-skill shared references live in `lifecycle/references/` by convention; discovery and refine reference back into this path). Reference must include the literal phrase `Conditional Loading` (≥1 occurrence) and explicit fallback language matching the regex `tags.*empty|tags.*absent|no tags`. Soft positive-routing phrasing only — no new MUST/CRITICAL escalations.
- **Verification**: `test -f skills/lifecycle/references/load-requirements.md` AND `grep -c "Conditional Loading" skills/lifecycle/references/load-requirements.md` ≥1 AND `grep -ciE 'tags.*empty|tags.*absent|no tags' skills/lifecycle/references/load-requirements.md` ≥1.
- **Status**: [ ] pending

### Task 2: Wire lifecycle clarify + specify to shared loader (reader of primitive A)
- **Files**: `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/specify.md`
- **What**: Edit clarify.md §2 and specify.md §1 (per research §1.3 Step 4 reference) to load requirements via the shared reference from Task 1. Remove the existing "scan for area docs whose names suggest relevance" heuristic prose entirely. Replace with a reference link to `load-requirements.md` and a one-line summary of the contract (tag-based loading).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Spec R2. Acceptance pattern is `grep -l "load-requirements.md\|tag-based.*loading"` matches both files AND `grep -c "names suggest relevance"` returns 0 across both files. Both files must continue to declare their own protocol section ordering; the loader reference is invoked, not inlined.
- **Verification**: `grep -l "load-requirements.md\|tag-based.*loading" skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md | wc -l` returns 2 AND `grep -c "names suggest relevance" skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md` returns 0.
- **Status**: [ ] pending

### Task 3: Wire discovery clarify + research to shared loader (reader of primitive A)
- **Files**: `skills/discovery/references/clarify.md`, `skills/discovery/references/research.md`
- **What**: Edit both discovery reference files to load requirements via the shared reference. Replace heuristic name-matching prose with the loader reference link. Preserve discovery-specific gating behavior (discovery clarify still gates on aim alignment; only the requirements-loading prelude changes).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Spec R3. Discovery's reference docs sit under `skills/discovery/references/`; the cross-skill reference path uses `../../lifecycle/references/load-requirements.md` relative or repo-absolute citation. Acceptance unchanged from R3 grep patterns.
- **Verification**: `grep -l "load-requirements.md\|tag-based.*loading" skills/discovery/references/clarify.md skills/discovery/references/research.md | wc -l` returns 2 AND `grep -c "names suggest relevance" skills/discovery/references/clarify.md skills/discovery/references/research.md` returns 0.
- **Status**: [ ] pending

### Task 4: Wire refine to shared loader (reader of primitive A)
- **Files**: `skills/refine/SKILL.md`
- **What**: Edit refine SKILL.md Step 3 (Clarify Phase) so that when delegating to `references/clarify.md`, it explicitly invokes the shared loader. Refine wraps lifecycle clarify; the invocation path is via the delegated reference, but a top-level mention in SKILL.md ensures the path is discoverable.
- **Depends on**: [1, 2]
- **Complexity**: trivial
- **Context**: Spec R4. The dependency on Task 2 is structural: refine delegates to `lifecycle/references/clarify.md`, so the reference must already be wired before refine claims tag-based loading. Acceptance: `grep -c "load-requirements.md\|tag-based.*loading" skills/refine/SKILL.md` ≥1.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/refine/SKILL.md` returns ≥1.
- **Status**: [ ] pending

### Task 5: Document critical-review exemption (reader-exempt of primitive A)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add an explicit prose note in critical-review's SKILL.md stating that it intentionally does NOT use the shared tag-based loader because it narrows context to parent Overview only (research §1.3 documents the existing pattern). The exemption is documented to prevent future "navigability=6/7 should be 7/7" audits from misreading the gap as a bug.
- **Depends on**: [1]
- **Complexity**: trivial
- **Context**: Spec R5. Acceptance: `grep -ciE 'requirements.*exempt|narrow.*overview|tag-based.*loading.*not' skills/critical-review/SKILL.md` ≥1. This is a documentation-only change; no behavior shift.
- **Verification**: `grep -ciE 'requirements.*exempt|narrow.*overview|tag-based.*loading.*not' skills/critical-review/SKILL.md` returns ≥1.
- **Status**: [ ] pending

### Task 6: Navigability rollup verification across all 6 consumers (reader-set integrity check for primitive A)
- **Files**: none (verification only)
- **What**: Run the R5 rollup grep against all six non-exempt consumer files to confirm the shared loader is referenced by exactly 6 files and the critical-review exemption is documented. This task is a verification-only checkpoint, not a code change; it gates Phase 1 PR.
- **Depends on**: [2, 3, 4, 5]
- **Complexity**: trivial
- **Context**: Spec R5 explicitly defines this as a rollup acceptance criterion separate from the per-file checks.
- **Verification**: `grep -l 'load-requirements.md\|tag-based.*loading' skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md skills/lifecycle/references/review.md skills/discovery/references/clarify.md skills/discovery/references/research.md skills/refine/SKILL.md | wc -l` returns 6 AND `grep -ciE 'requirements.*exempt|narrow.*overview|tag-based.*loading.*not' skills/critical-review/SKILL.md` returns ≥1.
- **Status**: [ ] pending

---

### Group B — Shared primitive: the `tags:` field in lifecycle index.md files

This primitive is **backfilled** by Task 7 and **read** by Tasks 2-5's loader contract at runtime. Tasks 7-9 group all `tags:` writes (existing files) before Phase 3's reader (Task 19's verification script depends on real tags).

### Task 7: Backfill `tags:` into existing index.md files (writer for primitive B)
- **Files**: 10 existing `cortex/lifecycle/*/index.md` files (the subset where `tags:` is currently absent)
- **What**: Enumerate every `cortex/lifecycle/*/index.md` that lacks a `tags:` frontmatter field; for each, derive tags from the parent backlog item's `tags:` frontmatter when `parent_backlog_id` is non-null; otherwise insert `tags: []` with an inline comment that fallback loading applies. Use the same YAML frontmatter conventions present in active index.md files (preserve key order, indentation).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R6. The 10 affected files are identifiable via `find cortex/lifecycle -maxdepth 2 -name index.md -exec grep -L "^tags:" {} \;`. Parent backlog discovery: read `parent_backlog_id` from each index.md's frontmatter, locate the corresponding `cortex/backlog/<id>-*.md`, copy its `tags:` array. Lifecycles with `parent_backlog_id: null` get `tags: []`.
- **Verification**: `find cortex/lifecycle -maxdepth 2 -name index.md -exec grep -L "^tags:" {} \;` returns no files (all 41 index.md files have `tags:` present, possibly `[]`).
- **Status**: [ ] pending

### Task 8: Verify backfill integrity against parent backlog tags
- **Files**: none (verification only)
- **What**: For each index.md updated in Task 7 with a non-null `parent_backlog_id`, confirm the inserted tag array matches (is a subset of, or equal to) the parent backlog item's tags. Spot-check ≥3 backfilled files manually to confirm no drift between backlog and lifecycle tag values.
- **Depends on**: [7]
- **Complexity**: trivial
- **Context**: Sanity check on Task 7's mechanical extraction; protects against silent tag-array corruption.
- **Verification**: Spot-check ≥3 backfilled `cortex/lifecycle/*/index.md` files; compare `tags:` against parent `cortex/backlog/*.md` `tags:`; no discrepancies.
- **Status**: [ ] pending

### Task 9: Confirm Phase 1 acceptance rollup (Groups A+B combined)
- **Files**: none (verification only)
- **What**: Run all Phase 1 acceptance checks (R1, R2, R3, R4, R5, R6) as a combined gate before opening the Phase 1 PR. This task exists as the explicit Phase 1 boundary; subsequent phases must not start until this gate passes.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8]
- **Complexity**: trivial
- **Context**: Phase 1 ships as a single PR (or two-PR group A+B). The combined verification confirms all phase-1 acceptance criteria pass.
- **Verification**: All R1-R6 acceptance grep patterns from spec return their required values.
- **Status**: [ ] pending

---

### Group C — Shared primitive: the events.log schema (`drift_protocol_breach` event)

This primitive is **declared** by Task 10 (events-registry), **emitted** by Task 11 (review.md), **consumed** by Task 12 (report.py). All writer/declarer tasks precede consumer tasks.

### Task 10: Register `drift_protocol_breach` event in events registry (writer for primitive C)
- **Files**: `bin/.events-registry.md`
- **What**: Add a new event-type entry for `drift_protocol_breach` documenting: event name, fields (lifecycle slug, retry count, dispatch timestamp), emission site (`review.md` post-dispatch validation gate), consumer (morning report). Follow the existing registry entry shape exactly — see other entries for required columns.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: Spec R7. The events registry is the canonical declaration site for any new event type per cortex's events-discipline (referenced in Technical Constraints). Registration must precede first emission for parity gates to pass.
- **Verification**: `grep -c "drift_protocol_breach" bin/.events-registry.md` returns ≥1.
- **Status**: [ ] pending

### Task 11: Implement post-dispatch enforcement + emit `drift_protocol_breach` (writer/emitter for primitive C and primitive D)
- **Files**: `skills/lifecycle/references/review.md`
- **What**: Modify review.md §4 (post-dispatch validation) so that when `requirements_drift: detected` is emitted but the `## Suggested Requirements Update` section is absent, the gate re-dispatches the reviewer. Max-retry is 2; on the third pass, log a `drift_protocol_breach` event to events.log with state=detected, suggestion=missing, and fall through (do not block the lifecycle). Document the retry policy and the breach event inline in review.md prose. Soft positive-routing only — no new MUST language; enforcement is structural (the gate re-dispatches), not prose imperative.
- **Depends on**: [10]
- **Complexity**: complex
- **Context**: Spec R7. Acceptance covers four greps: `Suggested Requirements Update` count increases ≥1 over baseline, `max[-_ ]retry.*2|retry.*max.*2` ≥1, `drift_protocol_breach` ≥1, all in review.md. This task also writes to primitive D's read surface (`requirements_drift` field) by referencing its enforcement; Group D consumes the same field.
- **Verification**: `grep -c "Suggested Requirements Update" skills/lifecycle/references/review.md` increases ≥1 vs baseline AND `grep -c "max[-_ ]retry.*2\|retry.*max.*2" skills/lifecycle/references/review.md` ≥1 AND `grep -c "drift_protocol_breach" skills/lifecycle/references/review.md` ≥1.
- **Status**: [ ] pending

### Task 12: Surface `drift_protocol_breach` in morning report (reader for primitive C)
- **Files**: `cortex_command/overnight/report.py`
- **What**: Extend report.py session-header summary to include `drift_protocol_breach` event lines from events.log. The surfacing logic reads events.log for the session window, filters for `drift_protocol_breach`, and renders a one-line entry per breach in the morning report header (lifecycle slug + retry count). Existing `_read_requirements_drift()` path (report.py:559,635) is not modified; this is an additive event-surface.
- **Depends on**: [10, 11]
- **Complexity**: simple
- **Context**: Spec R7 acceptance: `grep -c "drift_protocol_breach" cortex_command/overnight/report.py` ≥1. Behavior change documented in Changes to Existing Behavior. The dependency on Task 11 is logical (the emitter must exist first); not strictly mechanical (report.py can compile without an actual emission).
- **Verification**: `grep -c "drift_protocol_breach" cortex_command/overnight/report.py` returns ≥1; manual run of report against a synthetic events.log containing a `drift_protocol_breach` event surfaces it in the session header.
- **Status**: [ ] pending

---

### Group D — Shared primitive: `requirements_drift` field + `## Suggested Requirements Update` section in review.md artifacts

This primitive is **read for enforcement** by Task 11 (already done in Group C), **remediated historically** by Tasks 13-14, and **audited longitudinally** by Task 15.

### Task 13: Build the one-shot historical remediation script (writer for primitive D, historical-only)
- **Files**: `cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py` (new)
- **What**: Write a one-shot Python script that (a) enumerates `cortex/lifecycle/*/review.md` and `cortex/lifecycle/archive/*/review.md` files where `requirements_drift: detected` (or `"detected"`) is present but `## Suggested Requirements Update` section is absent — the 8 historical artifacts identified in research §2; (b) dispatches a Claude Agent SDK reviewer agent per file to author the missing suggestion section; (c) writes the result back to the lifecycle dir; (d) logs per-artifact outcome (success/failure) to stdout. The script lives in the lifecycle dir as documentation of what was done; it is not installed in `bin/` and not wired to the overnight runner.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec R8. The script is a one-shot, not long-running infrastructure (Non-Requirements explicitly excludes a permanent backfill pass). Operator runs it once during Phase 2 implementation; per Technical Constraints, it runs as an interactive session-time operation, not an overnight pass. Failure on any individual artifact logs and continues to the next.
- **Verification**: Script file exists, is executable, passes a dry-run on a synthetic fixture (one fake `detected`-without-suggestion review.md file).
- **Status**: [ ] pending

### Task 14: Execute one-shot remediation against the 8 historical artifacts (writer for primitive D, historical-only)
- **Files**: up to 8 `cortex/lifecycle/{archive,}/*/review.md` files (modifications)
- **What**: Run the Task 13 script against the 8 historical artifacts; commit the resulting `## Suggested Requirements Update` additions. Operator oversees the script during the run. Acceptance allows ≤1 unfixed (≥7/8 remediated).
- **Depends on**: [13]
- **Complexity**: simple
- **Context**: Spec R8 acceptance: after Phase 2 completes, `grep -L "## Suggested Requirements Update" $(grep -rln 'requirements_drift: "detected"\|requirements_drift: detected' cortex/lifecycle/ cortex/lifecycle/archive/ --include=review.md)` returns ≤1.
- **Verification**: Acceptance grep above returns ≤1 (≥7/8 fixed).
- **Status**: [ ] pending

### Task 15: Build the parity-audit script (reader for primitive D, longitudinal)
- **Files**: `bin/cortex-requirements-parity-audit` (new), `justfile` (add recipe)
- **What**: Add an executable Python (or shell) script under `bin/` that scans all `cortex/lifecycle/*/review.md` and `cortex/lifecycle/archive/*/review.md` files since #013 shipped (2026-04-03), counts (a) detected-drift artifacts and (b) actual requirements doc changes that materialized those suggestions (heuristic: scan git log of `cortex/requirements/*.md` for commits referencing each detected-drift artifact's lifecycle slug). Emits a JSON report listing drift suggestions logged but not applied. Add a `just requirements-parity-audit` recipe to invoke it. Pre-#013 reviews without the `requirements_drift` field are skipped silently. Script supports `--help` and exits 0 on help.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec R9 (Should-have). Per Technical Constraints, the bin-script parity gate requires the script reference an in-scope artifact (the justfile recipe satisfies this). The audit is informational, not blocking — it surfaces gaps for operator triage.
- **Verification**: `test -x bin/cortex-requirements-parity-audit` AND `bin/cortex-requirements-parity-audit --help` exits 0 AND `just --list 2>&1 | grep -c requirements-parity` ≥1.
- **Status**: [ ] pending

---

### Group E — Shared primitive: parent `cortex/requirements/project.md` content surface

This primitive's content is **trimmed** by Task 16, **partitioned** by Task 17 (Optional H2), **clarified** by Task 18 (Project Boundaries), and **verified** by Task 19 (Conditional Loading intersection). Tasks 16-18 must land before Task 19's intersection check.

### Task 16: Trim parent project.md to ≤1,200 tokens (writer for primitive E)
- **Files**: `cortex/requirements/project.md`
- **What**: Reduce project.md token count to ≤1,200 (cl100k_base) while preserving all required sections (Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading). Surfaces beyond the budget are relocated, not deleted — they move into the new `## Optional` section created in Task 17. The current count is ~1,785 tokens; the trim is ~32%. Before trimming, audit every section reference from skills/hooks (per Edge Case "Parent doc trim removes a section another consumer prose references by name") and exempt any section referenced by name. If `tiktoken` is not yet a dependency, add it to `pyproject.toml`.
- **Depends on**: [17]
- **Complexity**: complex
- **Context**: Spec R10. Acceptance is tiktoken-verified: `python3 -c "import tiktoken, pathlib; enc = tiktoken.get_encoding('cl100k_base'); n = len(enc.encode(pathlib.Path('cortex/requirements/project.md').read_text())); print(n); assert n <= 1200"` exits 0. R10 is not a commit-time enforcement gate (Non-Requirements explicitly excludes that); audit-time only. Note the structural dependency on Task 17: the `## Optional` partition must exist before Task 16 can move content into it.
- **Verification**: tiktoken assertion above passes.
- **Status**: [ ] pending

### Task 17: Introduce `## Optional` partition (writer for primitive E)
- **Files**: `cortex/requirements/project.md`
- **What**: Add a new `## Optional` H2 section in project.md (placed after the existing required sections, before any trailing matter). The section's first non-heading line states the prunability convention (e.g., "Content in this section is prunable under token pressure" or equivalent — must contain one of: `prunable`, `optional`, `deferrable`). The section starts empty (or with a short prose explainer); Task 16 populates it with relocated content.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R11. Pattern reference: llms.txt's `## Optional` partition convention (research §3, §6).
- **Verification**: `grep -c "^## Optional$" cortex/requirements/project.md` returns 1 AND `sed -n '/^## Optional$/,/^## /p' cortex/requirements/project.md | head -3 | grep -ciE 'prunable|optional|deferrable'` returns ≥1.
- **Status**: [ ] pending

### Task 18: Clarify Project Boundaries (discovery/backlog inline-documented status) (writer for primitive E)
- **Files**: `cortex/requirements/project.md`
- **What**: Edit the Project Boundaries (In Scope) section to explicitly state that discovery and backlog subsystems are documented inline (in their respective SKILL.md and backlog index) rather than via dedicated area docs. The clarification resolves the scope-documentation gap identified in research §1.2 without creating new area docs. Verification: no new `cortex/requirements/discovery.md` or `cortex/requirements/backlog.md` files are created.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R14. Non-Requirements explicitly excludes creating new area docs. Acceptance: `grep -ciE "discovery.*documented inline|discovery.*inline.*document|inline.*discovery" cortex/requirements/project.md` ≥1 AND `grep -ciE "backlog.*documented inline|backlog.*inline.*document|inline.*backlog" cortex/requirements/project.md` ≥1 AND `test ! -f cortex/requirements/discovery.md && test ! -f cortex/requirements/backlog.md`.
- **Verification**: All three acceptance assertions above pass.
- **Status**: [ ] pending

---

### Group F — Shared primitive: `## Conditional Loading` section in project.md (intersected with real tags from primitive B)

This group is structurally distinct from Group E even though both edit project.md: Group F's reader integrity check **intersects** the Conditional Loading triggers with the real tag set from index.md files (primitive B). It depends on Group B (Task 7) for tag data.

### Task 19: Build and run Conditional Loading intersection verifier (reader for primitives B and E)
- **Files**: `cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py` (new)
- **What**: Write a verification script that (a) reads `tags:` arrays from all active (non-archived) `cortex/lifecycle/*/index.md` files; (b) extracts the union of unique tag words; (c) reads the `## Conditional Loading` section of `cortex/requirements/project.md` and extracts each area doc's trigger phrase; (d) asserts each Conditional Loading entry has ≥1 intersection with the real tag set, case-insensitively. Exits 0 on success, non-zero on any miss. Run the script as part of Phase 3 acceptance.
- **Depends on**: [7, 16, 17, 18]
- **Complexity**: simple
- **Context**: Spec R12. The dependency on Task 7 (tag backfill) is load-bearing: pre-backfill, the intersection check would fail because the 10 backfilled lifecycles' tags would be missing. The dependency on Tasks 16-18 ensures the project.md Conditional Loading section is in its final v2 shape before intersection.
- **Verification**: `sed -n '/^## Conditional Loading$/,/^## /p' cortex/requirements/project.md | grep -c "multi-agent\|observability\|pipeline\|remote-access"` returns ≥4 (each area-doc stem appears at least once) AND `python3 cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py` exits 0.
- **Status**: [ ] pending

### Task 20: Confirm Phase 3 acceptance rollup
- **Files**: none (verification only)
- **What**: Run R10, R11, R12, R14 acceptance checks as a combined Phase 3 gate.
- **Depends on**: [16, 17, 18, 19]
- **Complexity**: trivial
- **Context**: Phase 3 PR boundary.
- **Verification**: All R10/R11/R12/R14 acceptance grep + tiktoken + script assertions pass.
- **Status**: [ ] pending

---

### Group G — Shared primitive: the 4 area docs (`multi-agent.md`, `observability.md`, `pipeline.md`, `remote-access.md`)

This primitive is **audited** by Task 21, **patched in place** by Task 22, and **memorialized** by the audit memo. No rewrite-from-scratch.

### Task 21: Spot-check 12+ claims across the 4 area docs (reader for primitive G)
- **Files**: `cortex/requirements/multi-agent.md`, `cortex/requirements/observability.md`, `cortex/requirements/pipeline.md`, `cortex/requirements/remote-access.md` (read-only at this step)
- **What**: For each of the 4 area docs, identify ≥3 specific claims (file:line + verbatim quote) and verify each against current code in the cortex_command repo. Record findings in `cortex/lifecycle/requirements-skill-v2/area-audit.md` with verdict ✓ or ✗ per claim. Total ≥12 spot-checks. The audit references the same code paths research §1.2 used (`cortex_command/install_guard.py`, `init/settings_merge.py`, `overnight/state.py`, `pipeline/dispatch.py`, etc.) plus additional spot-checks per area.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec R13. Research §1.2 verified 5 spot-checks and found 5/5 accurate, suggesting drift is minimal; this task formally expands to ≥12 spot-checks and produces the memo for the record.
- **Verification**: Memo file exists with ≥12 entries, each containing file:line + quote + verdict.
- **Status**: [ ] pending

### Task 22: Patch any drift identified by Task 21 (writer for primitive G)
- **Files**: any area doc with a ✗ verdict from Task 21
- **What**: For each ✗ verdict, patch the specific drift in place — minimal edit, not section rewrite. Link the patch commit hash in the audit memo. If Task 21 finds no drift (per research §1.2's 5/5-confirmed precedent), this task is a no-op and the memo records that explicitly.
- **Depends on**: [21]
- **Complexity**: simple
- **Context**: Spec R13. Non-Requirements explicitly excludes wholesale area-doc rewrites; patch-in-place only.
- **Verification**: Every ✗ in the memo has a linked patch commit; re-running the spot-check on each patched claim returns ✓.
- **Status**: [ ] pending

### Task 23: Confirm Phase 4 acceptance rollup
- **Files**: none (verification only)
- **What**: Run R13, R14 acceptance checks as a combined Phase 4 gate.
- **Depends on**: [18, 22]
- **Complexity**: trivial
- **Context**: Phase 4 PR boundary. R14 is co-located in Group E (Task 18) but its acceptance is part of Phase 4; this rollup is where both R13 (audit memo) and R14 (Project Boundaries clarification) are jointly verified.
- **Verification**: Audit memo passes R13 acceptance AND project.md passes R14 acceptance.
- **Status**: [ ] pending

---

### Group H — Shared primitive: the `/requirements` skill surface (orchestrator + gather + write)

This primitive is **decomposed** by Tasks 24-26 (the three SKILL.md files), **retired in part** by Task 27 (removing `references/gather.md`), **weight-checked** by Task 28, **end-to-end tested** by Task 29, and **mirrored** by Task 30.

### Task 24: Create `/requirements-gather` SKILL.md (writer for primitive H)
- **Files**: `skills/requirements-gather/SKILL.md` (new), `skills/requirements-gather/` (new directory)
- **What**: Author the interview-only sub-skill at ≤80 lines. The SKILL.md must encode three mattpocock-style patterns: (a) recommend-before-asking (the model commits a position before each question); (b) codebase-trumps-interview (explore code when answerable from code, then ask); (c) lazy artifact creation (do not write to disk until something to write). Output contract: a structured Q&A markdown block ready for `/requirements-write` to consume. Prescribe What and Why (decision criteria, gates, output shapes), not How (no step-by-step procedure). Soft positive-routing only.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec R15. Brevity target ≤80 lines is the enforcement mechanism for the What/Why principle. Acceptance includes ≥1 match for each of: `recommend.*before.*ask|recommended answer`, `codebase.*trump|explore.*code.*instead`, `lazy|only.*write.*when`. Research §4 documents the mattpocock patterns (grill-me, grill-with-docs); the transferable subset is items 1, 2, 3 from §4 Transferable patterns.
- **Verification**: `wc -l skills/requirements-gather/SKILL.md` returns ≤80 AND all three regex checks return ≥1.
- **Status**: [ ] pending

### Task 25: Create `/requirements-write` SKILL.md (writer for primitive H)
- **Files**: `skills/requirements-write/SKILL.md` (new), `skills/requirements-write/` (new directory)
- **What**: Author the synthesize-only sub-skill at ≤50 lines. Inputs: structured Q&A from `/requirements-gather` + existing target doc if any. Outputs: `cortex/requirements/{project|area}.md` per v2 artifact format. Artifact-format templates inline (no separate `references/` subdirectory). Both scopes addressed (parent and area) in the SKILL.md body. Prescribe What and Why only.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R16. Acceptance: `wc -l skills/requirements-write/SKILL.md` ≤50 AND `grep -c "project\.md\|area\.md" skills/requirements-write/SKILL.md` ≥2.
- **Verification**: Above two checks pass.
- **Status**: [ ] pending

### Task 26: Rewrite `/requirements` SKILL.md as thin orchestrator (writer for primitive H)
- **Files**: `skills/requirements/SKILL.md`
- **What**: Rewrite the existing 348-line skill as a thin orchestrator at ≤30 lines that invokes `/requirements-gather` and `/requirements-write` in sequence. Preserve the existing user-facing entry point (`/cortex-core:requirements [area]`) so callers and prose references continue to work. The orchestrator describes the gather→write handoff contract, not the substance of either sub-skill.
- **Depends on**: [24, 25]
- **Complexity**: simple
- **Context**: Spec R17. Acceptance: `wc -l` ≤30 AND both sub-skill references present.
- **Verification**: `wc -l skills/requirements/SKILL.md` ≤30 AND `grep -c "/requirements-gather\|requirements-gather"` ≥1 AND `grep -c "/requirements-write\|requirements-write"` ≥1.
- **Status**: [ ] pending

### Task 27: Retire `references/gather.md` (writer for primitive H — deletion)
- **Files**: `skills/requirements/references/gather.md` (deletion)
- **What**: Remove the 232-line procedural narration file. Confirm no live references remain in active source (excluding archived lifecycle dirs, research dirs, backlog dirs, tests, and the v2 lifecycle dir).
- **Depends on**: [24, 26]
- **Complexity**: trivial
- **Context**: Spec R18. The dependency on Tasks 24 and 26 is logical: the new gather skill and the thin orchestrator must already absorb gather.md's essential decision criteria before the file is removed. Acceptance: file absent AND `grep -rln "references/gather.md\|requirements/references/gather" . --exclude-dir=.git --exclude-dir=docs/internals --exclude-dir=cortex/lifecycle/requirements-skill-v2 --exclude-dir=cortex/lifecycle/archive --exclude-dir=cortex/research --exclude-dir=cortex/backlog --exclude-dir=tests` returns no matches.
- **Verification**: `test ! -f skills/requirements/references/gather.md` AND the grep above returns empty.
- **Status**: [ ] pending

### Task 28: Verify skill total weight ≤160 lines (reader for primitive H — integrity check)
- **Files**: none (verification only)
- **What**: Sum the line counts of `skills/requirements/SKILL.md` + `skills/requirements-gather/SKILL.md` + `skills/requirements-write/SKILL.md`; confirm ≤160 (vs v1 baseline 348). Gate Phase 5 PR on this check.
- **Depends on**: [24, 25, 26]
- **Complexity**: trivial
- **Context**: Spec R19. Acceptance: `wc -l skills/requirements/SKILL.md skills/requirements-gather/SKILL.md skills/requirements-write/SKILL.md | tail -1 | awk '{print $1}'` returns ≤160.
- **Verification**: Above wc check passes.
- **Status**: [ ] pending

### Task 29: Build end-to-end routing test (reader for primitive H — integrity check)
- **Files**: `tests/test_requirements_skill_e2e.py` (new)
- **What**: Pytest test that invokes the orchestrator path (`/cortex-core:requirements observability` or equivalent existing area name) and verifies (a) `/requirements-gather` is invoked; (b) `/requirements-write` is invoked; (c) the resulting `cortex/requirements/{area}.md` is written to the expected path; (d) the artifact has the required sections from the format template. The test mocks the user-interview surface (canned answers) so it runs non-interactively. Any external dispatch (e.g., Claude API) is mocked deterministically. Hermetic by design.
- **Depends on**: [24, 25, 26]
- **Complexity**: complex
- **Context**: Spec R20. The test must fail if either sub-skill is not invoked, if the artifact is not written, or if the artifact lacks required sections. Mocking strategy follows existing test patterns in `tests/`.
- **Verification**: `test -f tests/test_requirements_skill_e2e.py && python3 -m pytest tests/test_requirements_skill_e2e.py -v` exits 0.
- **Status**: [ ] pending

### Task 30: Verify plugin auto-mirror for new sub-skills (reader for primitive H — mirror integrity)
- **Files**: `plugins/cortex-core/skills/requirements-gather/` (auto-mirrored), `plugins/cortex-core/skills/requirements-write/` (auto-mirrored)
- **What**: After committing Tasks 24-26, the pre-commit dual-source hook regenerates `plugins/cortex-core/skills/` mirrors. Verify both new sub-skill directories appear in the mirror, and the parity check passes against the mirrored state. If `bin/.parity-exceptions.md` needs an entry for either sub-skill, add it (R21 explicitly allows this as a hygiene fallback).
- **Depends on**: [24, 25, 26]
- **Complexity**: trivial
- **Context**: Spec R21 (Should-have). The pre-commit dual-source hook is the load-bearing mechanism; this task confirms it fired correctly.
- **Verification**: `find plugins/cortex-core/skills -maxdepth 2 -type d -name "requirements-*" | wc -l` returns ≥2 AND `bin/cortex-check-parity` (or equivalent) exits 0.
- **Status**: [ ] pending

### Task 31: Confirm Phase 5 acceptance rollup
- **Files**: none (verification only)
- **What**: Run R15-R21 acceptance checks as a combined Phase 5 gate before opening the Phase 5 PR.
- **Depends on**: [24, 25, 26, 27, 28, 29, 30]
- **Complexity**: trivial
- **Context**: Phase 5 PR boundary; this is the largest phase by primitive count.
- **Verification**: All R15-R21 acceptance assertions pass.
- **Status**: [ ] pending

---

### Group I — Lifecycle-level rollup

### Task 32: Final lifecycle acceptance rollup + retro entry
- **Files**: `cortex/lifecycle/requirements-skill-v2/retro.md` (new), `cortex/lifecycle/requirements-skill-v2/index.md` (update)
- **What**: Run all 21 R-criteria acceptance checks as a single final gate. Record a retro entry noting any deviations from the plan, any escalation-policy considerations triggered (e.g., MUST-escalation policy invocations), and the events.log path for the lifecycle. Update index.md status to `complete`.
- **Depends on**: [9, 15, 20, 23, 31]
- **Complexity**: trivial
- **Context**: Lifecycle completion convention. The dependency set covers each phase's rollup task (9, 15+other, 20, 23, 31). Group I exists outside the eight primitive groups because it operates on the lifecycle's own metadata, not on any of the eight shared primitives.
- **Verification**: All 21 R-criteria pass; retro.md present; index.md status updated to `complete`.
- **Status**: [ ] pending

---

## Risks

- **Risk 1 (high)** — **Task 16's tiktoken trim may collide with Edge Case "trim removes a section another consumer prose references by name"**: Before Task 16 trims, an audit of section references across all skills/hooks is required. If a referenced section can't move cleanly to `## Optional`, it must be exempted from trim and documented in spec amendments. Mitigation: include the reference audit as the first sub-step of Task 16.

- **Risk 2 (medium)** — **Task 13/14 (one-shot remediation) is a session-time operation that depends on Claude API availability**: If the script fails mid-run on multiple artifacts due to API rate limits or transient errors, the operator must re-run with partial-progress resumption. Mitigation: Task 13's script logs per-artifact outcome and supports re-run idempotency (skip artifacts already containing the suggestion section).

- **Risk 3 (medium)** — **Task 7's tag-backfill depends on parent backlog item tags being accurate**: If backlog items have stale or missing tags, Task 7 propagates that staleness into lifecycle index.md files. Mitigation: Task 8 spot-checks ≥3 backfilled files; the cost of a tag mismatch is silent under-loading (the R1 fallback applies), not failure.

- **Risk 4 (medium)** — **Tasks 24-26 (skill rewrite) must avoid new MUST language per CLAUDE.md MUST-escalation policy**: The brevity targets (≤80, ≤50, ≤30) make this easier (less prose room for imperative language), but the rewrite must be reviewed for MUST/CRITICAL/REQUIRED escalations and re-routed to soft positive-routing form. Mitigation: include a MUST-grep check in Task 31's rollup.

- **Risk 5 (low)** — **Task 19's intersection verifier may surface a real gap between Conditional Loading triggers and actual tags**: If the verifier fails after Task 16's trim, the trim must be revisited to ensure all area-doc triggers still match the real tag corpus. Mitigation: Task 19's failure is informational and triggers a Task-16 amendment, not a Phase 3 rollback.

- **Risk 6 (low)** — **Task 29's E2E test requires mocking Claude API dispatch**: If the existing test suite has no mocking infrastructure for Agent SDK calls, this task may need to introduce one. Mitigation: cite existing test patterns first; only build new infrastructure if none exists.

- **Risk 7 (low)** — **Group ordering vs. spec's recommended layer order (A→E→B→D→C)**: This plan's shared-state grouping produces a slightly different ship cadence (Groups A+B = Phase 1; Group C+D = Phase 2; Groups E+F = Phase 3; Group G = Phase 4; Group H = Phase 5). The mapping is preserved within phases. Mitigation: the spec's Phase boundaries are still respected; only intra-phase task ordering is primitive-driven rather than spec-prose-driven.

## Acceptance

The lifecycle is complete when all 21 R-criteria (R1-R21) pass their spec-defined verification commands:

1. R1: `test -f skills/lifecycle/references/load-requirements.md` AND `grep -c "Conditional Loading"` ≥1 AND fallback regex match ≥1
2. R2: Loader reference in 2 lifecycle files; heuristic prose removed
3. R3: Loader reference in 2 discovery files; heuristic prose removed
4. R4: Loader reference in refine SKILL.md
5. R5: 6-of-6 consumers wired; critical-review exemption documented
6. R6: All 41 lifecycle index.md files have `tags:` present (10 backfilled)
7. R7: Suggested Update section enforced; max-retry=2 documented; `drift_protocol_breach` emitted in review.md, surfaced in report.py, registered in `.events-registry.md`
8. R8: ≥7-of-8 historical drift artifacts remediated (≤1 unfixed)
9. R9: `bin/cortex-requirements-parity-audit` exists, executable, `--help` works, `just` recipe present
10. R10: project.md ≤1,200 tokens (cl100k_base)
11. R11: `## Optional` H2 section exists with prunability convention statement
12. R12: Conditional Loading triggers intersect real tag corpus (verifier exits 0)
13. R13: Area audit memo with ≥12 spot-checks; any ✗ has linked patch commit
14. R14: Project Boundaries clarifies discovery/backlog inline-documented; no new area docs
15. R15: `/requirements-gather` ≤80 lines with 3 mattpocock patterns
16. R16: `/requirements-write` ≤50 lines with both scopes addressed
17. R17: `/requirements` ≤30 lines; thin orchestrator
18. R18: `references/gather.md` removed; no live references in active source
19. R19: Total skill weight ≤160 lines
20. R20: E2E pytest passes
21. R21: Plugin mirror present for both sub-skills; parity check passes

Plus Task 32's retro entry, index.md status=complete, and final acceptance rollup at the lifecycle level.
