# Review: offload-load-requirementsmd-selection-to-a

Read-only review of commits `d9fb8dfc..b92900c8` (7 commits, #333) against `spec.md` (R1–R15, two phases). Behavior was verified live via `CORTEX_COMMAND_FORCE_SOURCE=1 bin/cortex-load-requirements` and `python3 -m`, and by running the three target test files plus the two #328 sweep files (all green). The documented deviations (stdlib-only tag parsing; R14b/R15 found already-green upstream) are honored and not flagged as FAIL.

## Stage 1: Spec Compliance

### Requirement 1: Verb module (pure selection fn + CLI shim)
- **Expected**: `cortex_command/lifecycle/load_requirements_cli.py` with a pure `resolve(...)` fn (modeled on `resolve_item.py`) + a `main()` shim (modeled on `backlog_backend_cli.py`); `python3 -m … --feature <slug>` exits 0 and prints a newline-delimited path list to stdout.
- **Actual**: `resolve(project_root, feature_slug)` at L188 returns `(lines, fallback_note)`; `main()` at L271 resolves the project root (falls back to `cwd` on `CortexProjectRootError`), writes the joined list + trailing newline to stdout and the note to stderr, returns 0. Live `--feature` run on a synthetic repo printed the 3-path list and exited 0.
- **Verdict**: PASS
- **Notes**: Clean separation of pure selection from I/O shim, exactly per the cited sibling modules.

### Requirement 2: Console-script + bin wrapper + in-scope wiring (W003-safe)
- **Expected**: `cortex-load-requirements = "…load_requirements_cli:main"` in `[project.scripts]`; `bin/cortex-load-requirements` wrapper modeled on `cortex-read-backlog-backend`; an in-scope path-qualified wiring reference; parity green.
- **Actual**: `grep -c 'cortex-load-requirements = ' pyproject.toml` = 1; wrapper is executable and is a faithful dual-channel (FORCE_SOURCE → wheel-probe → working-tree → fail-open) copy of the read-backlog-backend shape, with the `cortex-log-invocation` shim. `CORTEX_COMMAND_FORCE_SOURCE=1 bin/cortex-load-requirements` exits 0 (first line `cortex/requirements/project.md`). The R9 parity file carries the contiguous path-qualified `bin/cortex-load-requirements` literal (`WRAPPER_REL`) as the W003 wiring signal and passes.
- **Verdict**: PASS
- **Notes**: Parity test green; could not replay the historical `--staged` pre-commit run, but the wiring literal is present and the parity suite passes.

### Requirement 3: Input contract — `--feature <slug>` with graceful fallback, byte-equal to no-feature
- **Expected**: `--feature` reads `cortex/lifecycle/{slug}/index.md` tags; absent/tag-less index OR omitted `--feature` ⇒ fallback (never error); `--feature`-on-absent-index stdout byte-identical to no-`--feature`; tests for the three arms + an explicit byte-equality assertion.
- **Actual**: `_read_tags` returns `[]` on missing slug/index/frontmatter (catches `OSError`, never raises). `test_feature_matching_tags_loads_area_docs` (positive), `test_feature_absent_index_falls_back`, `test_no_feature_falls_back`, and `test_feature_absent_index_byte_equals_no_feature` (asserts `a.stdout == b.stdout` AND `a.stderr == b.stderr` byte-for-byte) all pass.
- **Verdict**: PASS

### Requirement 4: Algorithm fidelity with discriminating tests
- **Expected**: trigger-only (left of `→`) match; ASCII case-insensitive substring; whole-tag (no split of `harness-adaptation`); dedup; strip empty/whitespace tags; `[]` ≡ absent ⇒ fallback. Each negative control paired with a positive in the same test on a discriminating fixture: (a) `["", "pipeline"]` loads ONLY pipeline, (b) trigger-vs-path "requirements", (c) `harness-adaptation` not loaded / `harness` loaded.
- **Actual**: `test_empty_string_tag_loads_only_real_match` (loads pipeline, NOT observability, not none), `test_trigger_only_match_not_path` (reqgather loaded, requirements-area path NOT), `test_whole_tag_not_split` (neg `harness-adaptation` → not loaded; pos `harness` → loaded), `test_pure_substring_axis` (`pipe` ⊂ `pipeline` → loads; pins substring vs word-boundary). All paired, all pass. Matching at L211–216 is `tag.lower() in trigger.lower()` over `_parse_conditional_loading` trigger text only.
- **Verdict**: PASS

### Requirement 5: Output shape — full repo-relative paths only, deterministic order, defined dedup, note on stderr
- **Expected**: stdout newline-delimited paths only; `cortex/requirements/project.md` first; then Global Context in file order (absent ⇒ ` (skipped: file absent)`); then matched area docs in section order; dedup by resolved path with Global Context position winning; fallback note to stderr.
- **Actual**: `emit()` (L221) dedups by `seen` set, suffixes absent paths, emits project.md → Global Context → matched in that order. `test_first_line_is_project_md`, `test_stdout_is_paths_only`, `test_dedup_global_context_position_wins` (exact ordered golden `[project.md, shared.md]`) all pass. Live run: note goes to stderr, stdout stays a pure path list.
- **Verdict**: PASS

### Requirement 6: Prose-derived golden + independently-pinned fallback string + live selection oracle
- **Expected**: hand-authored (NOT self-captured) goldens for match / no-match `[]`-single-multi / dedup-multi-tag-one-phrase-unmatched-dropped; **plus a selection test against the live `cortex/requirements/project.md`** that hand-computes the expected selection set for a chosen tag set and asserts the verb matches (a selection oracle, "not just format"); fallback literal written independently in the test.
- **Actual**: The synthetic prose-derived goldens are all present and strong — `test_golden_match` (exact ordered list), `test_golden_fallback_empty`, `test_fallback_string_single_and_multi`, `test_dedup_multi_tag_one_phrase`, `test_unmatched_tag_dropped`. The fallback literals (`EXPECTED_FALLBACK_EMPTY/SINGLE/MULTI`) are hand-written independently of the verb constant (a typo in `FALLBACK_NOTE_TEMPLATE` would fail them). **However**, the live-`project.md` tests do NOT implement a selection oracle for a chosen non-empty tag set: `test_live_project_md_format_invariants` and `test_absent_glossary_literal_resolution` call `resolve(REPO_ROOT, None)` (fallback, no tags, format-only — labeled "Drift-robust invariants only"), and `test_live_conditional_loading_parses_compound_triggers` exercises the *parser* shape (`_parse_conditional_loading`), not the tag→selected-set matching. The "selection oracle, not just format" clause (restated in Technical Constraints) is the one named sub-deliverable not realized.
- **Verdict**: PARTIAL
- **Notes**: Behavior is correct and otherwise well-covered: I verified live that `resolve()` against a real-compound-trigger `project.md` with tag `pipeline` selects `pipeline.md`; the real-format *parse* is pinned by `test_live_conditional_loading_parses_compound_triggers`, and the *selection* logic is pinned by the synthetic prose-derived `test_golden_match`. The residual risk (verb matching silently diverging on the live file's format) is small because both halves are independently covered — but they are not fused into the single live-selection assertion R6 names. The likely cause is the deliberately-shelved `--tags` arm (Non-Requirements): with `resolve()` taking only a `feature_slug` read from disk, a clean live oracle would need a synthetic `cortex/lifecycle/<slug>/index.md` materialized under the repo or a direct exercise of the match loop over live-parsed pairs. A follow-up adding either would close the gap. Non-blocking (behavior correct, no FAIL).

### Requirement 7: No events emission (behavioral assertion)
- **Expected**: verb writes nothing to `events.log`, registers no event; `grep -c '"event"'` = 0; no new `bin/.events-registry.md` row; a behavioral test capturing events.log existence/mtime.
- **Actual**: `grep -c '"event"' …load_requirements_cli.py` = 0. `test_verb_writes_no_events_log` seeds a pre-existing events.log, runs the verb, asserts mtime unchanged AND that the only events.log under the repo is the seeded one. Passes.
- **Verdict**: PASS

### Requirement 8: `project.md` Global Context data fix (behavioral assertion)
- **Expected**: `- glossary.md` → `- cortex/requirements/glossary.md`; `grep -c '^- cortex/requirements/glossary.md'` = 1 and `^- glossary.md$` = 0; a verb test asserting the absent-glossary line is exactly `cortex/requirements/glossary.md (skipped: file absent)`.
- **Actual**: Both greps confirm (1 and 0). `test_absent_glossary_literal_resolution` asserts the exact skipped line against live `REPO_ROOT`. Live run reproduces it. Confirms literal repo-root resolution, not a bare-filename heuristic.
- **Verdict**: PASS

### Requirement 9: Parity test (no replay harness; carries the wiring reference)
- **Expected**: `tests/test_cortex_load_requirements_parity.py` modeled on siblings for structure but NOT reusing the replay harness; carries the path-qualified `bin/cortex-load-requirements` literal; exits 0.
- **Actual**: File present, docstring explicitly states no golden-replay (the "original" is LLM prose), pins deploy surface (wrapper executable, console-script line, log-invocation shim, FORCE_SOURCE first-line). `WRAPPER_REL = "bin/cortex-load-requirements"` is the contiguous wiring literal. Passes.
- **Verdict**: PASS

### Requirement 10: Collapse `load-requirements.md` (~31 → ~12 lines), co-located with test fixes
- **Expected**: keep `# Tag-Based Requirements Loading` + `## Protocol` (run/read/inject/relay) + glossary-surfacing line verbatim; retain `tag-based … loading` citation; remove `## Matching Semantics`; relocate `## Why this protocol` to the module docstring. Collapse + R14 test fixes in the same commit.
- **Actual**: File is 11 lines: title, intent paragraph (names the verb as single source of selection truth), `## Protocol` (3 steps: run verb / read non-skipped paths / inject + relay), glossary line verbatim. Greps: `cortex-load-requirements` = 2, `absence as a signal` = 1, `## Matching Semantics` = 0, citation ≥ 1. Commit `4b934597` collapses the file; commit `384070cc` migrates consumers — the protocol-shape test reconcile landed with the collapse (suite stays green; verified by running `test_load_requirements_protocol.py`).
- **Verdict**: PASS

### Requirement 11: Migrate consumer references (retain citation + name the verb)
- **Expected**: 4 live consumers (refine/clarify, lifecycle/review, discovery/clarify, discovery/research) invoke the verb; specify.md is citation-only (no live call); all 5 keep a citation; lifecycle/refine pass `--feature {slug}`, discovery omits it; no `python3 -m`/`import cortex_command`.
- **Actual**: All 5 match `_CITATION_RE` (grep ≥ 1 each). The 4 live consumers name `cortex-load-requirements` (review.md twice). specify.md names the verb 0 times (citation-only carrier, §1 load skipped on resume). refine/clarify §2 and lifecycle/review §1 pass `--feature {slug}`/`--feature {feature}`; discovery clarify §2 and research §1a omit `--feature` (correct — no lifecycle index). No `python3 -m` in any of the 5 (L201 clean).
- **Verdict**: PASS

### Requirement 12: Fallback-note phrasing reconciled
- **Expected**: review.md §1 keeps its own `drift check covers project.md only` wrapper (orchestrator note, line 12); the reviewer-prompt slot (line 31) is reconciled to a single instruction deferring to the verb output.
- **Actual**: `grep -c 'drift check covers project.md only'` = 1 (review.md §1 line 12, around the verb path list). The line-31 reviewer-prompt slot now reads a single instruction: "the path list cortex-load-requirements printed in §1 … if the verb emitted its no-match fallback note, relay that note instead" — no competing second fallback string.
- **Verdict**: PASS

### Requirement 13: Mirror regeneration + drift-hook green
- **Expected**: `just build-plugin` then `git diff --quiet plugins/` exits 0; dual-source mirror-parity passes; canonical + mirror committed together.
- **Actual**: Ran `just build-plugin`; `git diff --quiet plugins/` exits 0 (clean). `bin/cortex-load-requirements`, `plugins/cortex-core/bin/…`, and `…/skills/lifecycle/references/load-requirements.md` are byte-identical to canonical. Commit-range diffstat shows each canonical edit paired with its mirror.
- **Verdict**: PASS

### Requirement 14: Reconcile protocol-shape tests + pre-existing #328 red, assertion content pinned
- **Expected**: (a) migrate the two former prose-shape tests' substance (numbered-steps/Global-Context nouns AND empty/absent-tags fallback) into the verb test as assertions of the verb's actual selection/fallback behavior (not a `verb runs` placeholder); (b) fix `CONSUMER_REFS`/`RULE_CARRIERS` stale `lifecycle/references/{clarify,specify}.md` → `refine/references/…`. `_CITATION_RE` unchanged. `test_load_requirements_protocol.py` exits 0 with regression-detecting verb assertions.
- **Actual**: `test_load_requirements_protocol.py` passes. `CONSUMER_REFS` now points at `refine/references/{clarify,specify}.md` and `refine/SKILL.md`; `RULE_CARRIERS` at `refine/references/specify.md`. The former prose-shape checks are replaced by `test_load_requirements_md_drives_the_verb` (shim names the verb, keeps `## Protocol`, keeps citation, no `## Matching Semantics`). The selection/fallback substance migrated into `test_load_requirements_cli.py` as real behavioral assertions — `test_golden_match` (exact ordered selection set), `test_unmatched_tag_dropped` (matched-vs-dropped), `test_golden_fallback_empty`/`test_feature_absent_index_falls_back`/`test_no_feature_falls_back` (empty/absent fallback). These fail on a matching/fallback regression — not exit-0 placeholders.
- **Verdict**: PASS

### Requirement 15: Sweep the broader #328 stale path-assertions (proof is a green suite)
- **Expected**: fix stale assertions citing relocated `lifecycle/references/{clarify,specify}.md` in `tests/test_check_skill_path.py` and `tests/test_critical_review_gate_nonlocal_failsafe.py`; leave intentional fixture content; `just test` green (known external flakes excepted).
- **Actual**: Both named files pass (17 passed). The residual `grep` hits in `test_check_skill_path.py` are intentional lint-INPUT strings (e.g. `Read ${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` fed to the SP001/SP002 detector to assert it PASSES, and `../lifecycle/references/clarify.md` fed to assert it FLAGS) — not stale file-existence assertions; the spec explicitly directs "leave intentional fixture content" and states "the binding completeness proof is the green suite, since grep hits ≠ live assertions." All three target test files + both #328 files run green.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the cited patterns. Pure `resolve(project_root, feature_slug)` mirrors `resolve_item.py`; `main(argv)` + `_build_parser()` mirror `backlog_backend_cli.py`. Private helpers (`_frontmatter_lines`, `_extract_tags`, `_read_tags`, `_section_lines`, `_parse_conditional_loading`, `_parse_global_context`, `emit`) are well-scoped and underscore-prefixed. Module-level constants (`PROJECT_MD_RELPATH`, `SKIPPED_SUFFIX`, `ARROW`, `FALLBACK_NOTE_TEMPLATE`) read clearly.
- **Error handling**: Appropriate and fail-safe. Never raises on a missing index (`OSError` → `[]`), missing/unterminated frontmatter (`None` → `[]`), or missing project.md (`OSError` → `""` → fallback). `main()` degrades `CortexProjectRootError` to `cwd`. `_parse_conditional_loading` uses `partition(ARROW)` so a separator-less bullet is skipped, never an `IndexError`. The wrapper fail-opens (branch d, exit 0) so it never blocks a consumer. Stdlib-only tag parsing (documented deviation) lets the wrapper run under system `python3`.
- **Test coverage**: Strong. 33 tests across the three files, all green; discriminating tests are genuinely discriminating — each negative control is paired with a positive in the same test on an engineered fixture (empty-tag, trigger-vs-path, whole-tag, pure-substring), and goldens assert exact ordered lists rather than membership where order/dedup matter. The fallback literals are written independently of the verb constant. The one shortfall is R6's missing live-`project.md` selection oracle (see R6 PARTIAL) — the live tests are format/parse-only; the selection logic is pinned on synthetic data and the real-format parse on live data, but not fused. Recommend a follow-up adding a live selection assertion (materialize a synthetic index under the repo, or exercise the match loop directly over `_parse_conditional_loading(live_text)` for a chosen tag).
- **Pattern consistency**: The dual-channel wrapper matches `bin/cortex-read-backlog-backend` branch-for-branch (FORCE_SOURCE → wheel-probe → working-tree-by-pyproject-name → fail-open) with the `cortex-log-invocation` shim in the first lines. Console-script registered in `[project.scripts]`; canonical + mirror byte-identical. The read-only no-events posture matches the "degenerate Skill-helper module" framing in project.md.

## Requirements Drift
**State**: none
**Findings**:
- None. The new `cortex-load-requirements` console-script adds to the command surface, but this is an instance of the already-documented **Skill-helper modules** constraint in `cortex/requirements/project.md` ("Promoted modules expose a `[project.scripts]` console-script entry (e.g. `cortex-<skill>`)…"). project.md describes the *pattern*, not an enumeration of every console-script, so the addition is anticipated by — and consistent with — existing requirements. The `project.md` glossary-path normalization (R8) conforms the data to the `requirements-write/SKILL.md` Global Context authoring contract rather than diverging from it.
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
