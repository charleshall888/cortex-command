# Review: overnight-launchd-scheduled-runner-operates-from

## Stage 1: Spec Compliance

### Requirement R1: Single-funnel precedence with a marker-based validity guard
- **Expected**: `_resolve_repo_path` gains `state_project_root: Path | None = None` and resolves by precedence valid-state → valid-env → `git rev-parse` → `cwd`. A candidate (state OR env) is valid only if, after `.resolve()`, it is non-null, exists, is a directory, is not `/`, and bears a `.git`/`cortex/` marker. The guard validates a SINGLE candidate in place — no upward walk. Resolution stays in this one function (R20).
- **Actual**: `cli_handler.py:171` `_resolve_repo_path(state_project_root=None)` applies the precedence exactly: `_is_valid_repo_root(state_project_root)` first, then `CORTEX_REPO_ROOT` through the same `_is_valid_repo_root` predicate, then `git rev-parse`, then `Path.cwd()`. `_is_valid_repo_root` (`cli_handler.py:141`) resolves the candidate, rejects non-dir / `/` / marker-less, and tests `(.git).exists() or (cortex/).is_dir()` — it inspects only the supplied path and returns `False` on a miss (no `for parent in ...` walk). Both state and env go through the identical predicate.
- **Verdict**: PASS
- **Notes**: The non-walking property is explicit and load-bearing (docstring lines 150-155). Unit test `test_resolve_repo_path.py` exercises every precedence branch and both guard rejections; all 11 cases pass.

### Requirement R2: `handle_start` threads `state.project_root` into resolution; regression test targets the `--launchd` inline path
- **Expected**: `handle_start` loads the `--state` file and passes `project_root` into `_resolve_repo_path(state_project_root=…)` before threading `repo_path` into `runner.run`, covering both the async-spawn parent and the `--launchd` inline child. A regression test builds a session with a marker-bearing `project_root`, sets cwd=`/`, clears `CORTEX_REPO_ROOT`, calls `handle_start` with the `--launchd` namespace, spies `runner.run`'s `repo_path`, asserts it equals `state.project_root`, and does NOT monkeypatch `_resolve_repo_path`.
- **Actual**: `handle_start` defines `_repo_path_from_state()` (`cli_handler.py:712`) that loads the state via `state_module.load_state` and calls `_resolve_repo_path(state_project_root=Path(st.project_root))`. The closure is invoked at ALL THREE `runner.run`-bound dispatch sites: dry-run inline (line 770), `--launchd` inline (line 812), and `_spawn_runner_async` (line 822). `test_launchd_repo_root.py` Case A drives the real `--launchd` inline path, spies only `runner.run`, asserts `repo_path == tmp_path.resolve()` and `!= /`; Case B covers the `--scheduled` parent against `_spawn_runner_async`. Neither references the resolver symbol — confirmed by `grep`.
- **Verdict**: PASS
- **Notes**: The closure design (lazy, per-branch) correctly preserves the JSON concurrent-runner short-circuit, which returns before any `load_state`. The corrected root reaches every dispatch site including the `--scheduled` parent.

### Requirement R3: Guardian scan resolves correctly under launchd
- **Expected**: `_dispatch_overnight_guardian_scan` calls `_resolve_repo_path()` with no state and relies on the plist-set `CORTEX_REPO_ROOT`; after the fix it returns the env value over cwd=`/`. A unit test asserts the no-state env branch.
- **Actual**: `cli.py:171` `_dispatch_overnight_guardian_scan` calls `_resolve_repo_path()` (no state arg). `build_guardian_plist_dict` (`macos.py:1189`) sets `CORTEX_REPO_ROOT` unconditionally in `EnvironmentVariables`. With the R1 env precedence, a marker-bearing env wins over cwd=`/`. `test_resolve_repo_path.py::test_env_returned_when_state_none_and_cwd_is_root` asserts exactly this shape.
- **Verdict**: PASS

### Requirement R4: Per-feature `repo: null` resolves to the session root
- **Expected**: `handle_start` threads a non-null resolved `repo_path` into `runner.run`, which exports `os.environ["CORTEX_REPO_ROOT"]` (runner.py:2503) so `feature_executor`'s `Path.cwd()` fallback never hits `/`. The R2 test additionally asserts the threaded root reaching the per-feature path is the session root.
- **Actual**: `runner.py:2503` `os.environ["CORTEX_REPO_ROOT"] = str(repo_path)` is present. `test_launchd_repo_root.py` Case A asserts `runner.run` receives `repo_path == session root`; since the export derives directly from that kwarg, the per-feature path inherits the session root, not `/`. The R4 mechanism is satisfied transitively by the kwarg assertion.
- **Verdict**: PASS
- **Notes**: The spec's R4 acceptance is a corollary of R2's assertion plus the existing runner export; no separate test is required and none was added, consistent with the spec wording ("the R2 regression test additionally asserts").

### Requirement R5: Existing `_resolve_repo_path` monkeypatch sites updated WITHOUT becoming the only coverage
- **Expected**: The ~30+ tests that monkeypatch `_resolve_repo_path` accept the new optional parameter (`lambda *a, **k: …`) so they do not raise on the new signature; protection against recurrence is R1+R2 (un-patched real-resolver tests), which must NOT monkeypatch the resolver (`grep -L` confirms).
- **Actual**: All monkeypatch sites widened to `lambda *a, **k: …` — verified across `cortex_command/overnight/tests/` and `tests/`; no zero-arg `lambda:` patching of `_resolve_repo_path` remains (`grep` returns none). `grep -L` confirms `test_resolve_repo_path.py` and `test_launchd_repo_root.py` never patch `_resolve_repo_path`. The full overnight + affected `tests/` suite runs 622 passed, 1 skipped, 0 signature errors.
- **Verdict**: PASS

### Requirement R6: `status` no longer crashes on naive/aware compare and does not misreport fire times
- **Expected**: `_parse_iso` normalizes every timestamp via `datetime.fromisoformat(ts).astimezone(timezone.utc)` — naive interpreted as system-local (DST-correct), aware converted to UTC — at the single chokepoint, not per-field and not the `_is_spent` `replace()` idiom. A regression test exercises `render_status` with a naive-local `scheduled_start` near a fire boundary under a non-UTC TZ, asserting no exception, no `Error reading status:`, and a correct local-wall-clock dormant decision.
- **Actual**: `status.py:107` `return datetime.fromisoformat(ts).astimezone(timezone.utc)` — exactly the mandated mechanism in the single chokepoint. All compare sites (`_is_scheduled_dormant`, `render_status` elapsed/last-event/per-feature) flow through it. `test_status_tz.py` reproduces the reported dormant crash under `America/New_York`, plus naive `started_at`, aware `started_at`, and mixed cases; the future-local-wall-clock fixture would flip the dormant decision under a UTC-skew regression, so it guards the offset correctness, not just the no-crash property. All 4 cases pass.
- **Verdict**: PASS
- **Notes**: The dormant-path crash (`fires_at <= now` in `_is_scheduled_dormant`) — the actual #311 reported crash — is covered by `test_dormant_naive_local_scheduled_start_does_not_crash`.

### Requirement R7: Writer emits aware `scheduled_start` going forward, without breaking GC reaping
- **Expected**: The scheduler writes `scheduled_start`/`scheduled_for_iso` tz-aware via `resolved_target.astimezone().isoformat()` (one writer; `state.scheduled_start` and the sidecar share the source string). `_is_spent` must still reap a now-aware `scheduled_for` against the GC's naive `now`. Tests: new write parses tz-aware; legacy-naive reader still passes; spent aware `scheduled_for` still reaped against naive `now`.
- **Actual**: `macos.py:406` `scheduled_for_iso = target.astimezone().isoformat()` (real schedule path); `cli_handler.py:1827` the same for the dry-run preview. `_is_spent` (`macos.py:1034`) normalizes `now` to the stored offset via `now.astimezone(scheduled_for.tzinfo)` when stored is aware + `now` naive — no naive/aware crash. `test_scheduled_start_aware.py` covers all three: writer-emits-aware (through real `backend.schedule`), `_is_spent` reaps past-aware vs naive-now + preserves future-aware, end-to-end `_gc_pass` reaps an aware spent entry, and the legacy-naive reader backstop. All pass.
- **Verdict**: PASS
- **Notes**: R7 is ranked Should; it is nonetheless fully implemented with the GC-reaping guard the spec pins as the risk.

### Requirement R8: `status` stays read-only
- **Expected**: The tz fix normalizes in-memory only; no `os.replace`/`write_text`/`open(..., "w")`/state-mutation in `status.py`'s R6 change (ADR-0011).
- **Actual**: `status.py` contains no write/replace/mutation calls (`grep` for `os.replace`/`write_text`/`open(...,'w')`/`.write(` returns none). `_parse_iso` returns a value; nothing is persisted. The change is confined to read/normalize logic.
- **Verdict**: PASS

### Requirement R9: The fix is verified in the installed-wheel/launchd path
- **Expected**: After reinstalling the wheel, either (a) a real near-term launchd fire confirming `active-session.json:repo_path` is the real root and no `morning_report_commit_failed details.project_root: "/"`, OR (b) a documented invocation of the console-script entrypoint with cwd=`/` + bare env + state file asserting the resolved root. The completion summary must state the wheel was reinstalled and which verification ran.
- **Actual**: `preflight.md` documents option (b) variant: a faithful installed-wheel-equivalent invocation under the real launchd condition (cwd=`/`, `CORTEX_REPO_ROOT` stripped) via the repo's editable `.venv` interpreter (which exposes the identical `cli_handler.py` the wheel ships). The observed-result table shows the fixed resolver recovers the real root and the unfixed contrapositive (`state_project_root=None`) reproduces `/`, proving causality. The doc records the deploy-time `uv tool install --force` as a remaining post-merge operator action and is explicit it is an audit record, not a structural gate.
- **Verdict**: PASS
- **Notes**: The wheel was NOT yet force-reinstalled globally — deliberately deferred to post-merge (rationale: a global reinstall mid-lifecycle disrupts concurrent sessions and is premature before the Review gate). The substitution is faithful because the editable `.venv` exposes byte-identical resolver code under the exact launchd filesystem/env condition. R9's acceptance explicitly permits a "documented test that invokes the entrypoint with cwd=/ + bare env + state file and asserts the resolved root" (option b); the preflight satisfies this and additionally pins the deploy step. Acceptable for the Review verdict; the post-merge reinstall remains the operator's deploy-time confirmation.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the module. `_is_valid_repo_root` / `_resolve_repo_path` / `_repo_path_from_state` follow the file's private-helper convention; the closure name reads as intent. Test helpers (`_make_marker_repo`, `_make_bare_dir`, `_fail_git_rev_parse`, `_simulate_launchd`, `_local_naive_offset`) are descriptive and self-documenting.
- **Error handling**: Appropriate. `_is_valid_repo_root` catches `(OSError, RuntimeError)` from `.resolve()` and returns `False` (fall-through, not raise). `_resolve_repo_path` keeps the `git rev-parse` try/except on `(CalledProcessError, FileNotFoundError, OSError)` falling to `cwd`. `_parse_iso` callers (`_is_scheduled_dormant`, `_read_last_event_ts`, per-feature elapsed) all guard the parse with `except ValueError`, so a malformed timestamp degrades gracefully rather than crashing the status render. `_is_spent` is conservative on unparseable input (returns `False`, never spuriously reaps).
- **Test coverage**: Strong and anti-masking-disciplined. The two un-patched tests exercise the real resolver and spy only downstream sinks (`runner.run`, `_spawn_runner_async`) — the precise discipline whose absence shipped the bug. The tz tests pin offset correctness (not just no-crash) by using future-local-wall-clock fixtures under a non-UTC TZ that would flip the dormant decision on a UTC-skew regression. R7 covers writer, unit `_is_spent`, and end-to-end `_gc_pass`. Targeted suite: 22 passed. Full overnight + affected `tests/`: 622 passed, 1 skipped, 0 failures. The plan's verification steps were executed. (The one unrelated `just test` failure — `test_resolve_backlog_item::test_no_order_drift_against_baseline` from a concurrent session's uncommitted fixture drift — is not attributable to this feature and is excluded per the review instructions.)
- **Pattern consistency**: Strong. R20 single-resolver is preserved literally — one function owns precedence; callers supply inputs and never re-derive (the closure routes through `_resolve_repo_path`, the spawn child re-runs `handle_start` rather than re-deriving in the argv). The marker-guard idiom aligns with the house siblings (`log_invocation._resolve_repo_root` `.git`, `common._resolve_user_project_root` `cortex/`) while deliberately NOT merging them (the non-walking design is the documented divergence, recorded in ADR-0013). ADR-0013 follows the three-criteria gate shape with explicit rejected alternatives. No new event literals introduced (none needed).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation matches the stated requirements. The single-resolver (R20), ADR three-criteria gate, out-of-process supervision (ADR-0011 read-only status), and house-idiom marker check are all reflected in `cortex/requirements/project.md` and the referenced ADRs. The fix introduces no behavior beyond the bug remediation already framed by those constraints; the marker-validated precedence and tz normalization are bugfix mechanics within the existing overnight/observability scope, not new product surface.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
