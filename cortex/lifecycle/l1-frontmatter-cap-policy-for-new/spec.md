# Specification: L1 frontmatter cap policy for new skills + research-description overage (#298)

## Problem Statement

The L1 frontmatter surface (every skill's `description` + `when_to_use`, loaded into every session's system prompt in every project with the plugin) grew from 5,777B (post-#191) to 8,339B — a +44% regression. Research established the driver is **absence of a budget policy for new skills**: four skills added since #191 contribute 2,368B uncapped, and the existing ratchet (`tests/test_l1_surface_ratchet.py`) froze that bloated snapshot as a placeholder, explicitly deferring the formal policy to this ticket (`project.md:48`).

The durable value of this feature is the **enforced forward default** that prevents the *next* +44%: a ≤400B budget that the ratchet test structurally rejects new over-budget skills against (today the ratchet only catches growth past a row that already exists — it cannot reject a new skill, which is exactly how the four uncapped skills landed). Alongside that, it recovers ~768B now by trimming the four uncapped skills to the default. It deliberately does **not** claw back the routing-pressure cluster (dev, lifecycle, refine, research, discovery, critical-review ≈ 4,048B ≈ 48.5% of the surface): those skills carry irreducible disambiguation and path-routing tokens and are exempted by design, bounded by their own ratchet rows. The research-description regrowth (a separate +124B revert that depends on #299) is split into a follow-on ticket, not this one (see Non-Requirements).

## Phases

- **Phase 1: Policy + enforced default + fixes + routing floors** — reframe the ratchet to deliberate budgets, add the completeness assertion (every skill must have a budget row), write the cap policy, fix the misdirected references, and land trigger-phrase fixtures for the four uncapped skills. No skill-text trims yet.
- **Phase 2: Trim the four uncapped skills + turn on the ≤400 default assertion** — trim interview / requirements-write / requirements-gather / backlog-author to ≤400B SUM, then enable the ratchet's "non-cluster skills ≤400" assertion (satisfiable only once the trims land), structurally enforcing the default on all future non-cluster skills.

## Requirements

1. **Reframe the ratchet to deliberate budgets and add the completeness assertion.** In `tests/test_l1_surface_ratchet.py`: rename/recomment the `_BASELINES` dict to express deliberate per-skill byte budgets (comparison mechanics — equal-or-lower, parametrized per-skill + total — unchanged); add an assertion that **every skill enumerated under `skills/` has a budget row** (a new skill with no row fails the test, closing the add-time hole for the row's existence). Acceptance: `just test` exits 0 (pass if exit 0); `grep -ci "deliberate budget" tests/test_l1_surface_ratchet.py` ≥ 1; the test asserts row-completeness against the canonical skill enumerator (read-check: a skill present in `skills/` but absent from the budget dict raises). **Phase**: Phase 1: Policy + enforced default + fixes + routing floors. **Priority**: Must.

2. **Write the cap policy in `cortex/requirements/project.md`.** Rewrite the "SKILL.md L1 surface ratchet" constraint (currently `project.md:48`) in place to state: (a) the ratchet now holds deliberate budgets, not a snapshot; (b) the **≤400B desc+wtu SUM default** for non-cluster skills, structurally enforced by the test (R7); (c) the **routing-pressure cluster** (`dev, lifecycle, refine, research, discovery, critical-review`) is the single exemption surface — a non-cluster skill that genuinely needs >400B is promoted into the cluster by a reviewed decision, not a self-granted per-skill pass; cluster skills are bounded by their own ratchet rows; (d) **raising any budget row requires a lifecycle-id + rationale** (re-cap-with-rationale), aligning with the ratchet's existing "do not raise without a documented justification and lifecycle artifact" governance — so a legitimate re-cap is distinguishable from silent drift. Acceptance: `grep -c "400" cortex/requirements/project.md` ≥ 1 in the constraint; read-check that all of (a)/(b)/(c)/(d) appear, including the lifecycle-id requirement for raises. **Phase**: Phase 1: Policy + enforced default + fixes + routing floors. **Priority**: Must.

3. **Point new-skill authors at the budget.** Add one line to the skill-authoring guidance in `CLAUDE.md` stating that a new skill's `description`+`when_to_use` SUM is bounded by the L1 budget (default ≤400B for non-cluster skills; see `project.md` and `tests/test_l1_surface_ratchet.py`). Acceptance: `grep -ci "L1 budget\|400B\|l1 surface" CLAUDE.md` ≥ 1 within the skill-authoring section. **Phase**: Phase 1: Policy + enforced default + fixes + routing floors. **Priority**: Should — discoverability nicety; the policy is structurally enforced without it.

4. **Fix the misdirected ticket-295 references.** Repoint all three references to `cortex/backlog/295-automate-dependency-bump-...` in `tests/test_l1_surface_ratchet.py` (module docstring, `_BASELINES` comment, assertion failure message) to `cortex/backlog/298-l1-frontmatter-cap-policy-for-new-skills-research-description-overage.md`; name 298 in the `project.md` L1 constraint. Acceptance: `grep -c "295-automate" tests/test_l1_surface_ratchet.py` = 0; `grep -c "298-l1-frontmatter" tests/test_l1_surface_ratchet.py` ≥ 1; `grep -c "298" cortex/requirements/project.md` ≥ 1 in the L1 constraint. **Phase**: Phase 1: Policy + enforced default + fixes + routing floors. **Priority**: Should — defect hygiene; cheap and in-scope since the file is already being edited.

5. **Correct the regrowth provenance.** Record that `research` is itself post-#191 regrowth (+124B: 378→502), correcting the ticket body's claim that "the original 13 grew only ~194B (+3.4%) … NOT regrowth of trimmed skills." Capture the correction in the cap-policy provenance (a comment in the ratchet or a line in the policy text). Acceptance: `research.md` documents the +124B finding (already present); a one-line corrective note appears in the policy text or ratchet provenance comment. **Phase**: Phase 1: Policy + enforced default + fixes + routing floors. **Priority**: Should — provenance accuracy; does not affect the policy's function.

6. **Land trigger-phrase fixtures for the four uncapped skills (regression guard).** Add `skills:` entries to `tests/fixtures/skill_trigger_phrases.yaml` for `interview`, `requirements-write`, `requirements-gather`, `backlog-author`, each with ≥3 `must_contain` phrases currently present in that skill's `description` field. For the two collision-prone pairs (`requirements-gather`↔`requirements-write`, `interview`↔`backlog-author`), each skill's set must include **≥1 phrase that disambiguates it from its sibling** — a phrase present in its own `description` and absent from the sibling's — so the guard protects the actual confusion risk, not just any substring. This is a regression guard against accidental trigger-phrase deletion during the Phase-2 trim, not a routing-quality proof. Acceptance: `tests/test_skill_descriptions.py` passes (phrases present in current descriptions, green on add); the fixture's `skills` map has entries for all four; each has ≥3 `must_contain` phrases; for each collision-pair skill, at least one of its phrases is verifiably absent from its sibling's current `description` (read-check). **Phase**: Phase 1: Policy + enforced default + fixes + routing floors. **Priority**: Must — the regression guard that makes Requirement 7 verifiable.

7. **Trim the four uncapped skills to ≤400B SUM and enable the default assertion.** Reduce each of `interview` (758), `requirements-write` (685), `requirements-gather` (498), `backlog-author` (427) so its `description`+`when_to_use` SUM ≤ 400 bytes, keeping every Phase-1 fixture phrase in `description`. Update the four ratchet budgets to the new measured values. Then add the ratchet assertion that **every non-cluster skill's budget ≤ 400** (satisfiable only now that the trims have landed) — this structurally enforces the default on all future non-cluster skills. Regenerate plugin mirrors and commit canonical+mirror together. Acceptance: `bin/cortex-measure-l1-surface` reports each of the four ≤ 400; `tests/test_skill_descriptions.py` and `tests/test_skill_routing_disambiguation.py` both pass; `tests/test_l1_surface_ratchet.py` passes with the lowered budgets AND the non-cluster-≤400 assertion present (read-check: a non-cluster budget set >400 raises); `tests/test_plugin_mirror_parity.py` passes. **Phase**: Phase 2: Trim the four uncapped skills + turn on the ≤400 default assertion. **Priority**: Must.

## Non-Requirements

- **Research-frontmatter revert is OUT of scope for 298.** The ~378B careful-revert of `skills/research/SKILL.md`'s description (removing the +124B mechanism-narration regrowth) is split into a separate follow-on ticket that is `blocked_by #299` (now refined). Reason: the overnight runner has no phase-park state, so gating a 298 requirement on "#299 merged" would fail 298's whole verdict; and #299 edits the research *body* while the revert edits the *frontmatter*, so they are byte-disjoint and need only merge-ordering, not coupling inside 298. 298 therefore does **not** touch `skills/research/SKILL.md`; research's ratchet budget stays at **502** as its deliberate cluster budget until the follow-on lands.
- **No new pre-commit lint / authoring-time gate.** Enforcement is the existing ratchet test, strengthened with the completeness (R1) and non-cluster-≤400 (R7) assertions. No separate `cortex-check-*` script.
- **No `size-budget-exception` marker port.** That grammar guards a line-count body cap; an in-body marker cannot gate frontmatter bytes. The cluster allowlist + lifecycle-id'd re-cap is the exception surface instead.
- **No single flat cap.** Rejected for the 4.5× spread; the cluster exemption is the structural alternative.
- **Does NOT trim existing non-cluster skills other than the four targets.** All other non-cluster skills are already ≤400 (backlog 319, morning-review 320, overnight 314, commit 208, diagnose 294, pr 237, requirements 231), so the R7 assertion sweeps in nobody new; their current values become their deliberate budgets.
- **Does NOT change the routing tests' logic** — only their fixture data (R6).

## Changes to Existing Behavior

- MODIFIED: `tests/test_l1_surface_ratchet.py` — `_BASELINES`→deliberate budgets; ADDED a row-completeness assertion (Phase 1) and a non-cluster-≤400 assertion (Phase 2); lowered budgets for the four targets.
- MODIFIED: `cortex/requirements/project.md` "SKILL.md L1 surface ratchet" constraint (states the policy, the enforced ≤400 default, the cluster-promotion exemption, and the lifecycle-id'd re-cap rule).
- MODIFIED: `CLAUDE.md` skill-authoring guidance (one budget-pointer line).
- MODIFIED: four skills' frontmatter (Phase 2 trims).
- ADDED: trigger-phrase fixtures (regression guard) for four skills in `skill_trigger_phrases.yaml`.
- ADDED: a structurally-enforced new-skill budget policy (≤400B default for non-cluster skills + cluster-promotion exemption + lifecycle-id'd re-cap).

## Edge Cases

- **A new skill is added with no budget row**: the R1 completeness assertion fails the ratchet test — the skill cannot be added without declaring a budget.
- **A new non-cluster skill ships >400B**: the R7 non-cluster-≤400 assertion fails — it must trim, or be promoted into the cluster allowlist by a reviewed `project.md` edit.
- **A cluster skill genuinely cannot meet a desired target without dropping a trigger phrase**: set its deliberate cluster budget to the achievable value via the re-cap rule (record minimum-achievable + reason + gap + **lifecycle-id** in the policy/inline comment). This is a budget *raise*, so the lifecycle-id makes it distinguishable from silent drift.
- **A chosen fixture phrase is not present in a skill's current description**: `test_skill_descriptions.py` fails on fixture-add. Mitigation: select only phrases verified present.
- **A collision-pair fixture phrase also appears in the sibling's description**: it provides no disambiguation; R6 requires ≥1 phrase per collision-pair skill that is absent from the sibling.
- **Trigger phrase lives in `when_to_use`, not `description`**: `test_skill_descriptions.py` checks `description` alone, so keep all fixture phrases in `description`.

## Technical Constraints

- Measurement is the `description`+`when_to_use` **SUM in UTF-8 bytes** via `bin/cortex-measure-l1-surface` (canonical skills only); express budgets in bytes.
- `tests/test_skill_descriptions.py` enforces `must_contain` phrases against the `description` field **alone**; `tests/test_skill_routing_disambiguation.py` checks concatenated `description`+`when_to_use` for the fixed routing-pressure cluster only.
- The cluster allowlist in the policy/test must match the routing-pressure cluster encoded in `tests/test_skill_routing_disambiguation.py` (`dev, lifecycle, refine, research, discovery, critical-review`) — single source of truth for cluster membership.
- The ratchet's existing governance ("Do NOT raise these values without a documented justification and lifecycle artifact") is now encoded in R2(d)'s lifecycle-id'd re-cap rule.
- Canonical `skills/*/SKILL.md` edits require `just build-plugin` mirror regen; canonical + mirror commit **together** (drift hook + shared-checkout coupling).
- Editing `tests/`, `skills/`, `cortex/requirements/`, `CLAUDE.md` are within lifecycle-gated paths and trip parity/contract/skill-path pre-commit gates — run them per edit.
- The research-frontmatter follow-on ticket is `blocked_by #299` (refined, not yet merged); it is not part of 298's overnight unit.
- MUST-escalation policy: re-trimmed frontmatter must not introduce new MUST/CRITICAL/REQUIRED language without the evidence artifact; prefer soft positive-routing phrasing.
- The cap policy is documented as a `project.md` Architectural Constraint (same shape as the SKILL.md size-cap), not an ADR — reversible, documented inline.

## Open Decisions

- **Exact trigger phrases per skill (R6) and exact trimmed wording (R7)**: deferred to implementation — phrase selection (including the disambiguating phrase per collision-pair skill) and trim spans require the live `description` text and per-skill routing-role judgment that only exist at edit time.

## Proposed ADR

None considered. The policy is enforcement detail documented as a `project.md` Architectural Constraint (consistent with the existing SKILL.md size-cap entry); it is reversible and does not clear the three-criteria ADR gate.
