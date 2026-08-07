# Plan: escalated-is-terminal-so-operator-direction

## Overview

Add exactly one new encoded phase form — `escalated:rework-cap:<n>` — to the phase vocabulary, derived at read time from `review.md`, and teach the four operator-facing surfaces to narrate it. Bare `escalated` keeps its current meaning (reviewer REJECTED), so every existing label, fixture, and wire value stays valid and the change is purely additive on the wire.

Two key architectural decisions:

- **`phase` and `route` split.** `_result()` in `common.py` today sets `route = phase`. The discriminant rides `phase` only; `route` stays the bare machine state `escalated`. That keeps `next_verb`'s `route not in tt.STATE_NAMES` check, `advance`'s from-state gate, and `_EVENTS_TERMINAL_STATES` membership working untouched — which is what makes R3's "-paused must not be appended" acceptance pass by construction rather than by a string patch.
- **Literal prefix checks at each site**, matching the established `implement-rework:` idiom, rather than a shared `lifecycle_phase_base()` normalizer. The one place the normalization is a *set-membership* test (`scan_lifecycle._is_terminal_mismatch`) gets a `startswith("escalated:")` clause alongside its existing `startswith("complete:")` clause. `phase_labels.py` stays import-free and pure.

The artifact detector's CHANGES_REQUESTED rung gains a cycle branch: cycle 1 → `implement-rework` (unchanged), cycle ≥ 2 → the cap form. That aligns the legacy artifact fallback with `review_verdict._route_target`, which has always routed cycle-≥2 CHANGES_REQUESTED to `escalated` — today the two disagree.

## Outline

### Phase 1: Encode the discriminant (tasks: 1, 2)
**Goal**: `detect_lifecycle_phase` and `resolve_lifecycle_phase` distinguish a rework-cap escalation from a rejection, and a parity fixture exists for the new case.
**Checkpoint**: `detect_lifecycle_phase` on the cycle-2 CHANGES_REQUESTED fixture returns `phase="escalated:rework-cap:2"`, `route="escalated"`.

### Phase 2: Render it (tasks: 3, 4, 5, 6, 7, 8)
**Goal**: the label, the SessionStart hint, the served directive, the statusline, and the backlog index each handle the new form; the full suite is green.
**Checkpoint**: `just test` passes with the new fixture collected by every parity subtest, and no surface says REJECTED for a capped feature.

## Tasks

### Task 1: Encode the rework-cap discriminant in the phase resolvers
- **Files**: `cortex_command/common.py`
- **What**: Emit `escalated:rework-cap:<cycle>` as `phase` (with `route` still `escalated`) whenever `review.md`'s last verdict is `CHANGES_REQUESTED` at cycle ≥ 2, in both the artifact detector and the events-first resolver.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `_result(phase)` (`:358-376`) currently sets `route = phase` and tests terminality with `phase not in ("complete", "escalated")`. Give it a second parameter — `_result(phase, route=None)` with `route = route or phase` — and switch the `is_paused` test to `route`. All existing call sites keep their single-argument form.
  - The verdict rung (`:403-410`): `CHANGES_REQUESTED` currently returns `_result("implement-rework")` unconditionally. Branch on the already-computed `cycle` local (`:355`, the count of `"verdict"` regex matches in `review.md`, floored at 1): `cycle >= 2` → `_result(f"escalated:rework-cap:{cycle}", route="escalated")`; else unchanged. `REJECTED` stays `_result("escalated")`.
  - `resolve_lifecycle_phase` (`:590-631`) returns `machine_state` for both `phase` and `route`. When `machine_state == "escalated"` **and** the artifact dict's `route` is also `"escalated"`, use the artifact's `phase` as the served `phase`; otherwise keep the bare state. That covers the real capped feature (which carries a `phase_transition to=escalated` row) and satisfies the spec's Edge Case for a missing/unparseable `review.md` by falling through to bare `escalated`. `route` and the `_EVENTS_TERMINAL_STATES` paused test keep reading `machine_state`, so no `-paused` suffix can attach.
  - Update the `detect_lifecycle_phase` docstring's step-2 mapping (`:440-450`) and its `phase` value set (`:456-463`).
- **Verification**: `uv run python -c "import json,pathlib,tempfile; from cortex_command.common import detect_lifecycle_phase as f; d=pathlib.Path(tempfile.mkdtemp()); (d/'review.md').write_text('{\"verdict\": \"CHANGES_REQUESTED\"}\n{\"verdict\": \"CHANGES_REQUESTED\"}\n'); r=f(d); print(r['phase'], r['route'], r['paused'])"` prints `escalated:rework-cap:2 escalated False`; the same command with a single CHANGES_REQUESTED line prints `implement-rework implement-rework False`, and with one `REJECTED` line prints `escalated escalated False`. **And** the events-first half, on a dir carrying both the cycle-2 `review.md` and an `events.log` whose `phase_transition` row has `to = escalated` followed by a later `feature_paused` row: `uv run python -c "import pathlib,tempfile; from cortex_command.common import resolve_lifecycle_phase as r; d=pathlib.Path(tempfile.mkdtemp()); (d/'review.md').write_text('{\"verdict\": \"CHANGES_REQUESTED\"}\n{\"verdict\": \"CHANGES_REQUESTED\"}\n'); (d/'events.log').write_text('{\"event\": \"phase_transition\", \"from\": \"review\", \"to\": \"escalated\"}\n{\"event\": \"feature_paused\"}\n'); x=r(d); print(x['phase'], x['route']); print(x['phase']=='escalated:rework-cap:2', not x['phase'].endswith('-paused'), x['route']=='escalated')"` prints `escalated:rework-cap:2 escalated` then `True True True` — this is R3's second acceptance (no `-paused` suffix on the discriminated form) made runnable rather than argued by construction. At HEAD it prints `escalated escalated` then `False True True`. Pass = all three detector cases **and** all three booleans of the resolver case.
- **Status**: [ ] pending

### Task 2: Add the cycle-2 CHANGES_REQUESTED parity fixture
- **Files**: `tests/fixtures/lifecycle_phase_parity/review-changes-requested-cycle2/review.md`
- **What**: Stage the rework-cap fixture the parity suite enumerates via `iterdir()`, so every parity subtest picks it up automatically.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Model on `tests/fixtures/lifecycle_phase_parity/review-changes-requested/review.md`. The detector's `cycle` is the **count of `"verdict"` regex matches**, not the `"cycle"` JSON field — so the fixture needs two verdict blocks, each on its own line (the bash mirror greps per line, so a two-verdicts-on-one-line file would desync bash from Python). No `events.log`: the fixture must exercise the artifact ladder, which is what the statusline parity subtest compares against. Directory name `review-changes-requested-cycle2` sorts adjacent to its cycle-1 sibling.
- **Verification**: `grep -c '"verdict"' tests/fixtures/lifecycle_phase_parity/review-changes-requested-cycle2/review.md` = 2, and `ls tests/fixtures/lifecycle_phase_parity/review-changes-requested-cycle2/` lists exactly `review.md`.
- **Status**: [ ] pending

### Task 3: Render the rework-cap label
- **Files**: `cortex_command/phase_labels.py`
- **What**: `phase_label("escalated:rework-cap:<n>")` returns a label naming the rework cap and the cycle; bare `escalated` keeps its REJECTED label.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Add a `startswith("escalated:rework-cap:")` branch **above** the `== "escalated"` branch (`:73-74`), mirroring the shape of the `implement-rework:` branch at `:68-70`. Target label: `Escalated — rework cap reached (review cycle <n>)`. Keep the module import-free and pure per its docstring — no `common` import. Update the docstring mapping table (`:19-32`) with the new row. This also satisfies R9: the dashboard registers this function as the `phase_label` Jinja filter (`dashboard/app.py:212-213`), so the new form never reaches the verbatim fall-through.
- **Verification**: `uv run python -c "from cortex_command.phase_labels import phase_label as p; a=p('escalated:rework-cap:2'); b=p('escalated'); print(a); print(b); print(a!=b and a!='escalated:rework-cap:2' and 'REJECTED' not in a)"` prints the two labels then `True`.
- **Status**: [ ] pending

### Task 4: Split the SessionStart hint and base-normalize the terminal check
- **Files**: `cortex_command/hooks/scan_lifecycle.py`
- **What**: The rework-cap case gets its own next-step hint naming the cycle, and `_is_terminal_mismatch` keeps counting the discriminated form as terminal.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **The function the spec calls `_next_step_hint` is actually `_interrupted_hint`** (`:93-163`) — the spec's R6 acceptance command names a symbol that does not exist. Use the real name.
  - Add a `startswith("escalated:rework-cap:")` branch above the `== "escalated"` branch (`:158-162`), shaped like the `implement-rework:` hint immediately above it (`:151-157`): name the cycle, say the rework cap was reached, point at `cortex/lifecycle/<feature>/review.md`, and name the sanctioned override (`cortex-lifecycle-event log --event <name> --feature <slug>`, the string `advance._SANCTIONED_OVERRIDE` at `advance.py:121-124` already teaches) as the recorded way to authorize another pass. The hint must not contain the literal `REJECTED`. The rejection branch is unchanged.
  - `_is_terminal_mismatch` (`:195-198`) receives the **encoded** phase (call site `:1004`), so the exact-match tuple misses the discriminated form. Add `or events_phase.startswith("escalated:")` alongside the existing `startswith("complete:")` clause.
  - Update the docstring hint-rule lists at `:104-110` and the `_encode_phase` docstring (`:43-48`) note that any other phase passes through bare — the cap form takes that arm unchanged, which is correct.
- **Verification**: `uv run python -c "from cortex_command.hooks.scan_lifecycle import _interrupted_hint as h, _is_terminal_mismatch as m; a=h('escalated:rework-cap:2','demo'); b=h('escalated','demo'); print(a); print(a!=b and 'REJECTED' not in a and '2' in a, m('escalated:rework-cap:2','in_progress'), m('escalated','in_progress'))"` prints the cap hint then `True True True`.
- **Status**: [ ] pending

### Task 5: Serve a rework-cap directive from `next`
- **Files**: `cortex_command/lifecycle/resolve.py`, `cortex_command/lifecycle/next_verb.py`
- **What**: `fragment_ref.directive` (and the resolver's legacy `next`) name the rework cap rather than a rejection when the served phase is the cap form.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `resolve.py`: add `_ROUTE_NEXT["escalated:rework-cap"]` next to the existing `"escalated"` entry (`:86-88`). Text: the rework cap was reached without a reviewer rejection; present the review findings and ask the user for direction; the recorded way to authorize another pass is the sanctioned override. Must not contain `REJECTED`.
  - `_next_for_route(route, phase_overridden)` (`:92-96`) keys on `route`. Thread the resolved `phase` in as a third, `None`-defaulted parameter — `_next_for_route(route, phase_overridden, phase=None)` — at its only call site (`:273`) and select the `escalated:rework-cap` key when `route == "escalated"` and `phase.startswith("escalated:rework-cap:")` — **only when `phase_override` is falsy**, since an explicit `--phase` override decouples `route` from the detected `phase`.
  - `next_verb.py`: `_terminal_directive(state)` (`:198-208`) is called from `build_served_envelope` (`:342`) with the bare table state. Give it the same optional discriminated-phase argument and thread `resolved["phase"]` through `build_served_envelope` (call site `:503-513`, which already threads `cycle`/`checked`/`total` from the same dict). Default the new argument to `None` so `describe`-side and test callers are unaffected.
  - Do **not** touch `transition_table.py` or `next_verb.KNOWN_STATES`: the served `state` stays the bare `escalated`, so the import-time assert at `:137-139` and the `route not in tt.STATE_NAMES` guard at `:496` are untouched. No protocol bump — no new returnable state, no payload shape change.
- **Verification**: `uv run python -c "from cortex_command.lifecycle.next_verb import _terminal_directive as d; a=d('escalated','escalated:rework-cap:2'); b=d('escalated','escalated'); c=d('escalated'); print(a); print('REJECTED' not in a, 'REJECTED' in b, b==c)"` prints the cap directive then `True True True`. **And** the `resolve.py` half (R8's anchor): `uv run python -c "from cortex_command.lifecycle.resolve import _next_for_route as n; a=n('escalated', False, 'escalated:rework-cap:2'); b=n('escalated', False, 'escalated'); print(a); print('REJECTED' not in a, 'REJECTED' in b)"` prints the cap directive then `True True` — at HEAD it raises `TypeError: _next_for_route() takes 2 positional arguments but 3 were given`. Pass = the `next_verb` command's three booleans **and** the `resolve` command's two, both from a clean exit.
- **Status**: [ ] pending

### Task 6: Mirror the discriminant in the statusline ladder
- **Files**: `claude/statusline.sh`
- **What**: The bash ladder reads the review cycle, emits the cap form, and renders it as a rework cap instead of as active rework in progress.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Verdict ladder (`:427-433`): the `CHANGES_REQUESTED)` arm currently sets `implement-rework` and reads no cycle. Count verdict matches the way Python does — `grep -o '"verdict"[[:space:]]*:[[:space:]]*"[A-Z_][A-Z_]*"' "$_lc_fdir/review.md" | wc -l`, guarded with `|| true` under `set -euo pipefail` and floored at 1 — then emit `escalated:rework-cap:$_lc_cycle` when the count is ≥ 2, `implement-rework` otherwise. Use `[A-Z_][A-Z_]*` (not the existing arm's `[A-Z_]*`, which can match an empty verdict value that Python's `[A-Z_]+` rejects). `REJECTED)` stays `escalated`.
  - Paused-suffix guard (`:475-483`): the `[ "$_lc_phase" != "escalated" ]` exact test misses the cap form, and the `*:*)` arm would mangle it into `escalated-paused:rework-cap:2`. Add an `escalated:*` exclusion.
  - `_lc_phase_icon` (`:352-363`): add `escalated:*` to the `escalated)` arm so the cap form gets ⚠️ rather than the 🔄 default.
  - Group-key normalization (`:583-586`): add `escalated:*) _lc_phase_key="escalated" ;;` so two capped features at different cycles group together rather than each forming its own group.
  - Both display case statements (`:592-600` multi, `:611-631` single): add an `escalated:rework-cap:*)` arm rendering `Escalated (rework cap)` so the raw wire value never reaches the `*)` verbatim arm.
  - The parity extractor anchors on `_lc_phase=""` and the `# Skip completed features` comment — keep both intact and keep every edit inside that span (the icon function and display cases sit outside it and are covered by the parser subtest instead).
- **Verification**: `uv run python -c "import sys,tempfile,pathlib; sys.path.insert(0,'tests'); from test_lifecycle_phase_parity import _invoke_statusline_ladder as L; d=pathlib.Path(tempfile.mkdtemp()); (d/'review.md').write_text('{\"verdict\": \"CHANGES_REQUESTED\"}\n{\"verdict\": \"CHANGES_REQUESTED\"}\n'); print(L(d))"` prints `escalated:rework-cap:2` (it prints `implement-rework` before the change). The import only reads `claude/statusline.sh` and runs bash, so it does not depend on the Python encoder change.
- **Status**: [ ] pending

### Task 7: Keep the backlog index's `lifecycle_phase` a closed set
- **Files**: `cortex_command/backlog/generate_index.py`
- **What**: Write the base machine state into `index.json`'s `lifecycle_phase` rather than the discriminated phase string.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `:199-205` reads `resolve_lifecycle_phase(lc_dir)["phase"]` and strips only `-paused`, with a comment (`:188-198`) pinning the value set to the eight base phase names for downstream readers (morning-review report, dashboard merges) and `docs/backlog.md:28` / `skills/backlog/references/schema.md:15` documenting that set. The discriminated form would leak `escalated:rework-cap:2` into it. Read `["route"]` instead — the resolver's `route` is already the bare machine state with no `-paused` suffix, so the `removesuffix` becomes dead and can go. Update the surrounding comment to say the index stores `route`. This is an exact-match consumer R3's sweep is responsible for; it is called out as its own task because the fix is a real behaviour change, not a normalization.
- **Verification**: `grep -c 'resolve_lifecycle_phase(lc_dir)\["route"\]' cortex_command/backlog/generate_index.py` = 1 **and** `grep -c 'removesuffix("-paused")' cortex_command/backlog/generate_index.py` = 0.
- **Status**: [ ] pending

### Task 8: Update the parity test tables, finish the consumer sweep, and green the suite
- **Files**: `tests/test_lifecycle_phase_parity.py`, `tests/test_phase_labels_none.py`, plus any file the sweep in **What** identifies (candidate set: `cortex_command/common.py`, `cortex_command/hooks/scan_lifecycle.py`, `cortex_command/lifecycle/advance.py`, `cortex_command/lifecycle/resolve.py`, `cortex_command/backlog/generate_index.py`, `claude/statusline.sh`). `cortex_command/lifecycle/transition_table.py` and `cortex_command/lifecycle/review_verdict.py` are **not** in this set and must not be edited — they are diff-checked-unmodified by this task's Verification, which is R2's runnable check.
- **What**: Teach the parity harness the new wire value and label, add a label regression row, sweep the remaining bare-`escalated` comparisons for base-normalization needs, and bring the whole suite green.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7]
- **Complexity**: complex
- **Context**:
  - `tests/test_lifecycle_phase_parity.py`: `_label_to_wire` (`:437-469`) raises on an unrecognised label — add a `re.fullmatch` arm for the new label mapping back to `escalated:rework-cap:<n>`, mirroring the `implement-rework` arm at `:454-457`. Add `escalated:rework-cap:2` to `_PARSER_WIRE_VALUES` (`:337-348`) so the statusline parser subtest proves the new arm renders non-empty, and add an `("escalated:rework-cap:2", 0, 0, 2, "escalated:rework-cap:2")` row to `GLUE_FIXTURES` (`:58-69`) pinning `_encode_phase`'s pass-through. The three parametrized subtests pick the new fixture dir up automatically via `iterdir()` (`:279-281`, `:548-550`) — no registration needed.
  - `tests/test_phase_labels_none.py:36-38`: add a row for the cap form alongside the existing `implement-rework:2` and `escalated` rows.
  - **Sweep (report-then-decide).** Run `rg -n '"escalated"' --type py cortex_command/ hooks/` and `rg -n "'escalated'" --type py cortex_command/ hooks/`, plus `rg -n 'escalated' claude/statusline.sh`. For each hit outside `overnight/` (whose `escalated`/`advisory_escalated` identifiers are the unrelated fire-marker vocabulary), decide whether it is base-normalized or deliberately exact. Already analysed and requiring **no** change, so treat a re-derivation that contradicts these as the signal to look harder: `common.py:526` (`_MACHINE_STATE_NAMES`, matches `phase_transition.to` values, which stay bare); `common.py:533` (`_EVENTS_TERMINAL_STATES`, tested against `machine_state`, which stays bare); `advance.py:280`/`:1070` (from-state gate — `escalated` is terminal with zero outgoing edges, so no verb ever names it as `effective_from`; a discriminated phase there only improves the refusal message); `review_verdict.py` and `transition_table.py` (R2 forbids touching either, and both operate on machine-state names).
  - Run `just test` and fix the fallout. **Expect breakage from Task 1's rung change**: any existing test that stages a `review.md` with two or more `CHANGES_REQUESTED` verdict blocks and asserts an artifact-derived `implement-rework` now gets the cap form. Highest-density candidates by verdict count: `cortex_command/lifecycle/tests/test_counters.py`, `tests/test_lifecycle_auto_advance.py`, `cortex_command/pipeline/tests/test_metrics.py`, `tests/test_implement_rework_exit.py`. Tests asserting on **events-derived** state are unaffected; only artifact-fallback assertions flip. Where one flips, the new expectation is the correct one (it is what `review_verdict._route_target` has always routed) — update the assertion rather than special-casing the detector.
  - No `skills/` or `plugins/` prose changes are in scope, so the reference-size ratchet and dual-source mirror sequence do not apply. `claude/` is not a mirror path.
- **Verification**: `just test` reports zero `[FAIL]` lines, **and** `uv run pytest tests/test_lifecycle_phase_parity.py tests/test_phase_labels_none.py -q` passes, **and** `uv run pytest tests/test_lifecycle_phase_parity.py -q -k "review-changes-requested-cycle2"` reports `2 passed` (the ladder and hook-end-to-end subtests parametrized over the new fixture dir), **and** R2's unchanged-machine-state check: `git diff --stat cortex_command/lifecycle/transition_table.py cortex_command/lifecycle/review_verdict.py` produces empty output (zero bytes on stdout — any `|` / insertion line means one of the two forbidden files was edited, which fails the task). This clause is the one Verification here that also holds at HEAD, by design: it asserts an absence.
- **Status**: [ ] pending

## Risks

- **The spec's R6 acceptance command names a symbol that does not exist.** `scan_lifecycle._next_step_hint` is not defined anywhere in the repo; the function at the cited lines is `_interrupted_hint`. Task 4 uses the real name, so R6's intent is met but its literal command is not runnable as written.
- **Task 1 changes an existing rung, not just adds one.** CHANGES_REQUESTED at cycle ≥ 2 stops resolving to `implement-rework` in the artifact fallback. This is the only way to make R1's acceptance ("a `CHANGES_REQUESTED` verdict at cycle 2 prints the rework-cap form") true, and it aligns the fallback with `review_verdict._route_target`, but the spec's *Changes to Existing Behavior* frames it only as "the encoder emits a discriminated form". Task 8 owns the test fallout and will surface how wide it is.
- **`generate_index.py` is a behaviour fix beyond the spec's letter.** The spec lists two known exact-match consumers and asks the implementer to sweep for others; this is one, and leaving it would put a ninth value into a `lifecycle_phase` set that two docs pin as closed. Fixed in Task 7 rather than deferred.
- **Rejected alternative: a shared `lifecycle_phase_base()` normalizer** in `common.py`, imported at each comparison site. It would have exactly one non-trivial consumer (`_is_terminal_mismatch`) and would force `phase_labels.py` — deliberately import-free and pure — to take a dependency. The literal-prefix idiom the codebase already uses for `implement-rework:` is the cheaper match, and the parity test is the cross-site pin either way.
- **The statusline's documented cycle-blindness narrows.** `tests/test_lifecycle_phase_parity.py:113-121` documents that the ladder reads `verdict` but never `cycle`; Task 6 makes it read cycle for this one arm. The exclusion in `test_statusline_ladder_matches_canonical` stays correct for `implement-rework` (still emitted bare) — only the cap form carries a cycle on the bash side.
