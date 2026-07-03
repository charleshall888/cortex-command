# Backlog Status Check and Backlog Write-Back

Two Step 2 sub-procedures: check whether the backlog item is already complete, and write the lifecycle start back to the originating backlog item. (`index.md` creation for new lifecycles is handled in `discovery-bootstrap.md`.) This file is also the canonical home for two rules consumed by later phase references: `cortex-update-item` exit-2 handling and artifact registration in `index.md`.

Both sub-procedures consume Step 1's resolved `{backlog-file}` and parsed frontmatter; never re-scan the backlog directory.

## Backend routing (resolve once)

Two write-back paths consume the active backlog backend, resolved once with `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0): the **close-lifecycle** `cortex-update-item` write-back, which stays inline in the Backlog Status Check close path below, and the **lifecycle-start** in-progress + lifecycle-slug write-backs, which are offloaded to the backend-routed start-sync verb (see Backlog Write-Back (Lifecycle Start) below — pass the resolved value as its `--backend`). Route on the value:

- **`cortex-backlog`** (the default arm) → run the `cortex-update-item` call(s) unchanged.
- **`none`** → skip the `cortex-update-item` call(s), noting a one-line advisory that backlog write-back is disabled for this repo, and continue.
- **any other value** (an external tracker) → make the equivalent change best-effort on the configured tracker using the config `backlog.instructions` and your own judgment (e.g. `gh issue` create/edit/close), surfacing the composed content if it cannot be completed so no work is lost.

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
     1. Log the completion event:
        ```bash
        cortex-lifecycle-event log --event feature_complete --feature <name>
        ```
        Intentionally omit `tasks_total` and `rework_cycles` — `plan.md` may not exist on this path. Do NOT add those fields with value 0.
     2. Gate this write-back on the backend resolved via `` `cortex-read-backlog-backend` `` (see Backend routing). On `cortex-backlog`, run:
        ```bash
        cortex-update-item <slug> --status complete --lifecycle-phase complete --session-id null
        ```
        Where `<slug>` is the backlog filename stem.
     3. **Exit immediately.** Do not proceed to Discovery Bootstrap or any subsequent Step 2 sections or later steps.

   - **If `phase = none`** (no `cortex/lifecycle/{feature}/` directory exists):
     1. **Exit immediately** without creating any lifecycle artifacts (no directory, no events.log, no index.md) and without calling `cortex-update-item`.

## Backlog Write-Back (Lifecycle Start)

After registering the session, write the lifecycle start back to the originating backlog item via the backend-routed start-sync verb, consuming Step 1's resolved result. Resolve the backend once (see Backend routing) and pass it through:

```bash
cortex-lifecycle-start-sync --backend {resolved-backend} --backlog-file {backlog-filename-or-empty-string} --phase {none-or-current-phase} --session-id $LIFECYCLE_SESSION_ID --lifecycle-slug {lifecycle-slug}
```

`{backlog-filename}` is Step 1's resolver `filename` basename (e.g. `326-foo.md`); the verb reduces it to the `cortex-update-item` slug itself. The verb runs the in-progress status write-back on every phase, and additionally records the lifecycle-slug association **only when `--phase none`** (a brand-new lifecycle). On a resolver exit-3 no-match, pass `--backlog-file ""` and the verb no-ops.

On **any other value** of the backend (an external tracker) the verb makes no local write — make the equivalent **in-progress** update **and (on `--phase none`) the lifecycle-slug association** best-effort on the external tracker per `backlog.instructions`, surfacing the composed content if it cannot be completed so no work is lost.

## `cortex-update-item` Exit-2 Handling (canonical)

If any `cortex-update-item` invocation exits 2, that signals an ambiguous slug match. Present the candidate list emitted on stderr to the user and ask them to re-invoke with a disambiguated slug.

## Registering an Artifact in index.md (canonical)

When a phase produces an artifact (e.g. `"plan"`, `"review"`), register it in `cortex/lifecycle/{feature}/index.md`:

- If the artifact key is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append the artifact key to the artifacts inline array
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

Phase references point here rather than restating these bullets.
