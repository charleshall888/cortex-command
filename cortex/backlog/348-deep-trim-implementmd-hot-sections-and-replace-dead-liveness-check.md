---
schema_version: "1"
uuid: b2475c58-a893-4da1-ab31-338463568b87
title: Deep-trim implement.md hot sections and replace dead liveness check
status: in_progress
priority: high
type: feature
tags: ['skill-value-scorecard']
areas: ['skills', 'lifecycle']
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
lifecycle_phase: research
lifecycle_slug: deep-trim-implementmd-hot-sections-and
complexity: complex
criticality: high
spec: cortex/lifecycle/deep-trim-implementmd-hot-sections-and/spec.md
---
## Why
implement.md is the audit corpus outlier: its content rides into dispatched builder prompts, so every resident token multiplies. Eleven verified verdicts remain unapplied: three big structural ones, eight section compressions (s3, s5, s6, s11, s12, s14, s21, s23 — together ~10.1k weighted, including the s21 builder-prompt template at 1,680), and one section (1a-i, the interactive worktree liveness check) probes a PID file that nothing in the codebase ever writes — dead code that still costs ~672 weighted tokens and provides no guard.

## Role
Apply the remaining verified implement.md verdicts from master_candidates.json: compress the step-v auto-enter narration between its test-pinned anchors (s13, roughly 20 percent of 873 tokens), move the five-case merge-back procedure to a lazily read sibling reference since it is skipped entirely for sequential dispatch (s18), apply the eight remaining compressions per their keep-lists, and replace section 1a-i with a one-line probe of the interactive-lock console script so the suppressed branch-mode path — which skips the section-1 Step B guard — gains a real same-slug concurrency check (user decision recorded 2026-07-02).

## Integration
The step-v ordering test extracts a bounded block and asserts token order, not prose bulk; the verdicts name the boundaries — but their line anchors predate the inline trim commit for this file, so locate sections by heading and pinned tokens. The lazy-ref move needs a read trigger at the worktree-mode branch point and must keep references resolving (references-resolve test requires new files to be committed before the test run). The probe replacement touches the same suppressed-path routing the inline s4/s7 trims just compressed.

## Edges
- Verdicts carry exact keep-lists (EnterWorktree skipped token, worktree-precondition verb name, interactive_worktree_entered event) — research should re-validate each pin before cutting. For s13, the safe-compression figure is the failure-history lens's 10-15 percent, not the scorer's 20.
- The probe must not fire on the picker-selected path, which already runs Step B.
- implement.md has NO provisional candidates — all 13 are verified, and the eight compressions above are owned here, not by the 353 sweep. On section 1a-i, this ticket is the durable record of the user's 2026-07-02 direction: replace with a probe, do not merely delete. The s10 verdict lenses conflict on replacement design (keep the sessions-path contract facts vs defer wholly to the interactive-lock verb); research resolves that design within the replace direction.
- Three groups in dup_groups.json span implement.md and sibling references; coordinate with the 353 sweep so each single-sourcing edit happens exactly once.

## Touch points
- skills/lifecycle/references/implement.md (sections 1a step v, 1a-i, 2e)
- possibly a new skills/lifecycle/references/ sibling for the merge-back procedure
- cortex_command/lifecycle_implement.py — the s10 verdicts carry a same-commit precondition: its docstring cite to implement.md line numbers is already stale and must be realigned; also decide in scope whether picker fire-condition iv (pinned by tests/test_lifecycle_implement_branch_mode.py) should stop probing the phantom sessions PID path
- plugins/cortex-core mirror (same commit)
- cortex/research/skill-value-scorecard/master_candidates.json (verdict source)