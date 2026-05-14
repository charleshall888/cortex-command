---
schema_version: "1"
uuid: 9780ae26-602f-4eee-9027-0e18894d613d
title: "Restore subscription auth for autonomous worktree subprocess"
status: complete
priority: medium
type: feature
tags: [overnight, auth, regression, subscription, plugin]
created: 2026-05-14
updated: 2026-05-14
session_id: null
lifecycle_phase: plan
lifecycle_slug: restore-subscription-auth-for-autonomous-worktree
complexity: complex
criticality: high
spec: cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md
areas: [overnight-runner]
---

## Background

The bash `runner.sh` previously shelled out to `claude -p <prompt>` for each round, which let Claude Code itself handle Keychain-based subscription auth. Subscription-only users (no Anthropic Console API key) could leave `apiKeyHelper` empty or unset and autonomous overnight runs worked transparently.

Commit `122037d0` (2026-05-12, "Add resolve_and_probe helper; converge runner and daytime auth paths") replaced this with the Python `claude_agent_sdk` path. The SDK requires an explicit env-resolved auth vector (`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `apiKeyHelper`-resolved key, `CLAUDE_CODE_OAUTH_TOKEN`, or `~/.claude/personal-oauth-token`) and does **not** fall back to using the Keychain. Subscription-only users now hit `error: auth probe failed: vector=none, keychain=absent — Keychain entry absent; no auth vector available` when launching `cortex-daytime-pipeline` (autonomous worktree dispatch).

The commit message itself acknowledges the removal: *"Removes misleading 'will use Keychain auth if available' message text in auth.py; replaced with probe-outcome-driven wording."* The wording was load-bearing — it described real behavior that no longer exists.

## Reproducer

1. Subscription-only user (no `ANTHROPIC_API_KEY` in env, no `apiKeyHelper` configured, no `~/.claude/personal-oauth-token` file).
2. Macos Keychain has `Claude Code-credentials` entry but ACL is bound to Claude Code's bundle identity (subprocess cannot read it).
3. From inside Claude Code, dispatch `/cortex-core:lifecycle <feature> implement` and select "Implement in autonomous worktree".
4. The dispatched `cortex-daytime-pipeline` subprocess invokes `resolve_and_probe`, which fails at `vector="none"` + `keychain="absent"` (probe returns absent when subprocess can't read the Keychain entry).
5. Subprocess exits 1 with the auth-probe-failed stderr line.

## Goal

Explore the design space and pick the right fix for the maintainer's actual use cases. The maintainer is a subscription user without an Anthropic Console API key.

## Candidate paths to investigate

1. **Hybrid shell-out to `claude -p` when vector=none and keychain=present** — closest restoration of pre-122037d0 behavior. Have `daytime_pipeline` (or a slim adapter inside the SDK auth path) shell out to `claude -p` for prompts when no explicit vector resolves. Cost: two execution paths, one through SDK, one through CLI subprocess. Diverges from "one converged auth chain" goal of 122037d0 but restores subscription compatibility.

2. **Have Claude Code propagate `CLAUDE_CODE_OAUTH_TOKEN` (or equivalent) to spawned subprocesses' env** — would require Anthropic-side change to Claude Code's subprocess-spawning behavior. May not be feasible; tracking-only path. Worth a feature request to Anthropic if other options are unattractive.

3. **Add a `SubscriptionAuthMode` flag in `auth.py`** — disables the explicit-vector requirement when running under `CLAUDE_CODE_SESSION_ID` with `keychain=present`, falls through to using whatever auth Claude Code itself uses. Probably requires the SDK to also have a subscription-passthrough mode; investigate whether claude_agent_sdk supports this.

4. **Document that autonomous worktree requires an API key** — status-quo + setup-time clarity. Update `docs/setup.md`'s Autonomous Worktree section (if any) and `skills/lifecycle/references/implement.md` §1a to state the requirement loudly. Cheapest path but explicitly closes off subscription users from the feature.

5. **Build an `oauthKeyHelper` mechanism analogous to `apiKeyHelper`** — let the user write a script that returns a refreshed OAuth token. Requires the user to figure out how to obtain a refreshed token from Claude Code (`claude print-token`?), which may not be exposed today. If Claude Code has such a command, this is clean; if not, it's a wish.

6. **Other paths surfaced during research.**

## Output

A `spec.md` with the recommended approach + rationale + acceptance criteria. Should be opinionated about which path to take (and which to discard) based on maintainer's use case as a subscription user.

## Acceptance

A subscription-only user can run `cortex-daytime-pipeline` (or the autonomous-worktree-dispatch path) without:
- Setting `ANTHROPIC_API_KEY` in their environment
- Manually extracting an OAuth token from Keychain Access into `~/.claude/personal-oauth-token`
- Acquiring an Anthropic Console API key

The fix is durable across token refresh and doesn't require the user to maintain an external script.

## Cross-references

- Originating commit: `122037d0` (this repo, 2026-05-12)
- Pre-regression message: `cortex_command/overnight/auth.py` pre-122037d0 line containing `claude -p will use Keychain auth if available`
- Affected entry point: `cortex_command/overnight/daytime_pipeline.py` (invokes `resolve_and_probe`)
- Auth chain: `cortex_command/overnight/auth.py` `ensure_sdk_auth` (lines 398-468)
- Related: lifecycle `prep-hooks-and-apikey-for-sharing` (archived) — pre-distribution-refactor era when the stub script + symlink wiring was in place
