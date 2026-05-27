# Review: gate-worktree-option-on-console-script

**Cycle**: 1
**Reviewer**: Claude Code (Sonnet 4.6)
**Date**: 2026-05-27

---

## Stage 1: Spec Compliance

### R1 — New `cortex-worktree-create` console-script with IO and idempotency contract

**PASS**

- `pyproject.toml` contains exactly 1 match for `^cortex-worktree-create = ` pointing at `cortex_command.pipeline.worktree_create_cli:main`.
- The wrapper accepts `--feature` (required) and `--base-branch` (default `main`).
- **stdout contract**: `print(info.path)` is the sole stdout write; `create_worktree` uses `capture_output=True` throughout its subprocess calls, so git chatter never reaches the wrapper's stdout. The IO contract is satisfied by capture, not explicit redirection — functionally equivalent.
- **stderr contract**: informational output (`worktree already exists`), exception traces (`repr(exc)`), and the `--feature must be non-empty` diagnostic all go to `sys.stderr`.
- **Idempotency**: `resolve_worktree_root(...).exists()` probed before `create_worktree`; `create_worktree` itself returns the existing `WorktreeInfo` when the path is already a registered worktree (confirmed in `worktree.py:204–236`). The wrapper prints the path to stdout, writes `worktree already exists` to stderr, exits 0. Re-entry is success.
- **Exception handling**: `except Exception as exc` → `print(repr(exc), file=sys.stderr)` → `return 1`. All exception types produce a unified exit 1 with the stderr trace as the differentiator. Acceptance criteria verified by orchestrator's live test outcomes.

One observation: `already_existed` is set by `candidate.exists()` (directory existence), not by checking that `create_worktree` returned a pre-existing valid registered worktree. A directory that exists but isn't a valid git worktree would emit "worktree already exists" even though `create_worktree` would actually proceed to create/repair it. This is an edge case not exercised by the spec's acceptance criteria and doesn't affect any known test path.

### R2 — Gate probe swaps from bare-Python import to console-script reachability

**PASS**

- `grep -c 'importlib.util.find_spec' skills/lifecycle/references/implement.md` = 0 ✓
- `grep -c 'command -v cortex-worktree-create' skills/lifecycle/references/implement.md` = 1 ✓
- All three dispositions are verbatim in implement.md §1:
  - exit 0 → all three options remain
  - exit 1 → silent hide of "Implement on feature branch with worktree"
  - Bash tool failure or other exit → fail open with `runtime probe skipped: console-script probe failed`
- Plugin mirror at `plugins/cortex-core/skills/lifecycle/references/implement.md` is byte-identical (diff = empty).

### R3 — §1a step iii invokes `cortex-worktree-create` rather than fenced Python

**PASS**

- `grep -c 'from cortex_command.pipeline.worktree import create_worktree' skills/lifecycle/references/implement.md` = 0 ✓
- `grep -c 'cortex-worktree-create --feature' skills/lifecycle/references/implement.md` = 1 ✓
- The invocation uses `worktree_path=$(cortex-worktree-create --feature interactive-{slug} --base-branch main)` — stdout captured via `$(...)`.
- Failure prose: "the wrapper writes `repr(exc)` to stderr and exits 1. Surface the stderr output to the user and exit §1a" — `repr(exc)` explicitly named as the surfaced error ✓

### R4 — Structural-marker contract test verifies gate↔gated-path binary pairing

**PASS**

- `grep -c "test_gate_and_gated_path_use_same_binary" tests/test_implement_worktree_interactive_contract.py` = 1 ✓
- The test correctly:
  - Extracts §1 body via `### 1. Pre-Flight Check.*?(?=### 1a\.)` regex
  - Extracts §1a body via `### 1a\..*?(?=### 1b\.|\Z)` regex
  - Narrows §1a to step iii between `**iii.` and `**iv.` markers
  - Applies `command -v (\S+)` on §1 → captures gate binary
  - Applies `^(?:\w+=\$\()?(\S+?)\s+--feature\s+interactive-` on §1a step iii → captures gated binary
  - Asserts `gate_binary == gated_binary`
- Both capture `cortex-worktree-create` against the live implement.md.
- Orchestrator verified: `pytest tests/test_implement_worktree_interactive_contract.py -v` → 4/4 pass ✓

### R5 — New lint module `cortex_command/lint/bare_python_import.py`

**PASS**

- Module exists at `cortex_command/lint/bare_python_import.py` (645 lines).
- `cortex-check-bare-python-import = "cortex_command.lint.bare_python_import:main"` in pyproject.toml (1 match) ✓
- **Python-source-region definition**: All four rules implemented:
  - Rule 1: `_PYTHON_INFO_RE` matches `^(python|python3|py)$` case-insensitively → Phase B labeled-fence branch
  - Rule 2: `_PYTHON_C_RE` scans full text (Phase A) — fires anywhere including inside unlabeled fences (Rule 4)
  - Rule 3: `_HEREDOC_RE` detects `python3 - <<MARKER` and `python3 <<MARKER` — fired in Phase B, both in prose and inside unlabeled fences
  - Rule 4: Unlabeled fences are not themselves python-source regions, but Rule 2/3 invocations inside them are scanned by Phase A and Phase B respectively ✓
- **Import regex**: Superset of spec's required pattern — adds `importlib.util.find_spec`, `importlib.import_module`, `__import__` dynamic forms. This is aligned with the spec's Non-Requirements note about the removed §1 probe and the regression-prevention rationale.
- **Sentinel suppression**: `prev_nonblank` pattern implemented via `prev_nonblank_at` dict in Phase A and `prev_nonblank` variable in Phase B. Intervening blank lines do not defeat suppression ✓
- **Inline-code span stripping**: `_INLINE_CODE_RE` applied per-line before regex scanning ✓
- Negative cases (prose, stdlib-only, inline-code-span) correctly pass clean.
- Live skills corpus (`implement.md`) passes clean post-Task-1 ✓

### R6 — Pre-commit wiring

**PASS**

- Phase 1.86 stanza present in `.githooks/pre-commit` ✓
- Trigger pattern: `skills/*|cortex/backlog/*.md|bin/cortex-check-bare-python-import` matches spec ✓
- Invokes `just check-bare-python-import` ✓
- Diagnostic text: `pre-commit: bare-python cortex_command import check failed — convert to a cortex-* console-script call, or add the <!-- bare-python-lint:ignore-next --> sentinel if the bare-Python form is intentional.` — verbatim match to spec ✓
- `grep -c 'check-bare-python-import' .githooks/pre-commit` = 2 (trigger variable assignment + invocation) ✓
- `justfile` has `check-bare-python-import` recipe (wraps `--staged`) and `check-bare-python-import-audit` recipe (wraps `--audit`) ✓
- `grep -c '^check-bare-python-import' justfile` = 2 ✓
- Orchestrator verified: staging fixture containing `python3 -c "import cortex_command"` → pre-commit exits 1 with R6 diagnostic ✓

### R7 — Lint test coverage

**PASS**

- `tests/test_bare_python_import_lint.py` exists (23 tests) ✓
- `pytest tests/test_bare_python_import_lint.py -v` → 23/23 pass ✓
- Positive cases by rule:
  - Rule 1: `test_rule1_labeled_fence_python`, `test_rule1_labeled_fence_py_variant`, `test_rule1_labeled_fence_python3_variant`
  - Rule 2: `test_rule2_python3_c_single_line_in_prose`, `test_rule2_python3_c_multiline`
  - Rule 3: `test_rule3_heredoc`
  - Rule 4: `test_rule4_python3_c_inside_unlabeled_fence`
  - Dynamic: `test_dynamic_import_find_spec`, `test_dynamic_import_import_module`, `test_dynamic_import_dunder_import`
  - Totals: ≥4 positive cases (one per Rule 1-4), requirement met by 10 ✓
- Negative cases: `stdlib_only`, `narrative_prose`, `inline_code_span`, `sentinel_immediate`, `sentinel_with_blank_line`, `two_sentinels`, `non_cortex_import`, `stdlib_in_labeled_fence`
  - Totals: ≥4 negative cases (stdlib-only, prose-only, sentinel-immediate, sentinel-with-blank-line), requirement met by 8 ✓
- Fixtures: `tests/fixtures/bare_python_import/positive.md` (8 sections) and `tests/fixtures/bare_python_import/negative.md` (6 sections) ✓
- Regression test `test_find_spec_regression_caught` pins the specific probe text removed in Task 1 ✓
- Regression test `test_staged_glob_matches_deep_skills_path` pins the `full_match` fix from the orchestrator follow-up ✓

### R8 — Events-registry / contract-lint registration

**PASS**

- `bin/.events-registry.md` not modified (new console-scripts emit no events) ✓
- Both `cortex_command/pipeline/worktree_create_cli.py` and `cortex_command/lint/bare_python_import.py` use standard `argparse.ArgumentParser` + `.add_argument` — no `.contract-lint-exceptions.md` entry required ✓
- Orchestrator verified: `cortex-check-contract --audit` exits 0 ✓

---

## Stage 2: Code Quality

All requirements PASS; proceeding to Stage 2.

### Naming conventions

Consistent with project patterns. `worktree_create_cli.py` follows the `<module>_cli.py` convention for thin argparse wrappers (mirrors `worktree_resolve_cli.py`, `branch_mode_cli.py`, `picker_decision_cli.py`). `bare_python_import.py` follows the `cortex_command/lint/<linter>.py` pattern alongside `contract.py` and `prescriptive_prose.py`.

### Error handling

Appropriate for the context:
- `worktree_create_cli.py`: broad `except Exception` with `repr(exc)` to stderr is correct per spec; the wrapper deliberately does not differentiate exception classes via exit code.
- `bare_python_import.py`: `(OSError, UnicodeDecodeError)` on file reads; `(subprocess.CalledProcessError, FileNotFoundError)` on git calls — narrow, appropriate catches for the I/O surfaces involved.

### Test coverage

23 tests exercising both the scan engine (positive/negative fixture paths) and the glob-matching regression. `test_live_skills_corpus_clean` provides integration-level confidence that implement.md is clean. The `test_staged_glob_matches_deep_skills_path` test pins the `Path.full_match` fix that the orchestrator added after discovering `Path.match` silently skipped deep skills paths in pre-commit mode — a high-value regression guard.

### Pattern consistency

- Dual-channel shim in `bin/cortex-check-bare-python-import` follows the same branch-ordering pattern as `bin/cortex-check-contract` and `bin/cortex-check-prescriptive-prose` (FORCE_SOURCE → wheel probe → working-tree fallback → error).
- `bin/cortex-check-bare-python-import` and `plugins/cortex-core/bin/cortex-check-bare-python-import` are byte-identical ✓
- Two-mode gate pattern (`--staged` + `--audit`) matches `cortex-check-events-registry` and `cortex-check-contract` ✓
- Telemetry call `_telemetry.log_invocation("cortex-check-bare-python-import")` present at the top of `main()` ✓

---

## Requirements Drift

**State**: detected

**Findings**:
- `cortex/requirements/project.md` documents the positive convention ("Skill-helper modules" → use console-scripts; `python3 -m` as fallback) but does not capture the structural prohibition on bare-Python `cortex_command` imports in skill files or the enforcement mechanism (`cortex-check-bare-python-import`, L201, Phase 1.86 pre-commit gate). A future skill author reading the requirements would learn the preferred idiom but not that the anti-pattern is structurally blocked.

**Update needed**: `cortex/requirements/project.md`

---

## Suggested Requirements Update

**File**: `cortex/requirements/project.md`

**Section**: `## Architectural Constraints`

**Content**:
```
- **Bare-Python skill-invocation prohibition (L201)**: Skill files (`skills/**/*.md`) and related corpus files must not contain bare-Python `cortex_command` imports (static `import`/`from import` or dynamic `importlib.util.find_spec`/`importlib.import_module`/`__import__` forms). Violations are structurally caught at pre-commit by `cortex-check-bare-python-import` (Phase 1.86, L201). Use `cortex-<skill>` console-script invocations instead. Where a bare-Python form is intentional (e.g., illustrative `## Touch points` prose), precede the python-source region with `<!-- bare-python-lint:ignore-next -->`.
```

---

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
