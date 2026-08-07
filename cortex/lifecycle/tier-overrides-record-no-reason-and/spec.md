# Specification: Give `--tier-reason` its first caller

## Problem Statement

`--tier-reason` shipped on `cortex-refine reconcile-clarify` with zero tests and zero skill-prose callers, so every `complexity_override` row written at `gate=clarify_reconcile` — 54 in cortex-command, 103 in wild-light — records *that* the tier was ratcheted off its seed but never *why*. Under `project.md`'s deletion-bias clause a zero-consumer surface carries the presumption of removal, and #452's own review named this flag as meeting that condition. This gives the flag a real caller and a test that turns red on its removal, and fixes two defects in the same function that become reachable the moment it ships. It deliberately stops short of forking the clause vocabulary, because there is no evidence yet that wiring a reason flag into prose causes anyone to fill it — `--criticality-reason`'s wiring shipped in `v4.6.0` (tagged `2026-08-07T17:23:31Z`) and every reconcile row in both corpora predates it.

## Phases

- **Phase 1: Verb correctness** — fix the two defects in `_cmd_reconcile_clarify` and the comment that becomes false alongside them.
- **Phase 2: Wire and pin** — pass `--tier-reason` from Step 4 and add the tests that discharge the presumption of removal.

## Requirements

1. **Both bad clause tags are reported in one run.** `_cmd_reconcile_clarify` evaluates both reason flags before returning, so an author with two bad tags fixes both in one round-trip instead of two. Acceptance: invoke `reconcile-clarify … --tier-reason "badA: x" --criticality-reason "badB: y"` on a fixture lifecycle; stderr contains **both** a `--tier-reason` line and a `--criticality-reason` line, and exit is 2. Verified failing on HEAD: only the `--tier-reason` line prints. Grounding: `cortex_command/refine.py:353-356`. **Phase**: Verb correctness

2. **An empty reason omits the key rather than writing `""`.** Both emit guards move from `is not None` to truthiness, so `--tier-reason ""` and `--criticality-reason ""` behave as if the flag were omitted. Acceptance: invoke with both reasons set to `""`; neither the emitted `complexity_override` nor `criticality_override` row contains a `reason` key. Verified failing on HEAD: both rows carry `"reason": ""`, which ADR-0036's tally (`if r.get('reason')`) counts as reason-less — the row looks filled to a reader and empty to the tally. Grounding: `cortex_command/refine.py:404` and `:420-424`. **Phase**: Verb correctness

3. **The comment claiming cross-writer parity stops claiming it.** `refine.py:399-403` justifies the current guard as *"matching that module's optional-field handling"*; R2 breaks that parity for the empty-string case, since `lifecycle_event.py:364` keeps the `is not None` shape and is out of scope. Acceptance: the string `that module's optional-field handling` no longer appears in `cortex_command/refine.py`, and the replacement comment states the divergence. Verified failing on HEAD: the phrase appears once. **Phase**: Verb correctness

4. **A discarded tier reason is announced, not silently dropped.** When a reason is supplied for a field the no-op guard leaves unratcheted, `reconcile-clarify` writes one stderr line naming which reason was not recorded. Exit code and JSON payload are unchanged — this is a diagnostic, not a failure. Acceptance: invoke twice on the same fixture with `--tier-reason "other: x"`, the second invocation being a tier no-op; the second run's stderr names the discarded tier reason and exit is 0. Verified failing on HEAD: nothing is emitted. Grounding: the rank-comparison blocks at `cortex_command/refine.py:396-424`; measured need — 24 of 78 cortex-command and 14 of 117 wild-light lifecycles fire a `criticality_override` with no `complexity_override` at this gate. **Phase**: Verb correctness

5. **Step 4 passes `--tier-reason` on both arms.** `skills/refine/SKILL.md` Step 4 appends `--tier-reason "{tag}: {why}"` after `--criticality-reason` on the Context A and Context B invocations. Acceptance: `grep -c -- '--tier-reason' skills/refine/SKILL.md` returns `2`. Verified failing on HEAD: returns `0`. Verified safe: appending after `--criticality-reason` leaves both contiguous pins at `tests/test_refine_reconcile_clarify.py:357-368` matching, since they are prefix substrings. **Phase**: Wire and pin

6. **A functional test turns red when the flag is removed.** A test invoking the verb directly asserts the emitted `complexity_override` row carries the supplied `reason`, mirroring the `--criticality-reason` tests. This is what discharges the deletion-bias presumption — `project.md:23` requires *"a consumer that turns a build or gate red when the surface is removed"*, and skill prose is not executed by CI. Acceptance (mutation check): delete the `--tier-reason` argparse block from `cortex_command/refine.py`, run `uv run python -m pytest tests/test_refine_reconcile_clarify.py`, observe at least one failure, restore. Verified failing on HEAD: `grep -c 'tier_reason\|tier-reason' tests/test_refine_reconcile_clarify.py` returns `0`, so the deletion is currently invisible to the suite. **Phase**: Wire and pin

7. **The Step 4 wiring is pinned without extending a prose pin.** A new, separate assertion checks `--tier-reason` appears in the SKILL.md body, with a docstring naming the silent failure it prevents (tier reasons never recorded, with nothing surfacing the omission). The existing contiguous pins are **not** extended. Acceptance: the new assertion exists in its own test function; `tests/test_refine_reconcile_clarify.py:357-368` is unchanged; `uv run python -m pytest tests/test_refine_reconcile_clarify.py` passes. Grounding: `docs/policies.md:43` — existing pins *"hold no standing … do not cite an existing pin as precedent for a new one"*; `CLAUDE.md`'s machine-token carve-out permits the bare existence assertion. **Phase**: Wire and pin

8. **Both stderr messages are pinned.** A test asserts R1's two-message behavior, so a future refactor cannot silently reintroduce the short-circuit. Acceptance: the test asserts both flag names appear in captured stderr; removing one `_reason_clause_ok` call turns it red. Grounding: the `_reason_clause_ok` predicate at `cortex_command/refine.py:299-320`, invoked via the short-circuiting `or` at `cortex_command/refine.py:353-356`; test template: `tests/test_refine_reconcile_clarify.py:401-438` (`test_reconcile_clarify_records_criticality_reason_per_axis`). **Phase**: Wire and pin

## Non-Requirements

- **The §5.2-derived tier clause vocabulary** — ticket #471's headline ask, deliberately declined. This slice does not close #471; a tier author reaching for `design-fork:` is still rejected. **The tier clause vocabulary stays the criticality set for now.** Classifying all 24 existing free-prose tier reasons against `{reversibility, exposure, consequence, other}` found roughly half land on `other` — tier's defining language ("competing designs", "a precedent others follow", "whether the next tier down was considered") has no corresponding tag — and the ~9 that land on `exposure` do so by coincidental vocabulary overlap, describing design-uncertainty scope rather than downstream-breakage risk. **The commit body must record that a resulting distribution dominated by `other` is evidence *for* a tier-specific vocabulary, not against it**, and state a re-measure trigger: if fill on `complexity_override` at `gate=clarify_reconcile` remains under 5% after 60 days or 50 lifecycles, the prose wiring is not doing the work and the mechanism — not the vocabulary — is the thing to revisit. Without that caveat travelling with the data, a null result reads as a positive one.
- **Validating `lifecycle_event.py`'s `complexity-override --reason`.** A second, entirely unvalidated tier-reason writer holding 24 free-prose rows. Validating it needs a per-field validator hook in `_emit_subcommand`, a dispatcher shared by every event kind. Follow-up ticket, together with its `is not None` guard (R3's divergence).
- **Renaming `--complexity` to `--tier`.** A ratified-glossary mismatch, not cosmetics — but a breaking CLI change across many callers.
- **Backfilling reasons onto the 157 existing rows.** They record what the runs actually did; rewriting them would falsify the corpus.

## Edge Cases

- **Both reason flags carry bad tags** → both diagnostics print, nothing is appended, exit 2. The all-or-nothing append (R6 of the original design) is preserved: validation still runs before the log directory is created.
- **A reason is supplied but its axis is already at rank** → no row, one stderr line naming the discarded reason, exit 0, JSON payload unchanged. Roughly a fifth of real invocations.
- **Both axes no-op** → two stderr lines, `state: noop`, exit 0.
- **`--tier-reason ""` alongside a valid `--criticality-reason`** → the tier key is omitted, the criticality reason is recorded normally. The two flags are independent.
- **An untagged reason** (no colon) → accepted verbatim, unchanged behavior. Only a colon-led out-of-set prefix is rejected.
- **Resume / re-run of refine** → the no-op guard makes the whole call idempotent; a re-run emits the discard diagnostic rather than duplicate rows.

## Changes to Existing Behavior

- **MODIFIED** — `--criticality-reason ""` currently writes `"reason": ""`; it will omit the key. This is a behavior change to an already-shipped flag. No reader observes the difference (dashboard, report, and overnight readers all use `.get()`/truthy access, not `"reason" in row`), and no test pins the current shape.
- **MODIFIED** — a reconcile that discards a supplied reason now writes to stderr where it previously stayed silent. Exit codes and JSON payloads are unchanged, so no caller parsing stdout is affected.
- **ADDED** — Step 4's two invocations carry one further flag each.

## Technical Constraints

- `project.md:64`'s three-site co-edit is **not** triggered — its condition is "adding a tag", and no tag is added.
- Wheel-before-prose is already satisfied: both flags landed in `2d8e2575`, an ancestor of `v4.6.0`. No version floor, no wheel bump, `PROTOCOL_VERSION` not implicated.
- ADR-0036 needs neither amendment nor successor: its data requirement is criticality-scoped by its own text, its re-open trigger is computable from `from`/`to` alone, and it already documents this flag as a corpus-reading caveat.
- `skills/refine/SKILL.md` is lifecycle-gated (satisfied by this lifecycle); `cortex_command/refine.py` is not. The `plugins/cortex-core/` mirror is rebuilt from the staged blob by the pre-commit hook — never hand-staged.
- Budgets have headroom and are untouched: SKILL.md is 94/500 lines; the L1 ratchet measures frontmatter only; `skills/refine/references/` sits at zero headroom but is not measured for `SKILL.md`.
- `cortex-refine` on PATH runs the installed wheel — verify with `uv run python -m cortex_command.refine`.

## Open Decisions

None.

## Proposed ADR

None considered. The vocabulary decision is reversible in one file, ADR-0036 already owns the clause-vocabulary area, and the deferral plus its re-measure trigger is recorded above and in the commit body — a second ADR restating it would be ceremony the three-criteria gate does not call for.
