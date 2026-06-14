# Review: l1-frontmatter-cap-policy-for-new

## Stage 1: Spec Compliance

### Requirement 1: Reframe the ratchet to deliberate budgets and add the completeness assertion (Must)
- **Expected**: `_BASELINES` recommented as deliberate per-skill byte budgets (comparison mechanics unchanged); a completeness assertion that every skill under `skills/` has a budget row, asserted against the canonical skill enumerator; `grep -ci "deliberate budget"` ≥ 1; a row-less skill must raise.
- **Actual**: `tests/test_l1_surface_ratchet.py` recomments `_BASELINES` as "Deliberate per-skill byte budgets (the 298 cap policy) — NOT a frozen snapshot" (module docstring + inline comment; `grep -ci "deliberate budget"` = 4). `test_budget_rows_complete` asserts set-equality between `_BASELINES` (minus `total`) and the measure-utility's rows, then cross-checks that the conftest `enumerate_canonical_skills()` walk equals the utility's rows. A new skill present under `skills/` but absent from the budget dict appears in the utility rows and fails the set-equality `measured == budgeted` assertion; a stale row fails the reverse direction. The canonical-enumerator cross-check guards against a directory-walk divergence (e.g. a dangling SKILL.md symlink). All 55 tests pass.
- **Verdict**: PASS
- **Notes**: The implementation enforces row-completeness via set-equality against the measure-utility rows PLUS a cross-check tying `enumerate_canonical_skills` to those same rows. This satisfies the spec's "row-completeness against the canonical skill enumerator": the canonical enumerator is asserted equal to the measured set, and the measured set is asserted equal to the budget set, so by transitivity a skill in the canonical enumeration without a budget row fails. The two-hop form is stronger than a single direct check (it also catches enumerator/utility divergence).

### Requirement 2: Write the cap policy in `cortex/requirements/project.md` (Must)
- **Expected**: Rewrite the "SKILL.md L1 surface ratchet" constraint in place stating (a) deliberate budgets not a snapshot; (b) ≤400B non-cluster default structurally enforced; (c) the named six-skill routing-pressure cluster as the single exemption surface (promotion by reviewed edit, not self-granted); (d) raising any budget row requires a lifecycle-id + rationale. `grep -c "400"` ≥ 1; names 298.
- **Actual**: `project.md:48` is fully rewritten. (a) "deliberate per-skill byte budget … the cap policy from lifecycle 298, no longer the frozen `evidence.json` snapshot." (b) "default budget for non-cluster skills is ≤400B, structurally enforced by the test's non-cluster-≤400 assertion" (`grep -c "400"` = 1). (c) names "`dev`, `lifecycle`, `refine`, `research`, `discovery`, `critical-review`" as "the single exemption surface … promoted into the cluster by a reviewed edit to that allowlist, not a self-granted per-skill pass," with membership "encoded once in `tests/test_skill_routing_disambiguation.py`'s `ROUTING_PRESSURE_CLUSTER` and imported by the ratchet." (d) "Raising any budget row … requires a documented rationale plus a lifecycle-id (the re-cap-with-rationale rule)." Names 298 (`grep -c "298"` = 1, in-constraint backlog link).
- **Verdict**: PASS
- **Notes**: All four sub-points present and the lifecycle-id requirement for raises is explicit.

### Requirement 3: Point new-skill authors at the budget in `CLAUDE.md` (Should)
- **Expected**: One line in the skill-authoring guidance stating the new-skill desc+wtu SUM is bounded by the L1 budget (default ≤400B non-cluster; cross-refs project.md and the ratchet test). `grep -ci "L1 budget\|400B\|l1 surface"` ≥ 1 within the skill-authoring section.
- **Actual**: `CLAUDE.md:44`, immediately after the existing "New skills go in `skills/`…" convention line, adds: "A new skill's `description` + `when_to_use` SUM is bounded by the L1 surface budget — default ≤400B for non-cluster skills, enforced by `tests/test_l1_surface_ratchet.py`; see the 'SKILL.md L1 surface ratchet' constraint in `cortex/requirements/project.md` for the cluster exemption and re-cap rule." `grep -ci` = 1.
- **Verdict**: PASS
- **Notes**: Placed within the Conventions/skill-authoring block, cross-references both the test and project.md.

### Requirement 4: Fix the misdirected ticket-295 references (Should)
- **Expected**: All three `295-automate` references in the ratchet (docstring, `_BASELINES` comment, assertion message) repointed to 298; 298 named in project.md. `grep -c "295-automate"` = 0; `grep -c "298-l1-frontmatter"` ≥ 1; `grep -c "298"` in project.md ≥ 1.
- **Actual**: `grep -c "295-automate"` = 0; `grep -c "298-l1-frontmatter"` = 3 (docstring, `_BASELINES` comment, and the `test_l1_surface_within_baseline` assertion message); `grep -c "298"` in project.md = 1 (in-constraint link).
- **Verdict**: PASS

### Requirement 5: Correct the regrowth provenance (Should)
- **Expected**: A one-line corrective note recording that `research` is itself post-#191 regrowth (+124B: 378→502), in the policy text or ratchet provenance comment; `research.md` already documents the finding.
- **Actual**: The ratchet module docstring (lines 22–26) carries a "Provenance correction (298)" block: "`research` is itself post-#191 regrowth — its L1 surface grew +124B (378 -> 502) after the harness-token-efficiency-trim snapshot … `research` stays at its deliberate cluster budget of 502 until the follow-on revert (ticket 302) lands." `grep` for "124B" / "378 -> 502" = 1.
- **Verdict**: PASS
- **Notes**: Note correctly ties the 502 budget hold to follow-on ticket 302 (the split research-frontmatter revert), consistent with the Non-Requirements.

### Requirement 6: Land trigger-phrase fixtures for the four uncapped skills (Must)
- **Expected**: `skills:` entries for interview, requirements-write, requirements-gather, backlog-author, each with ≥3 `must_contain` phrases present in the current (trimmed) `description`; for each collision pair (requirements-gather↔requirements-write, interview↔backlog-author) ≥1 phrase verifiably absent from the sibling's description. `test_skill_descriptions.py` green.
- **Actual**: All four entries present in `tests/fixtures/skill_trigger_phrases.yaml`. Phrase counts: interview 4, backlog-author 4, requirements-gather 3, requirements-write 3. Verified against the TRIMMED descriptions (Task 5/08f3f21a already landed): every phrase is a present substring of its skill's current `description`. Collision-pair disambiguation (against trimmed siblings): requirements-gather has 3 phrases absent from requirements-write (e.g. "Interview-only sub-skill"); requirements-write has 3 absent from requirements-gather (e.g. "Synthesize-only sub-skill"); interview has 4 absent from backlog-author (e.g. "thinking-partner interview"); backlog-author has 4 absent from interview (e.g. "Why/Role/Integration/Edges/Touch-points template"). Each collision-pair skill clears the ≥1-disambiguator bar comfortably. `test_skill_descriptions.py` passes.
- **Verdict**: PASS

### Requirement 7: Trim the four uncapped skills to ≤400B SUM and enable the default assertion (Must)
- **Expected**: Each of interview / requirements-write / requirements-gather / backlog-author trimmed so desc+wtu SUM ≤ 400B (keeping Phase-1 fixture phrases); the four `_BASELINES` rows updated to the measured values; the non-cluster-≤400 assertion present and live; canonical+mirror byte-identical (mirror parity passes).
- **Actual**: `bin/cortex-measure-l1-surface` reports interview 361, requirements-gather 347, requirements-write 353, backlog-author 288 — all ≤ 400. The four `_BASELINES` rows equal the measured values exactly (361/353/347/288); total row 7320 equals the measured total. `test_non_cluster_budgets_within_default` is present and live: it first guards that every cluster name has a budget row, then asserts no non-cluster budget exceeds 400 (read-check confirmed: simulating interview=401 fails the assertion). Canonical and mirror SKILL.md are byte-identical for all four skills (and research); `test_plugin_mirror_parity.py` passes. `test_skill_descriptions.py` and `test_skill_routing_disambiguation.py` both pass.
- **Verdict**: PASS

### Non-Requirements (held)
- `skills/research/SKILL.md` NOT modified: confirmed — `git status` shows it unmodified, canonical/mirror byte-identical, research budget stays 502. HELD.
- No new pre-commit lint script: confirmed — no new `bin/cortex-check-*` for the L1 cap; enforcement is the strengthened ratchet test. HELD.
- No single flat cap: confirmed — the policy keeps the per-skill budget dict plus the cluster exemption; the ≤400 default applies only to non-cluster skills. HELD.
- No non-cluster skill other than the four targets trimmed: confirmed — all other non-cluster skills are unchanged and already ≤400 (backlog 319, morning-review 320, overnight 314, commit 208, diagnose 294, pr 237, requirements 231); their current values are their deliberate budgets and the R7 assertion sweeps in nobody new. HELD.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the existing module idioms. New test functions `test_budget_rows_complete` and `test_non_cluster_budgets_within_default` match the `test_*` snake-case convention and the descriptive-name style of the pre-existing `test_l1_surface_within_baseline`. `_BASELINES`, `_RATCHET_CASES`, `_utility_rows` are unchanged. The retained `_BASELINES` name (rather than a rename to e.g. `_BUDGETS`) is acceptable: the spec said "rename/recomment" and the recomment plus docstring reframing make the deliberate-budget intent unambiguous, while keeping the name stable avoids churn in the `total`/parametrization plumbing.
- **Error handling**: Assertion messages are specific and actionable. `test_budget_rows_complete` reports the exact set-difference both ways (missing budget rows vs stale rows) and the canonical-vs-utility divergence with the dangling-symlink hint. `test_non_cluster_budgets_within_default` reports the offending `{name: budget}` map and names both remedies (trim to ≤400B or promote into the cluster via reviewed allowlist edit). The per-skill ratchet message reports actual/budget/delta and points at the cap-policy backlog. The cluster-name-without-a-budget-row guard in `test_non_cluster_budgets_within_default` is a thoughtful subtractive-set safeguard: it fails loudly rather than silently shrinking the enforced non-cluster set if a cluster name is stray/renamed.
- **Test coverage**: Both new gates fire. The completeness gate is driven by the module-scoped `utility_rows` fixture (real utility output) and additionally walks the canonical enumerator. The non-cluster-≤400 gate operates on the literal `_BASELINES` dict so it is independent of measurement noise and catches an over-budget row at declaration time (read-check verified: a simulated interview=401 raises). The four trimmed skills' measured values equal their budgets exactly, so the ratchet has zero slack — any future regrowth of even 1 byte fails. The R6 fixtures are a deletion regression-guard verified live by `test_skill_descriptions.py`.
- **Pattern consistency**: Matches existing ratchet/test idioms — module-scoped fixture, parametrized per-skill cases plus a `total` row, equal-or-lower direction unchanged. The cross-module import `from test_skill_routing_disambiguation import ROUTING_PRESSURE_CLUSTER` is the spec's mandated single source of truth for cluster membership (Technical Constraint); it resolves to exactly the spec's six skills (critical-review, dev, discovery, lifecycle, refine, research) and is imported rather than duplicated, so the test and `project.md` cannot drift from the routing test's allowlist.

## Requirements Drift
**State**: none
**Findings**:
- None. The feature deliberately rewrote the "SKILL.md L1 surface ratchet" Architectural Constraint (`project.md:48`) to express the new policy, and the implementation agrees with it on every point: deliberate budgets (not a snapshot), the ≤400B non-cluster default structurally enforced by `test_non_cluster_budgets_within_default`, the six-skill routing-pressure cluster as the single exemption surface sourced once from `ROUTING_PRESSURE_CLUSTER`, the completeness gate, and the lifecycle-id'd re-cap rule for raises. The CLAUDE.md authoring pointer the constraint references exists. No implemented behavior is left uncaptured by the constraint, and the constraint asserts nothing the implementation omits.
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
