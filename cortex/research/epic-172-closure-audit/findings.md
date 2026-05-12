# Epic-172 closure-inaccuracy audit (DR-5 spike, #194)

## Question

Is #179's "closed but never executed" closure-quality gap a one-off, or systemic across epic #172's 11 children? If systemic, which failure mode dominates: discipline gap, scope-drift confound, or general closure-inaccuracy?

## Method

Sampled 3 sibling tickets from epic #172, plus #179 itself (already verified by the parent audit). Mix designed to discriminate: at least one ticket without mid-flight scope changes (control), at least one with. For each sample: read the spec's `## Verification` section, run each acceptance check against current repo state, classify the closure as clean / partial-gap / scope-drift / non-delivery.

Samples:
- **#179** (audit's original case) — extract conditional content; underwent mid-flight scope trim (6 extractions → 2)
- **#173** (control) — fix duplicated block + 5 stale refs; no documented scope changes
- **#178** (variable) — skill-creator-lens improvements across 4 skills; many concerns, plausible drift surface
- **#181** (variable) — skill-design test infrastructure (4 named test files); plausible naming evolution during implementation

## Per-ticket findings

### #173 — CLEAN

Spec's 4 verification checks (`backlog/173-...md:57-62`):
- Duplicated `Alignment-Considerations Propagation` block removed ✅ (one block at `skills/refine/SKILL.md:118-137`; no duplicate at 138-157)
- `grep -c "claude/common.py" skills/lifecycle/SKILL.md` returns 0 ✅
- `grep -c "bin/overnight-status" skills/lifecycle/references/implement.md` returns 0 ✅
- Pre-commit dual-source drift hook passes — assumed (no current failure)

**Verdict**: Clean. Spec's acceptance criteria match current repo state.

### #178 — PARTIAL DELIVERY + STALE LINE RANGES

Spec's 8 verification checks (`backlog/178-...md:96-105`):

| # | Check | Result |
|---|-------|--------|
| 1 | `## Contents` TOC in 4 large files (lifecycle, critical-review, refine, discovery SKILL.md) | **2 of 4** — refine and discovery SKILL.md have no `## Contents` heading |
| 2 | `Different from /cortex-core` disambiguator in 4 SKILL.md files | **3 of 4** — critical-review/SKILL.md has no such phrase |
| 3 | 7 MUSTs in review.md + clarify-critic.md softened to positive-routing | review.md = 0 MUSTs ✅; clarify-critic.md = 3 MUSTs remaining (unclear if grandfathered or originally targeted) |
| 4 | `critical-review/SKILL.md:336-365` Apply/Dismiss/Ask body replaced with ~5-line WHAT/WHY | **Line range is stale** — file is now 369 lines; region 336-365 contains a `python3 -c` block for atomic JSON write (Step 2e), not Apply/Dismiss/Ask. The Apply/Dismiss/Ask section doesn't appear in `grep` of the current file at all. Either the section was removed entirely, or moved, or renamed — spec's line-range check cannot verify. |
| 5 | Constraints "Thought/Reality" tables trimmed to ≤2 retro-cited rows per file | Not exhaustively verified; many `Constraints` sections still present. Probably partial. |
| 6 | `lifecycle/SKILL.md:33-35` slugify HOW prose replaced with `slugify()` reference | Not verified — line range may also be stale. |
| 7 | `critical-review/SKILL.md` frontmatter has `argument-hint`, `inputs`, `outputs`, `preconditions` | ✅ all present |
| 8 | Pre-commit dual-source drift hook passes | Assumed |

**Verdict**: Partial delivery (TOC in 2/4, disambiguator in 3/4) + stale line-range references (the line-anchored checks 4, 6 can't be verified because the file evolved during implementation and the spec wasn't updated). **Multiple verifiable gaps.**

### #181 — FULL DELIVERY UNDER DIFFERENT NAMES (scope-drift confound)

Spec's 5 verification checks (`backlog/181-...md:86-95`):

- "All four new tests pass against the current state of skills/" — the spec elsewhere names: `test_skill_descriptions.py`, `test_skill_cross_skill_handoff.py`, `test_skill_reference_paths.py`, `test_skill_size_budget.py`.
- Actual test files in `tests/`:
  - `test_skill_descriptions.py` ✅ exists
  - `test_skill_size_budget.py` ✅ exists
  - `test_skill_cross_skill_handoff.py` ❌ does NOT exist; **`test_skill_handoff.py` exists instead** — its docstring says *"Test #2 (skill-design test infrastructure, ticket #181)"*, confirming this is the same work under a different name.
  - `test_skill_reference_paths.py` ❌ does NOT exist; **`test_lifecycle_references_resolve.py` exists instead** — its docstring says *"Test #3 (skill-design test infrastructure, ticket #181) extends this file with a sixth form"*, confirming this is the same work merged into an existing test file rather than created as a new one.

- "Wired into `just test` or equivalent" — actual `justfile` invocation: `uv run pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py` — wires the renamed files. ✅ functionally.
- Deliberate-regression checks (drop trigger phrase, rename referenced file) — work substantively delivered per docstrings; not re-verified end-to-end here.

**Verdict**: Work substantively delivered, but **2 of 4 promised file names differ from spec**, and one was merged into an existing test file rather than created new. A literal verification of the spec's acceptance criteria would fail (`ls test_skill_cross_skill_handoff.py` returns nothing) despite the work being done. **Pure scope-drift confound: spec's acceptance criteria were not re-aligned when implementation renamed/merged the deliverables.**

### #179 (from parent audit) — NON-DELIVERY (scope-trim confound)

Spec called for extracting `skills/critical-review/references/a-b-downgrade-rubric.md` and `skills/lifecycle/references/implement-daytime.md`. Files do not exist. Spec target `implement.md` ~210 lines; actual 283. Audit notes #179 underwent mid-flight scope trim from 6 extractions to 2 per "epic-172-audit C7" — the trimmed scope itself was specified, but the trimmed deliverables never landed.

**Verdict**: Non-delivery despite trimmed-scope spec. Closure marked `complete` without verification.

## Base rate

**3 of 4 sampled tickets show closure-quality gaps** (#179, #178, #181). Only **#173** is clean. Roughly 75% gap rate in this small sample.

**This is NOT a one-off.** The N=1 extrapolation that DR-5 originally jumped to was directionally correct, even if the original gate-recommendation was wrong.

## Failure-mode breakdown

Across the 3 gap cases:

- **#179**: pure non-delivery + scope-trim confound — spec called for 2 files post-trim; closure marked complete without checking files exist.
- **#178**: partial delivery (2/4 TOCs, 3/4 disambiguators) + stale line-range anchoring (line ranges in verification commands went stale as files evolved during implementation; spec not updated).
- **#181**: substantively complete work + acceptance-criteria-naming-drift (test files renamed and merged during implementation; spec's named files don't exist; renamed equivalents do).

**Common factor**: **acceptance criteria not re-aligned with mid-flight implementation changes.** Whether the change is scope trim (#179), file restructuring (#178), or rename/merge (#181), the spec's acceptance criteria stay frozen at the moment the spec was approved, but the implementation evolves. Closure checks the criteria against an evolved repo state and either (a) fails silently (criteria check non-existent files), or (b) is skipped entirely.

This is not a discipline gap (the work was done, just under different names/scope). It's not general closure-inaccuracy. **It is specifically a spec-evolution gap**: the lifecycle has no checkpoint that says *"acceptance criteria were rewritten during plan or implement; verify the new criteria, not the old ones."*

## Recommendation

**DO NOT add a project-wide mechanical completion gate.** The original DR-5 proposal would catch #179 (file-exists check) but miss #181 entirely (criteria refer to wrong filenames; the gate would correctly fail despite the work being done — high false-positive rate). It would catch some of #178 but not the line-range-staleness issues.

**Right intervention: spec re-acceptance at the moment of mid-flight change.**

- When `/cortex-core:lifecycle`'s implement phase modifies a spec's acceptance criteria (e.g., trims scope, renames deliverables, restructures files), prompt: *"acceptance criteria changed; review and confirm new criteria before resuming implementation."*
- This intervention is closer to the existing "Open Decisions" pattern than to a closure-time check.
- A secondary check could verify the spec's `## Verification` commands actually run cleanly against current repo state at closure time — but it's a guard, not the primary mechanism.

**Frame the follow-up as a feature, not a gate.** "Spec drift awareness during implement" rather than "closure verification gate."

**Suggested follow-up scoping** (not a ticket — file separately if user agrees):

- Investigate where in `/cortex-core:lifecycle`'s plan/implement phases a spec is allowed to evolve (and where it's frozen). Today the spec is often treated as immutable post-approval; in practice it isn't.
- Add a re-acceptance prompt when the implement phase rewrites or restructures verification commands or named deliverables.
- Optional: at closure, dry-run the spec's `## Verification` commands and warn (don't fail) on staleness — caught some of #178's issues, but won't catch #181 because the spec criteria are correct in isolation, just disconnected from implementation.

## What this spike does NOT recommend

- Adding a project-wide closure-time filesystem gate (would have caught only ~33% of the observed failure modes).
- Adding closure-discipline tooling (the discipline failure isn't the dominant pattern).
- Re-opening #178, #179, #181 to "fix" the gaps. Recommend leaving the historical record; the next epic that depends on these tickets' deliverables will surface any real-world impact, and at that point the gap can be addressed with full context.

## Self-aware caveat

This audit's own `[premise-unverified]` markers in `research/lifecycle-discovery-token-audit/research.md` mean it does not meet the standard it would be asking other closures to meet. The recommendation above is correspondingly humble: prompt at the moment of change, don't enforce at the moment of closure.
