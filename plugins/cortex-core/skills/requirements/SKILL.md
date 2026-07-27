---
name: requirements
description: Use /cortex-core:requirements to gather requirements or define project scope. Thin orchestrator that routes to /requirements-gather then /requirements-write; disable-model-invocation:true — invoked only by explicit slash command.
disable-model-invocation: true
argument-hint: "[area|project|list]"
---

# Requirements (orchestrator)

Parse `$ARGUMENTS`, then sequence `/requirements-gather` → `/requirements-write`.

- **`list`** → run `cortex-list-requirements` and exit. `absent` → "No requirements documented yet. Run `/cortex-core:requirements` to start with project-level requirements." `ok` → render `rows` as a table (file, scope, last_gathered, requirement_count). This excludes `glossary.md`, a producer-managed vocabulary artifact rather than a scope-level doc.
- **empty or `project`** → scope `project`.
- **any other single token** → that token as a kebab-case area slug.

Then: invoke `/requirements-gather` with the resolved scope, passing `cortex/requirements/{scope}.md` as `existing-doc` when it already exists so the interview refines rather than rewrites. Hand its Q&A block plus the same `existing-doc` to `/requirements-write`, and surface the written path for approval. On approval, stage `cortex/requirements/` and commit via `/cortex-core:commit`.

Requirements are passive artifacts — do not auto-dispatch any consumer; downstream skills load them on their own schedule. The glossary is the one producer-managed exception (`/requirements-gather` appends terms inline).
