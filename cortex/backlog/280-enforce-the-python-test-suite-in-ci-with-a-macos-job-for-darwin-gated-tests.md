---
schema_version: "1"
uuid: 24bcac44-fef4-448d-aaa5-b87e219e8397
title: "Enforce the Python test suite in CI with a macOS job for darwin-gated tests"
status: wont-do
priority: medium
type: chore
created: 2026-06-02
updated: 2026-06-02
---
**Why:** `.github/workflows/validate.yml` runs only the skill and callgraph validators — no Python tests. The whole `cortex_command` suite (`just test`) is enforced only when a developer runs it locally. #277 is the concrete example: its platform-agnostic guards run only under local `just test`, and its headline behaviors — real scheduled fire on stock macOS, `cortex overnight schedule` exit-0 on Darwin 25+, bootout-on-fire — are darwin-gated tests that run on no CI runner at all. A regression in any of these can land on `main` unguarded.

**Role:** Make the Python test suite an enforced CI gate on push and PR, including a macOS job so the darwin-gated overnight/scheduler tests actually execute somewhere.

**Integration:**
- Add a CI job running `just test` (or the pytest suites) on push and PR.
- Add a macOS runner job for the darwin-gated suites: `test_scheduler_e2e`, `test_scheduler_bootout_on_fire`, the schedule exit-0 path, and the launcher fire-marker tests.

**Edges:**
- Hosted macOS runners cost more minutes and are slower — decide which suites run on which OS to keep the matrix lean.
- The darwin fire tests need real launchd access in the GUI domain (`gui/$(id -u)`); hosted macOS runners may lack a logged-in GUI session, so verify reachability and mark any unreachable subset explicitly rather than letting it silently skip.
- Bare `python3 cortex_command/...` entry points fail outside the uv tool venv (hit during #277 completion when regenerating the backlog index) — CI must invoke through the project venv / console scripts, not system `python3`.

**Touch-points:** `.github/workflows/validate.yml` (or a new workflow), the `justfile` test recipes, and the darwin `skipif` gates under `cortex_command/overnight/tests/`. Flagged out-of-scope by the #277 plan (Risks: "Test reachability") and confirmed during completion.

---

## Decision: wont-do (2026-06-02, during /refine clarify)

Dropped at the clarify gate after a premise check. The Why claims the darwin-gated tests "run on no CI runner at all" — but `cortex/lifecycle.config.md` sets `test-command: just test`, so the lifecycle **complete** phase already runs the full `just test` suite on first-run (`skills/lifecycle/references/complete.md` Step 1). That runs on the maintainer's actual macOS, in a real GUI launchd session — which exercises the darwin tests *including* `test_scheduler_bootout_on_fire`, the one test a hosted macOS runner could never run (hosted runners lack a logged-in GUI session and would silently skip it).

So the residual value of the proposed work is narrower than the ticket frames:
- A **Linux** CI job would add a genuine but modest backstop (unconditional guard for changes that bypass `complete`: direct-to-main, quick fixes, external PRs on this public repo).
- The **macOS** job — the ticket's headline element — is largely redundant with the maintainer's local `complete` runs and *cannot* run its marquee GUI test anyway. Low marginal value at ~10x runner cost/latency.

Given the value case doesn't survive the premise, the maintainer elected to close rather than build. If bypass-path regressions (non-lifecycle PRs, direct-to-main) later prove a real problem, reopen scoped to a **Linux-only, non-blocking** signal job — not the macOS matrix.