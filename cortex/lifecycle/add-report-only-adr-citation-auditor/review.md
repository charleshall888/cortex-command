# Review: add-report-only-adr-citation-auditor

## Stage 1: Spec Compliance

### Requirement 1: Auditor shipped as a console-script module
- **Expected**: `cortex_command/adr_citation_audit.py` with `main()` entry, registered in `pyproject.toml [project.scripts]` as `cortex-adr-citation-audit`, thin dual-channel `bin/cortex-adr-citation-audit` wrapper. Exit 0 on every path. `--help` exits 0; unresolved reference → exits 0.
- **Actual**: Module exists with `main()` and `if __name__ == "__main__": sys.exit(main())`. `pyproject.toml` line 38: `cortex-adr-citation-audit = "cortex_command.adr_citation_audit:main"`. `bin/cortex-adr-citation-audit` implements the four-branch dual-channel pattern. `--help` confirmed exits 0; run against tree with unresolved refs exits 0.
- **Verdict**: PASS

### Requirement 2: Canonical 4-digit reference resolution
- **Expected**: Recognizes prefix `ADR-NNNN`, bracketed `[ADR-NNNN]`, space `ADR NNNN`, and path `adr/NNNN[-slug]` (exactly 4 digits). Right-boundary `(?![0-9A-Za-z])`. Filed ADRs matched by `^[0-9]{4}-[a-z0-9-]+\.md$`, README.md excluded. Slug-less resolves by number; path-with-slug by exact stem match. Acceptance: `ADR-0001` filed → no finding; `ADR-9999` unfiled → `kind: "unresolved"`; `adr/0001-wrong-slug` with correct `0001-foo.md` → `kind: "slug_mismatch"`.
- **Actual**: `_PREFIX_RE` and `_PATH_RE` match the spec grammar verbatim. `_CORPUS_FILENAME_RE` matches `^([0-9]{4})-([a-z0-9-]+)\.md$` (README excluded by non-digit start). All three acceptance cases confirmed passing by the test suite (`test_req2_*`).
- **Verdict**: PASS

### Requirement 3: Document-local labels and placeholders are not flagged
- **Expected**: `ADR-N` (1–3 digit), `ADR-000N`, `NNNN-` template placeholders produce zero findings.
- **Actual**: `_PREFIX_RE` requires exactly `[0-9]{4}` — one-digit `ADR-2` and non-numeric `ADR-000N` do not match. `NNNN-slug` does not match the ADR regex. `test_req3_non_four_digit_not_flagged` passes.
- **Verdict**: PASS

### Requirement 4: Repo-agnostic within the cortex convention
- **Expected**: Defaults to CWD, accepts `--root <dir>`, resolves against `<root>/cortex/adr/`. Run against synthetic cortex-convention tmp tree → exits 0; `ADR-0001` not reported; `ADR-0002` reported `kind: "unresolved"`.
- **Actual**: `--root` wired via argparse; `audit()` hardcodes `root / "cortex" / "adr"`. `test_req4_synthetic_cortex_convention_tree` passes — no `plugins/`, no cortex-command layout, correctly scopes to `cortex/adr/`.
- **Verdict**: PASS

### Requirement 5: Missing-corpus handling
- **Expected**: When `<root>/cortex/adr/` absent or empty, top-level `corpus_present: false` and references reported `kind: "unresolved"`. Exit 0.
- **Actual**: `load_corpus()` returns `(index, False)` when dir absent. `audit()` sets `corpus_present` from this. `test_req5_no_adr_dir_corpus_present_false` passes. Confirmed via CLI: empty tree → `corpus_present: false`.
- **Verdict**: PASS

### Requirement 6: Duplicate-number detection
- **Expected**: Two or more corpus files with same `NNNN` prefix → `kind: "duplicate_number"` naming colliding files.
- **Actual**: `detect_duplicates()` iterates `index` and emits `{"kind": "duplicate_number", "number": num, "files": [...]}` for `len(stems) > 1`. `test_req6_duplicate_number_finding` passes.
- **Verdict**: PASS

### Requirement 7: Gap detection
- **Expected**: Missing number in `1..max(filed)` → `kind: "gap"`. Superseded-but-present file NOT a gap. Finding uses `gap_number` key.
- **Actual**: `detect_gaps()` scans `range(1, max_num + 1)` and emits `{"kind": "gap", "gap_number": n}` for missing entries. Superseded-but-present files are in the index (keyed on file presence, not frontmatter status). `test_req7_gap_missing_number` and `test_req7_superseded_present_file_not_a_gap` both pass.
- **Verdict**: PASS

### Requirement 8: JSON report contract with finding taxonomy
- **Expected**: Single JSON object on stdout. `# Contract` docblock enumerating four `kind` values. `corpus_present` at top level. `cortex-adr-citation-audit --root <fixture> | python3 -m json.tool` exits 0.
- **Actual**: `# Contract` docblock at lines 20–56 documents the full schema including all four `kind` values and field semantics. `print(json.dumps(report, indent=2, sort_keys=True))` emits the object. Confirmed: `| python3 -m json.tool` exits 0. `test_json_contract_schema` validates the runtime schema.
- **Verdict**: PASS

### Requirement 9: Test suite
- **Expected**: `tests/test_adr_citation_audit.py` exercises reqs 2–7 via subprocess + `--root <tmp_path>`. Model: `tests/test_requirements_parity_audit.py`. Tests pass under `just test`.
- **Actual**: 11 tests covering `--help`, contract schema, reqs 2–7. Uses `subprocess.run` with `sys.executable -m cortex_command.adr_citation_audit --root <tmp_path>`. Fixtures dir path (`tests/fixtures/cortex-adr-citation-audit/`) is excluded in `_EXCLUDED_DIR_PARTS` even though the dir doesn't exist yet (self-exclusion is wired; absence of the dir is not a failure). All 11 tests pass.
- **Verdict**: PASS

### Requirement 10: Console-script wiring + parity + plugin mirror
- **Expected**: `[project.scripts]` entry added; `bin/` wrapper added to justfile recipe (W003 satisfied) and `--help` smoke-test inventory at `test_phase1_sibling_rewrite_smoke.py:45`; `plugins/cortex-core/bin/cortex-adr-citation-audit` regenerated and byte-identical; `test_plugin_mirror_parity.py` passes; parity check reports no W003 orphan.
- **Actual**: `pyproject.toml` line 38 has the console-script entry. Justfile lines 415–417: `adr-citation-audit` recipe calling `bin/cortex-adr-citation-audit`. `test_phase1_sibling_rewrite_smoke.py` has `test_cortex_adr_citation_audit_no_log_invocation_warning` (lines 207–216) under the "Bash dual-channel wrappers" section (docstring header at line 36 lists it). `plugins/cortex-core/bin/cortex-adr-citation-audit` is byte-identical to `bin/cortex-adr-citation-audit` (confirmed by `diff`). `test_plugin_mirror_parity.py` passes. `cortex_command.parity_check` exits 0 with no W003.
- **Verdict**: PASS

### Requirement 11: README:45 area-tagging reword
- **Expected**: `grep -c 'backfill ticket' cortex/adr/README.md` = 0 AND `grep -c 'do not invent' cortex/adr/README.md` ≥ 1.
- **Actual**: `backfill ticket` count = 0; `do not invent` count = 1. Line 45 reads: *"No `area:` field is defined. Area tagging was considered and deliberately not adopted (no consumer); do not invent one ad hoc."* Matches the spec's suggested wording.
- **Verdict**: PASS

---

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Module `adr_citation_audit.py` follows the `parity_check.py` / `requirements_parity_audit.py` naming style. Bin wrapper `cortex-adr-citation-audit` follows the `cortex-check-parity` template exactly.
- **Error handling**: Appropriate for a report-only tool. `load_corpus()` returns a safe default on `OSError`. `scan_file()` returns `[]` on read error. `main()` always returns 0. `set -euo pipefail` in the wrapper with non-zero exit on branch (d) only (not branch (b)/(c) resolution paths). The wrapper correctly does not set `exit 0` at the end — branches (a)/(b)/(c) all `exec` (replacing the process), branch (d) exits 2.
- **Test coverage**: All spec acceptance criteria (reqs 2–7) have dedicated tests. Contract schema validated separately. `--help` smoke test in both the unit file and the phase1 sibling smoke file. 11/11 tests pass.
- **Pattern consistency**: Follows all existing project conventions: stdlib-only module, `# Contract` docblock, dual-channel four-branch `bin/` wrapper, `cortex-log-invocation` shim guard, `[project.scripts]` entry, justfile recipe, plugin mirror, smoke test inventory entry. The `_EXCLUDED_DIR_PARTS` self-exclusion for `tests/fixtures/cortex-adr-citation-audit/` and `plugins/cortex-core` is correctly encoded even though the fixtures directory does not yet contain any files.

---

## Requirements Drift

**State**: none

**Findings**:
- None

**Update needed**: None

---

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
