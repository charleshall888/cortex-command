# Backlog Status Check, Backend Routing, and Artifact Registration

Step 2 concerns surviving the `cortex-lifecycle-enter` composition (which owns create-index, the lifecycle-start write-back, `cortex init --ensure`, and `.session`). All consume Step 1's resolved `{backlog-file}` — never re-scan.

**Backend routing (resolve once).** `cortex-read-backlog-backend` (argless) picks the arm every backend-gated write-back routes on — the canonical 3-arm shape: `cortex-backlog` → `cortex-update-item` unchanged; `none` → skip with a one-line advisory; external tracker → equivalent change best-effort per `backlog.instructions`, surfacing content it can't complete.

**Backlog Status Check.** `cortex-lifecycle-enter` reports the pre-entry `backlog_status` (never auto-closes). `open`/`no_match` → proceed. `already_complete` → `AskUserQuestion`: **Close lifecycle** / **Continue from current phase** (no AskUserQuestion, e.g. overnight → default **Continue**). **Close** → `cortex-lifecycle-finalize --feature <name> --backend {resolved-backend} --backlog-file {backlog-filename}` (marks complete, `session_id=null`, idempotent `feature_complete`), then **exit**.

**Exit-2 (ambiguous slug, canonical).** Present the stderr candidates and ask the user to re-invoke disambiguated; `cortex-lifecycle-enter`/`-finalize` re-emit it from their `cortex-update-item` calls.

**Registering an artifact (canonical).** Each phase registers its produced artifact — skip-if-present append to `index.md`'s `artifacts:` array + `updated:` bump: `cortex-lifecycle-register-artifact --feature <feature> --artifact <research|spec|plan|review>`.
