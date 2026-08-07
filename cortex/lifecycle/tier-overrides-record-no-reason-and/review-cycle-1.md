# Review: tier-overrides-record-no-reason-and — cycle 1

**Tier**: moderate · **Criticality**: high → **Stage 1 runs; Stage 2 (code quality) does not.**
Code-quality remarks below are recorded as non-blocking observations, not as a Stage 2 pass.

**Test baseline consumed, not re-run.** 5 of 8 groups pass; the three failures
(`cortex_command/init/tests/test_handler_ensure.py` ×19,
`tests/test_log_invocation_perf.py::test_log_invocation_fast_path_budget`,
`cortex_command/lifecycle/tests/test_init_ensure.py::test_r9c_namespace_shape_equivalence`)
are pre-existing at base `b8eb8f8f`. **I do not believe any of them is related to this change**: none
touches `refine.py`, `skills/refine/`, or reason-clause handling, and the changed function is reached
only through the `reconcile-clarify` subparser. `tests/test_refine_reconcile_clarify.py` is green (14).

## Stage 1 — Spec compliance

| Req | Verdict |
|---|---|
| R1 both bad clause tags reported in one run | **PASS** |
| R2 empty reason omits the key | **PASS** |
| R3 cross-writer parity comment corrected | **PASS** |
| R4 discarded reason announced | **PASS** |
| R5 Step 4 passes `--tier-reason` on both arms | **PASS** |
| R6 functional test turns red on flag removal | **PASS** |
| R7 wiring pinned without extending a prose pin | **PASS** |
| R8 both stderr messages pinned | **PASS** |

### R1 — PASS

`cortex_command/refine.py:364-369` assigns both predicate results before testing them. Confirmed
independently by direct invocation against working-tree code (`cortex_command.refine.main`, not the
PATH binstub) on a scratch lifecycle: both diagnostics print, exit is 2, and `events.log` is
byte-unchanged — the all-or-nothing append survives. Test
`test_reconcile_clarify_reports_both_bad_clause_tags_in_one_run` matches each message to its own bogus
tag, so one diagnostic printed twice cannot satisfy it, and it asserts `len(err_lines) == 2` and empty
stdout. Good test.

### R2 — PASS

Guards at `refine.py:422` and `:439` now key off truthiness. Confirmed independently: with both reasons
`""` the two appended rows are `{ts, event, feature, from, to, gate}` — no `reason` key on either.

**On the shipped-behavior change (brief item 1).** The spec's "Changes to Existing Behavior" entry is
honest and, as far as I can establish, complete. I searched for a membership-style reader across
`*.py`/`*.js`/`*.ts`/`*.jsx`/`*.tsx` (`['\"]reason['\"] *in `) and found **zero occurrences anywhere in
the repo**. The documented corpus recipe in `cortex/adr/0036-*.md:63` uses `r.get('reason')` — truthy —
so the change strictly improves that tally rather than perturbing it, exactly as R2 claims. The one
overreach in the spec sentence is scope: it says "No reader observes the difference" without qualifying
that this is a repo-local search; a consumer repo's ad-hoc script is out of anyone's reach. Not a
defect, and not worth a PARTIAL.

### R3 — PASS

`grep -c "that module's optional-field handling" cortex_command/refine.py` → `0`. The replacement at
`:413-421` states the divergence rather than deleting the note, and cites `lifecycle_event.py:364`. I
checked that citation: line 364 is `if value is None and not required:` in `_emit_subcommand` — the
exact `is not None` shape claimed. Accurate today. Line-number citations in comments rot; see the
non-blocking notes.

### R4 — PASS

Confirmed independently in two shapes: (a) a second reconcile against an already-ratcheted tier prints
the discard line and exits 0 with `{"state":"noop","rows":0,...}` — payload unchanged; (b) the partial
case (tier at rank, criticality moving) prints the tier discard line while the criticality row lands
with its reason intact. Emitted text:

```
cortex-refine: --tier-reason 'other: x' discarded: tier stays at 'complex', so no override row was appended to carry it
```

**On scope (brief item 4, second half).** Ticket #471's Edges say the noop silent drop is "not a defect
to fix here", and R4 overrides that. This is *not* quiet scope creep: `research.md:80` and `:88` argue
the override explicitly, with measured evidence (24/78 cortex-command, 14/117 wild-light fire a
criticality row with no tier row at this gate) and the reasoning that the ticket's disposition was
written for a zero-caller flag and does not bind the case this change creates. Honestly recorded.
`spec.md` itself does not restate the ticket-edge override, only `research.md` does — a small
traceability gap, not a compliance failure.

### R5 — PASS

`grep -c -- '--tier-reason' skills/refine/SKILL.md` → `2`; the `plugins/cortex-core/` mirror is in sync
at `2`. The flag is appended after `--criticality-reason` on both arms, so the contiguous prefix pins
at `tests/test_refine_reconcile_clarify.py:357-368` still match (they are prefixes; the diff shows that
test untouched).

**On the prose rewording (brief item 2).** The builder wrote "its tier counterpart" instead of naming
the flag, to keep `grep -c` at exactly 2. I judge the result **clear enough, not a clarity trade** — but
the acceptance criterion, not the author, deserves the credit. The literal token `--tier-reason` appears
in both invocation bullets directly above the sentence, so an author reaching for the flag reads it
verbatim in the line they are about to run; "its tier counterpart" is unambiguous with the referent two
lines up. The sentence also improved in one respect: "An unknown tag is rejected and nothing is
written" is now true of *both* flags, where before it described one.

The real observation is upstream: R5's acceptance is an **exact occurrence count**, and
`docs/policies.md:37` rejects occurrence-count constraints precisely because they "fail on edits that
change nothing a consumer sees". That criterion lives in the spec, not in a shipped test — the shipped
test is bare existence — so no policy is violated. But the criterion did steer the prose, and a future
spec should say "appears in both invocations" rather than "returns 2". Non-blocking.

### R6 — PASS

`args.tier_reason` has exactly one producer: the argparse block at `refine.py:946`. Deleting it makes
`main([... "--tier-reason", ...])` an argparse error → `SystemExit(2)` before any assertion, turning at
least `test_reconcile_clarify_records_tier_reason_per_axis`,
`test_reconcile_clarify_empty_tier_reason_omits_the_key`, and
`test_reconcile_clarify_reports_both_bad_clause_tags_in_one_run` red.

**I confirmed this by inspection, not by executing the mutation** — I am read-only and will not edit
`refine.py`. The orchestrator's report (12 failed under mutation, 14 passed restored, empty
`git diff --stat` afterwards) is consistent with the code and I have no reason to doubt it. The check is
not self-sealing: the mutation is in the wheel and the assertion is on emitted row content, so the test
cannot pass by inspecting the thing it deleted.

`test_reconcile_clarify_records_tier_reason_per_axis` also asserts exact key order on both rows and that
the untagged criticality row does **not** inherit the tier reason — per-axis independence in both
directions. That is stronger than the criticality template it copies.

### R7 — PASS, and it genuinely complies

`docs/policies.md:43` bars citing an existing pin as precedent. Verified rather than taken on trust:

- The diff on `tests/test_refine_reconcile_clarify.py` is **+155/-0**, all additions after line 601.
  Lines 357-368 are byte-unchanged, so the contiguous pins were not extended.
- The new assertion is its own function, `test_refine_skill_passes_the_tier_reason_flag`, containing a
  single `assert "--tier-reason" in body` — existence only. No proximity, ordering, count, or
  section-placement constraint.
- Its docstring names the specific failure: Clarify's tier reasoning never reaches a
  `complexity_override` row, and no exit code, diagnostic, or gate surfaces it. That is the bar
  `docs/policies.md:35` sets, and the omission really is silent — I confirmed there is no runtime check
  that would catch a SKILL.md that dropped the flag.
- It reads `_REFINE_SKILL` = `skills/refine/SKILL.md` (canonical source), not the plugin mirror. Correct.

### R8 — PASS

Covered above under R1. Removing either `_reason_clause_ok` call turns
`test_reconcile_clarify_reports_both_bad_clause_tags_in_one_run` red on the `len(err_lines) == 2`
assertion and on the per-tag `any(...)` for the dropped flag.

## Blocking issue

### The spec's mandated commit-body caveat reached no commit body

`spec.md` Non-Requirements states, in bold: *"**The commit body must record that a resulting distribution
dominated by `other` is evidence *for* a tier-specific vocabulary, not against it**, and state a
re-measure trigger: if fill on `complexity_override` at `gate=clarify_reconcile` remains under 5% after
60 days or 50 lifecycles, the prose wiring is not doing the work and the mechanism — not the vocabulary
— is the thing to revisit. Without that caveat travelling with the data, a null result reads as a
positive one."*

`plan.md` Risks names this as the top risk and flags it as unenforceable by any task: *"it must reach
the implementation commit body — it is not enforceable by any task here."*

It did not reach any commit body. All four bodies in `b8eb8f8f..HEAD` were read:

- `f0cf4ec1` (the prose-wiring commit — the natural home) has an **empty body**.
- `93e19551` documents the three verb fixes; no caveat, no re-measure trigger.
- `46600bb7` documents the deletion-bias discharge; no caveat.
- `ab29161b` is checkpoint bookkeeping.

This is the failure the plan predicted: a spec deliverable that no task owned, so no task did it. It is
mitigated — the text survives in `spec.md`, which persists under `cortex/lifecycle/` — but the spec
asked for the commit body specifically because `git log -S` is what a future measurer reaches for when
the fill number comes back low, and the branch is unmerged so this costs one amended body.

**Fix**: amend `f0cf4ec1`'s body (or place it in the completion commit) with the caveat and the
re-measure trigger, in the spec's own terms. No code change.

## Non-blocking observations

These are recorded because the brief asked for scrutiny on them. Stage 2 did not run.

1. **The discard diagnostic's wording (brief item 3) is good and does not read as an error** — but only
   by module convention, not by design. Every stderr message in `refine.py` uses the bare
   `cortex-refine: <description>` shape with no severity token, including the fatal exit-64 ones at
   `:150` and `:172` and the non-fatal legacy-coercion warning at `:163`. The new message follows that
   shape exactly, so it is consistent; it is also, like the coercion warning before it, textually
   indistinguishable from a fatal message. That ambiguity is pre-existing and this change neither
   creates nor worsens it. The message itself is well-built: it names the flag, quotes the discarded
   value, names the field, gives the current value, and explains *why* nothing was recorded.

2. **Frequency on the resume path.** Now that Step 4 passes `--tier-reason` unconditionally, every
   idempotent re-run of refine prints **two** discard lines. `spec.md` Edge Cases anticipates this
   ("a re-run emits the discard diagnostic rather than duplicate rows") and `plan.md` Risks names the
   right remedy if it proves noisy ("quiet it, not re-silence the drop"). Flagged for awareness, not as
   a defect.

3. **`lifecycle_event.py:364` is cited by line number in a comment.** R3 asked for it and it is accurate
   today, but that file is under active follow-up (the spec's own Non-Requirements names a ticket to add
   a per-field validator hook to `_emit_subcommand`, the very function containing line 364). The
   citation will likely be stale before the divergence is closed. Naming the function
   (`_emit_subcommand`'s optional-flag drop) would survive that edit.

4. **Ticket #471's headline ask is declined, and the spec says so plainly.** "This slice does not close
   #471; a tier author reaching for `design-fork:` is still rejected" is about as unambiguous as a
   deferral gets, and it is backed by a measurement (roughly half of the 24 existing free-prose tier
   reasons land on `other`; the ~9 on `exposure` do so by coincidental vocabulary overlap). The work
   does not quietly under-deliver — it over-delivers on the ticket's "not a defect to fix here" edge
   (R4) while under-delivering on its headline, and records both. The ticket's remaining ask that its
   seeded-tier blind spot "be stated rather than assumed away" is satisfied in substance: the twin
   population is measured (24/78, 14/117) and R4 makes it audible rather than silent.

## Requirements Drift

- **State**: `detected`
- **Findings**:
  - `cortex/requirements/project.md:64` asserts a cross-writer parity that R2 deliberately breaks: *"Both
    writers of an override row — `lifecycle_event.py` (typed verbs) and `refine.py`
    (`reconcile-clarify`) — emit the same field order `from, to, reason, gate`, with `reason` omitted
    rather than nulled."* After this change the two writers diverge on the empty-string case:
    `refine.py` omits `reason` when it is falsy, while `lifecycle_event.py:364` still keys off
    `is not None` and would record `"reason": ""`. The field order is unaffected; the omission rule is.
    The divergence is acknowledged in a code comment (`refine.py:413-421`), in the commit body of
    `93e19551`, and in `spec.md` R3 — but not in the requirements file that states the constraint as a
    project-level invariant.
- **Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/project.md`
- **Section**: the bullet list containing **Override-reason clause vocabulary** (line 64)
- **Content**: append to the end of that bullet, before the `→ ADR-0036.` pointer:

```
The two writers diverge on an *empty* reason: `refine.py` omits the key on any falsy value, since `""` names no axis a corpus tally can bucket on, while `lifecycle_event.py` still omits only on `None` and would record `"reason": ""`. Closing that gap needs a per-field validator hook in `_emit_subcommand` and is tracked as follow-up.
```

## Verdict

```json
{
  "verdict": "CHANGES_REQUESTED",
  "cycle": 1,
  "issues": [
    "The spec's mandated commit-body caveat reached no commit body. spec.md Non-Requirements requires the implementation commit to record that an `other`-dominated clause distribution is evidence FOR a tier-specific vocabulary, plus the re-measure trigger (fill under 5% after 60 days or 50 lifecycles means the mechanism, not the vocabulary, is what to revisit). None of f0cf4ec1, 93e19551, 46600bb7, or ab29161b carries it, and f0cf4ec1 has an empty body. plan.md's Risks predicted exactly this, naming it unenforceable by any task. Fix: amend f0cf4ec1's body (or record it in the completion commit) in the spec's own terms. No code change."
  ],
  "requirements_drift": "detected"
}
```
