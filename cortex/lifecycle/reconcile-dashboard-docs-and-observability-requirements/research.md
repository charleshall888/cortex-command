# Research: Reconcile dashboard docs and observability requirements with reality

> Refine research, 2026-07-27. Ticket #415 (parent epic #410). Sizing: complexity `complex`, criticality `high` (7-agent cell: 6 core angles + adversarial). Requirements context: `cortex-load-requirements` returned `no area docs matched for tags: []` and printed only `project.md` + `glossary.md` — it reads the *lifecycle* `index.md` tags, and `index.md` is created by `create_index.py` at build Step 2, so it does not exist during refine. `cortex/requirements/observability.md` and `pipeline.md` were read directly.

**Clarified intent.** Make every dashboard bind-address claim in the repo true and close the remaining 0.0.0.0 exposure path so #413's no-sanitizer contingency holds for every launch path; regather `observability.md`'s Dashboard entry against shipped reality; declare a dashboard-docs owner in `docs/policies.md`.

**Settled at Clarify** (user-confirmed, not open): (1) correct all bind-claim sites *and* flip the justfile default rather than docs-only; (2) run the full reconciliation now rather than staging the regather behind unbuilt siblings; (3) add a new `policies.md` ownership section rather than recording the gap or folding into the overnight map.

## Epic Reference

Discovery research for parent epic #410 lives at `cortex/research/dashboard-command-station/research.md`. It is background spanning all five children — read for context, not copied here. Two clauses bear directly on this ticket: the **Sanitizer** decision record (`:85`), which rejects nh3 and makes the stale 0.0.0.0 claims a coupled obligation of the same epic; and **Stale docs the epic must fix** (`:35`), which names `observability.md:107` and `app.py:11` but **not** `pipeline.md:156` or `docs/overnight-operations.md:627`.

## Codebase Analysis

**`cortex_command/cli.py` needs no change.** `_dispatch_dashboard` (`cli.py:454-504`) already hardcodes `host="127.0.0.1"` (`cli.py:498-501`), and the `--port` help text already reads "TCP port to bind on 127.0.0.1" (`cli.py:1228-1229`) — accurate today. There is no `--host` flag anywhere in `cortex_command/`; the nearest style precedent for a guarded opt-in is the `store_true` `--force`/`--dry-run` idiom on `overnight start` (`cli.py:625-651`).

**`justfile:103-116` is the only live 0.0.0.0 launch path.** Two parameterization idioms coexist: the top-level `dashboard_port := env_var_or_default("DASHBOARD_PORT", "8080")` (`justfile:101`) and recipe parameters with defaults (`overnight-run state="..." time-limit="..."`, `justfile:68`). Three lines change: the recipe signature or a new top-level variable, the `echo` at `:115` (which prints `http://0.0.0.0:{{dashboard_port}}` — itself a bind claim), and the `--host 0.0.0.0` literal at `:116`. No other recipe depends on `dashboard`.

**Nothing depends on the 0.0.0.0 default.** `.github/workflows/validate.yml:86-93` runs `test_routes_smoke.py`, which uses Starlette `TestClient` and never opens a socket. `skills/overnight/references/new-session-flow.md:147` polls `http://localhost:8080/health`, which resolves to loopback either way. `tests/test_cortex_morning_review_resolve_demo_config.py` treats `"just dashboard"` as opaque config text. No test anywhere asserts on host, bind, `127.0.0.1`, or `0.0.0.0`.

**Gating.** Per `CLAUDE.md:28`, none of `cortex_command/dashboard/`, `cli.py`, or `justfile` is lifecycle-gated, and none matches the dual-source mirror regex (`.githooks/pre-commit:528`) — no `plugins/cortex-core/` regeneration. Editing `justfile` does trip pre-commit Phase 1.55 (`just check-contract --staged`) and Phase 1.95 (`just sync-install-guard --check`); both should pass as no-ops, but see Adversarial (e) — Phase 1.55 will **block** a commit that documents a `--host` flag `cortex dashboard` does not have.

**`app.py:11`** is the sole bind claim in the dashboard package; no other launch line exists in the module or package. No test pins the docstring text.

## Web & Documentation Research

**Loopback-by-default is the settled convention.** Flask (`127.0.0.1`, `--host=0.0.0.0` to opt in), Django `runserver` (`127.0.0.1:8000`; ticket #396 states the rationale — "inexperienced users could accidentally expose development servers"), uvicorn (`127.0.0.1`; docs: "Use `--host 0.0.0.0` to make the application available on your local network"), Vite, and Jupyter all converge. Next.js and Streamlit are the counter-examples and both carry open community pushback calling their own defaults insecure (streamlit/streamlit#10155; vercel/next.js discussion #64650) — they read as known anti-patterns inside their own projects, not alternative conventions.

**CWE-1327 (Binding to an Unrestricted IP Address)** is the direct classification: "binds to 0.0.0.0 … effectively exposing the server to every possible network." OWASP A05:2021 is the umbrella category. Static-analysis tooling flags literal `host="0.0.0.0"` as a rule, not a suggestion.

**"0.0.0.0 Day" (Oligo Security, Aug 2024)** — a malicious public web page can reach services **bound to 0.0.0.0** on macOS/Linux, because `0.0.0.0` was absent from the Private Network Access blocklist that already covered `127.0.0.1`. It specifically does **not** reach services bound strictly to loopback. This makes the justfile flip a closure of a real, browser-exploitable vector, not merely a LAN-neighbour concern. Chrome fixed via PNA rollout (128–133), Safari in iOS/macOS 18+, Firefox pending as of that writeup.

**DNS rebinding does reach loopback.** Per GitHub's security blog, a malicious domain resolves first to a public IP then rebinds to `127.0.0.1`, reaching the service under same-origin rules for that hostname; the article states loopback binding alone is "not sufficient protection" for an unauthenticated service and names Host-header allowlisting as the control. webpack-dev-server's fix for CVE-2018-14732 was a Host check, not a bind change. **This is the load-bearing finding against #413's "contingent on the loopback bind" framing** — see Adversarial §2.

**Correction — do not propagate.** The Clarify-stage prompt cited "CVE-2024-3566" for 0.0.0.0 Day. That CVE is an unrelated Node.js/Windows `cmd.exe` argument-injection issue. 0.0.0.0 Day carries no single CVE. Independently flagged by two angles.

**Docs ownership prior art**: GitLab treats CODEOWNERS as "a version controlled, single source of truth," and additionally binds ownership at page level via front-matter. Consensus practice holds that an SSOT needs authority, uniqueness, accessibility, and ownership — the recurring failure mode being that nothing in version control connects a behavior change to the doc claim it invalidates.

*(Two `WebFetch` calls to flask.palletsprojects.com returned HTTP 429; the Flask default is sourced from search snippets of that page, corroborated by two independent sources.)*

## Requirements & Constraints

**`project.md:23` front-door bar.** #415 is not efficiency-framed, so the net-effect clause does not bind. Evidence is concrete: `413-*.md:30` and `415-*.md:19`. But note precisely — 415's Why cites the **app.py docstring** copy-paste risk, not the justfile recipe; the justfile flip is connective inference. If it stays in scope, its evidence line should name `justfile:115-116` explicitly.

**`project.md:41` enforcement-gate bar.** "A new gate enters only with its named failure stated here." Nothing in the drafted scope requires one. If the spec adds a bind-drift regression test, that test **is** a new gate and needs its own named-evidence line — it does not inherit the docstring evidence. See Drift Detection and Adversarial §1 for the contradicting verdicts.

**`project.md:25` solution horizon.** The bind correction is a one-time factual sync across files with no shared source — plain correction is the right horizon. The `policies.md` section is the durable half.

**Epic #410 Integration (`410-*.md:24`)** — "docs/requirements reconciliation **alongside**", not after. Supports decision 2. **Epic Edge (`:28`)** — "no auth changes": the bind-default flip changes network exposure, not authentication. No conflict, but the spec should state the distinction so a reviewer does not conflate them.

**#413's contingency (`413-*.md:30`)** — "No sanitizer — contingent on the loopback bind, so the docs-reconciliation sibling ticket's bind-address and docstring correction lands no later than this ticket." Binding sequencing: this must ship no later than #413, not before #411/#412/#414.

**Requirements-edit conventions** (`skills/requirements/SKILL.md:54,67,72`): seven H2s in fixed order; H2/H3 anchors stay verbatim; refine in place, never rewrite from scratch; bump `> Last gathered:` (currently `observability.md:3` reads "2026-04-03 (updated 2026-04-08)"); validate with `cortex-validate-requirements-doc --path {path} --scope area`.

**No `cortex/requirements/docs.md` exists and none is needed** — documentation governance lives in `docs/policies.md` by design. The ticket's `docs` area is satisfied by the new ownership section.

**ADRs**: none governs the dashboard bind address, its read-only posture as a standalone decision, or documentation ownership. ADR-0011 (`:31`) cites observability read-only-ness as rationale for a different decision. Nothing here meets the three-criteria ADR gate — prose-only is correct.

**Prior drift incident (named evidence).** `cortex/lifecycle/archive/gather-area-requirements-docs-for-four-missing-areas/review.md:27,82` (2026-04-03) records `pipeline.md` saying "localhost-only" while `observability.md` said "0.0.0.0" — the same two docs, disagreeing in the opposite direction from today.

## Dashboard Ground Truth

Verified against code; lift directly into the regather.

**Routes** (`app.py:278-429`): `/health`, `/`, `/sessions`, `/sessions/{session_id}` (404 on missing), and ten `/partials/*`. **`pipeline_panel.html` is server-included at page render (`base.html:2201-2203`), not polled** — no `/partials/pipeline-panel` route exists; it refreshes only on full page reload.

**Panels.** `base.html`'s `§ 01`–`§ 10` order matches `docs/dashboard.md`'s `### 1.`–`### 10.` **exactly — no mismatch**, plus an unnumbered Alerts Banner. HTMX cadences: 3s (activity stream), 5s (alerts, session, escalations, feature cards, fleet, swim-lane, round history), 30s (metrics, backlog).

**Complete input set** — the regather's Inputs list. `observability.md:30` currently names five paths; the real set is:

| Path | Loop / cadence |
|---|---|
| `~/.local/share/overnight-sessions/active-session.json` | `_poll_state_files`, 2s — **not** `cortex/lifecycle/active-session.json` as `:30` claims |
| `cortex/lifecycle/sessions/{id}/overnight-state.json` | 2s |
| `cortex/lifecycle/sessions/{id}/overnight-events.log` | `_poll_jsonl_events`, 1s (byte-offset incremental) |
| `cortex/lifecycle/sessions/latest-pipeline/pipeline-state.json` | 2s |
| per-feature `{slug}/events.log`, `plan.md`, `agent-activity.jsonl`, `escalations.jsonl`, `exit-reports/*.json`, `pr.json`, `learnings/progress.txt` | 2s |
| `cortex/lifecycle/pipeline-events.log`, `metrics.json` | `_poll_slow`, 30s |
| `cortex/lifecycle.config.md` (backend gate) and `cortex/backlog/*.md` | `_poll_slow`, 30s — backlog read **only** when `resolve_backlog_backend(root) == "cortex-backlog"` |
| `sessions/*/overnight-state.json` (glob), `sessions/{id}/morning-report.md` | per-request, `/sessions*` routes |

**Four poll loops**, not three: `_poll_state_files` 2s, `_poll_jsonl_events` 1s, `_poll_slow` 30s, `_poll_alerts` 5s (`poller.py:401-417`). The module docstring at `poller.py:1-11` undercounts to three.

**Outputs claim at `observability.md:31` is FALSE.** `fire_notifications` (`alerts.py:97-133`) only calls `logger.info` and flips a `notified` flag; its own docstring records that the shell-subprocess channel was retired. `git show --stat 13c4acde` confirms deletion of `hooks/cortex-notify.sh`. The doc's own retirement note at `:51` covers the separate notifications subsystem, not this Outputs line.

**All six acceptance criteria verified still true** and can carry forward unchanged: 7s latency (2s poll + 5s HTMX), incremental non-double-counting cost (`data.py:234-278`, offset only advances), once-per-session circuit breaker (`alerts.py:130-132`), 300s stall threshold (`alerts.py:24`), silent malformed-file handling (`data.py:52-55,71-74` + last-good retention at `poller.py:169-171`), offset reset on session change (`poller.py:163-167`).

**`observability.md` never mentions the backend gate** (`resolve_backlog_backend`, `lifecycle_config.py:141-181`) or `cortex/lifecycle.config.md`, though its Inputs implies an unconditional backlog read.

**`docs/dashboard.md` inaccuracies**: `:92` Data Sources omits `pipeline-events.log`, `pipeline-state.json`, `escalations.jsonl`, `exit-reports/*.json`, `pr.json`, `learnings/progress.txt`, `active-session.json`, `lifecycle.config.md`. `:100-113` Polling Intervals omits `_poll_alerts` entirely. `:161` says Fleet/Pipeline are "hidden" with no session; both actually render explicit empty-state text (`fleet-panel.html:43-52`, `pipeline_panel.html:32-34`).

## Docs & Governance Surface

**Bind-claim inventory — seven live copies of one fact:**

| Site | Kind |
|---|---|
| `cortex/requirements/observability.md:107` | Unqualified; false for the shipped path |
| `cortex/requirements/pipeline.md:156` | Unqualified; **restates** the value inline while also cross-referencing observability.md |
| `docs/overnight-operations.md:627` | Unqualified, in `## Security and Trust Boundaries` |
| `docs/overnight-operations.md` corollary bullet ("'Local network' ≠ 'home network'") | Threat-model prose predicated on the false premise |
| `cortex_command/dashboard/app.py:11` | Unqualified docstring launch line |
| `docs/dashboard.md:9` | **Correct** — names both paths |
| `docs/dashboard.md:159` | **Correct** — names both paths |

Plus `justfile:115-116`, which is accurate as an artifact but is the behavior being changed.

**No `plugins/` mirror carries the claim** — `plugins/cortex-core/` mirrors only `bin/`, `hooks/`, `skills/`. No parallel fix needed.

**Ownership tension, real.** `docs/policies.md:37-39` assigns `docs/overnight-operations.md` to the overnight map. A dashboard claim currently lives inside that overnight-owned doc, added deliberately (`cortex/lifecycle/archive/document-overnight-pipeline-operations-and-architecture/spec.md:50` required it as one of five enumerated boundaries). A second ownership map covering the same file needs a stated precedence or it adds ambiguity.

**`policies.md` section shape** (both precedents, `:37-39` and `:41-43`): H2 `## <Area> docs source of truth`; one paragraph naming each doc and its owned topic; closing directive ("update the owning doc and link from the others rather than duplicating content" / "link to them from other docs rather than restating"). No MUST language in either — matches the MUST-escalation policy default.

**`docs/dashboard.md` panel-entry template** (`:40-42`, `:76-78`): `### <N>. <Panel Name>` followed by 2–3 sentences stating what it shows, where the data comes from (backtick paths inline), and any conditional-visibility note. A new panel on a new file needs a `## Data Sources` bullet; on a new cadence, a `### Polling Intervals` row.

**Sibling amendment.** `cortex-update-item` (`cortex_command/backlog/update_item.py:385-520`) is **frontmatter-only** — its flags cover status/priority/type/complexity/criticality/spec/lifecycle-slug/lifecycle-phase/session-id/parent/blocked-by/rework-of/areas/tags. No verb in `bin/` or `cortex_command/backlog/` mutates a ticket body. Amending #412 requires a manual `Edit` to its Edges section. **#414 should not be amended** — it adds no panel, so the obligation would fail the front-door evidence bar.

**Elsewhere**: `README.md:60` describes the dashboard as "for monitoring overnight sessions" — will undersell it once the epic lands, but makes no bind or panel claim; follow-up, not in scope. `CHANGELOG.md`, `docs/overnight.md:30`, `skills/overnight/`, `plugins/cortex-ui-extras/` carry no stale bind claim.

## Drift Detection & Test Surface

**No test pins the bind address.** Zero hits for `0.0.0.0`/`127.0.0.1` across `tests/` and `cortex_command/dashboard/tests/`. `test_routes_smoke.py` builds the app *without* entering the lifespan and never calls `uvicorn.run`; `tests/test_cli_dashboard.py` asserts only on `--help` and PID-path resolution. Nothing would have caught the original drift, and nothing will catch a revert. **No existing test breaks when the default flips.**

**Existing doc-drift gates all check structure, never semantic truth**: ADR citation audit (report-only), skill-path lint (the canonical `--staged`/`--audit` two-mode pattern, `cortex_command/lint/skill_path.py:525,541`), contract lint, dual-source byte-diff, reference-size ratchet, `test_lifecycle_references_resolve.py` (path/line existence), `test_backlog_grep_targets_resolve.py` (token existence — the closest analog, still existence not accuracy).

**The nearest analog was retired.** `bin/cortex-requirements-parity-audit` scanned `review.md` for logged-but-unapplied requirements drift, was already informational and never-failing, and was deleted in `e3aef4e5` under #407 for lacking named evidence.

**This angle's verdict: no new gate.** It argued the drift is "a single aging event … with no evidence of a second occurrence," offering an optional near-zero-cost fallback — one assertion folded into the already-CI-wired `test_routes_smoke.py`, framed as a marginal addition rather than a new named gate. **The Requirements angle contradicts the premise** (a prior incident exists) and the Adversarial angle re-adjudicates the conclusion — see Adversarial §1 and Open Questions.

## Adversarial Review

**§1 — the gate contradiction, adjudicated.** The 2026-04-03 incident is real, and three details matter: the review verdict was **APPROVED with `"requirements_drift": "none"`** (seen, logged, waved through); the reviewer offered two fixes — restate correctly, **or "defer entirely to observability.md"**; the restate option was taken. `pipeline.md:156` today reads "…(binds to `0.0.0.0`) by design (see `cortex/requirements/observability.md`)" — aligned by **copying**, and now wrong again. So incident two is partly a consequence of how incident one was resolved.

The named generator is **duplication, not the absence of a test**. Seven live copies of one fact. A ticket that makes all seven true and leaves all seven standing rebuilds the generator and buys one cycle. On the gate itself the Adversarial angle **sides with Drift, for a different reason**: `project.md:41` retired the parity audit for exactly this class, and a bind assertion in `test_routes_smoke.py` is that audit under another filename. Two incidents in four months of a fact that is only wrong because it is written down seven times clears the bar for **deleting five of the seven copies**, not for machinery.

**Miss no angle caught: `cortex/requirements/pipeline.md:156`.** Absent from the ticket's Touch points, absent from the epic research (`:35`), absent from every core angle's findings. As specced, the ticket **fails its own headline acceptance** — and it is the same doc that drifted in 2026-04-03.

**§2 — false assurance.** Verified: **zero** `TrustedHost`, `CORS`, `Origin`, or `add_middleware` occurrences in `cortex_command/dashboard/` (orchestrator re-verified). Also verified and materially under-reported by every other angle: **the unsanitized-markdown-to-DOM path already exists today, pre-#413** — `data.py:940-942` renders `morning-report.md` via `markdown.markdown(...)` and `session_detail.html:56` emits it with `| safe`.

Strong objection: after this ticket the repo contains a documented, supported opt-in that switches #413's contingency off, and #415 becomes the artifact cited as having discharged it. What the angle actually believes: residual risk is acceptable, the *framing* is not. The ticket-body trust boundary does hold (`poller.py:366` gates backlog reads on the local backend, so a pluggable backend cannot feed the reader), but the morning report is the weaker boundary and is already `| safe`, carrying agent-generated prose plus redacted child stderr whose allowlist `project.md` itself calls "defense-in-depth, NOT complete."

Consequences: (a) the spec records the loopback bind as **defense-in-depth, not the sanitizer's substitute**, naming the accepted residual (DNS rebinding against an unauthenticated, Host-unvalidated local service); (b) `TrustedHostMiddleware(allowed_hosts=["localhost","127.0.0.1","[::1]"])` is ~3 lines and closes rebinding — epic #410's "no auth changes" does not forbid Host validation — but belongs in a **follow-up ticket, not smuggled into #415**. Secondary: the Why's "would expose" framing understates the fact — `just dashboard` on 0.0.0.0 has been serving that `| safe` path all along.

**§3 — decision 2's counter collapses on facts already on disk.** `cortex/backlog/411-*.md:5` is `status: in_progress` with a written spec; it **adds a panel** (the ticket feed) and its body carries **zero** docs obligation. A governance section written today cannot reach a ticket already mid-implementation — the very next panel to land lands undocumented, possibly before #415 merges. #412 and #414 are being refined concurrently (their `events.log` files were created today), so "current reality" is a target three sessions are actively moving. And the repo's own evidence indicts prose ownership rules: `docs/overnight-operations.md:622` states verbatim "The trust boundaries below are enumerated once here; safety notes are not scattered elsewhere in this doc" — and the section it introduces is itself a duplicate of `observability.md:107`, duplicated twice more internally. A convention saying "enumerate once" produced three copies of the very claim this ticket exists to fix. On reachability: `CLAUDE.md` scopes the policies.md read trigger to "skills, hooks, phase templates, or overnight docs" — a #412 builder editing `base.html` and `poller.py` has no instruction to open it.

Verdict: the **bind-address half of decision 2 is right and must land now**. The **panel-regather half** runs against a moving target with a mechanism that cannot reach the two tickets that will move it next. Minimum repair if it stands: hand-amend #411 and #412 bodies, and mark the enumeration as a point-in-time snapshot with a named as-of commit.

**§4 — cleaner ownership formulation: make the rule subtractive.** `docs/dashboard.md` is canonical for dashboard *behavior* (bind, panels, polling); every other doc links rather than restates. `observability.md`'s Dashboard entry holds *requirements* (what must be true), not behavior — state this explicitly or the two drift again by construction. Collapse `overnight-operations.md:627` + corollary to a one-line pointer, and **delete** the `(binds to 0.0.0.0)` parenthetical at `pipeline.md:156`, whose cross-reference is already there. That is the 2026-04-03 reviewer's option B, four months late. Seven copies → two, converting a prose rule this repo has two documented failures of into a structural fact.

**§5 — scope integrity.** Filed: 4 touch points. Actual: ~11 sites across 8 files plus ticket-body edits. **The ticket body now contradicts the settled decision** — `415-*.md:27` says the regather "completes after the board and strip land" and `:31` says "Two-stage by nature"; both are false under decision 2, and `cortex-update-item` cannot fix them. Fold in (same file, same validate run, same `Last gathered:` bump): `observability.md:31`'s false Outputs line, `:30`'s wrong `active-session.json` path, `:116`'s dead `terminal-notifier` dependency. **Split out**: the `overnight-operations.md` security-section *rewrite* (rewriting a threat model is not "make a bind claim true", and it is overnight-owned prose — reduce to a pointer here), and any `TrustedHostMiddleware` work.

**§6 — missed by all six angles.**

- **(b) The proposed opt-in invocation is wrong.** Verified empirically at just 1.55.1 with `dashboard_host := env_var_or_default("DASHBOARD_HOST","127.0.0.1")`: `just dashboard_host=0.0.0.0 dashboard` ✓ and `DASHBOARD_HOST=0.0.0.0 just dashboard` ✓, but `just host=0.0.0.0 dashboard` → `error: variable 'host' overridden on the command line but not present in justfile`. Naming the variable `host` to make that form work breaks parallelism with `dashboard_port` at `justfile:101`. Writing `just host=0.0.0.0 dashboard` into the docs would ship a **brand-new false invocation claim** while fixing old ones. *(Orchestrator re-verified all four forms independently.)*
- **(c) Empty-env-var footgun.** `DASHBOARD_HOST= just dashboard` yields an empty value (`env_var_or_default` returns set-but-empty), so unquoted `--host {{dashboard_host}}` hands uvicorn `--host --port 8080`. Quote it. *(Orchestrator re-verified.)*
- **(d) `justfile:115`'s echo is itself a bind claim** — prints a `0.0.0.0` URL nobody should paste. Print the resolved host, rendering `127.0.0.1` as `localhost`.
- **(e) The LAN/Tailscale downside.** `cortex/requirements/remote-access.md:26,30` scopes remote access to reattaching a Claude Code session via Tailscale + mosh and never mentions the dashboard — no requirement breaks. But a loopback bind is unreachable over `tailscale0`, and `cortex dashboard` has **no `--host` flag at all**, so after this ticket a consumer with no clone has zero supported path to view the dashboard from a phone. Decide explicitly: accepted non-goal stated in `docs/dashboard.md`, or a follow-up ticket.
- **(e, related) A pre-existing gate was claimed to do part of the job — the claim is FALSE.** This bullet originally read that `.githooks/pre-commit:107`'s `just check-contract` would block a commit documenting a `--host` flag that does not exist. Critical review probed it directly and disproved it: `cortex_command/lint/contract.py:461` defines `_BINARY_RE = re.compile(r"cortex-[a-z][a-z0-9-]*")`, which matches only hyphenated `cortex-*` console scripts, so `cortex <verb> --flag` is never extracted. A docs file containing `` `cortex dashboard --host 0.0.0.0` `` produced zero violations and exit 0, while `` `cortex-check-contract --totally-fake-flag` `` in the same file produced `E102` and exit 1. The linter runs on those paths but is blind to this form. Corrected here so the error does not propagate further; teaching the linter `cortex <verb> --flag` forms is a candidate follow-up.
- **(g)** Independently agreed: do not propagate "CVE-2024-3566."

## Open Questions

All seven resolved at the Research exit gate (2026-07-27). Recorded here with their answers; none carried into Spec unannotated.

- **Fix-by-correction vs fix-by-deletion.** → **RESOLVED: collapse seven copies to two.** Delete the `(binds to 0.0.0.0)` parenthetical at `pipeline.md:156` (its `see observability.md` cross-ref already carries the delegation) and reduce `overnight-operations.md:627` + corollary to a one-line pointer; correct `observability.md:107`, `app.py:11`, and the justfile. Rationale: deletion removes the evidenced generator rather than rebuilding it, it is the 2026-04-03 reviewer's own option B, and `project.md`'s deletion bias puts the burden of proof on keeping. The threat-model *rewrite* variant was rejected — rewriting the L2-broadcast/hotel-coworking framing is a different job on overnight-owned prose.
- **Contradiction between angles on the drift gate.** → **RESOLVED: no new gate, and no optional assertion.** The conclusion was unanimous; the disputed fallback is decided on Adversarial's grounds — a bind assertion in `test_routes_smoke.py` is the retired `cortex-requirements-parity-audit` under another filename, `project.md:41` retired exactly that class, and a new assertion would need its own named-evidence line that the docstring evidence does not supply. The contradiction in *reasoning* is recorded, not silently reconciled: Drift Detection's "no second occurrence" premise is false (see Requirements & Constraints), but its conclusion survives on independent grounds.
- **#411 is `in_progress`, adds a panel, and carries no docs obligation.** → **RESOLVED by removing the moving target.** Under the subtractive ownership formulation (Adversarial §4), `docs/dashboard.md` owns the panel list and `observability.md` holds requirements — so `observability.md` should not enumerate panels at all, but point at the owning doc. This resolves the gap without an as-of snapshot and without amending a ticket mid-implementation. Regather the Description's scope framing (it currently reads "monitors overnight sessions" and names 5 of 10 panels), fix Inputs/Outputs/Dependencies, replace the enumeration with a pointer, and hand-amend **#412** only. **#414 is not amended** — it adds no panel, so the obligation would fail the front-door evidence bar.
- **Ticket-body contradiction.** → **RESOLVED: the spec owns a manual `Edit` to `415-*.md:27,31`.** `cortex-update-item` is frontmatter-only; leaving the body asserting two-stage sequencing the built artifact contradicts would mislead review-phase drift checks.
- **`cortex dashboard --host` for remote/Tailscale access** → **RESOLVED: in scope for this ticket** (user decision). Ship the flag on the shipped CLI path, not only the contributor recipe. The flag and its documentation must land in the same commit — `.githooks/pre-commit:107` fires `just check-contract` on staged `docs/*`, `justfile`, and `cortex/requirements/*` paths and will block a commit documenting a flag that does not exist. Assess `[release-type: minor]` at commit time (new user-facing CLI surface).
- **`TrustedHostMiddleware`** → **DEFERRED to a follow-up ticket.** Confirmed absent, ~3 lines, closes the DNS-rebinding residual, not forbidden by epic #410's "no auth changes" edge (Host validation is not auth). Deferred because "add security middleware" is not "reconcile docs" and needs its own Why and evidence line. The spec still records the loopback bind as defense-in-depth, naming this residual as accepted.
- **`docs/overnight-operations.md` security section** → **RESOLVED: pointer-only reduction**, folded into the first question above.

## Considerations Addressed

- **"Epic #410 places reconciliation alongside the children — check nothing assumes the panel work has landed."** Addressed and partly inverted. Requirements & Constraints confirmed the "alongside" reading at `410-*.md:24`, and the bind-address half is genuinely independent of #411–#414. But the Adversarial angle found the reverse hazard: the *regather* half assumes the panel set is stable, and #411 is `in_progress` while #412/#414 are being refined concurrently — so the enumeration is being written against a target three sessions are moving. Surfaced as an Open Question with three concrete options.
- **"Assess whether the regather belongs inside this epic or is standalone upkeep the epic merely triggers."** Addressed. No requirement compels either placement — Requirements & Constraints confirmed `project.md:23,41` govern new machinery, not doc-correction chores, and nothing asserts drift fixes must be scoped inside the triggering epic. The Web angle noted the general docs-hygiene pattern treats accuracy as a standing named-owner obligation rather than epic-delivered work, which weakly favors standalone upkeep. Adversarial supplies the operative split instead: the bind-address half is a real correctness dependency of #413 and belongs here; the panel-regather half is the part whose epic-membership is genuinely arguable.
