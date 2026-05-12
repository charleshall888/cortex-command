# Plan: requirements-skill-v2

## Overview
**Architectural Pattern**: layered
Unlike the pipeline variant (which sequences work by spec-phase A→E→B→D→C) and the shared-state variant (which fans out around a common artifact/state), the layered variant stratifies tasks by abstraction level — primitives ship first, then migrations, then consumer adoption, then enforcement, then content trim, then the skill surface — so each layer's contract solidifies before higher layers consume it.

**PR cadence recommendation**: 6 PRs, one per layer (Layer 0 primitives → Layer 1 migrations → Layer 2 consumer adoption → Layer 3 enforcement → Layer 4 content → Layer 5 skill surface). Each PR is independently reviewable and revertible. Inside a layer, tasks may execute in parallel based on Depends-on. Optionally Layers 0+1 can be combined into a single foundation PR if the migration is small (R6's tag backfill touches 10 files).

## Outline

### Phase 1: Consumer navigability (tasks: 1, 6, 7, 11, 12, 13, 14, 15)
**Goal**: Establish the shared loading primitive (Layer 0), backfill index.md tags (Layer 1), and migrate all six non-exempt consumers to read against that primitive (Layer 2). Result: 6/6 non-exempt consumers wired to tag-based loading; no consumer regresses below the v1 heuristic.
**Checkpoint**: `grep -l 'load-requirements.md\|tag-based.*loading' skills/lifecycle/references/{clarify,specify,review}.md skills/discovery/references/{clarify,research}.md skills/refine/SKILL.md | wc -l` returns 6; `find cortex/lifecycle -maxdepth 2 -name index.md -exec grep -L "^tags:" {} \;` returns no files.

### Phase 2: Drift tightening (tasks: 2, 3, 4, 5, 8, 16, 17, 21)
**Goal**: Register the `drift_protocol_breach` event (Layer 0), run the one-shot historical remediation (Layer 1), enforce the Suggested Update section in `review.md` and surface breaches in the morning report (Layer 3), and add the informational parity-audit script (Layer 3).
**Checkpoint**: All R7 acceptance greps pass; remediation script has been invoked and at most 1 historical artifact remains without a Suggested Update section; `bin/cortex-requirements-parity-audit --help` exits 0.

### Phase 3: Parent trim + Optional partition (tasks: 18, 22, 23, 24, 25)
**Goal**: Execute the trim of `cortex/requirements/project.md` to ≤1,200 cl100k_base tokens (Layer 4), partition prunable content into `## Optional` (Layer 4), and verify that the Conditional Loading triggers still intersect real tag words from active index.md files via the verifier script (Layer 3).
**Checkpoint**: tiktoken check exits 0; `## Optional` H2 present; `verify-conditional-loading.py` exits 0 against current index.md tag corpus.

### Phase 4: Area-doc audit + patch (tasks: 26, 27, 28, 29, 30)
**Goal**: Spot-check ≥12 claims (≥3 per area doc) against current code, patch drift in place, and clarify Project Boundaries so discovery and backlog are explicitly marked as inline-documented (no new area docs).
**Checkpoint**: `area-audit.md` lists ≥12 spot-checks; any ✗ verdict has a linked patch commit; `grep -ciE "discovery.*documented inline" project.md` and the backlog equivalent both return ≥1; no new `discovery.md` or `backlog.md` exists.

### Phase 5: Skill split + brevity (tasks: 9, 10, 19, 20, 31, 32, 33, 34, 35, 36)
**Goal**: Stand up the new sub-skills `/requirements-gather` and `/requirements-write` (Layer 5), thin the orchestrator at `skills/requirements/SKILL.md` (Layer 5), retire `references/gather.md` (Layer 5), satisfy the ≤160 total-line budget (Layer 5), run the e2e routing test (Layer 5), and confirm parity-mirror auto-regeneration (Layer 5).
**Checkpoint**: Three skill files at ≤80/≤50/≤30 lines; combined ≤160; `tests/test_requirements_skill_e2e.py` exits 0; `plugins/cortex-core/skills/requirements-*` mirrors exist; `bin/cortex-check-parity` exits 0.

---

## Tasks

> Tasks are ordered plan-wide by layer position (Layer 0 → Layer 5). Each task carries its spec-phase tag. Inside a layer, independent tasks may run in parallel.

---

### Layer 0 — Primitives (shared references, schema additions, event-registry entries)

### Task 1: Create shared tag-based loading reference
- **Files**: `skills/lifecycle/references/load-requirements.md` (new)
- **What**: Author the shared reference per R1. Document: (a) always read `cortex/requirements/project.md`; (b) read consumer's lifecycle `index.md` and extract `tags:`; (c) case-insensitively match each tag word against Conditional Loading phrases in `project.md`; (d) load matched area docs; (e) fallback when `tags:` is absent or empty — load `project.md` only, no error, no prose-MUST escalation. Prose follows "What/Why, not How" — describe decisions and intent, not procedural steps.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Layer 0 primitive. Source material is `skills/lifecycle/references/review.md` lines 12-16. Spec: R1. Phase: Phase 1.
- **Verification**: `test -f skills/lifecycle/references/load-requirements.md`; `grep -c "Conditional Loading" skills/lifecycle/references/load-requirements.md` ≥1; `grep -ciE 'tags.*empty|tags.*absent|no tags' skills/lifecycle/references/load-requirements.md` ≥1.
- **Status**: [ ] pending

### Task 2: Register `drift_protocol_breach` event in events registry
- **Files**: `bin/.events-registry.md`
- **What**: Add a new entry for the `drift_protocol_breach` event type. Document emitter (lifecycle review.md post-dispatch validation gate after max-retry exhaustion), schema fields the event carries (lifecycle slug, retry count, state, suggestion-status), and consumer surfaces (morning report).
- **Depends on**: none
- **Complexity**: trivial
- **Context**: Layer 0 primitive needed before Layer 3 R7 enforcement gate can emit it. Spec: R7 (subset). Phase: Phase 2.
- **Verification**: `grep -c "drift_protocol_breach" bin/.events-registry.md` ≥1.
- **Status**: [ ] pending

### Task 3: Define event payload contract for `drift_protocol_breach`
- **Files**: `bin/.events-registry.md` (continuation of Task 2 entry) OR `cortex_command/overnight/events.py` if a payload schema is defined there
- **What**: Lock the field shape that downstream consumers (report.py, parity audit) will read. Fields: `lifecycle_slug: str`, `retry_count: int (=2)`, `state: "detected"`, `suggestion_status: "missing"`, `review_path: str`, `timestamp: ISO8601`. No implementation — this is a contract task that the registry documents and the report.py consumer reads against.
- **Depends on**: 2
- **Complexity**: trivial
- **Context**: Layer 0 contract. Spec: R7 (event payload). Phase: Phase 2.
- **Verification**: The event entry in `bin/.events-registry.md` enumerates the 6 fields above.
- **Status**: [ ] pending

### Task 4: Add `tiktoken` dependency declaration
- **Files**: `pyproject.toml`
- **What**: Ensure `tiktoken` is declared as a project dependency (or dev dependency, per project convention) so R10's acceptance check runs without a `pip install` side-effect. Only required if `tiktoken` is not already a transitive dep.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: Layer 0 primitive — gates Layer 4 R10 trim verification. Spec: Technical Constraints — Tokenizer. Phase: Phase 3.
- **Verification**: `uv pip install -e .` succeeds and `python3 -c "import tiktoken"` exits 0.
- **Status**: [ ] pending

### Task 5: Document `## Suggested Requirements Update` section contract
- **Files**: `skills/lifecycle/references/load-requirements.md` (append) OR a sibling reference `skills/lifecycle/references/suggested-update-format.md`
- **What**: Define the structural contract for the `## Suggested Requirements Update` section that R7 will enforce: required H2 heading verbatim, required sub-bullets describing target file + proposed diff/prose, and the parser predicate (heading present + ≥1 non-empty body line) the Layer 3 gate will check. Co-locate with the loading reference to keep the requirements-loading contracts in one place.
- **Depends on**: 1
- **Complexity**: simple
- **Context**: Layer 0 contract — Layer 3 R7 gate reads against this. Spec: R7. Phase: Phase 2.
- **Verification**: Reference file documents heading verbatim, body shape, and the parser predicate as three named subsections.
- **Status**: [ ] pending

---

### Layer 1 — One-shot migrations and remediations

### Task 6: Backfill `tags:` field into existing index.md files (R6)
- **Files**: `cortex/lifecycle/*/index.md` (10 files identified in spec)
- **What**: For each of the 10 active-lifecycle `index.md` files missing `tags:`, add a `tags:` array derived from the parent backlog item's `tags:` frontmatter where one exists; for lifecycles with `parent_backlog_id: null`, write `tags: []` with an inline comment that the loader falls back to `project.md`-only. No content rewriting; YAML frontmatter only.
- **Depends on**: 1
- **Complexity**: simple
- **Context**: Layer 1 migration. Spec: R6. Phase: Phase 1. Eliminates the 24.4% regression case before Layer 2 consumers go live against the new loader.
- **Verification**: `find cortex/lifecycle -maxdepth 2 -name index.md -exec grep -L "^tags:" {} \;` returns no files.
- **Status**: [ ] pending

### Task 7: Author historical drift remediation script
- **Files**: `cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py` (new)
- **What**: One-shot script that (a) enumerates `cortex/lifecycle/*/review.md` and `cortex/lifecycle/archive/*/review.md` where `requirements_drift: detected` and `## Suggested Requirements Update` is absent; (b) for each, dispatches a reviewer agent to add the missing section; (c) writes the updated review.md back; (d) on per-artifact failure, logs and continues. Script is lifecycle-local — not in `bin/`, not wired to overnight runner. Interactive (operator invokes once, oversees re-dispatch).
- **Depends on**: 5
- **Complexity**: complex
- **Context**: Layer 1 migration. Spec: R8. Phase: Phase 2. Function signature: `main(dry_run: bool = False) -> int`; iterates over a target list of 8 known breaching files (enumerated by grep before commit).
- **Verification**: `test -x cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py`; `python3 cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py --help` exits 0.
- **Status**: [ ] pending

### Task 8: Execute historical drift remediation
- **Files**: 8 historical `review.md` files (acceptance allows ≤1 unfixed)
- **What**: Operator-driven run of Task 7's script. Reviewer re-dispatches add `## Suggested Requirements Update` sections to the 8 affected artifacts. Commit results to the lifecycle dirs separately from skill prose changes for clear blast-radius isolation.
- **Depends on**: 7
- **Complexity**: simple
- **Context**: Layer 1 execution. Spec: R8 (acceptance). Phase: Phase 2.
- **Verification**: `grep -L "## Suggested Requirements Update" $(grep -rln 'requirements_drift: "detected"\|requirements_drift: detected' cortex/lifecycle/ cortex/lifecycle/archive/ --include=review.md)` returns ≤1.
- **Status**: [ ] pending

---

### Layer 2 — Consumer adoption (existing-skill prose edits adopting the primitives)

### Task 9: Adopt shared loading reference in lifecycle clarify
- **Files**: `skills/lifecycle/references/clarify.md`
- **What**: Replace the heuristic "scan area docs whose names suggest relevance" prose in §2 with a reference to `skills/lifecycle/references/load-requirements.md`. Soft-positive routing only — no MUST escalation. Preserve §2's surrounding intent statement (why the consumer loads requirements at clarify time).
- **Depends on**: 1, 6
- **Complexity**: simple
- **Context**: Layer 2 adoption. Spec: R2 (clarify portion). Phase: Phase 1.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/lifecycle/references/clarify.md` ≥1; `grep -c "names suggest relevance" skills/lifecycle/references/clarify.md` = 0.
- **Status**: [ ] pending

### Task 10: Adopt shared loading reference in lifecycle specify
- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Replace the heuristic name-matching prose in §1 (or Step 4 per research §1.3) with a reference to `load-requirements.md`. Preserve the surrounding intent prose.
- **Depends on**: 1, 6
- **Complexity**: simple
- **Context**: Layer 2 adoption. Spec: R2 (specify portion). Phase: Phase 1. Parallel to Task 9.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/lifecycle/references/specify.md` ≥1; `grep -c "names suggest relevance" skills/lifecycle/references/specify.md` = 0.
- **Status**: [ ] pending

### Task 11: Adopt shared loading reference in discovery clarify
- **Files**: `skills/discovery/references/clarify.md`
- **What**: Replace heuristic name-matching prose with a reference to `load-requirements.md`. Preserve surrounding intent.
- **Depends on**: 1, 6
- **Complexity**: simple
- **Context**: Layer 2 adoption. Spec: R3 (clarify portion). Phase: Phase 1. Parallel to Task 9, 10.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/discovery/references/clarify.md` ≥1; `grep -c "names suggest relevance" skills/discovery/references/clarify.md` = 0.
- **Status**: [ ] pending

### Task 12: Adopt shared loading reference in discovery research
- **Files**: `skills/discovery/references/research.md`
- **What**: Replace heuristic name-matching prose with a reference to `load-requirements.md`. Preserve surrounding intent.
- **Depends on**: 1, 6
- **Complexity**: simple
- **Context**: Layer 2 adoption. Spec: R3 (research portion). Phase: Phase 1. Parallel to Task 9, 10, 11.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/discovery/references/research.md` ≥1; `grep -c "names suggest relevance" skills/discovery/references/research.md` = 0.
- **Status**: [ ] pending

### Task 13: Adopt shared loading reference in refine
- **Files**: `skills/refine/SKILL.md`
- **What**: Edit Step 3 (Clarify Phase) so that when refine delegates to `references/clarify.md`, requirements loading is routed via the shared `load-requirements.md` reference. Preserve refine's overall flow.
- **Depends on**: 1, 6
- **Complexity**: simple
- **Context**: Layer 2 adoption. Spec: R4. Phase: Phase 1.
- **Verification**: `grep -c "load-requirements.md\|tag-based.*loading" skills/refine/SKILL.md` ≥1.
- **Status**: [ ] pending

### Task 14: Document critical-review's intentional exemption
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add a short note that critical-review intentionally narrows requirements context to the parent Overview only and does not adopt tag-based loading. Soft prose — explanation of the design choice, not a prescriptive prohibition.
- **Depends on**: 1
- **Complexity**: trivial
- **Context**: Layer 2 adoption (documentation side). Spec: R5 (exemption clause). Phase: Phase 1.
- **Verification**: `grep -ciE 'requirements.*exempt|narrow.*overview|tag-based.*loading.*not' skills/critical-review/SKILL.md` ≥1.
- **Status**: [ ] pending

### Task 15: Validate Phase 1 navigability count
- **Files**: none (validation task)
- **What**: Run the R5 acceptance grep against the 6 non-exempt consumer files and confirm `wc -l` returns 6. If any consumer was missed, fix it in this task's commit rather than reopening earlier tasks.
- **Depends on**: 9, 10, 11, 12, 13, 14
- **Complexity**: trivial
- **Context**: Layer 2 verification gate. Spec: R5. Phase: Phase 1.
- **Verification**: `grep -l 'load-requirements.md\|tag-based.*loading' skills/lifecycle/references/{clarify,specify,review}.md skills/discovery/references/{clarify,research}.md skills/refine/SKILL.md | wc -l` returns 6.
- **Status**: [ ] pending

---

### Layer 3 — Enforcement (gate logic, validation, audit scripts)

### Task 16: Add post-dispatch enforcement of Suggested Update section in review.md
- **Files**: `skills/lifecycle/references/review.md`
- **What**: In §4 (post-dispatch validation), add a gate that detects `requirements_drift: detected` with a missing `## Suggested Requirements Update` section, re-dispatches the reviewer with the soft positive-routing prompt to add the section, retries up to 2 times. On the third pass, log a `drift_protocol_breach` event via the existing events-log surface and let the lifecycle proceed with `state=detected, suggestion=missing`. Soft prose only — no new MUST escalation; the structural gate (re-dispatch) does the enforcement.
- **Depends on**: 1, 2, 3, 5
- **Complexity**: complex
- **Context**: Layer 3 enforcement. Spec: R7 (review.md half). Phase: Phase 2.
- **Verification**: `grep -c "Suggested Requirements Update" skills/lifecycle/references/review.md` increases by ≥1 from baseline; `grep -c "max[-_ ]retry.*2\|retry.*max.*2" skills/lifecycle/references/review.md` ≥1; `grep -c "drift_protocol_breach" skills/lifecycle/references/review.md` ≥1.
- **Status**: [ ] pending

### Task 17: Surface `drift_protocol_breach` in morning report
- **Files**: `cortex_command/overnight/report.py`
- **What**: Extend the session header generation path (read via the existing event-log read path used by `_read_requirements_drift`) so that `drift_protocol_breach` events emitted by Task 16's gate appear in the morning report's session-header summary. Function-signature shape: a new helper `_collect_drift_protocol_breaches(session_dir: Path) -> list[dict]` that returns parsed event records; integrate output into the existing header formatter.
- **Depends on**: 2, 3
- **Complexity**: complex
- **Context**: Layer 3 enforcement (consumer side). Spec: R7 (report.py half). Phase: Phase 2. Parallel to Task 16.
- **Verification**: `grep -c "drift_protocol_breach" cortex_command/overnight/report.py` ≥1; unit test (if present per the repo's test conventions) covers the new helper.
- **Status**: [ ] pending

### Task 18: Author Conditional Loading verifier script
- **Files**: `cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py` (new)
- **What**: Script reads all active (non-archived) `cortex/lifecycle/*/index.md` files, extracts each `tags:` array, computes the union of tag words, then asserts that each Conditional Loading entry in `cortex/requirements/project.md` has at least one tag word intersecting its trigger phrase. Exits 0 on full intersection, nonzero with a diff report otherwise. Function signature: `main(project_md: Path = Path("cortex/requirements/project.md")) -> int`.
- **Depends on**: 6
- **Complexity**: complex
- **Context**: Layer 3 enforcement (Conditional Loading consistency). Spec: R12. Phase: Phase 3. Depends on R6 backfill so the tag corpus is real.
- **Verification**: `test -x cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py`; `--help` exits 0.
- **Status**: [ ] pending

### Task 19: Author parity-audit bin script
- **Files**: `bin/cortex-requirements-parity-audit` (new); `plugins/cortex-core/bin/cortex-requirements-parity-audit` (auto-mirrored by pre-commit hook)
- **What**: Script scans `cortex/lifecycle/*/review.md` and `cortex/lifecycle/archive/*/review.md` since 2026-04-03, counts (a) detected-drift artifacts and (b) materialized changes in `cortex/requirements/` git log over the same window, and emits a JSON report listing logged-but-not-applied drift suggestions. Args: `--since YYYY-MM-DD`, `--format json|text`, `--help`. Pre-#013 artifacts without `requirements_drift` field are skipped silently.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Layer 3 enforcement (informational). Spec: R9. Phase: Phase 2. Should-have priority. Must reference an in-scope surface (SKILL.md, requirements, docs, hooks, justfile, tests) per `bin/cortex-check-parity` — the `just requirements-parity-audit` recipe satisfies this.
- **Verification**: `test -x bin/cortex-requirements-parity-audit`; `--help` exits 0.
- **Status**: [ ] pending

### Task 20: Wire `just requirements-parity-audit` recipe
- **Files**: `justfile`
- **What**: Add a recipe `requirements-parity-audit` that invokes `bin/cortex-requirements-parity-audit` with sensible defaults. Satisfies the parity-gate "in-scope reference" requirement for the new bin script.
- **Depends on**: 19
- **Complexity**: trivial
- **Context**: Layer 3 enforcement. Spec: R9 + Technical Constraints (Bin-script parity gate). Phase: Phase 2.
- **Verification**: `just --list 2>&1 | grep -c requirements-parity` ≥1.
- **Status**: [ ] pending

### Task 21: Tokenizer-based size check for parent doc
- **Files**: `tests/test_requirements_parent_token_budget.py` (new) OR a `just` recipe `requirements-token-check`
- **What**: A repeatable check that uses `tiktoken.get_encoding('cl100k_base')` to encode `cortex/requirements/project.md` and asserts ≤1,200 tokens. Acceptance-time only — not a commit-time gate per Non-Requirements. Provides a stable surface for Phase 3 to validate against and for future audits.
- **Depends on**: 4
- **Complexity**: simple
- **Context**: Layer 3 verification tool. Spec: R10 (acceptance check). Phase: Phase 3. Predates the actual trim in Layer 4 so the trimmer has an objective signal.
- **Verification**: Test/recipe is invokable independently; baseline run reports current token count (≥1,200 prior to trim).
- **Status**: [ ] pending

---

### Layer 4 — Content (parent-doc trim + Optional partition + area-doc audit + Project Boundaries)

### Task 22: Inventory referenced sections of project.md before trim
- **Files**: `cortex/lifecycle/requirements-skill-v2/trim-audit.md` (new, lifecycle-local working memo)
- **What**: Run `grep -rln "project.md#" .` and similar grep against the active source tree to identify any section of `cortex/requirements/project.md` referenced by anchor from another skill/hook/doc. List each referenced section. Per spec Edge Cases: sections referenced by name must be preserved through the trim or explicitly exempted with a documented reason.
- **Depends on**: 21
- **Complexity**: simple
- **Context**: Layer 4 content (preflight). Spec: Edge Cases — "Parent doc trim removes a section another consumer prose references by name." Phase: Phase 3.
- **Verification**: Memo lists every named-reference section; sections to be trimmed are cross-checked against the list.
- **Status**: [ ] pending

### Task 23: Trim parent project.md to ≤1,200 tokens
- **Files**: `cortex/requirements/project.md`
- **What**: Reduce the document to ≤1,200 cl100k_base tokens while preserving required sections (Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading). Apply concision passes; do not move sections elsewhere except into the new `## Optional` H2 (Task 24). Honor Task 22's preserve-list.
- **Depends on**: 21, 22
- **Complexity**: complex
- **Context**: Layer 4 content. Spec: R10. Phase: Phase 3.
- **Verification**: Token-check tool from Task 21 exits 0; all named-reference sections still present.
- **Status**: [ ] pending

### Task 24: Introduce `## Optional` partition in parent project.md
- **Files**: `cortex/requirements/project.md`
- **What**: Add a new `## Optional` H2 section. Move prunable content (deferred items, lesser-priority architectural notes per spec) into it. The section's opening non-heading line states the prunability convention using one of: "prunable", "optional", "deferrable".
- **Depends on**: 23
- **Complexity**: simple
- **Context**: Layer 4 content. Spec: R11. Phase: Phase 3. llms.txt pattern.
- **Verification**: `grep -c "^## Optional$" cortex/requirements/project.md` = 1; `sed -n '/^## Optional$/,/^## /p' cortex/requirements/project.md | head -3 | grep -ciE 'prunable|optional|deferrable'` ≥1.
- **Status**: [ ] pending

### Task 25: Run Conditional Loading verifier against trimmed parent
- **Files**: none (verification task)
- **What**: Invoke `verify-conditional-loading.py` (Task 18) against the post-trim `project.md`. If intersection check fails, either restore the missing trigger phrase or update the `Conditional Loading` section to use a tag word that actually exists in active index.md files.
- **Depends on**: 18, 23, 24
- **Complexity**: simple
- **Context**: Layer 4 content verification (closes the loop with Layer 3's R12 verifier). Spec: R12. Phase: Phase 3.
- **Verification**: `python3 cortex/lifecycle/requirements-skill-v2/scripts/verify-conditional-loading.py` exits 0; each of the 4 area-doc stems (`multi-agent`, `observability`, `pipeline`, `remote-access`) appears in the Conditional Loading section.
- **Status**: [ ] pending

### Task 26: Spot-check multi-agent.md area doc
- **Files**: `cortex/requirements/multi-agent.md` (patch in place where drift found); `cortex/lifecycle/requirements-skill-v2/area-audit.md` (audit memo, new or appended)
- **What**: Identify ≥3 specific claims (line numbers + verbatim quotes) and check each against current `cortex_command/` code. Record verdicts (✓/✗) in `area-audit.md`. For any ✗, patch the doc in place; do not rewrite from scratch.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Layer 4 content. Spec: R13 (multi-agent portion). Phase: Phase 4. Parallel with Tasks 27, 28, 29.
- **Verification**: `area-audit.md` contains a multi-agent.md subsection with ≥3 spot-checks; any ✗ links to a patch commit.
- **Status**: [ ] pending

### Task 27: Spot-check observability.md area doc
- **Files**: `cortex/requirements/observability.md` (patch in place); `area-audit.md` (append)
- **What**: ≥3 spot-checks against current code. Patch drift in place. Record in `area-audit.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Layer 4 content. Spec: R13 (observability portion). Phase: Phase 4. Parallel with Tasks 26, 28, 29.
- **Verification**: `area-audit.md` contains an observability.md subsection with ≥3 spot-checks; any ✗ linked.
- **Status**: [ ] pending

### Task 28: Spot-check pipeline.md area doc
- **Files**: `cortex/requirements/pipeline.md` (patch in place); `area-audit.md` (append)
- **What**: ≥3 spot-checks against `cortex_command/pipeline/`. Patch drift in place. Record in `area-audit.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Layer 4 content. Spec: R13 (pipeline portion). Phase: Phase 4. Parallel with Tasks 26, 27, 29.
- **Verification**: `area-audit.md` contains a pipeline.md subsection with ≥3 spot-checks; any ✗ linked.
- **Status**: [ ] pending

### Task 29: Spot-check remote-access.md area doc
- **Files**: `cortex/requirements/remote-access.md` (patch in place); `area-audit.md` (append)
- **What**: ≥3 spot-checks against current remote-access code paths. Patch drift in place. Record in `area-audit.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Layer 4 content. Spec: R13 (remote-access portion). Phase: Phase 4. Parallel with Tasks 26, 27, 28.
- **Verification**: `area-audit.md` contains a remote-access.md subsection with ≥3 spot-checks; any ✗ linked.
- **Status**: [ ] pending

### Task 30: Clarify discovery/backlog status in Project Boundaries
- **Files**: `cortex/requirements/project.md`
- **What**: Edit the Project Boundaries (In Scope) section to explicitly state that discovery and backlog are documented inline (in their respective SKILL.md and backlog index.md) rather than via dedicated area docs. No new area docs are created. Phrasing must be greppable per the R14 acceptance regexes.
- **Depends on**: 23, 24
- **Complexity**: simple
- **Context**: Layer 4 content. Spec: R14. Phase: Phase 4.
- **Verification**: `grep -ciE "discovery.*documented inline|discovery.*inline.*document|inline.*discovery" cortex/requirements/project.md` ≥1; same for backlog; `test ! -f cortex/requirements/discovery.md && test ! -f cortex/requirements/backlog.md`.
- **Status**: [ ] pending

---

### Layer 5 — Skill surface (skill split + brevity + E2E test + parity mirror)

### Task 31: Author `skills/requirements-gather/SKILL.md`
- **Files**: `skills/requirements-gather/SKILL.md` (new)
- **What**: Interview-only sub-skill ≤80 lines. Adopt three mattpocock-style patterns: (a) recommend-before-asking — commit a position before each question; (b) codebase-trumps-interview — when answerable from code, explore code instead; (c) lazy artifact creation — no disk write until synthesize phase. Output shape: a structured Q&A markdown block that `/requirements-write` will consume. Prose follows "What/Why, not How": describe decision criteria, gates, output shape; do not narrate procedure. Soft positive routing throughout — no MUST escalation.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Layer 5 skill surface. Spec: R15. Phase: Phase 5. Front-matter: `name: requirements-gather`, `description:` describing trigger conditions.
- **Verification**: `wc -l skills/requirements-gather/SKILL.md | awk '{print $1}'` ≤80; `grep -ciE 'recommend.*before.*ask|recommended answer' skills/requirements-gather/SKILL.md` ≥1; `grep -ciE 'codebase.*trump|explore.*code.*instead' skills/requirements-gather/SKILL.md` ≥1; `grep -ciE 'lazy|only.*write.*when' skills/requirements-gather/SKILL.md` ≥1.
- **Status**: [ ] pending

### Task 32: Author `skills/requirements-write/SKILL.md`
- **Files**: `skills/requirements-write/SKILL.md` (new)
- **What**: Synthesize-only sub-skill ≤50 lines. Consumes the structured Q&A from `/requirements-gather` plus any existing target doc; produces `cortex/requirements/{project|area}.md` per the v2 artifact format. Includes the artifact-format templates inline (no separate `references/`) for parent and area scopes.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Layer 5 skill surface. Spec: R16. Phase: Phase 5. Parallel with Task 31. Front-matter: `name: requirements-write`.
- **Verification**: `wc -l skills/requirements-write/SKILL.md | awk '{print $1}'` ≤50; `grep -c "project\.md\|area\.md" skills/requirements-write/SKILL.md` ≥2.
- **Status**: [ ] pending

### Task 33: Rewrite `skills/requirements/SKILL.md` as thin orchestrator
- **Files**: `skills/requirements/SKILL.md`
- **What**: Replace the existing 348-line procedural skill with a ≤30-line thin orchestrator that invokes `/requirements-gather` then `/requirements-write` in sequence. Preserve user-facing entry point `/cortex-core:requirements [area]` so existing callers and prose references continue to work.
- **Depends on**: 31, 32
- **Complexity**: simple
- **Context**: Layer 5 skill surface. Spec: R17. Phase: Phase 5.
- **Verification**: `wc -l skills/requirements/SKILL.md | awk '{print $1}'` ≤30; `grep -c "/requirements-gather\|requirements-gather"` ≥1; `grep -c "/requirements-write\|requirements-write"` ≥1.
- **Status**: [ ] pending

### Task 34: Retire `skills/requirements/references/gather.md`
- **Files**: `skills/requirements/references/gather.md` (delete); search and remove any live references in active source
- **What**: Delete the 232-line procedural file. Scan active source (excluding `.git`, `docs/internals`, this lifecycle's dir, `cortex/lifecycle/archive`, `cortex/research`, `cortex/backlog`, `tests`) for live references to `references/gather.md` and remove them. Essential decision criteria already absorbed into Task 31's SKILL.md.
- **Depends on**: 31, 33
- **Complexity**: simple
- **Context**: Layer 5 skill surface. Spec: R18. Phase: Phase 5.
- **Verification**: `test ! -f skills/requirements/references/gather.md`; `grep -rln "references/gather.md\|requirements/references/gather" . --exclude-dir=.git --exclude-dir=docs/internals --exclude-dir=cortex/lifecycle/requirements-skill-v2 --exclude-dir=cortex/lifecycle/archive --exclude-dir=cortex/research --exclude-dir=cortex/backlog --exclude-dir=tests` returns nothing.
- **Status**: [ ] pending

### Task 35: Verify total skill-line budget
- **Files**: none (verification task)
- **What**: Run the R19 total-line-count check across the three skill files. If budget is exceeded, trim — most likely from the orchestrator or write skill before touching gather.
- **Depends on**: 31, 32, 33
- **Complexity**: trivial
- **Context**: Layer 5 verification. Spec: R19. Phase: Phase 5.
- **Verification**: `wc -l skills/requirements/SKILL.md skills/requirements-gather/SKILL.md skills/requirements-write/SKILL.md | tail -1 | awk '{print $1}'` ≤160.
- **Status**: [ ] pending

### Task 36: Author end-to-end routing test
- **Files**: `tests/test_requirements_skill_e2e.py` (new)
- **What**: Hermetic test that exercises `/cortex-core:requirements observability` (or any existing area name) through `/requirements-gather` → `/requirements-write` and asserts a valid `cortex/requirements/{area}.md` is produced. Mock the user-interview surface with canned answers; if the orchestrator dispatches to a real model surface, mock that dispatch deterministically. Fails if either sub-skill is not invoked, if the artifact is not written to the expected path, or if the artifact lacks the required template sections.
- **Depends on**: 31, 32, 33
- **Complexity**: complex
- **Context**: Layer 5 verification. Spec: R20. Phase: Phase 5. Test function shape: `test_requirements_routes_through_gather_then_write(tmp_path, mock_dispatch) -> None`.
- **Verification**: `test -f tests/test_requirements_skill_e2e.py`; `python3 -m pytest tests/test_requirements_skill_e2e.py -v` exits 0.
- **Status**: [ ] pending

### Task 37: Confirm plugin-mirror auto-regeneration
- **Files**: `plugins/cortex-core/skills/requirements-gather/`, `plugins/cortex-core/skills/requirements-write/`, `plugins/cortex-core/skills/requirements/` (all auto-mirrored by pre-commit hook)
- **What**: After Tasks 31-34 land, the pre-commit dual-source hook regenerates the plugin mirror entries. Confirm both new skills appear in `plugins/cortex-core/skills/`. If `bin/cortex-check-parity` flags any divergence, fix the underlying canonical source rather than editing the mirror directly.
- **Depends on**: 31, 32, 33, 34
- **Complexity**: trivial
- **Context**: Layer 5 skill surface (parity hygiene). Spec: R21. Phase: Phase 5.
- **Verification**: `find plugins/cortex-core/skills -maxdepth 2 -type d -name "requirements-*" | wc -l` ≥2; `bin/cortex-check-parity` exits 0.
- **Status**: [ ] pending

---

## Risks

- **Layer 0 reference under-specifies the loader contract** — if `load-requirements.md` is too terse (`What/Why, not How`), Layer 2 consumers may interpret tag-matching inconsistently. Mitigation: Task 5 explicitly co-locates the Suggested-Update parser predicate with the loader reference so contracts are reviewable in one place; the verifier script (Task 18) provides a downstream integrity check.
- **R6 tag backfill miscategorizes a lifecycle** — assigning the wrong tag set to an existing `index.md` causes the new loader to load wrong area docs. Mitigation: derive tags strictly from parent backlog item's `tags:`; for `parent_backlog_id: null`, write `[]` and let the fallback fire; the v1 heuristic was already imperfect, so worst case matches v1.
- **Layer 3 review.md gate loops indefinitely** — a buggy max-retry counter could cause the reviewer to redispatch beyond 2. Mitigation: structural test for the retry count via the existing lifecycle test suite; the `drift_protocol_breach` event itself is the escape hatch and is observable in events.log.
- **Token trim removes a section a consumer references by anchor** — caught in Task 22 preflight memo; deferring or moving to `## Optional` resolves it.
- **Plugin-mirror regeneration fails on the new skill directories** — Task 37 is positioned last in Layer 5 specifically because the canonical sources must land first; pre-commit hook regenerates from there. If the hook is broken, fix the hook (separate ticket) rather than editing mirrors.
- **Historical drift remediation (Task 8) destabilizes archived lifecycles** — script writes to `cortex/lifecycle/archive/*/review.md` via reviewer redispatch. Mitigation: dry-run mode in Task 7's script; commit batches separately; per-artifact failure is tolerated (≤1 unfixed allowed).
- **e2e test (Task 36) becomes flaky due to dispatch mocking** — if the orchestrator's invocation surface changes between gather and write, the mock must keep pace. Mitigation: mock at the lowest stable dispatch boundary; test asserts on artifact file presence + section structure rather than on the dispatch call shape.
- **Layer cadence assumes Layer 0 ships clean** — if the shared `load-requirements.md` reference needs revision after Layer 2 adoption, all Layer 2 consumers may need re-edits. Mitigation: Layer 2 consumer edits reference the shared file by path, so a revision to the reference propagates without consumer edits; only a structural breaking change (e.g., new required step in the loader) would force consumer re-edits.

## Acceptance

The plan is complete when, in order of layer:

- **Layer 0**: `skills/lifecycle/references/load-requirements.md` exists with documented tag-matching + fallback (R1); `drift_protocol_breach` is registered with a 6-field payload contract in `bin/.events-registry.md` (R7 subset); `tiktoken` is installable (R10 prerequisite); the Suggested-Update structural contract is documented (R7 contract).
- **Layer 1**: All 10 affected `cortex/lifecycle/*/index.md` files carry `tags:` (R6); ≥7 of 8 historical drift artifacts now contain `## Suggested Requirements Update` (R8).
- **Layer 2**: 6/6 non-exempt consumers reference the shared loading protocol; critical-review's exemption is documented (R2, R3, R4, R5).
- **Layer 3**: review.md enforces the Suggested Update section with max-retry=2 (R7); report.py surfaces `drift_protocol_breach` (R7); `verify-conditional-loading.py` exits 0 (R12 prep); `bin/cortex-requirements-parity-audit` is executable and wired via `just` (R9); token-budget tool runs (R10 prerequisite).
- **Layer 4**: `cortex/requirements/project.md` ≤1,200 cl100k_base tokens (R10); `## Optional` H2 present with prunability prose (R11); verifier exits 0 against the trimmed parent (R12); 4 area-doc spot-checks recorded in `area-audit.md` with ≥12 total (R13); Project Boundaries clarifies discovery/backlog inline status (R14).
- **Layer 5**: `/requirements-gather` ≤80 lines (R15); `/requirements-write` ≤50 lines (R16); `/requirements` ≤30 lines (R17); `references/gather.md` removed with no live references (R18); combined ≤160 lines (R19); e2e test passes (R20); plugin mirror regenerated (R21).

All acceptance greps and script exit codes specified per requirement in the spec must return as specified. PR cadence — 6 PRs (one per layer) recommended; revertibility is per-layer.
