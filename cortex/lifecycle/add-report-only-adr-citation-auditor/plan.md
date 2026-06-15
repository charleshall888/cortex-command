# Plan: add-report-only-adr-citation-auditor

## Overview
Ship a report-only ADR citation auditor as a `cortex_command/` console-script module (`adr_citation_audit.py`) with a thin dual-channel `bin/` wrapper, modeled structurally on `cortex-check-parity` → `cortex_command/parity_check.py` and behaviorally (exit-0, JSON-to-stdout, `# Contract` docblock, log-invocation shim in the wrapper) on `bin/cortex-requirements-parity-audit`. The module is a four-stage pipeline — load ADR corpus → scan/extract reference tokens → resolve+classify → emit a single JSON report — followed by integration wiring (`[project.scripts]`, justfile recipe, plugin mirror, smoke-test inventory) and the `cortex/adr/README.md:45` area-tagging reword.
**Architectural Pattern**: pipeline

## Outline

### Phase 1: Auditor core (tasks: 1, 2)
**Goal**: A working `cortex_command.adr_citation_audit` module — token grammar, corpus resolution, duplicate/gap detection, missing-corpus handling, `kind`-taxonomy JSON output, exit-0-always — plus its hermetic test suite covering requirements 2–7.
**Checkpoint**: `python3 -m pytest tests/test_adr_citation_audit.py -q` is green; `python3 -m cortex_command.adr_citation_audit --help` exits 0.

### Phase 2: Integration & fold-in (tasks: 3, 4, 5)
**Goal**: The module reaches consumers as a console-script and is dogfooded — `[project.scripts]` entry, dual-channel `bin/` wrapper, justfile recipe (W003 wiring), plugin-bin mirror, `--help` smoke-test inventory entry — and the README:45 broken-backfill promise is reworded.
**Checkpoint**: `just test` passes (new test + smoke inventory + mirror parity); `bin/cortex-check-parity` reports no W003 orphan for the new wrapper; README:45 grep gates pass.

## Tasks

### Task 1: Implement the auditor module `cortex_command/adr_citation_audit.py`
- **Files**: `cortex_command/adr_citation_audit.py`
- **What**: Create the report-only auditor module — token grammar, ADR-corpus index, reference resolution + classification, duplicate-number and gap detection, missing-corpus handling, a single JSON object on stdout, and exit 0 on every path. Satisfies spec requirements 2–8 and the module half of requirement 1.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Model the module layout on `cortex_command/parity_check.py` (`build_parser()`, `main(argv: list[str] | None = None) -> int`, `if __name__ == "__main__": sys.exit(main())`). Do NOT put the `cortex-log-invocation` shim in the module — it lives in the bash wrapper (Task 3), matching `bin/cortex-check-parity`.
  - Header discipline (from `bin/cortex-requirements-parity-audit`): `from __future__ import annotations`, stdlib-only, a `# Contract` docblock below the imports enumerating the four `kind` values (`unresolved`, `slug_mismatch`, `duplicate_number`, `gap`), the top-level `corpus_present` boolean, the JSON-on-stdout shape, and the load-bearing "exit code is 0 regardless" statement (spec req 8).
  - Argparse: `--root <dir>` (default `None` → cwd); `--help` exits 0. No `--proposals`, no `--adr-dir` (both Non-Requirements).
  - Corpus loader signature `load_corpus(adr_dir: Path) -> tuple[dict[int, list[str]], bool]`: scan `<root>/cortex/adr/` for files matching `^[0-9]{4}-[a-z0-9-]+\.md$` (`README.md` excluded), build a number→filenames index, and return `corpus_present` = (dir exists AND ≥1 conforming file). Gap/duplicate detectors ride this index. Gap detector keys on file *presence* over `1..max(filed)`, NOT on `status:` — a superseded-but-present ADR is not a gap (spec req 7, Edge Cases).
  - Scanner signature `iter_scan_files(root: Path) -> Iterator[Path]`: walk `<root>` for source text files (extension set `.md` + `.py` — where references demonstrably appear per research), excluding `.git/`, `tests/fixtures/cortex-adr-citation-audit/`, and the generated mirror tree `plugins/cortex-core/**` (Adversarial #1–#3 mitigations; spec Technical Constraints scan-scope line).
  - Token grammar — compile these module-level regexes verbatim from the spec (config values, not implementation): prefix/space/bracketed `(?<![0-9A-Za-z])\[?ADR[- ](?P<num>[0-9]{4})\]?(?![0-9A-Za-z])`; path `(?<![0-9A-Za-z])adr/(?P<num>[0-9]{4})(?:-(?P<slug>[a-z0-9-]+?))?(?=\.md|[^a-z0-9-]|$)`. The exactly-four-digit discriminator is what excludes the document-local `ADR-1/2/3` proposal labels and `ADR-000N`/`NNNN-` placeholders without any directory carve-out (spec req 3).
  - Resolution + classification: slug-less forms resolve by numeric prefix; path-with-slug resolves by exact `NNNN-slug` filename match. Emit `kind: "unresolved"` for a number absent from the index, `kind: "slug_mismatch"` for a path form whose number is filed under a different slug (spec req 2).
  - Output: `print(json.dumps(report, ...))` then `return 0` — every path returns 0 (spec req 8; the load-bearing report-only property).
- **Verification**: (a) `python3 -c "import cortex_command.adr_citation_audit"` exits 0; (b) `python3 -m cortex_command.adr_citation_audit --help` exits 0; (c) **behavioral end-to-end smoke** — build a throwaway tmp tree with `cortex/adr/0001-foo.md` plus a doc citing both `ADR-0001` and `ADR-9999`, run `python3 -m cortex_command.adr_citation_audit --root <tmp>`, and assert: exit 0 AND stdout parses as JSON AND top-level `corpus_present` is `true` AND a finding with `kind: "unresolved"` exists for `ADR-9999` AND no finding exists for `ADR-0001`; (d) `grep -c '# Contract' cortex_command/adr_citation_audit.py` ≥ 1. Check (c) drives the resolve→classify→emit pipeline once end-to-end so the task's "done" state reflects working behavior — not merely a parseable module whose docblock happens to contain the four `kind` strings. Exhaustive per-requirement coverage (reqs 2–7, all four `kind` values, gap/duplicate/missing-corpus paths) remains Task 2.
- **Status**: [ ] pending

### Task 2: Hermetic test suite `tests/test_adr_citation_audit.py`
- **Files**: `tests/test_adr_citation_audit.py`
- **What**: Exercise spec requirements 2–7 plus the `--help`-exits-0 and JSON-contract checks via subprocess against synthetic `--root <tmp tree>` fixtures, modeled on `tests/test_requirements_parity_audit.py`. Satisfies spec requirement 9.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Model on `tests/test_requirements_parity_audit.py`: `REPO_ROOT = Path(__file__).resolve().parent.parent`; build synthetic `--root` trees under `tmp_path`; invoke the auditor via subprocess. Per spec Technical Constraints (line 69), invoke the working tree as `[sys.executable, "-m", "cortex_command.adr_citation_audit", "--root", str(tree)]` (NOT the `bin/` wrapper path the model test uses, because our auditor is a module behind a wrapper).
  - Required test cases, each asserting exit 0:
    - req 2: `cortex/adr/0001-foo.md` filed; doc cites `ADR-0001` (no finding), `ADR-9999` (`kind: "unresolved"`), `adr/0001-wrong-slug` (`kind: "slug_mismatch"`).
    - req 3: doc with `ADR-2`, `ADR-000N`, `NNNN-slug` → zero findings for those tokens.
    - req 4: synthetic cortex-convention tree (no `plugins/`, no cortex-command layout) with `cortex/adr/0001-foo.md`, doc citing `ADR-0001`+`ADR-0002` → `ADR-0002` `unresolved`, `ADR-0001` not reported.
    - req 5: tree with ADR references but no `cortex/adr/` dir → top-level `corpus_present == false` and references reported `unresolved`.
    - req 6: `cortex/adr/0001-a.md` + `cortex/adr/0001-b.md` → `kind: "duplicate_number"` naming both files.
    - req 7: `0001`,`0002`,`0004` filed (`0003` absent) → `kind: "gap"` for `0003`; a tree where `0002` is present with `status: superseded` → no gap finding for `0002`.
    - contract: parse stdout as JSON (`json.loads`); assert top-level `corpus_present` present and every finding carries a `kind` in the four-value set.
    - help: `[..., "--help"]` exits 0.
  - Any persistent fixture files belong under `tests/fixtures/cortex-adr-citation-audit/` (the path Task 1's scanner excludes); per-test `tmp_path` trees are preferred for hermeticity per the model.
- **Verification**: `python3 -m pytest tests/test_adr_citation_audit.py -q` — pass if exit 0 and all tests pass.
- **Status**: [ ] pending

### Task 3: Console-script wiring — `[project.scripts]`, `bin/` wrapper, justfile recipe, plugin mirror
- **Files**: `pyproject.toml`, `bin/cortex-adr-citation-audit`, `justfile`, `plugins/cortex-core/bin/cortex-adr-citation-audit`
- **What**: Register the console-script, create the dual-channel bash wrapper, wire the justfile recipe (the W003 parity signal), and regenerate + commit the plugin-bin mirror alongside the canonical. Satisfies the wrapper half of spec req 1 and spec req 10.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - `pyproject.toml`: add `cortex-adr-citation-audit = "cortex_command.adr_citation_audit:main"` to the `[project.scripts]` table (alongside `cortex-check-parity = "cortex_command.parity_check:main"`). The editable install already points at the working tree, so `python3 -m cortex_command.adr_citation_audit` resolves without reinstall; the PATH binstub `cortex-adr-citation-audit` materializes on the next `uv tool install`/editable reinstall (needed only for manual/dogfood PATH use, not for `just test`).
  - `bin/cortex-adr-citation-audit`: copy `bin/cortex-check-parity` verbatim and substitute the module name `cortex_command.parity_check` → `cortex_command.adr_citation_audit`. Preserve the four-branch dual-channel order (FORCE_SOURCE → wheel-import probe → working-tree PYTHONPATH → exit 2) and the `cortex-log-invocation` shim block verbatim. `chmod +x` the wrapper. In branch (d), rewrite the remediation string to name `cortex-adr-citation-audit` while keeping the `uv tool install … @<latest-tag>` URL/tag correct. **Exit-0 scope clarification**: branch (d)'s `exit 2` is an *installation-resolution* error (neither a wheel nor a working-tree module could be located — the auditor never ran), categorically distinct from and exempt from the spec's report-only "exit 0 on every path" discipline, which governs every path where the auditor *executes*. Do NOT change branch (d) to exit 0 — a tool-not-found error correctly signals non-zero. The exit-0 contract is a property of the module (Task 1), verified there via the behavioral smoke.
  - `justfile`: add a recipe beside `requirements-parity-audit:` (justfile:416) whose body is the single line `bin/cortex-adr-citation-audit`. The recipe body containing `bin/cortex-adr-citation-audit` is the W003 wiring signal — wire it, do not allowlist (allowlisting a wired script triggers W005, per research).
  - Plugin mirror: run `just build-plugin` to regenerate `plugins/cortex-core/bin/cortex-adr-citation-audit` (rsync, byte-identical). Per the drift-hook/shared-checkout coupling constraint, regenerate and stage the mirror WITH this task's canonical edit — do not defer mirror regen to a later task. No `bin/.events-registry.md` entry (the auditor emits no event; spec line 68).
- **Verification**: (a) `bin/cortex-adr-citation-audit --help` exits 0; (b) `grep -c 'cortex-adr-citation-audit' pyproject.toml` ≥ 1 AND `grep -c 'adr-citation-audit' justfile` ≥ 1; (c) `diff bin/cortex-adr-citation-audit plugins/cortex-core/bin/cortex-adr-citation-audit` exits 0 (byte parity); (d) `bin/cortex-check-parity` exits 0 with no W003 orphan naming `cortex-adr-citation-audit`; (e) `python3 -m pytest tests/test_plugin_mirror_parity.py -q` passes.
- **Status**: [ ] pending

### Task 4: Add the auditor to the `--help` smoke-test inventory
- **Files**: `tests/test_phase1_sibling_rewrite_smoke.py`
- **What**: Add a smoke-test function asserting `bin/cortex-adr-citation-audit --help` exits 0 with no `cortex-log-invocation failed:` warning, and add the script to the docstring "Covered scripts" inventory (around line 45). Satisfies the smoke-inventory clause of spec req 10.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Model the new test on `test_requirements_parity_audit` (the function near line 257): resolve `script = BIN_DIR / "cortex-adr-citation-audit"`, run `--help` under the isolated-PATH helper, call `_assert_no_log_invocation_warning(...)`, and assert exit 0. The wrapper dispatches to the module via its branch (b) wheel-import probe, so the module (Task 1) must exist — hence the dependency on Task 3 (which depends on Task 1).
  - Add `cortex-adr-citation-audit` to the docstring inventory block near line 45 so the covered-scripts list stays accurate.
- **Verification**: `python3 -m pytest tests/test_phase1_sibling_rewrite_smoke.py -q` — pass if exit 0 and all tests (including the new one) pass.
- **Status**: [ ] pending

### Task 5: Reword the `cortex/adr/README.md:45` area-tagging note
- **Files**: `cortex/adr/README.md`
- **What**: Replace the area-tagging note's broken "deferred to a backfill ticket" promise (the backfill was deliberately not filed per epic 303; `area:` has no consumer) while keeping the still-live "do not invent one ad hoc" guardrail. Satisfies spec req 11.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current text (README:45): *"No `area:` field is defined at v1. Area tagging is intentionally deferred to a backfill ticket; do not invent one ad hoc."*
  - Reword to drop the backfill-ticket promise and keep the guardrail, e.g.: *"No `area:` field is defined. Area tagging was considered and deliberately not adopted (no consumer); do not invent one ad hoc."* (the operator-approved narrowing of the ticket's literal "delete the note" wording, per spec req 11).
- **Verification**: `grep -c 'backfill ticket' cortex/adr/README.md` = 0 AND `grep -c 'do not invent' cortex/adr/README.md` ≥ 1 — pass if both hold.
- **Status**: [ ] pending

## Risks
- **Dogfood run surfaces self-referential example-token findings (bounded, ~22% real signal).** A measured in-repo run produces ~18 findings, of which ~14 are this lifecycle's OWN illustrative tokens in `plan.md`/`spec.md`/`research.md` (`ADR-9999`, `adr/0001-wrong-slug`, `adr/0001-foo|a|b`); the remaining ~4 are stray `docs/adr/0001-*` path tokens elsewhere in the repo. The README is **not** a noise source — its `ADR-0001`/`ADR-0002` refs resolve cleanly to the real corpus (zero findings). The tool is report-only (exit 0) and no test/gate asserts a zero-finding dogfood run — consistent with the spec's tolerance for minor false positives (Edge Cases line 53). The spec's scan-scope exclusion set is kept as-specified (`.git/`, `tests/fixtures/cortex-adr-citation-audit/`, `plugins/cortex-core/**`); **excluding all of `cortex/lifecycle/**` is deliberately rejected** — it would stop checking legitimate ADR citations in real specs, defeating the auditor's purpose. Called out so the self-referential findings are not mistaken for a defect.
- **Gap detection is the more speculative of the two numbering checks.** The documented Wild Light incident exhibited dangling references and a duplicate number — *not* a numbering gap; the contiguous `0001`–`0010` corpus has no gap today. Gap detection (req 7) is kept per the spec §4 value-gate decision (its marginal cost rides the number→files index that duplicate detection already requires), but it is predictive rather than incident-grounded — unlike duplicate detection, which traces directly to the incident. Surfaced here for visibility at plan approval: cutting gap detection is a spec-scope change (re-open the spec), not a plan edit.
- **Implement-phase dispatch must be sequential, not worktree.** This edits the `cortex_command/` package and `just test` runs the editable install pointed at the working tree; a worktree builder would verify against stale code, and the editable-`.pth` rewrite hazard applies. Use sequential dispatch in Implement.
- **Drift-hook / shared-checkout coupling.** Task 3 must regenerate (`just build-plugin`) and stage the plugin mirror together with the canonical `bin/` wrapper in one commit; deferring the mirror to a final task trips the pre-commit drift hook.
- **`[project.scripts]` PATH binstub vs working tree.** Tests rely on `python3 -m ...` and the wrapper's import probe, both of which resolve from the working tree without a reinstall; the on-PATH `cortex-adr-citation-audit` binstub only appears after an editable/`uv tool` reinstall, which is a manual-use convenience, not a test prerequisite.

## Acceptance
Running the auditor (`just adr-citation-audit`, `bin/cortex-adr-citation-audit`, or `python3 -m cortex_command.adr_citation_audit`) against a cortex-convention repo emits a single exit-0 JSON object on stdout carrying top-level `corpus_present` and findings each keyed by `kind ∈ {unresolved, slug_mismatch, duplicate_number, gap}` — never failing a gate. `just test` passes including `tests/test_adr_citation_audit.py` (reqs 2–7), the smoke-inventory entry, and `tests/test_plugin_mirror_parity.py`; `bin/cortex-check-parity` reports no W003 orphan for the new wrapper; and `cortex/adr/README.md:45` no longer promises a backfill ticket while retaining the "do not invent one ad hoc" guardrail.
