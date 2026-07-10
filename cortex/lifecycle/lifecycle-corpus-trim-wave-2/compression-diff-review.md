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
inline and adjudicated each finding. One finding (F1) was a confirmed regression and
was fixed structurally; two (F2, F3) were dismissed with rationale.

## Per-file verdict

| File | Task(s) | Verdict |
|------|---------|---------|
| `skills/lifecycle/SKILL.md` | 7, 10 | CLEAN (F1 carve-out restored) |
| `skills/lifecycle/references/backlog-writeback.md` | 7 | CLEAN (F1 carve-out restored) |
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

**Task 7 (`ac6fab64`) — the three named untouchables survived the collapse into verb calls
(the one lost sub-branch is F1, now fixed):**
- *Close/Continue decision semantics* — all arms preserved in `backlog-writeback.md`:
  `open`/`no_match` → proceed; `already_complete` → `AskUserQuestion` Close/Continue with
  "no AskUserQuestion (overnight) → default **Continue**, never auto-close" intact; **Close**
  → exit; **Continue** → proceed. The phase=none no-writes sub-branch was the F1 regression.
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
  ownership) under their "verify any code-behavior claim against actual code" condition (F2);
  §3b's full boolean seed-tier fail-safe condition intact (only the trailing rationale phrase trimmed).
- `research/SKILL.md` + `angle-templates.md`: `{INJECTION_RESISTANCE_INSTRUCTION}` placeholder,
  considerations-file reader contract, and the hybrid-angle selection rule all intact; only
  by-design duplicated descriptive phrasing removed.

## Findings and dispositions

**F1 — CONFIRMED REGRESSION → FIXED. Task 7 (`ac6fab64`) dropped the `phase=none` no-writes
carve-out from the Close path.**
Old `backlog-writeback.md` Close arm branched: `phase != none` → log completion + close
write-back + exit; **`phase = none` → exit immediately, create no artifacts, call no
`cortex-update-item`**. The rewiring collapsed Close to an unconditional
`cortex-lifecycle-finalize` → exit, and — compounding it — `cortex-lifecycle-enter` read
`backlog_status` but ran create-index / start-sync / init-ensure / `.session` *before* the
skill could decide, so an already-complete item created a lifecycle directory regardless. The
no-side-effect guarantee for a completed backlog item was lost.

*Fix (structural, not prose):*
- `cortex_command/lifecycle/enter.py` — `enter()` now returns
  `{state: "needs-decision", backlog_status: "already_complete", feature}` **before** any
  composed step when the item is `already_complete` and the new `--acknowledge-complete` flag
  is absent; the flag (caller-passed — the verb stays a dumb arg-actor per ADR-0019) drives the
  full composition on the Continue decision. `needs-decision` added to `KNOWN_STATES`.
- `skills/lifecycle/SKILL.md` Step 2 — routes on `needs-decision`: **Continue** re-runs the
  call with `--acknowledge-complete`; **Close** on `phase = none` exits immediately creating no
  artifacts and calling **no** finalize (no lifecycle dir exists), on any other phase runs the
  finalize Close arm.
- `skills/lifecycle/references/backlog-writeback.md` — Close arm made explicitly conditional:
  `phase = none` → exit, no artifacts, no finalize; other phases → `cortex-lifecycle-finalize`.
- Tests (`cortex_command/lifecycle/tests/test_enter.py`): no-side-effects test (composed
  primitives patched to fail loudly; asserts `cortex/lifecycle/` never created), acknowledge-
  proceeds test, CLI needs-decision + CLI `--acknowledge-complete` tests, and `needs-decision`
  added to the `KNOWN_STATES` reachability test.

*Fix evidence:* `test_enter.py` + `test_init_ensure.py`, `test_lifecycle_event_roundtrip.py`,
`test_lifecycle_kept_pauses_parity.py`, `test_lifecycle_invocation_grammar_parity.py`,
`test_dual_source_reference_parity.py`, `test_lifecycle_verb_deployment.py`,
`test_skill_section_citations.py` all green; `just check-contract` and `just check-parity`
exit 0 (E101 prose-vs-argparse clean — `--acknowledge-complete` is optional and matches the
argparse surface); kept-pauses anchor `backlog-writeback.md:7` still resolves to the
`AskUserQuestion` site; mirrors regenerated via `just build-plugin`.

**F2 — DISMISSED. `specify.md` §2b dropped the "File paths — verify the file exists…" and
"Function behavior — read the function…" verification bullets (Task 11).**
The umbrella condition "verify any code-behavior claim against actual code before writing it"
plus the retained §2b bullets (Git two-dot/three-dot, State ownership) carry the requirement;
the cut items were audited probably-safe generic guidance and are operator-approved under spec
R11's named refine safe-cut set. No condition lost.

**F3 — DISMISSED. `cortex-lifecycle-finalize` populates counters where the old prose said to
"omit `tasks_total`/`rework_cycles`" on the Close write-back.**
Verb-owned provenance enrichment: the load-bearing fields (`merge_anchor: "merge"` and the
idempotent-`feature_complete` guard, per spec R2) are preserved, and the downstream metrics
readers tolerate populated counters. The change is additive provenance, not a lost condition
or a changed cap.

## Additional candidates investigated (no action)

- **`research-phase.md` path-guard → pointer (Task 11).** `bc8f0df7` briefly pointed at the
  later-deleted `discovery-bootstrap.md`; the subsequent delegation-merge commit re-pointed it
  to `refine-delegation.md` (which carries the "never a substitute" rule), and the binary rule
  ("only a file at that exact path counts") stays inline. Clean at HEAD; no dangling pointer.
- **SKILL.md Step 2 route enumeration relocation (Task 7).** `implement-rework`/`complete`/
  `escalated` semantics moved to the resolver's `next` directive — the intended architecture
  per the spec's "MODIFIED: lifecycle Step 2 entry"; not a compression regression.
- **Nits (phrasing only, meaning identical):** orchestrator P5 "copy-paste-ready code" →
  "copy-paste code"; assorted descriptive tightenings. No condition, gate, cap, or literal affected.

## Bottom line

Findings: **1 confirmed regression (F1) — fixed and verified**; **2 dismissed with rationale
(F2, F3)**. After the F1 fix, every condition, gate, cap, retry limit, skip rule, and pinned
literal across the Task 7/9/10/11 diffs is preserved with identical meaning — inline, in an
extracted reference the change points to, or in the canonical downstream contract it delegates
to. No unresolved findings remain.

VERDICT: parity-confirmed
