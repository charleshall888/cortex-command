# Supporting Techniques

Three techniques referenced from the 4-phase protocol; read on demand when the body points here.

## Backward Root-Cause Tracing

**Core principle**: Bugs manifest far from their source. Trace backward through the execution path to the original trigger, then fix there — not at the symptom.

Example: `git commit` fails with a GPG error because `GNUPGHOME` is unset → trace up: the SessionStart hook that sets it didn't complete → its socket-path logic broke when `TMPDIR` changed. Fix the socket-path logic, not the symptom (don't suppress the GPG error in the commit skill).

When you can't trace manually, instrument: log state at each boundary (`set -x`, or a targeted `echo ... >&2`) rather than guessing.

---

## Defense-in-Depth Validation

**Core principle**: One validation point can be bypassed by other code paths. Validate at every layer data passes through — make the bug structurally impossible.

**The four layers:**

1. **Entry point**: reject invalid input at the boundary (e.g., a hook checks required env vars before using them)
2. **Business logic**: ensure data makes sense for this operation (e.g., a lifecycle script validates events.log is well-formed JSON before appending)
3. **Environment guards**: prevent dangerous operations in the wrong context (e.g., verify the working directory before a destructive operation)
4. **Debug instrumentation**: log state at each boundary so anything that slips through leaves a forensic trail

---

## Condition-Based Waiting

**Core principle**: Arbitrary sleeps guess at timing and race under load. Wait for the actual condition you care about, not a guess about how long it takes — poll it in a loop with a timeout, not a fixed `sleep N`.

Reserve a real sleep only for testing timing behavior itself (a debounce or rate-limit), documented with a comment.
