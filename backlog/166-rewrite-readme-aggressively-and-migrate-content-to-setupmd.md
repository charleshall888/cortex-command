---
schema_version: "1"
uuid: c95205c0-a3cf-4c9c-a60d-792c7c8b2a81
title: "Rewrite README, migrate content to docs/setup.md, reorganize docs/, and fix stale paths"
status: complete
priority: high
type: feature
tags: [repo-spring-cleaning, readme, setup, documentation, share-readiness, stale-paths]
areas: [docs]
created: 2026-05-05
updated: 2026-05-05
parent: "165"
blocks: []
blocked-by: []
discovery_source: cortex/research/repo-spring-cleaning/research.md
session_id: null
lifecycle_phase: implement
lifecycle_slug: rewrite-readme-migrate-content-to-docs-setupmd-reorganize-docs-and-fix-stale-paths
complexity: complex
criticality: high
---

# Rewrite README, migrate content to docs/setup.md, reorganize docs/, and fix stale paths

## Context from discovery

`research/repo-spring-cleaning/research.md` (DR-1 + DR-3 ratified) prescribes a coordinated docs cleanup for installer-audience share-readiness. The README rewrite supersedes #150 (which dropped Customization/Distribution/Commands moves from its scope). The `docs/` reorganization moves three pure-internal docs to a new `docs/internals/` subdir and eliminates skill-table duplication. Stale-path fixes resolve four small post-#117/#148 residuals.

This is one ticket because:
- Shared file domain: all changes live under `docs/`, `README.md`, `requirements/`, `CHANGELOG.md`.
- Atomic-landing benefit: the README's Documentation index needs the new `docs/internals/` paths in the same commit as the README rewrite, so the index never points at relocated docs that haven't moved yet.
- Same audience goal: end-user installers running `cortex init` to use cortex-command in their own projects, not forkers.

## Scope — README cuts (target ~80 lines, down from 132)

Cut from current `README.md`:
- L11–29: ASCII pipeline diagram + tier/criticality legend (concept-encyclopedia content; lives in `docs/agentic-layer.md`)
- L52–54: Plugin auto-update mechanics paragraph + extras-tier callout (move to setup.md)
- L73–75: Authentication H2 (fold into Documentation index as a row)
- L77–88: What's Inside table (per OQ §6 ratified — repo-structure tour is a forker concern; CLI-bin row is a recurring drift vector unenforced by the parity check)
- L89–91: Customization H2 (move to setup.md — #150 OE-1 target, dropped)
- L93–100: Distribution H2 (move to setup.md — #150 OE-1 target, dropped)
- L102–115: Commands H2 (move to setup.md — #150 OE-1 target, dropped)

Keep (with minor trim):
- Title + 1-paragraph pitch (~6 lines; drop distribution-mechanics blur in current paragraph 3)
- Workflow narrative prose at L9 (~5 lines, link to `docs/agentic-layer.md`)
- Prerequisites (L31–35)
- Quickstart 3-step block (L36–50)
- Plugin roster table (L58–71; trim header/footer prose, keep table)
- Verification pointer (L56)
- Documentation index (L117–128; expand by 1 row to absorb Authentication pointer; update `pipeline.md`/`sdk.md`/`mcp-contract.md` rows to the new `docs/internals/` paths)
- License (L130–132)

## Scope — `docs/setup.md` migration (HARD PREREQUISITE for README cuts)

Critical-review surfaced that DR-1's "content moved, not lost" claim was false at the time of writing: setup.md does not contain three operational notes from README L93–100. **Setup.md must gain the following BEFORE the README cut commit lands**, or the cut deletes content rather than relocating it:

- `uv run` operates-on-user-project semantics note (currently `README.md:97`)
- `uv tool uninstall uv` foot-gun warning (currently `README.md:98`)
- Forker fork-install URL pattern (currently `README.md:100`): `uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>`
- "Upgrade & maintenance" subsection covering the upgrade paths currently above-fold at `README.md:93-100`
- Customization content from current README L89–91 (settings.json ownership rule)
- Commands subsection (cortex CLI subcommand listing; backed by `cortex --help` for installers whose binary works, but reachable in setup.md for stalled-install recovery)

Verify `docs/setup.md` Troubleshooting section at L49-53 covers `cortex: command not found` AND surfaces `cortex --print-root` as the verify-install command before cutting Commands H2.

## Scope — `docs/setup.md` trim

Per F-2: collapse the 7-step `cortex init` explainer (L107-128) to a shorter form; push `lifecycle.config.md` schema (L130-160) to a reference card or compress; decide whether `CLAUDE_CONFIG_DIR` § (L352-388) stays or moves to a forker-tier section.

## Scope — `docs/internals/` move (DR-3 = Option B)

Move three pure-internal docs into a new `docs/internals/` subdirectory:
- `docs/pipeline.md` → `docs/internals/pipeline.md`
- `docs/sdk.md` → `docs/internals/sdk.md`
- `docs/mcp-contract.md` → `docs/internals/mcp-contract.md`

Leave `docs/plugin-development.md` and `docs/release-process.md` at `docs/` root (per DR-3 Option B — less deeply internal, useful for forkers and contributors who do read `docs/`).

**Cross-references requiring path updates** (round 2 enumerated full set):

- `CLAUDE.md:50` doc-ownership rule (NOT line 34 — round 2 corrected line-number drift)
- `README.md:127` Documentation index (already in scope per atomic-landing requirement)
- `docs/overnight-operations.md:318, 326, 339, 593, 599` — sibling-link references to `pipeline.md`/`sdk.md` paths
- `docs/mcp-server.md:9` — sibling-of prose mentions
- `docs/pipeline.md:13` — internal forward-link to `sdk.md` (relative, OK as-is since both move together)
- **Code references requiring update** (round 2 caught these — NOT in original scope):
  - `cortex_command/cli.py:268` runtime stderr message: `"see docs/mcp-contract.md."` — **user-facing CLI output**, must update or installers see broken-link error
  - `bin/cortex-check-parity:59` script comment referencing `docs/pipeline.md` and `docs/overnight-operations.md`
  - `plugins/cortex-core/bin/cortex-check-parity:59` mirror — auto-regenerates from canonical via `just build-plugin`

## Scope — Skill-table dedup (F-4)

`docs/skills-reference.md` is the canonical skill index (one row per skill, links to SKILL.md). `docs/agentic-layer.md` currently duplicates this. Merge: keep `skills-reference.md` as canonical; trim `agentic-layer.md` to diagrams + workflow narratives + lifecycle phase map; drop the skill-inventory tables.

**Round 2 verified**: 100% skill-set overlap between the two docs. **Migration callout** (must NOT be lost during dedup): the `pipeline-not-a-skill` callout at `docs/agentic-layer.md:64` ("internal reference, not a user-facing skill") has no equivalent in `skills-reference.md`. Migrate it as a similar note in `skills-reference.md` before trimming agentic-layer.

## Scope — "bash runner" terminology drift sweep (broader than round 1)

Round 2 found this drift is FAR more pervasive than round 1's 3-line scope. The runner is now `cortex_command/overnight/runner.py` (Python CLI invoked via `cortex overnight start`); the bash entrypoint `runner.sh` does not exist in the repo. User-facing terminology must be updated:

**Skills** (canonical sources — plugin mirrors regenerate via `just build-plugin`):
- `skills/overnight/SKILL.md:3, 22, 391, 400, 401` — 5 occurrences in description and body
- `skills/diagnose/SKILL.md:62` — debugging example

**Docs** (user-facing):
- `docs/overnight.md:8` — "launch a bash runner"
- `docs/agentic-layer.md:187` — "a bash runner detaches in a tmux session" (round 1 caught this)
- `docs/agentic-layer.md:313` — "The bash overnight runner writes execution state" (round 1 caught this)
- `docs/skills-reference.md:59, 71` — same regression as agentic-layer; round 1 missed both

**Note** (round 2 correction): `docs/agentic-layer.md:183` does NOT contain bash-runner terminology in current state. The earlier ticket scope listed it; drop from the line-number-targeted list. Replace with `grep -n 'bash runner\|bash overnight runner\|runner\.sh' docs/ skills/` exhaustive sweep at plan time.

**Out of user-facing scope (acceptable to leave)**:
- `cortex_command/overnight/*.py` 30+ docstring/comment references to `runner.sh` — these are port-provenance citations ("Mirrors `runner.sh:N`") documenting where the Python code came from. They are internal documentation; not user-facing.
- `cortex_command/overnight/prompts/orchestrator-round.md` references to "the bash runner will invoke" — runtime narration in an orchestrator prompt. **Investigate during plan** — if the prompt language confuses spawned agents, fix; if it's harmless provenance, leave.
- `plugins/cortex-core/hooks/cortex-worktree-create.sh:49` and `cortex_command/pipeline/worktree.py:176` mention `runner.sh venv check` in comments. The actual venv-symlink behavior is preserved in `runner.py`; comments are stale but non-load-bearing.

## Scope — `docs/backlog.md` trim

Cut the "Global Deployment (Cross-Repo Use)" section at `docs/backlog.md:198-234` (37 lines of plugin-development content). **Round 2 caught**: this is NOT a clean delete — `docs/plugin-development.md` does NOT cover (a) the `Path.cwd()` vs `Path(__file__).parent` rule for repo-local dirs (load-bearing for anyone adding a deployable script), (b) the per-script bin-deployment mechanism. Substantive migration of the architectural rules to `plugin-development.md` is required before the cut. The currently-deployed-scripts list (3-row table) is drift-prone and can be dropped.

## Scope — Stale-path fixes (F-5)

- `requirements/pipeline.md:130` — references `claude/reference/output-floors.md` (directory retired in #117). Round 2 confirmed no replacement exists (`find . -name 'output-floors.md'` returns 0). Cleanest: delete the parenthetical entirely; the convention is now defined inline above the parenthetical. Final wording: *"… the relevant events.log entry should include a `rationale` field explaining the reasoning. Routine forward-progress decisions do not require this field."*
- `CHANGELOG.md:21-22` — promises `docs/install.md` and `docs/migration-no-clone-install.md`, neither file exists. Replace with single bullet pointing at `docs/setup.md` (canonical).
- `scripts/validate-callgraph.py:12` (round 2 caught) — comment: `claude/reference/claude-skills.md "Common Mistakes" row 303`. Live script (KEEP per #168 inventory) but with stale comment. Update or remove the parenthetical reference.
- `skills/requirements/references/gather.md:201` (round 2 caught) — broken relative link `[requirements/project.md](project.md)`. Fix to `../../../requirements/project.md`.
- `backlog/133-...md:56` (round 2 caught) — broken cross-reference to non-existent lifecycle dir `../lifecycle/remove-progress-update-scaffolding-from-long-running-prom...` (truncated). Verify and remove or correct.

## Scope — `docs/dashboard.md` policy (OQ §4)

Confirmed during research that no `cortex dashboard` subcommand exists in `cortex_command/cli.py:284-628`. `docs/dashboard.md:14` instructs `just dashboard`, which only works inside a clone. Pick one of three options during plan phase:

1. Ship a `cortex dashboard` verb that wraps the FastAPI server invocation (smallest installer-facing fix).
2. Flag dashboard as contributor-only-launchable; update `docs/dashboard.md` and remove from any installer-facing docs index.
3. Cut `docs/dashboard.md` from the installer-facing docs index entirely; keep file but mark contributor-tier.

## Out of scope

- Code/script/hook deletion — child #168.
- Lifecycle/research archive sweep — child #169.
- `requirements/project.md:7` audience language — F-12 dropped post-critical-review (line already balanced).
- DR-2 visibility cleanup (gitignore-hide / `.cortex/` relocation) — deferred per DR-2 = C.

## Suggested lifecycle plan-phase sequencing

1. Move 3 docs to `docs/internals/`; update `CLAUDE.md:34` doc-ownership cross-refs.
2. Merge `agentic-layer.md` skill table into `skills-reference.md`; trim `agentic-layer.md`.
3. Fix stale paths (`requirements/pipeline.md:130`, `CHANGELOG.md:21-22`, `docs/agentic-layer.md:183/187/313`).
4. Trim `docs/backlog.md` "Global Deployment" §.
5. Resolve `docs/dashboard.md` policy decision.
6. Trim `docs/setup.md` (`cortex init` explainer, `lifecycle.config.md` schema).
7. Add setup.md content from soon-to-be-cut README sections (Customization, Distribution, Commands, Upgrade & maintenance).
8. Trim README pitch + cut sections (Authentication, What's Inside, Customization, Distribution, Commands, ASCII legend).
9. Final README Documentation index update with new `docs/internals/` paths and Authentication row.

## Acceptance signals

- README ≤ 90 lines.
- Every cut README section has its content present in `docs/setup.md` (or another doc) at the time of the README-cut commit. No content lost from the repo.
- README Documentation index has rows for Authentication and Upgrade & maintenance, and points at correct paths for relocated internals docs.
- `cortex --print-root` verification command reachable from `docs/setup.md` Troubleshooting.
- Plugin roster table preserved.
- `docs/{pipeline,sdk,mcp-contract}.md` relocated to `docs/internals/` with all cross-refs updated.
- `docs/agentic-layer.md` skill tables removed; `docs/skills-reference.md` is the sole skill inventory; `pipeline-not-a-skill` callout migrated to skills-reference.md.
- `requirements/pipeline.md:130` and `CHANGELOG.md:21-22` resolve to live content.
- `docs/dashboard.md` policy decision documented in implementation evidence.

**Verifiable greps** (round 2 added):
- `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' --include='*.py' --include='*.sh' .` returns no hits (catches `cortex_command/cli.py:268` and `bin/cortex-check-parity:59` stragglers).
- `grep -rn 'bash runner\|bash overnight runner' docs/ skills/` returns no hits (covers full set: agentic-layer, overnight, skills-reference, overnight.md, diagnose).
- `docs/setup.md` contains the strings `uv tool uninstall uv`, `cortex overnight start`, `cortex overnight status` (verifies migrations landed).
- `requirements/pipeline.md` does NOT contain `claude/reference/` (full scrub, not cosmetic edit).
- `CHANGELOG.md` does NOT contain `docs/install.md` or `docs/migration-no-clone-install.md` (negative-existence check).
- `docs/agentic-layer.md` Skills section line count drops by ≥40 lines (table dedup actually happened).
- `plugins/cortex-core/bin/cortex-check-parity` regenerated cleanly by `just build-plugin` after canonical source updated (pre-commit dual-source sanity).

## Research

See `research/repo-spring-cleaning/research.md` — DR-1, DR-3, F-1, F-2, F-3, F-4, F-5, README anatomy table, doc inventory tables, #150 residual analysis, README target-shape benchmarks (uv/mise/gh), OQ §4 dashboard verb policy, and OQ §6 What's Inside resolution.
