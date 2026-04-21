# Research: orchestrator-worktree-escape

> Investigate the class of overnight-runner bugs where operations meant for the per-session worktree/integration branch execute against the home repo and `main` instead — OR where writes to gitignored paths silently no-op. Surfaced acutely by session `overnight-2026-04-21-1708` but spans a deeper systemic gap: the invariant *"operations land where they're supposed to"* has been accidentally honored by the orchestrator's stochastic behavior while the shell and Python layers have been quietly broken for the full history of this machine's overnight work.

## Research Questions

1. **How deep is the path-injection pattern?** → **Narrow but mis-framed.** Only one bug surface in `orchestrator-round.md:258-285` where per-feature tokens (`{slug}`, `{spec_path}`, per-feature `{plan_path}`) are expected to be substituted by the orchestrator agent from `state.features[slug]` at runtime. The mechanism is *lexical priming* — the prompt repeatedly shows `Path("{session_dir}")`, `Path("{state_path}")` etc. as absolute-path Python literals, and the per-feature tokens use the identical syntax with no disambiguation. See DR-1 for the targeted fix.

2. **Where did the `{plan_path}` token overload originate?** → **Initial commit `428e54e` (2026-04-01).** Not introduced by backlog 048. PR #2 (`a628a95`) merged on 2026-04-11 only added `PLAN_GEN_DISPATCHED` instrumentation; the overload predates it.

3. **Is morning-report push regression or always-broken? Why?** → **Always broken since initial commit. Mechanism is NOT what the initial facts section suggested.** The failure is not a push-target cwd bug. It is:
   - `.gitignore:41` contains `lifecycle/sessions/` ("Overnight session archives") — ALL per-session artifacts are gitignored.
   - `runner.sh:1223-1225` uses `git add "lifecycle/sessions/${SESSION_ID}/morning-report.md"` — without `-f`, which silently skips ignored files.
   - `git diff --cached --quiet` returns true (nothing staged) and the `|| git commit` branch is never taken.
   - **The morning-report "commit" at runner.sh:1220-1226 is a silent no-op.** No commit ever lands anywhere. Morning reports remain only as untracked working-tree files in `$REPO_ROOT`.
   - `docs/overnight-operations.md:413` claim *"The morning-report commit is the only runner commit that stays on local main"* is aspirational — the commit never actually happens.
   - `sync-allowlist.conf:36` lists `lifecycle/sessions/*/morning-report.md` for `--theirs` conflict resolution, but since the files are never tracked, they cannot conflict. That allowlist entry is dead code.
   - 4 sessions lost their morning reports: `overnight-2026-04-01-2112`, `overnight-2026-04-07-0008`, `overnight-2026-04-11-1443`, `overnight-2026-04-21-1708`. **That is every overnight session in this machine's history — the population, not a sample.** Files exist locally at `lifecycle/sessions/<id>/morning-report.md` but have never entered git history on any branch. They are tombstones on one machine's filesystem. Any machine wipe, repo reclone, or `/tmp` cleanup deletes the historical record.

4. **Operational blast radius of current session state?** → **See §Current Session State.**

5. **What enforcement mechanisms prevent recurrence?** → **Primary: a single `pre-commit` hook in `$REPO_ROOT/.git/hooks/pre-commit` that rejects commits to `main` while `LIFECYCLE_SESSION_ID` is set. Git worktrees share `.git/hooks/` with the main repo via gitdir indirection (`$WORKTREE/.git` resolves to `$REPO_ROOT/.git/worktrees/<name>/`), so a single hook fires for both. Supplementary: Option C postflight plan-visibility check (narrow detection of plan-ENOENT-class bugs). See DR-3.**

6. **PR creation gating?** → **Unconditional at `runner.sh:1149`. `MC_MERGED_COUNT` computed at lines 1134-1142 is used only in PR body, not as a gate. Recommend creating PR as `--draft` on `MC_MERGED_COUNT == 0`. See DR-2. But note: this bug is *not* a worktree-escape bug — it is an unrelated gating defect.**

7. **One epic or two?** → **Two epics.** See DR-1 for the scope split.

8. **Fact-section errors flagged?** → **Five.** Three from the original user facts, two discovered during critical review. See §Fact-Section Corrections.

## Codebase Analysis

### The substitution contract (RQ1, RQ2) — mechanism is lexical priming

The `orchestrator-round.md` prompt presents session-level path tokens repeatedly as absolute-path Python literals before the per-feature dispatch block:

- Line 14: `` **Session plan**: {plan_path} `` — absolute path
- Lines 128-133: `state_path = Path("{state_path}")` — Python literal
- Line 185: `strategy_path = Path("{session_dir}") / "overnight-strategy.json"`
- Line 244: `missing = [f for f in features_to_run if not Path(f["plan_path"]).exists()]` — note: this reads per-feature from state, correctly, but still echoes the `{token}` style
- Line 254: `log_path = Path("{events_path}")`
- Line 311: `output_path = Path("{session_dir}") / "batch-plan-round-{round_number}.md"`
- Line 321: `state_path = Path("{state_path}")`

Then at lines 258-285, the per-feature dispatch block uses identical `{token}` syntax:

```
- Spec: {spec_path}
- Recovery history: lifecycle/{slug}/learnings/recovery-log.md
- write a complete plan to {plan_path}
```

By the time the agent reaches line 258, its in-context prior is overwhelmingly "curly-braced tokens are absolute paths that belong inside `Path(...)`." The agent (a) replicates the absolute-path style (copying `/Users/.../cortex-command/lifecycle/{slug}/...` from the session examples) and (b) sometimes forgets to substitute `{slug}` at all — producing the hybrid failure seen in session 1708.

The `{plan_path}` name collision is the acute vector: line 14 (session-level, pre-filled by `fill_prompt` as absolute path) vs line 269 (per-feature, agent must substitute from state). Same token name, different semantics, no marker distinguishing them.

The HTML comment at `orchestrator-round.md:19-20` documents only `{session_dir}` — it is not a substitute for disambiguation of per-feature tokens.

### Substitution responsibility split

| Layer | Call site | Tokens |
|-------|-----------|--------|
| Session-level (shell) | `fill_prompt()` at `runner.sh:386-391` | `{state_path}`, `{plan_path}` (session), `{events_path}`, `{session_dir}`, `{round_number}`, `{tier}` |
| Per-feature (agent) | Orchestrator agent at runtime, reading `state.features[<slug>]` | `{slug}`, `{spec_path}`, per-feature `{plan_path}` in the subagent dispatch block |

Other prompts do per-feature substitution correctly via explicit `.replace()` at dispatch time: `repair-agent.md` via `conflict.py:290-298`, `batch-brain.md` via `brain.py:215`, `feature_executor.py:518-560` via `_render_template`. Only the orchestrator's self-substitution of per-feature tokens is ambiguously specified — and that ambiguity is what the targeted prompt edit resolves.

### Path classification

| File:Line | Token / Path | Classification | Notes |
|-----------|--------------|----------------|-------|
| `runner.sh:386-391` | `{state_path}`, `{events_path}`, `{session_dir}`, session `{plan_path}` | **Intentional** | Session artifacts at home repo per `state.py:28 _LIFECYCLE_ROOT` |
| `orchestrator-round.md:264` | `{spec_path}` (per-feature) | **Bug surface** | Lexical priming + name collision; see DR-1 |
| `orchestrator-round.md:265-266` | `{slug}` | **Bug surface** | No priming disambiguation |
| `orchestrator-round.md:269` | per-feature `{plan_path}` | **Bug surface + name collision** with line 14 session-level `{plan_path}` |
| `conflict.py:290-298` + `repair-agent.md` | `{spec_path}`, `{feature}` | **Correct** | `.replace()` at dispatch time |
| `brain.py:215` + `batch-brain.md` | `{feature}` | **Correct** | `_render_template()` |
| `feature_executor.py:518-560` | `{spec_path}` (absolute) | **Correct** | Per-task implementation prompts legitimately use absolute per-feature paths |

### Morning-report silent no-op (RQ3)

- `.gitignore:41`: `lifecycle/sessions/` — all per-session artifacts are gitignored
- `runner.sh:1220-1226`:
  ```
  (
      cd "$REPO_ROOT"
      git add "lifecycle/sessions/${SESSION_ID}/morning-report.md" 2>/dev/null || true
      git add "lifecycle/morning-report.md"                        2>/dev/null || true
      git diff --cached --quiet || git commit -m "..."
  )
  ```
- `git add` without `-f` silently skips ignored files. `lifecycle/morning-report.md` is not gitignored but is not produced by the runner (no writer exists). `git diff --cached --quiet` returns true. The commit never runs.
- Verified by direct inspection: `git log --all -- lifecycle/sessions/overnight-2026-04-11-1443/morning-report.md` returns zero commits. The file exists at 8327 bytes on disk; it is not in git history.
- Affects: every overnight session ever. 4 sessions exist; 4 sessions lost their report.
- Fix options: (a) `git add -f` to force-stage ignored files; (b) un-ignore `lifecycle/sessions/*/morning-report.md` specifically in `.gitignore`; (c) relocate morning-report.md to a non-ignored path. (b) or (c) are cleaner than (a) — `git add -f` has surprising behavior and couples the runner to the gitignore layout.

### PR creation unconditional (RQ6)

- `runner.sh:1149`: `gh pr create` fires whenever `INTEGRATION_BRANCH` is set.
- `MC_MERGED_COUNT` computed at lines 1134-1142, used only in PR body text.
- Session 1708 demonstrates: zero merges, PR #4 still created.
- **This is not a worktree-escape bug.** No home-vs-worktree confusion involved. It's an unrelated gating defect that surfaced in the same session.

### No worktree GC, no session-failure rollback

- Worktree creation: `runner.sh:582` via `git worktree add`. Cleanup at line 1329 only on natural loop exit. SIGINT/SIGTERM trap (lines 468-524) preserves worktree for `/overnight resume`.
- No sweeper for orphaned `/tmp/claude-*-overnight-worktrees-*/` dirs or `~/.claude/projects/-private-tmp-claude-*-overnight-worktrees-*/` subagent transcripts.
- `backlog.py:321,365` mutates `session_id` frontmatter on session start. No rollback path.

## Current Session State (RQ4)

### PR #4

- OPEN, MERGEABLE, CLEAN. Head `6cdb16d` on `overnight/overnight-2026-04-21-1708`.
- Integration branch is exactly **1 commit ahead** of main. Main is **6 commits ahead** of integration branch.
- Unique content of `6cdb16d`: adds `session_id: null` to backlog files 094/095/096 — 3 lines, 3 files. Not catastrophic if merged, but pollutes frontmatter with stale markers.

### Main's 17 unpushed commits

Legitimate pre-session work (lifecycle 085/087/088/089 landings, discoveries, refines, plans). Push at normal cadence.

### Plan commits at `0e1c4b6`

On main. Valid plans for 094/095/096 re-run.

### Followup items 101/102/103

Data loss is effectively **permanent** at 101/102/103:

- Overnight at 13:14: `create_followup_backlog_items()` at `report.py:272-360` wrote structured followup items (parse-error context, failure rationale) at IDs 101/102/103 via home-repo path.
- Runner's `git add` at `runner.sh:1002-1008` staged worktree files only; home-repo writes remained untracked.
- Later at 14:04: `/discovery` decompose ran (commit `8c5cff4`) and allocated IDs 101/102/103 to different content, overwriting the untracked overnight files.
- Morning report at `morning-report.md:96-98` captures only slug-like titles — not the structured body, discovery source, acceptance criteria, or failure rationale the runner wrote.
- Recovery produces **stubs**, not a reconstruction. See Recovery Step 3.

### Worktrees and transcripts

- `git worktree list` clean.
- `/tmp/claude-503/overnight-worktrees/overnight-2026-04-21-1708` empty.
- `~/.claude/projects/-private-tmp-claude-503-overnight-worktrees-overnight-2026-04-21-1708/` exists (~184KB). No sweeper.

## Feasibility Assessment

### Enforcement options (RQ5)

| Option | Effort | Catches | Misses | Verdict |
|--------|--------|---------|--------|---------|
| **E. Git `pre-commit` hook** | **S (1-2h)** | Session 1708's Bash `cd && git commit` escape; any commit to main during overnight; backlog frontmatter mutations on main; morning-report-on-main commits | Nothing in the currently-observed failure set — worktree shares hooks via gitdir indirection so the hook fires for commits in any worktree | **Recommend (primary)** |
| C. Postflight plan-visibility check at Step 3e | M (3-4h) | plan.md ENOENT-class failures; mis-substituted `{slug}` directory | Morning-report (not expected on worktree); followup persistence (runs after); correct plan + Bash-cd escape | Keep as supplementary detection for Step 3e |
| A. `{worktree_root}` token in `fill_prompt()` | M (2-3h) | Intent clarity in documentation | Runtime path construction; Claude Edit/Write ignore cwd | Defer; longer-term clarity play |
| D. PreToolUse Edit/Write path guard (hook) | S (1-2h) | Absolute-path Edit/Write during overnight | **Session 1708's actual escape (Bash `cd && git commit`)**; symlinks | **Reject** — does not catch the observed failure vector |
| B. Prompt linter | S (1-2h) | Accidental absolute-path hardcodes in new prompts | High false-positive rate against documentation text | Reject as primary |

**Why Option E dominates C+D**: Git worktrees share `.git/hooks/` via `$WORKTREE/.git` → `$REPO_ROOT/.git/worktrees/<name>/` gitdir redirection, so a `pre-commit` hook at `$REPO_ROOT/.git/hooks/pre-commit` fires for commits from ANY worktree. A ~20-line shell script reading `$LIFECYCLE_SESSION_ID` + `git symbolic-ref HEAD` rejects commits to `main` during an overnight session. This catches the exact escape vector of session 1708 (which D does not), plus morning-report commits if they existed, plus backlog frontmatter mutations on main — a single mechanism, smaller effort than C+D combined, directly enforces the invariant. The options table in an earlier draft omitted this entirely; that was a completeness defect.

### Repair tickets

| Ticket | Epic | Effort | Criticality | Rationale |
|--------|------|--------|-------------|-----------|
| **Targeted prompt disambiguation** — rename `{plan_path}` → `{session_plan_path}` (session) / `{feature_plan_path}` (per-feature) in `orchestrator-round.md`, update `fill_prompt()` in `runner.sh:386-391`, add explicit "YOU substitute `{slug}`, `{spec_path}`, `{feature_plan_path}` from `state.features[<slug>]`" block before line 258 | Worktree-escape | **S (~30min)** | **Critical** | Addresses the lexical-priming + name-collision mechanism directly; cheapest high-leverage fix |
| **Install git `pre-commit` hook** (Option E above) — reject commits to `main` while `LIFECYCLE_SESSION_ID` is set | Worktree-escape | S (1-2h) | **Critical** | Enforces the invariant across all future Bash-based escapes |
| **Morning-report commit un-silence** — either (b) un-ignore `lifecycle/sessions/*/morning-report.md` in `.gitignore` or (c) relocate to non-ignored path; update `runner.sh:1220-1226` if path changes | Worktree-escape | S (1h) | **Critical** | 100% of overnight history has lost its morning report; 1-line fix once the storage decision is made |
| **Followup-item persistence fix** — `report.py:272-360` must commit via worktree path so `git add` at `runner.sh:1002-1008` picks them up | Worktree-escape | S (1-2h) | High | Prevents silent clobber by concurrent backlog allocations |
| **Backlog frontmatter rollback on session failure** — revert `session_id` mutations written by `backlog.py:321,365` when a session transitions to `failed` | Worktree-escape | S | Medium | Unzombies failed features |
| **PR-creation gating** — gate `gh pr create` at `runner.sh:1149` on `MC_MERGED_COUNT > 0`, or create as `--draft` on zero-merge | **Separate ticket (not in epic)** | S (30min) | Medium | No worktree confusion involved; unrelated defect that surfaced in the same session |
| **Orphaned-worktree + subagent-transcript GC** | Hygiene (own ticket, not in epic) | S | Low | Hygiene; accumulates linearly |
| **Retroactive morning-report publication** | **Own ticket (not in epic)** | S (1-2h) | Medium | 20 days of archival record should be reconstructed; depends on morning-report-un-silence fix landing first |
| **`{worktree_root}` token + prompt sweep** | Clarity play (own ticket, not in epic) | M | Low | Longer-term clarity; orthogonal to the failure-mode fixes |
| **Instrumentation of substitution step** | Observability (own ticket, not in epic) | S | Low | Logs substituted tokens for post-hoc analysis; bundle with other instrumentation work |

## Decision Records

### DR-1: Two epics — worktree-escape (scoped) and PR-gating (separate)

- **Context**: Whether to bundle all failure modes surfaced by session 1708 under one epic, or split.

- **Options considered**:
  - **α (one epic, as originally proposed)**: Single epic "Eliminate home-repo-vs-worktree context drift" covering substitution-contract, morning-report, followup-persistence, frontmatter-rollback, PR-gating, worktree GC, retroactive recovery.
  - **β (two epics + standalone tickets)**: Epic 1 "Worktree-escape and home-repo-vs-worktree drift" covering the 5 fixes with genuine worktree-confusion mechanisms. Standalone ticket: PR-gating (no worktree confusion). Standalone tickets: orphaned-worktree GC, retroactive morning-report publication, `{worktree_root}` sweep, instrumentation.

- **Recommendation**: **β.**

- **Reasoning**: PR-gating does not share the worktree-confusion invariant — `MC_MERGED_COUNT` is computed and ignored; the PR would have been created identically if every worktree bug were fixed. Lumping it in is a category error that inflates the epic's apparent coherence. GC, retroactive recovery, `{worktree_root}` sweep, and instrumentation are adjacent-but-independent work — bundling them gates urgent fixes (morning-report un-silence, prompt disambiguation) on slower work. Critical + High tickets should land independently as they're completed, not be gated atomically on Low-priority hygiene. The "partial-invariant state" concern from the earlier draft is inverted: landing the 1-hour morning-report fix tomorrow recovers reports for all future sessions, regardless of when the substitution-contract fix lands.

- **Trade-offs**: Two+ smaller epics means two+ review surfaces. Acceptable given the alternative is an 8-10 ticket super-epic across three layers that no single reviewer has strong context across. Narrower epic scopes also make each epic's Definition of Done explicit.

### DR-2: Gate PR creation on `merged > 0` as `--draft`

- **Context**: Should zero-merge overnight sessions create PRs, and in what state?

- **Options considered**: Skip entirely; `--draft` with explicit title; closed-with-comment; `do-not-merge` label.

- **Recommendation**: **`--draft` with explicit title.**

- **Reasoning**: Skipping hides the failure from the morning-review workflow. `--draft` blocks auto-merge, appears in review queue, and title signals zero progress. Closed-with-comment is destructive. Label-only doesn't prevent accidental merge.

- **Trade-offs**: Draft PRs consume slots. Acceptable.

- **Note**: This ticket is NOT in the worktree-escape epic per DR-1.

### DR-3: Primary enforcement is git `pre-commit` hook (Option E); C supplementary; drop D

- **Context**: Which enforcement mechanism to implement against worktree-escape recurrence.

- **Options considered**: A (`{worktree_root}` token), B (prompt linter), C (postflight plan-visibility check), D (PreToolUse Edit/Write hook), **E (git `pre-commit` hook)**.

- **Recommendation**: **Primary E. Supplementary C (Step 3e plan-visibility check for early-failure detection). Drop D. Defer A. Reject B as primary enforcement.**

- **Reasoning**: E catches the exact failure vector of session 1708 (Bash `cd "$REPO_ROOT" && git commit`) — which D does not. E also catches future Bash-based escapes from any subagent, morning-report commits on main, and backlog frontmatter mutations on main. Single mechanism, ~20 lines of shell, ~1-2h effort. Git worktrees share hooks via gitdir indirection, so the hook fires for commits from any worktree. C remains useful as early-failure detection at orchestrator-round.md Step 3e but is a detector of symptoms, not an enforcement layer. D is correctly scoped in the options table (catches Edit/Write) but does not cover the observed escape vector — keeping it would pay cost without preventing the failure that motivated the epic.

- **Trade-offs**: Any existing tooling that commits to main while `$LIFECYCLE_SESSION_ID` happens to be set (e.g., interactive sessions where the env var leaked in) would be blocked. Mitigation: set `LIFECYCLE_SESSION_ID` only when the runner spawns agents; ensure it unsets on session end; document for operators.

## Fact-Section Corrections (RQ8)

Five corrections to claims made in the original facts section or in the earlier draft of this research:

1. **"items exist nowhere on disk now — ls backlog/ ends at 100"** (user's facts) — **Incorrect.** Files exist at `backlog/101-*.md`, `102-*.md`, `103-*.md`, but their content was overwritten by a later `/discovery` decompose at commit `8c5cff4` (2026-04-21 14:04). The data loss is real but subtler: the IDs were reused; the overnight's structured followup content is permanently gone.

2. **"`pipeline/trim-and-instrument-overnight-plan-gen-prompt` is an open feature branch"** (user's facts) — **Misleading.** Branch exists locally but backlog 048 is complete and merged to main via PR #2 (`a628a95`) on 2026-04-11.

3. **Implicit in Q6: that backlog 048 "might have introduced the `{plan_path}` overload"** (user's facts) — **Incorrect.** Tokens existed in initial commit `428e54e` (2026-04-01). Backlog 048's prompt-touching commit `4a3dfcd` added only `log_event(PLAN_GEN_DISPATCHED)` instrumentation around Step 3b.

4. **"Morning-report commit lands on local main but runner never pushes main"** (earlier draft of this research) — **Incorrect mechanism.** The commit never lands anywhere. `lifecycle/sessions/` is gitignored at `.gitignore:41`; `runner.sh:1223-1225` uses `git add` without `-f`; ignored files are silently skipped; `git diff --cached --quiet` returns true; commit step is never taken. The correct framing is a silent no-op induced by gitignore, not a push-target bug.

5. **"The 3 lost reports ... exist locally ... cheap and worth considering" for retroactive recovery** (earlier draft) — **Undersized.** Bug present since initial commit 2026-04-01; today 2026-04-21. 4 sessions exist; 4 lost reports. That is the population, not a 3-week sample. Every overnight session in this machine's history has failed to commit its morning report. The retroactive recovery is an audit-trail restoration for the full operational history, not a cleanup side-quest — it gets its own ticket outside the forward-path epic.

## Current Session State Recovery Recommendation

Ordered, conservative, minimum-risk sequence. Starts with a verification step — the earlier draft asked the operator to trust research claims without a pre-flight; this is corrected.

0. **Dry-run diff verification** (confirms PR #4's contents match this research before closing):
   ```
   gh pr diff 4
   git log main..origin/overnight/overnight-2026-04-21-1708 --stat
   ```
   Expected: one commit `6cdb16d` adding 3 lines (`session_id: null`) to 3 files. If the output differs, stop and re-investigate.

1. **Close PR #4 without merging**:
   ```
   gh pr close 4 --comment "Closing: overnight session 1708 failed at feature_start on all 3 features; no merged content. Session state cleanup deferred to epic work (see research/orchestrator-worktree-escape/)."
   ```

2. **Delete the integration branch on origin**:
   ```
   git push origin --delete overnight/overnight-2026-04-21-1708
   ```

3. **Create 3 follow-up backlog stubs** (NOT a reconstruction — source content is permanently lost):
   Use `/backlog add` or `create_item.py` to create new stubs at the next available IDs (122, 123, 124 or wherever). Each stub:
   - Title: "Follow up: retry <feature>" — mirror `morning-report.md:96-98` text
   - Body: "Overnight session 1708 failed at plan parse. Original followup content at IDs 101/102/103 was clobbered by commit `8c5cff4`. Treat as new work; `/refine` before execution."
   Each stub needs `/refine` before it's actionable. Do not treat these as equivalent to the lost items.

4. **Delete orphaned subagent-transcript directory**:
   ```
   rm -rf ~/.claude/projects/-private-tmp-claude-503-overnight-worktrees-overnight-2026-04-21-1708
   ```

5. **Leave main's 17 unpushed commits alone** — legitimate pre-session work. Push at normal cadence.

6. **No action needed** for plan commits at `0e1c4b6`, for backlog items 094/095/096 (working tree clean after session), or for `/tmp/claude-503/overnight-worktrees/overnight-2026-04-21-1708/` (empty).

## Open Questions

- **Storage decision for morning-report files**: un-ignore `lifecycle/sessions/*/morning-report.md` specifically (adds scope to `.gitignore`), or relocate the file out from under the `lifecycle/sessions/` gitignore rule. Either works; the decompose phase should pick one — the choice affects the retroactive-publication ticket's implementation.
- **`{worktree_root}` token inclusion**: make it a standalone clarity ticket as recommended, or absorb into the substitution-contract fix? The targeted disambiguation edit doesn't need it, but a sweep would be cleaner if done together. Deferred to operator preference.
- **Instrumentation inclusion**: logging which tokens were substituted with what values in `orchestrator-round.md` would catch near-miss variance post-fix. Standalone ticket or absorbed into substitution-contract fix? Standalone is preferred for reviewer focus.
