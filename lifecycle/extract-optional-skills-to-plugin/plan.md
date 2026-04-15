# Plan: extract-optional-skills-to-plugin

## Overview

Two-repo, forward-ordered implementation: a go/no-go token benchmark first (R7 abort gate), then atomic extraction — building `cortex-command-plugins` alongside removals in this repo. Work in three waves: (1) prepare — benchmark, rewrite ui-check probes; (2) build new repo — scaffold, copy skill subtrees, copy docs, add validation; (3) clean this repo — delete extracted skills, demote harness-review, update justfile, update docs.

## Tasks

### Task 1: Run token-savings benchmark and document results
- **Files**: `lifecycle/extract-optional-skills-to-plugin/research.md` (append appendix section)
- **What**: **This task requires an interactive Claude Code session and must be completed manually before any other task begins. Do not dispatch this plan overnight until Task 1 is complete and its verification passes.** Execute the R7 measurement protocol — record `/context` system-reminder token count in a baseline session, capture each of the 7 extracted skills' description character counts from their SKILL.md frontmatter, use the `claude-md-management` plugin disable/enable as the proxy ratio, project `expected_savings_tokens`, and append the results as an appendix to research.md. If `expected_savings_tokens < 1500`, halt the lifecycle, record the abort, and document the Option C fallback.
- **Depends on**: none
- **Complexity**: simple
- **Context**: 7 skills to measure: `ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup`, `pr-review`. Measurement steps per spec R7: (1) baseline `/context` in fresh session, (2) per-skill description char count from `description:` field in each `skills/<name>/SKILL.md`, (3) disable `claude-md-management` via `/plugin`, record new `/context` delta as the proxy ratio, (4) compute `expected_savings_chars = sum(description chars for 7 skills)`, convert via proxy ratio. Abort threshold: 1500 tokens. R7 acceptance: `grep -cE '[0-9]+\s*tokens?' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1 AND `grep -c 'expected_savings_tokens' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1 AND `grep -c 'abort threshold' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1.
- **Verification**: Interactive/session-dependent: requires `/context` in a live Claude Code session — no shell command equivalent. After appending: `grep -c 'abort threshold' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 2: Rewrite ui-check FS probes (commit in cortex-command before move)
- **Files**: `skills/ui-check/SKILL.md`
- **What**: Edit `skills/ui-check/SKILL.md` to remove both hardcoded FS probes. At line ~11: remove the `~/.claude/skills/ui-lint/SKILL.md` probe (within the plugin, ui-lint is always co-deployed). At line ~74: remove the `~/.claude/skills/ui-a11y/SKILL.md` existence check entirely — same treatment as the ui-lint probe. Within the plugin, ui-a11y is always co-deployed with ui-check, so no availability gate is needed; the graceful-skip path becomes dead code. Commit in cortex-command before any move.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Research.md §Adversarial Review Finding 3 identifies the two probe locations. Both probes use FS paths under `~/.claude/skills/` that cease to exist after extraction. Within the plugin, both `ui-lint` and `ui-a11y` are always co-deployed with `ui-check` — no availability check is needed for either. Remove both probes. The graceful-skip path for ui-a11y (set `a11y.status = "skipped"`) becomes dead code within the plugin context and should be removed with the probe. Read lines 1–100 of `skills/ui-check/SKILL.md` before editing to understand the full structure.
- **Verification**: `grep -c '~/.claude/skills/ui-' skills/ui-check/SKILL.md` = 0 — pass if count = 0 (covers both probes).
- **Status**: [ ] pending

### Task 3: Scaffold `cortex-command-plugins` repo
- **Files** (all in `~/Workspaces/cortex-command-plugins/` — new directory outside this repo):
  - `README.md`
  - `LICENSE`
  - `.claude-plugin/marketplace.json`
  - `plugins/cortex-ui-extras/.claude-plugin/plugin.json`
  - `plugins/cortex-pr-review/.claude-plugin/plugin.json`
- **What**: Create `~/Workspaces/cortex-command-plugins/`, run `git init`, then write the skeletal manifest files: `marketplace.json` listing both plugins with `source: ./plugins/<name>` entries; each `plugin.json` with its `name` field; `LICENSE` copied from `cortex-command` (same terms); `README.md` explaining the repo's purpose, how to install (`claude /plugin marketplace add <github-url>`), how to enable per-project (add `"cortex-ui-extras@cortex-command-plugins": true` to `.claude/settings.json`), and the relationship to `cortex-command`.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: `marketplace.json` structure: `{"plugins": [{"name": "cortex-ui-extras", "source": "./plugins/cortex-ui-extras"}, {"name": "cortex-pr-review", "source": "./plugins/cortex-pr-review"}]}`. `plugin.json` structure: `{"name": "cortex-ui-extras"}` and `{"name": "cortex-pr-review"}`. The README references `docs/ui-tooling.md` as the in-repo UI reference (that file arrives in Task 7). Copy `LICENSE` verbatim from cortex-command root.
- **Verification**: `jq '.plugins | length' ~/Workspaces/cortex-command-plugins/.claude-plugin/marketplace.json` = 2 — pass if output is `2`. `jq -r .name ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/.claude-plugin/plugin.json` = `cortex-ui-extras` — pass if name matches.
- **Status**: [ ] pending

### Task 4: Copy 4 SKILL.md-only UI skills into new repo
- **Files** (all in `~/Workspaces/cortex-command-plugins/`):
  - `plugins/cortex-ui-extras/skills/ui-a11y/SKILL.md`
  - `plugins/cortex-ui-extras/skills/ui-judge/SKILL.md`
  - `plugins/cortex-ui-extras/skills/ui-lint/SKILL.md`
  - `plugins/cortex-ui-extras/skills/ui-setup/SKILL.md`
- **What**: Copy each of the four SKILL.md-only UI skills from `cortex-command/skills/<name>/SKILL.md` to `plugins/cortex-ui-extras/skills/<name>/SKILL.md` in the new repo. Do not modify the SKILL.md bodies — peer-skill dispatches within the plugin use bare names (e.g., `ui-check` invoking `ui-lint` stays bare), which is correct per Anthropic's plugin-dev reference. Before copying, list each skill's `skills/<name>/` directory to confirm no files are present beyond SKILL.md.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Research.md §Codebase Analysis confirms `ui-a11y`, `ui-judge`, `ui-lint`, and `ui-setup` are SKILL.md-only — no subtrees. After this task, `ls plugins/cortex-ui-extras/skills/` has 4 entries; ui-brief arrives in Task 5, ui-check in Task 6.
- **Verification**: `ls ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/skills/ | wc -l` = 4 — pass if count = 4. Each of `ui-a11y`, `ui-judge`, `ui-lint`, `ui-setup` must appear in that listing.
- **Status**: [ ] pending

### Task 5: Copy ui-brief with its references/ subtree into new repo
- **Files** (all in `~/Workspaces/cortex-command-plugins/`):
  - `plugins/cortex-ui-extras/skills/ui-brief/SKILL.md`
  - `plugins/cortex-ui-extras/skills/ui-brief/references/design-md-template.md`
  - `plugins/cortex-ui-extras/skills/ui-brief/references/theme-template.md`
- **What**: Copy the full `ui-brief` subtree from `cortex-command/skills/ui-brief/` to `plugins/cortex-ui-extras/skills/ui-brief/` in the new repo, including both files in `references/`. Do not modify the SKILL.md body. Before copying, list `skills/ui-brief/` to confirm the two reference files are present and no additional files exist.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Research.md §Codebase Analysis confirms `ui-brief` has `SKILL.md` + `references/` with `design-md-template.md` and `theme-template.md`. After this task, `ls plugins/cortex-ui-extras/skills/` has 5 entries (ui-check arrives in Task 6).
- **Verification**: `ls ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/skills/ui-brief/references/` lists `design-md-template.md` and `theme-template.md` — pass if both files exist. `ls ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/skills/ | wc -l` = 5 — pass if count = 5.
- **Status**: [ ] pending

### Task 6: Copy ui-check (post-rewrite) into new repo
- **Files** (in `~/Workspaces/cortex-command-plugins/`):
  - `plugins/cortex-ui-extras/skills/ui-check/SKILL.md`
- **What**: Copy the rewritten `skills/ui-check/SKILL.md` (committed in Task 2) to `plugins/cortex-ui-extras/skills/ui-check/` in the new repo. The copy happens after Task 2's commit, so the destination starts with correct probe logic (no hardcoded `~/.claude/skills/ui-*` paths).
- **Depends on**: [2, 4, 5]
- **Complexity**: simple
- **Context**: After this task, `ls plugins/cortex-ui-extras/skills/ | wc -l` = 6. Confirm the copied file passes the R5 acceptance check before proceeding to Task 9.
- **Verification**: `ls ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/skills/ | wc -l` = 6 — pass if count = 6. `grep -c '~/.claude/skills/ui-' ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/skills/ui-check/SKILL.md` = 0 — pass if count = 0.
- **Status**: [ ] pending

### Task 7: Copy pr-review into new repo
- **Files** (in `~/Workspaces/cortex-command-plugins/`):
  - `plugins/cortex-pr-review/skills/pr-review/SKILL.md`
  - `plugins/cortex-pr-review/skills/pr-review/references/protocol.md`
- **What**: Copy the full `skills/pr-review/` subtree from cortex-command to `plugins/cortex-pr-review/skills/pr-review/` in the new repo. Before copying, list `skills/pr-review/` to confirm which files are present beyond SKILL.md and `references/protocol.md`.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Research.md confirms: `pr-review` has `SKILL.md` + `references/`. Spec R3 acceptance: `ls plugins/cortex-pr-review/skills/` = `pr-review`; `jq -r .name plugins/cortex-pr-review/.claude-plugin/plugin.json` = `cortex-pr-review`.
- **Verification**: `ls ~/Workspaces/cortex-command-plugins/plugins/cortex-pr-review/skills/` = `pr-review` only — pass if single entry. `ls ~/Workspaces/cortex-command-plugins/plugins/cortex-pr-review/skills/pr-review/references/protocol.md` exists — pass if file found.
- **Status**: [ ] pending

### Task 8: Copy docs/ui-tooling.md to new repo and update back-link
- **Files**:
  - `~/Workspaces/cortex-command-plugins/docs/ui-tooling.md` (created — copy of `docs/ui-tooling.md`)
- **What**: Copy `docs/ui-tooling.md` (127 lines) from cortex-command to `~/Workspaces/cortex-command-plugins/docs/ui-tooling.md`. Update the back-link `[← Back to Agentic Layer](agentic-layer.md)` — replace with a GitHub link back to `cortex-command/docs/agentic-layer.md` (e.g., `[← cortex-command](https://github.com/charleshall888/cortex-command/blob/main/docs/agentic-layer.md)`) or remove the back-link if the GitHub URL isn't confirmed. The cortex-command copy is deleted in Task 12.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: The back-link is a relative markdown link that would be broken in the new repo since `agentic-layer.md` doesn't exist there. The replacement must be either an absolute GitHub URL or removed. Spec R1 says "Update its back-link from ... to a GitHub link back to cortex-command/docs/agentic-layer.md (or remove the back-link — implementation-time choice)." Choose whichever is cleaner; the critical acceptance is that no bare `(agentic-layer.md)` relative link remains.
- **Verification**: `ls ~/Workspaces/cortex-command-plugins/docs/ui-tooling.md` exists — pass if file found. `grep -c '(agentic-layer.md)' ~/Workspaces/cortex-command-plugins/docs/ui-tooling.md` = 0 — pass if no bare relative link remains.
- **Status**: [ ] pending

### Task 9: Add validation infrastructure and ui-check probe guard to new repo
- **Files** (in `~/Workspaces/cortex-command-plugins/`):
  - `scripts/validate-skill.py`
  - `.github/workflows/validate.yml`
- **What**: Copy `skills/skill-creator/scripts/validate-skill.py` from cortex-command to `scripts/validate-skill.py` in the new repo (pinned copy — not a symlink; changes to the source in cortex-command do not auto-sync). Write `.github/workflows/validate.yml` — a GitHub Actions workflow triggered on `push` and `pull_request` that: (a) checks out the repo, (b) sets up Python, (c) runs `python3 scripts/validate-skill.py plugins/cortex-ui-extras/skills` and `python3 scripts/validate-skill.py plugins/cortex-pr-review/skills`, (d) runs a probe guard step: `grep -r '~/.claude/skills/ui-' plugins/cortex-ui-extras/skills/ui-check/SKILL.md && exit 1 || exit 0` (fails if any hardcoded path is found).
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: `validate-skill.py` accepts a directory path and walks `*/SKILL.md` files in that dir, checking `name` + `description` frontmatter, YAML parse, `{{variable}}` consistency. The GH Actions workflow should use `actions/checkout@v4` and `actions/setup-python@v5` (or current equivalents at implementation time). The probe guard inverts the grep exit code: grep returns 0 if found (bad), 1 if not found (good) — so negate it. R10 acceptance: running the guard against a clean ui-check.SKILL.md returns 0 (no matches = pass); introducing a `~/.claude/skills/ui-lint/SKILL.md` reference makes the guard return non-zero (fail). Verify R9/R10 acceptance locally before Task 14.
- **Verification**: `python3 ~/Workspaces/cortex-command-plugins/scripts/validate-skill.py ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/skills` exits 0 — pass if exit code = 0. `grep -c 'validate-skill.py' ~/Workspaces/cortex-command-plugins/.github/workflows/validate.yml` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 10: Demote harness-review to project-local scope
- **Files** (in cortex-command):
  - `.claude/skills/harness-review/SKILL.md` (new location — moved from `skills/harness-review/`)
  - `justfile` (remove `harness-review` from the four deploy recipes)
- **What**: Move `skills/harness-review/SKILL.md` to `.claude/skills/harness-review/SKILL.md` in this repo. Remove the global symlink `~/.claude/skills/harness-review` if it exists. Update the justfile to remove `harness-review` from `deploy-skills`, `setup-force`, `verify-setup`/`check-symlinks`, and `validate-skills` recipes. Read the justfile at the lines identified in research.md before editing: `setup-force` (~L64–73), `deploy-skills` (~L224–261), `verify-setup`/`check-symlinks` (~L758–762), `validate-skills` (~L716, ~L839).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Existing precedent: `.claude/skills/setup-merge/` is a project-local skill in this repo — harness-review follows the same pattern. Research.md (Codebase Analysis) confirms: `harness-review` has `SKILL.md` only, no subtrees. If `validate-skills` uses a `skills/*/SKILL.md` glob (not an explicit list), no change is needed there for harness-review — the glob won't pick up `.claude/skills/`. Confirm the recipe pattern before editing.
- **Verification**: `ls .claude/skills/harness-review/SKILL.md` exists — pass if file found. `ls skills/harness-review 2>/dev/null` is empty — pass if directory gone. `readlink ~/.claude/skills/harness-review 2>/dev/null` is empty — pass if no global symlink.
- **Status**: [ ] pending

### Task 11: Delete the 7 extracted skill directories from cortex-command
- **Files** (in cortex-command — all deleted):
  - `skills/ui-a11y/` (delete)
  - `skills/ui-brief/` (delete directory + `references/` subtree)
  - `skills/ui-check/` (delete)
  - `skills/ui-judge/` (delete)
  - `skills/ui-lint/` (delete)
  - `skills/ui-setup/` (delete)
  - `skills/pr-review/` (delete directory + `references/` subtree)
- **What**: Delete all 7 skill directories from `skills/`. After deletion, remove any stale global symlinks under `~/.claude/skills/` that point to these now-deleted directories (e.g., `~/.claude/skills/ui-lint`, `~/.claude/skills/pr-review`) — these symlinks were created by prior `just setup` runs and are no longer valid. Commit in cortex-command.
- **Depends on**: [10, 14]
- **Complexity**: complex
- **Context**: Research.md (Codebase Analysis) confirms all 7 skill subtrees. Run `just check-symlinks` (or equivalent) after deletion to confirm no broken symlink warnings for the 7 names. The deploy recipes still reference these names until Task 12 removes them, so run the symlink check before editing the justfile.
- **Verification**: `ls skills/ | grep -cE '^(ui-a11y|ui-brief|ui-check|ui-judge|ui-lint|ui-setup|pr-review)$'` = 0 — pass if count = 0. `readlink ~/.claude/skills/ui-lint 2>/dev/null` is empty — pass if symlink gone.
- **Status**: [ ] pending

### Task 12: Verify and update justfile deploy recipes
- **Files** (in cortex-command):
  - `justfile` (update only if explicit skill names exist — may be no-op if glob-based)
- **What**: Read the `deploy-skills`, `setup-force`, `verify-setup`/`check-symlinks`, and `validate-skills` recipes. **If** any recipe contains hardcoded explicit entries for the 7 extracted skill names, remove those entries and commit the change. **If** all four recipes use `skills/*/SKILL.md` glob patterns with no hardcoded skill names, the directory deletions in Task 11 already exclude the skills automatically — make no edits and skip the commit (do not create an empty commit).
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: Research.md (Codebase Analysis) identifies justfile skill-iteration at `setup-force` (~L64–73), `deploy-skills` (~L224–261), `verify-setup`/`check-symlinks` (~L758–762), `validate-skills` (~L716, ~L839). If those recipes use `skills/*/SKILL.md` glob patterns (not explicit name lists), this task is a no-op — the glob naturally excludes deleted directories. Determine which case applies before deciding whether to edit or skip.
- **Verification**: Read the four recipes first. If explicit names were present and removed: `grep -cE 'skills/(ui-a11y|ui-brief|ui-check|ui-judge|ui-lint|ui-setup|pr-review)/' justfile` = 0 — pass if count = 0 (more targeted than a bare name match). If recipes are glob-based and no edits were made: `readlink ~/.claude/skills/ui-lint 2>/dev/null` is empty — pass if symlink gone (confirms Task 11's cleanup held).
- **Status**: [ ] pending

### Task 13: Update cortex-command documentation
- **Files** (in cortex-command):
  - `docs/skills-reference.md`
  - `docs/agentic-layer.md`
  - `docs/setup.md`
  - `docs/dashboard.md`
  - `docs/ui-tooling.md` (delete — moved to new repo in Task 8)
- **What**:
  - `docs/skills-reference.md`: remove the 7 extracted skills from the primary catalog; add a short "Optional opt-in plugins" section pointing at `cortex-command-plugins` with install instructions (`claude /plugin marketplace add <url>`); retain a pointer for `harness-review` noting it is project-local to cortex-command.
  - `docs/agentic-layer.md`: remove the 7 extracted skills from the catalog table; update any local markdown link to `ui-tooling.md` (or `docs/ui-tooling.md`) to point at the new repo's GitHub URL (or replace with a note).
  - `docs/setup.md`: rewrite the "install all six or none" UI-bundle section and `rm ~/.claude/skills/ui-*` removal instructions — replace with plugin install flow (`claude /plugin marketplace add <url>` + per-project enable in `.claude/settings.json`).
  - `docs/dashboard.md`: update mentions of `ui-judge` and `ui-a11y` to note they now live in `cortex-command-plugins` and require the plugin to be enabled (use namespaced form `cortex-ui-extras:ui-judge` where relevant).
  - Delete `docs/ui-tooling.md` (it moved to the new repo in Task 8).
  Read each doc before editing. Historical files (retros, backlog, lifecycle events) are NOT rewritten.
- **Depends on**: [8, 12]
- **Complexity**: complex
- **Context**: Research.md reports: `docs/skills-reference.md` has 27 occurrences of extracted skill names; `docs/agentic-layer.md` has 14 occurrences. Spec R8 acceptance: `grep -c 'cortex-command-plugins' docs/skills-reference.md` ≥ 1 AND `grep -c 'install all six or none' docs/setup.md` = 0 AND `ls docs/ui-tooling.md 2>/dev/null` empty AND `grep -cE '\[.*\]\(ui-tooling\.md\)' docs/agentic-layer.md` = 0.
- **Verification**: `grep -c 'cortex-command-plugins' docs/skills-reference.md` ≥ 1 — pass if count ≥ 1. `grep -c 'install all six or none' docs/setup.md` = 0 — pass if count = 0. `ls docs/ui-tooling.md 2>/dev/null` empty — pass if file absent.
- **Status**: [ ] pending

### Task 14: Initial commit of cortex-command-plugins and acceptance checklist
- **Files** (in `~/Workspaces/cortex-command-plugins/`):
  - all files created in Tasks 3–9 (committed via standard git workflow)
- **What**: Run the full spec acceptance checklist first (before committing) — verify marketplace.json, plugin counts, skill directory counts, probe-guard execution, validator dry-run. If all items pass, stage all files in the new repo (`git add -A`) and create an initial commit. **This task is not complete until all acceptance checklist items pass.** If any item fails, fix the new repo contents and re-run the checklist before committing. Task 11 (which deletes skills from cortex-command) must not start until this task is fully complete. The new repo does not yet have a remote; the user pushes to GitHub separately.
- **Depends on**: [6, 7, 8, 9]
- **Complexity**: simple
- **Context**: This task operates in `~/Workspaces/cortex-command-plugins/`. Use plain `git commit -m "..."` (not `/commit` skill — that skill is for cortex-command). Suggested commit message: `"Add cortex-ui-extras and cortex-pr-review plugins with validation"`. Run full acceptance: `jq '.plugins | length' .claude-plugin/marketplace.json` = 2; `ls plugins/cortex-ui-extras/skills/ | wc -l` = 6; `python3 scripts/validate-skill.py plugins/cortex-ui-extras/skills` exits 0; `python3 scripts/validate-skill.py plugins/cortex-pr-review/skills` exits 0; `grep -c '~/.claude/skills/ui-' plugins/cortex-ui-extras/skills/ui-check/SKILL.md` = 0.
- **Verification**: `git -C ~/Workspaces/cortex-command-plugins log --oneline | head -1` is non-empty — pass if a commit exists. `python3 ~/Workspaces/cortex-command-plugins/scripts/validate-skill.py ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/skills` exits 0 — pass if exit code = 0.
- **Status**: [ ] pending

## Verification Strategy

End-to-end checks after all tasks, run from cortex-command root:

1. `ls skills/ | grep -cE '^(ui-a11y|ui-brief|ui-check|ui-judge|ui-lint|ui-setup|pr-review|harness-review)$'` = 0 — all extracted + demoted skills gone from `skills/`
2. `ls .claude/skills/harness-review/SKILL.md` exists — harness-review in project-local scope
3. `readlink ~/.claude/skills/ui-lint 2>/dev/null` is empty — global symlink cleaned
4. `ls docs/ui-tooling.md 2>/dev/null` empty — file removed from this repo
5. `grep -c 'cortex-command-plugins' docs/skills-reference.md` ≥ 1 — docs updated
6. In new repo: `jq '.plugins | length' .claude-plugin/marketplace.json` = 2; `ls plugins/cortex-ui-extras/skills/ | wc -l` = 6; validator exits 0
7. Token savings ≥ 1500 tokens (gated in Task 1 — if this gate failed, implementation did not proceed)

## Veto Surface

- **Task 1 blocks overnight dispatch**: Task 1 requires an interactive Claude Code session (`/context`, `/plugin` commands). The plan must not be dispatched to an overnight agent until Task 1 is manually completed and checked off. All remaining tasks are safe for overnight execution once Task 1 is done.
- **New repo path**: plan assumes `~/Workspaces/cortex-command-plugins/`. User may prefer a different parent directory — change only affects file paths in Tasks 3–9 and 14.
- **Task 1 abort gate**: if the benchmark returns < 1500 tokens, the entire feature halts. This is by spec — the plan does not implement Option C fallback.
- **ui-tooling.md back-link**: implementation-time choice between GitHub URL and removal — either satisfies R1.
- **validate-skills justfile recipe**: if the recipe uses `skills/*/SKILL.md` glob rather than an explicit list, Task 12 needs no change there. Confirm before editing.
- **Probe guard shell logic**: the grep inversion in Task 9 (`grep ... && exit 1 || exit 0`) should be confirmed against the actual GitHub Actions YAML — GH Actions' `run:` steps treat non-zero exit as failure, so the logic is correct, but verify shell behavior under `set -e` if the workflow uses it.

## Scope Boundaries

Per spec Non-Requirements:
- No in-repo plugin structure in cortex-command (no `plugins/` dir, no marketplace entries in `claude/settings.json`)
- No CI canary for upstream #40789 regression (manual observation only)
- No call-graph validator asserting core skills never reference extracted skill names
- No rewriting of historical artifacts (retros, backlog, lifecycle events)
- No automated cross-repo version pinning
- No git history preservation on move (copy-then-delete accepted)
- No `just setup` integration for the new repo's marketplace install (one-time-per-machine `/plugin marketplace add <url>` documented in new repo's README only)
- No publishing workflow (CI, release tags, versioning) for the new repo in this ticket
- `tests/test_skill_contracts.py` not updated (plugin lives in a separate repo; cortex-command's test suite scope stays within this repo)
