# Review: rescope-cortex-init-ensure-to-never (cycle 2)

> Cycle 1 returned CHANGES_REQUESTED with two PARTIAL requirements (R3, R7).
> This cycle verifies the two fixes (commits `aec05f7a`, `5343d768`) and
> confirms no regression in R1, R2, R4, R5, R6, R8, R9.

## Stage 1: Spec Compliance

### Requirement 1: In-session `--ensure` performs no `~/.claude/` write
- **Expected**: `_run_ensure` contains zero `settings_merge.{validate_settings,register,unregister_matching_in_place}` calls; no replacement `~/.claude/` write; spy test asserts all three fire zero times across cases (i)–(v); temp-HOME byte-identity test asserts the settings file is unchanged/absent.
- **Actual**: `_run_ensure` (`cortex_command/init/handler.py:129-249`) has no `~/.claude/`-touching `settings_merge` calls; the post-dispatch block is repo-scope only (`ensure_gitignore`, `ensure_claude_md_authorization`). `test_r1_ensure_makes_no_claude_settings_calls` spies all three across cases (i)–(v) and asserts zero; `test_r1_ensure_temp_home_byte_identical` asserts byte-identity plus lockfile-absence. End-to-end confirmed in a temp HOME: clean-repo `--ensure` created no `~/.claude/settings.local.json` and no `.settings.local.json.lock`.
- **Verdict**: PASS
- **Notes**: Unaffected by the cycle-2 rework (handler production code untouched by both commits). Re-verified, still passing.

### Requirement 2: Marker-present refresh succeeds under the sandbox after the change
- **Expected**: Cases (ii) hash-mismatch and (v) R8 recovery scaffold `cortex/` (repo-scope) + refresh the marker with no `~/.claude/` access; case (i) hash-match is an early `return 0`.
- **Actual**: Case (ii) (`handler.py:181-187`) and case (v) (`:189-209`) call `scaffold.scaffold(...)` + `write_marker(refresh=True)` + drift report — all repo-scope; case (i) (`:176-179`) returns 0. `test_r4_case_ii_*`, `test_r8_bundle1/5_*` pass.
- **Verdict**: PASS
- **Notes**: Unaffected by the cycle-2 rework. Re-verified.

### Requirement 3: Marker-absent clean repo refuses with exit 2 + a directive
- **Expected**: Case (iii) refuses via the user-correctable path (`ScaffoldError` → exit 2) with a single-line directive naming terminal `cortex init` and carrying a unique substring ABSENT from the R19 `check_content_decline` message — and the acceptance mandates that absence be asserted against both messages in one test (so reusing R19 text verbatim fails the gate). No `cortex/`/`CLAUDE.md`/`.gitignore`/`~/.claude/` writes. **This is the reworked requirement (commit `aec05f7a`).**
- **Actual**: `handler.py:228-233` raises `ScaffoldError` with "...this repo is not yet initialized for cortex (no `cortex/`). Run `cortex init` in your terminal, then re-run /lifecycle." → exit 2. The cycle-1 gap (no regression test guarding distinctness) is now closed: `test_r3_clean_repo_directive_distinct_from_refusal_messages` (`test_handler_ensure.py:329-402`) genuinely (a) captures the clean-repo directive via `init_main(_make_ensure_args(repo_clean))` and asserts the substring is PRESENT, then (b) independently captures the R19 message via `scaffold.check_content_decline(repo_r19)` (asserting its distinctive "pre-existing content" phrase as a sanity check that it is the real R19 text) and asserts `"not yet initialized" not in r19_message`. It additionally guards the two R8 marker-corruption messages (unparseable-JSON and missing-`cortex_version`) by capturing each via real `--ensure` invocations and asserting the substring is absent. The test is non-tautological: it derives the R19 message from `check_content_decline` itself rather than hard-coding it, and the absence assertion would fail if the clean-repo directive were reworded to reuse R19 phrasing. Source-grep confirms the fact independently: `grep -c "not yet initialized" cortex_command/init/scaffold.py` returns 0 (the substring lives only in the handler directive). End-to-end confirmed: exit 2, directive on stderr, empty `git status --porcelain`, no `cortex/`, no `~/.claude/` file. Test passes in isolation and within the module.
- **Verdict**: PASS
- **Notes**: The cycle-1 PARTIAL (binary distinctness gate not wired) is resolved. The mandated single-test, both-messages assertion now exists and is correct.

### Requirement 4: Marker-absent + `cortex/`-has-content (R19) is unchanged
- **Expected**: Case (iv) still fires `scaffold.check_content_decline(repo_root)` → exit 2 with the R19 message, distinct from the R3 directive.
- **Actual**: `handler.py:234-238` calls `scaffold.check_content_decline(repo_root)` unchanged on the `else` branch. `test_r4_case_iv_foreign_cortex_content_exit2` asserts exit 2 with the R19 message; the R19 text ("pre-existing content") and R3 directive ("not yet initialized") are textually distinct (now also enforced by the R3 regression test).
- **Verdict**: PASS
- **Notes**: Unaffected by the cycle-2 rework. Re-verified.

### Requirement 5: Terminal `cortex init` is unchanged
- **Expected**: The standard `_run` path still writes the `~/.claude/` grant at Step 7 (`register`) and runs the Step 7b migration only on `--update`. Terminal `cortex init` in a clean repo writes the `cortex/` grant under `allowWrite` and exits 0; `just test` passes.
- **Actual**: `_run` (`handler.py:346-540`) untouched on the in-scope paths: `register` at `:529`, migration gated `if args.update:` at `:537-538`. End-to-end confirmed: terminal `cortex init` (no `--ensure`) on a clean repo with a temp HOME wrote `settings.local.json` with one `cortex/` `allowWrite` entry and exited 0. Init test suite (85 tests) passes.
- **Verdict**: PASS
- **Notes**: Unaffected by the cycle-2 rework. Re-verified.

### Requirement 6: `CORTEX_AUTO_ENSURE=0` and worktree-attached guards unchanged
- **Expected**: The `(a)` opt-out early `return 0` and `(b)` worktree-attached refusal behave as today. `CORTEX_AUTO_ENSURE=0 cortex init --ensure` exits 0 writing nothing; worktree-attached refusal still exits 2.
- **Actual**: `handler.py:148-150` retains the `CORTEX_AUTO_ENSURE=0` early `return 0`; `:156` retains `_check_not_attached_worktree()` (body `:252-300` unchanged). `test_r7_cortex_auto_ensure_0_no_op` passes (exit 0, no writes, foreign file untouched).
- **Verdict**: PASS
- **Notes**: Unaffected by the cycle-2 rework. Re-verified.

### Requirement 7: Amend `auto-apply-cortex-init-at-lifecycle/spec.md` at every clean-repo-bootstrap site
- **Expected**: Revise all three sites — (a) R4 dispatch-table case-(iii) row, (b) R4 acceptance #1, (c) Problem-Statement clause — to the exit-2 refuse contract; per-site #273 rationale + top-of-file superseding pointer; preserve R5's "bootstrap a clean one" verbatim. Acceptance greps: "exits 0 and writes" + "bootstrap automatically" → 0; `grep -c "273"` ≥ 1; **the dispatch-table case-(iii) row no longer contains the word "bootstrap"**. **This is the reworked requirement (commit `5343d768`).**
- **Actual**: The cycle-1 literal deviation is fixed. The case-(iii) dispatch-table row (line 28) now reads "→ refuse with exit 2, directing the user to run terminal `cortex init` (clean-repo first-init removed per #273). (Rationale: #273 — ...)" — `sed -n '28p' | grep -c "bootstrap"` returns 0, satisfying R7 acceptance #3 literally. R5's "bootstrap a clean one" (line 32) is preserved verbatim. Acceptance greps: `grep -c "exits 0 and writes"` = 0; `grep -c "bootstrap automatically"` = 0; `grep -c "273"` = 4. The remaining "bootstrap" occurrences are all legitimate: the top-of-file superseding pointer (line 3), the Problem-Statement #273-rationale clause (line 7, "it cannot bootstrap a clean repo"), R4 acceptance #1's "clean-repo bootstrap replaced by exit-2 refuse" (line 30), R5's preserved "bootstrap a clean one" (line 32), and R11's unrelated worktree-guard diagnostic (line 44) — none is the case-(iii) row.
- **Verdict**: PASS
- **Notes**: The cycle-1 PARTIAL (case-(iii) row still contained "bootstrap" inside a negation) is resolved by rewording to drop the token entirely, exactly as the cycle-1 issue suggested. The other two sites (Problem-Statement, R4 acceptance #1) remain correctly revised to the exit-2 contract with #273 rationale.

### Requirement 8: Tests are updated to the new contract
- **Expected**: `test_r4_case_iii_a/b` assert exit-2/refuse; the no-`~/.claude/`-write spy is present; sibling `test_init_ensure.py` needs no behavioral change. Both modules pass.
- **Actual**: Both case-iii tests assert exit 2 + "not yet initialized" + clean `git status`; R1 spy and byte-identity tests present; clean-repo-dependent tests re-pointed to plant markers via `_make_update_args`. `pytest cortex_command/init/tests/test_handler_ensure.py cortex_command/lifecycle/tests/test_init_ensure.py` → 27 passed (was 26 in cycle 1; +1 is the new R3 distinctness test). Full init suite → 85 passed.
- **Verdict**: PASS
- **Notes**: The cycle-2 R3 test (`aec05f7a`) is an additive +76-line test-only change; no other test behavior changed.

### Requirement 9: First-contact docs corrected so terminal `cortex init` precedes `/lifecycle`
- **Expected**: README `cortex init` step no longer OPTIONAL (overnight-plugin OPTIONAL preserved); `docs/index.html` cortex-core start-here block surfaces literal `cortex init`.
- **Actual**: README `:27` reads "# 3. In each project, before running /lifecycle. Required per-project setup." (no OPTIONAL on the `cortex init` step); the overnight-plugin "OPTIONAL - autonomous overnight runs" (`:25`) is preserved. `docs/index.html` cortex-core "required · start here" `<article>` (lines 6653-6662) contains the literal `cortex init` at line 6661 ("in each repo, before `/lifecycle`: `cortex init`").
- **Verdict**: PASS
- **Notes**: Unaffected by the cycle-2 rework. Re-verified.

## Requirements Drift
**State**: none
**Findings**:
- None. The change tightens an existing in-session behavior (`--ensure` no longer writes `~/.claude/`) without introducing behavior outside what `project.md` covers: the `CORTEX_AUTO_ENSURE=0` opt-out is named in Architectural Constraints; ADR-0003's per-repo sandbox registration is preserved (terminal `cortex init` still performs it, explicitly out of scope per the spec's Non-Requirements); the encoded consent boundary aligns with the "Defense-in-depth for permissions" quality attribute. No requirements file asserts in-session clean-repo bootstrap, so removing it contradicts nothing. The cycle-2 rework (a test addition and a one-line spec wording change) introduces no new behavior and therefore no new drift surface.
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The new R3 test `test_r3_clean_repo_directive_distinct_from_refusal_messages` follows the module's `test_r<N>_*` convention and reuses the established `_make_ensure_args`, `_git_init`, `_isolate_home`, and `_write_marker` helpers. The reworded spec row keeps the dispatch-table bullet shape.
- **Error handling**: Unchanged and correct. The clean-repo refuse still raises `ScaffoldError` before any scaffold call (no partial writes), translated to exit 2 in `main()`. The new test exercises the real error paths (`ScaffoldError` via `check_content_decline` and via `--ensure` against corrupt markers) rather than mocking message text.
- **Test coverage**: Now complete on the previously-flagged gap. The R3 distinctness test is non-tautological — it derives the R19 message from `check_content_decline` at runtime, sanity-checks it via its distinctive "pre-existing content" phrase, then asserts the clean-repo substring is absent from it (and from both R8 corruption messages, which the test also captures via real invocations). A future reword of the clean-repo directive to reuse any sibling message's phrasing would now fail this regression test. Init suite 85/85; combined init+lifecycle modules 27/27.
- **Pattern consistency**: Follows project conventions. The dependent-spec amendment retains the superseding-pointer + per-site #273-rationale pattern; the case-(iii) reword stays within the dispatch-table contract format. Both rework commits are tightly scoped (test-only `+76` lines; single-line spec edit) with no out-of-scope edits. Changed-file set matches the spec's declared scope (handler, its tests, the dependent spec, README, docs/index.html).

## Verdict
```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
