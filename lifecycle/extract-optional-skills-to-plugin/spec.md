# Specification: Extract optional skills into a separate plugin repo

## Problem Statement

The repo ships 26 skills, all deployed globally via symlink to `~/.claude/skills/`. Every session pays the token cost of loading every skill's description into the system prompt, regardless of whether the user uses them in the current project. This is near the practical context-budget ceiling (~2% of context; 20–30 skills per Anthropic's own guidance). Peripheral skills — UI tooling and PR-review automation — are only relevant in specific repos. Extracting them into a **separate public repo (`cortex-command-plugins`) as Claude Code plugins, disabled by default, opt-in per project** restores per-project discretion over which skill descriptions occupy each session's context window. A separate repo isolates the opt-in concerns from the core toolkit, simplifies this repo's deployment surface, and gives users who don't want those skills a cleaner fork story.

## Requirements

Each requirement is tagged `[MUST]` (blocking) or `[SHOULD]` (high-value but non-blocking).

1. **[MUST] Create `cortex-command-plugins` repo scaffolding** (outside this repo tree; user pushes to a new public GitHub repo after local scaffolding is complete). Contents:
   - `.claude-plugin/marketplace.json` at the repo root — Claude Code's marketplace manifest, listing both plugins with local-path `source: ./plugins/<name>` entries.
   - `plugins/cortex-ui-extras/.claude-plugin/plugin.json` + `plugins/cortex-ui-extras/skills/<6 UI skills>/SKILL.md` (each UI skill retains its own `references/` or `scripts/` subtree — e.g., `ui-brief/references/design-md-template.md`, `ui-brief/references/theme-template.md` — moved as part of the skill subtree, not left behind in `cortex-command`).
   - `plugins/cortex-pr-review/.claude-plugin/plugin.json` + `plugins/cortex-pr-review/skills/pr-review/SKILL.md` + `plugins/cortex-pr-review/skills/pr-review/references/protocol.md` (the full pr-review subtree moves intact).
   - `docs/ui-tooling.md` — the existing `cortex-command/docs/ui-tooling.md` (127 lines) relocates to the new repo as its canonical UI-tooling reference. Update its back-link from `[← Back to Agentic Layer](agentic-layer.md)` to a GitHub link back to `cortex-command/docs/agentic-layer.md` (or remove the back-link — implementation-time choice).
   - `README.md` at repo root explaining what the repo is, how to install (`claude /plugin marketplace add <github-url>`), how to enable per-project, and the relationship to `cortex-command`. The README references `docs/ui-tooling.md` as the in-repo reference for the UI cluster.
   - `LICENSE` matching `cortex-command`.
   - `scripts/validate-skill.py` — a copy of `cortex-command`'s current validator (or a pinned-version copy) — enforces `name` + `description` frontmatter, YAML parse, and `{{variable}}` consistency for each plugin's SKILL.md files (see R9).
   - `.github/workflows/validate.yml` — GitHub Actions workflow running `scripts/validate-skill.py` against `plugins/*/skills/` on push and pull-request (see R9).
   Acceptance: directory tree exists locally under an agreed path (e.g., `~/Workspaces/cortex-command-plugins/`); `jq '.plugins | length' .claude-plugin/marketplace.json` = 2; both `plugin.json` files are valid JSON with a `name` field matching the directory; `ls plugins/cortex-ui-extras/skills/ui-brief/references/` contains `design-md-template.md` and `theme-template.md`; `ls plugins/cortex-pr-review/skills/pr-review/references/` contains `protocol.md`; `ls docs/ui-tooling.md` exists in the new repo.

2. **[MUST] Move the 6 UI skills into `cortex-command-plugins`** — `ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup`. Each skill's full subtree (`SKILL.md` + any `references/` or `scripts/`) moves to `plugins/cortex-ui-extras/skills/<skill>/`. Peer-skill dispatches (e.g., `ui-check` invoking `ui-lint`) use bare names — Anthropic's plugin-dev reference confirms bare-name peer dispatch is the correct pattern within a plugin. Acceptance in `cortex-command-plugins`: `ls plugins/cortex-ui-extras/skills/ | wc -l` = 6 with exactly those 6 names.

3. **[MUST] Move `pr-review` into `cortex-command-plugins`** — full subtree (`SKILL.md` + `references/`) to `plugins/cortex-pr-review/skills/pr-review/`. Single-skill plugin named for its purpose. Acceptance: `ls plugins/cortex-pr-review/skills/` = `pr-review`; `jq -r .name plugins/cortex-pr-review/.claude-plugin/plugin.json` = `cortex-pr-review`.

4. **[MUST] Remove the extracted skills from `cortex-command`** and from `~/.claude/skills/`. Delete `skills/ui-a11y/`, `skills/ui-brief/`, `skills/ui-check/`, `skills/ui-judge/`, `skills/ui-lint/`, `skills/ui-setup/`, `skills/pr-review/` in this repo. Update `justfile` deploy recipes (`setup-force`, `deploy-skills`) to no longer symlink those names into `~/.claude/skills/`. Acceptance: `ls skills/ | grep -cE '^(ui-a11y|ui-brief|ui-check|ui-judge|ui-lint|ui-setup|pr-review)$'` = 0; `readlink ~/.claude/skills/ui-lint 2>/dev/null` is empty (or `just check-symlinks` returns no warning for those names).

5. **[MUST] Rewrite `ui-check` FS probes BEFORE moving it**: in the current `skills/ui-check/SKILL.md`, replace the hardcoded `~/.claude/skills/ui-lint/SKILL.md` probe at `:11` by removing the line (rely on invocation failure, which is a clean error surface since ui-check is in the same plugin as ui-lint after the move). Replace the `~/.claude/skills/ui-a11y/SKILL.md` check at `:74` with a skill-availability check that sets `a11y.status = "skipped"` with reason `"ui-a11y not available"` — preserving the current graceful-skip behavior. Commit the rewrite first so the moved copy in the new repo starts with correct probe logic. Acceptance after move: `grep -c '~/.claude/skills/ui-' plugins/cortex-ui-extras/skills/ui-check/SKILL.md` = 0 AND `grep -c 'a11y.status = \"skipped\"' plugins/cortex-ui-extras/skills/ui-check/SKILL.md` ≥ 1.

6. **[MUST] Demote `harness-review` to project-local scope** in `cortex-command` — move `skills/harness-review/` to `.claude/skills/harness-review/` in this repo (alongside the existing `.claude/skills/setup-merge/`). Remove the global symlink from `~/.claude/skills/harness-review`. Update `justfile` to not deploy `harness-review` globally. The skill remains invokable only when Claude runs with `cortex-command` as CWD. Acceptance: `ls .claude/skills/harness-review/SKILL.md` exists; `ls skills/harness-review 2>/dev/null` is empty; `readlink ~/.claude/skills/harness-review 2>/dev/null` is empty.

7. **[MUST] Empirical token-savings benchmark with abort threshold (measurement methodology defined)**: before implementation begins, run the following measurement and document it in `research.md` (appendix).

   **What to measure**: the full character length of the "The following skills are available for use with the Skill tool:" block that Claude Code injects into the session system reminder. The block contains one line per available skill (namespaced or bare) with the skill's `description` field. **Do not measure** full SKILL.md files or full frontmatter — only what actually appears in the system-reminder block, since that is what the session context pays for.

   **How to estimate tokens from characters**: use the 1 token ≈ 4 chars approximation for cross-check, but prefer the output of Claude Code's `/context` command (or equivalent) for the authoritative token count. Both numbers should be recorded.

   **Measurement protocol**:
   1. In a fresh `cortex-command` session, record `/context`'s reported system-reminder size (baseline).
   2. Record the character count of each of the 7 extracted skills' `description:` field as declared in their current `skills/<name>/SKILL.md` frontmatter.
   3. Disable `claude-md-management` via `/plugin`, start a new session, and record `/context` again. The delta is the savings from removing that plugin's entries (1 command + 1 skill, per the installed plugin inspection earlier in this lifecycle).
   4. Compute: `expected_savings_chars = sum(description_chars for each of 7 extracted skills)`. Convert to expected tokens via the ratio of (step 3 token delta) ÷ (step 3 char delta), or via the 1:4 approximation if step 3 is unavailable. This projects from the proxy to the extracted set without assuming size equivalence.

   **Abort threshold**: if `expected_savings_tokens < 1500`, halt and escalate — the value case is too weak. Fallback is Option C (gitignored/opt-in symlinks, `deploy-skills` honors a `skills.skip` list). Rationale for 1500: ~60% of #064's ~2.6k deferral figure, providing headroom for measurement noise while still clearing the "<2% of context" bar that #064 cited as the deferral reason.

   Acceptance: `grep -cE '[0-9]+\s*tokens?' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1 AND `grep -c 'v2\.' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1 AND `grep -c 'abort threshold' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1 AND `grep -c 'expected_savings_tokens' lifecycle/extract-optional-skills-to-plugin/research.md` ≥ 1.

8. **[MUST] Update `cortex-command` docs after the move** (promoted from `[SHOULD]` because stale references to moved files are a broken-install hazard, not merely a tidiness issue):
   - **`docs/skills-reference.md`**: remove the 7 extracted skills from the primary catalog; add a short "Optional opt-in plugins" section pointing at `cortex-command-plugins` with install instructions (`claude /plugin marketplace add <url>`); retain a pointer for `harness-review` noting it's a project-local skill.
   - **`docs/agentic-layer.md`**: remove the 7 extracted skills from the catalog table; update any link to `docs/ui-tooling.md` to point at the new repo's copy (GitHub URL or a short redirect note).
   - **`docs/setup.md`**: rewrite the "install all six or none" UI-bundle section and the `rm ~/.claude/skills/ui-*` removal instructions — replace with install instructions for the new repo (`claude /plugin marketplace add <url>` + per-project enable in `.claude/settings.json`).
   - **`docs/dashboard.md`**: update mentions of `ui-judge` and `ui-a11y` skills to note they now live in `cortex-command-plugins` (namespaced form where relevant) and require the plugin to be enabled.
   - **`docs/ui-tooling.md`**: removed from `cortex-command` (moves to the new repo per R1). Delete the file in this repo.
   - Historical files (retros, backlog, lifecycle events) are NOT rewritten.
   
   Acceptance: `grep -c 'cortex-command-plugins' docs/skills-reference.md` ≥ 1 AND the 7 extracted skill names no longer appear in the primary catalog table in `docs/skills-reference.md` AND `grep -c 'cortex-command-plugins' docs/setup.md` ≥ 1 AND `grep -c 'install all six or none' docs/setup.md` = 0 (stale bundle language removed) AND `ls docs/ui-tooling.md 2>/dev/null` is empty (file removed from this repo) AND `grep -cE '\[.*\]\(ui-tooling\.md\)' docs/agentic-layer.md` = 0 (no more local markdown links to the moved file).

9. **[MUST] Frontmatter validation in new repo**: `cortex-command-plugins` ships `scripts/validate-skill.py` (copied from or referencing `cortex-command`'s current validator) plus a `.github/workflows/validate.yml` GitHub Actions workflow that runs the validator against `plugins/*/skills/*/SKILL.md` on push and pull-request. The workflow is the test boundary — without it, frontmatter regressions in the new repo land without detection. Acceptance: `python3 scripts/validate-skill.py plugins/cortex-ui-extras/skills` exits 0 on a clean checkout of the new repo; `.github/workflows/validate.yml` exists with a `jobs.*.steps` entry invoking `validate-skill.py`.

10. **[SHOULD] Post-move guard for `ui-check` FS-probe reintroduction**: Add a small assertion to the new repo's `validate.yml` (or a companion `scripts/ui-check-probe-guard.sh`) that greps `plugins/cortex-ui-extras/skills/ui-check/SKILL.md` for `~/.claude/skills/ui-` and fails if any match is found. Prevents silent reintroduction of the hardcoded FS paths that R5 removes. Acceptance: running the guard against the migrated file returns zero matches (pass); manually introducing a `~/.claude/skills/ui-lint/SKILL.md` reference in ui-check's body makes the guard fail.

## Non-Requirements

- **Not extracting** `retro`, `diagnose`, `devils-advocate`, `skill-creator`, `fresh`, `evolve`. Each has programmatic or hardcoded references blocking safe extraction. Defer.
- **No in-repo plugin structure** in `cortex-command`. No `plugins/` directory, no `.claude-plugin/marketplace.json`, no plugin entries in `claude/settings.json`'s `enabledPlugins`, no update to `REQUIRED_PLUGIN_KEYS` in `merge_settings.py`, no CLAUDE.md plugin-cache deviation note. The new repo owns all of that.
- **No CI canary** for upstream #40789 regression. Manual verification on observation.
- **No call-graph validator** asserting core skills never reference extracted skill names. Reviewer discipline suffices.
- **No rewriting of historical artifacts** (retros, backlog items, lifecycle event logs). Stale references accepted.
- **No automated cross-repo version pinning**. The new repo releases stand alone; cortex-command does not reference a specific plugin version.
- **No git history preservation on move**. Copy-then-delete is acceptable — the skills' git history in `cortex-command` remains searchable via `git log -- skills/ui-lint/` up to the deletion commit.
- **No just-setup change to install the new marketplace**. User performs `/plugin marketplace add <url>` once per machine, same as for any other Claude Code plugin. `just setup` in `cortex-command` is unaware of `cortex-command-plugins`.
- **No publishing workflow** (CI, release tags, versioning) for the new repo in this ticket. The new repo ships as a working plugin marketplace; formal release tooling is a future decision.

## Edge Cases

- **User enables `cortex-ui-extras` in a project before running `/plugin marketplace add <url>`**: Claude Code silently ignores the unresolved entry; skills don't appear. The `cortex-command-plugins` README documents the ordering requirement.
- **User clones `cortex-command` but never adds the `cortex-command-plugins` marketplace**: `cortex-command` continues to function; UI skills and `/pr-review` are simply unavailable. No error, no broken install. This is the intended "opt in" behavior.
- **Fresh `cortex-command-plugins` clone for a collaborator**: the collaborator runs `claude /plugin marketplace add <url>` once per machine, then enables the specific plugin(s) they want per project in `.claude/settings.json`. No `just setup` equivalent in the new repo — it's docs-only for install.
- **`ui-check` invoked when plugin is disabled**: the skill itself is unavailable; invocation fails at the skill-resolution layer. No confusing intermediate state.
- **Worktree inheritance**: per-project enable in VCS-tracked `.claude/settings.json` propagates **per branch**. A worktree on a branch predating the enable commit will see the plugin disabled; a worktree on a branch that includes the commit will see it enabled. Plugin cache is host-level — if `/plugin marketplace add <url>` was run on the host, all worktrees on that host get the plugin files when enabled.
- **Upstream #40789 regression**: if Anthropic regresses the disabled-plugin-gating fix, disabled plugins leak descriptions back into the session. Feature delivers zero context savings until upstream re-fixes; no silent data corruption. Manual observation only.
- **`harness-review` invoked from a different repo**: not available — project-local to `cortex-command`. Expected: Claude responds "skill not defined." Acceptable in single-maintainer context.
- **`.claude/skills/harness-review/` and `.claude/skills/setup-merge/` coexistence**: no collision (different names); precedent already set by `setup-merge`.
- **`cortex-command-plugins` repo drifts (new plugin version, bug fix)**: user runs `/plugin marketplace update cortex-command-plugins` (or equivalent Claude Code command) to refresh. Document in the new repo's README.

## Changes to Existing Behavior

- **REMOVED — global `~/.claude/skills/` entries** for `ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup`, `pr-review`, `harness-review`. The UI skills + `pr-review` relocate to the new repo's plugin structure; `harness-review` relocates to project-local `.claude/skills/`.
- **REMOVED — `cortex-command/skills/ui-*/`, `cortex-command/skills/pr-review/`, `cortex-command/skills/harness-review/`** directories. First two move to the new repo (subtrees intact — `references/` + `scripts/` travel with their skills); last moves to `.claude/skills/` in this repo.
- **REMOVED — `cortex-command/docs/ui-tooling.md`**: the dedicated UI-tooling reference (127 lines) moves to `cortex-command-plugins/docs/ui-tooling.md`. Cross-references in `docs/agentic-layer.md` to this doc are updated to point at the new repo (or removed if an updated target doesn't exist yet).
- **MODIFIED — `docs/setup.md`, `docs/dashboard.md`**: references to extracted skill names updated to point at the new repo; UI-bundle install/removal instructions rewritten around the plugin install flow.
- **MODIFIED — `cortex-command`'s `justfile`** deploy-skills recipes no longer iterate the extracted skill names. Must stay consistent across `setup-force`, `deploy-skills`, `verify-setup`/`check-symlinks`, `validate-skills`.
- **MODIFIED — `skills/ui-check/SKILL.md`** (pre-move): hardcoded FS probes replaced with skill-availability check; this edit lands in `cortex-command` first, then the file moves to the new repo.
- **MODIFIED — `docs/skills-reference.md`, `docs/agentic-layer.md`** — extracted skill entries removed from catalog; pointer to `cortex-command-plugins` added.
- **ADDED — new repo `cortex-command-plugins`** with marketplace manifest, 2 plugins (6+1 skills), README, LICENSE, `scripts/validate-skill.py`, `.github/workflows/validate.yml`, and the ui-check FS-probe guard.
- **ADDED — `cortex-command/.claude/skills/harness-review/`** directory (project-local skill scope).

## Technical Constraints

- **Q1 verified favorable on Claude Code v2.1.109** (2026-04-15): disabled plugins do not contribute skill descriptions to the session system reminder. Feature delivers real context savings today.
- **Plugin skill namespace is `<plugin-name>:<skill-name>`** — invocation changes (e.g., `/ui-lint` → `/cortex-ui-extras:ui-lint`). No name collision with user-level skills. Historical artifact references stay bare.
- **Marketplace install from a public GitHub repo** requires a one-time-per-machine `/plugin marketplace add <url>` step. `cortex-command`'s `just setup` does not perform this — it's documented in the new repo's README only.
- **Peer-skill dispatch within a plugin uses bare names** (Anthropic plugin-dev reference). No namespaced-rewrite tax for `ui-check` dispatches.
- **`ui-check` FS-probe rewrite must land before the move** to avoid a broken interim state where ui-check references user-level paths that no longer exist.
- **Repo name**: proposed `cortex-command-plugins` (plural). User may choose a different name at repo-creation time; spec is not rigid on the name, only on the structure.
- **The new repo lives outside the `cortex-command` working tree**. Implementation phase will operate in two physical paths. Both repos' changes ship in a cohesive PR/commit effort but each to its own repo.

## Open Decisions

None. All spec-time decisions resolved during Clarify, Research, and Specify interviews.
