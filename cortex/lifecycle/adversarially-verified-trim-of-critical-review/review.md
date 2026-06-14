# Review: adversarially-verified-trim-of-critical-review

## Stage 1: Spec Compliance

### Requirement 1: Pin the total-failure literal in BOTH SKILL.md and verification-gates.md
- **Expected**: A test asserts the exact string `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.` appears verbatim in both `skills/critical-review/SKILL.md` and `…/references/verification-gates.md`; removing/paraphrasing from either fails.
- **Actual**: `tests/test_critical_review_reference_pins.py` defines `TOTAL_FAILURE_LITERAL` and three tests (`test_total_failure_literal_in_skill_md`, `…_in_verification_gates`, `…_cross_file_equality`). `grep -Fc` returns 1 in each file. Negative control confirmed: paraphrasing the literal fails the presence + cross-file-equality tests (2 failed), and the file restored cleanly (`git diff --quiet` exits 0).
- **Verdict**: PASS
- **Notes**: The cross-file-equality test asserts both copies match the same canonical constant, transitively pinning byte-equality — a strengthening the plan added per a critical-review finding.

### Requirement 2: Pin the verification-gates.md preserve-set designators + route markers
- **Expected**: Test asserts presence of exit-0/3/4 markers for both `check-artifact-stable` and `check-synth-stable`, the three Step designators (2a.5/2c.5/2d.5), with a docstring stating the token-presence-not-prose limitation.
- **Actual**: `STEP_DESIGNATORS` pins all three exact heading lines; `test_step_designators_present` verifies them. `EXIT_MARKERS` (`- **Exit 0/3/4**`) are checked per-section via `_route_sections()`, which slices at the Step headings so a single-section deletion is localized (not a whole-file count). `test_exit2_stop_dispatch_reaction_present` additionally pins the exit-2 stop-dispatch reaction. The module docstring states the known limitation verbatim in intent.
- **Verdict**: PASS
- **Notes**: Per-section slicing (required, not optional) correctly addresses the "each marker occurs exactly twice file-wide" localization gap. Exit-2 pin exceeds the spec's exit-0/3/4 minimum — a documented hardening.

### Requirement 3: Wire the pin test into the suite, green on the pre-trim tree
- **Expected**: `just test` exits 0 with the new test discovered and passing.
- **Actual**: `uv run pytest tests/test_critical_review_reference_pins.py -q` → 6 passed. The module is discovered by the suite (Phase-1 commit `1bcf2095` landed it before the Phase-2 trim, per git log). `just test` shows the `tests` recipe's only failure is the unrelated pypi DNS flake (see R10).
- **Verdict**: PASS
- **Notes**: Two-commit structure (pin test, then trim) matches the plan's "independently shippable Phase 1, committed before any Phase-2 edit."

### Requirement 4: Run and record an adversarial trim pass over verification-gates.md
- **Expected**: A per-proposal record with section/kind/action/est_savings_bytes/risk/excerpt/verifier_reason/verdict; every proposal carries a verdict + non-empty verifier_reason; the tempfile-guard passage and both exit-4 rationales appear as evaluated proposals (verdict value NOT mandated).
- **Actual**: `trim-map.md` records 8 proposals (P1–P8). Each carries the full schema plus distinct `auditor_reason` AND `verifier_reason` (the structural evidence of two separate passes). The tempfile-guard passage is P1, the two exit-4 rationales are P2 (Step 2c.5) and P3 (Step 2d.5) — all three present as evaluated proposals with concrete refuter anchors. Verdict summary: 0 safe, 6 downgraded, 2 refuted. The P8 refutation premise (`record-exclusion` is a real separately-invokable subcommand) was verified accurate against `cortex_command/critical_review/__init__.py:949` (`add_parser("record-exclusion")`).
- **Verdict**: PASS
- **Notes**: The required mandatory proposals all landed downgraded (P1) / downgraded (P2/P3) — consistent with the research-derived prior, but assigned fresh with concrete anchors, not pre-written.

### Requirement 5: Apply only certified safe + downgraded-per-downgrade proposals
- **Expected**: Refuted proposals NOT applied; tempfile-guard (both named failure modes) and both exit-4 rationales remain present; net byte change ≥ 0 equal to the certified subset; a zero-byte result is valid and the set MUST NOT be padded.
- **Actual**: Only P5 (captured-SHA cross-reference) and P6 (substitution-site enumeration) were applied, both per-downgrade pure-redundancy/narration cuts. `git diff origin/main` confirms exactly these two single-line condensations and nothing else. Byte change: 10565 → 10439 (−126B, net ≥ 0). Preserve-set intact: `grep -Fc 'concurrent runs to corrupt each other'` = 1, `grep -Fc "trip the Write tool's read-before-overwrite guard"` = 1 (both tempfile-guard failure modes), `grep -c 'Exit 4'` = 3 (≥ 2), exit-2 reaction present. The two refuted proposals (P7 last-match split, P8 record-exclusion guard) were correctly NOT applied.
- **Verdict**: PASS
- **Notes**: Honest and spec-compliant. Applying only 2 of 8 proposals (−126B) is the verifier-bounded result, not a padded one — the diff touches zero route-reaction prose and zero pinned tokens. The spec explicitly permits a small/zero applied trim; the implementation did not manufacture cuts to inflate the byte count. The four downgrades that touch behavioral routing prose were correctly deferred ("skipped-with-reason") rather than applied without a behavioral test.

### Requirement 6: Preserve-set survives verbatim; out-of-scope files untouched; pin green post-trim
- **Expected**: (a) E101 contract lint passes (both fenced invocations keep required flags); (b) `a-to-b-downgrade-rubric.md`, `residue-write.md`, `angle-menu.md` show 0 changed lines (canonical + mirror); (c) Phase-1 pin test exits 0 post-trim.
- **Actual**: (a) `cortex-check-contract --audit` returns no violations; the fenced invocations retain all flags — `check-artifact-stable` has 5 (`--feature --reviewer-angle --expected-sha --model-tier --input-file`), `check-synth-stable` has 2 (`--feature --expected-sha`). (b) `git diff --numstat origin/main` shows empty (0 changed lines) for all three out-of-scope files, canonical and mirror. (c) `uv run pytest tests/test_critical_review_reference_pins.py -q` → 6 passed post-trim.
- **Verdict**: PASS

### Requirement 7: Commit canonical + regenerated mirror together; dual-source parity green
- **Expected**: Mirror staged alongside canonical; `test_dual_source_reference_parity.py` exits 0; drift hook passes.
- **Actual**: `diff -q` confirms canonical and mirror `verification-gates.md` are byte-identical. `uv run pytest tests/test_dual_source_reference_parity.py -q` → 58 passed. The Phase-2 commit `0a0e6be7` landed canonical + mirror together (commit succeeded, so the pre-commit drift hook passed).
- **Verdict**: PASS

### Requirement 8: No route-table↔Python drift (one-time hand-diff)
- **Expected**: An `implementation-notes.md` entry records the hand-diff; exit 3/4 prose still matches Python emitter behavior. This is a one-time author check, not a re-runnable gate.
- **Actual**: `implementation-notes.md` records a dated (2026-06-13) hand-diff covering all four codes (exit 0/2/3/4), each with a quoted Python-side line and a quoted markdown-side line plus a per-code "match" verdict. Verified against source: exit 2 = `return 2` on path-validation failure (`__init__.py:646/657/660/671`); exit 3 = `return 3` after event append (`:727/:801`); exit 4 = `EXIT_TELEMETRY_SKIPPED = 4` (`:52`) on absent lifecycle dir (`:722/:793`). The note correctly states P5/P6 condensed no route-reaction prose, so the hand-diff is the widened correctness check rather than a diff of changed prose.
- **Verdict**: PASS
- **Notes**: Scope widened to exit 0/2/3/4 (vs the spec's 3/4 floor) per a critical-review finding catching the exit-2 stop-dispatch path. Both-sides quoted evidence is present, exceeding a filename-mention floor.

### Requirement 9: No new MUST escalations; frontmatter byte-count unchanged
- **Expected**: `test_l1_surface_ratchet.py` exits 0 (frontmatter stays 795B); no new MUST/CRITICAL/REQUIRED token in the diff.
- **Actual**: `uv run pytest tests/test_l1_surface_ratchet.py -q` → 18 passed. `git diff origin/main -- …/verification-gates.md | grep '^\+' | grep -E 'MUST|CRITICAL|REQUIRED'` returns no added-line matches. The trim touches reference bodies only; frontmatter is untouched.
- **Verdict**: PASS

### Requirement 10: Full suite green
- **Expected**: `just test` exits 0 on the final tree.
- **Actual**: `just test` shows 6/7 recipes pass; the sole failure is `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`, whose stderr is `Failed to fetch: https://pypi.org/simple/packaging/ … dns error … failed to lookup address information`. This is the documented pre-existing pypi sandbox-network flake, unrelated to this feature, and the review instructions direct not to count it against R10.
- **Verdict**: PASS
- **Notes**: All feature-relevant tests (pin, parity, ratchet, contract) are green. The single failure is environmental (sandbox DNS block), not a regression from this change.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the repo. The new module mirrors the precedent `tests/test_skill_section_citations.py`: same `REPO_ROOT = Path(__file__).resolve().parent.parent` idiom, module-level constant tuples (`STEP_DESIGNATORS`, `EXIT_MARKERS`), `_read`/`_route_sections` helpers, descriptive `test_*` function names. Each assertion carries a maintainer-facing message naming the citing site (SKILL.md:48/:64/:72/:86) — matching the precedent's "identify the citing site" convention.
- **Error handling**: Assertion messages are actionable, telling a future editor exactly what to restore and which callers depend on the pinned string. `_route_sections` handles the EOF-fallback case (`## Partial Coverage` absent → slice to `len(text)`) defensively. No bare excepts; uses `text.index` with explicit start offsets for ordered slicing.
- **Test coverage**: The plan's verification steps were executed and reproduced here — pin test green pre- and post-trim, negative-control (scratch-delete → 2 failures → clean revert), dual-source parity (58 passed), L1 ratchet (18 passed), E101 audit clean, byte accounting (10565→10439). The trim-map's verifier-independence is a process property (two distinct dispatches with distinct auditor/verifier attributions) that a string check cannot prove — appropriately reported as session-dependent rather than over-claimed.
- **Pattern consistency**: Strong. The implementation deliberately built a sibling module rather than extending `test_skill_section_citations.py`, because that module's `_read_headings()` collects only `#`-prefixed lines into a set and cannot pin body content or list-item route markers — a correct, documented choice. The per-section slicing is a genuine improvement in localization over the precedent's whole-file heading-set approach.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
