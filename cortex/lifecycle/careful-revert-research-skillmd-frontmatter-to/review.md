# Review: careful-revert-research-skillmd-frontmatter-to

## Stage 1: Spec Compliance

### Requirement 1: Revert research's `description` to the #191 close-state with the agent count corrected (`3–5`→`3–10`), deterministically derived, removing the +124B elaborated-mechanism regrowth while preserving the trigger and disambiguation phrases.
- **Expected**: `bin/cortex-measure-l1-surface` reports `research 379`; the reverted description is byte-equal to `git show 500e8464:skills/research/SKILL.md`'s description block with `3–5`→`3–10` applied; the three test-enforced triggers (`/cortex-core:research`, `research this topic`, `investigate this feature`) and the preserved phrases (`gather research for`, the refine-delegation phrase, `research.md or conversation output`) all present; the elaborated mechanism clause removed; deterministic construction (no hand-author).
- **Actual**: `bin/cortex-measure-l1-surface` prints `research 379`. Diffing the #191 close-state description block with `3–5`→`3–10` applied against the current canonical description block is empty (byte-equal). All three test-enforced triggers and all three preserved-by-construction phrases are present. The `tier×criticality` matrix clause and the `always-last adversarial pass for high/critical` clause are both removed from the description. The landing commit `6f683afb` shows exactly the 5-line folded-scalar swap (the multi-line elaborated form → the compact `3–10 ... (codebase, web, constraints, tradeoffs, adversarial)` form), with zero body-marker lines changed.
- **Verdict**: PASS
- **Notes**: The byte-equal `diff` is empty, confirming the deterministic git-derived construction — no hand-author drift. The folded-scalar edge case (trailing-newline clip) is handled by gating on the tool, exactly per spec R1/Edge Cases.

### Requirement 2: Both routing guard tests pass with the reverted description.
- **Expected**: `pytest tests/test_skill_descriptions.py tests/test_skill_routing_disambiguation.py -q` exits 0.
- **Actual**: `.venv/bin/pytest tests/test_skill_descriptions.py tests/test_skill_routing_disambiguation.py -q` → `24 passed`, exit 0.
- **Verdict**: PASS
- **Notes**: research has no `when_to_use`, so the routing surface equals the `description`; the three trigger phrases survive the revert and both guard tests are green.

### Requirement 3: Regenerate the cortex-core plugin mirror and stage it together with the canonical edit.
- **Expected**: both `skills/research/SKILL.md` and `plugins/cortex-core/skills/research/SKILL.md` appear in commit `6f683afb`; mirror frontmatter byte-equal to canonical.
- **Actual**: `git show 6f683afb --name-only` lists exactly both files. The canonical and mirror frontmatter blocks are byte-equal; the full files are in fact identical (research has no canonical/mirror divergence). Canonical + mirror co-committed, satisfying the fail-closed drift hook (the commit landed cleanly).
- **Verdict**: PASS
- **Notes**: The mirror-staging stall hazard (Edge Cases) was avoided — both staged in the same commit.

### Requirement 4: Lower the `research` and `total` ratchet budgets to the tool-measured values.
- **Expected**: `grep -c '"research": 379'` = 1 AND `grep -c '"total": 7197'` = 1; `total − research == 6818` invariant holds; `pytest tests/test_l1_surface_ratchet.py -q` exits 0.
- **Actual**: `grep -c '"research": 379'` = 1; `grep -c '"total": 7197'` = 1; `7197 − 379 == 6818` (invariant holds). `.venv/bin/pytest tests/test_l1_surface_ratchet.py -q` → `20 passed`, exit 0. The `total` row was lowered (not left stale-high), closing the "forgotten total passes green" drift channel called out in Edge Cases.
- **Verdict**: PASS
- **Notes**: Values match the tool output verbatim (`research 379`, `total 7197` from a fresh `cortex-measure-l1-surface` run) — budget == measured, no headroom, consistent with the #298 anti-drift pattern.

### Requirement 5: Update the ratchet docstring to reflect the landed revert.
- **Expected**: `grep -c 'until the follow-on revert (ticket 302) lands'` = 0 AND `sed -n '1,50p' ... | grep -c '379'` ≥ 1 (docstring region references the new value).
- **Actual**: `grep -c 'until the follow-on revert (ticket 302) lands'` = 0; `sed -n '1,50p' | grep -c '379'` = 1. The provenance block (lines 22–27) now reads "Ticket 302 has since reverted that regrowth: `research` is now at its post-revert cluster budget of 379 (the #191 close-state, plus 1B for the corrected 3-10 agent count)."
- **Verdict**: PASS
- **Notes**: The `379` hit is in the header/docstring region above `_BASELINES`, not a side-effect of the R4 dict edit (the dict starts at line ~53).

### Requirement 6: The pre-commit gate set and full suite pass for the edited files.
- **Expected**: the landing commits' pre-commit hook exits 0; `just test` exits 0.
- **Actual**: Both `6f683afb` and `baae2043` landed as real commits on `main` (pre-commit gates passed at commit time — parity, contract, events-registry, prescriptive-prose no-op, bare-python-lint, skill-path). `just test` reports 6/7 suites passing; the single failure is `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`. Running that test in isolation confirms the failure cause is a DNS error — `uv run --script` cannot reach `pypi.org` (`failed to lookup address information`) in the network-restricted sandbox; it never reaches the `'plugin path mismatch' in stderr` assertion. 1888 tests pass, 1 environmental failure, 27 skipped.
- **Verdict**: PASS
- **Notes**: Independently verified the spec's note: the failing test is exactly the one named, the failure is an environmental/sandbox DNS artifact, and the change (research frontmatter + ratchet budgets) has zero relationship to MCP subprocess plugin-path resolution. Not a regression of this implementation; it would pass with network access.

### Non-Requirements verification
- **Body untouched**: `6f683afb` changes only the description folded-scalar (5 ± lines, 0 body-marker lines). research's SKILL.md body is byte-disjoint from this change (that was #299's territory). PASS.
- **No other budget row moved**: `baae2043`'s `_BASELINES` diff shows only `research` 502→379 and `total` 7320→7197; no other skill row touched. PASS.
- **No over-trim toward the rejected ~200B / Option-C ~265B form**: lands at exactly 379B (Option B), the #191 close-state + 1B; the light one-line mechanism summary and the disambiguation tail are preserved. PASS.
- **No new MUST/CRITICAL/REQUIRED language**: escalation-token count in the description is 0; the removed "always-last … for high/critical" was mechanism, not escalation. PASS.

## Stage 2: Code Quality
- **Naming conventions**: Consistent. `_BASELINES` keys remain skill-name-keyed; the `total` synthetic row is preserved. No new identifiers introduced. The two commit subjects follow the imperative, capitalized, ≤72-char convention.
- **Error handling**: Not applicable to this change in the runtime sense — it is frontmatter + test-budget data. The ratchet test's `actual <= baseline` direction check plus the R4 literal-value grep together pin budget==measured (the one-sided assertion alone cannot catch a too-high budget; the grep closes that gap, exactly as the spec notes).
- **Test coverage**: The plan's verification steps were executed and pass: tool measurement (379), byte-equal deterministic-construction diff (empty), routing guards (24 passed), ratchet (20 passed), the grep/invariant gates, and the full suite (1888 passed bar the documented network artifact). research's cluster membership in `ROUTING_PRESSURE_CLUSTER` was confirmed, legitimizing its exemption from the ≤400 default (and 379 is in fact below 400 regardless).
- **Pattern consistency**: Follows the #298 budget==measured anti-drift pattern (no headroom — the headroom is precisely what permitted the 378→502 drift) and the cluster-exemption rule (research is an allowlisted cluster member; lowering a cluster budget needs no re-cap rationale per project.md). The docstring provenance update keeps the test self-documenting in the established style.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
