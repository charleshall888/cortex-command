---
schema_version: "1"
uuid: e634fb4a-f683-4141-9cd9-2373d1690711
title: "Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations"
status: complete
priority: high
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, discoverability, enforcement]
created: 2026-04-21
updated: 2026-04-28
discovery_source: cortex/research/extract-scripts-from-agent-tool-sequences/research.md
session_id: null
lifecycle_phase: complete
lifecycle_slug: ship-dr-5-skillmd-to-bin-parity-linter-with-zero-existing-violations
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/ship-dr-5-skillmd-to-bin-parity-linter-with-zero-existing-violations/spec.md
areas: [skills]
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

> **2026-04-27 (epic #113 complete) — scope amendment.** The distribution model assumed in the original Scope above is dead post-113.
>
> **Deploy mechanism (L31, L35):** `just deploy-bin` no longer exists; the linter ships as `bin/cortex-check-parity` and is built into `plugins/cortex-interactive/bin/` via `just build-plugin` (drift-checked by `.githooks/pre-commit`). The `cortex-` prefix is structural — `build-plugin` filters with `--include='cortex-*' --exclude='*'`.
>
> **Symlink-deploy inventory (L35) is moot:** cortex no longer symlinks into `~/.claude/` or `~/.local/bin/` (per CLAUDE.md). Replace the inventory item with: enumerate plugin-tree deploy patterns — top-level `bin/cortex-*` → `plugins/cortex-interactive/bin/`; top-level `hooks/cortex-*.sh` and `claude/hooks/cortex-*.sh` → routed to either `cortex-interactive` or `cortex-overnight-integration` per `justfile:420-432`.
>
> **Scan scope (L33):** drop `claude/reference/` (directory removed). Open call for `/refine`: scan top-level `skills/` only and rely on `build-plugin` drift detection, OR scan `plugins/*/skills/**/*.md` too. The drift-only approach is simpler.
>
> **Signal categories (L34):** drop the `~/.local/bin/foo` heuristic — that target is dead.
>
> **Retrofit list (L36) is partially already done:** `cortex-update-item`, `cortex-create-backlog-item`, `cortex-generate-backlog-index` are already wired in current SKILLs. Re-scope the retrofit at refine time. Real fixtures the linter should catch on its first run: `skills/morning-review/references/walkthrough.md` references `git-sync-rebase.sh` (5 occurrences; actual binary is `cortex-git-sync-rebase`); `skills/lifecycle/references/complete.md` falls back to `~/.local/bin/generate-backlog-index` (dead path).
>
> **Open question for refine:** does `validate-spec` get renamed to `cortex-validate-spec` to ride plugin distribution, or stay un-prefixed and ship via the `cortex` CLI itself? The current top-level `bin/validate-spec` is the only remaining un-prefixed script that 102 cared about.
