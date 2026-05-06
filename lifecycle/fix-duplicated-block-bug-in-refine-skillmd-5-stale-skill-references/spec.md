# Specification: fix-duplicated-block-bug-in-refine-skillmd-5-stale-skill-references

## Problem Statement

`skills/refine/SKILL.md` contains a byte-identical 20-line `### Alignment-Considerations Propagation` block at lines 117-136 and 138-157, costing ~21 lines of context per refine invocation. In parallel, eight skill/doc files contain stale references to paths that no longer exist or have been renamed: `claude/common.py` (8 sites in skills/lifecycle/SKILL.md, skills/backlog/references/schema.md, docs/overnight-operations.md, docs/backlog.md), unqualified `cortex-worktree-create.sh` (2 sites), `bin/overnight-status` (1 site, never existed), `backlog/generate_index.py` (2 sites), and `update_item.py` (4 sites — replaced by `cortex-update-item` CLI). One of these — the `claude/common.py` token in skills/lifecycle/SKILL.md:3 — sits inside the description-fence ("Required before editing any file in...") that Claude Code uses to route incoming requests to the lifecycle skill, so the correction also realigns a load-bearing trigger surface with the live shared-helpers path. Cleanup costs less than 30 minutes; benefits future readers, reduces refine-invocation context cost, and corrects one stale gating fence.

## Requirements

1. **Duplicated-block deletion**: The byte-identical second `### Alignment-Considerations Propagation` block in `skills/refine/SKILL.md` (currently lines 138-157) is removed; exactly one heading-and-block remains. Acceptance criteria:
   - `grep -c "^### Alignment-Considerations Propagation$" skills/refine/SKILL.md` = 1 (pass if exit code = 0 AND output = "1"). Heading text is structurally unique-per-line in markdown, so grep's line-count equals match-count here.
   - The surviving block remains contiguously connected to its "After writing `research.md`, update..." continuation line. Verified with a single-quoted shell command (avoids backtick command-substitution): `grep -A 1 'argument entirely from the research dispatch' skills/refine/SKILL.md` returns 2 lines whose second line begins with "After writing".

2. **`claude/common.py` token replaced everywhere in scope**: All 8 occurrences of the literal string `claude/common.py` across the 5 in-scope files are replaced with `cortex_command/common.py`. Acceptance criteria — each command exits 0 with output "0":
   - `grep -c "claude/common\.py" skills/lifecycle/SKILL.md`
   - `grep -c "claude/common\.py" skills/backlog/references/schema.md`
   - `grep -c "claude/common\.py" docs/overnight-operations.md`
   - `grep -c "claude/common\.py" docs/backlog.md`

3. **`cortex-worktree-create.sh` qualified everywhere in scope**: Both unqualified occurrences are replaced with `claude/hooks/cortex-worktree-create.sh`. Acceptance — for each command, every `cortex-worktree-create.sh` hit must be preceded by `claude/hooks/`:
   - `grep -n "cortex-worktree-create\.sh" skills/lifecycle/SKILL.md` shows every line is the qualified form (no bare `cortex-worktree-create.sh` outside the `claude/hooks/` prefix). Pass if every line in the output contains `claude/hooks/cortex-worktree-create.sh`.
   - `grep -n "cortex-worktree-create\.sh" skills/lifecycle/references/implement.md` — same check.

4. **`bin/overnight-status` reference removed**: The full sentence `This matches the detection pattern used by \`bin/overnight-status\`.` at `skills/lifecycle/references/implement.md:68` is deleted (not just the backticked token — token-only deletion would leave a grammatical fragment). Acceptance criteria:
   - `grep -c "bin/overnight-status" skills/lifecycle/references/implement.md` = 0 (pass if exit code = 0 AND output = "0")
   - `grep -c "This matches the detection pattern used by" skills/lifecycle/references/implement.md` = 0

5. **`backlog/generate_index.py` path-fixed (test-f guard preserved)**: Both occurrences in `skills/lifecycle/references/complete.md` are replaced with `cortex_command/backlog/generate_index.py`; the surrounding `test -f` guard pattern AND the `cortex-generate-backlog-index` CLI fallback chain remain structurally intact (no logic restructure). Acceptance criteria — pure positive assertions (negative-form check is in R8's ripgrep sweep):
   - `grep -c "cortex_command/backlog/generate_index\.py" skills/lifecycle/references/complete.md` = 2 (both occurrences point at the new qualified path; pass if output = "2")
   - `grep -c "test -f" skills/lifecycle/references/complete.md` = 4 (exact pre-fix count; this PR neither adds nor removes guards; pass if output = "4")
   - `grep -c "cortex-generate-backlog-index" skills/lifecycle/references/complete.md` = 2 (the two CLI fallback references; pass if output = "2")

6. **`update_item.py` token replaced with `cortex-update-item` everywhere in scope**: All 4 occurrences across 3 files are replaced. Acceptance criteria — each command exits 0 with output "0":
   - `grep -c "update_item\.py" skills/lifecycle/references/clarify.md`
   - `grep -c "update_item\.py" skills/refine/references/clarify.md`
   - `grep -c "update_item\.py" skills/refine/SKILL.md`

7. **Frontmatter still parses after edits**: The YAML frontmatter of `skills/lifecycle/SKILL.md` parses without exception after the description-field substitution. Acceptance criteria — uses a line-anchored split so a stray `---` substring inside the body cannot cause the check to validate the wrong segment:
   - `python3 -c "import re, yaml; c = open('skills/lifecycle/SKILL.md').read(); parts = re.split(r'^---\\s*$', c, maxsplit=2, flags=re.MULTILINE); assert len(parts) >= 3 and parts[0].strip() == '', 'no leading frontmatter delimiter'; yaml.safe_load(parts[1])"` exits 0.

8. **Scoped ripgrep sweep across 8 modified files confirms full token removal**: For each old token, ripgrep across the modified files returns no hits. Acceptance criteria — each command exits 1 (no matches) AND emits empty stdout. Lookbehind regexes use `-P` (PCRE2) explicitly because ripgrep's default Rust regex engine rejects look-around with a parse error:
   - `rg -n "claude/common\.py" skills/lifecycle/SKILL.md skills/backlog/references/schema.md docs/overnight-operations.md docs/backlog.md` returns no hits
   - `rg -nP "(?<!hooks/)cortex-worktree-create\.sh" skills/lifecycle/SKILL.md skills/lifecycle/references/implement.md` returns no hits (PCRE lookbehind: matches only the bare form, not the qualified form)
   - `rg -n "bin/overnight-status" skills/lifecycle/references/implement.md` returns no hits
   - `rg -nP "(?<!cortex_command/)backlog/generate_index\.py" skills/lifecycle/references/complete.md` returns no hits (PCRE lookbehind: matches only the old bare path, not the new qualified path)
   - `rg -n "update_item\.py" skills/lifecycle/references/clarify.md skills/refine/references/clarify.md skills/refine/SKILL.md` returns no hits

9. **Pre-commit dual-source drift hook passes**: The commit succeeds with the standard pre-commit hook chain (`.githooks/pre-commit` Phases 1.5/2/3/4) without `--no-verify`. `just build-plugin` uses `rsync -a --delete` to mirror each entire skill subtree (verified: `plugins/cortex-core/skills/{lifecycle,refine,backlog}/` mirror SKILL.md AND the full `references/` subdirectory byte-for-byte). For Reqs 4-6 (which edit only `references/*.md`, not top-level SKILL.md), the regenerated mirror files are the `references/*.md` mirrors, not the `SKILL.md` mirrors — the drift assertion below is scope-agnostic and catches drift at any level. `docs/` files are NOT mirrored anywhere in `plugins/cortex-core/`, so the docs edits in Req 2 do not trigger or affect the mirror layer. Acceptance criteria:
   - The git commit completes without hook failure.
   - Post-commit, `git diff --exit-code plugins/cortex-core/` exits 0 (no untracked drift at any path level — top-level SKILL.md mirrors AND references/*.md mirrors).

10. **Pre-edit drift baseline check**: Before the first edit, the working tree's plugin mirror state must be verified clean to ensure pre-existing drift unrelated to this PR is not silently folded into the diff. Acceptance criteria — binary, run as the agent's first action before any spec edit:
    - `just build-plugin && git diff --exit-code plugins/` exits 0. If exit ≠ 0, the agent halts (does NOT proceed to edits) and surfaces the diff to the user with a one-line message naming this gate. Resumption requires explicit user direction.

## Non-Requirements

- **Out-of-scope `update_item.py` and `bin/overnight-status` references will NOT be touched in this PR.** Specifically: `skills/morning-review/SKILL.md:113`, `skills/morning-review/references/walkthrough.md:469,:600,:601`, `skills/backlog/SKILL.md:66`, multiple lines of `docs/backlog.md` containing `update_item.py`, and `lifecycle/morning-report.md:24` containing `bin/overnight-status`. These were surfaced during research as additional stale references but are not in the user's §4 scope-expansion choice. They may be filed as a follow-up ticket at completion.
- **`backlog/generate_index.py` references in `docs/backlog.md` and `skills/backlog/SKILL.md`** are NOT in scope. Same rationale.
- **Mirror files at `plugins/cortex-core/skills/{lifecycle,refine,backlog}/SKILL.md` will NOT be hand-edited.** They are auto-regenerated by the pre-commit hook from canonical sources. Editing them directly is a dual-source drift violation.
- **No restructure of the `complete.md` test-f guard chain.** The guard structure (test-f → file path → else CLI → else warning) remains; only the path string changes. Per user §4 choice (path-fix, not CLI-restructure).
- **No CHANGELOG.md update required for this PR.** This is a documentation/skill-text cleanup with no behavioral effect on running code (the description-fence behavior change is durable in commit-message body per Requirement 11 below).
- **No tests added.** The change is doc-only; existing dual-source drift tests already cover mirror parity.

11. **Commit-body callout for description-fence behavior change**: The commit message body explicitly notes that replacing `claude/common.py` with `cortex_command/common.py` in `skills/lifecycle/SKILL.md:3`'s description-fence intentionally re-fences the live shared-helpers file — meaning lifecycle-skill auto-trigger gating now applies to edits in `cortex_command/common.py` (whereas the stale path never triggered). Acceptance criteria:
    - Commit message body contains a sentence describing the gating-rule effect of the description-fence path change. Verifiable via `git log -1 --format=%B HEAD | grep -i "gating\|fence\|trigger"` returning at least one match line.

## Edge Cases

- **Pre-existing mirror drift (Requirement 10)**: handled by the pre-edit drift baseline check — surfaces to user before the first ticket edit.
- **Parity-linter false-positives (`just check-parity --staged`)**: if the linter trips on the modified description-field text, surface to user; do not bypass with `--no-verify`. Resolution path is fixing the linter or surfacing the false-positive — out of scope for this ticket but must not be silently bypassed.
- **Edit-tool exact-match failure on duplicated block**: if the agent's `old_string` for the dedup deletion fails to match (e.g., due to a whitespace drift), the agent must re-read the file region and rebuild the `old_string` against the actual current content — must NOT fall back to line-range deletion.
- **Multiple-occurrence handling within a single file**: skills/lifecycle/SKILL.md contains `claude/common.py` at both line 3 (description) and line 35 (body). Use Edit with `replace_all=true` per-file to handle both. Same for skills/refine/SKILL.md (lines 231 and 232 both contain `update_item.py`).
- **CLI-fallback runtime path shift in complete.md**: post-fix, `cortex_command/backlog/generate_index.py` always exists (it's part of the package), so the test-f guard always fires the file-path branch and the second-tier `cortex-generate-backlog-index` CLI fallback never fires. Functional behavior is identical (both produce the same index regen) but the emit-message string differs ("Index regenerated via cortex_command/backlog/generate_index.py" vs "via cortex-generate-backlog-index"). This is a documented runtime-path shift, not a regression — noted in commit body but does not block.

## Changes to Existing Behavior

- **MODIFIED — lifecycle-skill description-fence**: the gating-rule path-list in `skills/lifecycle/SKILL.md:3`'s `description:` field changes from including a non-existent `claude/common.py` (which never matched any real file edit) to the live `cortex_command/common.py` (which is the actual canonical shared-helpers location). Effect: when a user attempts to edit `cortex_command/common.py`, Claude Code's request-matcher will now route through the lifecycle skill's "Required before editing any file in..." fence — whereas previously this routing never fired because the fenced path didn't exist. This is an intentional behavior change that aligns the gating rule with reality.
- **REMOVED — `bin/overnight-status` documentation**: the sentence `This matches the detection pattern used by \`bin/overnight-status\`.` at `skills/lifecycle/references/implement.md:68` is deleted. The sentence cited a script that never existed in `bin/`; removing it eliminates a misleading reader pointer.
- **REMOVED — duplicated `### Alignment-Considerations Propagation` block in `skills/refine/SKILL.md`**: the second copy at lines 138-157 is deleted. Net effect: refine-skill body shrinks by 21 lines (heading + body + blank-line separator); refine-skill behavior is unchanged because the surviving copy is byte-identical to the deleted one.
- **MODIFIED — runtime emit-message in `complete.md` test-f guard branch**: the guard branch will now print "Index regenerated via cortex_command/backlog/generate_index.py" (post-fix) instead of "via backlog/generate_index.py" (pre-fix). Functionally equivalent regen; only the emit string differs.
- **No ADDED behavior** — this PR removes and corrects, it does not add.

## Technical Constraints

- **Dual-source canonical/mirror parity** (`requirements/project.md:27`, `CLAUDE.md`): canonical sources only — `plugins/cortex-core/{skills,hooks,bin}/` mirrors are auto-regenerated by `.githooks/pre-commit`. Pre-commit hook Phase 4 fails on drift. Implementation must not bypass with `--no-verify`.
- **SKILL.md description field is load-bearing for routing** (per Anthropic Skills spec): description is injected into Claude Code's system prompt and used by the LLM as a triggering hint. Path strings inside it are semantically meaningful, not cosmetic. Verified via Web Research — see research.md §Web Research §1.
- **`cortex-update-item` CLI is on PATH at `~/.local/bin/cortex-update-item`** (verified). `cortex-generate-backlog-index` CLI is also on PATH (verified). `cortex_command/common.py` is a live file (verified, 20653 bytes). `cortex_command/backlog/generate_index.py` is a live file (verified, 11493 bytes). `claude/hooks/cortex-worktree-create.sh` is a live file (verified, 2484 bytes). `bin/overnight-status` does not exist (verified — never existed).
- **Implementation strategy: single Edit per substitution, one commit total** (per Tradeoffs §A). Use Edit's `replace_all` per-file when a token recurs in the same file. Do NOT use `sed -i` batch replacement (would over-match into CHANGELOG, lifecycle/sessions/, lifecycle/archive/, research/archive/, and active tickets like `backlog/110-...md`).
- **Use `/cortex-core:commit`** per CLAUDE.md (no manual `git commit`). The commit-validation hook checks message format.
- **Verification regex must be file-scoped, not repo-wide**: a repo-wide grep for `claude/common.py` would false-flag ~80+ archive/historical hits (lifecycle event logs, archived research, CHANGELOG, ticket bodies). The acceptance criteria above are explicitly scoped to the 8 modified files.

## Open Decisions

None.
