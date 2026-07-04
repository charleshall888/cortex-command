# Discovery Bootstrap

## Create index.md (New Lifecycle Only)

When `phase = none` (no `cortex/lifecycle/{slug}/` directory), create the lifecycle `index.md` via the verb — consume Step 1's resolved `{backlog-file}` (the resolver's `filename` basename, e.g. `326-foo.md`); don't re-scan the backlog. The verb is skip-if-exists and backend-blind (always local, no `--backend`). Pass the basename, or `""` when Step 1 found no match:

```bash
cortex-lifecycle-create-index --feature {lifecycle-slug} --backlog-file {backlog-filename-or-empty-string}
```

## Epic Research Detection

When `phase = research` (no lifecycle directory yet), check whether discovery already produced epic-level artifacts — consume Step 1's parsed frontmatter, don't re-scan. Take `discovery_source` as the epic research path (falling back to the `research` field); record it only if the file exists on disk (warn and treat as unset otherwise). Record the `spec` field as `epic_spec_path` only alongside a recorded research path and only if it too exists. A no-match or missing field means no epic context.

**Do not copy epic content into lifecycle files** — epic research spans all tickets in the epic, so copying it bleeds cross-ticket context into this ticket. Record the paths as reference only; `/cortex-core:refine` produces ticket-specific research.md and spec.md that link the epic artifacts without reproducing them. If `epic_research_path` was found, announce it as background reference for the research and spec phases.

## Epic Context Injection (during /cortex-core:refine delegation)

When `epic_research_path` was recorded, before starting Clarify read `{epic_research_path}` (and `{epic_spec_path}` if present) as background, and instruct `/cortex-core:refine` to:

- Scope research and spec to THIS ticket's requirements only — don't reproduce content belonging to other tickets in the epic.
- Add a `## Epic Reference` section near the top of `research.md` linking the epic research path with a one-sentence note on how the epic relates to this ticket.
- Add a brief preamble note in `spec.md` referencing the epic research path for broader context.

## Refine Starting-Point Rules

`/cortex-core:refine`'s Step 2 (Check State) checks for `cortex/lifecycle/{lifecycle-slug}/research.md` and `spec.md` at those exact paths:

- Both exist → Step 2 proceeds normally.
- A backlog item's `discovery_source`/`research` field pointing to epic research at a different path is background context for Clarify, not a substitute — `/cortex-core:refine` still runs its full Research phase to produce `cortex/lifecycle/{slug}/research.md`.
