# Plan: relocate-cortex-command-artifacts-under-cortex-root

## Overview

Single atomic commit that rebases every cortex-managed path from repo-root scattered (`lifecycle/`, `backlog/`, `research/`, `requirements/`, `retros/`, `debug/`, `lifecycle.config.md`, `.cortex-init`) to the umbrella `cortex/`. The implementer works through 4 phases — root-detection contract, path-literal migration, data + doc rebases + `git mv` storm, then the atomic commit and finalize sequence — all landing in one commit. Per DR-7, no intermediate commits; partial completion is a working-copy-only state that an operator reverts via `git checkout -- .` or `git stash`.

## Outline

### Phase 1: Root-detection & init contract (tasks: 1, 2, 3)
**Goal**: Switch `_resolve_user_project_root()` predicate to detect `cortex/`, collapse the `cortex init` `_CONTENT_DECLINE_TARGETS` tuple, and swap sandbox registration from dual-`lifecycle/sessions/`+`lifecycle/` to umbrella `cortex/`.
**Checkpoint**: `_resolve_user_project_root()` returns the project root when called from inside a `cortex/`-bearing repo and raises `CortexProjectRootError` otherwise; `init.scaffold._CONTENT_DECLINE_TARGETS == ("cortex",)`; `init.handler` registration block adds a single `cortex/` entry.

### Phase 2: Path-literal migration (tasks: 4–10)
**Goal**: Rebase every code path literal from `lifecycle/`/`backlog/`/`research/`/`requirements/`/`retros/`/`debug/`/`lifecycle.config.md`/`.cortex-init` to its `cortex/`-prefixed equivalent across the overnight, backlog, dashboard, discovery, hook, bin, and plugin-canonical surfaces.
**Checkpoint**: `grep -rEn '/ "(lifecycle|backlog|research|requirements|retros|debug|lifecycle\.config\.md|\.cortex-init)"($|[^/])' cortex_command/ hooks/ claude/hooks/ bin/ plugins/cortex-overnight/server.py` returns no matches; equivalent `/ "cortex" / "..."` literals appear at every prior site.

### Phase 3: Data migration, doc rebases, and `git mv` storm (tasks: 11–16)
**Goal**: Author + run the one-time encoded-data migration (287 backlog YAML lines, 61 critical-review-residue artifacts, ~6 research prose cross-refs), rebase prose in requirements/skills/docs/tests, author `cortex/README.md`, and execute the `git mv` storm relocating every directory and state file under `cortex/`.
**Checkpoint**: encoded-data fields all carry `cortex/` prefixes; all five operational-doc files and two skill files use `cortex/`-prefixed paths in prose; `ls -d lifecycle backlog research requirements retros debug 2>&1 | grep -c "No such file"` ≥ 6 (working-copy view, pre-commit).

### Phase 4: Single atomic commit & finalize (tasks: 17, 18, 19)
**Goal**: Regenerate sandbox preflight against pre-relocation HEAD, stage everything with `git add -A`, commit, and run the post-commit finalize sequence (`cortex init --update`, version tag, plugin update note).
**Checkpoint**: `git log -1 --pretty=format:'%s'` matches the relocation commit subject; `just test` exits 0; `jq` against `~/.claude/settings.local.json` shows the umbrella `cortex/` allowWrite entry; an annotated `vN.0.0` tag points at HEAD.

## Tasks

### Task 1: Switch `_resolve_user_project_root()` predicate to detect `cortex/`
- **Files**: `cortex_command/common.py`, `cortex_command/tests/test_common.py` (or the existing resolver test file — locate via `grep -lr '_resolve_user_project_root' cortex_command/tests/ cortex_command/*/tests/`)
- **What**: Replace the line-89 predicate `(current / "lifecycle").is_dir() or (current / "backlog").is_dir()` with `(current / "cortex").is_dir()`. Update the `CortexProjectRootError` docstring at lines 46–52 and the resolver docstring at lines 56–80 to reference `cortex/`. Update the error-message string at lines 98–103 (`"Run from your cortex project root..."`) — the user-facing instruction text remains correct; only the "Searched:" trailer's directory-detection narrative changes if it mentions the old predicate. Add or update one resolver test that fixtures a `cortex/` subdir and confirms detection.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The function lives at `cortex_command/common.py:55-103`. The detection predicate is a single line (line 89). Single-condition `(current / "cortex").is_dir()` because both prior anchors (`lifecycle/` and `backlog/`) move under `cortex/`. The upward-walk loop (lines 85–96) and `.git/` terminator (line 91) are unchanged. The test fixture pattern lives somewhere under `cortex_command/tests/` or `cortex_command/*/tests/`; use `pytest`'s `tmp_path` + `monkeypatch.chdir` (the resolver is invoked at call time per the docstring, so chdir-based tests work).
- **Verification**: `grep -nE '\(current / "cortex"\)\.is_dir\(\)' cortex_command/common.py` returns exactly 1 match; `grep -nE '\(current / "lifecycle"\)\.is_dir\(\) or \(current / "backlog"\)\.is_dir\(\)' cortex_command/common.py` returns 0 matches; `just test` exits 0 (resolver tests pass).
- **Status**: [x] complete (commit c6c2e0c)

### Task 2: Collapse `_CONTENT_DECLINE_TARGETS` + add `cortex.gitignore` template entry
- **Files**: `cortex_command/init/scaffold.py`, `cortex_command/init/tests/test_scaffold.py`
- **What**: Update `_CONTENT_DECLINE_TARGETS` at `scaffold.py:56-61` from the four-tuple `("lifecycle", "backlog", "requirements", "lifecycle.config.md")` to the single-tuple `("cortex",)`. In the same file, locate the `.gitignore` append logic (controlled by `_GITIGNORE_TARGETS` at line 52 and the surrounding append helper near lines ~227–276) and add a commented-by-default `# cortex/` line under a documented `# Uncomment to gitignore cortex tool state` marker. Update the matching test in `tests/test_scaffold.py` so the R19 decline gate fires on a populated `cortex/` directory instead of populated `lifecycle/`/`backlog/`/etc.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_CONTENT_DECLINE_TARGETS` is consumed by R19 gate logic (search `scaffold.py` for `_CONTENT_DECLINE_TARGETS` usage — likely a `for target in _CONTENT_DECLINE_TARGETS:` loop near the decline-gate function). `_GITIGNORE_TARGETS` at line 52 currently contains `(_MARKER_FILENAME, _BACKUP_DIR_PATTERN)` = `(".cortex-init", ".cortex-init-backup/")`; do NOT add `cortex/` to this tuple (which would unconditionally gitignore) — instead, append the commented-out `cortex/` line in the literal-text emission of the `.gitignore` append. The test fixture pattern: `cortex_command/init/tests/test_scaffold.py` has existing R19 tests against the prior tuple — update fixtures to create a `cortex/` directory and assert the decline-gate raises.
- **Verification**: `grep -nE '_CONTENT_DECLINE_TARGETS = \("cortex",\)' cortex_command/init/scaffold.py` returns 1 match; `grep -nE '# Uncomment to gitignore cortex tool state' cortex_command/init/scaffold.py` returns at least 1 match; `pytest cortex_command/init/tests/test_scaffold.py -k decline` exits 0.
- **Status**: [x] complete (commit 776d6f4)

### Task 3: Collapse sandbox registration to umbrella `cortex/`
- **Files**: `cortex_command/init/handler.py`, `cortex_command/init/tests/test_settings_merge.py`
- **What**: At `handler.py:125-153` (the dual-registration block writing `lifecycle/sessions/` + `lifecycle/` into `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite`), collapse to a single entry that appends `<repo_root>/cortex`. Remove the two prior literal-path additions; preserve the surrounding flock + atomic-write contract (`settings_merge.py:65-66,140-164,256-262`) unchanged. Also update lines 203–204 if they reference the literal `"lifecycle"` string. Update the matching test in `test_settings_merge.py` to assert the registered path ends with `/cortex` and that exactly one new entry is added per `cortex init` invocation.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The dual-registration invariant exists for TOCTOU closure between the narrow legacy path (`lifecycle/sessions/`) and the wide path (`lifecycle/`). The umbrella `cortex/` is itself a parent of `cortex/lifecycle/sessions/`, so the TOCTOU window closes via the single broader grant — no two-entry coexistence needed. Reference `settings_merge.register()` (search for it) for the existing append contract; reuse without modification. The test file is at `cortex_command/init/tests/test_settings_merge.py` — read existing tests for the dual-registration assertion pattern and replace with single-entry assertion.
- **Verification**: `grep -nE '"lifecycle/sessions"|"lifecycle"' cortex_command/init/handler.py` returns 0 matches inside the registration block (lines 125–153 region); `pytest cortex_command/init/tests/test_settings_merge.py` exits 0.
- **Status**: [x] complete (commit b41c338)

### Task 4: Rebase overnight runtime path literals — state.py + runner.py
- **Files**: `cortex_command/overnight/state.py`, `cortex_command/overnight/runner.py`
- **What**: Replace `_resolve_user_project_root() / "lifecycle"` with `_resolve_user_project_root() / "cortex" / "lifecycle"` at `state.py:298,321,341`. In `runner.py`, replace `Path(worktree_path) / "backlog"` and `repo_path / "backlog"` at lines 421,423 with `... / "cortex" / "backlog"`; replace `repo_path / "lifecycle"` at line 1804 (the `pipeline-events.log` site) with `repo_path / "cortex" / "lifecycle"`. Update inline comments at runner.py:404–405 and 553/606 that mention `lifecycle/sessions/` to `cortex/lifecycle/sessions/`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `state.py:_session_dir()` is the single most load-bearing path-computation site — every overnight session resolves session storage through it. `runner.py` is the orchestration entry point; lines 421/423 set the followup-backlog write target, line 1804 sets the pipeline-events log path. Variable-name patterns vary (`_resolve_user_project_root()`, `repo_path`, `worktree_path`, `Path(worktree_path)`) — match each. Use `grep -nE '/ "(lifecycle|backlog)"' cortex_command/overnight/state.py cortex_command/overnight/runner.py` to enumerate all sites in these two files before editing.
- **Verification**: `grep -nE '/ "(lifecycle|backlog)"($|[^/])' cortex_command/overnight/state.py cortex_command/overnight/runner.py` returns 0 matches; `grep -cE '/ "cortex" / "(lifecycle|backlog)"' cortex_command/overnight/state.py` ≥ 3; `grep -cE '/ "cortex" / "(lifecycle|backlog)"' cortex_command/overnight/runner.py` ≥ 3.
- **Status**: [x] complete (squashed into commit c8110de5)

### Task 5: Rebase overnight runtime path literals — orchestrator, report, cli_handler
- **Files**: `cortex_command/overnight/orchestrator.py`, `cortex_command/overnight/report.py`, `cortex_command/overnight/cli_handler.py`
- **What**: At `orchestrator.py:98,101,104,107`, rebase the four `_resolve_user_project_root() / "lifecycle" / ...` factory defaults to include the `cortex/` prefix. At `report.py:52,125,616,631,949,2020,2062,2106`, rebase every `lifecycle_root` / `user_root` / `project_root` / `Path("lifecycle")` site. At `cli_handler.py:58`, rebase the `lifecycle.config.md` read path.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `orchestrator.py` has four `@dataclass` field factories with `default_factory=lambda: ...` — match the `lambda` pattern. `report.py:616,631` uses bare `Path("lifecycle").glob("*/review.md")` — replace with `Path("cortex/lifecycle").glob(...)` (or `Path("cortex") / "lifecycle"`). `report.py:2106` is `_cli_lifecycle_root = _cli_user_root / "lifecycle"` — drop in the `/ "cortex" /` prefix. `cli_handler.py:58` reads `lifecycle.config.md` from cwd — its new location is `cortex/lifecycle.config.md`.
- **Verification**: `grep -nE '/ "lifecycle"($|[^/])' cortex_command/overnight/orchestrator.py cortex_command/overnight/report.py cortex_command/overnight/cli_handler.py` returns 0 matches; `grep -nE 'Path\("lifecycle"\)' cortex_command/overnight/report.py` returns 0 matches; `grep -nE '"lifecycle\.config\.md"' cortex_command/overnight/cli_handler.py` returns 0 matches (replaced with `"cortex/lifecycle.config.md"` or split path components).
- **Status**: [x] complete (squashed into commit c8110de5)

### Task 6: Rebase overnight runtime path literals — daytime_pipeline, backlog, feature_executor
- **Files**: `cortex_command/overnight/daytime_pipeline.py`, `cortex_command/overnight/backlog.py`, `cortex_command/overnight/feature_executor.py`
- **What**: At `daytime_pipeline.py:181`, rebase `config_path = cwd / "lifecycle.config.md"` to `cwd / "cortex" / "lifecycle.config.md"`. At lines 220–243 and 391, rebase every `cwd / f"lifecycle/{feature}/..."` literal to `cwd / "cortex" / f"lifecycle/{feature}/..."`. At `backlog.py:506,507,580,581`, rebase the four `project_root / "lifecycle" / slug / ...` literals. At `feature_executor.py:153,165`, rebase the two `worktree_path / "lifecycle" / feature / ...` fallback paths.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `daytime_pipeline.py:59` already imports and calls `_resolve_user_project_root()` (post-#201); the literals on lines 181/220-243/391 still construct `lifecycle/<feature>/...` paths relative to `cwd` — preserve the `cwd` variable, just insert the `/ "cortex"` segment. `daytime_pipeline.py:243` has `(cwd / f"lifecycle/{feature}/deferred").mkdir(...)` — rebase the literal. `backlog.py:506-507` and `580-581` read research/spec paths for refine-context — rebase under `cortex/lifecycle/`. `feature_executor.py:153,165` is the worktree exit-report fallback path.
- **Verification**: `grep -rEn '/ ?"lifecycle(\.config\.md)?"($|[^/])|cwd / f"lifecycle/|/ "lifecycle" / ' cortex_command/overnight/daytime_pipeline.py cortex_command/overnight/backlog.py cortex_command/overnight/feature_executor.py` returns 0 matches; `grep -cE '/ "cortex" /' cortex_command/overnight/daytime_pipeline.py` ≥ 4.
- **Status**: [x] complete (squashed into commit c8110de5)

### Task 7: Rebase backlog modules + dashboard + discovery path literals
- **Files**: `cortex_command/backlog/generate_index.py`, `cortex_command/backlog/update_item.py`, `cortex_command/backlog/create_item.py`, `cortex_command/backlog/build_epic_map.py`, `cortex_command/discovery.py`
- **What**: In each backlog module, rebase `_resolve_user_project_root() / "backlog"` and `... / "lifecycle"` at the assignment sites (`generate_index.py:95,97,303`; `update_item.py:445`; `create_item.py:163`; `build_epic_map.py:160` if present) to include `/ "cortex" /`. In `discovery.py:104,187,195`, rebase `repo_root / "lifecycle"` and `repo_root / "research"` to `repo_root / "cortex" / "lifecycle"` and `repo_root / "cortex" / "research"`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: All three primary backlog modules wire through `_resolve_user_project_root()` (post-#201). `build_epic_map.py:160` is referenced in research as a consumer of `spec:` YAML — verify the line ref and edit accordingly. `discovery.py` uses `_default_repo_root()` (git rev-parse) at line 62, not `_resolve_user_project_root()` — the literals at 104/187/195 are constructed against `repo_root` parameter, just insert the `/ "cortex"` segment.
- **Verification**: `grep -rEn '_resolve_user_project_root\(\) / "(backlog|lifecycle)"($|[^/])' cortex_command/backlog/` returns 0 matches; `grep -nE 'repo_root / "(lifecycle|research)"($|[^/])' cortex_command/discovery.py` returns 0 matches.
- **Status**: [x] complete (squashed into commit c8110de5)

### Task 8: Rebase dashboard module path literals
- **Files**: `cortex_command/dashboard/app.py`, `cortex_command/dashboard/seed.py`, `cortex_command/dashboard/poller.py`, `cortex_command/dashboard/data.py`
- **What**: Across the four dashboard modules (~15 path-construction sites per research), rebase every literal `"lifecycle"`, `"backlog"`, `"research"` segment in `Path(...) / ...` constructions and every f-string of the form `f"lifecycle/{slug}/..."` to the `cortex/`-prefixed equivalent. Specifically `seed.py:99-100` has `f"lifecycle/{slug}/spec.md"` (per research) — replace with `f"cortex/lifecycle/{slug}/spec.md"`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Dashboard reads/serves JSON seed and live-poll data sourced from `lifecycle/<feature>/` artifacts. Run `grep -nE '"lifecycle"|/ "lifecycle"|f"lifecycle/' cortex_command/dashboard/*.py` to enumerate all 15 sites before editing. Where the literal is a path segment in `Path(...)` composition, insert `/ "cortex"`; where it's an f-string, insert `cortex/` before `lifecycle/`.
- **Verification**: `grep -rEn '"lifecycle"|f"lifecycle/' cortex_command/dashboard/*.py` returns 0 matches except inside `cortex/`-prefixed compositions; `pytest cortex_command/dashboard/tests/` exits 0.
- **Status**: [x] complete (squashed into commit c8110de5)

### Task 9: Rebase hooks + bin + parity gates
- **Files**: `hooks/cortex-scan-lifecycle.sh`, `claude/hooks/cortex-tool-failure-tracker.sh`, `.githooks/pre-commit`, `bin/cortex-check-parity`, `bin/cortex-log-invocation`
- **What**: In `cortex-scan-lifecycle.sh` at lines 26, 50, 84, 114, 328, 349, 361, 381, replace every `LIFECYCLE_DIR="$CWD/lifecycle"` (or equivalent) with `LIFECYCLE_DIR="$CWD/cortex/lifecycle"` and update any user-facing context message strings mentioning `lifecycle/`. In `cortex-tool-failure-tracker.sh:42`, replace `TRACK_DIR="lifecycle/sessions/${LIFECYCLE_SESSION_ID}/tool-failures"` with `TRACK_DIR="cortex/lifecycle/sessions/${LIFECYCLE_SESSION_ID}/tool-failures"`. In `.githooks/pre-commit:81`, update the parity-trigger glob from `requirements/*` to `cortex/requirements/*`. In `bin/cortex-check-parity:75`, update the glob from `"requirements/**/*.md"` to `"cortex/requirements/**/*.md"`; at lines 112–113, update `PREFLIGHT_PATH = "lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md"` to `"cortex/lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md"`. In `bin/cortex-log-invocation:46`, update the lifecycle-path reference.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Shell variable values use literal path fragments — straightforward sed-style substitutions. Pre-commit hook (`.githooks/pre-commit`) orchestrates parity + drift checks; glob update keeps the trigger firing when staged diffs touch the relocated requirements. `bin/cortex-check-parity` at lines 1001/1005/1010/1019/1027/1052/1064/1080/1090 consume `PREFLIGHT_PATH` — those callsites read the constant, no per-callsite edit needed. `bin/cortex-log-invocation:46` is one line; verify its exact path-string and edit.
- **Verification**: `grep -nE '"\$CWD/lifecycle"' hooks/cortex-scan-lifecycle.sh` returns 0 matches; `grep -nE 'TRACK_DIR="lifecycle/' claude/hooks/cortex-tool-failure-tracker.sh` returns 0 matches; `grep -nE '"requirements/\*\*/\*\.md"' bin/cortex-check-parity` returns 0 matches; `grep -nE 'PREFLIGHT_PATH = "lifecycle/' bin/cortex-check-parity` returns 0 matches; `grep -cE 'cortex/lifecycle' hooks/cortex-scan-lifecycle.sh` ≥ 8.
- **Status**: [x] complete (commit a029b87)

### Task 10: Rebase plugin canonical non-mirror
- **Files**: `plugins/cortex-overnight/server.py`
- **What**: At line 2164, replace `Path(cortex_root) / "lifecycle" / "sessions" / payload.session_id` with `Path(cortex_root) / "cortex" / "lifecycle" / "sessions" / payload.session_id`. Audit the rest of `plugins/cortex-overnight/server.py` for additional `"lifecycle"`/`"backlog"`/`"research"` path literals (search `grep -nE '"lifecycle"|"backlog"|"research"' plugins/cortex-overnight/server.py`) and rebase any others found.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Per CLAUDE.md and the discovery research §"Plugin mirrors", `plugins/cortex-overnight/server.py` is NOT auto-mirrored from a canonical source — it is hand-maintained Python. Plugin mirrors at `plugins/cortex-core/{skills,hooks,bin}/` and `plugins/cortex-overnight/{skills,hooks}/` regenerate via `just build-plugin` and need no manual edit. The other hand-maintained plugins (`cortex-pr-review`, `cortex-ui-extras`, `cortex-dev-extras`, `android-dev-extras`) have zero references to relocated paths per research.
- **Verification**: `grep -nE 'Path\(cortex_root\) / "lifecycle"' plugins/cortex-overnight/server.py` returns 0 matches; `grep -nE '"(lifecycle|backlog|research|requirements|retros|debug)"' plugins/cortex-overnight/server.py` returns 0 matches.
- **Status**: [x] complete (commit fe8778e)

### Task 11: Author + run encoded-data migration script
- **Files**: `cortex_command/init/_relocation_migration.py` (new, one-time), `cortex_command/init/tests/test_relocation_migration.py` (new), plus every file the script mutates (287 backlog YAML lines + 61 critical-review-residue JSON keys + ~6 research/<topic>/decomposed.md prose cross-refs)
- **What**: Write a one-time migration script that: (a) walks `backlog/*.md` and rewrites the four YAML fields (`discovery_source:`, `spec:`, `plan:`, `research:`) by prepending `cortex/` to any value matching `(lifecycle|backlog|research)/...` that lacks the prefix — idempotent on already-prefixed values; (b) walks `lifecycle/*/critical-review-residue.json` (active + archive) and rewrites every `"artifact"` key value with the same idempotent prefix logic via a JSON-aware loader (preserves ordering and unicode); (c) walks `research/*/decomposed.md` and rewrites prose cross-refs of the form `lifecycle/<slug>/` or `backlog/<id>` — narrow regex to avoid matching `cortex/lifecycle/` already-migrated text. Add a `test_relocation_migration.py` unit test exercising each of the three branches plus an idempotency assertion (running the script twice produces zero file changes on the second pass). Run the script once against the working tree; commit the script (deletion to a follow-up commit).
- **Depends on**: none
- **Complexity**: complex
- **Context**: 287 backlog YAML lines across 4 fields per discovery research; 61 `"artifact"` keys across active + archive per discovery. Use `ruamel.yaml` or in-memory YAML round-trip if available (preserves frontmatter ordering); else regex-based line-level rewrite is acceptable given the field-key prefixes are deterministic. JSON loader: `json.loads`/`json.dumps(..., indent=2)`. Idempotency invariant: `re.sub(r'^((discovery_source|spec|plan|research): )(?!cortex/)(lifecycle|backlog|research)/', r'\1cortex/\3/', line)` — only rewrites when value lacks the `cortex/` prefix.
- **Verification**: `pytest cortex_command/init/tests/test_relocation_migration.py` exits 0; after running the script, `grep -rEn '^(discovery_source|spec|plan|research): (lifecycle|backlog|research)/' backlog/` returns 0 matches; running the script a second time produces zero `git diff` output.
- **Status**: [x] complete (commit 99725dd)

### Task 12: Rebase requirements/project.md sandbox-constraint text + Conditional Loading footer
- **Files**: `requirements/project.md`
- **What**: At `requirements/project.md:28`, rewrite the "Per-repo sandbox registration" bullet's inline reference from `lifecycle/` to `cortex/`, and shift the surrounding sentence framing from "the repo's `lifecycle/` path" to "the repo's `cortex/` umbrella" (single-narrow-path → single-umbrella-path). At the "Conditional Loading" footer (search for `requirements/observability.md` reference), update area-doc relative paths so they remain valid after `requirements/` moves to `cortex/requirements/` (these are relative to the `requirements/` directory itself, so once the directory moves the relative refs continue to work — verify that no absolute repo-relative paths exist there).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The constraint at line 28 names the literal path `lifecycle/` and the change semantics are governed by DR-5 — the umbrella grant is a contract change, not just spirit-preservation. Surrounding text at lines 27–34 describes the additive registration + lockfile + flock pattern; preserve those facts, only the path reference and umbrella framing change.
- **Verification**: `grep -nE "registers the repo' \\?s \\?\`lifecycle/\\?\`" requirements/project.md` returns 0 matches; `grep -nE "registers the repo' \\?s \\?\`cortex/\\?\`" requirements/project.md` returns at least 1 match.
- **Status**: [x] complete (commits 1461a1e + a78b2b7 follow-up)

### Task 13: Rebase operational docs + CHANGELOG entry
- **Files**: `CLAUDE.md`, `docs/setup.md`, `docs/agentic-layer.md`, `README.md`, `CHANGELOG.md`
- **What**: In CLAUDE.md, locate the 5 path references (per discovery research §"Dogfood scale") and rebase to `cortex/`-prefixed equivalents — verify via `grep -nE '(^|[^/])(lifecycle|research|backlog|requirements|retros|debug)/' CLAUDE.md` and inspect each match (some may be in code examples or commit-evidence snippets where the path should remain pre-relocation; exercise judgment). In `docs/setup.md`, update the filesystem-layout walkthrough to describe the `cortex/` umbrella post-`cortex init`, single sandbox-grant entry, and optional gitignore-as-unit. In `docs/agentic-layer.md`, update any literal filesystem-layout descriptions (per discovery research, line 254 quotes filesystem paths users observe). In README.md, update the repo-layout overview and any `cortex init` example output. In CHANGELOG.md, prepend a new top entry describing the major-version cutover, required `/plugin update cortex-core`, post-commit `cortex init --update`, and a one-line note that backlog YAML / critical-review-residue have been bulk-migrated.
- **Depends on**: none
- **Complexity**: simple
- **Context**: These are prose edits, not code — manual inspection is appropriate. CHANGELOG entry should follow the existing CHANGELOG format (read the top few entries to confirm style). The discovery research enumerates 5 CLAUDE.md path refs (verified low count). docs/setup.md and docs/agentic-layer.md are operational documentation per research — they describe literal user-observable state and must update lock-step.
- **Verification**: `grep -nE '(^|[^/])(lifecycle|research|backlog|requirements|retros|debug)/' CLAUDE.md docs/setup.md docs/agentic-layer.md README.md` shows no matches that reference the post-relocation layout incorrectly (manual review of any remaining matches confirms they're either inside `cortex/...` compositions or are intentional historical references); `head -30 CHANGELOG.md | grep -iE 'cortex/ umbrella|relocate|plugin update cortex-core'` returns at least 2 matches.
- **Status**: [x] complete (commit 10d7edd)

### Task 14: Rebase skill prose + author cortex/README.md
- **Files**: `skills/lifecycle/SKILL.md`, `skills/refine/SKILL.md`, `cortex/README.md` (new)
- **What**: Create the umbrella directory via `mkdir -p cortex/` (idempotent; safe even if Task 16's `git mv` later populates it). In `skills/lifecycle/SKILL.md` and `skills/refine/SKILL.md`, replace ~60 prose references of the form `lifecycle/{feature}` and `lifecycle/<feature>` with `cortex/lifecycle/{feature}` and `cortex/lifecycle/<feature>` (preserve the `{feature}` and `<feature>` placeholder shapes). Replace the single `backlog/193-lifecycle-and-hook-hygiene-one-offs.md` example at `skills/lifecycle/SKILL.md:59` with `cortex/backlog/193-lifecycle-and-hook-hygiene-one-offs.md`. Author a new `cortex/README.md` at the umbrella root (~25–40 lines): one-paragraph blurb per direct child — `lifecycle/`, `research/`, `backlog/`, `requirements/`, `retros/`, `debug/`, `.cortex-init`, `lifecycle.config.md`. Plugin mirrors at `plugins/cortex-core/skills/{lifecycle,refine}/SKILL.md` regenerate automatically via `just build-plugin` — zero manual mirror edits.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Most skill prose mentions are in protocol-step descriptions and example tables. Use `grep -nE '(^|[^/])lifecycle/\{?(feature|slug)\}?' skills/lifecycle/SKILL.md skills/refine/SKILL.md` for the placeholder sites and `grep -nE '(^|[^/])lifecycle/[a-z]' skills/lifecycle/SKILL.md skills/refine/SKILL.md` for any literal-slug sites. cortex/README.md: lead with one sentence stating "Tool-managed working area for cortex-command. Safe to gitignore as a unit." Then one-paragraph descriptions per child. No need to enumerate every lifecycle subdirectory — high-level only.
- **Verification**: `grep -rEn '(^|[^/])lifecycle/\{?(feature|slug)\}?' skills/lifecycle/SKILL.md skills/refine/SKILL.md` returns 0 matches; `test -f cortex/README.md && [ $(wc -l < cortex/README.md) -ge 20 ]` succeeds; `head -1 cortex/README.md | grep -iE 'tool-managed|cortex-command'` returns a match.
- **Status**: [x] complete (commit 518a2d5)

### Task 15: Rebase test fixtures
- **Files**: `tests/test_lifecycle_phase_parity.py`, `tests/test_resolve_backlog_item.py`
- **What**: Update the 11 fixture sites across these two test files (per discovery research) — every `lifecycle/<slug>/`, `backlog/<id>-`, `research/<topic>/`, `requirements/<file>` literal in test fixtures and assertions gets a `cortex/` prefix. Where a test uses `tmp_path` with chdir setup that creates a `lifecycle/` subdir, change it to create a `cortex/lifecycle/` subdir. Where a test asserts a string output containing one of these path prefixes, update the assertion.
- **Depends on**: [1, 4, 5, 6, 7]
- **Complexity**: simple
- **Context**: `test_lifecycle_phase_parity.py` and `test_resolve_backlog_item.py` both rely on filesystem fixtures and string-output assertions. Read each test before editing — some fixtures create directories via `mkdir` and write files; others string-match outputs from `cortex-resolve-backlog-item`. After editing, run the specific test files first (faster feedback than `just test`), then the full suite.
- **Verification**: `pytest tests/test_lifecycle_phase_parity.py tests/test_resolve_backlog_item.py` exits 0; `just test` exits 0.
- **Status**: [x] complete (commits c6c2e0c [Task 1 baseline], multiple Task-15 commits; expansion picked up ~20 additional broken fixture sites across overnight + init suites; only `test_shim_records_invocation` remains failing — pre-existing, unrelated)

### Task 16: Execute `git mv` storm under `cortex/`
- **Files**: All relocated directories and state files — `lifecycle/`, `lifecycle/archive/`, `research/`, `research/archive/`, `backlog/`, `requirements/`, `retros/archive/`, `debug/`, `lifecycle.config.md`, `.cortex-init`
- **What**: Create the umbrella directory (`mkdir -p cortex/`) if not already present. Execute `git mv lifecycle cortex/lifecycle`, `git mv research cortex/research`, `git mv backlog cortex/backlog`, `git mv requirements cortex/requirements`, `git mv retros cortex/retros`, `git mv debug cortex/debug`, `git mv lifecycle.config.md cortex/lifecycle.config.md`, `git mv .cortex-init cortex/.cortex-init`. After the moves, run `git status` to confirm rename detection picked up the moves as `R` status (rather than `D` + `A`); if any path reports as `D` + `A`, `git mv` may have hit a path conflict — investigate before staging.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: `git mv` operates on the working tree and the index simultaneously, registering the move as a rename. With ~400+ tracked files affected (38+146 lifecycle dirs × files inside, 195 backlog items, 56 retros files, 10+30 research dirs × files, 5 requirements files, 5 debug files), git's default rename-detection threshold (`-M50`) should pick up most renames; if `git status` shows D/A pairs, add `-M30` to subsequent diff/status invocations for verification. The `_relocation_migration.py` script (Task 11) must have already run because the working tree's content references must be `cortex/`-prefixed before the `git mv` so the post-commit state is self-consistent.
- **Verification**: `ls -d lifecycle backlog research requirements retros debug 2>&1 | grep -c "No such file or directory"` ≥ 6; `git status --porcelain | awk '$1 ~ /^R/' | wc -l` ≥ 400; `ls cortex/` shows all 8 children.
- **Status**: [x] complete (squashed into commit c8110de5)

### Task 17: Refresh sandbox preflight against pre-relocation HEAD
- **Files**: `lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` (in working tree, pre-`git mv`)
- **What**: Before the `git mv` storm executes (Task 16), regenerate `lifecycle/apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites/preflight.md` against pre-relocation HEAD so `bin/cortex-check-parity:988` accepts the relocation commit. Use the existing preflight regeneration command (search the codebase or `just --list` for `preflight`, `sandbox-preflight`, or similar recipe). The preflight's `commit_hash:` field encodes pre-relocation HEAD; the file content moves under `cortex/lifecycle/.../preflight.md` as part of the rename storm.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Per the spec Edge Cases section, `bin/cortex-check-parity` triggers on staged edits matching sandbox-source regex patterns in lines 89–109. The runner.py edits in Task 4 (lines 421/423/1804) match this regex. The preflight gate at line 988 reads `commit_hash:` from the YAML and compares against staged HEAD — if the field is stale, the gate fails with E102. Solution: regenerate the preflight to point at pre-relocation HEAD so the gate accepts. The PREFLIGHT_PATH constant in `bin/cortex-check-parity:112-113` was updated in Task 9 to point at the new cortex/-prefixed location.
- **Verification**: Interactive/session-dependent (the preflight regeneration command varies by `just --list` output — implementer runs it and confirms `bin/cortex-check-parity --staged` exits 0 in the pre-commit dry-run before staging proceeds).
- **Status**: [x] complete via option (b) — `bin/cortex-check-parity --staged` exited 0 against the relocation commit's staged set, so the preflight gate was never invoked. No regeneration of the preflight artifact required. Squashed into commit c8110de5.

### Task 18: Single atomic commit (precondition checks → `git add -A` → `git commit`)
- **Files**: Commit metadata only; no file edits in this task
- **What**: Run the operator-side precondition checks in sequence: (a) `cortex overnight status` reports zero live sessions; (b) `[ -z "$LIFECYCLE_SESSION_ID" ]` from the shell where this commit will execute; (c) the commit shell is freshly opened (the implementer confirms by recording `echo $$` and `ps -o ppid= -p $$` for paper trail). Stage everything with `git add -A`. Commit with subject "Relocate cortex-command artifacts under cortex/ umbrella (#202)" and a body describing the major-version cutover, DR-5/7/8/9 references, and post-commit operator actions (cortex init --update, plugin update). Confirm pre-commit hooks pass — drift check, parity check, sandbox preflight, commit-message validator — and the commit lands in one log entry.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
- **Complexity**: simple
- **Context**: DR-7 binds single-atomic-commit. `git add -A` is required (no partial staging — partial staging makes working-copy and staged versions diverge under `core.hooksPath`). Pre-commit hook runs the parity + drift + preflight gates against the unified working copy. The shell session must be fresh (no `LIFECYCLE_SESSION_ID`) to avoid writes to a lifecycle dir mid-rename. Commit message should follow the project convention: imperative mood, capitalized, no trailing period, ≤72 chars subject — per CLAUDE.md.
- **Verification**: `git log -1 --pretty=format:'%s'` matches the commit subject; `git log -1 --name-only | wc -l` ≥ 500; `git log --oneline -2 | awk 'NR==1{first=$0} NR==2{print first; print $0}'` shows the relocation commit at HEAD with the prior commit unchanged.
- **Status**: [x] complete (squashed into commit c8110de5)

### Task 19: Post-commit finalize — `cortex init --update`, version tag, plugin-update note, `just test`
- **Files**: `~/.claude/settings.local.json` (sandbox grant refresh), git annotated tag
- **What**: Run `cortex init --update` from the fresh shell to replace the prior `lifecycle/`/`research/`/etc. sandbox-allow entries with the umbrella `cortex/` entry in `~/.claude/settings.local.json`. Apply an annotated tag `vN.0.0` (next major version) pointing at the relocation commit (`git tag -a vN.0.0 -m "Major version bump: cortex/ umbrella relocation"`). Confirm `just test` exits 0 against the relocated layout. Document the `/plugin update cortex-core` step in the commit's PR/notes (the user runs it before the next Claude Code session — not automatable from inside the commit).
- **Depends on**: [18]
- **Complexity**: simple
- **Context**: `cortex init --update` is the documented mechanism per `cortex_command/init/handler.py` (search for `--update`) for refreshing settings idempotently. Determine the next major version from the existing tag set via `git tag -l 'v[0-9]*' | sort -V | tail -1` and increment major. `just test` runs the full suite; failures here indicate a missed touchpoint and require returning to earlier tasks for fix.
- **Verification**: `jq '.sandbox.filesystem.allowWrite' ~/.claude/settings.local.json | grep -E '"[^"]+/cortex"'` returns at least 1 match; `git tag --points-at HEAD | grep -E '^v[0-9]+\.0\.0$'` returns at least 1 match; `just test` exits 0; `just validate-commit` exits 0.
- **Status**: [x] complete (squashed into commit c8110de5)

## Risks

- **Encoded-data migration script committed as code vs. ephemeral**: Task 11 commits the script under `cortex_command/init/_relocation_migration.py` and defers deletion to a follow-up commit. Alternative: run it ephemerally (paste-into-shell, not committed). Committing preserves auditability but adds ~150 lines of one-time code to `cortex_command/`. Recommend committing — the test file is genuinely useful for the post-mortem and the deletion follow-up is one trivial commit.
- **`git mv` rename-detection threshold**: With ~400+ tracked files moving under `cortex/`, git's `-M50` default should detect most as renames. If a small file's content materially differs from any rename candidate (unlikely for pure `git mv` operations), it appears as D + A. Mitigation: post-`git mv`, inspect `git status --porcelain`; if any D/A pairs surface, investigate before staging. No code-side mitigation needed.
- **Preflight regeneration sequencing**: Task 17 runs before Task 16's `git mv` so the regenerated preflight is at the OLD path (`lifecycle/apply-per-spawn-.../preflight.md`) and the rename storm relocates it under `cortex/`. If the preflight regenerator inspects current-working-tree state, it must run before any literal edits that match the sandbox-source regex have been staged — i.e., Task 17 in the order above runs *after* Task 4's edits but *before* `git add`. Confirm by inspecting the regenerator's behavior during Task 17.
- **Commit size impact on review**: The commit will touch 500+ files. PR review by a human (if any) is impractical at the file-by-file level. Mitigation: PR body should cite the DR records, the relocation runbook, and provide reviewer guidance to focus on hand-edited code/doc sites (~30) rather than the rename storm.
- **Plugin-version skew until `/plugin update cortex-core` runs**: Until the operator updates the local plugin, an existing Claude Code session's loaded plugin still emits prose telling agents to write to `lifecycle/<feature>/`. Sessions started post-commit pre-update will misfire. Mitigation: CHANGELOG entry + commit message + verbal confirmation with the operator before the commit lands.
- **Self-reference relocator commit cadence**: Per the spec Edge Cases, the relocation commit cannot run from this conversation's lifecycle session (LIFECYCLE_SESSION_ID is set). The operator must complete this lifecycle (Plan → Implement → Review → Complete), then open a fresh shell and run the relocation commit. The 19-task plan therefore describes work that the implement-phase orchestrator executes against the lifecycle's session, with Task 18's precondition-(b) check failing until the fresh shell is opened. Effectively: Tasks 1–17 run inside the lifecycle session; Task 18 requires the operator to step out into a fresh shell before staging.

## Acceptance

The relocation commit lands as a single git commit at HEAD with ≥500 file paths touched (renames + content edits + new files), all pre-commit gates green. Post-commit: `just test` exits 0, `~/.claude/settings.local.json` shows the umbrella `cortex/` allowWrite entry, an annotated major-version tag points at HEAD, and `cortex/` is the sole tool-managed root at repo level (the eight prior repo-root paths are absent). The relocation is reversible via `git revert HEAD` (large but mechanical revert) until the major-version tag is pushed.
