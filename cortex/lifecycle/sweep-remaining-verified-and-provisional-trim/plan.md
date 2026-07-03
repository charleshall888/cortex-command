# Plan: sweep-remaining-verified-and-provisional-trim (Batch 1)

## Overview
Apply the 50 verified lifecycle-cluster trim verdicts (+ the one verified critical-review candidate) file-by-file, each as a canonical+mirror commit, honoring the per-candidate keep-list from `master_candidates.json`. Mechanical-but-editorial prose compression; the audit already did the analysis.

## Outline

### Phase 1: Verified trim application (tasks 1–13)
**Goal**: Apply all 50 verdicts, one commit per file/small-batch, canonical + regenerated `plugins/cortex-core/` mirror staged together.
**Checkpoint**: All 19 files trimmed, each commit passes the drift pre-commit hook, per-file pinned tests green.

### Phase 2: Integration gate (task 14)
**Goal**: Full-suite green + keep-list survival tally + savings measurement before Review.
**Checkpoint**: `just test` all green; every applied keep-list token still present; ~8.6k weighted savings tallied.

## Execution notes (apply to every task 1–13)
- **`Files` lists canonical edit targets only.** The `plugins/cortex-core/` mirror for each edited file is build output, not a hand-edit. Every task is explicitly authorized to run `just build-plugin` (which rewrites the mirror tree) and to stage the regenerated mirror(s) in the same commit, even though mirrors are not enumerated in per-task `Files`.
- **Locate by heading + pinned tokens**, never stored line numbers (stale).
- **Authoritative instruction** = each candidate's `verdict_summaries[].revised_claim` in `cortex/research/skill-value-scorecard/master_candidates.json`. Filter by `file` + `id`. Apply its action; keep verbatim exactly what it names.
- **Mirror + commit**: after editing canonical, run `just build-plugin`, then stage **canonical + regenerated mirror together** and commit via `/cortex-core:commit` with an explicit pathspec (concurrent session on `main`). The drift hook fails a split.
- **Verification is two-sided**: the keep-list token still greps present AND the removed phrase's count dropped (a keep-grep alone doesn't prove a cut).

## Tasks

### Task 1: Trim critical-review reviewer-prompt JSON-envelope spec (s9)
- **Files**: skills/critical-review/references/reviewer-prompt.md
- **What**: COMPRESS the JSON-envelope spec (732w) — the highest-risk candidate. Isolated first so any synthesizer-contract issue surfaces early.
- **Depends on**: none
- **Complexity**: simple
- **Context**: candidate `reviewer-prompt.md s9`. Before trimming, read the critical-review synthesizer to enumerate what it parses (the `<!--findings-json-->` delimiter and every field it extracts). **Asymmetric keep**: the straddle-rationale population instruction is the sole one repo-wide — keep or relocate, never drop (spec R4). Keep the delimiter contract and all parsed fields verbatim; compress only prose/examples the synthesizer never reads.
- **Verification**: `grep -c 'findings-json' skills/critical-review/references/reviewer-prompt.md` ≥ 1 AND straddle-rationale instruction still present (grep) — pass if both hold; and `diff <(git show HEAD:skills/critical-review/references/reviewer-prompt.md) skills/critical-review/references/reviewer-prompt.md | grep -c '^>'` shows fewer added-than-removed (net shrink). Run the critical-review contract/parity tests if any pin this file.
- **Status**: [ ] pending

### Task 2: Trim lifecycle SKILL.md body (s8, s5, s12, s16)
- **Files**: skills/lifecycle/SKILL.md
- **What**: Largest lifecycle target (2166w). s8 Artifact-Based Phase Detection (COMPRESS), s5 Step-1 mode-routing table (COMPRESS), s12 refine-Delegation (COMPRESS), s16 Kept-user-pauses (MERGE_DEDUP vs kept-pauses.md).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: candidates `SKILL.md s8/s5/s12/s16`. **s16 must not change the parity-tested pause inventory** (spec R5) — compress the restatement, not the pause list. Keep the mode-routing table's closed-set mode values and the reference-path manifest anchors (SKILL.md:155 map is pinned by test_lifecycle_references_resolve).
- **Verification**: `just test-skill-design` and `python -m pytest tests/test_lifecycle_kept_pauses_parity.py tests/test_lifecycle_references_resolve.py` — pass if exit 0; AND net line count of SKILL.md decreased vs HEAD.
- **Status**: [ ] pending

### Task 3: Trim complete.md (s14, s12, s4)
- **Files**: skills/lifecycle/references/complete.md
- **What**: s14 finalize-artifacts commit (COMPRESS), s12 backlog-index-sync (COMPRESS), s4 push/PR (COMPRESS).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: candidates `complete.md s14/s12/s4`. Keep every verb+flag invocation (cortex-* commands, git steps) and the emission-ordering guarantees verbatim; compress surrounding rationale only.
- **Verification**: keep-list cortex-* command tokens still grep-present in the file AND file net-shrinks vs HEAD; `just test-lifecycle-state` exit 0.
- **Status**: [ ] pending

### Task 4: Trim criticality-matrix.md (s2, s3, s4, s5)
- **Files**: skills/lifecycle/references/criticality-matrix.md
- **What**: s2 Criticality-Override (COMPRESS), s3 Behavior-Matrix (COMPRESS), s4 Reading-lifecycle-state (COMPRESS), s5 seed→reconcile→gate ordering (LAZY_REF).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: candidates `criticality-matrix.md s2/s3/s4/s5`. This file is cited by lifecycle SKILL "Reading lifecycle state" and Plan/Specify — keep the `--field` invocation forms and matrix cell semantics; s5 LAZY_REF must leave a resolvable pointer to the ordering rule's canonical home.
- **Verification**: `python -m pytest tests/test_lifecycle_references_resolve.py` exit 0; `--field` invocation tokens still present; file net-shrinks.
- **Status**: [ ] pending

### Task 5: Trim backlog-writeback.md (s3, s5)
- **Files**: skills/lifecycle/references/backlog-writeback.md
- **What**: s3 Backlog-Status-Check (COMPRESS), s5 exit-2 handling (COMPRESS).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: candidates `backlog-writeback.md s3/s5`. Keep the canonical exit-2 rule anchor (other references point here), the `cortex-update-item`/`cortex-lifecycle-start-sync` invocations, and the close-path event ordering verbatim.
- **Verification**: `cortex-update-item` + `cortex-lifecycle-event` invocation tokens grep-present; file net-shrinks; `just test-lifecycle-state` exit 0.
- **Status**: [ ] pending

### Task 6: Trim orchestrator-review.md (s3, s4, s7, s12, s13)
- **Files**: skills/lifecycle/references/orchestrator-review.md
- **What**: s3 Protocol (COMPRESS), s4 Execute-Review (COMPRESS), s7 Fix-Agent-Prompt-Template (LAZY_REF), s12 Cycle-Cap (MERGE_DEDUP), s13 Constraints (DELETE).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: candidates `orchestrator-review.md s3/s4/s7/s12/s13`. s13 is a verified DELETE of the Constraints section (redundant); s7 LAZY_REF replaces the embedded fix-agent template with a resolvable pointer — confirm the pointer target exists. Keep the cycle-cap number and review-pass gate semantics.
- **Verification**: Constraints section removed (`grep -c '## Constraints' file` = 0); fix-agent pointer resolves; `python -m pytest tests/test_lifecycle_references_resolve.py` exit 0; file net-shrinks.
- **Status**: [ ] pending

### Task 7: Trim plan.md reference (s5, s9, s14, s19, file-compress)
- **Files**: skills/lifecycle/references/plan.md
- **What**: s5 Design-Approach (COMPRESS), s9 Task-Complexity-Classification (COMPRESS), s14 Code-Budget (COMPRESS), s19 Hard-Gate (MERGE_DEDUP), file-compress manifest-boilerplate/cross-section dedup.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: candidates `plan.md s5/s9/s14/s19/file-compress`. Keep the complexity-tier table's critical rule (trivial→turn-exhaustion), the (a)/(b)/(c) Verification format, and the Hard-Gate "no code in plans" directive. This is the file I am currently generating from — edit the reference, not this artifact.
- **Verification**: complexity table + (a)/(b)/(c) format + Hard-Gate directive grep-present; file net-shrinks; `just test-skill-design` exit 0.
- **Status**: [ ] pending

### Task 8: Trim competing-plans.md (s3, s4, s6, s8)
- **Files**: skills/lifecycle/references/competing-plans.md
- **What**: s4 Plan-Agent-Prompt-Template (COMPRESS), s8 route-on-verdict (COMPRESS), s6 synthesizer-dispatch (COMPRESS), s3 dispatch-plan-agents+model-resolution (COMPRESS).
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: candidates `competing-plans.md s3/s4/s6/s8`. Only reached on the `critical` Plan branch. Keep the model-resolution invocation and the verdict/confidence routing thresholds verbatim; compress the embedded prompt-template prose.
- **Verification**: model-resolution + verdict-routing tokens grep-present; file net-shrinks; `python -m pytest tests/test_lifecycle_references_resolve.py` exit 0.
- **Status**: [ ] pending

### Task 9: Trim review.md reference (s2, s3, s8, s9)
- **Files**: skills/lifecycle/references/review.md
- **What**: s2 Gather-Inputs (COMPRESS), s3 Launch-Review-Subtask (COMPRESS), s8 Process-Verdict (COMPRESS), s9 Auto-Apply-Requirements-Drift (COMPRESS).
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: candidates `review.md s2/s3/s8/s9`. Keep the verdict enum (APPROVED/CHANGES_REQUESTED/REJECTED), the review_verdict event emission, and the drift auto-apply gate condition verbatim.
- **Verification**: verdict enum + review_verdict event tokens grep-present; file net-shrinks; `just test-lifecycle-state` exit 0.
- **Status**: [ ] pending

### Task 10: Trim critical-review-gate.md (s3, s4)
- **Files**: skills/lifecycle/references/critical-review-gate.md
- **What**: s3 Non-Local-Seed-Tier-Rule (COMPRESS), s4 Run/Skip-Matrix (COMPRESS).
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: candidates `critical-review-gate.md s3/s4`. Keep the run-condition (`tier=complex AND criticality∈{medium,high,critical}`) verbatim — it is the actual gate other files depend on.
- **Verification**: run-condition string grep-present; file net-shrinks; `python -m pytest tests/test_lifecycle_references_resolve.py` exit 0.
- **Status**: [ ] pending

### Task 11: Trim small references batch A (discovery-bootstrap, load-requirements, refine-delegation)
- **Files**: skills/lifecycle/references/discovery-bootstrap.md, skills/lifecycle/references/load-requirements.md, skills/lifecycle/references/refine-delegation.md
- **What**: discovery-bootstrap s2/s4, load-requirements s1/s2, refine-delegation s2/s3/s5 — all COMPRESS. One commit (all three files + mirrors).
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: candidates in those three files (7 total). Keep the `cortex-lifecycle-create-index` invocation, the tag-selection protocol steps, and the `<REFINE_SKILL_MD>`/`<COMPLEXITY_ESCALATION_MD>` substitution-token names verbatim.
- **Verification**: create-index + substitution-token names grep-present across the three files; each file net-shrinks; `python -m pytest tests/test_lifecycle_references_resolve.py` exit 0.
- **Status**: [ ] pending

### Task 12: Trim small references batch B (complexity-escalation, post-refine-commit, parallel-execution)
- **Files**: skills/lifecycle/references/complexity-escalation.md, skills/lifecycle/references/post-refine-commit.md, skills/lifecycle/references/parallel-execution.md
- **What**: complexity-escalation s1/s2, post-refine-commit s2/s6, parallel-execution s1/file-compress — all COMPRESS. One commit.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: candidates in those three files (6 total). Keep the verb+flag invocation + three-way exit/stdout routing (complexity-escalation), the flag-check invocation (post-refine-commit), and the worktree-inspection invariant statement (parallel-execution) verbatim.
- **Verification**: exit-routing + flag-check + worktree-invariant tokens grep-present; each file net-shrinks; `python -m pytest tests/test_lifecycle_references_resolve.py tests/test_complexity_escalator.py` exit 0.
- **Status**: [ ] pending

### Task 13: Trim tiny references batch C (kept-pauses, wontfix, concurrent-sessions)
- **Files**: skills/lifecycle/references/kept-pauses.md, skills/lifecycle/references/wontfix.md, skills/lifecycle/references/concurrent-sessions.md
- **What**: kept-pauses s1 (COMPRESS preamble), wontfix s2 (COMPRESS), concurrent-sessions file-compress (MERGE_DEDUP s1–s3 aggregate). One commit.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: candidates in those three files. **kept-pauses.md must not change the parity-tested pause inventory** (spec R5) — compress preamble only. Keep the `.session` convention and wontfix verb invocation verbatim.
- **Verification**: `python -m pytest tests/test_lifecycle_kept_pauses_parity.py` exit 0; `.session` + wontfix tokens grep-present; each file net-shrinks.
- **Status**: [ ] pending

### Task 14: Integration gate — full suite + savings tally
- **Files**: (verification only — no edits)
- **What**: Run the full test suite, confirm every applied keep-list token survived, tally realized weighted savings before Review.
- **Depends on**: [13]
- **Complexity**: simple
- **Context**: This is the whole-batch checkpoint. Re-run keep-list survival greps across all 19 files; sum the `weighted_cost` of applied candidates for the savings report.
- **Verification**: `just test` — pass if exit 0 and all suites green; savings tally ≈ 8.6k weighted tokens reported.
- **Status**: [ ] pending

## Risks
- **reviewer-prompt s9 synthesizer coupling** (Task 1) — the single genuine correctness risk; mitigated by reading the synthesizer parse surface before trimming and isolating it as the first commit.
- **Mirror races** — foreclosed by the serial `Depends on` chain; do not parallelize.
- **kept-pauses / reference-resolve regressions** — guarded by per-task parity/resolve test gates (Tasks 2, 13, and the resolve suite throughout).
- **Concurrent session on `main`** — explicit-pathspec commits per task keep foreign staged files out.
