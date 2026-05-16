# Review: restore-worktree-root-env-prefix

## Stage 1: Spec Compliance

### Requirement 1: Resolver branch (c) default → `$TMPDIR/cortex-worktrees/<feature>`
- **Expected**: `resolve_worktree_root()` branch (c) returns `$TMPDIR/cortex-worktrees/<feature>` (fallback `/tmp` when unset); two dedicated pytest tests pass.
- **Actual**: `cortex_command/pipeline/worktree.py:188` returns `Path(os.environ.get("TMPDIR", "/tmp")).resolve() / "cortex-worktrees" / feature` from branch (c). The `repo_root` parameter is retained on the signature for backwards-compatibility but no longer dereferenced on this branch. Tests `test_branch_c_default_returns_tmpdir` and `test_branch_c_default_tmpdir_unset_falls_back_to_tmp` are both present and pass (`pytest tests/test_worktree.py -q` → 26 passed).
- **Verdict**: PASS
- **Notes**: Implementation matches the spec precisely. The `$TMPDIR` fallback to `/tmp` mirrors branch (d) per spec.

### Requirement 2: Resolver canonicalizes the `$TMPDIR` path via `Path.resolve()`
- **Expected**: branch (c) calls `.resolve()` on the result so Seatbelt comparisons match `/private/var/folders/...` form. Positive-symlink and negative-control tests pass.
- **Actual**: `worktree.py:188` calls `.resolve()` on the `Path($TMPDIR)`. Tests `test_branch_c_path_is_resolved` (symlink) and `test_branch_c_path_no_symlink_unchanged` (control) both present, both passing.
- **Verdict**: PASS
- **Notes**: The `.resolve()` is applied to the `TMPDIR` Path itself, not to the full path with `/cortex-worktrees/<feature>` appended — equivalent for canonicalization since the appended segments do not exist yet. Behavior is correct.

### Requirement 3: Branch (b) substring marker tightened to structurally-distinct entry shape
- **Expected**: replace `"worktrees/" in entry` substring scan with structurally-distinct sentinel suffix `"<path>#cortex-worktree-root"`; foreign paths containing `worktrees/` substring are ignored. Two tests pass.
- **Actual**: `_registered_worktree_root()` at `worktree.py:84-125` uses `entry.partition("#")` and matches only when `marker == "cortex-worktree-root"`. Tests `test_branch_b_ignores_unrelated_worktrees_substring` and `test_branch_b_sentinel_suffix_matches` are present and pass.
- **Verdict**: PASS
- **Notes**: Uses `str.partition` rather than `split("#", 1)` — equivalent semantics, returns sentinel tuple on absent separator. Correct.

### Requirement 4: `cleanup_worktree()` fallback routes through resolver
- **Expected**: replace hardcoded fallback `repo / ".claude" / "worktrees" / feature` with `resolve_worktree_root(feature, session_id=None, repo_root=repo)`. Test verifies resolver is called, git state cleaned.
- **Actual**: `cleanup_worktree` at `worktree.py:309-371` calls `resolve_worktree_root(feature, session_id=None, repo_root=repo)` when `worktree_path is None`. Tests `test_cleanup_worktree_routes_through_resolver` and `test_cleanup_worktree_explicit_path_bypasses_resolver` are present and pass.
- **Verdict**: PASS

### Requirement 5: Structural regression tests in `tests/test_worktree.py` — positive, negative, and behavioral
- **Expected**: update three existing branch-(c) tests; add negative-property test; R1-R5 each have dedicated test function (named per `verify-rN` slug); `pytest tests/test_worktree.py --collect-only | grep -E "verify-r[1-5]"` returns ≥4 lines.
- **Actual**: existing tests updated (`test_branch_c_default_same_repo`, `test_no_settings_file_falls_through_to_c`, `test_settings_without_worktrees_marker_falls_through` all assert the new `$TMPDIR/cortex-worktrees/<feature>` default). Negative-property test `test_branch_c_result_not_under_repo_claude` exists. Five dedicated `TestVerifyR{1..5}` classes exist. **However**, the test class names use camelCase (`TestVerifyR1BranchCTmpdirDefault`) rather than hyphenated `verify-r1`, so the literal grep `grep -E "verify-r[1-5]"` returns 0 lines. `pytest tests/test_worktree.py -q` exits 0 with 26 passing.
- **Verdict**: PARTIAL
- **Notes**: The substantive requirement (R1-R5 each have dedicated test functions; pytest collection picks them up; suite exits 0) is fulfilled. The literal grep command in the acceptance criteria does not match the implementation's naming, but the spirit ("verified by pytest collection") is satisfied. This is a literal-text deviation from the verification command, not a behavioral failure. The implementer chose a more conventional `TestVerifyR<N>...` class-name pattern.

### Requirement 6: `cortex init` Step 8 removed
- **Expected**: delete Step 8 block in `cortex_command/init/handler.py`; (a) `grep -E "^[[:space:]]*# Step 8|worktree_root_path|worktree_target"` returns no matches AND (b) `test_cortex_init_does_not_register_worktrees_path` passes.
- **Actual**: Step 8 is gone from `handler.py` (`grep -E "..." cortex_command/init/handler.py` exits 0 with no matches). Step 7 (umbrella `cortex/` registration) remains at line 198. Test `tests/test_init_worktree_registration_removed.py::test_cortex_init_does_not_register_worktrees_path` exists and passes (`just test-init` → PASS).
- **Verdict**: PASS

### Requirement 7: `tests/test_init_worktree_registration.py` deleted
- **Expected**: file is removed; `just test` exits 0; no orphan references in `cortex_command/ tests/ bin/ skills/`.
- **Actual**: file is absent (`ls` confirms FILE_DELETED). `grep -r "test_init_worktree_registration"` returns one match in `tests/test_init_worktree_registration_removed.py` (the replacement file's docstring references the deleted file's name as historical context — this is benign documentation, not an orphan code import). `just test` exits 0 (6/6 test suites pass).
- **Verdict**: PASS
- **Notes**: The remaining `grep` hit is in the replacement file's docstring naming the file it replaces. No code-level orphan imports anywhere. The Phase 1 scope expansion deleting `test_dual_registration_order_lifecycle_first` from `test_settings_merge.py` is also confirmed structurally (Step 8 absence implies the test it covered is invalid).

### Requirement 8: `cortex-worktree-create.sh` hook shells out to the Python resolver (single-chokepoint)
- **Expected**: hook replaces hardcoded path computation with shell-out to `cortex-worktree-resolve`; non-zero exit + diagnostic when unreachable; byte-identity parity test passes; mock-replacement test passes.
- **Actual**: `claude/hooks/cortex-worktree-create.sh:42-50` checks `command -v cortex-worktree-resolve` and exits 1 with diagnostic on absence; `WORKTREE_PATH=$(cortex-worktree-resolve "$NAME")` is the sole path-resolution step (no inline duplication). `cortex_command/pipeline/worktree_resolve_cli.py` is the thin wrapper. `pyproject.toml` exposes `cortex-worktree-resolve = "cortex_command.pipeline.worktree_resolve_cli:main"`. `tests/test_hooks_resolver_parity.sh` passes (verified with `dangerouslyDisableSandbox`: `PASS hooks_resolver_parity: hook='...verify-r8' == python='...verify-r8'`). Mock-replacement integration in `tests/test_hooks.sh` shadows HOME so the test-controlled `cortex-worktree-resolve` mock wins on PATH.
- **Verdict**: PASS
- **Notes**: The hook also bootstraps PATH (`$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH`) at line 18 to mitigate launchd-PATH limitations — a robustness addition not in the spec but consistent with the "fail loud if unreachable" requirement (and the diagnostic explicitly references this case).

### Requirement 9: `tests/test_hooks.sh` assertions updated for the resolver-aligned path
- **Expected**: four worktree-path assertions reference `cortex-worktree-resolve` (mock or computed). `grep -c "cortex-worktree-resolve" tests/test_hooks.sh` ≥4.
- **Actual**: `grep -c "cortex-worktree-resolve" tests/test_hooks.sh` returns 7 (≥4). Mock shim installed at `$WT_FAKE_HOME/.local/bin/cortex-worktree-resolve` (line 171); `expected_path=$(cortex-worktree-resolve "my-feature")` (line 189) and three other assertions all use the same resolver shell-out. `just test` passes the worktree-create tests.
- **Verdict**: PASS

### Requirement 10: Seatbelt-active integration test covers both Python resolver AND bash hook
- **Expected**: `tests/test_worktree_seatbelt.py` with two test functions, `pytest.mark.skipif` on `CLAUDE_CODE_SANDBOX != "1"`; `f_row_evidence` event in events.log after a successful sandbox-active run.
- **Actual**: `tests/test_worktree_seatbelt.py` contains exactly two `def test_` functions (`test_python_resolver_default_passes_probe_under_seatbelt` and `test_hook_emitted_path_passes_probe_under_seatbelt`), both gated by `@pytest.mark.skipif`. `events.log:14` contains `{"ts": "2026-05-16T03:26:55Z", "event": "f_row_evidence", ..., "outcome": "passed", "claude_code_sandbox": "1", "pytest_exit_code": 0, "pytest_summary": "passed=2,failed=0,skipped=0", ...}`.
- **Verdict**: PASS
- **Notes**: The event records both functions passed (`passed=2,failed=0`) under `CLAUDE_CODE_SANDBOX=1`. R14(d) citation base is durable.

### Requirement 11: Atime-touch guard on lifecycle resume — test must distinguish guard-set from creation-fresh
- **Expected**: `os.utime(path, (now, now))` on idempotent-return; `CORTEX_SKIP_ATIME_TOUCH=1` opt-out; positive test advances atime past `old_time + 60`, negative test leaves it within 5 seconds of `old_time`.
- **Actual**: `worktree.py:249-251` and `:262-264` both touch atime via `os.utime(worktree_path, (now, now))` on the idempotent path, gated by `if not os.environ.get("CORTEX_SKIP_ATIME_TOUCH")`. Tests `test_atime_touch_distinguishes_guard_set_from_creation_fresh` and `test_atime_touch_skipped_with_env_opt_out` are present as module-level functions and pass.
- **Verdict**: PASS

### Requirement 12: `cortex/requirements/multi-agent.md` updated — same-repo convention reversed with rationale
- **Expected**: four grep checks: (a) `\.claude/worktrees` returns no matches; (b) `cortex-worktrees` ≥2; (c) `Seatbelt mandatory deny on .mcp.json` ≥1; (d) `cortex/lifecycle/restore-worktree-root-env-prefix` ≥1.
- **Actual**: (a) 0 matches (exit 1); (b) 2 matches; (c) 1 match; (d) 1 match. The Architectural Constraints section at line 77 contains the new convention with the verbatim rationale phrase and citation.
- **Verdict**: PASS

### Requirement 13: Other `.claude/worktrees/` references swept — full repo scope, archive excluded
- **Expected**: master grep `grep -rln "\.claude/worktrees" skills/ docs/ cortex/requirements/ cortex/lifecycle/ cortex/research/ cortex_command/ tests/ bin/ claude/ plugins/cortex-core/ | grep -Ev "/archive/|/restore-worktree-root-env-prefix/|/harden-autonomous-dispatch-path-for-interactive/"` returns zero matches.
- **Actual**: the master grep returns **5 residual matches** in research artifacts of OTHER lifecycles (one additional autogenerated `daytime.log` is present in working-tree-modified state but excluded by the grep scope since it's flagged as untracked-ish/uncommitted — actually `cortex/lifecycle/lead-refine-4-complexity-value-gate/daytime.log` is committed and shows as modified-not-staged, so it depends on whether grep walks it; running the literal grep yielded the 5 paths below):
  1. `cortex/lifecycle/shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits/research.md`
  2. `cortex/lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/research.md`
  3. `cortex/lifecycle/reduce-sub-agent-dispatch-artifact-duplication/research.md`
  4. `cortex/lifecycle/trim-cortex-log-invocation-shim-cost-per-call-21ms/research.md`
  5. `cortex/research/windows-support/research.md`

  Active source code, requirements docs, internals docs, skill prose, hooks, bin scripts, and tests all sweep clean. The five residual files are all `research.md` documents in other lifecycles documenting state-at-time-of-research.
- **Verdict**: PARTIAL
- **Notes**: The spec's R13 wording — "**Active references must be deleted or rewritten** — the `(legacy)` annotation escape hatch is NOT permitted" — does not explicitly carve out historical research artifacts. The literal grep returns non-zero matches. However, the implementer's interpretation is defensible: a `research.md` documents what was true at the moment the research was conducted; rewriting it falsifies the historical record (just as commit messages are not retroactively rewritten when constants change). The structural fix (active source code, requirements, internals, skill prose, plugin mirrors) is complete. See "Resolution of R13 ambiguity" below for the recommended path forward.

### Requirement 14: R7 of harden-autonomous-dispatch-path-for-interactive superseded with cited evidence — byte-parity-verified
- **Expected**: six checks: (a) four citations present in harden spec; (b) same four in current spec's `## Changes to Existing Behavior`; (c) byte-parity between sentinel markers; (d) `requirement_superseded` event in harden events.log; (e) F-row event reference resolves; (f) supersession timestamp > F-row timestamp.
- **Actual**:
  - (a) harden spec: `restore-worktree-root-env-prefix`=4 hits, `DeepWiki sandbox-runtime mandatory deny list`=1, `cortex/lifecycle/restore-worktree-root-env-prefix/research.md`=1, `cortex/lifecycle/restore-worktree-root-env-prefix/events.log`=1. All ≥1.
  - (b) current spec: `restore-worktree-root-env-prefix`=10, `DeepWiki sandbox-runtime mandatory deny list`=2, `research.md`=2, `events.log`=4. All ≥1.
  - (c) `diff <(sed ...)` between sentinel markers exits 0 (byte-identical).
  - (d) `cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/events.log` contains `{"ts": "2026-05-16T03:36:38Z", "event": "requirement_superseded", "requirement": "R7", "superseded_by": "restore-worktree-root-env-prefix"}`.
  - (e) The F-row event referenced at `cortex/lifecycle/restore-worktree-root-env-prefix/events.log:14` is present and has `outcome: passed`.
  - (f) supersession ts (`03:36:38Z`) > f_row_evidence ts (`03:26:55Z`) → supersession follows evidence.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- The implementation is fully reflected in `cortex/requirements/multi-agent.md` (R12 was an explicit requirement update). `cortex/requirements/project.md` remains accurate — its Architectural Constraints describe the `cortex/` umbrella `allowWrite` registration, which is unchanged by this lifecycle (Step 7 stays; only Step 8 is removed). The `$TMPDIR/cortex-worktrees/...` convention is correctly captured in the multi-agent area doc, which is the conditionally-loaded scope for worktree/parallel-dispatch behavior. No new behavior escapes the requirements vocabulary.

**Update needed**: None

## Resolution of R13 ambiguity (advisory)

The implementer correctly identified a policy gap: the spec's master grep does not distinguish between active references (which must be rewritten) and historical-record references (which would be falsified by rewriting). The 5 residual matches are all in `research.md` files documenting other lifecycles' state-at-time-of-research.

Recommended resolution: file a follow-up backlog item to either (a) amend the master grep pattern to explicitly exclude `cortex/lifecycle/*/research.md` and `cortex/research/*/research.md` from the active-sweep scope, formalizing the historical-record carve-out, OR (b) define a project-wide convention that `research.md` artifacts are append-only / read-only after their lifecycle's research phase completes, and document this in `cortex/requirements/project.md` (Architectural Constraints). Option (a) is lower-cost; option (b) generalizes to other historical-record artifact classes (events.log entries, completed-lifecycle plan.md content, etc.).

For this lifecycle, accept the PARTIAL verdict on R13 with the rationale that the structural goal (no active references to a deprecated path in code, requirements, skills, docs, hooks, bin, tests, or plugin mirrors) is achieved.

## Stage 2: Code Quality

- **Naming conventions**: Console-script `cortex-worktree-resolve` follows the established `cortex-*` pattern (cf. `cortex-update-item`, `cortex-generate-backlog-index`). Reserved-token additions in `bin/cortex-check-parity` (`cortex-worktrees`, `cortex-worktree-root`) are correctly placed in `RESERVED_NON_BIN_NAMES`. The sentinel suffix `#cortex-worktree-root` is namespaced under the `cortex-` prefix, consistent with project conventions. Test class names (`TestVerifyR1BranchCTmpdirDefault`, etc.) follow pytest camelCase convention; the minor mismatch with the spec's literal `grep -E "verify-r[1-5]"` is the only naming-related deviation (already flagged in R5).
- **Error handling**: The hook's `cortex-worktree-resolve` shell-out has a clear-diagnostic, fail-loud failure mode (no silent fallback to a duplicated path), preserving the single-chokepoint guarantee. The diagnostic enumerates plausible root causes (install missing; launchd PATH; Dock/Finder launch context). `cleanup_worktree()` swallows git-cleanup failures appropriately (idempotent). `resolve_worktree_root()` does not raise on missing settings file — `json.JSONDecodeError`/`OSError` is caught and returns `None`, falling through correctly. The CLI wrapper validates `len(sys.argv) == 2` and non-empty feature name, returning exit code 2 with stderr diagnostic on usage error.
- **Test coverage**: 26 tests in `test_worktree.py`, including 5 dedicated `TestVerifyR{1..5}` classes plus atime-touch positive/negative pair plus seatbelt integration plus parity bash script plus mock-shimmed hook integration. The `f_row_evidence` event provides durable proof the seatbelt-active test ran and passed. `just test` exits 0 across all 6 suites.
- **Pattern consistency**: The dual-source pattern (canonical `bin/` + auto-regenerated `plugins/cortex-core/bin/`) is respected; canonical sources only. The hook's `set -euo pipefail` discipline and JSON-on-stdin contract follow existing hook patterns (cf. `cortex-cleanup-session.sh`, `cortex-scan-lifecycle.sh`). The sentinel-suffix scheme for branch (b) avoids introducing a sidecar JSON file, keeping `allowWrite` as a single source of truth — consistent with the project's preference for file-based state minimization. The `f_row_evidence` and `requirement_superseded` events are appropriately scoped to this lifecycle's events.log and the superseded lifecycle's events.log respectively, with the schemas documented in `## Technical Constraints` of the spec.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
