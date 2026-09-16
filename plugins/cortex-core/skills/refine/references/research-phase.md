# Research Phase

Inputs: Clarify's §5 outputs (intent, scope, tier, criticality).

**Sufficiency.** If `cortex/lifecycle/{lifecycle-slug}/research.md` exists — only that exact path counts; a backlog `discovery_source`/`research` field is background — apply clarify.md §6. Sufficient → announce the signals checked and skip to Spec. Insufficient → name the signal(s) and re-run. Re-entry from specify.md §2a bypasses this check and re-runs from scratch.

**Alignment considerations.** Clarify-critic findings with `origin: "alignment"` dispositioned Apply (or Ask → Apply) — dismissed ones don't propagate. Only when ≥1 survives: overwrite `cortex/lifecycle/{lifecycle-slug}/research-considerations.md` with one one-sentence bullet each **and** pass `research-considerations-file=` on dispatch. Always paired.

**Dispatch:**

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

The clarified intent, not the ticket body, anchors scope. Complex-tier or high/critical features carrying a suggested implementation must explore ≥1 alternative — validating the suggestion is a fine outcome.

Afterwards `research.md` must exist and be non-empty, else surface and halt.

**Exit gate.** In `## Open Questions`, an item is resolved with an inline answer or deferred with written rationale; a bare bullet is neither — settle each before Spec. An absent section passes.
