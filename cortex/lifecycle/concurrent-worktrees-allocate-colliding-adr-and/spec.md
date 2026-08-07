# Specification: concurrent-worktrees-allocate-colliding-adr-and

## Problem Statement

Two overnight features each authored an ADR numbered **0080** and `git merge` joined both
silently, because the filenames differed. Six in-tree references then cited an ambiguous bare
"ADR-0080". Research corrected the ticket's premise — the collision was decided at **plan time in
the home repo**, by concurrent plan-gen sub-agents globbing one shared directory
(`cortex_command/overnight/prompts/orchestrator-round.md:483`, `:474`), not across worktrees — and
then a critical review refuted every mechanism proposed to prevent it, including this spec's own
earlier design, by measurement.

What survived is a narrow, real defect. **Nothing in any codebase parses an ADR number** — verified,
`grep -rn "superseded_by" --include="*.py"` returns nothing, no module allocates a number, and
`cortex_command/adr_citation_audit.py` only *reports*. So a duplicate number is a **reading**
ambiguity everywhere except one place: `superseded_by: NNNN` is a bare number in machine-readable
frontmatter with no slug to disambiguate it. Under a duplicate, `superseded_by: 0080` is genuinely
unresolvable rather than merely ambiguous — a reader cannot tell which of two ADRs supersedes the
one in hand, and no tool can tell them either.

This spec fixes that one pointer and nothing else. It does **not** prevent duplicate numbers.
That is deliberate: the measured damage from the incident was nine lines in one commit (wild-light
`7ebc1ded`: 5 files, +9/-7), caught and repaired by a human in one morning with a tiebreak that
took no investigation, and every prevention mechanism explored was refuted — several by
live measurement against this repo. Under `cortex/requirements/project.md`'s front-door evidence
bar, adding harness machinery to prevent a nine-line, hand-repairable defect is not justified;
removing a genuine unresolvable-pointer ambiguity for ten frontmatter lines is.

**Live contention is real and is not addressed here.** Three artifacts in this repo currently
claim 0035, and `a-rework-re-review-re-reads/spec.md:290` proposes `0030-reviewer-brief-…` while
`cortex/adr/0030-mode-agnostic-interactive-dispatch.md` already exists. Duplicates and stale
proposals will keep happening. They stay cheap to repair by hand, and the existing report-only
auditor already detects both (`detect_duplicates`, `slug_mismatch`) for anyone who runs it.

## Phases

- **Phase 1: Disambiguate the pointer** — `superseded_by` carries the full `NNNN-slug` stem, and existing sites migrate.
- **Phase 2: Record the refutations** — the rejected mechanisms are written into the ticket so they are not re-derived.

## Requirements

1. **`superseded_by` carries the full stem**: `cortex/adr/README.md`'s frontmatter contract changes `superseded_by: NNNN` to the superseding ADR's full `NNNN-slug` filename stem, and the prose at `:42-43` is updated to match (it currently says "the zero-padded four-digit number" and "pointing at the replacement's four-digit number"). [Acceptance: `grep -c "superseded_by: NNNN" cortex/adr/README.md` returns 0 — on unmodified HEAD it returns 2, so this fails on HEAD; and `grep -c "four-digit number" cortex/adr/README.md` returns 0 — on HEAD it returns 2.] **Phase**: Disambiguate the pointer

2. **Existing sites migrate**: both live `superseded_by` values in this repo carry the full stem. [Acceptance: `grep -h "^superseded_by:" cortex/adr/*.md` emits `superseded_by: 0008-picker-selection-authorizes-enterworktree` and `superseded_by: 0032-cortex-selects-no-model`; `grep -cE "^superseded_by: [0-9]{4}$" cortex/adr/*.md` returns 0 across all files — on HEAD that pattern matches 2 files.] **Phase**: Disambiguate the pointer

3. **The migration is verifiably faithful**: each migrated pointer's slug matches an ADR file that actually exists, so the change cannot silently introduce a dangling pointer. [Acceptance: for every `superseded_by: <stem>` value, `test -f "cortex/adr/<stem>.md"` succeeds. Checked for all sites; a one-line shell loop is sufficient.] **Phase**: Disambiguate the pointer

4. **The auditor is not regressed**: the corpus scan reports no new findings after the migration. [Acceptance: capture `uv run python -m cortex_command.adr_citation_audit` finding counts by kind immediately before the first edit, then re-run after; each kind's count must be equal or lower. **Capture the baseline at implementation time — do not pin a literal**: it drifts as lifecycle artifacts add ADR citations (measured 41/25, then 41/33, then 41/34 across this refine session alone). **This is a regression guard — it passes on unmodified HEAD by design**; Requirements 1 and 2 are the detecting criteria.] **Phase**: Disambiguate the pointer

5. **The refuted mechanisms are recorded in the ticket**: `cortex/backlog/464-*.md` gains a section naming each rejected approach and the measurement that killed it, so a future session does not re-derive them. Must cover: spec-time claim-by-creating (inverts gate-then-emit; the untracked stub blocks the merge that lands the real ADR), post-merge allocation with citation rewrite (the rewriting scanner is `.md`/`.py`-only, so it half-applies), arming the existing detector (631 findings across two repos, 0 actioned), slug-primary or date/hash identity (permanently mixed corpus; the date variant does not prevent same-run collisions), and a blocking gate (contradicts #304's ratified report-only posture). [Acceptance: the ticket contains a section heading for the rejected approaches, and `grep -c "claim-by-creating\|post-merge allocation\|slug-primary" cortex/backlog/464-*.md` returns 3 or more — on HEAD it returns 0.] **Phase**: Record the refutations

6. **The ticket's corrected premise is recorded**: the ticket's Why currently asserts the race is across worktrees and that no detector exists; both are false. [Acceptance: the ticket states the race is decided at plan time in the home repo, and acknowledges `detect_duplicates` already exists. `grep -c "plan time" cortex/backlog/464-*.md` returns 1 or more — on HEAD it returns 0.] **Phase**: Record the refutations

## Non-Requirements

- **Preventing duplicate ADR numbers.** Explicitly out of scope, and this is the spec's central concession. Every mechanism explored was refuted: see Requirement 5's list. Duplicates remain possible and remain a hand-repair.
- **Resolving the live 0035 contention or the stale 0030 proposal.** Separate janitorial work; this spec's own `## Proposed ADR` is set to None, which releases 0035 and removes one of the three claimants.
- **Any allocator, reservation, lock, gate, hook, or CI check.** #304's report-only ruling is honored in full.
- **Arming the duplicate detector into any report.** Measured: 66 findings here, 565 in wild-light, 0 actioned, including 5 `gap` findings a corpus README explicitly sanctions.
- **Migrating wild-light's 8 `superseded_by` sites.** Cross-repo work; the contract change ships here and consumer repos adopt it when they next touch those files.
- **Requiring citations to carry the slug.** Measured at 28,439 bare-form citations against 3,746 slug-carrying in wild-light — an 88% bare rate *despite* wild-light's `CLAUDE.md:167` already saying "Cite ADRs by meaning, not bare number." The convention exists and did not survive contact; restating it is not a fix.
- **Changing `status:` semantics or adding a reaper.** Nothing parses `status:` either; it is decorative for tooling and read only by humans.

## Edge Cases

- **An ADR is superseded by one that is later renamed**: the pointer dangles. Expected — same exposure as today's bare number, no worse; Requirement 3's existence check catches it at change time, and the existing auditor's `slug_mismatch` arm catches it afterwards.
- **A consumer repo still writes `superseded_by: NNNN`**: expected. Nothing parses the field, so a bare number stays readable; the contract change is forward-looking guidance, not enforcement.
- **Two ADRs share a number *and* one is superseded**: this is the case the change exists for. Expected: the full-stem pointer resolves unambiguously to exactly one file.
- **The migrated stem contains a typo**: caught by Requirement 3's `test -f` check before the change lands.

## Changes to Existing Behavior

- **MODIFIED** — `cortex/adr/README.md`: the `superseded_by` frontmatter contract and its two prose descriptions.
- **MODIFIED** — `cortex/adr/0006-*.md` and `cortex/adr/0023-*.md`: the two live `superseded_by` values.
- **MODIFIED** — `cortex/backlog/464-*.md`: corrected premise plus the rejected-approaches record.
- **UNCHANGED** — `cortex_command/adr_citation_audit.py` (it never parses frontmatter), every ADR number, every citation, every skill, every gate, and `cortex_command/` in its entirety. No code changes ship in this spec.

## Technical Constraints

- **Nothing parses `superseded_by`** — verified: `grep -rn "superseded_by" --include="*.py"` returns nothing, and `load_corpus` (`adr_citation_audit.py:91-120`) indexes on the filename regex without opening the file. This change is therefore a human-legibility fix with zero runtime consumer, and the spec claims nothing more.
- No file under `skills/` or `plugins/` is touched, so neither the reference-size ratchet nor the dual-source mirror hook is engaged, and the CLAUDE.md lifecycle gate on `skills/` does not apply.
- `cortex/adr/README.md` carries no frontmatter of its own and is not an ADR (`README.md:49`); editing it does not alter the corpus index.
- The three-criteria ADR gate is not met by this change (it is reversible by editing one README and two lines in one PR), so no ADR is emitted — consistent with `README.md:19-27`.

## Open Decisions

None.

## Proposed ADR

None considered.
