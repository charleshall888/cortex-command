# Review: harden-the-distributed-cli-against-transitive

## Stage 1: Spec Compliance

### Requirement 1: Rewrite the 13 `TemplateResponse` call sites to request-first form
- **Expected**: All 13 calls in `cortex_command/dashboard/app.py` move from name-first `templates.TemplateResponse("name.html", {"request": request, ...})` to request-first `templates.TemplateResponse(request, "name.html", {...})`. Acceptance: `grep -c 'TemplateResponse(' app.py` = 13; correctness gated by Req 4's route test at Starlette ≥1.0.
- **Actual**: `grep -c 'TemplateResponse(' cortex_command/dashboard/app.py` = 13. Every call site (e.g. lines 268, 279, 291, 302, 312, 323, 333, 343, 353, 363, 373, 383, 399) passes `request` as the first positional argument before the template name. The `session_detail` handler retains its `status_code=` kwarg (line 295). Line numbers shifted modestly from the spec's stated pre-rewrite lines because the rewrite expanded the calls to multi-line form — non-material; no call added or removed.
- **Verdict**: PASS
- **Notes**: Request-first is cross-compatible 0.29→1.x. The dev-venv route test (Starlette 0.52.1) passes 15/15; the ≥1.0 discrimination is proven under Req 4.

### Requirement 2: Promote `starlette` to a direct, bounded dependency
- **Expected**: Add `starlette>=0.49.1,<2.0` to `[project.dependencies]` with a one-line comment recording why starlette is direct. Acceptance: `grep -c 'starlette>=0.49.1,<2.0' pyproject.toml` = 1.
- **Actual**: `grep -c 'starlette>=0.49.1,<2.0' pyproject.toml` = 1 (line 19). The preceding comment (line 18) records the rationale: "FastAPI depends on starlette with no upper bound and its maintainers refuse to add one (discussions #6211/#15193), so the app must own this cap; it also governs the mcp/sse-starlette starlette paths." `uv.lock` carries it as a direct dependency: `cortex-command`'s `requires-dist` lists `{ name = "starlette", specifier = ">=0.49.1,<2.0" }` (line 253) and starlette appears as a first-class dependency of the package (line 232).
- **Verdict**: PASS
- **Notes**: Anchored quoted bound present in `[project.dependencies]`; uv.lock consistent.

### Requirement 3: Cap the drift-prone web stack
- **Expected**: `fastapi<1.0`, `uvicorn[standard]<1.0`, `markdown<4`, `psutil>=5.9,<8`; leave jinja2/pyyaml/mcp as-is; `uv lock` succeeds. Acceptance: each cap greps to exactly 1.
- **Actual**: `grep -cE 'fastapi[^"]*<1\.0'` = 1, `grep -cE 'uvicorn\[standard\][^"]*<1\.0'` = 1, `grep -c 'markdown<4'` = 1, `grep -c 'psutil>=5.9,<8'` = 1 — all four match exactly once (pyproject lines 11, 12, 14, 15). `jinja2`, `pyyaml`, `mcp` left bounded only where they already were (jinja2 unbounded, pyyaml `>=6.0`, mcp `>=1.27.0`) — matching the spec. `uv.lock` regenerated with these caps in `requires-dist` (lines 247, 249, 251, 254); the recorded fresh-install proof shows `uv build --wheel` succeeded (exit 0) emitting these exact bounds into the wheel metadata, implying the lock regen succeeded.
- **Verdict**: PASS

### Requirement 4: Add a route-level smoke test exercising the real `TemplateResponse` render path on a ≥1.0 resolve
- **Expected**: A `starlette.testclient.TestClient` test asserting 200 for `/`, `/sessions`, `/health`, and all 10 `/partials/*`, and 404 for a missing session; fixture root via `CORTEX_REPO_ROOT` with `.claude/` + `cortex/lifecycle/`; deterministic lifespan management. Acceptance: (a) exits 0 at Starlette ≥1.0; (b) a one-time discrimination check against pre-rewrite code at ≥1.0 exits non-zero, recorded in lifecycle notes.
- **Actual**: `cortex_command/dashboard/tests/test_routes_smoke.py` exists. It parametrizes `test_route_renders_200` over `PAGE_ROUTES` (`/`, `/sessions`, `/health`) + the 10 `PARTIAL_ROUTES` and asserts 200; `test_missing_session_returns_404` asserts 404 on a missing session id (the `status_code` path); `test_all_ten_partial_routes_covered` guards the partial inventory at exactly 10. The fixture builds a tmp root with `.claude/` and `cortex/lifecycle/` and sets `CORTEX_REPO_ROOT`. Lifespan is managed deterministically by NOT entering it (`TestClient(app)` without the `with` context), so no background poller tasks or PID file are created — the documented avoid-lifespan choice from the spec. The test drives the real ASGI + `TemplateResponse` layer (it imports the app and issues HTTP `client.get(...)`), distinct from `test_templates.py`'s direct-Jinja render. (a) The test passes 15/15 on the dev venv; the recorded fresh-install proof confirms CI's fresh resolve lands Starlette 1.2.1 (≥1.0). (b) `discrimination-check.md` records the one-time check: against the pre-rewrite name-first `app.py` (ref `4af68ab4`, byte-identical to baseline) at a fresh Starlette **1.2.1** resolve, the test exits **non-zero** (`13 failed, 2 passed`), failing with `TypeError: ... unhashable type: 'dict'` in Jinja's cache-key path. The note documents a non-material deviation (TestClient `raise_server_exceptions=True` re-raises the TypeError rather than returning a 500) but the discrimination signal — non-zero exit with the specified error — is exactly as required, and the isolation method (throwaway worktree + venv, live tree untouched) is sound.
- **Verdict**: PASS
- **Notes**: Meaningful route test (drives real render path); discrimination proof is rigorous and addresses the import-shadowing trap explicitly.

### Requirement 5: Declare `httpx` as a dev/test dependency
- **Expected**: Add `httpx` to `[dependency-groups].dev`. Acceptance: `grep -c 'httpx' pyproject.toml` ≥ 1.
- **Actual**: `grep -c 'httpx' pyproject.toml` = 2 (a comment line + the `"httpx"` entry at line 109 inside `[dependency-groups].dev`). `uv.lock` lists httpx in `[package.dev-dependencies].dev` (line 239) and `[package.metadata.requires-dev].dev` (line 260), so it is no longer an incidental transitive of mcp.
- **Verdict**: PASS

### Requirement 6: Run the route smoke test on a fresh resolve in CI, and locally
- **Expected**: A `validate.yml` step installs the package + httpx and runs the route test on a fresh resolve; assert Starlette ≥1.0; `just test` actually collects/runs `test_routes_smoke`. Acceptance: `grep -c 'test_routes_smoke' .github/workflows/validate.yml` ≥ 1 inside a package-install + pytest step; `just test 2>&1 | grep -c 'test_routes_smoke'` ≥ 1.
- **Actual**: `validate.yml` adds the step "Dashboard route smoke test (fresh resolve, Starlette floored at >=1.0)" (lines 41–54): `pip install . httpx packaging` (constraints-free fresh resolve), then a `packaging.version` assertion that `starlette.__version__ >= 1.0` (line 53), then `pytest cortex_command/dashboard/tests/test_routes_smoke.py` (line 54). `grep -c 'test_routes_smoke' validate.yml` = 1, inside the install+pytest step. The justfile `test:` recipe (lines 521–523) emits a `--collect-only` listing of the dashboard suite and runs `tests-dashboard` via `pytest cortex_command/dashboard/tests/`. Verified collection: `pytest cortex_command/dashboard/tests/ --collect-only` yields 15 `test_routes_smoke` node IDs, so `just test 2>&1 | grep -c 'test_routes_smoke'` ≥ 1. The previous `pytest tests/`-only override is gone — the dashboard suite now runs.
- **Verdict**: PASS
- **Notes**: The explicit ≥1.0 assertion guards against a non-discriminating run where `<2.0` admits a <1.0 resolve — a thoughtful robustness addition beyond the literal acceptance.

### Requirement 7: Verify a clean fresh install renders the dashboard end-to-end on both named install paths (recorded)
- **Expected**: Build the wheel, install into a clean no-constraints venv via the bare `uv tool install` AND the `install.sh` path; confirm `GET /` → 200 on each; recorded in lifecycle artifacts.
- **Actual**: `fresh-install-verification.md` records: wheel built (`uv build --wheel`, exit 0) with `requires-dist` carrying all bounds; Path A (bare `uv tool install --force` into an isolated `UV_TOOL_DIR`) resolved Starlette **1.2.1**, fastapi 0.136.3, uvicorn 0.49.0, and `GET /` → **200** (plus `/health` → 200); Path B (`install.sh`/`install_core.py`) covered by a documented install-path-equivalence argument (both run bare `uv tool install` from a git ref, no constraints; `--reinstall --refresh-package` only force re-resolve) AND concretely re-exercised via a clean throwaway venv `pip install` of the same wheel → same resolved set (Starlette 1.2.1), `GET /` → 200. The lifespan `.claude/` guard was satisfied via a fixture `CORTEX_REPO_ROOT`. Developer's global tool install confirmed intact afterward.
- **Verdict**: PASS
- **Notes**: The proof scopes itself honestly — it verifies the wheel built from this branch (a faithful proxy for the released tag, since auto-release builds from the same pyproject), not a pre-existing released tag (none carries the caps until merge). Both paths land ≥1.0 and render.

### Requirement 8: Record the deferred keep-current decision as a follow-up ticket
- **Expected**: A `cortex/backlog/NNN-*.md` recording deferred bump-automation + broader general-class drift protection, with named reopen triggers. Acceptance: `grep -rl 'capped-out major' cortex/backlog/` ≥ 1 file.
- **Actual**: `cortex/backlog/295-automate-dependency-bump-tooling-and-broaden-transitive-drift-protection-deferred-from-291.md` exists; `grep -rl 'capped-out major' cortex/backlog/` returns it (1 file). It records both deferred goals (Renovate/Dependabot bump automation; general-class protection for unbounded jinja2/pyyaml/mcp) and three named reopen triggers: (1) cap-bump toil grows, (2) a CVE lands in a capped-out major version, (3) a stale cap blocks a wanted upgrade. Body follows the Why/Role/Integration/Edges/Touch-points template; status `backlog`, priority `low`.
- **Verdict**: PASS

## Requirements Drift
**State**: detected
**Findings**:
- The implementation establishes a cross-cutting dependency-governance convention — promote a transitive (`starlette`) to a direct, capped dependency when an upstream parent (FastAPI) leaves it uncapped, and adopt upper-bound caps on the drift-prone web stack (`<1.0`/`<2.0`/`<4`/`<8`) so the bounds travel in wheel `requires-dist` to every install path. `cortex/requirements/project.md` "Architectural Constraints" records other cross-cutting conventions (status vocabulary, parity, install-state contract) but has no entry for dependency pinning/governance; this decision is currently captured only in the spec, a pyproject comment, and the route test, not in the requirements doc. The spec consciously declined a formal ADR; this is flagged as an observation only and does not affect the verdict.
**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: Architectural Constraints
**Content**:
```
- **Distributed-CLI dependency bounds**: `uv tool install` from a git ref ignores `uv.lock`, so `pyproject.toml` `[project.dependencies]` bounds (which travel in the wheel's `requires-dist`) are the only governance reaching every install path. Cap the drift-prone web stack at the next breaking major; promote a transitive to a direct, capped dependency when an uncapped upstream parent (e.g. FastAPI's uncapped `starlette`) would otherwise let it drift across a breaking boundary. The fresh-resolve route test (`cortex_command/dashboard/tests/test_routes_smoke.py`, run in `validate.yml`) is the structural anti-revert guard.
```

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. New test file follows the `test_*.py` convention and lives in the package's `tests/` dir alongside `test_templates.py`; fixtures (`fixture_root`, `client`) and route constants (`PAGE_ROUTES`, `PARTIAL_ROUTES`, `ALL_OK_ROUTES`) are clearly named. The pyproject comment and proof-note filenames match repository conventions.
- **Error handling**: Appropriate. The route test correctly exercises the `status_code=404` path for a missing session via `session_detail`'s existing branch; the lifespan `RuntimeError` guard is satisfied by the fixture rather than bypassed. The avoid-lifespan fixture choice is well-justified in the module docstring (the PID path is a module-level singleton captured at import time, so a per-test `XDG_CACHE_HOME` cannot redirect it cleanly) — a correct read of the code rather than a shortcut.
- **Test coverage**: The plan's verification steps are satisfied. The route test is meaningful, not trivial: it drives each handler through the real ASGI + `TemplateResponse` layer (distinct from `test_templates.py`'s direct-Jinja render), and the recorded discrimination check empirically proves it fails (`13 failed`) against pre-rewrite code at Starlette 1.2.1 with the exact specified `TypeError`. The CI step adds an explicit ≥1.0 assertion so a within-`<2.0` resolve that landed <1.0 fails loudly rather than passing non-discriminatingly. `test_templates.py`'s 11 rewritten tests (now partial-render) and the route test both pass on the dev venv (19 + 15).
- **Pattern consistency**: `test_templates.py`'s partial-render approach correctly mirrors the post-redesign reality (base.html ships empty shells; panels load via `hx-get="/partials/..."`), and its `_fake_request` stub matches the request-first context contract the app now uses. The `app.py` rewrite is uniform across all 13 call sites (request as first positional, `status_code` preserved where present), consistent with the supported Starlette API. No skill/hook prose touched, so the parity/MUST-escalation/structural conventions do not apply here.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
