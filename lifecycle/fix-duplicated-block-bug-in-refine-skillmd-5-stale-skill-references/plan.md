# Plan: fix-duplicated-block-bug-in-refine-skillmd-5-stale-skill-references

## Overview

Surgical, single-commit cleanup: 16 path-string substitutions + 1 sentence deletion + 1 byte-identical block deletion across 8 canonical files. Strategy A from research (single Edit per substitution, one commit), with `replace_all` per-file when a token recurs. Tasks that share a file are sequenced via explicit `Depends on` edges so concurrent Edit-tool dispatch cannot race. Mirror regen and staging are done by the agent before commit (`just build-plugin && git add plugins/cortex-core/`); the pre-commit hook re-runs `just build-plugin` for verification but does NOT auto-stage — its Phase 4 drift check compares working-tree to index, so unstaged regen output would block the commit. A pre-edit drift baseline check halts the agent if pre-existing mirror drift is detected so it is not silently folded into this PR.

## Tasks

### Task 1: Pre-edit drift baseline check
- **Files**: none modified; reads `plugins/cortex-core/` mirror tree
- **What**: Verify the working tree's plugin mirror is clean before any canonical-source edit, so pre-existing drift unrelated to this PR is not silently included in the final diff.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Run `just build-plugin` then `git diff --exit-code plugins/`.
  - On non-zero exit: HALT — do not proceed to subsequent tasks. Surface `git diff plugins/` output to the user with a one-line message naming this gate (Spec R10). Resumption requires explicit user direction.
  - On exit 0: proceed.
- **Verification**: run `just build-plugin && git diff --exit-code plugins/` — pass if exit 0; fail (halt feature) on any non-zero exit.
- **Status**: [ ] pending

### Task 2: Dedup byte-identical block in `skills/refine/SKILL.md`
- **Files**: `skills/refine/SKILL.md`
- **What**: Remove the second copy of the `### Alignment-Considerations Propagation` 20-line block (currently lines 138–157 inclusive), leaving exactly one heading-and-body. Surviving block at line 117 must remain contiguously connected to its `After writing \`research.md\`, update...` continuation line.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Pre-edit assertion: `grep -c "^### Alignment-Considerations Propagation$" skills/refine/SKILL.md` must equal 2 before the edit. If not 2, HALT and surface to user — the file has drifted from the spec inventory.
  - Verified pre-state: `diff <(sed -n '117,136p' skills/refine/SKILL.md) <(sed -n '138,157p' skills/refine/SKILL.md)` returns no output (byte-identical).
  - Anchor Edit's `old_string` on heading + body content — NOT line numbers (FM-3 in research). Old string must include the blank line (137) before the duplicate heading + the full second copy (138–157), ending at the line preceding "After writing".
  - Edge case (spec Edge Cases): if the agent's `old_string` exact-match fails, re-read the file region and rebuild against actual current content; do NOT fall back to line-range deletion.
- **Verification**: `grep -c "^### Alignment-Considerations Propagation$" skills/refine/SKILL.md` — pass if output = "1".
- **Status**: [ ] pending

### Task 3: Replace `claude/common.py` with `cortex_command/common.py` across 4 in-scope files
- **Files**: `skills/lifecycle/SKILL.md`, `skills/backlog/references/schema.md`, `docs/overnight-operations.md`, `docs/backlog.md`
- **What**: Substitute the 8 occurrences of `claude/common.py` with `cortex_command/common.py` across these 4 files (Spec R2; research inventory rows 1–8). One file (`skills/lifecycle/SKILL.md`) contains the token at both line 3 (description-fence) and line 35 (body); use Edit's `replace_all=true` for that file. `docs/overnight-operations.md` has 3 sites (101, 103, 326) and `docs/backlog.md` has 2 sites (121, 174); use `replace_all=true` per file. Substitution is provably YAML-safe (research §Frontmatter-edit safety verdict).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Pre-edit count assertions (run before the corresponding Edit; HALT on mismatch): `grep -c "claude/common\.py" skills/lifecycle/SKILL.md` = 2; `grep -c "claude/common\.py" skills/backlog/references/schema.md` = 1; `grep -c "claude/common\.py" docs/overnight-operations.md` = 3; `grep -c "claude/common\.py" docs/backlog.md` = 2. If any count differs from the expected, HALT and surface to user — the file has drifted from the spec inventory and `replace_all=true` would over-match silently.
  - The `skills/lifecycle/SKILL.md:3` substitution intentionally re-fences the lifecycle skill's description gating-rule onto the live shared-helpers path; this is a behavior change tracked in Task 9's commit body (Spec Changes to Existing Behavior, SEC-1 in research).
  - Out-of-scope (DO NOT touch): any `claude/common.py` hits in `lifecycle/`, `research/`, `CHANGELOG.md`, archived backlog tickets — these intentionally preserve historical references (Spec Non-Requirements; FM-2 in research).
- **Verification**: each command exits 0 with the expected output:
  - Negative (old token gone): `grep -c "claude/common\.py" skills/lifecycle/SKILL.md` = 0; same check on `skills/backlog/references/schema.md`, `docs/overnight-operations.md`, `docs/backlog.md` — all 0.
  - Positive (new token present at expected count): `grep -c "cortex_command/common\.py" skills/lifecycle/SKILL.md` = 2; `grep -c "cortex_command/common\.py" skills/backlog/references/schema.md` = 1; `grep -c "cortex_command/common\.py" docs/overnight-operations.md` = 3; `grep -c "cortex_command/common\.py" docs/backlog.md` = 2. (This catches the typo class — e.g., `cortex_command/common.pyy` — that the negative check alone cannot.)
- **Status**: [ ] pending

### Task 4: Qualify `cortex-worktree-create.sh` references with `claude/hooks/` prefix
- **Files**: `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/implement.md`
- **What**: Replace both unqualified `cortex-worktree-create.sh` references (`skills/lifecycle/SKILL.md:378`, `skills/lifecycle/references/implement.md:206`) with `claude/hooks/cortex-worktree-create.sh` (Spec R3; research inventory rows 9–10).
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**:
  - Sequenced after Task 3 because both tasks edit `skills/lifecycle/SKILL.md` — concurrent Edit-tool dispatch on the same file would race on `old_string` exact-match or force a worktree merge conflict. Task 3 → Task 4 ordering eliminates the race.
  - Edit's `old_string` should anchor on enough surrounding context to disambiguate the unqualified hit from any already-qualified `claude/hooks/cortex-worktree-create.sh` mention in the same file.
  - Verification regex below uses PCRE lookbehind (`-P`) because ripgrep's default Rust regex engine rejects look-around with a parse error (Spec R8 footnote).
- **Verification**: `rg -nP "(?<!hooks/)cortex-worktree-create\.sh" skills/lifecycle/SKILL.md skills/lifecycle/references/implement.md` returns no hits — pass if exit 1 AND empty stdout.
- **Status**: [ ] pending

### Task 5: Delete `bin/overnight-status` reference sentence in `implement.md`
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Delete the entire sentence `This matches the detection pattern used by \`bin/overnight-status\`.` at line 68 (Spec R4; FM-4 in research). Token-only deletion would leave a grammatical fragment.
- **Depends on**: [1, 4]
- **Complexity**: simple
- **Context**:
  - Sequenced after Task 4 because both tasks edit `skills/lifecycle/references/implement.md`. Concurrent edits would race; Task 4 → Task 5 ordering eliminates the race.
  - Edit's `old_string` includes the full sentence including its leading whitespace and the preceding/following sentence boundaries needed to maintain paragraph flow after deletion.
  - Out-of-scope (DO NOT touch): `bin/overnight-status` reference in `lifecycle/morning-report.md:24` (Spec Non-Requirements; FM-6 in research).
- **Verification**: both commands exit 0 with output "0":
  - `grep -c "bin/overnight-status" skills/lifecycle/references/implement.md`
  - `grep -c "This matches the detection pattern used by" skills/lifecycle/references/implement.md`
- **Status**: [ ] pending

### Task 6: Path-fix `backlog/generate_index.py` references in `complete.md`
- **Files**: `skills/lifecycle/references/complete.md`
- **What**: Replace both `backlog/generate_index.py` occurrences (lines 42, 65) with `cortex_command/backlog/generate_index.py`. Preserve the surrounding `test -f` guard structure AND the `cortex-generate-backlog-index` CLI fallback chain — no logic restructure (Spec R5; Spec Non-Requirements: "No restructure of the complete.md test-f guard chain").
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Pre-edit count assertion: `grep -c "backlog/generate_index\.py" skills/lifecycle/references/complete.md` = 2 (the two old-path occurrences). If count ≠ 2, HALT — file has drifted.
  - Use Edit's `replace_all=true` for the file (token recurs at 42 and 65; both are the same substitution).
  - Documented runtime-path shift (A-4 in research, Spec Edge Cases): post-fix, `cortex_command/backlog/generate_index.py` always exists (it's part of the package), so the test-f guard always fires the file-path branch — the second-tier `cortex-generate-backlog-index` CLI fallback never fires at runtime. Functionally equivalent regen; only emit-message differs. Documented in Task 9's commit body.
  - Out-of-scope (DO NOT touch): `backlog/generate_index.py` references in `docs/backlog.md` and `skills/backlog/SKILL.md` (Spec Non-Requirements).
- **Verification**: each command exits 0 with the expected output:
  - Positive (new path present): `grep -c "cortex_command/backlog/generate_index\.py" skills/lifecycle/references/complete.md` = 2.
  - CLI fallback intact: `grep -c "cortex-generate-backlog-index" skills/lifecycle/references/complete.md` = 2.
  - Structural guard preserved (more meaningful than counting `test -f` overall, which also matches prose mentions of the construct): `grep -c "Run \`test -f" skills/lifecycle/references/complete.md` = 2 — counts the two literal guard invocations the spec wants preserved (lines 42 and 65 in the bullet form `Run \`test -f X\` ...`), not prose like `using \`test -f\` to check`.
- **Status**: [ ] pending

### Task 7: Replace `update_item.py` with `cortex-update-item` across 3 in-scope files
- **Files**: `skills/lifecycle/references/clarify.md`, `skills/refine/references/clarify.md`, `skills/refine/SKILL.md`
- **What**: Substitute the 4 occurrences of `update_item.py` with `cortex-update-item` (CLI name) across these 3 files (Spec R6; research inventory rows 14–17). `skills/refine/SKILL.md` contains the token at both line 231 and line 232 (constraints table rows 3 and 4); use `replace_all=true` for that file.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - Pre-edit count assertions (HALT on mismatch): `grep -c "update_item\.py" skills/lifecycle/references/clarify.md` = 1; `grep -c "update_item\.py" skills/refine/references/clarify.md` = 1; `grep -c "update_item\.py" skills/refine/SKILL.md` = 2.
  - `cortex-update-item` is the canonical CLI name (verified on `~/.local/bin/cortex-update-item` per Spec Technical Constraints).
  - Out-of-scope (DO NOT touch): `update_item.py` hits in `skills/morning-review/SKILL.md:113`, `skills/morning-review/references/walkthrough.md:469,:600,:601`, `skills/backlog/SKILL.md:66`, `docs/backlog.md` lines 100/103-104/121/157-205, and `lifecycle/morning-report.md:24` (Spec Non-Requirements; FM-6 in research). May be filed as a follow-up ticket at completion.
- **Verification**: each command exits 0 with the expected output:
  - Negative (old token gone): `grep -c "update_item\.py" skills/lifecycle/references/clarify.md` = 0; same check on `skills/refine/references/clarify.md` and `skills/refine/SKILL.md` — all 0.
  - Positive (new CLI name present at expected count): `grep -c "cortex-update-item" skills/lifecycle/references/clarify.md` ≥ 1; same for `skills/refine/references/clarify.md`; `grep -c "cortex-update-item" skills/refine/SKILL.md` ≥ 2.
- **Status**: [ ] pending

### Task 8: Verify frontmatter parses + scoped sweep + modified-file whitelist
- **Files**: none modified; reads the 8 in-scope files and `git diff --name-only` output
- **What**: Run the spec's R7 frontmatter-parse check on `skills/lifecycle/SKILL.md` (catches accidental YAML breakage in the description-fence edit); the spec's R8 scoped ripgrep sweep across the 8 modified files (catches missed swaps if any prior task silently no-op'd); and a modified-file whitelist check to confirm the agent did not accidentally edit a file outside the 8-file scope.
- **Depends on**: [2, 3, 4, 5, 6, 7]
- **Complexity**: simple
- **Context**:
  - Frontmatter parse uses line-anchored regex split (Spec R7) so a stray `---` substring inside the body cannot validate the wrong segment.
  - Ripgrep sweep is file-scoped (NOT repo-wide) — repo-wide would false-flag ~80+ archive/historical hits (FM-2 in research).
  - PCRE lookbehind (`-P`) is required for the `cortex-worktree-create.sh` and `backlog/generate_index.py` checks because ripgrep's default Rust regex engine rejects look-around (Spec R8 footnote).
  - Whitelist check: `git diff --name-only` (unstaged) PLUS `git diff --cached --name-only` (staged) must return only files within {`skills/refine/SKILL.md`, `skills/lifecycle/SKILL.md`, `skills/backlog/references/schema.md`, `docs/overnight-operations.md`, `docs/backlog.md`, `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/complete.md`, `skills/lifecycle/references/clarify.md`, `skills/refine/references/clarify.md`} ∪ {`lifecycle/{feature}/**`, `plugins/cortex-core/**` (mirror)}. Any other path indicates an accidental edit and HALTs.
- **Verification**: all of:
  - `python3 -c "import re, yaml; c = open('skills/lifecycle/SKILL.md').read(); parts = re.split(r'^---\\s*$', c, maxsplit=2, flags=re.MULTILINE); assert len(parts) >= 3 and parts[0].strip() == '', 'no leading frontmatter delimiter'; yaml.safe_load(parts[1])"` exits 0.
  - `rg -n "claude/common\.py" skills/lifecycle/SKILL.md skills/backlog/references/schema.md docs/overnight-operations.md docs/backlog.md` exits 1 with empty stdout.
  - `rg -nP "(?<!hooks/)cortex-worktree-create\.sh" skills/lifecycle/SKILL.md skills/lifecycle/references/implement.md` exits 1 with empty stdout.
  - `rg -n "bin/overnight-status" skills/lifecycle/references/implement.md` exits 1 with empty stdout.
  - `rg -nP "(?<!cortex_command/)backlog/generate_index\.py" skills/lifecycle/references/complete.md` exits 1 with empty stdout.
  - `rg -n "update_item\.py" skills/lifecycle/references/clarify.md skills/refine/references/clarify.md skills/refine/SKILL.md` exits 1 with empty stdout.
  - Whitelist: `(git diff --name-only; git diff --cached --name-only) | sort -u | grep -vE '^(skills/refine/SKILL\.md|skills/lifecycle/SKILL\.md|skills/backlog/references/schema\.md|docs/overnight-operations\.md|docs/backlog\.md|skills/lifecycle/references/implement\.md|skills/lifecycle/references/complete\.md|skills/lifecycle/references/clarify\.md|skills/refine/references/clarify\.md|lifecycle/fix-duplicated-block-bug-in-refine-skillmd-5-stale-skill-references/|plugins/cortex-core/)'` returns empty (exit 1).
- **Status**: [ ] pending

### Task 9: Build mirror, stage, commit via `/cortex-core:commit` with description-fence callout
- **Files**: stages all 8 canonical-source edits + lifecycle artifacts + regenerated `plugins/cortex-core/` mirror; commit message body explicitly cites the description-fence behavior change
- **What**: Regenerate the plugin mirror, stage canonical + mirror + lifecycle artifacts, then invoke `/cortex-core:commit`. Commit message body must explicitly note that replacing `claude/common.py` with `cortex_command/common.py` in `skills/lifecycle/SKILL.md:3`'s description-fence intentionally re-fences the live shared-helpers file — meaning lifecycle-skill auto-trigger gating now applies to edits in `cortex_command/common.py` (whereas the stale path never triggered). This is Spec R11. The pre-commit hook (`.githooks/pre-commit`) Phase 2/3/4 chain re-runs `just build-plugin` and asserts no working-tree-vs-index drift; the hook does NOT auto-stage, so the agent must pre-stage the mirror or Phase 4 will block the commit. Commit must succeed without `--no-verify` (Spec R9). On parity-linter (Phase 1.5) false-positive: HALT, surface `just check-parity --staged` output to the user, leave the staged index intact, and require explicit user direction before bypass — never use `--no-verify` (Spec Edge Cases).
- **Depends on**: [8]
- **Complexity**: simple
- **Context**:
  - Workflow:
    1. `just build-plugin` — regenerates `plugins/cortex-core/` mirrors via `rsync -a --delete` from canonical sources.
    2. `git add` the 8 canonical files explicitly (no `git add -A`).
    3. `git add plugins/cortex-core/` to stage the regenerated mirrors.
    4. (lifecycle artifacts will be staged by `/cortex-core:commit` per `commit-artifacts: true` in `lifecycle.config.md`).
    5. Invoke `/cortex-core:commit`.
  - Why pre-stage: the pre-commit hook's Phase 3 (`just build-plugin`) writes mirrors to the working tree but never runs `git add`; Phase 4's drift check (`git diff --quiet -- "plugins/$p/"`) compares working tree to index, so unstaged regen output is detected as drift and the commit fails. Verified by reading `.githooks/pre-commit` and confirmed by recent canonical-edit commits (e.g. 3e4bea5) which staged canonical + mirror together.
  - Lifecycle artifact staging is hook-safe: the hook's Phase 2 BUILD_NEEDED regex `^(skills/|bin/cortex-|hooks/cortex-|claude/hooks/cortex-)` does not match `lifecycle/` paths, so staging `lifecycle/{feature}/plan.md` etc. does not trigger spurious mirror regen.
  - Per CLAUDE.md: never run `git commit` manually — use `/cortex-core:commit`. The commit-validation hook checks message format.
  - Commit body sentence must contain BOTH the literal token `cortex_command/common.py` AND at least one of {`gating`, `fence`, `trigger`}. The dual requirement prevents the verification grep from passing on incidental keyword matches that don't carry the substantive description-fence semantic-shift callout R11 requires.
- **Verification**: all of:
  - `git diff --exit-code plugins/cortex-core/` exits 0 post-commit (no untracked drift; Spec R9).
  - `git log -1 --format=%B HEAD | grep -F "cortex_command/common.py"` returns at least one match line (substantive new-path mention in body).
  - `git log -1 --format=%B HEAD | grep -iE "gating|fence|trigger"` returns at least one match line (Spec R11 keyword).
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete, the feature is verified end-to-end by re-running the spec's acceptance commands (R1 through R11) in order, augmented by the plan's per-task pre-edit count assertions, post-edit positive-form assertions, and Task 8's modified-file whitelist. R10 was already confirmed at Task 1; R1–R8 are confirmed by Tasks 2–8 (with positive checks added beyond the spec's negative-only minimums to catch typo and over-match silent-pass modes); R9 and R11 are confirmed at Task 9 (with R11's keyword grep tightened to require both the new path token and a fence-keyword). The pre-commit hook chain remains the load-bearing structural integration test for canonical/mirror parity: it runs `just check-parity --staged` (Phase 1.5), regenerates `plugins/cortex-core/` mirrors via `rsync -a --delete` (Phase 2/3), and fails the commit if `git diff --quiet plugins/` shows drift between the regenerated working tree and the staged index (Phase 4). Because Phase 4 compares working-tree to index (not `--cached`), the agent must pre-stage the regenerated mirrors as part of Task 9's workflow; the hook validates the agent's staging, it does not perform staging itself.

## Veto Surface

- **Description-fence behavior change at `skills/lifecycle/SKILL.md:3`**: replacing `claude/common.py` with `cortex_command/common.py` re-fences the live shared-helpers path under the lifecycle skill's auto-trigger gating rule. Users editing `cortex_command/common.py` will now trigger the lifecycle skill (whereas previously the fenced path did not exist and the gating rule never fired on that path). The user explicitly accepted this in the F3 disposition of clarify-critic; surfacing again here in case priority shifts before implementation.
- **Same-file task sequencing**: Tasks 3 → 4 are serialized via `Task 4 Depends on: [1, 3]` because both edit `skills/lifecycle/SKILL.md`; Tasks 4 → 5 are serialized via `Task 5 Depends on: [1, 4]` because both edit `skills/lifecycle/references/implement.md`. Without these edges, parallel-dispatch in the implement phase (or worktree-merge dispatch under overnight) would race two Edit-tool agents against the same file, corrupting `old_string` exact-match or forcing a 3-way merge. Override surface only if user wants tasks merged into one combined task instead of sequenced.
- **Out-of-scope hits surfaced during research are not addressed in this PR**: `update_item.py` in `skills/morning-review/`, `skills/backlog/SKILL.md:66`, `docs/backlog.md`; `bin/overnight-status` in `lifecycle/morning-report.md:24`; `backlog/generate_index.py` in `docs/backlog.md` and `skills/backlog/SKILL.md`. These were excluded by user §4 scope choice and may be filed as a follow-up ticket.
- **Single-commit strategy (vs. per-token commits)**: alternative C in research §Tradeoffs is per-token commits for atomic-revert. Rejected because mechanical name swaps have no behavioral coupling and per-token would multiply review load + mirror regen with no upside. Reversible via `git revert <sha>` in the unlikely event of regression.
- **Mirror pre-staging in Task 9**: the plan instructs the agent to run `just build-plugin && git add plugins/cortex-core/` before invoking `/cortex-core:commit`. This contradicts an earlier (incorrect) reading of `.githooks/pre-commit` as auto-staging; the hook does not auto-stage and Phase 4 would block any unstaged regen. Override surface only if user wants `/cortex-core:commit` itself enhanced to handle pre-staging — out of scope for this ticket, would be a separate follow-up.
- **No CHANGELOG.md update**: this is a documentation/skill-text cleanup with no behavioral effect on running code; the description-fence behavior change is durable in the commit-message body. Override surface if the user wants a CHANGELOG entry.

## Scope Boundaries

Per Spec Non-Requirements:
- **Out-of-scope `update_item.py` and `bin/overnight-status` references will NOT be touched in this PR**: `skills/morning-review/SKILL.md:113`, `skills/morning-review/references/walkthrough.md:469,:600,:601`, `skills/backlog/SKILL.md:66`, multiple lines of `docs/backlog.md` containing `update_item.py`, and `lifecycle/morning-report.md:24` containing `bin/overnight-status`.
- **`backlog/generate_index.py` references in `docs/backlog.md` and `skills/backlog/SKILL.md`** are NOT in scope.
- **Mirror files at `plugins/cortex-core/skills/{lifecycle,refine,backlog}/SKILL.md` will NOT be hand-edited** — auto-regenerated by `just build-plugin` from canonical sources; the agent stages the regenerated mirrors but does not edit them.
- **No restructure of the `complete.md` test-f guard chain**.
- **No CHANGELOG.md update required for this PR**.
- **No tests added** — the change is doc-only; existing dual-source drift tests cover mirror parity.
