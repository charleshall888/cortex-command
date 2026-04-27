---
schema_version: "1"
uuid: 5cc1ab08-5283-41fa-bd29-02f7e89423a2
title: "Restructure README and setup.md for clearer onboarding"
status: backlog
priority: medium
type: feature
tags: [docs-setup-audit, documentation, onboarding, setup]
areas: []
created: 2026-04-27
updated: 2026-04-27
blocks: []
blocked-by: []
discovery_source: research/docs-setup-audit/research.md
---

# Restructure README and setup.md for clearer onboarding

## Context from discovery

`research/docs-setup-audit/research.md` audited cortex-command's user-facing onboarding surface (README + `docs/setup.md` + the docs index in README). The audit followed the user's stated binary: README quickstart with linked deeper setup, OR consolidate setup detail into `docs/setup.md`. Findings span codebase-verified defects and a substantive per-repo-flow documentation gap.

### Codebase-verified defects

- **Plugin install command syntax conflict**: `README.md:86-91` uses the bare form `claude /plugin install cortex-interactive`; `docs/setup.md:36-42` uses the marketplace-scoped `@cortex-command` form. A first-time reader cannot determine which is canonical from the docs alone.
- **Plugin count discrepancy**: `README.md:97` says "ships six plugins"; `README.md:99-106` lists six; the Quick Start at `README.md:86-91` installs four; `docs/setup.md:34` and `docs/setup.md:44` say "four." Silent contract gap.
- **CLI utility list incomplete**: `README.md:152` lists 7 utilities; `bin/` contains 9 (`cortex-archive-rewrite-paths` and `cortex-archive-sample-select` are undocumented).
- **Authentication duplicated**: `README.md:110-140` and `docs/setup.md:82-132` both cover auth with overlapping content; setup.md is the more complete copy.
- **Cross-platform promise unmet**: `README.md:72` says "For Linux or Windows setup, see docs/setup.md," but `docs/setup.md:266-276` Dependencies table says `brew install` everywhere — Linux/Windows coverage is not actually delivered.

### Per-repo flow documentation gap

- `cortex init` has 7 distinct side effects in `cortex_command/init/handler.py:44-223` (scaffold `lifecycle/`, `backlog/`, `retros/`, `requirements/`; write `.cortex-init` marker; append to `.gitignore`; merge `sandbox.filesystem.allowWrite` into `~/.claude/settings.local.json`); only 2 surface in the 6-line description at `docs/setup.md:72-78`.
- `lifecycle.config.md` schema is referenced only inside `skills/lifecycle/SKILL.md:29-30` and is not surfaced in any user-facing doc.
- No narrative bridge connects `cortex init` → first `/cortex-interactive:lifecycle` invocation. A fresh forker has no documented path from "I ran the install steps" to "my first feature is working."

## Recommendations from research

Research presents option evaluations with a recommended path. Plan phase confirms or revises:

- **OE-1 (README depth)**: trim to value-prop + 2-step quickstart + plugin roster + verification + docs index. Maps to user binary option (I). Auth + customization + commands + distribution sections move to setup.md.
- **OE-2 (setup.md scope)**: Approach D — single file, reorder so prose-walkthrough sections come first and reference content (sandbox, MCP, permission scoping) follows. No new docs.
- **OE-3 (cortex init flow)**: expand `docs/setup.md:72-78` in place with the 7 side effects, `lifecycle.config.md` schema, and a worked first-invocation example.
- **OE-4 (diagrams)**: keep the lifecycle phase flow diagram (`README.md:45-63`) in README; move the requirements→discovery→backlog→lifecycle pipeline diagram (`README.md:9-43`) to `docs/agentic-layer.md`.
- **OE-5 (verification)**: add `cortex --version && claude /plugin list` smoke test at the end of the install section. The OE-3 worked example doubles as end-to-end verification.
- **OE-6 (plugin install canonicalization)**: standardize on `@cortex-command` form everywhere. Verify behavioral equivalence between bare and `@cortex-command` forms during implementation; document the verification result in the implementation PR.
- **Cross-platform**: deliver what `README.md:72` promises — add Linux/Windows install notes (`apt`/`pacman` equivalents for `just`, `uv`, `gh`, `tmux`) and the macOS-only caveat for `terminal-notifier` to `docs/setup.md`.

## Out of scope

- Rewriting deep reference docs (`docs/skills-reference.md`, `docs/mcp-server.md`, `docs/pipeline.md`, `docs/sdk.md`, `docs/overnight-operations.md`) — they own their content per the `CLAUDE.md:50` owning-doc rule.
- Splitting `docs/setup.md` into `docs/onboarding.md` or `docs/customize.md` (Approach E in research) — outside the user's stated binary.
- Hosted docs site.

## Why now

`requirements/project.md:7` describes cortex-command as "primarily personal tooling, shared publicly for others to clone or fork." The codebase-verified defects (plugin command conflict, count drift, broken cross-platform promise) directly block the share-publicly mission. The per-repo flow gap is the highest-friction part of the onboarding journey for a fresh forker. Ticket #148 just landed cleanup of post-113 stale paths, leaving a clean baseline.

## Research

See `research/docs-setup-audit/research.md` for full findings, option evaluations, recommendations, and the methodology note disclosing cold-reader simulation as advisory (not measured) evidence.
