# Review: extract-the-critical-only-competing-plans

## Stage 1: Spec Compliance

### Requirement 1: Create the new sibling reference (`competing-plans.md`) with all seven sub-parts a–g, restated heading + TOC
- **Expected**: File exists AND `grep -c "plan_comparison" competing-plans.md` ≥ 1 AND `grep -c "plan_comparison" plan.md` = 0 (schema left plan.md entirely). File ≈104 lines, restated `### 1b.` heading + one-line TOC.
- **Actual**: `skills/lifecycle/references/competing-plans.md` exists, 108 lines, opens with byte-identical `### 1b. Competing Plans (Critical Only)` heading + a one-line TOC blockquote listing sub-parts a–g. All seven sub-parts present (prepare context, dispatch + verbatim prompt template, collect, synthesizer dispatch, envelope LAST-occurrence anchor, verdict/confidence routing + legacy table, v2 `plan_comparison` event schema). `grep -c plan_comparison competing-plans.md` = **5** (≥1 ✓). `grep -c plan_comparison plan.md` = **1** (spec requires **0**). The residual occurrence is a prose mention inside the §1b stub pointer at `plan.md:23` ("log the v2 `plan_comparison` event") describing the moved protocol.
- **Verdict**: PARTIAL
- **Notes**: The substantive intent stated in the requirement's parenthetical — "the schema left plan.md entirely" — is met: the JSON event schema and all field semantics moved to competing-plans.md; only a single descriptive prose token remains in the one-line stub. But the requirement's explicit, binary acceptance command (`grep -c "plan_comparison" skills/lifecycle/references/plan.md` = 0) demonstrably returns 1. This is a spec-internal tension (Req 2 invites a descriptive "one-line pointer," and a natural descriptive pointer names the moved protocol's event) rather than a behavioral defect. No CI gate depends on this count; `just test` is fully green.

### Requirement 2: Reduce plan.md §1b to a load-bearing stub, gate the read in §1a's `critical` branch
- **Expected**: §1b body replaced by byte-identical heading + one-line pointer; imperative read directive in §1a's `critical` branch; `test_skill_section_citations.py` exits 0 AND `grep -c competing-plans plan.md` ≥ 1 AND `grep -c references/competing-plans.md plan.md` = 0.
- **Actual**: `plan.md:21` heading byte-identical to `### 1b. Competing Plans (Critical Only)` (verified via string equality). `plan.md:18` (§1a `critical` branch) now reads "read and follow the competing-plans protocol (use the body-resolved absolute path … the **competing-plans** target) before dispatching" — the routing directive on the ~2% path. `plan.md:23` is the stub pointer naming the **competing-plans** target (bold named-target idiom). `test_skill_section_citations.py`: 5 passed. `grep -c competing-plans plan.md` = 2 (≥1 ✓). `grep -c references/competing-plans.md plan.md` = 0 (no bare-relative read path ✓). `check-skill-path-audit` clean.
- **Verdict**: PASS
- **Notes**: Structural gate (routing control flow), not prose-only. Non-critical top-to-bottom readers never reach the directive — over-fetch dual closed. Bold-agnostic acceptance satisfied.

### Requirement 3: Register the sibling in the SKILL.md propagation manifest
- **Expected**: One manifest bullet modeled on `critical-review-gate`, in the propagation list (not the Step 3 table); `grep -c competing-plans SKILL.md` ≥ 1 AND `test_skill_size_budget.py` exits 0.
- **Actual**: `SKILL.md:160` adds `**competing-plans** (read on Plan's `critical` branch via §1a→§1b) → ${CLAUDE_SKILL_DIR}/references/competing-plans.md` in the `### Reference-path propagation (load-bearing)` list, directly after `critical-review-gate` — modeled exactly. Not in the Step 3 phase-execution table. `grep -c` = 1 (≥1 ✓). `test_skill_size_budget.py`: 5 passed.
- **Verdict**: PASS

### Requirement 4: File-qualify the four dangling cross-references
- **Expected**: The four forward-refs to plan.md sections rewritten with `plan.md` qualifier (or dropped for the subagent-template §3 ref); Req-4 token-complete grep returns 0 lines.
- **Actual**: All four sites qualified in competing-plans.md — "Use the plan format defined in plan.md §3 (Write Plan Artifact)" (template ref qualified, self-contradictory "below" removed), "proceed to plan.md §3a" / "single-plan flow in plan.md §2–§3", "fall back to the standard single-plan flow in plan.md §2–§3", "proceed to plan.md §3a … or to plan.md §2". Internal `§1b.x` refs retained (anchor the restated heading). Acceptance grep `defined in §3 Write Plan Artifact|proceed to §3a|single-plan flow \(§2-§3\)|or to §2 \(Design` returns **0 lines** ✓.
- **Verdict**: PASS

### Requirement 5: Re-anchor the shifted kept-pauses entry
- **Expected**: Anchor at `kept-pauses.md:18` updated from `plan.md:281` to the post-edit line within `LINE_TOLERANCE = 35`; `test_lifecycle_kept_pauses_parity.py` exits 0.
- **Actual**: `kept-pauses.md:18` now reads `skills/lifecycle/references/plan.md:184`. `plan.md:184` is the `**Compose the AskUserQuestion options**` line of the merged plan-approval surface (the AskUserQuestion site). `test_lifecycle_kept_pauses_parity.py`: 2 passed.
- **Verdict**: PASS

### Requirement 6: Repoint documentation citations for accuracy
- **Expected**: `orchestrator-round.md:302` and `test_orchestrator_round.py:85` docstring cite competing-plans.md; `grep -c competing-plans orchestrator-round.md` ≥ 1.
- **Actual**: `orchestrator-round.md:302` now reads "the same LAST-occurrence anchor pattern as the canonical `skills/lifecycle/references/competing-plans.md` §1b". `test_orchestrator_round.py:85` docstring cites `skills/lifecycle/references/competing-plans.md` §1b. `grep -c` = 1 in each. `test_orchestrator_round.py`: 4 passed.
- **Verdict**: PASS

### Requirement 7: Regenerate the plugin mirror in the same commit
- **Expected**: After `just build-plugin`, `git diff --quiet -- plugins/cortex-core/` (no drift) AND `test_dual_source_reference_parity.py` exits 0.
- **Actual**: `git diff --quiet -- plugins/cortex-core/` exits 0 (no drift). `plugins/cortex-core/skills/lifecycle/references/competing-plans.md` exists and is byte-identical to canonical (`diff -q` matches). `test_dual_source_reference_parity.py`: 59 passed.
- **Verdict**: PASS

### Requirement 8: All gates green
- **Expected**: `just test` exits 0 covering the named tests plus pre-commit lints.
- **Actual**: `just test` → "Test suite: 7/7 passed". Spot-checked: `test_skill_section_citations` (5), `test_lifecycle_kept_pauses_parity` (2), `test_lifecycle_references_resolve` (4), `test_dual_source_reference_parity` (59), `test_dispatch_template_placeholders` (9), `test_orchestrator_round` (4) — all pass. `check-skill-path-audit` clean; `check-parity` exit 0.
- **Verdict**: PASS

### Requirement 9: Add a durable wiring test
- **Expected**: `tests/test_competing_plans_wired.py` statically pins (a) file+mirror existence, (b) SKILL.md manifest reference, (c) plan.md references target near §1b/§1a, (d) `plan_comparison` content token; honest about static-vs-runtime; exits 0.
- **Actual**: File present with 5 tests, all passing. Covers all four assertions. Critically, `test_plan_md_carries_the_1a_read_directive` requires a *single* line containing all of `critical` + `read` + `competing-plans` — verified that ONLY `plan.md:18` (the §1a routing directive) matches; the §1b stub at `plan.md:23` uses "loads it" (no `read` token), so it cannot satisfy the assertion. A revert of §1a to "proceed to §1b" would drop the routing wire and fail this test even though the stub survives — the test genuinely pins the load-bearing wire, not the co-located stub. The module docstring and an explicit "Deliberately OUT OF SCOPE" note disclaim the runtime cold-read as untestable, so the gate is honest, not self-sealing.
- **Verdict**: PASS

### Non-Requirements & Edge Cases
- Heading text unchanged: `### 1b. Competing Plans (Critical Only)` byte-identical at `plan.md:21` and `competing-plans.md:1` ✓.
- No new `bin/cortex-*` verb / no `.parity-exceptions.md` edit: `git show` of both commits touches no `bin/` verb; `check-parity` exit 0. The only `cortex-*` tokens in the block (`cortex-resolve-model`, `cortex-lifecycle-state`) stay wired ✓.
- §1a routing outcomes preserved: `critical` → competing-plans; low/medium/high → §2. No new branch or changed condition ✓.
- SKILL.md-body gate NOT used (Alternative B rejected): directive lives in plan.md §1a, manifest bullet only in SKILL.md ✓.
- Cold-read edge case handled as specced: read directive is one level deep in §1a's `critical` branch (structural gate); runtime miss accepted as untestable and disclaimed in the wiring test ✓.

## Stage 2: Code Quality
- **Naming conventions**: `tests/test_competing_plans_wired.py` and its `_repo_root`/`_plan_lines` helpers and `test_*` names mirror the `test_post_refine_commit_wired.py` precedent. Sibling reference file naming (`competing-plans.md`) matches the `critical-review-gate.md` lazy-sibling convention. Consistent with repo patterns.
- **Error handling**: N/A for the prose relocation. The moved protocol preserves the existing `cortex-resolve-model` nonzero-exit halt-and-escalate semantics verbatim; no new error paths introduced.
- **Test coverage**: All plan verification steps executed and green. The wiring test is honest about scope (static wiring guarded; runtime cold-read explicitly out of scope). It improves on the base precedent by adding the distinct §1a-directive assertion (all-three-tokens-on-one-line) that a co-located stub cannot satisfy — a genuine guard against silently reverting the routing wire.
- **Pattern consistency**: Follows the `critical-review-gate` manifest-bullet + branch-gated-read lazy-sibling precedent and the `#334 fanout.md` extract+citer-repoint+mirror-in-one-commit precedent (all token forms scrubbed, not just path-form). Consistent with `test_post_refine_commit_wired.py`.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict (Cycle 1 — superseded)
```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["Req 1 literal acceptance fails: `grep -c \"plan_comparison\" skills/lifecycle/references/plan.md` returns 1, not the spec-required 0. The residual token is a prose mention in the §1b stub pointer at plan.md:23 (\"log the v2 `plan_comparison` event\"). Low severity, non-behavioral: the schema itself fully moved (the requirement's stated intent, \"the schema left plan.md entirely\", is met) and no CI gate depends on this count. Resolve by either (a) rewording the plan.md:23 stub pointer so the literal `plan_comparison` token no longer appears (e.g. \"…→ route → log the v2 comparison event\"), or (b) amending the Req 1 acceptance to reflect that the schema block — not every mention of the event name — must leave plan.md, since Req 2's descriptive one-line pointer naturally names the moved protocol."], "requirements_drift": "none"}
```

---

## Cycle 2 Re-Review

Cycle 1 returned CHANGES_REQUESTED with exactly one low-severity blocker: Req 1's binary acceptance `grep -c "plan_comparison" skills/lifecycle/references/plan.md` returned 1 (not 0), because the §1b stub pointer at `plan.md:23` contained the prose token `plan_comparison`. The fix landed in commit `04841f92` ("Drop residual plan_comparison token from the §1b stub pointer"), rewording "log the v2 `plan_comparison` event" → "log the v2 comparison event". This cycle confirms the fix resolves the issue and introduces no regression.

### Issue resolution (Req 1)
- **`grep -c plan_comparison skills/lifecycle/references/plan.md` = 0** — the spec-required count is now met. The schema block genuinely lives only in the sibling.
- **`grep -c plan_comparison skills/lifecycle/references/competing-plans.md` = 5** (≥1 ✓) — the JSON event schema and all field semantics remain fully in competing-plans.md; the reword removed only the descriptive prose mention from plan.md, not any schema content.
- **Verdict**: Req 1 now **PASS** (was PARTIAL in cycle 1).

### Regression check (the reword changed only one token)
- The commit diff shows a single-line, single-token change on `plan.md:23` (canonical) plus its byte-identical mirror line — `plan_comparison` → `comparison`. Nothing else in plan.md moved.
- **§1b stub still names the target** (Req 2 one-line pointer intact): `plan.md:23` still reads "…now lives in the **competing-plans** target; §1a's `critical` branch loads it before dispatching…". `grep -c competing-plans plan.md` = 2 (≥1 ✓); `grep -c references/competing-plans.md plan.md` = 0 (no bare-relative read path ✓).
- **§1a critical-branch read directive unchanged** (`plan.md:18`): still "read and follow the competing-plans protocol (use the body-resolved absolute path … the **competing-plans** target) before dispatching…" — untouched by the reword. It still carries all three wiring tokens (`critical` + `read` + `competing-plans`) on one line, so Req 9's `test_plan_md_carries_the_1a_read_directive` remains satisfied.
- **Heading byte-identical**: `### 1b. Competing Plans (Critical Only)` still present at `plan.md:21` (Non-Requirement / `test_skill_section_citations.py` pin intact).

### Gates
- `.venv/bin/python -m pytest tests/test_skill_section_citations.py tests/test_competing_plans_wired.py tests/test_dual_source_reference_parity.py tests/test_lifecycle_kept_pauses_parity.py tests/test_dispatch_template_placeholders.py -q` → **80 passed**.
- Mirror parity: `git diff --quiet -- plugins/cortex-core/` → **CLEAN** (canonical + mirror plan.md lines match; the fix commit updated both).

### Requirements 2–9 spot-check
Untouched by the reword except the single stub-line token in plan.md. Req 2 (stub + §1a directive), Req 3 (SKILL.md manifest bullet), Req 4 (four cross-refs qualified in competing-plans.md), Req 5 (kept-pauses anchor), Req 6 (orchestrator doc cites), Req 7 (mirror), Req 8 (full suite), Req 9 (wiring test) all remain satisfied — corroborated by the green gate run above (dual-source parity 59 cases, kept-pauses parity, section citations, wiring test, dispatch placeholders all pass) and the CLEAN drift check. No regression detected.

## Requirements Drift
**State**: none
**Findings**:
- None. The cycle-1 fix took resolution path (a) — rewording the stub pointer — which is the spec-anticipated remedy; no amendment to Req 1's acceptance was needed, so the requirements text stands unchanged and is now fully satisfied by the implementation.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
