---
schema_version: "1"
uuid: e634fb4a-f683-4141-9cd9-2373d1690711
title: "Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations"
status: backlog
priority: high
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, discoverability, enforcement]
created: 2026-04-21
updated: 2026-04-21
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
---

# Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations

## Context from discovery

Five of nine good-shape `bin/` scripts are currently under-adopted. Root-cause analysis shows three failure modes: day-one missing reference (`validate-spec`, `count-tokens`, `audit-doc`), hidden behind module abstraction (`create-backlog-item`, `update-item`), and confirmed drift (`skills/backlog/generate-index.sh` deleted and rewired). Shipping a linter without first clearing the backlog of existing violations defeats the enforcement point — the linter would land red or require blanket allowlisting. This ticket bundles linter delivery with concurrent retrofit of existing violations so the first run is green.

## Research context

- DR-5 spec in `research/extract-scripts-from-agent-tool-sequences/research.md` — three-category signal detection, allowlist format, failure modes enumerated.
- Enforcement: `just check-parity` recipe + pre-commit hook (CI-gated enforcement is dead wiring — this repo has ~3 PRs ever).
- Known limits: `--no-verify` bypass, staged-files-only scope, overnight-runner bypass. Mitigation: periodic full-tree scan as part of retro / morning-review protocol.

## Scope

- New `bin/check-parity` CLI + `just check-parity` recipe.
- Deploy via `just deploy-bin` symlink.
- Scan scope: `skills/**/*.md`, `CLAUDE.md`, `claude/reference/`, `requirements/`.
- Signal categories: literal `bin/foo` mentions, bare `foo` invocations in shell code blocks, path-qualified `~/.local/bin/foo`, `just <recipe>` cross-references, and a heuristic for transitive Python module wiring.
- Allowlist: `bin/.parity-exceptions.md` with `{reason, audience: user-only | orchestrator-only | module-shim}`.
- Deploy-path inventory extends beyond `just deploy-bin` — enumerate other symlink-deploy patterns (e.g., `hooks/cortex-notify.sh` → `~/.claude/notify.sh`).
- Retrofit in same ticket: wire `validate-spec` into `skills/lifecycle/references/orchestrator-review.md`; allowlist-or-wire `count-tokens` and `audit-doc`; surface `create-backlog-item` / `update-item` directly in their owning SKILL.md references.

## Out of scope

- Runtime adoption telemetry (separate ticket 103 / DR-7).
- New extractions (tickets 105–111).
