# Backlog Status Check, Backend Routing, and Artifact Registration

Step 2 concerns surviving the `cortex-lifecycle-enter` composition (create-index, the lifecycle-start write-back, `cortex init --ensure`, `.session`). All consume Step 1's resolved `{backlog-file}` — never re-scan.

**Backend routing (resolve once).** `cortex-read-backlog-backend` (argless) picks the arm every backend-gated write-back routes on — the canonical 3-arm shape: `cortex-backlog` → `cortex-update-item` unchanged; `none` → skip with a one-line advisory; external tracker → the equivalent change best-effort per `backlog.instructions`, surfacing content it can't complete.

<!-- pause: backlog-already-complete-pick config-conditional -->
**Backlog Status Check.** `cortex-lifecycle-enter` returns `state: needs-decision` for an `already_complete` item, having run **no** side effect — it never auto-closes (`open`/`no_match` proceed). On `needs-decision`, ask via `AskUserQuestion`: **Close lifecycle** or **Continue from current phase**; with no `AskUserQuestion` available, e.g. overnight, default to **Continue**.

- **Continue** → re-run `cortex-lifecycle-enter` with `--acknowledge-complete` appended, which drives the full composition.
- **Close** → on `phase = none` (no lifecycle dir yet) **exit** immediately, creating no artifacts and calling no finalize; on any other phase run `cortex-lifecycle-finalize --feature <name> --backend {resolved-backend} --backlog-file {backlog-filename}` (marks complete, `session_id=null`, idempotent completion event), then **exit**.

<!-- pause: backlog-ambiguous-slug-reinvoke question -->
**Exit-2 (ambiguous slug, canonical).** Present the stderr candidates and ask the user to re-invoke disambiguated. Both `cortex-lifecycle-enter` and `-finalize` re-emit it from their `cortex-update-item` calls.

**Registering an artifact (canonical).** Each phase registers what it produced — a skip-if-present append to `index.md`'s `artifacts:` array plus an `updated:` bump:

```
cortex-lifecycle-register-artifact --feature <feature> --artifact <research|spec|plan|review>
```
