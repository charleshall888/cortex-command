# Plan: Agent-driven demoability assessment and validation setup at morning review

## Overview

Implements the morning-review demo-setup feature defined in `spec.md` by extending two skill files (`skills/lifecycle/assets/lifecycle.config.md` for the `demo-command` schema field, and `skills/morning-review/SKILL.md` + `skills/morning-review/references/walkthrough.md` for the new Section 2a, Step 0 garbage sweep, Section 6 cleanup reminder, and Edge Cases table rows). All edits are additive except for two single-line transition-clause updates in `walkthrough.md` (current lines 76 and 84) that the new Section 2a requires. A separate small fix corrects the wrong Godot CLI example (`--play` flag) at its three propagation sites.

The Section 2a content is split across three tasks (skeleton → guards → active flow) to keep each task within the 5–15 minute envelope and to avoid intra-file edit conflicts in `walkthrough.md`. Task dependencies serialize edits to the same file. A sentinel HTML comment is used to bridge the skeleton-to-content handoff between Tasks 3, 4, and 5 — the implementer of each later task can grep the file for the sentinel to find the exact insertion point with no inference.

## Skill-text vs runtime-substitution convention

This plan distinguishes two layers:

1. **Skill instruction text** (the static content of `walkthrough.md` / `SKILL.md`): contains literal placeholders like `{integration_branch}`, `{session_id}`, `{timestamp}`, `{target-path}`, `{demo-command}`, `{resolved-target-path}`. These braces are LITERAL characters in the skill text — the agent's runtime behavior is what substitutes them when the skill is executed against a real session.
2. **The implementer's edit operation**: when the plan says to insert a command template into `walkthrough.md`, the implementer must keep the `{...}` placeholders as literal characters, NOT substitute them at edit time.

When a task says "the literal text X must appear in walkthrough.md", X is the skill instruction text — placeholders are part of X.

## Tasks

### Task 1: Add `demo-command` schema field and correct Godot example at source
- **Files**: `skills/lifecycle/assets/lifecycle.config.md`, `research/morning-review-demo-setup/research.md`, `backlog/071-auto-launch-demo-at-morning-review.md`
- **What**: Add an optional, commented-by-default `demo-command` field to the lifecycle.config.md template alongside `test-command`. Correct the wrong Godot example (`godot --play res://main.tscn`) in the discovery research and the originating backlog item per spec TC12. The field add and the three example fixes are bundled because they all relate to the same `demo-command` example string and the implementer satisfies all four ACs as a single coherent edit pass.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `lifecycle.config.md` template currently has fields commented-by-default in YAML frontmatter (lines 1–9). The new field follows the same `# field:           # comment` form. Insertion point: directly after `# test-command:` (line 3). Exact line to add: `# demo-command:           # e.g., godot res://main.tscn, uv run fastapi run src/main.py`. The example must use `godot res://main.tscn` (positional scene argument), NOT `godot --play res://main.tscn`.
  - `research/morning-review-demo-setup/research.md` line 19 contains the wrong example. Replace `godot --play res://main.tscn` with `godot res://main.tscn`.
  - `backlog/071-auto-launch-demo-at-morning-review.md` line 43 contains the wrong example inside a fenced code block. Replace `godot --play res://main.tscn` with `godot res://main.tscn`.
  - Spec reference: R1, TC12.
- **Verification**:
  - `grep -c '^# demo-command:' skills/lifecycle/assets/lifecycle.config.md` — pass if = 1
  - `grep -c -- '--play' skills/lifecycle/assets/lifecycle.config.md` — pass if = 0
  - `grep -c -- '--play' research/morning-review-demo-setup/research.md` — pass if = 0
  - `grep -c -- '--play' backlog/071-auto-launch-demo-at-morning-review.md` — pass if = 0
- **Status**: [x] complete

### Task 2: Add Demo Setup bullet to morning-review SKILL.md Step 3 outline
- **Files**: `skills/morning-review/SKILL.md`
- **What**: Insert a new "Demo Setup" item into the Step 3 numbered list, between item 1 (Completed Features) and item 2 (Lifecycle Advancement), and renumber subsequent items.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - SKILL.md Step 3 (lines 70–79) currently has 4 numbered bullets. The new bullet 2 reads: `2. **Demo Setup** — if \`demo-command\` is configured and the session is local, offer to spin up a demo worktree from the overnight branch.` Subsequent items become 3, 4, 5.
  - Spec reference: R13.
- **Verification**:
  - `grep -c 'Demo Setup' skills/morning-review/SKILL.md` — pass if ≥ 1
  - `awk '/Completed Features/ {a=NR} /Demo Setup/ {b=NR} /Lifecycle Advancement/ {c=NR} END {exit !(a<b && b<c)}' skills/morning-review/SKILL.md` — pass if exit 0 (Demo Setup line falls between Completed Features and Lifecycle Advancement)
- **Status**: [x] complete

### Task 3: Add Section 2a skeleton (heading + sentinel + transition line edits)
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Insert the `## Section 2a — Demo Setup` heading between Section 2 and Section 2b, write a one-line "Skip this section entirely if any of the following hold:" leader matching the established Sections 2b/2c/6a convention, place a sentinel HTML comment as the placeholder for Tasks 4 and 5 to find, and update walkthrough.md current-lines 76 and 84 to reference Section 2a as the new intermediate section. **Edit ordering matters** — see Context below.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Edit ordering**: line numbers in this Context block reference walkthrough.md's CURRENT state (before any edits). Inserting the new Section 2a heading shifts line numbers below it. To avoid stale-line-number errors, the implementer should perform edits in this order: (1) update the line currently at 76, (2) update the line currently at 84, (3) insert the new section. OR use Edit's content-based matching (search for the literal old text and replace) which is line-number-agnostic. The Edit tool's content-based matching is preferred — it eliminates the ordering concern entirely.
  - **Section 2 ends at line 79** with `Verified/skipped statuses are for reporting context only — they do not gate lifecycle advancement.` followed by a `---` divider on line 80 and `## Section 2b — Lifecycle Advancement` on line 82.
  - **New section content** (insert between line 80's `---` divider and line 82's Section 2b heading; the insertion creates a new `---` divider, the new heading, the skip-clause leader, the sentinel, and another `---` divider before Section 2b):
    ```
    ## Section 2a — Demo Setup

    Skip this section entirely if any of the following hold:

    <!-- SECTION-2A-PLACEHOLDER: Task 4 replaces this comment with the guard sub-blocks (R3, R4, R5). Task 5 appends the active-flow content (R6-R10) after Task 4's guards. -->

    ---
    ```
    The sentinel HTML comment is the canonical anchor that Tasks 4 and 5 will grep for. Its exact text is `<!-- SECTION-2A-PLACEHOLDER:` (the rest of the comment is human-readable but only the prefix is grep-anchored).
  - **Line 76 update**: change the literal text `Record verified/skipped status per feature, then proceed immediately to Section 2b. Verified/skipped statuses are for reporting context only — they do not gate lifecycle advancement.` to `Record verified/skipped status per feature, then proceed immediately to Section 2a (which may be skipped — see its guard clauses; if skipped, advance directly to Section 2b). Verified/skipped statuses are for reporting context only — they do not gate lifecycle advancement.`
  - **Line 84 update**: change the literal text `Run immediately after the batch verification response. No additional user input is needed.` to `Run immediately after Section 2a (or after the batch verification response if Section 2a was skipped). No additional user input is needed.`
  - Spec reference: R2.
- **Verification**:
  - `grep -c '^## Section 2a — Demo Setup$' skills/morning-review/references/walkthrough.md` — pass if = 1
  - `grep -c 'proceed immediately to Section 2a' skills/morning-review/references/walkthrough.md` — pass if ≥ 1
  - `grep -c 'Run immediately after Section 2a' skills/morning-review/references/walkthrough.md` — pass if ≥ 1
  - `grep -c 'SECTION-2A-PLACEHOLDER' skills/morning-review/references/walkthrough.md` — pass if = 1 (sentinel exists for Task 4)
  - `awk '/^## Section 2 / {a=NR} /^## Section 2a / {b=NR} /^## Section 2b / {c=NR} END {exit !(a<b && b<c)}' skills/morning-review/references/walkthrough.md` — pass if exit 0 (Section 2a heading falls between Section 2 and Section 2b)
- **Status**: [x] complete

### Task 4: Add Section 2a guards and parsing rules (R3, R4, R5)
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Replace the `<!-- SECTION-2A-PLACEHOLDER: ... -->` sentinel comment in Section 2a (placed by Task 3) with the four guard sub-blocks: (a) `lifecycle.config.md` configured + parsing rules, (b) `$SSH_CONNECTION` not set, (c) `git rev-parse --verify {integration_branch}` succeeds. Include the six pinned parsing rules from spec R3 (read line, ignore comments, extract after first `:`, reject control characters, treat empty as unset, do not strip inline `#`). After replacing the sentinel, append a new sentinel `<!-- SECTION-2A-CONTENT-INSERT: Task 5 appends the active-flow content here. -->` so Task 5 has an anchor.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - **Find the placeholder**: grep for `SECTION-2A-PLACEHOLDER` in walkthrough.md and replace the entire HTML comment line with the new content.
  - **Guard 1 (R3 — config not set)**: text describing the four skip conditions (file missing, field absent or commented, value empty, control characters in value). Followed by the six numbered parsing rules. The parsing rules must use the exact phrases pinned by spec R3 ACs: "comment line", "after the first", "leading and trailing whitespace", "control character", "treat the field as unset", "inline ... comments". The skip conditions must use the exact phrases: "lifecycle.config.md ... missing", "demo-command ... absent", "value ... empty", "control character".
  - **Parser implementation note** (non-user-facing — include as a skill-internal aside or leave to the implementer's judgment, but do not omit): the implementer should use a sed-based extraction like `sed -n 's/^[[:space:]]*demo-command:[[:space:]]*//p'` and NOT a naive `awk -F:` (which breaks on `godot res://main.tscn` because of the `:` in the value). Spec R3 has the explicit warning.
  - **Reading state**: the integration_branch must be read from `lifecycle/sessions/latest-overnight/overnight-state.json` via jq. The exact pattern (already used by walkthrough.md Section 6 step 1 at line 348): `jq -r '.integration_branch' lifecycle/sessions/latest-overnight/overnight-state.json`. Section 2a's guard text must reference both the literal phrase `integration_branch` and the literal phrase `git rev-parse --verify` so both spec R5 ACs pass.
  - **Guard 2 (R4 — remote session)**: one sentence saying "Skip Section 2a if `$SSH_CONNECTION` is set and non-empty." This catches both SSH and mosh sessions (mosh inherits `$SSH_CONNECTION` from the underlying SSH handshake).
  - **Guard 3 (R5 — branch missing)**: one sentence saying "Skip Section 2a if `git rev-parse --verify {integration_branch}` exits non-zero, where `{integration_branch}` is read from `lifecycle/sessions/latest-overnight/overnight-state.json` (same jq pattern as Section 6 step 1)."
  - **Place the next sentinel**: after the last guard sub-block but before the `---` divider that begins Section 2b, insert `<!-- SECTION-2A-CONTENT-INSERT: Task 5 appends the active-flow content here. -->` as a new line. This is the anchor Task 5 will find.
  - Spec references: R3, R4, R5.
- **Verification** (each grep run against `skills/morning-review/references/walkthrough.md`):
  - `grep -c 'SECTION-2A-PLACEHOLDER'` — pass if = 0 (placeholder removed)
  - `grep -c 'SECTION-2A-CONTENT-INSERT'` — pass if = 1 (new sentinel for Task 5 in place)
  - `grep -c 'comment line'` — pass if ≥ 1 (R3 rule 2)
  - `grep -c 'after the first'` — pass if ≥ 1 (R3 rule 3)
  - `grep -c 'leading and trailing whitespace'` — pass if ≥ 1 (R3 rule 3)
  - `grep -c 'control character'` — pass if ≥ 1 (R3 rule 4)
  - `grep -c 'treat the field as unset'` — pass if ≥ 1 (R3 rule 5)
  - `grep -c 'inline.*comments'` — pass if ≥ 1 (R3 rule 6)
  - `grep -c 'lifecycle.config.md.*missing'` — pass if ≥ 1 (R3 guard 1)
  - `grep -c 'demo-command.*absent'` — pass if ≥ 1 (R3 guard 2)
  - `grep -c 'value.*empty'` — pass if ≥ 1 (R3 guard 3)
  - `grep -c 'SSH_CONNECTION'` — pass if ≥ 1 (R4 guard)
  - `grep -c 'rev-parse --verify'` — pass if ≥ 1 (R5 guard — command name)
  - `grep -c 'integration_branch'` — pass if ≥ 1 (R5 guard — variable name from spec AC)
- **Status**: [x] complete

### Task 5: Add Section 2a active flow (offer, worktree command, print, auto-advance, security)
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Replace the `<!-- SECTION-2A-CONTENT-INSERT: ... -->` sentinel comment (placed by Task 4) with the active-flow content: the single yes/no offer (R6), the worktree-creation command with `git -c core.hooksPath=/dev/null worktree add` and `realpath`-resolved path (R7), the print template for the worktree path + verbatim demo-command + cleanup hint (R8), the immediate auto-advance language (R9), and the explicit "MUST NOT execute the demo-command" security boundary statement (R10).
- **Depends on**: [4]
- **Complexity**: complex
- **Context**:
  - **Find the sentinel**: grep for `SECTION-2A-CONTENT-INSERT` in walkthrough.md and replace the entire HTML comment line with the new content.
  - **Yes/no offer (R6)**: one sentence introducing the prompt and the prompt itself: "Spin up a demo worktree of `{integration_branch}` at `$TMPDIR/demo-{session_id}-{timestamp}` and print the launch command? [y / n]". On `n` or any unparseable input, advance to Section 2b. On `y`, proceed to the worktree creation step. Section 2a must not ask follow-up questions. The placeholders `{integration_branch}`, `{session_id}`, `{timestamp}` are LITERAL characters in the skill text per the "Skill-text vs runtime-substitution convention" at the top of this plan.
  - **Worktree command (R7)**: exactly one git invocation. Steps:
    1. Resolve `$TMPDIR` via `realpath "$TMPDIR"`.
    2. Build target path `{resolved-tmpdir}/demo-{session_id}-{timestamp}` where `{timestamp}` is `$(date -u +%Y%m%dT%H%M%SZ)`.
    3. Run the literal command (the double-quotes around the placeholders are ALSO literal in the skill text — they protect paths with spaces at runtime): `git -c core.hooksPath=/dev/null worktree add "{target-path}" "{integration_branch}"`. The `git -c core.hooksPath=/dev/null` prefix is mandatory — it neutralizes any tracked `post-checkout` hook on the overnight branch (e.g., husky / lefthook). Do NOT use `--force`. Do NOT use `git -C` (per `claude/rules/sandbox-behaviors.md`); note that `git -c` (lowercase) is distinct from `git -C` (uppercase) and is allowed.
    4. On non-zero exit: print the captured stderr and advance to Section 2b. Do not retry. Do not invoke any cleanup.
  - **Print template (R8)**: after a successful worktree-add, print exactly the following block (the implementer should put this inside a fenced code block in the skill text, not as a literal output instruction — the agent at runtime is told to print this block with placeholders substituted):
    ```
    Demo worktree created at: {resolved-target-path}

    To start the demo, run this in a separate terminal or shell:
        {demo-command}

    When you're done, close the demo and remove the worktree:
        git worktree remove {resolved-target-path}
    ```
    The `{resolved-target-path}` placeholder is the agent's runtime substitution of the absolute path. The `{demo-command}` placeholder is the agent's runtime substitution of the verbatim value extracted from `lifecycle.config.md` (already validated by R3 step 4 to contain no control characters).
  - **Auto-advance language (R9)**: one literal sentence: "After this section completes (skipped, declined, or accepted), proceed immediately to Section 2b. Do not wait for the user to report demo completion."
  - **Security boundary (R10)**: one literal sentence: "The agent MUST NOT execute the demo-command itself; it is printed for the user to run manually in a separate terminal session."
  - Spec references: R6, R7, R8, R9, R10.
- **Verification** (each grep run against `skills/morning-review/references/walkthrough.md`):
  - `grep -c 'SECTION-2A-CONTENT-INSERT'` — pass if = 0 (sentinel removed)
  - `awk '/^## Section 2a — Demo Setup$/,/^## Section 2b/' skills/morning-review/references/walkthrough.md | grep -c '?'` — pass if ≤ 2 (R6 single-prompt smoke test)
  - `grep -c 'realpath' skills/morning-review/references/walkthrough.md` — pass if ≥ 1 (R7 step 1)
  - `grep -c 'core.hooksPath=/dev/null' skills/morning-review/references/walkthrough.md` — pass if ≥ 1 (R7 step 3 hook neutralization)
  - `grep -c 'git worktree add' skills/morning-review/references/walkthrough.md` — pass if ≥ 1 (R7 step 3 worktree command)
  - `grep -c 'NOT use --force' skills/morning-review/references/walkthrough.md` — pass if ≥ 1 (R7 step 3 prohibition)
  - `grep -c 'Demo worktree created at:' skills/morning-review/references/walkthrough.md` — pass if = 1 (R8 print template)
  - `grep -c 'git worktree remove' skills/morning-review/references/walkthrough.md` — pass if ≥ 2 (R8 — once in Section 2a print template, once in existing Section 6 worktree-removal logic)
  - `grep -c 'Do not wait' skills/morning-review/references/walkthrough.md` — pass if ≥ 1 (R9 auto-advance language)
  - `grep -c 'MUST NOT execute the demo-command' skills/morning-review/references/walkthrough.md` — pass if ≥ 1 (R10 security boundary)
- **Status**: [x] complete

### Task 6: Add Section 6 step 5 cleanup reminder line
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Insert a one-line unconditional reminder into Section 6 step 5 success path (after the existing integration-worktree removal report at line 385) telling the user to close any demo and clean up its worktree manually.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - walkthrough.md Section 6 step 5 (lines 378–386) handles PR-merge success. The existing flow runs `git worktree remove --force {worktree_path}` and reports success/failure. The new reminder is appended after that report, still inside the "If yes" success path.
  - **Use content-based matching** for the insertion to avoid line-number drift after Tasks 3, 4, 5 inserted Section 2a content above. Search for the literal text `On failure: report the error but do not fail the review.` (which is the last sub-bullet of step 5 success path) and append the reminder line below it.
  - Reminder text (literal): `If you spun up a demo earlier in this review, close the demo and remove its worktree using the \`git worktree remove\` command printed at the time.`
  - The reminder is unconditional — it does NOT check whether Section 2a was actually accepted. The cost of an unnecessary reminder is one extra line of output; the cost of forgetting is a stale worktree.
  - Spec reference: R11.
- **Verification**:
  - `grep -c 'If you spun up a demo earlier' skills/morning-review/references/walkthrough.md` — pass if = 1
- **Status**: [x] complete

### Task 7: Add Step 0 garbage sweep sub-step to morning-review SKILL.md
- **Files**: `skills/morning-review/SKILL.md`
- **What**: Extend SKILL.md Step 0 (Mark Overnight Session Complete, lines 23–50) with a new sub-step that sweeps stale demo worktrees from prior sessions: enumerate via `git worktree list --porcelain`, filter to paths matching the canonical `{resolved-tmpdir}/demo-overnight-{date}-{time}-{ts}` regex, and remove those that don't belong to the current session via `git worktree remove` (no `--force`). Run `git worktree prune` AFTER all per-worktree removals (the ordering is mandatory — see Context).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - The sweep sub-step is added after the existing "mark phase complete" logic at line 49 (after the pointer-file update), but before "Skip Step 0 entirely if no session is found".
  - Sub-step heading must literally include the phrase "Garbage sweep" per spec R12 AC.
  - Logic in 5 numbered steps per spec R12, with the ordering between steps 4 and 5 being load-bearing:
    1. Read the current session ID (already resolved by Step 0 from `overnight-state.json`).
    2. Resolve `$TMPDIR` via `realpath "$TMPDIR"`.
    3. Run `git worktree list --porcelain`. For each line beginning with `worktree `, extract the path.
    4. For each path matching the regex `^{resolved-tmpdir}/demo-overnight-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}-[0-9]{8}T[0-9]{6}Z$`: if the path does NOT begin with `{resolved-tmpdir}/demo-{current_session_id}-`, run `git worktree remove "{path}"` (no `--force`). On failure (dirty worktree etc.), print stderr and continue.
    5. **AFTER all per-worktree removals complete in step 4** (not before, not interleaved): run `git worktree prune` to clean orphaned admin metadata. Errors non-fatal.
  - **Regex syntax**: the regex above uses ERE (POSIX Extended Regular Expressions). The implementer should match it via `grep -E`, `awk` (which uses ERE by default), or a Bash `[[ "$path" =~ ... ]]` test (which also uses ERE). Do NOT use `grep` without `-E` (POSIX BRE — `{n}` quantifiers behave differently). Do NOT use a `case` glob (no character classes).
  - **Curly-brace ambiguity**: the regex contains both `{n}` quantifiers (e.g., `[0-9]{4}`) and one `{resolved-tmpdir}` placeholder. The placeholder is a SHELL VARIABLE substitution at sweep-script construction time (not a regex group), and the `{n}` quantifiers are ERE syntax. To avoid confusion, the implementer should write the sweep as a small shell snippet that constructs the regex by string concatenation: e.g., `prefix="$(realpath "$TMPDIR")/demo-overnight-"` and then match with `[[ "$path" =~ ^${prefix}[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}-[0-9]{8}T[0-9]{6}Z$ ]]`.
  - The path-filter regex is intentionally narrow — `$TMPDIR/demo-*` would collide with unrelated user worktrees on Linux. The strict pattern matches only the canonical Section-2a-created form.
  - Sub-step text must explicitly mention "no `--force`" per spec R12 AC.
  - Spec reference: R12.
- **Verification** (each grep run against `skills/morning-review/SKILL.md`):
  - `grep -c 'Garbage sweep'` — pass if ≥ 1
  - `grep -c 'git worktree list --porcelain'` — pass if ≥ 1
  - `grep -c 'demo-overnight-'` — pass if ≥ 1
  - `grep -c 'git worktree remove'` — pass if ≥ 1
  - `grep -c 'no .--force'` — pass if ≥ 1
  - `grep -c 'git worktree prune'` — pass if ≥ 1
  - `awk '/git worktree remove/ {a=NR} /git worktree prune/ {b=NR} END {exit !(a<b)}' skills/morning-review/SKILL.md` — pass if exit 0 (prune appears AFTER remove in file order)
- **Status**: [x] complete

### Task 8: Add Section 2a edge case rows to walkthrough.md Edge Cases table
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Add 14 new rows to the existing Edge Cases table (currently lines 418–457) covering all Section 2a guards, failure paths, and follow-up scenarios per spec R14.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - The Edge Cases table is a markdown table with `| Situation | Action |` columns. Append new rows at the end of the existing table.
  - **Use content-based matching** for the insertion: search for the last existing row (`All conflicts auto-resolved via allowlist`) and append new rows after it. Line 457 is approximate after the prior tasks have inserted content above.
  - Rows to add (each row's "Situation" must contain the unique substring listed in spec R14's AC list):
    1. `lifecycle.config.md missing at project root` → Skip Section 2a entirely
    2. `lifecycle.config.md present but demo-command absent or commented out` → Skip Section 2a entirely
    3. `lifecycle.config.md present but demo-command value is empty` → Skip Section 2a entirely
    4. `demo-command value contains control characters / ANSI escapes` → Skip Section 2a entirely; treat as malformed
    5. `$SSH_CONNECTION set (running over SSH or mosh)` → Skip Section 2a entirely
    6. `git rev-parse --verify {integration_branch} exits non-zero` → Skip Section 2a entirely
    7. `Overnight branch already checked out by another worktree` → `git worktree add` fails with "already checked out"; print stderr; advance
    8. `User declines the demo offer` → Print no further output; advance
    9. `git worktree add fails on accept (any other reason)` → Print git's stderr; advance without retry
    10. `Agent crashes between worktree creation and command print` → Worktree exists with no record for user; next sweep retries
    11. `Stale demo worktree from prior session in $TMPDIR` → Removed by Step 0 garbage sweep on next morning-review (if clean)
    12. `Stale demo worktree from prior session contains user edits` → Sweep's `git worktree remove` (no --force) fails; stderr printed; user can rescue manually
    13. `Demo worktree created but user closes session before Section 6 reminder` → No cleanup until next morning-review's Step 0 sweep
    14. `User abandons the repo entirely (no future morning-review for it)` → Stale worktrees and admin entries persist until manual cleanup or OS reboot
  - Spec reference: R14.
- **Verification** (each grep run against `skills/morning-review/references/walkthrough.md`):
  - `grep -c 'lifecycle.config.md missing at project root'` — pass if ≥ 1
  - `grep -c 'demo-command.* absent or commented'` — pass if ≥ 1
  - `grep -c 'demo-command.* value is empty'` — pass if ≥ 1
  - `grep -c 'control characters'` — pass if ≥ 1
  - `grep -c 'SSH_CONNECTION.* set'` — pass if ≥ 1
  - `grep -c 'already checked out'` — pass if ≥ 1
  - `grep -c 'declines the demo offer'` — pass if ≥ 1
  - `grep -c 'git worktree add.* fails'` — pass if ≥ 1
  - `grep -c 'crashes between worktree creation'` — pass if ≥ 1
  - `grep -c 'Stale demo worktree from prior session'` — pass if ≥ 2
  - `grep -c 'closes session before'` — pass if ≥ 1
  - `grep -c 'abandons the repo'` — pass if ≥ 1
- **Status**: [x] complete

### Task 9: End-to-end spec acceptance verification
- **Files**: (none — verification only; reads `skills/lifecycle/assets/lifecycle.config.md`, `skills/morning-review/SKILL.md`, `skills/morning-review/references/walkthrough.md`, `research/morning-review-demo-setup/research.md`, `backlog/071-auto-launch-demo-at-morning-review.md`, `claude/settings.json`, and `lifecycle/archive/agent-driven-demoability-assessment-and-validation-setup-at-morning-review/spec.md` for the AC reference)
- **What**: Run every acceptance criterion from spec R1–R14 against the modified files and confirm each check returns its expected value. Also verify TC6 (sandbox `$TMPDIR` allowlist) and TC7 (`Bash(git worktree *)` permission allow rule) are still in place. This is the integration verification step that catches any drift between individual task verification and the spec's authoritative ACs.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8]
- **Complexity**: simple
- **Context**:
  - The spec at `lifecycle/archive/agent-driven-demoability-assessment-and-validation-setup-at-morning-review/spec.md` contains a list of acceptance criteria for each requirement R1–R14, expressed mostly as `grep -c "<phrase>" <file>` checks against `skills/lifecycle/assets/lifecycle.config.md`, `skills/morning-review/SKILL.md`, `skills/morning-review/references/walkthrough.md`, `research/morning-review-demo-setup/research.md`, and `backlog/071-auto-launch-demo-at-morning-review.md`.
  - Walk through R1–R14 in spec.md, run each AC, and confirm pass.
  - Additional integration checks (not covered by per-task ACs):
    - **TC6 sanity**: `grep -c '"\$TMPDIR"' claude/settings.json` ≥ 1 OR `grep -c 'TMPDIR' claude/settings.json` ≥ 1 — confirm `$TMPDIR` is still in the sandbox `allowWrite` list.
    - **TC7 sanity**: `grep -c 'Bash(git worktree \*)' claude/settings.json` ≥ 1 — confirm the permission allow rule for git worktree commands is still in place.
    - **TC12 sanity** (already verified by Task 1's per-file `--play` greps, but the integration check repeats them to confirm no drift): `grep -c -- '--play' research/morning-review-demo-setup/research.md` = 0 AND `grep -c -- '--play' backlog/071-auto-launch-demo-at-morning-review.md` = 0 AND `grep -c -- '--play' skills/lifecycle/assets/lifecycle.config.md` = 0.
  - **R6 mechanical check**: extract Section 2a's body via `awk '/^## Section 2a — Demo Setup$/,/^## Section 2b/' skills/morning-review/references/walkthrough.md` and run `| grep -c '?'` — pass if ≤ 2. The "exactly one user prompt" semantics is best-effort verified by the cap; the AC is mechanical, not human-judgment.
  - On any AC failure, Task 9's report must name the failing AC by spec line and the actual vs expected value, so the orchestrator can attribute the failure to the right upstream task.
  - This task does not modify any files. P6 (Files/Verification consistency) is satisfied because reading files for verification does not require listing them in Files (the constraint is about modification, not reading).
- **Verification**:
  - All `grep -c` ACs from R1–R14 in spec.md return their expected values.
  - The R2 ordering check (`awk` exit 0) passes.
  - The R6 awk-extracted body has `grep -c '?'` ≤ 2.
  - The TC6, TC7, TC12 sanity greps above pass.
- **Status**: [x] complete

## Verification Strategy

After all tasks complete:

1. **Mechanical AC pass** (Task 9): every `grep -c` check from spec R1–R14 returns its expected value, plus TC6, TC7, TC12 sanity checks.

2. **Manual smoke read**: read `skills/morning-review/references/walkthrough.md` Section 2a end-to-end. Confirm the section reads coherently (the implementer didn't paste content out of order between Tasks 3, 4, and 5; both sentinels were removed; no `<!-- SECTION-2A-... -->` markers remain), the parsing rules are stated unambiguously, the worktree command is exactly one git invocation with the `git -c core.hooksPath=/dev/null` prefix, the print template's path placeholder is filled with the resolved path, and the auto-advance language is unambiguous.

3. **Manual smoke read**: read `skills/morning-review/SKILL.md` Step 0 garbage sweep sub-step. Confirm the sub-step's regex matches only the canonical demo-worktree path form (not any `$TMPDIR/demo-*`), and the sub-step does NOT use `--force`.

4. **Manual smoke read**: read `skills/morning-review/SKILL.md` Step 3 outline. Confirm "Demo Setup" appears between "Completed Features" and "Lifecycle Advancement" in the numbered list.

5. **Live test (next overnight session, post-merge)**: cortex-command's project-root `lifecycle.config.md` ALREADY EXISTS at `/Users/charlie.hall/Workspaces/cortex-command/lifecycle.config.md` and currently has `type: other`, `test-command: just test`, and the standard lifecycle fields. To enable a live test of this feature, the user can manually add `demo-command: uv run python -m claude.overnight.dashboard` to that file (one line addition) and then run `/morning-review` after the next overnight session lands. Verify Section 2a fires, the offer is presented, accepting creates a worktree at `$TMPDIR/demo-overnight-{...}-{...}`, and the printed command runs in a separate terminal (or, since cortex-command's overnight runner sometimes runs from inside an SSH/mosh session, that the SSH guard correctly skips Section 2a). Confirm Section 6 cleanup reminder appears post-merge. Confirm the next morning-review's Step 0 sweep cleans up the prior demo worktree (if it was clean) or fails loudly (if dirty). This is the only end-to-end test that validates the user experience; it cannot be automated in the implementation phase because it requires a real overnight session and a real interactive `/morning-review` invocation. The plan deliberately does NOT auto-add `demo-command` to cortex-command's `lifecycle.config.md` — that's a user configuration choice, not an implementation deliverable.

## Veto Surface

The user already had two opportunities to redirect the design (the value-vs-scope check during research, and the security framing decisions during critical review). The choices that survived those rounds:

- **Approach H (inline in morning-review)** vs Approach A (standalone `/demo` skill). The user chose H. If a future use case wants demo-launch outside morning-review, extracting to `/demo` is mechanical.
- **Drop the smart-assessment layer entirely**. The "agent reasons about which features are demoable" framing is gone; v1 just offers when configured + branch exists + non-remote.
- **`$TMPDIR` worktree path with timestamp salt**. Not `lifecycle/sessions/`, not `.claude/worktrees/`. Resolved via `realpath` to handle macOS symlink chain.
- **Hook neutralization via `git -c core.hooksPath=/dev/null`** (A1).
- **Control-character rejection at parse time** (B1).
- **No printed dependency-execution warning** (C1 declined). User opt-in is the consent surface.
- **Sentinel-comment handoff between Tasks 3, 4, 5**: the alternative was to merge them into one big complex task. The sentinel approach keeps each task within the 5–15 minute envelope at the cost of two extra HTML comment lines (which are removed by the time Task 5 completes).

If any of these choices prove wrong during implementation, the affected task is the place to revisit (Tasks 3–5 for parser, worktree command, security boundary; Task 7 for sweep; etc.).

## Scope Boundaries

Maps directly to the spec's Non-Requirements (NR1–NR14). Not implemented in v1:
- Smart demoability assessment (NR1)
- Agent-managed demo process (NR2)
- "Still running" detection (NR3)
- Multiple demoable surfaces per repo / map schema (NR4)
- Per-feature `demo-command` override (NR5)
- Standalone `/demo` slash command (NR6)
- Conditional offer based on diff content / docs-only filter (NR7)
- Automatic worktree cleanup at Section 6 (NR8) — only the next-session sweep cleans up
- Changes to overnight runner / parser / state (NR9)
- New shared YAML parser module (NR10)
- Backward-compatibility shims for old walkthroughs without Section 2a (NR11)
- `demo-command` values with inline `#` comments (NR12)
- Cleanup for abandoned repos (NR13) — accepted limitation
- Printed dependency-execution warning (NR14)
- Auto-adding `demo-command` to cortex-command's own `lifecycle.config.md` — that's a user configuration choice, not an implementation deliverable
