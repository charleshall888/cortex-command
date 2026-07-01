# Plan: Fix morning-review pre-merge auto-close ordering bug (#342)

## Overview

Remove the stale pre-merge close from `skills/morning-review/SKILL.md` (collapse Step 4 to a
semantic post-merge breadcrumb, relocate the sole §6b reference into Step 6), migrate the
Step-4-unique handling (exit-2 disambiguation + no-confirmation guardrail) into `walkthrough.md`
§6b, add soft closure-state notes to the non-standard §6 PR exits, and add a spelling-agnostic
absence-based regression test with durable positive controls. Canonical edits only; the
`cortex-overnight` mirror regenerates via `just build-plugin` and is committed alongside each
canonical edit (pre-commit drift hook + `test_dual_source_reference_parity.py`).

**Dispatch note (load-bearing)**: the three skill-editing tasks (1→2→3) run **serially**, not in
parallel. `just build-plugin` does `rsync -a --delete` over the ENTIRE
`plugins/cortex-overnight/skills/morning-review/` mirror dir (both `SKILL.md` and
`walkthrough.md`) from current canonical, so two concurrently-dispatched skill edits collide on
the shared mirror even when their declared canonical Files are disjoint (Task 1's `build-plugin`
would pull Task 2's uncommitted `walkthrough.md` into the mirror → drift hook blocks the commit,
or a force-stage breaks parity). The dependency chain (Task 2 `[1]`, Task 3 `[2]`) enforces the
serialization under every dispatch mode.

## Outline

### Phase 1: Single-source closure post-merge (tasks: 1, 2, 3 — serial chain)
**Goal**: Closure is referenced in exactly one place (post-merge, in Step 6 / §6b), no pre-merge close or routing prose remains in Step 4, every Step-4-unique behavior survives in §6b, and §6's non-standard exits surface closure state.
**Checkpoint**: over the Step-4 stub span `grep -icE "update[-_]item|cortex-read-backlog-backend"` = 0; SKILL.md has exactly one `Section 6b` reference, after the `### Step 6` heading; §6b's report list has a third `ambiguous slug` entry with the candidate-list action; the 3 unmerged §6 exits each carry a "ticket remains open" clause and the already-merged exit carries a verify-closure advisory; mirror matches canonical.

### Phase 2: Regression guard (task: 4)
**Goal**: A durable, CI-proven-discriminating structural guard prevents the pre-merge close (in either spelling) and a mis-placed/duplicate §6b reference from returning to SKILL.md.
**Checkpoint**: `just test` exits 0 with the new SKILL.md guard green, its embedded positive-control assertions passing (close-pattern matches both spellings; ordering check flags a synthetic pre-merge §6b), and existing walkthrough ordering + mirror-parity tests green.

## Tasks

### Task 1: Collapse SKILL.md Step 4 to a semantic breadcrumb and place the sole §6b reference in Step 6
- **Files**: `skills/morning-review/SKILL.md`, `plugins/cortex-overnight/skills/morning-review/SKILL.md` (regenerated, do not hand-edit)
- **What**: Replace SKILL.md Step 4's pre-merge auto-close body (lines ~95-120) with a short soft stub that (a) carries NO close-command name in ANY form (`cortex-update-item` / `cortex_command.backlog.update_item`) and NO backend-routing prose, and (b) forward-points to post-merge closure with a SEMANTIC phrase (e.g., "Backlog ticket closure now happens after the PR is merged — not here."). The stub must NOT contain the literal token "Section 6b" and must NOT use a step number, so the SOLE "Section 6b" reference lands in Step 6. Add that reference: a companion sentence in Step 6 after the §6a mention (line ~141) stating §6b closes each completed feature's ticket once merge and sync are confirmed. (Reqs 1, 2.)
- **Depends on**: none
- **Complexity**: simple
- **Context**: Step 4 heading at line 95, body ends 120; Step 5 (Commit) at 122; Step 6 (PR Merge) at 137-141 references §6/§6a but not §6b; the only current §6b mention is line 99 inside Step 4. Collapse-to-pointer (not delete+renumber). **Do NOT copy walkthrough §5's stub literally** — §5's stub NAMES "Section 6b" (walkthrough.md:435 "closure has moved to **Section 6b**"); reproducing that creates a second reference and fails the exactly-one count. Step 4's body also currently holds six bare `cortex-update-item`/`update_item` mentions (lines ~101,103,111,113,117,118: slug-resolution, exit-2 prose, report-state list) and the line-99 backend-routing prose (`cortex-read-backlog-backend`, the three arms) — the collapse removes ALL of them (the routing/slug prose already lives in §6b; exit-2 is migrated by Task 2). After editing, run `just build-plugin`, stage canonical + regenerated mirror in the same commit, `/cortex-core:commit`.
- **Verification**: (b) over the Step-4 stub span (from the `### Step 4` heading to the `### Step 5` heading — extract with awk/sed): `grep -icE "update[-_]item|cortex-read-backlog-backend"` = `0` (stub cleared of every close-command name + routing prose, not merely the `--status complete` line); AND `grep -crEi "update[-_]item.*--status complete" skills/morning-review/SKILL.md` = `0`; AND `grep -c "Section 6b" skills/morning-review/SKILL.md` = `1` with that single match after the `### Step 6` heading (confirm line numbers via `grep -n`). Plus (a) `just test` — mirror parity passes.
- **Status**: [x] complete

### Task 2: Migrate exit-2 disambiguation and the no-confirmation guardrail into §6b
- **Files**: `skills/morning-review/references/walkthrough.md`, `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` (regenerated)
- **What**: In §6b (lines ~535-591): (i) amend the exit-code enumeration line (~568, "exits 0 on success … and exits 1 silently if no item is found") so it no longer denies exit-2 exists; (ii) add a THIRD `ambiguous slug` entry to the per-feature reporting list (~574-577, currently `closed #ID` / `no ticket found`); (iii) preserve the exit-2 ACTION — surface the stderr candidate list and ask the operator to re-invoke with a disambiguated slug (was SKILL.md Step 4 lines 113/118); (iv) carry a soft "no per-feature confirmation is needed" equivalent into §6b (was SKILL.md line 97). (Req 3 + the two removed-behavior gaps.)
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: §6b's close call is ~562; report list ~574-577. `update_item.py` exit 2 = ambiguous, candidate list to stderr. Soft declarative phrasing; no `MUST`/`CRITICAL`/`REQUIRED` tokens. Serialized after Task 1 (shared build-plugin mirror dir — see Dispatch note). Run `just build-plugin`, stage canonical + mirror together, `/cortex-core:commit`.
- **Verification**: **Extract the §6b span first** (e.g. `awk '/^## Section 6b/{f=1;next} /^## /{f=0} f' walkthrough.md`), then over THAT span only (span-scoping excludes the pre-existing "candidate" at L142 / other-section text): (ii) `grep -ic "ambiguous slug"` ≥ 1 — the report-state ENTRY, distinct from the (i) enumeration prose which the bare word "ambiguous" would also match; (iii) `grep -ic "candidate"` ≥ 1 — the disambiguation action; (iv) `grep -icE "no per-feature confirmation|without.*confirmation|no confirmation"` ≥ 1; (i) the enumeration line no longer reads as a closed `exits 0 … exits 1` pair (manually confirm it admits exit-2). The greps are proxies — manually confirm the candidate-list-surfacing + re-invoke ACTION actually migrated (not just the tokens). Plus (a) `just test` mirror parity passes.
- **Status**: [x] complete

### Task 3: Add closure-state notes to the non-standard §6 PR exits
- **Files**: `skills/morning-review/references/walkthrough.md`, `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` (regenerated)
- **What**: Add a soft "the feature's backlog ticket remains open (work is on the integration branch, not main)" note to the three genuinely-unmerged §6 exits — no-PR-found (§6 step 2 stop, ~456-458), declined-merge (§6 step 7, ~505), merge-failed (§6 step 6 failure, ~503) — NOT the draft-PR exits (zero completed features to strand). And add a soft verify-closure advisory to the "PR already merged — main is up to date" exit (§6 step 2, ~459) prompting the operator to verify this session's completed-feature tickets are `complete` (a rare mid-session write failure could leave one open). (Reqs 6, 7.)
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: §6 spans ~443-509. Anchors: no-PR-found near "No PR found for"; declined near "PR left open at {url} — merge manually"; merge-failed near "leave the PR open for manual resolution"; already-merged at "PR already merged — main is up to date"; draft sub-branch ~472-485 (skip). Soft declarative phrasing; no MUST tokens; prose only (no copy-pinning test). The novel datum on the unmerged exits is the ticket-open clause. Serialized after Task 2 (same file). Run `just build-plugin`, stage canonical + mirror together, `/cortex-core:commit`.
- **Verification**: (b) **per-exit** (confirm the clause lands in EACH of the three distinct exit spans, not a single ≥1 over all §6): at each unmerged exit's anchor lines, `grep -iE "ticket.*remain|remain[s]? open|not closed|stays? open"` is present. For the already-merged exit (~459): the advisory uses `verify` (NOT `check` — "check" pre-exists at L481 in the skipped draft exit, so a `verify|check` pattern would false-green) plus a `ticket|complete` reference — confirm `grep -iE "verify.*(ticket|complete)|(ticket|complete).*verify"` matches at that exit. Plus (a) `just test` mirror parity passes; the existing `test_morning_review_status_close_ordering.py` stays green.
- **Status**: [x] complete

### Task 4: Add the spelling-agnostic absence-based SKILL.md ordering guard with durable positive controls
- **Files**: `tests/test_morning_review_status_close_ordering.py`
- **What**: Extend the existing test (or add a sibling in the same file) inspecting `skills/morning-review/SKILL.md` that asserts (a) no close literal in EITHER spelling appears anywhere in SKILL.md — the close pattern matches both `update-item` (console) and `update_item` (module) + `--status complete`, not the existing console-only `CLOSE_LITERAL = "cortex-update-item"`; and (b) exactly one `Section 6b` reference in SKILL.md, after the "PR Merge" step (semantic-heading anchor, never a step number; SKILL.md has no `gh pr merge` literal). **Prove discrimination DURABLY, not via an ephemeral revert-demo**: embed positive-control assertions in the test — assert the close-detection pattern MATCHES synthetic close samples in both spellings (`"cortex-update-item 078 --status complete"` and `"python3 -m cortex_command.backlog.update_item 078 --status complete"`), and assert the single-source/ordering check FLAGS a synthetic SKILL.md-shaped string carrying a pre-merge §6b reference. These positive controls live permanently in the test file and run in CI every time, so a mis-written (never-matching) guard fails rather than passing green. (Req 5 + the module-spelling and single-source hardening from critical-review.)
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: The existing test defines `WALKTHROUGH` (walkthrough.md only), `MERGE_LITERAL = "gh pr merge"`, `CLOSE_LITERAL = "cortex-update-item"`, `CLOSE_ARG = "--status complete"`, and `_first_occurrence` / section-finder helpers. Add a `SKILL` path constant. Spelling-agnostic close pattern: `update[-_]item` + `--status complete`. Anchor SKILL.md ordering on the "PR Merge" heading text (not `gh pr merge`, which SKILL.md lacks). Depends on Tasks 1-3 so the full suite is green when this runs.
- **Verification**: (a) `just test` exits 0 — the new SKILL.md assertions pass on the fixed SKILL.md; the embedded positive-control assertions pass (close-pattern matches both spellings; ordering check flags a synthetic pre-merge §6b), proving the guard is discriminating in CI (not by an out-of-band claim); existing walkthrough ordering + `test_dual_source_reference_parity.py` stay green.
- **Status**: [x] complete

## Risks

- **Verification proof-strength** was the dominant through-line across both the spec and plan critical-reviews. The acceptances above extract spans mechanically (not whole-file greps), require the novel entry/clause (not pre-existing text), and prove the Task-4 guard via CI-resident positive controls rather than an honor-system demo. The remaining honor-system residue is the manual confirmation that Task 2's candidate-list ACTION (not just its tokens) migrated — unavoidable for prose-in-a-skill; the implementer must actually confirm it.
- **Module-spelling grep evasion**: Task 4's close pattern must be spelling-agnostic (`update[-_]item`) with a positive control asserting it matches both forms, or a future module-form pre-merge close passes green — the whole point of the hardened guard.
- **Mirror-dir coupling**: `just build-plugin` regenerates the whole morning-review mirror; the 1→2→3 serial chain is required (not optional) to avoid a drift-hook commit collision / parity break under concurrent dispatch.
- **Follow-up ticket**: the observed-merge auto-close (for the `BACKLOG_WRITE_FAILED` × out-of-band exit), stranded-merged-work reconciliation, and the cross-repo bare-numeric-close hazard are deliberately deferred — file the follow-up backlog ticket at Complete so they are not lost.
- **Scope**: Approach B (auto-close unmerged paths) is refuted; do not satisfy the ticket Role's literal "close somewhere" by re-adding any close on an unmerged exit.

## Acceptance

`just test` exits 0 with: the new SKILL.md guard green and its positive controls passing (close-pattern matches both console and module spellings; the ordering check flags a synthetic pre-merge §6b), the existing walkthrough ordering test green, and `test_dual_source_reference_parity.py` green (cortex-overnight mirror matches canonical). Over the Step-4 stub span `grep -icE "update[-_]item|cortex-read-backlog-backend"` = 0 and `grep -crEi "update[-_]item.*--status complete" skills/morning-review/SKILL.md` = 0; SKILL.md carries exactly one `Section 6b` reference, after the PR-Merge step; §6b's report list has the third `ambiguous slug` entry with the candidate-list surfacing action; the three unmerged §6 exits carry a "ticket remains open" clause and the already-merged exit carries a `verify`-worded verify-closure advisory.
