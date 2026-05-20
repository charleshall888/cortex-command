# Review: gate-policy-taxonomy-and-critical-review

## Stage 1: Spec Compliance

### Requirement 1: Gate-class taxonomy is source-discoverable
- **Expected**: Every gate in `cortex_command/critical_review.py` carries a `# gate-class:` annotation; `grep -c "# gate-class:"` returns exactly 7.
- **Actual**: `grep -c "# gate-class:" cortex_command/critical_review.py` returns **10**. The three extra annotations (lines 126, 135, 197) cover Task 5's `--allow-adhoc` additions: NUL byte hygiene, surrogate hygiene, and the ad-hoc-path `is_file` security gate. The structural intent — every gate annotated, closed-set values only, enforced by parity test — is preserved.
- **Verdict**: PARTIAL
- **Notes**: Count drift documented in the implementation plan and acknowledged in the review brief. The 3 extra annotations represent new gate sites that *correctly* require annotation under Requirement 2(a). Marking PARTIAL rather than FAIL per reviewer guidance — the closed-set + every-site-annotated invariant is the load-bearing contract, not the literal count of 7.

### Requirement 2: Gate-class annotations + docstring caveat are enforced by parity test
- **Expected**: `tests/test_critical_review_gate_class_parity.py` performs three assertions: (a) every gate site has an in-scope annotation from `{security, hygiene, advisory}`; (b) `check_artifact_stable` and `check_synth_stable` docstrings each contain "Does NOT detect", "orchestrator-fabricated input", "engagement"; (c) one `is_relative_to(...)` on a `.resolve()`-d root and zero `os.path.realpath(root) != abspath` patterns.
- **Actual**: All three assertions are implemented (`test_every_gate_site_carries_in_scope_annotation`, `test_renamed_verifiers_have_caveat_substrings`, `test_no_root_pre_resolution_gate`). The (c) test strips docstring + comments before regex-matching to avoid false-positives on archaeological prose. Closed set `_VALID_GATE_CLASSES = frozenset({"security", "hygiene", "advisory"})`. The named-failure diagnostic `Phase 1 atomicity invariant violated — root pre-resolution gate present` matches the spec verbatim. `pytest tests/test_critical_review_gate_class_parity.py -v` exits 0.
- **Verdict**: PASS

### Requirement 3: Ancestor-symlink check replaced with under-root scoping
- **Expected**: The candidate-symlink gate at `:82-89` (`realpath != abspath`) replaced with `Path(candidate).resolve().is_relative_to(Path(root).resolve())` semantics with macOS normcase handling. New tests assert (a) ancestor-symlink accepted if realpath under root, (b) realpath escaping root rejected with realpath in message.
- **Actual**: Implementation at `critical_review.py:142-181` uses `Path(realpath)` + `os.path.normcase` + `is_relative_to`, mirroring `init/scaffold.py`. Both new tests present and passing (`test_module_api_accepts_ancestor_symlink_if_realpath_under_root`, `test_module_api_rejects_realpath_escaping_root` + CLI counterparts). Rejection message names `/etc/hostname` realpath endpoint.
- **Verdict**: PASS

### Requirement 4: Redundant root-symlink gate is removed; atomicity is structurally enforced
- **Expected**: Pre-Phase-1 `realpath(root) != abspath(root)` gate removed; parity test `test_no_root_pre_resolution_gate` enforces atomicity with the named-failure message verbatim.
- **Actual**: No `realpath(root)` binding remains in `validate_artifact_path`. The parity test uses three regex patterns (direct one-line, flipped-operand, two-line bind-then-compare) to defend against re-introduction of the gate in any shape. Strips docstring + comments first to avoid false-positives on archaeological narration. Test passes.
- **Verdict**: PASS

### Requirement 5: Existing symlink-rejection tests split and updated
- **Expected**: `test_critical_review_path_validation.py` splits the old single-rejection tests into accept/reject pairs at both module and CLI layers; `grep -c 'def test_module_api_accepts_ancestor_symlink_if_realpath_under_root\|def test_module_api_rejects_realpath_escaping_root'` returns 2.
- **Actual**: Both module-API tests defined (`:101-117`, `:120-156`) and CLI counterparts also present (`test_cli_rejects_realpath_escaping_root`, `test_cli_accepts_ancestor_symlink_if_realpath_under_root`). Spec grep returns 2. Strict-prefix and prepare-dispatch tests unchanged.
- **Verdict**: PASS

### Requirement 6: Auto-resolve helper snapshots ad-hoc input
- **Expected**: `validate_artifact_path(allow_adhoc=True)` snapshots files outside both roots into `cortex/_adhoc/<sha[:2]>/<sha[2:]>/<basename>` using atomic temp-rename via `.staging-*` filename; returns dict with `source_path` and `snapshot_sha`.
- **Actual**: `_snapshot_adhoc` helper at `:228-272` reads bytes, writes to `<fanout>/.staging-<sha[2:]>.<basename>`, fsyncs, then `os.rename`s to `<fanout>/<sha[2:]>/<basename>` after `final_dir.mkdir(parents=True, exist_ok=True)`. Repo root derived from `first_root.parent.parent` as specified. Snapshot test (`test_module_api_adhoc_snapshots_file_under_cortex_adhoc`) asserts (a) snapshot exists at expected path, (b) bytes match, (c) `source_path` + `snapshot_sha` round-trip in the dict result.
- **Verdict**: PASS

### Requirement 7: `source_path` and `snapshot_sha` recorded in events.log; NUL/surrogate validation
- **Expected**: `_build_sentinel_absence_event` accepts optional kwargs; threaded through event emitters; NUL bytes and surrogate code points rejected at validation boundary; other ASCII controls (incl. newlines) preserved verbatim and JSON-escaped on write. Grep returns ≥ 4.
- **Actual**: Helper signature at `:552-561` accepts `source_path` and `snapshot_sha`, with field-additive emission (kwargs omitted from dict when None). NUL check at `:127` and surrogate check at `:132-140` raise `ValueError` before any realpath/snapshot work. Newline-in-path test (`test_module_api_accepts_newline_in_path`) and JSON-escape round-trip test (`test_newline_path_round_trips_through_json_escape`) both pass and assert the raw events.log row contains the JSON-escaped `\n` sequence rather than a real newline byte. `grep -c 'source_path\|snapshot_sha' cortex_command/critical_review.py` returns 28 (≥ 4).
- **Verdict**: PASS

### Requirement 8: Events-registry schema is updated
- **Expected**: `bin/.events-registry.md`'s `sentinel_absence` row declares optional `source_path:` and `snapshot_sha:` fields; `grep -c` returns ≥ 2.
- **Actual**: Lines 151-152 of `bin/.events-registry.md` extend the `sentinel_absence` row with both fields, marked `(string, optional)` and citing the consumer (`cortex clean --adhoc`). `grep -c` returns 2.
- **Verdict**: PASS

### Requirement 9: `cortex clean --adhoc` retention recipe with events.log pinning
- **Expected**: New `cortex-clean` script implementing 3-tier glob (active + archive + sessions), pin set from `snapshot_sha:` values across events.logs, time + pin retention, tombstone-rename two-pass deletion, malformed-row WARN handler with exit code 2, `.staging-*` ignored, `--dry-run`.
- **Actual**: `cortex_command/clean.py` implements all of this. `_enumerate_events_logs` walks the three iteration classes (`*/events.log`, `archive/*/events.log`, `sessions/*/events.log`) with materialized list + `FileNotFoundError` tolerance. `_build_pin_set` parses JSONL with the WARN-and-continue handler in the exact specified format. `_delete_snapshot` uses tombstone-rename with EEXIST/ENOTEMPTY collision handling + reclaim-and-retry. `_enumerate_snapshot_dirs` filters `.staging-*` and `.tombstone-*` at both fanout and leaf levels. Exit-code policy: 0 / 2 / 3 implemented. All 11 scenario tests pass (including archive-pin, sessions-pin, malformed-row WARN with exit 2). Concurrency invariant test file ships separately with structural pattern guards.
- **Verdict**: PASS

### Requirement 10: `cortex/_adhoc/` is gitignored
- **Expected**: `git check-ignore cortex/_adhoc/anything/file` exits 0.
- **Actual**: Line 60 of `.gitignore` contains `cortex/_adhoc/`. `git check-ignore` exits 0.
- **Verdict**: PASS

### Requirement 11: Verifier subcommands renamed, gate-class annotated `advisory`
- **Expected**: `verify-reviewer-output` → `check-artifact-stable`; `verify-synth-output` → `check-synth-stable`; Python function renames in lock-step; `# gate-class: advisory` annotation on each; docstring contains the 3 required substrings; wire-protocol sentinels `READ_OK:` / `SYNTH_READ_OK:` intentionally unchanged with a divergence note in the docstring.
- **Actual**: Both subcommand names (`:824, :835`) and function names (`check_synth_stable`, `check_artifact_stable`) renamed in lock-step. `# gate-class: advisory` on `:377` and `:447`. Docstrings on both functions contain all three substrings. Sentinel-divergence note recorded in both docstrings. `grep -c 'check-artifact-stable\|check-synth-stable'` returns 7 (≥ 4); `grep -c 'verify-reviewer-output\|verify-synth-output'` returns 0.
- **Verdict**: PASS

### Requirement 12: All downstream skill-prose references update in lock-step
- **Expected**: All 7 SKILL.md / verification-gates.md sites updated; tests updated; plugin mirrors regenerated; archived lifecycle dirs intentionally frozen. Spec grep returns 0.
- **Actual**: Canonical skills updated at the listed sites. Plugin mirrors regenerated identically. `tests/test_critical_review_sentinel_window.py` imports renamed. `tests/test_variant_a_writer_sites_baseline.py:225, 238, 245` reference `check-synth-stable`. Spec grep returns 0. Reviewer-fixture transcripts under `tests/fixtures/critical-review/` still mention `verify_reviewer_output` / `verify_synth_output` — these are intentional historical transcript content (fixture inputs to sentinel-window tests) and fall outside the rename surface specified by Requirement 12.
- **Verdict**: PASS

### Requirement 13: `is_file` gate is classified `security`
- **Expected**: The `is_file` non-regular-file rejection gate is annotated `# gate-class: security`.
- **Actual**: Line 185 (primary `is_file` gate post-root-match) carries `# gate-class: security`. Line 197 (ad-hoc-path `is_file` gate added by Task 5) also carries `# gate-class: security`. Both fall within the closed set asserted by the parity test.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. Public functions use `snake_case`; private helpers prefixed `_`; module organization mirrors existing `cortex_command/` patterns (section banners, dataclass-free single-purpose functions). The rename surfaces (`check_artifact_stable` / `check_synth_stable` / subcommand mirrors) match the spec verbatim. The `_VALID_GATE_CLASSES` frozenset in the parity test follows the project's idiom for module-level constants.

- **Error handling**: Appropriate. `validate_artifact_path` raises typed `ValueError` with caller-debuggable messages naming the realpath endpoint and the violated rule; CLI handlers (`_cmd_*`) convert `ValueError` / `OSError` to exit code 2 with the message on stderr. `_snapshot_adhoc` uses fsync before atomic rename, ensuring durability before the destination becomes visible. `clean.py`'s `_delete_snapshot` carefully distinguishes benign races (`FileNotFoundError`, `EEXIST`, `ENOTEMPTY`) from hard failures (propagated up to convert to exit code 3); malformed JSONL rows produce WARN-and-continue rather than aborting the pass; the three-band exit codes (0 / 2 / 3) are documented and tested. `append_event` already uses tempfile + `os.replace` and the new fields inherit that atomicity.

- **Test coverage**: Strong. 65 tests across the modified/new files all pass. The parity-test file ships three named-failure invariants (`Phase 1 atomicity invariant violated`, `Gate-class parity violated`, the docstring caveat check). The concurrency invariant test file has source-level structural guards (`_assert_tombstone_rename_pattern_intact`) that fire before runtime assertions if `os.rename`, `.tombstone-`, EEXIST/ENOTEMPTY handling, or the enumeration filter is removed. Edge-case coverage includes NUL byte, lone surrogate, newline-in-path, archive-pin, sessions-pin, malformed JSONL row with WARN + exit 2, dry-run, stray non-hex directories, fresh-repo (no archive/sessions).

- **Pattern consistency**: Strong adherence to existing project conventions. The under-root scoping uses the canonical in-house pattern from `init/scaffold.py:113-172` (`os.path.normcase` + `is_relative_to`). The atomic-temp-rename snapshot write mirrors `append_event`'s tempfile + `os.replace` discipline. The two-pass tombstone-rename for deletion mirrors the broader project pattern of decoupling visible-name change from the actual file mutation. The `# gate-class:` annotation pattern matches the project's preference for grep-discoverable contracts over runtime-only registry constructs. The renamed-verifier divergence note (sentinels stay, function name changes) is documented openly in the function docstrings, honoring the Solution-horizon principle from CLAUDE.md (anchor on current knowledge: renaming wire-protocol sentinels would break fixtures and is out of scope).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
