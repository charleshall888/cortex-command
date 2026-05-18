# Specification: Release-gate empirical from-Claude-session smoke test for #228 daytime dispatch

## Problem Statement

#228 wires the daytime dispatch through `cortex` CLI + MCP and claims (spec R16) that `daytime_start_run` invoked from inside a real Claude Code session escapes the calling session's Seatbelt sandbox — the load-bearing property that makes daytime usable. pytest cannot exercise the MCP-from-real-Claude-session surface (no MCP host inside CI). The current backlog ticket #230 holds a manual procedure to verify this empirically and to gate the production release tag (not the lifecycle's `feature_complete`). Adversarial review of the existing procedure found two fatal defects (`feature_dispatched` is not an emitted event; `events.log` is the wrong log file) propagated through both #230 and #228 spec R16, plus a version-mismatch failure mode where the smoke runs against the operator's stale local CLI/plugin rather than the post-merge code. This spec corrects the procedure, propagates the fix into #228 spec R16, and adds a recurrence-preventing pytest lint.

## Phases

- **Phase 1: Procedure corrections (docs)** — fix the assertion target (event + path), add Step 0 version-pinning, codify archive-then-cleanup ordering with timeouts, update §Results template, propagate fix into #228 spec R16.
- **Phase 2: Recurrence-prevention lint (code)** — add a pytest lint that scans backlog markdown for `grep -c "<token>"` patterns and verifies each token appears in `bin/.events-registry.md` or in an actual code emission site. Catches this bug class at CI time.
- **Phase 3: Doc cross-reference** — one paragraph in `docs/release-process.md` pointing to #230's procedure pattern so future release-gated tickets are discoverable from the canonical release doc.

## Requirements

1. **Replace the hallucinated assertion target with paired events that actually exist.** Rewrite #230 §Procedure step 3's three grep assertions to use, against `cortex/lifecycle/smoke-release-gate/pipeline-events.log` (NOT `events.log`):
   - `grep -c '"event": "dispatch_start"' cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `≥ 1` with a payload whose `feature` field equals `smoke-release-gate`
   - `grep -c '"event": "dispatch_complete"' cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `≥ 1` with the same `feature` field AND a `ts` strictly greater than the matched `dispatch_start` line's `ts`
   - `grep -c "EPERM" cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `0`
   - `grep -c "Sandbox failed to initialize" cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `0`
   Acceptance: after spec lands, `grep -c "feature_dispatched" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns `0`; `grep -c 'dispatch_start' cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns `≥ 1`; `grep -c 'pipeline-events.log' cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns `≥ 1`. **Phase**: Phase 1.

2. **Propagate the fix into #228 spec R16.** Update `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` R16 (line 53) to remove `feature_dispatched` and `events.log`, replacing with the paired `dispatch_start` + `dispatch_complete` assertion against `pipeline-events.log`. Preserve R16's other claims (tier-enum rationale, release-tag handshake framing, `[release-type: skip]` then `[release-type: minor]` flow). Acceptance: after spec lands, `grep -c "feature_dispatched" cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` returns `0`. **Phase**: Phase 1.

3. **Add Step 0: version-pinning to the merged #228 SHA.** Insert a new step at the top of #230 §Procedure:
   - Operator captures the #228 merge commit SHA on `main`: `git log --grep='#228' --format='%H %s' main | head -3` (operator selects the squash-merge SHA, pastes into §Results).
   - Operator runs `uv tool install --reinstall --no-cache git+https://github.com/charleshall888/cortex-command.git@<#228-merge-sha>`.
   - Operator re-installs the cortex-daytime plugin from the same SHA (or confirms it via `/plugin list` in the Claude session — the plugin must be at or after the #228 merge commit).
   - Operator captures `cortex --version` output into §Results.
   - Acceptance gate on §Results: the captured CLI version line and the merge-commit SHA must both be populated; the procedure declares FAIL if either field is empty when §Acceptance is evaluated.
   Acceptance for the spec edit: after spec lands, `grep -c "uv tool install --reinstall" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns `≥ 1`. **Phase**: Phase 1.

4. **Codify archive-then-cleanup ordering with a wait-and-poll contract.** Rewrite #230 §Procedure steps 4 and 5 to enforce:
   - Step 4 (record): paste operator initials, UTC date, the two paired event lines (`dispatch_start` + `dispatch_complete`), and the captured `git rev-parse HEAD` from the same shell that ran the greps.
   - Step 4.5 (archive): `mkdir -p cortex/lifecycle/release-gate-empirical-from-claude-session/archive/`; `cp cortex/lifecycle/smoke-release-gate/pipeline-events.log cortex/lifecycle/release-gate-empirical-from-claude-session/archive/smoke-pipeline-events-<UTC-date>.log`; `git add` the archive file. The archive lives outside the cleanup target and outside `cortex_command/overnight/sync-allowlist.conf`'s `--theirs` auto-resolve globs.
   - Step 5 (terminate-then-cleanup): `cortex daytime cancel --feature smoke-release-gate`; poll `cortex daytime status --feature smoke-release-gate` at 5-second intervals until it reports no active dispatch or 30 seconds elapse (whichever first); only after that, `git clean -fd cortex/lifecycle/smoke-release-gate/`.
   - Wall-clock timeout for "wait for dispatch event" (covers the entire step 2 + step 3 window): 5 minutes from MCP-tool invocation. On timeout: capture the failure-mode evidence (MCP tool call stdout/stderr, contents of `cortex/lifecycle/smoke-release-gate/` if any) and proceed to the FAIL path.
   Acceptance: after spec lands, `grep -c "cortex daytime status" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns `≥ 1`; `grep -c "git add" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns `≥ 1`; the §Procedure step ordering puts "archive" before "git clean". **Phase**: Phase 1.

5. **Update §Results template to reflect the corrected proof shape.** Replace the existing §Results fields with:
   - `**#228 merge commit SHA on main**:`
   - `**CLI version captured before Step 1** (`cortex --version`):`
   - `**Plugin version captured before Step 1** (`/plugin list` excerpt):`
   - `**Dispatch ID**:`
   - `**Pipeline-events.log absolute path**:`
   - `**EPERM count**:`
   - `**Sandbox-init-failure count**:`
   - `**Paired dispatch event lines** (verbatim from pipeline-events.log, single JSON object each; the `dispatch_complete` `ts` must be strictly greater than the `dispatch_start` `ts`):`
     ```
     dispatch_start:
     dispatch_complete:
     ```
   - `**git rev-parse HEAD** (captured in the same shell that ran the greps):`
   - `**Archive path** (committed before cleanup):`
   - `**Operator initials**:`
   - `**UTC date** (ISO 8601):`
   Acceptance: after spec lands, the §Results section in #230 contains all 12 fields above with blank values (not pre-filled). **Phase**: Phase 1.

6. **Add a pytest lint that catches future event-name hallucinations in backlog markdown.** Add `tests/test_backlog_grep_targets_resolve.py` that:
   - Walks `cortex/backlog/*.md` (skipping `cortex/backlog/archive/`).
   - Extracts every `grep -c "<token>"` and `grep -c '<token>'` pattern from inside fenced code blocks and inline `grep -c` invocations within the file's prose.
   - For each `<token>` that looks like an event name (matches `^[a-z_]+$` and doesn't contain spaces), verifies it appears in EITHER `bin/.events-registry.md` (as a registered event) OR in the codebase as a string literal under `cortex_command/` (using `git grep -F "<token>"`). If neither, the test fails with `UNREGISTERED_GREP_TARGET: <ticket-path>:<line> references "<token>" which is neither a registered event nor an emitted string`.
   - Skips tokens that are common shell builtins, regex metacharacters, or quoted-prose phrases (heuristic: contains a space, starts with `\`, or is in a small allowlist defined in the test).
   Acceptance: `just test` runs `pytest tests/test_backlog_grep_targets_resolve.py -v` exits 0 against the current backlog corpus (which, after R1 + R2 land, contains no unregistered targets). **Phase**: Phase 2.

7. **Wire the lint into the existing test suite without bespoke configuration.** The lint is a pytest test in `tests/` — it inherits the project's existing `pytest` discovery and `just test` recipe. No new justfile recipe required; no CI workflow changes required. Acceptance: `just test 2>&1 | grep -c test_backlog_grep_targets_resolve.py` returns `≥ 1`. **Phase**: Phase 2.

8. **Cross-reference the procedure from `docs/release-process.md`.** Add one paragraph (≤6 sentences) under the "Cut a new release" section pointing to #230 as the canonical example of a release-gated ticket where a manual smoke procedure precedes the `[release-type: minor]` push. The paragraph describes the pattern, not the specific procedure (procedure stays in the ticket per Tradeoffs §D1). Acceptance: `grep -c "230-release-gate-empirical-from-claude-session" docs/release-process.md` returns `≥ 1`. **Phase**: Phase 3.

## Non-Requirements

- **No change to the pipeline tier enum.** `cortex_command/pipeline/dispatch.py:127-235`'s `trivial|simple|complex` enum stays closed; no "interactive" tier added. Adding one would booby-trap every autonomous dispatch per #228 spec R16's rationale.
- **No CI automation of the smoke test in this scope.** The MCP-Inspector + sandbox-exec automation path (Agent 2 web research §5) is acknowledged in §Open Decisions as a future option once the gate becomes recurring; not in scope for #230.
- **No new backlog status (`verified` vs `merged`).** The "merged"-semantics-for-procedure-tickets overload (adversarial review failure mode #7) is acknowledged in §Open Decisions; resolving it requires a `cortex-update-item` schema change that affects all procedure-execution tickets, not just #230.
- **No second smoke variant for the Bash-tool-routed `cortex daytime start` path.** Adding this variant doubles procedure length; the spec gates only the MCP-routed path. The Bash-routed path is regression-tested by spec R15's `tests/test_daytime_cli_detached_spawn.py` (PGID detachment) — necessary-but-insufficient for Bash-path sandbox escape, but accepted within the gate's narrow scope. Documented in §Open Decisions for future tightening.
- **No cryptographic signing of the archive (no cosign, no in-toto attestation).** Adversarial review §3 noted these would be theatre at single-maintainer scale within the operator-error (not operator-malice) threat model. The paired `dispatch_start` + `dispatch_complete` + `git rev-parse HEAD` proof shape is the practical fabricability hardening this spec adopts.
- **No introduction of `docs/runbooks/`.** Tradeoffs §D2 — the procedure stays in the ticket body; a one-paragraph cross-ref in `docs/release-process.md` closes the discoverability gap without standing up a new convention.
- **No standalone `bin/cortex-release-gate-228` helper.** Tradeoffs §D3 — defeats the gate's purpose (a script can be run from any shell, including non-Claude). The "interactive Claude Code session required" constraint is load-bearing.

## Edge Cases

- **Dispatched process crashes silently before writing pipeline-events.log.** Per `cortex_command/overnight/daytime_pipeline.py:380-388`, "daytime already running" exits with code 1 BEFORE any pipeline-events.log write. Expected behavior: the 5-minute wall-clock timeout (R4) fires; operator captures MCP-tool stdout/stderr and contents of `cortex/lifecycle/smoke-release-gate/` (if any) for the failure ticket; procedure transitions to FAIL path.
- **`cortex daytime status` returns "no PID file" within 30s of MCP-tool invocation.** Indicates the dispatch failed silently before writing `daytime.pid`. Expected behavior: early-exit from the wait loop; same FAIL-path capture as the wall-clock timeout case.
- **Operator's local plugin or CLI version doesn't match the captured #228 merge SHA.** The §Acceptance gate (R3) declares FAIL because the §Results SHA field doesn't match. Operator must re-install before re-running; do NOT proceed to §Release-tag handshake.
- **Concurrent `[release-type:]` markers from other tickets within one auto-release cycle.** `auto-release.yml`'s `concurrency: { group: auto-release, cancel-in-progress: true }` collapses concurrent pushes into a single release that resolves marker precedence as `skip > major > minor > patch`. Before pushing the §Release-tag empty commit, operator runs `git log <latest-tag>..HEAD --grep='\[release-type:' --oneline` and confirms no unresolved markers from other tickets are pending. If any are pending, coordinate with the other operator before pushing.
- **`git clean -fd` fails (file lock, permissions).** Operator manually resolves before re-running; do not proceed to §Release-tag handshake until cleanup completes (the archive is already committed, so the working tree must be clean before the release commit lands).
- **`/plugin list` doesn't surface a SHA-level version for cortex-daytime.** The plugin marketplace exposes plugin versions, not SHAs. Operator records the plugin version string returned by `/plugin list`; reconciliation between plugin version and #228 merge SHA is performed by checking that the plugin's published version corresponds to a tag at or after the #228 merge SHA (or the operator re-installs from a git ref pointing at the #228 SHA).
- **MCP tool not visible in the Claude session.** Operator types `/mcp` in the session and confirms `cortex-daytime` is listed as `connected`. If not, the procedure FAILs at Step 1; operator re-installs the plugin.

## Changes to Existing Behavior

- **MODIFIED: `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` §Procedure** — Step 0 (version-pin), Step 1 unchanged, Step 2 unchanged, Step 3 (assertions: paired events + correct path), Step 4 (record + git rev), Step 4.5 (archive), Step 5 (cancel-then-poll-then-clean). §Results template (12 fields). §Acceptance updated to reflect new §Results gate.
- **MODIFIED: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` R16** — `feature_dispatched` and `events.log` references replaced with `dispatch_start` + `dispatch_complete` against `pipeline-events.log`. R16's other framing (tier-enum rationale, release-tag handshake) preserved.
- **ADDED: `tests/test_backlog_grep_targets_resolve.py`** — new pytest lint that fails on unregistered grep-target tokens in backlog markdown. Runs as part of `just test`.
- **ADDED: paragraph in `docs/release-process.md`** under "Cut a new release" pointing to #230 as the canonical release-gated-ticket pattern.

## Technical Constraints

- **Dispatch event path is `pipeline-events.log`, not `events.log`.** Per `cortex_command/overnight/daytime_pipeline.py:220,222`, `pipeline_events_path` is the per-dispatch log and carries `dispatch_start`/`dispatch_complete`/`dispatch_progress` plus the EPERM and "Sandbox failed to initialize" strings under sandbox-blocked dispatches. `events_path` (events.log) is the higher-level batch loop's log. Verified empirically against `cortex/lifecycle/lead-refine-4-complexity-value-gate/pipeline-events.log:234`.
- **`dispatch_start` fires before the first SDK round-trip.** Per `cortex_command/pipeline/dispatch.py:660`, emitted as the SDK client is constructed. A child instantly killed by EPERM after this point still registers `dispatch_start: ≥ 1` — which is why the paired-with-`dispatch_complete` requirement is load-bearing.
- **Auto-release marker regex requires standalone-line position.** `bin/cortex-auto-bump-version` parses `(?im)^\s*\[release-type:\s*(major|minor|skip)\s*\]\s*$`; marker MUST be the entire content of its own line (modulo whitespace). Precedence: `skip > major > minor > patch`. Recent commits (`5776ce86`, `94eddf11`, `ab2bb308`) use the marker as the only content of the body following a blank line after the subject.
- **`cortex init` umbrella `cortex/` grant.** Per `cortex_command/init/handler.py:194-198`, the umbrella grant covers `cortex/lifecycle/smoke-release-gate/` and `cortex/lifecycle/release-gate-empirical-from-claude-session/archive/`; no extra allowWrite entry needed.
- **`sync-allowlist.conf` does NOT auto-`--theirs` `archive/` subdirs.** Per `cortex_command/overnight/sync-allowlist.conf`, the globs key on `lifecycle/sessions/*/` and `lifecycle/*/research.md|spec.md|plan.md|agent-activity.jsonl|pipeline-events.log`. The archive destination is safe from auto-resolve.
- **#228 surface dependency.** This spec assumes #228 has merged to `main` carrying `[release-type: skip]`. The procedure depends on #228 spec R10 (`confirm_dangerously_skip_permissions: Literal[True]` gate), R12 (`cortex daytime cancel --feature <slug>`), R13 (`cortex daytime status --feature <slug>` reads filesystem state), and the cortex-daytime plugin's MCP tool name `mcp__plugin_cortex-daytime_cortex-daytime__daytime_start_run`. If any of these contracts drift during #228 implementation, this spec must be updated before the procedure is executed.
- **The MCP-server stdout is reserved for JSON-RPC.** Per `docs/mcp-server.md:22`, the MCP server logs only to stderr; stdout is the JSON-RPC stream. Operator's MCP tool call surface (in the Claude session UI) is the tool-result display, not raw stdout.

## Open Decisions

- **Bash-tool-routed daytime smoke variant (Adversarial OQ6).** Adding a second smoke pass for `cortex daytime start --feature smoke-release-gate-cli` via Bash with `dangerouslyDisableSandbox` would cover both spec-claimed harness-escape paths (MCP-unsandboxed AND Bash-disable-sandbox). Deferred because (a) it doubles procedure length, (b) spec R15's `tests/test_daytime_cli_detached_spawn.py` already provides PGID-detachment regression coverage for the Bash path even though it doesn't prove sandbox escape, and (c) the bash-path failure mode is operationally distinct (Bash disable-sandbox is an explicit operator grant, not a harness-inferred property) — a regression would surface differently. Reason it can't be resolved at spec time: requires a judgment call on procedural-burden vs coverage-completeness that depends on how often this gate will actually be re-run, which is unknown until #228 ships and the gate runs at least once.
- **`merged` vs `verified` status for procedure-execution tickets (Adversarial OQ7).** Backlog convention overloads `merged` to cover both code-in-main AND procedure-executed. Resolving via a new `verified` status would require a `cortex-update-item` schema change that affects ALL procedure-execution tickets, not just #230. Reason it can't be resolved at spec time: this is a backlog-vocabulary policy decision with cross-ticket scope; #230 should not be the forcing function. Document the overload here; open a separate ticket for the policy change.
- **CI automation of the smoke test via MCP-Inspector + sandbox-exec (Web research §5).** Long-term durable path if the gate becomes recurring (multi-release frequency). Requires building a Claude-Code-equivalent Seatbelt profile in CI and verifying it tracks Anthropic's profile evolution. Reason it can't be resolved at spec time: ROI depends on gate-execution frequency, which is unknown pre-#228-merge. Re-evaluate after the first 2–3 release cuts.

## Proposed ADR

None considered. The decisions in this spec (paired events as proof shape, archive-then-cleanup ordering, lint as recurrence prevention, doc cross-ref over runbook extraction) reuse existing project conventions (events-registry pattern, sync-allowlist semantics, `bin/cortex-check-*` lint pattern, ticket-body-as-runbook convention). None meet the three-criteria gate (Hard to reverse + Surprising without context + Real trade-off) for ADR promotion.

## References

- `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` — ticket body (target of R1, R3, R4, R5)
- `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` line 53 — R16 (target of R2)
- `cortex/lifecycle/release-gate-empirical-from-claude-session/research.md` — research artifact
- `cortex_command/pipeline/dispatch.py:660` — `dispatch_start` emission
- `cortex_command/overnight/daytime_pipeline.py:220,222,380-388` — pipeline-events.log path; silent-fail exit path
- `cortex_command/overnight/events.py:36` — closed event vocabulary
- `bin/.events-registry.md` — lint reference for R6
- `bin/cortex-auto-bump-version` — release marker regex
- `bin/cortex-check-events-registry`, `tests/test_check_events_registry.py` — lint pattern precedent for R6
- `.github/workflows/auto-release.yml` — concurrency + marker semantics
- `cortex_command/overnight/sync-allowlist.conf` — post-merge sync globs (archive destination safe)
- `docs/overnight-operations.md:583-630` — per-spawn sandbox enforcement + seatbelt-probe pattern
- `docs/internals/auto-update.md:62-70` — release-ritual contract
- `docs/mcp-server.md:22,46-52` — stdout reservation + confirm-gate semantics
- `cortex/adr/0001-file-based-state-no-database.md`, `0002-cli-wheel-plus-plugin-distribution.md`, `0003-per-repo-sandbox-registration.md`
