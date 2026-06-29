---
status: proposed
---

# Structural /cortex-core:lifecycle invocation grammar

## Context

`/cortex-core:lifecycle` advertised reserved-first-word and phase-first invocation
forms across multiple prose surfaces — the frontmatter `argument-hint`, the
Invocation block, the honor-phase line, Step 1's parse, and `references/complete.md`
— but Step 1 actually parsed *first-word-as-feature* with no reserved-word
handling. The advertised forms were never implemented, so four were silently
broken: `wontfix <slug>` → `feature="wontfix"`, `resume <feature>` →
`feature="resume"`, `complete <slug>` → `feature="complete"`, and bare `<phase>`
(e.g. `plan`) → `feature="plan"` (a phantom lifecycle). The grammar was
prose-specified across drifted surfaces with no test, so the breakage went
unnoticed until the 2026-06-25 lifecycle reference-file audit (backlog #329). The
already-shipped-broken `complete <slug>` is direct evidence that prose-only
first-word parsing here had *already* drifted — the failure mode CLAUDE.md's
"prefer structural separation over prose-only enforcement for sequential gates"
warns against.

## Decision

Make a small `cortex-lifecycle-parse-args` CLI the single, unit-tested source of
truth for the invocation grammar. It emits `{"mode", "feature", "phase"}` and owns
the full grammar: reserved verbs `{wontfix, resume, complete}` and phase tokens
`{research, specify, plan, implement, review}` plus the default `<feature> [phase]`,
with the reserved/phase-first forms inverting the default order. The canonical
parse order is empty-check → `#`-sigil handling → reserved-word match →
slug/prose-derivation; the irreducible prose→slug derivation remains a model step
the helper signals via a `needs-derivation` mode. SKILL.md Step 1 is reduced to a
thin act-on-`mode` routing table, and a **docs-derived drift-guard**
(`tests/test_lifecycle_invocation_grammar_parity.py`) scrapes the advertised forms
from the live doc bytes and asserts the parser classifies each correctly, with a
bidirectional negative control and a mode-coverage proxy.

## Consequences

- The **doc↔parser drift class** is structurally closed: a doc gaining a form the
  current grammar mis-handles fails the drift-guard; a parser change that breaks an
  advertised form fails it too.
- All four previously-broken advertised commands route correctly; bare phase
  tokens stop creating phantom lifecycles (feature-required fallback). Full
  bare-phase-token "active feature" routing is deferred to a cross-linked sibling
  ticket — it needs an active-feature concept that does not exist yet.
- An explicit-phase-override route in SKILL.md Step 1 consumes the parser's `phase`
  for `complete <slug>` and `<feature> <phase>`, since `cortex-common detect-phase`
  routes on artifacts and ignores an explicit phase.

## Scope honesty (the residual)

The structural parser closes the **doc↔parser** drift class; the **parse↔dispatch**
glue — SKILL.md acting on `mode` — remains model-executed prose, reduced to a thin
act-on-`mode` table guarded by a mode-coverage proxy, not eliminated. The
drift-guard's shape-keyed oracle shares the parser's closed grammar, so a
genuinely **new reserved verb** added to docs-only is classified `feature` by both
oracle and parser (they agree → green); catching that requires updating the oracle
and grammar together. These residuals are acknowledged, not eliminated.

## Trade-off

Rejected the lower-cost prose reserved-word table because the already-broken
`complete <slug>` is direct evidence that prose-only first-word parsing here had
already drifted. The decision clears the ADR three-criteria gate: it is hard to
reverse once docs and tests depend on the parser; it is surprising without context
(the feature/phase inversion, a separate parse CLI, and a docs-scraping test); and
it is a real trade-off (structural parser CLI vs prose reserved-word table). The
companion `cortex-lifecycle-wontfix` order-enforcing verb does **not** clear that
bar (a one-pattern refactor with precedent) and back-points to ADR-0004 rather than
adding an ADR of its own.
