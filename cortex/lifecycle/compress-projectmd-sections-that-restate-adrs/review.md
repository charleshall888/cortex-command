# Review: compress-projectmd-sections-that-restate-adrs

Reviewed the real diff `git diff 7e46ee11..HEAD -- cortex/requirements/project.md` hunk by hunk. The four hunks touch exactly the eight verdict ranges and nothing else: Philosophy L25/L27 (s4), Architectural-Constraints L37/L38 (s6), L41/L42 (s7), L44/L45/L46 (s8), L47/L48 (s9), L49/L50 (s10), Quality-Attributes L58 (s11), and Optional L98/L99 (s15). Every mechanical gate (R1–R12) passes; below I also record the clause-level judgment the greps cannot do.

## Stage 1: Spec Compliance

### Requirement 1 (s4): Drop ADR-0004 finalization mechanics; keep philosophy contracts; fix L27 pointer
- **Expected**: Cut Steps 9–11a / "on all completion paths" / verbose `adr/0004-multi-step…` path; keep multi-step-reinvocation contract, `merge_anchor:"merge"`, two-kind pause taxonomy; add `→ ADR-0004` back-pointer (grep =1); fix `skills/lifecycle/SKILL.md` → `references/kept-pauses.md`.
- **Actual**: All three cut tokens =0; `merge_anchor`=1, `two kinds`=1, `ADR-0004`=1 (the introduced back-pointer, lowercase path gone). The two-kind taxonomy bullet is byte-identical to baseline except the corrected pointer — its (a)/(b) enumeration is fully preserved. L27 fixed; stale `skills/lifecycle/SKILL.md`=0. The only content dropped beyond the keep-list is the "aligns with GitHub/Linear/Jira/GitLab conventions" rationale, which is not a named keep and lives in ADR-0004.
- **Verdict**: PASS

### Requirement 2 (s6): historical-shim + wheel-binstub compression (keep-conservative)
- **Expected**: Keep L36 TERMINAL_STATUSES intact; keep shim policy sentence + `metrics.py` pointer; keep FORCE_SOURCE remedy + three binstub facts; cut "replaying or aggregating" and "Dogfooders iterating".
- **Actual**: Both cut tokens =0. `CORTEX_COMMAND_FORCE_SOURCE`=1 — the remedy clause survives in full ("makes the `bin/cortex-*` wrappers skip the wheel-import branch and run the working-tree module directly, regardless of whether a wheel is installed"). The shim-policy sentence survives ("retained as historical-compat shims, not deleted, so archived `pipeline-events.log` data still parses") with the `pipeline/metrics.py` pointer. All three binstub facts (binstub→wheel, `python3 -m`→working-tree, FORCE_SOURCE) intact. TERMINAL_STATUSES L36 byte-unchanged. The weakest-backstopped verdict was handled conservatively.
- **Verdict**: PASS

### Requirement 3 (s7): EnterWorktree / install-state / AUTO_ENSURE collapse
- **Expected**: Keep ADR-0008, parity test, `plugins/cortex-overnight/`, and the "never imports" dependency-direction invariant itself; cut "vendor-style" (and cd-shim). AUTO_ENSURE near-minimal — leave.
- **Actual**: `never imports`=1 — the directional claim "the wheel never imports from `plugins/cortex-overnight/`" survives verbatim as a full clause, not just the path token. `ADR-0008`, `test_install_state_path_parity.py`, `plugins/cortex-overnight/` all present. `cd-shim`=0, `vendor-style`=0. L43 AUTO_ENSURE untouched (not in diff).
- **Verdict**: PASS

### Requirement 4 (s8): lint-bullet compression (grep-c / bare-python / skill-dir)
- **Expected**: Keep both lint bins, both ignore-next sentinels, parity test, ADR-0009, and the L44 backlog-grep-c WHY clause; cut the L46 "resolves only in a SKILL.md body" duplication; no new contract-lint violations.
- **Actual**: All six keep tokens present; `resolves only in a SKILL.md body`=0. The L44 WHY clause survives intact, reworded ("so acceptance criteria can't pass trivially against hallucinated event names"). The dropped skill-dir paragraph is correctly replaced by a pointer to "the CLAUDE.md skill-authoring design principle" (its verbatim home). Both lint bins keep the passing inline-code form; no new bare `cortex-<verb>` mention introduced. `cortex-check-contract --audit` exits 0.
- **Verdict**: PASS

### Requirement 5 (s9): dependency-bounds + L1-ratchet compression
- **Expected**: Collapse starlette example to a pyproject pointer; keep four prose-only policies (ratchet heading token, cluster-exemption, re-cap-with-rationale-and-lifecycle-id, requires-dist-only-governance, promote-transitive-capped); cut "starlette" and "membership encoded once".
- **Actual**: All five keep tokens present; both cut tokens =0. The cluster-exemption + re-cap-with-rationale-plus-lifecycle-id policies (the two CLAUDE.md cites by name) survive as full clauses. The `≤400B` number and the six-member enumeration were dropped per the plan — both live elsewhere (CLAUDE.md L30 owns the ≤400 default; `ROUTING_PRESSURE_CLUSTER` owns membership), and the compressed text still points to "the non-cluster default", so the CLAUDE.md↔project.md cross-reference stays coherent.
- **Verdict**: PASS

### Requirement 6 (s10): supervision + containment compression
- **Expected**: Supervision → one line + ADR-0011; containment → invariant + exemption + test pointer; keep the same-repo-overnight "NOT exempt" clause (its only prose home); cut `_is_worktree_inside_repo` / `startswith` (and orphan-reap narration).
- **Actual**: `ADR-0011`, `test_containment` present; both code-internals cut tokens =0. `NOT exempt`=1 — the counter-intuitive clause survives with its full matrix context ("the same-repo overnight path (`repo_path=None`, `session_id` set) is NOT exempt and is governed by the guard"), which is exactly the clause with no ADR/test backstop.
- **Verdict**: PASS

### Requirement 7 (s11): redaction cue-family trim
- **Expected**: Trim only the cue-family enumeration to a `_redact` pointer; keep the three design-decision clauses (scrubbed-at-source, NOT-complete defense-in-depth, no-prefixless-blob-matcher) + `#309`; cut ASIA/xox.
- **Actual**: All three design clauses present as full sentences with their reasoning intact; `#309`=1; `ASIA`=0, `xox`=0. Only the parenthetical pattern list was removed, replaced by the `pipeline/dispatch.py:_redact` pointer. The five other QA bullets are byte-unchanged (R12).
- **Verdict**: PASS

### Requirement 8 (s15): Optional-section compression
- **Expected**: Compress the two target bullets to name+scope+pointer (SURVIVE, not delete); keep `## Optional` (=1), the convention line, and the Workflow-trimming bullet; cut the `_in_scan_scope` "recursive-glob matcher safe" narration; no new contract-lint violations.
- **Actual**: `Sandbox preflight`=1, `Two-mode gate`=1 (both compressed, not deleted); `## Optional`=1; `Workflow trimming` present and byte-unchanged; `recursive-glob matcher safe`=0 (and `claude --version`=0). The corpus-congruent clause survives on L99. Both bins stay path-qualified (`bin/cortex-check-parity`, `bin/cortex-check-events-registry`) — no new bare verb mention.
- **Verdict**: PASS

### Requirement 9: Contract-lint clean
- **Expected**: `cortex-check-contract` exits 0.
- **Actual**: `--audit` repo-wide exit 0.
- **Verdict**: PASS

### Requirement 10: Structural invariants preserved
- **Expected**: `just test` green (esp. `test_load_requirements_cli.py`, `test_l1_surface_ratchet.py`); 8 H2s; Conditional-Loading/Global-Context unchanged.
- **Actual**: `grep -c '^## '`=8. `test_load_requirements_cli.py` + `test_l1_surface_ratchet.py` + `test_lifecycle_kept_pauses_parity.py` = 43 passed. Conditional-Loading/Global-Context blocks not in the diff.
- **Verdict**: PASS

### Requirement 11: Net reduction achieved
- **Expected**: `wc -l` < 101; ≥800 bytes removed; Optional within ≤1,200-token budget.
- **Actual**: 100 lines; baseline 17,317 → current 13,703 bytes = 3,614 removed. Optional section is three short bullets, well within budget (`test_load_requirements_cli.py` green covers the budget assertion).
- **Verdict**: PASS

### Requirement 12: Diff-scoping guard (master check)
- **Expected**: Changed hunks confined to the eight ranges; every non-target line byte-identical to baseline; bullet-structure invariant (45 `- ` / 29 `- **`).
- **Actual**: `grep -c '^- '`=45, `grep -c '^- \*\*'`=29 (no bullet merged/deleted/added). All 17 lead-in substrings each match exactly one line. The non-target `diff` (`git show 7e46ee11:… | grep -vFf targets` vs current) is **empty** — every line outside an edited bullet, including the interleaved L39 `→ ADR-0002` and L40 bullets and the five QA siblings, is byte-identical to baseline.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: N/A for prose; the `→ ADR-NNNN` back-pointer form follows `cortex/adr/README.md` §No-content-duplication consistently across the introduced s4/s7/s10 pointers.
- **Error handling**: N/A — inert documentation, no runtime surface.
- **Test coverage**: The plan's full verification battery was executed and reproduced independently here: all R1–R8 keep/cut greps, R9 contract-lint exit 0, R10 structural tests (43 passed), R11 byte-reduction (3,614 ≥ 800), and the R12 non-target byte-identity diff (empty). The critical-focus clause-survival check was done by hand-reading each hunk, not by trusting the presence-greps — every "only prose home" clause (s6 shim+FORCE_SOURCE, s7 "never imports", s8 L44 WHY, s9 cluster-exemption+re-cap, s10 "NOT exempt", s11 three redaction clauses, s4 taxonomy+merge_anchor) survives as an intact clause, not a stranded token.
- **Pattern consistency**: Compressions consistently replace restated ADR/CLAUDE.md/test bodies with a named pointer while preserving the no-other-home residue — matches the audit's stated method and the ADR README's duplication policy.

## Requirements Drift
**State**: none
**Findings**:
- None. The edit compresses prose within `cortex/requirements/project.md` itself; it removes no normative requirement and introduces no new behavior. Every dropped clause has a verified other-home (ADR body, CLAUDE.md, test docstring, or enforcement-site doc), and every clause with no other home was preserved. The incidental research.md reword (`ba6817c3`, "consulted by lifecycle/refine/discovery" → "…by the lifecycle, refine, and discovery skills") clears a pre-existing resolver-test false-positive in a lifecycle artifact and is not part of the deliverable — benign, no requirements impact.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
