# Specification: review-has-no-recovery-path-for

## Problem Statement

`cortex-lifecycle-register-artifact` records that a lifecycle artifact exists without ever checking that
it does. When a dispatched reviewer finishes but never writes `review.md` — an observed and recurring
failure, seen in a consumer lifecycle on 2026-08-05 and four more times on 2026-08-07 including three
during this ticket's own refine — the verb appends `review` to `index.md`'s `artifacts:` array and exits
0. The lifecycle then carries a false claim about its own history: every downstream reader of `index.md`
believes a review exists, and the interactive phase can reach `complete` having produced nothing. This
spec makes the verb refuse to record what is not there, and gives the review phase a defined response
when it happens.

## Phases

- **Phase 1: Verb gate** — `register_artifact` refuses to register an absent or empty artifact.
- **Phase 2: Review-phase response** — `review.md` §2 permits resuming the idle reviewer; §3 defines the
  missing-artifact response.

Phase 1 is independently valuable and ships the enforcement; Phase 2 is desirable but not load-bearing
(the gate does not depend on prose reading anything), and is separable because it must be paid for out of
a zero-headroom byte ratchet.

## Requirements

1. **Refuse to register a missing artifact.** `register_artifact` returns the existing `error` state with
   a diagnostic `message` naming the expected path, and leaves `index.md` byte-unchanged, when the named
   artifact file does not exist. **Acceptance**: in a lifecycle dir containing `index.md` with
   `artifacts: []` and no `review.md`, `cortex-lifecycle-register-artifact --feature <f> --artifact review`
   emits JSON with `"state":"error"`, and `index.md` is byte-identical before and after (`cmp` exits 0).
   **Phase**: Verb gate

2. **Treat an empty artifact as missing.** A zero-byte artifact file is refused identically, matching the
   established idiom at `skills/refine/references/research-phase.md:23` ("exists and is non-empty").
   **Acceptance**: same as R1 with `review.md` created via `touch`; `"state":"error"`, `index.md`
   unchanged. **Phase**: Verb gate

3. **Resolve the artifact beside `index.md`.** The checked path is `index_path.parent / f"{artifact}.md"`,
   so the check follows whichever root resolved `index.md` and remains correct under the `index_path=`
   injection the test suite uses. **Acceptance**: with `index_path` injected as a `tmp_path` subdirectory
   whose name does not match the feature name, creating the artifact file beside that injected index
   yields `"state":"registered"`; creating the file only under a cwd-derived `cortex/lifecycle/{feature}/`
   path (with nothing beside the injected index) yields `"state":"error"`. **Phase**: Verb gate

4. **No new state value, and no protocol bump.** `KNOWN_STATES` is unchanged and `PROTOCOL_VERSION`
   remains 3. **Acceptance**: `grep -n 'KNOWN_STATES = ' cortex_command/lifecycle/register_artifact.py`
   still shows `("registered", "already-present", "no-index", "error")`; `grep -n 'PROTOCOL_VERSION = '
   cortex_command/lifecycle/protocol.py` shows `3`; `skills/build/references/protocol-expectation.txt`
   still `min=3` / `max=3`; `tests/test_protocol_parity.py` passes.
   **(preservation invariant — passes before the change; guards regression)** **Phase**: Verb gate

5. **Exit code contract preserved.** `main()` still returns 0 in all cases, per the module docstring's
   "always emits JSON and exits 0" contract shared with the sibling verbs. **Acceptance**: the R1 command
   exits 0 (`echo $?` = 0) while reporting `"state":"error"`.
   **(preservation invariant — passes before the change; guards regression)** **Phase**: Verb gate

6. **The overnight path is untouched.** No pipeline module gains a dependency on this verb.
   **Acceptance**: `grep -rn 'register_artifact' cortex_command/pipeline/ cortex_command/overnight/`
   returns no matches.
   **(preservation invariant — passes before the change; guards regression)** **Phase**: Verb gate

7. **Existing behaviour preserved on the happy path.** A present, non-empty artifact registers exactly as
   before, including skip-if-present idempotency and the `updated:` bump. **Acceptance**: the 16
   pre-existing tests in `cortex_command/lifecycle/tests/test_register_artifact.py` pass once each creates
   its artifact file; no assertion about `registered` / `already-present` / `no-index` semantics is
   weakened. **(preservation invariant — passes before the change; guards regression)** **Phase**: Verb gate

8. **Refusal precedence over `no-index`.** When `index.md` is itself absent the verb still returns
   `no-index` — the existing state — rather than the new refusal, so a missing index remains
   distinguishable from a missing artifact. **Acceptance**: with neither file present, `"state"` is
   `"no-index"`. **(preservation invariant — passes before the change; guards regression)** **Phase**:
   Verb gate

9. **§2 single-writer rule admits resumption.** `skills/build/references/review.md` §2's closed writer
   list is amended so resuming the original reviewer is a permitted way for `review.md` to come to exist,
   alongside the three existing re-dispatches. **Acceptance**: `Interactive/session-dependent: the
   mechanism is SendMessage to a live agent, which cannot be exercised from a test.` **Phase**:
   Review-phase response

10. **§3 defines the missing-artifact response.** `review.md` §3's missing-drift sentence is rewritten to
    cover an absent *file* as well as an absent *section*, so its remediation is no longer the incoherent
    "read the existing file and append it" for a file that was never written. **Acceptance**: observable
    state — `skills/build/references/review.md` contains no instruction to read an existing file as the
    remedy for an absent one. **Phase**: Review-phase response

11. **Ratchet stays green, both pins.** **Acceptance**: `just test` passes
    `tests/test_reference_size_ratchet.py`; `skills/build/references/size-pin.txt` and
    `plugins/cortex-core/skills/build/references/size-pin.txt` are byte-identical. Prefer a byte-neutral
    rewrite (R10); otherwise lower the pin via `just ratchet-refs`, or add a `# raised:` line in the
    established format (`# raised: <what> because <why>, lifecycle-id=<id>, date=<YYYY-MM-DD>`).
    **(preservation invariant — passes before the change; guards regression)** **Phase**: Review-phase
    response

12. **New refusal coverage.** Tests cover: missing artifact, empty artifact, missing index (R8
    precedence), and the happy path still registering. **Acceptance**: `just test` passes with ≥4 new
    assertions in `cortex_command/lifecycle/tests/test_register_artifact.py` naming the refusal.
    **Phase**: Verb gate

## Non-Requirements

- **The overnight path.** ADR-0015 already gives it a complete response (`parse_verdict` detects it, the
  `could_not_run` discriminator routes it, the merge is preserved, the PR is marked degraded, the breaker
  counts it under `review_no_artifact`). Recovering the idle agent's work is unbuildable there — no
  `--resume`/`--continue` affordance exists anywhere in `cortex_command/`.
- **Renaming the `review_no_artifact` cause class**, which despite its name fires for a missing file, a
  missing JSON block, *and* malformed JSON, since `parse_verdict` (`review_dispatch.py:205-217`) collapses
  all three into one `_ERROR_RESULT`. The behaviour is correct; only the label is imprecise. Recorded here
  so it is not rediscovered as a bug.
- **Splitting `parse_verdict`'s sentinel** so "no artifact" and "unparseable verdict" become
  distinguishable. That touches ADR-0015's load-bearing discriminants for no observed failure.
- **Detecting a bad review.** A syntactically complete but substantively empty `review.md` passes every
  check here. "Exists and is non-empty" is a weaker guarantee than it reads as, and closing that gap is
  not attempted.
- **A retry cap for resumption.** Resumption is bounded by orchestrator judgment; when it falls through to
  re-dispatch, §3's existing cap governs. No new cap is introduced.
- **The phase-detection mis-route this bug causes.** A missing `review.md` also makes `common.py`'s phase
  detection fall through to the plan-based step and report `review` instead of `implement-rework`
  (`cortex_command/lifecycle/review_brief.py:35-37`). Refusing to register leaves the artifact still
  absent, so the mis-routing persists unchanged; not a regression introduced by this work, and left for a
  separate ticket.

## Edge Cases

- **Reviewer mid-write** — a truncated but non-empty `review.md` passes the check and registers. Accepted:
  the non-empty test strictly dominates a bare stat but does not close the race, and no cheap check does.
- **Artifact written after a refusal** — re-running the verb registers normally. The refusal is stateless
  and the flow converges; nothing must be undone.
- **Worktree / root-resolution split** — `review_brief.py:607` and `register_artifact.py:100` share
  `_resolve_user_project_root_from_cwd`, so the reviewer's absolute `review_path` (`review_brief.py:618`)
  and the checked path agree *when both run from the same cwd*. This is **not** the documented
  `enter`-vs-`register-artifact` divergence (`enter` honours `CORTEX_REPO_ROOT`) — `enter` is not the
  writer, so that divergence does not sit on this path. The live hazard is narrower but **not
  hypothetical**: the interactive branch-mode flow runs in worktrees under `.claude/worktrees/`, and two
  are checked out right now. If the reviewer subagent writes into a different tree than the orchestrator's
  cwd resolves to, the check false-refuses on a `review.md` that exists. **The implementer must confirm
  which tree the reviewer writes into under branch mode before shipping Phase 1**, and pin
  `--project-root` at the call site if they diverge. This is the single most likely source of a false
  refusal.
- **Resume race** — R9 permits resuming an idle reviewer via SendMessage. A resumed agent may be several
  turns from flushing `review.md`, so an orchestrator that re-checks immediately re-triggers the halt and
  can loop. The response to a refusal is therefore resume-then-*wait-for-the-agent's-return*, never
  resume-then-immediately-recheck. No timer or backoff is specified — the agent's own return is the
  signal.
- **`index.md` absent** — returns `no-index` as today (R8), not the new refusal.
- **Non-`review` artifacts** — `plan`, `spec`, and `research` call sites inherit the refusal. This is
  intended, not incidental: `research-phase.md:23` already wants the check, and artifact-conditional logic
  would add branching for no benefit.

## Changes to Existing Behavior

- **MODIFIED** — `cortex_command/lifecycle/register_artifact.py`: `register_artifact()` gains an
  exists-and-non-empty precondition on the artifact file, returning `error` instead of `registered` when
  it fails. `index.md` is not written in that case. Callers that previously always saw a write now may
  not; all five callers are skill prose that does not branch on the state, so none breaks.
- **MODIFIED** — `cortex_command/lifecycle/tests/test_register_artifact.py`: the 16 existing tests must
  create their artifact file beside the injected index.
- **MODIFIED** — `skills/build/references/review.md` §2 and §3 (Phase 2), with the mirrored plugin copy
  and both `size-pin.txt` files kept in sync.

## Technical Constraints

- `register_artifact` has **zero non-test Python callers**; its consumers are five skill-prose call sites
  (`review.md:35`, `plan.md:76`, `backlog-writeback.md:19`, `refine/SKILL.md:76`,
  `research-phase.md:23`), none of which branch on the returned state. Enforcement must therefore be the
  withheld write, not a returned value.
- Adding a **new state value** would bump `PROTOCOL_VERSION` — `protocol.py`'s history sets the precedent
  ("2: spec-approve may return state `approved-direct` … prose predating the fork has no route for that
  state") — and a floor bump strands out-of-repo consumers. Reusing `error` avoids this.
- The gate must **not** land in `advance review-verdict`, for two verified reasons — **note the original
  reason was wrong and is corrected here.** *Withdrawn:* an earlier draft claimed a refusal there leaks
  into the overnight path. It does not. The overnight pipeline does import and call `advance`
  (`review_dispatch.py:36`), but `_advance_review_complete` is reached only at `:414` and `:703`, both
  guarded by `verdict_str == "APPROVED"`, and `parse_verdict` runs first — a missing `review.md` yields
  the `_ERROR_RESULT` sentinel, which can never equal `APPROVED`. An existence gate would never fire on
  that path. *The reasons that do hold:* (i) `skills/build/SKILL.md:61`'s generic `refused` handling
  prescribes "re-run `cortex-lifecycle-next` and re-invoke threading
  `advance_contract.expected_from_state`" — a remedy for a *gate-mismatch* refusal that does nothing to
  make `review.md` appear, so siting here needs a prose disambiguation anyway; and (ii) in the real skill
  sequence `register-artifact` runs first (`review.md:35` before `:48`), so `advance` is strictly the
  later, weaker interception point.
- `skills/build/references/` is at **zero** ratchet headroom (pin 57175, measured 57175), with a
  byte-identical mirror pin under `plugins/cortex-core/`. Per the known sync sequence, editing
  `skills/*/references/` runs ratchet-refs → build-plugin → ratchet-refs, and the mirror pin is the one
  mirror path staged by hand.
- `cortex/requirements/lifecycle.md` does not exist (in-flight #469), so this feature was assessed against
  `project.md` only.

## Open Decisions

None. R11 leaves three pre-validated routes for the ratchet bytes, but selecting among them needs only the
final byte count, which is a measurement the implementer takes — not a decision requiring the operator.

## Proposed ADR

None considered. The change reuses an existing state, preserves the exit-code contract, bumps no protocol
floor, and is trivially reversible — it fails all three ADR criteria. The one decision with a real
trade-off (siting the gate in `register_artifact` rather than `advance`) is recorded in Technical
Constraints, and its rationale is a consequence of ADR-0015's existing boundary rather than a new
architectural commitment.
