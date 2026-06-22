# Plan: post-discovery-brief-over-cap

## Overview

Reclassify the discovery gate's word cap from a posting gate to an advisory signal,
entirely within `cortex_command/discovery.py` and the prose-driven gate in
`skills/discovery/SKILL.md`. The shared `validate_brief` predicate stops hard-failing
over-cap (so both the generator's persist path and the file-reading gate contract accept
it), the generator persists + posts over-cap briefs with an `ok_over_cap` telemetry status
and a soft note, and the governing gate prose is **extended** (not rewritten) with an
over-cap soft-note display — the gate's existing three fallback triggers already match the
new behavior and stay verbatim — then re-mirrored in the same unit. Phase 1 also reconciles
the docstrings of the two surfaces it edits (`validate_brief` and `GATE_BRIEF_WORD_CAP`) so
the shippable unit never contains a function/constant whose docstring contradicts its new
behavior. Phase 2 reconciles the one remaining additive surface — the retry-feedback
template's stale posting-gate wording — and pins the change's scope with a regression test.

> **Phase-sequencing note (refines spec MoSCoW)**: the spec tags all of R10's wording
> reconciliation as Phase 2 ("Should"). This plan sequences R10's **docstring** sub-items
> (the `validate_brief` and `GATE_BRIEF_WORD_CAP` docstrings) into Phase 1 (Tasks 1–2),
> because a function/constant and its docstring must change atomically — leaving Phase 1
> shipping a predicate whose docstring still asserts the cap is enforced would be a
> self-contradictory contract, not deferrable hardening. Only R10's retry-template wording
> (genuinely additive: the template still functions) and R11/R12 remain in Phase 2, so the
> deferrable phase leaves zero contradictions.

**Architectural Pattern**: layered

**Verification reality (read first)**: the live research→decompose gate is *prose* in
`skills/discovery/SKILL.md` that a runtime agent executes — there is **no production render
function**. So no automated test can exercise the live "gate posts the brief" decision
end-to-end. What `just test` verifies: (a) the `validate_brief` predicate (Task 1), (b) the
`generate-brief` CLI subcommand's exit/persist/`ok_over_cap` behavior (Task 2), and (c) the
test-local `_render_gate` contract *mirror* (Task 5) — a re-implementation of the
file-reading contract the prose must encode, NOT the live agent path. **The mirror is
green by construction**: Task 5 authors both the helper logic and the assertion, so it
proves the *contract* is self-consistent, not that the SKILL.md prose encodes it (the 5→4
edge is authoring-discipline parity, not test-enforced). The live prose gate's correctness
is verified by human review of the Task 4 prose edit. Task 4's *machine* check is therefore
deliberately scoped to a **falsifiable presence-check** (the added soft-note instruction
introduces an `overage` token that is absent at HEAD) plus the marker-phrase/Architecture
pins in `test_discovery_gate_presentation.py` (via `just test`) — NOT the earlier
tautological `grep … = 0` absence check, which passed on unmodified HEAD and could not
detect a missing edit. The plan does not claim `just test` proves the runtime gate posts.

## Outline

### Phase 1: Soft-cap fix — validator + generator + gate prose (tasks: 1, 2, 3, 4, 5)
**Goal**: An anchor-valid over-cap brief posts (with a soft note + `ok_over_cap`) instead
of falling back to the `## Architecture` dump; empty/SDK/anchor-missing briefs unchanged;
the two discovery.py surfaces this phase edits (`validate_brief`, `GATE_BRIEF_WORD_CAP`)
carry docstrings consistent with the new advisory behavior.
**Checkpoint**: `just test` green with the new `validate_brief` unit tests, the stubbed
generator test (exit 0 + `brief.md` persisted + `status == "ok_over_cap"`), and the
`_render_gate` contract-mirror test (over-cap brief + soft note rendered, Architecture
absent); the SKILL.md gate prose **adds** the over-cap soft-note display instruction (the
three existing fallback triggers are unchanged), verified by the falsifiable `overage`-token
presence check and the `test_discovery_gate_presentation.py` marker-phrase pins; the
`validate_brief` and `GATE_BRIEF_WORD_CAP` docstrings no longer assert an enforced cap; and
the plugin-mirror drift gate passes. (Live-gate posting behavior is verified by review of
the Task 4 prose, not by `just test` — see Verification reality above.)

### Phase 2: Additive hardening — retry-template wording + scope pin (tasks: 6, 7)
**Goal**: The one remaining stale surface — the retry-feedback template's posting-gate
framing — is reconciled without degrading the live anchor/empty retry (the docstring
contradictions are already resolved in Phase 1); the generation-time target is documented
as deliberately retained; the soft-cap change's scope (anchor-valid only) is pinned. This
phase is genuinely deferrable — it changes no maintainer-facing contract and leaves no
contradiction if it lands after Phase 1.
**Checkpoint**: `grep -c 'hard ceiling' cortex_command/discovery.py` = 0,
`test_retry_feedback_covers_example_tokens` green, the new scope-regression test green,
`just test` green.

## Dispatch constraint (load-bearing — read before scheduling)

This feature MUST be implemented with **sequential, in-tree dispatch** — NOT parallel
`Agent(isolation: "worktree")`. Two independent reasons: (1) `just test` runs the editable
install, so a worktree verifies stale `cortex_command` code; (2) four tasks (1, 2, 5, 7)
edit `tests/test_discovery_gate_brief.py` and three (1, 2, 6) edit
`cortex_command/discovery.py`, so parallel dispatch into one shared worktree would clobber
(last-writer-wins). Under sequential dispatch the `Depends on` edges define order and the
shared-file edits are race-free. The edges below ALSO linearize each same-file group as
defense-in-depth (discovery.py: 1→2→6; test file: 1→2→5→7).

## Tasks

### Task 1: Make the word cap advisory in `validate_brief` + add overage helper
- **Files**: cortex_command/discovery.py, tests/test_discovery_gate_brief.py
- **What**: Remove the hard-fail word-cap branch from `validate_brief` so an anchor-valid,
  non-empty, over-cap brief returns `(True, "")`; add a `brief_word_overage` helper that
  surfaces the overage as a non-blocking signal; **reconcile `validate_brief`'s own
  docstring** in the same edit so it no longer asserts the cap is enforced (a function and
  its docstring change atomically). Add unit tests for the predicate and the helper.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `validate_brief` at `discovery.py:549-621`; the word-cap branch is the FINAL
  check at lines 612-621 (after the empty check at 587 and the three anchor checks at
  591-610). Delete/neutralize lines 612-621's `return False` so the function falls through
  to `return True, ""` once anchors pass. Keep the `(bool, str)` signature unchanged. New
  helper signature: `def brief_word_overage(brief: str) -> int` returning the number of
  words by which the brief exceeds `GATE_BRIEF_WORD_CAP + 25` (0 when within the ceiling);
  place adjacent to `validate_brief`. **Docstring reconciliation**: the summary line at
  `discovery.py:550` ("Check a generated brief for decision-content anchors **and word-cap
  tolerance**") and the "Word-cap tolerance: the brief must be at most ``GATE_BRIEF_WORD_CAP
  + 25`` words (Req 5a)" clause at `discovery.py:576-577` both currently assert enforcement
  — rewrite them to state the cap is **advisory** (surfaced via `brief_word_overage`, not a
  validation gate). Add parametrized unit tests near `test_validate_brief_canonical_floor`
  (test:907) asserting an over-cap anchored brief → `(True, "")` and `brief_word_overage`
  returns 0 within-cap / positive over-cap.
- **Verification**: `python3 -c "from cortex_command.discovery import validate_brief, brief_word_overage as o; b='We decided to ship. Alternatives were weighed. The tradeoff is cost. '+'filler '*400; print(validate_brief(b)[0], o(b)>0, o('decided alternatives tradeoff')==0)"` prints `True True True` (prints `False ...` against current code — genuinely falsifiable); AND `grep -c 'must be at most' cortex_command/discovery.py` = 0 (the docstring no longer asserts an enforced maximum — pass if count 0); AND `just test` exits 0.
- **Status**: [ ] pending

### Task 2: Persist + post the over-cap brief from `_cmd_generate_brief` with `ok_over_cap`
- **Files**: cortex_command/discovery.py, tests/test_discovery_gate_brief.py
- **What**: When a generated brief is non-empty and anchor-valid but over-cap, persist
  `brief.md`, print to stdout, emit `gate_brief_generated` with `status: "ok_over_cap"` and
  the real `brief_word_count`, and exit 0 — rather than the `validation_failed`/`return 1`
  fallback. **Reconcile the `GATE_BRIEF_WORD_CAP` docstring** in the same edit, since this
  task is what makes over-cap stop falling back. Add a stubbed test for the path.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `_cmd_generate_brief` at `discovery.py:727-890`; success path (event + stdout
  + persist) at 870-890; `_emit_event` closure at 776-807. After Task 1, validate_brief
  passes over-cap so control already reaches the success path — branch the status at the
  `_emit_event("ok", ...)` call (line 870) on `brief_word_overage(brief) > 0` → emit
  `"ok_over_cap"`. No change to the retry block (836) — over-cap no longer triggers it (the
  retry still fires for empty/anchor-missing failures). **Docstring reconciliation**: the
  `GATE_BRIEF_WORD_CAP` docstring at `discovery.py:273-289` currently frames the cap as a
  "275 effective ceiling" that "distinguish[es] a tight gate brief from a full section dump"
  and ends "Pair with the retry-on-overflow logic in ``_cmd_generate_brief`` for additional
  resilience" (line 287) — describing exactly the over-cap fallback this task removes.
  Rewrite it to describe the cap as a generation-time **target + soft advisory signal**
  (surfaced via the soft note / `ok_over_cap`), and drop the over-cap retry-on-overflow
  pairing. Model the new test on `test_validation_failed_event_includes_brief_excerpt`
  (test:409): stub `_run_brief_query` to return an over-cap anchored brief (stub must ignore
  `retry_feedback` so the first validation passes deterministically).
- **Verification**: `just test` exits 0 — the new stubbed over-cap test asserts ALL of:
  exit code 0, `brief.md` written with the stubbed brief's content, AND a
  `gate_brief_generated` event with `status == "ok_over_cap"` and `brief_word_count` equal
  to the brief's word count; AND the existing `test_brief_failure_falls_back_to_architecture`
  (anchor-missing) still passes; AND `grep -c 'retry-on-overflow' cortex_command/discovery.py`
  = 0 (the constant docstring no longer pairs the cap with over-cap retry-on-overflow — pass
  if count 0).
- **Status**: [ ] pending

### Task 3: Register `ok_over_cap` in the events registry
- **Files**: bin/.events-registry.md
- **What**: Extend the `gate_brief_generated` row's documented status values to include
  `ok_over_cap` (brief posted despite exceeding the advisory word cap).
- **Depends on**: none
- **Complexity**: simple
- **Context**: the `gate_brief_generated` entry is at `bin/.events-registry.md:119`; its
  notes column currently reads "status field distinguishes ok / fallback ...". Add
  `ok_over_cap` to that enumeration with a one-clause description. Do not change the row's
  scan-coverage or status columns.
- **Verification**: `grep -c 'ok_over_cap' bin/.events-registry.md` ≥ 1 AND the
  events-registry gate `cortex-check-events-registry --audit` exits 0.
- **Status**: [ ] pending

### Task 4: Extend the prose-driven gate with the over-cap soft note, regenerate the plugin mirror
- **Files**: skills/discovery/SKILL.md, plugins/cortex-core/skills/discovery/SKILL.md
- **What**: **Add** an over-cap soft-note display instruction to the research→decompose gate
  paragraph; regenerate the auto-mirror in the same change. The gate's existing three
  fallback triggers already match the new behavior and stay verbatim — this task adds the
  soft-note path, it does not remove a trigger (the prose never encoded a word-cap trigger;
  over-cap fallback was a Python-side property of `validate_brief`, now removed by Task 1).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: the gate paragraph is at `skills/discovery/SKILL.md:88` and **already** reads
  "If brief generation exits non-zero, OR `brief.md` is missing after the command runs, OR
  `brief.md` fails decision-content validation, the gate falls back ..." — exactly the three
  correct triggers, with no word-count mention anywhere in the file (verified: `grep -ic
  'word count'` = 0 at HEAD). Leave that sentence as-is. **Add** a following sentence:
  when `brief.md` is present, the generator exited 0, and anchors pass, but the word count
  exceeds the cap, display the brief followed by a one-line overage note — e.g. "(summary
  ran N words over the 275-word advisory cap)". **Wording precision**: 275 is
  `GATE_BRIEF_WORD_CAP + 25` (the tolerance-inclusive ceiling that `brief_word_overage`
  measures overage *past*), NOT the generation target — `GATE_BRIEF_WORD_CAP` is 250 and the
  rubric emits "no more than 250 words". Call 275 the "advisory cap"/"ceiling", never the
  "target". **Do not disturb the surrounding marker phrases**: `tests/test_discovery_gate_presentation.py`
  pins verbatim substrings against this file — `BRIEF_INVOCATION_MARKER_PHRASE`
  ("cortex-discovery generate-brief"), `GATE_OPTIONS_MARKER_PHRASE`
  ("<approve|revise|drop|promote-sub-topic>"), the R3 `drop` dual-use phrase, and a GATE-2
  Architecture-vocabulary drift guard — all must survive the edit. Then run `just
  build-plugin` to regenerate `plugins/cortex-core/skills/discovery/SKILL.md` (never
  hand-edit the mirror — drift hook).
- **Verification**: (falsifiable presence-check) `grep -ic 'overage' skills/discovery/SKILL.md`
  ≥ 1 (0 at HEAD — passes only if the soft-note instruction was actually added; genuinely
  falsifiable, unlike an absence grep); AND `just test` exits 0 (covers
  `test_discovery_gate_presentation.py`'s marker-phrase and Architecture-vocabulary pins, so
  a reflow that disturbs them fails loud); AND after `just build-plugin`, the dual-source
  drift gate (`cortex-check-parity` / pre-commit drift hook) reports the mirror
  byte-identical (exit 0). (Correctness of the soft-note *instruction wording* and the live
  agent's posting decision are human-reviewed at approval — inherent to a prose gate; the
  file-reading contract it must encode is pinned by Task 5's mirror test.)
- **Status**: [ ] pending

### Task 5: Extend the `_render_gate` contract mirror to cover the over-cap + soft-note path
- **Files**: tests/test_discovery_gate_brief.py
- **What**: Extend the test-local `_render_gate` helper to mirror the FULL over-cap contract
  (when `brief.md` is over-cap-but-anchored: render the brief text plus the soft note, not
  the Architecture fallback), and add a test scenario asserting it.
- **Depends on**: [2, 4]
- **Complexity**: simple
- **Context**: the `_render_gate` helper + contract test are at
  `test_discovery_gate_brief.py:270-307` and `test_gate_renders_brief_not_architecture`
  (test:310). The helper currently returns raw `brief_text` when `validate_brief(...)[0]` is
  True. Extend it to append the soft note when `brief_word_overage(brief_text) > 0`, mirroring
  the Task 4 prose contract — use the same overage-note token Task 4 adds (e.g. the "advisory
  cap" / "overage" phrasing) so the mirror and the prose stay in lockstep. Add a scenario
  writing an over-cap anchored `brief.md` (>275 words = over `GATE_BRIEF_WORD_CAP + 25`, all
  three anchors) and assert the rendered output contains the brief text AND the soft-note
  marker AND does NOT contain the `## Architecture` section body. This pins the file-reading
  contract the SKILL.md prose (Task 4) must encode — it is a test-local mirror, not a test of
  the live agent-executed gate. **The 5→4 dependency is authoring-discipline parity**: this
  test never reads `skills/discovery/SKILL.md`, so it would pass even if Task 4 had not run —
  the edge exists so the implementer writes the mirror to match Task 4's wording, and its
  violation surfaces as silent prose↔mirror drift, not a test failure (hence the human review
  of the Task 4 prose noted in Verification reality).
- **Verification**: `just test` exits 0 — the extended `_render_gate` over-cap scenario
  passes (brief text present, soft-note marker present, Architecture body absent).
- **Status**: [ ] pending

### Task 6: Reconcile the retry-feedback template's posting-gate wording; document the retained target
- **Files**: cortex_command/discovery.py
- **What**: Reconcile the one remaining stale soft-cap surface — the retry-feedback
  template's posting-gate framing — WITHOUT degrading the live anchor/empty retry; keep the
  generation-time word target and document it as intentional. (The `validate_brief` and
  `GATE_BRIEF_WORD_CAP` docstrings are reconciled in Tasks 1 and 2 so Phase 1 ships
  self-consistent; this task owns only the operational retry template + the target note.)
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: (a) the retry-feedback template `_GATE_BRIEF_RETRY_TEMPLATE` at
  `discovery.py:370-400` — remove the "(hard ceiling {GATE_BRIEF_WORD_CAP + 25})"
  parenthetical (line 374, the sole "hard ceiling" occurrence) but PRESERVE the "Rewrite at
  no more than {GATE_BRIEF_WORD_CAP} words" clause, the per-anchor example-token
  enumerations, and the `{reason}` interpolation. **Coverage note**: `test_retry_feedback_covers_example_tokens`
  (test:789) pins only the example tokens and `{reason}` — it does NOT guard the "no more
  than {N} words" clause; that clause is guarded by this task's own `grep -c 'no more than'
  ≥ 1`, not by the pinned test. (b) the rubric system prompt at `discovery.py:338` keeps its
  "write no more than {GATE_BRIEF_WORD_CAP} words" instruction unchanged; add a one-line
  docstring note that the generation-time target is deliberately retained as a best-effort
  brevity nudge while posting is advisory.
- **Verification**: `grep -c 'hard ceiling' cortex_command/discovery.py` = 0 AND
  `grep -c 'no more than' cortex_command/discovery.py` ≥ 1 AND `just test` exits 0
  (`test_retry_feedback_covers_example_tokens` passes).
- **Status**: [ ] pending

### Task 7: Pin the soft-cap scope (anchor-missing over-cap still fails) + clarify the fixture-test intent
- **Files**: tests/test_discovery_gate_brief.py
- **What**: Add a regression test confirming the soft-cap change is scoped to anchor-valid
  briefs — an over-cap brief that is ALSO anchor-missing still fails validation (returns the
  anchor reason, not `(True, "")`). This catches an over-broad Task 1 implementation that
  accepts ANY over-cap brief regardless of anchors. Annotate the fixture-length assertion as
  a corpus-quality check.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: add a unit test feeding a >275-word brief that LACKS one decision anchor and
  assert `validate_brief(brief)` returns `(False, <anchor reason>)` — NOT `(True, "")`. This
  is non-tautological: it fails if Task 1 is mis-implemented to short-circuit over-cap briefs
  to `True` before the anchor checks. Separately, update the comment on the `word_count <= cap`
  assertion in `test_brief_passes_all_fixtures` (test:147-153) to state it is a corpus-quality
  check on canonical fixtures, explicitly NOT a production-contract assertion (production now
  accepts over-cap briefs).
- **Verification**: `just test` exits 0 — the new scope-regression test passes (over-cap
  anchor-missing brief → `(False, <anchor reason>)`), and the fixture test continues to pass.
- **Status**: [ ] pending

## Risks

- **Sequential dispatch is mandatory** (see "Dispatch constraint" above) — parallel worktree
  dispatch both verifies stale editable-install code and clobbers the shared test/discovery
  files. This feature is NOT eligible for parallel worktree dispatch (interactive or overnight).
- **Prose gate has no end-to-end automated test** (see "Verification reality") — the live
  gate's posting decision is verified by human review of the Task 4 prose; `just test` covers
  the predicate, the CLI subcommand, and the file-reading contract mirror only. This is
  inherent to a prose-driven gate, not a coverage gap to "fix" with more tests.
- **Drift-hook coupling (Task 4)**: the canonical SKILL.md edit and its regenerated mirror
  must land in the same commit; run `just build-plugin` before committing Task 4.
- **Accepted product tradeoff (recorded, not a risk to fix)**: the cap no longer constrains
  length — an anchor-valid arbitrarily-long brief posts. This is the operator's informed
  no-ceiling decision (spec Non-Requirements).

## Acceptance

Running the discovery research→decompose gate on a research.md whose generated brief is
anchor-valid but exceeds 275 words posts that brief — with a one-line overage soft note —
as the gate summary instead of the `## Architecture` dump, and emits a `gate_brief_generated`
event with `status: ok_over_cap`. Empty, SDK-failed, and missing-anchor briefs still fall
back unchanged. Verified by: `just test` green (new `validate_brief`, generator-`ok_over_cap`,
`_render_gate` over-cap+soft-note mirror, and scope-regression tests) and the plugin-mirror
drift gate; plus human review confirming the Task 4 SKILL.md prose instructs the over-cap
soft-note display (the live prose gate has no automated end-to-end test by construction).
