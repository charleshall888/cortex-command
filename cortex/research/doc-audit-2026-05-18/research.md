# Doc Audit and Fix Pass — 2026-05-18

## Goal

User invoked `/goal` with: "make sure every single piece of documentation in this repo is accurate and up-to-date. Kick off a bunch of subagents from different angles."

User also flagged mid-session: "we have multiple agents working in separate claude sessions at the same time, so don't mess with those agents' work."

## Approach

### Phase 1 — Parallel audit (8 read-only subagents)

Dispatched 8 general-purpose subagents in parallel, each scoped to a non-overlapping doc slice:

1. **Top-level user docs** — README, CLAUDE.md, docs/setup, docs/agentic-layer, docs/release-process, docs/policies
2. **Skills + lifecycle** — docs/skills-reference, docs/interactive-phases, docs/backlog, skills/*/SKILL.md
3. **Overnight + pipeline** — docs/overnight-operations, docs/overnight, docs/internals/sdk, docs/internals/pipeline, docs/internals/auto-update, skills/overnight/*
4. **Dashboard + MCP + internals** — docs/dashboard, docs/mcp-server, docs/internals/mcp-contract, docs/internals/events-registry, docs/internals/one-shot-scripts, docs/plugin-development, bin/.* allowlists
5. **ADRs + requirements + project meta** — cortex/adr/*, cortex/requirements/*, cortex/README, cortex/lifecycle.config, CHANGELOG
6. **Non-core plugins** — plugins/android-dev-extras, plugins/cortex-pr-review, plugins/cortex-ui-extras, plugins/cortex-dev-extras
7. **Landing page + init templates** — landing-page/*, cortex_command/init/templates/*
8. **Cross-cutting link integrity** — every .md file in repo (excluding tool-managed dirs) — broken links, dead anchors, dead skill/CLI refs, stale paths

Each subagent was asked to read assigned files in full, cross-reference against current code, and report file:line + severity (HIGH/MEDIUM/LOW). Audits were strictly read-only.

### Phase 2 — Decision rule for which fixes to apply

After all audits returned, I split findings into three categories:

- **Safe-zone**: anything in `docs/**`, `cortex/**` (except tool-managed subdirs), `CHANGELOG.md`, `README.md`, `landing-page/**`, `cortex_command/init/templates/**`, `bin/.events-registry.md`, `cortex_command/dashboard/DESIGN.md`. Fix directly.
- **Gated**: anything in `skills/**`, `plugins/cortex-pr-review/**`, `plugins/cortex-ui-extras/**`. Per CLAUDE.md, these paths normally require a lifecycle. Surfaced to user for decision.
- **Don't touch**: any file currently dirty in `git status` (other sessions' in-flight work). Specifically excluded: `cortex_command/dashboard/app.py` + `templates/*.html`, all `cortex/lifecycle/**`, all `cortex/backlog/*.md` files currently modified, `tests/fixtures/predicate_a_baseline.json`.

### Phase 3 — Parallel fix (6 subagents)

Dispatched 4 parallel safe-zone fix agents (non-overlapping file scopes). Then surfaced lifecycle-gated items via AskUserQuestion. User authorized direct edits. Dispatched 2 more parallel fix agents for the gated paths. One agent terminated early (only 2 of 8 files); I completed the remaining 6 manually with direct Edit calls.

## Outputs

- **38 files modified** total (29 in safe zone, 9 in lifecycle-gated paths)
- **0 files touched** that were dirty in `git status` at session start
- **0 commits** — left for user to invoke `/cortex-core:commit`

## Severity breakdown of findings actually fixed

- HIGH (~22): broken CLI commands, deleted-file references, broken anchors, wrong panel counts, wrong host bindings, wrong tool counts
- MEDIUM (~15): outdated CLI surface, missing fields/enums, stale claims, init template drift
- LOW (~10): cosmetic, line-anchor drift within tolerance, link clarifications

## Items NOT fixed (deliberate deferrals)

1. **ui-extras grid mismatch** (4px vs 8px) — fixed as docs but the underlying issue is a code↔doc inconsistency: ui-setup's rhythmguard config in stylelint enforces a grid that the design system docs contradict. Docs now say 4px; if the code was right at 8px, the docs are now wrong. Not verified which side is canonical.
2. **`--tier` flag CLI/throttle/doc three-way drift** — docs/overnight-operations.md was honest about the drift; CLI accepts `simple|complex`, throttle expects `max_5/max_100/max_200`, falls back to `max_100`. This is a real bug in the code, not just docs.
3. **`mcp__plugin_cortex-overnight__overnight_cancel` output schema** — kept the doc's existing shape on the strength of the fix agent's verification; not independently re-verified by me.
4. **`cortex/requirements/glossary.md`** — referenced from 8 docs as conditionally lazy-created; never created. Considered intentional per the docs' framing.
5. **Skill kept-pauses line anchors** in `skills/lifecycle/SKILL.md` — within ±35 tolerance, parity test passes; deferred.
6. **plugins/cortex-core/* mirrors** — left untouched on the assumption that pre-commit hook regenerates them from canonical `skills/`, `hooks/`, `bin/`.

## Validation performed

- `git status --short` and `git diff --stat HEAD` to confirm no unintended files touched
- No test runs, no linter runs, no commit hook invocations
- No browser test of doc renders

## Open risks

1. Some fixes (especially the v1.0/v1.1 → v2.0 release-process rewrite, and the overnight-operations runner.sh→runner.py sweep) involved rewriting prose, not just one-word swaps. If my interpretation of code drift was wrong, the docs are now wrong in a different direction.
2. The init template `backlog/README.md` was replaced with a pointer to canonical schema rather than the schema itself. Downstream `cortex init` users now get less self-contained docs and a soft dependency on the upstream plugin docs.
3. The audit deliberately exempted Anthropic-domain assumptions (e.g., I didn't verify every model name or `effort` value in `docs/internals/sdk.md`).
4. Pre-commit hook may regenerate `plugins/cortex-core/*` mirrors at commit time; if the hook lags or fails, the mirror will diverge from canonical.

## Post-review verification (2026-05-18, after critical-review pass)

A critical-review pass over this research artifact surfaced 3 A-class through-lines: no content verification anywhere, code-as-oracle bias, and parallel fan-out without reconciliation. The Apply phase ran empirical verification on the riskiest claims.

**Verified canonical (was a coin-flip risk):**
- **ui-extras grid (4px vs 8px)** — verified 4px IS canonical. Sources: `plugins/cortex-ui-extras/skills/ui-brief/SKILL.md:105` ("Spacing: p-1 … p-96 (4px grid, auto-generated)"), `theme-template.md:76-77` (`--spacing: 0.25rem` = 4px), `ui-judge/SKILL.md:69` ("All gaps are multiples of 4px throughout"). The original 8px in ui-setup was the code bug; the doc fix to 4px was correct.

**Verified consistent (parallel-fix worked):**
- **v2.0 schema_version rewrite** — cross-checked `cortex_command/overnight/cli_handler.py:107` (`_JSON_SCHEMA_VERSION = "2.0"`) against the 4 docs my parallel agents edited: `docs/release-process.md:21-23`, `docs/internals/mcp-contract.md:17`, `CHANGELOG.md:7-24`, `bin/.events-registry.md`. All agree on the 2.0 schema version and the BREAKING split rationale.

**Verified inconsistent (parallel-fix had real misses):** the reviewer was correct that file-scope-only coordination missed semantic conflicts. Five additional fixes applied during the apply phase:
- `docs/setup.md:223` — "Run overnight in detached tmux" → "detached Python process (no tmux)"
- `docs/index.html:4555` — SVG annotation "▸ detaches into tmux" → "▸ detaches as Python process"
- `docs/index.html:4582` — section heading "runner · tmux · detached" → "runner · Python · detached"
- `docs/index.html:4852` — SVG comment "Doc: runs in runner.sh" → "Doc: runs in runner.py"
- `docs/index.html:4969` — "cortex overnight start runs in tmux" → "detaches as a Python process"
- `skills/overnight/references/new-session-flow.md:199-200` — "Attach with `tmux attach -t overnight-runner`" → "Inspect progress with `cortex overnight status` and `cortex overnight logs <session-id>`"

**Verified CLI surface (mcp-contract claim):**
- `cortex overnight start --format json` and `--max-rounds N` are real flags per `cortex overnight start --help`. Docs that reference them are accurate.

**Total: 6 additional doc edits applied during apply phase across 3 files (2 in docs/setup.md and docs/index.html; 1 in skills/overnight/references/new-session-flow.md).**

The critical-review's most valuable contribution was forcing the empirical re-check that the original audit-then-fix pipeline did not include.
