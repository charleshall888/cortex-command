# Plan: untrack-backlog-index-cache

## Overview
Harden the one hard-failing index consumer (`ready.py`) and the soft-failing `/backlog list` so they work when the index is absent, THEN untrack `cortex/backlog/index.json`/`index.md` (gitignore + `git rm --cached`), delete the stray nested junk index, and stop the overnight pre-flight from committing the regenerated index. The index becomes a deterministic local cache regenerated on demand. Library edits (`cortex_command/`) ship in the wheel; skill edits regenerate their plugin mirror in the same commit.

## Outline

### Phase 1: Harden consumers (tasks: 1, 2)
**Goal**: Every index reader works when `index.json`/`index.md` is absent, before tracking is removed.
**Checkpoint**: `cortex-backlog-ready` and `/backlog list` succeed (regenerating on demand) with no index files on disk; new test green.

### Phase 2: Untrack and stop committing (tasks: 3, 4, 5, 6)
**Goal**: Remove the index from version control, delete the stray, stop committing it overnight, true-up docs, and verify the whole feature green incl. the wheel-source runtime path.
**Checkpoint**: `git ls-files` shows no index files; `git check-ignore` ignores both; `just test` green; mirrors in sync; force-source binstub works on a missing index.

## Tasks

### Task 1: ready.py regenerate-on-miss + unit test
- **Files**: cortex_command/backlog/ready.py, tests/test_backlog_ready_missing_index.py
- **What**: On a missing `index.json`, `ready.py` regenerates records in-memory (no disk write) instead of hard-failing; its module docstring is corrected to match; a new test pins the contract. (Spec reqs 1, 2.)
- **Depends on**: none
- **Complexity**: simple
- **Context**: In `ready.py` `main()` the index is loaded at ≈L425-435 inside an outer `try` whose `except Exception` (≈L444) maps to the canonical `_emit_error` JSON. Replace the `except FileNotFoundError: return _emit_error("backlog/index.json not found")` (≈L429-430) with an in-process regenerate: `from cortex_command.backlog.generate_index import collect_items, generate_json`; `collect_items` returns a 4-tuple `(items, active_ids, archive_ids, all_items)`; build the records list by parsing `generate_json(items)` output as JSON (the same record shape `ready.py` already consumes from `index.json`); pass `BACKLOG_DIR` (ready.py's CWD-relative dir) and `lifecycle_dir` so records carry `lifecycle_slug`/`lifecycle_phase` (parity with the committed index). Keep the regenerate call INSIDE the existing outer `try` so `collect_items`' unguarded `read_text`/`detect_lifecycle_phase` I/O (generate_index.py:124,142,177) converts a raise to `_emit_error`, not a traceback. Leave the staleness machinery (ready.py:92-123) unchanged. **Also correct the module docstring** (ready.py:33-34, "On missing or malformed input the script emits … and exits 1") so it no longer claims *missing* exits 1 — reword to "On malformed input the script emits … and exits 1; a missing index is regenerated in-memory." Test: follow the tmp_path fixture pattern in tests/test_backlog_ready_render.py (writes `[0-9]*-*.md` items, runs the `cortex-backlog-ready` console script via subprocess) but WITHOUT writing `index.json`; assert exit 0, stdout parses as JSON with a `groups` key, and no `index.json` was written to the tmp backlog dir.
- **Verification**: `python3 -m pytest tests/test_backlog_ready_missing_index.py -q` (exit 0) AND `! grep -q "missing or malformed input the script emits" cortex_command/backlog/ready.py` (exit 0 — stale docstring clause gone) — pass if both exit 0.
- **Status**: [ ] pending

### Task 2: backlog SKILL prose works on a missing index (list/pick/ready)
- **Files**: skills/backlog/SKILL.md, plugins/cortex-core/skills/backlog/SKILL.md
- **What**: Make all three missing-index prose sites in the backlog skill consistent with the new `ready.py` behavior: `### list` auto-regenerates instead of suggesting reindex; `### pick` (L92) and `### ready` (L109) drop "missing" from their reindex suggestion (after Task 1, a *missing* index self-heals — only *malformed* still errors). Regenerate the plugin mirror in the same commit. (Spec req 3.)
- **Depends on**: none
- **Complexity**: simple
- **Context**: skills/backlog/SKILL.md `### list` is at ≈L66-72 ("3. If `cortex/backlog/index.md` does not exist, suggest running `reindex` first"). Replace step 3 with: if absent, run `cortex-generate-backlog-index` then read. Then at L92 (pick) and L109 (ready), both currently "suggest running `/cortex-core:backlog reindex` if the error indicates a **missing or malformed** backlog index" — change to "if the error indicates a **malformed** backlog index" (missing now regenerates in-memory and exits 0, so only the malformed/JSONDecodeError path still emits a non-zero exit). After editing canonical, run `just build-plugin` (rsyncs skills/backlog/ → plugins/cortex-core/skills/backlog/) and stage the regenerated mirror in the SAME commit — the `.githooks/pre-commit` drift hook blocks otherwise (CLAUDE.md dual-source enforcement).
- **Verification**: `grep -q "cortex-generate-backlog-index" skills/backlog/SKILL.md` (exit 0) AND `! grep -q "suggest running .reindex. first" skills/backlog/SKILL.md` (exit 0) AND `test "$(grep -c "missing or malformed backlog index" skills/backlog/SKILL.md)" = 0` (exit 0 — pick/ready prose updated) AND `just build-plugin >/dev/null && cmp skills/backlog/SKILL.md plugins/cortex-core/skills/backlog/SKILL.md` (exit 0) — pass if all exit 0.
- **Status**: [ ] pending

### Task 3: gitignore + untrack canonical pair + delete stray
- **Files**: .gitignore, cortex/backlog/index.json (git rm --cached — untracked, retained on disk), cortex/backlog/index.md (git rm --cached — untracked, retained on disk), cortex/backlog/backlog/index.json (git rm -rf — deleted), cortex/backlog/backlog/index.md (git rm -rf — deleted)
- **What**: Add anchored ignore lines for the index pair, `git rm --cached` the tracked canonical pair (retain on disk), and `git rm -r` the stray `cortex/backlog/backlog/` junk directory (spec reqs 4, 5, 6).
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Add adjacent to .gitignore's existing `cortex/backlog/*.events.jsonl` (≈L33): two lines `cortex/backlog/index.json` and `cortex/backlog/index.md` (anchored, NOT `**/index.*`). Then `git rm --cached cortex/backlog/index.json cortex/backlog/index.md` (files stay on disk, become untracked/ignored). Then `git rm -rf cortex/backlog/backlog/` (the `-f` is required — bare `git rm -r` aborts with exit 1 if a stray copy is dirty-vs-HEAD; these are disposable `[]`-junk from the May-12 umbrella relocation, commit c8110de5, so forcing is correct; generator no longer writes there). Depends on Tasks 1-2 so consumers are hardened before tracking is removed (Phase-1-before-Phase-2 in the working tree).
- **Verification**: `git check-ignore cortex/backlog/index.json cortex/backlog/index.md` prints both (exit 0) AND `test -z "$(git ls-files cortex/backlog/index.json cortex/backlog/index.md cortex/backlog/backlog/)"` (exit 0) AND `test -f cortex/backlog/index.json && test ! -e cortex/backlog/backlog` (exit 0) — pass if all exit 0.
- **Status**: [ ] pending

### Task 4: overnight pre-flight regenerates but stops committing the index
- **Files**: skills/overnight/references/new-session-flow.md, skills/overnight/SKILL.md, plugins/cortex-overnight/skills/overnight/references/new-session-flow.md, plugins/cortex-overnight/skills/overnight/SKILL.md
- **What**: Remove the `git add cortex/backlog/index.json index.md` + conditional "Regenerate backlog index" commit from the pre-selection step, keeping the `cortex-generate-backlog-index` regenerate and its halt-on-non-zero (spec req 7). Update the SKILL.md summary bullet. Regenerate the cortex-overnight mirror in the same commit.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: skills/overnight/references/new-session-flow.md ≈L19-22: keep sub-step 1 ("Run `cortex-generate-backlog-index` … exit non-zero → halt"); delete sub-step 2 (`git add cortex/backlog/index.json cortex/backlog/index.md`) and sub-step 3-4 (commit "Regenerate backlog index" if changed / skip if unchanged). skills/overnight/SKILL.md ≈L64 "Pre-selection index regeneration" bullet: reword to "regenerate; do not commit (index is a local cache)". Leave the separate uncommitted-files pre-flight (`git status --porcelain -- cortex/lifecycle/ cortex/backlog/`, ≈L123) untouched — it correctly stops seeing the now-ignored index and still catches dirty backlog item `.md` files. After edits run `just build-plugin` and stage the cortex-overnight mirror in the same commit.
- **Verification**: `test "$(grep -c 'git add cortex/backlog/index' skills/overnight/references/new-session-flow.md)" = 0` (exit 0) AND `grep -q 'cortex-generate-backlog-index' skills/overnight/references/new-session-flow.md` (exit 0) AND `grep -qi 'halt' skills/overnight/references/new-session-flow.md` (exit 0) AND `test "$(grep -c 'git add cortex/backlog/index' skills/overnight/SKILL.md)" = 0` (exit 0 — summary bullet reworded) AND `just build-plugin >/dev/null && cmp skills/overnight/references/new-session-flow.md plugins/cortex-overnight/skills/overnight/references/new-session-flow.md && cmp skills/overnight/SKILL.md plugins/cortex-overnight/skills/overnight/SKILL.md` (exit 0 — both mirrors in sync) — pass if all exit 0.
- **Status**: [ ] pending

### Task 5: docs describe the index as a regenerated local cache
- **Files**: docs/backlog.md, docs/agentic-layer.md
- **What**: Update the index-regeneration note (~docs/backlog.md L176), the `list` note (~L92), and the backlog-index description (~docs/agentic-layer.md L250) to state the index is generated on demand and not version-controlled (spec req 8).
- **Depends on**: none
- **Complexity**: simple
- **Context**: docs/backlog.md L176 currently describes regeneration via `cortex-generate-backlog-index`; add that the files are not committed (gitignored local cache, regenerated on every `cortex-update-item` and on demand). docs/backlog.md L92 currently reads "Reads `cortex/backlog/index.md` and presents the summary table. Suggests running `reindex` if the index does not exist." — that becomes false after Task 2 (list auto-regenerates); reword to drop the "Suggests running reindex" clause (the index is auto-regenerated on demand). docs/agentic-layer.md L250 backlog-index bullet: add "generated locally, not version-controlled". Prose-only — no code, no parity surface.
- **Verification**: `grep -qiE 'not (version-)?control|local cache|not committed|regenerated on demand' docs/backlog.md` (exit 0) AND `test "$(grep -c 'Suggests running .reindex. if the index does not exist' docs/backlog.md)" = 0` (exit 0 — stale L92 clause gone) AND `grep -qiE 'not (version-)?control|local cache|not committed|generated locally' docs/agentic-layer.md` (exit 0) — pass if all exit 0.
- **Status**: [ ] pending

### Task 6: whole-feature verification — suite, mirror drift, wheel-source runtime
- **Files**: (verification only — no edits; if drift/failures surface, fix in the owning task)
- **What**: Confirm the suite is green, plugin mirrors carry no drift, and the installed-binstub code path (wheel-source) handles a missing index — closing the deployment-window gap (spec reqs 9, 10, 11).
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: simple
- **Context**: `just test` runs the full suite (spec req 10). After `just build-plugin`, ANY non-empty `git status --porcelain plugins/` means residual mirror drift (the per-task commits in Tasks 2/4 should already have staged+committed the mirrors, so a clean rebuild produces no output); req 9. For req 11, the working-tree fix must be exercised against the actual module — NOTE `cortex-backlog-ready` is a pip/uv **console script**, not a `bin/cortex-*` bash wrapper, so `CORTEX_COMMAND_FORCE_SOURCE` does NOT apply to it; run the working tree directly via `python3 -m cortex_command.backlog.ready`. This proves the shipped source handles a missing index without a wheel reinstall. The actual `uv tool install --reinstall` + plugin re-sync is a completion/release action (see Risks) recorded for the Complete phase. Exercise BOTH index files missing (index.json for ready.py; index.md is covered by Task 2's list path).
- **Verification**: `just test` (exit 0) AND `rm -f cortex/backlog/index.json cortex/backlog/index.md; python3 -m cortex_command.backlog.ready >/dev/null 2>&1; rc=$?; cortex-generate-backlog-index >/dev/null 2>&1; test "$rc" = 0` (exit 0 — working-tree ready.py succeeds on a missing index, then index regenerated) AND `just build-plugin >/dev/null && test -z "$(git status --porcelain plugins/)"` (exit 0 — zero residual mirror drift) — pass if all exit 0.
- **Status**: [ ] pending

## Risks
- **Wheel reinstall must happen at completion.** The Phase-1 `ready.py` fix protects the runtime only after the wheel is reinstalled and the plugin re-synced (project.md:38). Within this single feature/release the fix and the untrack ship together, so a fresh clone installing the released wheel is safe; the residual window is the dogfooding box between merge-to-main and reinstall, and fresh interactive/overnight worktrees materialized from the new HEAD with the old wheel. Mitigation: the Complete phase / release ritual reinstalls the wheel + re-syncs plugins before relying on a fresh worktree; `CORTEX_COMMAND_FORCE_SOURCE=1` is the working-tree escape hatch meanwhile.
- **Does not solve #135** (the `.git/index` staging-area race) — orthogonal, `wontfix`. This only removes one file from the shared-staging contention surface.
- **`build_epic_map` direct invocation** on a fresh checkout now exits 1 with a clear, regenerable error (unchanged failure mode; deliberately not hardened to preserve `dev`'s exit-1 fallback contract).

## Acceptance
After this lands (and the wheel is reinstalled), `git ls-files cortex/backlog/ | grep -c index` = 0 and `git check-ignore` ignores both index files, yet every consumer works on a checkout with no index present — `cortex-backlog-ready`/`/backlog pick`/`ready` regenerate in-memory, `/backlog list` and `/dev` auto-regenerate, overnight selection falls back/regenerates, and `scan_lifecycle`/dashboard degrade or scan directly. Parallel `/refine` sessions no longer produce committed `index.json`/`index.md` diffs that conflict. `just test` is green and plugin mirrors carry no drift.
