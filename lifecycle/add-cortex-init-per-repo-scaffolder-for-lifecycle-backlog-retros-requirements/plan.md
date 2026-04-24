# Plan: add-cortex-init-per-repo-scaffolder-for-lifecycle-backlog-retros-requirements

## Overview

Build `cortex init` as a new `cortex_command/init/` subpackage that scaffolds five templates into a target git repo and additively registers `$(repo-root)/lifecycle/sessions/` in `~/.claude/settings.local.json` under `fcntl.flock`. Decomposed bottom-up: skeleton + test-infra wiring first, then the five template files, then scaffolder logic, then settings-merge logic, then argparse handler, then CLI wire-up, then tests and documentation. Ordering in `handler.py` enforces ADR-3 (pre-flight gates → scaffold → marker → settings merge) so partial failure recovers via `cortex init --update`.

## Tasks

### Task 1: Create init subpackage skeleton and test-infra wiring

- **Files**:
  - `cortex_command/init/__init__.py` (new, empty)
  - `cortex_command/init/tests/__init__.py` (new, empty)
  - `pyproject.toml` (modify — add `cortex_command/init/tests` to `[tool.pytest.ini_options] testpaths`)
  - `justfile` (modify — add `test-init` recipe after `test-overnight` and wire `run_test "test-init" just test-init` into the `test` recipe)
- **What**: Create the subpackage directory layout and wire the new test directory into both the pytest `testpaths` array and the aggregate `just test` recipe. No template files or runtime Python logic land here — this is the foundation subsequent tasks build on.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Package-data loading convention: `Path(__file__).resolve().parent / "templates"` (see `cortex_command/overnight/prompts/` loaded at `cortex_command/overnight/brain.py:103`). Hatch's default wheel build at `pyproject.toml:20-21` ships non-Python files inside `cortex_command/` with no extra wiring.
  - `pyproject.toml:24` `testpaths` currently includes `tests`, `cortex_command/dashboard/tests`, `cortex_command/pipeline/tests`, `cortex_command/overnight/tests` — append `cortex_command/init/tests` in the same inline-array style.
  - `justfile` test recipe at line ~385 uses pattern `run_test "<label>" just test-<subpkg>` — mirror `test-pipeline` / `test-overnight` shape exactly (see `justfile:360-370` for `test-pipeline` recipe body: `.venv/bin/pytest cortex_command/pipeline/tests/ -q` guarded by `.venv/bin/pytest` existence check).
- **Verification**: run `grep -c 'cortex_command/init/tests' pyproject.toml` — pass if count ≥ 1. Run `grep -c '^test-init:' justfile` — pass if count = 1 (confirms the recipe is wired without running pytest against an empty dir).
- **Status**: [x] complete

### Task 2: Ship the 5 template files

- **Files**:
  - `cortex_command/init/templates/lifecycle/README.md` (new)
  - `cortex_command/init/templates/backlog/README.md` (new)
  - `cortex_command/init/templates/retros/README.md` (new)
  - `cortex_command/init/templates/requirements/project.md` (new)
  - `cortex_command/init/templates/lifecycle.config.md` (new)
- **What**: Create the five shipped template files with minimum-viable stub content. No Python logic or test wiring — the templates are static data that the scaffolder (Task 3) will copy into target repos.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Template content per `research.md` §D6 (Template files content): `requirements/project.md` with `## Overview`, `## Philosophy of Work`, `## Architectural Constraints`, `## Quality Attributes`, `## Project Boundaries`, `## Conditional Loading` sections with TODO placeholders; `backlog/README.md` ~30 lines; `lifecycle/README.md` ~25 lines; `retros/README.md` ~15 lines; `lifecycle.config.md` frontmatter matches this repo's `lifecycle.config.md:1-10` with `type: other`, `test-command: echo "TODO: set test-command"`, commented-out `demo-commands`, and a TODO bullet under `## Review Criteria`.
  - Template root will be resolved at runtime via `Path(__file__).resolve().parent / "templates"` in `scaffold.py` (Task 3).
- **Verification**: run `ls cortex_command/init/templates/**/*.md cortex_command/init/templates/*.md 2>/dev/null | wc -l` — pass if count = 5.
- **Status**: [x] complete

### Task 3: Implement scaffold.py template materialization core

- **Files**:
  - `cortex_command/init/scaffold.py` (new)
- **What**: Produce the core scaffolder — walks `templates/`, writes each file via `cortex_command.common.atomic_write` only if absent on disk (additive baseline), writes the `.cortex-init` JSON marker with `cortex_version` + `initialized_at`, appends `.cortex-init` and `.cortex-init-backup/` to the repo's `.gitignore` (creating the file if absent; idempotent by pattern match). Covers R4, R5, R8 (additive), R20 (marker refresh on update).
- **Depends on**: [1, 2]
- **Complexity**: complex
- **Context**:
  - Reuse `from cortex_command.common import atomic_write` for every file write.
  - Template root resolution: `_TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"` (matches `cortex_command/overnight/brain.py:103`).
  - Marker schema: `{"cortex_version": importlib.metadata.version("cortex-command"), "initialized_at": datetime.datetime.now(datetime.UTC).isoformat()}` serialized with `json.dumps(data, indent=2) + "\n"`.
  - `.gitignore` idempotence **and orphan-prefix repair**: read existing content if file exists, then (a) scan for any line matching the regex `^\.cortex-init(?:-backup)?.*$` that is NOT exactly `.cortex-init` or `.cortex-init-backup/` (these are orphan-prefix fragments left by a prior partial write, e.g., `.cortex-init-backu` from a truncated append) — remove each orphan line (write back via `atomic_write` if any removals happened); then (b) check each target pattern (`.cortex-init`, `.cortex-init-backup/`) via line-exact membership, append missing patterns with leading `\n` if the last byte is not `\n` (newline-safety per R10's acceptance). The scan-and-repair step closes the partial-failure recovery gap where a previous run's truncated append would otherwise produce a permanently-malformed `.gitignore` on the next run.
  - Exposed signatures (consumed by Tasks 4, 5, 6, 9):
    - `def scaffold(repo_root: Path, *, overwrite: bool, backup_dir: Path | None) -> list[Path]` — returns list of files written (for stderr reporting).
    - `def write_marker(repo_root: Path, *, refresh: bool) -> None` — writes or refreshes `.cortex-init`.
    - `def ensure_gitignore(repo_root: Path) -> None` — idempotent append.
- **Verification**: run `.venv/bin/python -c "from cortex_command.init.handler import main; import argparse; ns = argparse.Namespace(path=None, update=False, force=False, unregister=False); print(callable(main))"` is not yet possible (handler lands in Task 9); instead run `.venv/bin/python -c "from cortex_command.init import scaffold; print(callable(scaffold.scaffold))"` — pass if stdout = `True`. Run `grep -c 'atomic_write\|write_marker\|ensure_gitignore\|def scaffold' cortex_command/init/scaffold.py` — pass if count ≥ 4.
- **Status**: [x] complete

### Task 4: Implement scaffold.py pre-flight gates (decline, content-aware, symlink)

- **Files**:
  - `cortex_command/init/scaffold.py` (modify — add gate functions)
- **What**: Add three pre-flight gate functions that `handler.py` will call before any filesystem mutation. Covers R6 (marker-present decline), R19 (content-aware decline on populated non-marker repos), R13 (symlink safety — refuse if `lifecycle/sessions/` resolves outside the repo root).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Gate return convention: each returns `None` on pass; raises `ScaffoldError(message: str)` (new exception class defined in this file) on fail. `handler.py` translates the exception to stderr + exit 2.
  - R6 gate — `check_marker_decline(repo_root: Path) -> None`: fire if `(repo_root / ".cortex-init").exists()`; message per spec ("`cortex init`: repo already initialized. Use `--update` to add missing templates or `--force` to overwrite.").
  - R19 gate — `check_content_decline(repo_root: Path) -> None`: fire if marker absent AND any of the five target scaffold paths exists non-empty (directory non-empty OR file present). Target paths: `lifecycle/`, `backlog/`, `retros/`, `requirements/`, `lifecycle.config.md`. Message per spec exactly ("`cortex init`: one or more target paths exist with pre-existing content (no `.cortex-init` marker). Run `cortex init --update` to add missing templates without overwriting, or `cortex init --force` to overwrite with backup.").
  - R13 gate — `check_symlink_safety(repo_root: Path) -> Path`: returns the **canonical `sessions/` path** as a resolved string with trailing slash — this value is threaded through to `settings_merge.register` (Task 9 step 8) so registration uses the exact path that was validated (closes the TOCTOU window between pre-flight resolve and the re-resolve that a separate `register` call would do). If `(repo_root / "lifecycle" / "sessions").exists()` (via `Path.exists(follow_symlinks=False)` or presence check tolerant of dangling symlinks), compute `sessions_canon = (repo_root / "lifecycle" / "sessions").resolve(strict=False)` and `root_canon = repo_root.resolve(strict=False)`, then check subpath containment **using `Path.is_relative_to()` (Python 3.12+) — not `str.startswith`**, because `str(/tmp/repository).startswith(str(/tmp/repo))` is True but `/tmp/repository` is NOT a subpath of `/tmp/repo`. Apply `os.path.normcase()` to both sides before the `is_relative_to` check on case-insensitive filesystems (APFS on macOS preserves case but compares case-insensitively; `Path.resolve` does NOT normalize case). Fire `ScaffoldError` if `sessions_canon.is_relative_to(root_canon)` is False (message includes `outside the repo`). If `lifecycle/sessions/` does not exist, skip resolution and return `str((repo_root / "lifecycle" / "sessions")) + "/"` (non-canonical is acceptable when the path does not exist yet — registration will match what the future-created directory resolves to as long as ancestor canonicalization is consistent; see Task 9 step 1 for the handler-level `repo_root.resolve()` invariant that makes this consistent).
- **Verification**: run `grep -c 'check_marker_decline\|check_content_decline\|check_symlink_safety\|ScaffoldError' cortex_command/init/scaffold.py` — pass if count ≥ 4.
- **Status**: [x] complete

### Task 5: Implement scaffold.py drift report and marker refresh for --update

- **Files**:
  - `cortex_command/init/scaffold.py` (modify — add drift function, update marker-write for `--update` path)
- **What**: Add `drift_files(repo_root: Path) -> list[Path]` that returns scaffold target paths whose on-disk bytes (after `\r\n`→`\n` normalization) differ from the shipped template, and ensure `write_marker(..., refresh=True)` overwrites `.cortex-init` with the current package version + fresh timestamp. Covers R9 (drift report) and R20 (marker refresh under `--update`).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - `drift_files` reads shipped bytes from `_TEMPLATE_ROOT / <relative-path>` and disk bytes from `repo_root / <relative-path>`; normalizes both `content.replace(b"\r\n", b"\n")` then compares with `==`. Returns paths relative to `repo_root`.
  - `handler.py` will format the drift list per R9's acceptance: bulleted stderr lines (one per path) + a hint line containing `--force`. Format example in `research.md` §D8.
  - `write_marker` already exists from Task 3; Task 5 just verifies the `refresh=True` branch (called from `--update`) rewrites with today's version/timestamp unconditionally. Acceptance R20 is fixture-injected package version.
- **Verification**: run `grep -c 'def drift_files' cortex_command/init/scaffold.py` — pass if count = 1. Run `grep -c 'replace.*\\\\r\\\\n\|\\\\r\\\\n' cortex_command/init/scaffold.py` — pass if count ≥ 1 (line-ending normalization present).
- **Status**: [x] complete

### Task 6: Implement scaffold.py --force backup path

- **Files**:
  - `cortex_command/init/scaffold.py` (modify — add backup helper, extend `scaffold()` overwrite path)
- **What**: Before `--force` overwrites any of the five scaffold targets, copy each existing target's current content to `.cortex-init-backup/<UTC-timestamp>/<relative-path>/` using `atomic_write`. `.gitignore` pattern `.cortex-init-backup/` was already added in Task 3's `ensure_gitignore`; this task verifies the pattern is present and idempotently re-appends if not (same function reused). Covers R10.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Backup directory naming: `.cortex-init-backup/<iso-timestamp-utc>/` with colons replaced by hyphens: `datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")` (per spec Technical Constraint "Backup directory naming").
  - Signature: `def backup_existing(repo_root: Path, *, targets: Iterable[Path]) -> Path` — returns the backup directory path for stderr logging.
  - Extend `scaffold(..., overwrite=True, backup_dir=...)` to call `backup_existing` before writing each file whose destination already exists on disk.
  - Edge cases to handle: `.gitignore` absent (R10 edge case — create with single line `.cortex-init-backup/`), pattern already present (no duplicate), trailing newline preservation.
- **Verification**: run `grep -c 'def backup_existing\|cortex-init-backup\|%Y-%m-%d' cortex_command/init/scaffold.py` — pass if count ≥ 2.
- **Status**: [x] complete

### Task 7: Implement settings_merge.py flock-protected additive merge

- **Files**:
  - `cortex_command/init/settings_merge.py` (new)
- **What**: Add the `~/.claude/settings.local.json` merge — acquires `fcntl.flock` on a stable sibling lockfile (`~/.claude/.settings.local.json.lock`, NOT on `settings.local.json` itself), reads JSON (creating `{}` if file absent), pre-validates `.sandbox` and `.sandbox.filesystem` are objects (or translates to a clear diagnostic), additively appends the **caller-supplied canonical** `<repo-root>/lifecycle/sessions/` path to `sandbox.filesystem.allowWrite` with order-preserving `in` check, and writes via `atomic_write`. Covers R11, R12, R14, ADR-2 (this task's sibling-lockfile choice supersedes the spec ADR-2 line that reads "Lock file is `settings.local.json` itself (same inode)" — rationale in Context below).
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Exposed signatures (consumed by Task 8 and Task 9):
    - `def register(repo_root: Path, target_path: str, *, home: Path | None = None) -> None` — caller supplies the already-resolved, canonicalized `target_path` (trailing slash). `repo_root` retained for diagnostic messages only.
    - `def validate_settings(home: Path | None = None) -> None` — pre-flight-only R14 gate. Acquires the lockfile, opens `settings.local.json` if present, validates `.sandbox` and `.sandbox.filesystem` are objects (or absent), releases the lock. No mutation. Raises `SettingsMergeError` on malformation. Called from Task 9 step 3.
  - Settings path: `(home or Path.home()) / ".claude" / "settings.local.json"`. `(home or Path.home()) / ".claude"` is `mkdir -p`'d before any write (edge case "`~/.claude/` does not exist").
  - **Sibling lockfile** (rationale, critical): `atomic_write` performs `os.replace(tmp_path, settings_path)` which swaps the inode at `settings.local.json`. `fcntl.flock` is an advisory lock on a specific inode — a second caller that opens `settings.local.json` after a first caller's `os.replace` gets an fd on the NEW inode and acquires an independent (non-contending) `LOCK_EX`. To actually serialize concurrent callers, the lock must be on a stable inode that `atomic_write` never replaces. Use `~/.claude/.settings.local.json.lock` (create-on-first-use, `0o600`, persistent). `fcntl.flock` on the lockfile's fd contends for all callers regardless of how many `os.replace`s happen on the target.
  - Flock acquisition: `lock_fd = os.open(lockfile_path, os.O_RDWR | os.O_CREAT, 0o600)`, `fcntl.flock(lock_fd, fcntl.LOCK_EX)`, perform read + validate + mutate + `atomic_write`, release via `os.close(lock_fd)` in a `try/finally`. The lockfile itself contains no payload.
  - Malformed-type check (R14): after `json.loads`, if `data.get("sandbox")` exists but is not a `dict`, raise `SettingsMergeError` with message `~/.claude/settings.local.json: expected sandbox to be an object, got <type>`. Likewise for `sandbox.filesystem`. Handler translates to exit 2.
  - Invalid-JSON handling (edge case from spec): `json.JSONDecodeError` re-raised as `SettingsMergeError("settings.local.json: invalid JSON at line X:Y")`.
  - Idempotent append: `if target_path not in allow_array: allow_array.append(target_path)` — do not use `set()` (would reorder).
- **Verification**: run `grep -c 'fcntl.flock\|LOCK_EX' cortex_command/init/settings_merge.py` — pass if count ≥ 2. Run `grep -c 'atomic_write\|os.replace' cortex_command/init/settings_merge.py` — pass if count ≥ 1. Run `grep -c '\.lock\|lockfile_path\|\.settings\.local\.json\.lock' cortex_command/init/settings_merge.py` — pass if count ≥ 1 (confirms sibling lockfile is used rather than locking the settings file directly). Run `grep -c 'def validate_settings' cortex_command/init/settings_merge.py` — pass if count = 1.
- **Status**: [x] complete

### Task 8: Implement settings_merge.py --unregister path

- **Files**:
  - `cortex_command/init/settings_merge.py` (modify — add `unregister()` function)
- **What**: Add `unregister(repo_root: Path, target_path: str, *, home: Path | None = None) -> None` — same sibling-lockfile flock discipline as `register`, but removes the caller-supplied canonical `target_path` from `sandbox.filesystem.allowWrite` if present. Idempotent (absent entry is a no-op success). Preserves unrelated entries and sibling keys. Covers R15 and ADR-2 for unregister.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**:
  - Mirrors `register` exactly: acquire sibling-lockfile flock, read, validate sandbox/filesystem types (same diagnostics as R14), mutate, atomic_write. Caller supplies the canonical `target_path`; no re-resolution inside this function.
  - Removal: `allow_array = [e for e in allow_array if e != target_path]` preserves order.
  - No-op early-exit when file absent or key absent (do not create an empty settings file on unregister).
- **Verification**: run `grep -c 'def unregister' cortex_command/init/settings_merge.py` — pass if count = 1.
- **Status**: [x] complete

### Task 9: Implement handler.py — argparse + ADR-3 ordering

- **Files**:
  - `cortex_command/init/handler.py` (new)
- **What**: The argparse entry point called from `cli.py`. Defines flags `--path`, `--update`, `--force`, `--unregister`; resolves the target repo root via `git rev-parse --show-toplevel` (R2) and refuses submodules via `git rev-parse --show-superproject-working-tree` (R3); runs pre-flight gates in ADR-3 order; dispatches to `scaffold` / `drift_files` / `backup_existing` / `settings_merge.register|unregister` in the mandated sequence; emits stderr drift report for `--update`. Covers R1, R2, R3, R7, R21.
- **Depends on**: [4, 5, 6, 7, 8]
- **Complexity**: complex
- **Context**:
  - Entry point signature: `def main(args: argparse.Namespace) -> int` (matches stub replacement in Task 10).
  - Flag definitions attached to the subparser in Task 10 (cli.py wire). Handler expects `args.path`, `args.update`, `args.force`, `args.unregister` attributes.
  - Mutually exclusive flag pairs (argparse-enforced in Task 10, documented here): `--update` and `--force`; `--unregister` runs alone and skips scaffold/marker entirely (registers-only inverse path).
  - Git-repo resolution per spec Technical Constraints: `subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path, check=False, capture_output=True, text=True)`; non-zero returncode → stderr "not inside a git repository" + exit 2. Matches `cortex_command/pipeline/worktree.py:34-42` exactly (adapt `check=True` to `check=False`).
  - Submodule check (R3): `subprocess.run(["git", "rev-parse", "--show-superproject-working-tree"], ...)`; non-empty stdout → stderr "cortex init should run at the top-level repo, not inside a submodule" + exit 2.
  - ADR-3 ordering inside `main`:
    0. **`--unregister` early-branch** (resolved Ask item): `--unregister` is semantically a settings-cleanup verb, not a repo operation, so it skips the git-repo gates (R2/R3) to support cleanup of entries for already-deleted repos. Handler: compute `resolved_path = Path(args.path or os.getcwd()).resolve()` (no git check), `target_path = str(resolved_path / "lifecycle" / "sessions") + "/"`, call `settings_merge.validate_settings(home)` for the R14 pre-flight, call `settings_merge.unregister(resolved_path, target_path)`, return 0. The unregister function is idempotent — an entry that is not present (e.g., the deleted repo's resolved path differs from what was stored due to intervening symlink changes) is a silent no-op success. Skip `check_symlink_safety` on this path: there is no scaffolding to guard, and the path may no longer exist.
    1. For all other verbs: resolve `repo_root` via `git rev-parse --show-toplevel` and then `Path(raw).resolve()` (R2 + R3 gates run here). The resolved `repo_root` is threaded through **every** subsequent step — no step calls `resolve()` independently. This closes the TOCTOU gap between the pre-flight symlink-safety resolve and the registration re-resolve.
    2. Run `check_symlink_safety(repo_root)` (R13). **Capture the returned canonical `sessions_target` string** (Task 4 returns it); pass this exact value into `settings_merge.register` at step 8 — register does NOT re-resolve.
    3. Pre-flight malformed-settings validation (R14) — call `settings_merge.validate_settings(home)` (a standalone pre-flight-only function exposed by Task 7, NOT inlined into `register`). Acquires the sibling lockfile, reads + validates, releases. No mutation. Raises `SettingsMergeError` on malformation. This ensures the R14 gate fires before any repo write (ADR-3 step 1).
    4. If marker present: branch on `--update` (drift + additive scaffold + marker refresh) / `--force` (backup + overwrite scaffold + marker refresh) / default (R6 decline).
    5. Otherwise (no marker): branch on `--update` (additive scaffold + marker write) / `--force` (R19 does NOT fire; backup + overwrite + marker) / default (R19 content-aware decline check, then additive scaffold + marker write).
    6. Call `scaffold.ensure_gitignore(repo_root)`.
    7. Call `settings_merge.register(repo_root, sessions_target)` last.
  - Exit codes: 0 on success, 2 on any user-correctable failure (gate fires, malformed settings, not-a-repo, submodule, clobber), 1 on unexpected runtime failure (disk full, permission error at write time). `ScaffoldError` and `SettingsMergeError` are caught at `main`'s top level and translated to stderr + exit 2.
  - Drift report (R9): after additive scaffold under `--update`, call `drift_files(repo_root)`; if non-empty, emit to stderr in the format from `research.md` §D8 (one bullet per drifted path + hint line mentioning `--force`).
- **Verification**: run `.venv/bin/python -c "from cortex_command.init.handler import main; import argparse; ns = argparse.Namespace(path=None, update=False, force=False, unregister=False); print(callable(main))"` — pass if stdout = `True`.
- **Status**: [x] complete

### Task 10: Wire init handler into cli.py

- **Files**:
  - `cortex_command/cli.py` (modify — lines 63-68 replace stub; add flag definitions)
- **What**: Replace `init.set_defaults(func=_make_stub("init"))` at `cli.py:68` with a call to the real handler. Add `--path`, `--update`, `--force`, `--unregister` flag definitions to the `init` subparser with an argparse mutually-exclusive group for `--update` / `--force`. Covers R1 acceptance (`--help` shows all four flags).
- **Depends on**: [9]
- **Complexity**: simple
- **Context**:
  - Insert `from cortex_command.init.handler import main as init_main` at the top of `cli.py` (imports block, line ~13).
  - On the `init` subparser (cli.py:63-68), add:
    - `init.add_argument("--path", default=None, help="Target repo root (defaults to CWD)")`
    - **A single mutually-exclusive group containing all three verb flags: `--update`, `--force`, AND `--unregister`** — argparse enforces the documented "at most one of these" invariant. Rejecting `--unregister --update` and `--unregister --force` at argparse time is the only way to keep Task 9 step 4's "return 0 after unregister" from silently discarding the `--update`/`--force` intent.
    - `init.set_defaults(func=init_main)` (replacing the stub line).
  - No other subcommand changes — `overnight`, `mcp-server`, `upgrade` stubs remain untouched.
- **Verification**: run `.venv/bin/cortex init --help 2>&1 | grep -E -- '(--path|--update|--force|--unregister)' | wc -l` — pass if count = 4 (R1 acceptance).
- **Status**: [x] complete

### Task 11: Write scaffold tests

- **Files**:
  - `cortex_command/init/tests/test_scaffold.py` (new)
- **What**: Cover scaffold-side acceptance criteria: happy path (R4 + R5), `--update` additive semantics (R8), drift report (R9), `--force` backup (R10), marker decline (R6), symlink refusal (R13), submodule refusal (R3), content-aware decline (R19), marker refresh (R20), `--path` retargeting (R7), `.gitignore` append. Exercises R18 (subset).
- **Depends on**: [10]
- **Complexity**: complex
- **Context**:
  - Fixture pattern: `tmp_path` + `subprocess.run(["git", "init", str(tmp_path)], check=True)` at the start of each test.
  - Test functions name pattern: `test_happy_path_scaffolds_five_templates`, `test_update_preserves_user_edits`, `test_update_emits_drift_report`, `test_force_backs_up_existing_with_marker`, `test_force_overwrites_no_marker_populated`, `test_update_writes_marker_when_absent`, `test_update_on_empty_repo_acts_like_default`, `test_marker_decline`, `test_content_aware_decline`, `test_symlink_refusal_prefix_aliased_path` (covers the `/tmp/repo` vs `/tmp/repository` false-positive case — asserts `str.startswith` semantics would fail but `is_relative_to` passes), `test_symlink_refusal_case_variant` (macOS-only skip on Linux; covers APFS case-folding), `test_submodule_refusal`, `test_path_flag_retargets`, `test_marker_refresh_on_update`, `test_gitignore_append_idempotent`, `test_gitignore_orphan_prefix_repair` (pre-populate `.gitignore` with `.cortex-init-backu` and assert the orphan is removed and the full patterns are present after `ensure_gitignore`), `test_partial_scaffold_update_recovery` (monkeypatch `scaffold.atomic_write` to raise after 3 of 5 files written; re-run with `--update`; assert missing 2 files land, existing files untouched — explicitly asserts the known gap around additivity not repairing truncated files and that the drift report surfaces any tainted files), `test_unregister_accepts_non_git_path` (Ask-item resolved: asserts `--unregister --path /some/non-git-dir` exits 0 after removing the entry; verifies step-0 early-branch bypasses R2/R3 git-repo gates).
  - Happy path calls `init_main(argparse.Namespace(path=str(tmp_path), update=False, force=False, unregister=False))` and asserts all five scaffold files + `.cortex-init` + `.gitignore` (with both patterns) exist.
  - Drift test (R9) uses `capsys.readouterr()` to assert stderr contains `lifecycle/README.md` and `--force` after hand-editing a template and running `--update`.
  - Submodule fixture: create a nested git repo inside a parent, make the parent reference it via `.gitmodules` (or simulate by creating `.git/config` with `submodule.*` entries). Alternative per research: stub `subprocess.run(["git", "rev-parse", "--show-superproject-working-tree"])` via `monkeypatch` to return non-empty stdout — simpler and less fragile than real submodule fixture.
  - Marker-decline test (R6) runs `init_main` twice and asserts the second invocation exits 2 with stderr containing `already initialized`.
  - Content-aware decline (R19): pre-populate `tmp_path / "lifecycle" / "unrelated.md"` before invocation; assert exit 2 + stderr `pre-existing content` + no scaffold files written.
  - Every test that might touch `~/.claude/` must use `monkeypatch.setenv("HOME", str(tmp_path))` plus a fresh `.claude/` directory. The scaffold tests must not exercise settings.local.json beyond verifying it remains unchanged when a scaffold gate fires (byte-for-byte snapshot compare).
- **Verification**: run `.venv/bin/pytest cortex_command/init/tests/test_scaffold.py -v` — pass if exit code = 0 and collected count ≥ 16.
- **Status**: [x] complete

### Task 12: Write settings_merge tests (flock, partial failure, SIGINT)

- **Files**:
  - `cortex_command/init/tests/test_settings_merge.py` (new)
- **What**: Cover settings-merge-side acceptance criteria: happy path (R11 fresh + pre-existing), atomic write marker (R12), malformed settings refusal (R14), unregister (R15), concurrency under flock (R18 requirement), partial failure recovery (R18 + R21), SIGINT mid-merge (R18 + ADR-2 spec edge case).
- **Depends on**: [10]
- **Complexity**: complex
- **Context**:
  - Fixture: `monkeypatch.setenv("HOME", str(tmp_path))` with `tmp_path / ".claude"` pre-created.
  - `test_register_creates_settings_when_absent` — call `register(repo_root)`; assert `settings.local.json` exists, contains the target path as the only entry.
  - `test_register_preserves_sibling_keys` — pre-populate settings.local.json with `{"sandbox": {"network": {"allowUnixSockets": ["/tmp/x"]}}, "permissions": {"allow": ["read"]}}`; call `register`; assert both sibling keys are byte-identical after the merge and the allowWrite array contains the new path.
  - `test_register_idempotent` — call `register` twice; assert allowWrite array length unchanged after second run.
  - `test_register_preserves_array_order` — pre-populate `allowWrite: ["a", "b"]`; call `register` with a new path `c`; assert order is `["a", "b", "<path>"]` (not `["<path>", "a", "b"]` and not lexicographic).
  - `test_malformed_sandbox_refused` — pre-populate `{"sandbox": "broken"}`; call `register`; assert `SettingsMergeError` raised or (if called via `init_main`) exit 2 + stderr contains `expected`. File unchanged byte-for-byte.
  - `test_invalid_json_refused` — pre-populate `settings.local.json` with `{not json`; assert clear error + file unchanged.
  - `test_unregister_removes_entry` — call `register` then `unregister`; assert target path absent; unrelated entries preserved.
  - `test_unregister_idempotent` — call `unregister` twice on a clean file; assert no error.
  - `test_unregister_malformed_settings_refused` — pre-populate `{"sandbox": "broken"}`; invoke `init_main` with `--unregister`; assert exit 2 + stderr contains `expected`, settings.local.json byte-unchanged (verifies ADR-3 step 3 pre-flight fires for the unregister path too, not just register).
  - `test_argparse_mutex_rejects_unregister_with_update` — invoke `init_main` with both `--unregister=True` and `--update=True`; assert argparse raises `SystemExit` with exit 2 (argparse's default for mutex violations). Verifies the documented "unregister runs alone" invariant is enforced, not just documented.
  - `test_concurrent_registers_under_flock` — use `multiprocessing.Pool` (or `threading.Thread` + worker function that calls `register` with a different repo_root each) to launch two concurrent `register` calls against the same `HOME`; after both complete, assert both target paths are present in the allowWrite array. Use a `multiprocessing.Barrier(2)` to maximize the race window. **This test exercises only the pre-`os.replace` contention case — see next bullet for the post-replace-reopen case.**
  - `test_staggered_registers_post_replace` — explicitly covers the race window the Barrier-based test cannot hit: stagger caller-B so caller-B's `os.open(settings.local.json)` happens AFTER caller-A's `atomic_write` has landed `os.replace`. Achievable by monkeypatching `atomic_write` to signal a `multiprocessing.Event` immediately after `os.replace` returns, and having caller-B block on that event before entering `register`. Assert both caller-A's entry and caller-B's entry land in the final `allowWrite`. Under the OLD design (lock on `settings.local.json` itself), caller-B would get a fresh lock on the new inode and could proceed concurrently with a caller-A still holding its lock on the old inode — but with the sibling-lockfile design (Task 7), caller-B blocks on the stable lockfile inode until caller-A releases. This test is the primary guard against regressing the sibling-lockfile choice.
  - `test_failed_caller_a_does_not_block_b_from_lock` — monkeypatch caller-A's `atomic_write` to raise `OSError` before `os.replace`; caller-A releases the lock via `finally`. Caller-B then acquires the lock and proceeds on the pre-A state; assert caller-A's attempted entry is NOT in the final file (expected narrower guarantee per the ADR-2 reframing in the Critical Review: "no lost-update race between two SUCCESSFUL callers"). This test documents the guarantee as tested, rather than overstating it.
  - `test_partial_failure_recovery_step5` — monkeypatch `settings_merge.atomic_write` to raise `OSError("disk full")` once; call `init_main` (full pipeline); assert scaffold files + marker exist, `settings.local.json` byte-unchanged, exit code ≠ 0 with stderr naming the failed op. Restore `atomic_write` behavior; call `init_main` with `--update`; assert settings now contains the entry AND the marker's `initialized_at` timestamp was refreshed (R20 + R21 acceptance path).
  - `test_partial_failure_recovery_step4` — monkeypatch `scaffold.write_marker` (step 4 of ADR-3) to raise; assert scaffold files present, `.cortex-init` absent, exit code ≠ 0. Restore and run `cortex init --update`; assert marker now exists and settings merge completed.
  - `test_partial_failure_recovery_step3` — monkeypatch `scaffold.ensure_gitignore` to raise; assert scaffold files present, `.gitignore` absent or incomplete, marker absent, exit code ≠ 0. Restore and run `cortex init --update`; assert `.gitignore` now contains both required patterns and marker landed. This test also exercises the orphan-prefix repair: pre-populate `.gitignore` with a truncated line like `.cortex-init-backu` and assert the recovery run removes the orphan.
  - `test_partial_failure_recovery_step2` — monkeypatch `scaffold.atomic_write` to raise after writing N=3 of 5 template files; assert exit code ≠ 0, 3 files present, 2 missing, marker absent. Restore and run `cortex init --update`; assert all 5 files present and marker landed. **Explicitly assert the drift report surfaces any pre-existing files** — the additivity gap is documented here rather than pretended to be closed.
  - `test_sigint_mid_merge_releases_lock` — spawn a subprocess that calls `register`, monkeypatches `atomic_write` to sleep 30s, and have the test `subprocess.terminate()` it after 0.1s. Verify that a subsequent in-test `register` call acquires the lock cleanly (no deadlock — `fcntl.flock` is process-scoped; kernel releases on SIGTERM). Assert either old bytes or new bytes on disk (no torn file). This is the ADR-2 / spec Edge Cases SIGINT scenario.
- **Verification**: run `.venv/bin/pytest cortex_command/init/tests/test_settings_merge.py -v` — pass if exit code = 0 and collected count ≥ 15.
- **Status**: [x] complete

### Task 13: Update CLAUDE.md and post-install documentation

- **Files**:
  - `CLAUDE.md` (modify — line 5)
  - `docs/setup.md` (modify — add `cortex init` post-install note) OR `README.md` if `docs/setup.md` lacks a relevant section; R17 requires at least one documented location.
- **What**: Narrow CLAUDE.md:5's absolute "nothing is deployed into `~/.claude/` by this repo" claim to reflect the single additive `sandbox.filesystem.allowWrite` write that `cortex init` registers per repo. Add a post-install message to either `docs/setup.md` or `README.md` documenting that `cortex init` must run once per target repo. Covers R16 and R17.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**:
  - R16 acceptance: `grep -c 'settings.local.json' CLAUDE.md` ≥ 1; `grep -c 'nothing is deployed' CLAUDE.md` = 0; `grep -c 'sandbox.filesystem.allowWrite\|allowWrite array' CLAUDE.md` ≥ 1.
  - Proposed CLAUDE.md:5 wording (user may revise at review time): "Ships as a CLI (`uv tool install -e .`) plus plugins installed via `/plugin install` in Claude Code; `cortex init` additionally writes one entry per repo into `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array to unblock interactive session writes to `lifecycle/sessions/`."
  - Post-install message (R17): add a short section to `docs/setup.md` titled "Per-repo setup" containing the single sentence "Run `cortex init` once in each repo where you want to use the overnight runner or interactive dashboard; this scaffolds `lifecycle/`, `backlog/`, `retros/`, `requirements/` templates and registers the repo's `lifecycle/sessions/` path in your sandbox allowWrite list." R17 acceptance: `grep -l 'cortex init' docs/ README.md 2>/dev/null | wc -l` ≥ 1.
- **Verification**: run `grep -c 'settings.local.json' CLAUDE.md` — pass if count ≥ 1. Run `grep -c 'nothing is deployed' CLAUDE.md` — pass if count = 0. Run `grep -c 'sandbox.filesystem.allowWrite\|allowWrite array' CLAUDE.md` — pass if count ≥ 1. Run `grep -rl 'cortex init' docs/ README.md 2>/dev/null | wc -l` — pass if count ≥ 1.
- **Status**: [x] complete

### Task 14: Full-suite verification

- **Files**: none modified (this task runs verification commands only; no code or docs land here).
- **What**: Run `just test` end-to-end and confirm all pre-existing suites plus the new `test-init` suite pass. Covers R18 aggregate acceptance.
- **Depends on**: [11, 12, 13]
- **Complexity**: trivial
- **Context**:
  - `just test` runs `just test-pipeline` + `just test-overnight` + `just test-init` + `pytest tests/` per the justfile wiring from Task 1.
  - If any suite fails, the remediation is to return to the failing task (11, 12, or a latent bug in an earlier task) and fix — not to modify `just test` or the tests themselves.
- **Verification**: run `just test` — pass if exit code = 0 (R18 aggregate acceptance).
- **Status**: [x] complete

## Verification Strategy

The feature is verified end-to-end by Task 14's `just test` run plus the following acceptance-criteria-tied smoke tests executed against a temporary git repo:

1. `cortex init --help | grep -cE -- '(--path|--update|--force|--unregister)'` = 4 (R1).
2. Inside a non-git directory, `cortex init; echo $?` = 2 (R2).
3. Inside a fresh `git init` repo, `cortex init; ls lifecycle/README.md backlog/README.md retros/README.md requirements/project.md lifecycle.config.md .cortex-init .gitignore; grep -c '.cortex-init$\|.cortex-init-backup/$' .gitignore` = 2 (R4).
4. `python3 -c "import json; d=json.load(open('.cortex-init')); assert 'cortex_version' in d and 'initialized_at' in d"` exits 0 (R5).
5. `cortex init; cortex init; echo $?` second-run = 2 (R6).
6. `cortex init --update` after editing `requirements/project.md` and deleting `retros/README.md` — assert `USER-EDIT-SENTINEL` preserved and `retros/README.md` recreated (R8).
7. Stderr of step 6 contains drifted file paths + `--force` hint (R9).
8. `cortex init --force` after editing `requirements/project.md` with `FORCE-BACKUP-SENTINEL` — assert `.cortex-init-backup/<timestamp>/requirements/project.md` contains the sentinel (R10).
9. With `HOME=$TMPDIR/fake-home`, `python3 -c "import json; d=json.load(open('$TMPDIR/fake-home/.claude/settings.local.json')); assert '$repo/lifecycle/sessions/' in d['sandbox']['filesystem']['allowWrite']"` exits 0 after `cortex init`; running `cortex init` twice does not duplicate the entry (R11).
10. `grep -n 'atomic_write\|os.replace\|tempfile.mkstemp' cortex_command/init/settings_merge.py | wc -l` ≥ 1 (R12).
11. Symlink-escape fixture → exit 2, stderr contains `outside the repo`, settings.local.json byte-unchanged (R13).
12. `{"sandbox": "broken"}` fixture → exit 2, stderr contains `expected`, settings.local.json byte-unchanged (R14).
13. `cortex init --unregister` after `cortex init` → entry removed; double-unregister exits 0 (R15).
14. CLAUDE.md grep checks from Task 13 verification (R16).
15. `grep -l 'cortex init' docs/ README.md` finds at least one match (R17).
16. `just test` exit 0 (R18 aggregate, tasks 11+12 collectively cover happy path, update, force, decline, merge-pre-existing + fresh, unregister, symlink refusal, submodule refusal, malformed settings, concurrency, partial failure, SIGINT).
17. Marker fixture at v0.1.0 → mock version to v0.2.0 → `cortex init --update` → marker `cortex_version` = `"0.2.0"` (R20).
18. Force settings merge to raise after scaffold; assert scaffold + marker present, settings unchanged, exit ≠ 0; follow-up `cortex init --update` lands the entry (R21).

## Veto Surface

- **Bundling `settings.local.json` registration under `cortex init` rather than a separate `cortex setup` revival.** ADR-1 narrows CLAUDE.md:5's absolute claim to a single per-repo additive write. If the user wants to separate the concerns (e.g., re-introduce a machine-scoped `cortex setup` that registers a single parent directory rather than per-repo entries), this plan as drafted will need to be split across two tickets.
- **14 tasks is larger than the typical 5–10 feature.** The scope is genuinely complex (5 templates × 21 requirements × concurrency + partial-failure cases). If the user prefers fewer commits, Tasks 4–6 could be merged into one "scaffold.py edge cases" task, Tasks 7–8 into one "settings_merge.py both directions" task, and Tasks 11–12 into a single "init tests" task — reducing the task count to 10 at the cost of per-task reviewability.

- **Resolved Ask items (from critical review; directions locked in)**:
  - **Mid-scaffold corruption recovery** — **accepted as documented**: `--update` stays strictly additive per R8. Drift report (R9) surfaces truncated-file divergence; user runs `--force` to repair. `test_partial_scaffold_update_recovery` (Task 11) and `test_partial_failure_recovery_step2` (Task 12) explicitly document the behavior.
  - **R20 marker provenance after upgrade + recovery** — **accepted as documented**: marker's `cortex_version` is effectively a "last cortex-init touched this repo" stamp. No new fields, no conditional stamping.
  - **`--unregister` against a deleted repo** — **resolved: skip the git gate**. Task 9 now has a step-0 early-branch for `--unregister` that bypasses R2/R3 and accepts any path string. `test_unregister_accepts_non_git_path` (Task 11) is no longer conditional.
  - **Forward-direction symlink bypass** — **accepted as documented**: Scope Boundaries bullet added. No runtime re-validation in the overnight runner as part of this ticket.
- **Sibling lockfile at `~/.claude/.settings.local.json.lock` (supersedes spec ADR-2's "lock on the file itself" phrasing).** Task 7 was revised during critical review: `fcntl.flock` on `settings.local.json` itself is defeated by `atomic_write`'s `os.replace` (the lock is per-inode, and `os.replace` swaps the inode, so a second caller opens a fresh inode and acquires a non-contending lock — the lost-update race ADR-2 targets is NOT prevented). The sibling lockfile has a stable inode that `atomic_write` never replaces, so `fcntl.flock(lock_fd, LOCK_EX)` serializes all callers correctly. The lockfile adds one on-disk artifact (`~/.claude/.settings.local.json.lock`, empty, `0o600`). The spec's ADR-2 prose needs a matching update during implementation (note added to Task 7's "supersedes" clause).
- **Drift report format is bulleted stderr, not JSON.** Per spec Non-Requirements, structured output is deferred. If the user wants `--json` from day one, add to scope.
- **Task 12's SIGINT test spawns a subprocess with mocked `atomic_write`.** This is the most complex test in the suite; a simpler approach is to rely on the documented `fcntl.flock` semantic ("kernel releases on process exit") and skip the active signal-delivery test. If the user wants to trim test scope, this is the first candidate to drop.
- **Post-install message location (Task 13) is either `docs/setup.md` or `README.md`.** The plan lets the implementer choose whichever is more natural; if the user prefers one location, say so at approval time.

## Scope Boundaries

Mirroring `spec.md` Non-Requirements:

- Opinionated project-type tailoring (`--type library`, `--type app`) is out of scope.
- Migration from existing non-cortex layouts — `cortex init` declines on populated non-marker repos; no merge/import verb for legacy content.
- Drift auto-merge on `--update` — `--update` is strictly additive; the drift report is read-only.
- `cortex upgrade` integration — whether upgrade propagates template updates across registered repos is deferred.
- Interactive confirmation prompts — `cortex init` never calls `input()`; `--force` is guarded only by the timestamped backup.
- Structured drift output (table, JSON) — deferred behind a future `--json` flag.
- jq-based merge — explicitly ruled out in ADR-1; use Python `json`.
- `--dry-run` mode — out of scope; the drift report is the read-only signal for `--update`.
- Revalidating registered paths for deleted repos — users run `--unregister` manually.
- **Post-init forward-direction symlink-swap revalidation** — `cortex init` validates `lifecycle/sessions/` at init time (R13); if the user later replaces the path with a symlink that escapes the repo, `allowWrite` grants the sandbox write access to the escape target. The overnight runner does not re-validate. This is the inverse of R13's reverse-direction check and is out of scope for this ticket (see Veto Surface Ask-item for option inventory).
- **~~`--unregister` against a path that is not a git repo~~** — Resolved: `--unregister` skips the git-repo gate (see Task 9 step-0 early-branch). Entries for already-deleted repos can be cleaned up via `cortex init --unregister --path <absolute-path>`.
- **Automatic repair of truncated template files in `--update` recovery** — `--update` is strictly additive per R8; a file present-but-corrupt from a prior mid-scaffold failure is permanently skipped. The drift report (R9) surfaces the divergence; the user runs `--force` to repair. Out of scope for this ticket (see Veto Surface Ask-item).
