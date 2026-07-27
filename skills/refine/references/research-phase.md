# Research Phase

Clarify's §5 outputs (intent, scope, tier, criticality) are the inputs here.

## Sufficiency check

If `cortex/lifecycle/{lifecycle-slug}/research.md` exists, apply clarify.md §6's criteria against Clarify's intent and scope. **Only a file at that exact path counts** — a backlog item's `discovery_source`/`research` field is background, not a substitute. Sufficient → announce which signals were checked and skip to Spec. Insufficient → name the triggering signal(s) and run new research.

**Bypass**: re-entry from specify.md §2a's confidence-check loop-back skips this check and re-runs from scratch, overwriting `research.md`.

## Alignment-considerations propagation

Collect every clarify-critic finding with `origin: "alignment"` dispositioned **Apply** (or Ask resolved to Apply). Dismissed findings don't propagate. **Only when ≥1 survives**: write them to `cortex/lifecycle/{lifecycle-slug}/research-considerations.md` (overwrite, never append — newline-delimited bullets, one one-sentence paraphrase each) **and** pass `research-considerations-file=` on the dispatch. Always paired: no Applied alignment findings → neither the write nor the argument.

## Execution

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

The **clarified intent, not the ticket body**, is the research scope anchor. For complex-tier or high/critical features carrying a suggested implementation, research must explore ≥1 alternative alongside it — exploring isn't rejecting; validating the suggestion is a fine outcome.

Afterwards verify `research.md` exists and is non-empty (else surface and halt), then register it: `cortex-lifecycle-register-artifact --feature {lifecycle-slug} --artifact research`.

## Exit gate

Scan `## Open Questions`: an item is **resolved** with an inline answer, **deferred** when explicitly marked so with written rationale. A bare unannotated bullet is neither — present those and resolve or explicitly defer each before Spec. An absent section passes.
