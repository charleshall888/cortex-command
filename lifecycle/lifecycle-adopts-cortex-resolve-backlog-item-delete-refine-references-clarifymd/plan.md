# Plan: Lifecycle adopts cortex-resolve-backlog-item, delete refine clarify.md, simplify helper to slugify-only

## Overview

Land the spec in three sequenced commits within one PR: (A) gate-commit a frozen pre-removal baseline of the union-predicate's behavior on a curated input set, (B) remove Predicate A from `bin/cortex-resolve-backlog-item` and assert post-removal divergences either match the baseline or carry per-case judgment rows, (C) rewrite `skills/lifecycle/references/clarify.md` §1 to invoke the helper, delete `skills/refine/references/clarify.md`, retarget refine's SKILL.md to a bare-relative cross-skill path, and rebuild the plugin mirror. After the merge-meaningful units land, a manual two-shot smoke test under both invocation layouts (refine direct + lifecycle delegating into refine) records (layout, backlog-id, exit-status) tuples in the PR description per Requirement 8.

## Tasks

### Task 1: Add Step 5a baseline-capture test + fixture
- **Files**: `tests/test_resolve_backlog_item.py` (extend), `tests/fixtures/predicate_a_baseline.json` (new)
- **What**: Add a `test_predicate_a_baseline_capture` test that runs the curated input set against the **current** Predicate-A ∪ Predicate-B helper over the live `backlog/[0-9]*-*.md` items and writes (input, exit-code, resolved-filename-or-None) tuples to a fixture file. The fixture is checked in as the frozen pre-removal baseline.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Test extension to existing 679-line `tests/test_resolve_backlog_item.py`. Curated inputs MUST cover all categories enumerated in spec R5a: numeric IDs (including zero-padded), kebab slugs, title fuzzy matches, uppercase inputs, inputs with punctuation, ambiguous-multi inputs, no-match inputs. Plus ≥3 reverse-engineered Predicate-A-only candidates, derived by inspecting current backlog titles for shapes where slugify strips characters: backticks (e.g. `006-make-just-setup-additive`, title `Make \`just setup\` additive by default`), parentheses, slashes/underscores in titles, dot/period-bearing version numbers (e.g. `v4.7`), internal multi-spaces. Invocation pattern: subprocess `bin/cortex-resolve-backlog-item` with each input, capture (input, returncode, parsed-filename-or-None). Fixture is `json.dumps(list_of_tuples, indent=2)` written to `tests/fixtures/predicate_a_baseline.json`. Use `CORTEX_BACKLOG_DIR` env var if test isolation is needed (helper honors it per `bin/cortex-resolve-backlog-item:213`); otherwise let the helper resolve `backlog/` upward from cwd.
- **Verification**: `pytest tests/test_resolve_backlog_item.py -v -k baseline_capture` exits 0 — pass if exit code = 0; AND `python3 -c "import json; assert len(json.load(open('tests/fixtures/predicate_a_baseline.json'))) >= 10"` exits 0 — pass if exit code = 0.
- **Status**: [x] complete

### Task 2: Commit baseline (cluster A)
- **Files**: `tests/test_resolve_backlog_item.py`, `tests/fixtures/predicate_a_baseline.json`
- **What**: Run `/cortex-core:commit` with the new baseline-capture test and fixture. This commit is the regen-friendly anchor: if curated inputs need extension later in the PR, the fixture can be regenerated and re-reviewed against this commit's frozen baseline.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: No canonical-mirror paths touched (tests/ is not mirrored), so no `just build-plugin` needed. Use `/cortex-core:commit`. Subject under 72 chars, e.g. "Add Predicate-A baseline capture for #176". Body cites spec R5a and explains the gating-commit role.
- **Verification**: `git log -1 --pretty=%s` matches the subject pattern; `git show --stat HEAD --name-only` lists exactly the two files above — pass if both checks succeed.
- **Status**: [x] complete (commit 3337981)

### Task 3: Remove Predicate A from `_resolve_title_phrase`
- **Files**: `bin/cortex-resolve-backlog-item`
- **What**: In `_resolve_title_phrase` (L138-169), drop the `lower_input` derivation (L147), the `predicate_a` computation (L156-157), and the `predicate_a or predicate_b` union; gate match on `predicate_b` only. Update the function docstring (L142-145) to drop "Predicate A"/"Predicate B" naming and describe a single slugified-substring match. Update the parser epilog (L264-267) to collapse the two-line predicate block to one line: `slugify(input) ⊆ slugify(title)`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: The `_resolve_title_phrase` function is module-private (underscore prefix); no external callers. `slug_input = slugify(input_str)` MUST remain — it is also used at L354 and L375 in `main()` for empty-after-slugify detection (do not remove). After this task: function takes `items_with_fm`, computes `slug_input` and per-item `slug_title`, returns items where `slug_input ⊆ slug_title`, dedup by `path.name`. Header comment block at L31-36 ("Local slugify re-implementation") is unrelated and stays. The L376 inline comment ("Predicate A: empty lower(input)...") must also be removed since predicate-A naming is gone.
- **Verification**: `grep -c 'predicate_a' bin/cortex-resolve-backlog-item` = 0 — pass if count = 0; `grep -c 'lower_input' bin/cortex-resolve-backlog-item` = 0 — pass if count = 0; `grep -ciE 'Predicate A' bin/cortex-resolve-backlog-item` = 0 — pass if count = 0; `grep -c 'slug_input' bin/cortex-resolve-backlog-item` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete (also updated test_edge_empty_title_slugify to assert post-removal `[]` behavior — covered by R4 MODIFIED entry)

### Task 4: Add Step 5b divergence-assertion test
- **Files**: `tests/test_resolve_backlog_item.py`
- **What**: Add a `test_predicate_a_divergences_match_judgment` test that re-runs the same curated input set from Task 1 against the post-removal slugify-only helper and asserts each (input → outcome) tuple either (i) matches the baseline tuple loaded from `tests/fixtures/predicate_a_baseline.json`, or (ii) appears in an explicit `documented_divergences` list inside the test file with a per-case judgment (`bug-shaped` or `legitimate-feature`). Any unexpected divergence — a tuple that differs from baseline AND is not in `documented_divergences` — fails the test.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Same test file as Task 1. The `documented_divergences` is a Python list literal in the test module; each row is a dict with `input`, `baseline_outcome`, `post_outcome`, `judgment` (`"bug-shaped"` or `"legitimate-feature"`), and `rationale`. Empty list is acceptable when no divergence surfaces. The curated input set is the same one used by Task 1 — define it in a module-level constant (e.g. `CURATED_INPUTS`) shared between both tests so they exercise identical inputs. Helper invocation pattern: same subprocess pattern as Task 1.
- **Verification**: `grep -c 'documented_divergences' tests/test_resolve_backlog_item.py` ≥ 1 — pass if count ≥ 1; `grep -c 'test_predicate_a_divergences_match_judgment' tests/test_resolve_backlog_item.py` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 5: Curate per-case divergence judgments
- **Files**: `tests/test_resolve_backlog_item.py` (populate `documented_divergences`)
- **What**: Run the Task 4 test against the live backlog. For any divergence rows the test surfaces (baseline outcome differs from post-removal outcome, not in `documented_divergences`), classify each as `bug-shaped` or `legitimate-feature` per spec R5 per-case-judgment policy, and add the judgment row to `documented_divergences`. If any row is `legitimate-feature`, halt and surface to the user before merge — the spec requires either Predicate-A restoration with OQ3 evidence (events.log F-row + dispatch transcript) or explicit user override logged as a `divergence_accepted` event.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Per research §F6, the test author of `tests/test_resolve_backlog_item.py:300-389` documented an inability to construct a clean Predicate-A-only case across ~80 lines of comments. Expected outcome: zero divergences or all-bug-shaped, requiring either an empty `documented_divergences` list or a small list of bug-shaped rows. A `legitimate-feature` divergence is the failure mode that triggers the OQ3 escalation branch in spec Edge Cases; surface to user immediately.
- **Verification**: `pytest tests/test_resolve_backlog_item.py -v -k divergences_match_judgment` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (zero divergences surfaced; documented_divergences = [] is the curated state)

### Task 6: Rebuild plugin mirror for `bin/` change
- **Files**: `plugins/cortex-core/bin/cortex-resolve-backlog-item` (regenerated)
- **What**: Run `just build-plugin` to sync the modified `bin/cortex-resolve-backlog-item` into the plugin's `bin/` directory. The recipe at `justfile:516` uses `rsync -a --delete --include='cortex-*' --exclude='*' bin/ "plugins/$p/bin/"`; the dual-source pre-commit drift hook will block the next commit if mirror parity drifts.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Single command. No new files — `cortex-resolve-backlog-item` already exists in the plugin mirror; this just refreshes the content.
- **Verification**: `just build-plugin` exits 0 — pass if exit code = 0; `diff -q bin/cortex-resolve-backlog-item plugins/cortex-core/bin/cortex-resolve-backlog-item` exits 0 — pass if exit code = 0 (no diff).
- **Status**: [x] complete

### Task 7: Commit helper change + Step 5b assertion (cluster B)
- **Files**: `bin/cortex-resolve-backlog-item`, `tests/test_resolve_backlog_item.py`, `plugins/cortex-core/bin/cortex-resolve-backlog-item`
- **What**: Run `/cortex-core:commit` to land the helper Predicate-A removal (R4) + Step 5b assertion test (R5b) + curated judgments + plugin mirror sync atomically. Per spec OQ3 framing, the commit body links the Task 2 baseline commit SHA as the evidence anchor.
- **Depends on**: [3, 4, 5, 6]
- **Complexity**: simple
- **Context**: Use `/cortex-core:commit`. Subject under 72 chars, e.g. "Simplify cortex-resolve-backlog-item to slugify-only (#176)". Body cites Spec R4 and R5b plus the Task 2 baseline commit SHA. Pre-commit drift hook will pass because Task 6 synced the bin mirror.
- **Verification**: `git log -1 --pretty=%s` matches the subject pattern; `git show --stat HEAD --name-only` lists the three files above — pass if both checks succeed.
- **Status**: [x] complete (commit 4e77f8d)

### Task 8: Rewrite lifecycle clarify.md §1 to invoke the helper
- **Files**: `skills/lifecycle/references/clarify.md`
- **What**: Replace `skills/lifecycle/references/clarify.md` §1 "Resolve Input" (currently L7-L24) with a helper-invoking protocol modeled on `skills/refine/references/clarify.md` L7-L29: bash invocation block, the five-exit-code branch table (Exit 0/2/3/64/70), the JSON output schema (`filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`), and a title-phrase predicate explainer that documents the post-#176 **slugify-only** semantics (no Predicate-A wording). §2-§7 are byte-identical between the two files today and remain unchanged.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Source of the new §1 prose: `skills/refine/references/clarify.md` L7-L29, with one substantive edit — the title-phrase predicate paragraph at refine's L29 currently describes the Predicate A ∪ Predicate B union; rewrite that paragraph to describe the post-#176 single-predicate form: `slugify(input) ⊆ slugify(title)`, with both sides slugified symmetrically so case, punctuation, underscores, and slashes normalize away. Use soft-positive-routing form (no MUST/CRITICAL/REQUIRED) per spec Non-Requirements and CLAUDE.md OQ3 default. The Resolve Input section's heading style (`### 1. Resolve Input`) and the Note callout about implementation suggestions at refine's L23 are preserved verbatim.
- **Verification**: `grep -c 'cortex-resolve-backlog-item' skills/lifecycle/references/clarify.md` ≥ 1 — pass if count ≥ 1; `grep -c 'Exit 0' skills/lifecycle/references/clarify.md` ≥ 1 — pass if count ≥ 1; `grep -c 'Exit 2' skills/lifecycle/references/clarify.md` ≥ 1 — pass if count ≥ 1; `grep -c 'Exit 3' skills/lifecycle/references/clarify.md` ≥ 1 — pass if count ≥ 1; `grep -c 'Exit 64' skills/lifecycle/references/clarify.md` ≥ 1 — pass if count ≥ 1; `grep -c 'Exit 70' skills/lifecycle/references/clarify.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 9: Delete refine clarify.md and retarget refine SKILL.md to bare-relative path
- **Files**: `skills/refine/references/clarify.md` (delete), `skills/refine/SKILL.md` (modify L38, L65, L86)
- **What**: Delete `skills/refine/references/clarify.md`. In `skills/refine/SKILL.md`, retarget all three `references/clarify.md` mentions (L38 Exit-3 fallback description, L65 Step 3 protocol read, L86 §6 Sufficiency Criteria reference) to `../lifecycle/references/clarify.md` per spec R3 user decision. No `${CLAUDE_SKILL_DIR}/..` substitution.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Three call sites in `skills/refine/SKILL.md`. The bare-relative form `../lifecycle/references/clarify.md` has no precedent in the repo for cross-skill `..` traversal — its path-resolution semantics are asserted (anchor relative to the SKILL.md file's directory) and verified by Task 13's smoke-test matrix, not just by literal-string presence in this task's verification. After this task, no `references/clarify.md` references remain in `skills/refine/SKILL.md` that lack the `../lifecycle/` prefix.
- **Verification**: `test ! -f skills/refine/references/clarify.md` exits 0 — pass if exit code = 0; `grep -c '\.\./lifecycle/references/clarify\.md' skills/refine/SKILL.md` = 3 — pass if count = 3; `grep -cE '(^|[^/.])references/clarify\.md' skills/refine/SKILL.md` = 0 — pass if count = 0.
- **Status**: [x] complete

### Task 10: Rebuild plugin mirror for `skills/` changes
- **Files**: `plugins/cortex-core/skills/lifecycle/references/clarify.md` (regenerated), `plugins/cortex-core/skills/refine/references/clarify.md` (auto-pruned)
- **What**: Run `just build-plugin` to sync the lifecycle clarify.md rewrite and the refine clarify.md deletion through to the plugin mirror. The recipe at `justfile:509` uses `rsync -a --delete "skills/$s/" "plugins/$p/skills/$s/"`; `--delete` propagates the source-side deletion of refine's clarify.md to the mirror.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Single command. The mirror's lifecycle clarify.md is regenerated from canonical; the mirror's refine clarify.md is removed because the canonical no longer has it.
- **Verification**: `just build-plugin` exits 0 — pass if exit code = 0; `test ! -f plugins/cortex-core/skills/refine/references/clarify.md` exits 0 — pass if exit code = 0; `diff -q skills/lifecycle/references/clarify.md plugins/cortex-core/skills/lifecycle/references/clarify.md` exits 0 — pass if exit code = 0.
- **Status**: [x] complete

### Task 11: Run dual-source parity + lifecycle reference resolution tests
- **Files**: (read-only invocation: `tests/test_dual_source_reference_parity.py`, `tests/test_lifecycle_references_resolve.py`)
- **What**: Run both tests to confirm the canonical/mirror tree is in lockstep after the rebuild and lifecycle's reference paths still resolve correctly. The dual-source parity test's collected-pair count is expected to drop by 1 from the pre-#176 baseline (the refine clarify canonical/mirror pair is gone).
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Both tests are existing — `tests/test_dual_source_reference_parity.py` walks the canonical and mirror trees and asserts byte-identical parity for every collected pair; `tests/test_lifecycle_references_resolve.py` checks that paths referenced from lifecycle's SKILL.md and clarify.md resolve to existing files.
- **Verification**: `pytest tests/test_dual_source_reference_parity.py tests/test_lifecycle_references_resolve.py` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (test_lifecycle_references_resolve had a pre-existing latent bug exposed by the deletion — the slash-path regex over-matched `lifecycle/references/<file>.md` as feature citations when those are abbreviations for `skills/lifecycle/references/<file>.md`; added NON_FEATURE_SUBDIRS = {"references"} exclusion in `_extract_references`)

### Task 12: Commit lifecycle adoption + refine deletion + retarget + mirror sync (cluster C)
- **Files**: `skills/lifecycle/references/clarify.md`, `skills/refine/references/clarify.md` (deletion), `skills/refine/SKILL.md`, `plugins/cortex-core/skills/lifecycle/references/clarify.md`, `plugins/cortex-core/skills/refine/references/clarify.md` (deletion)
- **What**: Run `/cortex-core:commit` to land R1 + R2 + R3 + R6 atomically (per research §F9 atomicity recommendation). Pre-commit drift hook validates mirror parity on commit; Task 10 ensured parity holds.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: Use `/cortex-core:commit`. Subject under 72 chars, e.g. "Lifecycle adopts cortex-resolve-backlog-item; drop refine clarify (#176)". Body summarizes the three coupled requirements (R1 lifecycle §1 rewrite, R2/R3 refine deletion + retarget, R6 mirror auto-prune).
- **Verification**: `git log -1 --pretty=%s` matches the subject pattern; `git show --stat HEAD --name-only` includes all five files above — pass if both checks succeed.
- **Status**: [x] complete (commit 8268d08; also includes test_lifecycle_references_resolve.py NON_FEATURE_SUBDIRS fix and plugins/cortex-core/skills/refine/SKILL.md mirror sync)

### Task 13: Manual two-shot smoke test under both invocation layouts (R8)
- **Files**: PR description (interactive note recording the smoke-test result)
- **What**: Per spec R8, manually exercise the bare-relative cross-skill path under (Layout 1) `/cortex-core:refine <known-id>` direct invocation and (Layout 2) `/cortex-core:lifecycle <known-id>` delegating into refine. Record (layout, backlog-id, exit-status) for each layout in a one-line PR-description note. If either layout fails, the bare-relative form is invalidated and the spec must be revised to either substitute `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` or re-architect.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: Refine and lifecycle skill invocations are interactive Claude Code skills that cannot be executed from a shell command. Layout 2 is the runtime layout most likely to expose CWD-vs-file-relative resolution differences because lifecycle's SKILL.md L220 directs Claude to "Read `skills/refine/SKILL.md` verbatim" — the bare-relative path in refine's SKILL.md must resolve correctly when the active skill is lifecycle but the file containing the path is refine's. Cross-load anchor of inner `references/clarify-critic.md` references inside the loaded clarify.md must also be exercised (spec Edge Cases §"Cross-skill load cascade with §3a Critic Review").
- **Verification**: Interactive/session-dependent: refine and lifecycle invocations are interactive Claude Code skills that cannot be exercised from a shell — verification is a manual two-shot smoke test with the (layout, backlog-id, exit-status) tuple recorded in the PR description.
- **Status**: [x] skipped per user decision (R8 smoke test deferred; confidence based on textual path presence + standard relative-file resolution behavior, not live Layout 1/2 invocation)

## Verification Strategy

End-to-end verification spans three commit clusters and one manual smoke test:

1. **Cluster A gate** — Task 1's baseline-capture test passing with ≥10 entries in `tests/fixtures/predicate_a_baseline.json` confirms the pre-removal helper's behavior on the curated input set is frozen and reviewable.
2. **Cluster B gate** — Task 5's `test_predicate_a_divergences_match_judgment` passing confirms every (input → outcome) tuple either matches the baseline or has an explicit per-case judgment row. Any `legitimate-feature` row halts the lifecycle until OQ3 evidence is recorded or the user accepts the divergence on the record.
3. **Cluster C gate** — Task 11's `pytest tests/test_dual_source_reference_parity.py tests/test_lifecycle_references_resolve.py` passing confirms canonical/mirror parity holds and lifecycle's reference paths still resolve. The dual-source pre-commit drift hook (run automatically by `/cortex-core:commit` in Task 12) provides a second-line check.
4. **R8 smoke-test gate** — Task 13's manual two-shot smoke test confirms the bare-relative cross-skill path resolves under both invocation layouts; the (layout, backlog-id, exit-status) tuples land in the PR description as the recorded R8 evidence.

After Task 13, the full test suite (`just test`) is run from the merged branch to confirm no regressions in unrelated areas. Per spec Acceptance criteria, all `grep -c` checks and file-existence checks listed in Tasks 3, 8, 9, 10, 11 are the binary acceptance gates.

## Veto Surface

- **Bare-relative cross-skill path syntax (`../lifecycle/references/clarify.md`) has no precedent in the repo for cross-skill `..` traversal.** Path-resolution semantics are asserted (file-relative anchor) and verified only at Task 13 (manual smoke test). If the smoke test fails, the spec must be revised to use `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` (the substituted form is explicitly out of scope per spec Non-Requirements but is the named fallback). User may want to mandate the substituted form up front instead.
- **Bundling helper Predicate-A removal (R4) into the same ticket as lifecycle adoption (R1/R2/R3).** Spec rationale (causal entanglement: lifecycle's §1 prose documents the predicate semantics) justifies the bundle, but a reviewer may prefer to split. Splitting would require two separate baseline fixtures and two OQ3 records — strictly more work, but more reviewable.
- **Two-commit gating pattern for the OQ3 evidence record (Task 2 baseline commit + Task 7 helper-change commit).** Could collapse to a single test commit if regen-friendly granularity is judged unnecessary; the spec specifically calls for separate commits within the same PR.
- **Smoke-test layouts are restricted to the two named in spec R8.** Cross-load anchor of inner `references/clarify-critic.md` references must also be exercised inside Layout 2 (per spec Edge Cases §"Cross-skill load cascade with §3a Critic Review"), but no third smoke-test layout is added — this is included in Task 13's exercise of Layout 2 rather than as its own task.
- **Step 5a curated input categories enumerated by the spec are minima, not maxima.** Task 1's reverse-engineered Predicate-A-only candidates are required (≥3) but not pre-listed — the implementer derives them by inspecting current `backlog/[0-9]*-*.md` titles. A reviewer may want the candidate list named in this plan or in the spec; the spec leaves the derivation to the implementer.

## Scope Boundaries

Maps to spec Non-Requirements:

- `skills/discovery/references/clarify.md` is **not modified** — it is a separate semantic protocol (~65 lines, pre-research ideation gate). Post-#176 the repo retains two `clarify.md` files (lifecycle + discovery), not one.
- **No `${CLAUDE_SKILL_DIR}/..` substitution.** Refine's retargeted call sites use bare-relative paths only. The substituted form is the named fallback if Task 13's smoke test invalidates the bare form.
- **No `skills/_shared/` neutral location.** Lifecycle remains the canonical home; no new shared directory is introduced.
- **No symlink or build-time copy.** The deletion is permanent; refine references the surviving canonical via path.
- **No bundling with #175 (clarify-critic.md to canonical) or #184 (merge clarify+research into investigate.md).** Sibling tickets land independently. #176 is sequenced ahead of both per user decision.
- **No changes to §2–§7 of clarify.md.** Those sections are byte-identical between lifecycle and refine and remain unchanged.
- **No retroactive renaming or migration of v0.1.0 plugin paths.** Stale `plugins/cortex-interactive/...` references in research archives are out of scope.
- **No new MUST/CRITICAL/REQUIRED escalations** in lifecycle's clarify.md §1 prose. Soft-positive-routing form is used per CLAUDE.md OQ3 default-to-soft-positive-routing.
- **No splitting of Predicate-A removal into a separate ticket** — considered and rejected per spec Non-Requirements; causal entanglement justifies the bundle.
