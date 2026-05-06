---
schema_version: "1"
uuid: 237dcafa-b9e4-4eaa-a090-d7c1dba28b9e
title: "Extend /setup-merge with dynamic per-component opt-in for skills and hooks"
status: complete
priority: high
type: feature
tags: [setup, configurability, user-configurable-setup, setup-merge]
created: 2026-04-10
updated: 2026-04-11
parent: "063"
blocked-by: []
discovery_source: research/user-configurable-setup/research.md
complexity: complex
criticality: high
spec: lifecycle/archive/extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks/spec.md
areas: [skills]
research: lifecycle/archive/extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks/research.md
lifecycle_slug: extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks
session_id: null
lifecycle_phase: complete
---

# Extend /setup-merge with dynamic per-component opt-in for skills and hooks

> **Scope pivot 2026-04-10** — This ticket was originally scoped as the full per-component opt-in feature (dynamic discovery, new `skills:`/`hooks:` frontmatter sections, per-component prompts, `deploy-bin` gating). During the spec phase, a cost/benefit review concluded that the complexity did not earn its place for a single-maintainer project: primary value case (~2.6k tokens/session saved by not loading unused skill frontmatter) is <2% of context, and the implementation commits to ongoing maintenance of a hook-command-string rewriter plus multi-file state coherence. The per-component opt-in work is **deferred indefinitely**.
>
> **Current scope is a 3-requirement foundation cleanup** that fixes latent bugs the research + adversarial + critical-review surfaced — changes that stand on their own regardless of whether opt-in is ever built. The title is retained for lineage; the authoritative scope lives in the linked spec. If opt-in is revisited later, this foundation cleanup is a prerequisite (not wasted work).

## What this ticket delivers (narrowed scope)

The authoritative source is `lifecycle/archive/extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks/spec.md`. Summary:

1. **R1 — Extend `discover_symlinks` to cover `claude/hooks/`.** `merge_settings.py`'s `discover_symlinks()` (L94-185) walks `hooks/cortex-*` but not `claude/hooks/cortex-*`, so 8 hooks in `claude/hooks/` — including Band C `cortex-sync-permissions.py` — are invisible to `/setup-merge`'s conflict detection. Add a parallel walk of `claude/hooks/cortex-*` with the same target mapping. Non-hook files (`bell.ps1`, `output-filters.conf`, `setup-github-pat.sh`) are excluded by the `cortex-*` prefix.

2. **R2 — Reconcile `REQUIRED_HOOK_SCRIPTS` / `OPTIONAL_HOOK_SCRIPTS` with actual `claude/settings.json` wiring.** Three latent footguns in the current constants:
   - `cortex-output-filter.sh` is wired in PreToolUse[Bash] but in neither REQUIRED nor OPTIONAL — invisible to merge logic.
   - `cortex-setup-gpg-sandbox-home.sh`, `cortex-notify.sh`, `cortex-notify-remote.sh` are in OPTIONAL but are all unconditionally wired in settings.json. Prompting them as optional today is a footgun: answering "n" leaves a dangling command reference.
   
   Expand `REQUIRED_HOOK_SCRIPTS` to 13 entries (every wired hook). Delete `OPTIONAL_HOOK_SCRIPTS`. Add an invariant comment: every hook in `claude/settings.json`'s hooks block must appear in REQUIRED.

3. **R3 — Remove the dead optional-hook prompt step from `/setup-merge` SKILL.md.** After R2 deletes `OPTIONAL_HOOK_SCRIPTS`, the SKILL.md step that iterates it for per-hook prompts is dead code. Remove it.

All three requirements must land in the same commit. See spec §Technical Constraints for the landing-order rationale.

## What this ticket explicitly does NOT deliver

Items deferred to future work (originally scoped in, now out of scope):

- Per-component opt-in prompt flow for skills or hooks
- New top-level `skills:` / `hooks:` sections in `lifecycle.config.md`
- `deploy-bin` gating on enabled/disabled skills
- Derived allowlist file at `~/.claude/.cortex-bin-allowlist`
- `test -f` guards on hook commands (not needed because every wired hook is required)
- `install-floor: true` frontmatter migration on SKILL.md or hook files (no code would read the markers)
- Cluster header UX
- `CLAUDE_CONFIG_DIR` honoring in `merge_settings.py`
- Integration test harness for `/setup-merge` (manual verification for a 3-change ticket)
- `lifecycle.config.md` template example update

The original discovery and decomposition that drove the broader scope live in `research/user-configurable-setup/research.md` and `research/user-configurable-setup/decomposed.md`. Those documents are preserved for future reference if per-component opt-in is ever revisited.

## Success signals (narrowed)

- After this ticket lands, `python3 .claude/skills/setup-merge/scripts/merge_settings.py detect` surfaces every hook in `claude/hooks/cortex-*` — the 8 files previously invisible become visible.
- `REQUIRED_HOOK_SCRIPTS` equals exactly the set of hooks wired in `claude/settings.json`'s hooks block (13 entries after reconciliation).
- `OPTIONAL_HOOK_SCRIPTS` is removed from `merge_settings.py`.
- Running `/setup-merge` manually against a clean clone produces zero "[Y/n]" prompts for individual hooks — all hooks are merged silently as required.
- A new audit: an ad-hoc script that walks `claude/settings.json`'s hooks block and extracts basenames returns a set equal to `REQUIRED_HOOK_SCRIPTS`.

## References

- **Spec (authoritative for scope)**: `lifecycle/archive/extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks/spec.md`
- **Research**: `lifecycle/archive/extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks/research.md` (full context, including the deferred opt-in analysis and adversarial findings)
- **Events log**: `lifecycle/archive/extend-setup-merge-with-dynamic-per-component-opt-in-for-skills-and-hooks/events.log` (clarify critic, orchestrator reviews, critical review dispositions, scope descope event)
- **Original discovery (for deferred opt-in work)**: `research/user-configurable-setup/research.md`, `research/user-configurable-setup/decomposed.md`
- **Primary files touched by implementation**: `.claude/skills/setup-merge/scripts/merge_settings.py` (L14-32 constants, L94-185 `discover_symlinks`), `.claude/skills/setup-merge/SKILL.md` (prompt flow step for optional hooks)
