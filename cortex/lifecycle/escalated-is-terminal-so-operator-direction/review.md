# Review: escalated-is-terminal-so-operator-direction (cycle 1)

**Tier**: moderate → Stage 1 (spec compliance) only. Stage 2 (code quality) is complex-only and was **skipped**.
**Diff base**: `dfe213b9`. Feature commits: `a16d8be1`, `41b9590c`, `957a1a86`, `e1009a2a`, `7b08ccb2`, `0727cf75`, `2a4fb715`, `7e2db067`, `1e2c780c`, `e2c517b4`, `c4ce1a69`, `2abba4f4`. The concurrent session's commits (`fcda6ae6`, `86d18c90`, `a1318376`, `ad818a65`) and files (`cortex/backlog/464-467*`, `cortex/lifecycle/a-rework-re-review-re-reads/*`) were excluded and not reviewed.
**Test baseline (consumed, not re-run)**: `just test` → `Test suite: 8/8 passed`, zero `[FAIL]` lines.
**Requirements loaded**: `project.md`, `glossary.md` (auto), plus `observability.md` read manually — see Requirements Drift for why the auto-load missed an area doc.

---

## Stage 1 — Spec compliance

Every acceptance clause below was executed against the working tree. Where an "at base" column appears, the same check was re-run against the pre-feature code extracted with `git show dfe213b9:<path>` into a scratchpad and loaded via `importlib`, so a PASS is only recorded when the check demonstrably discriminates.

### R1 — The encoder distinguishes the two intents — **PASS**

Ran (the spec's literal command passes a `str`; `detect_lifecycle_phase` requires a `Path`, so a `Path` was substituted — cosmetic):

```
uv run python -c "from pathlib import Path; from cortex_command.common import detect_lifecycle_phase; ..."
  cap fixture   -> phase=escalated:rework-cap:2  route=escalated  cycle=2
  REJECTED x2   -> phase=escalated               route=escalated  cycle=2
  cycle-1 CR    -> phase=implement-rework        route=implement-rework  cycle=1
```

The two strings differ. **Could it have failed?** Yes — at `dfe213b9` the same cap fixture returns `phase=implement-rework, route=implement-rework, cycle=2`, so the criterion fails at base. Non-vacuous.

Design note: the discriminant rides `phase` only; `route` stays the bare machine state (`common.py` `_result(phase, route=None)`), which is what makes R3 hold structurally.

### R2 — The machine state is unchanged — **PASS (vacuous by construction, independently corroborated)**

```
git diff --stat dfe213b9 -- cortex_command/lifecycle/transition_table.py cortex_command/lifecycle/review_verdict.py
  -> (empty)
git diff --stat -- <same two files>            # working tree vs HEAD
  -> (empty)
uv run pytest tests/test_transition_table.py cortex_command/lifecycle/tests/test_transition_table.py -q
  -> 40 passed
```

**Could it have failed?** Not as written — an absence assertion holds at base by construction, exactly as flagged. Corroborated three other ways rather than relying on it: (a) both files are byte-identical to `dfe213b9`; (b) the end-to-end `next` envelope on a capped feature still reports `"state": "escalated"`, `evidence_trace[0].terminal = true`, `path_overview.outgoing = []` — one terminal state, zero outgoing edges; (c) `next_verb.KNOWN_STATES` (`:125`) and `_MACHINE_STATE_NAMES` (`common.py:543`) are untouched and the resolver tests that pin them equal to the table pass. No state added, no `terminal` flag flipped, no transition row touched.

### R3 — Every exact-match consumer of the bare `escalated` string still matches — **PASS**

Clause 1:
```
uv run python -c "from cortex_command.hooks.scan_lifecycle import _is_terminal_mismatch; ..."
  -> True True
```
**Could it have failed?** Yes — at base the same call prints `False True`. The `or events_phase.startswith("escalated:")` clause (`scan_lifecycle.py:211`) is load-bearing.

Clause 2 (`-paused` suppression), run on a cap fixture that also carries a `feature_paused` row after a `phase_transition to=escalated`:
```
uv run python -c "... resolve_lifecycle_phase(Path(d))['phase'].endswith('-paused')"
  -> False        (phase=escalated:rework-cap:2, route=escalated, paused=False)
uv run pytest tests/test_lifecycle_phase_resolver.py -q  -> 9 passed
```
**Could it have failed?** Two answers, and both matter:
- **Against the base commit: no.** At `dfe213b9` the same input yields `phase='escalated'`, which also does not end in `-paused`. `escalated` ∈ `_EVENTS_TERMINAL_STATES` (`frozenset({'complete','escalated','cancelled'})`), so `is_paused` is unconditionally `False` on this path. The suspicion in the review brief is **confirmed** for the base tree.
- **Against a plausible alternative implementation: yes.** The clause is not structurally unreachable — it is guarded by a specific choice. I built a variant of the current `common.py` computing `is_paused = raw_paused and served_phase not in _EVENTS_TERMINAL_STATES` (i.e. testing the discriminated string rather than `machine_state`) and the same input yields `phase='escalated:rework-cap:2-paused'`. So the criterion does discriminate between the implementation shipped and an easy mis-implementation of it; it just cannot discriminate against "no change at all."
- The bash mirror is falsifiable outright: with the `escalated:*` arm removed from the paused-eligibility case (`statusline.sh:500`), the ladder emits `escalated-paused:rework-cap:2`. With it, `escalated:rework-cap:2`. The spec's Edge Case ("the `-paused` suffix starts being appended to a terminal state") was a real hazard on the bash side and is genuinely closed there.

Sweep residue (the interactive/session-dependent half). `rg -n '"escalated"' --type py cortex_command/ hooks/` and the single-quoted variant return no hit outside the set the plan pre-analysed. Every remaining non-test hit is correctly left exact: `transition_table.py:104/364/366` and `review_verdict.py:89/163/169` (machine-state names; R2 forbids edits), `next_verb.py:125` (`KNOWN_STATES`, bare states only), `common.py:373` (now reads `route`), `common.py:543/550` (`_MACHINE_STATE_NAMES` / `_EVENTS_TERMINAL_STATES`, both tested against `machine_state`, which stays bare), `common.py:649` (the new guard itself). `advance.py` carries no `"escalated"` literal at all (the plan's cited `:280`/`:1070` from-state gate does not name it), so there is nothing to normalize there. One consumer beyond the spec's named two was found and fixed as its own requirement-adjacent task — `generate_index.py`, see R7 note below. I found no missed consumer.

### R4 — A cycle-≥2 `CHANGES_REQUESTED` fixture exists — **PASS**

```
tests/fixtures/lifecycle_phase_parity/review-changes-requested-cycle2/
  events.log  : 2 x {"event": "review_verdict"}, 0 x phase_transition/feature_complete/feature_wontfix/feature_paused
  review.md   : 1 x "verdict" (CHANGES_REQUESTED, cycle 2)
  ls          : exactly `events.log review.md`
uv run pytest tests/test_lifecycle_phase_parity.py -q  -> 55 passed
uv run pytest tests/test_lifecycle_phase_parity.py -q -k review-changes-requested-cycle2  -> 2 passed
```

**Could it have failed?** Yes, and it did once: the fixture as first committed (`a16d8be1`) carried no `events.log`, resolved to cycle 1, and could never reach the cap form. It was amended in `0727cf75` after the cycle-source correction. The `-k` selection returning exactly `2 passed` confirms the `iterdir()` parametrization picked the new directory up in both fixture-parametrized subtests (ladder + hook end-to-end) with no registration.

### R5 — `phase_labels.phase_label` renders both cases distinctly — **PASS**

```
uv run python -c "from cortex_command.phase_labels import phase_label as p; ..."
  'Escalated — rework cap reached (review cycle 2)'
  'Escalated (REJECTED — needs user direction)'
  differ=True  verbatim=False  'REJECTED' in cap=False  'REJECTED' in bare=True
```

Both non-empty, neither describes the other's cause, neither is the raw wire value. The module stays import-free and pure (no new imports in the diff; `phase_labels.py` gained 4 lines, all string logic). **Could it have failed?** Yes — the branch is new (`phase_labels.py:74-76`); at base the cap string falls through to the verbatim arm and returns `'escalated:rework-cap:2'`.

### R6 — `scan_lifecycle`'s SessionStart hint names the real cause — **PASS (spec command names a nonexistent symbol)**

The spec's acceptance command calls `scan_lifecycle._next_step_hint`, which does not exist in the repo — confirmed: `hasattr(scan_lifecycle, '_next_step_hint')` is `False`. The function at the cited lines is `_interrupted_hint`. The plan recorded this as a spec defect and used the real name; R6's *intent* is therefore testable and was tested, but its *literal* command is not runnable.

```
uv run python -c "from cortex_command.hooks.scan_lifecycle import _interrupted_hint as h; ..."
  CAP: Action needed: rework cap reached at review cycle 2. See cortex/lifecycle/demo/review.md
       for analysis. Recorded way to authorize another pass: cortex-lifecycle-event log
       --event <name> --feature demo (the sanctioned out-of-band hand-append).
  REJ: Action needed: review returned REJECTED. See cortex/lifecycle/demo/review.md for analysis.
  differ=True  'REJECTED' in cap=False  cycle named=True
```

Two different hints; the cap hint contains no `REJECTED`, names the cycle, points at `review.md`, and names the sanctioned override — matching the shape of the `implement-rework:` hint above it. The rejection branch is byte-unchanged. **Could it have failed?** Yes — the branch is new; at base the cap string reaches the `== "escalated"` arm and produces the REJECTED text verbatim.

### R7 — `claude/statusline.sh` mirrors the Python canon — **PASS**

```
uv run pytest tests/test_lifecycle_phase_parity.py -q  -> 55 passed
```

The acceptance clause as written ("the parity test passes") holds trivially on a tree with no fixture, so I verified the substance directly through the test's own ladder harness:

```
HEAD ladder, 2 review_verdict rows   -> escalated:rework-cap:2
HEAD ladder, 1 row                   -> implement-rework
HEAD ladder, no events.log at all    -> implement-rework      (absent-file guard holds under set -euo pipefail)
HEAD ladder, REJECTED x2             -> escalated             (rejection wins at any cycle)
HEAD ladder, R4 fixture              -> escalated:rework-cap:2
BASE ladder, R4 fixture              -> implement-rework
```

The last two lines are the proof the criterion is not vacuous: with the base `statusline.sh` and the new Python encoder, `test_statusline_ladder_matches_canonical[review-changes-requested-cycle2]` compares `implement-rework` against `escalated:rework-cap:2` and **fails**. The bash edit is load-bearing and the parity invariant is genuinely exercised, exactly as R7 claims. Downstream renders confirmed too: parser emits `Escalated (rework cap)` for the cap form and `Escalated` for bare, so no raw wire value reaches the `*)` arm; the icon arm (`escalated|escalated:*`) and the group-key normalization (`escalated:*) → escalated`) are both present. Measured statusline invocation: **116 ms** — comfortably inside observability.md's 500 ms budget despite the added `grep -c` per feature.

Cycle counted from `events.log` `review_verdict` rows on both sides, so bash and Python cannot desync — the correction recorded in the plan's Risks was applied here.

### R8 — `resolve.py`'s served directive names the real cause — **PASS, and the end-to-end wiring is genuinely proven**

This was the flagged weak spot: every task verification exercised private helpers (`_next_for_route`, `_terminal_directive`) with hand-supplied phase strings, never R8's actual acceptance. I ran R8 as written. Built two throwaway lifecycles in a scratchpad git repo (nothing created under `cortex/lifecycle/`):

```
cd <scratchpad>/r8repo
uv run python -m cortex_command.lifecycle.next_verb capped-demo
  state: escalated
  fragment_ref.directive: "The rework cap was reached without a reviewer rejection — present
    the review findings and ask the user for direction. The recorded way to authorize another
    pass is the sanctioned override: cortex-lifecycle-event log --event <name> --feature <slug>
    (the sanctioned out-of-band hand-append)."
  'REJECTED' in directive: False

uv run python -m cortex_command.lifecycle.next_verb rejected-demo
  state: escalated
  fragment_ref.directive: "review.md is REJECTED — present the reviewer analysis and ask the
    user for direction."
  'REJECTED' in directive: True
```

**The wiring really does thread the discriminated phase through** — not only the helpers. The full chain is live: `resolve_invocation` → `resolved["phase"]` → `build_served_envelope(phase=...)` (`next_verb.py:522`) → `_terminal_directive(state, phase)` → `resolve_mod._PHASE_NEXT`. Served `state` stays the bare `escalated` and `legacy_display_phase` stays `escalated`, so no wire contract widened. Verified against both the events-authoritative path (a `phase_transition to=escalated` row present) and the artifact-only legacy fallback (no machine rows) — both serve the cap directive.

**Could it have failed?** Yes. `_PHASE_NEXT` does not exist at `dfe213b9` and `_terminal_directive` took no phase argument, so `capped-demo` would have served the `_ROUTE_NEXT["escalated"]` REJECTED text. Also verified the `--phase` override guard: `_next_for_route('escalated', True, 'escalated:rework-cap:2')` falls back to the route-keyed REJECTED directive, as the plan specified.

### R9 — The dashboard's phase filter renders both — **PASS**

```
uv run pytest cortex_command/dashboard/tests/ -q  -> 311 passed, 154 subtests passed
```

Traced the actual dashboard data path rather than relying on R5: `dashboard/data.py:319` calls `resolve_lifecycle_phase(feature_dir)` and sets `current_phase = detector["phase"]` — the discriminated string — which the three templates render through the `phase_label` filter registered at `app.py:212-213`.

```
parse_feature_events('review-changes-requested-cycle2', <parity fixtures>)
  current_phase        -> escalated:rework-cap:2
  templates.env.filters['phase_label'](current_phase)
                       -> 'Escalated — rework cap reached (review cycle 2)'
  is verbatim?         -> False
```

Filter resolves to `cortex_command.phase_labels.phase_label`. No raw wire value reaches the operator. The one other `current_phase` consumer, the slow-phase classifier (`data.py:1829`), strips `-paused` and matches on `implement`/`implement-rework`/`review`; the cap form falls to its `continue` arm exactly as bare `escalated` already did — no behaviour change there.

---

## Plan-execution audit

**Per-task Verification steps: all eight re-executed and all hold.** Task 1 (three detector cases + three resolver booleans), Task 2 (four fixture greps: 2 / 0 / ≥1 / exactly two files), Task 3, Task 4, Task 5 (both halves — `next_verb` three booleans and `resolve` two), Task 6 (three ladder cases), Task 7 (`route` read = 1, `removesuffix("-paused")` = 0), Task 8 (suite green, targeted pytest green, `-k` selection = `2 passed`, R2 diff empty). No task's Verification is claimed-but-false.

**The mid-implement correction left no task inconsistent with the final code.** The cycle source was corrected in `7b08ccb2` (plan) before Tasks 1, 2-amended, and 6 landed (`2a4fb715`, `0727cf75`, `1e2c780c`), and all three read `review_verdict` rows from `events.log`. The one commit built on the wrong premise (`a16d8be1`, the events-log-free fixture) was superseded by `0727cf75`. Task 5 was split across `7e2db067` and `e2c517b4` ("Key the rework-cap directive by phase, not by route"), and the final shape matches the plan's amended Context. Two residues of the correction were **not** cleaned up — see issue 2 below.

**Behaviour change beyond the spec's letter, correctly flagged in the plan's Risks and worth restating here:** Task 1 modifies an existing rung. A cycle-≥2 `CHANGES_REQUESTED` feature on the legacy artifact-fallback path (no machine rows) previously resolved to the non-terminal `implement-rework` and now resolves to terminal `escalated` with zero outgoing edges — confirmed end-to-end on an artifact-only lifecycle. This is compelled by R1's acceptance and aligns the fallback with what `review_verdict._route_target` has always routed, so I read it as correct; but the spec's *Changes to Existing Behavior* describes it only as "the encoder emits a discriminated form," which understates it. Not a defect in the code.

**Residual risk: five of the change's new branches have zero automated coverage.** Confirmed by grep across the whole test corpus:

| Branch | Covered by a test? |
| --- | --- |
| detector cap rung (`common.py:418`) | yes — `test_lifecycle_auto_advance.py:152`, parity glue/ladder/e2e |
| resolver discriminant adoption (`common.py:649`) | yes — `test_generate_backlog_index.py:374` |
| `phase_label` cap branch | yes — `test_phase_labels_none.py:40`, `_label_to_wire` round-trip |
| `generate_index` `route` read | yes — new `TestLifecyclePhaseStoresRoute` class |
| statusline ladder + parser + paused guard | yes — parity ladder / `_PARSER_WIRE_VALUES` |
| **`_interrupted_hint` cap branch** | **no** |
| **`_is_terminal_mismatch`'s `startswith("escalated:")`** | **no** — no test passes an `escalated:` value to it |
| **`resolve._PHASE_NEXT`** | **no** |
| **`_next_for_route`'s third parameter** | **no** |
| **`_terminal_directive`'s `phase` argument** | **no** |

The two uncovered narration surfaces are the SessionStart hint and the served `next` directive — two of the four surfaces this ticket exists to fix, and among the highest-frequency operator surfaces in the harness. A revert of any of the five lands green. The implementer applied exactly the opposite standard one task earlier, writing a bespoke test class for `generate_index` on the stated reasoning that "without this class the `["route"]` read has zero coverage and a revert to `["phase"]` would leak silently." That reasoning transfers verbatim and was not applied.

---

## Requirements Drift

- **State**: `detected`
- **Findings**:
  - **No `cortex/requirements/lifecycle.md` exists, and `project.md`'s `## Conditional Loading` map has no lifecycle route.** Ticket 454 declares `areas: ['lifecycle']`; `cortex-load-requirements --feature escalated-is-terminal-so-operator-direction` printed `no area docs matched for tags: [lifecycle, review, escalation, state-machine]; loaded project.md only`. This is a silent gap, not a benign fallback: the lifecycle state machine, phase vocabulary, and served-verb class — the subsystem this whole feature edits — are governed only by scattered bullets in `project.md`'s Architectural Constraints. `observability.md` *does* govern part of the change (it names `claude/statusline.sh` as its Statusline subsystem) and was not loaded either, because no tag routes to it. Every other area in the repo has a doc and a Conditional Loading row.
  - **The `phase` / `route` split and the discriminated-phase form are load-bearing across six surfaces with no requirements-level statement.** `phase` may now carry a discriminant (`escalated:rework-cap:<n>`); `route` is always a bare machine state. That invariant is what keeps `next_verb.KNOWN_STATES`, `advance`'s from-state gate, `_EVENTS_TERMINAL_STATES` membership, and the `index.json` closed set working, and it is currently recorded only in code comments and this lifecycle's plan. `project.md` carries an exactly analogous clause for the *backlog status* vocabulary ("Backlog status vocabulary": where the canonical set lives and what an extension must update) but nothing for the lifecycle phase vocabulary. A future author adding a second discriminant has no requirement telling them `route` must stay bare.
  - **Assessed and NOT drift** (recorded so a later pass does not re-derive it): `observability.md`'s Statusline acceptance criteria all still hold. "Active lifecycle feature name and phase match `events.log`" is *improved* — the ladder now reads the review cycle from `events.log`, the same rows Python counts, where before it read no cycle at all and rendered a capped feature as active rework. `events.log` is already in the declared Inputs list, so the new read adds no undeclared input. Latency measured at 116 ms against the < 500 ms budget; the 3-line output contract is untouched (the new `Escalated (rework cap)` label is shorter than the existing `Complete (awaiting merge)` arm). Separately, the Statusline **Inputs** list omits `review.md` and `plan.md`, which the ladder has read since before this feature — a pre-existing inaccuracy, not introduced here, and left out of the update below deliberately.
  - **Also assessed and NOT drift**: the eight-value closed `lifecycle_phase` set documented in `docs/backlog.md:28` and `skills/backlog/references/schema.md:15` is preserved, because Task 7 writes the resolver's `route`. No doc update is owed there.
- **Update needed**: `cortex/requirements/project.md` (both findings). Creating `cortex/requirements/lifecycle.md` is the durable fix for the first finding but is a separate piece of work — the update below adds the routing row so the area is at least reachable and the gap is visible.

## Suggested Requirements Update

- **File**: `cortex/requirements/project.md`
  **Section**: `## Conditional Loading` (existing heading, line 94)
  **Content** (append as a new bullet in the list):
  ```
  - lifecycle state machine/phase vocabulary/served verbs (next, advance, enter)/escalation → cortex/requirements/lifecycle.md (NOT YET WRITTEN — `areas: ['lifecycle']` tickets currently load project.md only; statusline/dashboard narration of lifecycle phase is governed by cortex/requirements/observability.md)
  ```

- **File**: `cortex/requirements/project.md`
  **Section**: `## Architectural Constraints` (existing heading, line 33)
  **Content** (append as a new bullet in the list):
  ```
  - **Lifecycle phase vocabulary — `phase` may be discriminated, `route` may not**: the resolvers in `cortex_command/common.py` return both. `route` is always a bare transition-table state name (the eight in `transition_table.py` plus `cancelled`), and every membership or equality test that gates machine behaviour — `next_verb.KNOWN_STATES`, `advance`'s from-state gate, `_EVENTS_TERMINAL_STATES`, `index.json`'s `lifecycle_phase` — reads `route`. `phase` additionally carries operator-facing detail as a suffix (`implement:<n>/<m>`, `implement-rework:<n>`, `escalated:rework-cap:<n>`, `-paused`) and is what narration surfaces render through `phase_labels.phase_label`. Adding a discriminant means one new `phase` form and zero new `route` values; adding a `route` value means a transition-table row and the enumerating-surface cost priced in lifecycle 454's spec Non-Requirements. Bash parity is pinned by `tests/test_lifecycle_phase_parity.py`.
  ```

---

## Verdict rationale

All nine requirements pass, and eight of the nine were shown to discriminate against the pre-feature tree (R2 cannot, being an absence assertion; R3's `-paused` clause cannot against base but does against a plausible mis-implementation, demonstrated above). The two flagged weak spots resolved in opposite directions: **R8 is genuinely wired end-to-end**, not merely helper-proven — that suspicion is refuted; **the `_PHASE_NEXT` / `_terminal_directive` coverage gap is real** and extends to three further branches including the SessionStart hint.

Changes requested are additive only — test rows and comment corrections. No source change is needed, and no requirement is unmet.

**Issues**

1. **Add regression coverage for the five uncovered branches** (table above). Minimum: assert `_interrupted_hint('escalated:rework-cap:2', 'x')` differs from the bare-`escalated` hint and contains no `REJECTED` (`tests/test_hooks_scan_lifecycle.py`); assert `_is_terminal_mismatch('escalated:rework-cap:2', 'in_progress') is True` (`tests/test_lifecycle_phase_resolver.py`, next to the existing `complete:` case); assert the served `fragment_ref.directive` on a capped feature contains no `REJECTED` while a rejected feature's does (`cortex_command/lifecycle/tests/`, which already stages lifecycle dirs). The narration these branches produce is the entire deliverable of ticket 454, and today a revert of any of them lands the suite green.
2. **Correct the now-false cycle-blindness prose in `tests/test_lifecycle_phase_parity.py`.** Three places still assert an invariant Task 6 deliberately narrowed: `:120-124` ("the statusline ladder reads only `verdict`, never `cycle`"), `:266-267` ("Cycle is NOT emitted by the ladder (structural cycle-blindness)"), and `:300-303` in `test_statusline_ladder_matches_canonical`'s docstring. The ladder now emits `escalated:rework-cap:<n>` with the cycle inline, counted from `events.log`. This is more than cosmetic in a parity test: a future author trusting `:120-124` would read the new `grep -c '"review_verdict"'` as dead code and remove it, silently restoring the bug. The exclusion remains correct for `implement-rework`, which is still emitted bare — say that instead. Optionally also amend `spec.md:60`, whose Technical Constraint ("Any part of the discriminant derived from `events.log` rather than `review.md` would be invisible to it") the plan's Risks already records as wrong in its rationale.

```
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["Five new branches have zero automated coverage — _interrupted_hint's rework-cap hint, _is_terminal_mismatch's startswith(\"escalated:\") clause, resolve._PHASE_NEXT, _next_for_route's phase parameter, and _terminal_directive's phase argument. Two of them are the SessionStart hint and the served next directive, i.e. two of the four narration surfaces this ticket exists to fix; a revert of any of the five lands the suite green. Add the three assertions named in issue 1 of the review.", "tests/test_lifecycle_phase_parity.py still documents a statusline cycle-blindness invariant that Task 6 deliberately narrowed, at :120-124, :266-267, and :300-303. The ladder now emits escalated:rework-cap:<n> with the cycle inline from events.log. An author trusting the stale comment would read the new grep -c '\"review_verdict\"' as dead code and remove it, restoring the bug. Optionally also amend spec.md:60, which the plan's Risks already records as wrong in its rationale."], "requirements_drift": "detected"}
```
