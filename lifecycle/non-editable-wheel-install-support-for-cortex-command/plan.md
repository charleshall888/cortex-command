# Plan: non-editable-wheel-install-support-for-cortex-command

## Overview

Migrate the cortex CLI from editable clone-install to non-editable wheel-install via tag-pinned git URL, with the cortex-overnight-integration plugin's MCP server auto-installing the CLI on first tool call. The plan is structured around a **tag-before-coupling pivot** (Task 14): foundation tasks (1-6, 13, 16) land first; then `v0.1.0` is tagged and published; then plugin/install/doc tasks (7, 8, 9, 10, 11, 12) land — they reference `v0.1.0` only after the tag exists at the remote, eliminating the dangling-pointer window. `cortex --print-root` JSON envelope bumps to `version: "1.1"` and exposes both `root` (user's project, via `_resolve_user_project_root()`) and `package_root` (package install, for diagnostic introspection); spec R2d is amended accordingly. R8 throttle and R10 orchestration become dormant under wheel install — Task 16 short-circuits them explicitly because R4's first-install hook plus R13's schema-floor gate are the upgrade arrow. Sequencing of subsequent versions follows the same tag-before-coupling rule: bump pyproject.toml + CHANGELOG + push CLI tag → only then bump plugin's `CLI_PIN[0]` to reference the new tag.

## Tasks

### Task 1: Add `_resolve_user_project_root()` helper to `cortex_command/common.py`

- **Files**: `cortex_command/common.py`
- **What**: Define a single source of truth for "where does the user's cortex project live?" — returns `Path(os.environ["CORTEX_REPO_ROOT"])` when set, else `Path.cwd()` after a sanity check. Helper is a regular `def`, never a module-level constant.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Function signature: `def _resolve_user_project_root() -> Path:`
  - Sanity check (when env var unset): `if not (cwd / "lifecycle").is_dir() and not (cwd / "backlog").is_dir(): raise CortexProjectRootError(message)` — message text required by spec R3f: `"Run from your cortex project root, set CORTEX_REPO_ROOT, or create a new project here with \`git init && cortex init\` (cortex init requires a git repository)."`
  - Define `class CortexProjectRootError(RuntimeError)` near the helper for typed catch sites later.
  - Naming distinct from `cortex_command/init/handler.py:_resolve_repo_root` (git-based; reserved for `cortex init` dispatch) per spec Technical Constraints.
- **Verification**: `python3 -c "from cortex_command.common import _resolve_user_project_root, CortexProjectRootError; import os, tempfile; from pathlib import Path; d=tempfile.mkdtemp(); (Path(d)/'lifecycle').mkdir(); os.chdir(d); assert _resolve_user_project_root() == Path(d).resolve()"` — pass if exit 0. Plus `grep -E "_resolve_user_project_root|CORTEX_REPO_ROOT" cortex_command/common.py | wc -l` ≥ 2 — pass if count ≥ 2. Plus `grep -E "git init && cortex init|requires a git repository" cortex_command/common.py | wc -l` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 2: Convert package-internal `Path(__file__)` sites in `init/`, `pipeline/` to `importlib.resources`

- **Files**: `cortex_command/init/scaffold.py`, `cortex_command/pipeline/conflict.py`, `cortex_command/pipeline/review_dispatch.py`
- **What**: Replace `Path(__file__).parent / ...` constructs in three sites with `importlib.resources.files()` calls that resolve under both editable and non-editable installs.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `init/scaffold.py:45` (`Path(__file__).resolve().parent / "templates"`) → `importlib.resources.files("cortex_command.init.templates")`
  - `pipeline/conflict.py:29` (`parents[1] / "overnight/prompts/repair-agent.md"`) → `importlib.resources.files("cortex_command.overnight.prompts").joinpath("repair-agent.md")`
  - `pipeline/review_dispatch.py:86` (`parent / "prompts" / "review.md"`) → `importlib.resources.files("cortex_command.pipeline.prompts").joinpath("review.md")`
  - Pattern reference: `cortex_command/overnight/runner.py:33` and `cortex_command/overnight/fill_prompt.py:13-34` already use this idiom.
  - Use `.read_text(encoding="utf-8")` for consumers that read content; use `.joinpath(...)` and `.is_file()` / `.iterdir()` for directory traversal. Avoid `pathlib.Path`-only methods (`.stat()`, `.glob()`, `.resolve()`); if a real `pathlib.Path` is needed by an external API (e.g., Jinja2 loader paths), use `importlib.resources.as_file()`.
- **Verification**: `grep -rn "Path(__file__)" cortex_command/init/scaffold.py cortex_command/pipeline/conflict.py cortex_command/pipeline/review_dispatch.py | grep -v tests | wc -l` = 0 — pass if count = 0. Plus `python3 -c "from cortex_command.pipeline.review_dispatch import *; from cortex_command.pipeline.conflict import *; from cortex_command.init.scaffold import *"` — pass if exit 0 (imports succeed without error).
- **Status**: [x] complete

### Task 3: Convert package-internal `Path(__file__)` sites in `overnight/`, `dashboard/` to `importlib.resources`

- **Files**: `cortex_command/overnight/brain.py`, `cortex_command/overnight/feature_executor.py`, `cortex_command/dashboard/app.py`
- **What**: Replace the remaining three package-internal `Path(__file__)` references with `importlib.resources.files()`. The dashboard Jinja2 template loader requires `as_file()` materialization because Jinja2's `FileSystemLoader` needs a real directory path.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `overnight/brain.py:103` (`parent / "prompts/batch-brain.md"`) → `importlib.resources.files("cortex_command.overnight.prompts").joinpath("batch-brain.md").read_text(encoding="utf-8")`
  - `overnight/feature_executor.py:63` (`parents[1] / "pipeline/prompts/implement.md"`) → `importlib.resources.files("cortex_command.pipeline.prompts").joinpath("implement.md")`
  - `dashboard/app.py:49` (`parent / "templates"` for Jinja2): use `importlib.resources.as_file(importlib.resources.files("cortex_command.dashboard.templates"))` inside a context manager that wraps the Jinja2 environment construction; the wheel build unpacks templates so `as_file()` returns the real filesystem path under non-editable install.
  - Touch only line 49 in `dashboard/app.py` for this task; lines 42 and 184 are out of scope for Task 3 (line 42 is user-data — Task 5; line 184 is dev-only `.pid` — out of scope per spec Non-Requirements).
- **Verification**: `grep -E "Path\\(__file__\\)" cortex_command/overnight/brain.py cortex_command/overnight/feature_executor.py | wc -l` = 0 — pass if count = 0. Plus `grep -c "importlib.resources" cortex_command/dashboard/app.py` ≥ 1 — pass if count ≥ 1. Plus `python3 -c "from cortex_command.overnight.brain import *; from cortex_command.overnight.feature_executor import *; from cortex_command.dashboard.app import *"` — pass if exit 0.
- **Status**: [x] complete

### Task 4: Convert overnight user-data `Path(__file__)` sites to call-time `_resolve_user_project_root()`

- **Files**: `cortex_command/overnight/plan.py`, `cortex_command/overnight/events.py`, `cortex_command/overnight/orchestrator.py`, `cortex_command/overnight/state.py`
- **What**: Replace the four module-level `_LIFECYCLE_ROOT = Path(__file__).resolve().parents[2] / "lifecycle"` constants AND every downstream `DEFAULT_*_PATH` module-level capture AND every `BatchConfig` dataclass field default that captures `_LIFECYCLE_ROOT` with call-time resolution. Module-level binding is prohibited per spec R3c.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - **Direct symbol deletion**: delete `_LIFECYCLE_ROOT` from `plan.py:25`, `events.py:25`, `orchestrator.py:53`, `state.py:28`.
  - **Indirect captures (DEFAULT_* constants)**: `plan.py:27` (`DEFAULT_PLAN_PATH = _LIFECYCLE_ROOT / "overnight-plan.md"`), `events.py:141` (`DEFAULT_LOG_PATH = _LIFECYCLE_ROOT / "overnight-events.log"`), `state.py:287` (`DEFAULT_STATE_PATH`). Each is consumed as a function default arg (e.g., `events.py:177, 225, 267`; `plan.py:498`; `state.py` `load_state` signature). Replace each `DEFAULT_*_PATH` constant with a `_default_*_path()` function returning `_resolve_user_project_root() / "lifecycle" / "overnight-<name>"`, and update every consumer to either (a) pass an explicit path or (b) call `_default_*_path()` with no arg as the default — using `Optional[Path] = None` plus `path = path or _default_*_path()` inside the function body.
  - **`events.py:146`** (`lifecycle_root: Path = _LIFECYCLE_ROOT` as function default arg): change signature to `lifecycle_root: Optional[Path] = None` and resolve inside the body via `lifecycle_root = lifecycle_root or _resolve_user_project_root() / "lifecycle"`.
  - **`BatchConfig` dataclass fields (`orchestrator.py:90-93`)**: `overnight_state_path`, `overnight_events_path`, `result_dir`, `pipeline_events_path` are dataclass field defaults that today capture `_LIFECYCLE_ROOT`. Convert each to `field(default_factory=lambda: _resolve_user_project_root() / "lifecycle" / "<name>")`. Add `from dataclasses import field` if not already imported.
  - Add `from cortex_command.common import _resolve_user_project_root` to each file.
  - **Caller enumeration for `_LIFECYCLE_ROOT`**: `grep -rn "_LIFECYCLE_ROOT" cortex_command/` returns matches in plan.py, events.py, orchestrator.py, state.py (handled here) AND in report.py (handled in Task 5).
  - **Caller enumeration for `DEFAULT_PLAN_PATH` / `DEFAULT_LOG_PATH` / `DEFAULT_STATE_PATH`**: `grep -rn "DEFAULT_PLAN_PATH\|DEFAULT_LOG_PATH\|DEFAULT_STATE_PATH" cortex_command/ tests/` — enumerate every consumer (default arg, function body reference, test fixture) and update each.
  - **R3c AST-gate scope clarification**: spec R3c forbids module-level `ast.Assign` whose RHS calls `_resolve_user_project_root()`. The `field(default_factory=lambda: _resolve_user_project_root() / ...)` pattern is permitted because the call is inside the lambda body (deferred until instance construction). Document this in the verification command's comment so future maintainers understand why the lambda escape is intentional.
- **Verification**: `grep -rn "_LIFECYCLE_ROOT" cortex_command/overnight/plan.py cortex_command/overnight/events.py cortex_command/overnight/orchestrator.py cortex_command/overnight/state.py | wc -l` = 0 — pass if count = 0. Plus `grep -rn "_LIFECYCLE_ROOT \\*\\* \\| _LIFECYCLE_ROOT /" cortex_command/overnight/ | wc -l` = 0 — pass if count = 0 (no remaining indirect captures). Plus `python3 -c "from cortex_command.overnight import plan, events, orchestrator, state, report"` — pass if exit 0 (note: report.py included; Task 5 fixes it).
- **Status**: [x] complete

### Task 5: Convert remaining user-data sites and delete vestigial `sys.path.insert` in `outcome_router.py`

- **Files**: `cortex_command/overnight/report.py`, `cortex_command/overnight/status.py`, `cortex_command/dashboard/seed.py`, `cortex_command/dashboard/app.py`, `cortex_command/overnight/outcome_router.py`
- **What**: Replace all remaining user-data `Path(__file__)` and `_LIFECYCLE_ROOT` references with `_resolve_user_project_root()` calls inside function bodies. Delete the `_PROJECT_ROOT` + `sys.path.insert(0, str(_PROJECT_ROOT))` block in `outcome_router.py:307-309`. Replace `_PROJECT_ROOT / "backlog"` references on lines 360 and 417 with `_resolve_user_project_root() / "backlog"` evaluated in-function. Convert `status.py`'s module-level `EVENTS_SYMLINK` to a deferred function and replace `_LIFECYCLE_ROOT` references with call-time resolution (scope expansion: status.py was missing from the original Task 5 file list — Task 4's report flagged it; status.py is broken on main without this fix).
- **Depends on**: [1, 4]
- **Complexity**: complex
- **Context**:
  - **`report.py` — full reference enumeration** (the plan originally listed only line 493; the actual surface is broader):
    - Line 36: `from cortex_command.overnight.state import DEFAULT_STATE_PATH, OvernightState, _LIFECYCLE_ROOT, load_state, session_dir` — remove `_LIFECYCLE_ROOT` from the import (Task 4 deleted the symbol from `state.py`).
    - Line 43: `DEFAULT_REPORT_PATH = _LIFECYCLE_ROOT / "morning-report.md"` — convert to a `_default_report_path()` function returning `_resolve_user_project_root() / "lifecycle" / "morning-report.md"`. Update consumers (line 1484 doc reference; consumers using `DEFAULT_REPORT_PATH` as default arg).
    - Line 89: `state_path: Path = DEFAULT_STATE_PATH` (default arg using a Task-4-converted constant) — convert to `Optional[Path] = None` and resolve inside the function body.
    - Line 90: `events_path: Path = DEFAULT_LOG_PATH` — same treatment as line 89.
    - Lines 122, 140: `session_dir(..., lifecycle_root=_LIFECYCLE_ROOT)` — replace with `lifecycle_root=_resolve_user_project_root() / "lifecycle"` evaluated at the call site.
    - Line 493: `Path(__file__).resolve().parent.parent.parent.name` (home-repo name) → `_resolve_user_project_root().name`. Confirm `.name` is the only attribute consumed in the surrounding function; if a full path is used elsewhere, refactor.
    - Line 889: `(_LIFECYCLE_ROOT).glob("*/critical-review-residue.json")` — replace with `(_resolve_user_project_root() / "lifecycle").glob("*/critical-review-residue.json")` evaluated inside the enclosing function.
    - Line 1457-1458: `state_path: Path = DEFAULT_STATE_PATH` and `events_path: Path = DEFAULT_LOG_PATH` — same treatment as lines 89-90.
    - Line 1496: `_LIFECYCLE_ROOT.parent / "backlog"` → `_resolve_user_project_root() / "backlog"` evaluated inside the enclosing function (note: this drops the `.parent` because `_LIFECYCLE_ROOT` was `<root>/lifecycle` and the existing code's `_LIFECYCLE_ROOT.parent` reaches `<root>` to then descend into `backlog`; the new helper already returns `<root>`).
    - Line 1507: `session_dir(..., lifecycle_root=_LIFECYCLE_ROOT)` — same treatment as lines 122, 140.
  - **`overnight/status.py` — full reference enumeration** (scope expansion from Task 4 follow-up):
    - Line 19-24: `from cortex_command.overnight.state import (_LIFECYCLE_ROOT, latest_symlink_path, load_state, session_dir,)` — drop `_LIFECYCLE_ROOT` from the import (Task 4 deleted the symbol).
    - Line 31: `EVENTS_SYMLINK = latest_symlink_path("overnight", lifecycle_root=_LIFECYCLE_ROOT) / "overnight-events.log"` — module-level binding prohibited per spec R3c. Convert to a function `_events_symlink_path() -> Path` that resolves `_resolve_user_project_root() / "lifecycle"` at call time, and update consumers at lines 68, 69, 73, 75 (all inside `_resolve_events_log()`) to call `_events_symlink_path()` instead of referencing the module-level constant.
    - Line 78: `session_dir(session_id, lifecycle_root=_LIFECYCLE_ROOT)` → `session_dir(session_id, lifecycle_root=_resolve_user_project_root() / "lifecycle")` evaluated at the call site.
    - Line 191: `sessions_dir = _LIFECYCLE_ROOT / "sessions"` (inside `_find_latest_state_path()`) → `sessions_dir = _resolve_user_project_root() / "lifecycle" / "sessions"` evaluated in-function.
    - Add `from cortex_command.common import _resolve_user_project_root` import.
  - **`dashboard/seed.py:25`** (`parents[2]` — REPO_ROOT) → `_resolve_user_project_root()`.
  - **`dashboard/app.py:42`** (`parents[2]` — root) → `_resolve_user_project_root()` (line 42 only; line 49 was handled in Task 3, line 184 is out of scope).
  - **`overnight/outcome_router.py:307-309`** (`_PROJECT_ROOT = Path(__file__)... sys.path.insert(0, str(_PROJECT_ROOT))`) — DELETE the three lines entirely. **Rationale (corrected from prior plan revision)**: the deleted line was inserting `parents[2]` (the repo root, NOT the `cortex_command` package directory) onto `sys.path`. Under wheel install, `site-packages/` is on `sys.path` and contains `cortex_command/`, so qualified imports like `from cortex_command.backlog.update_item import ...` (lines 322-323) resolve correctly without the manual insert. Deletion is safe; the security delta is **neutral** on the deleted code (which was file-anchored, not CWD-derived). The CWD-as-import-root concern raised in research Adversarial #5 applies to the *replacement* helper (`_resolve_user_project_root()`), not to the deleted scaffold; the helper's `lifecycle/` + `backlog/` sanity check (Task 1) is the mitigation for that surface.
  - **`overnight/outcome_router.py:312`** — comment block referencing `_PROJECT_ROOT` becomes stale; rewrite to reference `_resolve_user_project_root()` and document that the fallback now resolves to the user's project root via the helper, not to a module-anchored path.
  - **`overnight/outcome_router.py:360, 417`** (`_PROJECT_ROOT / "backlog"` fallback for `_backlog_dir`) → `_resolve_user_project_root() / "backlog"` evaluated inside the enclosing function. Note the semantic shift: `_PROJECT_ROOT / "backlog"` was the cortex-command repo's own backlog under editable install (and broken under wheel install — resolved into site-packages's parent). The new helper anchors to the user's project root via env-var or CWD, which matches the actual intended behavior across both install modes.
  - **Caller enumeration for `_PROJECT_ROOT` (cross-module)**: `grep -rn "outcome_router._PROJECT_ROOT\\|from cortex_command.overnight.outcome_router import _PROJECT_ROOT" cortex_command/` — orchestrator.py:189 references `outcome_router._PROJECT_ROOT / "backlog"` inside an exception-logging block. After deletion, that branch raises `AttributeError` (swallowed by `except Exception: pass`). Update orchestrator.py:189 to reference `_resolve_user_project_root() / "backlog"` directly.
  - Add `from cortex_command.common import _resolve_user_project_root` to each file (and to `orchestrator.py` if not already added by Task 4).
- **Verification**: `grep -c "sys.path.insert" cortex_command/overnight/outcome_router.py` = 0 — pass if count = 0. Plus `grep -c "_PROJECT_ROOT" cortex_command/overnight/outcome_router.py cortex_command/overnight/orchestrator.py` = 0 — pass if count = 0. Plus `grep -c "_LIFECYCLE_ROOT" cortex_command/overnight/report.py` = 0 — pass if count = 0. Plus `grep -rn "Path(__file__).resolve().parents\\[2\\]" cortex_command/ --include='*.py' | grep -v tests | wc -l` = 0 — pass if count = 0. Plus AST gate from spec R3c: run `python3 -c "import ast; from pathlib import Path; failures = [f'{p}:{n.lineno}' for p in Path('cortex_command').rglob('*.py') if 'tests' not in str(p) for n in ast.walk(ast.parse(p.read_text())) if isinstance(n, ast.Assign) and any((isinstance(c, ast.Call) and getattr(c.func, 'attr', getattr(c.func, 'id', '')) == '_resolve_user_project_root') for c in ast.walk(n) if not isinstance(c, ast.Lambda))]; assert not failures, failures"` — pass if exit 0 (note: lambdas are excluded so `field(default_factory=lambda: _resolve_user_project_root() / ...)` is permitted; only direct module-level invocation is rejected). Plus `python3 -c "from cortex_command.overnight import report"` — pass if exit 0 (broken import on report.py:36 detected here; verification was previously absent). Plus `python3 -c "from cortex_command.overnight import status"` — pass if exit 0 (status.py scope-expansion smoke test). Plus `grep -c "_LIFECYCLE_ROOT" cortex_command/overnight/status.py` = 0 — pass if count = 0.
- **Status**: [x] complete

### Task 6: Rewrite `cortex upgrade` as advisory; rework `cortex --print-root` JSON envelope (project-root + new `package_root` field)

- **Files**: `cortex_command/cli.py`, `cortex_command/install_guard.py`, `lifecycle/non-editable-wheel-install-support-for-cortex-command/spec.md` (R2d amendment).
- **What**: Replace `_dispatch_upgrade`'s install-mutation body with an advisory printer that exits 0. Delete `_resolve_cortex_root()`. Rework `_dispatch_print_root` so the `root` field is the user's project root (via `_resolve_user_project_root()`) — matching the single-source-of-truth contract — and add a new `package_root` field for package introspection. Bump JSON envelope `version` to `"1.1"` (additive: new field, no consumer changes required, 1.0 consumers ignore the new field). Amend spec R2d to reflect the new envelope shape. Strip stale `~/.cortex` references from `install_guard.py` error messages.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - **Spec R2d amendment**: in `lifecycle/non-editable-wheel-install-support-for-cortex-command/spec.md`, replace R2d's "`--print-root` returns the package install location" with "`--print-root` returns the user's project root (via `_resolve_user_project_root()`); a new `package_root` field reports the package install location for diagnostic introspection." Note the amendment in the spec's `## Open Decisions` section as resolved (D2 → option a).
  - `_dispatch_upgrade` (cli.py:251-296): keep the `check_in_flight_install()` guard at the top. Remove env/cwd resolution, dirty-tree check, git pull, and `uv tool install -e ... --force`. Print two-line advisory:
    1. `"Run /plugin update cortex-overnight-integration@cortex-command in Claude Code to upgrade via the MCP-driven path."`
    2. `"Or run \`uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@<tag>\` for the bare-shell path; see https://github.com/charleshall888/cortex-command/releases for current tags."`
  - Keep the existing `.mcp.json` migration notice (cli.py:289-296) — still useful during transition.
  - `_dispatch_print_root` (cli.py:211-248):
    - Resolve `root` via `_resolve_user_project_root()` (raises `CortexProjectRootError` when CWD has neither `lifecycle/` nor `backlog/` AND `CORTEX_REPO_ROOT` is unset). Catch the exception at the dispatch layer and print a clear error to stderr; exit code 2.
    - Resolve `package_root` via `Path(cortex_command.__file__).resolve().parent`.
    - When `root` is a git clone (detected by `(root / ".git").is_dir()`), populate `remote_url` and `head_sha` from `git -C $root remote get-url origin` and `git -C $root rev-parse HEAD` (returncode-tolerant; empty string on failure). Otherwise (wheel install case, `root` is the user's project, may or may not be a git repo) probe the same — most user projects ARE git repos so `head_sha` is typically populated; for non-git projects both fields are empty.
    - Emit JSON envelope: `{"version": "1.1", "root": <user-project>, "package_root": <package-install>, "remote_url": <git-or-empty>, "head_sha": <git-or-empty>}`. Bumping the envelope's own `version` to `1.1` is additive — `1.0` consumers ignore the new `package_root` field. This `version` is the JSON-envelope version, distinct from `CLI_PIN[1]`'s schema major.
  - `_resolve_cortex_root` (cli.py:168-209): delete.
  - **Caller enumeration for `_resolve_cortex_root`**: `grep -rn "_resolve_cortex_root" cortex_command/` returns `cli.py:222` (Task 6 reworks), `cli.py:260` (Task 6 deletes — line is inside `_dispatch_upgrade`'s removed body). Also `tests/test_cli_print_root.py` and `tests/test_cli_upgrade.py` reference it via patching — Task 15 rewrites those tests for the new envelope shape.
  - `install_guard.py`: scan for `~/.cortex`, `CORTEX_COMMAND_ROOT`, and `_resolve_cortex_root` references; replace with the new helper or delete.
  - **MCP-side consumer impact** (handled in new Task 16): `plugins/cortex-overnight-integration/server.py:1614` (overnight_status session-dir construction) and `server.py:529-538` (R8 throttle cache key) consume `root` from this envelope. Under the new semantic, `root` is the user's project root — so session-dir resolution `Path(root) / "lifecycle" / "sessions" / session_id` correctly targets the user's project lifecycle tree. R8 throttle keying still requires non-empty `head_sha`/`remote_url`, which holds when the user's project is itself a git repo (the common case); when it isn't, the throttle skips silently — Task 16 resolves this by short-circuiting R8 explicitly under wheel install rather than relying on empty-string sentinel behavior.
- **Verification**: `grep -E "git pull|git status|~/\\.cortex|CORTEX_COMMAND_ROOT" cortex_command/cli.py | wc -l` = 0 — pass if count = 0. Plus `grep -E "subprocess.*uv.*tool.*install" cortex_command/cli.py | wc -l` = 0 — pass if count = 0. Plus `grep -c "_resolve_cortex_root" cortex_command/cli.py` = 0 — pass if count = 0. Plus `grep -E "/plugin update|--reinstall" cortex_command/cli.py | wc -l` ≥ 2 — pass if count ≥ 2. Plus `python3 -m cortex_command.cli upgrade` — pass if exit 0 (advisory printer exits cleanly). Plus `cd /tmp && python3 -m cortex_command.cli --print-root --format json 2>&1 | grep -E "lifecycle/ AND no backlog/|cortex project"` — pass if grep finds the error message (verifying the sanity-check raise propagates cleanly when CWD is unsuitable). Plus `cd $(git rev-parse --show-toplevel) && python3 -m cortex_command.cli --print-root --format json | python3 -c "import json, sys; d = json.loads(sys.stdin.read()); assert d['version'] == '1.1' and 'root' in d and 'package_root' in d"` — pass if exit 0.
- **Status**: [x] complete

### Task 7: Simplify `install.sh` to ensure `uv` and run `uv tool install git+<url>@<tag>`

- **Files**: `install.sh`
- **What**: Replace clone-and-editable-install flow with a single bootstrap that ensures `uv` is installed (via the `astral.sh/uv` curl installer if absent) and runs `uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>` where `<tag>` is the latest published release tag (resolved via `gh release view --json tagName -q .tagName`, or hardcoded `v0.1.0` for the initial cut).
- **Depends on**: [14]
- **Complexity**: simple
- **Context**:
  - Read existing `install.sh` to identify the clone-target path and editable-install command. Delete clone, delete `uv tool install -e`, keep any logging/banner output.
  - Add `command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh` as the prerequisite step.
  - Hardcode `v0.1.0` for the initial implementation; a follow-up can wire `gh release view` once tag discipline is established.
  - Pattern reference: read existing logging/error-handling style in `install.sh` and match it.
- **Verification**: `grep -E "git clone|uv tool install -e" install.sh | wc -l` = 0 — pass if count = 0. Plus `grep -E "uv tool install git\\+" install.sh | wc -l` ≥ 1 — pass if count ≥ 1. Plus `bash -n install.sh` — pass if exit 0 (script parses without syntax error).
- **Status**: [x] complete

### Task 8: Add `CLI_PIN` constant and `uv` startup probe to MCP `server.py`

- **Files**: `plugins/cortex-overnight-integration/server.py`
- **What**: Replace the bare `MCP_REQUIRED_CLI_VERSION = "1.0"` literal at server.py:102 with a `CLI_PIN = ("v0.1.0", "1.0")` tuple, derive `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]`, and add a `shutil.which("uv")` probe at server startup that emits a structured stderr error and refuses to start when `uv` is not on PATH.
- **Depends on**: [14]
- **Complexity**: simple
- **Context**:
  - Place `CLI_PIN: tuple[str, str] = ("v0.1.0", "1.0")` at module top alongside `MCP_REQUIRED_CLI_VERSION`. Spec R5a requires the literal form `CLI_PIN = (...)`; AST gate via grep.
  - Derive `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]`. Existing references to `MCP_REQUIRED_CLI_VERSION` (server.py:102, 137, 171, 176, 1050, 1067, 1191) are unchanged.
  - **Caller enumeration for `MCP_REQUIRED_CLI_VERSION`**: search `grep -rn "MCP_REQUIRED_CLI_VERSION" plugins/ cortex_command/ tests/` to confirm the constant is plugin-only (spec R5d forbids CLI references). If a CLI reference is found, escalate as a spec violation.
  - Startup probe (placed after the existing `shutil.which("cortex") is None` check at server.py:219): `if shutil.which("uv") is None: sys.stderr.write(<<<error message pointing at the macOS GUI-app + Homebrew + ~/.zshenv fix>>>); sys.exit(2)`. Error message must include the keywords `zshenv` and `GUI` per spec R4g grep verification.
  - Schema-mismatch error (existing site at server.py:170-180 or wherever the floor check raises): extend message to include `"downgrade plugin OR run \`uv tool install --reinstall git+<url>@<expected-tag>\` to upgrade cortex CLI to the matching version."` per spec R5b.
- **Verification**: `grep -E "^CLI_PIN = \\(" plugins/cortex-overnight-integration/server.py` returns ≥ 1 — pass if count ≥ 1. Plus `grep -E "MCP_REQUIRED_CLI_VERSION = CLI_PIN\\[1\\]" plugins/cortex-overnight-integration/server.py` returns ≥ 1 — pass if count ≥ 1. Plus `grep -E "shutil.which.*uv|zshenv|GUI" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 2 — pass if count ≥ 2. Plus `grep -E "downgrade plugin|--reinstall" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1. Plus `grep -E "CLI_PIN|MCP_REQUIRED_CLI_VERSION" cortex_command/cli.py | wc -l` = 0 — pass if count = 0 (CLI never references plugin constants).
- **Status**: [x] complete

### Task 9: Add `_ensure_cortex_installed()` hook with flock, sentinel, and post-install verification; wire into tool handlers

- **Files**: `plugins/cortex-overnight-integration/server.py`
- **What**: Add `_ensure_cortex_installed()` that detects missing CLI (`shutil.which("cortex") is None`), acquires a flock at `${XDG_STATE_HOME}/cortex-command/install.lock`, runs `uv tool install --reinstall git+<url>@CLI_PIN[0]`, verifies success via `cortex --print-root --format json`, writes a sentinel on failure, and logs to NDJSON. Wire the call into `_resolve_cortex_argv()` (or each tool handler) so it runs before any cortex subprocess invocation.
- **Depends on**: [8, 14]
- **Complexity**: complex
- **Context**:
  - Function signature: `def _ensure_cortex_installed() -> None:` — raises a structured exception on failure, otherwise returns silently when CLI is present or install succeeded.
  - Skip predicate: when `os.environ.get("CORTEX_AUTO_INSTALL") == "0"`, fall through to 146 R19's notice-only path (existing path; do not auto-install).
  - **Lock path**: `Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "cortex-command" / "install.lock"`. Create parent dirs idempotently.
  - **Flock pattern**: reuse 146 R11 / `cortex_command/init/settings_merge.py:69-85` (`fcntl.flock(LOCK_EX)` with 60s timeout, release in `try/finally`, re-verify CLI presence after acquiring — if CLI now present, skip install).
  - **Sentinel path**: `Path(os.environ.get("XDG_STATE_HOME", ...)) / "cortex-command" / f"install-failed.{int(time.time())}"`. Before attempting install, check for any existing `install-failed.*` files newer than 60s — if found, raise with the prior failure context instead of retrying.
  - **Install command**: `subprocess.run(["uv", "tool", "install", "--reinstall", f"git+https://github.com/charleshall888/cortex-command.git@{CLI_PIN[0]}"], timeout=300, capture_output=True, text=True)`.
  - **Post-install verification**: `subprocess.run(["cortex", "--print-root", "--format", "json"], timeout=10, capture_output=True, text=True)` — parse stdout as JSON; on parse failure or non-zero exit, treat as install failure (write sentinel, log NDJSON, raise).
  - **NDJSON failure log**: append to `${XDG_STATE_HOME}/cortex-command/last-error.log` with shape `{"ts": ISO8601, "stage": "first_install", "error": str, "context": {"cli_pin": CLI_PIN[0], "exit_code": int}}`. Reuse 146 R14 / `server.py:374-428` `_append_error_ndjson()` helper if exposed; otherwise inline the same pattern.
  - **Wiring**: insert `_ensure_cortex_installed()` call at the top of `_resolve_cortex_argv()` (server.py:245) so every tool handler that delegates to `cortex` triggers the hook implicitly. Confirms zero call-site additions in tool handlers.
  - **Caller enumeration for `_resolve_cortex_argv`**: `grep -rn "_resolve_cortex_argv" plugins/cortex-overnight-integration/server.py` returns server.py:245, 270, 760, 806, 1405. All five sites benefit from the hook transparently — no per-handler changes required.
  - **Schema-mismatch flow**: when post-install verification succeeds but the installed CLI's `cortex --print-root` reports a `version` major below `CLI_PIN[1]`'s major, the existing R13 schema-floor check (server.py:1050+) fires. The hook does not re-handle this case; it relies on the existing path.
- **Verification**: `grep -c "_ensure_cortex_installed" plugins/cortex-overnight-integration/server.py` ≥ 2 — pass if count ≥ 2 (definition + call site). Plus `grep -E "shutil.which.*cortex|uv.*tool.*install.*reinstall" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 2 — pass if count ≥ 2. Plus `grep -E "install.lock|XDG_STATE_HOME" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1. Plus `grep -E "install-failed|sentinel" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1. Plus `grep -E "first_install" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1. Plus `grep -E "cortex.*--print-root|print-root.*--format" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1. Plus `grep -E "CORTEX_AUTO_INSTALL" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 10: Add target-state and transition-mechanism tests in `tests/test_no_clone_install.py`

- **Files**: `tests/test_no_clone_install.py`
- **What**: Add two pytest tests: `test_target_state` builds the wheel via `uv build`, installs it in a tmpdir-isolated env, and asserts `cortex --print-root --format json` and `importlib.resources` lookups work under non-editable install. `test_mcp_first_install_hook` exercises `_ensure_cortex_installed()` end-to-end with mocked `subprocess.run` to verify the control flow (hook fires, install attempted, post-install verify called, sentinel written on failure, sentinel read on retry).
- **Depends on**: [1, 2, 3, 4, 5, 6, 8, 9, 14, 16]
- **Complexity**: complex
- **Context**:
  - `test_target_state`:
    - Use `pytest.fixture(scope="module")` to build the wheel once: `subprocess.run(["uv", "build", "--wheel"], cwd=repo_root, check=True)`; locate wheel at `dist/cortex_command-*.whl`.
    - Install in tmpdir: `subprocess.run(["uv", "tool", "install", "--reinstall", str(wheel_path)], env={"UV_TOOL_DIR": str(tmp_path), "UV_TOOL_BIN_DIR": str(tmp_path / "bin"), ...}, check=True)`.
    - Probe (via subprocess executing the installed shim): `cortex --print-root --format json` exit 0, JSON parseable, `version`, `root`, `remote_url`, `head_sha` all present.
    - Probe `importlib.resources.files("cortex_command.overnight.prompts").joinpath("orchestrator-round.md").read_text()` returns non-empty content. Run via `subprocess.run([str(tmp_path / "bin/python"), "-c", <inline probe>])` against the installed env's interpreter.
    - Parameterized over the six package-internal sites from Task 2/3 — confirm each `importlib.resources` lookup resolves under the wheel.
  - `test_mcp_first_install_hook`:
    - Use `unittest.mock.patch("subprocess.run")` to capture invocations without running the real `uv tool install`.
    - Use `unittest.mock.patch("shutil.which", return_value=None)` to simulate cortex absent.
    - Import the plugin's `server.py` module via `importlib` (the plugin tree lives outside the test's sys.path; the test fixture adds `plugins/cortex-overnight-integration/` to `sys.path`).
    - Assertions: (1) `subprocess.run` was called with `["uv", "tool", "install", "--reinstall", "git+...@v0.1.0"]`; (2) `subprocess.run` was called with `["cortex", "--print-root", "--format", "json"]` after install; (3) on simulated install failure (mock returns non-zero exit), a sentinel file `install-failed.*` exists at the test-controlled XDG_STATE_HOME; (4) a second `_ensure_cortex_installed()` call within 60s reads the sentinel and raises without re-attempting `subprocess.run(["uv", "tool", "install", ...])`.
    - Use `tmp_path` + `monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))` to isolate sentinel/lock files.
  - Pattern reference: `tests/test_cli_upgrade.py:37-84` (subprocess mock pattern) and `tests/test_cli_print_root.py` (CLI invocation pattern).
- **Verification**: `pytest tests/test_no_clone_install.py::test_target_state -v` — pass if exit 0. Plus `pytest tests/test_no_clone_install.py::test_mcp_first_install_hook -v` — pass if exit 0. Plus `test -f tests/test_no_clone_install.py` — pass if file exists.
- **Status**: [x] complete

### Task 11: Update existing project documentation (CLAUDE.md, requirements/project.md, requirements/observability.md)

- **Files**: `CLAUDE.md`, `requirements/project.md`, `requirements/observability.md`
- **What**: Replace `uv tool install -e .` references with `uv tool install git+<url>@<tag>`. Remove the "shared publicly for others to clone or fork" framing as primary identity (move to a "secondary forker path" context). Update the install-mutation classification in observability.md to drop the `-e` flag and add the MCP first-install hook as a tracked install-mutation orchestrator.
- **Depends on**: [14]
- **Complexity**: simple
- **Context**:
  - `CLAUDE.md` lines 5 and 22: replace `uv tool install -e .` with `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0`. Keep the `cortex init` per-repo allowWrite registration sentence intact.
  - `requirements/project.md` L7: rephrase from "Primarily personal tooling, shared publicly for others to clone or fork" to a CLI-first identity that mentions clone/fork only as a secondary forker path. L26 (per-repo sandbox registration): unchanged. L34 (defense-in-depth): unchanged. L55 (Out-of-scope): replace "the `cortex` CLI ships as a local editable install" with "the `cortex` CLI ships as a non-editable wheel installed from a tag-pinned git URL via `uv tool install git+<url>@<tag>`; PyPI publication remains out of scope."
  - `requirements/observability.md` L139-142: replace the `-e` reference in the install-mutation classification; add a new entry for the MCP first-install hook (`_ensure_cortex_installed`) with `stage: "first_install"` per spec R7f.
  - Word-level tracking: read each file before editing; preserve adjacent paragraphs that are not part of the change.
- **Verification**: `grep -E "uv tool install -e" CLAUDE.md requirements/project.md requirements/observability.md` returns 0 — pass if zero matches. Plus `grep -E "uv tool install git\\+" CLAUDE.md requirements/project.md` returns ≥ 2 — pass if count ≥ 2. Plus `grep -E "first_install|first install hook" requirements/observability.md` returns ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 12: Add new documentation files (docs/install.md, docs/migration-no-clone-install.md, docs/release-process.md, CHANGELOG.md)

- **Files**: `docs/install.md`, `docs/migration-no-clone-install.md`, `docs/release-process.md`, `CHANGELOG.md`
- **What**: Create four new documentation files: `install.md` leads with `uv tool install git+<url>@<tag>` as the primary path and documents the `curl | sh` fallback; `migration-no-clone-install.md` documents the existing-maintainer runbook (`uv tool uninstall cortex-command && uv tool install git+<url>@<tag>`); `release-process.md` documents the version-bump, tag-push, and **tag-before-coupling** discipline (CLI tag is pushed BEFORE the plugin's `CLI_PIN` is bumped to reference it); `CHANGELOG.md` is initialized with a `v0.1.0` entry.
- **Depends on**: [14]
- **Complexity**: simple
- **Context**:
  - `docs/install.md`: structure as (1) Quick install — `uv tool install git+...@v0.1.0`; (2) Post-install — `cortex init` per-repo registration; (3) `curl | sh` fallback for users without `uv`; (4) Bare-shell `cortex` access pattern; (5) Notes on plugin auto-update + stale-plugin behavior per spec R5c.
  - `docs/migration-no-clone-install.md`: list explicit shell commands for the `~/.cortex` editable-install user. Include verification step (`cortex --print-root --format json` exits 0; `cortex --version` matches the tag).
  - `docs/release-process.md`: document semver bumping in `pyproject.toml`, CHANGELOG entry, `git tag -a vX.Y.Z -m "..."`, `git push --tags`, and the resulting GitHub Actions workflow execution.
  - `CHANGELOG.md`: minimal Keep-a-Changelog format; first entry `## [v0.1.0]` with bullet points referencing the migration (no-clone install, MCP first-install hook, `Path(__file__)` audit).
  - Length target: 50-200 lines per file.
- **Verification**: `test -f docs/install.md && grep -c "uv tool install git\\+" docs/install.md` ≥ 1 — pass if file exists and count ≥ 1. Plus `test -f docs/migration-no-clone-install.md && grep -c "uv tool uninstall" docs/migration-no-clone-install.md` ≥ 1 — pass if file exists and count ≥ 1. Plus `test -f docs/release-process.md && grep -c "uv build\\|tag\\|release" docs/release-process.md` ≥ 3 — pass if file exists and count ≥ 3. Plus `test -f CHANGELOG.md && grep -c "v0.1.0" CHANGELOG.md` ≥ 1 — pass if file exists and count ≥ 1.
- **Status**: [x] complete

### Task 13: Add GitHub Actions release workflow (`.github/workflows/release.yml`)

- **Files**: `.github/workflows/release.yml`
- **What**: Create a release workflow that triggers on tag push matching `v[0-9]+.[0-9]+.[0-9]+`, builds the wheel via `uv build`, and publishes a GitHub Release with the wheel as a release asset.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Trigger: `on: push: tags: ['v[0-9]+.[0-9]+.[0-9]+']`.
  - Steps: (1) `actions/checkout@v4`; (2) install `uv` via `astral-sh/setup-uv@v3`; (3) `uv build --wheel`; (4) `softprops/action-gh-release@v2` (or `gh release create`) with `dist/*.whl` as the asset.
  - Permissions: `contents: write` for release creation.
  - Pattern reference: any existing workflow files in `.github/workflows/` — check `ls .github/workflows/` for prior conventions.
  - Comment in workflow file documenting that `tests/test_no_clone_install.py::test_target_state` (R6c) exercises the wheel-build + install path locally; the CI integration test for tag-trigger requires an actual tag push and is not run on every PR.
- **Verification**: `test -f .github/workflows/release.yml` — pass if file exists. Plus `grep -c "tags:" .github/workflows/release.yml` ≥ 1 — pass if count ≥ 1. Plus `grep -E "uv build|softprops/action-gh-release|gh release create" .github/workflows/release.yml | wc -l` ≥ 2 — pass if count ≥ 2.
- **Status**: [x] complete

### Task 14: Cut and push tag `v0.1.0` (tag-before-coupling pivot); verify GitHub Release published

- **Files**: (no file changes — git tag operation + remote push + verification)
- **What**: This task is the temporal pivot: it MUST run AFTER foundation tasks (Tasks 1-6, 13, 16) merge to main, and BEFORE plugin/install/doc tasks (Tasks 7, 8, 9, 10, 11, 12) that hardcode the `v0.1.0` literal. Tag the foundation integration commit as `v0.1.0`, push the tag, and verify the release publishes. After this task succeeds, the `v0.1.0` tag exists at the remote — making it safe for subsequent tasks to add `CLI_PIN[0] = "v0.1.0"`, `install.sh` references, doc references, etc., without creating a dangling-pointer window.
- **Depends on**: [1, 2, 3, 4, 5, 6, 13, 16]
- **Complexity**: simple
- **Context**:
  - **Pre-condition checks before tagging**:
    - `pyproject.toml` declares `version = "0.1.0"`.
    - `.github/workflows/release.yml` exists and lints clean (`gh workflow view release.yml` returns 0 errors; `actionlint .github/workflows/release.yml` if `actionlint` is available — otherwise inspect manually).
    - All foundation tests pass (`just test` exits 0 against the current main).
  - Run `git tag -a v0.1.0 -m "Initial tagged release for no-clone install"`.
  - Run `git push origin v0.1.0`.
  - Wait for `.github/workflows/release.yml` to complete. Monitor via `gh run watch $(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')`.
  - Verify the release published with the wheel asset: `gh release view v0.1.0 --json assets -q '.assets[].name' | grep -E 'cortex_command-0.1.0.*\\.whl'`.
  - **Rollback procedure on workflow failure**: if the workflow errored after the tag was pushed (e.g., release.yml YAML bug, runner unavailable, missing secrets), the tag exists at the remote but no release asset exists. To recover:
    1. Delete the remote tag: `git push --delete origin v0.1.0` (single-maintainer repo; safe at this stage because no users have installed against it yet — Tasks 7-12 have not landed).
    2. Delete the local tag: `git tag -d v0.1.0`.
    3. Fix the underlying workflow issue.
    4. Re-run Task 14 after the fix.
  - This is a publishing operation visible to other users of the repo — confirm with the user before pushing the tag. Tag deletion at this stage is recoverable; deletion AFTER subsequent tasks land would orphan their `v0.1.0` references, so deletion windows close once Task 7 merges.
- **Verification**: `git tag -l "v0.1.0" | wc -l` = 1 — pass if count = 1. Plus `gh release list --limit 5 | grep -c "v0.1.0"` ≥ 1 — pass if count ≥ 1. Plus `gh release view v0.1.0 --json assets -q '[.assets[].name] | length'` ≥ 1 — pass if count ≥ 1 (release asset published, not just an empty release).
- **Status**: [x] complete

### Task 16: Short-circuit R8 throttle and R10 orchestration paths in MCP `server.py` under wheel install

- **Files**: `plugins/cortex-overnight-integration/server.py`
- **What**: Under wheel install (no `.git/` at `cortex_root`), R8's upstream-probe throttle and R10's `cortex upgrade` orchestration are dead code paths that emit cryptic git-not-a-repository errors when exercised. R4's first-install hook (Task 9) and R13's schema-floor gate are the actual upgrade arrow under wheel install. This task short-circuits R8 and R10 explicitly so consumers don't rely on the empty-string-as-skip side effect.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **R8 throttle path** (server.py:520-545, `_maybe_check_upstream` and `_get_cortex_root_payload` consumers): add an early-return at the entry point that detects wheel install via `not (Path(cortex_root) / ".git").is_dir()` and returns `None` with a one-line debug log (no NDJSON entry — this is intended behavior, not an error). Replace the existing empty-string-sentinel branch (`if not cortex_root or not remote_url or not head_sha: return None`) with the explicit wheel-install check.
  - **R10 orchestration path** (`_orchestrate_upgrade` and `_orchestrate_schema_floor_upgrade` callers, ~ server.py:760, 909+): the schema-floor gate already triggers `_ensure_cortex_installed()` re-install on major mismatch (Task 9). The legacy `_orchestrate_upgrade` paths spawn `cortex upgrade` (now an advisory printer per Task 6) which exits 0 without doing anything. Either delete `_orchestrate_upgrade`-related code paths entirely, or short-circuit them with an early return that logs `"R10 orchestration deprecated under wheel install; R4 first-install hook + R13 schema-floor gate is the upgrade arrow."` and falls through. Recommend deletion to remove dead-code surface; if the surrounding flow is too tangled to delete cleanly, the early-return short-circuit is acceptable.
  - **Caller enumeration for `_orchestrate_upgrade`**: `grep -rn "_orchestrate_upgrade\\|_orchestrate_schema_floor_upgrade" plugins/cortex-overnight-integration/server.py` to enumerate every call site; each gets the early-return treatment or is deleted as part of the dead-code removal.
  - Document the short-circuit decision in a server.py module-level comment near the changed code: "Under non-editable wheel install, R8 throttle and R10 orchestration are dormant; the upgrade arrow flows plugin → CLI via R4 (`_ensure_cortex_installed`) on schema-floor mismatch (R13)."
- **Verification**: `grep -E "deprecated under wheel install|R8 throttle|wheel install" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 — pass if count ≥ 1 (short-circuit comment / log message present). Plus, run a smoke probe in a tmp env where `cortex_root` is a non-git directory: `python3 -c "import sys; sys.path.insert(0, 'plugins/cortex-overnight-integration'); from server import _maybe_check_upstream; assert _maybe_check_upstream() is None"` — pass if exit 0 (R8 returns None cleanly without raising).
- **Status**: [x] complete

### Task 15: Full regression run (`just test`) and post-merge sanity probes; rewrite tests broken by Task 6

- **Files**: `tests/test_cli_print_root.py`, `tests/test_cli_upgrade.py` (rewrite if Task 6 breaks them); plus full regression run.
- **What**: Run the full test suite via `just test` to confirm the migration doesn't regress existing tests. Update specific tests broken by Task 6's `_dispatch_print_root` and `_dispatch_upgrade` rewrites. Spot-check `cortex --print-root --format json` and `cortex upgrade` (advisory mode) for sanity.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16]
- **Complexity**: simple
- **Context**:
  - `tests/test_cli_print_root.py:84-103` asserts `len(head_sha) == 40`, `all(c in HEX_CHARS for c in head_sha)`, `len(remote_url) > 0` — these break under Task 6 when `CORTEX_REPO_ROOT` is unset (both fields become empty strings). Update the test to either (a) set `CORTEX_REPO_ROOT` to a real git clone in the fixture and keep the existing assertions, or (b) parameterize: with-`CORTEX_REPO_ROOT` asserts populated git fields; without asserts empty strings.
  - `tests/test_cli_upgrade.py` asserts subprocess invocations of `git pull` + `uv tool install -e`. Rewrite to assert the new advisory printer output (stdout contains `/plugin update` and `--reinstall`; exit 0; no subprocess invocation).
  - `tests/test_build_epic_map.py:41` sets `CORTEX_COMMAND_ROOT`. Replace with `CORTEX_REPO_ROOT` injection.
  - `just test` invokes the project's standard test runner. Existing tests must pass under the converted code per spec R3g and R6d.
  - Sanity probes: `cortex --print-root --format json | jq .` returns valid JSON; `cortex upgrade` exits 0 with the advisory message on stdout.
- **Verification**: `just test` — pass if exit 0. Plus `cortex --print-root --format json | python3 -c "import json, sys; d = json.loads(sys.stdin.read()); assert 'version' in d and 'root' in d"` — pass if exit 0. Plus `cortex upgrade; echo $?` — pass if exit 0.
- **Status**: [x] complete

## Verification Strategy

End-to-end: from a fresh terminal with `uv` available but no prior `cortex` install, run `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0`, then `cortex --print-root --format json` to confirm the wheel-installed CLI works (target state). Separately, in a Claude Code session with the cortex-overnight-integration plugin installed and `cortex` absent from PATH, invoke an MCP tool (e.g., `overnight_status`) and confirm `_ensure_cortex_installed()` fires (NDJSON entry at `~/.local/state/cortex-command/last-error.log` with `stage: "first_install"` for the install-attempt audit trail; `cortex` becomes present on PATH after the call). The test pair `tests/test_no_clone_install.py::test_target_state` and `::test_mcp_first_install_hook` exercises both surfaces in CI.

## Veto Surface

- **Tag literal `v0.1.0` is hardcoded in three places** (`server.py:CLI_PIN`, `install.sh`, `docs/install.md`). A version bump requires updating all three. The user may prefer a single source of truth — e.g., a `CLI_TAG` constant in `pyproject.toml` consumed by all three — at the cost of additional indirection. Plan keeps the duplication for v0.1.0; revisit at v0.2.0 if it becomes painful.
- **Tag bootstrap window is unsafe under any ordering that lands implementation commits before the tag exists.** This is a SEPARATE concern from version-bump duplication: the FIRST tag must exist at the remote BEFORE plugin auto-update can deliver `server.py` (with `CLI_PIN[0] = "v0.1.0"`) to users. See "Bootstrap-ordering decision" in Open Decisions below — the user must pick a sequencing strategy.
- **`Path.cwd()` semantics for user-data lookups** were chosen during research (Q3) over the explicit `CORTEX_REPO_ROOT`-required alternative. The sanity check raises clearly when CWD has no `lifecycle/` AND no `backlog/`, but a user running cortex from `~/Downloads/` (with `CORTEX_REPO_ROOT` unset) gets an error instead of silent corruption — this is the intended behavior. **Cross-process root divergence**: dashboard and CLI launched from different CWDs without `CORTEX_REPO_ROOT` resolve to different roots. Mitigation: `cli_handler.py:_resolve_repo_path()` already handles this for the CLI's own subprocesses; the dashboard is launched independently by the user via `just dashboard`, so user discipline ("run both from the same project root") is the de-facto contract. Plan does not add a runner-injected `CORTEX_REPO_ROOT` env-var compensator at this stage; revisit if observability bug reports surface.
- **`install.sh` v0.1.0 hardcoding** is the cheapest path; resolving the latest tag dynamically (`gh release view --json tagName`) requires the user to have `gh` installed, which conflicts with the bootstrap goal. Plan stays with hardcoded tag.
- **MCP first-install hook is unconditional except for `CORTEX_AUTO_INSTALL=0`** — the only opt-out. The user accepted zero-friction in research Q1 (auto-RCE blast radius accepted as documented trade-off). Plan does not add interactive opt-in.
- **`install_guard.py` cleanup scope** (Task 6) is intentionally narrow — only `~/.cortex` and `CORTEX_COMMAND_ROOT` references in error messages. A broader `install_guard.py` audit is out of scope.

## Resolved Decisions (from critical review, 2026-04-29)

The three architectural questions surfaced by critical review were resolved by the user with "best long-term" deliberation:

### D1 → tag-before-coupling discipline (resolved)

**Resolution**: No release branch; no force-push pre-tag. Instead, sequence the task graph so the v0.1.0 tag is pushed (Task 14) BETWEEN foundation tasks (1-6, 13, 16) and plugin/install/doc tasks (7, 8, 9, 10, 11, 12) that reference the literal `v0.1.0`. This eliminates the dangling-pointer window without forcing a release-branch overhead. The same discipline applies to all subsequent versions: push the CLI tag first; only then bump the plugin's `CLI_PIN[0]` to reference it.

**Workflow consequences** (documented in `docs/release-process.md` per Task 12):
- Continue committing to main as before — no release-branch flow.
- Tags are deliberate version-bump actions, not automatic on every push.
- SemVer cadence: 0.1.0 → 0.1.1 (patch), → 0.2.0 (minor feature), → 1.0.0 (breaking). Bump `pyproject.toml` version, add `CHANGELOG.md` entry, commit, tag the commit, push commit + tag (workflow auto-publishes).
- `CLI_PIN[1]` (schema major) bumps when the print-root JSON envelope shape changes incompatibly; distinct from `CLI_PIN[0]` (CLI tag) and from pyproject.toml's package version.

### D2 → amend spec R2d; `root` is user project, add `package_root` (resolved)

**Resolution**: `cortex --print-root --format json` returns:
```json
{"version": "1.1", "root": <user-project-root>, "package_root": <package-install-dir>, "remote_url": <git-or-empty>, "head_sha": <git-or-empty>}
```
`root` is resolved via `_resolve_user_project_root()` (single source of truth). `package_root` is a new additive field for package introspection. JSON envelope `version` bumps from `1.0` to `1.1` (additive — `1.0` consumers ignore `package_root`). Spec R2d is amended in Task 6 to reflect the new shape.

### D3 → intended dormancy; short-circuit R8 throttle and R10 orchestration (resolved)

**Resolution**: under wheel install there is no upstream remote and no git clone — R8 throttle's premise (rate-limited upstream probe) and R10's `cortex upgrade` orchestration don't apply. R4 first-install hook plus R13 schema-floor gate are the upgrade arrow. Task 16 (new) short-circuits R8 and R10 explicitly so consumers don't rely on empty-string-sentinel side effects.

## Scope Boundaries

Excluded per spec Non-Requirements:
- PyPI publication (deferred follow-up).
- Homebrew tap (ticket 125 wontfix).
- `cortex migrate` subcommand (runbook in `docs/migration-no-clone-install.md` is sufficient).
- Audit/conversion of dev-only `Path(__file__)` sites in `tests/` (4 sites kept as-is; tests not shipped in wheel).
- Concurrent first-install fault-injection tests (deferred to slow-tier opt-in).
- `dashboard/app.py:184` `.pid` file relocation to `XDG_RUNTIME_DIR`.
- Eliminating `~/.cortex` references entirely (some remain in test fixtures and 146-era code paths).
- Self-upgrade via `cortex upgrade` (architecturally impossible; advisory wrapper only).
