# Discovery Bootstrap

## Create index.md (New Lifecycle Only)

When `phase = none` (no prior `cortex/lifecycle/{slug}/` directory exists), create `cortex/lifecycle/{slug}/index.md` as follows. **Do not re-scan the backlog directory in this sub-procedure** — consume Step 1's resolved `{backlog-file}` and parsed frontmatter.

**Guard**: If `cortex/lifecycle/{slug}/index.md` already exists, skip this entire block — do not overwrite.

Populate from Step 1's parsed frontmatter; on resolver exit 3, set null fields.

Write `cortex/lifecycle/{slug}/index.md` with all seven required frontmatter fields:

```yaml
---
feature: {lifecycle-slug}
parent_backlog_uuid: {uuid from backlog item, or null}
parent_backlog_id: {numeric ID prefix from backlog filename, or null}
artifacts: []
tags: {inline array from backlog item tags field, or []}
created: {today's date in ISO 8601, e.g. 2026-03-23}
updated: {today's date in ISO 8601}
---
```

If a matching backlog item was found, append the wikilink body:

```
# [[{NNN}-{backlog-slug}|{backlog title}]]

Feature lifecycle for [[{NNN}-{backlog-slug}]].
```

Where `{NNN}` is the zero-padded numeric prefix exactly as it appears in the backlog filename (e.g. `030`, `1048`), and `{backlog-slug}` is the filename without its `.md` extension and numeric prefix (e.g. `cf-tunnel-fallback-polish` from `030-cf-tunnel-fallback-polish.md`). Use the full filename stem (numeric prefix + slug) in the wikilink, e.g. `[[1048-lifecycle-feature-index|...]]`.

If no matching backlog item was found, omit the heading and body line entirely.

`artifacts: []` must always use inline YAML array notation — never block notation.

## Epic Research Detection

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

`/cortex-core:refine`'s Step 2 (Check State) checks for `cortex/lifecycle/{lifecycle-slug}/research.md` and `cortex/lifecycle/{lifecycle-slug}/spec.md` at those exact paths. Rules:

- If both files exist at those exact paths: Step 2 proceeds normally.
- If a backlog item's `discovery_source` or `research` frontmatter field points to epic research at a different path: that epic file is background context for the Clarify phase, not a substitute for the lifecycle research artifact. `/cortex-core:refine` must still run its full Research phase to produce `cortex/lifecycle/{slug}/research.md`.
