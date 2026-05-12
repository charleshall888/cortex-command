# Specification: Reduce boot-context surface (CLAUDE.md + SKILL.md)

## Problem Statement

Every Claude Code session against cortex-command pays ~2,700 tok of always-loaded (L1) context from CLAUDE.md (67 lines, ~700 tok) and 13 SKILL.md `description:` + `when_to_use:` fields (~8,281 chars combined, ~2,000 tok). Several SKILL.md descriptions contain paraphrase/redundancy that doesn't aid routing; CLAUDE.md contains policy entries that are reference-not-instruction; four SKILL.md bodies (`diagnose` 489, `overnight` 409, `critical-review` 369, `lifecycle` 365 lines) are large L2 surfaces that compound when multiple skills trigger in one session. This work shrinks both L1 and L2 surfaces measurably without regressing skill auto-routing precision.

## Requirements

1. **Baseline measurement**: Capture the active skill-listing payload before any compression to anchor success criteria.
   - Acceptance: `lifecycle/reduce-boot-context-surface-claudemd-skillmd/baseline.md` exists and records: (a) total line count of CLAUDE.md (today: 67); (b) per-skill combined `description:` + `when_to_use:` character count for all 13 skills; (c) sum of those character counts (today: ~8,281); (d) per-skill body line counts; (e) output of `/doctor` skill-listing-budget inspection if accessible (note tooling gap if not). Verify with `test -f lifecycle/reduce-boot-context-surface-claudemd-skillmd/baseline.md && grep -c '^|' lifecycle/reduce-boot-context-surface-claudemd-skillmd/baseline.md` ≥ 13 (one row per skill).

2. **Test-fixture expansion prerequisite**: Before any description compression, expand `tests/fixtures/skill_trigger_phrases.yaml` to enforce must-contain trigger phrases for all 13 skills (currently covers 4: lifecycle, refine, critical-review, discovery). To prevent the fixture from rationalizing compression rather than constraining it, the fixture is authored and merged as a SEPARATE commit, landed before any R5 work. Each skill's entry MUST list at least 3 phrases. Each phrase MUST be one of: (a) the canonical slash-command name (e.g., `/cortex-core:commit`), (b) a multi-word imperative utterance a user would naturally speak to invoke the skill (e.g., "commit these changes"), or (c) a path or file-shape token used for path-based routing (e.g., `skills/`, `bin/cortex-*`). Single-word generic phrases (`commit`, `pr`) are NOT permitted as the sole entry for a skill.
   - Acceptance: `python -c "import yaml; d=yaml.safe_load(open('tests/fixtures/skill_trigger_phrases.yaml')); print(len(d)); print(min(len(v.get('must_contain',[])) for v in d.values()))"` prints `13` on the first line and `>= 3` on the second. `pytest tests/test_skill_descriptions.py` exits 0. The R2 commit lands in a separate PR from R5's compression commits; verify via `git log --oneline lifecycle/reduce-boot-context-surface-claudemd-skillmd/` showing fixture-expansion commit precedes any SKILL.md description edit.

3. **Lever D — CLAUDE.md policy extraction**:
   - OQ6 (Tone/voice policy, lines 61-65) extracts to `docs/policies.md` with a one-line pointer in CLAUDE.md (`Tone/voice policy: see docs/policies.md`).
   - OQ3 (MUST-escalation policy, lines 51-59) **stays in CLAUDE.md** (review-gate principle: policies that act as always-loaded review-gates stay L1; reactive-only policies become L2).
   - The 100-line threshold rule (line 67) is removed entirely.
   - CLAUDE.md lines L39 (commit-skill convention), L42 (frontmatter convention — see Requirement 4), L46-48 (cortex-jcc / dual-source guidance), L49 (overnight-docs source of truth) all stay.
   - Acceptance: `wc -l CLAUDE.md` reports ≤ 60 lines. `test -f docs/policies.md` exits 0. `grep -c "Tone/voice policy: see docs/policies.md" CLAUDE.md` = 1. `grep -c "CLAUDE.md is capped at 100 lines" CLAUDE.md` = 0. `grep -c "## MUST-escalation policy" CLAUDE.md` = 1.

4. **CLAUDE.md L42 frontmatter convention update**: Update L42 to mention `when_to_use:` as an optional frontmatter field now that 4 cortex skills use it and Claude Code documents it (per-research finding).
   - Acceptance: `grep -c "when_to_use" CLAUDE.md` ≥ 1.

5. **Lever A — Description and `when_to_use:` compression** (after Requirement 2 ships): For every SKILL.md across all 13 skills, compress the combined `description:` + `when_to_use:` content. The cap is **non-uniform** because routing-pressure skills carry irreducible content (disambiguation prose, path-based routing tokens) that compression cannot remove:
   - **Routing-pressure cluster** (`critical-review`, `lifecycle`, `discovery`, `refine`, `dev`, `research`): ≤ **1000 chars** combined desc+wtu.
   - **All other skills** (`backlog`, `commit`, `pr`, `diagnose`, `morning-review`, `overnight`, `requirements`): ≤ **400 chars** combined desc+wtu. (Note: `requirements` is also subject to R6's stricter ≤ 200-char cap; R6 takes precedence where stricter.)
   
   Compression removes paraphrase, redundant trigger-phrase repetition, and mechanism-explanation prose; it preserves all trigger phrases, disambiguation language, and path-based routing tokens. Disambiguation prose stays in `when_to_use:` — it MUST NOT migrate to the SKILL.md body (body content is L2 and the routing model does not see it at routing time).
   - Acceptance: For each `skills/*/SKILL.md` in the routing-pressure cluster, combined byte count of `description:` + `when_to_use:` ≤ 1000. For each other SKILL.md, combined byte count ≤ 400. Verify with the byte-count utility (Requirement 11). `pytest tests/test_skill_descriptions.py` exits 0 post-compression (the expanded fixture from Requirement 2 enforces trigger-phrase preservation across all 13 skills; the path-routing assertion from Requirement 9 protects lifecycle's path enumeration).

6. **Lever B — `requirements` SKILL.md description trim**: The `requirements` skill (`disable-model-invocation:true`) costs L1 tokens with zero routing benefit. Trim its description to a single-sentence stub describing the slash-command invocation purpose.
   - Acceptance: `skills/requirements/SKILL.md` `description:` field is ≤ 200 chars. `pytest tests/test_skill_descriptions.py` exits 0.

7. **Lever C — SKILL.md body trimming** (Level 2 reduction): For each of `diagnose`, `overnight`, `critical-review`, `lifecycle` SKILL.md, extract reference content (procedural detail, worked examples, format templates) to `skills/<name>/references/<topic>.md` files following the established pattern in `skills/lifecycle/references/`. SKILL.md bodies retain operational protocol, decision gates, and pointers; references hold the procedural detail.
   - Acceptance: Each of `wc -l skills/diagnose/SKILL.md`, `wc -l skills/overnight/SKILL.md`, `wc -l skills/critical-review/SKILL.md`, `wc -l skills/lifecycle/SKILL.md` reports ≤ 250 lines. `test -d skills/diagnose/references && test -d skills/overnight/references && test -d skills/critical-review/references && test -d skills/lifecycle/references` exits 0 (lifecycle already has `references/`; the others get newly-created directories).
   - Acceptance: `pytest tests/test_skill_size_budget.py` exits 0. No new `size-budget-exception` markers introduced.

8. **L1 reduction success criterion**: The overall reduction is verified via the file-level gates already specified in R3 (CLAUDE.md ≤ 60 lines), R5 (per-skill non-uniform caps: routing-pressure cluster ≤ 1000 chars, others ≤ 400 chars combined desc+wtu), and R6 (`requirements` ≤ 200 chars). The previous "ratio of byte-count totals" target is dropped because byte-count ratios are proxy bookkeeping — they don't observe loaded context, only file content, and the percentage target was arithmetically inconsistent with realistic content profiles. The aggregate reduction is whatever falls out of the per-file gates.
   - Acceptance: `lifecycle/reduce-boot-context-surface-claudemd-skillmd/post-trim-measurement.md` records the post-trim measurements (per-skill combined desc+wtu, CLAUDE.md line count, body line counts for the 4 large skills) alongside the baseline values from Requirement 1 — for the morning report and future-reference. The file documents the absolute reduction in each surface; no pass/fail ratio is checked here because R3/R5/R6/R7's per-file caps are the binding gates.

9. **Skill-routing non-regression**: The existing description-snapshot test plus the expanded fixture (Requirement 2) pass after every compression batch. A cross-skill disambiguation regression test asserts that the routing-pressure cluster (`dev` / `lifecycle` / `refine` / `research` / `discovery`) preserves disambiguation post-compression. A path-routing assertion specifically protects lifecycle's editing-restricted-paths enumeration, which is non-phrase routing data that substring tests miss without explicit listing.
   - Acceptance: `pytest tests/test_skill_descriptions.py` exits 0. A new test (e.g., `tests/test_skill_routing_disambiguation.py`) exists and exits 0; the test fixture lists at least 3 trigger phrases per routing-pressure skill that MUST land on that skill's `description:` or `when_to_use:` (substring check at minimum; if a routing-call API surfaces, prefer that).
   - Path-routing acceptance: the new test asserts that the concatenated `description:` + `when_to_use:` of `skills/lifecycle/SKILL.md` contains all of these substrings: `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-`, `cortex_command/common.py`. Verify by adding these path tokens to the lifecycle entry in `tests/fixtures/skill_trigger_phrases.yaml` under a `must_contain_paths:` key (distinct from `must_contain:` so phrase-vs-path distinction is observable in the fixture).

10. **Plugin-mirror regeneration**: The pre-commit hook regenerates `plugins/cortex-core/skills/*/SKILL.md` from canonical sources. The mirror is **filtered**, not byte-identical: `disable-model-invocation:true` skills (`morning-review`, `overnight`) are excluded from the mirror by design. The spec acknowledges this filter; the implementation phase verifies the filter behavior is preserved post-trim.
   - Acceptance: After running the pre-commit hook, `diff -r --brief skills plugins/cortex-core/skills` shows only the expected `morning-review` and `overnight` exclusions plus any other intentional mirror filters discovered during implementation. `pytest tests/test_plugin_mirror_parity.py` exits 0.

11. **Byte-count utility**: A small utility script measures combined `description:` + `when_to_use:` bytes per skill, used by both Requirement 1 (baseline) and Requirement 8 (post-trim). The script is invoked by `just` recipe.
   - Acceptance: `just measure-l1-surface` exits 0 AND its stdout contains at least 14 lines matching `^[a-z-]+\s+\d+$` (13 skill rows + 1 total row). The script lives at `bin/cortex-measure-l1-surface` to align with the SKILL.md-to-bin parity gate; `bin/cortex-check-parity` exits 0 after the script is added (parity satisfied via at least the new `justfile` recipe reference).

## Non-Requirements

- **Trigger-phrase relocation to non-`description:` frontmatter** (e.g., a new `triggers:` array) is NOT pursued. Per research, Claude Code concatenates `description:` and `when_to_use:` for routing — moving content between them does not reduce L1 cost. The empirical loader test for genuinely-new frontmatter routing fields remains out-of-scope.
- **Skill deletion** is NOT performed in this work. No skill emerges as zero-value from research; the per-PR "verified zero downstream consumers" audit required by the workflow-trimming doctrine is a separate effort and tickets via a separate backlog item if pursued.
- **Plugin-manifest split** (Alternative E — splitting `cortex-core` into smaller plugins so users install only what they need) is NOT pursued. Scoped as a follow-up backlog item if always-on cost grows with future skill additions.
- **Code-level MUST-policing** (e.g., a commit-msg hook scanning for new MUST/CRITICAL/REQUIRED additions and requiring evidence-artifact links) is NOT built here. Future ticket; would enable OQ3 to eventually move to `docs/policies.md`.
- **CLAUDE.md restructuring** beyond the OQ6 extraction, 100-line-rule removal, and L42 update is NOT performed. L39, L46-48, L49 stay where they are.
- **`disable-model-invocation:true` skill description trim for `morning-review` and `overnight`** is NOT pursued. The plugin mirror filters them out — compression saves L1 tokens only in maintainer dogfooding sessions, not for downstream cortex-core consumers. Disproportionate effort.

## Edge Cases

- **A skill's combined desc+wtu cannot be reduced to its applicable cap (1000 for routing-pressure cluster, 400 for others) without losing trigger-phrase coverage or path-routing tokens**: Surface the specific skill in `post-trim-measurement.md` with: (a) the measured minimum-achievable size while preserving all routing data, (b) a one-line rationale for what cannot be cut, (c) the gap to the cap. Do not strip routing data to hit the cap. The cap is a target with documented escape conditions, not a hard line.
- **`/doctor` is unavailable or doesn't report skill-listing-budget data**: Acceptable. Fall back to byte-count and estimated-token-cost (4 chars/token approximation) for Requirements 1 and 8. Note the tooling gap in `baseline.md`.
- **Expanding the fixture to 13 skills surfaces existing test-failures**: If the new fixture's must-contain phrases are not currently in some skill's description, EITHER add the missing phrase to the skill (preferred — closes a routing-recall gap) OR refine the fixture's must-contain set (only if the phrase is wrong, not a routing-recall gap). Document the choice per-skill in the implementation commit message.
- **Body trimming a SKILL.md breaks an internal cross-reference**: For example, lifecycle SKILL.md references `${CLAUDE_SKILL_DIR}/references/plan.md` — if reference reorganization changes the file structure, every cross-reference must update atomically. The implementation phase verifies via grep that no reference path is left dangling.
- **Pre-existing MUST language is grandfathered**: OQ3 stays in CLAUDE.md; OQ6 moves to `docs/policies.md`. Per the existing MUST-escalation policy, relocating pre-existing MUST/CRITICAL/REQUIRED language is NOT "adding or restoring" — the evidence-artifact gate does not fire. Description-compression edits that PRESERVE existing MUSTs are exempt; if a compression edit INTRODUCES new MUST language, the evidence-artifact gate applies per CLAUDE.md L51-59 (avoid: prefer soft positive-routing phrasing per the policy's default for new authoring).
- **Plugin mirror diverges in ways research didn't surface**: Implementation runs the pre-commit hook on a clean state first to confirm the current mirror baseline before making changes. Any new filter rules or transformations discovered are documented in `baseline.md`.
- **Listing-budget truncation is currently active**: If `/doctor` reports the skill-listing budget is overflowing today, compression is reducing already-truncated tail rather than effective context. This is acceptable — the cure is the same — but `baseline.md` notes the truncation state so success-criterion verification is honest about what's being reduced.

## Changes to Existing Behavior

- **MODIFIED: CLAUDE.md** — drops from 67 to ≤ 60 lines. OQ6 extracts to `docs/policies.md`. 100-line threshold rule removed. L42 frontmatter convention updated to mention `when_to_use:`.
- **ADDED: docs/policies.md** — new file holding OQ6 (initially) and any future reactive-only policies.
- **MODIFIED: tests/fixtures/skill_trigger_phrases.yaml** — extends from 4-skill coverage to 13-skill coverage.
- **MODIFIED: All 13 skills/*/SKILL.md description fields** — combined desc+wtu compressed with non-uniform caps: routing-pressure cluster (critical-review, lifecycle, discovery, refine, dev, research) ≤ 1000 chars; other 7 skills ≤ 400 chars; `requirements` ≤ 200 chars (R6). Paraphrase and mechanism-explanation prose removed; trigger phrases, disambiguation language, and path-based routing tokens preserved.
- **MODIFIED: skills/requirements/SKILL.md description** — trimmed to a one-sentence stub.
- **MODIFIED: skills/diagnose/SKILL.md, skills/overnight/SKILL.md, skills/critical-review/SKILL.md, skills/lifecycle/SKILL.md** — bodies trimmed to ≤ 250 lines via extraction to `references/<topic>.md` files.
- **ADDED: skills/diagnose/references/, skills/overnight/references/, skills/critical-review/references/** — new directories holding extracted reference content (lifecycle already has `references/`; expanded).
- **ADDED: tests/test_skill_routing_disambiguation.py (or equivalent)** — new test asserting routing-pressure cluster disambiguation.
- **ADDED: Byte-count utility** (likely `bin/cortex-measure-l1-surface` + `just measure-l1-surface`) for baseline/post-trim measurement.
- **MODIFIED: plugins/cortex-core/skills/*/SKILL.md** — auto-regenerated mirrors reflect canonical-source changes; the existing dmi:true filter behavior is preserved.
- **REMOVED: CLAUDE.md 100-line threshold rule** — the meta-rule itself is removed because policy extraction is now driven by the principled "review-gate vs. reactive" distinction, not a line-count trigger.

## Technical Constraints

- **Claude Code skill-listing contract**: `description:` and `when_to_use:` are concatenated for routing in the skill listing; combined cap is 1,536 chars per skill (truncation occurs above this). Cortex's per-skill cap of 800 chars sits comfortably below this with margin.
- **SKILL.md size cap** (`requirements/project.md` L30): 500 lines per file enforced by `tests/test_skill_size_budget.py`. Lever C's ≤ 250-line target is well within cap.
- **SKILL.md-to-bin parity gate** (`bin/cortex-check-parity`): every `bin/cortex-*` script must be referenced from at least one in-scope SKILL.md / requirements / docs / hooks / justfile / tests file. Description compression must not delete the last reference to any `bin/cortex-*`. The new `bin/cortex-measure-l1-surface` utility must be referenced from at minimum a `justfile` recipe (or a SKILL.md / docs file).
- **Pre-existing MUST grandfathering** (CLAUDE.md L51-59): relocating OQ6 from CLAUDE.md to `docs/policies.md` does not trigger the evidence-artifact gate. New MUST language in description rewrites IS subject to the gate — prefer soft positive-routing phrasing per the policy's default for new authoring.
- **No tone-shaping in shipped files** (CLAUDE.md L61-65): compression must not introduce warm/conciliatory/validation phrasing in SKILL.md frontmatter or CLAUDE.md.
- **Workflow-trimming doctrine** (`requirements/project.md` L23): does not apply here — no skills are being deleted. Bundled C does not constitute skill retirement; it's body-level reorganization within the existing skill surface.
- **References pattern** (`skills/lifecycle/references/` as canonical): use `${CLAUDE_SKILL_DIR}/references/<name>.md` substitution syntax in body cross-references. The pattern is established for `lifecycle`, `morning-review`, `discovery`, `refine`; `diagnose`, `overnight`, `critical-review` adopt the same pattern.
- **Plugin mirror is filtered**: `plugins/cortex-core/skills/` excludes `disable-model-invocation:true` skills (`morning-review`, `overnight`). The pre-commit regeneration hook preserves this filter. Any deviation is a parity bug.
- **Lifecycle-required edit paths**: editing `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*` requires a lifecycle (this ticket's lifecycle covers all such edits). CLAUDE.md and `docs/policies.md` are NOT under the editing-restricted paths.

## Open Decisions

None. All research-deferred open questions resolved during the structured interview.
