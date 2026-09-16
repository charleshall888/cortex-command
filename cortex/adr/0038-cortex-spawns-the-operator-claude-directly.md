---
status: accepted
---

# 0038 — cortex spawns the operator's claude directly

## Context

cortex reached the Claude CLI through `claude-agent-sdk`, whose wheels bundle a ~90 MB `claude` binary
that cortex already routes around, and whose publisher yanks and deletes old releases to stay under a
storage quota — which broke every install on 2026-09-16.

## Decision

cortex spawns the operator's own `claude` as a subprocess (`-p --output-format stream-json --verbose`,
prompt on stdin) and parses the JSON-lines stream itself, reading only the fields it needs and skipping
everything else. `resolve_claude_cli()` keeps its system search, including the non-PATH fallbacks, and
loses only the SDK-bundled branch.

This supersedes the bundled-vs-system half of ADR-0014 while preserving its effort-by-outcome handling,
and amends ADR-0032's mechanism wording: the observed model is read from the `assistant` frame, not from
`AssistantMessage`.

## Trade-off

cortex trades a pinned, range-tested Python contract for an unversioned CLI surface it must tolerate
defensively — in exchange it drops 216 MB, one dependency, and a recurring supply-chain fuse, and it
takes the integration path Anthropic's own documentation prescribes for non-SDK callers.

## Cross-references

- Spec: `cortex/lifecycle/remove-claude-agent-sdk-dependency/spec.md` — Proposed ADR 0038.
- Amends: ADR-0014 (bundled-vs-system half superseded; effort-by-outcome half kept), ADR-0032 (model
  read from the `assistant` frame).
