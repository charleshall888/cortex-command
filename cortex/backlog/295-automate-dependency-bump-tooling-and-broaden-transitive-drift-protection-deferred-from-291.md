---
schema_version: "1"
uuid: 8420af8c-79e6-45bb-9d76-856abea6a442
title: "Automate dependency-bump tooling and broaden transitive-drift protection (deferred from #291)"
status: deferred
priority: low
type: feature
created: 2026-06-09
updated: 2026-06-10
---
**Why:** Feature #291 (harden-the-distributed-cli-against-transitive) hardened the distributed CLI against transitive-dependency drift by *bounding the named web stack* (`starlette`, `fastapi`, `uvicorn`, `markdown`, `psutil`) via wheel metadata plus a route-level smoke test. That scope consciously **deferred** two broader goals stated in #291's spec Non-Requirements: (a) automated dependency-bump tooling (Renovate has native `uv.lock` support; Dependabot is the alternative) so the manual caps don't rot and security updates still flow, and (b) general-class drift protection against an arbitrary *unnamed* future transitive (`jinja2`/`pyyaml`/`mcp`) breaking in a novel, non-render-path way. This ticket records that deferral so the decision and its reopen triggers are not lost.

**Role:** A durable record of the downscope, not work to start now. The named-stack bounds + the fresh-resolve route test are the current governance; this ticket exists so the deferred general-class goal is reopened deliberately on evidence rather than rediscovered after an incident. The originating decision lives in #291's spec (Non-Requirements: 'No general-class protection for an arbitrary unnamed future transitive', 'No bump-automation built now').

**Reopen triggers** (any one is sufficient to pick this up):
1. **Cap-bump toil grows** — keeping the manual caps current (floor/cap bumps as upstream releases) becomes recurring maintenance friction worth automating away.
2. **A CVE lands in a capped-out major version** — a security fix ships only in a major release that the current `<N.0` cap blocks, so the cap actively withholds a needed patch.
3. **A stale cap blocks a wanted upgrade** — a cap (or a not-yet-bumped floor) prevents adopting an upstream version the project actually wants.

**Integration:** When reopened, evaluate Renovate (native `uv.lock` support) vs. Dependabot for automated bumps, gated by #291's route smoke test (`cortex_command/dashboard/tests/test_routes_smoke.py`) so any bump that breaks the render path is caught before merge. Reconsider whether general-class protection (beyond the named web stack) earns its keep at that point, or stays deferred.

**Edges:**
- Renovate/Dependabot config must respect the existing metadata caps in `pyproject.toml` and propose floor/cap bumps rather than fighting them.
- Bump automation must be gated by the existing route smoke test running on a fresh resolve, not merge bumps blind.
- General-class protection for unbounded deps (`jinja2`/`pyyaml`/`mcp`) was explicitly weighed and dismissed in #291 as not earning its keep; reopening should re-test that conclusion against then-current evidence, not assume it flipped.

**Touch-points:** `pyproject.toml` (the named-stack bounds), `uv.lock`, a future bump-automation config (`renovate.json` or `.github/dependabot.yml`), `.github/workflows/validate.yml` (the fresh-resolve route-test gate), and `cortex_command/dashboard/tests/test_routes_smoke.py` (the recurrence guard). Originating decision: feature/ticket #291.