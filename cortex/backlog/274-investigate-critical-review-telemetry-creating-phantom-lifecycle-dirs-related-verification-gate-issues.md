---
schema_version: "1"
uuid: c8d1e170-7149-49eb-8f50-c78984b0601f
title: "Investigate critical-review telemetry creating phantom lifecycle dirs (+ related verification-gate issues)"
status: complete
priority: medium
type: spike
created: 2026-06-01
updated: 2026-06-01
lifecycle_phase: research
lifecycle_slug: investigate-critical-review-telemetry-creating-phantom
complexity: complex
criticality: high
spec: cortex/lifecycle/investigate-critical-review-telemetry-creating-phantom/spec.md
areas: ['skills']
---
> **Spike framing**: this is an investigation to be run in a **fresh session**.
> The goal is to map the full failure surface and decide the fix shape — not to
> land a patch from this ticket directly. Confirm/refute each finding below
> independently; treat the prior-session analysis as leads, not settled fact.
> Likely follow-on: a `bug`/`feature` ticket (or `/cortex-core:refine`) once the
> fix shape is chosen.

## Why

Critical-review telemetry writes create **phantom lifecycle directories** under
`cortex/lifecycle/{slug}/` for topics that were never feature lifecycles. Each
phantom contains only a `synthesizer_drift` (or `sentinel_absence`) event and no
real artifacts, then trips the SessionStart scanner as a stale "Research"
lifecycle on every session start until someone manually archives it.

Observed twice in ~11 days, both with the identical signature (single drift
event, `observed_sha_or_null: null` = sentinel absent, matches a
`cortex/research/{topic}/` topic):

- `cortex-init-scope-reduction` — `synthesizer_drift`, 2026-05-29 (archived via
  wontfix in commit `d21d395e`; the discovery itself shipped via backlog #273).
- `doc-audit-2026-05-18` — `synthesizer_drift`, 2026-05-18 (already archived
  earlier — an independent prior hit).

**The "stale plugin/CLI" hypothesis was tested and refuted.** The skill guidance
that says to skip synth-verification when no `--feature` is in scope landed
2026-05-11; both phantoms were created *after* that (one a week later, one 2.5
weeks later), and the currently-deployed plugin skill carries that guidance. The
`cortex` CLI is an editable install pointing at the repo working copy, so it ran
current code too. The correct instructions were deployed both times — so this is
a structural defect, not a propagation lag. **Re-verify this timeline in the
fresh session** before discarding the transient hypothesis entirely.

## Role

Map the complete failure surface of critical-review's events.log telemetry
writes, identify every related issue (not just the one symptom), and recommend a
**structural** fix (per the repo's "prefer structural separation over prose-only
enforcement for gates" principle). The prior session found a credible root cause
and a candidate fix; this spike's job is to confirm it, widen the lens for
sibling defects, and decide the fix shape with evidence.

## Root cause (candidate — confirm)

1. Discovery/refine run `/cortex-core:critical-review cortex/research/{topic}/research.md`
   (the `<path>`-arg form).
2. `skills/critical-review/references/verification-gates.md` says that form must
   **omit `--feature`** and **skip** the synth-stability check ("drift telemetry
   requires a lifecycle feature directory"). This is **prose-only** enforcement —
   nothing structural stops it.
3. When the orchestrator passes `--feature {topic}` anyway (the topic is right
   there in the research path, trivially derivable), `check-synth-stable` writes
   to a hardcoded `lifecycle_root / {feature} / events.log`.
4. `append_event` does `parent.mkdir(parents=True, exist_ok=True)`
   unconditionally → the phantom `cortex/lifecycle/{topic}/` dir is born.

## Investigation angles (the "related issues" to probe)

- **All three telemetry write sites share the unconditional-mkdir risk**, not
  just `synthesizer_drift`: `check-synth-stable` (`synthesizer_drift`),
  `check-artifact-stable` (`sentinel_absence`), and `record-exclusion`
  (`sentinel_absence`). Verify each can independently create a phantom.
- **Multi-root validate vs single-root write mismatch**: `prepare-dispatch`
  accepts both `cortex/lifecycle/` and `cortex/research/` artifacts (and ad-hoc
  via `cortex/_adhoc/`), but all three telemetry writers are single-root —
  hardcoded to `cortex/lifecycle/{feature}/`. A critical-review on a research
  artifact therefore has **nowhere correct to write telemetry**; it can only
  create a phantom lifecycle dir. Is the right fix (a) a structural write-guard
  that refuses to create a non-existent dir, (b) routing research-scoped
  telemetry to `cortex/research/{topic}/`, or (c) both? Decide with evidence.
- **How is `--feature` actually derived for research-scoped reviews?** Trace the
  real discovery/refine → critical-review invocation. Is the orchestrator
  deviating from the skip-prose, or is some skill/refine instruction telling it
  to pass `--feature`? (No transcript survives the two incidents; reproduce.)
- **Defensive detection**: should `detect_lifecycle_phase` / the SessionStart
  scanner treat an artifact-less dir (events.log with only telemetry events, no
  research/spec/plan) as *non-lifecycle* rather than defaulting to "research
  phase"? That would neutralize phantoms regardless of who writes them.
- **Sweep + cleanup**: enumerate all existing phantom dirs (prior session found
  2; re-sweep live + archive) and decide whether a one-shot cleanup + a guard is
  warranted. Note any `.lock` debris (a stray ignored `.lock` was seen in one
  phantom — identify what writes it and whether it leaks elsewhere).
- **Other prose-only gates**: while in here, scan critical-review and lifecycle
  for sibling gates that rely on the model following prose where structural
  enforcement is feasible.

## Integration

- `skills/discovery/references/research.md:130` and `/cortex-core:refine`
  invoke `/cortex-core:critical-review` on research-scoped artifacts.
- `cortex_command/hooks/scan_lifecycle.py` + `cortex_command/common.py`
  (`detect_lifecycle_phase`) decide whether a dir surfaces as an incomplete
  lifecycle at SessionStart.
- The lifecycle `wontfix` path (`skills/lifecycle/references/wontfix.md`) is the
  current manual remedy — `git mv` to `archive/` + `feature_wontfix` event.

## Edges

- **Must not break the legitimate auto-trigger flow.** When critical-review
  auto-triggers inside a lifecycle (Complex + medium/high/critical, before spec
  and plan approval), `cortex/lifecycle/{feature}/` already exists by then. A
  "only write if the dir already exists" guard therefore breaks nothing while
  killing phantoms — verify this invariant holds at every auto-trigger site.
- A prose-only tightening of verification-gates.md alone re-arms the same trap;
  prefer/confirm a structural guard at the write site.
- `--feature` is `required=True` on `check-synth-stable` / `check-artifact-stable`
  / `record-exclusion`, so the argparse layer does not (and cannot, as-is)
  prevent the phantom — the guard must live in the command body or the write.

## Touch points

- `cortex_command/critical_review/__init__.py` — `append_event` (~:469,
  unconditional `mkdir`); `_cmd_check_synth_stable` (~:659 path, :689 append);
  `check-artifact-stable` write (~:743/:746); `_cmd_record_exclusion`
  (~:762/:774); `_default_lifecycle_root` (~:524); multi-root `prepare-dispatch`
  vs single-root note (~:535).
- `skills/critical-review/references/verification-gates.md` — lines 18, 49, 79,
  84 (the prose-only skip-when-no-feature guidance).
- `cortex_command/hooks/scan_lifecycle.py` — phantom surfaces here as incomplete.
- `skills/discovery/references/research.md:130` — discovery's critical-review call.
- Evidence: `cortex/lifecycle/archive/cortex-init-scope-reduction/events.log`,
  `cortex/lifecycle/archive/doc-audit-2026-05-18/events.log`.