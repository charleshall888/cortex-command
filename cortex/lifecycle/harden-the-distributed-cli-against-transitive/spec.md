# Specification: harden-the-distributed-cli-against-transitive

## Problem Statement

A fresh `cortex` install resolves the dashboard's web-stack dependencies fresh from PyPI (a wheel
installed via `uv tool install` from a git ref does not consume `uv.lock`), and the web stack is
unbounded in `pyproject.toml`. So a fresh install today pulls **Starlette 1.2.1**, which removed the
old positional `TemplateResponse(name, context)` signature the dashboard uses — the context dict
binds to the `name` slot and reaches Jinja's hashable cache key, so every page render throws
`TypeError: unhashable type: 'dict'` → **HTTP 500**. This is live right now at the current `CLI_PIN`
(`v2.20.0`); the dev `.venv` (Starlette 0.52.1) is the only reason it looks healthy locally. This fix
makes a fresh install land a working, tested dependency set that renders the dashboard, using the
straightforward approach — use the supported API, bound the deps that drift, add a route test that
runs on a fresh resolve. It guards against recurrence of this regression and of drift in the bounded
web stack; broader protection against an arbitrary unnamed future transitive is consciously deferred
(see Non-Requirements). It benefits every user who installs or auto-reinstalls cortex.

## Phases

- **Phase 1: Fix & Bound** — rewrite the dashboard to the supported Starlette API and bound the
  drift-prone web-stack dependencies so every install path lands a working set.
- **Phase 2: Prevent recurrence** — add a route-level smoke test that runs on a fresh resolve in CI,
  verify a clean fresh install end-to-end on both install paths, and record the deferred keep-current decision.

## Requirements

1. **Rewrite the 13 `TemplateResponse` call sites to request-first form.** All 13 calls in
   `cortex_command/dashboard/app.py` (lines 268, 278, 289, 299, 308, 318, 327, 336, 345, 354, 363,
   372, 387) change from name-first `templates.TemplateResponse("name.html", {"request": request, ...})`
   to request-first `templates.TemplateResponse(request, "name.html", {...})`, which is cross-compatible
   across Starlette 0.29→1.x. **Acceptance**: `grep -c 'TemplateResponse(' cortex_command/dashboard/app.py`
   = 13 (no call added/removed); definitive correctness is gated by Requirement 4's route test returning
   200 for all template routes **when run against a Starlette ≥1.0 resolve** (where the name-first form
   500s with `TypeError: unhashable type: 'dict'`). **Phase**: Fix & Bound.

2. **Promote `starlette` to a direct, bounded dependency.** Add `starlette>=0.49.1,<2.0` to
   `pyproject.toml` `[project.dependencies]` (it is transitive-only today). Floor `>=0.49.1` bakes in the
   2025 ReDoS CVE fix; cap `<2.0` adopts the current 1.x line (Requirement 1 makes the code 1.x-safe) and
   blocks only the next major. Include a one-line comment recording *why* starlette is direct (FastAPI
   declares `starlette>=0.46.0` uncapped and will not cap it, so the app must own this bound). The durable
   anti-revert guard for this decision is Requirement 4's route test on a fresh resolve, not the comment.
   **Acceptance**: `grep -c 'starlette>=0.49.1,<2.0' pyproject.toml` = 1. **Phase**: Fix & Bound.

3. **Cap the drift-prone web stack in `pyproject.toml`.** Bound the 0.x deps where a minor bump is a
   breaking boundary and add cheap major caps to the two post-1.0 deps with a real major-break history:
   `fastapi<1.0`, `uvicorn[standard]<1.0`, `markdown<4`, and `psutil>=5.9,<8`. Leave `jinja2`, `pyyaml`,
   and `mcp` as-is (mature/low-risk; the starlette-via-mcp path is already governed by Requirement 2).
   **Acceptance**: each of these resolves to exactly one match — `grep -cE 'fastapi[^"]*<1\.0' pyproject.toml`
   = 1, `grep -cE 'uvicorn\[standard\][^"]*<1\.0' pyproject.toml` = 1, `grep -c 'markdown<4' pyproject.toml`
   = 1, `grep -c 'psutil>=5.9,<8' pyproject.toml` = 1 — and `uv lock` succeeds (exit 0) with the new bounds.
   **Phase**: Fix & Bound.

4. **Add a route-level smoke test that exercises the real `TemplateResponse` render path on a ≥1.0 resolve.**
   A new `starlette.testclient.TestClient`-based test (e.g. `cortex_command/dashboard/tests/test_routes_smoke.py`)
   asserts `GET /`, `/sessions`, `/health`, and each of the 10 `/partials/*` routes return **200**, and
   `GET /sessions/{missing-id}` returns **404** (the `status_code` path), driving each handler through
   Starlette's `TemplateResponse` (the existing `test_templates.py:66` renders Jinja directly and cannot
   catch the break). It sets up a fixture root via `CORTEX_REPO_ROOT` pointing at a tmp dir containing
   `.claude/` and `cortex/lifecycle/` — `.claude` is required by the lifespan's `RuntimeError` guard
   (`app.py:238`), not by `_resolve_user_project_root` (which returns `CORTEX_REPO_ROOT` verbatim when
   set). The test must manage the lifespan deterministically: either avoid entering the lifespan, or enter
   it via `with TestClient(app) as client:` and ensure the background poller tasks
   (`asyncio.create_task(run_polling(...))`, four uncancelled `while True` loops) and the PID file are
   torn down/isolated so the suite does not hang or leak.
   **Acceptance**: (a) `pytest cortex_command/dashboard/tests/test_routes_smoke.py` exits 0 **in an
   environment that resolves Starlette ≥1.0** (the Requirement 6 CI step provides this via a fresh resolve
   of the new bounds, which lands ≥1.0); and (b) a one-time discrimination check — the same test run
   against the *pre-rewrite* name-first code at Starlette ≥1.0 exits **non-zero** — recorded in the
   lifecycle notes to prove the test catches the regression rather than passing trivially on 0.52.1.
   **Phase**: Prevent recurrence.

5. **Declare `httpx` as a dev/test dependency.** Add `httpx` to the project's dev/test dependency group
   (`[dependency-groups].dev`) so the TestClient backend is not an incidental transitive of `mcp`.
   **Acceptance**: `grep -c 'httpx' pyproject.toml` ≥ 1. **Phase**: Prevent recurrence.

6. **Run the route smoke test on a fresh resolve in CI, and locally.** Add a step to
   `.github/workflows/validate.yml` (which today installs only `pyyaml pytest` at line 20, so the
   dashboard's runtime deps are absent) that installs the package plus `httpx` and runs the dashboard
   route test. Because that CI install resolves freshly against the new bounds, it lands Starlette ≥1.0
   and exercises the real render path — catching a render-path regression from any dep that resolves
   within the bounds. `validate.yml` runs on every push and pull request, so it gates merges to `main`,
   from which releases are auto-built; note this is a **pre-merge** gate — `release.yml` itself runs no
   test suite, so it is not a literal tag-time gate (a tag-time gate is out of scope; catching the
   regression before merge is sufficient). Also make the dashboard suite actually run under `just test`
   (today the `test:` recipe runs `pytest tests/` with an explicit path that overrides `testpaths`, so
   the dashboard suite never runs). **Acceptance**: `grep -c 'test_routes_smoke' .github/workflows/validate.yml`
   ≥ 1 inside a step that installs the package and invokes `pytest`; and `just test 2>&1 | grep -c 'test_routes_smoke'`
   ≥ 1 (the route test is actually collected/run under `just test`, not merely that the string `dashboard`
   appears in the justfile). **Phase**: Prevent recurrence.

7. **Verify a clean fresh install renders the dashboard end-to-end, on both named install paths (one-time, recorded).**
   Build the wheel and install it into a clean virtualenv with **no constraints**, via BOTH the bare
   `uv tool install` resolution (the canonical documented command) AND the `install.sh` path
   (`install_core.py`'s `--reinstall --refresh-package` uses the same `uv tool install` resolution, so it
   is covered by the same check); start the app and confirm `GET /` returns 200 on each. **Acceptance**:
   Interactive/session-dependent — a recorded clean-venv install + `GET /` → 200 transcript or note for
   both the bare `uv tool install` and `install.sh` paths exists in the lifecycle artifacts (satisfies the
   ticket's "verified end-to-end … for both install.sh and a bare uv tool install" criterion empirically).
   **Phase**: Prevent recurrence.

8. **Record the deferred keep-current decision as a follow-up ticket.** File a `cortex/backlog/NNN-*.md`
   item recording that automated dependency-bump tooling (Renovate has native uv.lock support) and broader
   general-class drift protection are deliberately deferred, with named reopen triggers: cap-bump toil
   grows; a CVE lands in a capped-out major version; or a stale cap blocks a wanted upgrade. **Acceptance**:
   a backlog file exists referencing this deferral and its triggers (`grep -rl 'capped-out major' cortex/backlog/`
   returns ≥ 1 file). **Phase**: Prevent recurrence.

## Non-Requirements

- **No lock-honoring constraints install (candidate C).** Dismissed: doubled source of truth (pyproject
  bounds + an exported constraints file), an install-time network fetch on the unattended auto-reinstall
  path (a supply-chain surface), and a `-c` flag in 3+ install commands — while buying nothing the metadata
  bounds don't already cover for the named failure class.
- **No general-class protection for an arbitrary unnamed future transitive (explicit downscope).** This
  scope hardens against (a) *this* regression and (b) drift in the *named* web stack — bounds block the
  named deps from crossing a breaking major, and Requirement 4's route test on CI's fresh resolve catches
  *render-path* breaks from any within-bounds dep. It does **not** guard against an unbounded transitive
  (`jinja2`/`pyyaml`/`mcp`) breaking in a novel, non-render-path way; that broader general-class goal from
  the ticket is consciously deferred to bump-automation (Requirement 8), per the user's simplicity decision.
  No bespoke CI resolution-canary is built.
- **No bump-automation built now (Renovate/Dependabot).** Deferred to Requirement 8's follow-up ticket.
- **No framework rewrite / lighter web stack (candidate F).** Wrong problem — this is pinning discipline,
  not framework choice; the dashboard stays on FastAPI/Starlette.
- **No caps on `jinja2`, `pyyaml`, or `mcp`.** Mature/low-risk; blanket-bounding them adds floor-bump toil
  against the frequent-release cadence for negligible risk reduction.
- **No formal ADR.** An ADR was considered (research recommended one) and declined. The strongest argument
  for it — that deleting the "redundant" direct starlette dep would silently re-open the 500 — does not
  hold *after* Requirement 1: once the call sites are request-first the code is Starlette-1.x-safe, so
  removing the cap exposes only a *future-2.0* risk, not an immediate regression. That genuinely weakens
  the ADR gate's "hard to reverse" criterion, and Requirement 4's route test on a fresh resolve is a
  stronger structural anti-revert guard than prose. The rationale is recorded in the `pyproject.toml`
  comment (Requirement 2) plus `research.md`. (If the reviewer prefers, a one-paragraph ADR is cheap to add.)

## Edge Cases

- **Bare `uv tool install` (canonical documented command)**: now lands the bounded deps via wheel metadata
  (hatchling emits `[project.dependencies]` into `requires-dist`, verified) → dashboard renders.
- **Unattended auto-reinstall** (`install_core.py`'s `uv tool install --reinstall --refresh-package`,
  which re-resolves transitives at install time): the metadata caps travel in the wheel, so the re-resolve
  stays bounded → no recurrence.
- **`<2.0` resolvability**: stays satisfiable as long as no upstream package (`fastapi`/`mcp`/`sse-starlette`)
  adds its *own* starlette upper cap below 2.0 — all three are uncapped on starlette today. A rising floor
  toward 1.x is fine (`<2.0` admits 1.x); the rejected `<1.0` would have become unsatisfiable the moment a
  floor reached ≥1.0.
- **`GET /sessions/{missing-id}`**: returns 404 via the `status_code` path, not 500 — covered by Requirement 4.
- **`httpx` missing in the test env**: would ImportError the route test — prevented by Requirement 5.
- **CI without runtime deps**: `validate.yml` installs only `pyyaml pytest` today — Requirement 6 adds the
  package-install step before running the route test.

## Changes to Existing Behavior

- **MODIFIED**: dashboard `TemplateResponse` calls move to request-first form (works on Starlette 0.29→1.x).
- **MODIFIED**: `pyproject.toml` web-stack dependencies become bounded; `starlette` becomes a direct dependency.
- **ADDED**: a route-level dashboard smoke test in the suite and on the CI path; the dashboard suite now runs in `just test`.
- **MODIFIED**: `.github/workflows/validate.yml` installs the package's runtime dependencies and runs the dashboard route test on a fresh resolve.

## Technical Constraints

- `uv tool install` from a git ref does **not** consume `uv.lock` (verified, uv 0.11.9); metadata bounds in
  `pyproject.toml` are the only governance that reaches every install path (bare command, `install.sh`,
  `install_core.py` auto-reinstall).
- FastAPI declares `starlette>=0.46.0` uncapped and refuses to add an upper bound; the direct starlette
  bound must stay a subset of FastAPI's range — any `<2.0` is compatible today.
- **Whole-stack Starlette 1.x safety**: the dashboard's only 1.0-sensitive surface is `TemplateResponse`
  (Requirement 1 fixes it). `cortex_command` imports no `starlette`/`mcp`/`sse_starlette` symbols at runtime,
  and the only MCP consumer (`plugins/cortex-overnight/server.py`) runs FastMCP over **stdio**, so the
  1.x-sensitive ASGI surface is not exercised at runtime. Requirement 7 verifies the live render path on a
  fresh ≥1.0 resolve. (The live broken install is *not* evidence the rest of the stack works on 1.x — it
  500s its whole web surface; the dead-runtime-surface argument is the real basis.)
- **CI topology**: `validate.yml` runs on push/PR and gates merges to `main`; `auto-release.yml` and
  `release.yml` run independently and execute no pytest suite (only `cli-pin-lint` + skill validators), so
  the route test is a pre-merge gate, not a literal tag-time gate.
- The route test must construct a fixture project root and tear down the lifespan's PID file + background
  poller tasks (see Requirement 4).
- **Sequencing**: the capped release must ship before it can protect users; a user pinned to a *pre-cap*
  release whose reinstall re-resolves transitives still gets unbounded deps until they move to the capped release.
- request-first form is verified cross-compatible (no DeprecationWarning on 0.52.1; 200 on 1.x).
- If any skill/hook prose is touched (none expected), the `bin/cortex-*` parity, MUST-escalation, and
  structural-over-prose conventions apply.

## Open Decisions

None. The two load-bearing decisions were resolved with the user during the interview: Starlette cap
direction → `>=0.49.1,<2.0` (adopt 1.x); general-class scope → keep it simple, bound the named stack +
route test now and defer broader drift-automation (the downscope is stated explicitly in Non-Requirements).
The route-test fixture mechanics (avoid-lifespan vs enter-and-teardown) are an implementation detail
resolvable in Plan.

## Proposed ADR

None considered. See the "No formal ADR" entry under Non-Requirements for the reasoning (the ADR gate's
"hard to reverse" criterion is not met once Requirement 1 lands, and Requirement 4's route test is the
structural anti-revert guard). A one-paragraph ADR remains a cheap option if the reviewer wants the
convention recorded as a standalone file.
