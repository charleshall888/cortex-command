# Decomposition: user-configurable-setup

## Epic

- **Backlog ID**: 063
- **Title**: User-configurable setup: per-component opt-in and per-repo permissions scoping

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 064 | Extend `/setup-merge` with dynamic per-component opt-in for skills and hooks | high | M | — |
| 065 | Document `CLAUDE_CONFIG_DIR` + direnv pattern for per-repo permissions scoping | critical | S | — |

## Suggested Implementation Order

Either can ship first; they're fully independent. `#065` carries `critical` priority because it is the item whose shipping answers the commissioned use case ("only use project permissions in this repo, ignore global allows") — it should surface first in consumer sorts. `#064` is `high` because it covers the user-level opt-in half of the ask (skill/hook install-time selection).

`#065`'s first sub-task is the DR-7 upstream activity audit on anthropics/claude-code#12962, #37344, #35561, #26489. The audit outcome shapes the docs preamble (quiet/warm/hot framing) but does not change the core deliverable.

## Key Design Decisions

- **2 tickets, not 5 or 6.** Earlier rounds of decomposition produced more granular ticket shapes. A maintainability review (drift surfaces vs. maintainer count) pulled the plan back to the smallest shape that answers both commissioned requirements. See the epic's "Decompose summary" section for the full history.
- **No `cortex-doctor` CLI.** Deferred. Its value depends on drift surfaces stabilizing, which they haven't yet.
- **No `bin/cortex-shadow-config` generator.** Deferred. Docs + manual `cp -r` is the smallest viable delivery. Build the generator only if friction is observed.
- **No Band B dependency resolver.** Dropped. Soft coupling in Band B (e.g., `morning-review` without `overnight`) produces graceful empty-state behavior, not corruption. The oh-my-zsh anti-pattern ("hidden inter-module deps causing weird runtime failures") doesn't apply here — the failure mode is "no value," which users recognize and resolve themselves.
- **Dynamic discovery in `/setup-merge`, not a curated manifest.** The component list is generated at prompt time by scanning `skills/*/SKILL.md` and `hooks/*.sh`. No drift between a manifest and reality. Adding a new skill automatically surfaces it in the next `/setup-merge` run.
- **Audit lives inside ticket #065, not as a separate spike.** Per Decompose consolidation rule (b): the audit has no standalone deliverable value; it exists to shape the docs. Merging it into the consumer collapses a fake ticket boundary.
- **No ticket split on `lifecycle.config.md` schema changes.** The `skills:` and `hooks:` sections land as part of #064; there is no separate schema ticket. The YAML frontmatter is 10 lines; splitting it into "schema" and "implementation" tickets would produce coordination overhead for minimal parallelism gain.
- **No new config files beyond existing `lifecycle.config.md`.** DR-2: adding a new `.cortex/config.md` or similar fails the simplicity-earns-its-place test. Reuse the file that already exists at the project root.

## Created Files

- `backlog/063-user-configurable-setup-per-component-opt-in-and-per-repo-permissions-scoping.md` — Epic
- `backlog/064-extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks.md` — Install-time per-component opt-in
- `backlog/065-document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping.md` — Per-repo permissions scoping via documented Claude Code feature
