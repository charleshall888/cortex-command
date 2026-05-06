# Plan: remove-fresh-evolve-and-retro-skills

## Overview

Hard-delete `/fresh`, `/evolve`, `/retro` and the session-feedback infrastructure across canonical sources, plugin mirrors, hooks, tests, init scaffolding, statusline, docs, CLAUDE.md policy text, justfile/gitignore, the dual-source parity test, and backlog cross-references — with this repo's 162 historical retros archived (not deleted) into `retros/archive/`. All 18 spec requirements land in a single PR; tasks below preserve the spec's Atomicity & Sequencing constraints (R3 canonical+regen together, R6 git-mv before .gitkeep delete, R13+R18 same commit, R2 after R1, R17 last gate).

## Tasks

### Task 1: Delete `/fresh`, `/evolve`, `/retro` canonical skill directories
- **Files**: `skills/fresh/` (delete dir), `skills/evolve/` (delete dir), `skills/retro/` (delete dir)
- **What**: `git rm -r` the three canonical skill directories. The `CLAUDE_AUTOMATED_SESSION` env-var callers (R8) live exclusively inside `skills/fresh/SKILL.md:16` and `skills/retro/SKILL.md:31,112,113` and disappear with this delete — R8 needs no separate edit.
- **Depends on**: none
- **Complexity**: simple
- **Context**: each dir contains a single `SKILL.md`. No other files. No symlinks to worry about. Verified via research that no canonical-source caller of `CLAUDE_AUTOMATED_SESSION` lives outside these three SKILL.md files. The three directories are referenced by the justfile SKILLS array and the parity test PLUGINS dict — those are deleted in Task 12.
- **Verification**: `test ! -d skills/fresh && test ! -d skills/evolve && test ! -d skills/retro` — pass if exit 0.
- **Status**: [x] complete (bundled into commit 7db592a by parallel session)

### Task 2: Delete plugin-tree skill mirror directories
- **Files**: `plugins/cortex-core/skills/fresh/` (delete dir), `plugins/cortex-core/skills/evolve/` (delete dir), `plugins/cortex-core/skills/retro/` (delete dir)
- **What**: `git rm -r` the three orphan mirror dirs. `just build-plugin` will not garbage-collect them because the regenerator iterates per-canonical-skill, and the canonical sources no longer exist after Task 1.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `tests/test_dual_source_reference_parity.py:_discover_pairs` globs canonical-side `skills/*/SKILL.md` and routes each to a plugin via the `PLUGINS` map; an orphan mirror dir without a canonical pair is invisible to the parity test, which is why R2 is a discrete deliverable. The justfile build-plugin recipe is at `justfile:472,498-502` (BUILD_OUTPUT_PLUGINS); inspection during research confirmed `rsync -a --delete` operates per-skill, not across the skills/ root.
- **Verification**: `test ! -d plugins/cortex-core/skills/fresh && test ! -d plugins/cortex-core/skills/evolve && test ! -d plugins/cortex-core/skills/retro` — pass if exit 0.
- **Status**: [x] complete (commit 1a5e100)

### Task 3: Strip both resume mechanisms from `hooks/cortex-scan-lifecycle.sh` and regenerate the cortex-overnight mirror
- **Files**: `hooks/cortex-scan-lifecycle.sh`, `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` (regenerated, not hand-edited)
- **What**: Three line-precise canonical deletions per the research (L67–75 fresh-resume detection block; L357–363 fresh_resume_prompt prefix in build-context-message; L368–372 `/clear`-recovery prose injection). After the canonical edit, run `just build-plugin` to regenerate the cortex-overnight mirror, then stage both diffs together (atomicity rule R3).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Hook structure post-edit retains: SESSION_ID injection (L7–13), session-migration across `/clear` (L31–65), pipeline-state detection (L77–173), phase detection (L175–313), active-feature determination (L320–353), build-context-message without resume prompt (L365–423), pipeline-context prepend (L425–477), agent-specific JSON output (L479–496). The `context=""` initialization at L359 must remain — only the conditional that overwrote it with `fresh_resume_prompt` is removed. The pre-commit dual-source drift hook fails if canonical and mirror are out of sync; running `just build-plugin` and staging both diffs in the same commit is the rule.
- **Verification**: `! rg -q 'fresh-resume|fresh_resume_prompt|/clear recovery' hooks/cortex-scan-lifecycle.sh` — pass if exit 0; `! rg -q 'fresh-resume|fresh_resume_prompt|/clear recovery' plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` — pass if exit 0; `bash tests/test_hooks.sh` — pass if exit 0 (after Task 4 lands).
- **Status**: [x] complete (commit 30b63a3)

### Task 4: Remove `fresh-resume-fires` and `fresh-resume-absent` test cases plus the shared fixture
- **Files**: `tests/test_hooks.sh`, `tests/fixtures/hooks/scan-lifecycle/pending-resume.json` (delete)
- **What**: Delete the two test blocks at L145–179 of `tests/test_hooks.sh` and the `pending-resume.json` fixture file. Other `scan-lifecycle/*` cases (no-lifecycle-dir L102–112, single-incomplete-feature L114–129, claude-output-format L131–143) stay untouched.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Both test cases reference the deleted hook code paths; `fresh-resume-fires` is currently failing per `backlog/170` and is being closed by this PR (Task 15 narrows #170's body). The fixture has no other consumer (verified during research). The `tests/test_hooks.sh` runner does not have an "exactly N tests" assertion — deletions are tolerated.
- **Verification**: `! rg -q 'fresh-resume-(fires|absent)|pending-resume\.json' tests/test_hooks.sh` — pass if exit 0; `test ! -f tests/fixtures/hooks/scan-lifecycle/pending-resume.json` — pass if exit 0; `bash tests/test_hooks.sh` exits 0.
- **Status**: [x] complete (commit c0adc93)

### Task 5: Stop scaffolding `retros/` in `cortex init` and update the init test suite
- **Files**: `cortex_command/init/scaffold.py`, `cortex_command/init/templates/retros/` (delete dir + its single `README.md`), `cortex_command/init/tests/test_scaffold.py`, `cortex_command/init/tests/test_settings_merge.py`
- **What**: Remove `"retros",` from `_CONTENT_DECLINE_TARGETS` (`cortex_command/init/scaffold.py:59` inside the L56–62 tuple). Delete the `cortex_command/init/templates/retros/` directory entirely (`_iter_template_files` at L187–211 auto-discovers, no manifest update needed). Update three test edits: drop `"retros/README.md"` from `SCAFFOLD_FILES` at `test_scaffold.py:69`; rewrite `test_update_preserves_user_edits` (L116–136) to use a different scaffold target (e.g., `backlog/README.md`) for the missing-file --update assertion at L129–130 and L135; remove the `assert not (repo / "retros" / "README.md").exists()` line at `test_scaffold.py:324` inside `test_content_aware_decline`. Also drop `"retros/README.md"` from the local `SCAFFOLD_FILES` tuple at `test_settings_merge.py:698` (inside L695–701).
- **Depends on**: none
- **Complexity**: complex
- **Context**: `_CONTENT_DECLINE_TARGETS` is the tuple of directories where existing user content suppresses scaffold overwrite. Pattern reference: surviving entries (`backlog`, etc.) follow the same shape. `_iter_template_files` walker uses `iterdir()`, so removing a template subdirectory cleanly removes it from the scaffold without further code changes. The `test_update_preserves_user_edits` test verifies that `--update` restores a missing scaffold file — switching the test fixture to `backlog/README.md` (or `lifecycle/README.md` if present) preserves the test's intent. Per Non-Requirements bullet 9, `cortex init --update` is NOT extended to actively prune `retros/README.md` from already-initialized user repos — those users get the manual cleanup instructions in Task 14's CHANGELOG bullet.
- **Verification**: `uv run pytest cortex_command/init/tests/` — pass if exit 0.
- **Status**: [x] complete (commit 9f29473)

### Task 6: Archive this repo's 162 retros into `retros/archive/` via `git mv`, then delete `retros/.gitkeep`
- **Files**: `retros/*.md` (move), `retros/archive/` (created via git mv destinations), `retros/.gitkeep` (delete)
- **What**: For each `retros/*.md` at the `retros/` root, run `git mv retros/<file>.md retros/archive/<file>.md`. After all 162 files are moved, delete `retros/.gitkeep` (no replacement `.gitkeep` is created in `retros/archive/` — `archive/` is non-empty after the move, so it's git-tracked without a placeholder). Per spec's Open Decisions resolution, the `.gitkeep` is deleted entirely (option (c) of the three considered).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `git mv` preserves history per file (renames detected automatically by `git log --follow`). The atomicity rule says `git mv` BEFORE `.gitkeep` delete so a partial state remains git-recoverable via `git checkout`. The `retros/archive/` path is referenced by `bin/cortex-archive-rewrite-paths:5,203` and `bin/cortex-archive-sample-select:18` exclusion logic — those still match `retros/archive/` correctly post-move (the `--exclude-dir=retros` recipe excludes the entire subtree). Existing files: `find retros -maxdepth 1 -name '*.md'` enumerates the 162 retros at PR-creation time.
- **Verification**: `[ -d retros/archive ] && [ "$(find retros -maxdepth 1 -name '*.md' | wc -l)" -eq 0 ] && [ ! -f retros/.gitkeep ]` — pass if exit 0; `[ "$(find retros/archive -maxdepth 1 -name '*.md' | wc -l)" -ge 50 ]` — pass if exit 0 (lower bound sanity check).
- **Status**: [x] complete (commit 17a327c)

### Task 7: Remove the `retro:N` indicator from `claude/statusline.sh`
- **Files**: `claude/statusline.sh`
- **What**: Delete the `_evolve_indicator=""` initialization at L241; delete the entire `# ---- Evolve count indicator ----` block at L570–601 (which counts unprocessed retros and reads `retros/.evolve-state.json`); delete the `[ -n "$_evolve_indicator" ] && { ... }` line-3 append clause at L637–639.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `claude/statusline.sh` is single-source — NOT mirrored to plugin trees, so no `just build-plugin` regeneration required. The other line-3 indicators (which the spec preserves) live in adjacent blocks; verified during research that they share no shell variables with the `_evolve_indicator` block. Users with 10+ accumulated retros will see this indicator vanish silently — the CHANGELOG bullet (Task 14) does not specifically call this out, but the broader `### Removed` entry covers it.
- **Verification**: `! rg -q 'evolve.*indicator|_evolve_indicator|retros/\.evolve-state' claude/statusline.sh` — pass if exit 0.
- **Status**: [x] complete (commit 185a94d)

### Task 8: Rewrite CLAUDE.md OQ3/OQ6/Repository Structure and update `backlog/157` cross-references
- **Files**: `CLAUDE.md`, `backlog/157-empirically-test-rules-file-tone-leverage-under-opus-47.md`
- **What**: In `CLAUDE.md`: delete L17 Repository Structure bullet for `retros/`; remove OQ3 evidence-artifact clause `(b) retros/<YYYY-MM-DD>*.md path + line citing the failure, OR` at L54 and re-letter the surviving (a)/(c) → (a)/(b); rewrite the surviving prose `Without one of these three artifact links` → `Without one of these two artifact links` (or rephrase to drop the count); remove OQ3 re-evaluation trigger clause `(b) 2+ separate retros/ entries cite OQ3's policy as itself causing under-escalation...` at L60 and re-letter (a)/(c) → (a)/(b); remove OQ6 re-evaluation clauses (b) and (c) at L66 (both retros-citation triggers) and the orphaned closing sentence `Triggers (b) and (c) require a counted threshold — single observation does not fire revisit.`; re-letter OQ6 surviving clauses (a)/(d)/(e) → (a)/(b)/(c). In `backlog/157-...md`: update four occurrences of `R7 trigger (d)` (lines 17, 33, 39, 44) to `R7 trigger (b)` (the post-rewrite letter for the empirical-tone-test trigger), or dereference by topic (e.g., "the empirical-tone-test trigger") so the cross-reference survives.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The exact pre-edit prose for OQ3/OQ6 is quoted verbatim in `lifecycle/remove-fresh-evolve-and-retro-skills/research.md` Web Research section under "CLAUDE.md exact OQ3/OQ6 quote text". CLAUDE.md is currently 68 lines; this rewrite removes lines, so the 100-line cap and the `docs/policies.md` extraction trigger remain not-engaged. Surviving evidence-artifact options after rewrite: (a) `lifecycle/<feature>/events.log` path + line, and (b) commit-linked transcript URL or quoted excerpt.
- **Verification**: `! rg -q 'retros' CLAUDE.md` — pass if exit 0; `! rg -q 'three artifact' CLAUDE.md` — pass if exit 0; `! rg -q 'trigger \(d\)' backlog/157-*.md` — pass if exit 0; `[ "$(wc -l < CLAUDE.md)" -le 100 ]` — pass if exit 0.
- **Status**: [x] complete (commit 40776e3)

### Task 9: Delete the Self-Improvement Loop section and EVOLVE node from `docs/agentic-layer.md`
- **Files**: `docs/agentic-layer.md`
- **What**: At L45 (mermaid Diagram A): delete the `EVOLVE["/cortex-core:retro → /evolve\nself-improvement loop"]` node. At L70–71: delete both edges `MAIN --> EVOLVE` and `EVOLVE -->|"new items"| BACKLOG`. At L142: drop `and any fresh-resume prompts` from Workflow Narrative 3's parenthetical, keep the rest. At L148–150: delete the entire `### 5. Self-Improvement Loop` section (heading + body). At L161: edit the hook-inventory table row description from `...overnight execution state, and fresh-resume prompts into context` → `...and overnight execution state into context`. At L255: drop `and any fresh-resume prompts` from the prose. Per Non-Requirements bullet 6, no replacement narrative is added — the diagram and surrounding prose are intentionally left without an automated MAIN→BACKLOG feedback edge.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Mermaid diagrams break silently on dangling node references — the deletion is mechanical (remove the node and BOTH inbound/outbound edges symmetrically). Verification of mermaid syntactic coherence is by inspection. The `### 5.` section is the only place in the doc that narrates the feedback loop; no other doc points at it.
- **Verification**: `! rg -q 'EVOLVE|fresh-resume|Self-Improvement Loop|self-improvement loop' docs/agentic-layer.md` — pass if exit 0.
- **Status**: [x] complete (commit f11d53a)

### Task 10: Scrub `/fresh`, `/evolve`, `/retro`, `retros` from setup, skills-reference, and overnight docs
- **Files**: `docs/setup.md`, `docs/skills-reference.md`, `docs/overnight-operations.md`
- **What**: In `docs/setup.md` at L94, L109, L147–148: drop `retros/,` from scaffolding directory enumerations; remove `retros/` and `retros/README.md` from the worked-example tree. In `docs/skills-reference.md` at L116–137: delete the entire `## Session Management` section including parent header, the three subsections `### fresh`, `### retro`, `### evolve`, and the trailing `---`. In `docs/overnight-operations.md` at L11: scrub the incidental "retro back-reference" stylistic mention (per spec R11's resolution of the deferred research question, the mention is removed).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The `## Session Management` section in `skills-reference.md` exists exclusively to document the three deleted skills; no other doc links into specific subsections of it (verified during research). The `--glob '!docs/internals/**'` exclusion in the verification grep covers internal-docs that may have unrelated retrospective-word usage.
- **Verification**: `! rg -q '\b(/fresh|/evolve|/retro|retros)\b' docs/ --glob '!docs/internals/**'` — pass if exit 0.
- **Status**: [x] complete (commit 6c12c11)

### Task 11: Remove the "Retro surfaces unmet assumption" bullet from `skills/requirements/references/gather.md`
- **Files**: `skills/requirements/references/gather.md`
- **What**: Inside the `## Re-Gather Triggers` section at L140, delete only the second bullet `**Retro surfaces unmet assumption**: a session retrospective identifies a requirement that was assumed but never documented...`. The section header and the other four bullets remain.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The section is bulleted with `- **Heading**: prose` shape; the four surviving bullets share that shape. The verification awk extracts only the section's bullets (file-wide bullet count is irrelevant because templates elsewhere in the file have identical-shape bullets).
- **Verification**: `! rg -q 'Retro surfaces unmet assumption' skills/requirements/` — pass if exit 0; `awk '/^## Re-Gather Triggers/{f=1; next} /^## /{f=0} f' skills/requirements/references/gather.md | grep -cE '^- \*\*' | xargs -I{} test {} -eq 4` — pass if exit 0.
- **Status**: [x] complete (commit f58b31c)

### Task 12: Update justfile SKILLS array, `.gitignore`, and the dual-source parity test PLUGINS dict in one commit
- **Files**: `justfile`, `.gitignore`, `tests/test_dual_source_reference_parity.py`
- **What**: At `justfile:494`: drop `fresh`, `evolve`, `retro` from the `cortex-core` SKILLS Bash array; result is `SKILLS=(commit pr lifecycle backlog requirements research discovery refine dev diagnose critical-review)` (11 entries; was 14). Preserve the `--exclude-dir=retros` recipes at `justfile:255,261` (they continue to exclude `retros/archive/` which stays on disk). At `.gitignore:9`: delete `lifecycle/.fresh-resume`. At `.gitignore:11–13`: delete the `# Retros ephemeral files` comment, `retros/.session-lessons.md`, and `retros/.retro-written-*` (the section becomes empty; remove the section header). At `tests/test_dual_source_reference_parity.py:55,57,59`: drop `"retro"`, `"fresh"`, `"evolve"` from the `cortex-core` SKILLS tuple inside the `PLUGINS` dict.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: The `PLUGINS` dict shape is `{plugin_name: ("skill_a", "skill_b", ...)}`; surviving entries follow the same tuple shape. The parity test uses `_discover_pairs` to glob canonical-side `skills/*/SKILL.md` and route each to a plugin via `PLUGINS` — there is NO "exactly N skills" assertion (verified during research). R13 + R18 atomicity requires both edits in the same commit; staging them separately leaves the parity test silently broken until the next dual-source pre-commit hook fires.
- **Verification**: `! grep -E '^\s*SKILLS=.*\b(fresh|evolve|retro)\b' justfile` — pass if exit 0; `! rg -q 'fresh-resume|session-lessons|retro-written' .gitignore` — pass if exit 0; `! grep -qE '"(fresh|evolve|retro)"' tests/test_dual_source_reference_parity.py` — pass if exit 0; `uv run pytest tests/test_dual_source_reference_parity.py` — pass if exit 0.
- **Status**: [x] complete (commit c7c7e5e; ran ahead of Task 3 due to build-plugin dependency)

### Task 13: Defensively sweep on-disk runtime artifacts produced by the deleted skills
- **Files**: `lifecycle/.fresh-resume` (rm -f), `retros/.session-lessons.md` (rm -f), `retros/.retro-written-*` (rm -f), `retros/.evolve-state.json` (rm -f) — none currently exist in this repo per research; the sweep is defensive
- **What**: Run `rm -f` against each pattern at the repo root (excluding `retros/archive/`). The motivation is that `.gitignore` no longer ignores these patterns after Task 12, so any future runtime artifact would surface in `git status`. Currently none exist on disk in this repo (verified during research); the sweep prevents accidental staging if any appear between research and PR-cut time.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: `find . -path ./retros/archive -prune -o ...` is the verification-friendly form; `rm -f` is idempotent and exits 0 even when the target is absent. Users updating cortex on existing checkouts may have these files on disk — the cleanup paths for those users are named in Task 14's CHANGELOG bullet, not auto-removed by this PR (per Non-Requirements bullet 9 on `cortex init --update`).
- **Verification**: `find . -path ./retros/archive -prune -o \( -name '.fresh-resume' -o -name '.session-lessons.md' -o -name '.retro-written-*' -o -name '.evolve-state.json' \) -print | grep -v '^./retros/archive$' | wc -l | xargs -I{} test {} -eq 0` — pass if exit 0.
- **Status**: [x] complete (no commit (no on-disk artifacts found))

### Task 14: Add the `### Removed` CHANGELOG entry under `## [Unreleased]` with replacement-workflow guidance and user-side cleanup paths
- **Files**: `CHANGELOG.md`
- **What**: Append a `### Removed` bullet (or extend the existing one) under `## [Unreleased]`. The bullet must (a) name the removed slash commands `/cortex-core:fresh`, `/cortex-core:evolve`, `/cortex-core:retro` in user-facing terms; (b) point users at `/cortex-core:backlog add` and `/cortex-core:discovery` as replacement entry points for "I noticed a problem and want a ticket" workflows; (c) enumerate the user-side cleanup paths for already-initialized repos, since `cortex init --update` does not auto-prune removed templates: `rm -f lifecycle/.fresh-resume retros/.session-lessons.md retros/.retro-written-* retros/.evolve-state.json` and `rm -f retros/README.md && rmdir retros 2>/dev/null || true` (the README is the orphaned scaffolded template; `rmdir` is a safe no-op if the directory still has user-written content); (d) include the "update plugin and CLI together" note from spec Edge Cases (`docs/release-process.md:98–120` tag-before-coupling window can leave a user running post-deletion plugin against pre-deletion CLI v0.1.0).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing `## [Unreleased]` section conventions: read CHANGELOG.md before editing to match the file's existing `### Removed` cadence, voice, and bullet shape. The spec's R15 acceptance check parses the `## [Unreleased]` section with awk and counts the removed-command and replacement-workflow tokens; the prose can be free-form provided the named tokens appear.
- **Verification**: `awk '/^## \[Unreleased\]/{found=1; next} /^## \[/{found=0} found' CHANGELOG.md > /tmp/unreleased.tmp && grep -cE '/(fresh|evolve|retro)\b|/cortex-core:(backlog|discovery)' /tmp/unreleased.tmp | xargs -I{} test {} -ge 2` — pass if exit 0; `grep -q 'retros/README\.md\|\.fresh-resume\|\.evolve-state\.json' /tmp/unreleased.tmp` — pass if exit 0. Bullet prose quality (clarity, user-facing tone, conformance to existing cadence) is verified by inspection — Interactive/session-dependent: prose-quality assessment requires human judgment about voice consistency with prior `### Removed` entries.
- **Status**: [x] complete (commit 0d43633)

### Task 15: Narrow `backlog/170` — drop the `fresh-resume-fires` Evidence bullet
- **Files**: `backlog/170-fix-pre-existing-scan-lifecycle-test-failures-in-tests-test-hookssh.md`
- **What**: Remove the `scan-lifecycle/fresh-resume-fires` Evidence bullet from the body. Leave the `single-incomplete-feature` and `claude-output-format` Evidence bullets and the rest of the ticket intact. The ticket stays open; no successor ticket is filed (per Non-Requirements bullet 4).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: The bullet is closed by Task 4's deletion of the test case. The other two listed failures are unaddressed by this PR and remain in #170's scope.
- **Verification**: `! grep -q 'fresh-resume-fires' backlog/170-*.md` — pass if exit 0; `grep -cE 'single-incomplete-feature|claude-output-format' backlog/170-*.md | xargs -I{} test {} -ge 2` — pass if exit 0.
- **Status**: [x] complete (commit fda047f)

### Task 16: Final reference sweep — last-gate verification before merge
- **Files**: none (verification only)
- **What**: Run a global ripgrep sweep across live code and live docs for the three skill names and supporting tokens. Zero hits expected outside historical/archival paths and outside legitimate documentation-of-this-work paths. This task also covers R8's `CLAUDE_AUTOMATED_SESSION` acceptance (the env-var callers were inside the deleted skills, so a clean sweep here doubles as R8 verification).
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
- **Complexity**: simple
- **Context**: The verification glob excludes `retros/archive/**`, `lifecycle/**`, `research/archive/**`, plugin trees, `CHANGELOG.md`, and `*.pyc`. The `lifecycle/**` exclusion covers this active feature's own documentation and any other in-flight lifecycle artifacts that legitimately reference the deleted surface as scope description; plugin-tree mirrors are excluded because they auto-regenerate from canonical sources, and Task 2's per-requirement check is the structural backstop for partial mirror cleanup. R8's `CLAUDE_AUTOMATED_SESSION` sweep runs over `skills/ hooks/ claude/ bin/ cortex_command/ tests/ docs/ requirements/ CLAUDE.md justfile`.
- **Verification**: `! rg -q '/fresh\b|/evolve\b|/retro\b|fresh-resume|CLAUDE_AUTOMATED_SESSION' --glob '!retros/archive/**' --glob '!lifecycle/**' --glob '!research/archive/**' --glob '!plugins/cortex-core/**' --glob '!plugins/cortex-overnight/**' --glob '!CHANGELOG.md' --glob '!*.pyc'` — pass if exit 0; `! rg -q 'CLAUDE_AUTOMATED_SESSION' skills/ hooks/ claude/ bin/ cortex_command/ tests/ docs/ requirements/ CLAUDE.md justfile` — pass if exit 0.
- **Status**: [x] complete (success_with_caveats — see events.log note)

## Verification Strategy

End-to-end verification after all tasks are complete, run in this order:

1. **Per-requirement gates** — every task's Verification command exits 0.
2. **Test suite** — `just test` exits 0 (covers `tests/test_hooks.sh`, `tests/test_dual_source_reference_parity.py`, the init test suite, and the rest of the project test surface).
3. **Pre-commit drift hook** — `.githooks/pre-commit` Phase 3 (`just build-plugin` + `git diff --exit-code plugins/`) confirms canonical/mirror coherence post-Task 3.
4. **Final reference sweep (Task 16)** — last-gate verification.
5. **Manual smoke** — invoke `/cortex-core:fresh`, `/cortex-core:evolve`, `/cortex-core:retro` in a fresh session to confirm "skill not found" failure (this is the user-facing breaking change acknowledged in the CHANGELOG).
6. **Setup-on-fresh-repo smoke** — in a scratch directory, run `cortex init` and confirm no `retros/` directory is scaffolded (covers R5's interactive verification surface).

The PR cannot merge with any per-requirement gate failing. If a gate fails mid-implementation, the recovery path per the spec is `git reset --hard` to the last clean commit and re-execute from that point — partial-merge is not supported.

## Veto Surface

- **`retros/.gitkeep` deletion** — spec resolved this to "delete entirely" (option (c)) without preserving an `archive/.gitkeep`. Reviewer may want option (a) `retros/archive/.gitkeep` preserved for explicit directory-tracking, or option (b) keep at `retros/` root. Spec's choice (c) is loosely justified ("`archive/` is non-empty after the move, so it's git-tracked without a placeholder") — reviewable.
- **No replacement narrative for the deleted MAIN→BACKLOG feedback edge** — Task 9 deletes the `### 5. Self-Improvement Loop` section without a one-line replacement (per Non-Requirements bullet 6). Reviewer may want a replacement pointer like "problems surface via direct `/cortex-core:backlog add` or `/cortex-core:discovery` invocation" inserted at L150 or in the Workflow Narratives section.
- **`docs/overnight-operations.md` L11 scrub** — Task 10 removes the "retro back-reference" stylistic mention. Spec called this "spec author's call whether to scrub" and resolved to scrub. Reviewer may want it preserved as historical reference (the doc still works either way).
- **`bin/cortex-archive-rewrite-paths` and `bin/cortex-archive-sample-select` rationale comments** — spec folds these into Task 10's R11 "intentionally left out of scope" (per Non-Requirements bullet 3 on helper-script comments). Reviewer may want the now-stale "retros are immutable per /retro skill" rationale comments updated even though the exclusion behavior itself is correct.
- **CLAUDE_AUTOMATED_SESSION removal as breaking change** — the env var has zero readers post-Task 1, but a downstream user repo's automation may set it. The CHANGELOG bullet (Task 14) calls out the removal but does not deprecate-then-remove. Reviewer may want a one-version deprecation window before final removal — spec rejected this in favor of hard-delete (Tradeoffs alternatives D and E).
- **Aligning lifecycle to `complex`/`high` from backlog frontmatter** rather than the events.log defaults of `simple`/`medium`. The override events were appended at plan-phase entry (`2026-05-06T13:30:00Z`); reviewer may want to revisit if the plan turns out to be simpler than tier=complex implies.

## Scope Boundaries

Mirrors the spec's Non-Requirements section in summary form:

- **NOT deleting** `retros/archive/` or any historical retro content.
- **NOT introducing** a deprecation notice, tombstone SKILL.md, or env-var soft-delete.
- **NOT migrating or rewriting** content inside archived retros.
- **NOT closing** `backlog/170` outright — it stays open with the two unaddressed test failures.
- **NOT modifying** `requirements/*.md` files (verified to have no live references to the deleted surface).
- **NOT adding** a successor "Manual Backlog Entry" narrative to `docs/agentic-layer.md`.
- **NOT touching** `harness-review`, `tests/test_archive_rewrite_paths.py`, `skills/refine/references/clarify-critic.md`, or `docs/internals/*` (verified clean).
- **NOT introducing** a new env var, configuration knob, or feature flag — the work removes one (`CLAUDE_AUTOMATED_SESSION`).
- **NOT extending** `cortex init --update` to auto-prune the orphaned `retros/README.md` template from already-initialized user repos. R15's CHANGELOG bullet names the manual cleanup paths.
- **NOT pinning** the cortex CLI release tag this PR ships under. Per spec, the next release MUST be at least a minor bump (`0.1.x → 0.2.0`) under SemVer's "no behavior changes for users in patches" rule, but the actual tag is the maintainer's call.
