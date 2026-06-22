# Specification: post-discovery-brief-over-cap

## Problem Statement

Today the discovery research→decompose gate generates a brief summary, validates
it, and — if the brief exceeds the 275-word effective ceiling — **discards it** and
falls back to dumping the raw `## Architecture` section with a `brief_generation_failed`
warning. Because the brief generator (a Sonnet sub-agent) naturally emits ~300-word
output regardless of the word target, an anchor-valid, perfectly coherent summary is
routinely thrown away in favor of a denser section dump. The operator reading the gate
loses the summary they wanted. This feature reclassifies the word cap from a *posting
gate* to an *advisory*: an over-cap brief that still contains the three decision-content
anchors is posted as the gate summary with a one-line soft note. Empty, SDK-failed, and
missing-anchor briefs continue to fall back unchanged.

**Honest scope of what the cap becomes**: this change *removes* the word cap's
enforcement as a posting gate. It does **not** preserve the cap as a length constraint.
What survives the change is (a) a generation-time brevity *target* in the rubric
(best-effort, deliberately retained), (b) a one-line soft note at the gate, and (c) an
`ok_over_cap` telemetry status. None of these constrain length — they only surface it.
"Post at any length / no runaway ceiling" is an explicit, informed operator decision
(Clarify §4: the operator chose "post at any length" over "keep a runaway ceiling," with
the degenerate-full-dump tradeoff stated in the question).

## Phases

- **Phase 1: Soft-cap fix (validator + generator + gate prose)** — the complete,
  coherent, operator-visible fix as a single shippable unit: make the cap advisory in
  `validate_brief`, persist + post the over-cap brief from `_cmd_generate_brief`
  (exit 0, `ok_over_cap`), register the status, **reword the prose-driven gate in
  `skills/discovery/SKILL.md` + add the soft note**, regenerate the plugin mirror, and
  cover the over-cap render path in tests. The gate is prose-driven, so the SKILL.md
  edit is part of the fix — not polish; runtime and governing prose change together.
- **Phase 2: Contract hardening + wording reconciliation** — reconcile every remaining
  stale soft-cap surface (the `validate_brief` docstring, the `GATE_BRIEF_WORD_CAP`
  docstring, the retry-feedback template), pin R5's fallback guarantee against a future
  cap-branch reorder, and clarify the fixture-length test's intent.

**Priority (MoSCoW)**: Phase 1 (R1–R9) is **Must** — it is the complete operator-visible
fix and ships as one unit so the prose-driven gate's documented behavior never contradicts
runtime. Phase 2 (R10–R12) is **Should** — genuine hardening (wording reconciliation,
ordering pin, test-intent clarity) that does not change operator-visible behavior and can
follow without leaving a broken state. The `## Non-Requirements` section enumerates the
**Won't**.

## Requirements

1. **Word cap is advisory in `validate_brief`**: An anchor-valid, non-empty brief that
   exceeds `GATE_BRIEF_WORD_CAP + 25` words no longer fails validation. Acceptance: a new
   unit test feeds a >275-word brief containing all three decision-content anchors and
   asserts `validate_brief(brief) == (True, "")`; `just test` exits 0. (Grounds:
   `cortex_command/discovery.py:612-621`.) **Phase**: Phase 1: Soft-cap fix

2. **Overage exposed as a separate non-blocking signal**: A helper exposes the word
   overage so the generator and gate can warn without blocking. Acceptance: a new unit
   test asserts the helper returns 0 for a within-cap brief and the positive
   words-over-`GATE_BRIEF_WORD_CAP+25` count for an over-cap brief; `just test` exits 0.
   **Phase**: Phase 1: Soft-cap fix

3. **Generator persists + posts the over-cap brief**: When a generated brief is non-empty
   and anchor-valid but over-cap, `_cmd_generate_brief` writes `brief.md` (when
   `--persist-to` is given), prints it to stdout, and exits 0. Acceptance: a test stubbing
   `_run_brief_query` (as `test_validation_failed_event_includes_brief_excerpt` does, with
   a stub that ignores `retry_feedback` so the first validation deterministically passes
   and no retry fires) to return an over-cap anchored brief asserts exit code 0 AND
   `brief.md` exists AND its content equals the generated brief; `just test` exits 0.
   (Grounds: `cortex_command/discovery.py:727-890`.) **Phase**: Phase 1: Soft-cap fix

4. **Over-cap posts carry an `ok_over_cap` telemetry status**: The `gate_brief_generated`
   event for a posted over-cap brief carries `status: "ok_over_cap"` and the actual
   `brief_word_count`. Acceptance: the R3 test asserts the emitted `gate_brief_generated`
   event has `status == "ok_over_cap"` and `brief_word_count` equal to the brief's word
   count; `just test` exits 0. **Phase**: Phase 1: Soft-cap fix

5. **Unchanged fallback for real failures**: Empty briefs, SDK/dispatch failures, and
   missing-decision-anchor briefs still exit non-zero, do not persist `brief.md`, and emit
   a failure status. Acceptance: the existing `test_brief_failure_falls_back_to_architecture`
   (anchor-missing input) and `test_validation_failed_event_includes_brief_excerpt` pass
   unchanged; `just test` exits 0. **Phase**: Phase 1: Soft-cap fix

6. **`ok_over_cap` registered in the events registry**: Acceptance:
   `grep -c 'ok_over_cap' bin/.events-registry.md` ≥ 1 AND the events-registry pre-commit
   gate (`cortex-check-events-registry`) passes. **Phase**: Phase 1: Soft-cap fix

7. **Prose-driven gate posts the over-cap brief with a soft note**: The discovery gate is
   prose-driven — an agent reads `skills/discovery/SKILL.md:88` to decide whether to
   display `brief.md` or fall back. That prose must change for the fix to land. Acceptance
   (observable state, form b): in `skills/discovery/SKILL.md`, the research→decompose gate
   section (the paragraph beginning "If brief generation exits non-zero") (a) enumerates
   exactly three Architecture-fallback triggers — generator non-zero exit, `brief.md`
   missing, and decision-content (anchor) validation failure — with **no** mention of word
   count / cap among them, and (b) contains an explicit instruction to display the brief
   plus a one-line overage note when the posted brief is over-cap (i.e. `brief.md` exists,
   generator exited 0, anchors present, but the word count exceeds the cap). Runtime
   behavior is pinned by R9's render test. **Phase**: Phase 1: Soft-cap fix

8. **Plugin mirror regenerated with the SKILL.md edit**: `plugins/cortex-core/skills/discovery/SKILL.md`
   matches the edited canonical `skills/discovery/SKILL.md`, committed together (the
   drift gate forbids splitting them). Acceptance: after `just build-plugin`, the
   dual-source drift pre-commit gate passes (mirror is byte-identical to the regenerated
   output). **Phase**: Phase 1: Soft-cap fix

9. **Gate-render contract test covers the over-cap path**: The gate-render test
   (`tests/test_discovery_gate_brief.py`, `_render_gate` helper) renders an over-cap
   anchored `brief.md` as the brief — NOT the Architecture fallback. Acceptance: a
   new/extended test asserts that for an over-cap anchored `brief.md`, the rendered output
   contains the brief text and does NOT contain the Architecture-section body; `just test`
   exits 0. **Phase**: Phase 1: Soft-cap fix

10. **Reconcile every stale soft-cap wording surface (without breaking the live retry)**:
    No caller-facing contract may assert that over-cap blocks posting. Three surfaces in
    `cortex_command/discovery.py` are reconciled: (a) the `GATE_BRIEF_WORD_CAP` docstring
    (no longer states over-cap causes fallback); (b) the `validate_brief` docstring at
    lines 576-577 (currently "the brief must be at most `GATE_BRIEF_WORD_CAP + 25` words" —
    must reflect that the cap is now advisory, not enforced); (c) the retry-feedback
    template (drop the over-cap "hard ceiling" / posting-gate framing). The retry-template
    rewrite **must preserve** its word-target clause, its per-anchor example-token
    enumerations, and its `{reason}` interpolation — these are pinned by
    `test_retry_feedback_covers_example_tokens` (`tests/test_discovery_gate_brief.py:789`).
    Acceptance: `grep -c 'hard ceiling' cortex_command/discovery.py` = 0 AND
    `test_retry_feedback_covers_example_tokens` passes AND the `validate_brief` docstring
    no longer asserts an enforced word maximum; `just test` exits 0. **Phase**: Phase 2: Contract hardening

11. **Generation-time word target retained deliberately**: The rubric system prompt's
    "write no more than `{GATE_BRIEF_WORD_CAP}` words" instruction (`discovery.py:338`) is
    **intentionally kept** as a best-effort brevity nudge — ask-for-brevity at generation
    time while accepting whatever is produced at posting time is the intended design, not a
    contradiction. Acceptance (observable state): the rubric still contains the word-target
    instruction (`grep -c 'no more than' cortex_command/discovery.py` ≥ 1) AND the docstring
    documents the target-vs-acceptance split as intentional; `just test` exits 0.
    **Phase**: Phase 2: Contract hardening

12. **Pin R5's fallback guarantee against a cap-branch reorder + clarify the fixture test**:
    (a) A test asserts that an over-cap AND anchor-missing brief still fails validation with
    the anchor reason (so the advisory cap branch staying after the anchor checks is pinned;
    a future reorder that returns `(True, "")` for such a brief would fail this test).
    (b) The `word_count <= cap` assertion in `test_brief_passes_all_fixtures` (test:147-153)
    is documented (code comment) as a corpus/fixture-quality check (canonical examples model
    tight briefs) — explicitly NOT a production-contract assertion, since production now
    accepts over-cap briefs. Acceptance: the new ordering test passes; the fixture-test
    comment names it a fixture-quality check; `just test` exits 0. **Phase**: Phase 2: Contract hardening

## Non-Requirements

- Does **not** change the `GATE_BRIEF_WORD_CAP` value (250) or the +25 tolerance — the
  threshold is retained as the generation-time target and the soft-warning trigger point.
- Does **not** preserve the word cap as an enforced *length constraint* at the gate. Its
  enforcement as a posting gate is removed; only the generation-time target, the soft note,
  and telemetry survive. This is the operator's explicit, informed choice (Clarify §4).
- **Accepted tradeoff**: an anchor-valid but arbitrarily long brief (e.g., a degenerate
  near-verbatim research dump that happens to contain the three anchor words) will post at
  full length. This residual is the accepted consequence of the no-runaway-ceiling decision
  — not a defect to guard against.
- Does **not** change fallback behavior for empty, SDK-failed, dispatch-failed, or
  missing-decision-anchor briefs.
- Does **not** change the decision-content anchor vocabulary or the canonical-floor parity
  test.
- Does **not** add a user-facing approval/confirmation step inside the gate for over-cap
  briefs — the brief simply posts with the soft note.

## Edge Cases

- **Over-cap brief on the post-retry path**: a first brief that is anchor-missing triggers
  the existing retry; if the retry returns an anchor-valid but over-cap brief, it is
  validated as `(True, "")` and posted with `ok_over_cap` — the retry result benefits from
  soft-cap too.
- **Over-cap AND anchor-missing simultaneously**: `validate_brief` checks anchors before
  the word cap, so an anchor-missing brief returns the anchor reason first and falls back —
  over-cap only matters once all anchors are present. R12 pins this ordering with a test so
  a future reorder cannot silently regress R5.
- **Brief exactly at `cap + 25` (275 words)**: not over-cap (check is strict `>`); posts as
  a normal `ok` brief — unchanged.
- **Degenerate large over-cap brief**: posts at any length per the operator decision; the
  soft note reports the (large) overage. No ceiling (see Non-Requirements accepted tradeoff).
- **`--persist-to` omitted**: over-cap brief still prints to stdout and exits 0; no file is
  written (same persistence semantics as a within-cap `ok` brief).

## Changes to Existing Behavior

- MODIFIED: `validate_brief` over-cap branch (`discovery.py:612-621`) — was
  `(False, "...exceeds cap...")`, now `(True, "")` for anchor-valid over-cap briefs.
- MODIFIED: `_cmd_generate_brief` over-cap outcome — was exit 1, no persist,
  `validation_failed` event, Architecture fallback; now exit 0, persist, `ok_over_cap`
  event, brief posted.
- MODIFIED: retry-on-overflow no longer targets over-cap (an over-cap brief is now valid →
  no retry); the retry remains for empty/anchor-missing failures, and its word-target +
  token-enumeration + `{reason}` prompt content is preserved (R10).
- MODIFIED: discovery gate prose + plugin mirror (`SKILL.md:88` + mirror) — over-cap removed
  from the fallback-trigger list; over-cap now displays the brief with a soft note. Lands
  in the SAME phase/commit as the validator+generator change so governing prose never
  contradicts runtime.
- MODIFIED: `gate_brief_generated` events-registry entry — adds `ok_over_cap` to the
  documented status values.
- MODIFIED: `validate_brief` and `GATE_BRIEF_WORD_CAP` docstrings — reconciled to advisory
  semantics (R10).
- ADDED: `ok_over_cap` event status; word-overage helper.

## Technical Constraints

- The discovery gate is **prose-driven**: an agent reads `skills/discovery/SKILL.md:88` to
  decide fallback. `validate_brief` is the single source of truth for the *generator's*
  persist/exit decision (`discovery.py:830,859`) and for the `_render_gate` *test* mirror
  (`test_discovery_gate_brief.py:287`) — but a Python return value does **not** propagate
  into the prose the live gate agent reads. The gate prose must therefore be edited directly
  (R7), in the same unit as the validator change.
- Pinned test surfaces this change touches (none may be broken silently): the canonical-floor
  parity test (anchor tokens only — untouched), `test_retry_feedback_covers_example_tokens`
  (`test:789` — retry-template tokens + `{reason}`, preserved by R10), and
  `test_brief_passes_all_fixtures`'s `word_count <= cap` assertion (`test:147-153` — a
  fixture-quality check that stays green because corpus fixtures are tight; clarified by R12,
  not a production contract).
- No production code switches on `gate_brief_generated.status`; `ok_over_cap` is safe to add
  but is inert telemetry (a greppable signal, not a consumed one).
- The Phase-1 unit (validator + generator + gate prose + mirror + render test) must land
  together; the plugin mirror auto-regenerates via the pre-commit drift hook — edit the
  canonical `skills/discovery/SKILL.md` only and commit the regenerated mirror in the same
  commit (`just build-plugin`).
- The events-registry pre-commit gate and the backlog `grep -c` Done-When resolution require
  `ok_over_cap` to be registered before any acceptance check greps for it.
- Test command: `just test`.

## Open Decisions

None — the retry-behavior and event-status-shape questions deferred from research resolve at
spec time (retry naturally no longer fires on over-cap; status is `ok_over_cap`). The
no-runaway-ceiling question was an explicit operator decision in Clarify §4.

## Proposed ADR

None considered.
