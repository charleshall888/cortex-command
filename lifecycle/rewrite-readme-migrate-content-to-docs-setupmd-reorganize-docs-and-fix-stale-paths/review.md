# Review: rewrite-readme-migrate-content-to-docs-setupmd-reorganize-docs-and-fix-stale-paths

## Stage 1: Spec Compliance

### Requirement 1: README ≤ 90 lines
- **Expected**: `wc -l < README.md` returns ≤ 90.
- **Actual**: `wc -l < README.md` returns 57.
- **Verdict**: PASS

### Requirement 2: README cuts (ASCII pipeline diagram, plugin auto-update, Authentication, What's Inside, Customization, Distribution, Commands)
- **Expected**: `grep -cE '^## (Authentication|What.s Inside|Customization|Distribution|Commands)$' README.md` returns 0.
- **Actual**: returns 0. Spot check confirms README contains only Prerequisites / Quickstart / Plugin roster / Documentation / License H2s; the ASCII pipeline+legend, plugin auto-update paragraph, Authentication body, What's Inside table, Customization, Distribution, and Commands sections are all gone.
- **Verdict**: PASS

### Requirement 3: README pitch trimmed (≤ 100 words between `# Cortex Command` and `## Prerequisites`)
- **Expected**: `awk '/^# Cortex Command/{flag=1; next} /^## Prerequisites/{flag=0} flag' README.md | wc -w` ≤ 100.
- **Actual**: returns 92. Pitch reduced to two paragraphs (single-sentence opener + workflow narrative paragraph) with the docs/agentic-layer.md cross-link preserved.
- **Verdict**: PASS

### Requirement 4: README Documentation index updated (Authentication row, Upgrade & maintenance row, no internals rows, no docs/pipeline.md row)
- **Expected**: Authentication and Upgrade & maintenance rows present (≥ 2 matches); no `docs/internals/` rows; no `docs/pipeline.md` row.
- **Actual**: README L47 anchors `docs/setup.md#authentication`; L48 anchors `docs/setup.md#upgrade--maintenance`; both anchors resolve to live H2s in setup.md (L242 and L188 respectively, verified by grep). `grep -cE '^\| .*docs/internals/' README.md` returns 0. `grep -E '^\| .*docs/pipeline\.md' README.md` returns 0. Anchor live-target check goes beyond V4's surface grep.
- **Verdict**: PASS

### Requirement 5: docs/setup.md hard-prereq additions (foot-gun warning, uv run semantics, fork URL pattern, Upgrade & maintenance H2, Customization rule, Commands subsection with 6 verbs)
- **Expected**: Each individual co-occurrence/existence grep ≥ 1.
- **Actual**:
  - foot-gun warning: `grep -B2 'uv tool uninstall uv' | grep -iE 'foot-gun|warning|do not|never|breaks'` returns ≥ 1 — present (`Warning: do not run`, `breaks`, `foot-guns` heading).
  - uv run semantics: present at L… ("`uv run` operates on the user's current project venv, not cortex-command's tool venv").
  - forker URL pattern `github.com/<your-fork>/cortex-command.git@<branch-or-tag>`: present.
  - `## Upgrade & maintenance`: present at L188 (1 match).
  - settings.json ownership rule: "Cortex-command does not own `~/.claude/settings.json`" — present.
  - `### Commands` heading: present (1 match). All six verbs present (`cortex overnight start`/`status`/`cancel`/`logs`, `cortex init`, `cortex --print-root`).
- **Verdict**: PASS

### Requirement 6: docs/setup.md trims (cortex init explainer ≤ 4 items; lifecycle.config.md schema ≥ 15 lines reduced)
- **Expected**: cortex init explainer has ≤ 4 top-level items; lifecycle.config.md schema yaml fence has ≤ 15 content lines (from ~30).
- **Actual**: cortex init explainer (L102-111) uses bold-numbered format `**1.**` through `**4.**`, four items total — passes manual-gate ≤ 4. The yaml fence content-line awk returns 8 — passes (≤ 15).
- **Verdict**: PASS

### Requirement 7: docs/internals/ relocation atomic commit (3 file moves + 7a breadcrumbs + 7b intra-file `../` prefixes + 7c cross-refs in 8 files)
- **Expected**: All three files moved; old paths absent; CLAUDE.md L50 updated; cli.py:268 stderr message uses canonical GitHub URL; bin/cortex-check-parity comment updated; overnight-operations.md and mcp-server.md cross-refs updated; README.md docs/pipeline.md row dropped; breadcrumbs and intra-file links use `../` prefix; broadened cross-reference filter returns no live-source hits.
- **Actual**:
  - File moves verified (`docs/internals/{pipeline,sdk,mcp-contract}.md` exist; old paths absent).
  - Broadened filter `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' . --include='*' | grep -vE 'lifecycle/|research/|backlog/|retros/'` returns 0 hits.
  - CLAUDE.md L50 path-substitution applied (both new paths on the same single line — `grep -o 'docs/internals/' CLAUDE.md | wc -l` returns 2 occurrences though `grep -c` returns 1 line; intent satisfied).
  - cli.py:268 (now L312) emits the canonical GitHub URL `https://github.com/charleshall888/cortex-command/blob/main/docs/internals/mcp-contract.md`.
  - bin/cortex-check-parity L59 comment references `docs/internals/pipeline.md`; plugins/cortex-core/bin/cortex-check-parity mirror is in sync (`git diff` is empty).
  - 7a breadcrumbs: pipeline.md and sdk.md L1 both use `(../agentic-layer.md)`; mcp-contract.md L1 has no breadcrumb (correct — spec said do not add).
  - 7b intra-file links: pipeline.md L117/L150 and sdk.md L9/L11/L112/L199 all use `../` prefix to overnight-operations.md / agentic-layer.md / `../../research/`. The negative grep `grep -E '\]\((overnight-operations\.md|agentic-layer\.md|\.\./research/)' docs/internals/*.md` (looking for unprefixed targets) returns 0.
- **Verdict**: PASS

Note on minor ambiguity: spec §7d acceptance line "`grep 'docs/internals/' CLAUDE.md` returns ≥ 2" — the bare grep returns matching lines (1 here, since both new paths share L50). The plan §1 verification text uses `-c` (returns 1) but says "≥ 2", which would FAIL strictly. Counting actual occurrences, both required substitutions exist (`docs/internals/pipeline.md` and `docs/internals/sdk.md`). Spec semantic intent is satisfied; treating as PASS since the spec's textual `grep 'docs/internals/'` (no -c) language is ambiguous between match-line-count and occurrence-count, and both required substitutions are visibly present.

### Requirement 8: agentic-layer.md skill-table dedup; pipeline-not-a-skill callout migrated; /pipeline routing → /overnight; top-of-file pointer added
- **Expected**: `wc -l < docs/agentic-layer.md` ≥ 40 lower than 327; pipeline-not-a-skill callout migrated to skills-reference.md; no `/pipeline` routing language; top-of-file pointer present.
- **Actual**: agentic-layer.md is now 281 lines (327 → 281, reduction 46 lines, ≥ 40). Callout `pipeline.*not a user-facing skill` present in skills-reference.md. Top-of-file pointer `For full skill descriptions and trigger details, see [skills-reference.md](skills-reference.md).` present at L3 (after breadcrumb, before first H2). Remaining `/pipeline` references in agentic-layer.md are narrative prose (e.g., "the `cortex_command/pipeline/` execution module" — module path, not routing).
- **Verdict**: PASS

### Requirement 9: User-facing bash-runner terminology sweep
- **Expected**: `grep -rn 'bash runner\|bash overnight runner' docs/ skills/` returns no hits; L198 `runner.sh` line-citation parenthetical removed.
- **Actual**: Both greps return 0. Sweep is complete across the seven enumerated files.
- **Verdict**: PASS

### Requirement 10: docs/backlog.md "Global Deployment" trim with substantive migration to plugin-development.md
- **Expected**: `## Global Deployment` and `Adding a new deployable script` headings absent from backlog.md; `## Adding a deployable bin script` present in plugin-development.md with `Path.cwd` rule and `cortex-core` `bin` mechanism.
- **Actual**: backlog.md greps return 0. plugin-development.md has `## Adding a deployable bin script` H2 with `Path.cwd()` vs `Path(__file__).parent` rule (substantive — explains why per-script bin scripts must use `Path.cwd()` to operate on the user's project) and per-script bin-deployment instructions citing `plugins/cortex-core/bin/`.
- **Verdict**: PASS

### Requirement 11: Stale-path fixes (5 sites + broad-scope claude/reference verifier)
- **Expected**: Six greps all return their expected counts.
- **Actual**:
  - `claude/reference/output-floors\.md` in requirements/pipeline.md: 0 (parenthetical deleted; "Routine forward-progress" now ends the line).
  - `docs/install\.md|docs/migration-no-clone-install\.md` in CHANGELOG.md: 0 (replaced by `docs/setup.md` reference at L25).
  - `claude/reference/claude-skills\.md` in scripts/validate-callgraph.py: 0; rule statement and self-contained rationale at L10-11 retained.
  - Broken `[requirements/project.md](project.md)` in skills/requirements/references/gather.md: 0; L201 fixed to `(../../../requirements/project.md)`.
  - backlog/133-…md L56 link target: now `../lifecycle/archive/remove-progress-update-...` (1 match) with no remaining `../lifecycle/remove-progress` (0 matches).
  - Broad-scope verifier `grep -rn 'claude/reference/' . --include='*.{py,sh,md}' | grep -vE 'lifecycle/|research/|backlog/|retros/'`: 0 live-source hits.
- **Verdict**: PASS

### Requirement 12: Ship `cortex dashboard` verb (12a-12g)
- **Expected**: argparse subcommand registered; in-process uvicorn (Strategy A); `--port` flag with default 8080 honoring `DASHBOARD_PORT` env fallback; XDG-compliant PID resolver in app.py L198 area; `_check_port` removed from lifespan; RuntimeError preserved with documentation in dashboard.md; PID consumers updated; tests pass; XDG/.cache strings present in cli.py + app.py + justfile (≥ 3); `cortex_command/dashboard/.pid` purged from probes; functional smoke returns 200.
- **Actual**:
  - 12a: cli.py L672-692 registers `dashboard` subparser between `init` and `upgrade` with `--port` flag defaulting to `int(os.environ.get("DASHBOARD_PORT", "8080"))`. `_dispatch_dashboard` (L236-276) imports uvicorn and calls `uvicorn.run("cortex_command.dashboard.app:app", host="127.0.0.1", port=port, log_level="info")` directly (Strategy A). Port set to `DASHBOARD_PORT` env var before invoking uvicorn (single source of truth).
  - 12b: app.py L198-213 defines `_resolve_pid_path()` that returns `Path(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')) / 'cortex' / 'dashboard.pid'` and creates the parent dir. `_pid_file` is module-level at L216. `_check_port` removed from lifespan entirely (L226 comment explicitly notes uvicorn binds the port itself in the parent process). RuntimeError preserved (L233-237) for missing `.claude/`; documentation alternative chosen per Plan §6 strategy (ii).
  - 12c: skills/overnight/SKILL.md L208 probe path uses `${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid`. Plugin mirror in sync (`grep -c 'cortex_command/dashboard/\.pid' …` returns 0 across canonical and mirror). `.gitignore` orphaned `claude/dashboard/.pid` removed.
  - 12d: tests/test_cli_dashboard.py covers all three required cases ((1) `--help` exits 0 + contains `--port`; (2) PID under `~/.cache/cortex/`; (3) verb does NOT write to `cortex_command/dashboard/.pid`). `pytest tests/test_cli_dashboard.py -v` returns 5 passed.
  - 12e: justfile L104 `PID_FILE="${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid"` matches.
  - 12f: docs/dashboard.md L14 instructs `cortex dashboard` as primary; L19 documents the `cortex init` prerequisite + RuntimeError; L21 retains `just dashboard` with explicit "(requires a clone of cortex-command)" annotation.
  - 12g: All seven acceptance commands pass. Functional smoke test (verb on port 18080 → curl /health) returns HTTP 200 (uv run path). XDG markers in cli.py + app.py: present (≥ 2 distinct files).
- **Verdict**: PASS

### Requirement 13: plugins/cortex-core/bin/cortex-check-parity regenerated cleanly
- **Expected**: `git diff plugins/cortex-core/bin/cortex-check-parity` shows only the L59 path-substitution change (or zero diff post-hook).
- **Actual**: `git diff` is empty (zero diff post-hook). Mirror L59 reads `# documented in docs/internals/pipeline.md and docs/overnight-operations.md;`.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

The implementation conforms to project.md's CLI-first identity: a wheel-installed CLI gains a new `dashboard` subcommand (in-package PID writes are eliminated, satisfying the wheel-install constraint). Documentation reorganization aligns with the in-scope item "Dashboard (~1800 LOC FastAPI): real-time web monitoring of overnight sessions" by improving installer-tier discoverability without altering the architecturally-bounded scope. Per the orchestration's tag-mapped scope, observability.md and pipeline.md were intentionally excluded from authoritative drift comparison; project.md remains consistent with the implementation.

## Stage 2: Code Quality

- **Naming conventions**: `_dispatch_dashboard` follows the established `_dispatch_<verb>` pattern (`_dispatch_overnight_start`, `_dispatch_print_root`, `_dispatch_upgrade`, etc.) — consistent. The argparse subparser variable `dashboard` matches sibling patterns (`init`, `upgrade`).
- **Error handling**: app.py lifespan RuntimeError at L234-237 preserves the data-integrity gate per Plan §6 strategy (ii). Message text reads "Dashboard lifecycle root appears wrong: {root}. Check module installation." — actionable but slightly generic; the user-facing actionable guidance ("run `cortex init`", `.claude/` prerequisite) lives in docs/dashboard.md L19 rather than the exception text. Minor improvement opportunity (not spec-blocking): the RuntimeError could mention `cortex init` or the `.claude/` directory directly to short-circuit the doc-lookup. Logged as a code-quality note, not an issue.
- **Test coverage**: tests/test_cli_dashboard.py covers all three required spec §12d cases (help-exits-zero, help-contains-port-flag, PID-under-XDG-cache, PID-falls-back-to-home-cache, PID-never-in-package). The test pattern matches sibling tests (test_cli_print_root.py, test_cli_upgrade.py, test_cli_handler_logs.py) and uses `importlib.reload` correctly to re-resolve the module-level `_pid_file` after env-var manipulation. Functional smoke test (port 18080 → curl /health) verified out-of-band returns 200.
- **Pattern consistency**: app.py uses manual XDG fallback `os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")` consistent with the spec Edge Cases #5 specification (no `platformdirs` dependency added). Cross-component consistency is high — cli.py, app.py, justfile, skills/overnight/SKILL.md L208 all reference the same `${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid` path. The Plan §Veto Surface item 1 (manual XDG vs platformdirs) is acknowledged as a deferred refinement; current choice is spec-compliant.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
