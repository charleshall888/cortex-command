# Research: Fix morning-review pre-merge auto-close ordering bug (#342)

## Epic Reference

This is item **R7** of epic **#340** ("Core-skill efficiency survivors of the post-#336
adversarial audit"); epic research lives at
`cortex/research/skill-efficiency-remaining-work/research.md`. The epic frames R7 as *the
correctness fix* of the survivor set: a live contradiction between two orderings of a
destructive action, valued above its near-zero byte count. This artifact is scoped to THIS
ticket only and does not reproduce the epic's cross-ticket content.

## Summary (read first)

The fix the ticket asks for — **remove the stale pre-merge auto-close from
`skills/morning-review/SKILL.md` Step 4 so backlog-ticket closure happens in exactly one
place, post-merge (walkthrough §6b)** — is correct and worth doing. Research confirmed the
line-level mechanics and, through an adversarial pass, corrected a mid-investigation
scope-inversion that would have mis-scoped the fix. The net verified understanding:

- The overnight **runner** writes `status: complete` mid-session, **but to the integration
  worktree's backlog, committed to the integration branch — NOT home main**
  (`orchestrator.py:276` + `runner.py:619-661`). Home main's ticket reaches `complete` only
  when the integration PR merges.
- Therefore the **current pre-merge Step 4 close does real work on home main** (it marks the
  ticket `complete` and regenerates `index.md` on main *before* the PR merges), and is the
  **only** thing that produces a false-complete on main when a merge is later declined. It
  also creates a **merge-conflict / double-index-regen hazard** against the integration PR
  (which touched the same files). Removing it fixes both — this is correctness work, not a
  cosmetic prose de-duplication.
- On declined / no-PR paths, once Step 4 is gone the home-main ticket **correctly stays
  open automatically** (the runner's `complete` is stranded on the abandoned integration
  branch and never reaches main). No advisory or status-revert is needed to *achieve*
  "leave open" — it is the default once the premature close is removed. This reconciles the
  ticket Role's "still close their tickets somewhere / rather than silently losing closure":
  there is no closure to lose on those paths (not on main = not done); the genuine residual
  is **stranded merged work**, a separate concern.
- **§6b stays the sole (post-merge) closer.** It is a genuinely load-bearing backstop for
  the rare `BACKLOG_WRITE_FAILED` case (runner's integration-branch write threw), and it is
  idempotent-in-effect on the happy path.

Recommended shape: **collapse Step 4 to a forward-pointer** (the ticket's own word) + add a
**§6b closure reference at the post-merge position** (SKILL.md's only §6b mention today sits
pre-merge inside Step 4); **migrate the exit-2 ambiguous-slug handling into §6b**; add an
**absence-based** SKILL.md ordering test; regenerate the **`cortex-overnight`** mirror.

## Codebase Analysis

**Files that change (canonical only; mirror auto-regenerates):**
- `skills/morning-review/SKILL.md` — Step 4 "Auto-Close Backlog Tickets" is lines **95–120**
  (heading 95; body ends 120; Step 5 heading at 122; Step 6 at 137–141). This is the stale
  pre-merge close.
- `skills/morning-review/references/walkthrough.md` — §5 stub (433–439), §6 (443–507, the
  unmerged sub-paths), §6b (535–591, the sole closer). §6b needs the exit-2 handling added
  (see below); the unmerged sub-paths are candidate advisory attach points.
- `tests/test_morning_review_status_close_ordering.py` — extend to cover SKILL.md (see Test
  section).
- **Mirror:** `plugins/cortex-overnight/skills/morning-review/` regenerates via
  `just build-plugin` (justfile:588–618; morning-review is under the `cortex-overnight`
  manifest, `SKILLS=(overnight morning-review)`), gated by `.githooks/pre-commit` Phase 2–4.
  **Correction:** the ticket's touch-point `plugins/cortex-core/skills/morning-review/` is
  **wrong — that path does not exist.** `diff -rq` shows the cortex-overnight mirror
  currently matches canonical (no pre-existing drift). Edit canonical only.

**Verified mechanics:**
- SKILL.md references "Section 6b" **exactly once**, at line **99**, inside stale Step 4.
  Step 6 (137–141) references §6 and §6a but **not §6b** — so deleting/collapsing Step 4
  without adding a post-merge §6b pointer leaves SKILL.md's body with **zero** reference to
  the sole closer.
- §6b closes **"the same list as Section 2"** (current session only, line 557) and skips
  when "the merge was declined, skipped, or the PR was already merged/closed before this
  review" (537–540). There is **no automatic retroactive-closure path** for a
  declined-then-later-merged feature; morning-review reads only the current session's report.
- **Runner writes to the integration branch, not main** (the decisive fact):
  `outcome_router.py:378` `_OVERNIGHT_TO_BACKLOG["merged"] = {"status": "complete"}`, written
  via `_write_back_to_backlog(name, "merged", …)` on the merge-success path
  (`outcome_router.py:713`) when a feature's `pipeline/{name}` branch merges into the session
  integration branch. But `orchestrator.py:276` sets the backlog dir to the **integration
  worktree** (`{worktree_path}/cortex/backlog`), and `runner.py:619-661`
  (`_commit_followup_in_worktree`) commits it **on the integration branch** ("so the
  follow-ups land on the integration branch, not the home repo"). Home main gets `complete`
  only via the PR merge.
- `update_item.py:404` fires the terminal cascade (`_remove_uuid_from_blocked_by` +
  `_check_and_close_parent`) whenever `new_status ∈ TERMINAL_STATUSES`, **regardless of
  change**; the status-changed *event* is guarded by `!= old_status` (line 385). On an
  already-`complete` ticket the cascade re-runs but is **idempotent-in-effect** (parent
  already-terminal short-circuits at 284–285; blocked-by re-strip is a no-op; only the index
  regen re-runs). So §6b post-merge is a safe no-op re-affirmation on the happy path.
- Exit semantics of `cortex-update-item … --status complete` (`update_item.py`, console
  script `cortex-update-item = …:main`): exit 0 success, exit 1 not-found, exit 2 ambiguous
  (candidate list on stderr). **Gap:** §6b (walkthrough:568) documents only exit 0/1
  ("exits 1 silently if no item is found"); **SKILL.md Step 4 (113/118) is the only place
  documenting the exit-2 ambiguous-slug disambiguation.** Removing Step 4 regresses that
  unless it is **added** into §6b.
- Stale claim: SKILL.md:109 "Unpadded IDs return 'Item not found'." The resolver
  (`resolve_item.py` `_resolve_numeric`) is padding-agnostic — the claim is stale. Moot once
  Step 4's prose is removed.
- Backend routing (`cortex-backlog` / `none` / external via `cortex-read-backlog-backend`) is
  duplicated in Step 4 (99) and §6b (542–555); collapsing removes the duplicate, leaving §6b
  the single owner.

## Web Research

Internal-tooling topic; prior art applies by analogy, strongest first:
- **GitHub's merge-gated issue auto-close** is the direct product precedent: closure fires on
  the **merge** event, single place, single trigger, opt-out default. Exactly the "gate the
  destructive/finalizing action on the confirming event" shape this fix restores.
- **DRY / single-source-of-truth** and the runbook anti-pattern "different team members
  performing the same process with different steps/outcomes; letting runbooks drift out of
  sync" (AWS Well-Architected OPS07-BP03) name the two-places contradiction.
- **"Premature completion"** (agent anti-pattern literature): gate "done" on **observable
  external state** (merge), not an internal signal (a PR merely existing) — and enforce it
  **structurally**, not via prose. Directly backs the SKILL.md structural test guard.
- **Fail-loud / no silent no-ops**: "make the absence of expected behavior as visible as the
  presence of unexpected behavior" — supports a *visible* stranded-work surface over a silent
  skip, but see the Adversarial section for why the surface must target the **right**
  condition.
- A persistent deferred-confirmation queue (rejected Approach C) is a real HITL pattern but
  requires durable checkpoint/resume machinery — the heavier choice, unjustified here.

## Requirements & Constraints

- **"Structural separation over prose-only enforcement for sequential gates"** (CLAUDE.md):
  this is a merge-before-close sequential gate; the established idiom is the existing
  ordering test. Extending it to SKILL.md is the aligned move — a structural guard, not more
  prose. The existing test is the precedent.
- **MUST-escalation policy (post-4.7):** author the pointer/advisory in **soft declarative
  phrasing** mirroring §6b's existing "Skip this section entirely if …" idiom. Do **not**
  introduce new `MUST`/`CRITICAL`/`REQUIRED` tokens — that trips the evidence-artifact +
  effort-first obligation for zero benefit.
- **Prescribe What/Why, not How:** state the outcome/intent of the pointer and (if adopted)
  the stranded-work note; do not script exact wording machinery.
- **Solution horizon / ADR-0004:** "Merge (not PR-open) is the terminal event for Done" is an
  **existing durable convention**; this fix *applies* it to one skill. A persistent
  pending-closure or active-revert mechanism is over-engineering for a single-edge chore with
  no named follow-up — file separately if operators later demonstrate a real pattern.
- **Dual-source mirror:** edit canonical `skills/morning-review/` only; regenerate the
  `cortex-overnight` mirror in the **same commit** (drift pre-commit hook +
  `test_dual_source_reference_parity.py` will otherwise fail).
- **L1 surface ratchet** (`test_l1_surface_ratchet.py`): frontmatter-only (measures
  `description` + `when_to_use` bytes; morning-review row = 320B). A **body-only** change is
  exempt — do not touch frontmatter.
- **kept-pauses parity**: scoped to `skills/lifecycle` + `skills/refine` only; morning-review
  is out of scope and the fix adds no `AskUserQuestion` site.

## Tradeoffs & Alternatives

The core fix (remove pre-merge Step 4; §6b sole post-merge closer) is settled. The
unmerged-path closure decision, re-evaluated under the corrected integration-branch model:

- **A — "Leave open" (automatic) + optional stranded-work note.** Once Step 4 is removed,
  declined/no-PR tickets stay open on home main **for free** (the runner's `complete` never
  reached main). Correctness holds with zero new state. The only open choice is whether to
  add a lightweight **fail-loud note** naming the integration branch and that its work is not
  on main / tickets remain open. **Recommended.**
- **B — Still auto-close on unmerged paths** (literal reading of Role's "close somewhere"):
  **refuted.** Under the corrected model this would *re-introduce* a false-complete on main
  for work that never merged — the exact defect being removed. Rule it out explicitly in the
  spec so an implementer cannot satisfy the Role's literal words by re-adding closes.
- **C — Persistent pending-closure list** auto-closing on a later confirmed merge: real but
  **disproportionate** (new durable state + reconciliation across sessions + rewiring the
  "PR already merged → stop" branch). Fails the Solution-horizon test; file separately only
  on demonstrated need.
- **D — Leave open silently, no surface at all:** the ticket Role's intent argues against
  silence; under the corrected model the "loss" is *stranded work*, not lost closure — so if
  any surface is added, target that (see Adversarial). Bounded out otherwise.

**Structural placement:** **collapse Step 4 to a forward-pointer** (matches the ticket's
"collapse it to a pointer" and walkthrough §5's own stub precedent; avoids renumbering
Steps 5/6) **and** add the operative **§6b closure reference to the post-merge step** (Step 6
/ after the §6a mention) so SKILL.md's sole §6b reference sits post-merge. An in-place stub
that *is* the closure reference would leave it textually pre-merge — avoid that; the stub
points forward, the real reference lands post-merge. (Delete+renumber is a valid but more
fragile alternative and contradicts the ticket's language.)

## Test & Regression-Guard Design

- **Current gap:** `tests/test_morning_review_status_close_ordering.py` inspects **only**
  `walkthrough.md` (`WALKTHROUGH` constant, lines 16–18) and **passes today with the bug
  live** (verified by running it — 3 passed). It cannot see SKILL.md Step 4.
- **The robust SKILL.md guard is an ABSENCE assertion, not a step-number anchor.** SKILL.md
  contains no `gh pr merge` literal (only walkthrough does), and post-fix contains no
  `cortex-update-item … --status complete` literal at all (closure fully delegated to §6b).
  So assert: **`cortex-update-item … --status complete` does NOT appear anywhere in
  SKILL.md**, plus a **§6b reference appears after the PR-merge step** anchored on **semantic
  text** ("PR Merge" heading / the `Section 6b` token), **never a step number** (a future
  renumber must not silently break or vacuously pass the guard).
- **Discrimination validated (three-state):** today → red (close literal present in Step 4 at
  ~105–106); fixed → green (no close literal); fixed + reintroduced close → red. A guard that
  cannot fail on the exact bug is vacuous; this one flips correctly.
- **Advisory presence → leave prose-only.** Pinning the exact advisory copy is a tautology
  (same author writes sentence + assertion). The load-bearing invariant (no close on the
  unmerged path) is already covered by the absence assertion above. At most, extend the
  *existing* `skip_gate_phrases` list with a *category* of deferral synonyms — not a pinned
  sentence.
- **§6b anchor drift-guard** (`test_skill_section_citations.py`): the §6b reference is a
  within-skill cross-ref, not cited by Python/prompt code, so a full citation pin is
  **optional/nice-to-have, not blocking**.
- **Mirror parity** (`test_dual_source_reference_parity.py`, includes cortex-overnight
  morning-review) will fail unless the mirror is regenerated in the same commit.

## Downstream Blast-Radius & Closure-Semantics System Effects

- **Report "Completed Features" = `state.features[name].status == "merged"`** (report.py:743
  ← map_results.py:94), structurally paired with the runner's `merged`→`complete` write-back.
  But that write lands on the **integration branch**, so "report-complete" and
  "home-main-ticket-complete" are decoupled until the PR merges.
- **Integration model is all-or-nothing per session** (confirmed): one integration branch,
  one `gh pr create --base main` at session end (runner.py:2234); a decline/no-PR applies
  uniformly to every completed feature. No partial-merge exists.
- **Re-pick:** `ELIGIBLE_STATUSES` includes `backlog/ready/in_progress/implementing/refined`;
  a ticket left non-`complete` on main after a declined session is fully re-selectable next
  session (the `_is_pipeline_branch_merged` exclusion fails open once the pipeline branch is
  deleted post in-session merge). **Desirable** for transient causes (runner crash, draft),
  **potentially wasteful** for a genuine decline — no "declined, don't redo" signal exists;
  orphaned branches/PRs/worktrees can accumulate.
- **Scanner mismatch is a non-issue:** `scan_lifecycle.py` already special-cases
  "events complete + backlog non-terminal" (the "Complete-no-PR exclusion", 965–990) —
  suppressed from the live warning, best-effort diagnostic only.
- **Cross-repo latent hazard (for the separate ticket):** morning-review's close runs a
  bare-numeric `cortex-update-item {backlog_id}` against **home** `cortex/backlog/` with no
  per-feature repo routing; for cross-repo features this could hit the wrong home item or
  none. Not introduced by #342, but worth recording.

## Adversarial Review

The adversarial pass **refuted a mid-investigation scope-inversion** (that the runner's
`complete` made morning-review's close redundant on main) by finding the runner writes to the
**integration worktree/branch, not main** (`orchestrator.py:276`, `runner.py:619-661`). What
survived and what it changed:

- **Redundancy claim: false for the common pre-merge path.** Home main is at its pre-session
  status at Step 4 time, so Step 4 does real work. Removing it is not a no-op.
- **#342 is not vacuous:** pre-merge Step 4 writes `complete` + regenerates `index.md` on
  main, then Step 6 merges an integration PR that touched the same files → a real
  **merge/rebase-conflict + double-index-regen hazard**. Removing Step 4 eliminates it.
- **"Inverse bug" is backwards:** on a declined PR the runner's `complete` + cascade are
  **stranded on the abandoned integration branch, never reaching main** — home main correctly
  stays non-complete. The *only* current source of false-complete-on-main under a decline is
  **the pre-merge Step 4 itself** — precisely what the fix removes. The mid-session write is
  **intended optimistic design** (ADR-0004; `map_results._TERMINAL_STATUSES` includes
  `merged`; report renders `merged` as Completed).
- **Fail-loud warning: retarget or omit.** A "false-complete on unmerged paths" warning fires
  on a state the fix *removes* → noise. If any surface is added, target the genuinely-lossy
  condition: **"N features merged to integration branch X but the PR was declined/absent —
  their work is stranded on X and their home-main tickets remain open."** The report already
  carries adjacent surfaces (report.py:583–587 "Unreviewed merges preserved"; 1313–1318
  "on the integration branch — do NOT re-run"; §6 step 7 "PR left open — merge manually").
- **Test anchor:** do **not** anchor on a step number (the earlier `### Step 6` proposal
  self-contradicts a renumber); use the **absence** assertion + semantic anchor above.
- **Surviving confirmations:** §6b as sole post-merge closer + its `BACKLOG_WRITE_FAILED`
  backstop is load-bearing; mirror-path correction; no `gh pr merge` in SKILL.md; soft
  phrasing / no new MUST; L1 body-exempt; exit-2 handling must migrate into §6b; the
  stranded-work + cross-repo-close concerns belong in a separate ticket.

## Open Questions

1. **Stranded-work surface — include or omit? (scope/preference — for the operator.)** Once
   Step 4 is removed, declined/no-PR tickets correctly stay open with no code change. Should
   #342 additionally add a **lightweight, soft-phrased note** on the declined / no-PR / draft
   Section-6 exits — naming the integration branch and that its work is not on main and its
   tickets remain open (the actionable, correctly-targeted form of the ticket Role's
   "rather than silently losing closure") — or rely on the report's existing adjacent
   surfaces and keep #342 minimal (remove Step 4 + relocate pointer + migrate exit-2 + test +
   mirror)? **Recommendation: include the minimal note** — it is the correct residue of the
   Role's intent, cheap, and soft-phrased; it does **not** build revert machinery.

2. **Separate follow-up ticket — confirm split.** *Deferred: to be filed as a separate
   backlog item, not resolved in #342.* Stranded merged work on declined/abandoned
   integration branches (orphaned commits/PRs/worktrees; no re-pick backoff) and the
   cross-repo bare-numeric-close hazard are real but out of #342's scope per Solution horizon
   (no named follow-up requires building it here; #342 is a single-skill ordering fix). The
   spec should name this follow-up so the concern is not lost.

3. **Structural approach — collapse-to-pointer vs delete+renumber.** *Deferred: a spec-level
   drafting decision, recommendation recorded.* Recommend **collapse Step 4 to a
   forward-pointer** + add the §6b closure reference to the post-merge step (matches the
   ticket's "collapse it to a pointer" language and walkthrough §5's precedent; avoids
   fragile renumbering). Spec will finalize.
