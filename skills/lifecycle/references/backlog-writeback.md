# Backlog Status Check and Backlog Write-Back

Two Step 2 sub-procedures: check whether the backlog item is already complete, and write the lifecycle start back to the originating backlog item. (`index.md` creation for new lifecycles is handled in `discovery-bootstrap.md`.) This file is also the canonical home for two rules consumed by later phase references: `cortex-update-item` exit-2 handling and artifact registration in `index.md`.

Both sub-procedures consume Step 1's resolved `{backlog-file}` and parsed frontmatter; never re-scan the backlog directory.

## Backend routing (resolve once)

The three `cortex-update-item` write-backs below (close-lifecycle, in-progress status, lifecycle-slug) target the local backlog engine. Before reaching them, resolve the active backend once with `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0). Route on the value:

- **`cortex-backlog`** (the default arm) → proceed exactly as today; run the `cortex-update-item` calls unchanged.
- **`none`** → skip the three `cortex-update-item` calls, noting a one-line advisory that backlog write-back is disabled for this repo, and continue.
- **any other value** (an external tracker) → make the equivalent change best-effort on the configured tracker using the config `backlog.instructions` and your own judgment (e.g. `gh issue` create/edit/close), surfacing the composed content if it cannot be completed so no work is lost.

Each `cortex-update-item` write-back below carries the same `` `cortex-read-backlog-backend` `` routing inline; the default `cortex-backlog` arm is the unchanged behavior.

## Backlog Status Check

Before creating any artifacts or performing write-back, check whether the originating backlog item has already been marked complete outside the lifecycle. **Do not re-scan the backlog directory in this sub-procedure** — consume Step 1's resolved result.

1. **If no match was found** (resolver exit 3), or the parsed `status` field is not `complete`: skip this section silently and fall through to subsequent sections as normal.
2. **If a match was found and the parsed `status` is `complete`**: present a prompt using `AskUserQuestion` with two options:
   - **"Close lifecycle"**
   - **"Continue from current phase"**

   If `AskUserQuestion` is unavailable (e.g., overnight batch context where no interactive prompt is possible), default to **Continue** — never auto-close.

3. **On "Continue"**: fall through as normal.

4. **On "Close lifecycle"**: the behavior depends on the current phase:

   - **If `phase != none`** (a `cortex/lifecycle/{feature}/` directory exists):
     1. Append the following NDJSON event to `cortex/lifecycle/{feature}/events.log` (one JSON object per line):
        ```json
        {"ts": "<ISO 8601>", "event": "feature_complete", "feature": "<name>"}
        ```
        Intentionally omit `tasks_total` and `rework_cycles` — `plan.md` may not exist on this path. Do NOT add those fields with value 0.
     2. Gate this write-back on the backend resolved via `` `cortex-read-backlog-backend` `` (see Backend routing). On `cortex-backlog`, run:
        ```bash
        cortex-update-item <slug> --status complete --lifecycle-phase complete --session-id null
        ```
        Where `<slug>` is the backlog filename stem. On `none`, skip with a one-line advisory; on any other value, make the equivalent close best-effort on the external tracker per `backlog.instructions`.
     3. **Exit immediately.** Do not proceed to Discovery Bootstrap or any subsequent Step 2 sections or later steps.

   - **If `phase = none`** (no `cortex/lifecycle/{feature}/` directory exists):
     1. **Exit immediately** without creating any lifecycle artifacts (no directory, no events.log, no index.md) and without calling `cortex-update-item`.

## Backlog Write-Back (Lifecycle Start)

After registering the session, attempt to write the lifecycle start back to the originating backlog item. **Do not re-scan the backlog directory in this sub-procedure** — consume Step 1's resolved result.

If Step 1 resolved a `{backlog-file}` (exit 0), gate this write-back on the backend resolved via `` `cortex-read-backlog-backend` `` (see Backend routing). On `cortex-backlog`, run:

```bash
cortex-update-item <path> --status in_progress --session-id $LIFECYCLE_SESSION_ID --lifecycle-phase research
```

Where `<path>` is the slug-or-uuid of the matched backlog item (e.g., `045-my-feature`). On `none`, skip with a one-line advisory; on any other value, make the equivalent in-progress update best-effort on the external tracker per `backlog.instructions`.

Additionally, when `phase = none` (new lifecycle only), record the lifecycle slug — gated on the backend resolved via `` `cortex-read-backlog-backend` `` (see Backend routing). On `cortex-backlog`, run:

```bash
cortex-update-item <path> --lifecycle-slug {lifecycle-slug}
```

On `none`, skip with a one-line advisory; on any other value, record the lifecycle-slug association best-effort on the external tracker per `backlog.instructions`.

The status write-back runs on all phases when a match is found.

If Step 1's resolver returned exit 3 (no backlog match), skip this step silently — lifecycles can exist independently of the backlog.

## `cortex-update-item` Exit-2 Handling (canonical)

If any `cortex-update-item` invocation exits 2, that signals an ambiguous slug match. Present the candidate list emitted on stderr to the user and ask them to re-invoke with a disambiguated slug. This rule covers every `cortex-update-item` call site — the invocations in this file (the close-lifecycle call, the in-progress status write-back, the lifecycle-slug write-back) and those in later phase references, which point here rather than restating it.

## Registering an Artifact in index.md (canonical)

When a phase produces an artifact (e.g. `"plan"`, `"review"`), register it in `cortex/lifecycle/{feature}/index.md`:

- If the artifact key is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append the artifact key to the artifacts inline array
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

Phase references point here rather than restating these bullets.
