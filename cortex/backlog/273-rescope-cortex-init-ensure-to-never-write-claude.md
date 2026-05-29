---
schema_version: "1"
uuid: a66a9fe8-67c4-4243-8f31-f80e289a6528
title: "Rescope cortex init --ensure to never write ~/.claude/"
status: refined
priority: high
type: feature
created: 2026-05-29
updated: 2026-05-29
discovery_source: cortex/research/cortex-init-scope-reduction/research.md
tags: [cortex-init, distribution, sandbox, in-session]
complexity: complex
criticality: high
spec: cortex/lifecycle/rescope-cortex-init-ensure-to-never/spec.md
areas: ['skills']
---
## Why

`cortex init --ensure` (the in-session entry point called by `cortex-lifecycle-init-ensure`) currently attempts to write `~/.claude/settings.local.json` from a Bash subprocess inside Claude Code. The sandbox blocks this, forcing the calling sub-agent to retry with `dangerouslyDisableSandbox: true`. For new adopters evaluating cortex-command for distribution, the visible permission-bypass is a deal-breaker UX — users reasonably distrust tools that ask to bypass the security model they were just installed under. Per gap 3 of the discovery, this case is the *modal* first-contact path: the project's own README/landing-page guidance leads adopters to /plugin install + /lifecycle without ever running terminal cortex init, so the prompt-bypass pattern fires on first contact.

## Role

Restrict cortex init --ensure to repo-scope writes only. Never touch ~/.claude/. The flag itself encodes the user-vs-AI consent boundary: a write the user explicitly typed in their terminal can mutate ~/.claude/; a write an in-session AI helper performs cannot. Marker-present cases continue to refresh cortex/ content as today (sandbox-allowed under the repo's working directory). Marker-absent case refuses with a stderr directive pointing the user to terminal cortex init, instead of attempting to scaffold. Terminal cortex init's behavior is unchanged.

## Integration

The lifecycle skill at Step 2 invokes cortex-lifecycle-init-ensure before each phase dispatch. Today it expects exit 0 to proceed and exit 2 to indicate user-correctable failure. Under this change, the marker-absent exit-2 return must be surfaced by the lifecycle skill as a halt with user-visible message — not retried, not ignored. The README's OPTIONAL framing of cortex init and the landing page's plugin-install-first guidance must be corrected so that the modal first-contact path leads adopters to terminal init before they invoke /lifecycle.

## Edges

- Breaks the auto-apply-cortex-init-at-lifecycle spec's in-session-ensure-on-clean-scratch-repo acceptance criterion. Deliberate contract revision — spec amends inline with rationale or via follow-on lifecycle; the marker-absent case returns exit 2 with directive instead.
- Depends on Claude Code's sandbox semantics: writes to ~/.claude/ from in-session Bash subprocesses remain denied. Verified against current Anthropic docs.
- Coordinates with the existing terminal cortex init / --update / --force / --unregister verbs. These paths unchanged; --ensure becomes refresh-only.

## Touch points

- cortex_command/init/handler.py:129-247 (_run_ensure — remove validate_settings call at :163, register call at :240, unregister_matching_in_place at :245; add marker-absent stderr + exit 2)
- cortex_command/init/tests/test_handler_ensure.py:517-545 (test_r8_bundle5 — update case iii expectation)
- plugins/cortex-core/skills/lifecycle/SKILL.md:15,128 (Step 2 invocation — handle exit 2 with stderr surfacing + halt)
- README.md:27 (remove OPTIONAL framing of cortex init)
- docs/index.html:6659-6671 (landing page Start here path — include cortex init before /lifecycle)
- cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md R4(1) (acceptance criterion — inline amendment with rationale + commit linkage)