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

Routing surface for the v2 requirements workflow: parse `$ARGUMENTS`, then sequence `/requirements-gather` → `/requirements-write`.

## Argument shapes (every shape is load-bearing)

- `/cortex-core:requirements` — bare invocation; project scope.
- `/cortex-core:requirements project` — explicit alias of the bare form.
- `/cortex-core:requirements {area}` — area scope; `{area}` is a kebab-case slug (e.g. `multiplayer`, `observability`).
- `/cortex-core:requirements list` — read-only enumeration of `cortex/requirements/*.md`; skips the gather/write pipeline. Excludes `glossary.md` — a producer-managed vocabulary artifact (per-term append lifecycle), not a scope-level requirements doc.

## Routing

1. If `$ARGUMENTS == "list"`: run the inventory verb (excludes `glossary.md` itself — see above) and act on `state`, then exit either way:

   ```bash
   cortex-list-requirements
   ```

   `absent` → report "No requirements documented yet. Run `/cortex-core:requirements` to start with project-level requirements." `ok` → render `rows` as a table (file, scope, last_gathered, requirement_count).
2. Otherwise resolve `scope`: empty or `project` → `project`; any other single token → that token as the area slug.
3. Invoke `/requirements-gather` with the resolved `scope` and, when `cortex/requirements/{scope}.md` already exists, pass its path as `existing-doc` so the interview refines rather than rewrites.
4. Invoke `/requirements-write` with the same `scope`, the returned Q&A block, and the same `existing-doc` (if any); surface the written artifact path to the user for approval.
5. After user approval, stage `cortex/requirements/` and commit via `/cortex-core:commit`. Requirements are passive artifacts: do not auto-dispatch any consumer here — downstream skills load them on their own schedule. The glossary is the producer-managed exception (`/requirements-gather` appends terms inline; consumers still read it passively, no consumer-driven writes).
