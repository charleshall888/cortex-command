# Decomposition: post-113-repo-state

## Work Items

| ID  | Title                                                                                  | Priority | Size | Depends On |
|-----|----------------------------------------------------------------------------------------|----------|------|------------|
| 147 | Sunset cortex-command-plugins and vendor residual plugins into cortex-command           | medium   | M    | —          |
| 148 | Apply post-113 audit follow-ups: stale-doc cleanup, lifecycle-archive run, MCP hardening | high     | M    | —          |

## Suggested Implementation Order

148 first, then 147. Rationale:
- 148 contains S1 (MCP discovery-cache fix) — highest-value finding for the project's primary use case (multi-hour overnight runs). Should not wait.
- 147 is a cross-repo distribution change with one-time migration impact for any cortex-command-plugins users. Lower urgency; benefits from being done deliberately.
- The two tickets are independent (no shared files of consequence) and can be sequenced or parallelized as preferred.

## Key Design Decisions

**User-driven consolidation (this session)**: The original decomposition produced 8 tickets — 1 epic + 3 children for the sunset, plus 4 standalone tickets (stale-doc cleanup, lifecycle-archive run, MCP discovery-cache, MCP graceful-degrade). User requested consolidation to 2 tickets:
- Sunset epic + children → single ticket #147 (lifecycle plan phase will sequence the vendor + register + migrate + archive sub-steps internally).
- Standalone tickets 151–154 → single ticket #148 (lifecycle plan phase will sequence stale-doc cleanup → lifecycle-archive run → MCP discovery-cache → MCP graceful-degrade).

Rationale: the user prefers fewer, larger tickets at this maintenance scale. The lifecycle plan phase is the right place to break each ticket into implementation sub-steps. The two-ticket grouping preserves the natural boundary between distribution-layer change (cross-repo, externally visible) and post-audit follow-ups (in-repo, mostly internal).

Both tickets use `type: feature` rather than `type: epic` per backlog schema (epic is reserved for non-implementable parents that have children).

## Created Files

- `backlog/147-sunset-cortex-command-plugins-and-vendor-residual-into-cortex-command.md` — Sunset cortex-command-plugins
- `backlog/148-apply-post-113-audit-followups-stale-doc-cleanup-lifecycle-archive-mcp-hardening.md` — Apply post-113 audit follow-ups
