# Research: Manual release-gate procedure for #230 (gates #228 daytime dispatch release tag)

## Codebase Analysis

### Files this lifecycle will create/modify

**Mandatory edits**
- `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` — ticket body §Procedure / §Results / §Acceptance updated; add `spec: cortex/lifecycle/release-gate-empirical-from-claude-session/spec.md` to frontmatter per refine convention.
- `cortex/lifecycle/release-gate-empirical-from-claude-session/spec.md` — new spec file. Lifecycle dir already exists (currently contains `events.log` with a single `clarify_critic` row).
- `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` — must update R16 in two places to fix the `feature_dispatched` hallucination if the corrected-name decision lands (see Open Questions).
- One paragraph cross-reference in `docs/release-process.md` (per Agent 4 recommendation D1) pointing to #230's procedure pattern.

**Files referenced/touched at procedure runtime (documented in spec, not committed by spec)**
- `cortex/lifecycle/smoke-release-gate/events.log` AND `cortex/lifecycle/smoke-release-gate/pipeline-events.log` — created by dispatched daytime pipeline; cleanup target.
- `cortex/lifecycle/release-gate-empirical-from-claude-session/archive/smoke-release-gate-events-{UTC}.log` — tracked archive destination outside cleanup target; safe from `sync-allowlist.conf` auto-`--theirs` (which keys on `lifecycle/sessions/*/` and named lifecycle files, NOT `archive/` subdirs).

### Auto-release workflow contract

`.github/workflows/auto-release.yml`:
- Triggers on `push: branches: [main]`, `workflow_dispatch`, and a weekly cron probe.
- Workflow-level filter `!startsWith(github.event.head_commit.message, 'Release v')` skips self-retrigger.
- Version-bump delegated to `bin/cortex-auto-bump-version` which parses standalone-line regex `(?im)^\s*\[release-type:\s*(major|minor|skip)\s*\]\s*$` — marker MUST be entire content of its own line (modulo whitespace).
- Precedence: `skip > major > minor > patch (default)`. `BREAKING:` / `BREAKING CHANGE:` standalone-line is major-bump fallback.
- Concurrency: `group: auto-release, cancel-in-progress: true`. Under push storms, older runs cancel; latest push triggers a release covering ALL pending markers since last tag.
- Recent precedent in commits: `[release-type: skip]` markers routinely used (`5776ce86`, `94eddf11`, `ab2bb308`). No `[release-type: minor]` example yet — this would be a first.
- The auto-release run rewrites `CLI_PIN[0]` in `plugins/cortex-overnight/server.py` via `bin/cortex-rewrite-cli-pin` and commits the rewrite with `[release-type: skip]` (defense-in-depth so the rewrite doesn't loop).

### Daytime CLI and MCP tool (post-#228)

Per `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` (status: refined, not yet merged):
- MCP tool name: `mcp__plugin_cortex-daytime_cortex-daytime__daytime_start_run`. Plugin path: `plugins/cortex-daytime/` (separate from cortex-overnight per spec R9). The 64-char tool-name budget is checked in spec Edge Cases (57 chars — under budget).
- `cortex daytime cancel --feature <slug>` (NOT `--session-id` — asymmetric with overnight). Per spec R12 + plan Task 8: reads `cortex/lifecycle/<feature>/daytime.pid`, signals process group via `os.killpg(pgid, SIGTERM)`.
- Both `daytime_start_run` and `daytime_cancel` require `confirm_dangerously_skip_permissions: Literal[True]` per spec R10.
- Task 17 was deleted from plan.md (line 206 HTML comment, line 218 risk entry) and split into #230 — the §References "Plan reference" parenthetical in #230 needs updating to reflect this (Task 17 no longer exists).

### Events.log contract — critical inconsistency

**`feature_dispatched` is NOT an emitted event anywhere in the codebase.** Verified:
- `grep -rn feature_dispatched cortex_command/` returns 0 hits.
- `cortex_command/overnight/events.py:36` enumerates the closed event vocabulary; `FEATURE_DISPATCHED` is not present.
- Test reference `test_execute_feature_dispatches_repair_on_conflict_event` (`cortex_command/pipeline/tests/test_repair_agent.py:334`) is a function name, not an event string.

**The closest actually-emitted events at dispatch time** (`cortex_command/pipeline/dispatch.py:660`):
- `dispatch_start` — emitted as SDK client is constructed, BEFORE first SDK round-trip. A child instantly killed by EPERM after this point still registers `≥ 1`.
- `dispatch_progress`, `tool_call`, `tool_result`, `turn_complete`, `dispatch_complete`, `dispatch_error` — progress events during dispatched task.

**These events are written to `pipeline-events.log`, NOT `events.log`.** Verified empirically against `cortex/lifecycle/lead-refine-4-complexity-value-gate/`:
- `grep -c dispatch_start events.log` = 0
- `grep -c dispatch_start pipeline-events.log` = 11

`cortex_command/overnight/daytime_pipeline.py:220,222` confirms the path split: `events_path` (events.log) is the higher-level batch loop's log; `pipeline_events_path` (pipeline-events.log) is the per-dispatch log. The strings `EPERM` and `"Sandbox failed to initialize"` both appear in `pipeline-events.log` under sandbox-blocked dispatches (verified in the same corpus).

**Implication**: The ticket's three assertions (`grep -c "EPERM" events.log`, `grep -c "Sandbox failed to initialize" events.log`, `grep -c "feature_dispatched" events.log`) fail at TWO levels:
1. Wrong event name (`feature_dispatched` doesn't exist).
2. Wrong file path (`events.log` instead of `pipeline-events.log`).

The clarify Q1 resolution "keep as-is, defend in spec" was made on a false premise. This must be revisited in spec.

### Tracked-path archive convention

- `git clean -fd` removes ONLY untracked files. A git-added archive file is safe.
- Archive sequence: (1) `mkdir -p cortex/lifecycle/release-gate-empirical-from-claude-session/archive/`; (2) `cp cortex/lifecycle/smoke-release-gate/pipeline-events.log archive/smoke-pipeline-events-{UTC}.log` (and events.log if any signal-of-interest lives there); (3) `git add` archive files; (4) commit; (5) ONLY THEN `git clean -fd cortex/lifecycle/smoke-release-gate/`.
- `cortex_command/overnight/sync-allowlist.conf` auto-`--theirs` globs: `lifecycle/sessions/*/`, `lifecycle/*/research.md|spec.md|plan.md|agent-activity.jsonl|pipeline-events.log`, `lifecycle/pipeline-events.log`, `backlog/index.md`, `backlog/archive/*`, `backlog/[0-9]*-*.md`. **`archive/` subdir of a lifecycle dir is NOT in this list** — safe destination.
- Note: top-level `lifecycle/pipeline-events.log` IS in the auto-resolve list. The procedure's smoke pipeline-events.log lives at `lifecycle/smoke-release-gate/pipeline-events.log` (per-feature path), which IS in the auto-resolve glob `lifecycle/*/...|pipeline-events.log`. So if any of that file lingers in post-merge sync window, it could be auto-resolved with `--theirs` (remote wins). The archive destination (not in the glob) is safe.

### Sandbox writeability

`cortex init` (per `cortex_command/init/handler.py:194-198` + `cortex_command/init/settings_merge.py:139-211`) registers an umbrella `cortex/` grant (with trailing slash) in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. The dispatched pipeline can write `events.log`, `pipeline-events.log`, `daytime.pid`, `daytime-dispatch.json`, `daytime-result.json`, the worktree dir — no extra allowWrite entry needed.

### In-flight guard interaction

- Pre-install in-flight guard at `cortex_command/install_guard.py` reads `~/.local/share/overnight-sessions/active-session.json` + verifies `runner.pid` via psutil. Spec R3 extends to scan `cortex/lifecycle/*/daytime.pid` files. Bypass: `CORTEX_ALLOW_INSTALL_DURING_RUN=1` inline.
- `cortex daytime cancel --feature smoke-release-gate` is NOT an install-mutation path — guard does not trigger. Safe.
- During the smoke procedure, any concurrent `cortex` install-mutation path will be blocked while the spawned daytime dispatch is alive. After cleanup completes, the guard clears.

### Conventions to follow

- **Frontmatter**: keep `type: chore`, `tags: [daytime-pipeline, mcp, release-gate, manual-verification]`, `complexity: simple`, `criticality: high`, `areas: [overnight-runner]`, `blocked_by: [228]`. Add `spec: cortex/lifecycle/release-gate-empirical-from-claude-session/spec.md`.
- **Spec markdown structure**: use the established spec template (`## Problem Statement`, `## Requirements`, `## Non-Requirements`, `## Edge Cases`, `## Changes to Existing Behavior`, `## Technical Constraints`, `## Open Decisions`) as seen in #228 spec.
- **Release-cut commit format**: short imperative subject (max 72 chars, capitalized, no trailing period), blank line, body containing `[release-type: minor]` on its own line plus a short prose pointer (Proof: cortex/backlog/230-...md §Results).
- **Procedure pattern**: numbered list under `## Procedure`; non-prefilled blank-field operator-paste scaffolding under `## Results`; binary-asserted `## Acceptance` criteria; cross-references under `## References`.
- **Seatbelt-probe pattern** (`docs/overnight-operations.md:607-623`): capture process output to `$TMPDIR` files via `tee`/`printf`, read the file (not turn-final paraphrase); emit paraphrase-free grep-able events. The smoke procedure should follow this pattern when capturing operator-pasted evidence.

## Web Research

### 1. Manual release-gate patterns

Mature OSS projects rarely formalize a CI-impossible manual gate as a release blocker. Where one exists, the dominant patterns are NOT empty-commit-with-marker:
- **GitHub Environment Protection Rules with required reviewers** — workflow pauses; designated humans approve in GitHub UI; approval logged with identity and timestamp by GitHub itself.
- **`workflow_dispatch` as pre-pipeline gate** — operator fills typed form inputs (version, dry-run flag, environment); inputs themselves become audit record.
- **Issue-based approval** (`trstringer/manual-approval`) for free-tier private repos that can't use environments.

I did not find a mature OSS project that uses empty-commit-with-marker-on-main. release-please and semantic-release parse merged conventional commits — they do not require a separate marker commit because the release decision is inferred from the change set.

### 2. Commit-message-driven release workflows

Dominant convention is Conventional Commits parsed by release-please or semantic-release using git trailers (RFC 822 / `git interpret-trailers`), not subject-line regex:
- `feat:` / `fix:` / `BREAKING CHANGE:` footer → semver inference.
- release-please's `Release-As: x.y.z` footer is the closest analog to `[release-type:]`.
- Failure modes: wrong marker on wrong commit (subject-regex matches; trailer doesn't); race conditions (release-please serializes through a release PR); marker drift (subject is easy to mistype; trailers are parsed by `git interpret-trailers --parse`).

Better patterns than empty-commit-on-main: git trailer parsed by `git interpret-trailers --parse`; `workflow_dispatch` typed enum; tag-push trigger.

### 3. Non-fabricable proof

**Direct answer: a verbatim paste of an event-log line is NOT non-fabricable. It is trivially fabricable.** The operator (human or LLM) can type the expected line into §Results without ever running the test. The "Audit Trail Paradox" (https://dev.to/arkforge-ceo/the-audit-trail-paradox-why-your-llm-logs-arent-proof-1c21) addresses this directly: independent evidence is needed that each step happened, witnessed by a party with no stake. SLSA cites "non-falsifiable provenance" as the hardest requirement at Level 3.

Established patterns for genuinely non-fabricable proof, in increasing rigor:
1. **Self-attestation with cryptographic signature** (Sigstore/cosign with custom predicate; keyless Fulcio OIDC ties operator's GitHub identity to result).
2. **in-toto/witness attestations** for the test execution itself.
3. **Upload artifact, let CI re-grep** — split trust between operator (produces log) and gate (verifies log).
4. **Re-execute greps in CI on uploaded artifact**.
5. **Timestamped external witness** (RFC 3161 timestamp authority or Sigstore Rekor transparency log).

Bottom line: the current "paste three grep lines into the ticket" is paste-fabricable. Minimal upgrade: upload log artifact + CI re-greps. Rigorous upgrade: cosign-signed attestation.

### 4. macOS Seatbelt sandbox-escape verification

Established baseline: every child process spawned from a Seatbelt-sandboxed parent **inherits the parent's sandbox**; the sandbox cannot be removed from inside. Confirmed across Apple Developer Forums, third-party deep-dives (Pierce Freeman), and the Claude Code Sandboxing Camp materials.

Known exceptions where a child can escape inheritance:
- `LaunchServices` `open -a` (hands launch to launchd; new process gets fresh profile).
- `excludedCommands` in Claude Code with glob matching (Issue #40831).
- **MCP servers spawned by Claude Code at startup** — per [MCP STDIO RCE writeup](https://www.penligent.ai/hackinglabs/mcp-stdio-rce-the-agent-execution-boundary-failed/) and [Microsoft VS Code issue #294029](https://github.com/microsoft/vscode/issues/294029), local MCP servers launched as stdio child processes are generally **not subjected to the same sandbox** as the agent's bash tool. This is exactly the "escape" the project's release-gate verifies.

Programmatic "am I sandboxed?" detection: undocumented `libsystem_sandbox.dylib` APIs (`sandbox_check`, `sandbox_check_by_audit_token`); BSD `sysctl` queries; empirical (attempt known-blocked syscall, observe EPERM). Karol Mazurek's [Sandbox Detector](https://karol-mazurek.medium.com/sandbox-detector-4268ab3cd361) covers the C-level API.

**On the specific three-grep gate**: sufficient as outcome-level "no sandbox-induced syscall failures and reached dispatch path," but has gaps as PROOF of escape. A truly sandbox-trapped subprocess could produce 0 EPERMs if it never tried anything sandboxable. A stronger empirical test would have the spawned subprocess **actively probe** the boundary (write to path denied in parent's profile; call `sandbox_check()`; attempt `open("/private/etc/sudoers", O_RDONLY)`). Converts gate from "absence of negative signal" to "presence of positive signal."

### 5. MCP testing patterns

**The "real interactive Claude Code session required" constraint is more narrowly scoped than it appears.** It's not that MCP itself requires a real Claude session — MCP can be scripted via `@modelcontextprotocol/inspector` CLI (`npx @modelcontextprotocol/inspector --cli node build/index.js --method tools/call --tool-name mytool --tool-arg key=value`). Test harnesses (`mcptest`, `mcp-test`, `Bellwether`, `MCPSpec`) are MIT-licensed.

What MCP Inspector CANNOT simulate: the **launching-process identity**. If the gate's concern is "does a subprocess spawned by Claude Code escape Claude Code's Seatbelt profile" (as distinct from "does a subprocess spawned by Inspector escape Inspector's sandbox"), then the parent matters because the parent's profile is what gets inherited. Inspector running outside Claude Code is not inside Claude Code's Seatbelt to start with — any subprocess it spawns is trivially "escaped" but proves nothing about production.

Mitigation paths if the gate becomes recurring: (1) wrap Inspector in `sandbox-exec` with a profile approximating Claude Code's, or (2) verify whether non-interactive Claude Code (`--print`) exercises the same dispatch path and use it in CI.

## Requirements & Constraints

### `cortex/requirements/project.md`

- **Defense-in-depth for permissions** (line 40): "Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface." — the release-gate exists precisely because sandbox enforcement is the load-bearing security mechanism for daytime dispatch.
- **Destructive operations preserve uncommitted state** (line 41): Cleanup scripts SKIP on uncommitted state; inline destructive sequences extract into named scripts. The procedure's `git clean -fd` step should not bake destructive sequences inline without uncommitted-state guards.
- **Solution horizon** (Philosophy of Work, line 21): A scoped phase of a multi-phase lifecycle is not a stop-gap. Test: current knowledge, not prediction. Applies to the gate procedure itself — don't over-engineer for unknown future harness changes; spec R16 already cites Alternative A / launchctl as durable upgrade path if assumptions shift.
- **Complexity** (line 19): "Must earn its place by solving a real problem now. When in doubt, simpler wins."

### `cortex/requirements/pipeline.md`

- **MCP server section** (line 153): `confirm_dangerously_skip_permissions: Literal[True]` operational gate is symmetric for daytime per #228 spec R10. Pydantic-enforced; cannot be bypassed by FastMCP.
- **Pre-install in-flight guard** (line 154): Per spec R3 extension, scans daytime PID files. Smoke test's own dispatch creates a transient pre-install guard trip until the dispatched process clears its PID file. Cancel-bypass carve-out exists at `install_guard.py:140-143` for overnight cancel; spec R3 should mirror this for daytime cancel (or `daytime cancel` is not an install-mutation path so it's moot).
- **Edge case** (line 167): `.vscode`/`.idea` hardcoded sandbox denies are permanently blocked by Claude Code binary even with allowWrite — not relevant here (procedure doesn't touch those dirs).

### `cortex/requirements/glossary.md`

Status: ABSENT (referenced from project.md's Global Context but not present in tree). Recorded as `cortex/requirements/glossary.md (skipped: file absent)` per the load-requirements.md protocol.

### `cortex/adr/`

- **ADR-0001 (file-based state)**: Release-gate evidence lives in `cortex/` umbrella, reviewable in PR alongside the code that produced it.
- **ADR-0002 (CLI wheel + plugin distribution)**: The `[release-type: minor]` follow-up commit drives auto-release / CLI_PIN bump. Release-gate must prove daytime works BEFORE tag fires so broken daytime isn't pinned into the published wheel. Per spec R16, the #228 implementation PR carries `[release-type: skip]` precisely to defer the tag until #230 marks `merged`.
- **ADR-0003 (per-repo sandbox registration)**: Smoke test requires `cortex init` has registered the `cortex/` umbrella; otherwise dispatched process can't write events.log without sandbox prompts.

### `docs/overnight-operations.md` — Per-spawn sandbox enforcement (lines 583-630)

**Documented threat model boundary** (line 599): "Sandbox enforcement covers Bash-tool subprocess writes via OS-kernel rules. It does NOT cover Write-tool or Edit-tool calls (which run in-process in the SDK and bypass the sandbox per Anthropic #26616...) nor MCP-server-routed subprocess writes (MCP servers run unsandboxed at hook trust level)."

**Seatbelt probe pattern** (lines 607-623): kernel-anchored runtime re-attestation, invoked every session before round 1. Spawns `claude -p` under tight deny set + `allow_paths=[resolved-$TMPDIR]` and runs `pytest tests/test_worktree_seatbelt.py -v`. Agent writes pytest stdout/exit code to `$TMPDIR` files via `tee`/`printf`; probe reads files (not turn-final paraphrase) and computes `sha256` on captured stdout. Emits JSONL F-row to per-session `overnight-events.log` AND tracked `cortex/lifecycle/seatbelt-probe.log`.

**The smoke procedure should follow this pattern**: capture process output to a file via `tee`, read the file (not paraphrase), emit grep-able events.

### `docs/internals/auto-update.md`

Release-ritual contract (lines 62-70): push to main → auto-release.yml computes next semver → rewrites `CLI_PIN[0]` → commits with `[release-type: skip]` → tags `vX.Y.Z` → push branch + tag via PAT → release.yml fires on tag → cli-pin-lint → wheel build via `uv build --wheel` → GitHub Release → marketplace fast-forward (Layer 1) → next MCP tool call (Layer 2) triggers CLI reinstall.

Bash-tool subprocess dispatches that shell out to `cortex …` directly (not via MCP) do NOT trigger Layer 2 (`#145` wontfix). Implication: an operator running `cortex daytime cancel` from Bash won't auto-update the CLI from a stale install.

### `docs/mcp-server.md`

`overnight_start_run` operational gate (lines 46-52): `confirm_dangerously_skip_permissions: true` (literal value `true`; any other value or omission rejected). Symmetric for daytime per spec R10. The literal-True Pydantic gate cannot be bypassed.

Stdout reservation (line 22): "MCP server logs only to `stderr`; `stdout` is reserved for the JSON-RPC stream."

### `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` — R16 verbatim (line 53)

> "**Release-gate handed off to backlog #230 (not inside this lifecycle)**: empirical verification that `daytime_start_run` invoked from a real Claude session reaches `feature_dispatched` with zero EPERM and zero sandbox-init-failure events. **The cortex pipeline has no native 'interactive complexity tier'** (`cortex_command/pipeline/dispatch.py:127-235` enforces a closed `trivial|simple|complex` enum and raises `ValueError` on anything else), so this gate cannot live inside this lifecycle's `plan.md` without booby-trapping every autonomous run. The procedure lives in `cortex/backlog/230-...md` and gates **the production release tag**, not this lifecycle's `feature_complete` event. The implementation PR's merge commit carries `[release-type: skip]`; the version tag fires only after a follow-up commit with `[release-type: minor]` (or major), which the operator pushes after marking #230 `merged`. Documentation alone is NOT sufficient — #230's verification cross-references an operator-pasted `feature_dispatched` event line against an external `cortex/lifecycle/smoke-release-gate/events.log` to prevent fabrication. **Verification within this lifecycle**: `test -f cortex/backlog/230-...md && grep -c \"blocked_by: \[228\]\" cortex/backlog/230-...md = 1`."

**R16 contains the same `feature_dispatched`-in-`events.log` hallucination as #230.** Fixing one without the other leaves the bug propagated. R16 also contains the constraint: the procedure must "cross-reference an operator-pasted event line against an external events.log to prevent fabrication" — Agent 2's web research showed paste-cross-reference is fabricable in the absence of CI-side verification.

### Scope boundaries (from R16 + research)

- **In scope for #230**: empirical from-Claude-session smoke test; cross-reference of dispatch event line against the dispatched-process log file; gating the `[release-type: minor]` follow-up commit.
- **Out of scope for #230**: `feature_complete` of #228 itself (fires on PR merge with `[release-type: skip]`); any change to the pipeline tier enum (explicitly rejected — would booby-trap autonomous runs); CI automation of the smoke test (defer until gate becomes recurring).
- **Spec R15 caveat**: pytest `tests/test_daytime_cli_detached_spawn.py` proves PGID detachment only — necessary-but-insufficient. R16 (this ticket) closes the sandbox-escape gap.
- **Spec Technical Constraint** (line 108): "MCP-unsandboxed" is cortex's inference, not Anthropic doctrine. 12-month confidence horizon ~80-85%. This is what the smoke test validates at release time.
- **Spec Non-Requirement** (line 63): No real `launchctl bootstrap`-based detachment (Alternative A): explicitly deferred. Documented as durable upgrade path if Anthropic restricts `dangerouslyDisableSandbox: true` or sandboxes MCP servers upstream.

## Tradeoffs & Alternatives

### Dimension A — Release-tag handshake mechanism

- **A1 (current)** — empty commit on main with `[release-type: minor]` body marker. Pros: only path that composes with existing `bin/cortex-auto-bump-version` + `auto-release.yml` infrastructure; auto-release performs CLI_PIN rewriting + tagging for operator; cheap to revert; composes with `v*` tag protection. Cons: empty commits "pollute" history; marker typos like `[release_type: minor]` silently degrade to patch bump.
- **A2** — operator manually pushes git tag. Pros: structural encoding in git tag namespace. **Cons (failure-of-alternative)**: breaks CLI_PIN auto-bump coupling — `release.yml`'s `cli-pin-lint` job (release.yml:28-77) hard-fails because existing CLI_PIN points at previous tag; operator must manually edit CLI_PIN first. This is the documented "emergency tag" path (release-process.md:102-108), framed as unhappy fallback. Conflicts with recommended `v*` tag protection. Diverges from established mental model.
- **A3** — release PR with CHANGELOG bump. Pros: maximum review surface. Cons: no existing CHANGELOG-driven release workflow; auto-release does NOT read CHANGELOG.md; single-maintainer repo doesn't benefit from PR ceremony.
- **Recommendation: A1.** Only path that composes with existing infrastructure without divergence. Mitigation for "history pollution": make commit subject self-describing (`Cut release v0.X.0 — gated by #230 smoke proof`).

### Dimension B — Non-fabricable proof shape

- **B1 (current)** — paste verbatim event line into §Results. Pros: zero new infrastructure. Cons: cleanup destroys source-of-truth; pasting is fabricable.
- **B2** — archive entire events.log/pipeline-events.log to tracked path; §Results references archive. Pros: archive IS the proof; composes with clarify-mandated archive-before-cleanup; accumulates historical record. Cons: archive is created by operator `cp` — also fabricable (operator can `cp` any file).
- **B3** — SHA-256 of events.log pasted into §Results. **Cons (failure-of-alternative)**: solves wrong problem (threat model is operator forgetting to run gate, not malicious fabrication); SHA-checks are theatre at single-maintainer scale; no precedent.
- **Recommendation: B2 with B1 fragment retained.** §Results contains operator initials, UTC date, verbatim event line for at-a-glance scan, AND archive path. Archive is load-bearing proof.
- **Adversarial caveat (Agent 5)**: B2 doesn't fundamentally fix fabricability — operator can `cp` any file to the archive path. Practical hardening within the operator-error threat model: (a) require paired temporally-related event lines (e.g., `dispatch_start` line + `dispatch_complete` line with matching feature slug, ts-after), (b) require `git rev-parse HEAD` taken inside the same shell that ran the grep, (c) embed dispatch ISO date in pasted lines and require it within 24h of §Results UTC date. Reframe prose honestly as "self-audit checklist resistant to common operator-error patterns" not "non-fabricable cryptographic proof."

### Dimension C — Cleanup ordering

- **C1 (current + clarify)** — archive then `git clean -fd`. Pros: keeps tree clean before release commit; forces archive step; matches smoke-= ephemeral semantics. Cons: no re-grep window after cleanup (moot — archive is right there).
- **C2** — defer cleanup until after release tag. Pros: audit window. Cons: auto-release completes in minutes; release commit lands with untracked `smoke-release-gate/` in working tree (sequencing footgun if operator stages it).
- **C3** — no cleanup; persist as dated historical artifact. **Cons (failure-of-alternative)**: conflicts with fixed feature-name string `smoke-release-gate` (repeated runs clobber unless feature name carries date); B2 already provides historical archive in a single canonical place.
- **Recommendation: C1** (as already clarified).

### Dimension D — Procedure deliverable

- **D1 (current)** — procedure in backlog ticket body; §Results in-place. Pros: single source of truth; matches every other backlog convention; cheap to update. Cons: not discoverable from `docs/release-process.md` unless cross-linked.
- **D2** — extract to `docs/runbooks/release-gate-228.md`. **Cons (failure-of-alternative)**: `docs/runbooks/` does not exist (would establish new pattern with maintenance cost); for one-shot gate, extraction puts procedure in one file and proof in another; CLAUDE.md "solution horizon" says deliberately-scoped phase is not stop-gap awaiting generalization.
- **D3** — shell script `bin/cortex-release-gate-228`. **Cons (failure-of-alternative)**: the non-fabricable part is the *human running it from an interactive Claude session*; a script defeats the gate's purpose since it can be run from anywhere; versioning headache for ticket-numbered helpers.
- **Recommendation: D1 + one-paragraph cross-ref in `docs/release-process.md`.**

### Recommended composite

A1 + B2 (with B1 fragment + Agent 5 hardening) + C1 + D1.

## Adversarial Review

### Failure modes and edge cases

1. **`feature_dispatched` does not exist (hallucination propagated from spec R16)** — MUST FIX. Verified: 0 hits in codebase; not in `cortex_command/overnight/events.py:36` closed vocabulary. The closest actually-emitted event is `dispatch_start` (`cortex_command/pipeline/dispatch.py:660`), but `dispatch_start` fires before first SDK round-trip — a child instantly killed by EPERM after this point still registers `≥ 1`. **Mitigation**: Rewrite assertions to use events that exist AND prove the child actually ran. Candidate: (a) `dispatch_start` AND subsequent `dispatch_progress` AND `dispatch_complete` with non-failed outcome, OR (b) `task_output` (only fires after dispatched session executed and emitted content), OR (c) the higher-level `feature_complete` event (which fires after the full feature loop). Both spec R16 (two occurrences) and #230 ticket need the fix to avoid bug propagation.

2. **Wrong file path: `events.log` vs `pipeline-events.log`** — MUST FIX. Verified empirically: `dispatch_start` lives in `pipeline-events.log`, NOT `events.log`. Even with corrected event name, the procedure's grep targets fail 100% of the time at the current path. **Mitigation**: Rewrite grep targets to `cortex/lifecycle/smoke-release-gate/pipeline-events.log`. Consider also greping `events.log` for a separate higher-level signal.

3. **B2 archive doesn't fully fix non-fabricability** — operator can `cp` any file to the archive path. Practical mitigation: structure procedure so operator can't easily fool *themselves*. Pair `dispatch_start` + `dispatch_complete` lines with matching feature slug and ts-after; require `git rev-parse HEAD` from same shell; embed dispatch ISO date and require recency. Reframe prose as "self-audit checklist," not "non-fabricable cryptographic proof."

4. **Plugin/CLI version mismatch — smoke runs against stale local install** — MUST FIX. After #228 merges with `[release-type: skip]`, NO tag fires automatically, so neither marketplace plugin fast-forward nor `uv tool install …@<latest-tag>` will pick up the merged code. The operator's local Claude Code session may have a stale cortex-daytime plugin from BEFORE #228. The smoke test passes against stale code → `[release-type: minor]` fires → release tag cuts → downstream users hit the bug because merged code was never exercised. **Mitigation**: Add Step 0 — operator executes `uv tool install --reinstall git+<repo>@<commit-sha-of-#228-merge>` AND re-installs the cortex-daytime plugin from same commit SHA. Capture both versions into §Results with acceptance gate that they match the #228 merge commit SHA on main.

5. **Race condition: concurrent `[release-type:]` markers within one auto-release cycle** — Verified: `auto-release.yml` uses `concurrency: { group: auto-release, cancel-in-progress: true }`. Under push storms, only the latest push triggers a release covering ALL markers since last tag. Failure mode: if operator A pushes `[release-type: minor]` for ticket X and operator B pushes `[release-type: major]` (or `skip`) for ticket Y in the same cycle, precedence (`skip > major > minor > patch`) silently merges release intent. Operator A unaware their release was upgraded/suppressed. **Mitigation**: Pre-push check: `git log <latest-tag>..HEAD --grep='\[release-type:' --oneline` to confirm no unresolved markers. Flag in `docs/release-process.md`.

6. **PGID detachment vs sandbox escape — distinguishing "escaped" from "never sandboxed"** — Symmetric defense: the gate doesn't need to distinguish these in the success path because they have the same operational consequence (writes succeed). The gate's job is to detect the FAILURE path where Anthropic upstream begins sandboxing MCP servers, which WILL produce EPERM and "Sandbox failed to initialize." Different blindspot the agents didn't flag: the gate tests MCP-routed dispatch but NOT the Bash-tool direct path (`cortex daytime start` via Bash with dangerouslyDisableSandbox). R18 says console-script entry is preserved as "fresh-terminal regression guard"; a Claude session calling `cortex daytime start` via Bash exercises a different escape mechanism. **Optional Mitigation**: Add second smoke variant testing Bash-tool path; apply same assertions to its pipeline-events.log.

7. **"merged" semantics for procedure-execution ticket** — Backlog convention overloaded: `merged` traditionally means "code in main." This ticket has no code change. §Acceptance is prose-only enforcement of a status-marker invariant — `cortex-update-item ... status=merged` does NOT check §Results content. CLAUDE.md "Skill/phase authoring guidelines" explicitly prefers structural separation over prose-only enforcement. **Mitigation options**: (a) introduce new backlog status `verified` for procedure-execution tickets, enforced by `cortex-update-item`; (b) document the overload in conventions.

8. **No timeout on "wait for dispatch event"** — Step 2 has no defined timeout, polling interval, or failure mode for "events.log never appears." `cortex_command/overnight/daytime_pipeline.py:380-388` shows "daytime already running" exits with code 1 BEFORE any events.log write — silent failure path. **Mitigation**: Define wall-clock timeout (suggest 5 min); early-exit if `cortex daytime status --feature smoke-release-gate` returns no PID file or dead PID within 30s; on timeout, capture stdout/stderr + dir contents for failure ticket.

9. **Cleanup step failure mode undefined** — `cortex daytime cancel` can return non-zero if dispatch already exited; `git clean -fd` has no retry semantics; no ordering safeguard if operator runs `git clean -fd` before cancel completes asynchronously. **Mitigation**: Add ordering — cancel → poll `cortex daytime status` until "no active dispatch" → archive → clean.

10. **MCP-tool name binding is hardcoded** — If Anthropic changes the prefix convention, procedure literal won't autocomplete. Lower severity (operator gets "tool not found" and stops, doesn't silently mislead). **Mitigation**: Pre-flight step — operator types `/mcp` in Claude session, confirms `cortex-daytime` listed as `connected`.

### Security concerns and anti-patterns

- **Prose-only enforcement of a sequential gate** — `cortex-update-item ... status=merged` doesn't check §Results. CLAUDE.md prefers structural separation. Failure mode #7.
- **Relying on an event name that doesn't exist** — testable in CI today via a lint that scans backlog tickets' `grep -c "<event>"` patterns against the closed event vocabulary. Would catch failure modes #1 and #2 at lint time, not release time. **Durable fix**: add `tests/test_backlog_grep_targets_resolve.py`.
- **`--dangerously-skip-permissions` smoke session blast radius** — procedure doesn't tell operator to run smoke against a slug whose lifecycle dir contains NO plan.md (so dispatched session has nothing to do beyond dispatch handshake, then exits). Spec R7 of #228 gates the MCP boundary but doesn't isolate dispatched-session reach.

### Assumptions that may not hold

- `dispatch_start` is a semantic match for "daytime pipeline successfully started" → it's not (fires before first SDK round-trip).
- Operator's local plugin + CLI reflect as-of-merge code → false without explicit re-install.
- `[release-type:]` is an independent per-commit lever → false under multi-operator concurrency.
- "merged" is meaningful for procedure-execution tickets → convention is overloaded; not documented.
- Spec's 12-month confidence horizon (~80-85%) implies gate catches regression WHEN it happens → gate only detects at release-tag cut time; no continuous re-verification.
- Empty-commit marker mechanism IS sound mechanically — but requires operator to remember. No monitoring for "PR merged with `[release-type: skip]`, no follow-up marker within N days."

### Symmetric defense of the current procedure

- **A1 (empty-commit marker)** IS the right architectural choice. Manual tag-push trips `cli-pin-lint`; workflow-dispatch typed inputs require additional UI surface; the empty-commit marker keeps release intent in git history where it's auditable.
- **D1 (procedure-in-ticket)** is correct for a single-use procedure that may never re-run. Promoting to `docs/release-process.md` as a pattern would imply gate ritual is recurring; it's currently a one-shot validation of a research-falsified hypothesis.
- **Manual MCP invocation requirement** — the "interactive Claude Code session required" constraint is the CORRECT fidelity check. CI-automated equivalents are easier to bypass invisibly.

## Open Questions

Resolution required before Spec phase can proceed. These supersede the clarify-phase Q1 resolution ("three greps as-is, defend in spec"), which was made on a false premise (the grep target doesn't exist).

- **OQ1 (MUST RESOLVE)**: Which event(s) should the procedure actually grep for? Options: (a) `dispatch_start` + `dispatch_complete` paired with matching feature slug and time-ordering — proves the child actually completed; (b) `feature_complete` from the higher-level batch loop in events.log — proves the full feature lifecycle ran; (c) add a new `feature_dispatched` event with an emission site in `daytime_pipeline.py` plus a row in `bin/.events-registry.md`. Option (c) makes the ticket's prose accurate but adds scope; options (a) and (b) reuse existing events.

- **OQ2 (MUST RESOLVE)**: Which file should the procedure grep — `events.log` (higher-level batch loop) or `pipeline-events.log` (per-dispatch wrapper)? `dispatch_start` lives in pipeline-events.log; `feature_complete` lives in events.log. Resolution depends on OQ1.

- **OQ3 (MUST RESOLVE)**: How to defend against the local plugin/CLI version mismatch — the operator's local install may be pre-#228 code. Options: (a) Step 0 pins via `uv tool install --reinstall git+<repo>@<#228-merge-sha>` plus plugin re-install, capture both versions into §Results with acceptance gate that they match; (b) accept the risk and add a §Edge Cases note; (c) defer to a separate ticket.

- **OQ4 (RECOMMEND RESOLVE)**: Should #230's R16 fix propagate back to `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` R16 in the same spec/PR, or be a separate follow-up? The hallucinated event name and wrong path appear in both documents; fixing one without the other propagates the bug.

- **OQ5 (RECOMMEND RESOLVE)**: Add a CI lint (`tests/test_backlog_grep_targets_resolve.py`) that scans backlog markdown files for `grep -c "<event>"` patterns against the closed event vocabulary, to catch event-name hallucinations at CI time. Scope this in #230's spec or split into a separate ticket?

- **OQ6 (CAN DEFER)**: Should the procedure also gate the Bash-tool direct-call path (`cortex daytime start` via Bash with dangerouslyDisableSandbox)? Both harness escape paths matter per spec R18. Adding it doubles procedure length but covers both spec-claimed escape mechanisms.

- **OQ7 (CAN DEFER)**: "merged" semantics for procedure-execution tickets — introduce new backlog status `verified` enforced by `cortex-update-item`, or document the overload in conventions? Affects future procedure tickets, not just #230.

- **OQ8 (CAN DEFER)**: Define wall-clock timeout for "wait for dispatch event" (suggest 5 min) and early-exit via `cortex daytime status` polling. Defer if §Procedure is too detailed for the spec phase.

## References

- `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` — ticket body
- `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` — parent spec R16 (also references hallucinated `feature_dispatched`)
- `cortex_command/pipeline/dispatch.py:660` — actual `dispatch_start` emission site
- `cortex_command/overnight/daytime_pipeline.py:220,222,380-388` — events.log vs pipeline-events.log path split; silent-failure exit code 1 path
- `cortex_command/overnight/events.py:36` — closed event vocabulary (`feature_dispatched` absent)
- `.github/workflows/auto-release.yml` — concurrency + marker semantics
- `bin/cortex-auto-bump-version` — marker precedence (skip > major > minor > patch)
- `cortex_command/overnight/sync-allowlist.conf` — post-merge sync auto-resolve globs
- `cortex/lifecycle/lead-refine-4-complexity-value-gate/pipeline-events.log` — empirical evidence that `dispatch_start` appears in pipeline-events.log not events.log
- `docs/overnight-operations.md:583-630` — per-spawn sandbox enforcement threat model + seatbelt-probe pattern
- `docs/internals/auto-update.md:62-70` — release-ritual contract
- `docs/mcp-server.md:22,46-52` — stdout reservation + `confirm_dangerously_skip_permissions: Literal[True]` gate
- `cortex/adr/0001-file-based-state-no-database.md`, `0002-cli-wheel-plus-plugin-distribution.md`, `0003-per-repo-sandbox-registration.md`
- `cortex/requirements/glossary.md` (skipped: file absent)
