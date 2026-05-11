# Criticality Override and Behavior Matrix

## Criticality Override

The user can change criticality at any time by requesting it explicitly. When overriding, append a `criticality_override` event:

```json
{"ts": "<ISO 8601>", "event": "criticality_override", "feature": "<name>", "from": "<old>", "to": "<new>"}
```

The user's criticality setting is always final. No automated process (including future orchestrator additions) may override the user's choice.

## Criticality Behavior Matrix

| Criticality | Review phase (023) | Orchestrator review (024) | Scaled behaviors (025) | Model selection |
|-------------|-------------------|--------------------------|----------------------|----------------|
| low | Tier-based (skip for simple) | Skipped for simple; active for complex | Single research, single plan | Haiku explore, Sonnet build/review |
| medium | Tier-based (skip for simple) | Active at phase boundaries | Single research, single plan | Haiku explore, Sonnet build/review |
| high | Forced regardless of tier | Active at all phase boundaries | Single research, single plan | Sonnet explore, Opus build/review |
| critical | Forced regardless of tier | Active at all phase boundaries | Parallel research, competing plans | Sonnet explore/research/plan, Opus build/review |

All three tickets (023, 024, 025) are implemented. The Review phase column reflects tier-based skip logic, the Orchestrator review column reflects boundary-checking behavior, and the Scaled behaviors column reflects criticality-conditional dispatch in the research and plan reference files. The Model selection column reflects which models are used at each criticality level.
