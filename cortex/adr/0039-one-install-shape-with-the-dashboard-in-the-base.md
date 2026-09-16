---
status: accepted
---

# 0039 — One install shape with the dashboard in the base

## Context

The extras split exists because the overnight stack pulled a 197 MB SDK; with that gone, the only
optional weight is the ~17 MB dashboard stack, while the auto-installer has always installed `[all]`
anyway, so in practice every operator already carries it.

## Decision

The dashboard's dependencies move into the base install, and `[all]` / `[dashboard]` / `[overnight]` stay
declared but empty so every published install command — including the plugin auto-installer's
version-locked argv — keeps resolving.

## Trade-off

A backlog-only user downloads ~17 MB they may not use, and the extra names survive as vestigial
vocabulary; in exchange there is one install shape to document and test, the dashboard works for
operators who do not use Claude Code at all, and a class of "reinstalled without the right extra"
failures disappears. One consequence is not inert and is handled rather than accepted: the presence of
`uvicorn` is today the predicate that decides whether an operator wants the macOS app at all, so the
collapse would otherwise hand every macOS operator a compiled applet at `cortex init` time — the app
therefore moves behind the first `cortex dashboard` run, which is an expressed intent.

## Cross-references

- Spec: `cortex/lifecycle/remove-claude-agent-sdk-dependency/spec.md` — Proposed ADR 0039.
