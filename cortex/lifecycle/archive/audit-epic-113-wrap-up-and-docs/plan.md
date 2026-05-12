# Plan: audit-epic-113-wrap-up-and-docs

## Overview

Six tasks, one per commit group from the spec's Technical Constraints. Each task performs the file edits for its commit group and commits as a unit. Strict serial dependency chain enforces commit ordering — no parallel dispatch. Verification combines negative greps (forbidden phrases removed) with positive greps (replacement content present) so deletion-only edits cannot pass.

## Tasks

### Task 1: Rewrite `docs/plugin-development.md` (R1) — commit 1
- **Files**: `docs/plugin-development.md`
- **What**: Replace the current transitional scaffolding (5 ticket-N future-tense references) with a steady-state maintainer dogfood guide covering (a) registering the local marketplace via `/plugin marketplace add $PWD`, (b) `just build-plugin` and dual-source generation flow, (c) `just setup-githooks` for drift detection, (d) drift-fix workflow when the pre-commit hook flags drift, (e) build-output vs hand-maintained plugin distinction. Commit with `/cortex-interactive:commit`.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Current doc is at `docs/plugin-development.md` (~85 lines). Keep level-1 title; verify and preserve `[← Back to README](../README.md)` backlink convention if present. Drop the "Why this exists" rationale paragraph that anchors to ticket 122. Reference `.githooks/pre-commit` (lines 1–13 describe four-phase build/drift logic) for dual-source mechanics. Reference `justfile` recipes `build-plugin`, `_list-build-output-plugins`, `_list-hand-maintained-plugins`, `setup-githooks`. Marketplace shape: `.claude-plugin/marketplace.json`.
- **Verification**: `grep -cE "ticket 12[012]|before ticket|until ticket|when ticket [0-9]+ lands" docs/plugin-development.md` = 0; `grep -c "/plugin marketplace add \$PWD" docs/plugin-development.md` ≥ 1; `grep -c "just build-plugin" docs/plugin-development.md` ≥ 1; `grep -c "just setup-githooks" docs/plugin-development.md` ≥ 1; `grep -ciE "drift" docs/plugin-development.md` ≥ 1; `grep -ciE "build-output|hand-maintained" docs/plugin-development.md` ≥ 1; `git log -1 --pretty=%s` matches the commit-message convention (imperative, capitalized, no trailing period, ≤72 chars).
- **Status**: [x] complete (commit 811cd5b)

### Task 2: User-facing onboarding doc cleanup (R2, R5, R6) — commit 2
- **Files**: `README.md`, `docs/setup.md`
- **What**: (R2) Edit `README.md:187` table cell — current `Installation, symlinks, authentication, customization` → reword to match docs/setup.md's actual current scope (e.g., `Installation, plugins, authentication, customization`). (R5) Edit `docs/setup.md:180` — drop the `(ticket 119)` parenthetical from the `cortex init` sentence. (R6) Edit `docs/setup.md:194,196` — delete the two sentences that reference "the pre-117 version of `claude/settings.json`" and "`git show HEAD:claude/settings.json` on the pre-117 commit"; keep the surrounding `permissions.deny` paragraph's "compose your own / do not paste blindly" framing intact. Commit with `/cortex-interactive:commit`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: README.md table is the "Documentation" section table at the bottom. docs/setup.md's actual current contents: Prerequisites, Install, Authentication, Customization, Per-repo permission scoping, macOS Notifications, Dependencies. setup.md line 180 is in the `sandbox.filesystem.allowWrite` paragraph; lines 194-196 are in the `permissions.deny` paragraph that already contains "compose your own."
- **Verification**: `grep -c "Installation, symlinks" README.md` = 0; `grep -ciE "Installation, plugins|installation.*plugin" README.md` ≥ 1 (positive gate against deletion-only or wrong-replacement); `grep -c "ticket 119" docs/setup.md` = 0; `grep -cE "pre-117" docs/setup.md` = 0; `grep -ciE "compose your own|do not paste" docs/setup.md` ≥ 1 (positive gate confirming surrounding `permissions.deny` paragraph survived).
- **Status**: [x] complete (commit 14d604e)

### Task 3: Reference-doc cleanup (R3, R7) — commit 3
- **Files**: `docs/skills-reference.md`, `docs/backlog.md`
- **What**: (R3a) Edit `docs/skills-reference.md:6` — replace `**Assumes:** Claude Code is set up and skills are symlinked.` with the post-113 install assumption (e.g., `**Assumes:** Claude Code is set up and the cortex-interactive plugin is installed.`). (R3b) Edit line 157 — rewrite "not published as a plugin or symlinked globally" to refer to plugin distribution only. (R7) Edit `docs/backlog.md:205-210` — drop the "post-epic-120" temporal qualifier on line 205; rewrite the "How symlink resolution works" subsection (lines 208-210) so it (i) describes plugin `bin/` directories being added to PATH directly by Claude Code's plugin loader, AND (ii) preserves the existing explanation of how Python's `__file__` resolves to the real script path. Avoid the literal phrase "host-level symlink" in the replacement. Commit with `/cortex-interactive:commit`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: skills-reference.md line 157 is in the `harness-review` subsection. The replacement should explain harness-review is project-local because it is specific to cortex-command's overnight runner inventory, without invoking the "symlinked globally" alternative. backlog.md `__file__` explanation: `pathlib.Path(__file__).resolve().parent` is the canonical Python idiom for finding the script's own directory; preserve this teaching content.
- **Verification**: `grep -c "skills are symlinked" docs/skills-reference.md` = 0; `grep -c "symlinked globally" docs/skills-reference.md` = 0; `grep -c "cortex-interactive plugin" docs/skills-reference.md` ≥ 1 (positive gate that the post-113 install assumption replaced line 6, not deletion-only); `grep -c "\*\*Assumes:\*\*" docs/skills-reference.md` ≥ 1 (positive gate that line 6's preamble framing survived); `grep -c "post-epic-120" docs/backlog.md` = 0; `grep -c "~/.local/bin/" docs/backlog.md` = 0; `grep -c "__file__" docs/backlog.md` ≥ 1 (positive gate that the Python resolution explanation survives the rewrite); `grep -ciE "plugin loader|added to PATH" docs/backlog.md` ≥ 1 (positive gate that the new mechanism is named).
- **Status**: [x] complete (commit 51d0ab5)

### Task 4: Manifest + review-criteria cleanup (R4, R8, R9) — commit 4
- **Files**: `.claude-plugin/marketplace.json`, `lifecycle.config.md`
- **What**: (R4) Rewrite all four plugin descriptions in `.claude-plugin/marketplace.json` to a uniform style — one sentence, present tense, product-focused, no parenthetical-implementation enumeration. Specifically eliminate "(PEP 723 single-file server.py)" from `cortex-overnight-integration` and "(brief, setup, lint, a11y, judge, check)" from `cortex-ui-extras`. The other two are already noun-phrase product-focused; minor consistency rewording only if needed. (R9) Add `"$schema": "https://json.schemastore.org/claude-code-marketplace.json"` at the top of the JSON object; `"version": "1.0.0"` after `name`; per-plugin `"category": "development"` for all four plugins. (R8) Edit `lifecycle.config.md:20` — replace `New config files must follow the symlink pattern (source in repo, symlinked to system location)` with a criterion reflecting plugin-distribution (e.g., `New config files ship via the relevant plugin tree (cortex-interactive, cortex-overnight-integration) — never as host-level symlinks.`). Commit with `/cortex-interactive:commit`.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Reference: `https://github.com/anthropics/claude-code/blob/main/.claude-plugin/marketplace.json` for canonical shape and description-style examples. All four cortex plugins fit `development`. Preserve existing fields (`owner`, plugin `name`, `source`). lifecycle.config.md `## Review Criteria` section already has three other criteria about valid JSON, executable hooks, skill frontmatter — match their syntactic shape.
- **Verification**: `grep -c "PEP 723\|Hosts the canonical" .claude-plugin/marketplace.json` = 0; `grep -c "(brief, setup, lint, a11y, judge, check)" .claude-plugin/marketplace.json` = 0; `jq -r '."$schema"' .claude-plugin/marketplace.json` returns the schemastore URL; `jq -r '.version' .claude-plugin/marketplace.json` returns `1.0.0`; `jq '[.plugins[].category] | length' .claude-plugin/marketplace.json` returns `4`; `jq -r '.plugins[].description' .claude-plugin/marketplace.json | wc -l` returns `4` (positive gate against accidentally deleting a description); `jq '.' .claude-plugin/marketplace.json` exits 0 (valid JSON); `jq -r '.plugins[].description' .claude-plugin/marketplace.json | grep -c ';'` = 0; `grep -c "symlink pattern" lifecycle.config.md` = 0; `grep -ciE "plugin tree|cortex-interactive|cortex-overnight-integration" lifecycle.config.md` ≥ 1 (positive gate; references at least one plugin name in the Review Criteria section).
- **Status**: [x] complete (commit 320941c)

### Task 5: Author-state cleanup (R10, R11, R12) — commit 5
- **Files**: `requirements/remote-access.md`, `requirements/pipeline.md`, `CLAUDE.md`
- **What**: (R10) Drop the bullet at `requirements/remote-access.md:60` (the one referencing the previously-broken `remote/SETUP.md` link). Delete the entire bullet; renumber or rewrite surrounding text only as needed to keep the section coherent. (R11a) Edit `CLAUDE.md:18` — rewrite the `bin/` entry (currently `\`bin/\` - Global CLI utilities (migrate to \`cortex-interactive\` plugin bin/ in ticket 120)`) to describe the steady state: top-level `bin/` is the canonical source, mirrored into the cortex-interactive plugin's `bin/` via dual-source enforcement. (R11b) Edit `CLAUDE.md:47` — drop the `(ticket 120 scope)` parenthetical. (R12) Edit `requirements/pipeline.md:151` — rewrite `Stable contract for ticket 116 MCP control plane.` as steady-state, e.g., `Stable contract for the MCP control plane (versioned runner IPC).` Commit with `/cortex-interactive:commit`.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: requirements/remote-access.md bullet is in the `## Open Questions` section (verify exact section name during execution). CLAUDE.md line 18 is in `## Repository Structure`; line 47 is in `## Conventions`. requirements/pipeline.md line 151 is in the file's quality-attributes/invariants section. None require changes to surrounding text beyond the noted edits.
- **Verification**: `grep -c "remote/SETUP.md" requirements/remote-access.md` = 0; `wc -l < requirements/remote-access.md` ≥ 30 (positive structural sanity gate against whole-file deletion); `grep -c "in ticket 120" CLAUDE.md` = 0; `grep -c "(ticket 120 scope)" CLAUDE.md` = 0; `grep -ciE "canonical source|dual-source" CLAUDE.md` ≥ 1 (positive gate that the line 18 rewrite produced steady-state content, not just deleted the parenthetical); `grep -c "for ticket 116" requirements/pipeline.md` = 0; `grep -ciE "MCP control plane.*versioned|versioned.*MCP control plane|versioned runner IPC" requirements/pipeline.md` ≥ 1 (positive gate that line 151's specific replacement preserved the architectural meaning, not just removed the ticket reference — anchored on phrasing the rewrite must produce, not pre-existing content elsewhere).
- **Status**: [x] complete (commit b3f9589)

### Task 6: Final grep audit and fix any stragglers (R13) — commit 6
- **Files**: any files surfaced by the audit grep — most likely none after Tasks 1–5, but the audit is the safety net. If any straggler is found, the file holding it is added to this task's Files list at fix time.
- **What**: Run the spec's R13 forbidden-phrase regex across the full audit surface, including `plugins/*/.claude-plugin/plugin.json` (which the per-task verifications do not cover). Filter out the explicitly enumerated triage-as-clean hits. Any remaining hit is a residual; fix it with a surgical edit and re-run the audit until it passes. Commit with `/cortex-interactive:commit` (empty commit acceptable if no stragglers — `git commit --allow-empty` with the audit log in the message).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: The full R13 regex is `(skills are symlinked|symlinked globally|Installation, symlinks|before ticket [0-9]+|until ticket [0-9]+|when ticket [0-9]+ lands|in ticket 120|\(ticket 120 scope\)|for ticket 116|ticket 119|pre-117|PEP 723|Hosts the canonical|post-epic-120|symlink pattern|brief, setup, lint, a11y, judge, check)`. Surface includes `docs/`, `README.md`, `.claude-plugin/marketplace.json`, `plugins/*/.claude-plugin/plugin.json`, `justfile`, `lifecycle.config.md`, `CLAUDE.md`, `requirements/`. Use `find` for plugin-glob safety per spec — if the glob expands to zero matches, fail loudly rather than silently passing.
- **Verification**: After triage-as-clean filter applied, audit returns no remaining hits. Run: ```{ find docs README.md plugins/ -name 'plugin.json' -path '*/.claude-plugin/*' -type f -print 2>/dev/null; echo .claude-plugin/marketplace.json; echo justfile; echo lifecycle.config.md; echo CLAUDE.md; find requirements/ -type f -name '*.md' 2>/dev/null; find docs/ -type f -name '*.md' 2>/dev/null; echo README.md; } | sort -u | xargs grep -nE '<R13 regex>' 2>/dev/null | grep -vE 'agentic-layer\.md:311|overnight-operations\.md:317|sdk\.md:102'``` returns no lines (exit code may be 0 or 1 from grep — check that stdout is empty). Also: `find plugins/ -name 'plugin.json' -path '*/.claude-plugin/*' -type f` returns ≥ 4 results (confirms plugin.json files were found by find, not silently missed by a broken glob).
- **Status**: [x] complete (commit 44e7693)

## Verification Strategy

After all 6 tasks (and 6 commits) complete:
1. Re-run Task 6's audit verification to confirm no residual stale phrasings repo-wide.
2. Confirm all per-R acceptance criteria from the spec pass — each task's Verification field is now the exact superset of the spec's acceptance for the Rs in that commit group (positive greps added per critical-review feedback so deletion-only or wrong-replacement edits cannot pass).
3. `jq '.' .claude-plugin/marketplace.json` returns valid JSON.
4. Read `docs/plugin-development.md` end-to-end and confirm it reads as a coherent steady-state guide. Interactive/session-dependent: rationale — full-rewrite quality cannot be reduced to grep counts alone; one terminal human-read pass is the only sufficient gate.
5. `git log --oneline -6` shows six commits in the order specified by Task 1 → Task 6, matching the spec's Technical Constraints.

## Veto Surface

- **Six-task / six-commit collapse from prior 11-task draft.** Driven by critical review: the prior `Depends on: none` for Tasks 1–10 was incompatible with the spec's six-ordered-commits requirement under cortex-command's parallel-dispatch model. Each commit-group is now one task. The implementer may legitimately split a task's commit (e.g., Task 4 into two commits — manifest first, lifecycle.config separately) if it helps review.
- **R13 regex's "host-level symlink" exclusion** — design choice carried over from spec; the alternation is omitted because `README.md:7`'s legitimate steady-state phrasing would always trip it.
- **Task 6 may produce an empty commit** if Tasks 1–5 leave no stragglers. `git commit --allow-empty` documents that the audit ran and passed; this is preferable to silently skipping the commit.
- **`jq` dependency** for Task 4 verification. `jq` is listed in the project's standard tooling per CLAUDE.md; if absent, fall back to `python3 -c "import json; ..."` — but `jq` is the documented expectation.

## Scope Boundaries

Per the spec's Non-Requirements section, all of the following are explicitly out of scope:
- No CI grep linter (one-time audit via Task 6 only).
- No edits to `retros/` (append-only convention).
- No pre-113 migration aside (ticket 124 stays wontfix).
- No restructuring of doc organization or doc-ownership transfers.
- No code, hook, script, or behavior changes — docs/config/text only.
- No tightening of `CLAUDE.md:48` setup-githooks framing (Task 5 covers different lines: 18 + 47).
- No rewrite of `docs/agentic-layer.md:311` (legitimate `latest-overnight` runner-state symlink).
- No global rename of "symlink" across the repo.
- Same-cause-adjacent residue is in scope (R10–R12 inclusion); unrelated stale residue from other origins is out of scope.
- No creation of `remote/SETUP.md` in this repo (machine-config owns that).
