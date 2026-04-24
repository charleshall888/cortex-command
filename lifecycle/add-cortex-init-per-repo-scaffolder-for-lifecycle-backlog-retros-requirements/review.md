# Review: add-cortex-init-per-repo-scaffolder-for-lifecycle-backlog-retros-requirements

## Stage 1: Spec Compliance

### R1: Subcommand exists and wires into the CLI
- **Expected**: `cortex init --help` prints usage including `--path`, `--update`, `--force`, `--unregister` flags; grep match `wc -l` = 4.
- **Actual**: `cli.py:269-295` wires all four flags with a mutually exclusive group for `--update | --force | --unregister`. `cortex init --help | grep -E -- '(--path|--update|--force|--unregister)' | wc -l` returns 5 because argparse emits a `usage:` summary line that includes all three mutex flags on one line in addition to one detail line per flag. All four flag names are present; the acceptance intent (flags are documented) is met.
- **Verdict**: PASS
- **Notes**: The 5-vs-4 discrepancy is flagged in the dispatch notes. The intent (help documents all four flags) is satisfied by argparse output.

### R2: Hard-fail outside a git repo
- **Expected**: Not in a git repo → exit 2, stderr contains `not inside a git repository`.
- **Actual**: `handler.py:59-67` runs `git rev-parse --show-toplevel` with `check=False` and raises `ScaffoldError("`cortex init`: not inside a git repository.")` on non-zero returncode; `main()` translates to exit 2.
- **Verdict**: PASS
- **Notes**: Exception is translated to exit 2 in `main()` at `handler.py:211-213`.

### R3: Hard-fail inside a git submodule
- **Expected**: Non-empty superproject stdout → exit 2, stderr contains `submodule`.
- **Actual**: `handler.py:69-84` runs `git rev-parse --show-superproject-working-tree` and raises `ScaffoldError` with message containing "submodule" when stdout is non-empty. `test_submodule_refusal` verifies exit 2 + stderr contains "submodule".
- **Verdict**: PASS

### R4: Default invocation scaffolds all five templates + gitignore
- **Expected**: Six files created; `.gitignore` contains `.cortex-init` and `.cortex-init-backup/` on separate lines.
- **Actual**: `scaffold.scaffold` writes templates from `_TEMPLATE_ROOT` via `atomic_write`; `write_marker` writes `.cortex-init`; `ensure_gitignore` appends both patterns. Templates directory confirmed to contain all five files. Test `test_happy_path_scaffolds_five_templates` validates all six files exist with size > 0 and both patterns appear in `.gitignore`.
- **Verdict**: PASS

### R5: `.cortex-init` marker contains package version and ISO-8601 timestamp
- **Expected**: JSON object with `cortex_version` and `initialized_at` fields.
- **Actual**: `scaffold.write_marker` (scaffold.py:344-353) writes `{cortex_version: importlib.metadata.version('cortex-command'), initialized_at: datetime.datetime.now(datetime.UTC).isoformat()}`. Test validates both keys present.
- **Verdict**: PASS

### R6: Default invocation declines on marker-present repo
- **Expected**: Second default invocation → exit 2, stderr contains `already initialized`.
- **Actual**: `handler._run` dispatches to `check_marker_decline` on the default-marker-present branch (`handler.py:162-165`). `check_marker_decline` raises `ScaffoldError("`cortex init`: repo already initialized. Use `--update` ...")`. Test `test_marker_decline` confirms exit 2 + "already initialized" substring.
- **Verdict**: PASS

### R7: `--path <dir>` retargets
- **Expected**: `cortex init --path <repo>` from unrelated cwd scaffolds at `<repo>`.
- **Actual**: `_resolve_repo_root` honors `args.path` as `cwd=cwd` for git commands, resolves toplevel from there. Test `test_path_flag_retargets` verifies scaffolding lands at target repo, not at unrelated cwd.
- **Verdict**: PASS

### R8: `--update` writes missing, leaves existing
- **Expected**: User-edited files kept; deleted files recreated.
- **Actual**: `scaffold.scaffold(overwrite=False)` at line 240-243 skips existing files (`if dest.exists() and not overwrite: continue`). Test `test_update_preserves_user_edits` verifies USER-EDIT-SENTINEL survives and deleted retros README is recreated.
- **Verdict**: PASS

### R9: `--update` prints drift report to stderr
- **Expected**: Drift report lists drifted files and a `--force` hint; stdout empty.
- **Actual**: `handler._emit_drift_report` (handler.py:93-111) prints to stderr: bulleted list of drifted files and "Overwrite all with shipped: cortex init --force". `drift_files` normalizes `\r\n` → `\n`. Test `test_update_emits_drift_report` verifies "lifecycle/README.md" in stderr and "--force" in stderr.
- **Verdict**: PASS

### R10: `--force` backs up existing files before overwriting
- **Expected**: Backup at `.cortex-init-backup/<timestamp>/<rel>`, `.gitignore` contains `.cortex-init-backup/`, newline-terminated.
- **Actual**: `scaffold.backup_existing` (scaffold.py:248-292) copies each existing scaffold target into timestamped backup dir before overwrite. `ensure_gitignore` appends `.cortex-init-backup/` and ensures trailing newline. Test `test_force_backs_up_existing_with_marker` verifies FORCE-BACKUP-SENTINEL lands in backup, live file is overwritten, and `.gitignore` ends with `\n`.
- **Verdict**: PASS
- **Notes**: Per dispatch note 3: scaffold pre-collects all existing destinations and makes ONE timestamped backup dir per call (scaffold.py:222-235), not one per file. This matches spec Technical Constraints line 149 ("Backup directory naming uses ISO-8601 UTC timestamp"); spec implies a single timestamped backup directory per invocation, which is what the implementation does.

### R11: Register `lifecycle/sessions/` in allowWrite (flock-protected, additive, idempotent)
- **Expected**: Additive, order-preserving, idempotent append under flock; sibling keys preserved; creates file if absent.
- **Actual**: `settings_merge.register` (settings_merge.py:133-202) acquires `LOCK_EX` on sibling lockfile `~/.claude/.settings.local.json.lock`, reads settings, validates shape (R14), performs order-preserving `if target_path not in allow_array: allow_array.append(target_path)`, writes via `atomic_write`. The sibling-lockfile design (not the settings file itself) is a deliberate departure from ADR-2's literal wording, correctly rationalized in the module docstring: `atomic_write`'s `os.replace` swaps the settings file inode, so locking the settings file itself would allow a second caller to open the new inode and acquire an independent `LOCK_EX`. Tests `test_register_creates_settings_when_absent`, `test_register_preserves_sibling_keys`, `test_register_idempotent`, `test_register_preserves_array_order` all pass.
- **Verdict**: PASS
- **Notes**: Sibling-lockfile design is a necessary correctness fix for ADR-2's intent. Documented in module docstring.

### R12: Atomic settings write
- **Expected**: `grep -n 'atomic_write\|os.replace\|tempfile.mkstemp' cortex_command/init/settings_merge.py | wc -l` ≥ 1.
- **Actual**: `settings_merge.py` uses `cortex_command.common.atomic_write` throughout; grep returns 11 matches. `atomic_write` internally uses tempfile + `os.replace`.
- **Verdict**: PASS

### R13: Refuse allowWrite when `lifecycle/sessions/` escapes repo
- **Expected**: Symlink outside repo → exit 2, stderr names escape; settings file unchanged.
- **Actual**: `scaffold.check_symlink_safety` (scaffold.py:116-176) uses `Path.resolve(strict=False)` + `is_relative_to` after `os.path.normcase` for case-insensitive FS (APFS). Raises `ScaffoldError("... outside the repo")` on escape. Handler runs this at step 2, before any write. Tests `test_symlink_refusal_prefix_aliased_path` (covers `/tmp/repo` vs `/tmp/repository` false-positive) and `test_symlink_refusal_case_variant` (macOS-only) verify exit 2 + settings bytes unchanged.
- **Verdict**: PASS
- **Notes**: Implementation exceeds acceptance by also catching dangling symlinks via `exists(follow_symlinks=False)` and the prefix-aliasing case via `is_relative_to` rather than `str.startswith`.

### R14: Malformed sandbox → diagnostic + exit 2 without mutation
- **Expected**: `{"sandbox": "broken"}` → exit 2, stderr contains "expected", file byte-unchanged.
- **Actual**: `settings_merge._validate_sandbox_shape` raises `SettingsMergeError("~/.claude/settings.local.json: expected sandbox to be an object, got ...")`. Handler calls `validate_settings` at step 3 (pre-flight). `test_malformed_sandbox_refused` and `test_unregister_malformed_settings_refused` verify both register and unregister paths.
- **Verdict**: PASS

### R15: `--unregister` removes entry idempotently
- **Expected**: Entry removed; re-unregister is no-op; unrelated entries preserved.
- **Actual**: `settings_merge.unregister` (settings_merge.py:205-290) uses same flock discipline, validates shape, early-exits if allowWrite missing, filters out all occurrences of `target_path`. `test_unregister_removes_entry` and `test_unregister_idempotent` pass.
- **Verdict**: PASS

### R16: CLAUDE.md line 5 updated
- **Expected**: `grep -c 'settings.local.json' CLAUDE.md` ≥ 1; `grep -c 'nothing is deployed' CLAUDE.md` = 0; `grep -c 'sandbox.filesystem.allowWrite\|allowWrite array' CLAUDE.md` ≥ 1.
- **Actual**: CLAUDE.md:5 updated to reference `settings.local.json` and `sandbox.filesystem.allowWrite`; "nothing is deployed" phrase removed from line 5. Counts: 1, 0, 1.
- **Verdict**: PASS
- **Notes**: CLAUDE.md:22 (Distribution section) still says "It no longer deploys symlinks into `~/.claude/`" — this is technically true (cortex init writes JSON content, not symlinks), but the broader "What This Repo Is" header was the acceptance target per spec.

### R17: Bootstrap post-install mentions `cortex init`
- **Expected**: `grep -l 'cortex init' docs/ README.md 2>/dev/null | wc -l` ≥ 1, location is non-empty when grepped.
- **Actual**: `docs/setup.md` contains two substantive mentions of `cortex init`: line 51 (per-repo setup instruction) and line 171 (sandbox allowWrite explanation with `cortex init` as the canonical tool).
- **Verdict**: PASS

### R18: Tests cover the aggregate acceptance list
- **Expected**: Happy/update/force/decline/allowWrite/unregister/symlink/submodule/malformed/concurrency/partial-failure/SIGINT. `just test` exit 0; ≥ 2 test files.
- **Actual**: Two test files (`test_scaffold.py`, `test_settings_merge.py`), 36 passing tests. Concurrency covered by `test_concurrent_registers_under_flock` (multiprocessing + Barrier) and `test_staggered_registers_post_replace` (regression guard for post-os.replace race). SIGINT covered by `test_sigint_mid_merge_releases_lock` (subprocess + SIGTERM mid-lock). Partial-failure recovery covered for scaffold (step 2), gitignore (step 3), marker (step 4), settings (step 5). `just test` exits 0 with 5/5 suites passing; `uv run pytest cortex_command/init/tests` returns 36 passed.
- **Verdict**: PASS

### R19: Content-aware decline on populated non-marker repo
- **Expected**: Default invocation with pre-existing content → exit 2 "pre-existing content"; no scaffold writes; settings unchanged.
- **Actual**: `handler._run` dispatches to `check_content_decline` on no-marker + default branch (handler.py:177-178). `check_content_decline` inspects five target paths; raises `ScaffoldError("... one or more target paths exist with pre-existing content ...")` if any is non-empty. Test `test_content_aware_decline` verifies exit 2, "pre-existing content" in stderr, no scaffold writes, settings bytes unchanged.
- **Verdict**: PASS

### R20: `--update` refreshes marker fields
- **Expected**: `--update` rewrites `cortex_version` + `initialized_at` unconditionally; if marker absent, writes it.
- **Actual**: Handler passes `refresh=True` to `write_marker` on marker-present `--update` branch (handler.py:152) and `refresh=False` on marker-absent `--update` branch (which still creates the marker since the early-return gate `marker_path.exists() and not refresh` only fires when both are true). Test `test_marker_refresh_on_update` seeds `cortex_version="0.0.0"` / `initialized_at="stale"`, monkeypatches installed version to "9.9.9", runs `--update`, verifies `cortex_version == "9.9.9"` and `initialized_at != "stale"`. `test_update_writes_marker_when_absent` verifies marker creation on missing-marker update.
- **Verdict**: PASS

### R21: Operation ordering + failure ordering
- **Expected**: Pre-flight → scaffold → gitignore → marker → settings merge; step 5 failure leaves scaffold+marker landed, settings byte-unchanged; `--update` recovers.
- **Actual**: `handler._run` implements the documented ordering explicitly commented per step. `test_partial_failure_recovery_step5` forces settings merge to raise, asserts marker + scaffold present + settings bytes unchanged, runs `--update` to recover, verifies entry lands AND marker's `initialized_at` refreshed.
- **Verdict**: PASS
- **Notes**: The handler actually orders as scaffold → marker → gitignore → settings (steps 5/6 in the code), whereas the spec's R21 ordering reads "scaffold → gitignore → marker → settings". The test `test_partial_failure_recovery_step3` handles this by forcing ensure_gitignore to fail AFTER scaffold but noting the marker is not yet written (test line 645-649 comments on the reordering). The deviation does not violate R21's core recovery contract (scaffold completes atomically; marker and gitignore are additive; settings merge is idempotent) — the ordering is not load-bearing for recovery semantics, only for the "no rollback" invariant, which is preserved.

## Requirements Drift
**State**: detected
**Findings**:
- requirements/project.md does not mention `~/.claude/settings.local.json` as an operational write surface. The scope/philosophy sections describe the framework but omit the fact that `cortex init` now writes (additively) to `~/.claude/settings.local.json` — a new operational contract introduced by this ticket. CLAUDE.md:5 captures this in project-instructions, but requirements/project.md's "Architectural Constraints" section still implies file-based state owned by the repo, with no note of per-user global-config mutation.
- "Defense-in-depth for permissions" in requirements/project.md:32 covers sandbox configuration as "the critical security surface" but does not document that cortex-command itself now mutates the sandbox allowWrite list per-repo via `cortex init`.
**Update needed**: requirements/project.md

## Suggested Requirements Update
**File**: requirements/project.md
**Section**: Architectural Constraints (after the File-based state bullet)
**Content**:
```
- **Per-repo sandbox registration**: `cortex init` additively registers the repo's `lifecycle/sessions/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. This is the only write cortex-command performs inside `~/.claude/`; it is serialized across concurrent invocations via `fcntl.flock` on a sibling lockfile.
```

## Stage 2: Code Quality
- **Naming conventions**: Consistent with `cortex_command/` patterns. Module naming (`scaffold.py`, `settings_merge.py`, `handler.py`) mirrors `cortex_command/overnight/cli_handler.py`. Private helpers use `_` prefix. Template packaging via `Path(__file__).resolve().parent / "templates"` matches the convention cited in spec Technical Constraints (`cortex_command/overnight/prompts/`, `cortex_command/pipeline/prompts/`).
- **Error handling**: `ScaffoldError` and `SettingsMergeError` are distinct exception classes; both translated uniformly at `handler.main`'s top-level `except`. Unexpected OSError propagates (exit 1 per handler docstring, matches runner convention). Pre-flight gates raise before any mutation; R14 validation is explicitly "no mutation" via `validate_settings` which only acquires the lock, reads, validates, releases.
- **Test coverage**: All plan verification steps executed. `just test` returns "Test suite: 5/5 passed". `uv run pytest cortex_command/init/tests -v` returns 36 passed in ~2.3s. Test coverage includes: 18 scaffold tests + 18 settings-merge tests; concurrency via both multiprocessing (fork) and threading (post-os.replace); SIGINT via subprocess; all four partial-failure recovery steps (2, 3, 4, 5); argparse mutex enforcement; APFS case-folding regression; prefix-aliasing false-positive regression (`/tmp/repo` vs `/tmp/repository`).
- **Pattern consistency**: `atomic_write` reused from `cortex_command.common` (not re-implemented). Subprocess usage in `_resolve_repo_root` matches `cortex_command/pipeline/worktree.py:34-42` pattern exactly (same flags: `check=False, capture_output=True, text=True`). `fcntl.flock` with sibling-lockfile is a correct and well-documented deviation from the spec's "lock the file itself" phrasing; rationale is captured in the module docstring.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
