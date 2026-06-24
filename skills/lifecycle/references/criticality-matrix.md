# Criticality Override and Behavior Matrix

## Criticality Override

The user can change criticality at any time by requesting it explicitly. When overriding, append a `criticality_override` event:

```json
{"ts": "<ISO 8601>", "event": "criticality_override", "feature": "<name>", "from": "<old>", "to": "<new>"}
```

An automated **Clarify reconciliation** (emitted by `cortex-refine reconcile-clarify --lifecycle-slug {slug}` at Spec-phase entry) additionally carries an optional `gate: "clarify_reconcile"` field, so consumers that inspect `gate` can distinguish its provenance from a user-driven override (which omits `gate`) or an escalator-emitted override (which carries its own gate vocabulary). Consumers that read only `from`/`to` (e.g. `common.py`, `state_cli`) are unaffected.

The user's criticality setting is always final. No automated process (including future orchestrator additions) may override the user's *explicit* choice. The Clarify reconciliation above is **not** such an override: it transcribes the Clarify-determined criticality — which the user can correct *during* Clarify — into lifecycle state, is monotonic-up-only (never lowers a value), and is `gate`-marked `clarify_reconcile`. An explicit user criticality request still wins via the user-override path above (its later, ungated `criticality_override` row supersedes the reconciliation by recency).

## Criticality Behavior Matrix

| Criticality | Review phase (023) | Orchestrator review (024) | Scaled behaviors (025) | Model selection |
|-------------|-------------------|--------------------------|----------------------|----------------|
| low | Tier-based (skip for simple) | Skipped for simple; active for complex | Parallel research (sized by fan-out matrix), single plan | Haiku explore, Sonnet build/review |
| medium | Tier-based (skip for simple) | Active at phase boundaries | Parallel research (sized by fan-out matrix), single plan | Haiku explore, Sonnet build/review |
| high | Forced regardless of tier | Active at all phase boundaries | Parallel research (sized by fan-out matrix), single plan | Sonnet explore, Opus build/review |
| critical | Forced regardless of tier | Active at all phase boundaries | Parallel research (sized by fan-out matrix), competing plans | Sonnet explore/research/plan, Opus build/review |

All three tickets (023, 024, 025) are implemented. The Review phase column reflects tier-based skip logic, the Orchestrator review column reflects boundary-checking behavior, and the Scaled behaviors column reflects criticality-conditional dispatch in the research and plan reference files. The Model selection column reflects which models are used at each criticality level.

Research is **always parallel** at every criticality; the agent count is sized by the tier × criticality fan-out matrix — see `references/fanout.md` for the count-source-of-truth and dispatch protocol. Competing **plans** remain critical-only (single plan at low/medium/high).

## Reading lifecycle state

Run `cortex-lifecycle-state --feature {feature}` (whole-state JSON) or `cortex-lifecycle-state --feature {feature} --field <x>` (single-field JSON) to read tier or criticality. The command applies the canonical reduction rules:

- **criticality**: the most recent value from `lifecycle_start` or `criticality_override` events; defaults to `medium` when the key is absent or events.log is missing.
- **tier**: `lifecycle_start.tier` superseded by the most recent `complexity_override.to`; defaults to `simple` when the key is absent.
- **`"corrupted": true`**: if the output contains this field, events.log is corrupted and tier/criticality are unknowable — treat the feature as requiring review (run the critical-review / orchestrator-review gate) rather than applying the skip rule and defaulting.

## Seed → reconcile → gate ordering

`/cortex-core:refine` (and `/cortex-core:lifecycle`, which wraps it) must preserve a fixed order: **seed `lifecycle_start` → `reconcile-clarify` → §3b tier read**. This protects the critical-review gate's silent-skip behavior on non-`cortex-backlog` backends.

On a non-local backend (or Context B), the `lifecycle_start` seed is written without `--backlog-slug`, so it carries the canonical `simple`/`medium` defaults rather than any backlog-sourced values. The critical-review gate skips silently at `tier = simple`. So on those backends the gate stays alive *only* because `reconcile-clarify` — running at Spec-phase entry, before `specify.md` §3b — ratchets the lifecycle state up using **Clarify's computed** tier/criticality, passed as explicit `--complexity`/`--criticality` flags (never literals, never the seed defaults). If the §3b read ran before the reconcile, it would observe the seed `simple` and skip review.

Keep the three steps in order so the §3b read observes the ratcheted values. The local `cortex-backlog` arm is immune regardless: its `reconcile-clarify --backlog-slug` re-sources tier/criticality from backlog frontmatter, so the seed defaults never survive to the gate.
