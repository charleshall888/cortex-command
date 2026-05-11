# Backlog Status Check, index.md Creation, and Backlog Write-Back

Three closely related Step 2 sub-procedures: check whether the backlog item is already complete, create `index.md` for new lifecycles, and write the lifecycle start back to the originating backlog item.

## Backlog Status Check

Before creating any artifacts or performing write-back, check whether the originating backlog item has already been marked complete outside the lifecycle:

1. **Scan** for `backlog/[0-9]*-*{feature}*.md` — a matching backlog file for this feature.
2. **If no match is found**, or the matched file's YAML frontmatter `status` field is not `complete`: skip this section silently and fall through to "Create index.md" and subsequent sections as normal.
3. **If a match is found and `status: complete`**: present a prompt using `AskUserQuestion` with two options:
   - **"Close lifecycle"**
   - **"Continue from current phase"**

   If `AskUserQuestion` is unavailable (e.g., overnight batch context where no interactive prompt is possible), default to **Continue** — never auto-close.

4. **On "Continue"** (or if the check was skipped): fall through to "Create index.md" and "Backlog Write-Back" sections as normal. No further action from this section.

5. **On "Close lifecycle"**: the behavior depends on the current phase:

   - **If `phase != none`** (a `lifecycle/{feature}/` directory exists):
     1. Append the following NDJSON event to `lifecycle/{feature}/events.log` (one JSON object per line):
        ```json
        {"ts": "<ISO 8601>", "event": "feature_complete", "feature": "<name>"}
        ```
        Intentionally omit `tasks_total` and `rework_cycles` — `plan.md` may not exist on this path (the lifecycle may have been completed out-of-band before a plan was written). Do NOT add those fields with value 0.
     2. Run:
        ```bash
        cortex-update-item <slug> status=complete lifecycle_phase=complete session_id=null
        ```
        Where `<slug>` is the backlog filename stem (e.g., `1043-add-backlog-status-detection-to-lifecycle-resume`).
     3. **Exit immediately.** Do not proceed to "Create index.md", "Backlog Write-Back", "Discovery Bootstrap", or any subsequent Step 2 sections or later steps. The lifecycle is closed.

   - **If `phase = none`** (no `lifecycle/{feature}/` directory exists):
     1. **Exit immediately** without creating any lifecycle artifacts (no directory, no events.log, no index.md) and without calling `cortex-update-item`. The backlog item is already complete and no lifecycle artifacts need to exist.

## Create index.md (New Lifecycle Only)

When `phase = none` (no prior `lifecycle/{slug}/` directory exists), create `lifecycle/{slug}/index.md` as follows:

**Guard**: If `lifecycle/{slug}/index.md` already exists, skip this entire block — do not overwrite.

Scan `backlog/[0-9]*-*{slug}*.md` for a matching backlog item. If a match is found, read its frontmatter to populate the fields below. If no match is found, set null fields.

Write `lifecycle/{slug}/index.md` with all seven required frontmatter fields:

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

## Backlog Write-Back (Lifecycle Start)

After registering the session, attempt to write the lifecycle start back to the originating backlog item. Scan for a matching backlog file:

```
scan backlog/[0-9]*-*{feature}*.md for a matching file
```

If a match is found, run:

```bash
cortex-update-item <path> status=in_progress session_id=$LIFECYCLE_SESSION_ID lifecycle_phase=research
```

Where `<path>` is the slug-or-uuid of the matched backlog item (e.g., `045-my-feature`).

Additionally, when `phase = none` (new lifecycle only), also run the following write-back to record the lifecycle slug — this is separate from and in addition to the status write-back above:

```bash
cortex-update-item <path> lifecycle_slug={lifecycle-slug}
```

This `lifecycle_slug` write-back runs only when `phase = none`. The status write-back runs on all phases when a match is found.

If no backlog item is found, skip this step silently -- lifecycles can exist independently of the backlog.
