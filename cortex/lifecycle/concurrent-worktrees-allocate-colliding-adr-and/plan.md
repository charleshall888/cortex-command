# Plan: concurrent-worktrees-allocate-colliding-adr-and

## Overview

Docs-only change in two independent halves: make `superseded_by` carry the superseding ADR's
full `NNNN-slug` stem (contract + the two live pointers), and rewrite ticket #464's false
premise while recording the five refuted prevention mechanisms. No `cortex_command/` code, no
skill or plugin file, no new ADR — so neither the reference-size ratchet nor the dual-source
mirror hook is engaged. A before/after auditor snapshot brackets every edit as the regression
guard.

## Outline

### Phase 1: Disambiguate the pointer (tasks: 1, 2, 3, 4)
**Goal**: `superseded_by` is a full filename stem in the contract and at both live sites, with
no dangling pointer and no new auditor findings.
**Checkpoint**: `grep -cE "^superseded_by: [0-9]{4}$" cortex/adr/*.md` is 0 everywhere, both
migrated stems resolve to real files, and the auditor's per-kind counts are equal or lower than
the captured baseline.

### Phase 2: Record the refutations (tasks: 5)
**Goal**: ticket #464 states the corrected premise and names each rejected mechanism with the
measurement that killed it.
**Checkpoint**: the ticket carries a rejected-approaches section and no longer asserts a
cross-worktree race or a missing detector.

## Tasks

### Task 1: Capture the auditor baseline before any edit
- **Files**: `/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/a7c28512-de61-41f8-8ce3-d8213e4e32b3/scratchpad/adr-audit-baseline.txt`
- **What**: Snapshot per-kind finding counts from the ADR citation auditor so Requirement 4's
  no-regression comparison has a real reference point. Must run before Tasks 2, 3, and 5 touch
  anything, because all three edit `.md` files the auditor scans.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `uv run python -m cortex_command.adr_citation_audit` prints a JSON report on
  stdout with a `findings` list whose entries each carry a `kind` key
  (`unresolved` / `slug_mismatch` / `duplicate_number` / `gap`). Do **not** pin a literal count
  anywhere — the spec measured it drifting 41/25 → 41/33 → 41/34 across the refine session
  alone. Run from the repo root so the auditor's default `--root` is correct.
- **Verification**: `uv run python -m cortex_command.adr_citation_audit | python3 -c "import json,sys,collections;print(sorted(collections.Counter(f['kind'] for f in json.load(sys.stdin)['findings']).items()))" | tee <baseline-path>` — passes when the file exists and holds a non-empty sorted list of `(kind, count)` pairs.
- **Status**: [ ] pending

### Task 2: Change the `superseded_by` contract in the ADR README
- **Files**: `cortex/adr/README.md`
- **What**: The frontmatter contract and both prose descriptions stop describing
  `superseded_by` as a bare four-digit number and describe the superseding ADR's full filename
  stem instead. This is Requirement 1.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Three sites, all inside `## Frontmatter convention`. `:36` is the YAML template
  line `superseded_by: NNNN  # optional; ...`. `:42` is the `status` bullet, ending "**must** be
  paired with `superseded_by: NNNN` pointing at the replacement's four-digit number". `:43` is
  the `superseded_by` bullet, "the zero-padded four-digit number of the superseding ADR".
  Two acceptance greps constrain the wording: the literal string `superseded_by: NNNN` must not
  survive on any line, and neither must `four-digit number`. The angle-bracket placeholder form
  `<NNNN-slug>` satisfies both (the `<` breaks the first grep) and matches the placeholder
  dialect already used at `:35` and in `skills/refine/references/specify.md`. Line `:13`'s
  passing mention of `superseded_by:` needs no change. This README carries no frontmatter of its
  own (`:49`) and is not part of the corpus index, so editing it cannot alter the auditor's ADR
  index — only its citations, of which this edit adds none.
- **Verification**: `grep -c "superseded_by: NNNN" cortex/adr/README.md` returns 0 (returns 2 on unmodified HEAD) **and** `grep -c "four-digit number" cortex/adr/README.md` returns 0 (returns 2 on HEAD). Both must be 0 to pass.
- **Status**: [ ] pending

### Task 3: Migrate the two live `superseded_by` pointers
- **Files**: `cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md`, `cortex/adr/0023-route-core-research-fanout-to-sonnet-searcher-tier.md`
- **What**: Rewrite each file's frontmatter `superseded_by` value from the bare number to the
  superseding ADR's full stem. This is Requirement 2.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: These are the only two live sites in this repo (`grep -rn "^superseded_by:"
  cortex/adr/*.md`, excluding the README's template line). `0006`'s value `0008` becomes
  `0008-picker-selection-authorizes-enterworktree`; `0023`'s value `0032` becomes
  `0032-cortex-selects-no-model`. Both target files exist. Edit only the value on line 3 of each
  file — no status change, no body change. The stem carries no `.md` suffix, matching the
  contract Task 2 writes.
- **Verification**: `grep -h "^superseded_by:" cortex/adr/*.md` emits exactly `superseded_by: 0008-picker-selection-authorizes-enterworktree` and `superseded_by: 0032-cortex-selects-no-model` (plus the README's template line), and `grep -cE "^superseded_by: [0-9]{4}$" cortex/adr/*.md` reports 0 for every file (reports 1 for two files on HEAD).
- **Status**: [ ] pending

### Task 4: Verify pointer resolution and auditor non-regression
- **Files**: `cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md`, `cortex/adr/0023-route-core-research-fanout-to-sonnet-searcher-tier.md`, `/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/a7c28512-de61-41f8-8ce3-d8213e4e32b3/scratchpad/adr-audit-baseline.txt`
- **What**: Prove Requirements 3 and 4 — every migrated stem names an ADR file that exists, and
  no finding kind grew. Read-only; if either check fails, the fix belongs in Task 3 or Task 5,
  not here.
- **Depends on**: [2, 3, 5]
- **Complexity**: trivial
- **Context**: Requirement 3 is a `test -f "cortex/adr/<stem>.md"` loop over the migrated values.
  Requirement 4 compares against Task 1's captured file, not a literal — it is a regression
  guard that passes on unmodified HEAD by design, so it detects nothing on its own; Tasks 2 and
  3 are the detecting criteria. Task 5 is a dependency because it edits a `.md` file inside the
  auditor's scan scope, so its citations must be inside the compared window.
- **Verification**: (a) `grep -h "^superseded_by:" cortex/adr/[0-9]*.md | awk '{print $2}' | while read s; do test -f "cortex/adr/$s.md" || echo "DANGLING: $s"; done` prints nothing; (b) re-running Task 1's kind-count one-liner yields, for every kind, a count equal to or lower than the same kind's baseline entry, with no kind present that was absent from the baseline.
- **Status**: [ ] pending

### Task 5: Correct ticket #464's premise and record the refuted mechanisms
- **Files**: `cortex/backlog/464-concurrent-worktrees-allocate-colliding-adr-and-backlog-numbers-with-no-detector.md`
- **What**: Rewrite the two false claims in the Why and add a section naming each rejected
  prevention mechanism with the measurement that refuted it, so a future session does not
  re-derive them. This is Requirements 5 and 6.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Two Why claims are false and must be replaced, not annotated: that the race is a
  cross-worktree one (it is decided at **plan time in the home repo** by concurrent plan-gen
  sub-agents globbing one shared `cortex/adr/` — `cortex_command/overnight/prompts/orchestrator-round.md:483`, `:474`), and that no detector exists
  (`detect_duplicates` in `cortex_command/adr_citation_audit.py:128-142` already emits a
  `duplicate_number` finding; it is report-only and manually invoked, which is the actual gap).
  The rejected-approaches section must cover all five, each with its killer: spec-time
  **claim-by-creating** (inverts gate-then-emit — the untracked stub blocks the merge that lands
  the real ADR); **post-merge allocation** with citation rewrite (the rewriting scanner is
  `.md`/`.py`-only, so it half-applies and leaves thousands of `.gd`/`.json` citations wrong);
  arming the existing detector (631 findings across two repos, 0 actioned, 5 of them sanctioned
  false positives); **slug-primary** or date/hash identity (permanently mixed corpus, and the
  date variant does not prevent same-run collisions); and a blocking gate (contradicts #304's
  ratified report-only posture). Three acceptance greps constrain the text: a section heading
  for the rejected approaches, `grep -c "claim-by-creating\|post-merge allocation\|slug-primary"`
  ≥ 3 — so those three terms must land on at least three distinct lines, one per bullet — and
  `grep -c "plan time"` ≥ 1. **Auditor hazard**: this file is scanned, and any new `ADR-NNNN` or
  `adr/NNNN-slug` token for a number absent from *this* repo's corpus (0080, 0081) becomes a new
  `unresolved` finding and fails Task 4. Refer to the incident numbers bare ("numbered 0080") as
  the existing text already does. Leave frontmatter untouched — status and `lifecycle_phase` are
  lifecycle-owned.
- **Verification**: `grep -c "claim-by-creating\|post-merge allocation\|slug-primary" cortex/backlog/464-*.md` returns 3 or more (returns 0 on HEAD); `grep -c "plan time" cortex/backlog/464-*.md` returns 1 or more (returns 0 on HEAD); and `grep -c "^## " cortex/backlog/464-*.md` grows by exactly 1 versus HEAD, with the new heading naming the rejected approaches.
- **Status**: [ ] pending

## Risks

- **Requirement 4 is a guard that passes on HEAD.** It cannot fail the way Requirements 1, 2, 5,
  and 6 can; its only job is to catch a citation the edits accidentally introduce. Task 5's
  auditor hazard note is where that risk actually lives.
- **The stem-carrying contract is guidance, not enforcement.** Nothing parses `superseded_by`
  (verified: `grep -rn "superseded_by" --include="*.py"` returns nothing), so a consumer repo
  writing a bare number stays readable and nothing turns red. The spec accepts this — it is a
  human-legibility fix.
- **Duplicate ADR numbers remain possible.** The spec deliberately ships no prevention. Three
  artifacts in this repo currently claim 0035 and a stale 0030 proposal is live; both stay
  hand-repairs. Task 5 exists so that concession is recorded rather than re-litigated.
- **Graph depth.** Three levels across five tasks, with single-task levels at both ends. That is
  inherent to a capture → edit → compare shape, not a merge candidate: Task 1 must precede every
  edit and Task 4 must follow every edit. The middle level is three-wide with disjoint files.
