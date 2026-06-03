# Specification: untrack-backlog-index-cache

## Problem Statement

The derived backlog index (`cortex/backlog/index.json` + `index.md`) is committed to git, yet it is a 100%-deterministic aggregate of the per-item `cortex/backlog/NNN-*.md` files, regenerated as a side effect of every `cortex-update-item`. Because a version-controlled aggregate is rewritten in full by every writer, parallel `/refine` (and lifecycle) sessions produce divergent index copies that conflict or clobber each other when committed — the user's reported pain. The durable fix (per the project's Solution-horizon principle) is to stop version-controlling the derived data: gitignore the index, regenerate it as a local cache, and make the consumers that hard-depend on it regenerate-on-miss so nothing breaks on a fresh checkout. This eliminates the conflict class entirely rather than patching it with a merge driver.

## Phases

- **Phase 1: Harden consumers** — make every reader of the index work when the file is absent, BEFORE the file stops being tracked. NOTE this is a *commit*-ordering guarantee in the working tree; it becomes a *runtime* guarantee only once the wheel carrying req 1 is reinstalled and the plugin mirror re-synced (the consumers run from the installed wheel/plugin, not the working tree — see Technical Constraints "Deployment sequencing").
- **Phase 2: Untrack and stop committing** — gitignore the index, remove the tracked copies and the stray nested duplicate, stop the overnight pre-flight from committing the regenerated index, and update docs + plugin mirrors. Sequenced after the Phase-1 fixes are in the installed wheel/plugin.

## Requirements

**Priority (MoSCoW):** Must-have — reqs 1, 4, 5, 7 (the untrack itself plus the consumer guard and commit-site change that prevent breakage and stop the conflicts), reqs 9–10 (mirror + suite integrity, non-negotiable for a green merge), and req 11 (the wheel reinstall / plugin re-sync that makes the Phase-1 guard real at runtime, not just in the working tree). Must-have-supporting — reqs 2, 6, 8 (the contract test, the stray cleanup that finishes the untrack, the doc truth-up). Should-have — req 3 (`/backlog list` auto-regenerate): a UX tidy that completes "every consumer works when absent"; `ready.py` (req 1) already covers the hard-fail path, so `list`'s soft-fail is the lower-severity tail. Req 3 is the one scope item raised at the §4 approval surface. Won't-do this feature: see Non-Requirements.

1. **`cortex-backlog-ready` regenerates on missing index.** On `FileNotFoundError` for `cortex/backlog/index.json`, `cortex_command/backlog/ready.py` regenerates the records **in-process and in-memory** (via `collect_items` + `generate_json` from `cortex_command.backlog.generate_index`; no disk write) and continues, instead of `_emit_error("…not found")`. Acceptance: with no `cortex/backlog/index.json` present, `cortex-backlog-ready` exits 0 and emits a valid JSON object with a `groups` key (e.g. `cortex-backlog-ready | python3 -c "import json,sys; json.load(sys.stdin)"` exits 0). **Phase**: Harden consumers

2. **New test for the regenerate-on-miss contract.** A pytest asserts `cortex-backlog-ready` succeeds (exit 0, valid JSON, no `index.json` written to disk) when `index.json` is absent from a populated backlog dir. Acceptance: the new test file runs green under `just test` (e.g. `python3 -m pytest tests/test_backlog_ready_missing_index.py` exits 0). **Phase**: Harden consumers

3. **Backlog SKILL prose is consistent with the new missing-index behavior.** `skills/backlog/SKILL.md`'s `list` subcommand runs `cortex-generate-backlog-index` when `index.md` is absent, then reads it (replacing the "suggest running `reindex` first" branch); and the `pick` (L92) and `ready` (L109) subcommands drop "missing" from their reindex suggestion, since after req 1 a *missing* index self-heals and only a *malformed* one still exits non-zero. Acceptance: `grep -c "cortex-generate-backlog-index" skills/backlog/SKILL.md` ≥ 1; the "suggest running `reindex` first" instruction is removed from `list`; and `grep -c "missing or malformed backlog index" skills/backlog/SKILL.md` = 0. **Phase**: Harden consumers

4. **Index files are gitignored.** `.gitignore` ignores both `cortex/backlog/index.json` and `cortex/backlog/index.md` (anchored paths, adjacent to the existing `cortex/backlog/*.events.jsonl` rule). Acceptance: `git check-ignore cortex/backlog/index.json cortex/backlog/index.md` lists both (exit 0). **Phase**: Untrack and stop committing

5. **Canonical index pair is untracked (file retained on disk).** `cortex/backlog/index.json` and `index.md` are removed from git tracking via `git rm --cached` (the working-tree files stay, now ignored). Acceptance: `git ls-files cortex/backlog/index.json cortex/backlog/index.md` prints nothing; both files still exist on disk. **Phase**: Untrack and stop committing

6. **Stray nested index is deleted.** The junk `cortex/backlog/backlog/` directory (empty `[]` index from the May-12 umbrella relocation) is removed via `git rm -r`. Acceptance: `git ls-files cortex/backlog/backlog/` prints nothing and the directory no longer exists. **Phase**: Untrack and stop committing

7. **Overnight pre-flight stops committing the index but still regenerates it.** In `skills/overnight/references/new-session-flow.md`, the `git add cortex/backlog/index.json cortex/backlog/index.md` line and its conditional "Regenerate backlog index" commit are removed; the `cortex-generate-backlog-index` step **and its halt-on-non-zero behavior are retained**. `skills/overnight/SKILL.md`'s "Pre-selection index regeneration" bullet (≈L64, "stage … commit if changed") is updated to say the index is regenerated but not committed. Acceptance: `grep -c "git add cortex/backlog/index" skills/overnight/references/new-session-flow.md` = 0; `grep -c "cortex-generate-backlog-index" skills/overnight/references/new-session-flow.md` ≥ 1; the halt-on-failure sentence remains. **Phase**: Untrack and stop committing

8. **Docs describe the index as a regenerated local cache, not committed.** `docs/backlog.md` (index-regeneration note ~L176 and the `list` note ~L92) and `docs/agentic-layer.md` (~L250) state the index is generated-on-demand and not version-controlled. Acceptance: `grep -ci "not.*commit\|local cache\|regenerated on" docs/backlog.md` ≥ 1 at the index description. **Phase**: Untrack and stop committing

9. **Plugin mirrors regenerated and consistent.** After editing `skills/overnight/*` and `skills/backlog/*`, `just build-plugin` produces no drift (mirrors under `plugins/cortex-overnight/skills/overnight/` and `plugins/cortex-core/skills/backlog/` match canonical), and canonical + mirror are committed together. Acceptance: `just build-plugin` then `git status --porcelain plugins/` is empty after staging (the pre-commit drift hook passes). **Phase**: Untrack and stop committing

10. **Full suite green.** Acceptance: `just test` exits 0. **Phase**: Untrack and stop committing

11. **Runtime consumers carry the Phase-1 fix before relying on an absent index.** The wheel is reinstalled and the plugin mirror re-synced so the *installed* `cortex-backlog-ready` carries req 1 (closing the wheel-binstub deployment window per Technical Constraints "Deployment sequencing"). Acceptance: with no `cortex/backlog/index.json` on disk, the working-tree module succeeds — `python3 -m cortex_command.backlog.ready` exits 0 with valid JSON (proving the shipped source is correct; `cortex-backlog-ready` is a console script, so `python3 -m` — not `CORTEX_COMMAND_FORCE_SOURCE` — is the working-tree test path; the actual installed-binstub fix lands with the feature's wheel reinstall per `docs/internals/auto-update.md`). **Phase**: Untrack and stop committing

## Non-Requirements

- Does **not** solve #135 (the shared `.git/index` *staging-area* race between concurrent commits) — that is an orthogonal, `wontfix` problem; this only removes the backlog index *file* from the contention surface.
- Does **not** change the index file format, the generator's output, or `cortex-update-item`'s regenerate-on-mutation side effect.
- Does **not** modify `build_epic_map.py`, `scan_lifecycle.py` (fail-open `({}, [])` — acceptable), `dashboard/data.py` (scans `*.md` directly — no index dependency), or `overnight/backlog.py` (already falls back to `parse_backlog_dir`). On `build_epic_map.py` specifically: its `exit 1` on a missing index is **load-bearing for `dev`'s fallback** (`dev` Step 3a regenerates first, then `dev/SKILL.md:161-164` falls back to `index.md` on exit 1), so we deliberately do **not** add regenerate-on-miss there — doing so would break that contract. The honest cost: a *direct* `cortex-build-epic-map` invocation (human shell / another skill) on a fresh checkout now exits 1 with `index file not found` where the committed file used to satisfy it. This is acceptable degradation — a clear, regenerable error (`cortex-generate-backlog-index` fixes it), the same failure mode `build_epic_map` already produces today, not a silent or worse state.
- Does **not** remove `ready.py`'s staleness-warning machinery (`ready.py:92-123`) — still useful for present-but-stale, and silent when absent.
- Does **not** introduce a `.gitattributes merge=union` or a custom merge driver (the wrong fix for a file that should not be tracked at all).
- Does **not** create a new ADR (fails the three-criteria gate per research) or alter `complete.md:214`'s pre-existing `generate_index` invocation idiom.

## Edge Cases

- **Fresh clone, `/backlog pick` or `ready` before any regeneration**: `ready.py` regenerates in-memory → exits 0 with correct groups.
- **Fresh clone, `/backlog list`**: `list` auto-regenerates `index.md` → renders the table.
- **Stale-but-present index** (a `.md` edited directly, bypassing the tool): `ready.py` reads the present (stale) index and warns on stderr, exit 0 — unchanged from today. Overnight selection stays fresh because overnight regenerates at pre-flight before selecting.
- **Concurrent regenerate-on-miss**: `ready.py`'s regeneration is in-memory (writes nothing); on-disk regenerations elsewhere use `atomic_write` (temp + `os.replace`) and are deterministic → last-writer-wins is benign.
- **Pulling the untrack commit into an existing checkout**: the file leaves git's index but the working copy is retained and now ignored; `.gitignore` prevents re-tracking. The two directory-scoped `git add cortex/backlog/` sites — `complete.md:259` and `runner.py:506` (`_commit_followup_in_worktree`) — respect `.gitignore` and skip the now-ignored index (verified: a directory-scoped add does not stage an ignored file). There is no broad `git add -A`/`.`/`-u`/`commit -a` in skills/, hooks/, or cortex_command/.
- **In-flight worktree bootstrapped from a pre-untrack HEAD** (the dogfooding hazard): an overnight integration worktree or interactive worktree created from a HEAD predating Phase 2 still *tracks* `index.json`/`index.md`, so `runner.py:506`'s `git add cortex/backlog/` can re-commit a modified tracked index onto that integration branch. This self-heals once that branch merges and a later regeneration under the now-active `.gitignore` drops it; the **Deployment sequencing** constraint (reinstall + re-sync before materializing fresh worktrees) closes the runtime side of this window.
- **Scheduled overnight on a fresh checkout**: `new-session-flow.md` regenerates the index before `select_overnight_batch`, which itself falls back to file-scan — doubly safe.

## Changes to Existing Behavior

- **MODIFIED**: `cortex/backlog/index.json` + `index.md` are no longer git-tracked → a regenerated local cache.
- **MODIFIED**: `cortex-backlog-ready` regenerates in-memory on a missing index instead of hard-failing with exit 1.
- **MODIFIED**: `/backlog list` auto-regenerates on a missing `index.md` instead of suggesting `reindex`.
- **REMOVED**: overnight pre-flight no longer `git add`s/commits the regenerated index (it still regenerates and halts on regeneration failure).
- **REMOVED**: the tracked stray `cortex/backlog/backlog/index.{json,md}`.

## Technical Constraints

- **Deployment sequencing (wheel-binstub vs working tree).** `cortex-backlog-ready` (req 1) and `/backlog list` (req 3, shipped via the plugin mirror) execute against the *installed wheel/plugin*, not the working tree (project.md:38). The Phase-1 fixes therefore do not protect the runtime until the wheel is reinstalled (`uv tool install --reinstall …`) and the plugin re-synced. Completion of this feature MUST include that reinstall + re-sync, sequenced so the Phase-1-bearing wheel is installed before any fresh checkout/worktree relies on the absent index. On the dogfooding box, `git rm --cached` (req 5) retains the on-disk index, so the old wheel keeps working there until a fresh worktree/clone. To exercise the working-tree `ready.py` before a reinstall, invoke `python3 -m cortex_command.backlog.ready` directly — note `CORTEX_COMMAND_FORCE_SOURCE` is honored only by the `bin/cortex-*` bash wrappers, NOT by console-script entry points like `cortex-backlog-ready`, so it is not the escape hatch here.
- `ready.py` regenerate-on-miss uses `from cortex_command.backlog.generate_index import collect_items, generate_json`. At implement, confirm `collect_items`'s return-shape (it returns a 4-tuple `(items, active_ids, archive_ids, all_items)`) and whether to pass `lifecycle_dir` so regenerated records carry `lifecycle_slug`/`lifecycle_phase`; use `BACKLOG_DIR` (ready.py's CWD-relative dir) for consistency with the rest of the module. **Place the regenerate call inside `ready.py`'s existing outer `try` (≈L414-446)** so that `collect_items`' unguarded `read_text`/`detect_lifecycle_phase` I/O (generate_index.py:124,142,177) — which, unlike `ready.py:_load_full_corpus`, does not catch `OSError` — converts any raise to the canonical `_emit_error` JSON contract rather than an uncaught traceback. (Reviewers verified record field-parity, unpack arity, and the #152 external-blocker concern are all non-issues: `ready.py` never reads `lifecycle_slug`/`lifecycle_phase` from index records, and external-blocker classification uses an independent full-corpus scan.)
- `.gitignore` patterns are anchored (`cortex/backlog/index.json`, not `**/index.*`); the nested stray is removed by deletion (req 6), not by a glob.
- Plugin-mirror discipline (project convention + prior feedback): run `just build-plugin` and commit canonical + regenerated mirror **together** in the same commit — the pre-commit drift hook blocks otherwise; do not defer mirror regen to a final task. `cortex_command/` library edits (`ready.py`) are not mirrored and not parity-gated.
- No new console scripts → no `cortex-check-parity` wiring needed.

## Open Decisions

None. (The one genuine product trade-off — untrack both files vs. keep `index.md` committed for GitHub browsability — is resolved at the §4 approval surface, not deferred: the recommendation is **untrack both**, and the user can redirect via "Request changes".)

## Proposed ADR

None considered.
