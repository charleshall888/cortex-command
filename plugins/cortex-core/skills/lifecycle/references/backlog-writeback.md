# Backlog Status Check and Backlog Write-Back

Two Step 2 sub-procedures — check whether the backlog item is already complete, and write the lifecycle start back to it — plus the canonical home for two rules later phases cite: `cortex-update-item` exit-2 handling and `index.md` artifact registration. (`index.md` creation for new lifecycles lives in `discovery-bootstrap.md`.)

Both sub-procedures consume Step 1's resolved `{backlog-file}` and parsed frontmatter — never re-scan the backlog directory.

## Backend routing (resolve once)

Resolve the backend once with `cortex-read-backlog-backend` (argless; prints the backend, exits 0) and route both write-back paths on it:

- **`cortex-backlog`** (the default) → run the `cortex-update-item` call(s) unchanged.
- **`none`** → skip them with a one-line advisory that write-back is disabled for this repo, and continue.
- **any other value** (an external tracker) → make the equivalent change best-effort on the tracker per config `backlog.instructions` and your judgment (e.g. `gh issue` create/edit/close); if it can't complete, surface the composed content so no work is lost.

The close-lifecycle write-back stays inline below; the lifecycle-start write-back is offloaded to `cortex-lifecycle-start-sync` (pass the resolved value as `--backend`).

## Backlog Status Check

Before creating artifacts or writing back, check whether the item was already completed outside the lifecycle (consume Step 1's result, don't re-scan):

1. **No match** (resolver exit 3) or `status` ≠ `complete` → skip silently, fall through.
2. **Match with `status = complete`** → `AskUserQuestion` with **Close lifecycle** / **Continue from current phase**. If AskUserQuestion is unavailable (overnight batch, no interactive prompt), default to **Continue** — never auto-close.
3. **Continue** → fall through.
4. **Close lifecycle**:
   - **`phase != none`** (a `cortex/lifecycle/{feature}/` directory exists): log completion (omit `tasks_total`/`rework_cycles` — plan.md may not exist on this path; do NOT set them to 0), then on the `cortex-backlog` backend run the close write-back, then **exit immediately** (no Discovery Bootstrap, no later steps):
     ```bash
     cortex-lifecycle-event log --event feature_complete --feature <name>
     cortex-update-item <slug> --status complete --lifecycle-phase complete --session-id null
     ```
     (`<slug>` = the backlog filename stem.)
   - **`phase = none`** (no directory): **exit immediately** — create no artifacts (no directory, events.log, or index.md) and call no `cortex-update-item`.

## Backlog Write-Back (Lifecycle Start)

After registering the session, write the lifecycle start back via the backend-routed verb (backend resolved once, above):

```bash
cortex-lifecycle-start-sync --backend {resolved-backend} --backlog-file {backlog-filename-or-empty-string} --phase {none-or-current-phase} --session-id $LIFECYCLE_SESSION_ID --lifecycle-slug {lifecycle-slug}
```

`{backlog-filename}` is the resolver's `filename` basename (e.g. `326-foo.md`); the verb reduces it to the slug. It writes the in-progress status on every phase and records the lifecycle-slug association **only on `--phase none`** (a new lifecycle). On a resolver exit-3 no-match, pass `--backlog-file ""` and the verb no-ops. On an external tracker the verb makes no local write — make the equivalent in-progress update (and, on `--phase none`, the slug association) best-effort per `backlog.instructions`, surfacing content that can't complete.

## `cortex-update-item` Exit-2 Handling (canonical)

Exit 2 signals an ambiguous slug match. Present the stderr candidate list to the user and ask them to re-invoke with a disambiguated slug.

## Registering an Artifact in index.md (canonical)

When a phase produces an artifact (e.g. `"plan"`, `"review"`), register it in `cortex/lifecycle/{feature}/index.md`: skip if the key is already in the `artifacts` array; otherwise append it, set `updated` to today's date, and rewrite `index.md` atomically. Phase references point here rather than restating this.
