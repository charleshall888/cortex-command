# Discovery Bootstrap

When `phase = research` (no lifecycle directory exists yet), check whether discovery already produced epic-level artifacts for this feature. **Do not re-scan the backlog directory in this sub-procedure** — consume Step 1's resolved `{backlog-file}` and parsed frontmatter.

```
if Step 1 resolved a {backlog-file} (exit 0):
    use the parsed frontmatter from Step 1
    if discovery_source field exists:
        epic_research_path = discovery_source field value
    elif research field exists:
        epic_research_path = research field value
    else:
        (no epic context — epic_research_path is unset)
    if epic_research_path is set:
        if epic_research_path file exists on disk:
            record epic_research_path
            if spec field also exists and spec file path exists on disk:
                record epic_spec_path = spec field value
        else:
            log warning: "epic research file {epic_research_path} not found on disk — no epic context available"
            epic_research_path = unset
else:
    (Step 1 resolver returned exit 3 — no backlog match; no epic context)
```

**Do not copy epic content into lifecycle files.** Epic research covers all tickets in the epic — copying it wholesale bleeds cross-ticket context into this ticket's research and spec. Record the paths as reference context only; `/cortex-core:refine` will produce ticket-specific research.md and spec.md that reference the epic artifacts without reproducing them.

If `epic_research_path` was found, announce: "Found epic research at `{epic_research_path}` — will use as background reference during research. Running ticket-specific research and spec phases."

## Epic Context Injection (during /cortex-core:refine delegation)

When `epic_research_path` was recorded above, before starting Clarify, read the epic research file at `{epic_research_path}` (and `{epic_spec_path}` if present) as background context. This explains the broader epic scope and which concerns belong to adjacent tickets. Instruct `/cortex-core:refine` to:

- Scope research and spec to THIS ticket's specific requirements only — do not reproduce content that belongs to other tickets in the epic
- Include a `## Epic Reference` section near the top of `research.md` with a link to the epic research path and a one-sentence note on how the epic relates to this ticket
- In `spec.md`, add a brief preamble note referencing the epic research path for broader context

## Refine Starting-Point Rules

`/cortex-core:refine`'s Step 2 (Check State) checks for `lifecycle/{lifecycle-slug}/research.md` and `lifecycle/{lifecycle-slug}/spec.md` at those exact paths. Rules:

- If both files exist at those exact paths: Step 2 proceeds normally.
- If a backlog item's `discovery_source` or `research` frontmatter field points to epic research at a different path: that epic file is background context for the Clarify phase, not a substitute for the lifecycle research artifact. `/cortex-core:refine` must still run its full Research phase to produce `lifecycle/{slug}/research.md`.
