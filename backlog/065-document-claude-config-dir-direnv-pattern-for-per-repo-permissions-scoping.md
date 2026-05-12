---
schema_version: "1"
uuid: 48bd525d-6a38-49ef-b7d2-2d2e6301f168
title: "Document CLAUDE_CONFIG_DIR + direnv pattern for per-repo permissions scoping"
status: complete
priority: critical
type: feature
tags: [setup, configurability, user-configurable-setup, permissions, docs]
created: 2026-04-10
updated: 2026-04-11
parent: "063"
blocked-by: []
discovery_source: cortex/research/user-configurable-setup/research.md
complexity: simple
criticality: high
spec: cortex/lifecycle/archive/document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping/spec.md
areas: [docs]
session_id: null
lifecycle_phase: complete
---

# Document CLAUDE_CONFIG_DIR + direnv pattern for per-repo permissions scoping

## Context from discovery

The commissioned use case was *"only use project permissions in this repo, ignore global allows."* Research §Web & Documentation Research established that Claude Code's settings merge is strictly additive (arrays concatenate, no negation, `deny` is monotonic), so layering alone cannot deliver subtraction. The supported mechanism is `CLAUDE_CONFIG_DIR` pointing at a shadow user scope, combined with direnv (or a shell alias / wrapper script) for per-directory env var injection.

## Final scope: docs-only, one commit

This ticket ships **a single section inside `docs/setup.md`** (~30–80 lines) documenting the `CLAUDE_CONFIG_DIR` + direnv pattern with an honest limitations list. Paired with the sibling ticket #064's foundation-cleanup descope, this ticket follows the same "complexity must earn its place" principle: deliver the smallest useful artifact and let actual user friction drive any follow-up tooling.

The section must cover:
- WARM preamble with links to upstream `anthropics/claude-code#12962` and `#26489` and a "watch these issues" note
- direnv walkthrough with `.envrc` example
- `cp -R` symlink trap warning with explicit `rm` instructions for host-shared files (`settings.json`, `statusline.sh`, `notify.sh`, `CLAUDE.md` — verified empirically in research §4.1)
- Limitations list covering all 5 cortex-command foot-guns plus upstream Claude Code partial-support bugs
- Background link to `research/user-configurable-setup/research.md`

## What the 5 foot-guns are

Each is documented as a "don't do this" or "this has the following failure mode" — **not fixed**:

1. **`/setup-merge` hardcodes `~/.claude`** — do not run from a shadowed shell (silently bypasses the shadow).
2. **`just setup` hardcodes `~/.claude`** — re-run `just setup` from the shadow shell when the host updates, or use `cp -R --update` to refresh.
3. **`claude/settings.json` notify hook** references `~/.claude/notify.sh` literally — notify hook fires from the host path. Workaround: keep a host install alongside the shadow.
4. **Memory-path prose** in skill references `~/.claude/projects/...` — auto-memory under a shadow writes to the host scope. (Originally cited `skills/evolve/SKILL.md`; that skill was removed in #171, but the underlying shadow-vs-host memory-path concern still applies wherever skill prose touches `~/.claude/projects/...`.)
5. **`bin/audit-doc` and `bin/count-tokens`** fall back to `~/.claude` — users in a shadow get host results.

## What is deliberately NOT in this ticket

- **No new `docs/per-repo-permissions.md` file.** Content lives inside `docs/setup.md`.
- **No infrastructure fixes.** The ~85 hardcoded-path edits to `justfile`, `merge_settings.py`, `evolve`, `bin/audit-doc`, `bin/count-tokens`, and `claude/settings.json` are explicitly deferred. The docs warn about each; if a specific foot-gun starts biting in actual use, file a targeted follow-up ticket then.
- **No cross-links from README.md or CLAUDE.md.** If the section proves hard to find, add them in a follow-up.
- **No `bin/cortex-shadow-config` generator, no SessionStart hook, no `cortex doctor` CLI.** Deferred.
- **No regression tests.** Docs-only changes don't need `just check-symlinks` gates.

## First sub-task: DR-7 re-audit

Before writing the docs section, re-check the DR-7 audit (originally classified WARM on 2026-04-10):

```bash
gh issue view 12962 --repo anthropics/claude-code --json state,comments,labels,assignees
gh issue view 26489 --repo anthropics/claude-code --json state,comments,labels,assignees
```

If the audit is still WARM (both issues open, no Anthropic assignee, no roadmap label, no linked closing PR), proceed. If it has materially changed, halt and report to the user — the WARM-shape preamble would stake credibility on stale state.

## Success signals

- A user who wants "only use project permissions in this repo" can read the section, make a 1–2 minute setup change, and verify their Claude Code session no longer inherits the global allow list.
- The limitations are explicit — users know the shadow mechanism swaps the *entire* user scope, that `cp -R` on macOS creates symlink traps, that `/setup-merge` doesn't understand shadows, and that the notify hook fires from the host path.
- The commissioned use case is delivered without any cortex-command code changes.
- If upstream `#12962` or `#26489` lands, the section's "watch these issues" preamble has already told users how to migrate away cleanly (delete the `.envrc` line, `rm -rf` the shadow dir).

## References

- Research artifact: `research/user-configurable-setup/research.md`
- Lifecycle research: `lifecycle/archive/document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping/research.md`
- Spec: `lifecycle/archive/document-claude-config-dir-direnv-pattern-for-per-repo-permissions-scoping/spec.md`
- Decision records: DR-1 (`CLAUDE_CONFIG_DIR` over mutation), DR-7 (audit as gating check, hot→minimal framing), DR-8 (Option D real scope preserved)
- Upstream tracking issues: [anthropics/claude-code#12962](https://github.com/anthropics/claude-code/issues/12962), [#26489](https://github.com/anthropics/claude-code/issues/26489)
