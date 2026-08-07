---
schema_version: "1"
uuid: bd73ae5b-578e-4ca8-b1f6-84aea79dcadb
title: Pin the _TERMINAL_EVENT_TO_STATE key set and value invariants
status: done
priority: low
type: chore
created: 2026-08-07
updated: 2026-08-07
complexity: simple
criticality: low
tags: ['lifecycle', 'phase-vocabulary', 'tests']
areas: ['lifecycle']
---
## Why

`_TERMINAL_EVENT_TO_STATE` (`cortex_command/common.py:524-528`) maps the three terminal events to machine states and has **zero direct references anywhere under `tests/`**. Its sibling `_MACHINE_STATE_NAMES` is pinned equal to `transition_table.STATE_NAMES` by the resolver tests, so a drift there fails loudly; this dict has no equivalent structural pin.

**Scoped by measurement, 2026-08-07.** All three current keys already have *behavioural* coverage, so the exposure is narrower than "unguarded":

| Key | Covered by |
|---|---|
| `feature_wontfix` | `tests/test_lifecycle_phase_parity.py:623` (#210 R12–R17), over `tests/fixtures/lifecycle_phase_parity/events-feature-wontfix/` |
| `feature_complete` | `tests/test_lifecycle_phase_resolver.py`, `test_complete_route.py`, + fixture `events-feature-complete/` |
| `lifecycle_cancelled` | `tests/test_lifecycle_phase_resolver.py`, `test_lifecycle_phase_tracks_status.py` |

What is *not* caught is structural rather than behavioural: a **new** key added to the dict, or a value repointed to a state outside the machine vocabulary, passes the whole suite silently because no test reads the dict itself.

Two invariants hold today and are worth freezing (both verified against HEAD):

- every value ∈ `_MACHINE_STATE_NAMES` — a terminal event may not pin a state the resolver cannot serve;
- every value ∈ `_EVENTS_TERMINAL_STATES` — a *terminal* event may only pin a terminal state.

## Role

Give `_TERMINAL_EVENT_TO_STATE` the drift tripwire its sibling already has: a golden pin on the key set plus the two value invariants above, sited beside the `_MACHINE_STATE_NAMES` pin.

## Integration

Mirrors the existing `_MACHINE_STATE_NAMES` ↔ `transition_table.STATE_NAMES` pin — same file, same shape, no new mechanism. The value invariants are genuine cross-constant checks, not prose pinning, so this sits inside the CLAUDE.md testing policy rather than against it.

## Edges

- The key-set pin is a golden literal; adding a legitimate fourth terminal event is *meant* to require editing it, which is the point.
- Keep it a pin, not a schema: no reflection over the module, no enumeration helper.

## Touch-points

`tests/test_lifecycle_phase_resolver.py` (beside the `_MACHINE_STATE_NAMES` pin). No production code changes.

## Prior scope — refuted, do not re-file

This ticket was filed as *"feature_wontfix reports an abandoned feature as Complete across every surface"*, proposing a `complete:wontfix` display discriminant. That premise was refuted during Clarify on 2026-08-07 and the ticket was narrowed to the tripwire above. Recorded so it is not re-derived:

- **`feature_wontfix → complete` is a ratified decision, not a defect.** Origin `cortex/backlog/210-*.md:81` — *"Treat any `feature_wontfix` event in `events.log` as `phase=complete` (terminal)"* — pinned by two named tests at `tests/test_lifecycle_phase_parity.py:623` (#210 R12–R17). Changing it breaks them by design.
- **The reported symptom is unreachable.** `cortex_command/lifecycle/wontfix_cli.py:5-11` archive-moves the lifecycle dir *before* appending the row, in a documented load-bearing order. Every phase-reading surface reads the live path only: `hooks/scan_lifecycle.py:955` excludes `archive` by name; `backlog/generate_index.py:198` guards on `lc_dir.is_dir()` at the live path; `dashboard/data.py:318` resolves phase from the non-archive dir (the `archive/` probe at `:1522` serves artifact rendering, not phase); `claude/statusline.sh:424` reads `$_lc_fdir/events.log` and contains no occurrence of "archive". Corpus: **0** live lifecycles carry `feature_wontfix`, 16 archived ones do. An abandoned feature is narrated on *no* surface, not mislabelled on every one.
- **`pipeline/metrics.py` was a false touch-point.** `:230-236` gates completion on `feature_complete` rows and `phase_transition to == "complete"`; the file contains zero occurrences of `wontfix`, so abandoned features are already excluded from throughput.
- **The false claims were inherited.** #454's spec follow-up note (`cortex/lifecycle/escalated-is-terminal-so-operator-direction/spec.md:71-72`) asserted the metrics/dashboard/statusline spread without verifying it, and the original #468 propagated it unchecked.
- **Open, but separate:** whether silent archival is the right operator experience — an abandoned feature currently vanishes from every surface with no trace. That is a visibility question, not a labelling one, and has no observed-failure evidence yet. It needs the archive-readability decision first if it is ever filed.
