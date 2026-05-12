# Review: extract-commit-preflight-into-bin-commit-preflight

> Loaded scope: only `requirements/project.md` matched the tag scan `[harness, scripts, commit]` — no Conditional Loading phrases ("statusline/dashboard/notifications", "pipeline/overnight/conflict/deferral", "remote-access/tmux/mosh/Tailscale", "agent-spawning/parallel-dispatch/worktrees/model-selection") match those tags, so no area docs were loaded.

## Stage 1: Spec Compliance

### R1 — `bin/cortex-commit-preflight` exists, executable, python3 shebang
- **Expected**: file is executable and first line is `#!/usr/bin/env python3`.
- **Actual**: `test -x bin/cortex-commit-preflight && head -1 ... | grep '^#!/usr/bin/env python3$'` exits 0; line 1 of the script is `#!/usr/bin/env python3`.
- **Verdict**: PASS
- **Notes**: none.

### R2 — DR-7 telemetry shim present in first 50 lines using `realpath`, executes at runtime
- **Expected**: `head -50` finds a line containing both `cortex-log-invocation` and `os.path.realpath(__file__)`; runtime invocation appends a JSONL record.
- **Actual**: line 29 of the script is the shim using `os.path.dirname(os.path.realpath(__file__))`. The runtime test `test_shim_records_invocation` constructs a tmp-repo session and asserts delta == 1 with `script == "cortex-commit-preflight"` — that test PASSES (see R14). The end-to-end JSONL probe (`SID=test-spec-105-...`) returned `delta=1`.
- **Verdict**: PASS
- **Notes**: shim is on line 29, well within the 50-line window.

### R3 — `bin/cortex-invocation-report --check-shims` exits 0
- **Expected**: exit code 0.
- **Actual**: ran `bin/cortex-invocation-report --check-shims` → `Checked 12 scripts; 0 missing shim line.` exit 0.
- **Verdict**: PASS
- **Notes**: none.

### R4 — Single-line JSON envelope with `{status, diff, recent_log, notes}` schema
- **Expected**: stdout parses as JSON, key set is exactly `{status, diff, recent_log, notes}`, types match.
- **Actual**: `bin/cortex-commit-preflight | python3 -c '... assert set(o.keys())=={...} ...'` exits 0. JSON is single-line, encoded via `json.dumps(payload, ensure_ascii=False) + "\n"` (line 144).
- **Verdict**: PASS
- **Notes**: none.

### R5 — Full diff emitted (no cap, no truncation flag)
- **Expected**: in a tmp repo with a >10KB working-tree diff, `diff` field length > 10000.
- **Actual**: constructed a tmp repo with ~30KB of changed content; script emitted `diff` of length 56161 — far above 10000. No `--max-diff-bytes`, no `diff_truncated`, no `diff_bytes_total` in the script.
- **Verdict**: PASS
- **Notes**: none.

### R6 — Hardened git env (smoke + AST)
- **Expected**: `grep -E "GIT_OPTIONAL_LOCKS|LC_ALL=C.UTF-8|color.ui=never|--no-pager"` returns ≥4 lines; AST walk in `test_git_env_hardening` confirms every `subprocess.run` whose first arg starts with `"git"` has the six-element prefix and an `env=` dict containing `GIT_OPTIONAL_LOCKS` and `LC_ALL`.
- **Actual**: smoke grep returns 9 matches. `test_git_env_hardening` PASSES. `GIT_ENV` constant on lines 41–45 contains both required keys; the six-element prefix is hard-coded in three call sites (lines 61, 76, 86) plus passed via `*_GIT_PREFIX` is replaced by direct literals (the `_run_git` helper on line 53 uses an inlined literal at line 61, and the two probe calls also inline). All callsites pass `env=GIT_ENV`.
- **Verdict**: PASS
- **Notes**: the `_GIT_PREFIX` constant on line 50 is defined but unused in subprocess argv lists (each callsite re-inlines the six elements). This is harmless — the AST test still verifies the prefix at every callsite — but constitutes minor dead code.

### R7 — Bytes captured, decoded with `errors="replace"`; no `text=True`
- **Expected**: `errors="replace"` present; `subprocess.run(...text=True)` absent; binary diff doesn't crash.
- **Actual**: `errors="replace"` appears 3 times; zero `text=True` matches in subprocess.run calls. `_decode` helper on line 70 wraps the decode pattern. `test_binary_diff_no_crash` PASSES — uses NUL-free invalid UTF-8 (`\xc3\x28`) and asserts `�` appears AND `"Binary files"` does NOT (defending against vacuous pass).
- **Verdict**: PASS
- **Notes**: none.

### R8 — `ensure_ascii=False`
- **Expected**: at least one match.
- **Actual**: 1 match on line 144 (`json.dumps(payload, ensure_ascii=False)`).
- **Verdict**: PASS
- **Notes**: none.

### R9 — Exit-code taxonomy 0 / 2 / 3 / 5
- **Expected**: outside repo → 2; bare repo → 3; empty repo → 0 with `empty_repo` in notes.
- **Actual**: ran probes against tmp dirs — outside-repo exits 2 with stderr "not inside a git repository"; `git init --bare` repo exits 3 with stderr "bare repository -- no working tree"; fresh `git init` repo exits 0 with `notes: ["empty_repo"]`. Code paths: lines 81–95 (not-in-repo / bare detection during initial probe), 98–101 (post-probe bare guard), 111–113/127–129/132–135 (exit 5 on partial git failure).
- **Verdict**: PASS
- **Notes**: none.

### R10 — Empty repo emits `notes=["empty_repo"]`, empty `diff`/`recent_log`, exits 0
- **Expected**: empty-repo invocation produces JSON with `notes` containing `"empty_repo"`, `diff == ""`, `recent_log == ""`.
- **Actual**: tmp-repo probe printed `{..., "diff": "", "recent_log": "", "notes": ["empty_repo"]}`, exit 0. Code: lines 116–124 build the empty-repo branch.
- **Verdict**: PASS
- **Notes**: none.

### R11 — `skills/commit/SKILL.md` Step 1 collapsed to one inline-code-wired sentence
- **Expected**: parity check passes; `cortex-commit-preflight` mentioned ≥1 time; Workflow section contains zero occurrences of `git status`, `git log --oneline`, `git diff HEAD`; Step 1 is one sentence ≤250 bytes.
- **Actual**: parity check exit 0; `grep -c 'cortex-commit-preflight' skills/commit/SKILL.md` returns 1; multi-line Python check exits 0 (no leftover commands). New Step 1 text: ``Run `bin/cortex-commit-preflight` to get status, working-tree diff, and last 10 commits as a single JSON document.`` — 113 bytes, single sentence.
- **Verdict**: PASS
- **Notes**: none.

### R12 — `os.path.abspath(__file__)` → `os.path.realpath(__file__)` in 6 Python scripts
- **Expected**: each of the six files contains exactly one `os.path.realpath(__file__)` and zero `os.path.abspath(__file__)`.
- **Actual**: ran the loop — every file shows realpath=1, abspath=0. Confirmed for `cortex-archive-rewrite-paths`, `cortex-archive-sample-select`, `cortex-audit-doc`, `cortex-check-parity`, `cortex-count-tokens`, `cortex-validate-spec`.
- **Verdict**: PASS
- **Notes**: none.

### R13 — Plugin distribution byte-identity
- **Expected**: `cmp bin/cortex-commit-preflight plugins/cortex-interactive/bin/cortex-commit-preflight` exits 0; no untracked drift.
- **Actual**: cmp succeeds; `git diff --quiet -- plugins/cortex-interactive/bin/cortex-commit-preflight` succeeds.
- **Verdict**: PASS
- **Notes**: none.

### R14 — Six named pytest functions in `tests/test_commit_preflight.py` all PASS
- **Expected**: pytest exits 0; each of the six required test names reports PASSED.
- **Actual**: `pytest -v` outputs `6 passed in 1.03s`; the named-test PASSED grep returns 6. All required names present as top-level functions: `test_normal_repo_emits_valid_json`, `test_bare_repo_exits_3`, `test_empty_repo_emits_empty_repo_note`, `test_binary_diff_no_crash`, `test_shim_records_invocation`, `test_git_env_hardening`.
- **Verdict**: PASS
- **Notes**: each test is designed to fail when the property under test is absent (negative assertions on `Binary files`, `delta == 1`, AST vacuous-pass guard, etc.).

### R15 — `bin/cortex-check-parity` exits 0 on the post-change repository
- **Expected**: exit 0.
- **Actual**: ran `bin/cortex-check-parity` → exit 0.
- **Verdict**: PASS
- **Notes**: none.

### R16 — JSONL invocation telemetry delta ≥1 in `lifecycle/sessions/<UUID>/`
- **Expected**: with a fresh UUID session id, invocation produces a delta ≥1 in `bin-invocations.jsonl`.
- **Actual**: ran the spec acceptance script verbatim; `BEFORE=0 AFTER=1 delta=1`.
- **Verdict**: PASS
- **Notes**: none.

## Requirements Drift

**State**: none

**Findings**:
- None. Implementation matches `requirements/project.md` constraints (file-based state, SKILL.md-to-bin parity, no new global behavior, no PyPI publishing). The new script is a `bin/cortex-*` member wired through `skills/commit/SKILL.md`, which is the documented parity contract on line 27 of project.md.

**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `bin/cortex-commit-preflight` follows the kebab-case `bin/cortex-*` convention. Test file `tests/test_commit_preflight.py` follows the existing `tests/test_*.py` pattern (e.g., `tests/test_archive_rewrite_paths.py`). Module-level helper names (`_run_git`, `_decode`) use the existing private-underscore convention.

- **Error handling for the 0/2/3/5 taxonomy**: Code paths are clean — line 81–95 handle the dual-mode "not in worktree OR bare" path (rev-parse failure path), line 98–101 add the redundant bare guard for the worktree-inside-bare edge, lines 111–135 hard-fail with exit 5 on any unexpected git failure (e.g., `status`/`diff`/`log` returning non-zero) without emitting partial JSON, per the spec's "do not emit partial envelope" constraint. Stderr messages match the spec text exactly. No exit code 1 or 4 leak — the taxonomy is closed at 0/2/3/5.

- **Test coverage vs plan verification commands**: every plan Task 6 verification step is reflected in the test code: `test_normal_repo_emits_valid_json` covers Task 1's JSON-schema verification, `test_bare_repo_exits_3` covers the exit-code probe, `test_empty_repo_emits_empty_repo_note` covers the empty-repo branch, `test_binary_diff_no_crash` covers the `errors="replace"` decode (with the NUL-free invalid-UTF-8 + replacement-char positive assertion + `Binary files` negative assertion that the plan called out as the vacuous-pass defense), `test_shim_records_invocation` pins the JSONL path to the tmp repo (avoiding cortex-command-repo pollution, per the plan's note), `test_git_env_hardening` performs the AST walk with the four guards specified (env keyword present, six-element prefix, env-dict source check, vacuous-pass defense). Plan-defined "design to fail when property absent" requirement is honored throughout.

- **Pattern consistency with peer `bin/` scripts**: shebang, docstring, single-line shim on line 29, `__main__` guard on lines 149–150 — all match the family pattern (compare `bin/cortex-archive-rewrite-paths`). Subprocess invocation style matches the hardened pattern (capture_output=True, env=GIT_ENV, check=False) consistently across all four callsites. Minor observation: `_GIT_PREFIX` constant on line 50 is defined but unused (each callsite inlines the six elements verbatim) — likely retained as documentation; harmless dead code. No argparse / no CLI flags (per spec non-requirement). Stderr taxonomy text matches spec wording exactly.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
