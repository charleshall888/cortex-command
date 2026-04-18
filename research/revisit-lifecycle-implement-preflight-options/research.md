# Research: revisit-lifecycle-implement-preflight-options

> Investigates whether `/lifecycle`'s implement-phase pre-flight options (defined in `skills/lifecycle/references/implement.md` §1) should be restructured based on lived-experience evidence since the options were designed in epic #074 (2026-04-13).

## Research Questions

1. **How has option 1 ("Implement in worktree" via `Agent(isolation: "worktree")`) actually performed?** → **Under-observed. 1 successful dispatch, 0 failed, in event-log history. Retro-documented failure modes (CWD drift, silent dispatch failures, events.log divergence) come from a negative-signal corpus that cannot be read as damning in isolation. Evidence supports demotion, not removal.**
2. **Does DR-2's "live-steerability" justification hold empirically?** → **Inconclusive.** Retros don't capture successful steering (they capture problems), and the skill is structurally prohibited from AskUserQuestion inside the worktree agent — so evidence of the benefit being used would not appear in the corpus under review. The benefit may or may not be real; we cannot tell from retros alone.
3. **What's the right output contract for option 2 (daytime pipeline) during and after the run?** → **A durable, structured result file (`lifecycle/{slug}/daytime-result.json`) written atomically via `write-to-.tmp + os.replace`, with a `session_id` or start-timestamp freshness token. Log-based sentinel classification is discarded in favor of reading structured state (`daytime-state.json`, `events.log`, and the new result file).** See DR-2.
4. **What caused lifecycle 69's orphan-branch failure, and is it a pipeline defect?** → **Two defects confirmed regardless of root cause. (a) Atomicity: `git worktree add -b` creates the branch before checkout; on checkout failure the branch orphans and `create_worktree()` doesn't clean it up. (b) Logging: `subprocess.run(capture_output=True, check=True)` swallows git's stderr, making the root cause invisible. Actual root cause is unknown — multiple plausible hypotheses listed in [DR-4](#dr-4-fix-daytime-pipeline-atomicity--logging-as-a-dedicated-ticket-not-bundled), to be diagnosed once the logging fix surfaces git stderr.**
5. **Is "Implement on current branch" safe enough to be the recommended default?** → **Yes, with minimal guards.** Required: uncommitted-changes check. Optional and deferred to spec: criticality-aware demotion (warn but allow on high/critical). Rejected: plan-complexity ("5 tasks") gate — task count is orthogonal to trunk damage.
6. **Are these concerns one ticket or several?** → **Five seams.** See [Decomposition Preview](#decomposition-preview). Ordering revised to avoid stranding users in a strictly-worse intermediate state.

## Epistemic Standard (applies uniformly across DRs)

Retros are a negative-signal corpus: the `/retro` skill captures problems, not successes. Event logs are undercounted by known instrumentation gaps (e.g., TC8 — option-1 inner-agent events live on the worktree branch until PR merge, so grep-by-mode systematically under-reports worktree dispatches). Both corpora tell us about **failures that happened**, not about **which features earn their place**.

For this reason, this research applies a single epistemic standard across all decision records: **retro silence alone cannot support a one-way-door decision** (neither removal of a feature nor flipping a default). Reversible decisions (demotion, opt-in guards, phased rollout) may be justified by retro patterns; irreversible ones require independent evidence (code-level vulnerability, user incident reports, or a clear architectural cost).

This is a correction from the first-draft version of the artifact, which applied strict-evidence reasoning against option 1 while extending lenient-evidence reasoning to option 3.

## Codebase Analysis

### Current pre-flight structure

`skills/lifecycle/references/implement.md` §1 presents four options via `AskUserQuestion` when current branch is `main`/`master`:

| # | Option | Dispatch mechanism | Recommended today |
|---|--------|-------------------|--------------------|
| 1 | Implement in worktree | `Agent(isolation: "worktree")` — single agent, sequential inline per-task dispatch | **Yes (current default)** |
| 2 | Implement in autonomous worktree | `python3 -m claude.overnight.daytime_pipeline` as background subprocess; reuses overnight machinery for per-task fresh context | No |
| 3 | Implement on main | Trunk-based; edits land on `main` directly | No |
| 4 | Create feature branch | `git checkout -b feature/{slug}`; PR-based | No |

The skill has a "Worktree-agent context guard" (`implement.md:18`) that excludes option 2 when the dispatcher is itself running inside `^worktree/agent-`.

### Option 1 (§1a Worktree Dispatch)

Pipeline: main session writes `.dispatching` marker → dispatches `Agent(isolation: "worktree", name: "agent-{slug}")` with a verbatim prompt (`implement.md:58-82`) → main blocks on Agent completion → surfaces agent's summary → removes marker → exits /lifecycle.

Internal constraints (documented in the verbatim prompt):
- Inner agent has NO `Agent` tool, NO `AskUserQuestion`, NO Task tools — physically constrained to sequential inline per-task dispatch in one conversation.
- Per-task sub-agents explicitly forbidden (`implement.md:68-74`) — each task runs in the inner agent's own context window.
- Context exhaustion is the designed-in ceiling (TC4 per epic #074).

Known limitations from the skill itself (`implement.md:102-106`):
- **AskUserQuestion sharp edge**: inner agent can technically call `AskUserQuestion` despite prompt prohibition; may surface to main session terminal.
- **Events.log divergence (TC8)**: main's events.log captures only `implementation_dispatch` and `dispatch_complete`; inner-agent events live on the worktree branch until PR merge. This is also the instrumentation defect that makes option-1 usage counting unreliable.

### Option 2 (§1b Daytime Dispatch)

Pipeline: main session verifies plan.md exists → runs double-dispatch guard + overnight-concurrent guard → launches `daytime_pipeline.py` as background subprocess → polls at 120s cadence → surfaces result.

Code path: `daytime_pipeline.py::run_daytime()` → `create_worktree()` (`claude/pipeline/worktree.py:65`) → `execute_feature()` → `apply_feature_result()` → `cleanup_worktree()`. Orphan guard (`_orphan_guard`) cleans up if parent dies (PPID=1); does **not** trigger on subprocess-own-SIGKILL.

Polling protocol (`implement.md:144-164`):
- Initial 10s sleep after launch
- Per iteration: liveness check via `kill -0 $pid`, then `tail -n 5 lifecycle/{feature}/events.log` surfaced to user, then `sleep 120`
- 30-iteration (~1h) pause prompt; 120-iteration (~4h) hard stop

Result surfacing (`implement.md:157-164`):
- Reads last `"Feature "` line in `daytime.log` (free-form text)
- First-match-wins classification by substring: `merged successfully` / `deferred` / `paused` / `failed`
- Success: surfaces regex-scraped PR URL from log chatter
- Failed: shows last 20 lines of `daytime.log`

Structured state already exists but is ignored by the classifier:
- `daytime-state.json` carries `features_merged/paused/deferred/failed` arrays with structured `error` fields.
- `events.log` carries phase transitions, batch completions, review verdicts.
- `bin/overnight-status` (in-repo prior art) already reads these structured sources to render status.

### Lived-failure evidence (from event logs + retros)

**Worktree-mode dispatches (option 1)** — only 1 found in `lifecycle/*/events.log` **matching the `mode: worktree` event schema**:
- `devils-advocate-smart-feedback-application` (2026-04-12): succeeded in 8 min, produced merged PR #3.

**Caveat on this count**: the `mode` field is recent; earlier worktree dispatches may not carry it. TC8 (events.log divergence) also under-reports option-1 usage because inner-agent events (including `feature_complete`) live on the worktree branch until PR merge — so a survey of main's events.log misses most of the dispatch history. The "1 successful dispatch" figure is a floor, not a denominator.

**Daytime-mode dispatches (option 2)** — 1 found:
- `suppress-internal-narration-in-lifecycle-specify-phase` (lifecycle 69, 2026-04-17): dispatch failed at startup on `git worktree add` (exit 128). The feature subsequently completed via an alternate path (batch dispatch after user intervention).

**Retro-documented worktree failure modes**:
- `retros/2026-04-12-2038-lifecycle-implement-worktree-dispatch.md` — post-research adversarial review surfaced 12 failure modes (session hijack, cleanup hook prefix mismatch, events.log divergence); described in the retro itself as "speculation-ahead-of-research." This is the one clearly-option-1-relevant retro in the corpus.
- `retros/2026-04-08-0756.md` — CWD drift + four commits landing on the wrong branch. **Predates epic #074 (2026-04-13)**; this is evidence about a *prior* worktree design, not about `§1a` dispatch. Incorrectly cited as option-1 evidence in the first-draft version of this artifact.

**Live-steering usage**: zero retros describe productive mid-run steering of a worktree agent. Under the epistemic standard above, this is silence and does not independently justify killing the feature. The architectural prohibition on inner-agent `AskUserQuestion` (`implement.md:62-66`) structurally prevents in-conversation steering anyway; the benefit was narrowly defined to "watch and interrupt," which is behaviorally distinct from "steer."

### Defects identified in daytime_pipeline

From `claude/pipeline/worktree.py:142-148`:

```python
subprocess.run(
    ["git", "worktree", "add", str(worktree_path), "-b", branch, base_branch],
    capture_output=True,
    text=True,
    check=True,        # swallows stderr into CalledProcessError
    cwd=str(repo),
)
```

**Defect 1 — atomicity**: `git worktree add -b` creates the branch before performing checkout. If checkout fails (for any reason), the branch persists as an orphan. `create_worktree` has no try/except to clean up. The SKILL.md Parallel Execution section documents this failure mode for *manual* `git worktree add` in sandboxed sessions; the daytime pipeline uses manual `git worktree add` via Python subprocess and inherits the same vulnerability — though note that the **sandbox context is different** (see DR-4 on why the SKILL.md citation doesn't transfer cleanly).

**Defect 2 — logging**: `check=True` + `capture_output=True` means `CalledProcessError.stderr` exists but is never logged to `daytime.log`. The user sees only `returned non-zero exit status 128` with no git error text. This is what made lifecycle 69's failure unreadable.

**Interaction with `_resolve_branch_name`**: the fallback logic at `worktree.py:51-62` tries `pipeline/{feature}-2`, `-3` when the base name is taken. On a fresh retry after an orphan is left behind, this *should* work automatically without manual cleanup. The orphan-cleanup prompt the user saw is therefore conservative — necessary only because `create_worktree` doesn't clean up after itself, but *not* strictly required for retry to succeed. **This observation is a clue about root cause** (see DR-4): if retries work without cleanup, the original failure was stateful-leftover-dependent, not an immutable environmental restriction.

### Existing safety patterns reusable for option 3

- **`skills/pr/SKILL.md`** — checks "No uncommitted changes in working tree" before proceeding; warns and stops.
- **`skills/overnight/SKILL.md`** — runs `git status --porcelain -- lifecycle/ backlog/` pre-flight; rejects launch if lifecycle/backlog paths have uncommitted state.
- **No plan-complexity or criticality gates** currently exist in lifecycle pre-flight.

### Trunk-safety incident evidence

Zero retros found describing accidental main-branch edits, trunk damage, or confusion about which branch was active in an option-3 context. Git log shows no revert-main or fix-accidental-commit patterns in recent 50 commits.

Under the epistemic standard at the top of this artifact: this is silence in a negative-signal corpus. It does not prove trunk-safety; it just means no incidents have been *retro-logged*. The reversible-decision standard applies — adding an uncommitted-changes guard (low cost, high precision) is reasonable; adding a plan-complexity guard (low cost, no precision — task count is orthogonal to trunk-damage risk) is not.

## Web & Documentation Research

Surveyed agent-run observability patterns for prior art informing option 2's output contract:

1. **Structured result artifacts, not log parsing** (GitHub Actions `$GITHUB_OUTPUT`, Buildkite `buildkite-agent artifact`, gh CLI `gh run view`): modern tools emit structured result artifacts that survive log rotation, truncation, and process kills. Log-tail classification is the pattern these frameworks explicitly replaced.
2. **Atomic result file writes** (write-to-tempfile + `os.replace`): canonical Python pattern for crash-safe state updates. The `daytime-state.json` in this repo already uses this pattern via `save_state()` (atomic tempfile + `os.replace`) — the same primitive can carry the result artifact.
3. **Freshness tokens in result artifacts** (session_id, start_ts): modern agent frameworks stamp results with identity tokens so consumers can distinguish "this run's result" from "a stale prior run's result." Prevents the main-session-crash-then-restart scenario where a prior sentinel is misread as current.
4. **Progress via canonical milestones, not raw logs** (Buildkite, OpenAI Agents SDK traces): `tail` of raw logs is noisy; emit canonical progress markers (`batch 2/5 started`, `task foo complete`) that the poller filters to.
5. **Structured end-summary with fixed fields** (gh CLI `gh run view`, `bin/overnight-status` in-repo): fixed sections — metadata, counts-table, failed-items-with-reasons, artifact-links. The in-repo `bin/overnight-status` is the closest shape to mirror, and critically it reads **structured state files**, not log lines.

Key insight: **substring classification of free-form log lines is a pattern anti-correlated with reliability in every modern agent framework**. The current option-2 result classifier (last `"Feature "` line → first-match wins) is exactly the kind of code these frameworks replaced.

## Domain & Prior Art

`bin/overnight-status` (already in-repo) is the closest analog — a dedicated CLI that renders session state as fixed-field sections, reading `overnight-state.json` and `events.log` directly. Option 2's output contract should follow the same pattern: a structured result file consumed from disk, rendered through a dedicated renderer, never parsed from free-form log tail.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A. Demote option 1 (not remove) | S | Minor prompt-text inconsistency during rollout | None |
| B. Fix daytime atomicity + logging defects | S | Low — defensive fix; surfacing stderr enables diagnosis | Review `test_worktree_*` in `tests/` |
| C. Add option 3 safety guard (uncommitted-changes only) | S | False-positive demotions if users routinely have unrelated dirty state | None |
| D. Option 2 output contract (structured result file, renderer, state-file-based classification) | M | Multiple design decisions; `bin/daytime-status` vs. inline renderer; atomic-write discipline | Decide CLI vs. inline, decide result-file schema |
| E. Flip default recommendation to option 3 | S | Regression risk if guard (C) is insufficient | Depends on A + C — land behind C |

Total: 4× S + 1× M. Can land incrementally.

## Decision Records

### DR-1: Demote option 1 (do not remove)

- **Context**: Option 1 shipped first (epic #074). Epic #074's DR-2 kept it co-existing with option 2 on "live-steerability" grounds while acknowledging TC4 (context exhaustion) was theoretical. Lived evidence in this research remains thin on both sides: 1 success observed, no explicit steering-usage evidence, and the measurement corpus (retros + events.log) undercounts successful usage by design. A one-way-door removal is not justified by this evidence.
- **Options considered**:
  - Keep as-is (recommended default): evidence base too thin to either confirm or deny worth.
  - **Demote (not recommended, still selectable)**: reduces default-recommendation exposure, preserves scaffolding (`§1a` verbatim prompt, `.dispatching` marker, cleanup hook coordination, sub-agent prohibitions), keeps the escape hatch if live-steering proves useful later.
  - Remove entirely: forfeits reversibility for a simplification whose value depends on option 1 being *permanently* unneeded, which this research has not established.
- **Recommendation**: **Demote.** Prompt text updates to describe option 1 honestly — "single-agent sequential dispatch; context exhaustion is the designed ceiling; pick this for small features where you want to watch the inner agent work." No removal of `§1a` logic. If future evidence shows option 1 is never picked across a meaningful sample, revisit removal in a follow-up ticket.
- **Trade-offs**: Carries `§1a` maintenance cost (verbatim prompt, state-write boundaries, TC8 divergence). Accepts that cost until the evidence base supports removal.
- **Decision-drift note**: Epic #074's DR-2 ("co-exist") is preserved by this decision; only the default recommendation changes.

### DR-2: Daytime pipeline output contract uses a structured result file, not a log sentinel

- **Context**: Current result-surfacing reads the last `"Feature "` line of `daytime.log` and classifies by substring. This fails under: SIGKILL/OOM (no final line emitted), stdout block-buffering on redirected pipes (line emitted in Python but never flushed to disk), log rotation mid-run (line lost), main-session crash + restart (prior run's line misread as current). The first-draft version of this artifact proposed a `DAYTIME_RESULT {json}` sentinel line emitted from the subprocess — but the sentinel suffers all the same failure modes as the current substring-match approach.
- **Options considered**:
  - Sentinel line emitted by subprocess, skill parses log tail — **rejected**: inherits current failure modes (buffering, SIGKILL, rotation, no freshness token).
  - **Structured result file** `lifecycle/{slug}/daytime-result.json`, written by subprocess via `write-to-.tmp + os.replace`, consumed by skill via `json.loads(Path(...).read_text())` — **recommended**: atomic (same primitive as `save_state()`), survives log rotation, carries freshness fields (`session_id`, `start_ts`, `outcome`, `pr_url`, task/commit counts, duration, deferred-file list).
  - Read `daytime-state.json` directly — **partially applies**: state already carries `features_merged/paused/deferred/failed`, but does not carry PR URL or rework cycle count. Extend `daytime-state.json` schema, or layer a separate `daytime-result.json` on top. This research recommends the separate result file to avoid coupling result-surfacing to the execution-state schema.
- **Recommendation**: **Structured result file with atomic writes + freshness token.** Skill reads `daytime-result.json` first; falls back to `daytime-state.json` if the result file is missing (e.g., subprocess SIGKILLed before writing); falls back to log tail as last resort (surfacing the same tail-20 the current implementation shows). This is a three-tier fallback, not a single point of failure.
- **Trade-offs**: Slightly more subprocess code (write result file); slightly more skill code (read with fallbacks). Gains durability against every crash scenario analyzed.

### DR-3: Option 3 default flip requires one guard — not three

- **Context**: First-draft version of this artifact proposed three guards (plan-complexity ≥5 tasks, uncommitted-changes, criticality high/critical excludes option 3) before flipping the default. Critical review established that (a) the 5-task threshold is uncalibrated and task count is orthogonal to trunk-damage risk, (b) a criticality exclusion forces users into autonomous or PR workflows for high-criticality work where inline review is most valuable, (c) the phased rollout's "run clean for a period" tripwire is unreachable given observed throughput.
- **Options considered**:
  - Three guards + phased rollout (first-draft): rejected as over-engineered against uncorroborated risk.
  - **One guard (uncommitted-changes) + direct flip**: recommended.
  - No guards + direct flip: rejected; the uncommitted-changes check is cheap, causally connected to trunk damage, and reuses an existing pattern from `skills/pr/SKILL.md`.
- **Recommendation**: **One guard, no phasing.** Pre-flight check runs `git status --porcelain`; if non-empty, demote option 3 from "recommended" to "available but not recommended" and surface the uncommitted-state to the user with a one-line warning. All other guards are deferred: if incidents occur, add them as follow-up tickets.
- **Trade-offs**: Accepts the risk that a user on main with a clean tree picks option 3 for a large plan and later regrets not using a branch. This is a user-education surface, not an enforcement surface. The uncommitted-changes guard is the minimum viable precaution.
- **Criticality behavior (deferred)**: whether to demote option 3 for high/critical is an Open Question for the spec phase. Demotion (not exclusion) is the likely answer given that inline review is valuable for high-stakes work.

### DR-4: Fix daytime pipeline atomicity + logging as a dedicated ticket; do NOT assert a root cause yet

- **Context**: The exit-128 failure in lifecycle 69 had an unknown root cause. The first-draft version of this artifact claimed "The likely root cause of the checkout failure itself is a Seatbelt OS-level write restriction on `.claude/worktrees/`." This claim contradicts `claude/rules/sandbox-behaviors.md:26-31`, which documents that `excludedCommands` causes git and its children to bypass the Seatbelt sandbox entirely. The Seatbelt hypothesis was incorrect.
- **Actual status**: root cause is **unknown**. Plausible hypotheses, unordered:
  - Stale `.git/worktrees/{feature}/` directory leftover from a prior partial creation (`cleanup_stale_lock` at `worktree.py:223` proves the codebase already knows about this failure family).
  - Existing orphan branch from a prior partial creation — though `_resolve_branch_name` should handle this; only relevant if a race condition created the branch between the check and the `git worktree add` call.
  - `base_branch="main"` not fetched / not present (common exit-128 cause on fresh clones or detached HEAD states).
  - Non-empty destination path (previous partial worktree creation left files at `.claude/worktrees/{feature}/`).
  - `.venv` symlink collision from a prior `shutil.copy2` at `worktree.py:162`.
  - Filesystem-level issue (case-insensitive collision, inode limits, disk full).
- **Fix posture**: Ship the atomicity + logging fixes **without** asserting a root cause. Once `create_worktree` surfaces git's stderr, the next reproduction of the failure will name the cause. If the failure never recurs after the atomicity fix is applied (because the try/except cleans up the stateful leftover that would otherwise accumulate), that itself is a clue — supports the stateful-leftover hypothesis over environmental ones.
- **Trade-offs**: Accepts that the fix may mask the underlying bug. Mitigation: keep a follow-up diagnostic ticket open; close it only after the failure has either recurred (with stderr now available) or demonstrably stopped.

## Decomposition Preview

Natural seams suggest five tickets. Ordering revised from the first-draft to avoid any intermediate state that's strictly worse than the current state.

| # | Ticket | Effort | Blocked-by | Rationale for ordering |
|---|--------|--------|------------|-------------------------|
| 1 | Fix daytime atomicity + logging defects (DR-4) | S | none | Independent; ships a measurable reliability improvement for existing option-2 users and makes future exit-128 failures diagnosable. Land first. |
| 2 | Define + implement option 2 output contract (DR-2) | M | 1 (benefits from the logging fix first) | Structured `daytime-result.json` + atomic writes + skill-side reader with three-tier fallback. Independent of pre-flight changes. |
| 3 | Add option 3 uncommitted-changes guard (DR-3) | S | none | Prerequisite for ticket 5; independent of the option-1/option-2 work. |
| 4 | Demote option 1 recommendation (DR-1) | S | none | Prompt-text edit + remove "recommended" badge from option 1. `§1a` scaffolding kept intact. |
| 5 | Flip default recommendation to option 3 | S | 3, 4 | Requires the guard (3) and the demotion (4) to land first so that the intermediate state always has a safe default. |

Total: 4× S + 1× M. Tickets 1 and 2 can land in parallel with tickets 3, 4, 5 (different files). Ticket 5 is a one-line prompt change blocked only by ordering-safety.

Intermediate-state analysis: no intermediate state is strictly worse than today. After ticket 1: daytime-pipeline failures are diagnosable. After ticket 2: option 2 result surfacing is crash-safe. After tickets 3+4: option 3 has an uncommitted-changes guard and option 1 is no longer the default, but remains selectable. After ticket 5: option 3 is the recommended default on main with the guard in place.

Possible epic grouping: "lifecycle implement-phase pre-flight modernization" for tracking; or ship as independent tickets since the dependencies are minimal.

## Open Questions

- **`daytime-result.json` schema** (ticket 2): minimal fields are `outcome`, `pr_url`, `session_id`, `start_ts`, `end_ts`, `tasks_completed`, `commits`, `rework_cycles`, `deferred_files: []`. Reserve fields for `cost_usd` and `tokens` even if not populated initially. Spec decides final shape.
- **`bin/daytime-status` or inline renderer** (ticket 2): new CLI mirroring `bin/overnight-status` shape vs. inline poll-loop rendering in the skill. Duplication vs. reuse. Both viable; spec decides.
- **Criticality-aware demotion of option 3** (ticket 5, optional): deferred from DR-3. If spec adopts it, the likely form is "demote, don't exclude" — preserves inline review for high-stakes work. Open for incident-based addition later.
- **Live-steerability preservation** (DR-1): option 1 is now demoted, not removed, so the question of a power-user flag for live steering is moot. The scaffolding is preserved; selection is opt-in.
- **Root cause of lifecycle 69's exit 128** (ticket 1 follow-up): the fix ships, the logging surfaces stderr, and the next reproduction names the cause. Track in a diagnostic follow-up ticket; close it when either the failure recurs with new information or demonstrably stops recurring.
- **Result-file freshness token format** (ticket 2): `session_id` (UUID) vs. `start_ts` (ISO 8601) vs. both. Spec decides; the point is that something identifying the run exists to distinguish this run's result from a stale prior-run result.
