---
schema_version: "1"
uuid: 3710acc6-61ee-4484-a8f6-6c41132125cd
title: "Harden the distributed CLI against transitive-dependency drift (dashboard 500'd on a fresh install when Starlette auto-resolved to 1.x)"
status: complete
priority: medium
type: spike
created: 2026-06-08
updated: 2026-06-09
complexity: complex
criticality: high
spec: cortex/lifecycle/harden-the-distributed-cli-against-transitive/spec.md
areas: []
---
## Problem

On a fresh machine, `cortex dashboard` returned **HTTP 500** with `TypeError: unhashable type: 'dict'`, raised from Jinja2's template cache via Starlette's `TemplateResponse`. Root cause of the immediate symptom: the install resolved **Starlette 1.2.1**, which *removed* the long-deprecated `TemplateResponse(name, context)` positional signature (current form is `TemplateResponse(request, name, context)`). With the old call form, the context dict lands in the `name` slot and reaches Jinja's hashable cache key → crash. All 13 `TemplateResponse(...)` call sites in `cortex_command/dashboard/app.py` use the old form.

But the single TemplateResponse call is just the surface. The reason a *fresh install broke when an older one didn't* is structural, and it generalizes to the next transitive dependency that ships a breaking change. Three independent, verified gaps:

1. **The install path resolves dependencies fresh and ignores the lock we already maintain.** `install.sh` runs `uv tool install git+<url>@<tag>`. `uv tool install` resolves dependencies against PyPI at install time — it does **not** consume the repo's `uv.lock`. Yet `uv.lock` already pins a known-good set: `starlette 0.52.1`, `fastapi 0.133.1`, `jinja2 3.1.6`, `uvicorn 0.41.0`. So every user gets whatever PyPI serves on the day they install; a colleague who installed weeks ago is fine, a fresh install today gets Starlette 1.x.

2. **The volatile dependencies are unbounded, and the one that broke isn't even a direct dependency.** In `pyproject.toml`, `fastapi`, `uvicorn[standard]`, `jinja2`, and `markdown` have *no version specifiers*. `starlette` — the thing that actually broke — is pulled transitively through FastAPI, so there is no direct control over it today. (Contrast the disciplined `claude-agent-sdk>=0.1.46,<0.1.47` and `tiktoken<1.0`.)

3. **The dashboard tests render in a way that structurally cannot catch this.** `cortex_command/dashboard/tests/test_templates.py` renders via `templates.env.get_template("base.html").render(...)` — it talks to Jinja directly and never goes through Starlette's `TemplateResponse`. The exact API that broke is untested. There is no `TestClient`-level route test asserting `GET /` returns 200.

Per-machine, per-date, unbounded resolution + an ignored lock + tests that bypass the failing layer. Any of the three alone would have caused or permitted this.

## Goal

Investigate and decide how to make the distributed `cortex` CLI **resilient to transitive-dependency drift** across users and over time, so a fresh install reliably gets a working, tested dependency set — then apply the chosen mechanism. The decision is genuinely open; the directions below are candidates to evaluate, combine, or reject, not a prescribed plan. (A prior analysis was sketched in conversation while triaging the incident — re-test those conclusions rather than inheriting them.)

## Candidate directions to evaluate (not prescriptive)

- **Bound / declare the volatile deps in `pyproject.toml`.** Add upper bounds to the web stack and, notably, declare `starlette` as a *direct* dependency with an explicit bound so the thing that broke is directly governable. Pro: travels with package metadata, so it protects *every* install path (incl. a bare `uv tool install` that bypasses `install.sh`). Con: ranges are guesses and need maintenance; metadata `==` does not pin transitives (that is the lock's job).
- **Make the install honor the lock we already maintain.** e.g. export `uv.lock` to a constraints/requirements file at release and have `install.sh` pass `--constraints` (does it accept a URL fetched at the tag?). Pro: users get the exact transitive set that was tested; reuses existing artifacts. Con: only protects the `install.sh` path, not hand installs; second source of truth to keep in sync.
- **Add a route-level smoke test to the suite / release gate.** A `TestClient` test asserting `GET /` (and each partial) returns 200 — exercises the real `TemplateResponse` render path. Pro: catches breakage regardless of pinning strategy and would have stopped this from shipping; tiny. Con: needs to run somewhere that gates releases (note: `cortex-smoke-test` today does not touch the dashboard).
- **Automate dependency bumps** (Renovate/Dependabot or a `just`-driven `uv lock --upgrade`) so any pins/bounds don't rot and security updates still flow, gated by the smoke test.
- **Update the 13 `TemplateResponse` call sites to the current `request`-first signature** (forward+backward compatible across Starlette 0.x/1.x). Independently good hygiene; the lifecycle should decide whether this is part of the fix, in addition to or instead of pinning.
- **(Lower-confidence, list for completeness) Reduce dependency surface** — e.g. a lighter web stack for what is a local read-only HTMX status page. Likely not worth a rewrite; the issue reads as pinning discipline, not framework choice — but worth a sentence of consideration so it's explicitly weighed and dismissed.

These are not mutually exclusive; a layered answer (metadata bounds + lock-honoring install + smoke test + bump automation) is one plausible synthesis, but the lifecycle should reach its own conclusion on which layers earn their keep.

## Open questions to resolve

1. Does `uv tool install` from a git ref have any supported way to honor a `uv.lock`, or is `--constraints` / `--with-requirements` the only lever? Does `--constraints` accept a remote URL so `install.sh` can fetch the locked set pinned at the tag?
2. How tight should pinning be — upper bounds, compatible-release (`~=`), or a full transitive lock? Weigh reproducibility vs. security-update friction. Two factors favor tighter pinning here: releases are frequent and partly automated (`cortex-auto-bump-version`), and `uv tool` installs into an **isolated per-tool venv**, so the usual co-installation-conflict cost of pinning an application is absent.
3. Should `starlette` become a direct dependency so it is directly bounded, rather than floating transitively under FastAPI's loose constraint?
4. Scope: just the dashboard web stack (`fastapi`/`uvicorn`/`starlette`/`jinja2`/`markdown`), or all currently-unbounded / lower-bound-only deps (`mcp`, `psutil`, `pyyaml`)?
5. How to prevent recurrence at release time without slowing dev iteration — a route smoke test in `just test`, a release gate, or extending `cortex-smoke-test`? Where does it run?
6. Should hand installs (`uv tool install git+...` bypassing `install.sh`) be protected too? If yes, that argues for metadata-level bounds in addition to any install-time constraints.

## Acceptance criteria

- A decided dependency-resilience strategy with rationale, recorded (research doc; an ADR if it sets a cross-cutting convention for how the CLI pins/ships dependencies).
- Open questions 1 and 5 answered **empirically** (verify what `uv tool install` actually does with constraints/lock; verify the chosen recurrence-guard actually fails on the bad version), not assumed.
- A fresh install lands a dependency set that renders the dashboard — verified end-to-end (ideally for both `install.sh` and a bare `uv tool install`), not assumed.
- The specific regression cannot silently recur: some check in the test/release path exercises the real HTTP render path (`TemplateResponse`), not just Jinja templates rendered directly.
- A recorded decision on pin tightness, on whether `starlette` becomes a direct dependency, and on scope (web stack vs. all unbounded deps).
- If pins/bounds are introduced, a mechanism (or explicit decision to defer one) to keep them current without manual toil.

## Current state / context

- Triggering incident: `cortex dashboard` → HTTP 500 on a contributor's machine, 2026-06-08. Installed Starlette was 1.2.1; `uv.lock` had 0.52.1.
- The **live uv-tool install was hand-patched** (the 13 `TemplateResponse` calls → `request`-first signature) to unblock the running dashboard immediately. This patch is **temporary**: it reverts on the next `uv tool` reinstall/upgrade, which also re-resolves Starlette to 1.x — so it is not a fix, just a stopgap.
- The **canonical source was intentionally left unmodified** so this lifecycle owns the durable decision and the change is not conflated with the in-flight `investigate-and-standardize-path-resolution-for` lifecycle, which shares the same `main` working tree.
- Relevant files: `pyproject.toml` (`[project.dependencies]`), `install.sh`, `uv.lock`, `cortex_command/dashboard/app.py` (13 call sites), `cortex_command/dashboard/tests/test_templates.py` (the bypassing test), `cortex_command/overnight/smoke_test.py` (release smoke test that currently skips the dashboard). Related epic: #003 shareable-install.