# Discovery Bootstrap

## Create index.md (New Lifecycle Only)

When `phase = none` (no `cortex/lifecycle/{slug}/` directory), create the lifecycle `index.md` via the verb — consume Step 1's resolved `{backlog-file}`; don't re-scan the backlog. The verb is skip-if-exists and backend-blind (always local, no `--backend`):

```bash
cortex-lifecycle-create-index --feature {lifecycle-slug} --backlog-file {backlog-filename-or-empty-string}
```

Pass `""` when Step 1 found no match.

## Epic Research Detection

When `phase = research` (no lifecycle directory yet), check whether discovery already produced epic-level artifacts — consume Step 1's parsed frontmatter, don't re-scan. Take `discovery_source` as the epic research path (falling back to `research`), recording it only if the file exists (warn and treat as unset otherwise); record `spec` as `epic_spec_path` only alongside a recorded, existing research path. No match or missing field means no epic context.

**Do not copy epic content into lifecycle files** — epic research spans all tickets, so copying bleeds cross-ticket context into this ticket. Record the paths as reference only; `/cortex-core:refine` produces ticket-specific research.md and spec.md that link the epic artifacts without reproducing them. If found, announce `epic_research_path` as background reference for the research and spec phases.

## Epic Context Injection (during /cortex-core:refine delegation)

When `epic_research_path` was recorded, read it (and `{epic_spec_path}` if present) as background before Clarify, and instruct `/cortex-core:refine` to add a `## Epic Reference` section to `research.md` and a preamble note to `spec.md` linking the epic path — scoped to this ticket, without reproducing epic content.

## Refine Starting-Point Rules

`/cortex-core:refine`'s Step 2 (Check State) checks for `cortex/lifecycle/{lifecycle-slug}/research.md` and `spec.md` at those exact paths. Both exist → proceeds normally. A `discovery_source`/`research` field pointing to epic research elsewhere is background only — refine still runs its full Research phase to produce `cortex/lifecycle/{slug}/research.md`.
