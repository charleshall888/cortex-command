# Plan: requirements-skill-v2

## Overview
Ship v2 as five sequential phase-PRs, each consuming the previous phase's output and gated by an observable Checkpoint before the next phase begins. Each phase is one self-contained PR landing in the trunk; tasks inside a phase form a linear Depends-on chain so the phase's Checkpoint state is reached by the final task.
**Architectural Pattern**: pipeline
<!-- This variant ships work as 5 sequential phase-PRs with linear intra-phase dependency chains and one Checkpoint per phase, whereas the `layered` variant cuts by abstraction-layer (loader / drift / parent-doc / area / skill) potentially shipped in parallel, and the `shared-state` variant routes coordination through a central manifest (e.g. a tags/conditional-loading registry) that all consumers and producers read/write against. -->

## Outline

### Phase 1: Consumer navigability (tasks: 1, 2, 3, 4, 5, 6, 7, 8, 8b)
**Goal**: Layer A — extract the tag-based loading protocol from `review.md`, apply it to the 5 remaining non-exempt consumers, document the deliberate `critical-review` exemption, and backfill `tags:` into the 10 legacy lifecycle index.md files so consumers never read against an empty surface.
**Checkpoint**: `grep -l 'load-requirements.md\|tag-based.*loading' skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md skills/lifecycle/references/review.md skills/discovery/references/clarify.md skills/discovery/references/research.md skills/refine/SKILL.md | wc -l` returns `6`; `find cortex/lifecycle -maxdepth 2 -name index.md -exec grep -L '^tags:' {} \;` returns empty; `test -f skills/lifecycle/references/load-requirements.md`; AND **execution smoke test** `python3 -m pytest tests/test_load_requirements_protocol.py -v` exits `0` (Task 8 verifies the loader's protocol resolves correctly against a synthetic tagged index.md). Phase 1 PR merged before Phase 2 starts.

### Phase 2: Drift tightening (tasks: 9, 10, 11, 12, 13)
**Goal**: Layer E — enforce `## Suggested Requirements Update` for `requirements_drift: detected` via post-dispatch re-dispatch (max-retry=2), surface exhausted retries as `drift_protocol_breach` in the morning report, remediate the 8 historical breach artifacts, and ship the parity-audit script.
**Checkpoint**: `grep -c "drift_protocol_breach" cortex_command/overnight/report.py` ≥`1`; `grep -c "drift_protocol_breach" bin/.events-registry.md` ≥`1`; remediation script left in lifecycle dir and historical breaches reduced to ≤1; `test -x bin/cortex-requirements-parity-audit`. Phase 2 PR merged before Phase 3 starts.

### Phase 3: Parent trim + Optional partition (tasks: 14, 15, 16, 17)
**Goal**: Layer B — trim `cortex/requirements/project.md` to ≤1,200 cl100k_base tokens, introduce `## Optional` H2 with prunable-content callout, and prove `## Conditional Loading` trigger phrases intersect with real tags from Phase 1's backfilled index.md set.
**Checkpoint**: `python3 -c "import tiktoken, pathlib; n=len(tiktoken.get_encoding('cl100k_base').encode(pathlib.Path('cortex/requirements/project.md').read_text())); assert n<=1200"` exits `0`; `grep -c "^## Optional$" cortex/requirements/project.md` returns `1`; intersection verifier exits `0`. Phase 3 PR merged before Phase 4 starts.

### Phase 4: Area-doc audit + patch (tasks: 18, 19, 20)
**Goal**: Layer D — spot-check ≥3 claims per area doc (12 total) against current code with verbatim file:line quotes, patch drift in place (not rewrite), and clarify in Project Boundaries that discovery and backlog are documented inline rather than via dedicated area docs.
**Checkpoint**: `cortex/lifecycle/requirements-skill-v2/area-audit.md` lists ≥12 spot-checks with verdicts; every ✗ has a linked patch commit; `test ! -f cortex/requirements/discovery.md && test ! -f cortex/requirements/backlog.md`; `grep -ciE 'discovery.*documented inline|inline.*discovery' cortex/requirements/project.md` ≥`1`. Phase 4 PR merged before Phase 5 starts.

### Phase 5: Skill split + brevity (tasks: 21, 22, 23, 24, 25, 26, 27, 28)
**Goal**: Layer C — split `/requirements` into `/requirements-gather` (≤80 lines) + `/requirements-write` (≤50 lines), make `/requirements` a thin orchestrator (≤30 lines), retire `references/gather.md`, hit the 160-line combined cap, ship the e2e routing test, and confirm parity-mirror hygiene.
**Checkpoint**: `wc -l skills/requirements/SKILL.md skills/requirements-gather/SKILL.md skills/requirements-write/SKILL.md | tail -1 | awk '{print $1}'` ≤`160`; `test ! -f skills/requirements/references/gather.md`; `python3 -m pytest tests/test_requirements_skill_e2e.py -v` exits `0`; `find plugins/cortex-core/skills -maxdepth 2 -type d -name "requirements-*" | wc -l` ≥`2`; AND **`bin/cortex-check-parity` exits `0`** (verifies plugin-mirror parity correctness per R21 spec acceptance, not just directory presence). Phase 5 PR merged — feature complete.

## Tasks

### Task 1: Create shared tag-based loading reference (R1)
- **Files**: `skills/lifecycle/references/load-requirements.md`
- **What**: New shared reference describing the 5-step tag-based loading protocol (always-load project.md → read index.md tags → case-insensitive match against Conditional Loading phrases → load matched area docs → fallback when tags absent/empty), extracted from `skills/lifecycle/references/review.md` lines 12-16.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Source prose lives at `skills/lifecycle/references/review.md` §1 lines 12-16. Reference must explicitly document the fallback rule for `tags:` empty/absent: load `project.md` only, proceed silently. Cross-link from review.md is added in Task 3.
- **Verification**: `test -f skills/lifecycle/references/load-requirements.md && grep -c "Conditional Loading" skills/lifecycle/references/load-requirements.md` ≥`1` AND `grep -ciE 'tags.*empty|tags.*absent|no tags' skills/lifecycle/references/load-requirements.md` ≥`1`.
- **Status**: [x] completed (commit 48b26c8d)

### Task 2: Replace heuristic loading in lifecycle clarify + specify (R2)
- **Files**: `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/specify.md`
- **What**: Replace the "scan area docs whose names suggest relevance" prose in clarify.md §2 and specify.md §1 with a delegation to `load-requirements.md`. Remove the heuristic prose entirely.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Existing patterns in review.md §1 show the citation shape. The phrase "names suggest relevance" must be entirely absent from both files post-edit.
- **Verification**: `grep -l "load-requirements.md\|tag-based.*loading" skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md | wc -l` returns `2` AND `grep -c "names suggest relevance" skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md` returns `0`.
- **Status**: [x] completed (commit 6520ed64)

### Task 3: Cross-link review.md to the shared reference (R5 partial)
- **Files**: `skills/lifecycle/references/review.md`
- **What**: Update review.md §1 lines 12-16 to cite `load-requirements.md` as the canonical source of the tag-based loading protocol it currently inlines. Preserve any review-specific framing.
- **Depends on**: [1]
- **Complexity**: trivial
- **Context**: Review.md remains the consumer that originated the protocol; cross-link makes the shared reference authoritative without duplicating prose.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/lifecycle/references/review.md` ≥`1`.
- **Status**: [x] completed (commit f4228e78)

### Task 4: Apply tag-based loading to discovery clarify + research (R3)
- **Files**: `skills/discovery/references/clarify.md`, `skills/discovery/references/research.md`
- **What**: Replace heuristic name-matching prose in both files with delegation to `load-requirements.md`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Same pattern as Task 2 applied to the discovery surface. Both files currently read `project.md` always then heuristically scan area docs.
- **Verification**: `grep -l "load-requirements.md\|tag-based.*loading" skills/discovery/references/clarify.md skills/discovery/references/research.md | wc -l` returns `2` AND `grep -c "names suggest relevance" skills/discovery/references/clarify.md skills/discovery/references/research.md` returns `0`.
- **Status**: [ ] pending

### Task 5: Apply tag-based loading to refine (R4)
- **Files**: `skills/refine/SKILL.md`
- **What**: Edit Step 3 (Clarify Phase) to cite `load-requirements.md` when delegating to `references/clarify.md`.
- **Depends on**: [1]
- **Complexity**: trivial
- **Context**: Refine wraps lifecycle clarify; the citation chain is `refine SKILL.md → lifecycle clarify.md → load-requirements.md`. Step 3 is the right insertion point.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/refine/SKILL.md` ≥`1`.
- **Status**: [ ] pending

### Task 6: Document critical-review's deliberate exemption (R5)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add an inline note containing the specific anchor phrase "Requirements loading: deliberately exempt" (verbatim), then explain that critical-review intentionally narrows context to parent project.md Overview only and does not use tag-based loading. The anchor phrase is the load-bearing structural marker; surrounding prose explains the design choice.
- **Depends on**: [1]
- **Complexity**: trivial
- **Context**: Per research §1.3, critical-review reads only Overview (~250 words). The exemption must be a documented design choice, not an oversight. The specific anchor phrase prevents casual mentions ("this is not narrow Overview", "tag-based loading is not relevant elsewhere") from accidentally passing a loose regex.
- **Verification**: `grep -c "Requirements loading: deliberately exempt" skills/critical-review/SKILL.md` ≥`1` (specific anchor phrase, not loose regex).
- **Status**: [ ] pending

### Task 7: Backfill `tags:` into existing index.md files (R6)
- **Files**: All `cortex/lifecycle/*/index.md` files currently lacking a `tags:` field (research identifies 10 such files; verify count at task-execution time and backfill all of them) AND `cortex/lifecycle/requirements-skill-v2/tag-backfill-mapping.md` (new audit memo capturing each (lifecycle-slug → parent-backlog-id → derived-tags) decision)
- **What**: One-off migration with audit memo: enumerate every affected index.md, derive tags from `parent_backlog_id` lookup, record the (lifecycle-slug → backlog-id → tags-array) mapping in `tag-backfill-mapping.md`. For lifecycles with `parent_backlog_id: null`, write `tags: []` with an inline comment that the loader falls back to `project.md`-only. Operator reviews the memo before committing the index.md edits and references it in the Phase 1 PR body for sign-off.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Tag source is the backlog item referenced by `parent_backlog_id`. `cortex/backlog/{id}-*.md` carries canonical tags. Files in `cortex/lifecycle/archive/` are out of scope. The audit memo + operator-review step protects against a silent miscategorization that would regress 10 active lifecycles' context-loading (no rollback exists at the artifact level — getting it right pre-merge is the protection).
- **Verification**: `test -f cortex/lifecycle/requirements-skill-v2/tag-backfill-mapping.md` (mapping memo exists) AND `find cortex/lifecycle -maxdepth 2 -name index.md -exec grep -L "^tags:" {} \;` returns empty AND the Phase 1 PR body references the audit memo (`grep -ciE 'tag-backfill-mapping\.md' <PR-body>` ≥`1`).
- **Status**: [ ] pending

### Task 8: Phase 1 union check + execution smoke test (R5)
- **Files**: `tests/test_load_requirements_protocol.py` (new — hermetic smoke test exercising the shared loader against a synthetic tagged index.md fixture; asserts each of the 6 consumer references resolves and project.md + tag-matched area docs are surfaced as expected)
- **What**: Add an execution-level smoke test that proves Phase 1's prose changes actually wire tag-based loading correctly, not just that strings appear. The test mocks a tagged `index.md` and asserts the loader emits the correct (project.md + matched-area-docs) set. Also explicitly run the union grep `grep -l 'load-requirements.md\|tag-based.*loading' skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md skills/lifecycle/references/review.md skills/discovery/references/clarify.md skills/discovery/references/research.md skills/refine/SKILL.md | wc -l` (must return `6`) and the critical-review exemption grep BEFORE opening the PR — these are pre-merge gates, not post-merge checks (critical-review flagged Phase 1 Checkpoint as presence-only).
- **Depends on**: [2, 3, 4, 5, 6, 7]
- **Complexity**: complex
- **Context**: Critical-review flagged Phase 1 Checkpoint as presence-only. This task adds the execution-level gate so a regression in any one of the 6 consumer references is caught before PR merge, not silently after. Test pattern follows existing `tests/test_*` conventions.
- **Verification**: `test -f tests/test_load_requirements_protocol.py` AND `python3 -m pytest tests/test_load_requirements_protocol.py -v` exits `0` AND the 6-file union grep returns `6` AND `grep -c "Requirements loading: deliberately exempt" skills/critical-review/SKILL.md` ≥`1`.
- **Status**: [ ] pending

### Task 8b: Phase 1 PR
- **Files**: (no new files; PR groups Tasks 1-8)
- **What**: Open the Phase 1 PR. Title cites R1-R6, body summarizes the navigability fix, tag backfill, and execution smoke test. Reference the `tag-backfill-mapping.md` audit memo for operator sign-off. Merge after review.
- **Depends on**: [8]
- **Complexity**: trivial
- **Context**: PR cadence = one-PR-per-phase. Use `/cortex-core:pr`. Phase 2 work does not begin until this PR is merged.
- **Verification**: Phase 1 Checkpoint commands (from Outline) all pass on `main` after merge.
- **Status**: [ ] pending

### Task 9: Enforce Suggested Update section + retry logic in review.md (R7 part 1)
- **Files**: `skills/lifecycle/references/review.md`, `tests/test_drift_enforcement_protocol.py` (new — integration test simulating a reviewer omitting the Suggested Update section; asserts the re-dispatch fires and `drift_protocol_breach` event is emitted after retry exhaustion)
- **What**: Add post-dispatch validation gate prose to `review.md` §4: when reviewer emits `requirements_drift: detected`, the validator checks for `## Suggested Requirements Update` section; if absent, re-dispatch the reviewer with max-retry=2; after the 3rd unsuccessful pass, log a `drift_protocol_breach` event with `state=detected, suggestion=missing` and proceed without blocking. Add a tests/ integration test that simulates a reviewer omitting the section and asserts (a) the re-dispatch fires, (b) the retry count caps at 2, (c) the breach event is emitted on exhaustion. The behavioral test guards against the failure mode where review.md prose mentions the keywords but doesn't actually wire the gate.
- **Depends on**: [8b]
- **Complexity**: complex
- **Context**: Existing §4 of `review.md` already wires the auto-apply cascade for `requirements_drift: detected` with a Suggested Update section; this task adds the parallel enforcement path when the section is absent. Soft positive-routing only — no MUST/CRITICAL escalation in the new prose. Critical-review flagged that presence-only verification could pass while the prose says the opposite (e.g., "we do NOT enforce max-retry=2"); the integration test forces behavioral verification.
- **Verification**: `grep -c "Suggested Requirements Update" skills/lifecycle/references/review.md` returns ≥`2` (absolute target, not differential) AND `grep -c "max[-_ ]retry.*2\|retry.*max.*2" skills/lifecycle/references/review.md` ≥`1` AND `grep -c "drift_protocol_breach" skills/lifecycle/references/review.md` ≥`1` AND `test -f tests/test_drift_enforcement_protocol.py && python3 -m pytest tests/test_drift_enforcement_protocol.py -v` exits `0`.
- **Status**: [ ] pending

### Task 10: Wire `drift_protocol_breach` into report.py + events registry (R7 part 2)
- **Files**: `cortex_command/overnight/report.py`, `bin/.events-registry.md`
- **What**: Extend the session-header rendering in `report.py` to surface `drift_protocol_breach` events alongside the existing `requirements_drift` summary; register the new event type in `.events-registry.md`.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Existing pattern: `_read_requirements_drift` at `cortex_command/overnight/report.py:559,635`. The new event type travels through events.log, not the review.md frontmatter. Follow the existing event-row rendering for sibling event types in the same file.
- **Verification**: `grep -c "drift_protocol_breach" cortex_command/overnight/report.py` ≥`1` AND `grep -c "drift_protocol_breach" bin/.events-registry.md` ≥`1`.
- **Status**: [ ] pending

### Task 11: One-shot historical drift remediation script (R8)
- **Files**: `cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py`, `docs/internals/one-shot-scripts.md` (new or appended — registry of one-shot remediation scripts with discovery pointer)
- **What**: One-shot script that (a) enumerates `cortex/lifecycle/{,archive/}*/review.md` files with `requirements_drift: detected` and no `## Suggested Requirements Update` section, (b) dispatches a reviewer agent per file to add the missing section, (c) writes results back. Supports `--dry-run` mode that lists exactly the candidate files without dispatching. Lives in the lifecycle dir, not `bin/`; not wired into the overnight runner. Script handles per-file dispatch failures by logging and continuing. Add a pointer in `docs/internals/one-shot-scripts.md` so future maintainers can discover historical remediations without already knowing the lifecycle dir exists.
- **Depends on**: [9]
- **Complexity**: complex
- **Context**: Research §2 identifies 8 such artifacts. Acceptance soft target ≤1 unfixed (≥7/8 succeed). The `--dry-run` mode lets the operator verify the candidate set semantically (script implements the spec's enumeration logic correctly) before live dispatch. The `docs/internals/one-shot-scripts.md` pointer mitigates Risk #3 from the original plan (script outside `bin/` is undiscoverable).
- **Verification**: `test -x cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py` AND `python3 cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py --dry-run | grep -c review.md` returns the expected candidate count (verify count matches research §2's 8 artifacts) AND `grep -c "remediate-historical-drift" docs/internals/one-shot-scripts.md` ≥`1`.
- **Status**: [ ] pending

### Task 12: Run remediation script + commit results
- **Files**: Affected `cortex/lifecycle/*/review.md` and `cortex/lifecycle/archive/*/review.md` files (8 in total per research)
- **What**: Operator runs the Task 11 script under interactive session, reviews dispatch output, commits resulting patches.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: This is an interactive session-time operation, not an overnight pass. Per spec edge case, ≤1 intractable artifact is acceptable.
- **Verification**: `grep -L "## Suggested Requirements Update" $(grep -rln 'requirements_drift: "detected"\|requirements_drift: detected' cortex/lifecycle/ cortex/lifecycle/archive/ --include=review.md)` returns ≤`1` line.
- **Status**: [ ] pending

### Task 13: Parity-audit script + just recipe (R9) + Phase 2 PR
- **Files**: `bin/cortex-requirements-parity-audit`, `justfile`, `plugins/cortex-core/bin/cortex-requirements-parity-audit` (auto-mirrored), `tests/test_requirements_parity_audit.py` (new — fixture-based test that runs the audit against a known-shape archived review.md fixture and asserts output JSON schema)
- **What**: Add executable `cortex-requirements-parity-audit` that scans all `cortex/lifecycle/{,archive/}*/review.md` files post-#013 (2026-04-03+), counts detected-drift artifacts and actual `cortex/requirements/*.md` changes that materialized those suggestions, emits a JSON report listing logged-but-not-applied suggestions. Wire `just requirements-parity-audit` recipe. Add a fixture-based test that runs the audit against a synthetic known-shape archived review.md and asserts the output JSON schema (protects against silent regression if archived data shape changes). Then open Phase 2 PR (Tasks 9-13), merge before Phase 3 begins.
- **Depends on**: [10, 12]
- **Complexity**: complex
- **Context**: Read archived review.md files (pre-#013 reviews without the field are skipped silently). Pre-commit hook will auto-mirror to `plugins/cortex-core/bin/`. The just recipe satisfies the bin-script parity gate. PR is opened via `/cortex-core:pr`. The fixture test mitigates the implicit dependency on archived-data shape that critical-review flagged.
- **Verification**: `test -x bin/cortex-requirements-parity-audit` AND `bin/cortex-requirements-parity-audit --help` exits `0` AND `just --list 2>&1 | grep -c requirements-parity` ≥`1` AND `python3 -m pytest tests/test_requirements_parity_audit.py -v` exits `0`. After PR merge, Phase 2 Checkpoint (from Outline) all-pass on `main`.
- **Status**: [ ] pending

### Task 14: Add tiktoken dependency + verifier helper (R10 prep)
- **Files**: `pyproject.toml`, `cortex/lifecycle/requirements-skill-v2/scripts/measure-tokens.py`
- **What**: Add `tiktoken` to project dependencies if not present; add a small measurement script that prints the cl100k_base token count of `cortex/requirements/project.md` for use during the trim iteration loop.
- **Depends on**: [13]
- **Complexity**: simple
- **Context**: R10 uses `tiktoken.get_encoding('cl100k_base')`. The measurement script is iteration aid for Task 15; it remains in the lifecycle dir as documentation.
- **Verification**: `python3 -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"` exits `0` AND `test -x cortex/lifecycle/requirements-skill-v2/scripts/measure-tokens.py`.
- **Status**: [ ] pending

### Task 15: Trim parent project.md to ≤1,200 tokens + add Optional partition (R10, R11)
- **Files**: `cortex/requirements/project.md`, `cortex/lifecycle/requirements-skill-v2/trim-anchor-audit.md` (new — pre-trim enumeration of every `cortex/requirements/project.md#<anchor>` reference and named-section reference across active source, with exemption list for sections that must be preserved)
- **What**: BEFORE trimming, enumerate every reference to `cortex/requirements/project.md` (both anchor refs `project.md#<anchor>` and named-section refs like "see Philosophy of Work in project.md") across `skills/`, `hooks/`, `bin/`, `cortex_command/`, `docs/`, and any other active source. Record each in `trim-anchor-audit.md`. Then iterate trim of project.md while preserving all required H2 sections (Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading) AND every enumerated anchor/section from the audit. Move deferrable content to a new `## Optional` H2 whose first non-heading line states the prunability convention. Exempt referenced sections from the move and document exemptions inline.
- **Depends on**: [14]
- **Complexity**: complex
- **Context**: Current baseline ~1,785 tokens. Use Task 14's measurement script. Per spec edge case, critical-review flagged that named-anchor references could silently break post-trim — this task's pre-enumeration is the protection. Look for: `project.md#`, `Overview`, `Philosophy of Work`, `Architectural Constraints`, `Quality Attributes`, `Project Boundaries`, `Conditional Loading`, `Optional`, and any other H2 references.
- **Verification**: `test -f cortex/lifecycle/requirements-skill-v2/trim-anchor-audit.md` (pre-trim audit exists) AND `python3 -c "import tiktoken, pathlib; n=len(tiktoken.get_encoding('cl100k_base').encode(pathlib.Path('cortex/requirements/project.md').read_text())); assert n<=1200"` exits `0` AND `grep -c "^## Optional$" cortex/requirements/project.md` returns `1` AND `sed -n '/^## Optional$/,/^## /p' cortex/requirements/project.md | head -3 | grep -ciE 'prunable|optional|deferrable'` ≥`1` AND **post-trim anchor check**: every anchor enumerated in `trim-anchor-audit.md` is still resolvable in the trimmed project.md (verified via script that greps each anchor against the post-trim file).
- **Status**: [ ] pending

### Task 16: Verify Conditional Loading triggers intersect with real tags (R12)
- **Files**: `cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py`
- **What**: Script reads all active `cortex/lifecycle/*/index.md` `tags:` arrays (post-R6 backfill), extracts unique tag words, and asserts that for each of the 4 area-doc trigger entries in `cortex/requirements/project.md` `## Conditional Loading`, at least one tag word matches a trigger phrase. Exits non-zero with a diff report on mismatch.
- **Depends on**: [15]
- **Complexity**: complex
- **Context**: This is the intersection check between Phase 1's backfilled tags and Phase 3's trimmed Conditional Loading section. Area-doc stems: `multi-agent`, `observability`, `pipeline`, `remote-access`.
- **Verification**: `python3 cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py` exits `0` AND for each of the 4 area-doc stems, `sed -n '/^## Conditional Loading$/,/^## /p' cortex/requirements/project.md | grep -c "<stem>"` ≥`1`.
- **Status**: [ ] pending

### Task 17: Phase 3 PR — parent trim + Optional partition
- **Files**: (no new files; PR groups Tasks 14-16)
- **What**: Open Phase 3 PR. Body cites pre/post token counts (from Task 14 script output), the list of sections moved to Optional, and the intersection verifier result. Merge before Phase 4 starts.
- **Depends on**: [16]
- **Complexity**: trivial
- **Context**: PR cadence — one-PR-per-phase. Use `/cortex-core:pr`.
- **Verification**: Phase 3 Checkpoint commands (from Outline) all pass on `main` after merge.
- **Status**: [ ] pending

### Task 18: Area-doc spot-check audit (R13)
- **Files**: `cortex/lifecycle/requirements-skill-v2/area-audit.md`
- **What**: For each of `cortex/requirements/multi-agent.md`, `observability.md`, `pipeline.md`, `remote-access.md`, select ≥3 specific claims with file:line + verbatim quote, verify against current code, record verdict ✓/✗ in the audit memo. Minimum 12 spot-checks total.
- **Depends on**: [17]
- **Complexity**: complex
- **Context**: Research §1.2 demonstrates the spot-check pattern (claim + source + verdict + evidence file). Drift verdicts (✗) lead to Task 19 patches. Per research, drift is expected to be minor (research's own 5-claim sample was 5/5 confirmed).
- **Verification**: `wc -l cortex/lifecycle/requirements-skill-v2/area-audit.md` ≥ baseline + content for ≥12 spot-checks; manual inspection confirms 4 area docs each have ≥3 spot-checks with file:line + quote + verdict.
- **Status**: [ ] pending

### Task 19: Patch area docs where drift was found (R13 follow-through)
- **Files**: Whichever of `cortex/requirements/{multi-agent,observability,pipeline,remote-access}.md` have ✗ verdicts in Task 18's audit memo
- **What**: For every ✗ verdict in `area-audit.md`, patch the affected line in place (do not rewrite). Update the audit memo with the patch commit hash next to each ✗ row.
- **Depends on**: [18]
- **Complexity**: simple
- **Context**: Patch-in-place rule from spec: total replacement is out of scope. If a ✗ requires structural change, that becomes a separate ticket and is noted in `area-audit.md`.
- **Verification**: Every ✗ row in `cortex/lifecycle/requirements-skill-v2/area-audit.md` has a linked commit hash AND `git log --oneline --all -- cortex/requirements/multi-agent.md cortex/requirements/observability.md cortex/requirements/pipeline.md cortex/requirements/remote-access.md | head -20` shows the patch commits.
- **Status**: [ ] pending

### Task 20: Project Boundaries clarification for discovery/backlog (R14) + Phase 4 PR
- **Files**: `cortex/requirements/project.md`
- **What**: In the Project Boundaries (In Scope) subsection, add explicit prose clarifying that discovery and backlog subsystems are documented inline (in their respective `skills/discovery/SKILL.md` and `cortex/backlog/index.md`) rather than via dedicated area docs. Do not create `cortex/requirements/discovery.md` or `cortex/requirements/backlog.md`. Then open Phase 4 PR (Tasks 18-20), merge before Phase 5 starts.
- **Depends on**: [19]
- **Complexity**: simple
- **Context**: R14 resolves the documentation gap from research §1.2 (discovery/backlog listed In Scope without area docs). The prose change is small but must use specific wording matching the grep patterns. Re-verify token cap from Task 15 still holds after the additions.
- **Verification**: `grep -ciE "discovery.*documented inline|inline.*discovery" cortex/requirements/project.md` ≥`1` AND `grep -ciE "backlog.*documented inline|inline.*backlog" cortex/requirements/project.md` ≥`1` AND `test ! -f cortex/requirements/discovery.md && test ! -f cortex/requirements/backlog.md` AND post-merge Phase 4 Checkpoint passes.
- **Status**: [ ] pending

### Task 21: Define artifact-format templates for parent and area scopes
- **Files**: `cortex/lifecycle/requirements-skill-v2/artifact-format.md` (working draft used to seed Tasks 22-23)
- **What**: Draft the structured templates for `cortex/requirements/project.md` (parent scope) and `cortex/requirements/{area}.md` (area scope) that `/requirements-write` will produce — field names, H2 ordering, required sections. This is a planning artifact for Tasks 22-23; the templates will be inlined into `requirements-write/SKILL.md` per R16.
- **Depends on**: [20]
- **Complexity**: simple
- **Context**: Existing v1 templates live in `skills/requirements/references/gather.md` (being retired in Task 25) and in the canonical `cortex/requirements/project.md` post-trim. Required sections per R10/R14: Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries (with discovery/backlog inline clarification), Conditional Loading, Optional.
- **Verification**: `test -f cortex/lifecycle/requirements-skill-v2/artifact-format.md` AND file contains H2 sections for both `## Parent (project.md) template` and `## Area template`.
- **Status**: [ ] pending

### Task 22: Create `/requirements-gather` skill (R15)
- **Files**: `skills/requirements-gather/SKILL.md`
- **What**: Interview-only sub-skill ≤80 lines. Adopt three mattpocock patterns: (a) recommend-before-asking — model commits a position before each question; (b) codebase-trumps-interview — explore code when answerable from code, then ask; (c) lazy artifact creation — do not write to disk until something to write. Output: structured Q&A markdown block consumable by `/requirements-write`.
- **Depends on**: [21]
- **Complexity**: complex
- **Context**: Patterns sourced from research §4: `mattpocock/skills/skills/productivity/grill-me/SKILL.md` and `engineering/grill-with-docs/SKILL.md`. Follow cortex's "prescribe What and Why, not How" principle — describe decision criteria, not procedure. The 80-line cap is the structural enforcement of brevity. No new MUST/CRITICAL/REQUIRED escalations.
- **Verification**: `wc -l skills/requirements-gather/SKILL.md | awk '{print $1}'` ≤`80` AND `grep -ciE 'recommend.*before.*ask|recommended answer' skills/requirements-gather/SKILL.md` ≥`1` AND `grep -ciE 'codebase.*trump|explore.*code.*instead' skills/requirements-gather/SKILL.md` ≥`1` AND `grep -ciE 'lazy|only.*write.*when' skills/requirements-gather/SKILL.md` ≥`1`.
- **Status**: [ ] pending

### Task 23: Create `/requirements-write` skill (R16)
- **Files**: `skills/requirements-write/SKILL.md`
- **What**: Synthesize-only sub-skill ≤50 lines. Takes structured Q&A from `/requirements-gather` plus an existing target doc (if any) and produces `cortex/requirements/{project|area}.md`. Inlines both scope templates (no separate `references/`) from Task 21's artifact-format draft.
- **Depends on**: [21, 22]
- **Complexity**: complex
- **Context**: Use the parent and area templates drafted in Task 21. Both scopes (project.md and `{area}.md`) must be addressed by inline template references. Follow What/Why-not-How.
- **Verification**: `wc -l skills/requirements-write/SKILL.md | awk '{print $1}'` ≤`50` AND `grep -c "project\.md\|area\.md" skills/requirements-write/SKILL.md` ≥`2`.
- **Status**: [ ] pending

### Task 24: Rewrite `/requirements` as thin orchestrator (R17)
- **Files**: `skills/requirements/SKILL.md`, `cortex/lifecycle/requirements-skill-v2/requirements-caller-audit.md` (new — enumeration of every active-source reference to `/cortex-core:requirements` or `/requirements` invocation patterns, including argument shapes the v1 orchestrator supported)
- **What**: BEFORE rewriting, enumerate every active-source reference to `/cortex-core:requirements` or `/requirements` (skills/, docs/, CLAUDE.md, hooks/, justfile, tests/, plan templates). Record each caller's expected argument shape (e.g., `/requirements [area]`, `/requirements list`, etc.) in `requirements-caller-audit.md`. Then replace existing 116-line SKILL.md with a thin orchestrator ≤30 lines that invokes `/requirements-gather` then `/requirements-write` in sequence AND supports every argument shape the audit enumerated. Preserve user-facing entry point (`/cortex-core:requirements [area]`) so existing prose references and callers continue to work without modification.
- **Depends on**: [22, 23]
- **Complexity**: complex
- **Context**: The orchestrator is a routing surface; preserving the v1 contract is load-bearing for downstream callers. Critical-review flagged that line-count + string-presence verification doesn't prove contract preservation. The caller audit enumerates the contract surface so the rewrite can verify against it.
- **Verification**: `test -f cortex/lifecycle/requirements-skill-v2/requirements-caller-audit.md` (audit exists) AND `wc -l skills/requirements/SKILL.md | awk '{print $1}'` ≤`30` AND `grep -c "/requirements-gather\|requirements-gather" skills/requirements/SKILL.md` ≥`1` AND `grep -c "/requirements-write\|requirements-write" skills/requirements/SKILL.md` ≥`1` AND every argument shape enumerated in `requirements-caller-audit.md` is supported by the new orchestrator (verified by inspection in PR review).
- **Status**: [ ] pending

### Task 25: Retire `references/gather.md` and sweep stale refs (R18)
- **Files**: `skills/requirements/references/gather.md` (delete) AND the pre-enumerated list of active-source files referencing it (from `cortex/lifecycle/requirements-skill-v2/gather-md-callers.md` — captured at plan-authoring time below)
- **What**: BEFORE deletion, write the pre-enumerated caller list to `cortex/lifecycle/requirements-skill-v2/gather-md-callers.md` by running the exclusion-aware grep at plan-execution time and recording every file that currently references `references/gather.md` or `requirements/references/gather`. Then delete `references/gather.md` and update each enumerated caller to point at the new sub-skills (or remove the reference if obsolete). Excluded paths per spec: `.git`, `docs/internals`, `cortex/lifecycle/requirements-skill-v2`, `cortex/lifecycle/archive`, `cortex/research`, `cortex/backlog`, `tests`.
- **Depends on**: [24]
- **Complexity**: simple
- **Context**: Critical-review flagged that "any active-source files referencing it" is anti-pattern runtime discovery rather than plan-time enumeration. The pre-enumeration memo turns runtime discovery into a reviewable artifact: PR reviewers can see exactly which callers were updated and verify each update is correct. Spec R18 explicitly excludes lifecycle/archive/research/backlog/test paths from the sweep — those are historical artifacts that legitimately reference the old path.
- **Verification**: `test -f cortex/lifecycle/requirements-skill-v2/gather-md-callers.md` (pre-enumeration exists) AND `test ! -f skills/requirements/references/gather.md` AND `grep -rln "references/gather.md\|requirements/references/gather" . --exclude-dir=.git --exclude-dir=docs/internals --exclude-dir=cortex/lifecycle/requirements-skill-v2 --exclude-dir=cortex/lifecycle/archive --exclude-dir=cortex/research --exclude-dir=cortex/backlog --exclude-dir=tests` returns no matches.
- **Status**: [ ] pending

### Task 26: Verify skill total weight ≤160 lines (R19)
- **Files**: (verification-only; no edits unless cap breached)
- **What**: Check combined line count of the three SKILL.md files. If cap breached, iterate trim on the largest offender among Tasks 22-24 until the cap holds.
- **Depends on**: [24]
- **Complexity**: trivial
- **Context**: Caps are 30 + 80 + 50 = 160; this task confirms the sum holds after edits. Per-file caps already enforced by Tasks 22-24's verification.
- **Verification**: `wc -l skills/requirements/SKILL.md skills/requirements-gather/SKILL.md skills/requirements-write/SKILL.md | tail -1 | awk '{print $1}'` ≤`160`.
- **Status**: [ ] pending

### Task 27: End-to-end routing test (R20)
- **Files**: `tests/test_requirements_skill_e2e.py`
- **What**: Hermetic e2e test that invokes the `/cortex-core:requirements observability` entry point with canned user answers, verifies routing through `/requirements-gather` then `/requirements-write`, asserts the artifact is written to `cortex/requirements/{area}.md` and contains the required H2 sections from Task 21's artifact format. Test mocks user-interview surface and any external dispatch to be deterministic.
- **Depends on**: [24, 26]
- **Complexity**: complex
- **Context**: Existing test patterns live in `tests/`. The test must fail if either sub-skill is not invoked, if the artifact is missing, or if required sections are absent. Per spec edge case, must be hermetic with respect to external dispatches.
- **Verification**: `test -f tests/test_requirements_skill_e2e.py` AND `python3 -m pytest tests/test_requirements_skill_e2e.py -v` exits `0`.
- **Status**: [ ] pending

### Task 28: Parity-mirror hygiene + Phase 5 PR (R21)
- **Files**: `plugins/cortex-core/skills/requirements-gather/`, `plugins/cortex-core/skills/requirements-write/`, `plugins/cortex-core/skills/requirements/` (auto-mirrored by pre-commit hook); `bin/.parity-exceptions.md` (only if hook fails)
- **What**: Stage all Phase 5 changes, allow pre-commit hook to regenerate plugin mirrors. If parity check fails on the new sub-skills, add allowlist entries in `bin/.parity-exceptions.md`. Then open Phase 5 PR grouping Tasks 21-28. Merge to complete v2.
- **Depends on**: [25, 27]
- **Complexity**: simple
- **Context**: Pre-commit hook is the canonical regeneration path per CLAUDE.md. The just-shipped hook should auto-mirror; allowlist exception is fallback. PR opened via `/cortex-core:pr`.
- **Verification**: `find plugins/cortex-core/skills -maxdepth 2 -type d -name "requirements-*" | wc -l` ≥`2` AND `bin/cortex-check-parity` exits `0` AND post-merge Phase 5 Checkpoint (from Outline) all-passes on `main`.
- **Status**: [ ] pending

## Risks
- **Strict sequential phase gating extends total wall-clock time vs. a layered or parallel-shipped variant.** Phases 1→5 form a 5-merge sequence; the user may want to revisit whether Phases 3 (parent trim) and 4 (area-doc audit) could safely overlap, since neither depends on the other's content. The pipeline pattern intentionally serializes them to keep each PR's blast radius minimal.
- **R7's max-retry=2 enforcement happens in prose only, not in `cortex_command/overnight/runner.py`.** The re-dispatch is performed by the agent reading review.md and the test of whether it actually retries is observational. The spec explicitly avoided runner.py modification (Non-Requirements); if observation shows the retry loop is not firing in practice, a follow-up ticket to wire it into runner.py would be needed.
- **Task 11's one-shot script lives in `cortex/lifecycle/requirements-skill-v2/scripts/`, not `bin/`.** This means it is not subject to the bin-script parity gate. That is the intentional spec choice (one-shot remediation, not long-running infrastructure). Mitigation per critical-review: Task 11 now writes a registry pointer to `docs/internals/one-shot-scripts.md` so future maintainers can discover historical remediations without already knowing the lifecycle dir exists.
- **R14's discovery/backlog "inline-documented" clarification depends on the wording matching specific grep patterns** (`discovery.*documented inline|inline.*discovery`). Author must be careful with phrasing or the verification will fail despite semantically-correct prose.
- **Task 15 (parent doc trim) has the highest implementation risk** — the prose-trim iteration may require multiple passes to hit ≤1,200 tokens while preserving all required sections and the audit-before-moving rule. The measurement script (Task 14) is the iteration aid, but the trim itself is judgment-heavy.

## Acceptance
The full feature is accepted when (i) all five Phase Checkpoints from the Outline pass on `main` after their respective PRs merge, (ii) the consumer-loading ratio reaches 6/7 with `critical-review` documented as the exempt seventh, and (iii) invoking `/cortex-core:requirements observability` end-to-end produces a valid `cortex/requirements/observability.md` via `/requirements-gather` → `/requirements-write` routing (verified by `tests/test_requirements_skill_e2e.py`), with the combined skill weight ≤160 lines, parent `project.md` ≤1,200 tokens, the parity-audit script in `bin/`, and the 8 historical drift-without-suggestion artifacts remediated to ≤1 remaining.
