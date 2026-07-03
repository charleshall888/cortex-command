# Discovery Bootstrap

## Create index.md (New Lifecycle Only)

When `phase = none` (no prior `cortex/lifecycle/{slug}/` directory exists), create the lifecycle `index.md` by invoking the creation verb. **Do not re-scan the backlog directory in this sub-procedure** — consume Step 1's resolved `{backlog-file}` (the resolver's `filename` basename, e.g. `326-foo.md`) directly; the verb handles normalization.

The verb is skip-if-exists (it no-ops when `index.md` already exists). Pass the basename, or the empty string when Step 1 found no backlog match:

```bash
cortex-lifecycle-create-index --feature {lifecycle-slug} --backlog-file {backlog-filename-or-empty-string}
```

index.md creation is backend-blind (always local) — no `--backend` flag.

## Epic Research Detection

When `phase = research` (no lifecycle directory exists yet), check whether discovery already produced epic-level artifacts for this feature. **Do not re-scan the backlog directory in this sub-procedure** — consume Step 1's resolved `{backlog-file}` and parsed frontmatter.

From the parsed frontmatter (when Step 1 resolved a match): take `discovery_source` as the epic research path, falling back to the `research` field; record it only if the file exists on disk (warn and treat as unset when it does not), and record the `spec` field as `epic_spec_path` only alongside a recorded research path and only if it too exists on disk. A resolver no-match or no field means no epic context.

**Do not copy epic content into lifecycle files.** Epic research covers all tickets in the epic — copying it wholesale bleeds cross-ticket context into this ticket's research and spec. Record the paths as reference context only; `/cortex-core:refine` will produce ticket-specific research.md and spec.md that reference the epic artifacts without reproducing them.

If `epic_research_path` was found, announce the recorded path and that it will serve as background reference for the ticket-specific research and spec phases.

## Epic Context Injection (during /cortex-core:refine delegation)

When `epic_research_path` was recorded above, before starting Clarify, read the epic research file at `{epic_research_path}` (and `{epic_spec_path}` if present) as background context. Instruct `/cortex-core:refine` to:

- Scope research and spec to THIS ticket's specific requirements only — do not reproduce content that belongs to other tickets in the epic
- Include a `## Epic Reference` section near the top of `research.md` with a link to the epic research path and a one-sentence note on how the epic relates to this ticket
- In `spec.md`, add a brief preamble note referencing the epic research path for broader context

## Refine Starting-Point Rules

`/cortex-core:refine`'s Step 2 (Check State) checks for `cortex/lifecycle/{lifecycle-slug}/research.md` and `cortex/lifecycle/{lifecycle-slug}/spec.md` at those exact paths. Rules:

- If both files exist at those exact paths: Step 2 proceeds normally.
- If a backlog item's `discovery_source` or `research` frontmatter field points to epic research at a different path: that epic file is background context for the Clarify phase, not a substitute for the lifecycle research artifact. `/cortex-core:refine` must still run its full Research phase to produce `cortex/lifecycle/{slug}/research.md`.
