# Specification: Rewrite README, migrate content to docs/setup.md, reorganize docs/, and fix stale paths (#166)

> Epic context: this lifecycle is scoped from epic #165. See [research/repo-spring-cleaning/research.md](../../research/repo-spring-cleaning/research.md) for the broader epic-tier audit; this spec is scoped to #166's child slice only (README + setup.md + docs/internals/ + skill-table dedup + bash-runner sweep + docs/backlog.md trim + dashboard policy + stale paths).

## Problem Statement

The cortex-command repo is in a "still-bloated" state for the installer audience: 132-line `README.md` mixes installer-tier prose with concept-encyclopedia content (ASCII pipeline diagram, repo-structure tour, settings.json ownership rules); three pure-internal docs (`pipeline.md`, `sdk.md`, `mcp-contract.md`) sit in the same `docs/` root as user-tier docs; `agentic-layer.md` and `skills-reference.md` duplicate skill-inventory tables; bash-runner terminology drift propagates the false impression that `runner.sh` exists in the repo when it was retired in favor of `cortex_command/overnight/runner.py`; `docs/backlog.md` L198-234 carries plugin-development content miscategorized as backlog content; `docs/dashboard.md` instructs `just dashboard` (clone-only); five small post-#117/#148 stale-path residuals remain. Coordinated cleanup ships repo-share-readiness for end-user installers running `cortex init` to use the agentic layer in their own projects.

## Requirements

1. **README ≤ 90 lines.** Acceptance: `wc -l < README.md` returns a value ≤ 90.

2. **README cuts.** Remove the following sections in their entirety: ASCII pipeline diagram + tier/criticality legend (current L11–29); plugin auto-update mechanics paragraph + extras-tier callout (current L52–54); Authentication H2 + body (current L73–75); What's Inside table + body (current L77–88); Customization H2 + body (current L89–91); Distribution H2 + body (current L93–100); Commands H2 + body (current L102–115). Acceptance: `grep -cE '^## (Authentication|What.s Inside|Customization|Distribution|Commands)$' README.md` returns 0.

3. **README pitch trimmed.** Drop distribution-mechanics blur from current paragraph 3 (L7); keep workflow narrative paragraph (current L9). Acceptance: README pitch (lines from `# Cortex Command` to before `## Prerequisites`) is ≤ 100 words. (`awk '/^# Cortex Command/{flag=1; next} /^## Prerequisites/{flag=0} flag' README.md | wc -w` returns ≤ 100.)

4. **README Documentation index updated.** Add an Authentication row (pointing at `docs/setup.md#authentication`); add an Upgrade & maintenance row (pointing at `docs/setup.md#upgrade--maintenance`); drop the existing `docs/pipeline.md` row entirely (no `docs/internals/` rows added — internals are findable via in-doc cross-references in CLAUDE.md L50, mcp-server.md, agentic-layer.md). Acceptance: `grep -cE 'Authentication|Upgrade.*maintenance' README.md` returns ≥ 2 within the Documentation index section; `grep -cE '^\| .*docs/internals/' README.md` returns 0; `grep -E '^\| .*docs/pipeline\.md' README.md` returns 0.

5. **docs/setup.md hard-prereq additions.** These MUST land in the same commit as or before the README cut commit:
   - **`uv tool uninstall uv` foot-gun warning** with co-occurring caution context. Acceptance: `grep -B2 'uv tool uninstall uv' docs/setup.md | grep -iE 'foot-gun|warning|do not|never|breaks'` returns ≥ 1.
   - **`uv run` user-project semantics note**. Acceptance: `grep -A3 -B1 'uv run' docs/setup.md | grep -iE "user.s.*project|own project|own venv|operates on"` returns ≥ 1.
   - **Forker fork-install URL pattern** `uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>`. Acceptance: `grep 'github\.com/<your-fork>' docs/setup.md` returns ≥ 1.
   - **Top-level "## Upgrade & maintenance" section** elevated from the current `#### Upgrading` subsection at L40–47 (which lives under "Install the cortex CLI"). The new section absorbs both the MCP-driven path (`/plugin update cortex-overnight@cortex-command`) and bare-shell path (`uv tool install --reinstall ...`). Acceptance: `grep -E '^## Upgrade' docs/setup.md` returns 1.
   - **Customization content** (settings.json ownership rule) preserving the existing rule from the README. Acceptance: `grep -iE 'cortex-command does not own.*settings\.json|do not own.*settings\.json' docs/setup.md` returns ≥ 1.
   - **Commands subsection** listing cortex CLI subcommands. Acceptance: `grep -E '^### Commands|^## Commands' docs/setup.md` returns ≥ 1; the section contains: `cortex overnight start`, `cortex overnight status`, `cortex overnight cancel`, `cortex overnight logs`, `cortex init`, `cortex --print-root` (each individual `grep '<string>' docs/setup.md` returns ≥ 1).

6. **docs/setup.md trim.** Collapse `cortex init` 7-step explainer (current L107–128) to ≤ 4 steps; compress `lifecycle.config.md` schema block (current L130–160) to a brief reference card form. Decision: `CLAUDE_CONFIG_DIR` section (current L352–388) stays at its current location with no rename in this ticket — moving to a forker-tier section is deferred. Acceptance: `cortex init` numbered list in setup.md has ≤ 4 top-level items; `lifecycle.config.md` schema block reduced by ≥ 15 lines from its current 30-line form.

7. **docs/internals/ relocation atomic commit.** Move `docs/pipeline.md` → `docs/internals/pipeline.md`, `docs/sdk.md` → `docs/internals/sdk.md`, `docs/mcp-contract.md` → `docs/internals/mcp-contract.md`.
   
   **7a. Breadcrumb edits on the moved files** (per actual file content; mc-1 of the critical-review):
   - `docs/internals/pipeline.md` line 1: existing `[← Back to Agentic Layer](agentic-layer.md)` → `[← Back to Agentic Layer](../agentic-layer.md)` (agentic-layer.md stays at docs/-root).
   - `docs/internals/sdk.md` line 1: existing `[← Back to Agentic Layer](agentic-layer.md)` → `[← Back to Agentic Layer](../agentic-layer.md)`.
   - `docs/internals/mcp-contract.md` line 1: existing line is `# MCP ↔ CLI Contract` (NO breadcrumb at line 1; do not add one in this commit).
   
   **7b. Intra-file relative links inside the moving files** (each must gain a `../` prefix because the target is at docs/-root, not inside docs/internals/):
   - `docs/internals/pipeline.md` L117 `[overnight-operations.md…](overnight-operations.md#per-spawn-sandbox-enforcement)` → `(../overnight-operations.md#per-spawn-sandbox-enforcement)`.
   - `docs/internals/pipeline.md` L150 `[docs/overnight-operations.md](overnight-operations.md)` → `(../overnight-operations.md)`.
   - `docs/internals/pipeline.md` L13 `[SDK Integration](sdk.md)` requires NO edit (target is sibling inside docs/internals/).
   - `docs/internals/sdk.md` L9 `[research/claude-code-sdk-usage/research.md](../research/claude-code-sdk-usage/research.md)` → `(../../research/claude-code-sdk-usage/research.md)`.
   - `docs/internals/sdk.md` L11 `[overnight-operations.md](overnight-operations.md)` → `(../overnight-operations.md)`.
   - `docs/internals/sdk.md` L112 `[overnight-operations.md](overnight-operations.md)` → `(../overnight-operations.md)`.
   - `docs/internals/sdk.md` L199 `[\`docs/overnight-operations.md\`…](overnight-operations.md#per-spawn-sandbox-enforcement)` → `(../overnight-operations.md#per-spawn-sandbox-enforcement)`.
   
   **7c. Cross-references in non-moving files** (path updates):
   - `CLAUDE.md:50` doc-ownership rule path citations: `docs/pipeline.md` → `docs/internals/pipeline.md`; `docs/sdk.md` → `docs/internals/sdk.md` (path-substitution-only; do not expand the rule).
   - `cortex_command/cli.py:268` stderr message: bareword `docs/mcp-contract.md` → canonical GitHub URL `https://github.com/charleshall888/cortex-command/blob/main/docs/internals/mcp-contract.md`.
   - `bin/cortex-check-parity:59` comment: `docs/pipeline.md` → `docs/internals/pipeline.md`.
   - `docs/overnight-operations.md` L318/L326/L339 bareword `(sdk.md)` → `(internals/sdk.md)`.
   - `docs/overnight-operations.md` L593/L599 prose `docs/pipeline.md` → `docs/internals/pipeline.md`.
   - `docs/mcp-server.md:9` bareword sibling refs: `pipeline.md` → `internals/pipeline.md`, `sdk.md` → `internals/sdk.md`.
   - `README.md:127` (current Documentation index pipeline.md row) — drop entire row per Q4 user decision (no internals row added).
   - `plugins/cortex-core/bin/cortex-check-parity:59` mirror regenerates automatically via `just build-plugin` (pre-commit hook).
   
   **7d. Acceptance** (run on post-commit-1 HEAD):
   - `[ -f docs/internals/pipeline.md ] && [ -f docs/internals/sdk.md ] && [ -f docs/internals/mcp-contract.md ] && echo OK` returns "OK".
   - `[ ! -f docs/pipeline.md ] && [ ! -f docs/sdk.md ] && [ ! -f docs/mcp-contract.md ] && echo OK` returns "OK".
   - **Broadened filter** (excludes ALL lifecycle dirs, not just archive): `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' . --include='*' 2>/dev/null | grep -vE 'lifecycle/|research/|backlog/|retros/'` returns no live-source hits.
   - `grep 'docs/internals/' CLAUDE.md` returns ≥ 2.
   - `grep 'github\.com/charleshall888/cortex-command/blob/main/docs/internals/mcp-contract\.md' cortex_command/cli.py` returns 1.
   - `head -n 1 docs/internals/pipeline.md docs/internals/sdk.md` shows breadcrumb with `(../agentic-layer.md)` target on each (mcp-contract.md skipped — has no breadcrumb).
   - Intra-file link verification: `grep -E '\]\((overnight-operations\.md|agentic-layer\.md|\.\./research/)' docs/internals/*.md` returns no hits without a leading `../` (any unprefixed match indicates a missed L117/L150/L9/L11/L112/L199 edit).

8. **Skill-table dedup.** Remove skill-inventory tables from `docs/agentic-layer.md` (currently L17–62 across Development Workflow / Code Quality / Thinking Tools / Session Management / Utilities groupings). Migrate the `pipeline-not-a-skill` callout (currently `agentic-layer.md:64`) verbatim into `docs/skills-reference.md` BEFORE removing it from agentic-layer.md. Replace `agentic-layer.md` L21 dev-row "/pipeline" routing language with "/overnight" (the user-facing trigger). Add a top-of-file pointer to agentic-layer.md (positioned after the breadcrumb / before the first H2): `For full skill descriptions and trigger details, see [skills-reference.md](skills-reference.md).` Acceptance:
   - `wc -l < docs/agentic-layer.md` returns a value ≥ 40 lower than its pre-trim line count.
   - `grep -E '/pipeline\b' docs/skills-reference.md docs/agentic-layer.md` returns no live-routing hits (any remaining mentions must be in disambiguation prose, not routing instructions).
   - `grep 'pipeline.*not a user-facing skill' docs/skills-reference.md` returns 1.
   - `grep '\[skills-reference\.md\](skills-reference\.md)' docs/agentic-layer.md` returns ≥ 1.

9. **User-facing bash-runner terminology sweep.** Update each of the following to remove "bash runner" / "bash overnight runner" prose:
   - `skills/overnight/SKILL.md` L3 (description), L22 (body), L391, L400, L401: "bash runner" → "runner" or context-appropriate equivalent.
   - `skills/overnight/SKILL.md:198`: drop the "(line 179 of `runner.sh`)" parenthetical entirely; preserve surrounding text. Do NOT replace with a `runner.py:N` citation (line numbers re-rot).
   - `skills/diagnose/SKILL.md:62`: "bash runner" → "runner".
   - `docs/overnight.md:8`: "launch a bash runner" → "launch the runner".
   - `docs/agentic-layer.md` L187, L313: "bash runner" / "bash overnight runner" → "runner" / "overnight runner".
   - `docs/skills-reference.md` L59, L71: "bash runner" → "runner".
   - `docs/sdk.md:179` (relocating to `docs/internals/sdk.md` in same commit batch): "`runner.sh`" → "the runner" or equivalent.
   Acceptance: `grep -rn 'bash runner\|bash overnight runner' docs/ skills/` returns no hits.

10. **docs/backlog.md "Global Deployment" trim with substantive migration.** Cut the entire section at `docs/backlog.md` L198–234 (heading L198 "Global Deployment", subsections "Adding a new deployable script" L202, PATH-resolution L208, Path.cwd() rule L218, currently-deployed-scripts table L228–233). Migrate to `docs/plugin-development.md` as a new section "## Adding a deployable bin script" inserted after the current "## Iterating on plugin source" section (current L96–105), containing: (a) `Path.cwd()` vs `Path(__file__).parent` rule for repo-local dirs (load-bearing — per-script bin scripts must use `Path.cwd()` so they operate on the user's project, not cortex-command itself); (b) per-script bin-deployment mechanism (how a script gets exposed via the cortex-core plugin's `bin/` directory). Drop the 3-row currently-deployed-scripts table (drift-prone; replaceable by `ls plugins/cortex-core/bin/`). Acceptance:
    - `grep -E '^## Global Deployment|Adding a new deployable script' docs/backlog.md` returns 0.
    - `grep '^## Adding a deployable bin script' docs/plugin-development.md` returns 1.
    - `grep -E 'Path\.cwd|Path\(__file__\)' docs/plugin-development.md` returns ≥ 1.
    - `grep 'cortex-core' docs/plugin-development.md | grep -i 'bin'` returns ≥ 1 (per-script bin-deployment mechanism documented).

11. **Stale-path fixes.**
    - `requirements/pipeline.md:130`: delete the parenthetical `(Convention defined in claude/reference/output-floors.md; enforcement requires orchestrator prompt changes.)`. Final wording ends at "Routine forward-progress decisions do not require this field."
    - `CHANGELOG.md` L21–22: replace the bullets promising `docs/install.md` and `docs/migration-no-clone-install.md` with a single bullet pointing at `docs/setup.md` (canonical install/upgrade reference).
    - `scripts/validate-callgraph.py:12`: drop the sentence "See claude/reference/claude-skills.md "Common Mistakes" row 303." Keep the rule statement and self-contained rationale (lines 10–11).
    - `skills/requirements/references/gather.md:201`: fix broken relative link `[requirements/project.md](project.md)` → `[requirements/project.md](../../../requirements/project.md)`.
    - `backlog/133-evaluate-implementmd180-progress-tail-narration-under-opus-47.md:56`: fix broken markdown link target by inserting `archive/` segment: `[lifecycle/archive/...](../lifecycle/archive/remove-progress-update-scaffolding-from-long-running-prompts-dr-3-wave-1/research.md)` (display text already has `archive/`; only target needs the segment).
    Acceptance:
    - `grep 'claude/reference/output-floors\.md' requirements/pipeline.md` returns 0.
    - `grep -E 'docs/install\.md|docs/migration-no-clone-install\.md' CHANGELOG.md` returns 0.
    - `grep 'claude/reference/claude-skills\.md' scripts/validate-callgraph.py` returns 0.
    - `grep '\[requirements/project\.md\](project\.md)' skills/requirements/references/gather.md` returns 0.
    - `grep '\.\./lifecycle/remove-progress' backlog/133-*.md` returns 0; `grep '\.\./lifecycle/archive/remove-progress' backlog/133-*.md` returns 1.
    - **Broad-scope verifier** (per critical-review R3F4): `grep -rn 'claude/reference/' . --include='*.py' --include='*.sh' --include='*.md' 2>/dev/null | grep -vE 'lifecycle/|research/|backlog/|retros/'` returns no live-source hits (excludes lifecycle artifacts which retain historical references for context).

12. **Ship `cortex dashboard` verb (Option 1 per user decision).** This requirement spans multiple files; the `~25-40 LOC` budget covers cli.py only — additional files require concrete edits enumerated below (per critical-review TL1).
    
    **12a. cli.py changes**:
    - Argparse: `subparsers.add_parser("dashboard", help="Launch the dashboard web UI on localhost", ...)` registered alongside existing verbs (between `init` at L600 and `upgrade` at L628 is a natural slot).
    - `_dispatch_dashboard` handler: launches the dashboard. Two valid implementation strategies:
      - **(A) In-process uvicorn** — import `uvicorn` and call `uvicorn.run("cortex_command.dashboard.app:app", host=..., port=..., log_level=...)` directly. Avoids `uv run` subshell ambiguity (Edge Case L115); avoids subprocess orphaning (TL3); the verb itself blocks until uvicorn exits, and Ctrl-C/SIGTERM in the parent shell propagates naturally.
      - **(B) Subprocess `uv run uvicorn …`** — only if (A) is infeasible. If (B) is used, the handler MUST install a SIGTERM/SIGINT handler that forwards the signal to the uvicorn child process group before exiting. Acceptance: parent SIGTERM kills child uvicorn within 2s.
    - Strategy selection deferred to plan-phase but plan MUST pick (A) unless it documents why (A) fails for installed wheels.
    - `--port <int>` flag with default 8080; `DASHBOARD_PORT` env var honored as fallback before defaulting.
    
    **12b. cortex_command/dashboard/app.py changes** (mandatory; identified by critical-review TL1):
    - **L200**: replace hard-coded `_pid_file = Path(__file__).parent / ".pid"` with XDG-compliant resolver: `_pid_file = _resolve_pid_path()` where `_resolve_pid_path()` returns `Path(os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))) / 'cortex' / 'dashboard.pid'` and creates the parent directory if missing. (macOS native cache convention `~/Library/Caches/` is acceptable but XDG-with-`~/.cache` fallback is portable; deferred to plan-phase choice — see Edge Cases.)
    - **L226**: replace `_check_port(int(os.environ.get("DASHBOARD_PORT", "8080")))` with logic that reads port from a single source of truth — either an env var the verb sets before launching uvicorn, or a config-passed argument if strategy (A). The current decoupling between verb's `--port` flag and app.py's env-only port read is a fix-invalidating bug per critical-review TL1.
    - **L230** (lifespan precondition): the existing `if not (root / ".claude").exists(): raise RuntimeError(...)` blocks new installer users who run `cortex dashboard` before `cortex init`. Either downgrade to a printed warning + `cortex init`-suggestion, or document the prerequisite explicitly in `docs/dashboard.md`. Plan-phase chooses; current spec mandates one of the two outcomes.
    
    **12c. Existing PID consumers** (mandatory updates so the orchestrator and existing automation continue to work):
    - `skills/overnight/SKILL.md:208` (and plugin mirror `plugins/cortex-overnight/skills/overnight/SKILL.md:208`): liveness probe path `cortex_command/dashboard/.pid` → `~/.cache/cortex/dashboard.pid` (or platform-resolved equivalent matching 12b).
    - `.gitignore:30` `claude/dashboard/.pid` entry — orphaned by prior cleanup; remove or update if still relevant. Plan-phase resolves.
    
    **12d. Tests** (mandatory; existing pattern at tests/test_cli_print_root.py, tests/test_cli_upgrade.py, tests/test_cli_handler_logs.py):
    - New `tests/test_cli_dashboard.py` with at least: (1) `cortex dashboard --help` exits 0 and contains "--port"; (2) PID-file location resolves under `~/.cache/cortex/` or platform equivalent; (3) verb does NOT write to `cortex_command/dashboard/.pid` under any condition.
    
    **12e. justfile**:
    - Update `dashboard` recipe (current L100–113) to write PID to the same XDG-compliant location for consistency. (Optionally: replace recipe body with `cortex dashboard "$@"` if (A) ships first.)
    
    **12f. docs/dashboard.md prose**:
    - Update L14 instruction to `cortex dashboard` (verb) as primary; keep `just dashboard` as contributor-clone path with explicit "(requires a clone of cortex-command)" annotation.
    
    **12g. Acceptance** (post-implementation):
    - `cortex --help` lists `dashboard` in the subcommand block.
    - `cortex dashboard --help` exits 0 with usage text including `--port` flag.
    - `grep 'cortex dashboard' docs/dashboard.md` returns ≥ 1; `grep -i 'requires a clone' docs/dashboard.md` returns ≥ 1.
    - `grep -E 'XDG_CACHE_HOME|\.cache/cortex' cortex_command/cli.py cortex_command/dashboard/app.py` returns ≥ 2.
    - `grep 'cortex_command/dashboard/\.pid' skills/overnight/SKILL.md plugins/cortex-overnight/skills/overnight/SKILL.md` returns 0 (old path purged from probes).
    - `tests/test_cli_dashboard.py` exists; `pytest tests/test_cli_dashboard.py -v` exits 0.
    - **Functional smoke test (full form, NOT reducible)**: `cortex dashboard --port 18080 &; CHILD_PID=$!; sleep 3; HTTP_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:18080/health); kill $CHILD_PID; wait $CHILD_PID 2>/dev/null; echo "$HTTP_STATUS"` returns `200`. (Interactive/session-dependent rationale: requires the verb to bind a port and serve a request; the previous reduced-form fallback "exits 0 within 5s" was deleted because it can pass for a verb that fails to bind any port.)
    - **SIGTERM propagation acceptance** (only if strategy B): `cortex dashboard --port 18081 & PARENT=$!; sleep 2; kill -TERM $PARENT; sleep 2; pgrep -f 'uvicorn.*cortex_command.dashboard'` returns no PIDs (uvicorn child terminated within 2s of parent SIGTERM).

13. **plugins/cortex-core/bin/cortex-check-parity regenerated cleanly.** After `bin/cortex-check-parity` L59 edit, the pre-commit hook's `just build-plugin` regenerates the mirror. Acceptance: `git diff plugins/cortex-core/bin/cortex-check-parity` after a clean `just build-plugin` invocation shows only the L59 path-substitution change (or zero diff if commit was made through the hook).

## Non-Requirements

- **No edit to `requirements/project.md:7`** audience language. F-12 dropped post-critical-review per discovery; current line 7 already reads as installer-primary, forker-secondary.
- **No DR-2 visibility cleanup** (`.gitignore`-hide / `.cortex/` relocation). Deferred per DR-2 = Option C.
- **No code/script/hook deletion** — child #168.
- **No lifecycle/research archive sweep** — child #169.
- **No new MUST/CRITICAL/REQUIRED escalations** added to CLAUDE.md, skills/, or hooks/. Body's "must" usage in this spec is descriptive prerequisite/acceptance language, not normative directive added to runtime files.
- **No sweep of `cortex_command/overnight/*.py` port-provenance comments** (~30+ "Mirrors `runner.sh:N`" comments). Out of #166 user-facing scope; address in follow-on if drift becomes a clarity issue.
- **No sweep of `cortex_command/overnight/prompts/orchestrator-round.md` runtime prompt strings** (L8/L20/L486 "bash runner will invoke"). Per Agent 1 codebase analysis: agent's mental model is "exit; parent process resumes batch_runner.py" — language of parent is operationally invisible to the spawned agent. Out of #166 user-facing scope.
- **No sweep edit to `docs/overnight-operations.md`** for `runner.sh` mentions (23 occurrences). Carve-out rationale: doc owns runner round-loop content per CLAUDE.md:50; `runner.sh` references are operator-vocabulary glossary in file-and-state inventory tables (e.g., L81 file table row, L396 `lifecycle/.runner.lock | runner.sh`); the doc explicitly notes runner.sh retirement at L212. The acceptance grep pattern (`bash runner|bash overnight runner`) inherently excludes `runner.sh` mentions, which is what protects this doc from sweep collateral.
- **No sweep of `tests/` bash-runner mentions** (3 occurrences: tests/test_runner_followup_commit.py:10, tests/test_events.py:66, tests/test_runner_pr_gating.py:179). These are developer-facing test-file docstrings/comments, not user-facing prose. The Requirement 9 acceptance grep is scoped to `docs/ skills/` which mechanically excludes tests/. Carve-out rationale: tests/ are contributor-tier source not part of the installer-audience share-readiness scope; address in follow-on if the docstring drift becomes confusing during test maintenance.
- **No subtable for internals docs** in README Documentation index (per user decision). Drop pipeline.md row entirely; sdk.md and mcp-contract.md are not added.
- **No new pre-commit hook** for hard-prereq enforcement. Plan-phase commit ordering (commit 7 setup.md before commit 8 README rewrite) plus PR-review acceptance-grep checklist suffice. A pre-commit hook that fails README-cut commits when setup.md lacks required strings would be brittle (conditional-on-cut detection) and dead weight after the one-shot prereq is satisfied.
- **No programmatic skill-table generator.** Defer to follow-on ticket if drift recurs after canonical-source dedup. Build-system surface (a generator script + dual-source enforcement + drift hook) outweighs the one-time dedup benefit at current scale.
- **No frontmatter audit on backlog/133.** Verified: backlog/133's `spec:` frontmatter points at a different slug (`evaluate-implementmd119-...`) than the broken body-link target. Body-link fix is sufficient; frontmatter is unaffected.
- **No release-process.md or plugin-development.md relocation to docs/internals/.** DR-3 = Option B explicitly leaves these at `docs/` root because they serve forkers and contributors who do read `docs/`.

## Edge Cases

- **Atomic-landing constraint between commits**: Commit 1 (internals move + cross-refs) updates README.md:127 (drops the pipeline.md row entirely per user choice in Q4) so the README index never points at a relocated path between commits. Subsequent commits 2–8 do not touch internals paths in README.md. Verifiable: between any two adjacent commits in the sequence, `grep 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' README.md` returns 0.
- **Pre-commit hook regenerates plugin mirror, overwriting manual edits**: Risk if implementer stages both `bin/cortex-check-parity` (canonical) AND `plugins/cortex-core/bin/cortex-check-parity` (mirror) with inconsistent contents — Phase 3 of `.githooks/pre-commit` runs `just build-plugin`, regenerating the mirror and overwriting the manual edit. Mitigation: plan-phase guidance instructs implementer to edit only canonical sources (`bin/cortex-check-parity`); do NOT stage `plugins/cortex-core/bin/*` manually — let the hook regenerate.
- **CLAUDE.md 100-line cap**: Currently 68 non-empty lines. The L50 path-substitution edit is line-count-neutral (zero net delta). If any "while we're here" CLAUDE.md addition is suggested during plan-phase implementation, plan must re-test cap and apply receiver-edit cascade if exceeded (extract OQ3 + OQ6 + new entry to `docs/policies.md`, leave one-line pointer in CLAUDE.md).
- **Wheel install dashboard PID write**: Default PID at `cortex_command/dashboard/.pid` (justfile L104) fails for installed wheels — package directory is read-only. Verb must write to `$XDG_CACHE_HOME/cortex/dashboard.pid` with `~/.cache/cortex/dashboard.pid` fallback. justfile dashboard recipe should mirror this for code-path consistency.
- **Dashboard verb on systems without `~/.cache`**: Some BSDs / older Linux. Verb must use `os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))` and create the cortex/ subdir if missing.
- **macOS native cache convention** (per critical-review R2F6): macOS-native cache is `~/Library/Caches/`, not `~/.cache/`. Per requirements/project.md L34 ("macOS — primary supported platform"), the verb's PID-file location should ideally honor platform-native conventions. Plan-phase may use `platformdirs` library (already a transitive dep via fastapi/uvicorn? — verify) to resolve `user_cache_dir('cortex')` cleanly across darwin/linux/win32. If `platformdirs` is not used, the spec's `~/.cache/cortex/dashboard.pid` fallback is acceptable on macOS as long as the chosen path is consistent across all PID readers (cli.py verb, app.py L200, skills/overnight/SKILL.md:208 probe).
- **Reduced-form smoke test removed** (per critical-review R3F3): the previous "subprocess command exits 0 within 5s without traceback" reduction was deleted from Requirement 12g acceptance because a verb that fails to bind a port can satisfy it while serving zero requests. CI must run the full curl-based smoke test or skip the test entirely (with explicit annotation).
- **README leftover content backstop** (per critical-review R3F6): Requirement 5's hard-prereq greps verify content presence in setup.md but don't catch the case where Customization-body content is duplicated to setup.md AND survives in README in a renamed form. Backstop: PR-review checklist includes a manual diff check that no rule-statement string from the cut README sections (e.g., "cortex-command does not own", "uv tool uninstall uv") appears in BOTH setup.md AND README.md post-cut. Augment the existing wc -l ≤ 90 cap (Requirement 1) which provides partial line-count backstop.
- **Acceptance grep collision in code blocks**: Lexical-only grep can pass with strings inside fenced code-block "do not run this" examples, where warning context evaporates. Mitigation: Requirement 5 acceptance criteria use co-occurrence checks (e.g., `grep -B2 'uv tool uninstall uv' | grep -iE 'foot-gun|warning|do not|never|breaks'`) rather than bare existence checks.
- **agentic-layer.md trim breaks workflow narrative context**: After tables removed, narrative sections (currently L177–200) reference skills by trigger phrase without on-page definition. Mitigation: top-of-file pointer to skills-reference.md (Requirement 8) so readers reach the trigger-detail index without backtracking.
- **Stale link target in archived backlog**: backlog/133 is `status: complete`. Editing closed/complete backlog item bodies is unusual but not policy-blocked. Frontmatter is unaffected by this edit (verified: `lifecycle_slug` not present; `spec:` points at a different slug).
- **CHANGELOG broken-ref convention**: Common-Changelog FAQ permits historical edits ("a changelog is a historical record and a useful reference"). The `docs/install.md` reference is a "fix the typo" case — silently replace with the canonical destination.
- **uv tool venv vs current project**: `uv run` invoked by cortex internally operates on the user's current project venv, not cortex's tool venv. setup.md note must clarify this so installers don't expect cortex-command's own venv to satisfy their project deps.
- **Forker fork-URL pattern collides with main-URL pattern**: setup.md must distinguish the two: `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0` (upstream) vs `uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>` (fork). Both patterns are valid; setup.md's Upgrade & maintenance section presents both as alternatives.

## Changes to Existing Behavior

- **ADDED**: `cortex` CLI gains a `dashboard` subcommand. Behavior: launches `uv run uvicorn cortex_command.dashboard.app:app` on port 8080 (overridable via `--port`); writes PID to `$XDG_CACHE_HOME/cortex/dashboard.pid` (or `~/.cache/cortex/dashboard.pid`); usable from any cwd by an installer who installed cortex-command via `uv tool install`. Dashboard runtime deps (`fastapi`, `uvicorn[standard]`, `jinja2`) already ship in `[project.dependencies]` at `pyproject.toml:11–13` — no dependency changes required.
- **MODIFIED**: `docs/dashboard.md` L14 instructs `cortex dashboard` (verb) for installer invocation. `just dashboard` retained with explicit "(requires a clone of cortex-command)" annotation as the contributor-clone alternative.
- **MODIFIED**: `docs/pipeline.md`, `docs/sdk.md`, `docs/mcp-contract.md` relocated to `docs/internals/` subdirectory. External markdown-link references into the old paths break (acceptable per OSS reorganization conventions for repo-only Markdown — see Web Research findings on repo-only doc reorg).
- **MODIFIED**: `README.md` cut from 132 lines to ≤ 90. Removed sections: Authentication H2, What's Inside table, Customization H2, Distribution H2, Commands H2, ASCII pipeline+legend block. Documentation index expanded with Authentication and Upgrade & maintenance rows; pipeline.md row dropped (no `docs/internals/` rows added — internals findable via in-doc cross-references).
- **MODIFIED**: `CLAUDE.md:50` doc-ownership rule path citations updated for moved internals (`docs/pipeline.md` → `docs/internals/pipeline.md`; `docs/sdk.md` → `docs/internals/sdk.md`). Rule wording unchanged; line count unchanged.
- **MODIFIED**: `cortex_command/cli.py:268` post-upgrade-migration stderr message form: relative path `docs/mcp-contract.md` replaced with canonical GitHub URL `https://github.com/charleshall888/cortex-command/blob/main/docs/internals/mcp-contract.md`. Wheel-install users running `cortex upgrade` from arbitrary cwd can now follow the link.
- **MODIFIED**: `docs/agentic-layer.md` L21 dev-row routing language: `/pipeline` (a non-skill internal module name) replaced with `/overnight` (the user-facing trigger).
- **MODIFIED**: `docs/setup.md` gains a top-level `## Upgrade & maintenance` section absorbing the current `#### Upgrading` subsection content from L40–47.
- **REMOVED**: `docs/agentic-layer.md` skill-inventory tables (~ 45 lines across Development Workflow / Code Quality / Thinking Tools / Session Management / Utilities groupings). Pipeline-not-a-skill callout (currently agentic-layer.md:64) migrated verbatim to `docs/skills-reference.md`.
- **REMOVED**: `docs/backlog.md` "Global Deployment (Cross-Repo Use)" section (L198–234) including the 3-row currently-deployed-scripts table.
- **REMOVED**: `requirements/pipeline.md:130` parenthetical citing retired `claude/reference/output-floors.md`.
- **REMOVED**: `CHANGELOG.md` L21–22 references to non-existent `docs/install.md` and `docs/migration-no-clone-install.md`.
- **REMOVED**: `scripts/validate-callgraph.py:12` citation of retired `claude/reference/claude-skills.md`.
- **ADDED**: `docs/plugin-development.md` "## Adding a deployable bin script" section with `Path.cwd()` rule and per-script bin-deployment mechanism (substantively migrated from `docs/backlog.md` L198–234 before that section is cut).
- **ADDED**: `docs/setup.md` content additions: `uv tool uninstall uv` foot-gun warning, `uv run` user-project semantics note, forker fork-install URL pattern, top-level "Upgrade & maintenance" section, Customization (settings.json ownership), Commands subsection.
- **ADDED**: `docs/skills-reference.md` gains the pipeline-not-a-skill callout migrated from agentic-layer.md:64.
- **ADDED**: `docs/agentic-layer.md` gains a top-of-file pointer `For full skill descriptions and trigger details, see [skills-reference.md](skills-reference.md).` after breadcrumb / before first H2.
- **ADDED**: README Documentation index gains Authentication row and Upgrade & maintenance row.

## Technical Constraints

- **DR-1 hard prerequisite**: setup.md content additions (Requirement 5) MUST land in same commit as or before the README cut commit (Requirement 2). Failure mode: cut deletes content not yet relocated. Enforcement: plan-phase commit ordering (commit 7 setup.md before commit 8 README rewrite) + PR-review acceptance-grep checklist.
- **Pre-commit hook plugin-mirror regeneration**: `bin/cortex-check-parity` edit (Requirement 7) triggers `BUILD_NEEDED=1` in `.githooks/pre-commit` Phase 2 (matches `^bin/cortex-`). Phase 3 runs `just build-plugin`, regenerating `plugins/cortex-core/bin/cortex-check-parity`. Plan-phase guidance: edit only canonical sources; do not stage plugin mirror manually.
- **CLAUDE.md edits inside lifecycle**: this lifecycle (#166's slug) is a valid lifecycle for the CLAUDE.md L50 path edit (per CLAUDE.md's own convention: skill/hook/CLAUDE.md edits are lifecycle-mediated; this lifecycle covers the touched scope).
- **Skills/ edits inside lifecycle**: bash-runner sweep (Requirement 9) touches `skills/overnight/SKILL.md` and `skills/diagnose/SKILL.md` — both canonical sources whose plugin mirrors regenerate via `just build-plugin`. This lifecycle is a valid covering lifecycle for those edits.
- **All commits via `/cortex-core:commit`**: per CLAUDE.md L40. No manual `git commit` invocations.
- **CLAUDE.md L50 path-substitution-only**: Avoid expanding the rule with "see also" guidance to prevent line-count crossing of the 100-line cap.
- **Wheel-install URL form for cli.py:268**: `cortex upgrade` runs from arbitrary cwd; relative path `docs/internals/mcp-contract.md` is unfollowable for wheel users. Canonical GitHub URL is required.
- **`docs/overnight-operations.md` carve-out**: doc owns runner round-loop content per CLAUDE.md:50; `runner.sh` references are operator-vocabulary glossary; retirement notice already at L212. Carve-out is documented in this spec's Non-Requirements; no edits to overnight-operations.md beyond the cross-ref updates already enumerated in Requirement 7 (L318/L326/L339/L593/L599 path updates).
- **Dashboard verb XDG-compliance**: `cortex dashboard` PID file MUST use `$XDG_CACHE_HOME/cortex/dashboard.pid` with `~/.cache/cortex/dashboard.pid` fallback. In-package writes (`cortex_command/dashboard/.pid`) fail under installed-wheel layout.
- **Atomic-landing — no broken-cross-ref window**: README.md:127 path-update lands in commit 1 (with internals move). Per user choice in Q4, the fix is to drop the pipeline.md row entirely; this satisfies the atomic-landing requirement (the broken pipeline.md row simply ceases to exist in commit 1 rather than being repointed).
- **Underlying invariant** (per critical-review TL3): the binding constraint is "every relocating-path edit lands in the same diff as the file move" — not the specific 8-commit topology. Any commit topology that satisfies this invariant is acceptable. The 8-commit sequence below is one valid topology; plan-phase may revise (including in response to plan-boundary critical-review) provided the invariant holds.
- **Merge strategy clarification**: under squash-merge, the 8-commit sequence collapses to one main-branch commit and the invariant is automatically satisfied; under merge-commit, intermediate-commit ordering matters. The spec is invariant-driven, not topology-driven, to handle either workflow.
- **Intermediate-commit invariant** (under merge-commit): every commit on the PR branch MUST satisfy at minimum: (a) `git status` clean working tree post-commit; (b) `git ls-files --others --exclude-standard` returns no untracked source files; (c) `bin/cortex-check-parity` exits 0 (since this gate runs on every PR-touch path). Tests are NOT required to pass at every intermediate commit (the bash-runner sweep at commit 4 may transiently break test docstrings) but the build-plugin hook MUST pass.
- **Plan-phase 8-commit sequence** (one valid topology satisfying the invariant):
  1. docs/internals/ move + all 7c cross-refs (CLAUDE.md, cli.py:268 canonical-URL, bin/cortex-check-parity, overnight-operations.md, mcp-server.md, README.md:127 row drop) + 7a breadcrumb edits + 7b intra-file relative-link edits. Plugin mirror regenerated by hook. **Recovery**: if any sub-edit is missed and the acceptance grep at 7d fails post-commit, use a follow-up commit 1.5 with the missed edits — atomic-landing invariant is satisfied if all relocating-path edits exist by end-of-commit-sequence on the PR branch (and atomically under squash). Do NOT use `--amend` (cortex commit convention favors new commits).
  2. agentic-layer.md skill-table dedup: migrate pipeline-not-a-skill callout to skills-reference.md FIRST, replace L21 /pipeline → /overnight, drop tables, add top-of-file pointer.
  3. Stale-path fixes (5 sites: requirements/pipeline.md:130, CHANGELOG.md:21-22, scripts/validate-callgraph.py:12, skills/requirements/references/gather.md:201, backlog/133-…md:56).
  4. User-facing bash-runner sweep (skills/overnight/SKILL.md 6 sites including L198 line-citation drop, skills/diagnose/SKILL.md:62, docs/overnight.md:8, docs/agentic-layer.md L187/L313, docs/skills-reference.md L59/L71, docs/internals/sdk.md L179 — sdk.md is in docs/internals/ post-commit-1).
  5. docs/backlog.md "Global Deployment" cut + substantive migration to docs/plugin-development.md "## Adding a deployable bin script".
  **6a. `cortex dashboard` verb implementation** (Requirement 12a–12e): cli.py argparse + dispatcher + app.py L200/L226/L230 edits + tests/test_cli_dashboard.py + skills/overnight/SKILL.md PID probe update + plugin mirror regenerated + .gitignore + justfile recipe. **Test gate**: `pytest tests/test_cli_dashboard.py` MUST exit 0 before commit lands.
  **6b. `docs/dashboard.md` prose update** (Requirement 12f): only after 6a's tests pass. Splitting prevents the worse-than-no-change state where docs reference a non-existent command (per critical-review TL3 / R4F5). If 6a stalls, 6b does not land — better no doc update than docs pointing at broken behavior.
  7. docs/setup.md combined: trim (Requirement 6) AND additions (Requirement 5) in single setup.md commit. **MUST** land before commit 8 — under squash this is automatic; under merge-commit, the intermediate-commit invariant requires this ordering since commit 8's README cut deletes content that must already exist in setup.md.
  8. README.md rewrite (Requirements 1–4): cuts + pitch trim + Documentation index update (Authentication row, Upgrade & maintenance row, no internals rows). **Reviewer-reorder protection**: if a PR reviewer requests reordering 7 and 8, that reorder MUST be rejected — commit 8 unconditionally depends on commit 7's content existing in setup.md.

## Open Decisions

None remaining at spec time. Of the 7 open questions surfaced during research:
- 5 self-resolved during clarify→spec transition (overnight-operations.md carve-out; cli.py:268 canonical URL form; validate-callgraph.py:12 drop-citation-keep-rule; orchestrator-round.md prompt-strings out of scope; backlog/133 frontmatter no-audit-needed).
- 2 user-resolved via the §2 Spec interview (dashboard policy = Option 1 ship verb with XDG-compliant PID; README docs index for internals = drop internal-tier rows entirely).

Implementation can proceed to plan without further user-decision items.

---

**Verifiable greps** (acceptance signals — exhaustive, validated at PR review per Requirement-section acceptance criteria):
- `wc -l < README.md` ≤ 90.
- `grep -cE '^## (Authentication|What.s Inside|Customization|Distribution|Commands)$' README.md` = 0.
- `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' . --include='*' 2>/dev/null | grep -v 'lifecycle/archive\|research/\|backlog/'` = no live-source hits.
- `grep -rn 'bash runner\|bash overnight runner' docs/ skills/` = no hits.
- `grep -B2 'uv tool uninstall uv' docs/setup.md | grep -iE 'foot-gun|warning|do not|never|breaks'` ≥ 1.
- Each of `cortex overnight start`, `cortex overnight status`, `cortex init`, `cortex --print-root` present in `docs/setup.md`.
- `grep 'claude/reference/' requirements/pipeline.md scripts/validate-callgraph.py` = 0.
- `grep -E 'docs/install\.md|docs/migration-no-clone-install\.md' CHANGELOG.md` = 0.
- `wc -l < docs/agentic-layer.md` ≥ 40 lower than current 327 lines.
- `cortex dashboard --help` exits 0.
- `grep 'XDG_CACHE_HOME' cortex_command/cli.py` ≥ 1.
- `git diff plugins/cortex-core/bin/cortex-check-parity` shows only L59 change (or zero diff, if commit went through pre-commit hook).
