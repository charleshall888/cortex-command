---
schema_version: "1"
uuid: c0feada9-b95c-4ca4-9b30-98ae7b4e41be
title: Override-row writers disagree on an empty reason, and _emit_subcommand validates no clause tag
status: in_progress
priority: medium
type: bug
created: 2026-08-07
updated: 2026-08-08
tags: ['lifecycle', 'events', 'criticality']
areas: ['lifecycle']
complexity: complex
criticality: high
lifecycle_phase: research
spec: cortex/lifecycle/override-row-writers-disagree-on-an/spec.md
---
## Why

`#471` changed `refine.py`'s two override-reason emit guards from `is not None` to plain truthiness, so `reconcile-clarify --tier-reason ""` / `--criticality-reason ""` now omit the `reason` key. `lifecycle_event.py`'s `_emit_subcommand` still drops optional fields on `is not None` alone, so `cortex-lifecycle-event criticality-override --reason ""` still writes `"reason": ""`.

The two writers of an override row therefore disagree on the empty case. This is not hypothetical drift — it is recorded as a live divergence in `cortex/requirements/project.md:64`, which previously asserted the two writers agree, and in the code comment at `cortex_command/refine.py:413-421`.

An empty string is the worst of the three states: ADR-0036's clause tally uses `if r.get('reason')`, so `""` counts as reason-less, while a human reading the row sees a `reason` key and assumes one was recorded. The row looks filled and tallies empty.

`_emit_subcommand` is also the unvalidated second writer of tier reasons — its `--reason` is declared plain `_STR` with no clause-tag validation, holding 24 free-prose rows across cortex-command and wild-light. #452's plan cited exactly this tally-pollution risk as its reason for sharing one clause set across `refine.py`'s two flags, and then left the other writer untouched.

## Role

Close the empty-reason divergence, and decide whether `_emit_subcommand`'s `--reason` should validate against the same closed clause set that `refine.py`'s two flags already do.

## Integration

`_emit_subcommand` (`cortex_command/lifecycle_event.py`) is a generic dispatcher shared by every subcommand in `_EVENT_SUBCOMMANDS`, so neither change is local to the override verbs. The optional-field drop is one `if value is None and not required: continue` line serving all of them; tightening it to truthiness changes behavior for every optional field on every event type, not just `reason`.

Clause validation cannot ride the existing 5th tuple slot (`_choices`), which only feeds argparse `choices=` and cannot express a leading-prefix check.

## Edges

- **Do not tighten the shared drop indiscriminately.** Some optional fields may legitimately carry `""`. Enumerate them before changing the generic path; a per-field opt-in is likely safer than a blanket truthiness switch.
- **The 24 existing free-prose rows stay valid.** Validation runs at write time only, so past rows are unaffected either way — but a tally that widens later will still see them as whole-sentence buckets, not clause tags.
- **Untagged reasons must keep working.** A reason with no colon is accepted verbatim by `_reason_clause_ok`; any validation added here must preserve that.
- **`project.md:64` says this "is tracked as follow-up"** — this ticket is what makes that sentence true. If this is closed as wontfix, that clause must be reworded in the same change.

## Touch points

- `cortex_command/lifecycle_event.py` — `_emit_subcommand`, the `_EVENT_SUBCOMMANDS` table, the `criticality-override` / `complexity-override` entries
- `cortex_command/refine.py` — `_reason_clause_ok`, `_ALLOWED_REASON_CLAUSES` (the validator to reuse rather than duplicate)
- `cortex/requirements/project.md:64` — the Override-reason clause vocabulary constraint stating the divergence
- `cortex/adr/0036-ceremony-relief-is-not-taken-on-the-criticality-axis.md` — the clause-distribution recipe this protects
- `cortex/lifecycle/tier-overrides-record-no-reason-and/review.md` — non-blocking observation 1, which asked for this ticket
