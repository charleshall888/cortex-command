# Backlog Status Check and Backend Routing

Step 2 concerns surviving the `cortex-lifecycle-enter` composition. All consume Step 1's resolved `{backlog-file}` — never re-scan.

**Backend routing (resolve once).** `cortex-read-backlog-backend` (argless) picks the arm every backend-gated write-back routes on: `cortex-backlog` → `cortex-update-item` unchanged; `none` → skip with a one-line advisory; external → the equivalent change best-effort per `backlog.instructions`, surfacing what it can't complete.

<!-- pause: backlog-already-complete-pick config-conditional -->
**Backlog Status Check.** `cortex-lifecycle-enter` returns `needs-decision` for an `already_complete` item, having run no side effect (`open`/`no_match` proceed). Ask: **Close lifecycle** or **Continue from current phase**; when you cannot ask (overnight), default to **Continue**.

- **Continue** → re-run `cortex-lifecycle-enter` with `--acknowledge-complete` appended.
- **Close** → `phase = none` (no lifecycle dir) → exit at once, creating nothing; any other phase → `cortex-lifecycle-finalize --feature <name> --backend {resolved-backend} --backlog-file {backlog-filename}` (marks complete, `session_id=null`, idempotent completion event), then exit.

<!-- pause: backlog-ambiguous-slug-reinvoke question -->
**Exit-2 (ambiguous slug, canonical).** Present the stderr candidates and ask the user to re-invoke disambiguated. Both `cortex-lifecycle-enter` and `-finalize` re-emit it from their `cortex-update-item` calls.
