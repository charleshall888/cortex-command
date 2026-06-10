# Spec: harness-token-efficiency-trim

## Intent

Reduce the token mass the harness loads at runtime — the lifecycle/refine skill family's instruction files, their cross-file duplication, and the resume-path dead weight — **without changing any runtime behavior**. Every gate, decision criterion, event shape, exit-code route, user pause, and dispatched-verbatim prompt template survives unchanged. The change ships as one PR from `feature/harness-token-efficiency-trim` (branched from origin/main at 362bf765).

Non-goals: frontmatter description trimming (ratchet only — see R5), research/SKILL.md and critical-review reference trims (deferred tickets), the metrics fixes (separate PR), any change to phase sequencing, approval surfaces, criticality/tier semantics, or dispatch models.

## Requirements

### R1 — Apply the verified-safe trim inventory
For each of the 12 files in `evidence.json` → `trims_verified`: apply every `safe_proposals` entry as proposed, apply every `downgraded_proposals` entry per its `downgrade_to` action (these are condense/keep-canonical variants the verifier substituted for unsafe removals), and skip every `refuted_proposals` entry. Target ≥ 32KB net reduction across the 12 files (36,539B verified-safe minus the ADR-0009 manifest give-back from R4 and dedup pointer give-backs from R2). Where a proposal's `kind` is `maintainer-rationale` or `adr-recap` and the content is not already recorded in an ADR/doc/test docstring, relocate rather than delete (verifier notes flag which; most are already recorded elsewhere).

### R2 — Cross-file dedup, options 1–4 only
Per `evidence.json` → `duplication`: (1) extract the specify.md:165-180 / plan.md:273-288 §3b critical-review gate into `skills/lifecycle/references/critical-review-gate.md` (tier/criticality read, corrupted-log rule, run/skip matrix, `lifecycle_critical_review_skipped` event shape), replacing both sites with the 2-line pointer form already used for orchestrator-review.md; (2) reduce critical-review SKILL.md Steps 2a.5/2c.5/2d.5 to purpose + abort condition + pointer (canonical contract stays in verification-gates.md), keeping one-line abort conditions inline; (3) add a "Reading lifecycle state" section to criticality-matrix.md as the canonical statement of the `cortex-lifecycle-state` protocol (defaults, supersession rule, corrupted:true handling) and collapse the 8 consuming sites to bare command + pointer — canonical homes must be reachable from lifecycle, refine, discovery, AND research; (4) micro-canonicalizations (glossary sentence → load-requirements.md; index.md update block; `cortex-update-item` exit-2 handling; sub-task disjoint-Files race rule). **Do not touch**: dispatched-verbatim READ_OK copies, approval-surface skeletons, auto-advance reinforcements, model-routing inline values.

### R3 — Sync the orchestrator-review near-duplicate
`skills/discovery/references/orchestrator-review.md` and `skills/lifecycle/references/orchestrator-review.md` (79 divergent lines) converge on a shared canonical: keep the lifecycle copy as canonical (trimmed per R1), reduce the discovery copy to its genuinely discovery-specific deltas plus a body-resolved pointer to the canonical (discovery already resolves `../lifecycle/references/` paths for load-requirements.md and fanout.md — same mechanism). Discovery's behavior is unchanged.

### R4 — Progressive disclosure, option (b) only
(1) Extract SKILL.md's refine-delegation steps 1–6 (lines ~140–163 incl. event-log JSON templates) to `skills/lifecycle/references/refine-delegation.md`; the body keeps the three-way spec/research existence gate and gains a one-line read instruction. Add the extracted file's `${CLAUDE_SKILL_DIR}` targets (refine SKILL.md, discovery-bootstrap.md, complexity-escalation.md, post-refine-commit.md) to the body's Reference-path propagation manifest (ADR-0009). (2) Make the discovery-bootstrap.md read conditional on `phase = none/research`. (3) Split backlog-writeback.md's "Create index.md (New Lifecycle Only)" section into the conditional new-lifecycle read path, leaving Status Check + Write-Back as the resume-relevant file. Step 2's detect-phase table, the `-paused` rule, escalated handling, staleness signals, and the kept-pauses inventory location are untouched. **Option (c) (gate consolidation) is rejected per research.md F4 — do not implement any Step 2/3 routing change.** Update `tests/test_post_refine_commit_wired.py` anchors and post-refine-commit.md's "lifecycle Step 3 §4" cross-references in the same commit.

### R5 — L1 surface ratchet test
Add a test that runs `bin/cortex-measure-l1-surface` (reusing `tests/test_measure_l1_surface.py`'s `_utility_rows()` parsing) and fails if any skill's frontmatter bytes exceed the baseline in `evidence.json` → `l1_surface_baseline` (total 8,339), with a clear message pointing to the deferred cap-policy ticket. Ratchet only — no description text changes in this feature (routing-fixture tests stay untouched).

### R6 — Constraint preservation (hard gates)
(a) Kept-pauses inventory (`SKILL.md` §Kept user pauses) and `tests/test_lifecycle_kept_pauses_parity.py` updated in the same commit as any line-shifting edit; all 10 inventory entries survive with corrected anchors. (b) Canonical and `plugins/cortex-core/` mirrors committed together per the drift hook — never deferred. (c) The complete.md `**Hard guard**:` paragraph stays byte-identical to `tests/fixtures/complete_md_hard_guard.txt`; the `<!-- finalization-commit-step -->` marker region and implement.md's pinned token blocks survive (consult `evidence.json` → `constraints.anchors` per file before editing). (d) Grandfathered MUST/CRITICAL gates are not softened or deleted; only surrounding narration trims. (e) Event JSON shapes, exit-code routing tables, and all `cortex-*` invocation contracts (E101/E103) survive; events-registry lint passes. (f) Post-trim §-citation guard: grep `cortex_command/**` and `cortex_command/overnight/prompts/**` for `§`/`Step N` citations into every trimmed file (known: plan.md §1a/§1b/§5, complete.md Step 2, review.md §4a) and verify each cited section still exists under the same designator; record the result in the implementation notes.

### R7 — Verification
`just test` green; full pre-commit chain green on every commit (parity, contract, events-registry, skill-path, mirror drift); `bin/cortex-measure-l1-surface` total unchanged (R5 proves frontmatter untouched); per-file byte targets within ±15% of `evidence.json` safe-savings figures, with deviations explained; R6(f) grep log clean.

### R8 — Deferred-work tickets
Three backlog items created via `cortex-create-backlog-item` during Complete, each inlining its evidence verbatim (the /tmp research output does not survive; `evidence.json` in this directory is the durable source to quote): (a) L1 frontmatter cap policy + research-description overage, carrying the F6 decomposition; (b) research/SKILL.md trim map + trim, carrying its test anchors; (c) critical-review references trim map + trim, carrying the dispatched-verbatim exclusion list.

## Behavior-change policy

This feature is behavior-neutral by definition; any edit that cannot preserve a gate/criterion verbatim while trimming gets skipped and logged in the implementation notes rather than adapted. The two approved behavior-adjacent items (metrics re-bucketing, float rounding) are explicitly out of this PR.

## Approval

Scope, mechanism ((b) without (c)), packaging (two PRs), and the R3/R5 scope additions were approved by the user in-conversation on 2026-06-10 after a 5-angle adversarial review (research.md Provenance). The `spec_approved` event in events.log records that approval.
