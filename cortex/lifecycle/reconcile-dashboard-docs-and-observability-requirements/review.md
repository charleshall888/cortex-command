# Review: reconcile-dashboard-docs-and-observability-requirements

Reviewed 13 commits on `pipeline/reconcile-dashboard-docs-and-observability-requirements` (`534613ec`..`b2a69752`), 9 files, +87/-32. Every acceptance check in the spec was executed against the worktree at `just 1.55.1`; results are recorded per requirement below.

## Stage 1: Spec Compliance

### Requirement 1: `just dashboard` binds loopback by default with an explicit opt-in
- **Expected**: top-level `dashboard_host` defaulting to `127.0.0.1`, a second top-level `dashboard_display_host` conditional, recipe passes `--host "{{dashboard_host}}"`. Checks: `just --evaluate dashboard_host` → `127.0.0.1`; dry-run greps for `--host "127.0.0.1"` = 1, `DASHBOARD_HOST=0.0.0.0` → 1, `dashboard_host=0.0.0.0` override → 1; `grep -c -- '--host 0\.0\.0\.0' justfile` → 0.
- **Actual**: `justfile:103-112` defines `dashboard_host_env := env_var_or_default("DASHBOARD_HOST", "")`, `dashboard_host := if dashboard_host_env == "" { "127.0.0.1" } else { dashboard_host_env }`, and `dashboard_display_host := if dashboard_host == "127.0.0.1" { "localhost" } else { dashboard_host }`. Recipe line 131 passes `--host "{{dashboard_host}}"`. All five checks executed: `127.0.0.1`, `1`, `1`, `1`, `0`.
- **Verdict**: PASS
- **Notes**: The implementation deviates from the spec's literal one-variable form by interposing `dashboard_host_env` and coalescing empty to loopback. This is a deliberate and correct deviation: the spec's Edge Cases assert that quoting alone covers `DASHBOARD_HOST= just dashboard`, but quoting only prevents the *misparse* — `--host ""` is still handed to uvicorn, and an empty host binds every interface in asyncio, which is precisely the "must not silently launch on an unintended interface" outcome the edge case forbids. Verified empirically: `DASHBOARD_HOST= just --dry-run dashboard` emits `--host "127.0.0.1"`. The commit message (`b2a69752`) and the justfile comment both record the reasoning. Every mandated check still passes, and the command-line override path (`just dashboard_host=0.0.0.0 dashboard`) still works because `dashboard_host` remains a top-level variable.

### Requirement 2: The recipe's echo prints the resolved host and never a bare `0.0.0.0` URL
- **Expected**: dry-run `grep -c "http://localhost:"` → 1; dry-run `grep -c "0\.0\.0\.0"` → 0; `DASHBOARD_HOST=0.0.0.0` dry-run `grep -c "Dashboard running at http://0\.0\.0\.0:"` → 1.
- **Actual**: `1`, `0`, `1`. The recipe echoes `Dashboard running at http://{{dashboard_display_host}}:{{dashboard_port}}`; the already-running branch's URL was moved out of its own echo so the dry-run localhost count is exactly 1.
- **Verdict**: PASS
- **Notes**: The already-running branch was restructured (`RUNNING_PID` captured, `exit 0` deferred until after the shared echo) rather than removed. Behaviour is preserved — an already-running instance still exits 0 without starting a second server — with one cosmetic side effect noted in Stage 2.

### Requirement 3: No file this ticket writes prints a `just` invocation that does not work
- **Expected**: `grep -rn "just host=\|just dashboard host=" docs/ cortex/requirements/ justfile README.md CLAUDE.md` returns nothing.
- **Actual**: returns nothing (exit 1). `docs/dashboard.md:9` uses the verified-working `just dashboard_host=0.0.0.0 dashboard` form.
- **Verdict**: PASS

### Requirement 4: `app.py`'s docstring launch line is loopback
- **Expected**: `grep -c -- "--host 127\.0\.0\.1" cortex_command/dashboard/app.py` → 1; `grep -c "0\.0\.0\.0"` → 0.
- **Actual**: `1` and `0`. `app.py:11` now reads `uv run uvicorn cortex_command.dashboard.app:app --host 127.0.0.1 --port 8080`; the launch line survives rather than being deleted.
- **Verdict**: PASS

### Requirement 5: `observability.md`'s Architectural Constraint states the truth
- **Expected**: `grep -c "all network interfaces"` → 0; ``grep -c "binds to `0\.0\.0\.0`"`` → 0; `grep -c "Not suitable for untrusted networks"` → 1; bullet contains `127.0.0.1`, `DASHBOARD_HOST`, `no authentication`.
- **Actual**: `0`, `0`, `1`. The rewritten bullet at `:107` contains all three substrings ("Dashboard has no authentication… bind `127.0.0.1` by default… Setting `DASHBOARD_HOST` (honoured by the `just` recipe only)…").
- **Verdict**: PASS
- **Notes**: The bullet adds a correct extra clause — "every host that can reach the bound interface gets unauthenticated access" — which preserves the safety information the old all-interfaces sentence carried without restating the false bind claim.

### Requirement 6: `pipeline.md` delegates instead of restating, and what remains is true
- **Expected**: `grep -c "0\.0\.0\.0"` → 0; `grep -c "accessible to any host on the local network"` → 0; ``grep -c "see `cortex/requirements/observability.md`"`` → 1.
- **Actual**: `0`, `0`, `1`. `pipeline.md:156` now reads "unauthenticated by design; its bind address and exposure model are owned by the observability area (see `cortex/requirements/observability.md`)." The surrounding sentence was corrected, not just the parenthetical stripped.
- **Verdict**: PASS

### Requirement 7: The dashboard threat model is relocated to the owning doc, not deleted
- **Expected**: `grep -c "^### Threat model$" docs/dashboard.md` → 1; that subsection contains `session state`, `log excerpts`, `DASHBOARD_HOST`; `grep -c "hotel\|coworking"` ≥ 1.
- **Actual**: `1`; the subsection (under `## Known Limitations`) carries "read session state, feature names, and log excerpts without authenticating", "Once the `DASHBOARD_HOST` opt-in binds another interface", and "hotel Wi-Fi, coworking Wi-Fi, and shared office VLANs" (`grep` → 1).
- **Verdict**: PASS
- **Notes**: The "'Local network' ≠ 'home network'" corollary is preserved as prose including the "bites hardest at 2am" framing rationale, rewritten against a loopback default as required. The subsection correctly states the loopback default is "defense-in-depth, not a sanitizer" and names the residual DNS-rebinding risk as accepted — satisfying the Technical Constraint that this ticket's docs must not describe the bind as satisfying #413's sanitizer precondition. No CVE ID is cited, so the "do not cite CVE-2024-3566" trap is avoided.

### Requirement 8: `overnight-operations.md` points at the owner and its section stays internally honest
- **Expected**: `grep -c "0\.0\.0\.0"` → 0; `grep -c "docs/dashboard.md"` ≥ 1; `grep -c "enumerated once here"` → 0; the `--dangerously-skip-permissions`, `_ALLOWED_TOOLS`, and keychain bullets untouched.
- **Actual**: `0`, `3`, `0`. The preamble now reads "the trust boundaries below cover overnight execution itself; the dashboard's boundaries are owned by [`docs/dashboard.md`](dashboard.md) and are not restated here." The dashboard bullet is a one-line pointer and the corollary bullet is removed. Diff confirms the three named bullets are byte-identical.
- **Verdict**: PASS

### Requirement 9: `docs/dashboard.md` describes the new defaults and stops calling the LAN trusted
- **Expected**: `grep -c "trusted local network"` → 0; `grep -c "DASHBOARD_HOST"` ≥ 2; `test $(grep -c "0\.0\.0\.0" …) -ge 1 && grep -n "0\.0\.0\.0" … | grep -vc "DASHBOARD_HOST"` → 0.
- **Actual**: `0`, `3`, and the guarded check returns `0` (two `0.0.0.0` lines exist, both co-located with `DASHBOARD_HOST`). Both the top bind sentence (`:9`) and the Known Limitations authentication bullet (`:189`) name `cortex dashboard`, `just dashboard`, the `127.0.0.1` default, and the `just`-only `DASHBOARD_HOST` opt-in.
- **Verdict**: PASS

### Requirement 10: Remote viewing has a documented supported path
- **Expected**: `grep -c "ssh -L 8080:127\.0\.0\.1:8080" docs/dashboard.md` → 1, plus prose that loopback-only is deliberate for the shipped verb, no `--host` flag, Tailscale mesh as the channel.
- **Actual**: `1`. A `### Viewing the Dashboard Remotely` subsection states "Loopback-only is deliberate for the shipped `cortex dashboard` verb, which offers no `--host` flag", gives the fenced `ssh -L` command, and attributes the secure channel to the Tailscale mesh — consistent with `cortex/requirements/remote-access.md:30`.
- **Verdict**: PASS

### Requirement 11: Exactly two prose copies of the bind fact remain
- **Expected**: `grep -rln "0\.0\.0\.0" --include="*.md" cortex/requirements/ docs/` returns only `docs/dashboard.md`.
- **Actual**: returns exactly `docs/dashboard.md`. A wider repo sweep confirms remaining `0.0.0.0` occurrences are confined to `cortex/backlog/047-*.md`, `056-*.md`, and `cortex/research/**` — all correctly out of scope per the spec's Edge Cases.
- **Verdict**: PASS

### Requirement 12: `docs/policies.md` declares a dashboard-docs owner
- **Expected**: `grep -c "^## Dashboard docs source of truth$"` → 1; section body has exactly 1 non-blank line, 0 `- ` bullets, 0 `MUST`; body contains `docs/dashboard.md`, `cortex/requirements/observability.md`, `docs/overnight-operations.md`, `data sources`, `same phase`, `defer`.
- **Actual**: heading count `1`; body non-blank lines `1`, bullets `0`, `MUST` `0`; all six substrings present (each count 1). The paragraph closes with "update the owner and link from the others rather than duplicating content", matching the two precedent maps' closing directive.
- **Verdict**: PASS

### Requirement 13: The ownership rule is actually reachable from the work it governs
- **Expected**: `CLAUDE.md`'s `docs/policies.md` trigger line contains `dashboard`; `grep -c "dashboard docs ownership map\|dashboard docs source of truth" CLAUDE.md` ≥ 1.
- **Actual**: `CLAUDE.md:32` now reads "Before authoring or editing skills, hooks, phase templates, overnight docs, dashboard behavior, or dashboard docs, read `docs/policies.md` — it owns … the overnight docs ownership map, the dashboard docs source of truth, and the tone policy." Second check → `1`.
- **Verdict**: PASS

### Requirement 14: `overnight-operations.md` stops duplicating the categories R12 assigns elsewhere
- **Expected**: `grep -c "alert evaluation every 5s"` → 0; `grep -c "_poll_state_files"` → 0; `grep -c "os.replace()"` → 6 (unchanged).
- **Actual**: `0`, `0`, `6`. The `**Files**:` line now points at `docs/dashboard.md`'s Data Sources and Polling Intervals sections; the `**Inputs**:` paragraph and the cadence sentence are removed; the TOCTOU/atomic-write paragraph survives intact. Section read end-to-end and remains coherent.
- **Verdict**: PASS

### Requirement 15: `observability.md`'s Dashboard Description stops enumerating panels and stops calling it an overnight-session monitor
- **Expected**: Description contains `docs/dashboard.md`; `grep -c "monitors overnight sessions"` → 0; `grep -c "fleet overview"` → 0; `grep -c "swim-lane"` → 0.
- **Actual**: `0`, `0`, `0`; the Description now reads "…renders live session and pipeline state via HTMX polling. The panel inventory is owned by `docs/dashboard.md` and is not enumerated here."
- **Verdict**: PASS

### Requirement 16: `observability.md`'s Dashboard Inputs list matches what the code reads
- **Expected**: `grep -c "cortex/lifecycle/active-session.json"` → 0; `grep -c "~/.local/share/overnight-sessions/active-session.json"` → 2; `grep -c "resolve_backlog_backend"` → 1; `grep -c "backlog/archive"` ≥ 1.
- **Actual**: `0`, `2`, `1`, `1`. The Inputs bullet names every file the spec enumerates, including `cortex/backlog/archive/*.md` and the `resolve_backlog_backend(root) == "cortex-backlog"` gate. Grounding spot-checked against code: `poller.py:146` (pointer path), `:166` (`sessions/latest-pipeline/pipeline-state.json`), `:383` (`resolve_backlog_backend`), and `data.py:1142/1175/1371/1397/1430/1459` for `pipeline-events.log`, `metrics.json`, `escalations.jsonl`, `exit-reports/`, `pr.json`, `learnings/progress.txt`. The pre-existing In-Session Status CLI occurrence at `:73` survives, as required.
- **Verdict**: PASS

### Requirement 17: `observability.md`'s Dashboard Outputs no longer claims notify-script dispatch
- **Expected**: `grep -c "notify script"` → 0; Outputs bullet contains `HTMX`.
- **Actual**: `0`; Outputs reads "Live HTML UI updated via HTMX at ~5s intervals; alerts surfaced in the UI and written to the dashboard process log (no external dispatch)". Grounding confirmed: `alerts.py:126,131` call only `logger.info`, with no subprocess or notify invocation.
- **Verdict**: PASS

### Requirement 18: The dead `terminal-notifier` dependency is removed without destroying its retirement record
- **Expected**: `grep -c "terminal-notifier"` → 1; `grep -c "Notifications (macOS)"` → 0; the four sibling Dependencies bullets survive (`grep -c '^- \*\*\(Statusline\|Dashboard\|In-Session Status CLI\|Sandbox Socket Access\)\*\*'` → 4).
- **Actual**: `1`, `0`, `4`. The `:51` retirement note naming commit `13c4acde` is preserved.
- **Verdict**: PASS

### Requirement 19: The requirements doc still validates and records its regather
- **Expected**: `cortex-validate-requirements-doc --path cortex/requirements/observability.md --scope area` exits 0; H2/H3 anchors unchanged; `> Last gathered:` bumped.
- **Actual**: validator returns `{"state": "pass", …}` with exit 0 and no missing required sections. `git diff main..HEAD -- cortex/requirements/observability.md | grep -E "^[+-]#"` produces no output, confirming zero heading changes. Line 3 reads `> Last gathered: 2026-04-03 (updated 2026-07-28)`. The six existing Dashboard acceptance criteria are untouched in the diff, as the Technical Constraints require.
- **Verdict**: PASS

### Requirement 20: `docs/dashboard.md`'s Data Sources lists every backing file
- **Expected**: the `## Data Sources` section contains `pipeline-events.log`, `pipeline-state.json`, `escalations.jsonl`, `exit-reports/*.json`, `pr.json`, `learnings/progress.txt`, `active-session.json`, `cortex/lifecycle.config.md`, `cortex/backlog/archive/*.md`; `grep -c "backlog/archive"` ≥ 1.
- **Actual**: all nine strings present within the section (`awk`-extracted between `^## Data Sources$` and the next `^## `); `backlog/archive` count `1`.
- **Verdict**: PASS
- **Notes**: The section was reorganised into three bolded groups (Session state / Per-feature files / Backlog and configuration). No document links to `#data-sources` anchors, so nothing breaks. One small imprecision: the pointer entry says the dashboard "falls back to the local `cortex/lifecycle/` copies when the pointer is absent", where `poller.py:143-144` falls back specifically to `cortex/lifecycle/sessions/latest-overnight/`. Directionally correct, sub-threshold for a finding.

### Requirement 21: `docs/dashboard.md`'s Polling Intervals table includes the alerts loop
- **Expected**: the `### Polling Intervals` section contains both `_poll_alerts` and `5 s`.
- **Actual**: both present. The table now names all four backend loops with their cadences (2 s / 1 s / 5 s / 30 s), matching `poller.py:339,360,432,446` and the module docstring at `:453-456`.
- **Verdict**: PASS

### Requirement 22: `docs/dashboard.md`'s Known Limitations stops claiming panels are hidden
- **Expected**: the visual-layout bullet contains `Agent Fleet`, `Pipeline`, `empty-state`; `grep -c "are hidden when there is no active session"` → 0.
- **Actual**: `0` for the banned phrase; the bullet at `:191` names both panels and quotes the exact template strings. Grounding verified: `fleet-panel.html:50` renders `fleet stood down · no session` and `pipeline_panel.html:33` renders `no pipeline · refinement queue empty`, both inside `class="empty-state"`.
- **Verdict**: PASS

### Requirement 23: Ticket #415's own body stops contradicting its built scope
- **Expected**: `grep -c "Two-stage"` → 0; `grep -c "after the panels exist"` → 0; Integration still contains `no later than`; the two other Edges bullets each → 1; Touch points contain `pipeline.md`, `overnight-operations.md`, `justfile`.
- **Actual**: `0`, `0`, `1`, `1`, `1`, and all three touch-point strings present. Integration is rewritten to single-pass, the first Edge is rewritten to "Single-pass by nature", and four touch points were added. `updated:` frontmatter bumped to 2026-07-28.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None. The one behavioural change — `just dashboard` defaulting to loopback with a `DASHBOARD_HOST` opt-in — is now stated in `cortex/requirements/observability.md:107`, and the delegation in `cortex/requirements/pipeline.md:156` points at it. The empty-`DASHBOARD_HOST` coalescing is a refinement of that same stated rule ("Setting `DASHBOARD_HOST` … is the sole way to expose it beyond loopback"), not new behaviour outside it. No new CLI surface, flag, or dependency was added.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `dashboard_host` / `dashboard_display_host` mirror the existing `dashboard_port` idiom at `justfile:101`, and `dashboard_host_env` reads clearly as the raw-environment stage of the same value. The doc heading `## Dashboard docs source of truth` matches the sentence-case, no-colon style of the two precedent maps in `docs/policies.md`.
- **Error handling**: Appropriate for a config/docs change. The one genuine failure mode — `DASHBOARD_HOST` set-but-empty handing uvicorn an empty host and binding every interface — is handled at the just-variable layer where `--dry-run` can prove it, verified empirically (`DASHBOARD_HOST= just --dry-run dashboard` → `--host "127.0.0.1"`). Quoting is retained as well, so the failure is closed twice.
- **Verification coverage**: Strong. All 23 requirements' acceptance checks were re-executed against the worktree and every one returns the specified value. `cortex_command/dashboard/tests/` passes (194 passed, 4 subtests). The two pre-commit phases the spec flagged both pass on this tree: `just check-contract` exit 0 and `just sync-install-guard --check` exit 0. Grounding claims were independently confirmed against `poller.py`, `data.py`, `alerts.py`, `fleet-panel.html`, and `pipeline_panel.html` rather than taken on trust.
- **Pattern consistency**: Good. Requirements-doc conventions were followed — refined in place, H2/H3 anchors byte-identical, `> Last gathered:` bumped, validator green. The relocation pattern (owner doc gains the content, former holder gains a link) is applied uniformly across `overnight-operations.md`, `pipeline.md`, and `observability.md`. One minor structural note: the `### Dashboard Polling` section in `overnight-operations.md` now lacks the `**Inputs**:` line its sibling sections carry, which is the intended consequence of R14's "deleted where the surrounding paragraph survives without them" and reads fine.
- **Scope discipline**: Clean. Nine files, all named in the spec, and no source behaviour touched outside the `justfile` recipe. The two restructures that go beyond a literal reading of the spec — the `dashboard_host_env` coalescing and the already-running branch rework — are each forced by a check or an Edge Case in the spec itself, and each is documented in a comment and a dedicated commit. One cosmetic consequence worth recording for a future reader, not a fix request: when an instance is already running *and* `DASHBOARD_HOST` is exported to something other than the value that instance was launched with, the recipe now prints the configured host rather than the running instance's actual bind address. The pre-change recipe had the same class of imprecision (it hardcoded `localhost` in that branch regardless), and the spec does not address this path.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
