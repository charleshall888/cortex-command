---
status: accepted
---

# CLI wheel + plugin distribution

Cortex-command ships through two independent channels — a non-editable CLI wheel installed via `uv tool install git+<url>@<tag>` and Claude Code plugins (e.g. `cortex-overnight`) installed via `/plugin install` — coupled by a small compatibility contract: `plugins/cortex-overnight/server.py`'s `CLI_PIN` tuple `(<tag>, <schema_major.minor>)` and the `cortex --print-root --format json` envelope's `version` (PEP 440 package) and `schema_version` (M.m floor) fields, with schema-floor majors treated as forever-public-API per `docs/internals/mcp-contract.md`. We chose a two-channel split with a coupling contract because the CLI and plugins evolve at independent cadences (plugin marketplace updates land on different schedules than wheel releases), and a narrow versioned envelope lets each side ship without lockstep coordination while still failing loudly on incompatible pairings.

## Considered Options

- **Symlink-into-`~/.claude/` deployment** (rejected): the prior model deployed skills, hooks, and binaries by symlinking from the repo into `~/.claude/`. It collapsed the two surfaces into one but tied every user's install to a working-tree checkout, made versioning implicit (whatever was on disk), and conflicted with Claude Code's plugin model. The wheel + plugin split replaces it with two first-class, independently-versioned distribution surfaces.
