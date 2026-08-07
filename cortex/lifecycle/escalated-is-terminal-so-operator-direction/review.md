# Review: escalated-is-terminal-so-operator-direction (cycle 2)

**Tier**: moderate → Stage 1 (spec compliance) only. Stage 2 (code quality) is complex-only and was **skipped**.
**Scope**: narrow re-review of cycle 1's two additive issues. Rework commits reviewed: `24aa71aa`, `211948de`, `64fff4bb`.
**Test baseline (consumed, not re-run)**: `just test` → `Test suite: 8/8 passed`, zero `[FAIL]`, exit 0.

---

## Source is unchanged, so R1–R9 stand

```
git diff --name-only cdcf9be3..HEAD
  cortex_command/lifecycle/review_brief.py          <- NOT this feature (see below)
  cortex_command/lifecycle/tests/test_next_verb.py
  cortex_command/lifecycle/tests/test_resolve.py
  tests/test_hooks_scan_lifecycle.py
  tests/test_lifecycle_phase_parity.py
  tests/test_lifecycle_phase_resolver.py

git diff --stat cdcf9be3..HEAD -- cortex_command/common.py \
  cortex_command/hooks/scan_lifecycle.py cortex_command/phase_labels.py \
  cortex_command/lifecycle/resolve.py cortex_command/lifecycle/next_verb.py \
  claude/statusline.sh cortex_command/backlog/generate_index.py plugins/
  -> (empty)
```

Every source file this feature edits is byte-identical to the tree that cycle 1 rated all-PASS. R1–R9 therefore stand as rated and were not re-audited.

**The one non-test file in the range is not this feature's and does not invalidate the narrow scope.** `cortex_command/lifecycle/review_brief.py` arrives whole in `4c61e56c` ("Add the review-brief module behind the new lifecycle verb", 699 insertions / 0 deletions) — the concurrent session's ticket 455 work, explicitly out of scope. It is a brand-new module, `pyproject.toml` is unchanged, and `grep -rn review_brief` finds **zero importers** anywhere in `cortex_command/`, `hooks/`, `bin/`, `claude/`, or `tests/`. It cannot reach any surface R1–R9 rate. Flagging it because the instruction demanded it be flagged loudly, not because it moves the verdict.

---

## Issue 1 — five uncovered branches: **RESOLVED**

Mutation-tested independently. Method: `git archive HEAD | tar -x` into a scratchpad copy, so **no mutation ever touched the live repo** (a concurrent session is active). Each source revert was applied to the copy with a targeted Python string replace and restored by re-materialising the blob from `git show HEAD:<path>`; every restore was verified with `diff <(git show HEAD:<path>) <copy>`. Baseline in the copy: 159 passed across the five test files.

| Cycle-1 branch | Mutation applied | Result |
| --- | --- | --- |
| `_interrupted_hint` rework-cap branch | deleted the whole `startswith("escalated:rework-cap:")` block | **FAILED** `test_interrupted_hint_rework_cap` (1 failed, 42 passed) |
| `_is_terminal_mismatch`'s `startswith("escalated:")` | deleted that `or` clause | **FAILED** `test_resolver_rework_cap_phase_is_terminal_to_the_detector` (1 failed, 52 passed) |
| `resolve._PHASE_NEXT` | (a) lookup → `_ROUTE_NEXT.get(route, …)`; (b) symbol deleted outright | (a) **FAILED** both new `test_resolve.py` tests; (b) **COLLECTION ERROR** on `test_resolve.py` (the import pins the symbol) |
| `_next_for_route`'s third `phase` parameter | (a) dropped the 3rd arg at the `resolve.py:298` call site; (b) removed the parameter from the signature | (a) **FAILED** `test_rework_cap_resume_serves_the_phase_keyed_directive`; (b) **TypeError → FAILED** both new tests |
| `_terminal_directive`'s `phase` argument | `_terminal_directive(state, phase)` → `_terminal_directive(state)` | **FAILED** `test_rework_cap_escalation_serves_a_non_rejection_directive` |

Cycle 1's stated bar — "a revert of any of the five lands the suite green" — is no longer true for any of the five. The commit's mutation claims are accurate as written.

**Assertion quality: good, not merely deletion-detecting.** Four *plausible-wrong-implementation* mutations (not reverts) were also run, and all four were caught:

| Plausible wrong implementation | Result |
| --- | --- |
| `_PHASE_NEXT` cap text replaced by the rejection text (copy-paste error) | **3 tests FAILED** |
| override guard dropped (`not phase_overridden` removed — discriminant trusted under `--phase`) | **FAILED** `test_rework_cap_directive_yields_to_an_explicit_phase_override` |
| `_terminal_directive` returns the cap directive unconditionally | **FAILED** `test_rework_cap_escalation_serves_a_non_rejection_directive` |
| cap hint drops the cycle number from its text | **FAILED** `test_interrupted_hint_rework_cap` |

**Self-sealing check.** `test_rework_cap_directive_yields_to_an_explicit_phase_override` does contain three clauses that compare the implementation against itself (`_ROUTE_NEXT["escalated"] in overridden`, `_PHASE_NEXT["escalated:rework-cap"] not in overridden`, and an `== _PHASE_NEXT[...]` equality). Each is paired with a content-anchored assertion in the same test, and the copy-paste mutation above proves the pairing holds — that test failed on Q1, so it is not self-sealing in practice. `test_resolve`'s resume test and `test_next_verb`'s envelope test both anchor on literal content (`"rework cap" in`, `"REJECTED" not in`) rather than on the tables, which is the right choice.

**Residual (new, not cycle 1's): a sixth branch on the same path has zero coverage.** `next_verb.py:525` — `phase=resolved.get("phase")` inside the `build_served_envelope(...)` call — is the *only* wiring that carries the discriminated phase from `resolve_invocation` into the served envelope. Deleting that one line:

```
uv run pytest cortex_command/lifecycle/tests/ tests/test_hooks_scan_lifecycle.py \
  tests/test_lifecycle_phase_resolver.py tests/test_lifecycle_phase_parity.py -q
  -> 567 passed          (green)

# but at the CLI, on a real capped lifecycle:
HEAD:  state=escalated | REJECTED in directive: False | "rework cap" in directive: True
Q5:    state=escalated | REJECTED in directive: True  | "rework cap" in directive: False
```

`build_served_envelope` has exactly two references (its `def` and this one call), so this is the sole production path and removing the argument reinstates the precise bug ticket 454 exists to fix, silently. The new `test_next_verb` test covers `build_served_envelope(phase=…)` → `_terminal_directive`, and the new `test_resolve` test covers `resolve_invocation` → `next`, but nothing covers the hop between them. Cycle 1 did not name this branch and the code is correct (cycle 1 proved it end-to-end by hand), so this is a coverage follow-up, not a ship blocker — recorded in `issues` below.

---

## Issue 2 — stale cycle-blindness prose: **RESOLVED, with an incomplete correction**

All three locations cycle 1 named are now accurate: the module docstring (`:19-27`), the R12b comment block's exclusion statement (`:124-132`), and both test docstrings (`:279-285`, `:318-332`).

**The orchestrator's correction (`64fff4bb`) is accurate in every clause, verified independently.**

- *"the `review-changes-requested-cycle2` fixture DOES land on that arm"* — true. The fixture is in `_ladder_fixture_dirs` (an `iterdir()` sweep), and `detect_lifecycle_phase` returns `escalated:rework-cap:2` for it.
- *"the cycle is compared there rather than excluded"* — true, and for the stated reason. The test's only phase assertion is `parsed_phase == canonical_phase`; `_parse_statusline_phase` returns bare-phase wire strings whole, so the `:2` suffix is inside the compared value. The `cycle` *field* is still never compared — the docstring says exactly that ("because the cycle rides inside the phase string rather than the separate `cycle` field"), so this is precise, not overstated.
- *"Reverting the ladder's `review_verdict` count fails this subtest on that fixture"* — **re-run and confirmed, two ways.** Deleting the `[ "$_lc_cycle" -ge 2 ]` branch, and separately neutralising just the `grep -c '"event"…"review_verdict"'` capture, each produce `FAILED tests/test_lifecycle_phase_parity.py::test_statusline_ladder_matches_canonical[review-changes-requested-cycle2]` (1 failed, 14 passed) with the diagnostic `emitted 'implement-rework' … canonical returned 'escalated:rework-cap:2'`. `claude/statusline.sh` restored and diff-verified clean.

**But `64fff4bb` fixed only one of the two places `211948de` introduced the false claim.** The R12b comment block still says, at `:133-136`:

```
# reaches 2. None of the fixtures this parametrized test runs against land
# on that arm, so the ladder-vs-canonical comparison below still never
# compares cycle in practice — but that is fixture coverage, not a
# statement that the ladder is cycle-blind in general.
```

That is the same sentence the orchestrator identified as false and corrected 180 lines lower, and the mutation above disproves it directly: the cycle2 fixture does land on that arm, and the ladder-vs-canonical comparison does compare the cycle. The file now contradicts itself — an accurate docstring at `:326` and a false comment at `:133`. Its harm is the mirror image of the original stale prose: an author trusting `:133-136` would conclude the parity ladder does not cover the cap arm and could delete the fixture or add redundant coverage. Comment-only, four lines, one-line fix; recorded in `issues` rather than escalated.

**No other stale cycle-blindness prose remains.** `grep -rn 'cycle-blind' / 'never .cycle' / 'reads only'` across `tests/`, `cortex_command/`, `claude/`, `docs/`, `hooks/`, `skills/`, `plugins/` returns only: the four correctly-narrowed hits in `test_lifecycle_phase_parity.py`; `cortex_command/overnight/outcome_router.py:2038` ("keys off the verdict string, never `cycle`"), which is about the outcome router's ERROR-vs-REJECTED discrimination and is unrelated and still true; and four unrelated "reads only" hits (`test_skill_handoff.py`, `session_marker.py`, `transition_table.py`, `dashboard/tests/test_templates.py`).

**Accepted, recorded residue (not an issue):** `spec.md:60`'s Technical Constraint ("Any part of the discriminant derived from `events.log` rather than `review.md` would be invisible to it") remains wrong in its rationale, by operator decision. `plan.md:124` records the correction and why R7's acceptance still holds.

---

## Regressions

**None.** Verified rather than assumed:

- `24aa71aa` is `166 insertions, 0 deletions` across four test files — purely additive, no existing test touched.
- `211948de` + `64fff4bb` are comment- and docstring-only. Filtering the parity diff to non-comment, non-docstring-prose lines returns nothing; no `assert`, `def`, `parametrize`, `GLUE_FIXTURES`, or `_PARSER_WIRE_VALUES` line was added, removed, or altered; the only `assert`-matching deletion in the whole range is the prose word "asserts" inside a reflowed docstring sentence. No fixture file changed.
- Targeted re-runs in the pristine copy: 159 passed across the five changed test files; 567 passed across `cortex_command/lifecycle/tests/` + the three `tests/` files; `tests/test_lifecycle_phase_parity.py` 55 passed. No weakened or deleted pre-existing assertion.
- Live repo confirmed untouched by this review: `git diff --stat -- cortex_command/ claude/ tests/ hooks/ skills/ plugins/ bin/` is empty, and nothing is staged. The only working-tree changes are the concurrent session's backlog edits and this feature's `events.log`.

---

## Requirements Drift

- **State**: `none`
- **Findings**:
  - Cycle 1's two drift clauses are **present and accurate** in `cortex/requirements/project.md`. Clause 1 at `:103` under `## Conditional Loading` (the `lifecycle.md` NOT-YET-WRITTEN routing row); clause 2 at `:61` under `## Architectural Constraints` (the `phase` may be discriminated / `route` may not invariant). Both match the cycle-1 suggested text, and clause 2's factual claims still hold against the unchanged source: `route` remains bare in every gating read, `_PHASE_NEXT` is keyed off `phase` only, and `tests/test_lifecycle_phase_parity.py` still pins bash parity (mutation-verified above).
  - The rework changed only tests, comments, and docstrings, so no new requirement is implicated. No new drift.
- **Update needed**: none.

---

## Verdict rationale

Source is byte-identical to the tree that passed all nine requirements, so nothing shipping-facing changed. Cycle 1's stated bar for Issue 1 is met on all five branches under my own mutations, and the assertions catch plausible wrong implementations rather than only deletions. Cycle 1's three stale-prose locations are all corrected, the orchestrator's correction is accurate in every clause I could test, and its mutation claim reproduces. The suite is green.

Two residual items remain, both comment-or-coverage grade and neither a defect in shipped behaviour: an incompletely-propagated comment correction (four lines, in the same file as its accurate replacement) and a sixth uncovered wiring line that cycle 1 did not name. At the rework cap, escalating the feature and stopping automation for either would be disproportionate to a follow-up. **APPROVED.**

**Issues** (residual observations, not blockers)

1. `tests/test_lifecycle_phase_parity.py:133-136` still carries the false coverage claim that `64fff4bb` corrected at `:326` — "None of the fixtures this parametrized test runs against land on that arm". The `review-changes-requested-cycle2` fixture does land on it; neutralising the ladder's `review_verdict` count fails that subtest on that fixture. One-line fix, and the file currently contradicts itself.
2. `cortex_command/lifecycle/next_verb.py:525` (`phase=resolved.get("phase")`) has zero coverage: deleting it leaves 567 targeted tests green while the CLI serves a capped feature the REJECTED directive. It is the sole hop between the two newly-covered halves and the only production wiring of `build_served_envelope`.

```
{"verdict": "APPROVED", "cycle": 2, "issues": ["tests/test_lifecycle_phase_parity.py:133-136 still carries the false coverage claim that commit 64fff4bb corrected at :326 — 'None of the fixtures this parametrized test runs against land on that arm'. The review-changes-requested-cycle2 fixture DOES land on it, and neutralising the ladder's review_verdict count fails test_statusline_ladder_matches_canonical on that fixture (re-verified two ways). The file now contradicts itself: accurate docstring at :326, false comment at :133. One-line fix; comment-only, so recorded rather than escalated.", "cortex_command/lifecycle/next_verb.py:525 (phase=resolved.get(\"phase\") in the build_served_envelope call) has zero automated coverage — deleting it leaves 567 targeted tests green while the CLI serves a capped feature the REJECTED directive, reinstating the exact bug ticket 454 exists to fix. build_served_envelope has only that one call site, so it is the sole production wiring, and it is the untested hop between the two halves the rework did cover. Cycle 1 did not name this branch; the code is correct, so this is a coverage follow-up."], "requirements_drift": "none"}
```
