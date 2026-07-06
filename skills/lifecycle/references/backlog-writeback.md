# Backlog Status Check and Backlog Write-Back

Two Step 2 sub-procedures — check whether the backlog item is already complete, and write the lifecycle start back to it — plus the canonical home for `cortex-update-item` exit-2 handling and `index.md` artifact registration (`index.md` creation for new lifecycles lives in `discovery-bootstrap.md`). Both consume Step 1's resolved `{backlog-file}` and parsed frontmatter — never re-scan the backlog directory.

## Backend routing (resolve once)

Resolve the backend once with `cortex-read-backlog-backend` (argless, exits 0) and route both write-back paths on it: `cortex-backlog` (default) → run the `cortex-update-item` call(s) unchanged; `none` → skip with a one-line advisory and continue; any other value (external tracker) → make the equivalent change best-effort per config `backlog.instructions` (e.g. `gh issue` create/edit/close), surfacing the composed content if it can't complete.

The close-lifecycle write-back stays inline below; the lifecycle-start write-back is offloaded to `cortex-lifecycle-start-sync` (pass the resolved value as `--backend`).

## Backlog Status Check

Before creating artifacts or writing back, check whether the item was already completed outside the lifecycle:

1. **No match** (resolver exit 3) or `status` ≠ `complete` → skip silently, fall through.
2. **Match with `status = complete`** → `AskUserQuestion` with **Close lifecycle** / **Continue from current phase**. No AskUserQuestion available (overnight batch) → default **Continue**, never auto-close.
3. **Continue** → fall through.
4. **Close lifecycle**:
   - **`phase != none`** (lifecycle directory exists): log completion (omit `tasks_total`/`rework_cycles` rather than zeroing them), run the close write-back on the `cortex-backlog` backend, then **exit immediately**:
     ```bash
     cortex-lifecycle-event feature-complete --feature <name>
     cortex-update-item <slug> --status complete --lifecycle-phase complete --session-id null
     ```
     (`<slug>` = the backlog filename stem.)
   - **`phase = none`** (no directory): **exit immediately** — create no artifacts and call no `cortex-update-item`.

## Backlog Write-Back (Lifecycle Start)

After registering the session, write the lifecycle start back via the backend-routed verb:

```bash
cortex-lifecycle-start-sync --backend {resolved-backend} --backlog-file {backlog-filename-or-empty-string} --phase {none-or-current-phase} --session-id $LIFECYCLE_SESSION_ID --lifecycle-slug {lifecycle-slug}
```

`{backlog-filename}` is the resolver's `filename` basename; the verb reduces it to the slug, writes in-progress status on every phase, and records the lifecycle-slug association only on `--phase none`. On a resolver exit-3 no-match, pass `--backlog-file ""`. On an external tracker, make the equivalent update best-effort per `backlog.instructions`, surfacing content that can't complete.

## `cortex-update-item` Exit-2 Handling (canonical)

Exit 2 signals an ambiguous slug match — present the stderr candidate list and ask the user to re-invoke with a disambiguated slug.

## Registering an Artifact in index.md (canonical)

When a phase produces an artifact (e.g. `"plan"`, `"review"`), register it in `cortex/lifecycle/{feature}/index.md`: skip if already in `artifacts`; otherwise append it, set `updated` to today's date, and rewrite atomically. Phase references point here rather than restating this.
