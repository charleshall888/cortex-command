# Plan: harden-the-distributed-cli-against-transitive

## Overview
Fix the live dashboard 500 by rewriting all 13 `TemplateResponse` call sites to the
cross-compatible request-first form, then bound the drift-prone web stack as wheel metadata so that
— once the capped release ships (cut automatically by `auto-release.yml` on merge to main; see
Risks for the pre-cap reinstall window) — every install path (bare `uv tool install`, `install.sh`,
the auto-reinstall) lands a working, Starlette-1.x-safe dependency set. A route-level `TestClient`
smoke test wired into CI's fresh-resolve path (with an explicit ≥1.0 version assertion so the gate
is genuinely discriminating) and `just test` guards against recurrence; a fresh-install end-to-end
check and a deferred-drift-automation follow-up ticket close out the AC. No new architectural
pattern is introduced — this is pinning discipline plus a test guard.

## Outline

### Phase 1: Fix & Bound (tasks: 1, 2)
**Goal**: Make a fresh install land a working, Starlette-1.x-safe dependency set — rewrite the
broken call sites to the supported API and bound the drift-prone web-stack deps via metadata that
travels in the wheel.
**Checkpoint**: All 13 call sites are request-first; `pyproject.toml` carries the starlette direct
bound + web-stack caps; `uv lock` succeeds (exit 0) under the new bounds.

### Phase 2: Prevent recurrence (tasks: 3, 4, 5, 6, 7, 8)
**Goal**: Guard the render path on a fresh ≥1.0 resolve in CI and locally, verify a clean fresh
install renders end-to-end on both named install paths, and record the deferred keep-current decision.
**Checkpoint**: Route smoke test green under `just test` and wired into `validate.yml`'s
fresh-resolve step; discrimination check + fresh-install transcript recorded in lifecycle artifacts;
follow-up backlog ticket filed.

## Tasks

### Task 1: Rewrite the 13 `TemplateResponse` call sites to request-first form
- **Files**: `cortex_command/dashboard/app.py`
- **What**: Convert all 13 name-first `templates.TemplateResponse("name.html", {"request": request, ...})`
  calls to request-first `templates.TemplateResponse(request, "name.html", {...})`. This is
  cross-compatible across Starlette 0.29→1.x and fixes the `TypeError: unhashable type: 'dict'` → 500
  that name-first throws on ≥1.0. (Spec Requirement 1.)
- **Depends on**: none
- **Complexity**: simple
- **Context**: The 13 calls are at lines 268, 278, 289, 299, 308, 318, 327, 336, 345, 354, 363, 372,
  387 across 14 `@app.get` routes (`/health` returns `JSONResponse` and is not a `TemplateResponse`).
  Keep the template name string and the context dict contents identical — only the argument order
  changes (`request` moves from inside the dict's `"request"` key position to the first positional
  arg; the dict stays as the third arg, still carrying `"request": request` is harmless and idiomatic
  but the leading positional `request` is what fixes the bind). No function signature changes, so no
  external callers are affected. The existing `cortex_command/dashboard/tests/test_templates.py`
  renders Jinja directly and will not catch the difference — that gap is closed by Task 4.
- **Verification**: `grep -c 'TemplateResponse(' cortex_command/dashboard/app.py` = 13 (no call
  added or removed) — pass if count = 13. Definitive ≥1.0 correctness is gated by Task 4's route test
  on a fresh resolve (Tasks 5 and 7).
- **Status**: [ ] pending

### Task 2: Promote `starlette` to a direct bounded dep and cap the drift-prone web stack
- **Files**: `pyproject.toml`, `uv.lock`
- **What**: In `[project.dependencies]`, add `starlette>=0.49.1,<2.0` (transitive-only today) with a
  one-line comment recording why it is direct, and bound the drift-prone web stack:
  `fastapi<1.0`, `uvicorn[standard]<1.0`, `markdown<4`, `psutil>=5.9,<8`. Leave `jinja2`, `pyyaml`,
  and `mcp` as-is. Regenerate the lock. (Spec Requirements 2 and 3 — combined because both edit the
  same `[project.dependencies]` block.)
- **Depends on**: none
- **Context**: Floor `>=0.49.1` bakes in the 2025 ReDoS CVE fix (CVE-2025-62727); cap `<2.0` adopts
  the 1.x line (Task 1 makes the code 1.x-safe) and blocks only the next major. The comment must
  record *why* starlette is direct: **FastAPI depends on starlette with no upper bound and its
  maintainers refuse to add one** (discussions #6211/#15193), so the app must own this bound; the
  direct cap also governs the `mcp`/`sse-starlette` starlette paths. Record the *uncapped* invariant
  — do **not** bake a specific FastAPI floor number into the comment (the exact floor varies by
  fastapi version, e.g. the locked fastapi 0.133.1 is not the floor research sampled, and an
  out-of-date number invites a misread). The bound only needs to stay a subset of FastAPI's
  open-topped range, which any `<2.0` satisfies today. `<1.0` is explicitly rejected — its operative
  present-tense reason is that it discards Task 1's value (re-freezing on 0.x), and it would
  additionally become unsatisfiable *once* `mcp`/`sse-starlette` floors rise to ≥1.0. hatchling emits
  `[project.dependencies]` into wheel `requires-dist` (verified), so these bounds reach every install
  path. `uv lock` keeps the existing starlette 0.52.1 pin (it satisfies `>=0.49.1,<2.0`), so the dev
  venv is unchanged — the ≥1.0 exercise happens only on fresh resolves (Task 5's CI step asserts the
  resolved version is ≥1.0; Task 7).
- **Verification**: the four bound edits land as quoted dependency-table entries (anchored greps that
  match the `"<name><spec>"` form, not an explanatory comment) — `grep -cE '"starlette>=0\.49\.1,<2\.0"'
  pyproject.toml` = 1, `grep -cE '"fastapi[^"]*<1\.0"' pyproject.toml` = 1,
  `grep -cE '"uvicorn\[standard\][^"]*<1\.0"' pyproject.toml` = 1, `grep -cE '"markdown[^"]*<4"'
  pyproject.toml` = 1, `grep -cE '"psutil>=5\.9,<8"' pyproject.toml` = 1; AND each appears under
  `[project.dependencies]` (not a comment or another table — confirm via
  `python3 -c "import tomllib,sys; d=tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; print(sum('starlette' in x for x in d), sum(x.startswith('fastapi') for x in d))"` showing the
  parsed list carries them); AND `uv lock` exits 0. Pass if all five anchored counts = 1, the parsed
  `[project.dependencies]` list contains the bounds, and `uv lock` exit code = 0. (The explanatory
  comment must not embed the literal `starlette>=0.49.1,<2.0` token, or the anchored quote-form grep
  is what keeps the count at 1 regardless.)
- **Status**: [ ] pending

### Task 3: Declare `httpx` as a dev/test dependency
- **Files**: `pyproject.toml`, `uv.lock`
- **What**: Add `httpx` to `[dependency-groups].dev` so the `TestClient` backend (Task 4) is not an
  incidental transitive of `mcp`. (Spec Requirement 5.)
- **Depends on**: [2]
- **Context**: `starlette.testclient.TestClient` is httpx-backed; httpx is present today only
  transitively via `mcp` and would ImportError the route test the day `mcp` drops it. The
  `[dependency-groups].dev` table is the project's existing dev-group home (distinct from
  `[project.dependencies]` that Task 2 edits — depends on [2] only to serialize the same-file write).
  Regenerate `uv.lock` after the edit.
- **Verification**: `grep -c 'httpx' pyproject.toml` ≥ 1 — pass if count ≥ 1; `uv lock` exits 0.
- **Status**: [ ] pending

### Task 4: Add a route-level `TestClient` smoke test exercising the real render path
- **Files**: `cortex_command/dashboard/tests/test_routes_smoke.py`
- **What**: Add a `starlette.testclient.TestClient`-based test asserting `GET /`, `/sessions`,
  `/health`, and each of the 10 `/partials/*` routes return 200, and `GET /sessions/{missing-id}`
  returns 404 — driving each handler through Starlette's `TemplateResponse` (the layer the existing
  Jinja-direct test bypasses). (Spec Requirement 4, acceptance (a).)
- **Depends on**: [1, 3]
- **Context**: The 10 partials are `/partials/{fleet-panel, alerts-banner, session-panel,
  feature-cards, round-history, escalations, activity-stream, backlog, metrics, swim-lane}`. Set up a
  fixture root via `CORTEX_REPO_ROOT` pointing at a tmp dir containing `.claude/` and
  `cortex/lifecycle/` — `.claude` is required by the lifespan's `RuntimeError` guard (`app.py:238`),
  not by `_resolve_user_project_root` (which returns `CORTEX_REPO_ROOT` verbatim when set). Manage the
  lifespan deterministically: either avoid entering the lifespan, or enter it via
  `with TestClient(app) as client:` and ensure the four uncancelled `while True` background poller
  tasks (`asyncio.create_task(run_polling(...))`) and the PID file are torn down/isolated so the suite
  does not hang or leak. Follow the pytest-fixture conventions already used under
  `cortex_command/dashboard/tests/`. On the dev venv (Starlette 0.52.1) request-first returns 200, so
  this passes locally and proves only well-formedness; the *recurring* discriminating ≥1.0 run is
  Task 5's CI step (which both resolves ≥1.0 freshly and asserts that version), with Task 6 (one-time
  pre-rewrite discrimination) and Task 7 (one-time fresh-install) as the human-recorded acceptance
  proofs.
- **Verification**: `pytest cortex_command/dashboard/tests/test_routes_smoke.py` exits 0 — pass if
  exit code = 0 and no test hangs/leaks; and `grep -cE 'partials|/sessions|status_code|404|200'
  cortex_command/dashboard/tests/test_routes_smoke.py` ≥ 1 confirming the route assertions exist.
- **Status**: [ ] pending

### Task 5: Wire the route test into `validate.yml` (fresh resolve) and into `just test`
- **Files**: `.github/workflows/validate.yml`, `justfile`
- **What**: Add a `validate.yml` step that installs the package plus `httpx`, **asserts the
  freshly-resolved Starlette is ≥1.0**, and runs the dashboard route test — so the gate is genuinely
  discriminating (the `<2.0` cap permits but does not *require* ≥1.0, so the version must be checked,
  not assumed). Also make the dashboard suite actually run under `just test`. (Spec Requirement 6.)
- **Depends on**: [4]
- **Context**: `validate.yml` today installs only `pyyaml pytest` (line ~20), so the dashboard's
  runtime deps are absent — the new step must do a constraints-free fresh install (`uv pip install .`
  or `pip install . httpx`; **no `-c`/constraints file**, which would defeat the fresh resolve), then
  run a one-line version-floor assertion (e.g. `python -c "import starlette; from
  packaging.version import Version; assert Version(starlette.__version__) >= Version('1.0'),
  starlette.__version__"`) so the job fails loudly if the resolve ever lands <1.0, then invoke
  `pytest cortex_command/dashboard/tests/test_routes_smoke.py`. The assertion is what converts the
  plan's earlier *assumption* ("a fresh resolve lands ≥1.0") into an enforced, recurring gate — it is
  the durable anti-recurrence guard. `validate.yml` runs on every push/PR and gates merges to `main`;
  this is a **pre-merge** gate (not a tag-time gate — `release.yml` runs no pytest, which is out of
  scope). The `just test` recipe runs `pytest tests/` with an explicit path that overrides
  `testpaths`, so the dashboard suite never runs today — extend the `test:` recipe to also collect
  `cortex_command/dashboard/tests/` (the local `just test` run exercises the routes on the 0.52.1 dev
  venv; only the CI step is floored at ≥1.0).
- **Verification**: (a) the CI step asserts ≥1.0 then runs the route test —
  `grep -cE 'packaging|Version\(starlette' .github/workflows/validate.yml` ≥ 1 (the version-floor
  assertion is present) AND `grep -c 'test_routes_smoke' .github/workflows/validate.yml` ≥ 1 inside a
  step that installs the package and invokes `pytest`; pass if both counts ≥ 1; and (b)
  `just test 2>&1 | grep -c 'test_routes_smoke'` ≥ 1 (the route test is actually collected/run under
  `just test`) — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 6: Record the discrimination check (test catches the regression on ≥1.0)
- **Files**: `cortex/lifecycle/harden-the-distributed-cli-against-transitive/discrimination-check.md`
- **What**: Perform and record the one-time discrimination check from Spec Requirement 4 acceptance
  (b): run Task 4's test against the *pre-rewrite* name-first `app.py` in a Starlette ≥1.0
  environment and confirm it exits **non-zero**, proving the test catches the regression rather than
  passing trivially on 0.52.1.
- **Depends on**: [4]
- **Context**: Run the check in an **isolated checkout — never mutate the live working tree** (no
  `git stash`, no in-place revert of `app.py`). Materialize the pre-Task-1 code in isolation, e.g. a
  throwaway `git worktree add` at the pre-Task-1 commit into a tmp path (or extract the pre-rewrite
  `app.py` blob via `git show <pre-Task-1-rev>:cortex_command/dashboard/app.py` into a tmp working
  copy), copy in Task 4's test, create a ≥1.0 environment there (fresh constraints-free resolve under
  the new bounds, which lands ≥1.0), and run `pytest …/test_routes_smoke.py`. Observe non-zero (the
  `TypeError: unhashable type: 'dict'` → 500 fails the 200 assertions). Record the command, the
  resolved Starlette version, the exit code, **and a quoted excerpt of the actual failing
  traceback** (so the recorded proof rests on captured output, not a bare "non-zero" assertion) in
  the notes file. Tear down the worktree/tmp copy afterward; because the live tree is never touched,
  this task cannot race or corrupt sibling tasks (e.g. Task 5's `just test`).
- **Verification**: Interactive/session-dependent: requires a Starlette ≥1.0 resolve plus an isolated
  pre-rewrite checkout, neither of which is present in the dev venv (0.52.1) nor on the post-rewrite
  branch, so no single repeatable command captures it; pass when `discrimination-check.md` records a
  non-zero exit **and a quoted `TypeError: unhashable type: 'dict'` traceback excerpt** for the
  pre-rewrite code at a named ≥1.0 starlette version.
- **Status**: [ ] pending

### Task 7: Verify a clean fresh install renders the dashboard end-to-end on both install paths
- **Files**: `cortex/lifecycle/harden-the-distributed-cli-against-transitive/fresh-install-verification.md`
- **What**: Build the wheel and install it into a clean virtualenv with **no constraints** via BOTH
  the bare `uv tool install` resolution (the canonical documented command) AND the `install.sh` path
  (`install_core.py`'s `--reinstall --refresh-package` uses the same resolution), start the app, and
  confirm `GET /` returns 200 on each; record the transcript. (Spec Requirement 7.)
- **Depends on**: [1, 2, 3]
- **Context**: `uv build --wheel`, then install the built wheel into a clean venv letting deps
  resolve fresh (no `-c`), which lands Starlette ≥1.0 under the new bounds. (Depends on [3] as well as
  [1, 2] so the wheel build does not race Task 3's `pyproject.toml`/`uv.lock` edit — every writer of
  `pyproject.toml` must be serialized before the build reads it.) Starting the app needs a project
  root with `.claude/` and `cortex/lifecycle/` and `CORTEX_REPO_ROOT` (same lifespan guard as Task 4).
  Record the resolved starlette/fastapi versions and the `GET /` → 200 result for both the bare
  `uv tool install` and the `install.sh` invocation. **Scope note**: this verifies the wheel built
  *from this branch* — a faithful proxy for the released tag, since `auto-release.yml` builds the
  release wheel from the identical `pyproject.toml` on merge to main. It does **not** install a
  pre-existing released tag (none carries the caps until this work merges and the tag is cut); the
  reach/sequencing of that release is covered in Risks, not retested here. This is the only check that
  catches *resolution* drift and proves the caps work end-to-end.
- **Verification**: Interactive/session-dependent: a clean-venv wheel install + live `GET /` over
  two install paths cannot be reduced to a single repeatable repo command; pass when
  `fresh-install-verification.md` records `GET /` → 200 with a ≥1.0 resolved starlette for both the
  bare `uv tool install` and the `install.sh` paths.
- **Status**: [ ] pending

### Task 8: File the deferred keep-current / drift-automation follow-up ticket
- **Files**: `cortex/backlog/` (new `NNN-*.md` via `cortex-create-backlog-item`)
- **What**: Create a backlog item recording that automated dependency-bump tooling (Renovate has
  native uv.lock support) and broader general-class drift protection are deliberately deferred, with
  named reopen triggers. (Spec Requirement 8.)
- **Depends on**: none
- **Context**: Use `cortex-create-backlog-item` (do not hand-author the file path/index). The body
  must name the three reopen triggers: cap-bump toil grows; a CVE lands in a capped-out major version;
  or a stale cap blocks a wanted upgrade. Reference this feature/ticket #291 as the originating
  decision. This is the conscious downscope of the general-class-drift goal stated in the spec's
  Non-Requirements.
- **Verification**: `grep -rl 'capped-out major' cortex/backlog/` returns ≥ 1 file — pass if ≥ 1
  matching backlog file exists.
- **Status**: [ ] pending

## Risks

- **Starlette cap direction (`>=0.49.1,<2.0`, adopt 1.x)** and the **general-class downscope** (bound
  the named stack + route test now; defer broader drift-automation to Task 8) are the two load-bearing
  decisions. Both were resolved with the user in the Spec interview and are stated in the spec's
  Non-Requirements — flagged here only so they remain visible at plan approval.
- **No ADR.** Research recommended ADR-0009; the spec declined it (once Task 1 lands, the
  "hard-to-reverse" ADR criterion is no longer met, and Task 4's route test is a stronger structural
  anti-revert guard than prose). A one-paragraph ADR remains a cheap add if the reviewer prefers the
  convention recorded as a standalone file.
- **Reach depends on the capped release shipping; pre-cap-pinned users have a transient broken
  window.** The metadata caps protect a user only once the *capped* release is installed. The
  existing `auto-release.yml` cuts a new tag and bumps `CLI_PIN` automatically on merge to main, so no
  plan task owns the release — but until `CLI_PIN` advances, a user pinned to the pre-cap tag
  (currently `v2.20.0`) who triggers `install_core.py`'s `--reinstall --refresh-package` auto-reinstall
  re-resolves transitives to broken Starlette ≥1.0 **with no version bump**. This plan accepts that
  transient window as the cost of not building bespoke release machinery (the spec's "Sequencing"
  Technical Constraint). If the operator wants the window closed (e.g. a forced `CLI_PIN` bump or a
  release-shipped gate before declaring done), that is a scope addition to flag at approval.
- **The recurring ≥1.0 guard is Task 5's CI step; Tasks 6 and 7 are one-time human-recorded
  acceptance.** Task 5's version-floor assertion + route test on a fresh CI resolve is the durable,
  re-executed guard. Tasks 6 (discrimination) and 7 (fresh install) are interactive/session-dependent
  one-time proofs — they will not self-verify under an unattended overnight run, so if this feature is
  routed to overnight those two need an operator-run step. They are acceptance evidence, not the
  recurrence guard (which is why the recurrence burden was moved onto Task 5's assertion).
- **Combining Spec Req 2 + Req 3 into Task 2** (both edit `[project.dependencies]`) crosses the
  spec's per-requirement boundary for implementation convenience; the per-requirement acceptance
  greps are all preserved in Task 2's Verification.

## Acceptance
A wheel built from this branch, installed into a clean no-constraints venv via both `uv tool install
git+...` and the `install.sh` path, resolves Starlette ≥1.0 and serves `GET /` → 200 for all template
routes (recorded one-time in `fresh-install-verification.md`); `validate.yml` on a fresh resolve
**asserts the resolved Starlette is ≥1.0 and then runs** the route smoke test green (the durable,
recurring discriminating gate), and the same test is collected under `just test`; the one-time
discrimination check records a non-zero exit with a captured `TypeError` traceback for the
pre-rewrite code at ≥1.0 (proving the test catches the regression); and a follow-up backlog ticket
records the deferred drift-automation decision with its three reopen triggers.
