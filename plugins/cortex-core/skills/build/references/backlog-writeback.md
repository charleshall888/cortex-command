# Backlog Status Check

The Step 2 cases that `cortex-lifecycle-enter` leaves to you. All use the `{backlog-file}` found in Step 1 — never search again.

<!-- pause: backlog-already-complete-pick config-conditional -->
**Backlog Status Check.** `cortex-lifecycle-enter` returns `needs-decision` for an `already_complete` item and changes nothing (`open`/`no_match` proceed). Ask: **Close lifecycle** or **Continue from current phase**; when you cannot ask (overnight), default to **Continue**.

- **Continue** → re-run `cortex-lifecycle-enter` with `--acknowledge-complete` appended.
- **Close** → `phase = none` (no lifecycle dir) → exit now and create nothing; any other phase → `cortex-lifecycle-finalize --feature <name> --backlog-file {backlog-filename}` (finds the backend itself; marks complete, `session_id=null`, logs the completion event once), then exit.

<!-- pause: backlog-ambiguous-slug-reinvoke question -->
**Exit-2 (ambiguous slug, canonical).** Show the stderr candidates and ask the user to re-run with an exact slug. Both `cortex-lifecycle-enter` and `-finalize` pass it on from their `cortex-update-item` calls.
