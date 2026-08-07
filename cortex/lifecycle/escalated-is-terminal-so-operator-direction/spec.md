# Specification: escalated-is-terminal-so-operator-direction

## Problem Statement

An operator whose feature stops in `escalated` is told the reviewer rejected the work, even when no rejection happened: `review_verdict._route_target` (`review_verdict.py:152-163`) routes both a reviewer's `REJECTED` and a cycle-≥2 `CHANGES_REQUESTED` — a routine rework-cap exhaustion meaning only "the loop ran twice, a human should look" — to the single state `escalated`, and every operator-facing surface then narrates the rejection story unconditionally (`phase_labels.py:74` renders "Escalated (REJECTED — needs user direction)"; `scan_lifecycle.py:158-162` emits "Action needed: review returned REJECTED"; `resolve.py:86-88` serves "review.md is REJECTED"; `claude/statusline.sh:431` maps to the same). The 2026-08-05 occurrence was exactly this — a cycle-2 `CHANGES_REQUESTED` in a consumer repo where every surface the operator consulted misreported why the lifecycle stopped, leaving them to reconstruct the real cause from `review.md` by hand before they could decide anything. The cost is a wrong diagnosis on the highest-frequency surfaces in the harness, and it is live for every escalated feature today.

## Phases

- **Phase 1: Encode the discriminant** — the phase encoder distinguishes a rework cap from a rejection, and every exact-match consumer of the bare `escalated` string keeps working.
- **Phase 2: Render it** — the four operator-facing surfaces tell the truth, pinned by the existing parity test.

## Requirements

1. **The encoder distinguishes the two intents.** The canonical phase encoder in `cortex_command/common.py` emits a discriminated form for `escalated`, following the established suffix pattern that already carries per-case detail without adding a machine state — `implement-rework:<n>` renders "review cycle `<n>`" while the machine state stays `implement-rework`. The discriminant derives from the same `review.md` verdict and cycle the encoder already reads. Acceptance: on a fixture whose `review.md` carries a `CHANGES_REQUESTED` verdict at cycle 2, `uv run python -c "from cortex_command.common import detect_lifecycle_phase; print(detect_lifecycle_phase('<fixture>'))"` prints the rework-cap form; on a `REJECTED` fixture it prints the rejection form; the two strings differ. **Phase**: Encode the discriminant

2. **The machine state is unchanged.** `escalated` remains a single `terminal=True` state in the transition table with zero outgoing edges, and `review_verdict._route_target` keeps returning `escalated` for both inputs. No state is added, no `terminal` flag flips, no transition row is added or altered. Acceptance: `git diff --stat cortex_command/lifecycle/transition_table.py cortex_command/lifecycle/review_verdict.py` reports no changes to either file, and `uv run pytest tests/test_transition_table.py cortex_command/lifecycle/tests/test_transition_table.py -q` passes. **Phase**: Encode the discriminant

3. **Every exact-match consumer of the bare `escalated` string still matches.** The discriminated form must not silently fall out of equality checks that today compare the phase to the literal `"escalated"`. The known ones are `scan_lifecycle._is_terminal_mismatch` (`:195-198`, `events_phase in ("complete", "escalated")`) and `common.py:623`'s `-paused` suppression via `_EVENTS_TERMINAL_STATES` (`:533`); the implementer must sweep for others rather than trusting this list. Acceptance: `uv run python -c "from cortex_command.hooks.scan_lifecycle import _is_terminal_mismatch; print(_is_terminal_mismatch('<cap-form>', 'in_progress'), _is_terminal_mismatch('escalated', 'in_progress'))"` prints `True True` — the discriminated form is still counted terminal, exactly as the bare string is; `uv run python -c "from pathlib import Path; from cortex_command.common import resolve_lifecycle_phase; print(resolve_lifecycle_phase(Path('<cap-fixture>'))['phase'].endswith('-paused'))"` prints `False` on a cap fixture that also carries a pause row; `uv run pytest tests/test_lifecycle_phase_resolver.py -q` passes. Interactive/session-dependent: the sweep's residue — deciding whether each remaining hit of `rg -n '"escalated"' --type py cortex_command/ hooks/` and `rg -n "'escalated'" --type py cortex_command/ hooks/` is base-normalized or deliberately exact — turns on each call site's intent, which no command can read. **Phase**: Encode the discriminant

4. **A cycle-≥2 `CHANGES_REQUESTED` fixture exists.** The parity fixture directory `tests/fixtures/lifecycle_phase_parity/` is enumerated by `iterdir()` (`tests/test_lifecycle_phase_parity.py:280`), so a new directory is picked up automatically by every parity subtest. Acceptance: a directory named for the rework-cap case exists under that path containing a `review.md` with a `CHANGES_REQUESTED` verdict at cycle 2, and `uv run pytest tests/test_lifecycle_phase_parity.py -q` collects it — confirmed by the run passing with one more fixture than before. **Phase**: Encode the discriminant

5. **`phase_labels.phase_label` renders both cases distinctly.** The rework-cap form renders as a rework cap and names the cycle; the rejection form keeps naming a rejection. The function stays pure — no I/O — per its module docstring. Acceptance: `uv run python -c "from cortex_command.phase_labels import phase_label; print(repr(phase_label('<cap-form>')), repr(phase_label('<rejected-form>')))"` prints two different non-empty labels, neither of which describes the other's cause; `uv run pytest tests/test_lifecycle_phase_parity.py -q` passes. **Phase**: Render it

6. **`scan_lifecycle`'s SessionStart hint names the real cause.** The `escalated` branch at `scan_lifecycle.py:158-162` splits: the rework-cap case says the rework cap was reached and names the cycle, mirroring the shape of the existing `implement-rework:` hint immediately above it (`:151-156`); the rejection case keeps its current text. Acceptance: `uv run python -c "from cortex_command.hooks.scan_lifecycle import _next_step_hint; print(_next_step_hint('<cap-form>', 'demo')); print(_next_step_hint('<rejected-form>', 'demo'))"` prints two different hints, and the rework-cap hint does not contain the string `REJECTED`. **Phase**: Render it

7. **`claude/statusline.sh` mirrors the Python canon.** Its phase ladder (`:427-431`) currently maps `CHANGES_REQUESTED` to `implement-rework` and `REJECTED` to `escalated` and reads no cycle at all, so a capped feature renders as active rework in progress. It gains the cycle read and the discriminated emit. Acceptance: `uv run pytest tests/test_lifecycle_phase_parity.py -q` passes — with the R4 fixture present the ladder subtest compares bash against `detect_lifecycle_phase` on a case that now has an artifact signature, so agreement is genuinely exercised rather than vacuously true. **Phase**: Render it

8. **`resolve.py`'s served directive names the real cause.** `_ROUTE_NEXT["escalated"]` (`:86-88`) currently serves "review.md is REJECTED — present the reviewer analysis and ask the user for direction." The rework-cap case gets its own directive telling the operator the cap was reached and that the recorded way to authorize another pass is the sanctioned override. Acceptance: `uv run python -m cortex_command.lifecycle.next_verb <slug>` on a capped feature serves a `fragment_ref.directive` that does not contain `REJECTED`, and on a rejected feature serves one that does. **Phase**: Render it

9. **The dashboard's phase filter renders both.** `phase_label` is registered as a Jinja filter in `cortex_command/dashboard/app.py` (per `phase_labels.py`'s module docstring), so R5 carries it — but the discriminated string must not fall through to the "any other phase → verbatim" branch and surface a raw wire value to the operator. Acceptance: `uv run pytest cortex_command/dashboard/tests/ -q` passes, and `phase_label` returns a rendered label rather than its input for both new forms (already asserted by R5's non-verbatim check). **Phase**: Render it

## Non-Requirements

- **No new machine state.** The reviewers established that adding one costs at minimum `next_verb.KNOWN_STATES` (an import-time assert that hard-kills `cortex-lifecycle-next`), a `legacy_display_phase` value where neither available choice is correct for an events-only state, a `PROTOCOL_VERSION` bump whose skew classifier has one opt-in caller, three new transition rows requiring three new B1 arms that neither `review_verdict` nor `implement_transition` can supply, three `dashboard/data.py` branch sites, and consumer-facing enumerations in a plugin with no protocol handshake. None of that is required to fix the observed harm.
- **No verb for operator direction out of `escalated`.** Deferred, not refused — see Open Decisions. `_SANCTIONED_OVERRIDE` (`advance.py:105-108`) remains the documented path and is not re-pointed.
- **No pause-hold or `relayed-consent` machinery.** `_pause_refusal` exempts by verb string (`advance.py:330-331`) and no `feature_resumed` event exists in the wheel, so a hold at a state whose only exit verb is also its only resume is either transparent or permanent. Not needed here: nothing auto-crosses `escalated`, which the Stop hook already excludes (`hooks/cortex-lifecycle-continue.sh:68` gates on `review | complete`).
- **No change to `review_verdict`'s routing.** Both verdicts keep landing in `escalated`; only the narration changes.
- **Not typing the `sanctioned_override` hatch** into `_TERMINAL_EVENT_TO_STATE`, and **not reusing `wontfix`** for cancel — the latter archive-moves the lifecycle directory (`wontfix_cli.py:6-11`), erasing the escalation from the SessionStart scan.

## Edge Cases

- **A feature escalated before this ships.** The discriminant is derived at read time from `review.md`, not stored, so historical features are narrated correctly with no migration and no backfill. This is the direct benefit of encoding rather than adding a state.
- **`review.md` is missing, unparseable, or carries no cycle.** Expected: fall back to the current undiscriminated `escalated` behavior and today's label rather than guessing an intent. A wrong confident narration is the defect being fixed; an unspecific one is not.
- **A `REJECTED` verdict arrives at cycle ≥ 2.** Both conditions hold at once. Expected: the rejection form wins — a reviewer's explicit rejection is the stronger signal, and the cap is incidental to it.
- **A consumer repo on an older wheel.** It renders the old undiscriminated label; nothing breaks, because no wire contract changed and no state name is new. This is the compatibility property the state-addition design could not offer.
- **An exact-match consumer is missed in R3's sweep.** Expected: a feature at the cap silently drops out of a terminal check — e.g. `_is_terminal_mismatch` stops firing, or the `-paused` suffix starts being appended to a terminal state. R3's sweep is the guard; this is why it is a requirement rather than an implementation note.
- **The dashboard receives the discriminated string.** Expected: rendered via the Jinja `phase_label` filter, never surfaced as a raw wire value.

## Changes to Existing Behavior

- **MODIFIED** — the phase encoder emits a discriminated `escalated` form when `review.md` supports it.
- **MODIFIED** — `phase_labels.phase_label`, `scan_lifecycle`'s next-step hint, `resolve.py`'s `_ROUTE_NEXT` directive, and `claude/statusline.sh`'s ladder each narrate the two cases separately; the statusline additionally stops rendering a capped feature as active rework.
- **ADDED** — one parity fixture.
- **REMOVED** — nothing.

## Technical Constraints

- **`phase_label` must stay pure** — no I/O, no side effects (`phase_labels.py` module docstring). The discriminant therefore has to reach it through the encoded string, which is what makes the suffix pattern the right carrier.
- **Bash/Python parity is a pinned invariant.** `claude/statusline.sh` mirrors the canonical Python ladder and `tests/test_lifecycle_phase_parity.py` enforces it; the scan hook is a 9-line probe-then-exec wrapper with no ladder of its own, so it needs no bash edit.
- **The parity ladder subtest compares against `detect_lifecycle_phase`** — the artifact-only detector. This design lives entirely in artifact-derived territory, so that comparison genuinely exercises the change. Any part of the discriminant derived from `events.log` rather than `review.md` would be invisible to it.
- **Wheel-binstub trap** (`project.md:46`): `cortex-*` binstubs run the installed wheel. Verify via `uv run python -m` or `CORTEX_COMMAND_FORCE_SOURCE=1`.
- **`claude/` is not a dual-source mirror path**, but editing it is still lifecycle-gated per `CLAUDE.md`. No `skills/` prose changes are required by this design, so the ratchet/mirror sequence does not apply.

## Open Decisions

None blocking implementation.

**Deferred, with the evidence that would reopen it.** The ticket's Role — "give operator direction a verb" — is not delivered here. It is deferred rather than refused: the corpus carries zero `phase_transition` rows naming `escalated` and zero cycle-≥2 non-`APPROVED` `review_verdict` rows, so the sole evidence is one consumer-repo occurrence whose own trail was overwritten by the hand-append. `project.md:23` puts the burden of proof on adding machinery, and the reviewers priced the smallest correct version of that machinery at a new state across seven-plus enumerating surfaces, a protocol bump, three new B1 arms, and a consent event. **Reopen when a second occurrence is recorded, or when a resolution other than "authorize another rework pass" is actually needed** — at which point this fix has already removed the confounder that made the first occurrence hard to read.

**Follow-ups to file separately:**
- `_TERMINAL_EVENT_TO_STATE` (`common.py:507`) carries no drift tripwire, unlike `_MACHINE_STATE_NAMES` which is pinned equal to the table by the resolver tests — a phase change routed through it is invisible to `tests/test_transition_table.py`. Already affects `feature_wontfix`.
- `feature_wontfix` maps to `complete`, so an abandoned feature reports as complete across `metrics.py:230-238`, `dashboard/data.py:336-343`, and `claude/statusline.sh:422-431`.
- `scan_lifecycle._is_terminal_mismatch` (`:186-201`) fires a permanent terminal-mismatch warning for every `escalated` feature at backlog status `in_progress`.
- `project.md:59` cites "→ ADR-0029" for "Lifecycle identity is the canonical slug", but `cortex/adr/0029-*.md` is about sync-allowlist conflict resolution.

## Proposed ADR

None considered. The decision this work embodies — narrate a discriminant rather than add a machine state — is neither hard to reverse (it adds no state name, no transition id, and no wire contract, all of which the closed table makes permanent), nor a real trade-off once the alternative was priced, so it fails the three-criteria gate at `cortex/adr/README.md:23-25`. The deferred half — giving operator direction a verb out of `escalated` — is ADR-shaped and should carry one if it is ever built.
