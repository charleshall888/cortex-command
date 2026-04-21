# Plan: audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns

## Overview

Thirteen Implement-phase tasks. Task 1 sets up the Pass 2 child ticket (R7). Task 2 gates on #088 baseline readiness (R9) with an overnight-defer branch. Task 3 builds candidates.md skeleton. Task 4 performs an unconditional full-surface re-scan at Implement entry (closes both the research→plan-approval drift window and the plan-approval→implement drift window). Tasks 5–10 execute Pass 1 per-pattern audits (P1–P6) in parallel (fan-out from Task 4). Task 11 executes Pass 3 (P7) in parallel. Task 12 adds the P7 regression test (R12). Task 13 commits candidates.md and event log. R8 (post-merge drift check) remains a Review-phase activity.

### Execution Mode Contract

**#85's Implement phase runs interactively — not overnight.** Rationale:

- Spec R6 requires interactive mode for commits touching `claude/reference/*.md` or `claude/Agents.md`. Tasks 5–11 have dynamic file sets (grep enumerates hits at task start), so high-blast-radius paths cannot be classified at overnight-dispatch time.
- Spec R9 requires AskUserQuestion-based escalation when the baseline staleness bound fires. The overnight runner has no coherent halt-and-resume contract for >14-day waits within one round.
- Complex-tier sizing is retained for turn-budget purposes only. The executing agent is the main interactive session, not a dispatched sub-agent — `/commit` and PR workflows require the main agent's tool surface.

Overnight mode may still dispatch #85 tasks if they meet BOTH conditions at runtime: (a) the remediation only touches `skills/*/SKILL.md` or `skills/*/references/*.md` (non-high-blast), and (b) no R9 escalation is active. This is the mixed-mode path enabled by spec Non-Requirement #9. Choosing it requires explicit user opt-in (see Veto Surface).

Each Pass 1 task performs a **post-remediation path check before commit**: if any modified file is in `claude/reference/*.md` or `claude/Agents.md`, the task halts pre-commit, stages the edits, opens a PR via `gh pr create`, and waits for interactive self-review. Non-high-blast remediation commits direct-to-main via `/commit`.

## Tasks

### Task 1: Create Pass 2 child backlog ticket [x]
- **Files**: `backlog/*-rewrite-verification-mindset-md-to-positive-routing-structure-under-4-7-literalism.md` (new)
- **What**: Create a new backlog item titled exactly `"Rewrite verification-mindset.md to positive-routing structure under 4.7 literalism"` under epic #82. Body copies `research.md` §"verification-mindset.md structural inventory" verbatim under a `## Starting Context` heading; includes Scope, Non-requirement, and Acceptance sections from spec R7.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Use `/backlog` skill with `add` action. Frontmatter must include `parent: "82"`, `tags: [opus-4-7-harness-adaptation, skills]`, `blocked-by: [88]`, `priority: high`, `type: feature`. Do NOT set `lifecycle_phase` or `lifecycle_slug` on the child — it is a fresh backlog item. Source content for `## Starting Context` is at `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/research.md` §"verification-mindset.md structural inventory" (copy verbatim, do not link — line numbers may drift).
- **Verification**: `ls backlog/*-rewrite-verification-mindset-md-to-positive-routing-structure-under-4-7-literalism.md` exits 0 AND the file's frontmatter satisfies `parent == "82"` AND `88 in blocked-by` AND `"opus-4-7-harness-adaptation" in tags` (check with a Python YAML parse). Pass if both checks succeed.
- **Status**: [x] complete

### Task 2: Gate check — verify #088 baseline readiness (with overnight-defer branch)
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/events.log` (append on escalation or defer)
- **What**: Verify `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` exists with frontmatter `rounds_included >= 2`. Branch by execution mode and readiness:
  - **Baseline ready**: task passes; proceed to Task 3.
  - **Baseline missing AND interactive session AND ≤14 days since plan approval**: halt and inform user to wait for #088; Implement resumes when baseline lands.
  - **Baseline missing AND interactive session AND >14 days**: surface AskUserQuestion with options `continue_waiting | proceed_without_baseline | rescope`; log `scheduling_escalate` event with the user's choice; act accordingly.
  - **Baseline missing AND overnight session AND ≤14 days**: log `scheduling_defer` event (no AskUserQuestion — overnight cannot resolve the gate); Implement halts cleanly without escalation; daytime user will re-enter Implement when baseline lands or when the 14-day window elapses.
  - **Baseline missing AND overnight session AND >14 days**: log `scheduling_defer` with `reason: staleness-threshold-exceeded`; halt; daytime user must run Task 2 interactively to trigger escalation.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Frontmatter read via Python YAML. Event schemas:
  - `{"ts": "<ISO8601>", "event": "scheduling_escalate", "feature": "...", "days_since_plan_approval": <int>, "action": "continue_waiting|proceed_without_baseline|rescope"}`
  - `{"ts": "<ISO8601>", "event": "scheduling_defer", "feature": "...", "days_since_plan_approval": <int>, "reason": "interactive-required|staleness-threshold-exceeded"}`
  - Session-mode detection: check whether `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` or equivalent overnight-indicator env var is set, OR defer to the runner's mode flag. Fallback: if the task cannot determine mode, assume interactive.
- **Verification**: Pass if ANY of: (a) baseline file exists with `rounds_included >= 2`, (b) events.log has a `scheduling_escalate` event with `action in {proceed_without_baseline, rescope}`, (c) events.log has a `scheduling_defer` event (clean halt — downstream tasks remain pending, not marked failed).
- **Status**: [ ] pending

### Task 3: Create candidates.md skeleton
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (new)
- **What**: Create the candidates artifact with header (12-surface list from spec R1), 7 pattern sections (`## Pattern P1 — double-negation suppression` through `## Pattern P7 — [Cc]onsider hedge`), and auxiliary sections `## Preservation exclusions`, `## Null-pattern log`, `## Incidental findings`, `## Escalations`. Each pattern section contains an empty markdown table with columns `file:line | site excerpt | classification | M-label | commit SHA | notes`.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Pattern section headings must match the exact regex `^## Pattern P[1-7]` (for acceptance checks). No-emoji convention per `claude/reference/claude-skills.md`. Structure follows #053 precedent (`lifecycle/addendum-softening-aggressive-imperatives-in-skill-md-files/axis-b-candidates.md`).
- **Verification**: `grep -c '^## Pattern P[1-7]' lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` = 7 — pass if count = 7.
- **Status**: [ ] pending

### Task 4: Implement-entry full-surface pattern rescan
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md`, `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/events.log`
- **What**: Unconditionally re-run every locked pattern signature (spec Technical Constraints) against the 12-surface audit scope (spec R1) at Implement entry. Populate candidates.md pattern sections with the current file:line positions for every hit (this becomes the authoritative per-task starting state — downstream tasks work from this fresh baseline, not from research.md). Record a `candidates_refresh` event with per-pattern hit counts and the list of all current hits. This closes both drift windows (research→plan-approval AND plan-approval→implement-entry).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Pattern signatures (verbatim from spec Technical Constraints — do not redefine here to avoid spec drift): P1, P2, P3, P5, P6, P7 are regex-based; P4 is judgment-only. Reference spec §"Technical Constraints" for the regex text. 12-surface scope from spec R1. Event schema: `{"ts": "<ISO8601>", "event": "candidates_refresh", "feature": "...", "per_pattern_hit_counts": {"P1": N, "P2": N, ...}, "total_hits_recorded_in_candidates_md": N}`. For P4 (judgment-only, no regex): enumerate natural-language conditional blocks ≥10 lines manually per spec definition; do not attempt to auto-populate.
- **Verification**: Every regex-pattern-signature hit across the 12 surfaces at Task 4 completion time must appear as a `file:line` entry in candidates.md. Binary cross-check: for each of P1, P2, P3, P5, P6, P7, compute `grep -nE '<signature>' <each surface>` result count, then assert candidates.md's corresponding P[N] section contains a row for every one of those file:line positions. Pass if every hit is recorded; fail if any missing.
- **Status**: [ ] pending

### Task 5: Pass 1 / P1 — double-negation suppression audit and remediation
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (P1 section), files among the 12-surface audit scope that contain qualifying P1 sites (dynamic — enumerated from Task 4's rescan).
- **What**: For each P1 hit recorded in candidates.md by Task 4, apply per-site judgment against epic research.md's P1 hypothesis (double-negation likely skipped by 4.7; positive routing recovers intent). Update candidates.md P1 rows with `classification` in {qualifying, preservation-excluded, not-a-failure-mode}. For preservation-excluded hits, cite the preservation rule in the `notes` column. For qualifying hits, apply M1 (positive routing) by default, M4 (negation + rationale) where output-channel-directive overlap prevents pure positive framing. **Post-remediation path check**: if any modified file is in `claude/reference/*.md` or `claude/Agents.md`, halt pre-commit, stage edits, open PR via `gh pr create`, wait for interactive self-review; else commit direct-to-main via `/commit` as `Remediate P1 double-negation across <file list>`. If zero qualifying sites after exclusion: log a null entry in `## Null-pattern log` with the form `P1 — N sites audited, M preservation-excluded, 0 qualifying. Reason: <summary>.` — no commit.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: 12-surface audit scope per spec R1. `verification-mindset.md` is READ-ONLY in Pass 1 — any P1 hits there stay in candidates.md with `classification: routed-to-pass-2-child` and produce no edit under #85. Preservation ring-fence: 7 categories + 10 anchored decisions (spec Technical Constraints). Anchor-check grep is file-scoped per R10 (`grep -F "<anchor>" <specific file>`). Sites are enumerated from Task 4's rescan (authoritative — not from research.md's possibly-stale Per-site table). Commit discipline: `/commit` skill, not raw `git commit`.
- **Verification**: Every P1 row in candidates.md with `classification: qualifying` AND non-null `commit SHA` must satisfy: (a) the SHA exists on main (`git cat-file -e <sha>` exits 0), (b) the SHA's diff touches the file named in the row (`git diff --name-only <sha>^..<sha> | grep -qF <file>` exits 0), (c) the pattern signature no longer matches at the recorded file:line post-commit. For rows with `classification: preservation-excluded`, the `notes` column names a preservation rule from spec R10 (one of the 7 categories or 10 anchored decisions). For `classification: routed-to-pass-2-child` rows, no further check. If the P1 section produced a null entry, assert the entry cites the site count audited and the exclusion count. Pass if all rows in P1 satisfy their classification's check.
- **Status**: [ ] pending

### Task 6: Pass 1 / P2 — ambiguous conditional bypass audit and remediation
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (P2 section), files with qualifying P2 sites (dynamic from Task 4).
- **What**: For each P2 hit from Task 4's rescan, classify whether the path-guard scope requires explicit control-flow framing under 4.7. Qualifying sites default to M2 (explicit format spec — convert prose guard to structured control-flow statement). Post-remediation path check + commit workflow same as Task 5. Commit message: `Remediate P2 ambiguous-conditional-bypass across <file list>`. Null case: `P2 — N sites audited, 0 qualifying. Reason: <summary>.` in `## Null-pattern log`.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: P2 hits are preservation category 3 (control-flow gates) by default — M2 rewrites the gate form without removing the gate. Epic research.md explicitly flags `refine/SKILL.md` path-guard as HIGH-RISK (see research.md's Per-site table — but rely on Task 4's rescan for current positions, not research.md's line numbers).
- **Verification**: Every P2 row with `classification: qualifying` AND non-null `commit SHA` satisfies the (a)(b)(c) triplet from Task 5's Verification. Preservation-excluded rows cite a rule. Null case asserts audited-count and rationale. Pass if all rows satisfy their classification's check.
- **Status**: [ ] pending

### Task 7: Pass 1 / P3 — negation-only prohibition audit and remediation
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (P3 section), files with qualifying P3 sites (dynamic from Task 4, excluding `verification-mindset.md`).
- **What**: For each P3 hit from Task 4's rescan, classify per spec R10 preservation + per-site judgment. `verification-mindset.md` hits are READ-ONLY in #85 — record with `classification: routed-to-pass-2-child`, no edit. Non-verification-mindset qualifying sites default to M1 (positive routing); M4 only when negation is load-bearing with documented rationale. Commit workflow same as Task 5. Commit message: `Remediate P3 negation-only prohibition across <file list>`.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: The 10 anchored preservation strings from spec Technical Constraints — apply `grep -F <anchor> <specific file>` per R10 to confirm each still exists; if any anchor returns 0 matches (anchor reworded by a sibling ticket), log in `## Escalations` and treat as non-remediation (surface to user at Review phase per spec Edge Case). Do NOT attempt to restore an anchored string under #85.
- **Verification**: Every P3 row satisfies classification's check per Task 5 format. Anchored preservation rows list the specific anchor string matched. Routed-to-pass-2-child rows need no further check beyond row presence. Pass if all rows satisfy their classification's check.
- **Status**: [ ] pending

### Task 8: Pass 1 / P4 — multi-condition gate audit and remediation
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (P4 section), files with qualifying P4 sites (dynamic — judgment-enumerated at Task 4).
- **What**: For each P4 candidate block (judgment-enumerated in Task 4 per spec definition: natural-language conditional blocks ≥10 lines without explicit control structure), judge whether the block's implicit short-circuit logic is at risk under 4.7 literalism. Qualifying blocks default to M2 (convert to explicit numbered-step control structure with `if / then / else` framing). Commit workflow same as Task 5. Commit message: `Remediate P4 multi-condition-gate across <file list>`.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: P4 is preservation category 3 (control-flow gates). If a block's gate semantics are load-bearing, use M4 (explicit control + rationale) rather than skipping. **Fallback for missing section anchors**: if a research-era section heading (e.g., "Worktree-Aware Phase Detection") was renamed between research and implement, grep for a structural feature of the block (function name, distinctive phrase) instead; log the rename in `## Escalations`.
- **Verification**: Every P4 row satisfies classification's check per Task 5 format. Since P4 is judgment-only, the `file:line` range in each row must still contain the described conditional block structure post-commit (`wc -l` of the named line range matches the row's expected line count, or the row is annotated with post-commit range). Pass if all rows satisfy their classification's check.
- **Status**: [ ] pending

### Task 9: Pass 1 / P5 — procedural-order dependency audit and remediation
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (P5 section), files with qualifying P5 sites (dynamic — expected subset of the 3 known verbatim-contract sites; Pass 1 may surface additional non-verbatim sites).
- **What**: For each P5 hit from Task 4's rescan, classify: (a) verbatim-substitution contract for subagent-dispatch template (SKIP per R11 default — spec Non-Req #2), or (b) non-verbatim-contract site (M4 — explicit rationale for the negation). Commit workflow same as Task 5. Commit message (if any non-verbatim qualifying site): `Remediate P5 procedural-order across <file list>`. Null case: `P5 — N sites audited, M verbatim-SKIP, 0 qualifying. Reason: <summary>.` in `## Null-pattern log`.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Spec R11 default: SKIP for verbatim-substitution contracts; M4 for non-verbatim. Each SKIP entry records `classification: verbatim-contract-preservation` with `M-label: SKIP`. P5 has no regression guard (R12 excludes it — SKIP sites preserve original text, no signature change).
- **Verification**: Every P5 row satisfies classification's check per Task 5 format. SKIP rows must cite `verbatim-contract-preservation` rationale in notes. Pass if all rows satisfy their classification's check.
- **Status**: [ ] pending

### Task 10: Pass 1 / P6 — examples-as-exhaustive-list audit and remediation
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (P6 section), files with qualifying P6 sites (dynamic from Task 4).
- **What**: For each P6 hit from Task 4's rescan, classify: menu-as-exhaustive (qualifying), menu-as-authoritative (preservation — e.g., angle-menu), or example-list-with-clear-non-exhaustive-framing (skip). Qualifying sites default to M1 with explicit "not exhaustive" framing added. Commit workflow same as Task 5. Commit message: `Remediate P6 examples-as-exhaustive across <file list>`.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Angle-menu in `critical-review/SKILL.md` is anchored preservation (distinct-angle differentiation). Evaluate whether menu authority can be preserved while preventing closed-set interpretation — the "from the following" framing may be rewritable without changing authority. If not clean, SKIP with preservation-rule citation.
- **Verification**: Every P6 row satisfies classification's check per Task 5 format. Pass if all rows satisfy their classification's check.
- **Status**: [ ] pending

### Task 11: Pass 3 / P7 — [Cc]onsider hedge audit and remediation
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` (P7 section), files among the P7 sites within R1 scope with qualifying classification (a).
- **What**: Use the P7 hits from Task 4's rescan (authoritative — `grep -rn '\b[Cc]onsider\b' skills/` at Task 4 time). Classify each site: (a) conditional-requirement, (b) genuinely optional, (c) polite imperative. Record every hit as a row in candidates.md P7 table, regardless of classification. Only (a) sites within R1's 12-surface scope are remediation candidates — default M1 (positive routing replacing "consider X" with unambiguous phrasing); M4 where removing the softening loses load-bearing rationale. Sites outside R1's 12-surface scope (e.g., `skills/pr/`, `skills/morning-review/`) are recorded with classification but `M-label: out-of-scope-of-R1` and produce no edit. Commit workflow same as Task 5. Commit message: `Remediate P7 consider-hedge across <file list>`.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: The final P7 site count is whatever Task 4's rescan produces — NOT the research-era count of 9. Classifications (a/b/c) are per-site judgment at task time. `skills/lifecycle/references/plan.md` (this plan's own reference file — note the meta-level) is in scope per R1; if it contains a `consider` hedge, it is a live audit target.
- **Verification**: Every P7 row satisfies classification's check per Task 5 format. Specifically: out-of-scope rows list `out-of-scope-of-R1` in M-label. Rows with classification (a) in R1 scope have either a commit SHA or a preservation rule citation. The P7 table's row count equals Task 4's recorded P7 hit count from the rescan (no hard-coded row count — dynamic). Pass if all rows satisfy their classification's check and row count equals rescan count.
- **Status**: [ ] pending

### Task 12: Add P7 grep-regression test
- **Files**: `tests/test_p7_regression.py` (new)
- **What**: Add a pytest test module that, for every P7 candidates.md row with classification (a) AND non-null commit SHA AND `M-label in {M1, M4}`, asserts `\bconsider\b` does not appear at the remediated file:line post-commit. Test parametrizes dynamically by parsing candidates.md. If zero qualifying rows exist (entire P7 work skipped or produced no remediation), the test module logs an explicit skip with reason, which does NOT count as pass — `just test` must still exit 0, but a test runner summary flag surfaces that P7 regression coverage is vacuous.
- **Depends on**: [5, 6, 7, 8, 9, 10, 11]
- **Complexity**: simple
- **Context**: Parse candidates.md by reading the P7 table rows; split on `|`. Use `pytest.mark.parametrize` over the filtered (file, line) list. If the list is empty, emit a single `pytest.skip` with a descriptive message. Per spec R12: only P7 is guarded — P1, P3, P5 have no regression guard (too fuzzy / no signature change).
- **Verification**: `just test` exits 0. Additionally: if the P7 table has ≥1 classification-(a) row with non-null SHA, at least one parametrized test case runs (binary check on pytest collection output: `just test 2>&1 | grep -c 'test_p7_regression' >= 1`). If zero such rows, the skip-logged-with-reason behavior is observable in test output. Pass if both conditions hold.
- **Status**: [ ] pending

### Task 13: Commit candidates.md and events.log updates via `/commit`
- **Files**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md`, `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/events.log`
- **What**: Stage and commit the final candidates.md and events.log state via `/commit`. Commit message: `Land #85 candidates.md and audit event log`. `lifecycle/` is not in #088's freeze path list, so safe during the measurement window.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: Per `claude/Agents.md` ("Git Commits: Always Use the `/commit` Skill"). Commit-artifacts is true per `lifecycle.config.md`, so the phase-transition Implement→Review commit also lands automatically; this task explicitly captures candidates.md and events.log state before Review reads them.
- **Verification**: `git log --oneline main -- lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md | head -1 | grep -q .` exits 0 — pass if candidates.md has at least one commit on main.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification after all tasks:

1. **Surface correctness**: `ls` each of the 12 audit surfaces (spec R1) — all exit 0.
2. **Candidates completeness**: every P1–P7 table in candidates.md has one row per pattern hit from Task 4's rescan (no missing hits); every row has a classification; every qualifying row has either a commit SHA or a preservation-rule citation.
3. **Commit conformance + diff coverage**: for every commit matching `^[0-9a-f]+ Remediate P[1-7] ` on main during #85's window, `git diff --name-only <sha>^..<sha>` lists at least one file appearing in the candidates.md row(s) that reference that SHA (no phantom commits).
4. **PR gate**: for every commit on main in #85's window that modifies `claude/reference/*.md` or `claude/Agents.md`, `gh api repos/:owner/:repo/commits/<sha>/pulls --jq 'length'` ≥ 1 AND `gh api` exits 0. If `gh api` fails (non-zero exit), treat as FAIL per R6 — halt remediation.
5. **Preservation honored**: for each of the 10 anchored strings (spec Technical Constraints), `grep -Fc "<anchor>" <specific file>` = 1 post-#85 (spec R10). If any anchor returns 0, check `## Escalations` section in candidates.md for a logged "anchor reworded" entry; if missing, FAIL.
6. **Regression test**: `just test` exits 0 with `test_p7_regression.py` included (spec R12).
7. **Child ticket exists**: `ls backlog/*-rewrite-verification-mindset-md-*.md` exits 0 with correct frontmatter (spec R7).
8. **verification-mindset.md untouched**: `git diff main~<N>..main -- claude/reference/verification-mindset.md` shows no changes since #85 started (spec R2 / Non-Req #1).

R8 (post-merge drift check against #088 baseline) is executed by the lifecycle Review phase against the spec — not a plan task.

## Veto Surface

- **Execution Mode — interactive default** — the plan declares Implement interactive-only for this ticket. Alternative: mixed-mode per task (overnight for non-high-blast commits, interactive for PR-gated and AskUserQuestion steps). Interactive-only is simpler and avoids the dynamic-classification complexity; mixed-mode has wall-clock benefits if the ticket has long stretches of non-high-blast work. User may choose mixed-mode by opting in explicitly at Implement entry (update `lifecycle.config.md` or add a `mode_override` event to events.log).
- **Tasks 5–11 parallelism — fan-out from Task 4** — all P1–P7 pattern tasks now declare `Depends on: [4]` and can execute concurrently under the implement phase's parallel dispatch (per `skills/lifecycle/references/plan.md`). Rationale: pattern signatures are disjoint; candidates.md sections are disjoint; overlapping-site severity ordering is a spec-level tie-breaker, not a sequential dependency. Alternative: keep the serial chain for commit-order readability — loses wall-clock time for readability gains.
- **Task 4 unconditional rescan cost** — Task 4 runs all pattern signatures across all 12 surfaces unconditionally at Implement entry (not only if freeze-window drift detected). This closes the research→plan-approval drift window that the original plan left open. Cost: one full pattern-signature pass (~30 seconds of grep). Alternative: conditional rescan triggered by freeze-window commit detection — cheaper but leaves the research→plan-approval window uncovered.
- **Verification tier — per-row classification cross-check** — Tasks 5–11 verifications cross-check candidates.md rows against commit diffs and pattern signatures, not just commit subject presence. Alternative: keep the lighter subject-line-only check — faster but self-sealing (a task can bypass the audit and pass verification with an empty commit).
- **Task 12 regression-test trivial-pass handling** — when P7 has zero classification-(a) remediated rows, the test module emits a logged skip rather than silently parametrizing-to-zero. Alternative: accept a silent vacuous pass — simpler but hides the "no regression coverage" signal. The logged skip adds one signal, no failure mode.
- **Task 1 timing** — Task 1 creates the child ticket during Implement (after plan approval), not during Plan-phase authoring. Conservative choice avoids pre-approval side effects. If the user wants immediate creation, pull forward to a Plan-phase action instead.
- **R8 (drift smoke check) placement as Review-phase activity** — plan delegates to Review. Alternative: include as a final Implement task. Current choice matches how Review consumes spec acceptance criteria.

## Scope Boundaries

- **Not in scope** (from spec Non-Requirements):
  - `verification-mindset.md` whole-file rewrite (routed to Pass 2 child ticket per R7).
  - The 3 known P5 sites at `lifecycle/references/{research,plan,implement}.md` (SKIP per R11 default — verbatim subagent-dispatch contracts are correctly literal).
  - P8 severity-gating audit (deferred; Pass 1 incidentals recorded in `## Incidental findings` for a future ticket).
  - Qualitative spike-test of ring-fenced sites (coverage routed to #088's quantitative drift check).
  - Automated CI gate for R6 (process requirement only, no workflows).
  - Probe-based behavioral test for P1–P6 remediation verification (no harness exists).
  - Edits to `skills/overnight/` or `skills/pr/` (outside R1 audit surface).
  - Updates to epic research's P1–P7 taxonomy.
  - Rewrites of preservation rules or anchored decisions.
  - Cross-epic reconciliation with #067/#068/#069 (F1–F5 sibling tickets).
  - Overnight execution for `claude/reference/*.md` or `claude/Agents.md` commits (R6 requires interactive). Under this plan's Execution Mode Contract, the entire Implement phase runs interactively by default, so this is moot unless user opts into mixed-mode.

- **Dependencies outside plan scope**:
  - #088's baseline snapshot must land with `rounds_included >= 2` before Task 5 (first remediation commit). Task 2 gates this.
  - 14-day staleness bound per R9 — if breached in interactive session, Task 2 surfaces AskUserQuestion escalation; if breached in overnight session, Task 2 logs `scheduling_defer` and Implement halts until daytime.
