# Specification: refine-default-interactive-not-overnight

## Problem Statement

`/cortex-core:refine` assumes the work will run overnight. The Specify interview frames
acceptance criteria around autonomous verifiability ("how do we test this if it runs
overnight?") and the skill's purpose/completion language asserts overnight as the default
execution mode. In practice the user often runs the refined work **interactively**, where
they are present to verify. This forces needless interrogation during speccing and the
wrong default. Fix: default the interview to interactive (user-present) framing, reframe
refine as execution-agnostic, and replace the overnight pressure with a single **advisory
warning at refinement-complete** that fires only when the ticket is a poor overnight
candidate.

**Acknowledged tension (handoff-readiness).** The overnight-framed interrogation this spec
removes was partly serving the project's handoff-readiness invariant ("a feature isn't
overnight-ready until criteria are agent-verifiable from zero context",
`cortex/requirements/project.md`). To avoid trading that enforcement for nothing, the
reframe is deliberately narrow: it removes only the *overnight framing and the
interrogation of interactive criteria* — it does **not** relax the interview's demand for
honest, non-vague acceptance criteria (the (a)/(b)/(c) format and its prefer-testable
ordering are unchanged). The advisory warning (R6) is the lighter, explicit replacement for
the autonomy pressure: instead of interrogating overnight-verifiability mid-interview, refine
surfaces it once, at completion, only when it matters.

## Phases

- **Phase 1: Interactive-default reframe** — make the shared Specify interview assume
  interactive verification (without relaxing criteria rigor), and make refine's purpose/
  framing execution-agnostic, without breaking routing, the L1 ratchet, or mirror parity.
- **Phase 2: Overnight-candidate completion warning** — add an advisory, hybrid-heuristic
  warning at refine's Step 6 that fires only for poor overnight candidates, scoped to the
  standalone `/refine` invocation.

## Requirements

Priority: R1–R6 are all must-have — each is load-bearing for the reframe or its guards
(routing, ratchet, mirror). There are no should-have items; optional scope (runner-side
gating) is listed in Non-Requirements.

1. **Interview assumes interactive verification, without relaxing criteria rigor.** In
   `skills/lifecycle/references/specify.md`: (a) the Open Decision Resolution clause that
   reads "the user is present during spec; implementation may run overnight without them"
   (L96) is rewritten to assume interactive, user-present execution while preserving the
   "ask the user directly rather than deferring to `## Open Decisions`" intent; (b) a short
   interview-posture note is added in §2 stating the interview assumes the present user
   verifies acceptance criteria in-session and does **not** interrogate how criteria would
   be verified autonomously/overnight. The `(a)`/`(b)`/`(c)` acceptance-criteria format at
   L126 — including its prefer-testable ordering and the `(c)` "Interactive/session-
   dependent … if a command check is not possible" fallback wording — is left **unchanged**
   (this preserves criteria rigor and keeps the orchestrator-review S1 checklist consistent;
   see Non-Requirements). Acceptance: `grep -c "may run overnight without them"
   skills/lifecycle/references/specify.md` = `0`; the new §2 posture note is present
   (`grep -ci "interactive" skills/lifecycle/references/specify.md` increases and the note
   names user-present in-session verification — reviewer-confirmed); `grep -c "if a command
   check is not possible" skills/lifecycle/references/specify.md` ≥ `1` (format unchanged).
   **Phase**: Interactive-default reframe

2. **refine's purpose/framing is execution-agnostic.** In `skills/refine/SKILL.md`, the
   purpose statement (L19) and Step 6 completion language (L188 "Ready for overnight
   execution.") no longer assert overnight as the assumed execution mode; the purpose reads
   that refine prepares a backlog item **for execution** (terse — not "interactive or
   overnight"). The `outputs` line (L9) and the L19 "the overnight runner can plan and
   execute it without further human input" framing are softened to not presume overnight.
   Acceptance: `grep -c "Prepares a single backlog item for execution" skills/refine/SKILL.md`
   ≥ `1`; `grep -c "Ready for overnight execution." skills/refine/SKILL.md` = `0`.
   **Phase**: Interactive-default reframe

3. **Routing keywords preserved AND sibling-disambiguation unbroken.** refine's L1 surface
   (description + when_to_use) still contains the substrings `refine backlog item`,
   `prepare for overnight`, `prepare feature for execution`, and `Clarify → Research → Spec`
   (overnight stays a discoverability keyword; only the *assumption* is removed). Because
   substring-preservation is necessary but not sufficient for routing — the now-generic
   "for execution" purpose phrase could broaden refine's match against routing-pressure
   cluster siblings (`dev`, `lifecycle`) — the sibling-disambiguation test must also pass.
   Acceptance: `python3 -m pytest tests/test_skill_routing_disambiguation.py -q` exits `0`
   AND the test consuming `tests/fixtures/skill_trigger_phrases.yaml` passes (`just test`
   exits `0` covers both). **Phase**: Interactive-default reframe

4. **L1 ratchet honored and re-capped.** After the reframe, `bin/cortex-measure-l1-surface`
   is re-run; if refine's measured surface decreased from `644`, `_BASELINES["refine"]` in
   `tests/test_l1_surface_ratchet.py` is lowered to the new measured value. Lowering banks
   the reduction as the new ceiling; a future *raise* (e.g. adding a trigger phrase) is not
   prohibited but gated behind a documented lifecycle-id'd re-cap rationale per the CLAUDE.md
   re-cap rule. Acceptance: `python3 -m pytest tests/test_l1_surface_ratchet.py -q` exits
   `0`, and the recorded budget equals the measured surface. **Phase**: Interactive-default reframe

5. **Both regenerated mirrors committed; parity holds.** R1 edits
   `skills/lifecycle/references/specify.md` and R2 edits `skills/refine/SKILL.md` — `just
   build-plugin` regenerates **both** mirrors: `plugins/cortex-core/skills/refine/SKILL.md`
   AND `plugins/cortex-core/skills/lifecycle/references/specify.md` (the latter is in
   `test_plugin_mirror_parity.py` scope and currently byte-identical). All edited canonical
   sources and both regenerated mirrors are committed together. Acceptance: `python3 -m
   pytest tests/test_plugin_mirror_parity.py -q` exits `0`. **Phase**: Interactive-default reframe

6. **Advisory overnight-candidate warning at completion, scoped to standalone `/refine`.**
   `skills/refine/SKILL.md` Step 6 (Completion) instructs refine to assess overnight-
   suitability from the approved `spec.md` and surface an advisory warning **only when the
   ticket is a poor overnight candidate**, listing the specific reasons. Hybrid heuristic:
   anchored on the mechanical signals — any acceptance criterion marked
   `Interactive/session-dependent`, and any unresolved item under `## Open Decisions` — and
   may additionally cite judgment reasons (needs network/credentials, requires human-visual/
   judgment verification, or exploratory/under-specified scope). When none apply, no warning
   is emitted. **Standalone-only guard:** the warning is emitted at refine's Step 6 only when
   `events.log` contains no lifecycle-written `phase_transition` events (standalone `/refine`);
   under `/cortex-core:lifecycle` delegation those rows are present and the warning is
   suppressed. The warning lives in refine's Step 6, **not** in the shared `specify.md`, so it
   never interrupts the interview. Phrasing is soft positive-routing (no MUST/CRITICAL/
   REQUIRED).

   *Acceptance — testable surface:* the Step 6 text names the mechanical anchor signals,
   states the warning is conditional/advisory, and names the no-`phase_transition` guard;
   `grep -ci "overnight candidate" skills/refine/SKILL.md` ≥ `1`.
   *Acceptance — behavioral surface (Interactive/session-dependent):* because Step 6 is
   model-interpreted prose, not code, the *firing decision and reason-list cannot be unit-
   tested*. It is verified at Review via a stated manual protocol: run the Step 6 suitability
   assessment against (i) a fixture spec containing an `Interactive/session-dependent`
   criterion and no open decisions → expect a warning citing it; (ii) a fixture spec with all
   `(a)`/`(b)` command-checked criteria and no open decisions → expect silence; (iii) a spec
   with an unresolved `## Open Decisions` item → expect the decision cited. The mechanical
   anchor is deterministic; the judgment-reason list is model-discretionary and therefore
   not reproducible verbatim across runs by design — only the *fire/no-fire* decision and the
   mechanical reasons are asserted. **Phase**: Overnight-candidate completion warning

## Non-Requirements

- **No runner-side gate.** The overnight runner (`cortex_command/overnight/batch_plan.py`)
  continues to select on `status: refined` alone. This feature does NOT make the runner
  skip, defer, or block poor overnight candidates — the warning is advisory to the human at
  refine time only.
- **No relaxation of the acceptance-criteria format.** The `(a)`/`(b)`/`(c)` format and its
  prefer-testable ordering in `specify.md` L126 are unchanged; consequently the orchestrator-
  review S1 checklist (`orchestrator-review.md:98`), which validates that format on every
  Specify run, is **not** touched and stays consistent. Only the overnight *framing* and the
  interrogation posture are removed, not the testable-criteria discipline.
- **No execution-mode branch in the interview.** `specify.md` assumes interactive for all
  callers (both standalone `/refine` and `/cortex-core:lifecycle` are user-present at spec
  time); no branch keyed on execution mode is added to the interview. (The R6 warning's
  standalone guard lives in refine's Step 6, not in the interview, so it does not contradict
  this.)
- **No overnight warning under full `/cortex-core:lifecycle`.** Under lifecycle the user is
  building interactively through Plan/Implement/Review and is the verifier throughout, so an
  overnight-suitability warning is not surfaced; R6's standalone guard enforces this. (A
  lifecycle feature later handed to overnight is an accepted edge — see Edge Cases.)

## Edge Cases

- **Standalone spec with no interactive criteria and no open decisions** → no warning emitted
  (good overnight candidate). Step 6 completes silently on the suitability check.
- **Standalone spec where every requirement is `Interactive/session-dependent`** → warning
  lists each as a reason; strong poor-candidate signal.
- **Standalone spec with unresolved `## Open Decisions`** → warning cites the unresolved
  decisions as a reason (these need a human, so overnight would stall).
- **Invoked under `/cortex-core:lifecycle`** → `events.log` carries lifecycle-written
  `phase_transition` rows; R6's guard suppresses the warning. Speccing is unaffected (the
  warning is never in the interview).
- **Standalone re-run on a slug that previously ran under lifecycle** → prior
  `phase_transition` rows are present, so the guard suppresses the warning even though this
  run is standalone. Accepted minor limitation (rare); the guard favors silence over a
  spurious warning.
- **Re-run of refine** (`spec.md` already exists) → suitability re-assessed against the
  current spec; the warning reflects the latest spec, not a stale one.

## Changes to Existing Behavior

- MODIFIED: `specify.md` interview posture → assumes interactive/user-present verification
  and does not interrogate overnight-autonomy; the `(a)`/`(b)`/`(c)` acceptance-criteria
  format is unchanged. Affects every lifecycle Specify run (standalone-refine and
  `/cortex-core:lifecycle` alike).
- MODIFIED: refine purpose/framing → "prepare a backlog item for execution" (execution-
  agnostic) instead of "for overnight execution".
- REMOVED: refine Step 6 "Ready for overnight execution." unconditional completion line.
- ADDED: refine Step 6 conditional advisory overnight-candidate warning, guarded to the
  standalone `/refine` path.

## Technical Constraints

- L1 surface ratchet: refine budget currently `644` (routing-pressure cluster, exempt from
  the ≤400 default); ratchet **down** to the new measured value if reduced. A raise is gated
  by a documented lifecycle-id'd re-cap rationale, not prohibited
  (`tests/test_l1_surface_ratchet.py`; re-cap rule in `cortex/requirements/project.md`).
- Routing: substring preservation (`skill_trigger_phrases.yaml`) is necessary but not
  sufficient; `tests/test_skill_routing_disambiguation.py` guards sibling collisions within
  the routing-pressure cluster and must pass.
- Mirror parity (`tests/test_plugin_mirror_parity.py`): **two** mirrors change — refine's
  SKILL.md and lifecycle's `references/specify.md`; both regenerate via `just build-plugin`
  and are committed with their canonical sources.
- Standalone/lifecycle discriminator for R6: standalone `/refine` never writes
  `phase_transition` events (`skills/refine/SKILL.md:155`); lifecycle writes them during
  delegation (`refine-delegation.md` Step 4). "No `phase_transition` rows in `events.log`" is
  the standalone signal the R6 guard keys on.
- MUST-escalation policy (CLAUDE.md): new warning instruction uses soft phrasing.
- Prescribe What/Why not How: describe the warning trigger and shape; leave judgment-reason
  evaluation to the model (its outputs are therefore not reproducible verbatim — see R6).

## Open Decisions

None. The warning heuristic (hybrid) and reframe scope (full-but-terse) were resolved with
the user during Clarify. The completion-warning site and standalone-only posture were
**revised after critical review**: the warning is placed in refine's Step 6 with an explicit
`phase_transition`-absence guard (rather than relying on an unverified assumption that
lifecycle bypasses Step 6), and the contradictory "no warning under lifecycle" / "no
branching" framing was reconciled by scoping the no-branch rule to the interview only.

## Proposed ADR

None considered.
