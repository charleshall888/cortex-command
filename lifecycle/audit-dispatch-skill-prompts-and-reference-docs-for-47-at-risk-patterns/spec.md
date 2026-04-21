# Specification: Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns

> Epic reference: Child of [#082 Adapt harness to Opus 4.7](../../backlog/082-adapt-harness-to-opus-47-prompt-delta-capability-adoption.md). Primary research: [epic research.md](../../research/opus-4-7-harness-adaptation/research.md) defines P1–P7 patterns and M1–M3 remediation mechanisms; [this ticket's research.md](./research.md) narrows scope, corrects the audit surface, broadens Pass 3, and splits Pass 2 to a child ticket.

## Problem Statement

Opus 4.7's stricter literalism exposes seven prompt patterns (P1–P7) that #053's earlier rewrite did not cover. The 12 surfaces that dispatch subagents or load globally through `~/.claude/CLAUDE.md` contain candidate sites for these patterns. Left unremediated, dispatch skills and reference files produce subtly wrong output under 4.7 — gappy synthesis (P1), mis-parsed path guards (P2), dropped caveats (P3), skipped control flow (P4), refused reorderings (P5), closed-set interpretation (P6), or under-triggered soft imperatives (P7). This ticket audits the corrected surface and remediates the sites that survive preservation-rule exclusion and per-site judgment. Verification-mindset.md whole-file rewrite (the P3 outlier from #084) is split to a new child ticket with scope specified in R7. #088's frozen-prompt measurement window gates this ticket's implement phase so a quantitative baseline exists for post-change drift comparison.

## Requirements

1. **Audit surface (12 files)**: Pass 1 and Pass 3 scan these exact files and their child `references/*.md` (for the 6 skills) — no more, no fewer:
   - **6 dispatch skills**: `skills/critical-review/`, `skills/research/`, `skills/discovery/`, `skills/lifecycle/`, `skills/diagnose/`, `skills/refine/` (each: `SKILL.md` + all `references/*.md`)
   - **6 reference/global files**: `claude/reference/claude-skills.md`, `claude/reference/context-file-authoring.md`, `claude/reference/output-floors.md`, `claude/reference/parallel-agents.md`, `claude/reference/verification-mindset.md` (read-only in this ticket — Pass 2 child handles), `claude/Agents.md`
   - Acceptance: `ls` each path exits 0; the candidates file (Requirement 4) lists all 12 surfaces in its header section.

2. **Pass 1 — Pattern-grep audit for P1–P6 across the 12 surfaces**: For each surface, grep for P1–P6 pattern signatures (Technical Constraints section locks the exact regex), apply per-site judgment against the epic research hypothesis column, exclude preservation-ringed sites (with rule citation), and emit a per-pattern remediation commit if ≥1 qualifying site survives. `verification-mindset.md` is read-only in Pass 1 — P3 hits on it are noted and routed to the Pass 2 child ticket, not remediated under #85. **Pattern signatures are locked at Spec time**; amendments require spec revision, not Plan-time discretion.
   - Acceptance: `git log --oneline main -- skills/ claude/reference/ claude/Agents.md | grep -E 'P[1-6]'` returns ≥1 commit per pattern that had ≥1 qualifying site after exclusion; patterns with zero qualifying sites have no commit and a documented null entry in `candidates.md` (Requirement 4). `grep -n` over `verification-mindset.md` post-#85 is textually unchanged from pre-#85.

3. **Pass 3 — `[Cc]onsider` audit across all 9 occurrences in `skills/` (broadened)**: Classify each site by three-category rule: (a) conditional-requirement (underlying action required given the preceding condition), (b) genuinely optional, (c) polite imperative. Only (a) sites are remediation candidates. Remediate (a) sites under mechanism M1 (positive routing) by default; use M4 (context + rationale) if removing the softening loses load-bearing rationale.
   - Acceptance: `candidates.md` contains a table with 9 rows, one per `[Cc]onsider` site, with columns `file:line | classification | remediation decision | commit SHA or "null"`. For every row with classification `(a)`, the remediation decision is one of `M1`, `M4`, or `skip — preservation rule [name]`.

4. **Candidates artifact at `lifecycle/{slug}/candidates.md`**: Matches #053's `axis-b-candidates.md` precedent. Structure: (a) header listing all 12 surfaces, (b) per-pattern section (P1–P6, P7) with per-site decision table, (c) preservation-exclusion log with rule-citation per excluded site, (d) null-pattern log for patterns with zero qualifying sites. **Refresh step at implement entry**: if the Plan→Implement gap exceeds the freeze window (Requirement 9), re-run the locked pattern signatures against the audit surface and update candidates.md before remediation commits begin — sites added/removed by freeze-period edits are flagged.
   - Acceptance: `ls lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` exits 0; the file contains seven `## Pattern P[1-7]` sections; every site the commits touched appears in exactly one pattern section with the commit SHA recorded. At implement entry, a `candidates_refresh` event is logged to `events.log` (with either `refreshed: true` and a diff summary, or `refreshed: false, reason: "no freeze-window drift"`).

5. **Pattern-bucketed commits**: Remediation produces one git commit per remediated pattern (not per file). Commit message format: `Remediate P<n> <short pattern name> across <file list or "audit surface">` (matches #053 Task 8 precedent).
   - Acceptance: `git log --oneline main -- skills/ claude/reference/ claude/Agents.md` commits for #85 each match the regex `^[0-9a-f]+ Remediate P[1-7] `.

6. **PR gate for high-blast-radius files (pre-merge human review)**: Any commit that modifies `claude/reference/*.md` or `claude/Agents.md` lands via GitHub PR — not direct-to-main. Non-SKILL.md edits in `skills/*/references/` may still land direct-to-main per #053 precedent. **This is a pre-merge review gate, not a rollback mechanism** — rollback for any mistake (PR-merged or direct) is `git revert`. **Reviewer**: the ticket author acts as adversarial self-reviewer on the diff in the PR page's Files tab — the same discipline /critical-review applies to spec review. **Execution mode**: commits touching the two high-blast-radius paths (`claude/reference/*.md`, `claude/Agents.md`) run in interactive mode only, never under the overnight runner's `--dangerously-skip-permissions`. No CI automation is added.
   - Acceptance: for every commit on main that modifies `claude/reference/*.md` or `claude/Agents.md` during #85's execution window, `gh api repos/:owner/:repo/commits/<sha>/pulls --jq 'length'` returns ≥ 1 AND the API call exits 0; if the `gh api` exit is non-zero (auth/network/non-github origin failure), the acceptance check is treated as FAIL not PASS — halt remediation and surface the error.

7. **Pass 2 child ticket created as first Plan task — scope pre-specified here**: `verification-mindset.md` whole-file rewrite is out of scope for #85. A new backlog ticket under epic #82 is created via `/backlog add` at the start of Plan, titled exactly `"Rewrite verification-mindset.md to positive-routing structure under 4.7 literalism"`. Child ticket body includes:
   - **Parent**: #82; **Blocked-by**: #088 (same freeze dependency as #85).
   - **Starting context**: This ticket's `research.md` §Codebase Analysis §"verification-mindset.md structural inventory" is copied verbatim into the child's body under a `## Starting Context` heading (not referenced — copied — to avoid dangling cross-lifecycle reference).
   - **Scope**: Identify which of Iron Law, Gate Function, Red Flags, Common Failures, and Common Rationalizations sections exhibit P3 failure mode under 4.7 via a validation probe (per #084 reopener clause: real git repo + "tests pass" claim context). Remediate only the failing sections under M1 (positive routing). Preserve the 5-step Gate Function structure as the authoritative positive process regardless of rewrite extent — it is load-bearing.
   - **Non-requirement**: child ticket is NOT committed to "whole-file rewrite" if probe identifies only 1–2 sections as failing. "Whole-file rewrite" in this spec is shorthand for "Pass 2's full scope lives in the child"; the child may ship a section-level rewrite if its own Research supports it.
   - **Acceptance (child)**: probe log committed to child's lifecycle directory; remediated sections structurally positive-routed; ring-fenced Gate Function intact.
   - Acceptance (for #85): `ls backlog/*-rewrite-verification-mindset-md-to-positive-routing-structure-under-4-7-literalism.md` exits 0 (exact-stem match, not a glob prefix) after Plan phase begins; the backlog item's frontmatter has `parent: "82"`, `tags` include `opus-4-7-harness-adaptation`, and `blocked-by: [88]`.

8. **Post-change drift check against #088 baseline — cleanliness-guarded**: After #85's remediation commits merge to main, a smoke check compares dispatch metrics on the 6 audited dispatch skills against #088's committed baseline at `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md`. **Baseline-cleanliness guard**: before consuming the baseline, verify (a) #088's snapshot frontmatter has `rounds_included >= 2`, and (b) `git log --oneline <git_sha_window_start>..<git_sha_window_end> -- skills/ claude/reference/ claude/Agents.md CLAUDE.md` returns zero commits (no freeze violations during the measurement window). If either check fails, record the baseline as contaminated and skip drift comparison — note the contamination in review.md `## Observations` and file a follow-up ticket for baseline re-collection. The drift check is advisory, not a hard gate.
   - Acceptance: `grep -c "## Observations" lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/review.md` ≥ 1; the section names at least the per-skill num_turns and cost_usd median values from the post-#85 window alongside the baseline values (or records "baseline contaminated — comparison skipped" with reason).

9. **Scheduling dependency — implement blocks on #088, with staleness bound**: Spec and Plan phases proceed regardless of #088 state. Implement phase cannot begin until `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` exists on main with `rounds_included >= 2`. **Staleness bound**: if 14 days elapse from Plan approval without the baseline landing, escalate to user via AskUserQuestion with options: (a) continue waiting (default if #088 is making progress), (b) proceed without baseline (R8 drift check skipped; note in review.md), (c) re-scope #85 (return to Spec). Log the escalation and user choice as `scheduling_escalate` events in events.log.
   - Acceptance: `ls research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` exits 0 and the frontmatter satisfies `rounds_included >= 2` before the first remediation commit; OR a `scheduling_escalate` event with `action` in `["proceed_without_baseline", "rescope"]` exists in events.log before implement activity.

10. **Preservation rules honored — anchor-check scoped to specific files**: The 7 preservation categories and 10 anchored preservation decisions from #053 remain unmodified by #85. Any audit hit that falls under preservation is excluded with rule citation in `candidates.md`. Ring-fenced sites are not re-validated under 4.7 in this ticket (#088's quantitative drift check is the chosen coverage per OQ4 resolution). **Anchor-check grep scope**: the anchored-string grep is scoped to the specific file each anchor lives in (e.g., `grep -F "Do not soften or editorialize" skills/critical-review/SKILL.md`), not repo-wide, to avoid false-positives where the anchored phrase happens to be quoted elsewhere (e.g., inside this spec or research.md).
   - Acceptance: for each of the 10 anchored strings, `grep -Fc "<anchored string>" <specific file>` returns exactly 1 post-#85; `candidates.md` `## Preservation exclusions` section lists every excluded site with its rule-citation.

11. **Remediation mechanism classification per site — per-pattern defaults specified**: Each remediated site is tagged with its remediation mechanism. Per-pattern defaults:

    | Pattern | Default mechanism | Rationale |
    |---------|-------------------|-----------|
    | P1 (double-negation) | M1 (positive routing) | Clean inversion possible for most; if output-channel-directive overlap, M4 with rationale |
    | P2 (ambiguous conditional bypass) | M2 (explicit format spec) | Gate scope needs explicit control-flow statement, not prose |
    | P3 (negation-only prohibition) | M1 (positive routing) | Anthropic-backed canonical remediation; M4 only when negation is load-bearing with rationale |
    | P4 (multi-condition gate) | M2 (explicit format spec) | Same as P2 — implicit control flow needs to become explicit |
    | P5 (procedural order dependency) | **SKIP for verbatim-substitution contracts** (default for the 3 sites in `lifecycle/references/{research,plan,implement}.md`); M4 (negation + rationale) if Pass 1 surfaces non-verbatim sites | The 3 known P5 sites are verbatim subagent-dispatch templates where ordering is load-bearing — the literal instruction is correct under 4.7; no remediation needed |
    | P6 (examples-as-exhaustive) | M1 (positive routing with "not exhaustive" framing) | Explicit scope statement neutralizes closed-set interpretation |
    | P7 `consider` | M1 for (a) conditional-requirement sites; M4 if polite softening carries justification | Already specified in R3 |

    **M5 (downstream-filter framing)** is a fallback for severity-gate sites that surface incidentally during Pass 1 grep — not a primary choice for the 7 patterns. **M3 (output-gate on internal verification)** applies where verification steps are being narrated inappropriately; not expected to surface in this ticket's scope.
    - Acceptance: every row in `candidates.md`'s Pattern P1–P7 tables that records a commit SHA also records an M-label from the set `{M1, M2, M3, M4, M5, SKIP}`. `SKIP` entries record the reason (e.g., "verbatim-contract preservation").

12. **Grep-regression test for high-signal patterns — scope matches locked signatures**: A single new test or test-case added to `tests/` asserts that specific remediated-site text signatures do not reappear post-#85. Scope the regression guard to the subset of patterns with stable grep signatures from Technical Constraints: P7 `consider` sites remediated under M1 (softening removed — regression guard: `\bconsider\b` should not reappear in the specific remediated file:line positions). **P5 sites are NOT in the regression guard** because they're skipped per R11 defaults — the original text is preserved, no signature to guard. Do NOT attempt a regression guard for P1/P3 signatures (too fuzzy — high false-positive rate overwhelms value).
    - Acceptance: `just test` exits 0 with the new test present; the test fails if any of the remediated P7 sites re-introduces `\bconsider\b` at the specific file:line positions (recorded in candidates.md).

## Non-Requirements

- **No verification-mindset.md rewrite in #85**: routed to the child ticket (Requirement 7). #85 treats `verification-mindset.md` as read-only.
- **No remediation of the 3 known P5 sites** at `lifecycle/references/{research,plan,implement}.md`: these are verbatim subagent-dispatch contracts; "do not omit, reorder, or paraphrase" is correctly literal under 4.7 literalism and working as intended. If Pass 1 grep surfaces additional P5 sites where ordering is not load-bearing, per-site judgment determines remediation per R11 defaults.
- **No P8 severity-gating audit in #85**: deferred to a follow-up ticket if P1 grep work surfaces severity-gate sites worth their own pass. Document any incidental finds in `candidates.md` `## Incidental findings` for the follow-up.
- **No qualitative spike-test of ring-fenced sites**: OQ4 resolution accepts #088's quantitative drift check as sufficient coverage. Do not run individual dispatches-against-real-artifacts to inspect for dropped caveats.
- **No automated CI gate for the PR requirement**: Requirement 6 is a process requirement, not an infrastructure requirement. No `.github/workflows/` files are added.
- **No probe-based behavioral test for P1–P6 remediation verification**: D3 from research tradeoffs axis D. No harness exists; build cost not justified.
- **No edit to `skills/overnight/` or `skills/pr/`** — excluded from audit surface per Requirement 1.
- **No update to epic research's P1–P7 taxonomy**: taxonomy is frozen for this ticket's scope; M4/M5 mechanisms from web research are adopted as remediation options but not re-integrated into the epic's mechanism taxonomy by #85.
- **No rewrite of preservation rules or anchored decisions**: the ring-fence is honored as documented; #85 does not propose changes to it.
- **No cross-epic reconciliation**: sibling tickets #067/#068/#069 (observed failures F1–F5) are out of scope; #85 does not consume or feed them.
- **No overnight execution for `claude/reference/*.md` or `claude/Agents.md` commits**: Requirement 6 requires interactive mode for these paths. Other #85 commits (on dispatch skills' SKILL.md + references/) may run overnight.

## Edge Cases

- **A pattern bucket collapses to zero qualifying sites after exclusion filtering**: `candidates.md` records a null entry under the pattern section; no commit is produced for that pattern. This is expected — #053's P1/P4/P5 buckets collapsed similarly.
- **A ring-fenced site grep-matches a P1–P6 pattern**: excluded with rule citation in `candidates.md`; no edit. If Pass 1 grep encounters an apparent failure mode that the ring-fenced site exhibits *in the current surface* (not hypothetically), flag it in `candidates.md` `## Escalations` section and surface to the user at review.md; do not edit.
- **Line numbers in anchored preservation decisions have drifted since #053**: use string-match (`grep -F`), not line-number-match, to identify preservation sites.
- **#088's measurement window extends beyond Plan completion**: #85 sits at "plan approved" with no implement activity until the baseline snapshot lands, OR until the 14-day staleness bound fires and the user chooses via escalation. No pre-emptive implement work during the freeze.
- **Freeze-window prompt-surface edits slip through** (another ticket or hand-edit modifies a file in `skills/`, `claude/reference/`, `claude/Agents.md`, or `CLAUDE.md` between `git_sha_window_start` and `git_sha_window_end`): candidates.md's implement-entry refresh (R4) catches the drift; flagged sites are re-evaluated before remediation commits.
- **#088's baseline ships with contaminated window**: R8's cleanliness guard catches this; drift check is skipped; review.md records the contamination and a follow-up ticket is filed for baseline re-collection.
- **Pass 1 grep surfaces a severity-gating (P8) hit**: document in `candidates.md` `## Incidental findings` section for the P8 follow-up ticket; do not remediate under #85.
- **A ring-fenced anchored string was silently moved or reworded by a sibling ticket after #053**: `grep -F` returns zero matches for the anchored phrasing. Treat as a correctness-bug: surface to the user at review.md `## Observations`, do not attempt to restore the string under #85. File a follow-up.
- **Multiple patterns match the same site** (e.g., a site is both P1 and P6): assign to the highest-severity pattern per adversarial review (typically P3 > P1 > P6 > P4 > P5 > P2 > P7); document the secondary match as a cross-reference in `candidates.md`.
- **PR reviewer requests changes on a `claude/reference/*.md` PR**: revise and re-push to the PR branch; do not merge until self-review approval. Standard PR workflow.
- **A commit on `claude/reference/*.md` or `claude/Agents.md` lands direct-to-main during #85's execution window**: R6 acceptance check fails; revert the direct commit and re-land via PR. Never override the gate.
- **`gh api` check fails due to auth/network/non-github origin**: R6 acceptance FAILS (not passes). Halt remediation on the affected path; surface the error to the user. The acceptance check does not treat tooling failure as "no PR required."

## Changes to Existing Behavior

- **MODIFIED**: Up to 6 dispatch skills' `SKILL.md` + `references/*.md` files under `skills/{critical-review,research,discovery,lifecycle,diagnose,refine}/` — per-pattern remediation edits per Requirement 2.
- **MODIFIED**: Up to 5 reference files under `claude/reference/` (excluding `verification-mindset.md`) — per-pattern remediation edits per Requirement 2.
- **MODIFIED**: `claude/Agents.md` — per-pattern remediation edits per Requirement 2 (if any P1–P7 hits survive exclusion).
- **ADDED**: `lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md` — per-site exclusion decisions and per-pattern remediation tables.
- **ADDED**: one new backlog ticket under epic #82 for verification-mindset.md remediation (created during Plan per Requirement 7).
- **ADDED**: one new test case in `tests/` for P7 grep-regression guard per Requirement 12.
- **PROCESS CHANGE**: PR review required for `claude/reference/*.md` and `claude/Agents.md` edits during #85's execution window (and implicitly continuing afterward as the new convention, though enforcement is voluntary post-#85). Rationale for diverging from #053's direct-to-main precedent: #053's remediation surface overlapped less with globally-loaded reference files (it focused on SKILL.md imperative softening under `skills/`); #85 touches `claude/reference/*.md` (conditionally-loaded into every session via `~/.claude/CLAUDE.md`) and `claude/Agents.md` (symlinked to `~/.claude/CLAUDE.md`, loaded unconditionally at every session start). The blast-radius asymmetry justifies the divergence.

## Technical Constraints

- **Pattern signatures (locked — Plan may NOT retune without spec revision)**:
  - P1: `omit.*entirely|do not emit|omit.*and do not`
  - P2: `Only .* satisfies|does NOT (count|satisfy)` in the same 5-line window (path-guard scope)
  - P3: consecutive `^\s*[-*]? ?Do not ` lines (≥2) or `Do not [^.]+\. Do not [^.]+\.` within a sentence
  - P4: natural-language conditional blocks of ≥10 lines without explicit control-structure syntax; judgment-only
  - P5: `\bdo not (omit|reorder|paraphrase|alter)\b`
  - P6: `[Ss]elect .* from the following|from this menu|such as `.*:\s*$` in a section header followed by bullets
  - P7: `\b[Cc]onsider\b|\btry to\b|\bif possible\b`

- **Preservation ring-fence**:
  - 7 categories (security/injection, output-channel directives, control-flow gates, output-floor field names, quoted source material, code fences, protected section headers).
  - 10 anchored decisions (per ticket body lines 82–91 and research.md §Codebase Analysis): `critical-review/SKILL.md` "Do not soften or editorialize" and distinct-angle rule; `research/SKILL.md` empty-agent and contradiction handling; `diagnose/SKILL.md` root-cause-before-fixes and competing-hypotheses gate; `lifecycle/SKILL.md` epic-research announcement and prerequisite-missing warn; `backlog/SKILL.md` AskUserQuestion directives; `discovery/SKILL.md` "summarize findings, and proceed".
  - Cross-check by file-scoped `grep -F` (R10), not line number or repo-wide search.

- **Symlink architecture blast radius**: `claude/reference/*` → `~/.claude/reference/*`; `claude/Agents.md` → `~/.claude/CLAUDE.md`. Edits propagate globally to all local projects immediately on commit. PR review (Requirement 6) is pre-merge adversarial self-review; `git revert` is the rollback for any mistake regardless of merge path.

- **#088 measurement-window freeze**: #088's spec §5 holds `skills/`, `claude/reference/`, `claude/Agents.md`, `CLAUDE.md` frozen until the baseline snapshot lands. #85's implement phase gates on Requirement 9 to respect this freeze. Open-but-unmerged PR branches that modify these paths count as "edits" per #088's freeze definition — #85 does not open PRs on the two high-blast-radius paths until #088's baseline lands.

- **Git commits via `/commit` skill only**: per `claude/Agents.md` "Git Commits: Always Use the `/commit` Skill" — no raw `git commit` invocations.

- **Commit-artifacts enabled** (per `lifecycle.config.md`): `lifecycle/{slug}/*` artifacts are staged and committed by `/commit` at phase transitions. `lifecycle/` is not in the #088 freeze path list, so these commits are safe during the measurement window.

- **Forward-only phase transitions**: research → specify → plan → implement → review → complete. No reverse transitions.

- **Test command**: `just test` (per `lifecycle.config.md`). Requirement 12's new test must pass under this command.

- **No GitHub Actions CI** in this repo: PR gate (Requirement 6) is human-review only, not CI-enforced. Single-developer repo; the reviewer is the ticket author acting as adversarial self-reviewer on the PR's Files tab.

- **Realistic remediation surface**: research-corrected grep baseline is ~124 `do not` sites, ~9 `consider` sites, ~3 P5 sites across the 12 surfaces before exclusion. Post-exclusion remediation surface is expected in the 20–40 site range after per-R11 SKIP decisions (P5 sites, preservation ring-fence). This range is a soft estimate — the true count emerges during Pass 1 execution and is recorded in `candidates.md`. Plan does not tune it; Plan plans around the soft estimate with per-bucket collapse-to-zero expected.

- **Precedent divergence from #053**: #053 executed direct-to-main for all remediation commits. #85 diverges only for the two high-blast-radius paths (`claude/reference/*.md`, `claude/Agents.md`) via the PR gate; other paths follow #053's precedent. Rationale is in Changes to Existing Behavior (PROCESS CHANGE entry).

## Open Decisions

(None. All scope decisions resolved at Research Exit Gate and during Spec critical review. Pattern signatures, per-pattern mechanism defaults, child-ticket scope, staleness bound, and baseline-cleanliness guard are specified. Plan does not need to re-litigate any of these.)
