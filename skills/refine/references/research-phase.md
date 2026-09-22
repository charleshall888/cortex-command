# Research Phase

Inputs: Clarify's §5 outputs (intent, scope, tier, criticality).

**Sufficiency.** If `cortex/lifecycle/{lifecycle-slug}/research.md` exists (only that exact path counts; a backlog `discovery_source`/`research` field is background), apply clarify.md §6. Sufficient → announce the signals checked and skip to Spec. Insufficient → name the signal(s) and re-run. When specify.md §2a sends you back here, skip this check and re-run from scratch.

**Alignment considerations.** These are clarify-critic findings with `origin: "alignment"` that ended as Apply (or Ask → Apply); dismissed ones are dropped. Only when ≥1 remains: overwrite `cortex/lifecycle/{lifecycle-slug}/research-considerations.md` with a one-sentence bullet each **and** pass `research-considerations-file=` on dispatch. Always do both.

**Dispatch:**

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

The clarified intent sets the scope, not the ticket body. When a complex-tier or high/critical feature comes with a suggested implementation, explore ≥1 alternative — confirming the suggestion is a fine result.

Afterwards `research.md` must exist and be non-empty; if not, report it and stop.

**Exit check.** Each `## Open Questions` item needs an inline answer or a written reason to defer. A bare bullet has neither — settle each before Spec. A missing section passes.
