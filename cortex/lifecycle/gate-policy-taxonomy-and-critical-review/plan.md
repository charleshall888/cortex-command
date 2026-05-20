# Plan: gate-policy-taxonomy-and-critical-review

## Overview

Land four targeted fixes to `cortex_command/critical_review.py` plus a source-discoverable gate-class taxonomy in two phases. Every annotation, rename, or docstring substring that the spec binds to structural enforcement lands in the SAME commit as the parity-test assertion that enforces it — no inter-task drift window where prose-only enforcement covers a not-yet-asserted invariant. Phase 1 ships Fix 2 (under-root scoping replacing the ancestor-symlink check, with the redundant root-symlink gate removed atomically) and Fix 4 (verifier rename + `# gate-class: advisory` annotation + three-substring docstring caveat + the matching parity-test assertion). Phase 2 ships Fix 1 (per-gate annotations bundled with their parity-test assertion) and Fix 3 (auto-resolve helper + `_adhoc/` snapshot + `cortex-clean --adhoc` retention, split across two tasks so the concurrency invariant lives in its own parity-style test file).

## Outline

### Phase 1: Under-root scoping & verifier rename (tasks: 1, 2, 3)
**Goal**: Land Fix 2 (replace the macOS-broken candidate-symlink gate with under-root scoping; remove the redundant root-symlink gate atomically) and Fix 4 (rename verifier subcommands + functions, add `# gate-class: advisory`, add three-substring docstring caveats). Each invariant ships with the parity-test assertion that locks it in place — no separately-deletable annotation/docstring/protector triple.
**Checkpoint**: `pytest tests/test_critical_review_path_validation.py tests/test_critical_review_gate_class_parity.py tests/test_critical_review_sentinel_window.py tests/test_variant_a_writer_sites_baseline.py -v` exits 0; the parity test contains both `test_no_root_pre_resolution_gate` and `test_renamed_verifiers_have_caveat_substrings`; `grep -rn 'verify-reviewer-output\|verify-synth-output' skills/ tests/ plugins/cortex-core/skills/ | grep -v '^cortex/lifecycle/' | wc -l` returns 0.

### Phase 2: Auto-resolve helper & gate-class taxonomy (tasks: 4, 5, 6, 7, 8, 9)
**Goal**: Complete the gate-class annotation taxonomy on the remaining gates (`security` for G6, `hygiene` for G1/G2/G4/G5), bundling the annotations with the `test_every_gate_site_carries_in_scope_annotation` parity-test assertion in the same commit. Ship the `--allow-adhoc` snapshot helper with NUL/surrogate validation, thread `source_path` + `snapshot_sha` through event emission and the events-registry, gitignore `cortex/_adhoc/`, and ship `cortex-clean --adhoc` retention split across two tasks: Task 8 carries the script skeleton + pin-set construction + mtime gating + retention scenarios; Task 9 carries the tombstone-rename concurrency invariant in a dedicated parity-style test file with a named-failure diagnostic.
**Checkpoint**: `grep -c '# gate-class:' cortex_command/critical_review.py` returns 7; the parity test now also contains `test_every_gate_site_carries_in_scope_annotation`; `pytest tests/test_critical_review_gate_class_parity.py tests/test_critical_review_event_emission.py tests/test_clean_adhoc.py tests/test_clean_adhoc_concurrency_invariant.py tests/test_critical_review_path_validation.py -v` exits 0; `git check-ignore cortex/_adhoc/anything/file` exits 0; a snapshot pinned by an archived lifecycle's `cortex/lifecycle/archive/<feature>/events.log` is retained by `cortex-clean --adhoc` (verified by Task 8's archived-pin scenario test).

## Tasks

### Task 1: Apply Fix 2 atomically and ship the root-pre-resolution invariant test

- **Files**:
  - `cortex_command/critical_review.py` (modify `:82-89` and `:103-111`)
  - `tests/test_critical_review_gate_class_parity.py` (new)
- **What**: Replace the candidate-symlink gate at `:82-89` (current `realpath != abspath`) with `Path(candidate).resolve().is_relative_to(Path(root).resolve())` under-root scoping, and remove the redundant root-symlink gate at `:103-111` in the same commit. Ship a new pytest file containing only `test_no_root_pre_resolution_gate` (spec Req 2(c)) — this subtest is the structural atomicity invariant for the Phase 1 atomic landing.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - In-house under-root scoping precedent: `cortex_command/init/scaffold.py:167` (uses `Path.resolve().is_relative_to()` with case-normcase handling); `cortex_command/critical_review.py:115` (the existing `is_relative_to` site for the strict-prefix gate). Reuse the same primitive — do not adopt `realpath().startswith()` (explicitly rejected by the in-tree comment at `scaffold.py:165-166`).
  - macOS APFS case-normcase: the existing scaffold pattern already handles `/tmp/claude → /private/tmp/claude` resolution under the realpath endpoint check.
  - Parity test structure: walk `validate_artifact_path`'s source via `inspect.getsource()`, assert via regex that the function contains exactly one `is_relative_to(...)` call on a `.resolve()`-d root path AND zero call sites of the pattern `os.path.realpath(<root>)` followed by inequality comparison with `abspath`. Failure message: `Phase 1 atomicity invariant violated — root pre-resolution gate present`.
  - The new file establishes a small module-level helper `_get_function_source(name: str) -> str` (signature only — implementer writes the body using `inspect.getsource()`) which Task 3 and Task 4 reuse. Tests in this file do not yet assert anything about `check_artifact_stable` or `check_synth_stable` — those gate sites don't exist until Task 3.
- **Verification**: `pytest tests/test_critical_review_gate_class_parity.py::test_no_root_pre_resolution_gate -v` — pass if exit 0 with the test asserting both that the under-root call site is present and that no root pre-resolution gate exists; the test must fail with the named-failure message above if `realpath(root) != abspath(root)` is reintroduced anywhere in `validate_artifact_path`.
- **Status**: [ ] pending

### Task 2: Split path-validation tests and add ancestor-symlink accept/reject pair

- **Files**:
  - `tests/test_critical_review_path_validation.py` (modify `:92-103`, `:186-198`; add new test functions)
- **What**: Split `test_module_api_rejects_symlink_with_realpath_in_message` (`:92-103`) and `test_cli_rejects_symlink_nonzero_exit_and_stderr` (`:186-198`) into direct-symlink-rejected and ancestor-symlink-accepted cases (per spec Req 5). Add `test_module_api_accepts_ancestor_symlink_if_realpath_under_root` (constructs `/tmp/claude` → `/private/tmp/claude` ancestor symlink under a lifecycle root and asserts validation passes) and `test_module_api_rejects_realpath_escaping_root` (constructs a direct symlink at `cortex/lifecycle/foo/evil.md` → `/etc/hostname` and asserts rejection with realpath in the stderr message).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Existing fixture helpers in the file: `_tmp_lifecycle_root()`, `_lifecycle_dir()`. Reuse rather than reimplementing.
  - `tests/test_critical_review_path_validation.py:134-140` (`test_module_api_rejects_path_equal_to_lifecycle_root`) and `:153-162` (`test_module_api_prepare_dispatch_returns_sha_and_path`) remain unchanged.
  - The realpath-escapes-root case must verify the stderr message names the realpath endpoint (not the literal symlink path) — this is the contract for caller-debuggability.
- **Verification**: `pytest tests/test_critical_review_path_validation.py -v` — pass if exit 0; AND `grep -c 'def test_module_api_accepts_ancestor_symlink_if_realpath_under_root\|def test_module_api_rejects_realpath_escaping_root' tests/test_critical_review_path_validation.py` = 2.
- **Status**: [ ] pending

### Task 3: Rename verifier subcommands, update all callers, add `advisory` annotations, docstrings, and the matching parity-test assertion

- **Files**:
  - `cortex_command/critical_review.py` (rename `:195-216`, `:227-271`, `:449-496`, `:499-554`, `:585-678`; add annotations and docstrings)
  - `tests/test_critical_review_gate_class_parity.py` (extend with `test_renamed_verifiers_have_caveat_substrings`)
  - `skills/critical-review/SKILL.md` (lines 70, 86)
  - `skills/critical-review/references/verification-gates.md` (lines 33, 40, 70, 73, 84)
  - `tests/test_critical_review_sentinel_window.py` (update imports of `verify_reviewer_output` / `verify_synth_output`)
  - `tests/test_variant_a_writer_sites_baseline.py` (lines 225, 238, 245)
- **What**: Rename the Python functions `verify_reviewer_output` → `check_artifact_stable` and `verify_synth_output` → `check_synth_stable`, the argparse subparser names `verify-reviewer-output` → `check-artifact-stable` and `verify-synth-output` → `check-synth-stable`, all skill-prose references in the canonical skills tree, and all test references. Plugin mirrors at `plugins/cortex-core/skills/critical-review/SKILL.md` and `plugins/cortex-core/skills/critical-review/references/verification-gates.md` regenerate via the dual-source pre-commit hook — do not hand-edit. Add `# gate-class: advisory` annotation immediately preceding the `return` site of each renamed verifier. Replace each renamed function's docstring to contain all three substrings: `Does NOT detect`, `orchestrator-fabricated input`, `engagement`. Add a one-sentence docstring note explaining the deliberate sentinel-string divergence (`READ_OK:` / `SYNTH_READ_OK:` intentionally unchanged because renaming wire-protocol sentinels would break every reviewer fixture and dispatching skill — out of ticket 255 scope). **In the same commit**, extend `tests/test_critical_review_gate_class_parity.py` with `test_renamed_verifiers_have_caveat_substrings` (spec Req 2(b)) which reads `check_artifact_stable.__doc__` and `check_synth_stable.__doc__` and asserts all three substrings appear in each — multi-substring check resists single-word rephrasing. The annotation, docstring, and parity assertion land together; no inter-commit drift window.
- **Depends on**: none (parallel-eligible with Task 1 — the rename touches a different code surface)
- **Complexity**: complex
- **Context**:
  - Caller enumeration (per spec Reqs 11, 12 and research §Verifier-rename downstream callsite enumeration): seven canonical skill-prose lines + two Python test files + plugin mirrors (regen, not hand-edit) + critical_review.py function/argparse definitions. Archived lifecycle dirs (`cortex/lifecycle/critical-review-sentinel-gate-relax-first/`, `cortex/lifecycle/reduce-sub-agent-dispatch-artifact-duplication/`) are intentionally frozen — do not touch.
  - Sentinel-string divergence rationale: the wire-protocol sentinels (`READ_OK:`, `SYNTH_READ_OK:`) are emitted by reviewer/synth agent prompts and parsed by `_extract_read_ok_sha`. Renaming them would invalidate every saved transcript and break the dispatch-time prompt-template integration. The deliberate divergence is documented in the gate's docstring so a future maintainer grep-ing for `check_artifact_stable` finds the link to `READ_OK:`.
  - Annotation placement: `# gate-class: advisory` goes on the line immediately preceding the function's terminal `return` site (the canonical "gate fires" location). Per spec Req 1 this is the format the parity test will enforce.
  - The parity-test extension reuses Task 1's `_get_function_source` helper. The new test imports `cortex_command.critical_review.check_artifact_stable` and `check_synth_stable` directly, asserts each `.__doc__` contains all three required substrings.
- **Verification**: `pytest tests/test_critical_review_gate_class_parity.py::test_no_root_pre_resolution_gate tests/test_critical_review_gate_class_parity.py::test_renamed_verifiers_have_caveat_substrings tests/test_critical_review_sentinel_window.py tests/test_variant_a_writer_sites_baseline.py -v` — pass if exit 0; AND `grep -c 'check-artifact-stable\|check-synth-stable' cortex_command/critical_review.py` ≥ 4; AND `grep -c 'verify-reviewer-output\|verify-synth-output' cortex_command/critical_review.py` = 0; AND `grep -rn 'verify-reviewer-output\|verify-synth-output' skills/ tests/ plugins/cortex-core/skills/ | grep -v '^cortex/lifecycle/' | wc -l` = 0; AND `grep -c '# gate-class: advisory' cortex_command/critical_review.py` ≥ 2.
- **Status**: [ ] pending

### Task 4: Annotate remaining gates and ship the closed-set parity-test assertion

- **Files**:
  - `cortex_command/critical_review.py` (5 annotation sites)
  - `tests/test_critical_review_gate_class_parity.py` (extend with `test_every_gate_site_carries_in_scope_annotation`)
- **What**: Add `# gate-class: hygiene` annotations immediately preceding the gate `raise` / `return` sites of G1 (candidate-symlink check at `:82-89`, now under-root scoping after Task 1), G2 (root-empty validation at `:95-98`), G4 (strict-prefix containment at `:113-120` post-Phase-1 line shift), G5 (feature-narrowing prefix at `:122-129`). Add `# gate-class: security` on G6 (`is_file` check at `:132-135` — rejecting non-regular files is the closest gate in the inventory to a security boundary). G3 (the removed root-symlink gate) is not annotated — it no longer exists after Task 1. G7 and G8 (verifier gates) were annotated `advisory` in Task 3. **In the same commit**, extend `tests/test_critical_review_gate_class_parity.py` with `test_every_gate_site_carries_in_scope_annotation` (spec Req 2(a)) which walks every `raise GateError(...)` / `return ("absent"|"mismatch"|"read_failed"|"ok", ...)` site inside `validate_artifact_path`, `check_synth_stable`, and `check_artifact_stable`, asserts each carries an in-scope `# gate-class: <security|hygiene|advisory>` annotation within 3 lines preceding the site, with the class value drawn from the closed set (no bare `# gate-class:`, no other class names). The annotations and the parity assertion land together — a future commit that adds a new gate without annotation, or removes an annotation, fails the parity test immediately.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**:
  - Per-gate classification table per research.md lines 33-44; spec Reqs 1, 13.
  - Annotation idiom matches the in-file `# Req 9X` precedent (`critical_review.py:86, :114, :117, :125`).
  - Closed-set values: `security`, `hygiene`, `advisory`. The parity test asserts no other class names appear.
  - Walker shape: site-level regex `^[ ]+(raise GateError|return \(["\'](absent|mismatch|read_failed|ok)["\'])` matched against the source of the three named function bodies (via Task 1's `_get_function_source` helper). The 3-line annotation window is generous to allow blank lines and brief comments.
- **Verification**: `grep -c '# gate-class:' cortex_command/critical_review.py` = 7 (5 from this task + 2 advisory from Task 3); AND `grep -c '# gate-class: security' cortex_command/critical_review.py` = 1; AND `grep -c '# gate-class: hygiene' cortex_command/critical_review.py` = 4; AND `grep -c '# gate-class: advisory' cortex_command/critical_review.py` = 2; AND `pytest tests/test_critical_review_gate_class_parity.py::test_every_gate_site_carries_in_scope_annotation -v` exits 0.
- **Status**: [ ] pending

### Task 5: Add `--allow-adhoc` flag, NUL/surrogate validation, and snapshot helper

- **Files**:
  - `cortex_command/critical_review.py` (extend `validate_artifact_path` and argparse wiring at `:113-129` and `:585-678`)
  - `tests/test_critical_review_path_validation.py` (add `test_module_api_adhoc_snapshots_file_under_cortex_adhoc`, `test_module_api_rejects_nul_byte_in_path`, `test_module_api_rejects_surrogate_codepoint_in_path`, `test_module_api_accepts_newline_in_path`)
- **What**: Add a new `--allow-adhoc` argparse flag (default off) to the validation surface. Add NUL-byte and surrogate-codepoint rejection at the candidate-string boundary inside `validate_artifact_path` (raise `ValueError`) — the check fires via `candidate.encode('utf-8', errors='strict')`, where a `UnicodeEncodeError` indicates a surrogate. Other ASCII control characters (newlines, tabs, 0x01-0x09, 0x0B-0x1F, 0x7F) are LEGAL and pass through. When `--allow-adhoc` is set and the candidate's realpath lies outside both `cortex/lifecycle/` and `cortex/research/`, snapshot the file into `cortex/_adhoc/<sha[:2]>/<sha[2:]>/<basename>` (peer of `cortex/lifecycle/`, full-hash + 2-char fanout). Use atomic temp-rename: write to `cortex/_adhoc/<sha[:2]>/.staging-<sha[2:]>.<basename>` first, then `os.rename` to the final path after `os.makedirs(parents=True, exist_ok=True)`. Return a validation result dict carrying `source_path` (original path string, post-NUL/surrogate validation, preserved verbatim) and `snapshot_sha` (full hex SHA-256). Existing return shape for non-adhoc paths is unchanged.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - SHA-prefix layout: full-hash with 2-char fanout per research recommendation (pnpm CAFS pattern). Resists prefix-collision at the 65k-entry mark that 8-char prefixes hit.
  - Atomic temp-rename pattern: a snapshot in progress (`.staging-*` filename) is invisible to `cortex-clean --adhoc` (Task 8 ignores `.staging-*`) and the `os.rename` final step is atomic on the same filesystem.
  - NUL is the one POSIX byte paths cannot legally contain — rejection is universal. Surrogate code points come from `surrogateescape`-decoded argv carrying invalid UTF-8 bytes — the strict-encode check is the canonical detector. Other control chars (newlines, tabs, ANSI escapes) are legal POSIX and we preserve them; downstream consumer-side sanitization (terminal printing) is the consumer's responsibility, not the validation boundary's.
  - Helper signature for the snapshot worker: `_snapshot_adhoc(candidate_realpath: Path, repo_root: Path) -> tuple[Path, str]` returning `(snapshot_path, full_sha)`.
- **Verification**: `pytest tests/test_critical_review_path_validation.py::test_module_api_adhoc_snapshots_file_under_cortex_adhoc tests/test_critical_review_path_validation.py::test_module_api_rejects_nul_byte_in_path tests/test_critical_review_path_validation.py::test_module_api_rejects_surrogate_codepoint_in_path tests/test_critical_review_path_validation.py::test_module_api_accepts_newline_in_path -v` — pass if exit 0 with all four tests green.
- **Status**: [ ] pending

### Task 6: Thread `source_path` + `snapshot_sha` through event emission and the events-registry

- **Files**:
  - `cortex_command/critical_review.py` (extend `_build_sentinel_absence_event` at `:375-416` with two optional kwargs)
  - `bin/.events-registry.md` (extend the `sentinel_absence` row at line ~113)
  - `tests/test_critical_review_event_emission.py` (new; contains `test_source_path_field_round_trip`, `test_newline_path_round_trips_through_json_escape`)
- **What**: Extend `_build_sentinel_absence_event` to accept optional `source_path: str | None = None` and `snapshot_sha: str | None = None` kwargs. When a validation result includes a `source_path` (i.e., the artifact was ad-hoc-snapshotted in Task 5), event emitters thread both onto the `sentinel_absence` dict. Other event-construction paths pass `None` and the kwargs are omitted from the emitted JSON. Update the `sentinel_absence` row in `bin/.events-registry.md` to declare both `source_path:` (string, optional) and `snapshot_sha:` (string, optional) as field-additive extensions — no new event row is added. New test file asserts (a) snapshotted ad-hoc input produces an `events.log` row containing the original path under `source_path` and the snapshot SHA under `snapshot_sha`, (b) a path containing a newline character passes validation and round-trips through the events.log JSON-escaped form intact.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - `append_event` helper at `cortex_command/critical_review.py:278-326` already uses `json.dumps` (which JSON-escapes control chars on write) plus tempfile + `os.replace` for atomic-append durability. No changes to the writer; the kwargs flow into the dict before serialization.
  - Events-registry schema convention: optional fields are listed under the row with a `(optional)` qualifier; the existing schema-validation test (if present in `tests/test_events_registry_schema.py` or similar) tolerates field-additive extensions.
  - The round-trip test must construct a path containing `\n` (newline) and assert the events.log line is JSON-escaped (i.e., the literal `\\n` sequence appears in the events.log row when read as bytes, and `json.loads` of the row recovers the original `\n`-containing string).
- **Verification**: `pytest tests/test_critical_review_event_emission.py -v` — pass if exit 0 with both tests green; AND `grep -c '"source_path"\|"snapshot_sha"' cortex_command/critical_review.py` ≥ 4 (two helper signature params + two event-dict writes); AND `grep -c 'source_path\|snapshot_sha' bin/.events-registry.md` ≥ 2.
- **Status**: [ ] pending

### Task 7: Gitignore `cortex/_adhoc/`

- **Files**:
  - `.gitignore` (append one line)
- **What**: Append `cortex/_adhoc/` to the repository `.gitignore`. The line ensures snapshots produced by Task 5 are not tracked in git history (snapshots are scratch state, pruned by Task 8's retention recipe).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - The peer location (`cortex/_adhoc/`, NOT `cortex/lifecycle/_adhoc/`) avoids the lifecycle-slug-iterator collision documented in research Adversarial item 2 — multiple downstream consumers walk `cortex/lifecycle/*/` expecting per-feature directories.
- **Verification**: `git check-ignore cortex/_adhoc/anything/file` — pass if exit 0 (i.e., the path is gitignored); AND `grep -c '^cortex/_adhoc/$' .gitignore` = 1.
- **Status**: [ ] pending

### Task 8: Ship `cortex-clean` skeleton with `--adhoc` pin-set + retention basics

- **Files**:
  - `pyproject.toml` (add `[project.scripts]` entry `cortex-clean = "cortex_command.clean:main"`)
  - `cortex_command/clean.py` (new module — main, argparse, pin-set construction, mtime gating, SHA-regex directory filter, `.staging-*` skip, malformed-JSONL WARN handler, three-band exit-code policy, `--dry-run`)
  - `tests/test_clean_adhoc.py` (new test file — scenarios a, b, c, f, plus the archived-pin scenario added in response to the critical-review)
- **What**: Ship a new console script `cortex-clean` registered in `pyproject.toml`. The `--adhoc` subcommand scans `cortex/_adhoc/<sha[:2]>/<sha[2:]>/` snapshot directories, builds a pin set, and deletes snapshot directories whose computed SHA is not pinned AND whose mtime is older than 7 days. **Pin-set construction walks all three iteration classes of `cortex/lifecycle/`**: active lifecycles at `cortex/lifecycle/<feature>/events.log` (depth-1), archived lifecycles at `cortex/lifecycle/archive/<feature>/events.log` (depth-2), and sessions at `cortex/lifecycle/sessions/<uuid>/events.log` (depth-2). Implementation: enumerate via `list(Path('cortex/lifecycle').glob('*/events.log')) + list(Path('cortex/lifecycle/archive').glob('*/events.log')) + list(Path('cortex/lifecycle/sessions').glob('*/events.log'))`, materializing the result before iteration so a concurrent `git mv cortex/lifecycle/foo cortex/lifecycle/archive/foo` does not produce a duplicate read or a missing pin (tolerate per-file `FileNotFoundError` during iteration via try/except — the materialized list may name a now-moved path). Skip any directory matching `.staging-*` (in-flight snapshots from Task 5) or `.tombstone-*` (queued deletions; the tombstone-rename atomicity logic lives in Task 9). Malformed JSONL rows are skipped with a stderr `WARN: skipped malformed row at <path>:<lineno>: <reason>` and pin-set construction continues; exit code 2 (warning) when any row was skipped, exit code 0 on clean parse, exit code ≥ 3 on hard failure. Add `--dry-run` flag that prints deletion candidates without modifying anything.
- **Depends on**: [5]
- **Complexity**: complex (rationale: new module + new pattern — the three-tier `cortex/lifecycle/` iteration discipline is a project-new pattern not previously written)
- **Context**:
  - Three-tier iteration precedent: `cortex_command/discovery.py:112` recognizes `cortex/lifecycle/archive/` as a distinct iteration class (it `continue`s past it for active-session detection). Task 8 inverts that semantic (include archive when building the pin set) but reuses the same iteration-class taxonomy.
  - Console script registration pattern: see existing `[project.scripts]` entries in `pyproject.toml`.
  - Pin-set construction: open each `events.log` path in the materialized list, parse line-by-line with `json.loads`; on `json.JSONDecodeError` emit the WARN line and continue. Collect every `event["snapshot_sha"]` value where present; skip events without the field.
  - SHA derivation from directory path: `sha = parent_dir.name + leaf_dir.name` (the 2-char fanout + 62-char remainder). Snapshot directories not matching `^[0-9a-f]{2}/[0-9a-f]{62}/$` are skipped (no false-positive deletion of stray directories).
  - Test scenarios: (a) old-and-unpinned snapshot deleted; (b) old-and-pinned-by-active-events.log snapshot retained; (c) new-and-unpinned snapshot retained; (f) `.staging-*` and `.tombstone-*` paths are ignored; **(g) old-and-pinned-by-archived-events.log snapshot retained** (newly added in response to critical-review — constructs a snapshot, places a `snapshot_sha:` reference inside `cortex/lifecycle/archive/<feature>/events.log`, asserts the snapshot is NOT deleted after `cortex-clean --adhoc`); **(h) old-and-pinned-by-sessions-events.log snapshot retained** (newly added — same pattern with `cortex/lifecycle/sessions/<uuid>/events.log`). Concurrency scenarios (d and e from spec) move to Task 9.
- **Verification**: `pytest tests/test_clean_adhoc.py -v` — pass if exit 0 with all six scenario tests green (a/b/c/f/g/h); AND `grep -c '^cortex-clean = ' pyproject.toml` = 1; AND `cortex-clean --adhoc --dry-run` against a synthetic tempdir fixture containing one pinned-by-archive snapshot retains it (covered by scenario g).
- **Status**: [ ] pending

### Task 9: Ship tombstone-rename concurrency invariant in a dedicated parity-style test file

- **Files**:
  - `cortex_command/clean.py` (extend the deletion path with tombstone-rename two-pass logic)
  - `tests/test_clean_adhoc_concurrency_invariant.py` (new — dedicated parity-style file with named-failure diagnostic)
  - `tests/test_clean_adhoc.py` (extend with scenario e — malformed-JSONL WARN exit-code-2 path, since the malformed-row handler is exercised more naturally alongside the concurrency-aware deletion path)
- **What**: Extend `cortex_command/clean.py`'s deletion path with the tombstone-rename two-pass atomicity logic: rename `<sha[2:]>/` to `.tombstone-<sha[2:]>/` first, then `rm -rf` the tombstone in a second pass within the same invocation. Concurrent invocations that see `.tombstone-*` skip silently (the first invocation owns the cleanup). Ship a dedicated parity-style test file `tests/test_clean_adhoc_concurrency_invariant.py` containing `test_tombstone_rename_atomic_against_concurrent_cleaner` (simulates two concurrent invocations via tempdir + manual `.tombstone-*` placement; asserts no error, no half-delete, exactly one final `rm -rf`) AND `test_concurrent_cleaner_skips_tombstoned_directory` (asserts the second invocation observes `.tombstone-*` and skips). Both tests must fail with the named diagnostic `Concurrency invariant violated — tombstone-rename atomicity broken` if the tombstone-rename pattern is removed, replaced with direct `rm -rf`, or the skip-on-tombstone branch is deleted. The dedicated file with named diagnostic resists casual deletion in future test refactors (precedent: Phase 1's Task 1 parity file).
- **Depends on**: [8]
- **Complexity**: complex (rationale: new pattern — tombstone-rename atomicity is a project-new concurrency primitive)
- **Context**:
  - Tombstone-rename atomicity: `os.rename` is atomic within a filesystem. A second invocation seeing `.tombstone-<sha[2:]>/` skips because it's owned by the first invocation. The first invocation's second pass (`rm -rf`) tolerates partial pre-deletion.
  - Concurrency test simulation: pre-place a `.tombstone-<sha[2:]>/` directory in the fixture, then invoke `cortex-clean --adhoc` and assert it skips that directory without error.
  - Parity-test file naming and diagnostic format mirror Task 1's pattern (`tests/test_critical_review_gate_class_parity.py` with `Phase 1 atomicity invariant violated — root pre-resolution gate present`). The named diagnostic surfaces in the test failure message immediately and is grep-discoverable from the source.
  - Scenario e (malformed JSONL row → exit code 2 + WARN stderr line) is added to `tests/test_clean_adhoc.py` in this task (not Task 8) because the WARN-and-continue pattern interacts with the deletion path that Task 9 finalizes.
- **Verification**: `pytest tests/test_clean_adhoc_concurrency_invariant.py tests/test_clean_adhoc.py -v` — pass if exit 0 with both concurrency-invariant tests green and the (e) malformed-row scenario test green; AND the parity-style test fails with `Concurrency invariant violated — tombstone-rename atomicity broken` when `os.rename` is replaced with direct `shutil.rmtree` or the tombstone-skip branch is removed (verifier: a deliberate one-line edit to `clean.py` confirms the named-failure path fires).
- **Status**: [ ] pending

## Risks

- **Sentinel-string divergence is a known design call.** `READ_OK:` and `SYNTH_READ_OK:` intentionally do NOT rename alongside the verifier function rename, because renaming wire-protocol sentinels would invalidate every reviewer/synth transcript fixture and break every dispatching skill's prompt template. The Task 3 in-docstring breadcrumb is the maintainer-discoverability mitigation; the Task 3 parity assertion `test_renamed_verifiers_have_caveat_substrings` enforces the bypass-limitation substrings but does NOT enforce the sentinel-link breadcrumb (the spec's Req 2(b) substring set is `Does NOT detect`, `orchestrator-fabricated input`, `engagement` — disjoint from `READ_OK:` / `SYNTH_READ_OK:`). A future maintainer search for `check_artifact_stable` may not find the sentinel parser without the docstring breadcrumb. **If this becomes operationally painful, the follow-up fix is a Req 2(b) substring-set extension OR a parallel `# wire-protocol-sentinel: READ_OK` annotation pattern enforced by a new parity assertion** — not in scope for ticket 255 because the spec's Req 2(b) substring set is fixed.
- **`cortex-clean --adhoc` retention pin walks all three iteration classes of `cortex/lifecycle/` (active + archive + sessions). However, the wontfix workflow may later evolve to a different archival convention (e.g., `cortex/lifecycle/wontfix/`), and that case would silently regress pinning until the glob shape is extended.** Operators should not assume the three-tier iteration is forever; if a fourth lifecycle-tier directory is introduced, Task 8's glob and Task 8's scenario tests (g) and (h) must be extended.
- **In-flight race between `cortex-clean --adhoc` pin-set scan and `git mv` wontfix-relocation.** The scan materializes its glob result via `list(Path.glob(...))` BEFORE iterating, then tolerates per-file `FileNotFoundError` during iteration. The materialized snapshot may name a now-moved path; the FileNotFoundError tolerance preserves cleanup progress. A relocated lifecycle's events.log is included in the NEXT cleanup run via its new path (and not the old). Worst-case impact is one cleanup run missing some pins for the in-flight-moved lifecycle; the snapshot's mtime threshold (7 days) means a single missed scan is recoverable.
- **The Task 3 rename surface is enumerated from research §Verifier-rename downstream callsite enumeration but is grep-verified, not exhaustively cross-referenced.** A long-tail caller in an unscanned tree (e.g., a third-party plugin in `~/.claude/plugins/`) is out of repo scope but could break silently. Acceptance criterion 3 (`grep -rn 'verify-reviewer-output\|verify-synth-output' skills/ tests/ plugins/cortex-core/skills/` = 0) bounds the in-repo surface; out-of-repo callers are operator-discoverable via subcommand-not-found errors after the rename lands.
- **The `# gate-class:` annotation strategy is grep-discoverable AND parity-test enforced for presence + closed-set value, but not for staleness — an annotated gate whose semantics drift remains flagged with its original class until manually re-audited.** RUF100-style stale-tag detection is a deferred follow-up per spec Non-Requirements.
- **Phase 1 → Phase 2 hard dependency on macOS.** Phase 2's `_adhoc/` snapshot paths resolve through `/private/var/folders/...` on macOS; without Phase 1's under-root scoping fix (Task 1), the current ancestor-symlink check rejects these paths. Phase 2 tasks (5-9) cannot land before Phase 1 tasks (1-3) complete on a macOS dev machine.

## Acceptance

The four fixes (Fix 1 gate-class taxonomy, Fix 2 under-root scoping, Fix 3 auto-resolve helper, Fix 4 verifier rename + rescope) all land per the spec's Requirements 1-13: `pytest tests/test_critical_review_path_validation.py tests/test_critical_review_gate_class_parity.py tests/test_critical_review_sentinel_window.py tests/test_critical_review_event_emission.py tests/test_clean_adhoc.py tests/test_clean_adhoc_concurrency_invariant.py tests/test_variant_a_writer_sites_baseline.py -v` exits 0; `grep -c '# gate-class:' cortex_command/critical_review.py` = 7; `grep -rn 'verify-reviewer-output\|verify-synth-output' skills/ tests/ plugins/cortex-core/skills/ | grep -v '^cortex/lifecycle/' | wc -l` = 0; `git check-ignore cortex/_adhoc/anything/file` exits 0; the archived-pin scenario test from Task 8 (g) passes (a snapshot pinned by `cortex/lifecycle/archive/<feature>/events.log` is retained after `cortex-clean --adhoc`); the dedicated concurrency-invariant test file from Task 9 contains a named-failure diagnostic that fires on regression of the tombstone-rename pattern.
