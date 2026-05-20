# Plan: installation-integrity-layer-bash-to-entry

## Overview
Promote 13 skill-prose-referenced `bin/cortex-*` scripts to wheel-tier Python entry points, replace each with a dual-channel wrapper that emits a remediation hint at `command not found` time, and extend `cortex-session-start-path-bootstrap.sh` with a best-effort PATH self-test as a secondary advisory channel. The migration follows the established `cortex_command.<subpackage>.<module>:main` pattern, pre-allocates all 13 `[project.scripts]` entries in Task 1 to eliminate concurrent-pyproject-edit conflicts, and protects against silent regression with golden-replay parity tests captured pre-deletion of each bash script.

**Architectural Pattern**: layered
<!-- Relocates per-script logic from the `bin/` shim layer into the wheel-tier Python module layer and extends an existing hook with a probe. Layered tag reflects the wheel ↔ binstub ↔ hook layering established by ADR-0002. -->

## Outline

### Phase 1: Foundation (tasks 1–8)
**Goal**: Pre-allocate all 13 `[project.scripts]` entries, promote `cortex-log-invocation` as the keystone script, establish the dual-channel wrapper template (which doubles as the primary `command not found`-time remediation channel), rewrite every non-promoted bash/python script's sibling-script lookup, and ship the parity-test scaffolding all future phases consume.
**Checkpoint**: `cortex-log-invocation` resolves to a `~/.local/bin/` binstub after `uv tool install --reinstall --refresh`; all non-promoted `bin/cortex-*` scripts that invoke log-invocation use the loud-on-broken pattern appropriate to their shebang; `tests/test_cortex_log_invocation_parity.py`, `tests/test_parity_contract.py`, and `tests/test_phase1_sibling_rewrite_smoke.py` exit 0.

### Phase 2: DR4 milestone (tasks 9–10)
**Goal**: Promote `cortex-resolve-backlog-item` per DR4 — the most-load-bearing remaining bash script (called once per `/cortex-core:lifecycle` invocation) — using the Phase 1 template, and remove the stale `install_guard` comment block.
**Checkpoint**: `cortex-resolve-backlog-item` is a wheel entry point; the previous `bin/cortex-resolve-backlog-item:31-36` comment block referencing `__init__.py:13-15` is gone; `tests/test_cortex_resolve_backlog_item_parity.py` exits 0.

### Phase 3: Bulk migration (tasks 11–21)
**Goal**: Promote the remaining 11 skill-prose-referenced scripts, each shipping its module, dual-channel wrapper, captured fixtures, and parity test. Because all pyproject.toml edits are pre-allocated in Task 1, these tasks have no shared-file conflicts and are genuinely parallel-eligible (worktree-isolated).
**Checkpoint**: All 13 promoted scripts resolve via `importlib.metadata.entry_points(group='console_scripts')`; the four high-risk parity tests (`cortex-lifecycle-state`, `cortex-backlog-ready`, `cortex-lifecycle-counters`, `cortex-morning-review-gc-demo-worktrees`) exit 0.

### Phase 4: PATH self-test (tasks 22–25)
**Goal**: Add the `cortex_command.doctor.path_self_test` module and wire it into `cortex-session-start-path-bootstrap.sh` as a **secondary, best-effort** advisory channel. The primary remediation channel is the wrapper's exit-2 message (delivered at `command not found` time per Task 3) which bypasses claude-code#16538's plugin-hook silent-drop.
**Checkpoint**: The hook emits `additionalContext` when an entry point is missing AND Claude Code's plugin-hook pipeline does not drop it; the hook stays silent when `CORTEX_DEV_MODE=1` is set or `$CWD/pyproject.toml` names cortex-command; the hook never writes a sentinel file. Phase 4's value floor is the wrapper-time message from Task 3, not the SessionStart advisory.

### Phase 5: Docs + prose sweep (tasks 26–28)
**Goal**: Document the `CORTEX_COMMAND_FORCE_SOURCE=1` escape hatch in `cortex/requirements/project.md`, rewrite remaining path-qualified `bin/cortex-<name>` skill-prose references to bare-name, and confirm `cortex-check-parity` stays green post-migration.
**Checkpoint**: `grep -c CORTEX_COMMAND_FORCE_SOURCE cortex/requirements/project.md` = 1; the `grep -rnE 'bin/cortex-(...)'` sweep returns 0 hits; `bin/cortex-check-parity --audit` exits 0.

## Tasks

### Task 1: Pre-allocate all 13 `[project.scripts]` entries + create `cortex_command/log_invocation.py` [DONE]
- **Files**: `cortex_command/log_invocation.py` (new), `pyproject.toml`
- **What**: In a single coordinated edit, add ALL 13 new `[project.scripts]` entries to `pyproject.toml` alphabetically-positioned with the existing block. Entry-to-module mapping (final paths confirmed): `cortex-auto-bump-version = "cortex_command.auto_bump_version:main"`, `cortex-backlog-ready = "cortex_command.backlog.ready:main"`, `cortex-check-parity = "cortex_command.parity_check:main"`, `cortex-check-prescriptive-prose = "cortex_command.lint.prescriptive_prose:main"`, `cortex-commit-preflight = "cortex_command.commit.preflight:main"`, `cortex-complexity-escalator = "cortex_command.lifecycle.complexity_escalator:main"`, `cortex-git-sync-rebase = "cortex_command.git.sync_rebase:main"`, `cortex-lifecycle-counters = "cortex_command.lifecycle.counters:main"`, `cortex-lifecycle-state = "cortex_command.lifecycle.state_cli:main"`, `cortex-load-parent-epic = "cortex_command.backlog.load_parent_epic:main"`, `cortex-log-invocation = "cortex_command.log_invocation:main"`, `cortex-morning-review-gc-demo-worktrees = "cortex_command.overnight.gc_demo_worktrees:main"`, `cortex-resolve-backlog-item = "cortex_command.backlog.resolve_item:main"`. Then port the bash logic of `bin/cortex-log-invocation` (76 lines — a thin JSONL invocation logger) into `cortex_command/log_invocation.py` exposing `main(argv: List[str] | None = None) -> int`. The other 12 module files are stubs in this task (a docstring + `def main(argv=None): raise NotImplementedError("...promoted in Task N")` placeholder is acceptable to avoid `importlib.metadata` returning entries for which the module does not yet exist — but the placeholder MUST `sys.exit(70)` rather than raise to keep the wheel installable from any intermediate commit).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Pre-allocating all 13 entries in one task eliminates the pyproject.toml-as-serialization-point conflict identified in critical review. Stub modules ship with `main()` placeholders so the wheel installs cleanly; subsequent tasks replace the stub with the real port + delete the placeholder. JSON-emission prescription: use `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))` — the `ensure_ascii=False` is critical to match `jq -c`'s default UTF-8 emission for non-ASCII content (em-dashes, smart quotes, names with diacritics common throughout lifecycle/backlog content). Argparse parser `prog` matches the binstub name. Reuse `cortex_command/common.py` helpers where applicable.
- **Verification**: `python3 -c "import cortex_command.log_invocation; assert callable(cortex_command.log_invocation.main)"` exits 0. After `uv tool install --reinstall --refresh git+<repo>@<branch>` (operator step), `python3 -c "import importlib.metadata as m; required={'cortex-auto-bump-version','cortex-backlog-ready','cortex-check-parity','cortex-check-prescriptive-prose','cortex-commit-preflight','cortex-complexity-escalator','cortex-git-sync-rebase','cortex-lifecycle-counters','cortex-lifecycle-state','cortex-load-parent-epic','cortex-log-invocation','cortex-morning-review-gc-demo-worktrees','cortex-resolve-backlog-item'}; eps={ep.name for ep in m.entry_points(group='console_scripts')}; assert required <= eps, sorted(required - eps)"` exits 0. `command -v cortex-log-invocation | grep -q '/.local/bin/'` exits 0.
- **Status**: [x] done (commit `cde30477`)

### Task 2: Capture `cortex-log-invocation` golden-replay fixtures + write determinism README [DONE]
- **Files**: `tests/fixtures/cortex-log-invocation/` (new directory, ≥3 `.argv`/`.stdin`/`.stdout`/`.stderr`/`.exitcode` quintuples), `tests/fixtures/cortex-log-invocation/README.md` (new)
- **What**: Before deleting the bash version, run the current `bin/cortex-log-invocation` against 3–5 representative invocations under the determinism harness (`jq --version` recorded, `LC_ALL=C`, `TZ=UTC`, timestamps frozen via `sed` filter). Commit the captured `.argv`/`.stdin`/`.stdout`/`.stderr`/`.exitcode` quintuples. Author `README.md` documenting the determinism harness: jq version pinned, `LC_ALL=C`, `TZ=UTC`, timestamp-handling, **plus the named-tolerance categories the parity test consumes** (Unicode-escape, number-format, trailing-newline, key-reorder — see Task 5).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The README enumerates which divergence classes the parity test will tolerate per the broadened structural-equivalence rubric in Task 5. Fixtures themselves capture the bash version's literal output; the README is the contract that documents what tolerances are accepted at compare-time.
- **Verification**: `ls tests/fixtures/cortex-log-invocation/ | grep -cE '\.(stdin|argv|stdout|stderr|exitcode)$'` ≥ 12 — pass if count ≥ 12. `grep -c -E 'jq.*--version|LC_ALL=C|TZ=UTC' tests/fixtures/cortex-log-invocation/README.md` ≥ 3 — pass if count ≥ 3.
- **Status**: [x] done (commit `51c9e67f`, count = 20 quintuples)

### Task 3: Replace `bin/cortex-log-invocation` with canonical wrapper + ship the user-facing `command not found` remediation message [DONE]
- **Files**: `bin/cortex-log-invocation`
- **What**: Replace the existing bash script with the canonical dual-channel wrapper template. Branch order: (a) if `CORTEX_COMMAND_FORCE_SOURCE=1` is set, exec via `python3 -m cortex_command.log_invocation` (using `CORTEX_COMMAND_ROOT` if set, else `dirname "$0"/..`); (b) else try wheel-import probe (`python3 -c "import cortex_command.log_invocation"`) — on success, exec via wheel; (c) else fall back to working-tree mode if `pyproject.toml` names cortex-command; (d) else exit 2 with the **canonical remediation message**: `cortex-log-invocation: cortex-command wheel not found on PATH. To fix: run 'uv tool install --reinstall --refresh git+https://github.com/charleshall888/cortex-command.git@<latest-tag>'. If this happens after a recent upgrade, your wheel may be stale.` This branch (d) message is the **primary remediation channel** that bypasses claude-code#16538 — every wrapper in Tasks 9–21 includes the same message structure (with binstub name substituted). The wrapper itself is the script; no sibling-lookup applies.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The existing `bin/cortex-morning-review-complete-session` template does NOT honor `CORTEX_COMMAND_FORCE_SOURCE=1` (wheel-import wins unconditionally), regressing the working-tree escape hatch. The new template places `CORTEX_COMMAND_FORCE_SOURCE=1` FIRST per requirement 2. The branch-(d) message is new vs the existing template — it's where the missing-entry-point remediation hint surfaces to the user. Because this fires at the actual failure moment (a skill shelled out to a missing binstub), it's the channel that delivers value even if SessionStart's `additionalContext` is dropped by #16538. Preserve `set -euo pipefail` and `chmod +x`.
- **Verification**: With `CORTEX_COMMAND_FORCE_SOURCE=1 CORTEX_COMMAND_ROOT=$(pwd) bin/cortex-log-invocation --help`, exit code 0 and stdout originates from `cortex_command/log_invocation.py`. With no wheel installed and no working tree, `bin/cortex-log-invocation` exits 2 with stderr containing the literal substring `uv tool install --reinstall --refresh`. `test -x bin/cortex-log-invocation` exits 0.
- **Status**: [x] done (commit `7c05529c`)

### Task 4a: Sibling-pattern rewrite — bash subset (non-promoted only) [DONE]
- **Files**: bash-shebang `bin/cortex-*` scripts that are NOT being promoted in Phases 2–3 AND currently invoke sibling `cortex-log-invocation`. Re-enumerate at task-execution time via `for f in bin/cortex-*; do head -1 "$f" | grep -q '^#!.*bash' && grep -l 'cortex-log-invocation' "$f"; done | grep -vE '(log-invocation|resolve-backlog-item|auto-bump-version|backlog-ready|check-parity|check-prescriptive-prose|commit-preflight|complexity-escalator|git-sync-rebase|lifecycle-counters|lifecycle-state|load-parent-epic|morning-review-gc-demo-worktrees)$'`. Expected hits: `cortex-jcc`, `cortex-invocation-report` (if bash), and any other bash utility not in the promoted set.
- **What**: For each in-scope bash script, locate the existing sibling-call line (which may be at line 2, 12, 28, 35, or another position — NOT presumed to be line 1–2). Replace it in place with:
  ```bash
  if command -v cortex-log-invocation >/dev/null; then
    cortex-log-invocation "$0" "$@" || echo "cortex-log-invocation failed: $?" >&2
  fi
  ```
  Distinguishes "missing" (silent skip) from "present-but-broken" (loud stderr warning). The promoted scripts in Phases 2–3 do NOT go through this task — their entire file is replaced by the wrapper template in their respective tasks, and the wrapper itself does not invoke `cortex-log-invocation`. (Rationale: the wrapper is essentially `exec`-into-the-wheel and the wheel module's own entry can choose to log if desired — no sibling-call needed.)
- **Depends on**: none
- **Complexity**: simple
- **Context**: Critical-review finding established that 7 of 13 promoted scripts use a Python `subprocess.run(...)` one-liner, not the bash pattern; those are handled by Task 4b. Critical-review further established that Task 3's wrapper template has no sibling-call, so Task 4 must NOT touch the promoted scripts (their bin/ files are replaced wholesale in Tasks 9–21). The in-place edit replaces the existing call at whatever line it lives on, not "lines 1–2" mechanically.
- **Verification**: For every non-promoted bash script enumerated above: `grep -lE 'command -v cortex-log-invocation' <file>` returns the file path — pass if count = expected. `grep -c '"\$(dirname "\$0")/cortex-log-invocation"' bin/cortex-* | grep -v ':0$' | wc -l` = 0 — no non-promoted bash script retains the old pattern. The smoke test in Task 7 exercises each rewritten script.
- **Status**: [x] done (commit `d6e837d2`; rewrote `cortex-jcc` and `cortex-morning-review-complete-session`; `cortex-invocation-report` correctly skipped — string-literal-only)

### Task 4b: Sibling-pattern rewrite — Python/PEP 723 subset (non-promoted only) [DONE]
- **Files**: `#!/usr/bin/env python3` or `#!/usr/bin/env -S uv run --script` `bin/cortex-*` scripts that are NOT being promoted AND currently invoke sibling `cortex-log-invocation` via a Python one-liner. Re-enumerate at task-execution time. Expected hits: `cortex-archive-rewrite-paths`, `cortex-archive-sample-select`, `cortex-audit-doc`, `cortex-check-events-registry`, `cortex-check-path-hardcoding`, `cortex-count-tokens`, `cortex-measure-l1-surface`, `cortex-requirements-parity-audit`, `cortex-rewrite-cli-pin` — modulo whichever are already in the promoted set.
- **What**: For each in-scope Python/PEP 723 script, locate the existing `subprocess.run([os.path.join(os.path.dirname(os.path.realpath(__file__)), "cortex-log-invocation"), sys.argv[0], *sys.argv[1:]], check=False)` (or similar Python-form sibling-call). Replace with the canonical Python rewrite:
  ```python
  import shutil, subprocess, sys
  _li = shutil.which("cortex-log-invocation")
  if _li is not None:
      try:
          subprocess.run([_li, sys.argv[0], *sys.argv[1:]], check=False, timeout=2)
      except (subprocess.SubprocessError, OSError) as _e:
          print(f"cortex-log-invocation failed: {_e}", file=sys.stderr)
  ```
  This is the Python equivalent of Task 4a's bash idiom: silent skip when log-invocation is missing from PATH; loud stderr warning when it's present-but-broken. The same `cortex-log-invocation failed:` stderr literal appears so Task 7's smoke test can cover both shebang classes.
- **Depends on**: none
- **Complexity**: simple
- **Context**: This task addresses critical-review A-class finding: bash syntax is not valid Python. The Python rewrite uses `shutil.which()` (PATH-based lookup matching `command -v` semantics) and produces stderr line `cortex-log-invocation failed: <msg>` so Task 7's smoke-test assertion catches regressions in both shebang classes. Promoted-script files are NOT touched here (they're wholly replaced by wrappers in Tasks 9–21).
- **Verification**: For every non-promoted Python/PEP 723 script enumerated above: `grep -lE 'shutil.which\("cortex-log-invocation"\)' <file>` returns the file path. `grep -lE 'cortex-log-invocation failed:' <file>` returns the file path. The smoke test in Task 7 exercises each rewritten script and asserts no spurious `cortex-log-invocation failed:` stderr appears under normal conditions.
- **Status**: [x] done (commit `7437f64c`; 9 scripts rewritten)

### Task 5: Add `tests/test_parity_contract.py` with broadened named-tolerance escape [DONE]
- **Files**: `tests/test_parity_contract.py` (new)
- **What**: Implement the parity contract per the revised tolerance rubric. Helper functions: `assert_byte_identical(actual, expected)` and `assert_structurally_equivalent(actual, expected, stream, tolerances)`. The `@pytest.mark.structural_equivalence(stream="stdout"|"stderr", tolerances=["unicode-escape", "number-format", "trailing-newline", "key-reorder"])` decorator opts a stream into a NAMED SET of tolerance categories. Categories:
  - `key-reorder`: intra-object JSON key ordering (e.g., `{"a":1,"b":2}` ↔ `{"b":2,"a":1}`)
  - `unicode-escape`: ASCII-escape form `\uXXXX` ↔ raw UTF-8 byte form (`{"x":"é"}` ↔ `{"x":"é"}`)
  - `number-format`: integer-valued floats (`1` ↔ `1.0`); leading zeros excluded
  - `trailing-newline`: presence/absence of one trailing `\n` on stdout
  - `error-formatter-shape`: stderr text from a known-error path (jq's diagnostic vs Python's `JSONDecodeError`) — opt-in for parity tests of scripts that exercise error paths the bash version emits formatter-specific bytes for. When this tolerance is active, the test compares stderr by checking that BOTH outputs are non-empty and non-zero exit, OR both empty/zero exit — but does NOT compare the bytes themselves.
- **Depends on**: none
- **Complexity**: simple
- **Context**: This responds to critical-review finding that the prior "intra-object key reordering only" escape was too narrow to absorb the real jq→Python diff classes. The contract still holds the discipline (every tolerance is named, opt-in, and per-stream) but admits the empirically-realistic divergence categories. The `error-formatter-shape` tolerance is the explicit carve-out for jq error messages that Python's `json` module cannot byte-replicate without literal string forgery. Each parity test (Tasks 6, 9, 11–21, 20) MUST declare its tolerance set explicitly via the decorator — no implicit tolerances.
- **Verification**: `python3 -m pytest tests/test_parity_contract.py` — pass if exit 0, all tests pass. The test file exercises EACH named tolerance category in both directions (passes under tolerance opt-in; fails when tolerance is not opted in).
- **Status**: [x] done (commit `8e2c2bc5`, 30 tests pass)

### Task 6: Add `tests/test_cortex_log_invocation_parity.py` [DONE]
- **Files**: `tests/test_cortex_log_invocation_parity.py` (new)
- **What**: For each fixture quintuple in `tests/fixtures/cortex-log-invocation/`, invoke `python3 -m cortex_command.log_invocation` with the fixture's `.argv` and stdin, and assert byte-identical or named-tolerance-equivalent stdout/stderr/exit-code against the fixture's captured `.stdout`/`.stderr`/`.exitcode`. Use the `@pytest.mark.structural_equivalence` decorator on parity-class tests with the tolerances appropriate to each fixture (most fixtures need `["unicode-escape", "trailing-newline"]` at minimum for stdout-JSON).
- **Depends on**: [1, 2, 5]
- **Complexity**: simple
- **Context**: Use `subprocess.run` with `env=...` to override `LC_ALL`, `TZ`, and other determinism-sensitive variables to match fixture-capture. The fixture README from Task 2 enumerates which tolerance categories the test declares.
- **Verification**: `python3 -m pytest tests/test_cortex_log_invocation_parity.py` — pass if exit 0, all tests pass.
- **Status**: [x] done (commit `528e36b2`, 16/16 tests pass; named tolerances applied to JSONL side-effect rather than empty streams)

### Task 7: Add `tests/test_phase1_sibling_rewrite_smoke.py` covering both shebang classes [DONE]
- **Files**: `tests/test_phase1_sibling_rewrite_smoke.py` (new)
- **What**: For each `bin/cortex-*` script rewritten in tasks 4a OR 4b, invoke it with a trivial argv (`--help` if argparse accepts it, else `--cortex-smoke-test-flag` — a flag the script's own argparse will reject with nonzero exit). Assert that:
  - No spurious `cortex-log-invocation failed:` warning appears on stderr under normal conditions (covers both bash idiom and Python idiom — both emit the same literal substring).
  - The script's exit status is correctly its OWN (nonzero from argparse, or 0 from `--help`).
  - For Python/PEP 723 scripts, additionally assert no `SyntaxError` traceback on stderr (defensive check against accidental bash-block injection).
  Set `CORTEX_INVOCATION_LOG=/dev/null` or equivalent to avoid side-effecting state.
- **Depends on**: [4a, 4b]
- **Complexity**: simple
- **Context**: The literal stderr substring `cortex-log-invocation failed:` is identical across the bash and Python rewrite idioms by design (Task 4a's `echo` and Task 4b's `print(f"...")` both emit the same prefix), so one assertion covers both shebang classes. The `SyntaxError` check is the defensive verification against the critical-review-flagged hazard of accidentally inserting bash syntax into a Python script.
- **Verification**: `python3 -m pytest tests/test_phase1_sibling_rewrite_smoke.py` — pass if exit 0.
- **Status**: [x] done (commit `4cd1b39c`, 8 pass + 3 PEP 723 tests gated `@pytest.mark.slow`; `CORTEX_INVOCATION_LOG=/dev/null` env var the spec suggested isn't actually wired — agent used PATH isolation + HOME redirect as equivalent)

### Task 8: Capture `cortex-resolve-backlog-item` golden-replay fixtures pre-deletion [DONE]
- **Files**: `tests/fixtures/cortex-resolve-backlog-item/` (new directory, ≥3 quintuples), `tests/fixtures/cortex-resolve-backlog-item/README.md` (new)
- **What**: Pre-deletion of `bin/cortex-resolve-backlog-item`, capture ≥3 representative invocations under the determinism harness (jq pinned, `LC_ALL=C`, `TZ=UTC`). Required cases: (a) unambiguous match (exit 0, JSON on stdout), (b) ambiguous match (exit 2, candidates on stderr), (c) no match (exit 3). Write README documenting harness + applicable tolerance set (e.g., `unicode-escape`, `trailing-newline` for the JSON stdout).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The five-value exit-code closed set {0, 2, 3, 64, 70} — fixtures cover the three operationally-common values. Generate against backlog state at HEAD (commit the snapshot's JSON).
- **Verification**: `ls tests/fixtures/cortex-resolve-backlog-item/ | grep -cE '\.(stdin|argv|stdout|stderr|exitcode)$'` ≥ 12 — pass if count ≥ 12. `grep -c -E 'jq.*--version|LC_ALL=C|TZ=UTC' tests/fixtures/cortex-resolve-backlog-item/README.md` ≥ 3 — pass if count ≥ 3.
- **Status**: [x] done (commit `892b325a`, 15 quintuple files; covers exit 0, 2, 3)

### Task 9: Promote `cortex-resolve-backlog-item` to wheel entry point + remove stale install_guard comment [DONE]
- **Files**: `cortex_command/backlog/resolve_item.py` (replaces Task 1's stub), `bin/cortex-resolve-backlog-item` (replace with wrapper using Task 3 template), `tests/test_cortex_resolve_backlog_item_parity.py` (new)
- **What**: Port the PEP 723 logic (417 lines) into `cortex_command/backlog/resolve_item.py` exposing `main(argv) -> int`. Preserve the five-value exit-code contract (0/2/3/64/70). The `[project.scripts]` entry was pre-allocated in Task 1 — this task replaces the stub. Replace `bin/cortex-resolve-backlog-item` with the dual-channel wrapper (Task 3 template, exit-2 message substituting `cortex-resolve-backlog-item` for the binstub name). Author the parity test consuming Task 8 fixtures. The replacement wrapper drops the stale install_guard comment block (former lines 31–36 referencing `cortex_command/__init__.py:13-15`, which no longer exist).
- **Depends on**: [3, 5, 8]
- **Complexity**: complex
- **Context**: Reuse `cortex_command/common.py`'s `slugify()` and frontmatter helpers. Use `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))` per Task 1's prescription. The wrapper's exit-2 message is the user-facing missing-entry-point remediation channel.
- **Verification**: `python3 -c "import cortex_command.backlog.resolve_item; cortex_command.backlog.resolve_item.main"` exits 0. `grep -c '__init__.py:13-15' bin/cortex-resolve-backlog-item cortex_command/ 2>/dev/null` = 0. `python3 -m pytest tests/test_cortex_resolve_backlog_item_parity.py` exits 0.
- **Status**: [x] done (commit `1f4852a8`, 12 tests pass; wrapper includes cortex-log-invocation shim line — pre-commit hook enforces it on all bin/cortex-* except log-invocation itself)

### Task 10: Remove stale install_guard comment cross-references in any other locations [DONE]
- **Files**: `cortex_command/common.py` (conditional — only if the stale comment crops up elsewhere), any other file matching `grep -rlE '__init__.py:13-15' .` post-Task-9
- **What**: After Task 9 removes the stale comment from `bin/cortex-resolve-backlog-item`, sweep the repo for any other stale `__init__.py:13-15` cross-references (the lines no longer exist post-refactor). Remove them. If no other hits, this task is a no-op cleanup verification.
- **Depends on**: [9]
- **Complexity**: trivial
- **Context**: This task exists as a defensive cleanup — the spec's requirement 6 acceptance says `grep -c '__init__.py:13-15' bin/ cortex_command/ 2>/dev/null` = 0 across the whole tree, not just the promoted file.
- **Verification**: `grep -rc '__init__.py:13-15' bin/ cortex_command/ 2>/dev/null | grep -v ':0$' | wc -l` = 0 — pass if count = 0.
- **Status**: [x] done (no-op; Task 9 covered the only reference, verification passes with 0 hits)

### Task 11: Promote `cortex-auto-bump-version` [DONE]
- **Files**: `cortex_command/auto_bump_version.py` (replaces Task 1's stub), `bin/cortex-auto-bump-version`, `tests/fixtures/cortex-auto-bump-version/` (new), `tests/test_cortex_auto_bump_version_parity.py` (new)
- **What**: Port `bin/cortex-auto-bump-version` (220 lines, `#!/usr/bin/env python3`) into `cortex_command/auto_bump_version.py` exposing `main(argv) -> int`. Replace `bin/` with wrapper (Task 3 template). Capture ≥3 fixtures pre-deletion + README. Author parity test.
- **Depends on**: [3, 5]
- **Complexity**: simple
- **Context**: Already Python; promotion is a file-move with `main()` extraction. Module at `cortex_command/` root (precedent: `cortex_command/discovery.py`). Pre-deletion capture against a synthetic pyproject.toml in `tmp_path`. JSON-emission uses Task 1's `ensure_ascii=False` prescription.
- **Verification**: `python3 -c "import cortex_command.auto_bump_version"` exits 0. `python3 -m pytest tests/test_cortex_auto_bump_version_parity.py` exits 0.
- **Status**: [x] done (commit `6cd68ba5`, 18 parity tests pass + 20 existing tests still pass)

### Task 12: Promote `cortex-check-parity` [DONE]
- **Files**: `cortex_command/parity_check.py` (replaces Task 1's stub), `bin/cortex-check-parity`, `tests/fixtures/cortex-check-parity/` (new), `tests/test_cortex_check_parity_parity.py` (new)
- **What**: Port `bin/cortex-check-parity` (1792 lines, `#!/usr/bin/env python3`) into `cortex_command/parity_check.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures pre-deletion + README. Author parity test.
- **Depends on**: [3, 5]
- **Complexity**: complex
- **Context**: **Largest task in Phase 3** — 1792-line port. Realistic effort budget: 60–90 min, not the typical 5–15 min target. The script is already Python; the migration is structurally a file-move with `main()` extraction. The script consumes `bin/.parity-exceptions.md`; the parsed-exceptions logic moves with the script (Task 24 reuses this parser). Fixture cases: (a) all-green state, (b) W003 orphan-bin, (c) W005 wired-but-allowlisted state.
- **Verification**: `python3 -m cortex_command.parity_check --help` exits 0. `python3 -m pytest tests/test_cortex_check_parity_parity.py` exits 0.
- **Status**: [x] done (commit `0970416a`, 12 parity tests pass; 1796-line port; agent's context exhausted after commit while composing exit report)

### Task 13: Promote `cortex-check-prescriptive-prose` [DONE]
- **Files**: `cortex_command/lint/__init__.py` (new), `cortex_command/lint/prescriptive_prose.py` (replaces Task 1's stub), `bin/cortex-check-prescriptive-prose`, `tests/fixtures/cortex-check-prescriptive-prose/` (new), `tests/test_cortex_check_prescriptive_prose_parity.py` (new)
- **What**: Port `bin/cortex-check-prescriptive-prose` (409 lines, `#!/usr/bin/env python3`) into `cortex_command/lint/prescriptive_prose.py`. Create `cortex_command/lint/__init__.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures + README. Author parity test.
- **Depends on**: [3, 5]
- **Complexity**: simple
- **Context**: New `lint/` subpackage; `__init__.py` is docstring-only. Fixture cases: (a) clean input, (b) input with prescriptive-prose hits, (c) input with `<!-- prescriptive-prose-allow -->` carve-out.
- **Verification**: `python3 -c "import cortex_command.lint.prescriptive_prose"` exits 0. `python3 -m pytest tests/test_cortex_check_prescriptive_prose_parity.py` exits 0.
- **Status**: [x] done (commit `ffa3f8d4`, 9 tests pass; spec carve-out fixture `<!-- prescriptive-prose-allow -->` doesn't match an actual feature — agent substituted `with_fenced_block` case)

### Task 14: Promote `cortex-commit-preflight` [DONE]
- **Files**: `cortex_command/commit/__init__.py` (new), `cortex_command/commit/preflight.py` (replaces stub), `bin/cortex-commit-preflight`, `tests/fixtures/cortex-commit-preflight/` (new), `tests/test_cortex_commit_preflight_parity.py` (new)
- **What**: Port `bin/cortex-commit-preflight` (150 lines, `#!/usr/bin/env python3`) into `cortex_command/commit/preflight.py`. Create `cortex_command/commit/__init__.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures + README. Author parity test.
- **Depends on**: [3, 5]
- **Complexity**: simple
- **Context**: New `commit/` subpackage with empty `__init__.py`. Fixture cases: (a) staged tree valid, (b) parity-check violation, (c) banned-pattern detected.
- **Verification**: `python3 -c "import cortex_command.commit.preflight"` exits 0. `python3 -m pytest tests/test_cortex_commit_preflight_parity.py` exits 0.
- **Status**: [x] done (commit `290f0edf`, 10 tests pass; spec fixture cases didn't match script's actual exit branches — agent substituted valid_git_repo / empty_repo / not_in_repo; latent id(tmp_path) aliasing hazard in Task 6's pattern flagged but not patched there)

### Task 15: Promote `cortex-complexity-escalator` [DONE]
- **Files**: `cortex_command/lifecycle/__init__.py` (new), `cortex_command/lifecycle/complexity_escalator.py` (replaces stub), `bin/cortex-complexity-escalator`, `tests/fixtures/cortex-complexity-escalator/` (new), `tests/test_cortex_complexity_escalator_parity.py` (new)
- **What**: Port `bin/cortex-complexity-escalator` (344 lines, PEP 723) into `cortex_command/lifecycle/complexity_escalator.py`. Create `cortex_command/lifecycle/__init__.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures + README. Author parity test. Move PEP 723 inline deps into `pyproject.toml [project] dependencies` if any are not already declared.
- **Depends on**: [3, 5]
- **Complexity**: complex
- **Context**: Emits events to `events.log`; registry entry in `bin/.events-registry.md` remains pointing at same emitter name. Fixture cases: (a) escalation trigger met → `complexity_override` event emitted, (b) trigger not met → no emission, (c) ambiguous-tier path.
- **Verification**: `python3 -c "import cortex_command.lifecycle.complexity_escalator"` exits 0. `python3 -m pytest tests/test_cortex_complexity_escalator_parity.py` exits 0.
- **Status**: [x] done (commit `5f0d16eb`, 9 parity + 35 existing tests pass; agent also updated `tests/test_complexity_escalator.py` to import from module — repair for downstream regression from bin replacement)

### Task 16: Promote `cortex-load-parent-epic` [DONE]
- **Files**: `cortex_command/backlog/load_parent_epic.py` (replaces stub), `bin/cortex-load-parent-epic`, `tests/fixtures/cortex-load-parent-epic/` (new), `tests/test_cortex_load_parent_epic_parity.py` (new)
- **What**: Port `bin/cortex-load-parent-epic` (473 lines, PEP 723) into `cortex_command/backlog/load_parent_epic.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures + README. Author parity test. Move PEP 723 inline deps if needed.
- **Depends on**: [3, 5]
- **Complexity**: complex
- **Context**: Reuses `cortex_command/backlog/build_epic_map.py` helpers where applicable. Fixture cases: (a) valid parent → structured JSON, (b) no parent → silent exit 0, (c) broken parent → nonzero with stderr diagnostic.
- **Verification**: `python3 -c "import cortex_command.backlog.load_parent_epic"` exits 0. `python3 -m pytest tests/test_cortex_load_parent_epic_parity.py` exits 0.
- **Status**: [x] done (commit `808c4772`, 12 tests pass; PEP 723 inline-dep `pyyaml>=6.0` migrated to pyproject.toml + uv.lock)

### Task 17: Promote `cortex-backlog-ready` [DONE]
- **Files**: `cortex_command/backlog/ready.py` (replaces stub), `bin/cortex-backlog-ready`, `tests/fixtures/cortex-backlog-ready/` (new), `tests/test_cortex_backlog_ready_parity.py` (new)
- **What**: Port `bin/cortex-backlog-ready` (17 lines bash) into `cortex_command/backlog/ready.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures against frozen backlog snapshot. Author parity test.
- **Depends on**: [3, 5]
- **Complexity**: simple
- **Context**: Short bash; Python rewrite reads `cortex/backlog/index.json` (or scans `cortex/backlog/*.md` if that's what bash does — inspect at task time). Capture against synthetic backlog snapshot committed under fixtures to avoid live-state drift. One of the four high-risk parity tests per requirement 7.
- **Verification**: `python3 -c "import cortex_command.backlog.ready"` exits 0. `python3 -m pytest tests/test_cortex_backlog_ready_parity.py` exits 0.
- **Status**: [x] done (commit `c065c73b`, 9 tests pass; added 2 entries to `bin/.path-hardcoding-allowlist.md` for user-facing JSON error literals containing `"backlog/"`)

### Task 18: Promote `cortex-git-sync-rebase` [DONE]
- **Files**: `cortex_command/git/__init__.py` (new), `cortex_command/git/sync_rebase.py` (replaces stub), `bin/cortex-git-sync-rebase`, `tests/fixtures/cortex-git-sync-rebase/` (new), `tests/test_cortex_git_sync_rebase_parity.py` (new)
- **What**: Port `bin/cortex-git-sync-rebase` (204 lines bash) into `cortex_command/git/sync_rebase.py`. Create `cortex_command/git/__init__.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures + README. Author parity test.
- **Depends on**: [3, 5]
- **Complexity**: complex
- **Context**: New `git/` subpackage. Retain `subprocess` invocations for git plumbing. Fixture cases: (a) clean rebase, (b) merge-conflict surfaced, (c) no-op. Capture against synthetic git repos in `tmp_path`.
- **Verification**: `python3 -c "import cortex_command.git.sync_rebase"` exits 0. `python3 -m pytest tests/test_cortex_git_sync_rebase_parity.py` exits 0.
- **Status**: [x] done (commit `132ee3e3`; 9 parity tests; checkpoint-time fix added `GIT_CONFIG_*` env overrides to disable commit.gpgsign in test subprocess scope — original agent's tests passed in worktree env, failed on main due to global gpgsign=true)

### Task 19: Promote `cortex-lifecycle-counters` [DONE]
- **Files**: `cortex_command/lifecycle/counters.py` (replaces stub), `bin/cortex-lifecycle-counters`, `tests/fixtures/cortex-lifecycle-counters/` (new), `tests/test_cortex_lifecycle_counters_parity.py` (new)
- **What**: Port `bin/cortex-lifecycle-counters` (83 lines bash) into `cortex_command/lifecycle/counters.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures + README. Author parity test.
- **Depends on**: [3, 5, 15]
- **Complexity**: simple
- **Context**: Depends on Task 15 only for the shared `cortex_command/lifecycle/__init__.py`; modules are otherwise independent. Aggregates counts across multiple lifecycle dirs' events.log files. Fixture cases: (a) zero lifecycles, (b) multiple lifecycles at different phases, (c) lifecycle with malformed events.log line. One of the four high-risk parity tests.
- **Verification**: `python3 -c "import cortex_command.lifecycle.counters"` exits 0. `python3 -m pytest tests/test_cortex_lifecycle_counters_parity.py` exits 0.
- **Status**: [x] done (commit `ee4528bb`, 9 tests pass; counters intentionally do NOT read events.log — verified by `malformed-events-log` fixture case)

### Task 20: Capture `cortex-lifecycle-state` torn-line + `--field` fixtures pre-deletion [DONE]
- **Files**: `tests/fixtures/cortex-lifecycle-state/torn-line.*` quintuple (new); ≥3 representative-real-events.log fixtures; one fixture per supported `--field` value; `tests/fixtures/cortex-lifecycle-state/README.md` (new) enumerating the accepted `--field` set + applicable tolerances.
- **What**: BEFORE writing the Python re-implementation, run current `bin/cortex-lifecycle-state` against (a) a torn-line events.log fixture (capture WHATEVER bash does); (b) 3 representative real-shape fixtures; (c) one fixture per `--field` value bash accepts. Document the accepted `--field` set + applicable parity tolerances (`unicode-escape`, `key-reorder`, `number-format`, `error-formatter-shape` for the torn-line case). Run under determinism harness.
- **Depends on**: none
- **Complexity**: complex
- **Context**: The torn-line fixture sets up the parity contract for whatever bash currently does on malformed input. The README enumerates which tolerance categories apply per-fixture. The `error-formatter-shape` tolerance is the explicit carve-out for jq's error messages — Task 21's Python port doesn't try to byte-replicate jq's diagnostic text, just produces equivalent behavior (nonzero exit + non-empty stderr OR silent skip, matching what bash does).
- **Verification**: `test -f tests/fixtures/cortex-lifecycle-state/torn-line.argv -a -f tests/fixtures/cortex-lifecycle-state/torn-line.stdout -a -f tests/fixtures/cortex-lifecycle-state/torn-line.stderr -a -f tests/fixtures/cortex-lifecycle-state/torn-line.exitcode` exits 0. `ls tests/fixtures/cortex-lifecycle-state/*.argv | wc -l` ≥ 8.
- **Status**: [x] done (commit `f211cfe3`, 8 quintuples + .events.log companions; torn-line actually emits `null` not silent-skip — Task 21 must reproduce exactly)

### Task 21: Promote `cortex-lifecycle-state` [DONE]
- **Files**: `cortex_command/lifecycle/state_cli.py` (replaces stub), `bin/cortex-lifecycle-state`, `tests/test_cortex_lifecycle_state_parity.py` (new)
- **What**: Port `bin/cortex-lifecycle-state` (101 lines bash + jq) into `cortex_command/lifecycle/state_cli.py`. Replace `bin/` with wrapper. Author parity test consuming Task 20 fixtures. Use `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))` for stdout JSON. Apply the `error-formatter-shape` tolerance on stderr for the torn-line fixture; `--help` fixture (if captured) gets manual prose substitution rather than argparse auto-help (the bash version uses `sed -n '2,25p' "$0"` to extract the docblock — the Python port should output the SAME extracted prose as a literal string constant, NOT argparse's auto-generated help, to preserve byte-identical parity on the `--help` fixture).
- **Depends on**: [3, 5, 15, 20]
- **Complexity**: complex
- **Context**: jq-based event-log reducer. Python port reads events.log line-by-line + JSON-decodes + applies `--field` reduction. Reuse `cortex_command/lifecycle_event.py` + `cortex_command/common.py` helpers. The canonical rule: `lifecycle_start.tier` superseded by most recent `complexity_override.to`. The `--help` shape decision (literal string vs argparse) is explicit to avoid critical-review's flagged hazard.
- **Verification**: `python3 -c "import cortex_command.lifecycle.state_cli"` exits 0. `python3 -m pytest tests/test_cortex_lifecycle_state_parity.py` exits 0.
- **Status**: [x] done (commit `017a8f0b`, 24 tests pass; torn-line emits `null\n` exactly via jq-1.8.1 reduce semantics; `--help` is a literal docblock string constant; PYTHONPATH override ensures local module loads under test)

### Task 22: Promote `cortex-morning-review-gc-demo-worktrees` [DONE]
- **Files**: `cortex_command/overnight/gc_demo_worktrees.py` (replaces stub), `bin/cortex-morning-review-gc-demo-worktrees`, `tests/fixtures/cortex-morning-review-gc-demo-worktrees/` (new), `tests/test_cortex_morning_review_gc_demo_worktrees_parity.py` (new)
- **What**: Port `bin/cortex-morning-review-gc-demo-worktrees` (81 lines bash) into `cortex_command/overnight/gc_demo_worktrees.py`. Replace `bin/` with wrapper. Capture ≥3 fixtures + README. Author parity test.
- **Depends on**: [3, 5]
- **Complexity**: simple
- **Context**: `overnight/` subpackage already exists. GC stale demo worktrees from `$TMPDIR/cortex-worktrees/`. Fixtures against synthetic state in `tmp_path`. One of four high-risk parity tests.
- **Verification**: `python3 -c "import cortex_command.overnight.gc_demo_worktrees"` exits 0. `python3 -m pytest tests/test_cortex_morning_review_gc_demo_worktrees_parity.py` exits 0.
- **Status**: [x] done (commit `a2bb8167`, 12 tests pass; uses `<WT_PATH>` placeholder substitution for path-dependent stderr — `git worktree list --porcelain` returns resolved paths that differ from `tmp_path`)

### Task 23: Create `cortex_command/doctor/path_self_test.py` module [DONE]
- **Files**: `cortex_command/doctor/__init__.py` (new), `cortex_command/doctor/path_self_test.py` (new)
- **What**: Implement the PATH self-test per spec requirements 11–14. Public entry `main(argv) -> int` (returns 0 on all paths). Logic: (1) check dogfooder skip predicates ((a) `CORTEX_DEV_MODE=1`, (b) `$CWD/pyproject.toml` matches `^name\s*=\s*"cortex-command"`) → silent exit 0; (2) enumerate `entry_points(group='console_scripts')` filtered against `bin/.parity-exceptions.md` (excluding all three category enum values); (3) check `shutil.which(name)` against current PATH; (4) on missing → emit `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<factual message>"}}` to stdout; (5) all error paths exit 0 silently. Phase 4 is best-effort secondary channel — the primary value floor is the wrapper's exit-2 message from Task 3, which fires at `command not found` time and is not subject to claude-code#16538's plugin-hook silent drop.
- **Depends on**: [12]
- **Complexity**: complex
- **Context**: Dependency on Task 12 (parity-check promotion) is for the parity-exceptions parser — import a helper directly from `cortex_command.parity_check`, or if that module's parser isn't cleanly importable, factor a shared helper into `cortex_command/common.py` as part of Task 12. The advisory message uses factual phrasing per requirement 12 (no imperatives — Claude Code's prompt-injection defenses). Phase 4 SHOULD NOT be the primary remediation channel — Task 3's wrapper exit-2 message is. NEVER write a sentinel file under `cortex/.cache/`.
- **Verification**: `python3 -c "import cortex_command.doctor.path_self_test"` exits 0. `python3 -m cortex_command.doctor.path_self_test 2>&1` exits 0 unconditionally.
- **Status**: [x] done (commit `b04b4dc1`, 247 lines; agent inlined a simpler parity-exceptions parser into the module rather than importing from parity_check.py — decouples doctor from linter's AllowlistRow/E001 internals)

### Task 24: Extend `cortex-session-start-path-bootstrap.sh` with the PATH self-test invocation [DONE]
- **Files**: `plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh`
- **What**: After `AUGMENTED_PATH=...` (line 29) AND BEFORE the `$CLAUDE_ENV_FILE` write (lines 31–33), insert an inline `PATH="$AUGMENTED_PATH" python3 -m cortex_command.doctor.path_self_test 2>/dev/null || true` invocation. Capture stdout and pass through to the hook's own stdout so Claude Code receives any additionalContext.
- **Depends on**: [23]
- **Complexity**: simple
- **Context**: Hook structure preserved (cortex-shape gate line 25, `AUGMENTED_PATH=` line 29, `$CLAUDE_ENV_FILE` write lines 31–33). New invocation lands BETWEEN lines 29 and 31. `PATH="$AUGMENTED_PATH"` is the subprocess-only assignment so the self-test sees augmented PATH without exporting it globally. The `|| true` is belt-and-suspenders; Task 23 already guarantees exit 0 on all paths.
- **Verification**: `grep -E 'PATH="\$AUGMENTED_PATH".*path_self_test' plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh` ≥ 1 — pass if count ≥ 1. `awk '/AUGMENTED_PATH=/{a=NR} /path_self_test/{p=NR} /CLAUDE_ENV_FILE/{c=NR} END{exit (a<p && p<c)?0:1}' plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh` exits 0 (line order verified).
- **Status**: [x] done (commit `03e4d3a9`; agent caught that canonical source is `claude/hooks/` — spec only named the plugin mirror)

### Task 25: Add `tests/test_path_self_test_enumeration.py` and `tests/test_path_self_test_hook_integration.py`
- **Files**: `tests/test_path_self_test_enumeration.py` (new), `tests/test_path_self_test_hook_integration.py` (new)
- **What**: Two test files: (1) enumeration unit test: with a library-internal entry listed in `bin/.parity-exceptions.md`, it does NOT appear in the self-test's expected-binary set (mock `importlib.metadata.entry_points`); (2) hook integration test: feed fixture stdin to `cortex-session-start-path-bootstrap.sh` while overriding PATH to exclude an entry — assert stdout contains `additionalContext`, exit 0, no sentinel file (`test ! -e cortex/.cache/path-selftest.json`). Also covers: (a) `CORTEX_DEV_MODE=1` → no additionalContext; (b) `$CWD/pyproject.toml` names cortex-command → no additionalContext; (c) `PATH=/nonexistent` → hook exits 0 with empty stdout; (d) `importlib.metadata.PackageNotFoundError` simulation → exit 0 silently.
- **Depends on**: [23, 24]
- **Complexity**: complex
- **Context**: Hook integration test invokes the bash hook via subprocess; temp-dir fixture must contain `cortex/lifecycle/` subdir to pass the cortex-shape gate. The integration test is best-effort because claude-code#16538 affects the **plugin-hook pipeline** (where Claude Code consumes the hook's output), NOT the hook's own emission — so the test can verify the hook emits additionalContext correctly, but it cannot verify Claude Code receives it.
- **Verification**: `python3 -m pytest tests/test_path_self_test_enumeration.py tests/test_path_self_test_hook_integration.py` exits 0.
- **Status**: [ ] pending

### Task 26: Document `CORTEX_COMMAND_FORCE_SOURCE=1` in `cortex/requirements/project.md` [DONE]
- **Files**: `cortex/requirements/project.md`
- **What**: Add a paragraph to "Wheel-binstub vs working-tree invocation" (around lines 38–39) per requirement 15's literal text about `CORTEX_COMMAND_FORCE_SOURCE=1`.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: Documentation-grade addition; no ADR needed. Documents the escape hatch Task 3's wrapper template adds.
- **Verification**: `grep -c CORTEX_COMMAND_FORCE_SOURCE cortex/requirements/project.md` = 1 — pass if count = 1.
- **Status**: [x] done (commit `4de81868`)

### Task 27: Sweep skill prose for path-qualified `bin/cortex-<name>` references → bare-name [DONE]
- **Files**: any file under `skills/` matching `grep -rlE 'bin/cortex-(log-invocation|resolve-backlog-item|auto-bump-version|backlog-ready|check-parity|check-prescriptive-prose|commit-preflight|complexity-escalator|git-sync-rebase|lifecycle-counters|lifecycle-state|load-parent-epic|morning-review-gc-demo-worktrees)' skills/`. Known: `skills/refine/references/clarify-critic.md:16,65,198` for `bin/cortex-load-parent-epic`.
- **What**: Rewrite every literal `bin/cortex-<name>` reference for the 13 promoted scripts to bare entry-point name. Do NOT rewrite references to non-promoted scripts.
- **Depends on**: [9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22]
- **Complexity**: simple
- **Context**: Depends on all promotion tasks because the bare-name references resolve only after entries land. Anchor regex at word boundaries to avoid breaking `bin/cortex-load-parent-epic-something-else` (no such file today, but defensive).
- **Verification**: `grep -rnE 'bin/cortex-(log-invocation|resolve-backlog-item|auto-bump-version|backlog-ready|check-parity|check-prescriptive-prose|commit-preflight|complexity-escalator|git-sync-rebase|lifecycle-counters|lifecycle-state|load-parent-epic|morning-review-gc-demo-worktrees)' skills/ | wc -l` = 0 — pass if count = 0.
- **Status**: [x] done (commit `c27a45f2`, 12 files; agent dispatched as worktree subagent died mid-edit after 3 of ~10 references — completed inline on orchestrator)

### Task 28: Verify `cortex-check-parity` passes post-migration
- **Files**: `bin/.parity-exceptions.md` (conditional — only if new gaps need exception entries); any skill/doc/hook/justfile/test under repo root needing a wiring-signal touch-up (enumerated at task-execution time from W003/W005 warning output).
- **What**: Run `cortex-check-parity --audit` and confirm exit 0. Resolve any wiring-signal gaps surfaced — preferably by adding wiring, else by `bin/.parity-exceptions.md` entry with real rationale (literal-bans still apply).
- **Depends on**: [27]
- **Complexity**: simple
- **Context**: Migration's CI gate. Files conditional, finalized at task-execution time.
- **Verification**: `cortex-check-parity --audit` exits 0 — pass if exit 0.
- **Status**: [ ] pending

## Risks

- **Task 1 pre-allocates 13 entries with stub modules**: The wheel installs cleanly from any intermediate commit because each stub module's `main()` exits 70 (rather than raising NotImplementedError). However, if a user runs `cortex-auto-bump-version` (or any other promoted-but-not-yet-ported binstub) between Task 1's commit and the corresponding promotion task's commit, they get exit 70 with a stub error message rather than the bash version's logic. Mitigation: commit Tasks 9, 11–22 in close succession to minimize the window. Acceptable residual risk: a transient install during the migration window may see stubs.
- **Phase 4 channel reliability**: claude-code#16538 systematically drops `additionalContext` from plugin-defined SessionStart hooks (verified reproducing v2.1.42–v2.1.75). The PATH self-test is **secondary, best-effort** — the primary user-facing missing-entry-point remediation is Task 3's wrapper exit-2 message, which fires at `command not found` time on a channel #16538 cannot intercept. If the Anthropic bug is fixed in a future Claude Code release, the SessionStart advisory becomes a useful pre-failure signal; if it remains broken, users still get the wrapper message at failure time. The Acceptance section's "or emits a single additionalContext line" claim is now phrased as conditional ("AND Claude Code's plugin-hook pipeline does not drop it") in the Phase 4 checkpoint.
- **Task 12 critical-path realism**: Promoting 1792-line `cortex-check-parity` is the largest task in Phase 3. Realistic time budget: 60–90 min, not the typical 5–15 min target. This task is on the critical path for Task 23 (PATH self-test reuses the parity-exceptions parser). Mitigation: factor the parity-exceptions parser helper into `cortex_command/common.py` as part of Task 12 to decouple Task 23's start from Task 12's overall completion (the parser is a small subset of the 1792-line port).
- **Parity tests' tolerance scope**: The broadened `@pytest.mark.structural_equivalence(stream=..., tolerances=[...])` admits five named categories. If a real diff falls outside all five (e.g., locale-dependent month abbreviations, hostname/PID leakage), the parity test fails by design — that's the discipline. Mitigation: the determinism harness (Task 2/8/20 fixture READMEs document `LC_ALL=C`, `TZ=UTC`, timestamp filtering) should catch most non-tolerance-category drift before it reaches the parity test. Long-tail diffs may require a new tolerance category as a one-time amendment to Task 5's helper.
- **Sibling-pattern rewrite limited scope (Tasks 4a/4b)**: After critical review, Task 4 was restructured to touch ONLY non-promoted scripts (the 12 promoted scripts have their files wholly replaced by wrappers in Tasks 9/11–22, which is where their log-invocation usage is reconsidered). Risk: a non-promoted bash/python script outside the documented set may still use the old sibling-pattern post-migration. Mitigation: Tasks 4a/4b's verification grep checks the residual pattern count = 0 across the entire `bin/` directory.
- **Stub module deletion ordering**: Each promotion task replaces a Task-1 stub. If the stub is accidentally left in place after the port lands (e.g., the new file is written alongside the stub rather than replacing it), Python's module resolver may pick the wrong one. Mitigation: each promotion task's verification asserts `python3 -c "import <module>"` works and the imported callable matches the promoted (not stub) behavior — e.g., a known argument that the stub would exit 70 on must succeed.
- **PEP 723 inline-deps migration (Tasks 9, 15, 16)**: Three scripts ship as PEP 723 with inline-metadata deps. Promotion may surface a dep not already in `pyproject.toml`'s `[project] dependencies` — if so, add it. Mitigation: each task calls this out explicitly; reviewer confirms new deps don't bloat the wheel.

## Acceptance

After all 28 tasks ship, a user who runs `uv tool install --reinstall --refresh git+<repo>@<tag>` and starts a Claude Code session sees `command -v <each-promoted-script>` resolve to a `~/.local/bin/` binstub for all 13 promoted scripts. If any entry point is missing from PATH (e.g., stale install pre-Task-1's pre-allocation), the user gets a clear remediation message via one of two channels:
- **Primary** (always available): the dual-channel wrapper's exit-2 message fires at `command not found` time with the literal `uv tool install --reinstall --refresh ...` hint — bypasses any SessionStart `additionalContext` reliability issues.
- **Secondary** (best-effort): if claude-code's plugin-hook pipeline delivers the SessionStart advisory (`additionalContext`), the user sees a pre-failure listing of missing entries.

Every existing skill that invokes these scripts continues to work unchanged via the wheel-binstub chain. The "command not found" friction class flagged by ticket 252 is closed.
