# Review: tier-overrides-record-no-reason-and — cycle 2

**Tier**: moderate · **Criticality**: high → **Stage 1 runs; Stage 2 (code quality) does not.**
Code-quality remarks below are recorded as non-blocking observations, not as a Stage 2 pass.

**Mode: full**, not rework-scoped. `cortex-lifecycle-review-brief` labelled its output "cycle 1 · full
review" because it resolved the event log to this worktree's stale committed copy and so saw no prior
verdict. A scoped brief was therefore unavailable and the safe superset was run: all eight requirements
re-rated from scratch, plus regression checks on the cycle-1 fixes. Cycle 1 is archived at
`review-cycle-1.md` (byte-identical to the `review.md` this file replaces).

**Test baseline consumed, not re-run.** 5 of 8 groups pass; the three failures
(`cortex_command/init/tests/test_handler_ensure.py` ×19,
`tests/test_log_invocation_perf.py::test_log_invocation_fast_path_budget`,
`cortex_command/lifecycle/tests/test_init_ensure.py::test_r9c_namespace_shape_equivalence`) are
pre-existing at base `b8eb8f8f` and unrelated: none touches `refine.py`, `skills/refine/`, or reason-clause
handling. No requirement is failed on them.

## Cycle 1's blocking issue — resolved

**The caveat now exists in a commit body, and it discharges the spec in substance.** `12968dee`'s body
carries both halves the spec's Non-Requirements demanded, in the spec's own terms:

- The direction-of-evidence claim, stated unambiguously and with its reasoning intact — the four-tag set is
  not derived from the tier rubric; roughly half of the 24 existing free-prose tier reasons land on
  `other` because tier's defining language has no corresponding tag; the ~9 on `exposure` land there by
  coincidental vocabulary overlap. It closes with *"So a resulting distribution dominated by 'other' is
  evidence FOR a tier-specific vocabulary, not against it. Reading it the other way would be backwards."*
  That is the whole point of the requirement, and it is not paraphrased into vagueness.
- The re-measure trigger with all three of its numbers intact — under 5% fill on `complexity_override`
  rows at `gate=clarify_reconcile`, after 60 days or 50 lifecycles, and the correct conclusion (*"the
  mechanism — not the vocabulary — is what to revisit"*). It also adds a true and useful fact the spec did
  not state: `v4.6.0` was tagged after every existing reconcile row, so neither axis has production
  evidence yet.

Taking the reviewer's explicitly sanctioned second route (a new commit rather than amending `f0cf4ec1`
three commits back) was the right call, and the body is honest about why. **The requirement is
discharged.** One discovery caveat is recorded as non-blocking observation 2 — it does not reopen this.

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

Everything below was re-verified at cycle-2 HEAD (`12968dee`), independently of cycle 1's findings.

### R1 — PASS

`refine.py:364-369` assigns both predicate results before testing them. Executed against working-tree code
(`python -m cortex_command.refine`, never the PATH binstub) on a scratch lifecycle: both diagnostics print,
exit is 2, and `events.log` is byte-unchanged — the all-or-nothing append survives.

```
cortex-refine: --tier-reason 'badA: x': clause tag 'badA' is not one of: consequence, exposure, other, reversibility
cortex-refine: --criticality-reason 'badB: y': clause tag 'badB' is not one of: consequence, exposure, other, reversibility
```

### R2 — PASS

Guards at `refine.py:422` and `:439` key off truthiness. Executed: with both reasons `""` the two appended
rows are exactly `{ts, event, feature, from, to, gate}` — no `reason` key on either, and both rows still
land (state `ratcheted`, `rows: 2`), so this is omission and not suppression of the row.

### R3 — PASS

`grep -c "that module's optional-field handling" cortex_command/refine.py` → `0`, and the replacement at
`:413-421` states the divergence rather than deleting the note.

**The retargeted citation is accurate.** Cycle 1's observation 3 asked for the line number to be replaced
by a function name, and `12968dee` names `lifecycle_event.py`'s `_emit_subcommand` optional-flag drop.
Verified: `_emit_subcommand` is defined at `lifecycle_event.py:358` and its loop body is
`if value is None and not required: continue  # optional flag omitted — drop the field entirely` — the
`is not None` shape the comment claims, in the function it names. I also checked the claim's premise holds
for the reason field specifically: both `complexity-override` and `criticality-override` declare
`("--reason", "reason", _STR, False, None)` — `required=False`, so an empty string is non-`None`, survives
the guard, and would be recorded as `"reason": ""`. The divergence is real and correctly described.

### R4 — PASS

Executed on a scratch lifecycle already at rank on both axes, with both reasons supplied:

```
cortex-refine: --tier-reason 'other: x' discarded: tier stays at 'complex', so no override row was appended to carry it
cortex-refine: --criticality-reason 'other: y' discarded: criticality stays at 'high', so no override row was appended to carry it
{"state":"noop","rows":0,"tier":"complex","criticality":"high"}
```

Exit 0, payload unchanged, no rows appended. Both fields warn independently, matching the spec's "both axes
no-op → two stderr lines" edge case.

### R5 — PASS

`grep -c -- '--tier-reason' skills/refine/SKILL.md` → `2`, and the `plugins/cortex-core/` mirror is
byte-identical to the canonical source (`diff` returns nothing), so the pre-commit rebuild did its job. The
flag is appended after `--criticality-reason` on both arms; the diff confirms
`tests/test_refine_reconcile_clarify.py` has a single hunk at line 601, so the contiguous prefix pins at
`:357-368` are untouched.

### R6 — PASS, executed rather than inferred

Cycle 1 rated this by inspection (correctly) but did not run the mutation. I ran it, in a throwaway
`git archive` copy of HEAD under the scratchpad — no repo file was touched:

- Baseline in the copy: `tests/test_refine_reconcile_clarify.py` → **14 passed**.
- `--tier-reason` argparse block deleted: **12 failed, 2 passed**, including
  `test_reconcile_clarify_records_tier_reason_per_axis`,
  `test_reconcile_clarify_empty_tier_reason_omits_the_key`, and
  `test_reconcile_clarify_reports_both_bad_clause_tags_in_one_run`.
- Restored from `git show HEAD:cortex_command/refine.py`: **14 passed** again.

The presumption of removal is discharged by an executed check, not a read one. The check is not
self-sealing: the mutation is in the wheel and the assertions are on emitted row content.

### R7 — PASS

The new pin is its own function, `test_refine_skill_passes_the_tier_reason_flag`, whose body is a single
`assert "--tier-reason" in body` against the canonical `skills/refine/SKILL.md` — existence only, no
proximity, ordering, count, or placement constraint. Its docstring names the silent failure (Clarify's tier
reasoning never reaches a `complexity_override` row; no exit code, diagnostic, or gate surfaces it), which
is what `CLAUDE.md`'s machine-token carve-out requires. The diff on the test file is **+155/−0** in one
hunk after line 601 — zero deletions, so no existing pin was extended.

### R8 — PASS

`test_reconcile_clarify_reports_both_bad_clause_tags_in_one_run` asserts `len(err_lines) == 2`, matches each
message against its own bogus tag (so one diagnostic printed twice cannot satisfy it), asserts empty stdout,
and asserts `events_log.read_bytes()` is unchanged. Removing either `_reason_clause_ok` call turns it red on
two independent assertions.

## Regression check on the cycle-1 fixes

`12968dee` touches exactly two files: `cortex/requirements/project.md` (one line) and
`cortex_command/refine.py` (a comment inside a dict literal, `+4/−3`). **No behavioral change** — the diff
contains no executable line. Confirmed empirically as well: the 14-test baseline above was run against HEAD
*including* `12968dee`, and all four R1/R2/R4 probes were executed at HEAD. Nothing that passed in cycle 1
regressed.

**The drift edit landed in the right place and reads correctly.** It is appended to the end of the
**Override-reason clause vocabulary** bullet at `project.md:64`, immediately before the `→ ADR-0036.`
pointer, exactly as cycle 1's Suggested Requirements Update specified, and the text matches that suggestion
verbatim. In context it qualifies the preceding parity sentence rather than contradicting it: the field
order claim stands, the omission claim is narrowed to the `None` case for one writer. One inaccuracy in the
appended sentence is recorded as non-blocking observation 1.

## Non-blocking observations

Stage 2 did not run. These are recorded for the completion phase, not as compliance failures.

1. **`project.md:64` now says the `_emit_subcommand` gap "is tracked as follow-up", and no ticket tracks
   it.** `grep -rl "_emit_subcommand\|per-field validator" cortex/backlog/` returns nothing; the only
   backlog file mentioning the flag is #471 itself. The spec's Non-Requirements says "Follow-up ticket",
   which reads as a commitment to file one, and it was not filed. This is the cheapest kind of false claim
   to leave behind — a future reader greps the backlog, finds nothing, and cannot tell whether the work was
   dropped or never recorded. **Preferred remedy at complete: file the ticket** (per-field validator hook in
   `_emit_subcommand`, plus its `is not None` guard), which makes the sentence true as written. Reworded
   softening ("the closure path is recorded in this lifecycle's spec") is acceptable but weaker. I did
   **not** classify this as requirements drift: the requirements text is the thing that should stay and the
   world is what should change to match it, so routing it through the drift machinery would invert the fix.

2. **The caveat is reachable by `--grep` but not by the `-S` pickaxe on the flag name.** The spec's stated
   discovery route is a future measurer running `git log -S`. Measured at HEAD:
   `git log -S '--tier-reason' b8eb8f8f..HEAD` returns `46600bb7`, `93e19551`, `f0cf4ec1` — **not**
   `12968dee`, whose diff contains no such literal. `git log --grep=tier-reason` does return it. This is a
   real but small consequence of recording the caveat in a fifth commit instead of amending `f0cf4ec1`, and
   it is mitigated by adjacency: `12968dee` is the branch tip, one commit after every `-S` hit, so a
   measurer who lands on any of the three sees it in the same `git log` page. If the completion commit
   wants to close the gap for free it can quote the literal `--tier-reason` in its own body. Not worth a
   sixth commit on its own.

3. **"The omission TEST diverges" reads ambiguously.** In the `refine.py:413-421` comment, `TEST` in caps
   means the boolean test (the guard expression), but in a repo where "test" overwhelmingly means pytest,
   a reader can spend a beat looking for a diverging test case. "The omission *guard*" or "the omission
   *condition*" would remove the ambiguity. Cosmetic; the sentence is correct as written.

4. **Cycle 1's observations 1, 2 and 4 were correctly left unactioned.** Observation 1 (the stderr messages
   carry no severity token) describes a pre-existing module-wide convention that this change follows rather
   than worsens — deviating for one new message would make it the odd one out, which is strictly worse.
   Observation 2 (two discard lines on every idempotent re-run of refine) is anticipated by the spec's Edge
   Cases and has its remedy named in `plan.md` Risks ("quiet it, not re-silence the drop"); acting on a
   noise prediction before observing the noise would be speculative. Observation 4 was an approval note with
   no ask in it. All three were observations, not requirements — leaving them was right.

5. **#471's headline ask survives this slice and needs somewhere to live.** The spec declines the
   §5.2-derived tier clause vocabulary explicitly and says so plainly. The completion phase should not
   archive #471 as satisfied — a tier author reaching for `design-fork:` is still rejected, and the
   measurement backing the vocabulary case (half of 24 reasons landing on `other`) is now recorded in a
   commit body whose re-measure trigger is the thing that will call the question. Whether that lives as a
   re-scoped #471 or a successor ticket is the completion phase's call.

## Requirements Drift

- **State**: `none`
- **Findings**: Cycle 1's detected drift (`cortex/requirements/project.md:64`'s cross-writer parity claim
  versus R2's truthiness guard) was applied in `12968dee` and is verified above — correct location, correct
  text, reads correctly in context. No new drift found. I re-checked the two loaded requirements files
  against the shipped behavior: `project.md`'s **Override-reason clause vocabulary** bullet is now accurate
  (no tag was added, so its three-site co-edit condition never fired); `glossary.md`'s `tier` and
  `short road` entries are untouched by this change, and the `--complexity`/`tier` flag-name mismatch is a
  pre-existing, explicitly declined non-requirement, not drift this change introduced.
  `cortex/requirements/lifecycle.md` is absent — a known index gap, not a defect of this work. The one
  inaccuracy in the newly appended sentence is observation 1 above, which is fixed by filing a ticket rather
  than by editing a requirement.
- **Update needed**: none

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 2,
  "issues": [],
  "requirements_drift": "none"
}
```
