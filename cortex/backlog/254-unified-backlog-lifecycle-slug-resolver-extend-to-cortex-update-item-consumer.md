---
schema_version: "1"
uuid: f5887b4d-ad3e-485e-9c8e-a1269f5107b4
title: "Unified backlog/lifecycle slug resolver: extend to cortex-update-item consumer"
status: complete
priority: medium
type: feature
created: 2026-05-20
updated: 2026-05-25
parent: "251"
tags: [backlog, lifecycle, slug-resolution]
discovery_source: cortex/research/harness-friction-triage/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/unified-backlog-lifecycle-slug-resolver-extend/spec.md
areas: [backlog,skills]
---

## Role

Extends the already-shipped resolver (tickets 109 and 176, both `complete`) to the `cortex-update-item._find_item` consumer with a deterministic resolution order spanning all four slug forms in circulation: UUID prefix, then numeric ID, then exact filename stem with-or-without the leading numeric prefix, then exact `lifecycle_slug` frontmatter match, then ranked title-substring fallback. Replaces the current silent first-match substring behavior with explicit ambiguity surfacing — when multiple candidates rank equally, the resolver returns a ranked list rather than picking arbitrarily.

## Integration

Consumes the resolver module already extracted under `cortex_command/backlog/`. Per Decision Record DR4 in the discovery research, the boundary that previously kept the bash resolver script outside the wheel disappears — the bash script is promoted to a Python entry point in the installation-integrity child — so a single shared resolver module becomes structurally reachable from all consumer sites without crossing the install_guard boundary.

## Edges

- Breaks if slug forms gain a new structural shape (e.g., an epic-prefix encoding) that the resolver's deterministic ordering does not anticipate.
- Behavior change: each CLI begins accepting inputs it currently rejects fast. A regression sample covering every (CLI, input) pair where current behavior is fail-fast must be evaluated under the new order before the resolver ships.
- Depends on the installation-integrity child closing the install_guard boundary for this resolver per Decision Record DR4; absent that closure, the bash side remains a parallel resolver to consolidate by other means.

## Touch points

- `bin/cortex-resolve-backlog-item:113-152` — current resolver logic; subsumed by the Python entry-point promotion landed in the installation-integrity child.
- `cortex_command/backlog/update_item.py:128-152` — target consumer; currently does unranked substring matching at lines 142-145 and UUID-prefix matching at 147-152.
- `cortex_command/overnight/backlog.py:104-130` — parallel resolver path to consolidate against the shared module.
- `tests/test_resolve_backlog_item.py` — test surface to extend for ambiguity cases and the newly-accepted-input regression sample.
