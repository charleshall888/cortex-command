---
schema_version: "1"
uuid: 9f7c269f-0dfd-4e96-88ed-83bca9e88da7
title: Add a report-only file:line citation auditor for backlog, requirements, and lifecycle prose
status: backlog
priority: medium
type: feature
created: 2026-08-03
updated: 2026-08-03
tags: ['tooling', 'auditor', 'docs', 'citations']
areas: ['tooling']
---
## Why

**#304 shipped `cortex-adr-citation-audit` (complete) and it reads the decision-record directory as its
source of truth.** Nothing audits the far more common and far more load-bearing citation form: a
`path/to/file.gd:NNN` reference embedded in backlog, requirements, lifecycle, or `CLAUDE.md` prose.

Those citations rot silently, they rot *fast*, and downstream work treats them as verified. Four distinct
instances in a **single** `/cortex-core:refine` run (wild-light #432, 2026-08-03):

1. The backlog ticket's Touch points cited `autoloads/migration_coordinator.gd` — **a path that does not
   exist**; the file had moved to `autoloads/migration/`. Caught only because a grep for the symbol failed.
2. `cortex/requirements/engineering.md:807` cites `migration_coordinator.gd:235` for a timer that lives at
   `:272`. Still wrong at HEAD.
3. A one-line comment edit made *during the same session* (a docs fix at `migration_coordinator.gd:245`)
   shifted every line below it by one, invalidating `:271`/`:366-368`/`:375` citations written into the
   ticket **an hour earlier**.
4. The spec's acceptance criterion cited `tests/unit/test_migration_cutover.gd:122-171` as pinning a
   specific guard member. `grep -c` for that member in that file returns **0** — the whole file has none.
   The requirement therefore enforced half of what it claimed, and a critical reviewer caught it.

(4) is the shape that matters: a **line-range citation used as an acceptance anchor**, where being wrong
means a requirement silently passes. (3) shows the half-life can be under an hour, and that the session
causing the rot is often the session relying on the citation.

Consumer-repo memory already encodes this as a standing hazard ("plan line citations rot mid-implement",
"cross-citing artifacts echo one read") — which is evidence the discipline does not hold on its own and
wants tooling, not more prose.

## Role

Add a report-only auditor for `file:line` and `file:line-line` citations in tracked markdown, in the same
informational family as `cortex-adr-citation-audit` and `bin/cortex-requirements-parity-audit` — emits
findings, never fails a commit.

Minimum useful checks, in increasing cost:

- **Path exists.** Catches (1) outright, and is nearly free.
- **Line number is in range** for the cited file. Catches the crudest drift.
- **Optional anchor check**: when a citation is accompanied by a backticked symbol in the same sentence
  (the dominant convention: `` `migration_coordinator.gd:272` `` near `` `on_migration_timeout` ``),
  verify the symbol appears within a tolerance window of the cited line. This is what would have caught
  (2) and (4) — the cases where the path and range are both valid and the citation is still false.

## Integration

- New `bin/cortex-citation-audit` (or a sub-mode of the existing ADR auditor — decide which; a separate
  verb avoids overloading a shipped contract).
- Model on `bin/cortex-requirements-parity-audit` (informational, never gates) per #304's own stated shape.
- Scan targets: `cortex/backlog/`, `cortex/requirements/`, `cortex/lifecycle/`, `docs/`, `CLAUDE.md`.

## Edges

- **Must not gate a commit.** Line drift is constant and mostly harmless; a blocking gate would be turned
  off within a week. The value is a report an author can run before citing, and a reviewer can run before
  trusting.
- **False positives are the main risk.** Citations to deleted files in *historical* records (completed
  lifecycle artifacts, closed tickets, capture provenance) are correct-as-written and must not be flagged
  — a capture file documenting what a line said in July is not rot. Scope by `status:` and/or by directory,
  and make the default conservative.
- Line ranges spanning a region (`:122-171`) need a different anchor rule than point citations.
- The anchor check is heuristic by construction. Report it at a lower confidence tier than
  path-does-not-exist, and never merge the two into one count.
- This is a *reporting* tool. The deeper fix — preferring symbol anchors over line numbers in authored
  prose — is a convention change and is out of scope here.

## Touch points

- `cortex/backlog/304-add-report-only-adr-citation-auditor.md` (complete — the shape to model on, and the
  scope boundary this ticket extends)
- `bin/cortex-requirements-parity-audit` (informational-auditor precedent)
- `bin/cortex-adr-citation-audit`
