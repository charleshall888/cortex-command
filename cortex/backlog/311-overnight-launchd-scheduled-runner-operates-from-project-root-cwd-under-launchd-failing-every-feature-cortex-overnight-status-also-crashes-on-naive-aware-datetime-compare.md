---
schema_version: "1"
uuid: 263a4e97-248b-4f59-b68e-0e33b9f5efe9
title: Overnight launchd-scheduled runner operates from project_root='/' (CWD=/ under launchd), failing every feature; cortex overnight status also crashes on naive/aware datetime compare
status: complete
priority: high
type: bug
created: 2026-06-22
updated: 2026-06-22
lifecycle_phase: complete
lifecycle_slug: overnight-launchd-scheduled-runner-operates-from
complexity: complex
criticality: high
spec: cortex/lifecycle/overnight-launchd-scheduled-runner-operates-from/spec.md
areas: ['overnight-runner']
---
**Why:** A scheduled wild-light overnight session (`overnight-2026-06-22-0246`, registered via `cortex overnight schedule` → launchd, fired `2026-06-22T04:20Z`) failed **0/4 features in 23 min**. Root cause: at fire time the runner operated with **`project_root="/"`** (filesystem root) even though `overnight-state.json` stored the **correct** `project_root: /Users/charlie.hall/Workspaces/wild-light`. Every git / worktree / `batch_runner.py` operation therefore ran in `/` and failed.

**Evidence** (session dir `cortex/lifecycle/sessions/overnight-2026-06-22-0246/`):
- `active-session.json` pointer: `"repo_path": "/"`.
- `overnight-events.log`: `orchestrator_failed exit_code 1` in **both** rounds, immediately after `batch_assigned`; report shows "batch_runner.py did not produce results file" for all features (0 retries).
- `morning_report_commit_failed`: `returncode 128`, stderr `fatal: not a git repository (or any of the parent directories): .git`, `details.project_root: "/"`.
- `push_failed` on `overnight/overnight-2026-06-22-0246`.
- The **planning** orchestrator SUCCEEDED (wrote plans for #261/#262, ~$2.34, 17 min) — only **execution** (batch_runner + git) failed, consistent with a wrong CWD/root for git+worktree ops.
- `overnight-state.json` `project_root` is **correct** → the bad `/` is injected at launchd fire-time, not at launch-time.

**Diagnosis:** launchd jobs start with `CWD=/` and a bare environment. The runner derives the repo/project root from its runtime environment (CWD / env) instead of the stored `state.project_root`, so **scheduled** overnight runs operate in `/`. The **run-now** path inherits the repo CWD + shell env and is unaffected — scheduled overnight is effectively broken on this machine while run-now works. (Per-feature `repo: null` in state may compound this: a null repo likely also defaults to CWD `/`.)

**Fix direction:** the launchd-fired runner must `chdir` to (or resolve every git/worktree/batch path from) `state.project_root` before any git/worktree/`batch_runner` operation — never trust launchd's CWD/env. Treat per-feature `repo: null` as "the session's project_root".

**Role:** developer running scheduled overnight sessions.

**Integration:** overnight runner fire-path (launchd schedule branch) + repo/root resolution; sibling reliability bugs #308, #309 (overnight-runner area).

**Edges / non-goals:** not the run-now path (works); not the planning orchestrator (works).

---

**Bundled second bug — `cortex overnight status` crashes on tz compare.** `cortex overnight status` prints `Error reading status: can't compare offset-naive and offset-aware datetimes` and shows nothing — the command is unusable. Likely a naive-vs-aware `datetime` comparison (a parsed naive timestamp compared against a tz-aware `now()`/`started_at`). Repro: `cortex overnight status` against a session whose state has tz-aware ISO timestamps (e.g. `started_at: ...+00:00`). Review workaround: verify schedule via `launchctl list | grep overnight-schedule` and read `overnight-events.log` directly.
