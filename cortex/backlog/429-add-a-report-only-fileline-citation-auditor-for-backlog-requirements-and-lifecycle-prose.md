---
schema_version: "1"
uuid: 9f7c269f-0dfd-4e96-88ed-83bca9e88da7
title: Add a report-only file:line citation auditor for backlog, requirements, and lifecycle prose
status: abandoned
priority: medium
type: feature
created: 2026-08-03
updated: 2026-08-03
tags: ['tooling', 'auditor', 'docs', 'citations']
areas: ['tooling']
complexity: complex
criticality: medium
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

## Folded in from #444 (2026-08-03)

#444 ("Catch a decompose ticket body that contradicts its source research") asked whether one
auditor covers three failure shapes: a citation that does not resolve (this ticket), a citation
that resolves but whose stated behavior contradicts its source research (#444), and a research
artifact that asserts an unverified fact (#411). **It does not, and the reason is worth
recording before anyone builds the anchor check.**

#444's founding incident is invisible to this auditor. The contradicted claim was #436's
Integration sentence — *"The parent-closing cascade reads the same normalized status"* — which
carried **no `file:line` citation at all**. The research it contradicted did carry one
(`cortex/research/staged-epic-gate-tickets/research.md:31`, citing `:299` and `:333`). An
auditor that checks citations found nothing to check. #436's second wrong claim ("Three epics
are held open this way" — two) was an uncited count verifiable only by a census in another repo.

The three shapes do not share an oracle. This ticket's oracle is the filesystem (does the path
exist, is the line in range, does the symbol appear nearby) — deterministic, runnable anytime
over tracked markdown. #444's oracle is another prose document, and #411's is the code itself.
Only the first is a citation audit; the other two are judgments. Merging them would put an
LLM comparison behind the same verb as a `stat()` call and would inherit #444's own warning that
"an agent-authored comparison of prose against prose is exactly the kind of judgment that
produces false confidence."

**What this ticket absorbs from #444:** extend the scan targets to include the research artifact
a ticket's `discovery_source` points at (a real, populated field — 230 tickets carry it, read by
`refine.py:492` and indexed by `generate_index.py:208`). A citation in a research artifact rots
exactly the way one in a ticket body does, and auditing both is free once the engine exists.

**What is explicitly declined:** the general prose-against-prose comparison. No mechanical check
catches an uncited assertion that contradicts a cited source — the heuristic of flagging factual
claims that name no line does not fire on #436's sentence either, which names no backticked
symbol. The instrument that caught it was a reader opening the function. Reaching that case
structurally means requiring load-bearing claims to carry citations at the decompose boundary,
which is a convention change and a real authoring tax on the 4-in-5 tickets that were faithful —
out of scope here and not currently filed.

## Closed 2026-08-03 — premise did not survive measurement

Closed at the Clarify gate of `/cortex-core:refine`, before research. Per project.md's
"Verify with existing tools (grep/read/one-off script) before building measurement tooling",
the oracle was reproduced in throwaway scripts first. It does not support the ticket.

**The citation form this ticket is built on is a minority of the corpus.** Across tracked
markdown in the named scan targets, excluding `archive/` — 7,755 backticked `file:line`
citations in non-terminal artifacts:

| Form | Count | Share |
|---|---|---|
| Repo-relative path, resolves as written | 2,359 | 33% |
| Bare basename (`batch_runner.py:206`) | 3,695 | 48% — 1,316 ambiguous across 2–9 tracked files |
| Partial path (`overnight/events.py`, `lifecycle/resolve.py`) | ~1,088 | 14% — nearly all real files under `cortex_command/` |
| Genuinely dangling | remainder | — |

The Role section assumes `path/to/file.gd:NNN`. Two-thirds of the corpus is not that shape, so
*path resolution with an ambiguity policy* precedes every check the ticket names, and the ticket
never mentions it. Run naively, the cheapest check alone reports ~4,800 findings on this repo —
the exact "turned off within a week" outcome the Edges section warns about.

**The stated exclusion mechanism does not function.** Edges says "Scope by `status:` and/or by
directory." `status:` frontmatter exists on **13 of 1,653** files under `cortex/lifecycle/` and
**0 of 129** under `cortex/research/` — it cannot reach the directories holding the citations.
That leaves directory scoping, and the directories it would have to exclude are the ones the
ticket names as scan targets.

**Two of five scan targets carry no corpus.** `cortex/requirements/` contains exactly one
`file:line` citation repo-wide (`resolve_item.py:137-141` — itself a partial path that would not
resolve without the policy above). `CLAUDE.md` contains zero. The title names "requirements".

**The #444 fold contradicts the Edges constraint.** It adds `discovery_source` research artifacts
as "free once the engine exists". Research artifacts are the canonical historical record, carry no
`status:` field, and are ~65% dangling at HEAD — the single largest false-positive generator in
the repo, added by the section meant to narrow scope.

**The anchor check's premise is false here.** "The dominant convention" — a backticked symbol near
the citation — holds for ~31% of citations even at a generous ±200-char window, and 35% are line
ranges, for which the ticket concedes a different rule is needed without saying what it is.

**Its own citations demonstrate the thesis and the blind spot.** Touch points cite
`bin/cortex-requirements-parity-audit`, deleted in `e3aef4e5` and listed in project.md under
"Retired without named evidence". Meanwhile the founding evidence is entirely wild-light paths
(`cortex/requirements/engineering.md:807`, `tests/unit/test_migration_cutover.gd:122-171`) cited
from a cortex-command ticket — correct-as-written and unresolvable here by construction. Cross-repo
citation is not an edge case; it is how this ticket's own evidence is recorded, and the ticket has
no answer for it.

**Precedent argues against the sizing.** #304 shipped `complexity: complex` for a strictly narrower
job: one citation form, one directory, 24 citations, a closed filename convention as its oracle —
and cost a 344-line module, a test file, a four-branch wrapper, a scripts entry, a justfile recipe,
and a plugin mirror.

**Disposition.** The measurement scripts were the deliverable. The rot is real — instances (1)–(4)
happened — but the mechanical oracle that would catch them does not exist at acceptable precision
over this corpus, and the shape that actually bit (a line-range acceptance anchor naming a member
that is absent from the cited file) was caught by a critical reviewer, which is already the
backstop. Anything filed later should target that narrow slice and start from the numbers above,
not from this ticket's premise.
