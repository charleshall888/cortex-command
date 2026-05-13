---
schema_version: "1"
uuid: 905e8b61-56a8-4401-ac59-44b17bf3d743
title: "Refresh install/update docs + close MCP-only auto-update gaps"
status: refined
priority: medium
type: chore
tags: [distribution, upgrade, docs, mcp]
created: 2026-05-13
updated: 2026-05-13
session_id: 0ef921dd-0101-45d9-8b7a-0bd874179699
lifecycle_phase: research
lifecycle_slug: refresh-install-update-docs-close-mcp
complexity: complex
criticality: high
spec: cortex/lifecycle/refresh-install-update-docs-close-mcp/spec.md
areas: [lifecycle]
---

# Refresh install/update docs + close MCP-only auto-update gaps

Umbrella ticket consolidating ten install/update/documentation recommendations surfaced during the #208 (harden-autonomous-dispatch-path-for-interactive) implement phase. Most are docs-only; two are code hygiene; two are bugs against the shipped MCP-architecture refactor (#146) that warrant their own sub-tickets at refine time.

## Context

The #208 lifecycle hardened the autonomous-worktree dispatch path (auth probe, sandbox-friendly worktree wiring, console-script promotion, dispatch readiness fuse). During implement, a follow-up question — "should worktree daytime dispatch work now?" — exposed several misalignments between the install/update mental model the README implies and what the shipped #146 MCP-architecture refactor actually delivers:

- The auto-update mechanism (R4/R8/R10/R13 in `plugins/cortex-overnight/server.py`) is **MCP-tool-call-gated by design**. Per the #145 wontfix event log, the original SessionStart-probe + lazy-apply approach was rejected because "user's actual usage is MCP-primary" — covering bare-shell paths was the rejected premise. #146 shipped with deliberate MCP-only scope.
- The README's marketplace auto-update note ("this will keep CLI auto updated as well") sets a broader expectation than the shipped mechanism actually delivers — auto-update only fires when an MCP tool is invoked, never on Bash-tool subprocess dispatches like `implement.md §1a` Step 3's `cortex-daytime-pipeline` launch.
- The Quickstart relies on `~/.local/bin` already being on PATH; `install.sh` only hints at `uv tool update-shell` in a trailing log line, not as a discrete step.
- A real bug in #146's R8 logic surfaced during inspection: `_maybe_check_upstream` resolves cortex_root via `git rev-parse --show-toplevel` from CWD, so it compares the **working-tree's** HEAD to origin, not the **installed wheel's** pinned commit. When CWD-working-tree-HEAD and installed-wheel-commit diverge (common in dev clones), R8 can report "up to date" while the wheel is far behind.

## Cross-references

- **#145** — `lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke` — `feature_wontfix` 2026-04-25. Premise rejected: bare-shell-primary scoping. Replaced by #146.
- **#146** — `decouple-mcp-server-from-cli-python-imports-via-subprocessjson-contract` — `feature_complete` 2026-04-27. Shipped the auto-update via R4/R8/R10/R13 in cortex-overnight server.py. Archived at `cortex/lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/`.
- **#208** — `harden-autonomous-dispatch-path-for-interactive-claude-code-sessions` — `feature_complete` 2026-05-13. The 22-task lifecycle whose follow-up surfaced these gaps. Its `cortex-daytime-pipeline` launch line in `implement.md §1a` is the canonical Bash-tool dispatch path that bypasses #146's MCP gate.

## Sub-items, grouped by impact tier

### Tier 1 — Docs (single PR, ~45 min, biggest user-facing impact, no code risk)

**1. Quickstart: make PATH setup explicit (README.md)**

The current Quickstart relies on `~/.local/bin` already being on PATH. Convert the trailing log hint in `install.sh:48` ("if 'cortex' is not on your PATH, run 'uv tool update-shell' and reload your shell.") into a numbered Quickstart step. Add a verification snippet `cortex --print-root --format json` so the user confirms a working install before continuing.

**2. README marketplace auto-update note: promote from comment to bullet**

README line 24 today: `# Recommended to turn on Auto-Update Marketplace Plugins (this will keep CLI auto updated as well)`. Promote to a "Recommended settings" bullet with mechanism-accurate wording:

> *"Marketplace auto-update bumps the plugin version; the next MCP tool call triggers the cortex-overnight server's R13 schema-floor mismatch (or R8 upstream-advance check), which orchestrates `uv tool install --reinstall` synchronously and keeps the CLI in lockstep — the auto-update mechanism delivered by ticket #146."*

**3. `docs/setup.md#upgrade--maintenance`: document upgrade paths consolidated**

Today the upgrade flow is fragmented across README, install.sh, server.py, and CHANGELOG entries. Consolidate:
- (a) Marketplace auto-update toggle → next MCP tool call → R13/R8 → reinstall (the durable, intended flow)
- (b) Manual `uv tool install --reinstall git+...@<tag>` (when toggle is off)
- (c) Dev-clone editable install via `uv pip install -e . --no-deps` against `.venv` — venv-local, doesn't touch `~/.local/bin/cortex`

Add an explicit boxed callout: **"Auto-update is MCP-tool-call-gated by design (per #145 wontfix → #146 ship). If your usage path is purely Bash-tool subprocess (skills that launch console-scripts directly without MCP), invoke any MCP tool periodically to drive the upgrade check, or use manual reinstall."** Setting this expectation correctly is the single most important delta in this PR.

**4. In-flight install guard carve-out documentation**

`CORTEX_ALLOW_INSTALL_DURING_RUN=1` is mentioned in `cortex/requirements/pipeline.md` but easy to miss. Add a callout in `docs/setup.md#upgrade--maintenance` so users hitting "install aborted: active overnight session" know the escape hatch exists.

**10. README "auto-update" claim: tighten wording**

Today's wording on README line 24: *"this will keep CLI auto updated as well"*. With #146's reality, that's only true when an MCP tool is invoked. Tighten to *"auto-updates the CLI on next MCP tool invocation"* — accurate, sets the right mental model.

### Tier 2 — Code (separate small PRs)

**7. `implement.md §1a` fail-fast diagnostic when `cortex-daytime-pipeline` is missing**

With #146 deliberately scoped MCP-only, the Bash-tool dispatch path is the explicit gap. `implement.md §1a` Step 3's launch line will today return `command not found: cortex-daytime-pipeline` to stderr (landing in `daytime.log`) if the user's install is behind. Add a pre-launch `command -v cortex-daytime-pipeline` check with a structured error pointing at `uv tool install --reinstall` (or `cortex doctor` if/when that exists). Cheap, user-facing, closes the dispatch-time visibility gap.

### Tier 3 — Hygiene (small patches or backlog items)

**9. `detect-phase` should treat `feature_wontfix` as terminal**

`cortex_command/common.py:detect-phase` looks at artifact presence and review verdicts but doesn't acknowledge `feature_wontfix` events as a terminating condition. The #145 lifecycle still surfaces in the SessionStart "incomplete lifecycles" list as Plan-phase, 18 days after it was explicitly wontfix'd. Fix options:
- (a) Treat any `feature_wontfix` event in `events.log` as `phase=complete` (terminal)
- (b) Require the orchestrator to move wontfix'd lifecycles to `cortex/lifecycle/archive/` as part of the wontfix workflow (#146's lifecycle is already in archive/, suggesting the convention exists but isn't enforced)

Small but reduces SessionStart noise meaningfully — closed lifecycles shouldn't keep prompting "resume?".

### Deferred — file as separate backlog items at refine time

**5. R8 cwd-vs-installed-wheel divergence (#146 follow-up)**

`_maybe_check_upstream` in `plugins/cortex-overnight/server.py` uses `cortex --print-root`'s `head_sha`, which is resolved via `git rev-parse --show-toplevel` from CWD — that's the **working tree's** HEAD, not the **installed wheel's** pinned commit. When the working tree is ahead of origin AND the wheel is far behind both (common during dev iteration on the cortex-command repo itself), R8 reports "up to date" but the wheel is stale. The auto-update can lie about staleness whenever CWD-context and wheel-version diverge.

Fix: R8 should compare upstream against the installed wheel's pinned tag (recorded somewhere in the tool install metadata — `uv tool list` or the install-state dir), not the working tree's HEAD. At minimum, warn when they diverge. File as a backlog item scoped to "#146 follow-up: R8 should track installed-wheel-commit, not CWD-working-tree HEAD."

**6. CLI_PIN drift lint**

`plugins/cortex-overnight/server.py:105` hardcodes `CLI_PIN = ("v0.1.0", "1.0")`. When `main` advances past v0.1.0 and someone bumps the plugin version, CLI_PIN can silently stay stale. A CI lint that compares `CLI_PIN[0]` against the latest tag on `origin/main` and warns if behind would prevent silent drift. Or auto-derive CLI_PIN from `pyproject.toml` version + git tag at build time.

## Recommended order

1. **Tier 1 docs (1, 2, 3, 4, 10) in a single docs PR** — ~45 min, no code risk. The expectation-setting in (3)'s callout and (10)'s wording is the most important delta — it prevents the mental-model failure that motivated this ticket.
2. **Tier 2 code (7) — fail-fast in `implement.md §1a`** — ~15 min. Concrete Bash-path safety net for the deliberately-uncovered dispatch surface.
3. **Tier 3 hygiene (9) — detect-phase wontfix recognition** — ~20 min, or file as a backlog item for lifecycle treatment.
4. **Deferred items (5, 6)** — file as separate backlog items against the #146 area at refine time.

## Non-Goals

- **Re-litigating #145's wontfix decision.** Covering Bash-tool subprocess paths in the auto-update mechanism was the rejected premise. This ticket explicitly does not propose adding Bash-tool dispatch coverage to the auto-update flow — the documented expectation that "auto-update is MCP-tool-call-gated by design" is the durable answer. Sub-item (7) provides a fail-fast diagnostic, not coverage.
- **Replacing #146's R4/R8/R10/R13 architecture.** The shipped MCP-orchestrated upgrade flow is correct for the user's MCP-primary usage model. Sub-item (5) is a focused bug against R8's commit-resolution logic, not an architectural critique.
- **Discovery-phase decomposition.** This is filed as a single umbrella deliberately so refine can decide on decomposition. Sub-items (5) and (6) are explicitly flagged as candidates to break out into their own tickets.
