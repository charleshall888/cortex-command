# Research: Restore subscription auth for autonomous-worktree subprocess

## Codebase Analysis

### Files that will change

**Core auth subsystem** (`cortex_command/overnight/auth.py`, 567 lines):
- `ensure_sdk_auth()` lines 398–468 — main 4-step resolver (ANTHROPIC_AUTH_TOKEN → ANTHROPIC_API_KEY → apiKeyHelper → CLAUDE_CODE_OAUTH_TOKEN env → `~/.claude/personal-oauth-token` file → vector=none).
- `resolve_and_probe()` lines 293–390 — combines `ensure_sdk_auth` with `probe_keychain_presence` under the R3 policy (vector!=none → continue; vector=none + probe=absent → fail; vector=none + probe in {present,unavailable} → continue with auth_probe event).
- `probe_keychain_presence()` lines 82–121 — calls `security find-generic-password -s "Claude Code-credentials"` and returns `present|absent|unavailable`. Does **not** read the credential (no `-w` flag). Note: missing `-a "$USER"` may produce false `absent` results on Macs where the Keychain entry is scoped to a specific account.
- `_read_oauth_file()` lines 187–211 — reads `~/.claude/personal-oauth-token` and exports its content as `CLAUDE_CODE_OAUTH_TOKEN`. **This consumer side is fully wired** — any solution that drops a token into this file will be picked up without further auth.py changes.
- `_invoke_api_key_helper()` lines 158–184 — invokes `apiKeyHelper` subprocess with 5s timeout; returns "" on failure (falls through).
- `resolve_auth_for_shell()` lines 471–541 — shell entry point with exit codes 0/1/2.
- `AuthProbeResult` dataclass — fields `ok`, `vector`, `keychain`, `result`, `auth_event`, `probe_event`.

**Integration points** (minimal modification):
- `cortex_command/overnight/daytime_pipeline.py` (587 lines) — calls `verify_dispatch_readiness()` at line 343; two-phase auth pattern (Phase A resolves before worktree creation; Phase B emits buffered events after `build_config()`).
- `cortex_command/overnight/readiness.py` (129 lines) — `verify_dispatch_readiness()` line 88 calls `resolve_and_probe(feature=feature, event_log_path=None)`; returns `ReadinessResult` with `failed_check="auth"` on probe-absent.
- `cortex_command/overnight/runner.py` line 2044 — Phase A auth resolution for runner path; mirrors daytime contract.
- `cortex_command/pipeline/dispatch.py` lines 541–548 — already forwards both `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` to the SDK subprocess env via `ClaudeAgentOptions(env=_env)`. **Consumer chain is complete** — auth.py drops a value, dispatch.py propagates it.

**Test files**:
- `tests/test_runner_auth.py` (339 lines) — covers `resolve_and_probe()` contract and shell entry exit codes (R3 parity tests).
- `cortex_command/overnight/tests/test_daytime_auth.py` (191 lines) — covers daytime startup-failure on `vector=none + keychain=absent` and continue-path on `keychain=unavailable`.

**Console entry**: `pyproject.toml` line 33 registers `cortex-daytime-pipeline = "cortex_command.overnight.daytime_pipeline:_run"`. Lifecycle `implement` invokes it from the autonomous-worktree dispatch flow.

**Docs**: `docs/overnight-operations.md` lines 667–697 is the authoritative reference; explicitly warns that "divergence between the two paths [runner and daytime] is a silent correctness hazard."

### Relevant existing patterns

1. **One converged auth chain** — commit 122037d0 (2026-05-12) explicitly removed the runner.sh `claude -p` shell-out to eliminate divergence between runner and daytime auth paths. Both now go through `resolve_and_probe()`. Any candidate that reintroduces a parallel execution path fights this convergence.
2. **R3 policy** — `vector=none + probe="absent"` is the only failure case. `unavailable` (Keychain locked or non-Darwin) is a continue case. The decision tree is locked in by the readiness fuse and daytime tests.
3. **Two-phase daytime event emission** — Phase A resolves auth before `pipeline_events_path` exists; Phase B writes buffered events after `build_config()` returns. Required for the `finally` block's `daytime-result.json` classification.
4. **Byte-equivalence test (R7)** — auth events must byte-match between runner and daytime paths.
5. **Stdlib-only auth.py** — no `claude_agent_sdk` import at the auth-module level. Any new auth path that requires the SDK breaks this.
6. **Event schema** — `auth_bootstrap` (always) + `auth_probe` (vector=none only); schema documented in `bin/.events-registry.md`. Use `_build_event()` / `_build_probe_event()` builders.

### Integration constraints

- **Keychain service name**: hardcoded `"Claude Code-credentials"` (auth.py:79). Must remain consistent.
- **Env var precedence ordering**: `ANTHROPIC_AUTH_TOKEN` > `ANTHROPIC_API_KEY` > `apiKeyHelper` > `CLAUDE_CODE_OAUTH_TOKEN` env > oauth_file. Any token written by a new path can be shadowed by an earlier vector silently.
- **`~/.claude/` write policy**: project.md hard-constrains cortex-command's writes to `~/.claude/` to a single one in `cortex init` (registering the repo's umbrella path in `sandbox.filesystem.allowWrite`). Writing `~/.claude/personal-oauth-token` is an existing exception (the `oauth_file` vector reads it), but adding new writes there warrants explicit justification.

## Web Research

### Claude Agent SDK auth contract

- `claude-agent-sdk-python` does not implement auth — it spawns the bundled Claude Code CLI as a subprocess and inherits parent env. No SDK option exists for a token-refresh callback, no Keychain reader, no `oauthKeyHelper` concept.
- Two closed feature requests confirm this: anthropics/claude-agent-sdk-python#559 ("Agent SDK should support Max plan billing") and #106 ("Allow to authenticate ... in same manner as Claude Code"). Both resolved by adding env-var support (`CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`), not by in-SDK subscription detection.
- anthropics/claude-code#42106 ("Allow OAuth/subscription tokens with Agent SDK for personal development use") is still **open** but stale; no maintainer response.

### Canonical Claude Code auth precedence

Per `code.claude.com/docs/en/authentication`, Claude Code picks the first present:
1. Cloud provider creds (Bedrock/Vertex/Foundry)
2. `ANTHROPIC_AUTH_TOKEN` (sent as `Authorization: Bearer`)
3. `ANTHROPIC_API_KEY` (sent as `X-Api-Key`)
4. `apiKeyHelper` script stdout
5. `CLAUDE_CODE_OAUTH_TOKEN` env var
6. Subscription OAuth from `/login` (macOS Keychain entry `Claude Code-credentials`; Linux `~/.claude/.credentials.json` mode 0600)

Critical caveats:
- **`apiKeyHelper`, `ANTHROPIC_API_KEY`, and `ANTHROPIC_AUTH_TOKEN` apply to terminal CLI sessions only.** Claude Desktop and remote sessions use OAuth exclusively. They do not call apiKeyHelper or read API-key env vars.
- **Bare mode (`--bare`) does not read `CLAUDE_CODE_OAUTH_TOKEN`.** Must use API key or apiKeyHelper.

### Claude Code CLI auth surfaces

There are **two** subscription-auth CLI surfaces (the adversarial review caught this — earlier agents missed it):

- **`claude setup-token`** — legacy mint command. Runs OAuth browser flow, prints `sk-ant-oat01-*` token to stdout, **saves nothing**. anthropics/claude-code#19274 (closed as not-planned) confirms: not written to Keychain, not written to `.credentials.json`. The user captures stdout and re-exports manually.
- **`claude auth {login, logout, status}`** — modern entry. `claude auth login --claudeai` performs the subscription OAuth flow and writes the Keychain entry (Darwin) or `~/.claude/.credentials.json` (Linux, mode 0600) — containing `accessToken + refreshToken + expiresAt + scopes`. `claude auth status --json` emits a structured JSON status (e.g., `{"loggedIn":false,"authMethod":"none","apiProvider":"firstParty"}`).
- **No `claude print-token`, `claude auth token`, or `claude get-credentials` subcommand exists** — a documented gap vs. gh CLI (`gh auth token`), gcloud (`gcloud auth print-access-token`), and az CLI (`az account get-access-token`).

### Keychain entry behavior on macOS

- The `Claude Code-credentials` Keychain entry is created with permissive ACL: any process running as `$USER` that can exec `/usr/bin/security` can read it without prompting. anthropics/claude-code#29783 (closed as not-planned) confirms.
- Reproducer: `security -v find-generic-password -s "Claude Code-credentials" -a "$USER" -w` → returns `{"claudeAiOauth":{...}}` with no prompt.
- `griffinmartin/opencode-claude-auth` is a reference implementation that reads the Keychain entry, refreshes via direct `POST https://claude.ai/v1/oauth/token` when expiry is <60s, and writes the refreshed token back. Demonstrates the keychain-read approach works for non-Claude-Code processes.
- Known failure modes: SSH-only sessions (Keychain inaccessible, #44028/#44089), locked Keychain, locked screen, Automator-style sandboxed parents (#1154).

### OAuth-token API constraints

- OAuth tokens (`sk-ant-oat01-*`) are accepted by the CLI but **rejected by the raw Messages API**: direct `POST /v1/messages` with `Authorization: Bearer sk-ant-oat01-*` returns "OAuth authentication is currently not supported" (anthropics/claude-code#37205, closed). Third-party direct-API use of OAuth tokens was actively disabled circa 2026-02-20 (anthropics/claude-code#28091).
- This means: any path that bypasses the CLI subprocess and calls the Messages API directly with an OAuth token will fail. The CLI shell-out (which is what `claude_agent_sdk` does under the hood) is the only sanctioned path.

### June 15, 2026 inflection

Anthropic support article ([support.claude.com/en/articles/15036540](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)) announces: "Starting June 15, 2026, Agent SDK and `claude -p` usage on subscription plans will draw from a new monthly Agent SDK credit, separate from your interactive usage limits." One-time opt-in. **The technical vector remains `CLAUDE_CODE_OAUTH_TOKEN`** — no new env var or flag is specified.

Today is 2026-05-14, ~1 month before this goes live. Any solution that ships in this window must remain valid through the June-15 transition.

### Anti-patterns and silent failures

- **`ANTHROPIC_API_KEY` silent override**: if a user has it in their env (e.g., for another project), it wins over OAuth tokens. They'll billing-bill API credits while believing they're using a subscription.
- **Auth conflict**: setting both `CLAUDE_CODE_OAUTH_TOKEN` and `apiKeyHelper` triggers "Auth conflict" + "Invalid API key" failure (anthropics/claude-code#11587).
- **ToS exposure** (adversarial finding): in February 2026 Anthropic enforced against third-party redistribution of OAuth tokens for autonomous use. The Agent SDK's CLI-wrapper architecture is what keeps subscription-OAuth use in-bounds — that protection is contingent on Anthropic continuing to bless the CLI-wrapper pathway (which the June-15 metering separation does).

## Requirements & Constraints

### Architectural constraints (from `cortex/requirements/project.md`)

- **Per-repo sandbox registration** (line 28): `cortex init` additively adds the repo's `cortex/` umbrella to `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite` — **the only write cortex-command makes in `~/.claude/`**. Path 7's `~/.claude/personal-oauth-token` write is an existing exception (the `oauth_file` vector already reads it) but new writes warrant justification.
- **File-based state** (line 27): Auth state must follow this pattern.
- **Solution horizon principle** (line 21): Long-term project. Before suggesting a fix, ask: do I already know this needs redoing? If yes, propose the durable version or surface both. **A scoped phase of a multi-phase lifecycle is not a stop-gap.**
- **Complexity must earn its place** (line 19): Simpler wins when in doubt.
- **Defense-in-depth for permissions** (line 38): Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface.

### Requirements specific to auth

- **`cortex/requirements/multi-agent.md` line 85**: `ANTHROPIC_API_KEY` listed as a required dependency forwarded to each agent. The dependency listing predates the OAuth vector and is incomplete; `CLAUDE_CODE_OAUTH_TOKEN` is also forwarded today (dispatch.py:547–548).
- **`docs/overnight-operations.md` lines 667–697**: auth.py is the shared module for runner and daytime paths to ensure "one priority order, one sanitization rule, one event schema" — divergence is "a silent correctness hazard."
- **macOS keychain prompt risk** (line 580): If auth resolution falls through to keychain-backed creds, the first subprocess spawn may trigger a Keychain access dialog. "The runs-while-you-sleep premise breaks silently — the prompt blocks subprocess spawn until acknowledged."
- **Smoke test three modes** (`cortex_command/overnight/smoke_test.py` 171–191): OAuth-token mode, apiKeyHelper mode, subscription-passthrough mode (apiKeyHelper absent/empty).

### Scope boundaries

- **In scope**: Auth chain for autonomous daytime pipeline subprocess; multi-agent orchestration including worktree isolation.
- **Out of scope**: Writes to `~/.claude/` beyond `cortex init` (current); machine configuration; application code.

## Tradeoffs & Alternatives

### Path 1 — Hybrid shell-out to `claude -p` (REJECT)

Restore pre-122037d0 behavior by shelling out to `claude -p` when `vector=none + keychain=present`. Either a new "subscription transport" branch in `dispatch.py` bypassing `claude_agent_sdk.query()`, or swap the SDK's `cli_path` to a wrapper script.

**Reject**: Reintroduces the exact divergence 122037d0 eliminated. Would require reimplementing `ClaudeAgentOptions` semantics (effort, max_turns, budget, allowed_tools, sandbox, settings) on top of `claude -p --output-format stream-json`. ~5–8 files, ~400–600 LOC. Brittle to Claude Code CLI output-format changes. The ticket's repro itself shows the keychain probe returning `absent` from the daytime subprocess context — `claude -p` invoked from that same context may face the same Keychain-access boundary, so the path may not even work.

### Path 2 — Anthropic-side env propagation (TRACK)

File a feature request with Anthropic to propagate `CLAUDE_CODE_OAUTH_TOKEN` into spawned subprocess env by default.

**Track, not adopt**: Zero local code; pure tracking. Most architecturally correct fix in principle but not on a present-tense timeline. Useful as a parallel tracking issue (with a link to anthropics/claude-code#42106). Does not satisfy "durably" acceptance criterion on a present timeline.

### Path 3 — `SubscriptionAuthMode` flag with Keychain passthrough (REJECT)

Add a branch in `resolve_and_probe`: when `CLAUDE_CODE_SESSION_ID` is set and keychain=present, treat as pass-through without setting any env var, then dispatch the SDK.

**Reject**: Premise contradicts observed SDK behavior. The SDK spawns Claude Code CLI which itself reads env vars; with no env var set, the spawned CLI has no auth. "Hope it finds Keychain" doesn't work — the CLI subprocess is the one with the Keychain ACL issue. This path is Path 2 with extra dead branching.

### Path 4 — Document API-key requirement (REJECT)

Update docs/setup.md and skills/lifecycle/references/implement.md §1a to state autonomous worktree requires `ANTHROPIC_API_KEY`.

**Reject**: Violates acceptance criterion #3 ("without acquiring an Anthropic Console API key"). The maintainer is exactly the user this would close off.

### Path 5 — `oauthKeyHelper` analog to `apiKeyHelper` (REJECT)

Add new `oauthKeyHelper` setting; user writes a shell script that extracts the OAuth token (e.g., from Keychain) and prints it.

**Reject**: Two acceptance violations. (a) "without maintaining an external script" — a user-owned script is exactly that. (b) "durably across token refresh" — access tokens in Keychain expire in hours; user script would need refresh logic embedded (`POST claude.ai/v1/oauth/token` with refresh token) which they won't write. No concept of `oauthKeyHelper` exists in Anthropic docs.

### Path 7 — Bootstrap-mint via `claude setup-token` writing to `~/.claude/personal-oauth-token` (CONDITIONAL — has issues)

Add a `cortex auth bootstrap` subcommand (or fold into `cortex init`) that detects vector=none + no token file, runs `claude setup-token`, captures stdout, writes `~/.claude/personal-oauth-token` mode 0600. Zero changes to auth chain — consumer side via `oauth_file` vector is already wired.

**Pros**: Smallest change; preserves "one converged auth chain"; year-long token in the practical case; serves all subscription users on platforms where `claude setup-token` works.

**Cons surfaced by adversarial review**:
- **Wrong primitive**: `claude setup-token` is the legacy mint. The modern surface is `claude auth login --claudeai` which writes a Keychain entry (Darwin) or `~/.claude/.credentials.json` (Linux) containing `accessToken + refreshToken + expiresAt`. The minted-token-then-dump-to-file approach loses the refresh token, so the dispatched subprocess uses a stale snapshot even while the parent Claude Code auto-refreshes — recreating the silent-divergence pattern 122037d0 eliminated, one layer deeper.
- **ToS fragility**: post-2026-02-20 Anthropic enforcement against third-party OAuth-token use. June-15 metering separation may further change the contract.
- **Browser-flow blocker**: `claude setup-token` requires a browser. CI/headless Linux/SSH-only cannot bootstrap unattended. The "one-shot user action" framing arguably violates "without maintaining an external script" in spirit.
- **Security regression**: plaintext year-long bearer token in `~/.claude/personal-oauth-token` mode 0600 is strictly worse than the Keychain entry (which is encrypted at rest, locks with screen).
- **Token mixing**: precedence-ordered chain can silently shadow the freshly-written token (e.g., a stale `CLAUDE_CODE_OAUTH_TOKEN` env var or `ANTHROPIC_API_KEY` from another project wins).
- **Concurrency**: two `cortex auth bootstrap` invocations race on the file write; no lock today.

### Path 8 — `apiKeyHelper` returns the OAuth token via `security find-generic-password | jq .accessToken` (REJECT)

Documentation-only path: tell users to set `apiKeyHelper` to a shell command that extracts the OAuth token from Keychain.

**Reject**: Access tokens expire in hours; helper has no refresh logic; embedding the JSON-shape extraction is brittle to Anthropic-side changes; semantically wrong (stuffs an OAuth token into `ANTHROPIC_API_KEY` slot which is routed differently post-June-15).

### Path 10 — Native Keychain / `.credentials.json` reader vector in `auth.py` (NEW — strongest candidate)

Surfaced by adversarial review. Add a new auth vector in `auth.py` that:

- **On Darwin**: runs `security find-generic-password -s "Claude Code-credentials" -a "$USER" -w`, parses the returned JSON, extracts `accessToken`, exports as `CLAUDE_CODE_OAUTH_TOKEN`.
- **On Linux/other**: reads `~/.claude/.credentials.json`, parses JSON, extracts `accessToken`, exports as `CLAUDE_CODE_OAUTH_TOKEN`.
- **Pre-flight**: if `expiresAt` is within N seconds of now (or already expired), refresh via `POST https://claude.ai/v1/oauth/token` with the stored `refreshToken`, write back to the source. Mirrors `opencode-claude-auth`'s pattern.

This is what the codebase comparison "Claude Code does it; the SDK doesn't" actually means — Claude Code reads the credential file/Keychain and auto-refreshes; the SDK doesn't. Path 10 closes the gap by having `auth.py` do the same.

**Pros**:
- One code path. No "mint + consume" coupling; no `claude setup-token`; no new long-lived secret on disk.
- Auto-fresh: re-reading at each session start picks up Claude Code's own rotations. If we also implement refresh, we cover the case where the parent Claude Code never ran between sessions.
- The user's one-time action is `claude auth login --claudeai` (an Anthropic-documented blessed flow), not a cortex-command-specific bootstrap. Acceptance criterion #2 ("without manually extracting an OAuth token") is satisfied — auth.py extracts it, not the user.
- Honors the converged auth chain — Path 10 is one new vector added between `oauth_file` and `vector=none`, not a parallel execution path.
- Works on Darwin and Linux; degrades gracefully where neither source is available (continues to `vector=none`).

**Cons**:
- **ToS exposure**: direct refresh against `claude.ai/v1/oauth/token` from cortex-command is exactly the pattern Anthropic enforced against in Feb 2026 (third-party redistributors). Reading the entry locally (without refresh) is in-bounds — the entry is globally readable and we're just propagating to a subprocess that itself is a Claude Code wrapper. Adding refresh logic crosses into the enforced area.
- **Stale-token failure mode**: without refresh, the access token in Keychain may be stale if the parent Claude Code hasn't run recently. Failure mode: subprocess 401s mid-dispatch. Mitigation: detect 401 in `dispatch.py` and surface a clear remediation ("run `claude auth status --json`; if loggedIn:false, run `claude auth login --claudeai`").
- **Linux `.credentials.json` shape stability**: the file shape is documented-but-private; Anthropic could rename `accessToken` to `access_token` at any time.
- **Probe needs fixing**: `probe_keychain_presence` currently calls `security find-generic-password` without `-a "$USER"` — may return false `absent` on Macs where the entry is scoped to a specific account.

### Recommended approach

**Adopt Path 10 (native Keychain / `.credentials.json` reader vector in `auth.py`) with refresh-deferred-as-follow-up.** Track Path 2 as a parallel tracking issue. Reject Paths 1, 3, 4, 5, 7, 8.

**Rationale**:

1. **Smallest durable change.** One new vector in the existing converged chain (between `oauth_file` and `vector=none`), not a separate bootstrap utility. Mirrors the existing `_read_oauth_file` pattern.
2. **Avoids silent divergence.** Reading the credential source at each session start aligns the dispatched subprocess with the parent Claude Code's current state, eliminating the "parent auto-refreshes, child reads stale snapshot" failure mode Path 7 introduces.
3. **No new long-lived secret on disk** managed by cortex. The source-of-truth remains Claude Code's own credential storage.
4. **Acceptance criteria check**:
   - No `ANTHROPIC_API_KEY` required ✓
   - No manual OAuth-token extraction by the user (auth.py extracts) ✓
   - No Anthropic Console API key required ✓
   - "Durably across token refresh": **partially satisfied** without refresh logic — the access token lives until the next `claude auth login` or Claude Code session refreshes it. Re-reading at each session start picks up the most recent value. Adding our own refresh path crosses ToS lines, so the durable-without-our-refresh shape is the right scoped version.
   - "Without an external script": ✓ — `claude auth login --claudeai` is one Anthropic-documented user action, not an ongoing user-maintained script.
5. **Solution horizon test**: Do I already know this needs redoing? Anthropic may ship Path 2 (env propagation in Claude Code) eventually, at which point Path 10 becomes a graceful fallback — no rework. June-15 metering is technical-vector-stable (`CLAUDE_CODE_OAUTH_TOKEN` stays). The only known-future-rework is *if* Anthropic ships a `claude print-token` CLI, in which case we'd swap the Keychain-read for the CLI call — a small change. Path 10 is the durable shape; Paths 1, 5, 7, 8 are predictable-rework shapes.
6. **Honest about scope**: Headless Linux / SSH-only / CI users where Claude Code has never logged in get `vector=none` + clear remediation. The acceptance criterion's "any subscription user" claim is honestly bounded to "any user who has a logged-in Claude Code on the same machine."

## Adversarial Review

The adversarial agent surfaced 10 substantive concerns that shaped the recommendation above. The most consequential:

1. **`claude setup-token` is the wrong primitive** — `claude auth {login, status}` is the modern surface; the durable artifact is `~/.claude/.credentials.json` (Linux) or the Keychain entry (Darwin), which carry `accessToken + refreshToken + expiresAt`. Tradeoffs agent missed this entirely. Drove Path 10 recommendation over Path 7.
2. **Refresh divergence** — Path 7's mint-once-into-file produces a stale snapshot vs. Claude Code's auto-refreshing source-of-truth. Recreates the silent-divergence pattern 122037d0 eliminated, one layer deeper.
3. **ToS fragility post-Feb-2026** — Anthropic enforced against third-party OAuth-token redistributors. Direct refresh against `claude.ai/v1/oauth/token` from cortex-command code is the enforced pattern; reading-and-propagating without refresh is in-bounds.
4. **Browser-flow blocks CI/headless** — `claude setup-token` requires a browser. The acceptance criterion's "any subscription user" needs explicit bounding: macOS or Linux *where the user has logged in via `claude auth login`*.
5. **Plaintext-file security regression** — long-lived bearer token in `~/.claude/personal-oauth-token` is strictly worse than the Keychain entry (encrypted at rest, locks with screen). Argues against Path 7's file as a new artifact.
6. **`probe_keychain_presence` bug** — auth.py:103 calls `security find-generic-password` without `-a "$USER"`. May produce false `absent` on Macs where the Keychain entry is scoped to a specific account. **Likely the root cause of the ticket's reproducer** — the probe may be incorrectly reporting `absent` even when the entry exists. Fix candidate independent of which path is chosen.
7. **Same-user Keychain ACL is broad** — any process running as `$USER` can read the entry without prompting (anthropics/claude-code#29783). Path 10 inherits this risk surface; it is the surface Claude Code already presents. Path 7's plaintext file would add another surface of the same kind without removing the Keychain one.
8. **Concurrency on file writes** — Path 7's file write needs the same `fcntl` lock pattern `cortex_command/init/settings_merge.py:60–66` uses. Path 10 avoids this entirely by not writing.
9. **Token mixing precedence hazard** — chain ordering can silently shadow newly-written tokens. Argues for a `cortex auth status` subcommand that reports the resolved vector so the user sees what auth.py *will* pick before they dispatch.
10. **Test infrastructure for browser flows** — Path 7's mint step cannot be unit-tested without browser. Argues for keeping mint out of the codebase. Path 10's read step is mockable (mock `subprocess.run(["security", ...])` and `pathlib.Path("~/.claude/.credentials.json").read_text`).

## Open Questions

User resolved via post-research clarification round on 2026-05-14 after the canonical Anthropic guidance was fetched directly from `code.claude.com/docs/en/authentication`. The doc explicitly recommends `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` for "CI pipelines, scripts, or other environments where interactive browser login isn't available." Resolution per question:

1. **Path choice — RESOLVED → Path 7 (`cortex auth bootstrap` subcommand)**. Anthropic's authentication doc canonically prescribes `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` for non-interactive subprocess use. The adversarial review's "wrong primitive" concern was wrong: `claude auth login` is for interactive `claude` REPL sessions; `claude setup-token` is explicitly for script/CI contexts and emits a one-year token. The consumer side in `auth.py:_read_oauth_file` is already wired; the spec adds a producer-side wrapper.

2. **User population — RESOLVED → all subscription-only users where `claude setup-token` works** (i.e., all platforms Claude Code supports, including Darwin and Linux). The bootstrap subcommand is in the distributed CLI, not maintainer-private.

3. **Refresh implementation — RESOLVED → DEFER**. The Anthropic-blessed token is one-year. When it expires, user reruns `cortex auth bootstrap`. The "without external script" acceptance criterion is satisfied because `claude setup-token` is Anthropic's own tool (not a user-written script) and `cortex auth bootstrap` is cortex's own subcommand. Auto-refresh via direct `POST claude.ai/v1/oauth/token` is the pattern Anthropic enforced against in Feb 2026 — explicitly out of scope.

4. **`probe_keychain_presence` fix — DEFER to follow-up ticket**. With Path 7, the happy path resolves via `oauth_file` vector and the probe never runs. The probe bug only bites users in the transition window (before they run `cortex auth bootstrap`). The probe-absent error message will point them at the bootstrap command — that's sufficient remediation. Fixing the probe is independent and can be a separate small ticket.

5. **CI / headless — DOCUMENT**. Bootstrap requires browser-flow. CI/headless users can run bootstrap on a browser-capable machine and copy `~/.claude/personal-oauth-token` to the headless box, OR use `ANTHROPIC_API_KEY` (the existing precedence chain handles both). Spec will document this; CI-native bootstrap is out of scope.

6. **`cortex auth status` UX — IN SCOPE (paired with bootstrap)**. Useful diagnostic alongside `cortex auth bootstrap`. Reports the resolved auth vector (calls `ensure_sdk_auth`) plus a sanity check of whether `~/.claude/personal-oauth-token` exists and is readable. No credential is printed.

7. **Documentation scope — IN SCOPE**. The spec includes a `docs/setup.md` "subscription auth setup" section pointing at `cortex auth bootstrap`. The probe-absent stderr message in `auth.py:381` gets updated to reference the bootstrap command. `docs/overnight-operations.md` lines 667–697 (the auth resolution authoritative reference) gets a one-line link to the bootstrap UX.

All seven items resolved or explicitly deferred. Research Exit Gate satisfied.
