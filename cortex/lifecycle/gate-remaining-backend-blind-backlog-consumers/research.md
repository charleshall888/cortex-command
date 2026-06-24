# Research: Gate the three remaining backend-blind backlog consumers (dashboard panel, discovery clarify §3, discovery decompose §7)

## Epic Reference

Child of epic **#315** ("Optional backlog plugin + configurable backend"), follow-on to **#317** (config-driven backend resolver). #315's body is empty; the authoritative scope lives in `cortex/requirements/backlog.md` and `cortex/adr/0016-configurable-backlog-backend-and-llm-as-adapter.md`. #321 applies #315's skill-layer routing principle to three operations the epic left backend-blind; it is hardening, not a new capability. **Not** #318 (external create/write-back arm, `wontfix`) — #321 *suppresses* wrong local behavior and is independently relevant for the shipped `none` backend.

Scope = **three reachable consumers**. morning-review §4 was **dropped** by operator decision (it is transitively unreachable under a non-local backend; gating it is dead-path ceremony). `review.md:12` requirements guard is OUT OF SCOPE (unrelated `cortex/requirements/` nit).

## Codebase Analysis

**Edit sites (canonical only — `plugins/cortex-core/...` mirrors regenerate via `just build-plugin`; commit canonical + mirror together):**

1. **Dashboard** (wheel code, no mirror) — `cortex_command/dashboard/poller.py` `_poll_slow` (lines 351–371), `DashboardState` dataclass (lines 61–117), `cortex_command/dashboard/templates/backlog_panel.html`. Pure readers `cortex_command/dashboard/data.py:parse_backlog_counts` (969) / `parse_backlog_titles` (1026) **stay untouched** (regression anchor + purity).
2. **discovery clarify §3** — `skills/discovery/references/clarify.md:19–21` ("### 3. Check Existing Backlog Coverage" — scans `cortex/backlog/[0-9]*-*.md` before any backend resolve).
3. **discovery decompose §7** — `skills/discovery/references/decompose.md:187–189` ("### 7. Update Index" — runs `cortex-generate-backlog-index` unconditionally after the gated §5 create-routing).

**Reuse helpers (no new machinery):**
- Prose consumers → the `cortex-read-backlog-backend` binstub (`bin/cortex-read-backlog-backend`; console entry `pyproject.toml:59` → `cortex_command.lifecycle.backlog_backend_cli:main`). Argless (optional positional `repo_root`, honors `$CORTEX_COMMAND_ROOT`). Prints backend + newline, exits 0. **Fails OPEN** (degenerate input → prints `cortex-backlog`).
- Python consumers (dashboard) → `resolve_backlog_backend(repo_root)` at `cortex_command/lifecycle_config.py:97`. Returns a **string, never None, never raises**; every degenerate input → `"cortex-backlog"`. Possible values: `cortex-backlog` | `none` | external name (`github-issues`, `jira`, …). Reads `repo_root / "cortex/lifecycle.config.md"` (note: `cortex/lifecycle.config.md`, **not** under `cortex/lifecycle/`).

**Verbatim gate idiom to mirror** (decompose §5, `decompose.md:138`, a *create* path → three-arm):
> **Backend routing (resolve once before creating tickets).** … resolve the active backend once with `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0). Route on the value:
> - **`cortex-backlog`** (the default arm) → proceed exactly as today …
> - **`none`** → do not call the create CLI. Instead, surface … a one-line advisory … No writes land in `cortex/backlog/`.
> - **any other value** (an external tracker) → … best-effort … using the config `backlog.instructions` …

**Closest model for the new gates** is **dev Step 3** (`skills/dev/SKILL.md:135`), a *read/index* path that uses a **two-arm fold** (`cortex-backlog` proceeds; `none` OR external both stand down): "the local index does not represent the active backlog, so skip … with a one-line advisory … Do not run `cortex-generate-backlog-index` …". This two-arm shape is the right model for clarify §3 and decompose §7.

**Lint/constraint gates (all satisfied by the planned edits):**
- **L201 bare-Python prohibition** — use the `cortex-read-backlog-backend` console script (the prescribed compliant form); no bare imports.
- **cortex-check-contract (E101/E103)** — scans `skills/**/*.md`. `cortex-read-backlog-backend` has **no required flags**; wrap inline mentions in the double-backtick form `` `cortex-read-backlog-backend` `` (mirrors existing §5 idiom). `cortex-generate-backlog-index` is already used unwrapped in §7. No trigger.
- **SP001/SP002 skill-path** — console-script on `$PATH` + plain relative scan patterns; no `${CLAUDE_SKILL_DIR}` propagation introduced. No risk.
- **L1 surface ratchet** — measures frontmatter only. Reference-file + Python edits do **not** touch it.

## Dashboard Subsystem

**Gate site: `_poll_slow` in the poller** (not `data.py`). `_poll_slow(state, root)` already receives `root` (the project root) — exactly what `resolve_backlog_backend` wants. Poll cadence is **30s** (the slowest of four loops), so resolving the backend every cycle is negligible (one small file read) and picks up a mid-session config edit within 30s — no caching warranted. Concrete shape:

```python
backend = resolve_backlog_backend(root)
state.backlog_backend = backend
if backend == "cortex-backlog":
    state.backlog_counts = parse_backlog_counts(backlog_dir)
    state.backlog_titles = parse_backlog_titles(backlog_dir)
else:
    state.backlog_counts = {}
    state.backlog_titles = {}
```

Use the binary `== "cortex-backlog"` test (matches the convention at `cli_handler.py:1978`, `backlog_backend_cli.py:60` — everything non-`cortex-backlog` stands down).

**Placeholder mechanism: new `DashboardState` field** `backlog_backend: str = "cortex-backlog"` (added near `backlog_counts`/`backlog_titles` at poller.py:89–90; default = local so existing instantiations/tests stay byte-identical). Rendering passes the `state` object **directly into Jinja** (server-side Jinja2 + HTMX partials via `GET /partials/backlog`, `app.py:370–377`) — **no JSON/websocket serializer to update**, so a new field is free to plumb. Template branches `{% if state.backlog_backend != 'cortex-backlog' %}…placeholder…{% elif state.backlog_counts %}…{% else %}empty{% endif %}`. Storing the raw string (not a bool) lets the placeholder name the actual backend ("tracked externally via `<backend>`" vs "disabled" for `none`). This separates the **three states** the panel must now express (disabled/external · empty · populated) — avoiding the conflation of "disabled" with "empty" (a sentinel-in-`backlog_counts` approach would break the `.values() | sum` arithmetic at template line 22).

**Cross-panel effect (must be called out in spec):** `state.backlog_titles` is also consumed by `feature_cards.html:47` and `escalations_panel.html:19` — **both already fall back to the raw slug** when a title is absent (`state.backlog_titles.get(slug, slug)`). Clearing `backlog_titles` under a non-local backend is the *correct* behavior (titles came from the now-non-authoritative local dir); those panels degrade to slugs gracefully. Deliberate, not a surprise.

**Per-request/per-poll resolution invariant (R3c):** `app.py` forbids module-level root capture (`_root()` resolves per-request). The poller resolution is per-poll, consistent with this.

## Web Research

External prior art is thin (this is fundamentally an internal-convention move) but confirms the design vocabulary and one key anti-pattern:

- **Config-authoritative selection over capability detection** — deepagents `FilesystemMiddleware` and `get-shit-done` issue #528 both branch on a *declared* config value (default `"local"` for zero breaking changes), not on detecting an installed integration. Matches #321's resolver-based routing and confirms gating the dashboard the same way is a faithful application of the principle, not a divergence.
- **Anti-pattern this change avoids: conflating "not configured / no source" with "zero data."** Google Site Kit issue #4086 showed a widget rendering a provisional state whenever the API returned all zeros (which could also mean "genuinely zero"). Their fix: branch render state on a *diagnostic identity check*, not on an empty reading. **Lesson: branch the panel on the resolved backend identity, never on zero/empty counts** — exactly why the new `backlog_backend` field (not a `backlog_counts == {}` inference) is the right placeholder mechanism.
- **Read/write asymmetry** — deepagents (`files_update=None` for persistent backends) and GSD-528 (only managed paths affected; source ops stay local) both confirm external backends are treated as opaque on the read side: route by config, don't reach into the external store on every read. Validates "read paths stand down (skip + advisory), don't query the tracker."
- **Null-object pattern** for the `none` backend — valid only if the no-op preserves the consumer's contract; GSD-528 names the failure mode of a no-op left pointed at a store that no longer exists (i.e. showing stale local counts). Reinforces "skip the local read entirely," not "read an empty/stale dir."

No external standard prescribes *which* consumers to gate (an epic-315 scope decision) or the skip-plus-advisory convention — those remain internal conventions to define and document.

## Requirements & Constraints

**`cortex/requirements/backlog.md` — Consumer backend routing (skill layer), lines 48–58.** Acceptance criteria: `cortex-backlog` → CLI unchanged; external → LLM best-effort; `none` → skip. The named consumer set (line 51 / Dependencies line 110) is exactly `discovery, lifecycle, refine, dev, morning-review` (+ `overnight`, cortex-backlog-only). **The dashboard panel is enumerated nowhere; clarify §3 / decompose §7 are sub-operations inside `discovery` (a named consumer) that weren't individually called out.** → Gating these is a **consistent extension** of the same skill-layer principle (ADR-0016 line 100: "routing lives at the skill/consumer layer"), not a literal-requirement match and not a divergence from #315 scope.

**`none` backend behavior, lines 81–89:** "Incidental consumers … skip with a one-line advisory." → the route for all three #321 paths under `none`.

**External best-effort, lines 60–68 (priority *should*):** scoped to **exactly two paths — Create (discovery) and Round-trip (lifecycle/morning-review write-back).** Coverage-scan reads and index regen are neither. → On external, these three paths **stand down (skip + advisory), do not query the tracker** — matching dev Step 3 and the ticket's own Integration note.

**Backward-compat, line 94:** "Existing local-backlog repos see no behavior change." → the byte-identical `cortex-backlog`-arm regression anchor.

**ADR-0016** (`status: proposed`): consumers route on the resolved value at the skill layer; the `cortex-*` CLIs gain no backend awareness; routing "fails toward today's local behavior"; rejected per-tool adapters + plugin-install introspection. The dashboard is the documented exception — it lives in the *wheel*, so it resolves via the Python `resolve_backlog_backend`, not the console-script. Consumers **back-point to ADR-0016** rather than restating rationale; new gating prose should `→ ADR-0016`. (Proposed-not-accepted: the ADR consumer rule says a skill MUST NOT auto-treat a proposed ADR as binding without human confirmation; #321 is human-in-loop, so satisfied.)

**Terminology:** the local backend is `cortex-backlog` in all config values, prose, advisories, and placeholders — **never `local`** (`backlog.md:105`).

**Design principles:** "no new machinery" / "complexity must earn its place" → reuse the existing resolver + binstub + three-/two-arm pattern. "Prescribe What and Why, not How" → prose-driven branch, no typed adapter. "Solution horizon" → #321 is a planned child of #315/#317 (a scoped phase, not a stop-gap).

## Tradeoffs & Alternatives

**Dashboard gate site → poller `_poll_slow` (Alt A).** Only option that keeps both the regression anchor and `data.py` purity: the default arm wraps two existing lines in `if backend == "cortex-backlog":`. Gating in `data.py` (Alt B) would force a `repo_root` signature change and break `test_data.py`'s direct-call contract; gating at the route/render layer (Alt C) leaves the poller scanning `cortex/backlog/` every 30s and re-resolves config on every (frequent) HTMX partial poll.

**Dashboard placeholder → new state field (Alt A).** A single `backlog_backend` string is self-documenting, testable, and gives a *correct* message; a sentinel in `backlog_counts` (Alt B) breaks the sum arithmetic; a separate `bool` (Alt C) needs two coordinated fields to express one state.

**decompose §7 → move `cortex-generate-backlog-index` INSIDE §5's `cortex-backlog` arm (Alt A).** Index regen is intrinsically a `cortex-backlog`-only operation (the `none`/external arms never write to `cortex/backlog/`, so there's no local index to regenerate). Reuses §5's already-resolved value (no re-resolution), and makes the gate **structural (control-flow placement)** rather than prose-only — aligning with the repo's "prefer structural separation over prose-only enforcement for sequential gates." A separate §7 check (Alt B) re-resolves and creates a second drift-prone routing site.

**clarify §3 → two-arm: `none` AND external both skip-with-advisory (Alt A).** clarify §3 is a **read/coverage** path whose only output feeds the §4 "Novelty" dimension; a skipped scan defaults novelty to "no overlap detected" — the safe direction (it never *blocks* discovery). The three-arm shape (Alt B) is correct for *writes* (decompose §5 must not lose authored tickets, so it tries external best-effort) but wrong for a *read* (it would query the tracker, contradicting the operator's stand-down decision and re-introducing per-tracker behavior #315 scopes out). The right consistency is **semantic** (both gate on the resolved backend), not structural arm-count. **Document the intentional two-arm-vs-three-arm divergence in a one-line note** so a future reader doesn't "fix" the asymmetry.

**Cross-cutting → reuse the two existing channels, do NOT build a new shared helper.** Python (dashboard) → in-process `resolve_backlog_backend(root)` (like `cli_handler.py:1975`); prose (clarify/decompose) → the `cortex-read-backlog-backend` binstub (like decompose §5). Both fail **open** — the correct direction here (a consumer that can't resolve config degrades to local behavior). These two channels are **deliberately kept distinct** (`cli_handler.py:1961–1973` documents that the fail-open binstub must NOT be DRY-merged with the fail-closed overnight guard); a new fourth abstraction would have to re-make that settled decision.

## Testing Strategy

**Three test surfaces:**

1. **Dashboard gating (poller layer) + byte-identical anchor.** Template: `TestParseBacklogCounts` in `cortex_command/dashboard/tests/test_data.py:199` (`tempfile` dir + `_write_backlog_file` + exact `assertEqual(result, {...})`). New tests: drive the gated `_poll_slow`/state with a `cortex/lifecycle.config.md` set to `none`/external **plus leftover backlog files**, assert `state.backlog_counts == {}` / `backlog_titles == {}` and `state.backlog_backend` is set. **Byte-identical anchor:** golden-compare the gated `cortex-backlog` path against the un-gated `parse_backlog_counts(dir)` on the identical fixture — equal dict proves no behavior change (no snapshot file needed). Add `backlog_backend` default to `TestDashboardStateDefaults.test_defaults` (test_poller.py:23). Keep all 8 `test_data.py` cases green (they prove the pure reader is unchanged). **Skip-proof technique** (from `test_overnight_backlog_backend_guard.py`): patch/spy `parse_backlog_counts` to raise if called, assert it is never reached under `none`/external.
2. **Dashboard placeholder render.** `test_templates.py` renders templates directly (`templates.env.get_template(...).render(...)`) and has **no** backlog-panel test yet — cleanest home for a direct render: render `backlog_panel.html` with `state.backlog_backend != "cortex-backlog"`, assert placeholder text appears and stale counts do **not**. `test_routes_smoke.py` (`/partials/backlog`, fixture `CORTEX_REPO_ROOT`) does **not** enter the lifespan (poller never runs → `backlog_counts` stays default `{}`), so use it to assert the placeholder branch renders given post-gate empty state and still returns 200; the hard-coded `test_all_ten_partial_routes_covered` count stays 10 (no new route).
3. **Discovery prose-edit structural tests (NOT drift-gate-only).** The dual-source gate only checks mirror equality, not semantics. Templates: `test_decompose_rules.py` (parses `decompose.md` into `{heading: body}`, asserts tokens within their section, supports negative assertions) and `test_critical_review_gate_nonlocal_failsafe.py` (reads a skill `.md`, slices a section heading-to-next-heading, asserts `cortex-read-backlog-backend` token present **and ordered**; docstring: "Guards the DOCUMENTED RULE and ITS WIRING, not runtime gate behavior"). New assertions: clarify §3 ("### 3. Check Existing Backlog Coverage") section contains the backend gate + two-arm stand-down before the scan; decompose §7 ("### 7. Update Index") index regen is gated on / moved inside the `cortex-backlog` arm.

**Stale-leftover fixture (load-bearing — a clean-empty fixture would pass even a broken gate):** write `cortex/lifecycle.config.md` (`---\nbacklog:\n  backend: {none|github-issues}\n---\n`) **plus** leftover `cortex/backlog/NNN-*.md` items, then assert the gated path STILL returns `{}` / renders the placeholder and **no writes land in `cortex/backlog/`** under `none`.

**Backend-routing test patterns already in the repo:** `_write_config(tmp_path, body)` helper (writes `cortex/lifecycle.config.md`); `tests/test_lifecycle_config_backlog_backend.py` (resolver unit, all degenerate arms); `tests/test_overnight_backlog_backend_guard.py` (parametrized `["github-issues","jira","none"]` + patch-downstream-to-prove-skip); `tests/test_backlog_backend_cli.py` (in-process `main([str(tmp_path)])`).

**Runner + gotchas:** `just test` (pytest `testpaths` = `tests/` + `cortex_command/dashboard/tests/`). **Editing the `cortex_command` package → use sequential dispatch, NOT a worktree** (`just test` runs the editable install, so worktree edits to `data.py`/`poller.py`/`lifecycle_config.py` test stale code). Console scripts aren't on PATH until editable reinstall → test in-process. `monkeypatch.delenv("CORTEX_COMMAND_ROOT"/"CORTEX_REPO_ROOT", raising=False)` in routing tests (footgun masks dev-machine routing). Keep new tests fully hermetic (`tmp_path`, no network). Two recurring **external** `just test` failures are pre-existing, not regressions: a concurrent-fixture flake (note `tests/fixtures/predicate_a_baseline.json` is already modified in the working tree) and a sandbox-network skip (pypi/MCP DNS blocked). `~/cortex-backend-test` is an out-of-repo manual harness — not part of `just test`; do not depend on it for the automated suite.

## Open Questions

- **decompose §7 placement** — fold `cortex-generate-backlog-index` *into* §5's `cortex-backlog` arm vs keep §7 as a separately-gated step. *Deferred to Spec/Plan*: research recommends folding into §5 (structural gate, reuses the resolved value, index-regen is cortex-backlog-only); spec finalizes whether the §7 heading remains as a one-line pointer.
- **Exact advisory / placeholder strings** (3 sites) — *Deferred to Spec*: spec authors the one-line copy. Constraints: say `cortex-backlog`, never `local`; the dashboard placeholder names the actual backend ("tracked externally via `<backend>`" / "disabled" for `none`); each prose advisory is one line.
- **ADR-0016 `proposed` status** — *Resolved*: consumers back-point to it regardless of status; #321 is human-in-loop, so the "MUST NOT auto-treat a proposed ADR as binding without human confirmation" consumer rule is satisfied. No blocker.

## Considerations Addressed

- *The dashboard backlog panel is not a consumer enumerated in `backlog.md`, so confirm gating it is a consistent extension rather than a divergence from epic 315 scope.* — **Addressed.** Requirements + Codebase + Web converge: the named-consumer set (`discovery, lifecycle, refine, dev, morning-review`) excludes the dashboard, but ADR-0016's principle ("routing lives at the skill/consumer layer") plus the config-authoritative-selection prior art make gating it a faithful **extension**, not a divergence — the dashboard is the wheel-code analog using the Python resolver, and the Site Kit anti-pattern confirms branching on backend identity (not zero-data) is the correct display behavior.
- *The requirements doc scopes external best-effort to create and round-trip paths only, so the external arm on these read/coverage paths should stand down (skip + advisory) rather than query the tracker, matching the gated siblings.* — **Addressed.** Confirmed verbatim against `backlog.md:60–68` (external best-effort = Create + Round-trip only). All three #321 paths are read/coverage/index, so external folds into `none`'s skip-with-advisory branch (the **two-arm** shape from dev Step 3). Tradeoffs confirms a three-arm copy of decompose §5 would wrongly query the tracker on a read path; the divergence between clarify §3 (two-arm read) and decompose §5 (three-arm write) is principled and should be documented inline.
