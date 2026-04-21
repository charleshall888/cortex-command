# Cloudflare Remote-MCP — Research Report (April 2026)

## 1. What Cloudflare actually ships

- **`McpAgent` class** (Cloudflare Agents SDK) — Durable Object per session, built-in state, SSE + Streamable HTTP transports
- **`workers-oauth-provider`** — OAuth 2.1 provider library that wraps a Worker
- **Template repos**: `remote-mcp-authless`, `remote-mcp-github-oauth` (`npm create cloudflare@latest`)
- **`mcp-remote`** adapter — bridges stdio clients to remote servers
- **`workers-mcp`** — Workers-to-Claude-Desktop CLI (TS method auto-translation)
- **Cloudflare's own production MCP servers** at `mcp.cloudflare.com` (dogfood)
- Agents SDK v0.6.0 adds RPC transport and optional OAuth

## 2. Auth / end-user UX

OAuth 2.1 with PKCE. `workers-oauth-provider` handles `/authorize`, `/token`, `/register` using Workers KV. Providers: Cloudflare Access, GitHub, Google, Stytch, Auth0, WorkOS.

End-user: paste URL into Claude Code MCP config → browser auth pops on first tool call → token stored locally.

## 3. State persistence + limits

- **Durable Objects (SQLite)** — default for `McpAgent`. Free tier: 100k req/day, 5 GB SQLite. Paid: up to **10 GB per DO**. Evicted after 70–140s idle; `keepAlive()` keeps warm.
- **R2** (object storage), **D1** (larger SQL), **KV** (eventually-consistent) available.
- Single-threaded per DO.

## 4. Long-running tasks

**Workers CPU capped at 5 min** (Paid) / 10 ms (Free). DO alarms / cron / queue consumers capped at 15 min wall clock. **Cannot run a 6-hour job inside one Worker invocation.**

**Cloudflare Workflows** (GA'd, rearchitected in Agents Week 2026) is the durable-execution answer: multi-step durable, **sleep up to 365 days**, 25k steps, 30-day state retention, 1 GB persistent. CPU per step still 5 min.

Pattern: MCP tool enqueues Workflow → steps do LLM calls with sleeps → results polled or pushed via DO state + SSE.

**Each Workflow step is still short-lived compute doing I/O, NOT a long-lived process like cortex-command's `claude` subprocess.**

## 5. The local-filesystem blocker

A Cloudflare-hosted MCP physically cannot see `~/Workspaces/cortex-command/lifecycle/`. Three patterns exist, none fits cortex-command cleanly:

1. **Git as shared medium** — server reads/writes via GitHub App token (like `github-mcp-server`). Works for backlog markdown. **Breaks live-editing and worktree-atomicity** the runner depends on.
2. **Cloudflare Sandbox SDK / Dynamic Workers** — V8-isolate sandboxes with virtual FS, can spawn `claude` subprocesses inside. **Files operate on sandbox's virtual FS, not the user's laptop.**
3. **Hybrid (remote MCP + local bridge agent)** — re-introduces the local install you're trying to eliminate.

**Nothing shipped demonstrates "full dev workflow including live file edits in the user's local repo over remote MCP."** github-mcp-server is closest but sidesteps the problem by treating GitHub-as-truth.

## 6. Billing / multi-tenant

- **BYOK**: user's Anthropic key, stored in per-user DO SQLite (standard pattern, supported).
- **Centralized billing**: you hold one Anthropic key, bill via Stripe (`mcp-boilerplate` example). You implement quota + attribution.

## 7. Known failure modes

- **5-min CPU ceiling** per Worker invocation
- **DO eviction** at 70–140s idle — naïve in-memory state breaks
- **Sandbox filesystem ≠ user's filesystem** — any "runs on user's repo" requires sync
- **Subprocess-spawn requires Containers/Sandbox SDK, Paid-plan only**
- **Streamable HTTP is forward transport** (SSE deprecated); older clients need `mcp-remote` shim
- **Shadow MCP / security**: Cloudflare Gateway flags unsanctioned MCP traffic

## Bottom line for cortex-command

**A full port is the wrong shape.** Runner needs (a) long-lived processes spawning `claude` subprocesses, (b) writable git worktree on user's machine, (c) multi-hour execution with local file atomicity. Cloudflare gives you (c) via Workflows but fights you on (a) at Workers tier and **fundamentally cannot do (b) remotely**.

**Realistic slice: backlog + lifecycle as a remote MCP, runner stays local.**
- File-manipulation pieces already GitHub-shaped (backlog markdown, lifecycle docs, retros) → remote MCP using GitHub App token. `McpAgent` + `workers-oauth-provider` + GitHub OAuth = zero-install for the user.
- Skills needing live working tree (`/commit`, overnight runner, `/lifecycle implement`) stay local.
- Matches what `github-mcp-server` already does; avoids reinventing local-filesystem bridge.

Shipping the overnight runner itself as a remote MCP would require Sandbox Containers + repo upload or per-edit streaming — architectural mismatch without removing the local install.

## Sources
- [Cloudflare: Build a Remote MCP server](https://developers.cloudflare.com/agents/guides/remote-mcp-server/)
- [Cloudflare: MCP Authorization](https://developers.cloudflare.com/agents/model-context-protocol/authorization/)
- [Cloudflare: Agent class internals](https://developers.cloudflare.com/agents/concepts/agent-class/)
- [Cloudflare: Workflows limits](https://developers.cloudflare.com/workflows/reference/limits/)
- [Cloudflare: Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Cloudflare: Sandbox SDK](https://developers.cloudflare.com/sandbox/)
- [Remote MCP launch (Mar 2025)](https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/)
- [MCP + authn/authz + DO free tier](https://blog.cloudflare.com/building-ai-agents-with-mcp-authn-authz-and-durable-objects/)
- [Workflows v2 for the agentic era](https://blog.cloudflare.com/workflows-v2/)
- [cloudflare/workers-oauth-provider](https://github.com/cloudflare/workers-oauth-provider)
- [github/github-mcp-server](https://github.com/github/github-mcp-server)
- [iannuttall/mcp-boilerplate (Stripe-billed)](https://github.com/iannuttall/mcp-boilerplate)
