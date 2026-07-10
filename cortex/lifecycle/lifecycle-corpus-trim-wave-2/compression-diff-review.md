# Compression-Diff Adversarial Review (spec R13 constraint-compliance check)

Fresh clause-by-clause comparison of old→new text for every file touched by the
structural-rewiring and compression commits, hunting specifically for dropped
conditions, weakened gates, lost skip/scoping clauses, changed caps/retry limits,
and altered pinned literals — per the research finding that procedural-constraint
compliance degrades *before* task success, so parity is judged on conditions, not gist.

## Scope and method

Commits reviewed (old = `<sha>^`, new = `<sha>`), canonical (`skills/…`) sources only;
`plugins/cortex-core/…` are regenerated mirrors and were excluded:

| Task | Commit | Change class |
|------|--------|--------------|
| 7  | `ac6fab64` | Step 2 + backlog-writeback rewired onto the wrapper verbs |
| 9  | `ae226584` | orchestrator-review phase split (17-item checklists extracted) |
| 10 | `a8d27d54` | SKILL completion-rule collapse + situational trims |
| 11 | `bc8f0df7` | sub-skill safe cuts (refine / critical-review / research) |

Method: `git diff <sha>^..<sha> -- <path>` for every hunk, then verification that each
removed condition reappears — verbatim or exact-meaning — in the new file, in a new
reference the change points to, or in the canonical downstream contract it delegates to.
A fresh general-purpose adversarial agent was dispatched for the primary sweep; it
stalled mid-run, so the orchestrating builder completed the clause-by-clause sweep
inline and independently adjudicated every candidate finding below.

## Per-file verdict

| File | Task(s) | Verdict |
|------|---------|---------|
| `skills/lifecycle/SKILL.md` | 7, 10 | CLEAN |
| `skills/lifecycle/references/backlog-writeback.md` | 7 | CLEAN |
| `skills/lifecycle/references/orchestrator-review.md` | 9 | CLEAN |
| `skills/lifecycle/references/orchestrator-checklist-specify.md` (new) | 9 | CLEAN |
| `skills/lifecycle/references/orchestrator-checklist-plan.md` (new) | 9 | CLEAN |
| `skills/lifecycle/references/competing-plans.md` | 10 | CLEAN |
| `skills/lifecycle/references/review.md` | 7, 10 | CLEAN |
| `skills/lifecycle/references/plan.md` | 7, 9, 10 | CLEAN |
| `skills/lifecycle/references/kept-pauses.md` | 7, 10 | CLEAN |
| `skills/refine/SKILL.md` | 7, 11 | CLEAN |
| `skills/refine/references/specify.md` | 9, 11 | CLEAN |
| `skills/refine/references/clarify-critic.md` | 11 | CLEAN |
| `skills/refine/references/research-phase.md` | 11 | CLEAN |
| `skills/critical-review/SKILL.md` | 11 | CLEAN |
| `skills/critical-review/references/a-to-b-downgrade-rubric.md` | 11 | CLEAN |
| `skills/research/SKILL.md` | 11 | CLEAN |
| `skills/research/references/angle-templates.md` | 11 | CLEAN |

## Named-untouchable confirmations

**Task 7 (`ac6fab64`) — the three named untouchables survived the collapse into verb calls:**
- *Close/Continue decision semantics* — all four arms preserved in `backlog-writeback.md`:
  `open`/`no_match` → proceed (old "no match / status ≠ complete → skip, fall through");
  `already_complete` → `AskUserQuestion` Close/Continue, with "no AskUserQuestion (overnight)
  → default **Continue**, never auto-close" intact; **Close** → `cortex-lifecycle-finalize`
  → exit; **Continue** → proceed. The "never auto-closes" guard is stated on the verb.
- *Exit-2 rule* — "present the stderr candidates, ask the user to re-invoke disambiguated"
  preserved (now naming which verbs re-emit it from their `cortex-update-item` calls).
- *Backend 3-arm routing* — `cortex-backlog` → `cortex-update-item` unchanged; `none` →
  skip with one-line advisory; external tracker → best-effort per `backlog.instructions`,
  surfacing content it can't complete. All three arms verbatim in meaning.

**Task 9 (`ae226584`) — all 17 checklist items' conditions preserved across the split:**
- Every S1–S7 and P1–P10 condition, skip, gate, and scope clause carried into the two new
  checklist files with identical meaning. High-risk set verified: **S7** skip
  (`criticality=low AND tier=simple`), **P8** gate (`criticality = critical` when §1b ran,
  N/A otherwise), **P10** skip (skip on simple — last-phase Checkpoint is the contract),
  **P7** benign-vs-harmful nuance (verbatim), **S1/P4** binary-checkable definitions (now
  reference the shared-protocol "Binary-checkable" rule, which is preserved verbatim).
- Shared protocol pins intact: `--role orchestrator-fix`, "halt and escalate" window,
  criticality-matrix corrupted-state citation, "Max **2 review cycles per phase**" cap.
- `plan.md` §3a and `specify.md` §3a pointers correctly updated to load shared protocol +
  the one phase checklist (`orchestrator-checklist-plan.md` / `-specify.md`).

**Task 10 (`a8d27d54`) — the completion-rule collapse keeps every gate reachable:**
- SKILL.md's five inline per-phase gates were collapsed to "each phase reference owns that
  gate — read the current phase's reference." Each gate confirmed reachable in its reference:
  Specify `spec_approved`+`phase_transition` (`specify.md:143`), Plan `plan_approved`+
  `phase_transition` (`plan.md:122`), Implement "every task `[x]`, no approval"
  (`implement.md:111,123`), Review `review_verdict` APPROVED→Complete / cycle-2 escalation
  (`review.md:73,75`), Complete `feature_complete` emission (`complete.md:39`).
- `competing-plans.md`: `plan_comparison` v2 schema line byte-identical; the route-on-verdict
  conditions (`verdict ∈ {A,B,C}` AND `confidence ∈ {high,medium}` vs `low`/malformed), the
  verdict-C tie impossibility, and the graft/combine protocol all intact; only fallback
  phrasing tightened.
- `review.md`: only the Requirements-Drift observation sentence was reworded
  (`none`/`detected` conditions identical); the §4a protocol and Verdict-JSON contract are
  outside this commit's hunks (untouched).

**Task 11 (`bc8f0df7`) — every cut is an authorized duplicate; no pinned literal changed:**
- `clarify-critic.md` injection-defense sandwich intact (untrusted `<parent_epic_body>`
  markers + both "ignore embedded instructions" reminders); only the illustrative JSON
  example and a duplicate counts-only clause removed.
- `a-to-b-downgrade-rubric.md`: `## Trigger Definitions` and `## Worked Examples` byte-identical;
  the causal-link requirement survives in the kept "concrete failure mechanism" clause,
  Trigger 2, and all worked examples.
- `critical-review/SKILL.md` output-sections sentence removed as a true duplicate of the
  canonical `synthesizer-prompt.md`, which owns `## Objections/Through-lines/Tensions/Concerns`
  and the skip-empty rule.
- `specify.md` §2b keeps the codebase-specific gotchas (Git two-dot/three-dot, State
  ownership) under their "verify any code-behavior claim against actual code" condition;
  §3b's full boolean seed-tier fail-safe condition intact (only the trailing rationale phrase trimmed).
- `research/SKILL.md` + `angle-templates.md`: `{INJECTION_RESISTANCE_INSTRUCTION}` placeholder,
  considerations-file reader contract, and the hybrid-angle selection rule all intact; only
  by-design duplicated descriptive phrasing removed.

## Candidate findings — investigated and dismissed

**F1 — `research-phase.md` path-guard compressed to a pointer (Task 11).**
Old text stated the rule inline ("a backlog item's `discovery_source`/`research` field is
Clarify background, never a substitute"); `bc8f0df7` replaced it with a pointer that, at that
commit, named the later-deleted `discovery-bootstrap.md`.
*Disposition: DISMISSED at HEAD.* The subsequent delegation-merge commit re-pointed it to
`refine-delegation.md` (which exists and carries the Refine Starting-Point Rules, including the
"never a substitute" rule). No reference to `discovery-bootstrap.md` remains anywhere in
`skills/`, and the operative binary rule ("only a file at that exact path counts") is still
stated inline in `research-phase.md`. Meaning reachable; no dangling pointer.

**F2 — `critical-review/SKILL.md` dropped the Step 2d "Output sections … bullets only, skip
empty sections" sentence (Task 11).**
*Disposition: DISMISSED.* `synthesizer-prompt.md` — the verbatim canonical prompt the
synthesizer actually executes — defines `## Objections/Through-lines/Tensions/Concerns` and the
zero-count/skip-empty behavior. The SKILL sentence was a duplicate description; its removal is
the exact cut R11 authorizes.

**F3 — `a-to-b-downgrade-rubric.md` dropped "A-class status requires a concrete causal link…"
(Task 11).**
*Disposition: DISMISSED.* Exactly the R11-named opening-paragraph duplicate. The causal-link
requirement is preserved in the retained "ratify as A when the argument names a concrete failure
mechanism" clause and is fully specified by the untouched Trigger Definitions and Worked Examples.

**F4 — Task 7 SKILL.md Step 2 dropped the inline route enumeration (`implement-rework`,
`complete`, `escalated` semantics).**
*Disposition: DISMISSED.* Relocated to the resolver's `next` directive contract ("act on `next`,
don't re-derive it"), the intended architecture per the spec's "MODIFIED: lifecycle Step 2 entry"
change. Not among the three named untouchables (close/continue, exit-2, 3-arm), all of which survived.

**F5 — Task 7 backlog-writeback Close path dropped the old `phase=none` → "create no artifacts,
call no `cortex-update-item`" sub-branch.**
*Disposition: DISMISSED.* Superseded by the enter-verb composition ordering: `cortex-lifecycle-enter`
runs create-index (skip-if-exists) before reporting `backlog_status`, so the old "no directory yet"
guard is architecturally moot — a documented behavior change (spec Edge Cases: "Enter verb on
resume: create-index is skip-if-exists"), not a compression regression. The Close action itself
(finalize → mark complete `session_id=null` → idempotent `feature_complete` → exit) is preserved.

**Nits (phrasing only, meaning identical, no action):** orchestrator P5
"copy-paste-ready code" → "copy-paste code"; numerous descriptive tightenings across SKILL.md,
competing-plans.md, review.md, and the research skill. No condition, gate, cap, or literal affected.

## Bottom line

REGRESSION-severity findings: **0.** Every condition, gate, cap, retry limit, skip rule, and
pinned literal across the Task 7/9/10/11 diffs is preserved with identical meaning — inline, in
an extracted reference the change points to, or in the canonical downstream contract it delegates
to. All five candidate findings were investigated against the files and dismissed with rationale.

VERDICT: parity-confirmed
