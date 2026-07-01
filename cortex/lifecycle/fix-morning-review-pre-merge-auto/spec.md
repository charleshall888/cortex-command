# Specification: Fix morning-review pre-merge auto-close ordering bug (#342)

## Problem Statement

`skills/morning-review/SKILL.md` Step 4 runs a full backlog-ticket auto-close **before** the
PR is merged (it precedes Step 5 Commit and Step 6 PR Merge), while `references/walkthrough.md`
§6b is the post-merge closer the protocol deliberately moved closure to — and §5 explicitly
calls the pre-merge close "a bug." The model reads two contradictory orderings of a
destructive action on every morning-review run. Research established this is not cosmetic: the
overnight runner writes `status: complete` to the **integration branch**, so home main reaches
`complete` only via the PR merge — which means the pre-merge Step 4 close does real work on
home main (marking the ticket complete + regenerating `index.md` before the merge, colliding
with the integration PR that touched the same files), and it is the **only** thing that
produces a false-complete on main when a merge is declined. Removing it single-sources closure
to the post-merge path (§6b), eliminates a merge-conflict/double-index-regen hazard, and makes
"leave unmerged tickets open" the correct automatic behavior. Beneficiary: every morning-review
run (correctness + one less contradiction the model must reconcile).

## Phases
- **Phase 1: Single-source closure post-merge** — remove the pre-merge close, relocate the sole
  closure reference to the post-merge position, migrate the exit-2 + no-confirmation handling,
  regenerate mirror.
- **Phase 2: Guard + closure-state surfaces** — add the absence-based regression test and the
  soft closure-state notes on the non-standard PR exits.

## Requirements

Priority (MoSCoW): Reqs 1–5 and 7 are **Must-have** — 1–3 are the core correctness fix, 4 is a
CI gate, 5 is the structural regression guard whose absence is exactly why this bug survived,
and 7 keeps a rare-but-real regression (introduced by Req 1 on the already-merged exit) from
being *silent*. Req 6 is **Should-have**: on the genuinely-unmerged exits, §6's existing
messaging already tells the operator the PR is unmerged and needs manual action (walkthrough §6
lines 457-458, 481, 483, 503, 505), so "silently losing closure" is already largely prevented;
Req 6 adds only the explicit "ticket remains open" clause as polish on that existing non-silence.

**Close-literal note (applies to Reqs 1 and 5):** the ticket-close command has **two live
spellings** of the same operation — the console form `cortex-update-item … --status complete`
and the module form `python3 -m cortex_command.backlog.update_item … --status complete` (used in
skill prose, e.g. `skills/lifecycle/references/complete.md`, and documented as a mutual
grep-evasion pair in `bin/.audit-bare-python-m-allowlist.md`). Every absence check MUST match
**both** — use a spelling-agnostic pattern such as `update[-_]item.*--status complete` (matches
`update-item` and `update_item`), never the console-only literal.

1. **(Must)** **Remove the pre-merge auto-close from SKILL.md Step 4**, collapsing it to a soft
   forward-pointer stub (mirroring walkthrough §5's own stub style) that carries **no** close
   literal in either spelling. Acceptance:
   `grep -crEi "update[-_]item.*--status complete" skills/morning-review/SKILL.md` = `0`
   (currently `1`). **Phase**: Single-source closure post-merge.

2. **(Must)** **Add the §6b closure reference at the post-merge position** so SKILL.md's body
   references the sole closer exactly once, after the merge step (today its only §6b mention,
   line 99, sits pre-merge inside Step 4; Step 6 references §6/§6a but not §6b). Acceptance:
   `grep -n "Section 6b" skills/morning-review/SKILL.md` returns **exactly one** line, and that
   line falls after the `### Step 6` / "PR Merge" heading in source order (no §6b reference
   remains before the merge step). **Phase**: Single-source closure post-merge.

3. **(Must)** **Migrate the Step-4-unique handling into walkthrough §6b — completely.** Two
   Step-4-unique items would otherwise be lost when Step 4 is removed:
   - **Exit-2 (ambiguous-slug) disambiguation.** §6b today documents a *closed* two-outcome
     enumeration ("exits 0 on success … and exits 1 silently if no item is found", walkthrough
     line ~568) and reports only `closed #ID` / `no ticket found`. Removing Step 4 (SKILL.md
     lines 113, 118) drops the exit-2 path. Migrate ALL of it: (i) amend §6b's exit-code
     enumeration so it no longer denies exit-2 exists, (ii) add the third `ambiguous slug` report
     state to §6b's per-feature reporting list, and (iii) preserve the **action** — surface the
     stderr candidate list and ask the operator to re-invoke with a disambiguated slug.
   - **No-per-feature-confirmation guardrail.** SKILL.md Step 4 line 97 ("No per-feature
     confirmation is needed") has no equivalent in §6b; carry a soft equivalent into §6b so the
     auto-close-without-prompting intent survives.

   Acceptance (non-vacuous — proves the report **state** and **action** migrated, not mere
   word-presence): over the §6b span (from `## Section 6b` to the next `## ` heading),
   (a) `grep -ic "ambiguous"` ≥ 1 **and** `grep -ic "candidate"` ≥ 1 (the disambiguation
   action, not just the word), and (b) §6b's exit-code enumeration line no longer reads as a
   closed "exits 0 … exits 1" pair with no exit-2 (manually verify the amended enumeration
   admits exit-2). **Phase**: Single-source closure post-merge.

4. **(Must)** **The `cortex-overnight` mirror matches canonical at feature completion.** The
   canonical sources are `skills/morning-review/`; the mirror is
   `plugins/cortex-overnight/skills/morning-review/` (the ticket's `plugins/cortex-core/…` path
   does not exist). Each phase's commit regenerates the mirror (per-commit discipline in
   Technical Constraints); this requirement is the terminal parity check. Acceptance: `just test`
   passes `test_dual_source_reference_parity.py` (mirror matches canonical); the pre-commit drift
   gate is clean. **Phase**: Guard + closure-state surfaces.

5. **(Must)** **Add an absence-based SKILL.md ordering regression test** (extend
   `tests/test_morning_review_status_close_ordering.py` or add a sibling). Assert:
   (a) **no close literal in either spelling** anywhere in SKILL.md — the test's close pattern
   MUST match both `update-item` and `update_item` forms (per the Close-literal note), not the
   existing console-only `CLOSE_LITERAL = "cortex-update-item"`;
   (b) **exactly one `Section 6b` reference in SKILL.md, and it is after the "PR Merge" step** —
   this folds Req 2's single-source invariant into the durable guard so an incompletely-relocated
   (lingering pre-merge) §6b reference is caught, anchored on the semantic "PR Merge" heading,
   **never** a step number and **not** a `gh pr merge` literal (SKILL.md contains none).
   Acceptance: the new test passes on the fixed SKILL.md and is demonstrated **discriminating** —
   it fails when a pre-merge close is reintroduced **in either spelling** (unfixed→red,
   fixed→green, fixed+reintroduced-console→red, fixed+reintroduced-module→red); `just test`
   exits 0. **Phase**: Guard + closure-state surfaces.

6. **(Should)** **Add a soft "ticket remains open" note to the genuinely-unmerged §6 exits** —
   **no-PR-found (§6 step 2), declined-merge (§6 step 7), and merge-failed (§6 step 6 failure)**.
   Not the draft-PR exits: draft means "zero-progress session … produced no merged features"
   (walkthrough §6 step 4), so there is no completed feature to strand there. The note's **novel
   datum** is that the feature's backlog ticket **remains open** (the work is on the integration
   branch, not main); soft declarative phrasing (no `MUST`/`CRITICAL`/`REQUIRED` tokens); prose
   only, no dedicated copy-pinning test (tautology risk). Acceptance (region-scoped + requires the
   novel clause, not the pre-existing "integration branch" text): for **each** of the three named
   exits, that exit's prose contains an explicit ticket-open clause
   (`grep -iE "ticket[s]? .*remain|remain[s]? open|not closed|stays? open"` present in the span of
   each named exit) — verify per-exit, not a single ≥1 over all of §6. **Phase**: Guard +
   closure-state surfaces.

7. **(Must)** **Add a verify-closure advisory to the "PR already merged" exit (§6 step 2).**
   Removing Step 4 (Req 1) removes the only closer that covered the already-merged exit today, so
   in the rare `BACKLOG_WRITE_FAILED` × out-of-band-merge intersection a completed feature can
   reach main with its ticket still non-terminal and §6b skips it — a *silent* un-closed ticket.
   This requirement keeps that loss non-silent (the actual observed-merge auto-close is deferred
   to the follow-up ticket). On the "PR already merged — main is up to date" exit, add a soft
   advisory prompting the operator to verify this session's completed-feature tickets are
   `complete` (they normally are, via the merge; a rare mid-session write failure could leave one
   open). Soft phrasing; no new close call added. Acceptance: the §6 already-merged exit prose
   contains a verify-tickets-closed advisory
   (`grep -iE "verify|check" … && "ticket|complete"` present at that exit). **Phase**: Guard +
   closure-state surfaces.

## Non-Requirements

- Does **not** revert the runner's mid-session `status: complete` write or build any
  status-revert mechanism — that write is committed to the integration branch and never reaches
  main on a declined PR, so there is no false-complete on main to revert (the pre-merge Step 4
  was the only source, and Requirement 1 removes it).
- Does **not** build a persistent pending-closure list or deferred-closure auto-fire
  (over-engineering per Solution horizon; no named follow-up requires it here).
- Does **not** re-add any close on the unmerged paths (Approach B is refuted — it re-creates the
  false-complete-on-decline defect and contradicts the ticket's Edges).
- Does **not** implement observed-merge auto-close for the "PR already merged out-of-band" exit
  (closing on a merge this review did not perform). Req 7 makes the rare write-failed loss on that
  exit *non-silent*; the actual auto-close (and the stranded-merged-work reconciliation, orphaned
  integration branches/PRs/worktrees, no re-pick backoff, and the cross-repo bare-numeric-close
  hazard) is **filed as a separate follow-up backlog ticket** (see Technical Constraints). This is
  a genuine scope boundary, not "existing behavior": removing Step 4 changes the already-merged
  exit from close-then-stop to stop-with-advisory.
- Does **not** change §6b's post-merge idempotence or the `update_item` terminal cascade (§6b's
  re-close on an already-`complete` ticket is verified idempotent-in-effect).
- Does **not** touch SKILL.md frontmatter (L1 surface ratchet is frontmatter-only; this is a
  body-only change).

## Edge Cases

- **`BACKLOG_WRITE_FAILED`, then normal in-review merge**: the runner's integration-branch write
  threw, so the ticket reaches the PR merge still non-terminal; §6b (which DOES run on an
  in-review merge) is the sole completer and closes it post-merge. Expected: §6b closes it — this
  is why §6b is kept, not removed.
- **`BACKLOG_WRITE_FAILED`, then out-of-band merge** (the intersection): the non-terminal ticket
  lands on main via the out-of-band merge, but §6 step 2 stops at "PR already merged" **before**
  §6b, so §6b never runs and the ticket stays open despite work being on main. Today's pre-merge
  Step 4 closes it; Req 1 removes that. Expected under this spec: Req 7's advisory surfaces the
  risk (non-silent); the automatic close is the follow-up ticket's job.
- **Declined merge / no PR found / merge failed**: the home-main ticket stays at its pre-session
  status (open); no close fires; Req 6's "ticket remains open" note surfaces. Expected: ticket
  correctly not closed, deferral visible.
- **Draft-PR (close or skip)**: zero-progress session ⟹ no completed features ⟹ nothing to close
  or strand; no note needed. Expected: no closure, no note.
- **PR already merged in-review (normal happy path)**: the merge brings `complete` onto main;
  §6b re-close on the already-`complete` ticket is idempotent-in-effect — no spurious
  `status_changed` event (`update_item.py:385` guards on change), parent-close and
  blocked-by-strip are idempotent, only the index regen re-runs harmlessly. Expected: safe no-op
  re-affirmation.

## Changes to Existing Behavior

- **MODIFIED**: morning-review no longer closes backlog tickets pre-merge (SKILL.md Step 4's
  close removed) → closure occurs only post-merge via walkthrough §6b.
- **MODIFIED**: on the genuinely-unmerged exits, home-main tickets now remain open (previously
  falsely closed pre-merge by Step 4) and a soft "ticket remains open" note is surfaced.
- **MODIFIED**: on the "PR already merged" exit, morning-review now stops with a verify-closure
  advisory instead of unconditionally closing (Step 4 previously closed here — the only closer for
  this exit, since §6 stops before §6b).
- **ADDED**: exit-2 ambiguous-slug handling (state + candidate-list action) and the
  no-per-feature-confirmation guardrail migrated into §6b; a structural absence-based SKILL.md
  ordering test.
- **REMOVED**: SKILL.md Step 4's pre-merge close block, including its three-arm
  `cortex-read-backlog-backend` routing (now solely in §6b). Note this block was **not** a pure
  §6b duplicate — its exit-2 report state and its no-per-feature-confirmation guardrail were
  Step-4-unique and are migrated by Req 3, not dropped.

## Technical Constraints

- Edit canonical `skills/morning-review/` only; regenerate the `cortex-overnight` mirror in the
  **same commit** (drift pre-commit hook + `test_dual_source_reference_parity.py`).
- Every close-literal absence check matches **both** the `update-item` (console) and `update_item`
  (module) spellings — see the Close-literal note above (`bin/.audit-bare-python-m-allowlist.md`).
- Soft declarative phrasing throughout; no new `MUST`/`CRITICAL`/`REQUIRED` tokens
  (MUST-escalation policy).
- Prefer structural enforcement for the merge-before-close sequential gate: the absence-based test
  (Req 5) is the guard, not prose alone; and its close pattern must be spelling-agnostic or the
  guard is a partial one (a module-form reintroduction would pass green).
- The change applies the existing convention **ADR-0004 / `project.md`: "merge (not PR-open) is
  the terminal event for Done"** — no new ADR.
- Test anchors: absence of the close literal (both spellings) + a semantic ("PR Merge") anchor;
  never a step number; SKILL.md contains no `gh pr merge` literal.
- File the separate follow-up ticket (observed-merge auto-close for the already-merged exit +
  stranded-merged-work reconciliation + cross-repo bare-numeric-close hazard) during Complete so
  the concern is not lost.
- Commit via `/cortex-core:commit`; imperative, ≤72-char subject.

## Open Decisions

None. (OQ1 stranded-work note → resolved: Reqs 6–7. OQ2 separate follow-up → Non-Requirements +
Technical Constraints. OQ3 structural approach → resolved: collapse-to-pointer + post-merge
reference, Reqs 1–2.)

## Proposed ADR

None considered. The closure-on-merge-only stance applies existing ADR-0004; no new
hard-to-reverse decision with a live trade-off is introduced.
