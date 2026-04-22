# Research: Gate overnight PR creation on merged>0 (draft on zero-merge)

> Modify `claude/overnight/runner.sh` so the home-repo integration-branch PR creation at line 1149 branches on `MC_MERGED_COUNT`: when zero, create the PR as `--draft` with a zero-progress title/body; when non-zero, retain existing non-draft behavior.

## Epic Reference

This ticket is a **sibling**, not a child, of the `orchestrator-worktree-escape` epic (see [`research/orchestrator-worktree-escape/research.md`](../../research/orchestrator-worktree-escape/research.md), DR-1 and DR-2). The worktree-escape epic (parent #126, children 127–130) fixes home-vs-worktree invariant violations. Ticket 131 is a distinct gating defect — `MC_MERGED_COUNT` is computed and ignored — that surfaced in the same failed session (`overnight-2026-04-21-1708`, PR #4) by coincidence, not shared mechanism.

## Codebase Analysis

### Both `gh pr create` call sites — structural comparison

| Aspect | Cross-repo (`runner.sh:1020-1115`) | Home-repo (`runner.sh:1117-1177`) |
|---|---|---|
| Count variable | `MERGED_COUNT` (per-repo, lines 1043-1053) | `MC_MERGED_COUNT` (home-repo, lines 1134-1142) |
| Count computation | Filters by `repo_path == REPO_PATH` and `status == 'merged'` | Filters by `repo_path is None` and `status == 'merged'` |
| Zero-merge gating | **Line 1055**: `[[ "$MERGED_COUNT" -eq 0 ]]` → `continue` (skip+log) | **None** — unconditional PR creation at line 1149 |
| Body generation | Single-line body (line 1079) | Conditional on `INTEGRATION_DEGRADED` (lines 1143-1148): if degraded, prepend `INTEGRATION_WARNING_FILE` content; else single-line |
| `gh pr create` invocation | Lines 1083-1089 (with `--repo "$REPO_REMOTE"`; stderr → `PR_ERR_FILE`) | Lines 1149-1154 (no `--repo`; stderr → `/dev/null`) |
| Error recovery | Lines 1092-1104 — try `gh pr view --repo ... --head`; on failure warn + notify | Lines 1156-1163 — try `gh pr view --head`; on failure warn only (no notify) |
| URL persistence | Lines 1107-1114 (JSON keyed by `repo_path`) | Lines 1168-1175 (JSON keyed by `HOME_PROJECT_ROOT`) |

Structural asymmetry is **partially deliberate**: cross-repo targets are opt-in per-feature (`state.features[*].repo_path` is set only when a feature explicitly targets a non-home repo); home-repo is always-a-participant (integration branch is always created, artifact commits always land, morning-review always expects it). Skip is correct for opt-in participants; a weaker fit for always-participants.

### `MC_MERGED_COUNT` computation

```bash
# runner.sh:1134-1142
MC_MERGED_COUNT=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
count = sum(
    1 for fs in state.get('features', {}).values()
    if fs.get('status') == 'merged' and fs.get('repo_path') is None
)
print(count)
")
```

Counts home-repo features with `status == 'merged'`. Filter is correct: cross-repo features carry explicit `repo_path`; home-repo features have `repo_path = None` per `state.py:130,139`. The value is only unreliable if state is drift-corrupted (mid-flight crashes that leave features in `in_progress`). Not a code bug.

### Existing `--draft` usage in repo

Zero production callers. Three references across the entire repo:

- `backlog/131-*.md:39` — the ticket itself
- `research/orchestrator-worktree-escape/research.md:24` — DR-2 recommendation
- `skills/pr/SKILL.md:88` — **explicitly avoids** `--draft` by default ("No `--draft`, `--reviewer`, `--assignee`, or `--label` flags unless the user explicitly requests them")

The `/pr` skill's prohibition is a convention for user-invoked PRs; it does not speak to autonomous overnight artifacts. No existing runtime pattern to follow.

### Implementation pattern for the branch-point

The change site is lines 1134-1154. A reasonable edit:

```bash
# After MC_MERGED_COUNT is computed (after line 1142):
DRAFT_FLAG=""
if [[ "$MC_MERGED_COUNT" -eq 0 ]]; then
    DRAFT_FLAG="--draft"
    PR_TITLE="[ZERO PROGRESS] Overnight session: $INTEGRATION_BRANCH"
    # Zero-progress body — still reference morning-report for any later un-silence
    echo "**ZERO PROGRESS** — Overnight session $SESSION_ID merged 0 features. See \`lifecycle/sessions/${SESSION_ID}/morning-report.md\` for failure analysis." > "$PR_BODY_FILE"
else
    PR_TITLE="Overnight session: $INTEGRATION_BRANCH"
    # Existing multi-part body logic (lines 1143-1148):
    if [[ "$INTEGRATION_DEGRADED" == "true" ]] && [[ -f "$INTEGRATION_WARNING_FILE" ]]; then
        cat "$INTEGRATION_WARNING_FILE" > "$PR_BODY_FILE"
        echo "Overnight session $SESSION_ID: $MC_MERGED_COUNT features merged. See morning-report.md for details." >> "$PR_BODY_FILE"
    else
        echo "Overnight session $SESSION_ID: $MC_MERGED_COUNT features merged. See morning-report.md for details." > "$PR_BODY_FILE"
    fi
fi

MC_PR_URL=$(gh pr create \
    --title "$PR_TITLE" \
    $DRAFT_FLAG \
    --base main \
    --head "$INTEGRATION_BRANCH" \
    --body-file "$PR_BODY_FILE" \
    2>/dev/null)
```

`$DRAFT_FLAG` expansion is consistent with existing bash idiom in the script. Title becomes a variable instead of an inline string.

### Tests and dry-run scaffolding

**None exist.** Searches for runner.sh PR-block tests turned up:

- `tests/test_runner_resume.py` — tests the `count_pending()` snippet; structural assertion only
- `tests/test_runner_signal.py` — signal handling (SIGTERM, SIGINT)
- `tests/test_report.py` — morning-report rendering; has `pr_urls` fixtures but doesn't exercise PR creation
- No `tests/overnight/`, `tests/pipeline/`, or `tests/integration/` contains a mock of `gh pr create`

New verification must be scaffolded. Options surveyed below in Open Questions.

### Downstream consumers are agnostic to draft state

- `claude/overnight/report.py` morning-report rendering (lines ~575-590, ~1476-1488): reads `pr_urls` dict, appends PR URLs to feature-group sections and the notification body. Does not inspect draft state.
- `notify.sh`: prints URLs verbatim.
- `sync-allowlist.conf` + `bin/git-sync-rebase.sh`: operates on local/remote main divergence after a PR merges; unaffected by pre-merge draft state.
- `skills/morning-review/references/walkthrough.md` (lines ~489-530): **does not include `isDraft`** in its `gh pr list --head ... --json number,url,state,title` query and does not warn operators about drafts. This is a compatibility gap surfaced by adversarial review — see Open Questions.

### LIFECYCLE_SESSION_ID gating

The PR-creation block does not inspect `LIFECYCLE_SESSION_ID`. The pre-commit hook (worktree-escape epic) uses it to prevent main-branch commits during active sessions, but that is independent of PR creation. No interaction.

## Web Research

### `gh pr create --draft` semantics

- `--draft` marks the PR draft at creation. **Platform blocks merging entirely** until ready ([gh pr create manual](https://cli.github.com/manual/gh_pr_create), [Introducing draft pull requests](https://github.blog/news-insights/product-news/introducing-draft-pull-requests/)).
- Draft PRs refuse `gh pr merge --auto` and GitHub merge queue ([cli/cli discussion #3660](https://github.com/cli/cli/discussions/3660), [Merging a PR with a merge queue](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/merging-a-pull-request-with-a-merge-queue)).
- Drafts suppress CODEOWNERS notifications until marked ready.
- Status-check behavior is workflow-author's choice (CI may gate on `github.event.pull_request.draft == false`). This repo has `.github/workflows/` **empty** — no CI gating concern here.
- Available on all repos as of May 2025 ([changelog](https://github.blog/changelog/2025-05-01-draft-pull-requests-are-now-available-in-all-repositories/)).

### Draft ↔ ready transitions

- `gh pr ready [<pr>]` flips draft → ready.
- `gh pr ready --undo` flips ready → draft.
- No functional difference between born-draft and converted-to-draft; only externally visible timing of CODEOWNERS notifications.

### Convention patterns for failure-only PRs

| Pattern | Enforcement | Notes |
|---|---|---|
| Title prefix (`[WIP]`, `[DO NOT MERGE]`) | Cosmetic only | Pure convention; platform doesn't respect |
| `do-not-merge` label + Action + branch protection | Hard (if configured) | Requires repo-side infrastructure this repo doesn't have |
| `gh pr create --draft` | Platform-level | Self-enforcing; no action/rule needed |

Agentic workflows (VS Code Copilot cloud agent, githubnext/agentics) default to `draft: true` for AI-authored PRs — established convention.

### `gh pr create` failure modes

- **"PR already exists"** — non-zero exit; existing runner.sh recovery at lines 1094, 1157 handles via `gh pr view`.
- **"No commits between base and head"** — non-zero exit ([cli/cli #2691](https://github.com/cli/cli/issues/2691)). Relevant for zero-progress sessions where the integration branch is identical to main (see Adversarial Review).
- No `--idempotent` / `--upsert` flag exists.

## Requirements & Constraints

### `requirements/pipeline.md`

- Lines 22-23: "Integration branches (`overnight/{session_id}`) persist after session completion and are not auto-deleted — they are left for PR creation to main"
- Line 24: "The morning report commit is the only runner commit that stays on local `main` (needed before PR merge for morning review to read)"
- No requirement specifies PR draft state, title content, or auto-merge gating.

### `requirements/project.md`

- Failure-handling philosophy: "Surface all failures in the morning report. Keep working on other tasks. Stop only if the failure blocks all remaining work in the session."

### `docs/overnight-operations.md`

- Circuit breaker distinguishes "zero-progress breaker" (0 merges in 2 rounds) as a first-class stop condition — the codebase already recognizes zero-progress as a distinctive failure mode.
- Line 192: "a warning block containing the first 20 lines of the failing test output is prepended to the PR body so a human reviewer sees it before merging" — establishes the pattern that the PR body is a human-facing pre-merge surface.

### `skills/morning-review/references/walkthrough.md`

- Lines ~489-530: `gh pr list --head ... --json number,url,state,title` — **does not query `isDraft`**. Draft/non-draft is invisible to morning-review today.
- Line ~589 edge case: `gh pr merge` failure → "Show error, leave PR open for manual resolution." If a draft PR is merge-attempted, this path catches the failure but does not explain the cause to the operator.

### Architectural constraints

1. Integration branches always persist after session completion; they are the load-bearing handoff artifact.
2. The home-repo integration branch is always created per session; it is not optional or conditional.
3. Circuit-breaker semantics treat zero-progress as a distinctive session outcome worth surfacing.

### Silence / absence of guidance

Requirements are silent on:

- Draft-PR handling in `/morning-review`
- Exact zero-progress title format
- `INTEGRATION_DEGRADED` × `MC_MERGED_COUNT == 0` interaction
- Idempotency on resume (draft-state flips if merge count changes between runs)
- Cleanup policy for stale zero-progress drafts

These are spec-phase decisions.

## Tradeoffs & Alternatives

### Alternatives evaluated

| # | Alternative | One-line verdict |
|---|---|---|
| A | **Draft with explicit title** (ticket proposal) | **Recommended**; preserves home-repo always-participant semantics |
| B | Skip PR creation (mirror cross-repo) | Loses visible trace on main's view while morning-report un-silence ticket is outstanding |
| C | Create-then-close with comment | Two-call failure mode; overloads "closed" semantics |
| D | `do-not-merge` label | Requires repo-side Action + branch protection this repo lacks |
| E | Unified with cross-repo (skip both) | Collapses justified asymmetry |
| F | Unified inverse (draft both) | Spams draft PRs to repos that didn't participate in the session |
| G | Status quo + morning-report filter only | Leaves zombie-PR root cause unaddressed |

### Why Alternative A

1. **Home-repo / cross-repo asymmetry is semantically justified.** Home-repo integration branch is always a session participant (always created, always receives artifact commits, always the morning-review entry point). Cross-repo targets are opt-in per-feature — a repo with zero merges truly didn't participate. Skip works for opt-in; draft works for always-participant.

2. **Draft is self-enforcing at the platform level.** No Action, branch-protection rule, or label-enforcement machinery required. GitHub itself refuses the merge button.

3. **The morning-report commit is partially a no-op today.** `.gitignore:45` ignores only `lifecycle/sessions/` — other artifacts (research.md, spec.md, plan.md, backlog/, pipeline-events.log) are not gitignored and do commit to the integration branch. But the morning-report file itself (the single operator-readable summary) is silently skipped by `git add` without `-f` until ticket 129 un-silences it. The PR is the only *summary* artifact main-visible until 129 lands.

4. **Agentic-workflow convention.** VS Code Copilot cloud agents and the agentics framework both default to `draft: true` for AI-authored PRs. This is the converging industry pattern.

### Recommendation tightening

- **Title**: `[ZERO PROGRESS] Overnight session: $INTEGRATION_BRANCH` (bracket prefix survives word-wrap in list views; reads left-to-right as status-then-subject).
- **Body**: `**ZERO PROGRESS** — Overnight session $SESSION_ID merged 0 features. See \`lifecycle/sessions/${SESSION_ID}/morning-report.md\` for failure analysis.` (explicit pointer; works whether morning-report commit is un-silenced or not, since the file exists on disk either way).
- **Implementation style**: `DRAFT_FLAG` variable expansion (bash idiom already present in the script); explicit `PR_TITLE` variable instead of inline string.

## Adversarial Review

### Material edge cases

1. **Zero-commit integration branch silently degrades draft-with-title to skip.** If a session fails so early that no artifact commits land on the integration branch (all features fail at `feature_start` with no refine/research/spec/plan regeneration, no backlog frontmatter mutation), the branch is identical to main. `gh pr create --draft` fails with "No commits between base and head" ([cli/cli #2691](https://github.com/cli/cli/issues/2691)). Recovery at line 1157 runs `gh pr view --head`, returns empty, emits the warning at 1159. **Net effect: in exactly the subset of zero-progress sessions where the PR matters most, draft-with-title is silently equivalent to skip.** Session 1708 produced a PR only because backlog frontmatter mutations (a side-effect bug) happened to commit to the branch.

2. **Resume-flow state drift.** Scenario: a session creates a draft PR (`MC_MERGED_COUNT == 0`), is interrupted, resumes later, completes more merges (`MC_MERGED_COUNT > 0`). Line 1149 retries `gh pr create` (no `--draft`), gets "already exists" error, recovery at line 1156-1163 finds the old **draft** PR and reports success with `echo "PR already exists for $INTEGRATION_BRANCH"`. The PR URL is correct but the PR remains draft. `/morning-review` will try to merge it, fail with "Pull request is not mergeable", and leave lifecycle state inconsistent. No state-flip exists in the runner.

3. **`INTEGRATION_DEGRADED == "true"` × `MC_MERGED_COUNT == 0` is undefined.** Title ambiguity: is the PR "zero progress" or "integration gate failed"? Both can hold simultaneously. Ticket acceptance criteria cover only the `MC_MERGED_COUNT` axis.

4. **`/morning-review` does not expose draft state to the operator.** `gh pr list --json` omits `isDraft`; the walkthrough (lines ~489-530) displays "State: OPEN" regardless. Step 4 asks "Merge this PR to main?" with no hint that a draft merge will fail. The downstream edge case at ~589 catches the error, but the UX is poor — the operator will have to diagnose what went wrong.

5. **Long-tail cleanup** — zero-progress drafts accumulate forever without a sweep/expiry policy. Over months, `gh pr list` fills with draft artifacts nobody ever closed.

### Assumption corrections

- **"PR is the only main-visible session artifact"** (Agent 4's linchpin argument) is overstated. `.gitignore:45` matches only `lifecycle/sessions/`. Research/spec/plan/backlog/pipeline-events.log files commit to the integration branch normally. The correct framing: **the PR is the only main-visible *summary* artifact**, and the integration-branch commits reach main only via PR merge. Conclusion unchanged (draft > skip), reasoning tightened.

- **Zero-progress drafts might never be reviewed.** Agent 4 cites `--draft` as "appears in the review queue" — true on GitHub web but `gh pr list` default filters and many operator workflows silently skip drafts. If ticket 129 (morning-report un-silence) lands and `/morning-review` starts treating the morning-report commit as the canonical surface, zero-progress drafts risk becoming invisible the same way morning-reports were.

### Security / supply-chain

**None material.** The PR is created unconditionally today; `--draft` changes only the mergeability flag, not the content on the wire. The `INTEGRATION_DEGRADED` branch uploads test stderr to the PR body (existing behavior), which may contain local absolute paths — unchanged by this ticket.

No workflow files exist in `.github/workflows/` for this repo, so no CI/bot currently keys off title prefixes. The `[ZERO PROGRESS]` convention is safe.

### Confidence in the recommendation

**Partially concur.** Draft-with-title is the right call, but the narrow ticket scope (flag at line 1149 only) leaves two real gaps that a follow-up will have to close:

1. The `/morning-review` walkthrough needs to expose draft state to the operator (or the operator will hit merge failures without warning).
2. The resume-flow recovery path needs to detect and correct draft-state mismatches on already-existing PRs.

If the ticket scope stays narrow, these gaps should be spec'd as explicit known-followup items rather than silently deferred.

## Open Questions

Each item below is **deferred: will be resolved in Spec by asking the user**. Stances are enumerated; spec interview will select.

- **Zero-commit integration branch handling.** When `git rev-list --count main..$INTEGRATION_BRANCH == 0`, `gh pr create` fails before `--draft` can matter. Stances: (a) accept degradation — a session that produced literally zero changes arguably deserves no PR; (b) add a pre-check that emits a distinct `notify.sh` message ("zero-progress session with no branch commits — no PR created") and skips the `gh pr create` call cleanly; (c) force a no-op commit on the integration branch to guarantee at least one commit exists (probably bad — adds noise for a narrow case). Deferred to spec.

- **Resume-flow state-flip.** When `MC_MERGED_COUNT` transitions across zero between invocations, should the runner flip PR draft state? Stances: (a) yes — add `gh pr ready` (zero→non-zero) or `gh pr ready --undo` (non-zero→zero) calls in the recovery path, keyed on an `isDraft` read from `gh pr view --json`; (b) no — accept that resume does not flip state, document that the first run's state is sticky, operator flips manually. Deferred to spec (likely (a), small cost).

- **`INTEGRATION_DEGRADED == "true"` × `MC_MERGED_COUNT == 0` title treatment.** Stances: (a) `[ZERO PROGRESS + GATE FAILED] Overnight session: <branch>`; (b) `[ZERO PROGRESS] Overnight session: <branch>` — drop the gate-failure signal from the title, leave it in the body; (c) make gate-failure the dominant marker since the session still executed features: `[GATE FAILED] Overnight session: <branch>`. Deferred to spec.

- **`/morning-review` walkthrough update.** Should this ticket bundle an edit to `skills/morning-review/references/walkthrough.md` that includes `isDraft` in `gh pr list --json` fields and warns operators on draft PRs? Stances: (a) yes — bundle the UX fix so it lands together (~10-20 lines of skill edit + 2-3 test updates); (b) no — file a follow-up ticket explicitly ("morning-review: surface PR draft state"), keep this ticket narrow, document the gap in both tickets. Deferred to spec. Recommend (b) — keeps ticket atomic.

- **Verification approach.** Ticket acceptance criterion says "integration test (or manual dry-run)". No test harness for `runner.sh` PR-creation exists. Stances: (a) shell unit test that sources an extracted function and asserts `DRAFT_FLAG` against a fixture state file; (b) `--dry-run` flag on `runner.sh` that emits the `gh pr create` invocation without executing, with a stdout contract a test can assert against; (c) accept "manual dry-run" as-is — one-time validation, no ongoing regression coverage. Deferred to spec. Recommend (b) — reusable, testable, minimal surface.

- **Long-tail cleanup policy for stale zero-progress drafts.** Should this ticket scope a sweep/expiry mechanism, or is it out of scope / deferred to a separate ticket? Deferred to spec to confirm intended scope.
