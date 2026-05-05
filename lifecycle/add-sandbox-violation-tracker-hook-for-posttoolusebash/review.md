# Review: add-sandbox-violation-tracker-hook-for-posttoolusebash

Cycle 1 review of Alternative D implementation: classify sandbox-routed Bash
denials in the morning report at render time. No new hook ships (despite the
ticket title); classification is in Python at report-render time.

## Stage 1: Spec Compliance

### Requirement R1: Tracker write-side namespace fix

- **Expected**: `cortex-tool-failure-tracker.sh` reads `$LIFECYCLE_SESSION_ID`
  and writes to `lifecycle/sessions/<id>/tool-failures/` when set;
  falls back to `${TMPDIR:-/tmp}/claude-tool-failures-<sid>/` when unset.
- **Actual**: `claude/hooks/cortex-tool-failure-tracker.sh:41-50` implements
  the conditional path swap. When `LIFECYCLE_SESSION_ID` is set and not
  `"null"`, `TRACK_DIR` is set to the lifecycle path; otherwise to a
  `${TMPDIR:-/tmp}/claude-tool-failures-${SESSION_KEY}` path. Plugin mirror
  at `plugins/cortex-overnight/hooks/cortex-tool-failure-tracker.sh` is
  byte-identical to the canonical (verified via `diff`, exit 0).
- **Verdict**: PASS
- **Notes**: Lifecycle-routing acceptance verified in shell test
  `tool-failure-tracker/lifecycle-session-id-routes-to-lifecycle-path`
  (passes). Fallback-routing tests in the same file pass when run in a
  clean environment without `LIFECYCLE_SESSION_ID` exported.

### Requirement R1a: Aggregator read-side namespace fix

- **Expected**: All four `/tmp/claude-tool-failures-{session_id}` reader
  references in `report.py` prefer `lifecycle/sessions/{sid}/tool-failures/`
  with `/tmp` fallback only when the lifecycle path is absent. Duplicate
  function definitions either both patched, or dead duplicate deleted.
- **Actual**: `cortex_command/overnight/report.py:1031-1079` implements a
  single `collect_tool_failures` definition; `:1715-1739` implements a
  single `render_tool_failures` definition. Liveness analysis identified the
  pre-existing duplicates as dead code and they were deleted (per T3 plan
  context). The `collect_tool_failures` body checks `lifecycle_dir` first
  and falls back to `Path(f"{TMPDIR}/claude-tool-failures-{session_id}")`
  when the lifecycle path is absent. Functional verification via
  `python3 -c 'from ...report import collect_tool_failures; ...'` returns
  a non-empty dict against a hand-written lifecycle fixture (PASS).
- **Verdict**: PASS
- **Notes**: Spec's `grep -c 'lifecycle/sessions/' cortex_command/overnight/report.py`
  returns 6 (≥4 spec floor satisfied). The literal `/tmp/claude-tool-failures-`
  count returned 0 because the fallback was rewritten as
  `f"{tmpdir}/claude-tool-failures-{session_id}"` with `tmpdir =
  os.environ.get("TMPDIR", "/tmp")`. The spec's `grep -c '/tmp'` ≥1 floor
  reads 0, but the spec acceptance also explicitly permits "returns 0"
  when the `/tmp` literal is removed entirely; the TMPDIR-aware variant is
  functionally equivalent to (and more correct than) the original literal,
  preserving fallback semantics. PARTIAL would be appropriate only if the
  fallback semantics were dropped; they are not.

### Requirement R2: Sandbox deny-list sidecar contract

- **Expected**: Both spawn sites write per-spawn JSON sidecars under
  `lifecycle/sessions/<id>/sandbox-deny-lists/<spawn-id>.json` immediately
  after deny-list construction, schema-v2, atomic via tempfile +
  `os.replace`. Files never overwritten.
- **Actual**: `runner.py:931-961` implements `_write_sandbox_deny_list_sidecar`
  helper using tempfile + `os.replace` and is invoked at the orchestrator
  spawn site (`runner.py:1009-1014`). `dispatch.py:598-629` mirrors the
  same pattern inline (with structural guard at 608-611). Both sites
  include the structural guard `assert isinstance(deny_paths, list) and
  all(isinstance(p, str) for p in deny_paths)` per spec R2 + plan context.
- **Verdict**: PASS
- **Notes**: Implementation deviation acknowledged by orchestrator: the
  per-spawn dispatch spawn-id was changed from the spec's
  `feature-<slug>-<dispatch-N>` to
  `feature-<slug>-<skill>-attempt<N>[-cycle<N>]` because no per-feature
  dispatch counter exists in the codebase. Per-spawn uniqueness is
  preserved through the (feature, skill, attempt, cycle) tuple, and the
  aggregator treats the spawn-id as opaque per spec R3 (it only unions
  `deny_paths` arrays). Dispatch's `deny_paths` is intentionally `[]` per
  #163's allow-list narrowing design; the sidecar still writes (with
  `deny_paths: []`) for spawn-record provenance, and dispatch-level
  EPERMs bucket through `plumbing_eperm`/`unclassified_eperm` since the
  union has nothing from dispatch — both behaviors align with spec edge
  case "Sidecar present but `deny_paths` is empty."

### Requirement R3: Aggregator classifier

- **Expected**: New `PLUMBING_TOOLS` constant; new
  `collect_sandbox_denials(session_id) -> dict[str, int]` running the
  4-layer classifier (shell redirection → plumbing-tool subcommand
  mapping → plumbing fallthrough → unclassified). L1/L2 candidates
  matched against the union of sidecar `deny_paths` and classified by
  path-pattern (home_repo_*, cross_repo_*, other_deny_path); L3/L4
  fallthrough categories. Top-level exception envelope returns `{}` on
  any error.
- **Actual**: `report.py:1123` defines `PLUMBING_TOOLS = {"git", "gh",
  "npm", "pnpm", "yarn", "cargo", "hg", "jj"}` per spec. The classifier
  body (`:1150-1284`) implements the four layers via helpers
  `_strip_cd_prefix`, `_extract_redirect_targets`, `_layer2_git_targets`,
  `_path_pattern_classify`, `_glob_match_in_union`,
  `_classify_sandbox_denial`. Top-level `try/except Exception` envelope
  at `:1192/:1278` returns `{}` per the documented precedent. Sidecar
  reader-side structural guard at `:1221-1230` rejects malformed
  `deny_paths`. Per-entry shape guard at `:1257-1267` skips non-dict YAML
  docs. Home/cross repo roots resolved from `state.project_root` and
  `feature.repo_path` per the plan's heuristic.
- **Verdict**: PASS
- **Notes**: Categories enum matches spec exactly. Acceptance command
  `python3 -c 'from ...report import collect_sandbox_denials; r =
  collect_sandbox_denials("nonexistent-session-fixture-xyz"); assert r
  == {}'` exits 0.

### Requirement R3a: Tracker captures `tool_input.command`

- **Expected**: Tracker writes `command:` field per failure entry as YAML
  literal block scalar; truncates to 4KB.
- **Actual**: Hook at `:77-86` writes `command: |` block when
  `COMMAND_TEXT` is non-empty, with the `head -c 4096 | head -50 | sed
  's/^/  /'` truncation idiom from the plan (4KB byte cap + 50-line cap +
  indentation + trailing newline for parser safety).
- **Verdict**: PASS

### Requirement R4: render_sandbox_denials

- **Expected**: Markdown section with verbatim disclosure paragraph,
  total-count heading, suppressed zero-count category lines.
- **Actual**: `report.py:1775-1805` defines `render_sandbox_denials`. The
  disclosure paragraph constant `_SANDBOX_DENIAL_DISCLOSURE` at
  `:1765-1772` is byte-equivalent to the spec text (anchored on
  "Bash-routed sandbox denials" and "V1 scope" markers verified at
  render time). The category iteration at `:1800-1803` suppresses
  count-zero lines and emits one bullet per non-zero category in the
  spec-mandated order.
- **Verdict**: PASS
- **Notes**: Renderer-functional acceptance check (`python3 -c
  '...assert "Home-repo refs: 2" in out and "Plumbing EPERM" in out and
  "V1 scope" in out'`) exits 0.

### Requirement R5: ReportData and generate_report integration

- **Expected**: `ReportData.sandbox_denials: dict[str, int]` field;
  `collect_report_data` populates it after `collect_tool_failures`;
  `generate_report` appends `render_sandbox_denials(data)` conditionally
  on non-empty result.
- **Actual**: `ReportData` at `:96` adds `sandbox_denials: dict[str, int]
  = field(default_factory=dict)`. `collect_report_data` at `:200-208`
  populates it via `collect_sandbox_denials(data.session_id)` (or the
  date-key fallback when session_id is empty), directly after the
  `collect_tool_failures` call. `generate_report` at `:1845-1849`
  conditionally appends the rendered section.
- **Verdict**: PASS

### Requirement R6: Positive-control acceptance test

- **Expected**: pytest fixture session covering Layer 1, Layer 2, Layer 3
  classifications across two sidecars and a minimal `overnight-state.json`;
  asserts `home_repo_refs >= 2` and `plumbing_eperm >= 1`.
- **Actual**: `tests/test_report_sandbox_denials.py` defines four test
  cases:
  `test_layer1_redirection_entry_a_classifies_as_home_repo_refs`,
  `test_layer2_git_commit_entry_b_classifies_to_home_repo_bucket`,
  `test_layer3_unmapped_git_subcommand_entry_c_classifies_as_plumbing_eperm`,
  `test_render_emits_disclosure_and_v1_scope_markers`. All four pass
  (`pytest -v` reports `4 passed`, exceeding spec's ≥3 floor).
- **Verdict**: PASS

### Requirement R6a: Tracker shell-test extension

- **Expected**: New test case drives the hook with
  `LIFECYCLE_SESSION_ID=overnight-fixture-test` and asserts output
  appears at `lifecycle/sessions/...`. Existing tests retained.
- **Actual**: `tests/test_tool_failure_tracker.sh:235-277` adds the new
  test case `tool-failure-tracker/lifecycle-session-id-routes-to-lifecycle-path`
  with proper export of the env var across the `bash $HOOK` boundary
  (subshell + `export` pattern), pre-test cleanup, and the assertion
  that the lifecycle log/count files exist while the `/tmp` fallback
  dir does NOT exist. Cleanup at `:275-277`. Existing tests retained.
- **Verdict**: PASS
- **Notes**: When run in a normal shell environment (no
  `LIFECYCLE_SESSION_ID` or custom `TMPDIR` exported), all 9 tests pass.
  The test file hardcodes `/tmp/claude-tool-failures-*` paths which can
  conflict with custom-`TMPDIR` environments; this is a test-harness
  observation, not an implementation defect — the hook itself
  consistently honors `TMPDIR`.

### Requirement R7: End-to-end smoke verification documented

- **Expected**: Manual smoke recipe under
  `### Sandbox-Violation Telemetry` subsection.
- **Actual**: `docs/overnight-operations.md:509` contains the manual
  smoke recipe: temp git repo as home, deny-list including
  `<repo>/.git/refs/heads/main`, sandboxed `claude -p` with `git commit
  --allow-empty`, confirm `home_repo_refs` count in morning report.
- **Verdict**: PASS

### Requirement R8: Documentation subsection

- **Expected**: `### Sandbox-Violation Telemetry` subsection covering
  signal sources, four-layer categorization, what each category means,
  Bash-only and within-Bash plumbing caveats. Strings
  `unclassified_eperm`, `plumbing_eperm`, `Bash-only`,
  `sandbox-deny-lists/` must appear.
- **Actual**: `docs/overnight-operations.md:483-510` adds the subsection.
  All four required strings verified via `grep` (1 match for
  `^### Sandbox-Violation Telemetry`; multiple matches for the other
  three required strings).
- **Verdict**: PASS

### Requirement R9: Defensive env-var propagation in dispatch path

- **Expected**: `dispatch.py` `_env` block explicitly propagates
  `LIFECYCLE_SESSION_ID` from `os.environ`.
- **Actual**: `dispatch.py:549-554` adds the conditional propagation
  (walrus assignment mirroring the adjacent `ANTHROPIC_API_KEY` and
  `CLAUDE_CODE_OAUTH_TOKEN` blocks). Acceptance check `python3 -c
  '...assert "LIFECYCLE_SESSION_ID" in inspect.getsource(dispatch_task)'`
  exits 0.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Classifier
  helpers use single-leading-underscore (`_classify_sandbox_denial`,
  `_path_pattern_classify`, etc.), matching `report.py` precedent.
  Module-level constants `PLUMBING_TOOLS`, `_GIT_COMMIT_TARGETS`,
  `_SANDBOX_DENIAL_CATEGORIES`, `_SANDBOX_DENIAL_DISCLOSURE` use the
  appropriate public/private prefix. `_write_sandbox_deny_list_sidecar`
  helper in `runner.py` follows the existing private-helper convention.
- **Error handling**: Robust. Top-level exception envelope on
  `collect_sandbox_denials` returns `{}` and logs to stderr per the
  documented precedent in `collect_tool_failures`. Per-sidecar
  `OSError`/`json.JSONDecodeError` are caught individually so one
  malformed sidecar does not poison the union. Per-entry shape guards
  reject non-dict YAML docs (the `if not isinstance(doc, dict): continue`
  guard before any `.get()` call). Hook preserves the
  exit-0-unconditionally invariant. Atomic writes via tempfile +
  `os.replace` at both spawn sites.
- **Test coverage**: All plan verification commands executed and pass.
  Pytest `tests/test_report_sandbox_denials.py` reports 4/4 passed
  (≥3 spec floor). Shell `tests/test_tool_failure_tracker.sh` reports
  9/9 passed in a clean shell environment. Plan's failure-injection
  exception-envelope check (`collect_sandbox_denials("x-malformed")
  == {}`) exits 0 against the documented precedent.
- **Pattern consistency**: Sidecar-write atomic pattern mirrors the
  existing `atomic_write` precedent in `report.py:307`. Structural-guard
  pattern (`assert isinstance(deny_paths, list) and all(isinstance(p,
  str) for p in deny_paths)`) is used identically at both spawn sites
  AND on the reader side, defending the cross-ticket contract with
  #163. Disclosure-paragraph constant pattern matches the existing
  module-level prose constants. Plugin mirror sync is preserved
  (canonical and mirror byte-identical, verified via `diff`).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
