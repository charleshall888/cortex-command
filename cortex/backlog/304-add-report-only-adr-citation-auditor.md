---
schema_version: "1"
uuid: f570d455-26ca-45c7-bffa-9c42a0b7d0d7
title: Add report-only ADR citation auditor
status: complete
priority: high
type: feature
created: 2026-06-14
updated: 2026-06-15
parent: "303"
tags: ['cortex-core-tooling-gaps']
discovery_source: cortex/research/cortex-core-tooling-gaps/research.md
complexity: complex
criticality: medium
spec: cortex/lifecycle/add-report-only-adr-citation-auditor/spec.md
areas: []
---
## Why

The repo cites ADR identifiers in well over a hundred files — including production modules — but nothing checks that any of those references resolve to a real decision record. A consumer project building on cortex accumulated dozens of files pointing at ADRs that were never created, plus a duplicate number, and the breakage surfaced only when a human happened to look. The same silent rot can occur here the moment an ADR is renamed, deleted, or mis-numbered.

## Role

Provide a report-only auditor that, on demand, confirms every ADR reference across the repo resolves to an existing decision-record file and flags numbering gaps, duplicate numbers, and proposed-but-unfiled ADR numbers. After it lands, an operator can answer "do all our ADR citations still point at something real?" without hand-grepping, and a renamed or deleted ADR stops being a silent dangling pointer.

## Integration

It joins the family of cortex check utilities, modeled on the informational requirements-parity auditor rather than the blocking events-registry gate — it emits findings and never fails a commit. It reads the decision-record directory as its source of truth and scans the repo for reference tokens; its proposals sub-mode additionally reads the specify-phase template's proposed-ADR entries to catch lifecycles that completed without filing the decision they negotiated. It wires through an in-scope reference so the tooling-parity convention is satisfied, and any event it emits registers in the events registry.

## Edges

- Must stay report-only. The decision-record README makes a deliberate, argued case for prose-only ADR enforcement; a blocking gate would contradict that ratified posture and is out of scope unless a maintainer explicitly overturns the README rationale.
- Bounded to reference-resolution and numbering checks. It does not validate ADR content, status transitions, or supersession chains — those remain human-reviewed.
- The next-free-number helper is an explicit non-goal: existing ADRs are contiguous with no gaps or collisions, so a number-allocation tool solves a problem that has not occurred. The auditor surfaces gaps and collisions if they ever appear, which covers the real risk.
- Folds in one documentation correction: the decision-record README's area-tagging defer-note promises a backfill ticket that was never filed and is not being filed (the area field has no consumer), so the broken promise is removed rather than honored.
- Breaks if the ADR filename convention (the numeric-prefix-plus-slug shape) changes, since reference resolution depends on it.

## Touch points

- `bin/cortex-requirements-parity-audit` — informational-auditor shape to model on (never fails the gate)
- `bin/cortex-check-events-registry:473-535` — registry-backed scanner pattern for "every reference must back to a real target"
- `cortex/adr/README.md:11-17` — the prose-only enforcement rationale that bounds this to report-only
- `cortex/adr/README.md:45` — the area-tagging defer-note to delete (the never-filed backfill promise)
- `skills/lifecycle/references/specify.md:149-155` — the proposed-ADR template the proposals sub-mode reads
- `bin/.events-registry.md` — register any emitted event here
