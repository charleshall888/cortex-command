---
schema_version: "1"
uuid: 48bd525d-6a38-49ef-b7d2-2d2e6301f168
title: "Document CLAUDE_CONFIG_DIR + direnv pattern for per-repo permissions scoping"
status: backlog
priority: critical
type: feature
tags: [setup, configurability, user-configurable-setup, permissions, docs]
created: 2026-04-10
updated: 2026-04-10
parent: "063"
blocked-by: []
discovery_source: research/user-configurable-setup/research.md
---

# Document CLAUDE_CONFIG_DIR + direnv pattern for per-repo permissions scoping

## Context from discovery

The commissioned use case for this discovery was: *"only use project permissions in this repo, ignore global allows."* Research §Web & Documentation Research established that Claude Code's settings merge is strictly additive — arrays like `permissions.allow` concatenate across all scopes with no negation, no per-hook disable beyond the all-or-nothing `disableAllHooks: true`, and `permissions.deny` is monotonic. A native "in this repo, ignore the global allow list" is not possible through settings layering alone.

What IS possible: Claude Code reads a documented environment variable `CLAUDE_CONFIG_DIR` that points the CLI at an alternate user-config directory (default `~/.claude`). Setting it to a per-repo path gives the session an entirely different user scope — its own `settings.json`, its own `skills/`, its own `hooks/`, everything. Combined with per-directory environment-variable injection (direnv, mise, or a shell-wrapper alias), this delivers "in this repo, use a different Claude Code configuration" without any mutation of `~/.claude/settings.json`, any SessionStart hooks, or any new cortex-side state machine.

## Research context from DR-1, DR-7, DR-8

- **DR-1**: Per-repo permission override uses `CLAUDE_CONFIG_DIR`, not settings mutation. Option D (SessionStart hook mutating `~/.claude/settings.json`) was rejected on the grounds that (a) the existing `cortex-sync-permissions.py` hook is architecturally unsuited, (b) the true scope is XL not L once atomicity, concurrent sessions, SessionEnd unreliability, provenance markers, and upstream change detection are accounted for (DR-8 enumerates the 10 requirements), and (c) it would fight upstream Claude Code if issue #12962 or related lands.
- **DR-7**: Upstream activity audit is a gating check on this work. Before finalizing the docs, a short audit of anthropics/claude-code#12962, #37344, #35561, #26489 classifies the upstream landscape as quiet / warm / hot. Each outcome shapes the framing:
  - **Quiet**: proceed with full documentation of the pattern as the supported mechanism.
  - **Warm**: proceed but reference the upstream issues and flag that the pattern may become native.
  - **Hot**: document the pattern explicitly as an interim workaround and point at the upstream issue as the tracking canonical.
  All three framings ship the same core docs — the outcome only changes the preamble and upstream references.
- **DR-8**: If Option D is ever reconsidered, 10 requirements must be satisfied (atomic writes, parse-failure recovery, SessionEnd unreliability handling, provenance markers, concurrent-session coordination, user-edit conflict detection, safe error handling, upstream change detection, nested-repo handling, new-hook-not-extension). Preserved in the research so any future "let's just mutate settings" attempt starts with eyes open.

## What this ticket delivers

This is a **docs-only deliverable**. No new bin utility. No generator. No SessionStart hooks. No state mutation.

- A new docs page (likely `docs/per-repo-permissions.md` or similar) explaining the `CLAUDE_CONFIG_DIR` + direnv pattern for scoping Claude Code configuration per repo.
- An upstream-audit preamble: one paragraph summarizing the audit outcome with links to the tracking issues. The preamble's tone shifts based on quiet/warm/hot but the core "how to do this" content is the same.
- A minimal walkthrough for the commissioned use case: how to create a repo-local shadow of `~/.claude/`, how to set `CLAUDE_CONFIG_DIR` via direnv (`.envrc` example), how to verify Claude Code is reading from the shadow, and how to tear it down.
- A fallback section for users who don't use direnv: shell wrapper alias (`alias claude='CLAUDE_CONFIG_DIR=~/.cortex/repo-shadows/$(basename $PWD) claude'`) or a `just launch` recipe variant. Each fallback is documented with its trade-offs.
- A troubleshooting note covering the known failure modes: stale shadow when `~/.claude/` is updated (users regenerate manually with `cp -r`), direnv trust revocation, confusion about which scope Claude Code is actually reading.
- Cross-links from relevant existing docs (`docs/setup.md`, `CLAUDE.md`, `docs/` index if one exists) so users discovering cortex-command can find this mechanism.

## First sub-task: upstream audit

Before writing the docs, perform the DR-7 audit as the first task of this ticket. Gather:

- Current comment count, thumbs, and last activity date on each of #12962, #37344, #35561, #26489.
- Any Anthropic staff engagement (labels, assignees, comments).
- Any linked PRs suggesting in-progress work.
- Claude Code release notes from the past 3 months touching settings layering, hooks, or permission merge.

Classify the result as quiet / warm / hot per DR-7. Record the findings in the docs page's preamble. The audit is a short read — maybe an hour — and it directly shapes the framing of the rest of the page.

## Success signals

- A user who wants "only use project permissions in this repo" can read the docs page, make a 1-2 minute setup change, and verify that Claude Code running in that repo no longer inherits their global allow list.
- The docs make the mechanism's limitations explicit: it swaps the *entire* user scope, not just permissions; staleness is manual; it requires direnv or a fallback.
- Under a hot upstream audit, the page is framed as an interim workaround and users know to watch the upstream issue. Under warm, it's a documented pattern with upstream context. Under quiet, it's the primary supported mechanism.
- The commissioned use case from the research topic statement is delivered in docs form without any new cortex code.

## Out of scope

- A `bin/cortex-shadow-config` generator binary. If users manually running `cp -r ~/.claude ~/.cortex/repo-shadows/<repo>` proves friction-heavy, build the generator then. Let friction prove the need. Until then, docs + `cp -r` is the smallest viable delivery.
- Any SessionStart hook that mutates `~/.claude/settings.json`. DR-1 explicitly rejected this. DR-8 preserves the real scope if this is ever reconsidered.
- Per-repo skill or hook disable beyond what `CLAUDE_CONFIG_DIR` already provides. The shadow mechanism technically covers this (a shadow can have a different `skills/` directory), but a lighter-weight toggle is deferred (Feasibility Row G; explicit project decision to start with the shadow-only approach).
- Installing direnv for the user. The docs reference direnv as the recommended integration but do not bundle or install it. Users who don't have direnv follow the fallback section.
- Multi-machine state portability. The docs describe setup per machine; cross-machine sharing of shadows is left to whatever dotfile-management tool the user already uses.

## References

- Research artifact: `research/user-configurable-setup/research.md`
- Decision records: DR-1 (`CLAUDE_CONFIG_DIR` over mutation), DR-7 (audit as gating check), DR-8 (Option D real scope preserved)
- Claude Code docs: `CLAUDE_CONFIG_DIR` env var
- Upstream tracking issues: [anthropics/claude-code#12962](https://github.com/anthropics/claude-code/issues/12962), [#37344](https://github.com/anthropics/claude-code/issues/37344), [#35561](https://github.com/anthropics/claude-code/issues/35561), [#26489](https://github.com/anthropics/claude-code/issues/26489)
- Community prior art: [inancgumus dotfile zsh wrapper](https://github.com/anthropics/claude-code/issues/12962#issuecomment-4114842453), [yurukusa hook-based symlink approach](https://github.com/anthropics/claude-code/issues/12962#issuecomment-4150305251)
- Prior art pattern in research §4: direnv + per-directory env var scoping
