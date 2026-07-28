# Research: Make the overnight lifecycle arms supply a `from_state` the events-first gate accepts

Scope anchor (clarified intent): make both overnight lifecycle arms in
`cortex_command/pipeline/review_dispatch.py` supply a `from_state` the events-first gate
accepts, so an APPROVED overnight review durably records `review_verdict` +
`phase_transition review→complete`, **without routing around the gate**.

> **The ticket's stated diagnosis is wrong and must not be implemented literally.** Its Role
> section says "The open question is which directory each detector reads … which suggests
> `advance` resolves the feature directory from the slug against the project root rather than
> from `log_path`." That is false. `_current_phase` reads `feature_events_log.parent`
> (`review_dispatch.py:48`); `advance` reads `resolved_log.parent` (`advance.py:986`), where
> `resolved_log = Path(log_path)` and the caller passes `log_path=feature_events_log`. Same
> directory, every call. A builder following Role would hunt a bug that does not exist.

## Codebase

### The actual mechanism

Two *different functions*, not two different directories:

| Caller | Function | Kind |
|---|---|---|
| `_current_phase` (`review_dispatch.py:48`) | `common.detect_lifecycle_phase` | artifact-presence — the documented **legacy fallback** |
| `advance`'s gate (`advance.py:986`) | `common.resolve_lifecycle_phase` | **events-first** (ADR-0025) |

`advance.py:973-980` documents the split deliberately: *"This MUST NOT use
`detect_lifecycle_phase`: that artifact-presence derivation is the LEGACY FALLBACK, and it
reports `review` the moment plan.md's tasks are all `[x]`."* `resolve_lifecycle_phase` appears
nowhere in the ticket, including its Touch points.

`dispatch_review` writes `review.md` before calling `_advance_review_complete`
(`review_dispatch.py:403-414`), so the artifact detector short-circuits to `complete`
(`common.py:364-368`) while events correctly say `review`.

### Measured on realistic logs (this session, `advance()` called directly, no source edits)

A realistic overnight log carries the machine rows a real run emits (`specify→plan`,
`plan_approved`, `plan→implement`, `implement→review`):

```
_advance_to_review        : artifact='review'    events='implement'   -> REFUSED (gate-mismatch)
_advance_review_complete  : artifact='complete'  events='review'      -> REFUSED (gate-mismatch)
```

**Both arms are broken**, not one. The ticket's Integration section says `_advance_to_review`
"happens to succeed today, because at that moment `review.md` does not yet exist" — the real
reason is different and narrower: the observed session logs carry *zero* prior machine rows, so
`resolve_lifecycle_phase` fell back to the same artifact detector `_current_phase` uses, making
the gate a genuine tautology **by accident of a degenerate log**. On any log carrying a
`plan→implement` row, `implement.md §2d` flips plan.md's checkboxes to `[x]` *before* the
transition verb runs, so the artifact detector reports `review` while events report `implement`
→ refusal.

Table `from_state` values match the events-first value in both cases:
`implement.review` → `"implement"` (`transition_table.py:457`); `review.approved` → `"review"`
(`transition_table.py:339`).

### A third call site the ticket does not mention

`cortex_command/overnight/advance_lifecycle.py:225`:
```python
from_state = str(detect_lifecycle_phase(feature_dir).get("phase") or "review")
advance(verb="review-verdict", feature=feature, verdict="APPROVED", cycle=cycle, ...)
```
Same artifact detector, same `review.approved` arm. This is the **morning-review** path — the
very tool that reports `missing-review`. It handles two branches (`advance_lifecycle.py:216-223`):

| Branch | Condition | Measured on a realistic log (today) | Under Candidate A |
|---|---|---|---|
| `advanced-crash-recovery` | `review_required` and a real verdict exists | **passes** (artifact and events both `review`) | **passes** |
| `advanced-complete` | `not review_required` (short road) | **REFUSED** (artifact `plan`, events `implement`) | **REFUSED** |

The `advanced-complete` branch is **already broken today** on realistic logs, and for a
different reason: it fires the `review.approved` arm (`from_state="review"`) for a feature that
never entered review and is genuinely at `implement`. That is an **arm-selection** defect, not a
`from_state` defect. Measured: `advance(verb="implement-transition", mode="transition")` with no
`from_state` correctly emits `phase_transition implement→complete` on that same log
(`implement.complete`, `transition_table.py:471-475`, which resolves its own route from
tier/criticality via `it._resolve_route`).

**This call site is also completely silent.** `advance_lifecycle` never inspects `advance`'s
envelope (`advance_lifecycle.py:226-238` — `state` is set before the call and returned
unconditionally), so a refusal is reported to the CLI as `{"state": "advanced-complete", ...}`
with no events written and no warning. `review_dispatch.py` has `_advance_or_warn`
(`review_dispatch.py:51-83`, shipped in `fe521ea0`); this path has no equivalent.

### The correct pattern already exists in-repo

`next_verb.py:344` sets `advance_contract.expected_from_state` from `resolve.py:257`'s
`resolve_lifecycle_phase` — the same oracle the gate uses. `skills/build/SKILL.md:61` and
`skills/build/references/plan.md:116` thread it through `--from-state`. That is why the
interactive `/cortex-core:build` path never hits this bug.

`_current_phase` has exactly two callers, both in `review_dispatch.py` (`:103`, `:140`) — no
other importer repo-wide. It is deletable outright.

### The ticket's rejected-hardcode counter-evidence is a fixture defect

`cortex_command/pipeline/tests/test_review_verdict_recording.py:43-45` seeds
`{"from_phase": "implement", "to_phase": "review"}`, but `common.py:535` reads
`event.get("to")`, and every real producer emits `"from"`/`"to"` (`advance.py:367,401`,
`implement_transition.py:221-229`), as does the real evidence log. **This is the sole repo-wide
occurrence of those keys.** The seeded row is therefore invisible to the events-first resolver,
forcing artifact fallback in *both* detectors — so on that fixture they cannot disagree by
construction, manufacturing the "opposite direction" mismatch the ticket cites as grounds for
rejecting a fixed `from_state`.

Two further findings on that test: both branches of its `if appended:` conditional
assert-and-pass (`:62-76`), so it pins **neither** outcome before or after any fix; and
`git log --all --grep` finds no commit that ever tried and reverted a hardcode — the claim rests
on an uncommitted manual repro.

The same trap recurs in `tests/test_cortex_morning_review_advance_lifecycle.py`: both fixtures
(`:67-106`, `:145-173`) seed **no `phase_transition` rows at all**, so they too exercise only the
degenerate artifact-fallback path. `:104` asserts `complete_row["from"] == "review"` for a
feature that was never reviewed — pinning semantically wrong history.

### Constraints and success bar

- `tests/test_fold_completion.py:33-41,94-102,140-163` forbids `review_dispatch.py` and
  `advance_lifecycle.py` from calling `log_event`/`log_event_at` with an event in
  `{phase_transition, review_verdict, feature_complete, spec_approved, plan_approved}`, and
  requires each module to retain a call whose name contains `"advance"`.
- Best-effort pin: `test_review_verdict_recording.py::test_advance_failure_never_raises` (`:79-82`).
- `advance_lifecycle._has_real_review_verdict` (`:120-135`) requires `review_verdict` with an
  integer `cycle >= 1`; `_is_machine_complete` (`:168-176`) requires a terminal row or
  `phase_transition{to: "complete"}`.
- `metrics.py:extract_feature_metrics` (`:230-237`) detects completion off
  `feature_complete` **or** `phase_transition{to: "complete"}`.
- Both required rows are members of one `emissions` list gated once (`advance.py:388-403`,
  `986-1013`, `1029-1038`) — so a refusal loses both simultaneously, matching the observed symptom.

## Tradeoffs & Alternatives

| Candidate | Change | Verdict |
|---|---|---|
| **A — omit `from_state`** | delete `_current_phase` + the two `from_state=` args; `advance` uses `transition.from_state` (`advance.py:947`) | **Recommended.** Correct by construction |
| **B — swap the detector** | `_current_phase` calls `resolve_lifecycle_phase` | Rejected — produces a gate that can never refuse |
| **C — thread `next`'s contract** | call `next_state`, pass `advance_contract.expected_from_state` | Rejected here — adds machinery, and is *less* safe |
| **D — out-of-band `cortex-lifecycle-event log`** | hand-append the row | Rejected on requirements grounds |

**Why A is correct by construction, not corpus-fit.** `from_state` is invariant per verb across
the closed table: all three `review_verdict` arms are `from_state="review"`
(`transition_table.py:339,352,365`), and both non-batch `implement_transition` arms are
`"implement"` (`:457,474`). A verb *is* the gate for the state it fires from, so one verb cannot
have two departure states — meaning `transition.from_state` already equals the correct expected
phase for any valid call, on any log shape, with zero information loss versus a caller-supplied
value. Arm uniqueness is enforced at import time (`transition_table.py:565-566`).

**Why B is rejected.** It makes the docstring's tautology claim literally true for the first
time — and a literal tautology is the problem, not the fix: caller and gate would call the
identical function on the identical directory, so the gate could never refuse for gate-mismatch
again, for any caller. That is correctness by giving up on checking. It also deletes nothing.

**Why C is rejected at these call sites.** `next_state` (`next_verb.py:426,464-465`) anchors at
`resolve_main_repo_root()` and runs full `resolve_invocation` identity resolution with eight
non-resume passthrough states (`:103-111`) the pipeline would have to branch on — materially
more machinery than the helper it replaces, coupling the pipeline to `$ARGUMENTS`-classification
semantics designed for the interactive prose loop. It also *loses* safety: on an
already-complete feature `next` serves `expected_from_state="complete"`, which would **match**
and let the arm append a fabricated `phase_transition{from: "review", to: "complete"}` onto a
feature whose real prior state was already complete. A's fixed `"review"` refuses that for free.

The staleness argument that normally favours C does not apply to the two pipeline arms: they run
inside one synchronous `dispatch_review()` over a log this process just wrote, with per-feature
serialization already guaranteed (the same guarantee that let #397 delete the claim/commit
machine rows on a measured zero-collision rate, `advance.py:40-48`). `from_state` was never
meaningful information at these call sites.

**Why D is rejected.** `cortex/requirements/project.md`: *"Events are the authoritative phase
source wherever machine rows exist."* The gate refused **correctly** given the rows present.
Additionally `cortex-lifecycle-event log` routes to `lifecycle_event.py`'s raw-append `main()`,
skipping `_consent_cross_check` (`advance.py:606-650`) and `_project_status`
(`advance.py:688-777`) — a feature "completed" that way would never leave `in_progress` in the
backlog.

**Deletion bias.** A is the only candidate that removes code (`_current_phase`, its import, two
call args). B keeps the helper and adds a check that cannot fail. C adds machinery plus new
short-circuit logic to avoid the double-completion risk above.

**Provenance.** `from_state=_current_phase(...)` was deliberately authored at the #374 fold
(`28f3fb55`) with the (incorrect) tautology rationale; `c044055d` (#397) left it untouched;
`fe521ea0` (2026-07-28) diagnosed the disagreement and shipped `_advance_or_warn` audibility.

## Adversarial Review

The adversarial pass ran `advance()` against the two existing
`test_cortex_morning_review_advance_lifecycle.py` fixtures with `from_state` omitted, got
refusals in both, and concluded Candidate A is *empirically unsafe* at the third call site.

**That conclusion does not survive re-testing, because those fixtures carry no
`phase_transition` rows** — the identical unrepresentative-corpus trap that produced the
ticket's own rejected-hardcode claim. Re-run on realistic logs (measured above): crash-recovery
**passes** under both today's code and Candidate A; the no-review branch **refuses under both**,
so Candidate A neither causes nor fixes it. The adversarial recommendation — "pass an explicit
`from_state` chosen by the `review_required` branch" — would re-introduce exactly the
caller-side guessing this ticket exists to remove.

Its *underlying observations* stand and are load-bearing:

1. **The `review.approved` arm is being used for two structurally different predecessor
   states.** Correct, and the resolution is arm selection, not `from_state` selection: the
   no-review branch belongs on `implement-transition` (measured working above).
2. **The third call site's refusal is entirely silent** (`advance_lifecycle.py:226-238`) — a
   worse failure surface than the one this ticket fixes, since it reports success.
3. **Coupling between the two pipeline arms.** If `_advance_to_review` refuses, the log never
   reaches `review`, so fixing `_advance_review_complete` alone changes nothing. Both must land
   together — which the measurement above confirms they do under A.
4. **Refusals that survive any `from_state` fix**: an active enforcement-bearing pause whose
   slug is unmapped in `_PAUSE_OWNING_VERBS` (`advance.py:143-145,272-305`); and
   `_consent_cross_check` (`advance.py:606-650`) refusing `review.approved` when a `pr_opened`
   row exists whose PR is not `MERGED`. Both are by-design and out of scope, but they mean "the
   fix guarantees the rows land" is workflow-conditional — the spec's acceptance criteria should
   say so.
5. **Unvalidated cycle.** `dispatch_review` passes `cycle = verdict_dict.get("cycle", 0)`
   straight from the review agent's JSON (`review_dispatch.py:408`, `parse_verdict:188-217`). A
   missing/non-integer cycle fails `_has_real_review_verdict`'s `cycle >= 1` check even for a
   genuine APPROVED review — an independent path to `missing-review` that no `from_state`
   candidate addresses.
6. **Non-goal holds.** Every mismatch originates in a *caller*, not in
   `resolve_lifecycle_phase`/`_phase_from_machine_rows`, which behave coherently. The fix stays
   inside the ticket's stated boundary.

## Open Questions

1. **Is the third call site (`advance_lifecycle.py`) in scope?** — **Resolved: yes.** The ticket
   title is "make the transition record instead of silently refusing"; at this call site the
   refusal is *more* silent than the one being fixed (reported as success). Leaving it means the
   ticket's own success bar stays false at one of three sites, and the tool that surfaces the
   symptom would still fail to record the verdict itself.

2. **What should the `advanced-complete` (no-review) branch do?** — **Resolved by measurement:**
   route it through `advance(verb="implement-transition", mode="transition")`, which resolves its
   own route from tier/criticality and emits `phase_transition implement→complete`. Verified
   working on a realistic short-road log. The `review-verdict` arm stays for the crash-recovery
   branch only.

3. **Should the fixtures be rebuilt rather than patched?** — **Resolved: rebuilt.** Correcting
   `from_phase`/`to_phase` to `from`/`to` in `test_review_verdict_recording.py` is necessary but
   not sufficient — that test's both-branches-pass structure pins nothing, and the two
   `advance_lifecycle` fixtures lack machine rows entirely. All three need realistic
   `phase_transition` chains and single-outcome assertions, or the regression this ticket exists
   to prevent remains invisible to CI.

4. **Do the pause and gh-consent refusal paths need acceptance criteria?** — **Deferred.**
   Rationale: both are by-design refusals on evidence the gate is right to demand
   (`advance.py:272-305`, `606-650`), and neither is implicated in the observed failure. They
   bound the *claim* the spec may make ("the rows land whenever the gate's own preconditions
   hold"), not the work. Recording them as a stated limitation is sufficient.

5. **Is the unvalidated `cycle` from the review agent's JSON a separate ticket?** —
   **Deferred.** Rationale: it is an independent route to the same `missing-review` symptom, but
   it is not the mechanism this ticket reproduces, and fixing it requires deciding validation
   policy for agent-authored verdict JSON — a different design question. Should be filed as a
   follow-up rather than folded in.

6. **Does the scope expansion (three call sites, three test files, plus arm selection) exceed
   the `simple` tier set at Clarify?** — **Unresolved; escalation candidate.** The from_state
   change alone is mechanical, but arm selection at the third call site is a behavioral change
   with its own semantics, and the fixture rebuild changes what CI pins. Flagged for the
   complexity-escalation gate rather than decided here.
