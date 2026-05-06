# Plan: rewrite-readme-migrate-content-to-docs-setupmd-reorganize-docs-and-fix-stale-paths

## Overview

Coordinated docs cleanup that ships repo-share-readiness for `cortex init` installers: relocate three internal docs to `docs/internals/`, dedup the skill-table, sweep bash-runner terminology drift, migrate Path.cwd-rule prose to plugin-development.md, ship a `cortex dashboard` verb with XDG-compliant PID, fix five stale-path residuals, expand setup.md with content currently in README, then aggressively trim README to ≤90 lines. Tasks are sequenced to honor the underlying invariant (every relocating-path edit lands in the same diff as the file move; setup.md content additions land before the README cut).

## Tasks

### Task 1: Relocate docs/{pipeline,sdk,mcp-contract}.md → docs/internals/ atomically with cross-refs

- **Files**:
  - `docs/pipeline.md` (git mv → `docs/internals/pipeline.md`; intra-file edits at L13/L117/L150)
  - `docs/sdk.md` (git mv → `docs/internals/sdk.md`; intra-file edits at L9/L11/L112/L199)
  - `docs/mcp-contract.md` (git mv → `docs/internals/mcp-contract.md`; no intra-file edits)
  - `CLAUDE.md` (L50 path-substitution: `docs/pipeline.md` → `docs/internals/pipeline.md`, `docs/sdk.md` → `docs/internals/sdk.md`)
  - `cortex_command/cli.py` (L268 stderr `docs/mcp-contract.md` → canonical GitHub URL `https://github.com/charleshall888/cortex-command/blob/main/docs/internals/mcp-contract.md`)
  - `bin/cortex-check-parity` (L59 comment: `docs/pipeline.md` → `docs/internals/pipeline.md`)
  - `docs/overnight-operations.md` (L318/L326/L339 `(sdk.md)` → `(internals/sdk.md)`; L593/L599 prose `docs/pipeline.md` → `docs/internals/pipeline.md`)
  - `docs/mcp-server.md` (L9 sibling refs: `pipeline.md` → `internals/pipeline.md`, `sdk.md` → `internals/sdk.md`)
  - `README.md` (L127 — drop the `docs/pipeline.md` Documentation-index row entirely; no internals row added per Q4 user decision)
- **What**: Move three pure-internal docs into `docs/internals/`, repoint every live cross-reference (CLAUDE.md, cli.py stderr, parity-script comment, overnight-operations.md, mcp-server.md, README.md index), and patch the breadcrumbs and intra-file relative links inside the moved files in the same commit. The pre-commit hook regenerates `plugins/cortex-core/bin/cortex-check-parity` automatically.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec §7 (full enumeration), §7a (breadcrumbs: pipeline.md+sdk.md L1 `(agentic-layer.md)` → `(../agentic-layer.md)`; mcp-contract.md has no breadcrumb), §7b (intra-file relative links must gain `../` since target is at `docs/`-root: pipeline.md L117/L150, sdk.md L9/L11/L112/L199; pipeline.md L13 `[SDK Integration](sdk.md)` is sibling-in-internals so requires NO edit), §7c (cross-refs in non-moving files), §7d (acceptance). Edge Cases #1 (atomic-landing — README.md:127 changes in *this* commit so no broken-cross-ref window). Edge Cases #2 (do NOT stage `plugins/cortex-core/bin/cortex-check-parity` manually — hook regenerates). Technical Constraints L207-208 (the binding invariant is "every relocating-path edit lands in the same diff as the file move"). Use `git mv` for the three moves so the rename is preserved in history.
- **Verification**: All five commands must hold post-task:
  - `[ -f docs/internals/pipeline.md ] && [ -f docs/internals/sdk.md ] && [ -f docs/internals/mcp-contract.md ] && [ ! -f docs/pipeline.md ] && [ ! -f docs/sdk.md ] && [ ! -f docs/mcp-contract.md ] && echo OK` returns "OK"
  - `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' . --include='*' 2>/dev/null | grep -vE 'lifecycle/|research/|backlog/|retros/'` returns no live-source hits — pass if 0 lines
  - `grep -c 'docs/internals/' CLAUDE.md` returns ≥ 2
  - `grep -c 'github\.com/charleshall888/cortex-command/blob/main/docs/internals/mcp-contract\.md' cortex_command/cli.py` returns 1
  - `grep -oE '\]\([^)]*(overnight-operations|agentic-layer|/research/)[^)]*\)' docs/internals/*.md | grep -v '\.\./'` returns no hits (per-match extraction via `-o`: each markdown link target is checked independently, so a missed `../` prefix on one link is not hidden by a properly-prefixed link on the same line — catches a missed L117/L150/L9/L11/L112/L199 prefix edit)
- **Status**: [x] completed

### Task 2: Dedup skill-inventory table from agentic-layer.md; migrate pipeline-not-a-skill callout to skills-reference.md

- **Files**:
  - `docs/skills-reference.md` (insert pipeline-not-a-skill callout migrated verbatim from `docs/agentic-layer.md:64`)
  - `docs/agentic-layer.md` (remove skill-inventory tables L17–62 across Development Workflow / Code Quality / Thinking Tools / Session Management / Utilities groupings; replace L21 dev-row `/pipeline` routing language with `/overnight`; add top-of-file pointer `For full skill descriptions and trigger details, see [skills-reference.md](skills-reference.md).` positioned after the breadcrumb / before the first H2; remove the L64 callout AFTER it has been migrated to skills-reference.md)
- **What**: Migrate the pipeline-not-a-skill callout to `skills-reference.md` first (so no information is lost), then trim `agentic-layer.md` skill tables, fix the `/pipeline` routing slip, and add a one-line cross-pointer so trim-affected workflow narrative readers can find skill triggers.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec §8. agentic-layer.md is currently 327 lines; target reduction ≥ 40 lines. Edge Cases #8 (trim breaks workflow narrative skill-by-name references — top-of-file pointer is the mitigation). The pipeline-not-a-skill callout body at agentic-layer.md:64 reads "pipeline is not a user-facing skill and has no entry in skills/. It is an internal Python orchestration module..." — migrate this verbatim into a similar position in skills-reference.md (e.g., near the top or under a "Not a skill" disclaimer).
- **Verification**: All four must hold post-task:
  - `wc -l < docs/agentic-layer.md` returns ≤ 287 — pass if `[ $(wc -l < docs/agentic-layer.md) -le 287 ]`
  - `grep -c 'pipeline.*not a user-facing skill' docs/skills-reference.md` returns 1
  - `grep -c '\[skills-reference\.md\](skills-reference\.md)' docs/agentic-layer.md` returns ≥ 1
  - `grep -cE '^\|.*/pipeline' docs/agentic-layer.md` returns 0 (no markdown table row uses `/pipeline` as the trigger column — the L21 dev-row routing language is gone; remaining `/pipeline` mentions, if any, are non-table narrative prose)
- **Status**: [x] completed

### Task 3: Fix five stale-path residuals

- **Files**:
  - `requirements/pipeline.md` (L130: delete the parenthetical `(Convention defined in claude/reference/output-floors.md; enforcement requires orchestrator prompt changes.)`. Final wording ends at "Routine forward-progress decisions do not require this field.")
  - `CHANGELOG.md` (L21–22: replace the two bullets promising `docs/install.md` and `docs/migration-no-clone-install.md` with a single bullet pointing at `docs/setup.md` as the canonical install/upgrade reference)
  - `scripts/validate-callgraph.py` (L12: drop the sentence `See claude/reference/claude-skills.md "Common Mistakes" row 303.`. Keep the rule statement and self-contained rationale on lines 10–11.)
  - `skills/requirements/references/gather.md` (L201: fix broken relative link `[requirements/project.md](project.md)` → `[requirements/project.md](../../../requirements/project.md)`)
  - `backlog/133-evaluate-implementmd180-progress-tail-narration-under-opus-47.md` (L56: insert `archive/` segment in the markdown link target so display text and target agree — final form `[lifecycle/archive/...](../lifecycle/archive/remove-progress-update-scaffolding-from-long-running-prompts-dr-3-wave-1/research.md)`)
- **What**: Five small, mechanical path/citation fixes resolving post-#117/#148 residuals.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec §11. Edge Cases #9 (backlog/133 is `status: complete` but body edits are not policy-blocked; frontmatter unaffected — verified `lifecycle_slug` not present, `spec:` points at a different slug). Edge Cases #10 (CHANGELOG broken-ref convention permits typo-style replace).
- **Verification**: All six must hold post-task:
  - `grep -c 'claude/reference/output-floors\.md' requirements/pipeline.md` returns 0
  - `grep -cE 'docs/install\.md|docs/migration-no-clone-install\.md' CHANGELOG.md` returns 0
  - `grep -c 'claude/reference/claude-skills\.md' scripts/validate-callgraph.py` returns 0
  - `grep -c '\[requirements/project\.md\](project\.md)' skills/requirements/references/gather.md` returns 0
  - `grep -c '\.\./lifecycle/remove-progress' backlog/133-*.md` returns 0 AND `grep -c '\.\./lifecycle/archive/remove-progress' backlog/133-*.md` returns 1
  - `grep -rn 'claude/reference/' . --include='*.py' --include='*.sh' --include='*.md' 2>/dev/null | grep -vE 'lifecycle/|research/|backlog/|retros/'` returns no live-source hits (broad-scope verifier per spec L98)
- **Status**: [x] completed

### Task 4: User-facing bash-runner terminology sweep

- **Files**:
  - `skills/overnight/SKILL.md` (L3 description, L22 body, L391, L400, L401: "bash runner" → "runner" or context-appropriate equivalent; L198: drop the parenthetical `(line 179 of `runner.sh`)` entirely — preserve surrounding text; do NOT replace with a `runner.py:N` citation per spec rationale on line-number rot)
  - `skills/diagnose/SKILL.md` (L62: "bash runner" → "runner")
  - `docs/overnight.md` (L8: "launch a bash runner" → "launch the runner")
  - `docs/agentic-layer.md` (L187: "a bash runner detaches in a tmux session" → "the runner detaches in a tmux session"; L313: "The bash overnight runner writes execution state" → "The overnight runner writes execution state")
  - `docs/skills-reference.md` (L59 and L71: "bash runner" → "runner")
  - `docs/internals/sdk.md` (post-Task-1 path; was `docs/sdk.md:179`: `runner.sh` → "the runner" or context-appropriate equivalent)
- **What**: Strip "bash runner" / "bash overnight runner" / `runner.sh` line-citation drift from user-facing skills and docs. The bash entrypoint `runner.sh` no longer exists; the runner is `cortex_command/overnight/runner.py` invoked via `cortex overnight start`.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Spec §9. The 7-file size is a thematic-sweep constraint (one logical operation across all user-facing surfaces); splitting by file would create cross-task coupling without separable verification. Plugin mirrors regenerate via `just build-plugin` from canonical `skills/` sources. Non-Requirements explicitly carve out: `cortex_command/overnight/*.py` port-provenance comments (~30+), `cortex_command/overnight/prompts/orchestrator-round.md` runtime narration, `tests/` docstrings (3 occurrences), and `docs/overnight-operations.md` `runner.sh` mentions (operator-vocabulary glossary; the `bash runner` grep pattern mechanically excludes them). Re-grep one final time before commit to catch any drift the line-cited list missed (`grep -rn 'bash runner\|bash overnight runner' docs/ skills/`).
- **Verification**: 
  - `grep -rn 'bash runner\|bash overnight runner' docs/ skills/` returns no hits — pass if 0 lines of output
  - `grep -c 'line 179 of \`runner\.sh\`' skills/overnight/SKILL.md` returns 0 (parenthetical removed)
- **Status**: [x] completed

### Task 5: Cut docs/backlog.md "Global Deployment" section; migrate Path.cwd rule + bin-deployment mechanism to plugin-development.md

- **Files**:
  - `docs/plugin-development.md` (insert new `## Adding a deployable bin script` section after the current `## Iterating on plugin source` section L96–105. Body must include: (a) `Path.cwd()` vs `Path(__file__).parent` rule for repo-local dirs — explicit guidance that per-script bin scripts must use `Path.cwd()` so they operate on the user's project, not cortex-command itself; (b) per-script bin-deployment mechanism — how a script gets exposed via the cortex-core plugin's `bin/` directory)
  - `docs/backlog.md` (cut entire L198–234: heading L198 "Global Deployment", subsections "Adding a new deployable script" L202, PATH-resolution L208, Path.cwd() rule L218, currently-deployed-scripts table L228–233. Drop the 3-row currently-deployed-scripts table — drift-prone, replaceable by `ls plugins/cortex-core/bin/`.)
- **What**: Migrate substantive rules (Path.cwd, per-script bin deployment) to `docs/plugin-development.md` BEFORE cutting from `docs/backlog.md`, so no architectural rule is lost. Drop the currently-deployed-scripts table entirely.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec §10. Round-2 critical-review caught that this is NOT a clean delete — `plugin-development.md` did not previously cover the Path.cwd rule or per-script bin-deployment mechanism. Both are load-bearing for anyone adding a deployable script; substantive migration is required.
- **Verification**: All four must hold post-task:
  - `grep -cE '^## Global Deployment|Adding a new deployable script' docs/backlog.md` returns 0
  - `grep -c '^## Adding a deployable bin script' docs/plugin-development.md` returns 1
  - `grep -cE 'Path\.cwd|Path\(__file__\)' docs/plugin-development.md` returns ≥ 1
  - `grep 'cortex-core' docs/plugin-development.md | grep -ci 'bin'` returns ≥ 1
- **Status**: [x] completed

### Task 6: Implement `cortex dashboard` subcommand with XDG-compliant PID

- **Files**:
  - `cortex_command/cli.py` (add argparse `subparsers.add_parser("dashboard", help="Launch the dashboard web UI on localhost", ...)` between existing `init` (L600 area) and `upgrade` (L628 area); add `_dispatch_dashboard` handler using **strategy (A) in-process uvicorn** — `uvicorn.run("cortex_command.dashboard.app:app", host=..., port=..., log_level=...)`; add `--port <int>` flag with default 8080; honor `DASHBOARD_PORT` env var as fallback before defaulting; resolve PID-file path via the shared resolver introduced in `app.py` below and pass the chosen port to `app.py` via env var so verb's `--port` is the single source of truth)
  - `cortex_command/dashboard/app.py` (L200: replace `_pid_file = Path(__file__).parent / ".pid"` with `_pid_file = _resolve_pid_path()` where the resolver returns `Path(os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))) / 'cortex' / 'dashboard.pid'` and creates the parent directory if missing; L226: **REMOVE** the `_check_port(...)` call from the lifespan entirely under Strategy A — uvicorn binds the port itself in the parent process before the lifespan runs, so a lifespan-time `socket.bind()` collides with uvicorn's already-held socket and exits 1 on every start; uvicorn's own port-binding error handling surfaces a clean message if the port is occupied. If a pre-bind availability check is desired, perform it in `cli.py` *before* `uvicorn.run()` (try-bind a socket, close, then call uvicorn). L230 lifespan precondition: **KEEP the `RuntimeError`** unchanged — the `.claude/` check is a data-integrity gate (not just a UX gate) that protects `run_polling`'s four background tasks from reading non-existent paths under `lifecycle/` when the CWD has only `lifecycle/` or `backlog/` but no cortex registration. The prerequisite is documented in Task 7's `docs/dashboard.md` update instead.)
  - `tests/test_cli_dashboard.py` (NEW; pattern: `tests/test_cli_print_root.py`, `tests/test_cli_upgrade.py`, `tests/test_cli_handler_logs.py`. Three required test cases: (1) `cortex dashboard --help` exits 0 and contains `--port`; (2) PID-file location resolves under `~/.cache/cortex/` (or platform equivalent honoring `XDG_CACHE_HOME`); (3) verb does NOT write to `cortex_command/dashboard/.pid` under any condition)
  - `skills/overnight/SKILL.md` (L208: probe path `cortex_command/dashboard/.pid` → resolver matching app.py — either `${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid` literal or a documented Python helper invocation)
  - `.gitignore` (L30 `claude/dashboard/.pid` entry: remove if orphaned by prior cleanup; verify whether `cortex_command/dashboard/.pid` was previously gitignored and clean up consistently — plan-phase decision: remove the orphaned line)
  - `justfile` (L100–113 `dashboard` recipe: update `PID_FILE` at L104 to write to the same XDG-compliant location for consistency. Optional simplification: replace the recipe body with `cortex dashboard "$@"` once the verb ships, leaving the recipe as a one-line shim for contributor-clone use)
- **What**: Ship the `cortex dashboard` verb with a portable PID-file location consistent across the verb, the FastAPI app, and the SKILL.md liveness probe. Strategy (A) in-process uvicorn avoids `uv run` subshell ambiguity and orphaned-subprocess risks. The XDG-with-`~/.cache`-fallback resolver is consistent across all readers (no `platformdirs` dependency added — manual XDG is the spec-allowed fallback per Edge Cases #5; macOS-native `~/Library/Caches/` would be primary if `platformdirs` were used, see Veto Surface item 1).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec §12 (full requirements §12a–§12g). Strategy (A) is mandated unless infeasible — wheel install layout makes (A) trivially feasible since the package itself can be imported. Edge Cases #3 (wheel install dashboard PID write); Edge Cases #4 (systems without `~/.cache` — the `os.path.expanduser('~/.cache')` fallback creates the dir if missing). Edge Cases #5 (macOS native cache convention — manual XDG resolver is acceptable on macOS per spec). Pyproject deps already include `fastapi`, `uvicorn[standard]`, `jinja2` at `pyproject.toml:11–13`. **Wiring co-location**: cli.py's new dispatcher is consumed by tests/test_cli_dashboard.py (same task), skills/overnight/SKILL.md L208 PID probe (same task), and justfile (same task). **Non-applicable**: parity W003 ("orphan: deployed but not referenced") does not apply here — `cortex dashboard` is an argparse subcommand inside `cli.py`, not a standalone `bin/cortex-*` script.
- **Verification**: All six must hold post-task:
  - `cortex dashboard --help` exits 0 and stdout contains `--port` — pass if `cortex dashboard --help 2>&1 | grep -c -- '--port'` returns ≥ 1 AND exit code is 0
  - `pytest tests/test_cli_dashboard.py -v` exits 0
  - `grep -cE 'XDG_CACHE_HOME|\.cache/cortex' cortex_command/cli.py cortex_command/dashboard/app.py justfile` returns ≥ 3 (justfile recipe must use the same XDG path so contributor `just dashboard` and verb `cortex dashboard` write to the same PID location — prevents drift between SKILL.md probe and recipe-launched dashboard)
  - `grep -c 'cortex_command/dashboard/\.pid' skills/overnight/SKILL.md plugins/cortex-overnight/skills/overnight/SKILL.md` returns 0 (old PID path purged from all probe call sites; plugin mirror regenerated by hook)
  - **Functional smoke (full form, NOT reducible per spec R3F3)**: `cortex dashboard --port 18080 & CHILD_PID=$!; sleep 3; HTTP_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:18080/health); kill $CHILD_PID 2>/dev/null; wait $CHILD_PID 2>/dev/null; echo "$HTTP_STATUS"` prints `200`
  - `git diff plugins/cortex-overnight/skills/overnight/SKILL.md` after `just build-plugin` regeneration shows only the L208 PID-path delta (or zero diff if commit went through pre-commit hook)
- **Status**: [x] completed

### Task 7: Update docs/dashboard.md prose to instruct `cortex dashboard` as primary; document `cortex init` prerequisite

- **Files**:
  - `docs/dashboard.md` (L14: replace `just dashboard` instruction with `cortex dashboard` as primary; keep `just dashboard` as contributor-clone path with explicit `(requires a clone of cortex-command)` annotation. Add a brief prerequisite note near the verb instruction: `cortex dashboard` requires a cortex-registered project — run `cortex init` once in your project before launching the dashboard, or set `CORTEX_REPO_ROOT` to point at a registered project. The verb fails with a `RuntimeError` if `.claude/` is not present in the resolved root.)
- **What**: Update the dashboard doc to point installers at the new verb and document the `.claude/` prerequisite that the lifespan precondition (Task 6, kept unchanged) enforces. Splitting this from Task 6 (per spec §6b) prevents the worse-than-no-change state where docs reference a non-existent verb if Task 6 stalls.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Spec §12f. Spec L217 explicitly enforces: "If 6a stalls, 6b does not land — better no doc update than docs pointing at broken behavior." The `cortex init` prerequisite documentation is the alternative spec §12b L230 outcome (the plan retains the hard `RuntimeError` instead of downgrading per critical-review R3F2 — silent data-corruption risk if the polling loop runs against an unregistered root).
- **Verification**: All three must hold post-task:
  - `grep -c 'cortex dashboard' docs/dashboard.md` returns ≥ 1
  - `grep -ci 'requires a clone' docs/dashboard.md` returns ≥ 1
  - `grep -c 'cortex init' docs/dashboard.md` returns ≥ 1 AND `grep -ciE '\.claude|prerequisite|register' docs/dashboard.md` returns ≥ 1 (prerequisite documented)
- **Status**: [x] completed

### Task 8: Trim and expand docs/setup.md (hard prerequisite for README rewrite)

- **Files**:
  - `docs/setup.md` (multi-section edit:
    - Trim `cortex init` 7-step explainer (current L107–128) to ≤ 4 top-level numbered items
    - Compress `lifecycle.config.md` schema block (current L130–160, 30 lines) by ≥ 15 lines into a brief reference-card form
    - Add `uv tool uninstall uv` foot-gun warning with co-occurring caution context (e.g., a "Warning:" or "Do not run …" prose line within 2 lines of the `uv tool uninstall uv` string)
    - Add `uv run` user-project semantics note (e.g., "uv run operates on the user's current project venv, not cortex-command's tool venv") within ≤ 3 lines of any `uv run` mention
    - Add forker fork-install URL pattern: `uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>` (distinguished from upstream main pattern)
    - Elevate the current `#### Upgrading` subsection at L40–47 (under "Install the cortex CLI") to a top-level `## Upgrade & maintenance` section. Body absorbs both the MCP-driven path (`/plugin update cortex-overnight@cortex-command`) and the bare-shell path (`uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@v0.1.0`).
    - Add Customization content (settings.json ownership rule) carried verbatim or substantively from current `README.md` L89–91 — must include the rule "cortex-command does not own settings.json" or equivalent
    - Add a Commands subsection (`### Commands` or `## Commands`) listing each cortex CLI subcommand per spec §5: `cortex overnight start`, `cortex overnight status`, `cortex overnight cancel`, `cortex overnight logs`, `cortex init`, `cortex --print-root`. Do NOT list `cortex dashboard` here — its presence in setup.md is decoupled from Task 8 to honor spec §6a/§6b's "If 6a stalls, 6b does not land" partition; users discover the verb via `cortex --help` and `docs/dashboard.md` (Task 7).
    - Verify Troubleshooting section at L49–53 covers `cortex: command not found` AND `cortex --print-root` as verify-install command (these may already exist; only edit if missing))
- **What**: Single-file substantial edit that (a) trims two over-long sections per spec §6 and (b) imports content currently above-fold in README.md (Customization, Distribution, Commands, Upgrade-related notes) per spec §5. This must land BEFORE Task 9 — the README cut deletes content that must already exist in setup.md (DR-1 hard prerequisite). Does NOT depend on Task 6 — the Commands subsection lists only spec §5's six commands, not `cortex dashboard`, so Task 6 stall does not propagate to Task 8 or Task 9.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec §5 (hard-prereq additions), §6 (trims), Technical Constraints L197 (DR-1). Edge Cases #6 (acceptance grep collision in code blocks: use co-occurrence checks on the `uv tool uninstall uv` warning, not bare existence). Edge Cases #11 (forker fork-URL pattern collides with main-URL pattern — setup.md's Upgrade & maintenance section presents both as alternatives). Decoupled from Task 6 per critical-review R4F1 — listing `cortex dashboard` in setup.md would re-introduce the spec §6a/§6b coupling that the spec partition was designed to prevent.
- **Verification**: All nine must hold post-task:
  - `grep -B2 'uv tool uninstall uv' docs/setup.md | grep -ciE 'foot-gun|warning|do not|never|breaks'` returns ≥ 1
  - `grep -A3 -B1 'uv run' docs/setup.md | grep -ciE "user.s.*project|own project|own venv|operates on"` returns ≥ 1
  - `grep -c 'github\.com/<your-fork>' docs/setup.md` returns ≥ 1
  - `grep -cE '^## Upgrade' docs/setup.md` returns 1
  - `grep -ciE 'cortex-command does not own.*settings\.json|do not own.*settings\.json' docs/setup.md` returns ≥ 1
  - `grep -cE '^### Commands|^## Commands' docs/setup.md` returns ≥ 1
  - For each S in `cortex overnight start` `cortex overnight status` `cortex overnight cancel` `cortex overnight logs` `cortex init` `cortex --print-root`: `grep -c "$S" docs/setup.md` returns ≥ 1 (six commands per spec §5; `cortex dashboard` is intentionally excluded — Task 7 documents it in `docs/dashboard.md`)
  - **Interactive/session-dependent**: cortex-init explainer trim verified by manual diff review — the implementer is free to rename the section heading or use either plain-numbered (`1.`) or bold-numbered (`**1.**`) list format, both of which prevent a robust automated count without false positives or false negatives. Manual gate: post-edit cortex-init explainer has ≤ 4 numbered items.
  - `awk '/lifecycle\.config\.md/{near=1} near && /^```yaml$/{start=NR; next} start && /^```$/{print NR-start-1; exit}' docs/setup.md` returns ≤ 15 (count of content lines INSIDE the lifecycle.config.md schema yaml fence — pre-edit returns ~30 per spec §6; post-edit must be ≤ 15)
- **Status**: [x] completed

### Task 9: Rewrite README.md (cut to ≤ 90 lines, expand Documentation index)

- **Files**:
  - `README.md` (full rewrite per spec §1–§4:
    - **Cut** in entirety: ASCII pipeline diagram + tier/criticality legend (current L11–29); plugin auto-update mechanics paragraph + extras-tier callout (current L52–54); Authentication H2 + body (L73–75); What's Inside table + body (L77–88); Customization H2 + body (L89–91); Distribution H2 + body (L93–100); Commands H2 + body (L102–115)
    - **Trim** pitch: drop distribution-mechanics blur from current paragraph 3 (L7); keep workflow narrative paragraph (current L9). Final pitch (lines from `# Cortex Command` to before `## Prerequisites`) ≤ 100 words
    - **Keep** with minor trim: title + 1-paragraph pitch; workflow narrative; Prerequisites; Quickstart 3-step block; Plugin roster table (trim header/footer prose, keep table); Verification pointer; License
    - **Documentation index update**: add an Authentication row pointing at `docs/setup.md#authentication`; add an Upgrade & maintenance row pointing at `docs/setup.md#upgrade--maintenance`; the `docs/pipeline.md` row was already dropped in Task 1 (no internals row added — internals are findable via in-doc cross-references in CLAUDE.md L50, mcp-server.md, agentic-layer.md))
- **What**: Apply the aggressive README rewrite. The cut removes ~50–60 lines; the Documentation index grows by 2 rows. Final target: ≤ 90 lines, ≤ 100-word pitch.
- **Depends on**: [1, 8]
- **Complexity**: complex
- **Context**: Spec §1 (≤ 90 lines), §2 (cut sections), §3 (pitch), §4 (Documentation index). Task 1 already dropped the `docs/pipeline.md` Documentation-index row (atomic-landing requirement). Task 8 supplies the destination content for Customization, Distribution, Commands, Upgrade & maintenance. Edge Cases #7 (README leftover content backstop: PR-review checklist will manually diff-check that no rule-statement string from the cut sections — e.g., "cortex-command does not own", "uv tool uninstall uv" — appears in BOTH setup.md AND README.md post-cut). Reviewer-reorder protection (spec L219): if a PR reviewer requests reordering Task 8 and Task 9, that reorder MUST be rejected.
- **Verification**: All seven must hold post-task:
  - `wc -l < README.md` returns ≤ 90 — pass if `[ $(wc -l < README.md) -le 90 ]`
  - `grep -cE '^## (Authentication|What.s Inside|Customization|Distribution|Commands)$' README.md` returns 0
  - `awk '/^# Cortex Command/{flag=1; next} /^## Prerequisites/{flag=0} flag' README.md | wc -w` returns ≤ 100 — pass if `[ $(awk … | wc -w) -le 100 ]`
  - `awk '/^## Documentation/{flag=1; next} flag && /^## /{flag=0} flag' README.md | grep -cE 'Authentication|Upgrade.*maintenance'` returns ≥ 2 (matches confined to the Documentation index section — flag-based extraction skips the heading line itself and stops at the next H2; if Documentation is the LAST H2 the rest of the file is included, but Authentication/Upgrade rows are unique to the Documentation index by spec §4)
  - `grep -cE '^\| .*docs/internals/' README.md` returns 0 (no internals rows in Documentation index per Q4 user decision)
  - `grep -cE '^\| .*docs/pipeline\.md' README.md` returns 0 (pipeline.md row already dropped in Task 1; sanity check that nothing re-introduced it)
  - `grep -ciE 'cortex-command does not own' README.md` returns 0 (Customization rule purged from README — sanity check Edge Cases #7 backstop)
- **Status**: [x] completed

### Task 10: Final-state verification sweep

- **Files**: none (verification-only; no edits — final acceptance gate before PR submission)
- **What**: Run the full Verifiable greps suite from spec L231–L243 plus the intermediate-commit invariant checks (parity exit, clean working tree). This task is the final pre-PR gate — if any verifier fails, fix the prior task and re-run this sweep.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9]
- **Complexity**: simple
- **Context**: Spec L231–L243 (Verifiable greps — exhaustive). Technical Constraints L209 (intermediate-commit invariant: `git status` clean, `bin/cortex-check-parity` exits 0). All Task 8 required commands now appear in this sweep (R4F5 closure).
- **Verification**: All thirteen must hold:
  - `[ $(wc -l < README.md) -le 90 ]` — exit 0
  - `grep -cE '^## (Authentication|What.s Inside|Customization|Distribution|Commands)$' README.md` returns 0
  - `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' . --include='*' 2>/dev/null | grep -vE 'lifecycle/|research/|backlog/|retros/'` returns no live-source hits
  - `grep -rn 'bash runner\|bash overnight runner' docs/ skills/` returns no hits
  - `grep -B2 'uv tool uninstall uv' docs/setup.md | grep -ciE 'foot-gun|warning|do not|never|breaks'` returns ≥ 1
  - For each S in `cortex overnight start` `cortex overnight status` `cortex overnight cancel` `cortex overnight logs` `cortex init` `cortex --print-root`: `grep -c "$S" docs/setup.md` returns ≥ 1 (six spec §5 commands; full coverage of Task 8's required Commands list per critical-review R4F5)
  - `grep -c 'claude/reference/' requirements/pipeline.md scripts/validate-callgraph.py` returns 0
  - `grep -cE 'docs/install\.md|docs/migration-no-clone-install\.md' CHANGELOG.md` returns 0
  - `[ $(wc -l < docs/agentic-layer.md) -le 287 ]` — exit 0
  - `cortex dashboard --help` exits 0 AND functional curl smoke passes: `cortex dashboard --port 18080 & CHILD_PID=$!; sleep 3; HTTP_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:18080/health); kill $CHILD_PID 2>/dev/null; wait $CHILD_PID 2>/dev/null; [ "$HTTP_STATUS" = "200" ]` — exit 0 (catches a Task-6 lifespan-bind regression that `--help` alone misses, per critical-review R3F6; requires a cortex-registered project as CWD or `CORTEX_REPO_ROOT` set)
  - `grep -c 'XDG_CACHE_HOME' cortex_command/cli.py` returns ≥ 1
  - `grep -c 'cortex dashboard' docs/dashboard.md` returns ≥ 1 (Task 7 doc update landed)
  - `bin/cortex-check-parity` exits 0; `git diff plugins/cortex-core/bin/cortex-check-parity` shows only the L59 path-substitution change (or zero diff if commits all went through the pre-commit hook)
- **Status**: [x] completed

## Verification Strategy

End-to-end validation has three layers:

1. **Per-task verification** as listed in each task's Verification field — runs immediately after the task's commit lands.
2. **Intermediate-commit invariant** (Technical Constraints L209, extended per critical-review R1F2): every commit on the PR branch must satisfy (a) clean working tree post-commit; (b) no untracked source files; (c) `bin/cortex-check-parity` exits 0; (d) **starting from commit 1 onward**, `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' . --include='*' 2>/dev/null | grep -vE 'lifecycle/|research/|backlog/|retros/'` returns no live-source hits — this catches the missed-cross-ref failure mode that (a)–(c) do not detect; the parity script is unrelated to docs cross-references. Tests are NOT required to pass at every intermediate commit (the Task 4 bash-runner sweep may transiently break test docstrings) but the build-plugin hook must pass.
3. **Final-state sweep** (Task 10): runs all spec L231–L243 Verifiable greps plus a `cortex dashboard --help` smoke and parity check before PR submission.

End-to-end smoke for the dashboard verb (per spec Requirement 12g):

```
cortex dashboard --port 18080 &
CHILD_PID=$!
sleep 3
HTTP_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:18080/health)
kill $CHILD_PID 2>/dev/null
wait $CHILD_PID 2>/dev/null
echo "$HTTP_STATUS"  # expect: 200
```

This is the full-form smoke; the previous reduced "exits 0 within 5s" form was deleted from spec because a verb that fails to bind a port can satisfy it while serving zero requests.

## Veto Surface

Three plan-phase calls the user might want to revisit before implementation:

1. **Dashboard PID-file resolver: manual XDG vs `platformdirs` library.** Plan picked manual XDG (`os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache')) / 'cortex' / 'dashboard.pid'`) over the `platformdirs` library because (a) it adds no new dependency, (b) it is the spec-allowed fallback per Edge Cases #5 ("`~/.cache/cortex/dashboard.pid` fallback is acceptable on macOS as long as the chosen path is consistent across all PID readers"), (c) it can be replaced with platformdirs in a follow-up if drift becomes an issue. **Tradeoff acknowledged** (per critical-review R3F3): per requirements/project.md L34 ("macOS — primary supported platform") and spec Edge Cases #5, the platform-native cache is `~/Library/Caches/` on macOS. The plan's choice prioritizes dependency minimalism over platform convention; switching to `platformdirs.user_cache_dir('cortex')` is a one-line swap that would honor the macOS-primary platform preference more cleanly. Recommend keeping manual XDG; user may override.

2. **Dashboard lifespan precondition: keep RuntimeError + document, or downgrade.** Spec §12b L230 mandates one of two outcomes: (i) downgrade the `if not (root / ".claude").exists(): raise RuntimeError(...)` to a printed warning + `cortex init`-suggestion, OR (ii) keep the hard error and document the prerequisite in `docs/dashboard.md`. **Plan picked (ii)** per critical-review R3F2 — the `.claude/` check is a data-integrity gate, not a UX gate; downgrading routes `run_polling`'s four background tasks at unverified roots and exposes silent data corruption (200 from `/health` while the dashboard renders empty/stale state). Task 7 documents the prerequisite in `docs/dashboard.md`. The dashboard becomes a "post-init only" tool, which is more restrictive but also more predictable.

3. **Task ordering under merge-commit vs squash-merge.** Plan sequences Task 8 (setup.md) before Task 9 (README cut) per spec §7 8-commit topology. Spec L219 declares that reordering Task 8 and Task 9 "MUST be rejected" — but enforcement is operator/reviewer discipline only (per critical-review R4F6: spec Non-Requirements explicitly disclaim a pre-commit hook for hard-prereq enforcement; no CI workflow gates it). Under squash-merge integration, the 8-commit sequence collapses to one main-branch commit and ordering is automatic; under merge-commit, intermediate-commit ordering matters and is enforced by reviewer judgment + the extended intermediate-commit invariant (Verification Strategy §2 item d). Recommend confirming squash-merge as the intended integration strategy if available; if not, the residual reviewer-discipline risk is acknowledged. Per critical-review R1F1 the recovery-clause language inherited from spec L211 is squash-flavored — under merge-commit the recovery commit 1.5 cannot retroactively make commit 1 atomic, so a missed sub-edit would leave a real broken-cross-ref window on `main`. The extended intermediate-commit invariant (item d) detects this post-hoc on each commit.

## Scope Boundaries

Per spec Non-Requirements (lines 140–155):

- **No edit to `requirements/project.md:7`** audience language (F-12 dropped post-critical-review).
- **No DR-2 visibility cleanup** (`.gitignore`-hide / `.cortex/` relocation). Deferred per DR-2 = Option C.
- **No code/script/hook deletion** — child #168 owns this.
- **No lifecycle/research archive sweep** — child #169 owns this.
- **No new MUST/CRITICAL/REQUIRED escalations** added to CLAUDE.md, skills/, or hooks/. Body's "must" usage in this plan is descriptive prerequisite/acceptance language, not normative directive added to runtime files.
- **No sweep of `cortex_command/overnight/*.py` port-provenance comments** (~30+ "Mirrors `runner.sh:N`" comments). Out of #166 user-facing scope.
- **No sweep of `cortex_command/overnight/prompts/orchestrator-round.md` runtime prompt strings** (L8/L20/L486 "bash runner will invoke"). Out of #166 user-facing scope.
- **No sweep edit to `docs/overnight-operations.md`** for `runner.sh` mentions (23 occurrences). Doc owns runner round-loop content per CLAUDE.md:50; carve-out documented in spec.
- **No sweep of `tests/` bash-runner mentions** (3 occurrences). Tests are contributor-tier source, not part of installer-audience share-readiness.
- **No subtable for internals docs** in README Documentation index (per user Q4 decision). Pipeline.md row dropped entirely.
- **No new pre-commit hook** for hard-prereq enforcement. Plan-phase commit ordering plus PR-review acceptance-grep checklist suffice.
- **No programmatic skill-table generator.** Defer to follow-on if drift recurs.
- **No frontmatter audit on backlog/133.** Body-link fix is sufficient.
- **No release-process.md or plugin-development.md relocation to docs/internals/.** DR-3 = Option B keeps these at `docs/` root.
