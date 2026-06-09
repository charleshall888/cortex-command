# Research: Harden the distributed cortex CLI against transitive-dependency drift

> Clarified intent: make a fresh `cortex` install reliably land a working, tested dependency
> set that renders the dashboard, and ensure the Starlette `TemplateResponse` regression cannot
> silently recur — then apply the chosen mechanism. Tier: complex. Criticality: high.

**Headline (live state):** the bug is **not hypothetical — it is shipping today.** The uv-tool
install at the current `CLI_PIN` (`v2.20.0`) resolved **starlette 1.2.1 / fastapi 0.136.3**, so
`cortex dashboard` 500s for anyone on a fresh install right now. The dev `.venv` pins starlette
0.52.1, which **masks the bug** — local `just test`, local `cortex dashboard`, and any reviewer
running locally all see green. Fresh-install verification therefore cannot use the dev venv.

---

## Codebase Analysis

**The drift surface in `pyproject.toml` `[project.dependencies]`:**
```toml
"fastapi",            # NO specifier  ← drift surface
"uvicorn[standard]",  # NO specifier  ← drift surface
"jinja2",             # NO specifier
"markdown",           # NO specifier
"psutil>=5.9",        # lower-bound only
"mcp>=1.27.0",        # lower-bound only — DIRECT dep, also pulls starlette + sse-starlette
"pyyaml>=6.0",        # lower-bound only
"claude-agent-sdk>=0.1.46,<0.1.47",  # bounded (house style)
"tiktoken>=0.7.0,<1.0",              # bounded (house style)
```
`starlette` is **not** a direct dependency — it is transitive-only. The lock (`uv.lock`) currently
holds starlette 0.52.1, fastapi 0.133.1, jinja2 3.1.6, uvicorn 0.41.0, markdown 3.10.2, mcp 1.27.0,
psutil 7.2.2, pyyaml 6.0.3 — but **`uv tool install` from a git ref ignores `uv.lock`** (it's not
bundled in the wheel), so end-user installs re-resolve fresh from PyPI. Verified: hatchling faithfully
emits `[project.dependencies]` into wheel `requires-dist` (the existing `claude-agent-sdk`/`tiktoken`
caps are present in the live wheel METADATA), so **metadata bounds reach every install path**.

**The 13 `TemplateResponse` call sites** — `cortex_command/dashboard/app.py` lines 268, 278, 289,
299, 308, 318, 327, 336, 345, 354, 363, 372, 387, across 14 `@app.get` routes (`/health` returns
JSONResponse). All 13 use the **name-first form** `TemplateResponse("base.html", {"request": request, ...})`.

> ⚠️ **Contradiction resolved (recorded for Spec):** the Codebase agent labeled the name-first form
> "the modern Starlette form." That is **wrong** — name-first is the **deprecated** form, removed in
> Starlette 1.0. The Web agent, the Recurrence-Guard agent's tempdir repro, the Adversarial agent's
> *live* repro, and the ticket itself all agree: name-first is the broken-on-1.x form; `request`-first
> `TemplateResponse(request, name, context)` is the fix. Authoritative reading: **rewrite all 13 to
> request-first.** The actual failure is `TypeError: unhashable type: 'dict'` (the context dict binds
> to the `name` positional slot and reaches Jinja's hashable cache key), not a removed kwarg — test
> assertions must target a 200 vs the real TypeError-500.

**Routes a smoke test must cover** (14): `/health`, `/`, `/sessions`, `/sessions/{session_id}`, and
10 partials (`/partials/{fleet-panel, alerts-banner, session-panel, feature-cards, round-history,
escalations, activity-stream, backlog, metrics, swim-lane}`). **Test-setup cost is real:** the
`lifespan` handler (app.py ~237–248) raises `RuntimeError` unless `<root>/.claude` exists, writes a
PID file, and `asyncio.create_task(run_polling(...))` spawns a background poller; `_root()` →
`_resolve_user_project_root()` raises `CortexProjectRootError` without `CORTEX_REPO_ROOT` or a
cortex-project cwd. A route test needs a fixture root (`.claude/` + `cortex/lifecycle/`, `CORTEX_REPO_ROOT`).

**Existing tests cannot catch this:** `cortex_command/dashboard/tests/test_templates.py:64-66` renders
via `templates.env.get_template("base.html").render(...)` — raw Jinja, never through Starlette's
`TemplateResponse`. `tests/test_no_clone_install.py` only asserts `base.html` is *packaged/importable*.
No `TestClient` route test exists (grep for `TestClient`/`httpx`/`starlette.testclient` is empty).

**Test/release gating reality (the prevention gap):**
- `just test` runs `.venv/bin/pytest tests/ -q` with an explicit path → **overrides `testpaths`**, so
  the dashboard suite (`cortex_command/dashboard/tests/`) is **not run by `just test`** at all.
- `.github/workflows/validate.yml` (every push/PR) runs only `pytest tests/test_check_contract.py` +
  skill validators. **Line 20 installs only `pip install pyyaml pytest`** — no fastapi/starlette/jinja2/httpx.
- `release.yml` (on tag) runs `cli-pin-lint` + `uv build --wheel` — **zero test execution.**
- `cortex_command/overnight/smoke_test.py` (`cortex-smoke-test`) gates the overnight worker round-trip;
  it is live-model, slow, manual, and **does not touch the dashboard.** Wrong home for this guard.

**Install paths (all bypass the lock):** (a) bare `uv tool install git+...@<tag>` — **canonical**
documented command (`docs/setup.md`); (b) `install.sh` line 60 (`uv tool install ... --force`, no
constraints); (c) `plugins/cortex-overnight/install_core.py` — MCP/SessionStart auto-reinstall via
`uv tool install --reinstall --refresh-package cortex-command git+...@CLI_PIN[0]`, which **re-resolves
transitives at install time**.

**Release automation hook points:** `bin/cortex-auto-bump-version` runs in `auto-release.yml` on push
to main (computes next tag, rewrites `CLI_PIN[0]`, commits, tags); the tag retriggers `release.yml`
(`uv build --wheel`). A lock/constraints export or a gating test would hook here. Release-ritual
narrative is owned by `docs/internals/auto-update.md` (update there, link elsewhere).

---

## Web Research

**Starlette `TemplateResponse` timeline (authoritative):**
- `request`-first `TemplateResponse(request, name, context)` **added in 0.29.0** (2023-07, PR #2191) —
  deliberately non-breaking; name-first emits `DeprecationWarning`. Cross-compatible across all 0.x ≥0.29.
- name-first `TemplateResponse(name, context)` **removed in 1.0.0** (PR #3118). Changelog: *"Remove
  deprecated `TemplateResponse(name, context)` signature… Use `TemplateResponse(request, name, ...)`."*
- ⇒ **request-first works on 0.29→1.x; it needs no Starlette pin to be correct.** That is layer A.

**FastAPI ↔ Starlette coupling (root cause):** FastAPI declares **`starlette>=0.46.0` with no upper
bound** and maintainers **refuse to add one** (discussions #6211, #15193), explicitly telling consumers
to govern starlette themselves (Dependabot / pip-audit). FastAPI's "don't pin starlette" doc advice is
now stale relative to its own uncapped metadata. ⇒ **Pinning fastapi does not cap starlette.**

**App-pinning consensus:** Henry Schreiner (iscinumpy: app-vs-library) and Hynek Schlawack — *applications*
(unlike libraries) should ship a **lockfile pinning all transitives**; metadata caps are a library
anti-pattern and at best a stopgap for apps. (Tension with this repo: `uv tool install` ignores the
lock, so the lock alone doesn't reach users — see uv mechanics + tradeoffs.)

**Route smoke testing:** FastAPI/Starlette `TestClient` (httpx-backed) drives the full ASGI app
in-process; `client.get("/")` exercises the real `TemplateResponse` path. Direct `template.render()`
gives false confidence — it bypasses the layer that broke.

**Bump automation (2025-26):** Renovate has **native uv.lock support** (updates both pyproject + lock,
`lockFileMaintenance` for transitives). Dependabot reads pyproject but does not regenerate `uv.lock`
(needs a CI glue step). `just`-driven `uv lock --upgrade` is the manual alternative.

Sources: starlette release-notes / PR #2191 / PR #3118; fastapi discussions #6211, #15193, #15198;
iscinumpy app-vs-library; hynek python-app-deps; docs.astral.sh/uv; fastapi testing tutorial.

---

## Requirements & Constraints

- **Dashboard (~1800 LOC FastAPI) and CLI-wheel distribution are explicitly in scope** (project.md
  Project Boundaries; Overview → ADR-0002). A lighter web-stack rewrite is *out* ("published packages…
  out of scope"; ROI / Quality bar "ship faster, not be a project").
- **ADR-0002 (accepted)** fixes the distribution model: non-editable wheel via `uv tool install
  git+<url>@<tag>` + plugins, coupled by `CLI_PIN`. Any mechanism must operate **within** this model.
- **ADR three-criteria gate** (`cortex/adr/README.md`): a cross-cutting "how the CLI bounds/ships
  dependencies" convention is hard-to-reverse + surprising + a real trade-off ⇒ **warrants a new ADR**
  (~0009). A one-file bound tweak alone would not. New ADRs land `status: proposed`, promote at merge.
- **Solution-horizon vs Complexity/ROI (the central tension):** the 13 call sites and the *multiple
  named install surfaces* (install.sh + install_core.py + the bare documented command) are
  current-knowledge "multiple known places you can name" → the durable form (metadata bounds that cover
  all paths in one edit) is warranted. Breadth *beyond* the named web stack (capping mcp/pyyaml on the
  theory the next dep will break) is **prediction** → resist per the simplicity default.
- **Authoring constraints (CLAUDE.md):** prefer **structural enforcement** (a CI gate / test) over a
  prose MUST; the MUST-escalation policy requires an evidence artifact + effort=high attempt for any new
  MUST. Prescribe What/Why, not How. A new `bin/cortex-*` helper would need SKILL.md-to-bin parity (or a
  `.parity-exceptions.md` row) and the two-mode gate shape; a CI/install-only change likely emits no new events.
- **Doubled install surface** (`install.sh` + `install_core.py`) is itself a Solution-horizon signal
  favoring metadata bounds (travel with the wheel) over install-flag-only fixes (must be wired in each place).
- Related epic #003 "shareable-install" (complete) is about install *non-destructiveness*, not
  dependency resolution — tangential, listed only because both touch the fresh-install experience.

---

## uv Install Mechanics (Empirical)

uv version on this machine: **0.11.9**. All findings ran locally; no global tool install was mutated.

- **`uv tool install` does NOT consume `uv.lock`** (verified: `uv help tool install` never references the
  project lock in any resolution context; open feature request uv #7768). Installing `git+...@<tag>`
  re-resolves transitives fresh from PyPI. **This is the drift vector.**
- **Levers on `uv tool install`** (verbatim from `--help`): `-c/--constraints` (pins versions of packages
  already in the resolution; "equivalent to pip's `--constraint`"; env `UV_CONSTRAINT`), `--with-requirements`
  (adds packages from a file), `--with` (additive inline), `--overrides` (absolute replacement),
  `--exclude-newer <date>`, `--resolution {highest,lowest,lowest-direct}`.
- **Lock → constraints export:** `uv export --frozen --no-emit-project -o constraints.txt` produces a
  fully-pinned requirements file from `uv.lock`. Candidate "lock-honoring" pipeline:
  `uv export … -o constraints.txt` at the tag, then `uv tool install -c constraints.txt git+...@<tag>`.
- **`-c` accepts a remote https URL** — **empirically verified** (uv fetched + parsed a raw GitHub URL;
  offline probe classified it as "remote requirements file"). **Undocumented**; rests on the empirical
  probe. `--constraints`/`--with-requirements` otherwise documented as local paths only (remote support
  is open: uv #1481/#1332/#2067). Note the URL-fetch was verified on `uv pip compile`'s `-c` (shared loader);
  that `uv tool install -c <URL>` uses the same loader is inferred from identical flag semantics.
- **`--exclude-newer` / `--resolution`** are blunt alternatives — date- or floor-anchored, not exact;
  weaker than an exported constraints set. A possible belt-and-suspenders, not the primary fix.
- **Isolated per-tool venv confirmed** (docs): each `uv tool` gets its own venv ⇒ pinning the app's
  (and transitive) versions has **no co-installation-conflict cost** — pinning is essentially free here.

---

## Pinning Strategy & Dependency Volatility

**No dep in the resolved tree caps starlette below 1.x.** Verified via live METADATA — there are
**three unbounded starlette paths**: `fastapi` → `starlette>=0.46.0`; `mcp` → `starlette>=0.27` *and*
`sse-starlette>=1.6.1`; `sse-starlette` → `starlette>=0.49.1`. Only the lockfile keeps starlette at
0.52.1 in dev; a fresh resolve pulls 1.2.1. ⇒ A **separate, explicit starlette bound is required**,
and a direct constraint intersects *all three* paths (including mcp's).

**Pin-tightness for an isolated-venv, frequent-release app:**
- Exact `==` in pyproject — reject (redundant with lock; high churn against frequent releases).
- **Upper-bound / compatible-release caps — recommended.** Block the next breaking line; patch/minor
  security fixes still flow within the cap; revisit only at boundaries. Matches house style
  (`claude-agent-sdk`, `tiktoken`). Isolated venv removes the usual "don't pin an app" objection.
- Full transitive lock honored at install — necessary for *deep* reproducibility but `uv tool install`
  won't honor the lock natively (needs the export+`-c` plumbing — layer C).

**Per-dependency volatility (drift risk, high→low):**
| Dep | Versioning | Warrants bounding? |
|-----|-----------|--------------------|
| **starlette** | 0.x → just shipped 1.x; 1.0 removed public APIs; CVE-2025-54121 (fix 0.47.2), CVE-2025-62727 ReDoS (fix 0.49.1) | **YES — top priority, the dep that broke** |
| **fastapi** | 0.x; bumps starlette floor in patches; no SemVer | **YES — 0.x cap** |
| **uvicorn** | 0.x; documented 0.x breaks (`[standard]` split, 0.36 removed `setup_event_loop`) | **YES — 0.x cap** |
| **markdown** | post-1.0 (3.10.2); 3.0 was a big break; extension-API churn at minors | cheap **`<4`** major cap |
| **psutil** | post-1.0 (7.2.2); breaks only at majors (6.0 rename, 7.0 removal) w/ long deprecation | cheap **`<8`** major cap (currently `>=5.9` only) |
| **jinja2** | mature (3.1.6); security-only releases; breaks only at majors | optional `<4`; lower-bound defensible |
| **pyyaml** | mature (6.0.3); last real break was 6.0 | optional; lowest priority |
| **mcp** | 1.x but young/fast-moving; pulls starlette/sse-starlette w/ loose floors | `<2` reasonable; **but its starlette path is already governed by the direct starlette cap** |

**Promote starlette to a direct bounded dep — yes, idiomatic.** FastAPI *intends* downstream apps to
own this bound (maintainers say so). The bound must stay a subset of FastAPI's `>=0.46.0` (open-topped),
so any `>=0.49.1,<2.0` is satisfiable today. Floor at `>=0.49.1` to bake in the 2025 ReDoS CVE fix.

**Scope conclusion (OQ4):** bound the **0.x web stack (starlette, fastapi, uvicorn)** + cheap major
caps on markdown/psutil. jinja2/pyyaml/mcp caps are optional polish, not load-bearing — blanket-bounding
mature deps adds floor-bump toil against the frequent-release cadence for negligible risk reduction.

---

## Recurrence Guard (Test & Release)

**The guard:** a `TestClient` test issuing real `GET`s and asserting status, parametrized over the 14
routes (`/` and partials → 200; `/sessions/{id}` → 404 for a missing id exercises the `status_code`
path). It exercises the real `TemplateResponse` render path — the layer the existing Jinja-direct test
bypasses. **Empirically verified (tempdir + live repro):** name-first form → **500 (TypeError unhashable
dict)** on starlette 1.0/1.2.1, **200** on 0.52.1; request-first → **200** on both, no DeprecationWarning
on 0.52.1. So the guard flips green→red exactly at the 1.0 boundary, and request-first is safe to land now.

**Fixture cost (must be specced, not "tiny"):** the test needs `CORTEX_REPO_ROOT` + a fixture root with
`.claude/` and `cortex/lifecycle/`, and must handle the lifespan (PID file + background poller) — either
enter lifespan with a tmp fixture or call handlers with a constructed `Request`. **`httpx` is undeclared**
(present only transitively via mcp) — it must be added as a **dev/test dependency**, or the test
ImportErrors the day mcp drops it.

**Where it runs:** dashboard tests currently run **nowhere in CI** and not in `just test`. Two moves:
(1) wire the route test into `validate.yml` — but **`validate.yml` installs no runtime deps today
(`pip install pyyaml pytest` only)**, so the job must first `uv pip install .` (+ httpx); (2) add the
dashboard suite to `just test` for local coverage. **Do not** extend `smoke_test.py` (live-model, manual,
overnight-scoped, runs nowhere near release).

**The AC's actual requirement is stronger than a unit test.** A TestClient test against `-e .`/the dev
venv verifies the *code*, not a fresh install's *resolution*. To satisfy "a fresh install lands a
dependency set that renders the dashboard — verified end-to-end (ideally for both install.sh and a bare
`uv tool install`)", the portfolio needs a **fresh-install CI job**: build the wheel, install into a
clean venv with **no constraints**, set up the fixture root, start the app, `GET /` → 200. That is the
only test that catches *resolution* drift (and that proves the cap works). It is the AC; include it.

**The 13 call-site fix — IN ADDITION TO pinning (defense in depth).** request-first is cross-compatible,
so rewriting all 13 is safe now; it makes the code correct on both sides of 1.0 so the pin can later be
relaxed. The smoke guard is what lets you safely relax the pin. Per Solution-horizon, all 13 are "known
places" → the durable fix is rewrite-all-13 + guard, not a one-line pin alone.

**Auto-reinstall re-introduces drift for already-pinned users.** `install_core.py`'s
`--reinstall --refresh-package` re-resolves transitives at install time, so a user pinned to v2.20.0 who
triggers any auto-reinstall (or SessionStart background install) gets starlette re-resolved to latest and
the dashboard breaks **without any version bump**. ⇒ **A alone is insufficient even with no release; the
cap (B, traveling in wheel metadata) is what protects existing pins.** The `docs/setup.md` claim that a
stale pin "keeps working" is false for transitives pre-cap.

**Guard + bump automation compose:** the route guard is the precondition that makes any auto-bump (or
manual `just upgrade-deps`) safe — route it into the same CI job a bump PR triggers; never auto-merge a
dependency PR without that gate green.

---

## Tradeoffs & Alternatives

Candidate layers — **A** rewrite 13 call sites; **B** metadata bounds (starlette direct + 0.x web-stack
caps); **C** lock-honoring constraints install (`uv export` + `-c`); **D** route smoke test on a gating
path; **E** bump automation; **F** lighter web stack.

**Redundancy / complementarity:**
- **A is orthogonal** — fixes the code defect; needed regardless of pinning. A alone is a stopgap (does
  nothing for the next drift).
- **B is the primary, load-bearing layer** — bounds travel in wheel metadata, so they protect *every*
  install path (bare command, install.sh, auto-reinstall) in one edit, with zero install-command changes
  and no new network surface. House-style precedent. A direct starlette cap governs all three starlette
  paths (incl. mcp/sse-starlette).
- **C largely subsumed by B for the *named* failure class**, at higher cost: doubled source of truth
  (pyproject bounds + a checked-in constraints file), a new install-time **network fetch on the unattended
  auto-reinstall path** (a supply-chain surface — whoever controls the constraints URL controls the
  resolve), and a `-c` flag in 3+ documented install commands (forget one = the hole).
  > Correction to an earlier dismissal: "C still misses the bare command" is **false** —
  > `uv tool install -c constraints.txt git+...@<tag>` *is* the bare command plus a flag. C's real costs
  > are the doubled source of truth + the auto-reinstall network/supply-chain surface, not reach.
  C's genuine unique benefit is **whole-graph (incl. unnamed transitive) reproducibility** — the
  general-class protection the ticket explicitly asks for and B lacks. See Open Questions.
- **D complements B** (B prevents a bad version resolving; D catches what slips a cap — a patch break, or
  a cap raised too far). Trivial combined cost.
- **E services B** (keeps caps from rotting into a blocker / a CVE freeze). Value scales with cap count.
- **F is an alternative framing** — wrong problem (pinning discipline, not framework choice); dismiss.

**Recommended portfolio: A + B + D (now); defer E; dismiss C-as-primary and F; add ADR-0009** — refined
below in light of the adversarial findings (cap `<2.0`; add the fresh-install job; resolve the
general-class gap). Mapping to the tension: A/B/D are justified by **current, nameable knowledge** (13
sites, named install surfaces, a demonstrated test gap); C's deep-transitive plumbing, OQ4 breadth
(mcp/pyyaml), F, and E are **prediction** → defer/dismiss with named reopen triggers.

**Second-order effects:** (1) caps go stale and block a wanted FastAPI/Starlette upgrade — the real cost
of B; mitigate by minimal cap count + `just upgrade-deps` + the deferred-E trigger. (2) direct starlette
cap must move with FastAPI's floor — visible (resolution fails loudly), not silent. (3) ADR cost is low
and the decision is exactly what future contributors would otherwise re-derive.

---

## Adversarial Review

Live-repro-grounded challenges that reshape the recommendation:

1. **Bug mechanism corrected:** name-first is the *deprecated* form; on 1.x the dict rebinds to the
   `name` slot → `TypeError: unhashable type: 'dict'` → 500. Verified against the live uv-tool install
   (starlette 1.2.1). Spec/tests must target this, not a "removed kwarg."
2. **Bug is live now** at `CLI_PIN = v2.20.0`; the dev venv (0.52.1) masks it. Verification must use a
   clean wheel install, not the dev venv.
3. **`<1.0` is internally inconsistent with A and a resolution time-bomb.** If A makes the code 1.x-safe,
   `<1.0` throws that away (freezes on 0.x) and becomes **unsatisfiable** the moment mcp/sse-starlette
   raise their starlette floor to ≥1.0 → *every* install fails to resolve (worse than a 500). The
   dashboard's **only** 1.0-sensitive surface is `TemplateResponse` (grep-verified; MCP uses FastMCP, not
   raw starlette templating). ⇒ **Cap `>=0.49.1,<2.0`** (allow 1.x, block the next major, stay resolvable).
4. **"mcp is speculative" is incoherent** — mcp is a *direct* dep and a first-class unbounded starlette
   path; the starlette cap is load-bearing for it. Reconcile the language (cap starlette directly; that's
   what covers mcp's path — no separate mcp cap needed for *this* risk).
5. **D under-specified:** httpx undeclared (transitive via mcp); `validate.yml` installs no runtime deps;
   the route test needs fixtures (lifespan/root/poller). And a TestClient-on-dev-venv test **does not
   satisfy the AC** — only a fresh-install resolution job does.
6. **Auto-reinstall (`--reinstall --refresh-package`) re-resolves transitives** → already-pinned users
   break without a bump; the cap (B) is what protects them; the capped release must ship before the next
   auto-reinstall window (else users break on a reinstall of the pre-cap predecessor).
7. **Security:** hard caps freeze out CVE fixes released only in a capped-out major → E's reopen trigger
   must include "a CVE lands in a capped-out version," not just "drift recurs."
8. **General-class gap:** the ticket's stated goal is the *general* drift class ("the next transitive
   dependency that ships a breaking change"). B governs only named deps; dismissing C silently leaves that
   AC unmet. Resolve explicitly — recommended: a cheap **CI resolution-canary** (periodic unconstrained
   fresh resolve of the wheel + `GET /` render test) catches the next *unnamed* break in CI before a user
   hits it — cheaper/safer than C's install-time constraints — OR downscope the general-class AC in writing.

---

## Recommended Approach (synthesis)

A layered fix scoped by current knowledge, with the adversarial corrections folded in:

1. **A — Rewrite all 13 `TemplateResponse` call sites** in `dashboard/app.py` to request-first
   `TemplateResponse(request, "name.html", {...})`. Cross-compatible 0.29→1.x; fixes the actual
   `TypeError: unhashable dict` crash. (Required; orthogonal to pinning.)
2. **B — Metadata bounds in `pyproject.toml` (primary mechanism).** Promote `starlette` to a **direct**
   dependency `starlette>=0.49.1,<2.0`; add 0.x caps `fastapi<1.0`, `uvicorn<1.0`; cheap major caps
   `markdown<4`, `psutil<8`. (Reach: every install path via wheel metadata; the starlette cap governs the
   fastapi *and* mcp/sse-starlette paths.) Leave jinja2/pyyaml/mcp as-is.
3. **D — Two-part recurrence guard.** (i) A parametrized `TestClient` `GET`→200/404 route test (with a
   declared `httpx` dev dependency and a fixture root) added to `cortex_command/dashboard/tests/`, wired
   into `validate.yml` *after* a real runtime-dep install step, and into `just test`. (ii) A
   **fresh-install end-to-end CI job** (build wheel → clean venv, no constraints → start app → `GET /`
   200) — the AC's actual requirement and the only test that catches resolution drift.
4. **General-class net (open decision — see Open Questions):** recommended lightweight **CI
   resolution-canary** over C's install-time constraints.
5. **E — Defer bump automation** (Renovate has native uv support). Reopen triggers: cap-bump toil grows;
   **a CVE lands in a capped-out major**; a stale cap blocks a wanted upgrade. File a follow-up ticket.
6. **C, F — Dismiss** (C as primary, with corrected rationale; F as wrong-problem).
7. **ADR-0009** records the convention (starlette-as-direct-dep, web-stack caps via metadata, C dismissed
   + why, E deferred + triggers, the general-class decision). Clears the three-criteria gate.
8. **Sequencing:** ensure the capped release ships before the next auto-reinstall window; correct the
   `docs/setup.md` "stale pin keeps working" claim for transitives.

---

## Open Questions

1. **Starlette cap direction — `>=0.49.1,<2.0` (allow 1.x) vs `<1.0` (stay 0.x).**
   *Resolved (recommendation): `>=0.49.1,<2.0`.* Rationale: A makes the code 1.x-safe; `<1.0` discards
   A's value and is a resolution time-bomb as mcp/sse-starlette floors rise; the dashboard's only
   1.0-sensitive surface is `TemplateResponse` (adversarial grep-verified); the live stack already runs
   starlette 1.2.1 + fastapi 0.136.3 + mcp with only the dashboard breaking. **To be confirmed by the
   user in the Spec interview** (it's the load-bearing design choice).

2. **General-class protection — CI resolution-canary vs explicit downscope to deferred-E.**
   *Deferred to Spec.* The ticket's framing ("the next transitive dependency") asks for general-class
   protection that B (named-deps deny-list) does not provide. Options: (a) add a periodic
   unconstrained-resolution canary in CI that renders `GET /` (recommended — cheap, safe, catches the next
   *unnamed* break before users), or (b) record that general-class is deferred to bump-automation (E) with
   a named trigger. This is a genuine scope/effort call for the user — resolve in the Spec §4 interview.

3. **Scope breadth (OQ4) — which deps get bounds.**
   *Resolved (recommendation): 0.x web stack (starlette/fastapi/uvicorn) + cheap major caps markdown<4,
   psutil<8.* jinja2/pyyaml/mcp caps are optional polish, not load-bearing; the starlette-via-mcp risk is
   already covered by the direct starlette cap. Blanket-bounding mature deps adds toil for negligible gain.

4. **Does the lock-honoring constraints install (C) earn its keep?**
   *Resolved: dismiss as the primary mechanism* (B is cheaper, has universal reach, no doubled source of
   truth, no auto-reinstall network/supply-chain surface). Its unique general-class value is better met by
   OQ2's resolution-canary. (Corrected: the earlier "C misses the bare command" rationale was wrong — `-c`
   works on the bare command; the real costs are doubled source of truth + the unattended-install network/
   supply-chain surface.)

5. **D's home and fixture design.**
   *Resolved (recommendation): route TestClient test in `cortex_command/dashboard/tests/` + `httpx` as a
   declared dev dep + `validate.yml` gains a runtime-dep install step + the suite added to `just test`; a
   separate fresh-install end-to-end CI job for the AC.* Exact fixture mechanics (enter-lifespan-with-tmp
   vs construct `Request`) are an implementation detail for Plan.

6. **Full-stack compatibility on starlette 1.x.**
   *Resolved empirically:* the live install already runs starlette 1.2.1 + fastapi 0.136.3 + mcp/sse-starlette
   and only the dashboard `TemplateResponse` broke ⇒ the rest of the stack works on 1.x. Implementation
   should re-verify post-A that every route returns 200 on 1.2.1 in the fresh-install job.

7. **ADR vs no-ADR.**
   *Resolved (recommendation): write ADR-0009* — a cross-cutting pin/ship convention clears the
   three-criteria gate (the AC already anticipates "an ADR if it sets a cross-cutting convention").
