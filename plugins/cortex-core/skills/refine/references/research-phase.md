# Research Phase

Refine's research phase: sufficiency check, alignment-considerations propagation, dispatch, and exit gate. Clarify's §5 outputs (intent, scope, tier, criticality) are inputs here.

## Sufficiency Check

If `cortex/lifecycle/{lifecycle-slug}/research.md` exists, apply the Research Sufficiency Criteria (`clarify.md` §6) against Clarify's intent and scope. **Path guard**: only a file at that exact path counts (per the Refine Starting-Point Rules in `discovery-bootstrap.md`). Missing → run Research Execution.

- **Sufficient** → announce, state which signals were checked, skip to Spec.
- **Insufficient** → state the triggering signal(s), run new research.

**Bypass**: if Research is re-entered from specify.md's §2a confidence-check loop-back, skip the Sufficiency Check and re-run from scratch, overwriting `research.md`.

## Alignment-Considerations Propagation

After clarify-critic returns and dispositions are applied (Clarify phase), collect every `origin: "alignment"` finding dispositioned **Apply** (or Ask resolved to Apply via the §4 Q&A) — Dismiss'd findings aren't propagated. **Only when** ≥1 such finding exists: write the survivors to `cortex/lifecycle/{lifecycle-slug}/research-considerations.md` (overwrite, never append) **and** carry `research-considerations-file=cortex/lifecycle/{lifecycle-slug}/research-considerations.md` on the research dispatch, always paired. No Applied alignment findings → neither write nor argument.

Format: newline-delimited bullets, one one-sentence paraphrase per finding — a file, so arbitrary characters need no escaping.

## Research Execution

Delegate to `/cortex-core:research` (append `research-considerations-file=cortex/lifecycle/{lifecycle-slug}/research-considerations.md` only when the propagation write above fired):

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

The clarified intent, not the ticket body, is the research scope anchor. **Alternative exploration**: for complex-tier or high/critical features with a suggested implementation, research must explore ≥1 alternative alongside it (encouraged, not required, otherwise) — exploring isn't rejecting; validating the suggestion is a fine outcome.

After research returns, verify `research.md` exists and is non-empty (else surface the error and halt), then register the `"research"` artifact in `index.md` per backlog-writeback.md's canonical recipe.

## Research Exit Gate

Scan `research.md`'s `## Open Questions`: an item is **resolved** if it has an inline answer, **deferred** if explicitly marked deferred with written rationale; a bare unannotated bullet is neither. Any unresolved, non-deferred items → present them and resolve or explicitly defer each before Spec. An absent `## Open Questions` section → the gate passes.
