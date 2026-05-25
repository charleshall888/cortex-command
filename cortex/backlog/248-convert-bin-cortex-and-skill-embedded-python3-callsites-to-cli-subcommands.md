---
schema_version: "1"
uuid: 8c7e1f4a-d92b-4a7e-8c1f-7b2a9f3e4d5c
title: "Convert bin/cortex-* and skill-embedded python3 -c callsites to use the cortex CLI"
status: complete
priority: medium
type: feature
created: 2026-05-18
updated: 2026-05-25
tags: [skills, hooks, bin, install-topology]
areas: [skills,hooks]
session_id: 34145bba-3263-48d6-a122-a1e74e9518af
lifecycle_phase: implement
lifecycle_slug: convert-bin-cortex-and-skill-embedded
complexity: complex
criticality: high
spec: cortex/lifecycle/convert-bin-cortex-and-skill-embedded/spec.md
---

## Problem

After the SessionStart hook is refactored into `cortex hooks scan-lifecycle` (lifecycle: `resolve-cortex-interpreter-via-cli`), four other callsites still invoke bare `python3 -c "import cortex_command..."`. Under `uv tool install` distribution they suffer the same install-topology bug the hook fix obviates:

- `bin/cortex-backlog-ready:6-7` — three-branch wrapper, branch (a) is dead under uv-tool; falls through to branch (c) with a misdirecting "cortex-command CLI not found" message even when the CLI is installed.
- `bin/cortex-morning-review-complete-session:6-7` — same three-branch wrapper, same misdirecting message.
- `skills/critical-review/references/residue-write.md:13, 28` — two inline `python3 -c` invocations run inside `/cortex-core:critical-review` autonomous execution.
- `skills/lifecycle/references/implement.md:27` — one inline `python3 -c` invocation run inside `/cortex-core:lifecycle implement` autonomous execution.

The skill-embedded snippets are particularly bad because they run inside autonomous Claude execution paths with no human at the failure surface — they fail with raw `ModuleNotFoundError` traces that aren't read in real time.

## Why it matters

CLAUDE.md's Solution-Horizon principle says: "Before suggesting a fix, ask whether you already know it will need to be redone — because the same patch would apply in multiple known places you can name." Four callsites named here. The hook fix doesn't touch them; they will continue to surface install-topology bugs to users.

This ticket exists as the explicit successor track to the hook fix, named as the blocker for that ticket's Non-Requirements deferral.

## Proposed approach (not locked — Plan/Refine to decide)

The four callsites are NOT a mechanical substitution — they require design decisions:

- **bin/cortex-* wrappers**: choose between (a) shebang-resolve the cortex shim to discover its interpreter and reuse the existing three-branch pattern with a working branch (a-prime), (b) introduce new `cortex <subcommand>` entries (e.g., `cortex backlog-ready`) and reduce the wrappers to `exec cortex backlog-ready "$@"`, or (c) register the bin/* scripts as `[project.scripts]` console-script entries directly and retire the bash wrappers. Option (c) is the most aligned with project.md's documented idiom but is a bigger architectural shift.

- **Skill-embedded snippets**: each needs analysis for whether a corresponding `cortex <subcommand>` should exist, or whether the snippet should be wrapped in a different mechanism (e.g., the resolved-interpreter shebang trick the bin/* scripts use). Skill instructions are documentation the agent reads; the fix is to rewrite the prose around the snippet, not just the snippet itself.

## Out of scope

- The SessionStart hook refactor itself — covered by the `resolve-cortex-interpreter-via-cli` lifecycle.
- Backlog #170's known-fragile bash test scaffolding — separate concern.

## Done-when

- All four named callsites no longer suffer the install-topology bug under `uv tool install`.
- A consistent design choice is documented (which mechanism was chosen and why).
- The misdirecting "cortex-command CLI not found" messages in bin/cortex-* are removed or rewritten so they only fire when the CLI is genuinely absent.
- The skill-embedded snippets fail gracefully (no raw `ModuleNotFoundError`) when the install topology is broken.
- **Structural prevention (deferred from #261)**: A lint rule, pre-commit hook, or test-collection guard is shipped as part of this lifecycle that catches future `SourceFileLoader('...', 'bin/cortex-*')` and `subprocess.run(['bin/cortex-*', ...])` patterns in `tests/` before they merge. #261 (`cortex/lifecycle/fix-test-cascade-from-252-migration/spec.md` D1) deferred this with the explicit understanding that #248's wholesale rewrite of the bin/cortex-* invocation surface would land it — without it, the same cascade pattern recurs on the next migration.
