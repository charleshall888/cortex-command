---
name: requirements
description: Use /cortex-core:requirements to gather requirements or define project scope. Thin orchestrator that routes to /requirements-gather then /requirements-write; disable-model-invocation:true — invoked only by explicit slash command.
disable-model-invocation: true
argument-hint: "[area|project|list]"
inputs:
  - "$ARGUMENTS: optional — empty or 'project' for project scope; an area kebab-case slug for area scope; 'list' to enumerate existing requirements docs"
outputs:
  - "cortex/requirements/project.md (project scope) OR cortex/requirements/{area}.md (area scope) — written by /requirements-write"
---

# Requirements (orchestrator)

Thin routing surface for the v2 requirements workflow. Sequence: parse `$ARGUMENTS` → optionally short-circuit on `list` → dispatch `/requirements-gather` → hand the returned Q&A block to `/requirements-write`.

## Argument shapes (every shape is load-bearing — see `cortex/lifecycle/requirements-skill-v2/requirements-caller-audit.md`)

- `/cortex-core:requirements` — bare invocation; project scope.
- `/cortex-core:requirements project` — explicit project-scope alias of the bare form.
- `/cortex-core:requirements {area}` — area scope; `{area}` is a kebab-case slug (e.g. `multiplayer`, `observability`).
- `/cortex-core:requirements list` — read-only enumeration of `cortex/requirements/*.md`; does NOT enter the gather/write pipeline. The enumeration explicitly excludes `glossary.md` — it is a producer-managed vocabulary artifact with a per-term append lifecycle rather than a scope-level requirements doc, and surfacing it alongside project/area docs would conflate two different artifact lifecycles.

## Routing

1. If `$ARGUMENTS == "list"`: scan `cortex/requirements/` and present a table (file, scope, last-gathered date, requirement count), excluding `glossary.md` (rationale above — different artifact lifecycle). Exit. If the directory is absent, report "No requirements documented yet. Run `/cortex-core:requirements` to start with project-level requirements." and exit.
2. Otherwise resolve `scope`: empty or `project` → `project`; any other single token → that token as the area slug.
3. Invoke `/requirements-gather` with the resolved `scope` and, when `cortex/requirements/{scope}.md` already exists, pass its path as `existing-doc` so the interview refines rather than rewrites.
4. When gather returns the Q&A block, invoke `/requirements-write` with the same `scope`, the Q&A block, and the same `existing-doc` (if any). Surface the written artifact path to the user for approval.
5. After user approval, stage `cortex/requirements/` and commit via `/cortex-core:commit`. Requirements are passive artifacts — downstream skills (lifecycle, refine, discovery, review) consume them on their own loading schedule; do not auto-dispatch any consumer here. The glossary (`cortex/requirements/glossary.md`) is a producer-managed exception to the passive-artifact framing: it grows inline during requirements interviews via per-term appends by `/requirements-gather`, but consumers still treat it as passive on read (load via the tag-based protocol, no consumer-driven writes).
