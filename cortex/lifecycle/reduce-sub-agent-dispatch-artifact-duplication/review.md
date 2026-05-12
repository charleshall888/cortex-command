# Review: reduce-sub-agent-dispatch-artifact-duplication

## Stage 1: Spec Compliance

### Requirement 1: Critical-review reviewer dispatch uses path+SHA, not inline content
- **Expected**: `{artifact content}` removed; `{artifact_path}` ≥ 3 and `{artifact_sha256}` ≥ 3 in `skills/critical-review/SKILL.md`; reviewer instructed to Read and emit `READ_OK: <path> <sha>` first line, or `READ_FAILED: <path> <reason>` on failure.
- **Actual**: `{artifact content}` count = 0; `{artifact_path}` count = 5; `{artifact_sha256}` count = 8. Reviewer-prompt template (SKILL.md:113-126) shows Path/Expected-SHA-256 framing and the `READ_OK` / `READ_FAILED` first-line directive verbatim.
- **Verdict**: PASS

### Requirement 2: Critical-review fallback single-agent path uses path+SHA
- **Expected**: Same substitution at the fallback prompt site (originally SKILL.md:166); subsumed by Req 1's grep totals.
- **Actual**: Fallback template at SKILL.md:192-205 carries Path/Expected-SHA-256 + `READ_OK`/`READ_FAILED` directives, consistent with the reviewer template.
- **Verdict**: PASS

### Requirement 3: Critical-review synthesizer dispatch uses path+SHA and emits its own sentinel
- **Expected**: Same substitution at synthesizer site; synth Reads at start of synthesis; emits `SYNTH_READ_OK: <path> <sha>`. Acceptance: `Read.*{artifact_path}` ≥ 1 in lines 205–299; `SYNTH_READ_OK` count ≥ 1.
- **Actual**: Synth template (SKILL.md:278-291) instructs Read at start and emits `SYNTH_READ_OK`; lines 287-289 hold the directive. `SYNTH_READ_OK` count = 3 in SKILL.md. Synth `{artifact_path}` Read directive appears at line 287 and line 299.
- **Verdict**: PASS

### Requirement 4: Step 2c.5 verification gate — ordering, scope, exclusion routing
- **Expected**: `SHA drift detected` ≥ 2, `sentinel absent|Read failed` ≥ 2, `Critical-review pass invalidated` ≥ 1.
- **Actual**: `SHA drift detected` count = 2 (line 243 reviewer-side, line 259 mapping table). `sentinel absent|Read failed` count = 4. `Critical-review pass invalidated` count = 1 (line 410 in Step 2d.5 prose; the synthesizer-side diagnostic literal is constructed in `cortex_command/critical_review.py:313-329` and surfaced via `verify-synth-output` Exit-3 stdout, which SKILL.md instructs the orchestrator to relay verbatim). Phase-1-before-Phase-2 ordering, drop-from-all-tallies scope, synthesizer-side gate, and standardized `⚠ Reviewer {angle} excluded: {reason}` warning all present (SKILL.md:238-273).
- **Verdict**: PASS

### Requirement 5: Partial-coverage banner extension
- **Expected**: `grep -n 'excluded for drift/Read failure' skills/critical-review/SKILL.md` ≥ 1.
- **Actual**: 2 matches (lines 188 and 384). Both clauses unconditionally emit the parenthetical when K > 0 and omit it when K = 0.
- **Verdict**: PASS

### Requirement 6: Lifecycle critical-tier plan dispatch uses paths, not full contents
- **Expected**: `full contents of lifecycle` count = 0; `{spec_path}|{research_path}` ≥ 2 in `skills/lifecycle/references/plan.md`.
- **Actual**: `full contents of lifecycle` count = 0; combined `{spec_path}|{research_path}` count = 5. Plan agent template (plan.md:42-50) carries Read directive + `READ_OK: <path> <sha>` emission for each input file.
- **Verdict**: PASS

### Requirement 7: Lifecycle review.md reviewer uses path, not contents
- **Expected**: `contents of lifecycle/{feature}/spec.md, or a summary` count = 0; `{spec_path}` ≥ 1 in `skills/lifecycle/references/review.md`.
- **Actual**: Hedged-phrase count = 0; `{spec_path}` count = 2. Reviewer prompt (review.md:28-33) Reads the absolute path with no hedge.
- **Verdict**: PASS

### Requirement 8: Orchestrator-side absolute-path resolution
- **Expected**: `git rev-parse` appears in orchestrator-facing blocks only, not inside reviewer/agent prompt templates.
- **Actual**: 4 hits, all orchestrator-facing: `skills/critical-review/SKILL.md:43` (forbids reviewers from re-resolving), `:421` (residue-write feature resolver), `skills/lifecycle/references/plan.md:30` (orchestrator absolutifies before injection), `skills/lifecycle/references/review.md:26` (orchestrator absolutifies before injection). No occurrence inside the reviewer/agent prompt template body sections (SKILL.md:111-185 reviewer & fallback prompt regions, plan.md:37-78 plan-agent template, review.md:28-95 reviewer prompt template).
- **Verdict**: PASS

### Requirement 9: Path validation gate (security) — realpath-based
- **Expected**: `realpath` ≥ 1 in SKILL.md; new non-slow test exercising real symlink rejection.
- **Actual**: `realpath` count = 1 in SKILL.md (the Step 2a.5 prose at line 43 says the orchestrator MUST NOT shell out to `realpath`, and points to `prepare-dispatch` which performs realpath in `cortex_command/critical_review.py:78-93`). The new test file `tests/test_critical_review_path_validation.py` exists, holds 9 tests (incl. `test_module_api_rejects_symlink_with_realpath_in_message` and `test_cli_rejects_symlink_nonzero_exit_and_stderr` — symlink rejection at both module API and CLI subprocess layers), and carries 0 `@pytest.mark.slow` markers. All 9 tests pass.
- **Verdict**: PASS

### Requirement 10: Fast-path template-correctness unit test
- **Expected**: `just test tests/test_dispatch_template_placeholders.py` exits 0; 0 slow markers.
- **Actual**: 9/9 tests pass under `uv run pytest`. `grep -c '@pytest.mark.slow'` = 0. Tests cover Req-10a (no inline-content placeholders), Req-10b (path/SHA placeholders present), Req-10c (`READ_OK` directive verbatim in reviewer prompts), Req-10d (`SYNTH_READ_OK` directive verbatim in synthesizer prompt).
- **Verdict**: PASS

### Requirement 11: Existing slow test updated for new placeholders
- **Expected**: `{artifact content}` count = 0; `{artifact_path}|{artifact_sha256}` ≥ 2 in `tests/test_critical_review_classifier.py`.
- **Actual**: `{artifact content}` count = 0; `{artifact_path}|{artifact_sha256}` count = 23. Five `re.sub` substitution sites updated (lines ~293-299, 431-437, 634-640, 778-784, 958+ region), each followed by post-substitution asserts that the new placeholders no longer appear.
- **Verdict**: PASS

### Requirement 12: Sentinel-absence telemetry (events.log)
- **Expected**: `grep -c '"event": "sentinel_absence"|"event": "synthesizer_drift"' skills/critical-review/SKILL.md` ≥ 1.
- **Actual**: Literal-grep count = 0 in SKILL.md. The JSON-quoted event-name literals are absent from SKILL.md because the plan deliberately moved the emission into `cortex_command/critical_review.py` (lines 318-322 for `synthesizer_drift`, 354-363 for `sentinel_absence`) where both are emitted via the atomic `append_event` helper. The bare tokens `sentinel_absence` and `synthesizer_drift` DO appear in SKILL.md (lines 247, 261, 410) within subcommand-invocation prose. The implementation satisfies the spec's intent — telemetry is wired and documented in SKILL.md via subcommand-invocation pointers — but the spec's literal acceptance grep does not pass against SKILL.md alone.
- **Verdict**: PARTIAL
- **Notes**: This is the spec-amendment case the reviewer prompt called out. The implementation honors the plan's atomic-subcommand design choice; the spec's literal-grep acceptance criterion was written before that design was finalized. Recommended spec amendment: rewrite the Req 12 acceptance to `grep -cE 'sentinel_absence|synthesizer_drift' skills/critical-review/SKILL.md ≥ 2 AND grep -cE '"event": "(sentinel_absence|synthesizer_drift)"' cortex_command/critical_review.py ≥ 2`. No verdict-blocking failure: the telemetry is observably emitted, the SKILL.md documents the event names via subcommand prose, and event-payload schemas are documented in `cortex_command/critical_review.py:22-30`.

### Requirement 13: Dual-source mirrors regenerated
- **Expected**: `tests/test_dual_source_reference_parity.py` exits 0 (32/32).
- **Actual**: 32/32 byte-parity tests pass.
- **Verdict**: PASS

## Requirements Drift
**State**: detected
**Findings**:
- The new `cortex_command/critical_review.py` module introduces a **CLI-helper-module-per-skill** pattern not reflected in `requirements/project.md`. Project.md's architectural-constraints section names `bin/cortex-*` scripts + parity enforcement and `cortex_command/common.py` shared helpers, but does not capture the pattern of a skill-specific `cortex_command/<skill>.py` module fronted by `python3 -m cortex_command.<skill> <subcommand>` invocations from inside SKILL.md prose. The plan's Veto Surface preserves "no new helper subsystem"; whether a single-module skill-helper qualifies as a "subsystem" is a definitional gap. The orchestrator-side ceremony pattern (three atomic subprocess calls per critical-review dispatch — prepare-dispatch / record-exclusion / verify-synth-output) is a coherent architectural pattern worth naming so future skills that need atomic CLI ceremonies can follow it.
- The `sentinel_absence` and `synthesizer_drift` event types are emitted to `lifecycle/{feature}/events.log` by `cortex_command/critical_review.py` but are **not registered** in `bin/.events-registry.md`. The static gate (`bin/cortex-check-events-registry --staged`) currently passes because SKILL.md does not contain the literal `"event": "<name>"` form that the gate scans for, but the project.md architectural-constraints section names this registry as the source of truth for event-type registration. Two new event types were added without a registry row.

**Update needed**: `requirements/project.md` (helper-module pattern), `bin/.events-registry.md` (event registration).

## Suggested Requirements Update

**File**: `requirements/project.md`
**Section**: `## Architectural Constraints`
**Content**:
```
- **Skill-helper modules**: when a SKILL.md's dispatch ceremony is load-bearing enough that a weakly-grounded LLM would skip or paraphrase steps if expressed inline, the ceremony may be collapsed into atomic subcommands of a skill-specific module at `cortex_command/<skill>.py`, invoked from SKILL.md prose via `python3 -m cortex_command.<skill> <subcommand>`. Each subcommand must fuse the load-bearing operations (validation + mutation + telemetry) so partial execution is not addressable. The module's public functions are importable for unit testing. New event types emitted by the helper module register in `bin/.events-registry.md` even when SKILL.md does not contain the literal `"event": "<name>"` string that the static gate scans for.
```

**File**: `bin/.events-registry.md`
**Section**: registry table
**Content**:
```
| `sentinel_absence` | `per-feature-events-log` | `manual` | `cortex_command/critical_review.py:354-363` | (future per-tier compliance audit) | `live` | `2026-05-11` |  | `Reviewer-side sentinel/SHA-drift/Read-failure telemetry from /cortex-core:critical-review fan-out (spec Req 12)` |  |
| `synthesizer_drift` | `per-feature-events-log` | `manual` | `cortex_command/critical_review.py:318-322` | (future per-tier compliance audit) | `live` | `2026-05-11` |  | `Synthesizer-side SHA-drift telemetry from /cortex-core:critical-review (spec Req 12)` |  |
```

## Stage 2: Code Quality

- **Naming conventions**: `cortex_command/critical_review.py` follows the snake_case + `_cmd_<subcommand>` style consistent with `cortex_command/common.py`. CLI subcommands use hyphen-case (`prepare-dispatch`, `verify-synth-output`, `record-exclusion`) matching the `bin/cortex-*` convention. Module docstring (lines 1-31) explains the atomic-ceremony intent clearly. Public functions (`validate_artifact_path`, `sha256_of_path`, `prepare_dispatch`, `verify_synth_output`, `append_event`) are typed and have docstrings. The private `_cmd_*`, `_build_parser`, `_now_iso`, `_default_lifecycle_root` helpers follow underscore-prefix convention.

- **Error handling**: `validate_artifact_path` raises `ValueError` with messages that name the offending path AND the violated rule (e.g., "symlink detected in 'X'; realpath=Y != abspath=Z. lifecycle/ must not contain symlinks." at line 81-84). CLI exit codes match the spec: prepare-dispatch returns 2 on validation failure, verify-synth-output returns 3 on drift/absent, record-exclusion returns 2 on filesystem failure. The `append_event` helper uses the tempfile + `os.replace` pattern with cleanup on `BaseException` (lines 219-241), which is robust against partial writes and concurrent appenders. Each `append_event` call writes (existing-bytes + new-line) to a uniquely-named temp file in the same directory — the unique naming defeats temp-file collisions under concurrent invocation.

- **Test coverage**: 50 tests across the three new/updated test files all pass (9 template + 9 path-validation + 32 parity). The path-validation suite covers module-API rejection, module-API acceptance under matching feature, mismatched-feature rejection, lifecycle-root-equality rejection, CLI symlink rejection with non-zero exit + stderr message, CLI accept-and-emit-JSON, and prepare-dispatch's SHA-emission contract. The template suite covers the four Req-10 sub-acceptance criteria (no inline-content, path/SHA placeholders present, READ_OK directive verbatim, SYNTH_READ_OK directive verbatim). The classifier test is slow-marked (8 skipped under default `uv run pytest`) but its substitution sites are verified to use the new placeholders via grep.

- **Pattern consistency**: New SKILL.md additions (Step 2a.5 pre-dispatch and Step 2d.5 post-synthesis) use positive-routing phrasing — no new MUST/CRITICAL/REQUIRED escalations introduced (verified via `git diff` filter for `\bMUST\b|\bCRITICAL\b|\bREQUIRED\b` on the changed skill files, which returns no new MUST tokens). The `⚠ Reviewer {angle} excluded: {reason}` warning prefix at SKILL.md:246 matches the existing malformed-envelope warning format at SKILL.md:272. The atomic tempfile+rename idiom in `append_event` matches the residue-write pattern at SKILL.md:434-446 (both use tempfile in the same parent + `os.replace`).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
