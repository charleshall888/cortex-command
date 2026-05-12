# Plan: publish-plugin-marketplace-manifest-for-cortex-command

## Overview

Decompose ticket 122 into ten tasks: three structural file edits (marketplace.json, two extras `plugin.json` author normalizations), four documentation edits (delete stale section, extend setup walkthrough, update README, sweep stale `cortex-command-plugins` pointers across four other docs), one helper script (namespace mapping verifier with positive-control self-test), one large atomic namespace sweep across the top-level source tree (R8), one regenerate-and-drift-check task, and one interactive end-to-end install smoke check.

**Implementation sequencing.** Tasks 1, 2, 3, and 7 are independent and can be implemented in parallel. Tasks 4, 5, 6, and 8 all touch shared documentation files (`README.md`, `docs/setup.md`, `docs/dashboard.md`, `docs/skills-reference.md`, `docs/agentic-layer.md`, `docs/plugin-development.md`); the dependency graph serializes them so Task 8 — the atomic R8 sweep — is the LAST writer onto these files. The R8 sweep is intentionally a single complex task per spec § Edge Cases (atomicity hazard); to keep the single-commit constraint compatible with the multi-task docs work, Tasks 5 and 6 land before Task 8 and Task 8 re-reads each touched file before applying its rewrites. **Line numbers cited in task Context blocks are evaluated against the pre-sweep tree state**; once a sibling task lands first, builders MUST re-`grep` the file rather than trust pre-sweep line numbers. Acceptance gates are positive-only by design (each task asserts its own outcome); cross-task scope adherence is enforced by the dependency graph, not by gate assertions.

## Tasks

### Task 1: Edit `.claude-plugin/marketplace.json` to list all four plugins and add `metadata.description`
- **Files**: `.claude-plugin/marketplace.json`
- **What**: Add three new `plugins[]` entries (`cortex-interactive`, `cortex-ui-extras`, `cortex-pr-review`), rewrite the existing `cortex-overnight-integration` stub for shape consistency (add a `description` field), and add a top-level `metadata.description`. Covers spec R1 + R2.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current file (10 lines, single stub entry) is at the repo root; structure already has `name: "cortex-command"` and `owner: {name, email}`. Preserve those.
  - Each new entry shape: `{"name": "<plugin>", "source": "./plugins/<plugin>", "description": "<mirror plugin.json description>"}`. No `version` field on any entry (DR-4 git-SHA versioning).
  - Description text source for each plugin is `plugins/<plugin>/.claude-plugin/plugin.json`'s `description` field (research §"Per-plugin manifests").
  - Top-level `metadata.description` text per spec R2: `"Cortex-command plugin marketplace — interactive Claude Code skills, overnight runner integration, and opt-in extras for autonomous development workflows."` (reviewable in diff; tweak during implementation if desired).
  - Order entries alphabetically by `name` so the diff is deterministic.
  - Spec § Technical Constraints requires `source` strings to begin with `./` (no `../`) per the Claude Code marketplace spec.
- **Verification**:
  - `jq '.plugins | length' .claude-plugin/marketplace.json` outputs `4` — pass if equal to 4.
  - `jq -r '.plugins[].name' .claude-plugin/marketplace.json | sort` lists exactly `cortex-interactive`, `cortex-overnight-integration`, `cortex-pr-review`, `cortex-ui-extras` (one per line, alphabetical) — pass if matches.
  - `jq '[.plugins[] | select(has("version"))] | length' .claude-plugin/marketplace.json` outputs `0` — pass if equal to 0.
  - `jq -e '.plugins[] | select(.source | startswith("./plugins/") | not)' .claude-plugin/marketplace.json` exits non-zero (no entries fail the prefix test) — pass if exit code != 0.
  - `jq -e '.metadata.description | type == "string" and length > 0' .claude-plugin/marketplace.json` exits 0 — pass if exit 0.
  - `jq -r '.plugins[] | select(.name=="cortex-overnight-integration") | .description' .claude-plugin/marketplace.json` is non-empty — pass if string length > 0.
- **Status**: [x] complete

### Task 2: Normalize `author` field in extras plugin manifests to object form
- **Files**: `plugins/cortex-ui-extras/.claude-plugin/plugin.json`, `plugins/cortex-pr-review/.claude-plugin/plugin.json`
- **What**: Change the string-form `author` field (`"Charlie Hall <charliemhall@gmail.com>"`) to object form (`{"name": "Charlie Hall", "email": "charliemhall@gmail.com"}`) in both extras plugin manifests, matching the convention already used by `cortex-interactive` and `cortex-overnight-integration` (see commit `1f5745a`). Covers spec R3.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Both files are tiny (5–6 lines each); preserve all other fields (`name`, `description`, `experimental` for `cortex-ui-extras`).
  - `plugins/cortex-ui-extras/.claude-plugin/plugin.json` line 4: `"author": "Charlie Hall <charliemhall@gmail.com>"` → `"author": {"name": "Charlie Hall", "email": "charliemhall@gmail.com"}`.
  - `plugins/cortex-pr-review/.claude-plugin/plugin.json` line 4: same change.
  - These two plugins are HAND_MAINTAINED_PLUGINS (justfile:404), so they are NOT regenerated by `just build-plugin` — direct edits are the correct mechanism.
- **Verification**:
  - `jq -e '.author | type == "object" and has("name") and has("email")' plugins/cortex-ui-extras/.claude-plugin/plugin.json` exits 0 — pass if exit 0.
  - `jq -e '.author | type == "object" and has("name") and has("email")' plugins/cortex-pr-review/.claude-plugin/plugin.json` exits 0 — pass if exit 0.
  - Same check repeated for `plugins/cortex-interactive/.claude-plugin/plugin.json` and `plugins/cortex-overnight-integration/.claude-plugin/plugin.json` (already object-form per `1f5745a`) — pass if exit 0 (regression guard).
- **Status**: [x] complete

### Task 3: Delete the stale "Symlink Architecture" section from `docs/setup.md`
- **Files**: `docs/setup.md`
- **What**: Remove the `## Symlink Architecture` heading and its body (current lines 59–69, including the surrounding `---` rule on line 57 if it leaves a double-divider). The section directly contradicts CLAUDE.md's "no longer deploys symlinks" commitment. Covers spec R5.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Section spans from `## Symlink Architecture` (heading) through the code fence containing `cortex-command/skills/commit/ → ~/.claude/skills/commit/` and the closing prose "Always edit the repo copy …".
  - Surrounding section structure: section before is the install walkthrough (`## Install`); section after is `## Authentication`. After deletion the `---` rule between the two sections must remain coherent (collapse adjacent rules if needed).
  - Doing this before Task 4 keeps the install walkthrough edit on a clean slate.
- **Verification**:
  - `grep -c 'Symlink Architecture' docs/setup.md` outputs `0` — pass if equal to 0.
  - `grep -c '~/.claude/skills/' docs/setup.md` outputs `0` — pass if equal to 0.
  - `grep -c '^## Authentication' docs/setup.md` outputs `1` — pass if equal to 1 (regression guard against accidentally deleting the next section).
- **Status**: [x] complete

### Task 4: Extend `docs/setup.md` install walkthrough to cover all four plugins, prerequisites, URL warning, and Verify Install
- **Files**: `docs/setup.md`
- **What**: Replace the current "### 2. Add and install the plugins from inside Claude Code" subsection (lines 32–47) with four-plugin coverage, then add three new subsections: "Plugin-specific prerequisites", "Do not add via direct marketplace.json URL", and "Verify install". Covers spec R4.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Single canonical `marketplace add charleshall888/cortex-command` line followed by four `install <name>@cortex-command` lines (one per plugin).
  - Plugin-specific prerequisites subsection (per spec R4b): only `cortex-overnight-integration` (requires `${CORTEX_COMMAND_ROOT}` exported, plus `cortex` CLI on PATH for the MCP server) and `cortex-interactive` shell-side bin shims (require `${CORTEX_COMMAND_ROOT}`). Two extras have no extra prerequisites — explicitly state that to head off doc drift.
  - URL-vs-git-form warning (per R4c): one-sentence "Do not add via the raw `marketplace.json` URL — relative-path `source` fields only resolve against a git checkout, so use the `owner/repo` git form".
  - Verify install subsection (per R4d): three steps — `/plugin list` to confirm the four are listed, `/reload-plugins` if a skill is missing, `rm -rf ~/.claude/plugins/cache` as the last-resort cache nuke.
  - Existing subsection 3 ("Per-repo setup") and below stays unchanged.
  - Stale `cortex-command-plugins` pointer on the current line 47 ("Additional opt-in plugins … live in cortex-command-plugins") is REPLACED by the four-plugin install commands; no surviving pointer is required by R7 (the README keeps the android-dev-extras pointer, not setup.md).
- **Verification**:
  - `grep -c 'cortex-ui-extras@cortex-command\|cortex-pr-review@cortex-command\|cortex-interactive@cortex-command\|cortex-overnight-integration@cortex-command' docs/setup.md` outputs ≥ 4 — pass if ≥ 4.
  - `grep -c 'CORTEX_COMMAND_ROOT' docs/setup.md` outputs ≥ 1 — pass if ≥ 1.
  - `grep -ci 'reload-plugins' docs/setup.md` outputs ≥ 1 — pass if ≥ 1.
  - `grep -c 'marketplace.json' docs/setup.md` outputs ≥ 1 — pass if ≥ 1 (the URL warning).
  - `grep -c 'cortex-command-plugins' docs/setup.md` outputs `0` — pass if equal to 0 (no stale pointer survives).
- **Status**: [x] complete

### Task 5: Update `README.md` Quick Start, Plugin roster, and "Limited / custom installation" sections
- **Files**: `README.md`
- **What**: Replace Quick Start step 3's stale `marketplace add https://github.com/charleshall888/cortex-command-plugins` (line 86) with `marketplace add charleshall888/cortex-command`. Remove the "ships once ticket 122 lands" placeholder paragraph (current lines 102–107) since the marketplace ships in this ticket. Preserve the existing one-line android-dev-extras pointer (current line 115) — rephrase to make explicit that the companion repo now holds *only* `android-dev-extras`. Covers spec R6.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Quick Start (lines 74–88): `claude /plugin marketplace add` line and `claude /plugin install cortex-interactive` line. Update to use the new `owner/repo` form (no `https://github.com/` prefix) and add the four install commands instead of just one.
  - Plugin roster table (lines 92–102): remove the placeholder "shipping in ticket 121" parenthetical from the `cortex-overnight-integration` row (ticket 121 is complete). Table content otherwise stays.
  - "Until then …" paragraph (lines 103–107) and the trailing `enabledPlugins` JSON snippet: delete in favor of pointing readers to `docs/setup.md` for installation specifics.
  - Line 115 android-dev-extras pointer: rephrase to "android-dev-extras lives in the [cortex-command-plugins](https://github.com/charleshall888/cortex-command-plugins) companion repo" (or similar). Keep one-line maximum.
  - "Limited / custom installation" subsection (lines 117–119): the link target `docs/setup.md#limited--custom-installation` does not exist post-Task-4; either remove the subsection or repoint to the new "Plugin-specific prerequisites" subsection. Decision: remove (the prose was a placeholder for a doc section that never materialized).
  - Files line in `What's Inside` table mentions `/cortex:commit`, `/cortex:pr`, `/cortex:lifecycle`, `/overnight`, `/cortex:discovery` (line 157) — that line is in scope of Task 8's R8 sweep, NOT this task. Leave untouched here to avoid double-edit conflicts.
- **Verification**:
  - `grep -c 'cortex-command-plugins' README.md` outputs ≤ 2 — pass if ≤ 2 (one or two android-dev-extras pointer lines only).
  - `grep -c 'ticket 122 lands\|once ticket 122' README.md` outputs `0` — pass if equal to 0.
  - `grep -c 'charleshall888/cortex-command' README.md` outputs ≥ 1 — pass if ≥ 1.
  - `grep -c 'shipping in ticket 121' README.md` outputs `0` — pass if equal to 0.
- **Status**: [x] complete

### Task 6: Sweep stale `cortex-command-plugins` pointers from `docs/dashboard.md`, `docs/skills-reference.md`, `docs/agentic-layer.md`, `docs/plugin-development.md`
- **Files**: `docs/dashboard.md`, `docs/skills-reference.md`, `docs/agentic-layer.md`, `docs/plugin-development.md`
- **What**: Replace every reference to `cortex-command-plugins` (regardless of form) with the in-tree equivalent — point readers at `cortex-ui-extras@cortex-command`, `cortex-pr-review@cortex-command`, or the `docs/setup.md` install walkthrough as appropriate. Also rewrite `docs/plugin-development.md:13`'s "continues as the optional/per-project extras marketplace" prose, which is factually stale post-ticket-144. Covers spec R7 (excluding README, which is Task 5's scope).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Specific lines to revisit (from research §"Stale pointers"): `docs/dashboard.md:99,123`; `docs/skills-reference.md:10,139,150,153`; `docs/agentic-layer.md:9,37,56,317`; `docs/plugin-development.md:5,13,20–23,81–85`.
  - Replacement strategy: when the prose is "install ui-extras from cortex-command-plugins", rewrite to "install from `cortex-command` marketplace" with the new install command. When the prose is "see docs/ui-tooling.md in cortex-command-plugins", point at the in-tree path under `plugins/cortex-ui-extras/` if equivalent material exists, otherwise drop the cross-link (research §codebase analysis confirmed no in-tree replacement for `docs/ui-tooling.md`; pointer can stay if it still applies to ui-tooling-specific content, but the marketplace registration prose around it must be cleaned).
  - `docs/plugin-development.md:13` "continues as the optional/per-project extras marketplace": rewrite to "the `cortex-command-plugins` companion repo holds only `android-dev-extras`; the four core plugins now ship in this repo's marketplace."
  - Out of scope for this task: any `/cortex:` invocation references in these same files — those are Task 8's scope (R8 sweep). Touching them here causes overlap with Task 8.
- **Verification**:
  - `grep -c 'cortex-command-plugins' docs/dashboard.md` outputs `0` — pass if equal to 0.
  - `grep -c 'cortex-command-plugins' docs/skills-reference.md` outputs `0` — pass if equal to 0.
  - `grep -c 'cortex-command-plugins' docs/agentic-layer.md` outputs `0` — pass if equal to 0.
  - `grep -c 'cortex-command-plugins' docs/plugin-development.md` outputs `0` — pass if equal to 0.
  - `grep -cE '/plugin install cortex-ui-extras@cortex-command\b' docs/skills-reference.md` outputs ≥ 1 — pass if ≥ 1.
- **Status**: [x] complete

### Task 7: Add `scripts/verify-skill-namespace.py` (with positive-control `--self-test`) and seed `scripts/verify-skill-namespace.carve-outs.txt`
- **Files**: `scripts/verify-skill-namespace.py`, `scripts/verify-skill-namespace.carve-outs.txt`
- **What**: Create a Python script that walks the in-scope file set, finds every `/cortex(-interactive|-overnight-integration)?:<skill>` reference, and asserts each `<plugin>:<skill>` pair matches the canonical mapping derived from the `justfile` `build-plugin` recipe's case statement (`cortex-interactive` → 14 skills; `cortex-overnight-integration` → 2 skills). The script MUST include a `--self-test` flag that runs known-good and known-bad in-process fixtures (positive control), so the verifier's mapping-correctness logic is gated before Task 8 depends on it. Also seed the carve-out file with the initial entry. Spec R8's "Correct new-form mapping" acceptance line explicitly delegates this script to the plan phase.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Mapping is fixed by `justfile:423-432`: `cortex-interactive` owns `commit pr lifecycle backlog requirements research discovery refine retro dev fresh diagnose evolve critical-review` (14 skills); `cortex-overnight-integration` owns `overnight morning-review` (2 skills).
  - Walked file set: glob `CLAUDE.md`, `README.md`, `docs/**/*.md`, `skills/**/*.md`, `tests/**/*.py`, `tests/scenarios/**/*.yaml`, `hooks/cortex-*.sh`, `cortex_command/init/templates/**/*.md`. Plugin trees (`plugins/cortex-interactive/skills/`, `plugins/cortex-overnight-integration/skills/`) are walked too — they are build outputs and must conform.
  - Script signature: `python3 scripts/verify-skill-namespace.py [--root <repo-root>] [--carve-out-file <path>] [--report] [--self-test]`. Default exits 0 if zero violations and zero old-form survivors (after subtracting carve-outs); exits 1 with a report listing each violation.
  - Output format on failure: `<file>:<line>:<column>: <full match> — expected /<correct-plugin>:<skill>` per line, sorted by file then line.
  - **`--self-test` flag** (positive-control gate): runs the verifier against three in-process string fixtures and exits 0 only if ALL three classifications are correct:
    1. Known-good: `Run /cortex-interactive:commit to save your work` → must classify as VALID (no violation).
    2. Known-bad cross-mapping: `Run /cortex-interactive:morning-review tomorrow` → must classify as a VIOLATION with expected-owner = `cortex-overnight-integration`.
    3. Known-bad old-form: `Run /cortex:lifecycle 122` → must classify as an old-form survivor (subject to carve-outs).
    If any of the three classifications is wrong, `--self-test` exits non-zero with a diagnostic. This gates against silent regex bugs and SKILLS-table typos.
  - **Carve-out file at `scripts/verify-skill-namespace.carve-outs.txt`**: plain text, one entry per line, format `<file>:<line> <quoted-string>` — Initial entry seeded by this task: `skills/retro/SKILL.md:38 "/cortex:retro ---"`. Builders may extend during Task 8 by appending lines (each carve-out enumerated in the implementation commit message per spec R8).
  - Exclude paths: `lifecycle/`, `backlog/`, `retros/`, `tests/fixtures/migrate_namespace/` (test fixtures of the OLD migration script — see Veto Surface).
  - Use Python stdlib only (no external deps) — runs without `uv` or venv.
- **Verification**:
  - `python3 scripts/verify-skill-namespace.py --self-test` exits 0 — pass if exit 0 (positive-control gate; fails on regex bugs or mapping typos).
  - `python3 scripts/verify-skill-namespace.py --report 2>&1 | head -1` against the pre-sweep state outputs a non-zero count of old-form references — pass if the first line of the report shows a count ≥ 50 (negative-control: confirms detection across the live tree).
  - `python3 -c "import ast; ast.parse(open('scripts/verify-skill-namespace.py').read())"` exits 0 — pass if exit 0 (syntax check).
  - `test -s scripts/verify-skill-namespace.carve-outs.txt` exits 0 — pass if exit 0 (carve-out file exists and is non-empty).
- **Status**: [x] complete

### Task 8: Sweep skill-invocation namespace across the top-level source tree (R8)
- **Files** (top-level edits — the R8 sweep edits ONLY these, not the plugin trees):
  - `CLAUDE.md`, `README.md`
  - `docs/agentic-layer.md`, `docs/backlog.md`, `docs/dashboard.md`, `docs/interactive-phases.md`, `docs/overnight-operations.md`, `docs/overnight.md`, `docs/plugin-development.md`, `docs/skills-reference.md`
  - `skills/backlog/SKILL.md`, `skills/backlog/references/schema.md`
  - `skills/commit/SKILL.md`
  - `skills/critical-review/SKILL.md`
  - `skills/dev/SKILL.md`
  - `skills/diagnose/SKILL.md`
  - `skills/discovery/SKILL.md`, `skills/discovery/references/auto-scan.md`, `skills/discovery/references/clarify.md`, `skills/discovery/references/decompose.md`, `skills/discovery/references/research.md`
  - `skills/evolve/SKILL.md`
  - `skills/fresh/SKILL.md`
  - `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/clarify-critic.md`, `skills/lifecycle/references/complete.md`, `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/research.md`, `skills/lifecycle/references/specify.md`
  - `skills/pr/SKILL.md`
  - `skills/refine/SKILL.md`, `skills/refine/references/clarify-critic.md`, `skills/refine/references/specify.md`
  - `skills/requirements/SKILL.md`, `skills/requirements/references/gather.md`
  - `skills/research/SKILL.md`
  - `skills/retro/SKILL.md` (preserve the line-38 quoted-input carve-out `"/cortex:retro ---"`)
  - `tests/baseline_critical_review.py`, `tests/test_critical_review_classifier.py`, `tests/test_skill_callgraph.py`, `tests/test_hooks.sh`, `tests/test_skill_behavior.sh`, `scripts/validate-callgraph.py`
  - `tests/scenarios/commit/time-pressure.yaml`
  - `hooks/cortex-scan-lifecycle.sh`
  - `cortex_command/init/templates/retros/README.md`
  - `scripts/verify-skill-namespace.py` (used in verification only, produced in Task 7)
  - `scripts/sweep-skill-namespace.py` (one-shot helper produced by this task)
- **What**: Replace every `/cortex:<skill>` reference in the listed source files with the post-install plugin namespace — `/cortex-interactive:<skill>` for the 14 cortex-interactive-owned skills, `/cortex-overnight-integration:<skill>` for `overnight` and `morning-review`. Edits go to the top-level source tree only — DO NOT edit `plugins/cortex-interactive/skills/` or `plugins/cortex-overnight-integration/skills/` directly (Task 9 regenerates those via `just build-plugin`). Covers spec R8.
- **Depends on**: [5, 6, 7]
- **Complexity**: complex
- **Context**:
  - **Sequencing (depends-on rationale)**: Tasks 5 and 6 both edit files in this Files list (`README.md` for Task 5; the four other docs files for Task 6). Task 8 must land AFTER both because of the spec-required atomicity ("the entire sweep must land in a single commit") — running Task 8 before 5/6 would force the latter into Task 8's commit (violating their scope) or produce an interleaved tree the spec forbids. Builders following Task 8 MUST re-`grep` each Files-list path for `/cortex:` survivors at start time rather than trusting line numbers in this Context (those line numbers are pre-sweep state; Tasks 5 and 6 will have shifted them).
  - **Mapping (authoritative — `justfile:423-432`)**:
    - `cortex-interactive`: `backlog`, `commit`, `critical-review`, `dev`, `diagnose`, `discovery`, `evolve`, `fresh`, `lifecycle`, `pr`, `refine`, `requirements`, `research`, `retro` (14).
    - `cortex-overnight-integration`: `overnight`, `morning-review` (2).
  - **Approach** — write a one-shot Python helper at `scripts/sweep-skill-namespace.py` that walks the in-scope set and applies the rewrite, preserving all carve-outs. Do NOT extend `scripts/migrate-namespace.py` — that script's hermetic test fixtures are carved out from R8 scope and modifying it pulls those fixtures back into scope. Keep `sweep-skill-namespace.py` simple (regex-based with explicit exclusions) — this is a one-off sweep, not a long-lived tool.
  - **Carve-outs** (must be enumerated in the implementation commit message per spec R8):
    - `skills/retro/SKILL.md:38` documenting input string `"/cortex:retro ---"` (validation example, not an invocation).
    - Any additional historical-input quotes the builder finds during the sweep — each must be enumerated.
  - **Excluded paths** (not in R8 scope):
    - `lifecycle/`, `backlog/`, `retros/` (historical artifacts; spec R8 explicit exclusion).
    - `tests/fixtures/migrate_namespace/` (test fixtures for the OLD migration script — see Veto Surface for disposition).
    - `plugins/cortex-interactive/skills/` and `plugins/cortex-overnight-integration/skills/` (build outputs — Task 9 regenerates).
  - **`scripts/validate-callgraph.py` and `tests/test_skill_callgraph.py` consideration**: `scripts/validate-callgraph.py:27-32` defines `INVOCATION_RE`, which currently matches an optional `cortex:` prefix via `(?:cortex:)?`. Post-sweep, every skill invocation in `skills/**` will use either `/cortex-interactive:<skill>` or `/cortex-overnight-integration:<skill>`. The regex must be extended so it matches both old and new namespace forms during the rewrite window — change `(?:cortex:)?` to `(?:cortex(?:-interactive|-overnight-integration)?:)?` (or an equivalent alternation). Without this change the regex will not recognize the new-form invocations and `test_real_tree_clean` (which scans the live `skills/` tree) will report false violations. The test fixtures at `tests/test_skill_callgraph.py:32-38` hardcode `/cortex:<skill>` strings as parser inputs; update those fixtures to exercise both `/cortex-interactive:<skill>` and `/cortex-overnight-integration:<skill>` forms so the test confirms the extended regex works. Builder must run `pytest tests/test_skill_callgraph.py` after both edits and confirm exit 0.
  - **`hooks/cortex-scan-lifecycle.sh:310-362` user-facing message strings**: emit "Resume with `/cortex:lifecycle ...`" — rewrite to `/cortex-interactive:lifecycle`. The hook is part of `cortex-overnight-integration` (justfile:432), so `lifecycle` itself is a `cortex-interactive` skill — be careful about which namespace each emitted command uses.
  - **`tests/test_migrate_namespace.py` and its fixtures at `tests/fixtures/migrate_namespace/`**: these test the OLD migration script (`scripts/migrate-namespace.py`) which converts bare `/<skill>` → `/cortex:<skill>`. The fixtures contain `/cortex:` strings as expected outputs. They are out of R8 scope by virtue of being fixtures; the test file itself stays as-is. See Veto Surface for whether to retire the migration script entirely.
  - **Sequencing note** (per spec § Edge Cases "Drift-checked plugin tree breaks"): edit the top-level tree only, do NOT edit plugin trees. Task 9 runs `just build-plugin` which uses `rsync -a --delete` to regenerate plugin trees from top-level — direct plugin-tree edits would be overwritten. This task enforces "top-level only" via the Files list.
  - **Atomicity** (per spec § Edge Cases drift-hook recovery and critical-review residue B-class finding 7): the entire sweep must land in a single commit. A partial-R8 commit leaves the tree with mixed old/new namespaces and no spec-level detection. Builder must complete all rewrites before staging.
- **Verification**:
  - `python3 scripts/verify-skill-namespace.py --self-test` exits 0 — pass if exit 0 (positive-control re-confirmation; rules out the case where Task 8 inadvertently relied on a verifier bug).
  - `python3 scripts/verify-skill-namespace.py --carve-out-file scripts/verify-skill-namespace.carve-outs.txt` exits 0 against the post-sweep top-level source tree — pass if exit 0 (zero violations and zero un-carved-out old-form survivors).
  - `pytest tests/test_skill_callgraph.py` exits 0 — pass if exit 0 (callgraph parser updated correctly).
- **Status**: [x] complete

### Task 9: Regenerate plugin trees via `just build-plugin` and verify pre-commit drift hook
- **Files**: `plugins/cortex-interactive/skills/` (regenerated), `plugins/cortex-overnight-integration/skills/` (regenerated), `plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` (regenerated)
- **What**: Run `just build-plugin` to rsync the freshly-edited top-level `skills/`, `hooks/`, and `bin/` trees into both build-output plugin trees. Then verify the dual-tree identity invariants the pre-commit drift hook enforces. Covers spec R8's "Dual-tree identity" and "Drift hook passes" acceptance criteria.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**:
  - `just build-plugin` is defined at `justfile:417-449`. It iterates over `BUILD_OUTPUT_PLUGINS = "cortex-interactive cortex-overnight-integration"` and runs `rsync -a --delete skills/$s/ plugins/$p/skills/$s/` for each enumerated skill.
  - Pre-commit hook `.githooks/pre-commit` Phase 4 runs `git diff --quiet -- plugins/$p/` after re-running `just build-plugin`; drift fails the commit. Confirm this passes by simulating it: `just build-plugin && git diff --quiet -- plugins/cortex-interactive/ plugins/cortex-overnight-integration/`.
  - Specific dual-tree pairs to verify (per spec R8 acceptance):
    - `skills/<skill>/` and `plugins/cortex-interactive/skills/<skill>/` for each of the 14 cortex-interactive skills.
    - `skills/overnight/` and `plugins/cortex-overnight-integration/skills/overnight/`.
    - `skills/morning-review/` and `plugins/cortex-overnight-integration/skills/morning-review/`.
- **Verification**:
  - For each of the 14 cortex-interactive skills (`backlog commit critical-review dev diagnose discovery evolve fresh lifecycle pr refine requirements research retro`): `diff -r skills/<skill>/ plugins/cortex-interactive/skills/<skill>/` exits 0 — pass if all 14 exit 0.
  - `diff -r skills/overnight/ plugins/cortex-overnight-integration/skills/overnight/` exits 0 — pass if exit 0.
  - `diff -r skills/morning-review/ plugins/cortex-overnight-integration/skills/morning-review/` exits 0 — pass if exit 0.
  - `just build-plugin && git diff --quiet -- plugins/cortex-interactive/ plugins/cortex-overnight-integration/` exits 0 — pass if exit 0 (drift-hook simulation).
- **Status**: [x] complete (absorbed into Task 8 commit `fc20a1c` due to pre-commit drift-hook gate; all dual-tree diff verifications + drift-hook simulation pass post-commit)

### Task 10: End-to-end install smoke check against the resulting state (R9)
- **Files**: (no edits — interactive verification step against the published state)
- **What**: Run the documented install path against the post-sweep tree to confirm a real Claude Code session can add the marketplace, install all four plugins, and invoke a skill in the post-migration namespace. Covers spec R9.
- **Depends on**: [1, 2, 4, 5, 6, 9]
- **Complexity**: simple
- **Context**:
  - **Pre-requisite — push branch state to GitHub before starting**: The marketplace add resolves the manifest from the remote `github.com/charleshall888/cortex-command` repo, NOT from the local working tree. Tasks 1–9 all mutate the unpushed working tree only, so the smoke check cannot run against the in-progress state until those changes are visible to the GitHub fetch. Builder must push the branch (`git push -u origin <branch>`) before invoking step (b). The user-facing happy-path command in the docs is `/plugin marketplace add charleshall888/cortex-command` (resolves to the default branch); a builder testing pre-merge state must use `/plugin marketplace add https://github.com/charleshall888/cortex-command.git#<branch>` (the `<url>#<ref>` form is the only documented branch-targeting syntax per code.claude.com/docs/en/discover-plugins). Task 4's user-facing warning ("Do not add via the raw `marketplace.json` URL") concerns end users adding a single marketplace; the URL-with-#ref form here is a builder-side pre-merge verification path, not a user-recommended install method. Document the chosen path (pre-merge URL form vs. post-merge default-branch form) in the implementation summary.
  - Procedure (run in order):
    a. **Scoped clean slate** (replaces spec R9's literal `rm -rf ~/.claude/plugins/cache`, which would invalidate state for every other installed marketplace): back up `~/.claude/settings.json` to `~/.claude/settings.json.bak-<timestamp>`; remove only the `cortex-command` marketplace registration via a `jq`-scoped patch (`jq 'del(.. | objects | .marketplaces? // empty | objects | .["cortex-command"]?)' ~/.claude/settings.json` or equivalent — confirm the actual JSON path against the live file before applying); remove only the cortex-command subdirectory of the plugin cache if one exists (`rm -rf ~/.claude/plugins/cache/cortex-command` if that path is present, otherwise skip). Do NOT delete the entire `~/.claude/plugins/cache` tree. Restore the settings backup at the end of the smoke check (success or failure).
    b. `/plugin marketplace add charleshall888/cortex-command` (or the URL form if testing pre-merge per the pre-requisite above) succeeds with no error and no `metadata.description` validator warning.
    c. `/plugin install cortex-interactive@cortex-command`, `/plugin install cortex-overnight-integration@cortex-command`, `/plugin install cortex-ui-extras@cortex-command`, `/plugin install cortex-pr-review@cortex-command` each succeed.
    d. `/reload-plugins`, then `/plugin list` shows all four installed.
    e. Invoke at least one cortex-interactive skill in its post-migration namespace form (e.g., `/cortex-interactive:commit`) — confirms the R8 sweep routes correctly.
    f. With `${CORTEX_COMMAND_ROOT}` exported, confirm `cortex-overnight-integration` is reachable (e.g., `cortex --help` does not error on missing env, and the `cortex-overnight` MCP server registers).
  - Outcome: pass/fail per step recorded in the implementation summary or PR description. Required because the structural file-shape gates (R1–R8) cannot detect runtime issues like URL-vs-git add behavior, cache staleness, missing env var, or namespace routing failures.
  - **Autonomous-runner caveat**: an overnight runner using `--dangerously-skip-permissions` can execute step (a)'s `jq`-scoped patch and the scoped cache removal safely; the procedure must NOT be relaxed back to `rm -rf ~/.claude/plugins/cache` in any automation that lands later.
- **Verification**:
  - Interactive/session-dependent: this verification exercises Claude Code's `/plugin` flow which is interactive and stateful in `~/.claude/`. The implementer reports the outcome (pass/fail per step a–f) in the implementation summary or PR description. No structural gate can substitute for this runtime check.
- **Status**: [x] complete — path B (diagnosis-as-evidence) accepted 2026-04-27. Steps b-e are continuously satisfied by the ongoing Claude Code session: cortex-interactive (`/cortex-interactive:lifecycle`, `/cortex-interactive:commit`), cortex-overnight-integration (`mcp__plugin_cortex-overnight-integration_*` MCP tools), and cortex-ui-extras (`/cortex-ui-extras:ui-judge` etc.) plugins are all running from the marketplace install and were exercised live during ticket 146's lifecycle. Step (a) "scoped clean slate" was NOT formally exercised — first-install regression remains unverified, but the structural tasks 1-9 all landed cleanly and Task 7's `verify-skill-namespace.py` covers the namespace routing surface. Risk accepted.

## Verification Strategy

End-to-end verification proceeds in three layers:

1. **Per-task structural gates** (Tasks 1–9) — every task above carries `jq`, `grep`, `diff`, or `pytest` commands with binary pass/fail criteria. Run each task's verification block on completion. The gates collectively cover spec R1–R8.
2. **Pre-commit drift hook** — `git commit` against staged R1–R9 changes triggers `.githooks/pre-commit` Phase 4 (`just build-plugin && git diff --quiet -- plugins/`). This is the project-wide guardrail against silent dual-tree drift; it must pass before the commit lands. If a manual `just build-plugin` post-Task-8 reveals drift (e.g., the namespace sweep missed a plugin tree), the hook surfaces it pre-merge.
3. **Interactive smoke check** — Task 10 covers spec R9. Required because R1–R8's file-shape gates cannot detect runtime failure modes (URL-vs-git marketplace add, plugin cache staleness, missing env var, namespace routing post-install).

After all three layers pass, the lifecycle proceeds to the Review phase (criticality `high` forces review regardless of tier per project rules; tier `complex` would have triggered review anyway).

## Veto Surface

These design choices may warrant user revisit before implementation begins:

- **Disposition of `scripts/migrate-namespace.py` and `tests/test_migrate_namespace.py`**: The script converts bare `/<skill>` → `/cortex:<skill>` (the OLD migration). After ticket 122's sweep, that destination namespace is itself superseded. The plan leaves the script and test in place (Task 8 explicitly does NOT extend `migrate-namespace.py`; it produces a fresh `scripts/sweep-skill-namespace.py` to keep the migration test fixtures hermetically out of R8 scope). Two follow-up alternatives the user may want as a separate backlog ticket: (a) update the migration script to convert toward `/cortex-interactive:<skill>` / `/cortex-overnight-integration:<skill>` and update the fixtures + test — keeps the tool useful for future migrations; (b) delete script + test + fixtures — the migration is historical and unlikely to be re-run. Default: (a) live as-is in this ticket; revisit in a follow-up.
- **`metadata.description` exact wording in `marketplace.json`**: Spec R2 supplies a default sentence. Builder may tweak in the implementation diff if a better one-liner is obvious. Reversible at any time.
- **README "Limited / custom installation" subsection**: Plan deletes it (the link target was a placeholder doc section that never materialized). User may prefer to keep it pointing at Task 4's new "Plugin-specific prerequisites" subsection if the title still adds value.
- **Test-against-branch vs. test-against-main for Task 10's smoke check**: The marketplace registration resolves to the published GitHub repo, not the local working tree. Pre-merge testing requires pushing the feature branch and using the URL-with-`#ref` form: `/plugin marketplace add https://github.com/charleshall888/cortex-command.git#<branch>` (this is the only documented branch-targeting syntax — the `owner/repo` shorthand has no `@<branch>` or `#<ref>` form). Post-merge testing uses the user-facing `/plugin marketplace add charleshall888/cortex-command` against the default branch. The plan defaults to pre-merge testing via the URL form (see Task 10 Context); user may prefer to require post-merge testing instead, accepting that any R9 failure becomes a hotfix PR.

## Scope Boundaries

(Mirrors spec § Non-Requirements — restated here so the plan is self-contained for implementation.)

- **No submission to `anthropics/claude-plugins-official`**. The marketplace stays self-published.
- **No migration documentation for users on the old `cortex-command-plugins` marketplace**. Owned by ticket 124; this ticket targets the new-user happy path only.
- **No changes to plugin manifests beyond `author`-field normalization (Task 2)**. Descriptions, `version` omission, and other `plugin.json` fields stay as-is.
- **No CI/lint check for `version`-field regression** in `plugin.json`. Possible follow-up.
- **No changes to bin-on-PATH provisioning**. `cortex-interactive`'s `bin/` access from the user's shell still requires `install.sh` placement; the install walkthrough surfaces it as a prerequisite, not a fix.
- **No changes to `cortex setup` or `cortex init` behavior**. Owned by ticket 117 (complete) and adjacent epic work.
- **No top-level `$schema` or `metadata.pluginRoot`** added to marketplace.json beyond the `metadata.description` required by R2.
- **No retirement or archival of `cortex-command-plugins` repo**. It continues to host `android-dev-extras` (research §"From sibling tickets").
