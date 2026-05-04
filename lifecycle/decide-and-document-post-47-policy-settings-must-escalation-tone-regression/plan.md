# Plan: decide-and-document-post-47-policy-settings-must-escalation-tone-regression

## Overview

Append two policy sections (OQ3 MUST-escalation, OQ6 tone) plus an embedded 100-line bloat-threshold rule to repo `CLAUDE.md`, pre-file the R12 follow-up backlog ticket via the canonical `cortex-create-backlog-item` CLI, and author the `## Resolution` closing note in #91's body. Plan ends with the closing note authored but uncommitted; the lifecycle's Complete phase canonically handles the third commit (closing-note + `status: complete` write-back + canonical `feature_complete` event + index regeneration + git workflow), preserving the spec's three-commit atomicity while routing close-out through `references/complete.md` instead of an inline mid-session write-back.

## Tasks

### Task 1: Draft and append OQ3, OQ6, and bloat-rule additions to repo CLAUDE.md

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md`
- **What**: Append two new level-2 sections after the existing `## Conventions` section: `## MUST-escalation policy (post-Opus 4.7)` (R1, embedding the verbatim imperative clauses from R2, R3, R4, R8, plus inline cross-references for R11) and `## Tone and voice policy (Opus 4.7)` (R5, embedding the verbatim imperative clauses from R6, R7, R9, plus inline cross-references for R11). The bloat-threshold rule (R9) lands at the end of the OQ6 section.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Source for verbatim strings: `lifecycle/decide-and-document-post-47-policy-settings-must-escalation-tone-regression/spec.md` requirements R1–R11. Quote the spec's verbatim clauses unmodified — the substring grep checks (Task 2) require exact matches.
  - **Hygiene-rule precedence note**: The spec preamble forbids "negation-only constructions, hedge softeners, examples-as-exhaustive enumerations." This targets *descriptive* negation/hedging (e.g., "X does NOT satisfy Y", "consider whether to add Y"), not *imperative* commands like `do not escalate to MUST as a workaround` — imperative "do not X" is positive-routing in prescriptive form (commanding the inverse action). The verbatim strings R3 and R8 are imperative-positive and satisfy the hygiene rule. R6's `inconsistent leverage` is a noun phrase describing an empirical claim, not a hedge softener of an imperative. When in doubt, the verbatim spec phrasing wins — the spec authored these clauses with the hygiene rule in scope and accepted them.
  - Required substring matches (each must appear exactly the indicated number of times — Task 2 has the full grep list):
    - `## MUST-escalation policy (post-Opus 4.7)` (header, exactly 1)
    - `include in the commit body` (R2, exactly 1)
    - `is rejected at review` (R2, exactly 1)
    - `` run a dispatch with `effort=high` `` (R3, exactly 1; backticks around `effort=high` are part of the verbatim string)
    - `do not escalate to MUST as a workaround` (R3, exactly 1)
    - `tone perception` (R4, ≥1)
    - `all other failure types are OQ3-eligible` (R4, exactly 1)
    - `## Tone and voice policy (Opus 4.7)` (header, exactly 1)
    - `Use a warm, collaborative tone` (R6, exactly 1)
    - `inconsistent leverage` (R6, exactly 1)
    - `(d) an empirical test of rules-file tone leverage` (R7, exactly 1)
    - `2+ separate` (R7, ≥1)
    - `(a) Anthropic publishes guidance reversing` (R8, exactly 1)
    - `including this current edit` (R9, exactly 1)
    - `fires on the entry that crosses 100` (R9, exactly 1)
  - Cross-references (R11): inline mentions of `#91`, `#85`, `#82`, `support.tools`, and `Anthropic` so the combined regex `#0?91|#0?85|#0?82|support\.tools|anthropic|Anthropic` matches ≥4 times across the new sections.
  - **Line-budget formatting choice**: prefer **long-line paragraph form** (no internal line wraps within the verbatim blocks) so each multi-sentence verbatim block lands on 1–3 physical lines rather than 4–6. With long-line formatting, the new content fits in ~22–30 lines (existing 50 + new 22–30 = 72–80 lines, comfortably under 100). If the implementer prefers wrapped formatting, the budget tightens to ~37–45 new lines (87–95 total) — still under 100, but closer.
  - Itemized line cost (long-line form): OQ3 header (1) + intro (1) + R2 verbatim (1) + R3 verbatim (1) + R4 verbatim (1) + R8 verbatim (1) + cross-refs (1–2) + blank lines (3–4) ≈ 10–12 lines. OQ6 header (1) + intro (1) + R6 verbatim (1) + R7 verbatim (1) + R9 bloat rule (1–2) + cross-refs (1) + blank lines (3–4) ≈ 9–11 lines. Total: ~19–23 new lines, well under 50-line headroom.
  - Section ordering (Technical Constraints): both new sections land at the END of CLAUDE.md, after `## Conventions`. No interleaving with existing sections; no reflow of existing content.
  - Section style: title-case, level-2 (`## `), prose paragraphs and short bullet lists; no emojis. Match existing CLAUDE.md style (lines 38–50 of the existing file are reference shape).
  - Writing the OQ3 section: codify Alternative A (default soft, escalate on observed failure). R2 covers the artifact-bound evidence requirement; R3 the effort-first clause; R4 the tone-perception carve-out; R8 the re-evaluation triggers. Pre-existing MUSTs are grandfathered (R2's grandfathering clause).
  - Writing the OQ6 section: codify Alternative I (no shipped tone directive). R6 covers user-self-action guidance with explicit epistemic-honest caveat about rules-file leverage uncertainty; R7 covers re-evaluation triggers including the empirical-leverage signal (d); R9 ends the section with the bloat-threshold rule.
- **Verification**: `wc -l < /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` ≤ 100 — pass if line count is 100 or fewer; otherwise re-format any wrapped verbatim blocks into long-line paragraph form (which is permitted because markdown rendering ignores internal wrap), then re-check. The compression failover never edits verbatim substrings.
- **Status**: [x] complete

### Task 2: Verify all R1–R11 acceptance criteria pass

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` (read-only verification; edits only if a check fails)
- **What**: Run the 11 acceptance commands from the spec verbatim and confirm each returns the required count. If any check fails, return to Task 1's prose and adjust until every check passes; do not proceed to Task 3 with any failing check.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Acceptance commands (run each and confirm the indicated result):
    - R1: `grep -c '^## MUST-escalation policy (post-Opus 4\.7)$' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`
    - R2: `grep -Fc 'include in the commit body' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1` AND `grep -Fc 'is rejected at review' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`
    - R3: run `grep -Fc` against `/Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` with the literal pattern `run a dispatch with ` followed by a backtick then `effort=high` then a backtick (i.e. the spec's verbatim phrasing including the surrounding backticks around `effort=high`); require count = `1` AND `grep -Fc 'do not escalate to MUST as a workaround' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`. The exact pattern source: spec.md R3 acceptance line.
    - R4: `grep -Fc 'tone perception' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` ≥ `1` AND `grep -Fc 'all other failure types are OQ3-eligible' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`
    - R5: `grep -c '^## Tone and voice policy (Opus 4\.7)$' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`
    - R6: `grep -Fc 'Use a warm, collaborative tone' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1` AND `grep -Fc 'inconsistent leverage' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`
    - R7: `grep -Fc '(d) an empirical test of rules-file tone leverage' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1` AND `grep -Fc '2+ separate' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` ≥ `1`
    - R8: `grep -Fc '(a) Anthropic publishes guidance reversing' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`
    - R9: `grep -Fc 'including this current edit' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1` AND `grep -Fc 'fires on the entry that crosses 100' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` = `1`
    - R10: `wc -l < /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` ≤ `100`
    - R11: `grep -cE '#0?91|#0?85|#0?82|support\.tools|anthropic|Anthropic' /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` ≥ `4`
- **Verification**: A consolidated check runs all 11 commands above and reports pass/fail per requirement — pass if every requirement reports pass. The substrings checked are dictated by the spec, not chosen by Task 1, so this verification is not self-sealing.
- **Status**: [x] complete

### Task 3: Commit CLAUDE.md edits via /cortex-interactive:commit (Commit #1)

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` (staged)
- **What**: Stage the modified CLAUDE.md and create the first of three commits using `/cortex-interactive:commit`. Subject example: `Document MUST-escalation and tone policy in CLAUDE.md` (imperative mood, capitalized, no trailing period, ≤72 chars). Body: brief mention of OQ3 (Alternative A) and OQ6 (Alternative I) decisions, link to ticket #91 and epic #82.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Use the `/cortex-interactive:commit` skill (per the project's "Always commit using the /cortex-interactive:commit skill" convention). Do not run `git commit` manually.
  - The commit hook will validate subject format automatically; let it run.
  - This commit must NOT include the R12 backlog file (Task 4) or the #91 closing note (Task 5).
- **Verification**: `git log -1 --pretty=%H -- /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` returns a non-empty SHA AND `git diff HEAD~1 HEAD -- /Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md | grep -c '^+## MUST-escalation policy'` = `1` — pass if both checks pass.
- **Status**: [x] complete

### Task 4: Create R12 follow-up backlog ticket via cortex-create-backlog-item, post-edit frontmatter and body, and commit (Commit #2)

- **Files**:
  - new file at `/Users/charlie.hall/Workspaces/cortex-command/backlog/<NNN>-empirically-test-rules-file-tone-leverage-under-opus-4-7.md` (NNN assigned by canonical CLI, currently expected to be `157`)
  - new sidecar at `/Users/charlie.hall/Workspaces/cortex-command/backlog/<NNN>-empirically-test-rules-file-tone-leverage-under-opus-4-7.events.jsonl` (auto-emitted by canonical CLI)
  - `/Users/charlie.hall/Workspaces/cortex-command/backlog/index.md` and `index.json` (auto-regenerated by canonical CLI)
- **What**: Use the canonical `cortex-create-backlog-item` CLI to atomically assign the next ID, write the YAML frontmatter stub, append the `status_changed` event to the `.events.jsonl` sidecar, and regenerate the index. Then post-edit the new file to add `blocked-by: [91]`, `tags: [opus-4-7-harness-adaptation, policy]`, and the body content (Motivation, Test design, Out-of-scope per R12). Finally, run the R12 acceptance grep checks, regenerate the index once more if `cortex-create-backlog-item`'s auto-regen ran before the post-edit, and create Commit #2 via `/cortex-interactive:commit`.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - **Canonical creator**: `cortex-create-backlog-item` is the project's source-of-truth tool for new backlog tickets (`pyproject.toml` line 23 wires it; `cortex_command/backlog/create_item.py` implements ID assignment, UUID generation, frontmatter stub, sidecar event, and index regeneration). Run with `--title 'Empirically test rules-file tone leverage under Opus 4.7+' --parent 82 --type chore --priority low` (verify exact flag names by running `cortex-create-backlog-item --help` first).
  - **Post-edit needed for fields the CLI does not handle**: `blocked-by` and `tags` fields and the body. The CLI emits `parent: "82"` (string-quoted) and assigns ID/UUID/created/updated/title — the implementer adds `blocked-by: [91]` (inline integer array), `tags: [opus-4-7-harness-adaptation, policy]` (inline string array, matching #91 line 11), and `status: backlog` (verify the CLI's default — if it ships `status: backlog` already, no post-edit needed for status).
  - **Body content per R12** (paragraph or short sections):
    - `## Motivation`: gives R7 trigger (d) a concrete re-litigation path; converts the deferred empirical question from passive note to actionable backlog gate. References ticket #91 (parent #82).
    - `## Test design`: write a tone directive in `~/.claude/rules/cortex-tone-test.md`; run paired dispatches (with and without the directive) on a fixed user-facing-summary prompt under Opus 4.7+; compare outputs for warmth shift; document.
    - `## Out-of-scope`: one-shot test, not ongoing rules-file deployment (per spec Non-Requirements).
  - **Index re-regeneration after post-edit**: `cortex-update-item` (used implicitly when post-editing via the CLI's frontmatter setter) auto-regenerates the index. If the implementer post-edits via direct file write (e.g., `Edit` tool), explicitly run `just backlog-index` after the post-edit to ensure the index reflects the final frontmatter.
  - **R12 acceptance commands** (run before Commit #2):
    - `ls /Users/charlie.hall/Workspaces/cortex-command/backlog/*-empirically-test-rules-file-tone-leverage-under-opus-4-7.md` exits `0`
    - `grep -E '^parent: "?82"?$'` against the matched file returns `1` line
    - `grep -E '^status: backlog$'` against the matched file returns `1` line
  - **Commit**: stage the new backlog file, the new `.events.jsonl` sidecar, and the regenerated `backlog/index.md` and `backlog/index.json`. Subject example: `Pre-file empirical rules-file tone leverage test ticket`. Body: brief mention this gives R7 trigger (d) a concrete re-litigation path; link to #91. Use `/cortex-interactive:commit`, not manual `git commit`.
- **Verification**: All three R12 acceptance grep checks above pass AND `git log -1 --pretty=%H` returns a non-empty SHA AND `git diff HEAD~1 HEAD --name-only` includes `backlog/<NNN>-empirically-test-rules-file-tone-leverage-under-opus-4-7.md`, `backlog/<NNN>-empirically-test-rules-file-tone-leverage-under-opus-4-7.events.jsonl`, `backlog/index.md`, AND `backlog/index.json` — pass if all conditions hold.
- **Status**: [x] complete (note: CLI normalized slug to `opus-47` not `opus-4-7`; `.events.jsonl` is gitignored per `.gitignore:42` so not in commit. Substantive R12 frontmatter checks all pass: parent="82", status=backlog, blocked-by=[91], tags=[opus-4-7-harness-adaptation, policy]. Commit SHA 9d2db38.)

### Task 5: Author `## Resolution` closing note in #91 body (uncommitted; Complete phase commits)

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/backlog/091-decide-and-document-post-47-policy-settings-must-escalation-tone-regression.md`
- **What**: Append a `## Resolution (2026-05-04)` section to the #91 ticket body (after the existing `## Scope` section), summarizing the two decisions taken: Alternative A for OQ3 with FM-1/FM-2/FM-5 mitigations; Alternative I for OQ6 with epistemic-honest user-self-action note and empirical-test follow-up filed at the new ticket #<NNN>. Keep it ≤10 lines. Do NOT call `cortex-update-item` here — the `status: complete` flip and the canonical `feature_complete` event are Complete-phase responsibilities. Leave the closing note as an uncommitted working-tree change so Complete phase's git workflow stages and commits it together with the status update + events.log + index changes (this becomes Commit #3).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - **Why this task does not flip status or commit**: per critical-review finding 1, doing so mid-session inverts SKILL.md Step 2 Backlog Status Check on subsequent invocations and forecloses canonical Complete-phase entry. Letting Complete phase run `cortex-update-item ... status=complete session_id=null` (per `references/complete.md` Step 2) keeps the lifecycle protocol intact, produces the canonical `feature_complete` event with `tasks_total` and `rework_cycles` fields, and runs `just test` per `lifecycle.config.md`'s `test-command`.
  - **Where the closing note lands**: append after the existing `## Scope` section (currently the last body section in #91, ending around line 51 of the existing file — verify by reading the file first). The note's `## Resolution (YYYY-MM-DD)` header pattern matches existing project ticket-closure conventions.
  - **Closing-note structure** (≤10 lines): one paragraph per decision. Paragraph 1: OQ3 → Alternative A; FM-1 mitigated by R2 artifact requirement; FM-2 mitigated by R4 tone-perception carve-out; FM-5 mitigated by R3 effort-first clause; cross-reference the new R12 ticket ID. Paragraph 2: OQ6 → Alternative I; user-self-action recommendation in R6 with explicit epistemic-honest leverage caveat; R7 re-evaluation triggers including (d) empirical-test signal pre-filed at #<NNN>.
  - **Working-tree state at end of Task 5**: `backlog/091-...md` shows the new `## Resolution` section but `status: refined` (or whatever it was — `in_progress` per the SessionStart write-back). The Complete phase will flip status and stage everything together.
- **Verification**: `grep -c '^## Resolution' /Users/charlie.hall/Workspaces/cortex-command/backlog/091-decide-and-document-post-47-policy-settings-must-escalation-tone-regression.md` = `1` AND `git status --porcelain backlog/091-decide-and-document-post-47-policy-settings-must-escalation-tone-regression.md` shows the file as modified (`^.M `) — pass if both checks pass. The first grep verifies the closing note was authored; the second verifies it was NOT committed (left for Complete phase).
- **Status**: [x] complete

## Verification Strategy

End-to-end verification confirms (1) the policy lands in CLAUDE.md and is grep-verifiable per R1–R11, (2) the follow-up R12 ticket exists at the right path with the right frontmatter and the canonical `.events.jsonl` sidecar, (3) the `## Resolution` closing note is authored in #91's body, and (4) the work is split across the two Plan-phase commits while the Complete phase produces the third commit canonically. The Complete phase will then run `just test`, log the canonical `feature_complete` event with `tasks_total=5` and `rework_cycles=N`, run `cortex-update-item ... status=complete session_id=null`, regenerate the index, stage the closing note + lifecycle artifacts + #91 status update + index files, and commit (Commit #3) via `/cortex-interactive:commit`. After Complete phase, the spec's R13 acceptance check `grep -E '^status: complete$' backlog/091-...md` returns `1` line, and the spec's three-commit atomicity (R1–R11 first, R12 second, R13 third) is satisfied.

## Veto Surface

The critical-review surfaced these load-bearing tensions; the user should explicitly accept or override these choices before implementation begins:

- **Defer close-out (status flip + canonical feature_complete event + git workflow) to the Complete phase rather than executing inline as Task 7/8** (Reviewer 4 keystone finding): Selected. Alternative was to keep an inline three-commit Plan structure, but that mid-session `status=complete` write-back forecloses canonical Complete-phase entry — `references/complete.md` Steps 1 (run `just test`), 2 (canonical event with `tasks_total`/`rework_cycles`), 4 (git), 5 (Summary) become unreachable. The selected approach lets Complete phase run normally and still produces the spec-mandated three commits.
- **Use `cortex-create-backlog-item` for Task 4 instead of manual file creation** (Reviewer 3 finding): Selected. The canonical CLI atomically assigns ID, generates UUID, writes the `.events.jsonl` sidecar with the `status_changed` event the corpus convention requires, and regenerates the index. The previously-considered manual `ls | sed | sort` derivation produces a structurally non-equivalent artifact (no sidecar event) and a confabulated padding rule that diverges from `create_item.py:44`'s `f"{next_id:03d}" if next_id < 1000 else str(next_id)` fence.
- **Long-line paragraph form for verbatim blocks in CLAUDE.md** (Reviewer 1 budget concern): Recommended. With long-line formatting, new content fits in ~22 lines (total 72), comfortable headroom under R10's 100-line ceiling. Wrapped formatting tightens to ~40–45 new lines (90–95 total) — still under, but with less slack. Implementer may choose either form per aesthetic preference; verification via `wc -l ≤ 100` is the binding gate.
- **Hygiene-rule precedence: imperative "do not X" satisfies the spec preamble** (Reviewer 1 contradiction concern): Selected. The spec's "no negation-only" rule targets *descriptive* negation ("X does NOT satisfy Y") with no positive routing — not *imperative* commands like `do not escalate to MUST as a workaround` which are positive-routing in prescriptive form (commanding inverse action). R6's `inconsistent leverage` is a noun phrase describing an empirical claim, not a hedge softener. The spec authored these clauses with the hygiene rule in scope and accepted them; the verbatim phrasing wins. If user disagrees with this interpretation, `/cortex-interactive:refine` to reopen the spec is the right escalation, not in-plan re-litigation.
- **Three-commit atomicity preserved across Plan + Complete phases** (Spec Technical Constraints): Selected. Spec mandates exactly 3 commits. This plan produces commits #1 and #2 directly (Tasks 3 and 4); Complete phase produces commit #3 from Task 5's authored closing note plus its own canonical close-out (events.log, status flip, index). Alternative was 4 commits (Plan-phase commits closing note, Complete commits separately) — rejected because it violates spec.

## Scope Boundaries

- No edits to any `skills/`, `hooks/`, `bin/`, `claude/`, or `plugins/` files (Non-Requirements: "No code changes").
- No third policy decision in CLAUDE.md (Non-Requirements: "No third policy decision").
- No re-creation of `~/.claude/rules/cortex-*.md` infrastructure (Non-Requirements: "No re-establishment of rules infrastructure").
- No edits to any skill SKILL.md or reference file (Non-Requirements: "No edits to any skill SKILL.md or reference file").
- No write to `~/.claude/CLAUDE.md` (Non-Requirements: "No update to ~/.claude/CLAUDE.md").
- No effort-parameter SDK wiring in `claude/pipeline/dispatch.py` or elsewhere (Non-Requirements: "No effort-parameter SDK wiring").
- No P-pattern audit of skills outside the #85 dispatch-skill scope (Non-Requirements: "No P-pattern audit broadening").
- No automated MUST-addition linter / pre-commit hook (Non-Requirements: "No automated MUST-addition linter").
- No `docs/policies.md` pre-creation (R9 specifies the receiver edit creates it on first crossing; this ticket does not pre-create it).
- No mid-session `status=complete` write-back on #91 (per the keystone critical-review finding; Complete phase handles it canonically).
