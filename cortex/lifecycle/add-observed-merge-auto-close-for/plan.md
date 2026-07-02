# Plan: add-observed-merge-auto-close-for

## Overview
Ship the proportionate fix the spec landed on: rewrite morning-review's §6 step-2 "PR already merged" advisory to be fetch-first, ticket-specific, and actionable — no auto-close, no new mechanism — regenerating the cortex-overnight mirror in the same commit, then verify the ordering-guard and parity suites plus the full test suite stay green.

## Outline

### Phase 1: Advisory correctness tweak (tasks: 1, 2)
**Goal**: Replace the misleading MERGED-exit advisory with a fetch-first, ticket-specific manual procedure and land it with mirror parity in a single commit.
**Checkpoint**: Revised advisory committed on main (canonical + mirror byte-identical, same commit); `tests/test_morning_review_status_close_ordering.py` (all 7 tests) and `tests/test_dual_source_reference_parity.py` green; `just test` exits 0.

## Tasks

### Task 1: Rewrite the §6 step-2 MERGED-exit advisory, regenerate the mirror, commit together
- **Files**: `skills/morning-review/references/walkthrough.md` (canonical edit), `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` (regenerated via `just build-plugin`, no hand edits)
- **What**: Replace the three-line advisory at the `state == "MERGED"` early-exit (walkthrough.md ~L461–463, inside §6 step 2) with fetch-first, ticket-specific, actionable prose per spec Req 1, keeping the span free of close literals per Req 2; regenerate the mirror and commit canonical + mirror in one commit per Req 3.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The span to rewrite is the bullet beginning `- If the PR's \`state\` is \`"MERGED"\`:` and ending before the `"CLOSED"` bullet (currently L461–464 boundary). The revised advisory keeps the "Then stop." terminal semantics for §6 and covers three elements: (a) local `main` may be behind after this out-of-band merge because §6a's post-merge sync is skipped on this path — fetch or pull `origin main` first, before checking any ticket; (b) the set to check is this session's completed-feature backlog tickets (the completed-features list already surfaced in Section 2 from `overnight-state.json`, zero-padded `backlog_id`s); (c) any such ticket still open after the fetch is closed via Section 6b's documented backlog closer, then pushed. Phrase conditionally so a session with zero completed features adds no noise (Section 2's list is empty → nothing to check). Constraints that shape the wording: the ordering guard `tests/test_morning_review_status_close_ordering.py::test_status_complete_appears_after_merge_in_source_order` anchors on the first `cortex-update-item` occurrence appearing after the first `gh pr merge` literal (currently L481), so the span must not contain `cortex-update-item`, `update_item`, or `--status complete` — reference Section 6b by name instead (this also sidesteps the contract checker's E101/E103 on inline-code `cortex-*` tokens lacking required flags); soft declarative phrasing only, no `MUST`/`CRITICAL`/`REQUIRED` tokens (MUST-escalation policy). Mirror coupling: the drift pre-commit hook rejects a canonical-only commit, so run `just build-plugin` before committing and commit both files together via `/cortex-core:commit` with an explicit pathspec (`git commit -- <both walkthrough.md paths>`) so this checkout's unrelated files (untracked `cortex/backlog/346-*.md`, stray `${CLAUDE_SKILL_DIR}/` dir, lifecycle artifacts) stay out.
- **Verification**: (b) Span checks: `sed -n '/\`state\` is \`"MERGED"\`/,/\`state\` is \`"CLOSED"\`/p' skills/morning-review/references/walkthrough.md` piped to `grep -icE "git fetch|git pull"` ≥ 1 (fetch-first present — pass if ≥1); same span piped to `grep -icE "update[-_]item|--status complete"` = 0 (no close literal — pass if 0); same span piped to `grep -c "Section 6b"` ≥ 1 (closer referenced by section — pass if ≥1). Parity + same-commit: `cmp skills/morning-review/references/walkthrough.md plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` exits 0, and `git log -1 --name-only` lists both paths — pass if both hold.
- **Status**: [ ] pending

### Task 2: Verify guard, parity, and full suites
- **Files**: none (read-only verification)
- **What**: Run the two named suites the spec's acceptance cites, then the full suite, and confirm the Task 1 commit introduced no regression.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Targeted suites first for a sharp signal: `uv run pytest tests/test_morning_review_status_close_ordering.py tests/test_dual_source_reference_parity.py` (the ordering suite is 7 tests including positive controls). Then `just test` per spec acceptance. Prior sessions have seen environment-dependent `just test` failures unrelated to the diff (sandbox network/DNS, concurrent-session fixtures) — if a failure appears, triage relatedness: a failure in either named suite or any failure attributable to the walkthrough.md diff blocks and routes back to Task 1's edit; a reproducible-on-baseline external failure is reported, not fixed here.
- **Verification**: (a) `uv run pytest tests/test_morning_review_status_close_ordering.py tests/test_dual_source_reference_parity.py` — pass if exit 0; then `just test` — pass if exit 0 (or every failure is demonstrated pre-existing on the pre-Task-1 baseline commit and unrelated to this diff, reported explicitly).
- **Status**: [ ] pending

## Risks
- **Wording threads three constraints at once** — no close literal in the span (ordering guard), soft phrasing (MUST-escalation policy), and no flagless inline-code `cortex-*` tokens (contract checker E101/E103). Referencing Section 6b by name rather than by command satisfies all three; the residual risk is a drafting slip, which Task 1's span greps catch mechanically.
- **`just test` environmental flakes** — prior sessions recorded external failures (sandbox network, concurrent fixtures). Task 2's triage rule keeps these from blocking a correct change while still failing loud on anything attributable to this diff.
- **Concurrent-session checkout hygiene** — the working tree carries another session's untracked files; explicit-pathspec commit in Task 1 prevents leakage. Accepted as procedure, not a design choice to revisit.
- **Scope**: this deliberately ships an advisory, not a closer — the durable observed-merge close, reconciliation, and §6b bare-ID hardening live in follow-up #346 (already filed). If you want the auto-close after all, that reverses the research-backed spec decision and should reopen Specify, not widen this plan.
