# Research: gitbutler-workflow-integration

Investigate how GitButler's model — virtual branches, stacked PRs, the operations-log/undo
model, and its agent-facing `but` CLI/MCP surface — could improve the cortex-command harness.
Evaluate both adopting GitButler as a dependency and porting its concepts natively, across all
four workflow surfaces (overnight parallel agents, interactive daytime lifecycle, PR/handoff,
recovery), including whether virtual branches could replace git worktrees for agent isolation.

> **Bottom line (after critical review + a frequency measurement):** None of the GitButler-derived
> concepts clears the bar for a build right now. Worktrees should stay (the isolation argument is
> well-sourced; the "reconsider" question is answered *no for now*, re-open on a named trigger).
> Adopting GitButler the tool is rejected (FSL license, pre-1.0, not-a-wheel, file-state conflict).
> Stacked PRs — the one concept that looked high-value — solve a problem that **occurs in ~1 of 260
> backlog items today** and the simplest viable design does **not** land a chain cleanly under
> squash/edit merges. The honest recommendation is **defer everything**, file at most one low-priority
> watch/spike ticket, and revisit if dependency chains become common or `gh`-native stacked PRs reach GA.

## Research Questions

1. **Do GitButler virtual branches give real filesystem isolation suitable for parallel autonomous agents, or are they a single-working-directory abstraction?**
   → **Single-working-directory abstraction. No filesystem isolation.** This splits into a *durable architectural fact* and a *point-in-time vendor posture*, sourced differently:
   - *Durable fact (multi-source):* all applied virtual branches operate in ONE working tree; changes are assigned to branch "lanes" post-hoc via an ownership map ([building-virtual-branches](https://blog.gitbutler.com/building-virtual-branches)), and an independent production user (Trigger.dev) confirms same-file overlap "gets messy" and falls back to sequential work or worktrees ([parallel-agents-gitbutler](https://trigger.dev/blog/parallel-agents-gitbutler)).
   - *Point-in-time posture (single source):* a GitButler collaborator, asked directly, said *"no true isolation exists between concurrent agents"* and *"overlapping areas can definitely lead to problems related to races and interference"* ([discussion #12228](https://github.com/gitbutlerapp/gitbutler/discussions/12228), Feb 2026). This is one informal comment describing *current* architecture, not a permanent design guarantee — and GitButler's own native-worktree support is an **open** roadmap item (#10677, no date). So the *fact* is solid today; the *verdict* is "virtual branches cannot replace worktrees **as of the 0.19.x architecture**," not forever.

2. **What is GitButler's headless/agent surface in 2026, and is it dependable as a harness dependency?**
   → The `but` CLI is real, GUI-independent, has `-j/--json` everywhere, covers branch/stack/commit/push/oplog/PR ops, and runs on macOS/Linux/Windows without the GUI ([but-cli](https://blog.gitbutler.com/but-cli), [cli-overview](https://docs.gitbutler.com/cli-overview)). **But**: technical preview on a **pre-1.0 (0.19.x)** product; MCP server exposes a **single tool** today; license is **FSL-1.1-MIT** (source-available, non-compete, →MIT only 2 years post-release); it is a Tauri/Rust desktop binary (brew/curl install), **not a pip wheel** and not a documented embeddable library; mutating ops take an exclusive worktree lock (writes serialized). Scriptable experimentally; **not** dependable as a load-bearing dependency for an unattended harness shipping as a lean CLI wheel (ADR-0002).

3. **Would stacked PRs materially improve the handoff layer, given the current `intra_session_blocked_by` model and merged>0 gate? What would GitHub support cost?**
   → **The mechanism is real but the value is much smaller than it first appears — three corrections from critical review:**
   - **(a) Frequency, measured.** Of **260 backlog items, exactly 1** carries a non-empty `blocked_by` (#228 → [228]); **0** carry `intra_session_blocked_by`; no overnight session history records a non-empty intra-session chain. The problem stacked PRs solve — a dependency chain authored in one session — is **near-nonexistent in the actual backlog**. Concurrency is also capped at 1–3 workers `[cortex_command/overnight/throttle.py:27-39]`, so even when a chain exists a same-night chain is at most depth 2–3, and at the 1-worker tier the win is structurally zero.
   - **(b) "D nights → 1 night" conflates authoring with landing.** Today a dependent waits until its blocker reaches `merged` `[multi-agent.md:49]` because the session ships one integration PR `[runner.py:1457-1608]`. Stacking lets the chain be **authored and made reviewable** in one night — a *latency-to-review* win — but **landing** still requires sequential bottom-up human merges. The chain does not "land in one night" under any unattended-safe design.
   - **(c) The simplest design does not land cleanly.** GitHub auto-retarget on branch-delete moves a PR's **base pointer only**; it does **not** rebase B's commits off A's merged history. If A is **squash-merged or receives review changes** (the common cases), B still sits atop A's stale commits and needs a real commit rebase — exactly the operation an unattended-safe design must forbid at night. So a v1 that "delegates re-targeting to GitHub" only lands cleanly when A is **merge-commit-merged with no changes**. Robust stacking requires owning the cascade-rebase + force-push (what git-spice/spr/Graphite/gh-stack all do), which is the hard part, not a `gh --base` flag.
   GitHub *base-pointer* cost is low (`gh pr create --base <lower-branch>` — the runner already shells `gh pr create` `[runner.py:1585-1608]`); the *cascade* cost is the real cost and is unowned in the naive design.

4. **Does the oplog/snapshot/undo model add recovery beyond the current learnings-append + escalation ladder?**
   → It adds rollback-to-known-good and a bisect axis the current forward-only, lossy ladder lacks (`NOT_FOUND(query="oplog|reflog-based undo|snapshot rollback", scope="cortex_command/{overnight,pipeline}/*.py")`; only merge-revert exists `[cortex_command/pipeline/merge.py:301-324]`). But the gain overlaps commit-by-commit history and requires a GitButler dependency to get the *tool's* oplog. **Defer** — port the concept natively only if a second surface independently wants snapshots.

5. **Comparative landscape — what's worth porting natively vs adopting wholesale?**
   → The stacked-PR pattern is decade-proven (Meta ghstack/Sapling, Phabricator/Gerrit). **Critical correction:** the prior research named **git-spice** (branch-centric, local-only, multi-forge, auto-retarget, GPL-3.0 — fine for shell-out, not embedding) and **spr** (commit-centric, pure CLI, atomic re-target, MIT) as "the best models" but never ran the same adopt-vs-build analysis it ran on GitButler. These tools **already implement the cascade-rebase** that is the hard part of RQ3(c), are single static binaries (no desktop GUI, no FSL non-compete), and are GA. If stacking is ever pursued, **shelling out to git-spice/spr is a credible middle option** that avoids both a GitButler dependency and a from-scratch cascade implementation. **GitHub native `gh-stack`** is in private preview (Apr 2026, not GA) with an agent skill — strategically central but unstable to build against now. Container/VM-per-task (Devin, Codex, Copilot) is the proven *strong* isolation answer but at higher cost than worktrees.

6. **Per-surface verdict (adopt-tool / port-concept / do-nothing) with the strongest counter to each:**
   → • **Overnight parallel isolation → do-nothing** (keep worktrees). *Counter:* worktrees isolate files only, not DB/cache/services/ports, and cause disk blowup + slow re-installs (Trigger.dev's production report). *Honest weight:* our overnight units skew toward self-contained Python/markdown changes in one repo, so the shared-env pain is plausibly lower than Trigger.dev's multi-service case — but this is an **unmeasured** claim, and we *do* carry some worktree tax (slow re-installs; the editable-`.pth` rewrite footgun). It lowers, not eliminates, the counter.
   • **Interactive daytime side-quests → defer/low** (daytime convenience, not throughput; would need a GitButler dependency in interactive sessions).
   • **Stacked PRs → defer (not a current build).** Demoted from "highest value" by the RQ3 frequency measurement and the auto-retarget≠rebase flaw. Revisit on a named trigger (below).
   • **Oplog recovery → defer.**

## Codebase Analysis

**Dependency-chain frequency (new measurement — the decisive datum for RQ3).** `grep` over `cortex/backlog/[0-9]*.md`: **1 of 260** items has a non-empty `blocked_by` (#228 → `[228]`); `0` items contain `intra_session_blocked_by`; no non-empty intra-session dependency arrays appear in `~/.local/share/overnight-sessions` history. The class of work stacked PRs optimize is empirically rare in this repo.

**Worktree isolation (status quo).** Single resolver chokepoint `resolve_worktree_root()` `[cortex_command/pipeline/worktree.py:119-167]`; same-repo worktrees at `<repo>/.claude/worktrees/{feature}/` `[worktree.py:5-17,156-167]`; branch `pipeline/{feature}` with `-2/-3` collision suffixes `[worktree.py:98-116]`; idempotent create `[worktree.py:204-249]`; orphan-branch cleanup on add failure (#094) `[worktree.py:260-274]`; stale `index.lock` removal gated on `lsof` `[worktree.py:364-397]`. Interactive lifecycle materializes `interactive/{slug}` worktrees and auto-enters via `EnterWorktree` behind a 5-step preflight `[skills/lifecycle/references/implement.md:169-185]`, authorized by the regenerated CLAUDE.md clause.

**Parallel dispatch.** `ConcurrencyManager` wraps an `asyncio.Semaphore` fixed at the tier cap (1–3 workers; `max_5`→1, `max_100`→2, `max_200`→3) `[cortex_command/overnight/throttle.py:27-39,103-128]`; features run via `asyncio.gather(...)` `[orchestrator.py:485-488]`; batch circuit breaker at 3 consecutive pauses `[constants.py:7]`.

**PR handoff / merged>0 gate (#131).** Integration branch pushed unconditionally `[runner.py:1457-1495]`; `commit_count==0`→skip; `merged==0` w/ commits→`--draft` `[ZERO PROGRESS]`; else non-draft `[runner.py:1497-1544]`; PR via `gh pr create [--draft] --base main --head <integration_branch>` `[runner.py:1585-1608]`; per-feature merge does CI gate + `git merge --no-ff` + test + revert-on-fail `[cortex_command/pipeline/merge.py:158-332]`.

**Dependency model.** `intra_session_blocked_by` resolved at **round-planning** time by BFS round-assignment (dependent → round = max(blocker rounds)+1; cycles demoted) `[backlog.py:1051-1094]`, written via `features[slug].intra_session_blocked_by = ...` `[plan.py:421]`. Enforcement is structural (dependents in a later `run_batch` round), not a dispatch-time guard `[orchestrator.py:313-319]`.

**Error recovery.** Learnings appended to `cortex/lifecycle/{feature}/learnings/progress.txt`, prepended to next attempt `[retry.py:74-120]`; ladder `haiku→sonnet→opus`, opus-exhausted→pause `[dispatch.py:208-214; retry.py:402-439]`. **No oplog/undo** — only merge-revert `[merge.py:301-324]` and `gh pr ready --undo` `[runner.py:1699-1714]`.

**Known git-state pain.** Shared-git-index race between parallel `/commit` in one checkout (#135, **wontfix** — "right answer is per-agent worktree isolation"); home-repo-vs-worktree context drift epic (#126); `Agent(isolation:"worktree")`+`team_name` silent-failure invariant (never set — `NOT_FOUND(query="team_name", scope="skills/**, cortex_command/**/*.py excluding tests")`); TMPDIR placement bug reverted (#260).

## Web & Documentation Research

**GitButler facts (2026).**
- *Virtual branches:* one shared working tree; per-lane trees reconstructed from a `gitbutler/workspace` merge commit + ownership map; concurrent same-file edits racy ([#12228](https://github.com/gitbutlerapp/gitbutler/discussions/12228); [building-virtual-branches](https://blog.gitbutler.com/building-virtual-branches)). Native worktree support is roadmap-only (#10677, **open**).
- *Stacked branches/PRs:* v0.14.0+; each PR targets the branch below; base re-targeting **delegated to GitHub's auto-delete** (base-pointer move only, **not** a commit rebase); **GitHub-only** automation; open targeting bug #10936 ([stacked-branches docs](https://docs.gitbutler.com/features/branch-management/stacked-branches)).
- *Oplog:* snapshot before every state-changing op, parallel git history at `.git/gitbutler/operations-log.toml`; `but oplog list/snapshot/restore`, `but undo` ([recovering-stuff](https://docs.gitbutler.com/troubleshooting/recovering-stuff)).
- *`but` CLI / MCP:* real, GUI-independent, `-j/--json`; `but mcp` exposes one tool; `but skill install` ships an agent skill ([but-cli](https://blog.gitbutler.com/but-cli)).
- *License/arch:* **FSL-1.1-MIT** (→MIT after 2y) ([LICENSE](https://github.com/gitbutlerapp/gitbutler/blob/master/LICENSE.md)); Tauri/Rust/Svelte desktop app; no public HTTP API or embeddable library.
- *Maturity:* ~0.19.3 (Feb 2026), pre-1.0; a16z Series A (~Apr 2026) to "rebuild version control for AI-driven development" — i.e. the missing capabilities are *funded and roadmapped*, which is why the verdicts below are time-boxed.

**Trigger.dev production report** ([parallel-agents-gitbutler](https://trigger.dev/blog/parallel-agents-gitbutler)): abandoned worktrees for GitButler because worktrees isolate *source* not DB/cache/services, cause disk blowup (9.82 GB for a ~2 GB repo) and slow re-installs. Agents route changes via `but commit <branch> --changes <file-ids>` off `but status --json`. They **concede same-file overlap "gets messy" and fall back to sequential work or worktrees.**

## Domain & Prior Art

**Stacked-PR tooling.** git-spice (branch-centric, local-only, multi-forge GH/GL/BB, auto-retarget, GPL-3.0, JSON output, used at OpenAI/Uber/Spotify) and spr (commit-centric, pure CLI, atomic re-target, MIT) are the most headless/forge-friendly OSS — and crucially they **implement the cascade-rebase + force-push-on-merge** that the naive "delegate to GitHub auto-retarget" design omits. Graphite is most polished but SaaS-gated; ghstack needs repo write + `ghstack land`; git-branchless is alpha; Sapling is a full VCS. **GitHub native `gh-stack`** — private preview Apr 2026 (waitlisted, not GA), cascades rebase + atomic force-push, ships an **agent skill**.

**jujutsu (jj).** Conflict-tolerant rebase, op-log undo, anonymous branches; conceptually adjacent to GitButler on rewrite-safety but **not** a many-branches-in-one-tree system; no concurrent in-tree isolation. Pre-1.0; excellent git interop.

**How other AI agents isolate git.** worktree-per-task (Claude Code `--worktree`, file-only), container/microVM-per-task (Devin VMs, Codex microVMs, Copilot ephemeral GitHub-Actions envs — strong full-env isolation, higher cost; Copilot's `copilot/*` branch-prefix lock is a clean guardrail), branch-per-task atop either.

**Agents producing stacked PRs.** Nascent ("wave" layered decomposition against `gh stack`/Sapling; GitHub courting it). No rigorous study isolates stacking's effect on automated throughput; the **structural** caution (rebase cascades on squash/edit merges; force-push merge-killers) is the load-bearing argument. The one empirical preprint (arXiv [2602.19441](https://arxiv.org/abs/2602.19441)) flags force-pushes + large changes as merge-killers and reviewer engagement as dominant, but its authors concede it does not isolate stacking — so it **corroborates, it does not anchor**, the caution.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Status quo (port nothing)** | — | Forgoes a dependency-chain throughput win that the backlog shows is needed by ~1/260 items today; **preserves** flat, independently-mergeable PRs (a real safety property a stack would destroy) | — |
| **B1. Native stacked-PR handoff, naive (GitHub auto-retarget only)** | M | **Does not land cleanly under squash/edit merges** (auto-retarget moves base pointer, not commits); bottom-rejection strands the rest *worse* than status quo; 5 new internal pieces; near-zero current demand | Merge-commit-only merge policy; opt-in flag; retain exclude-until-merged |
| **B2. Native stacked-PR handoff, robust (own the cascade-rebase)** | L–XL | Owning autonomous force-push/rebase at night — the exact merge-killer the prior art warns against; high complexity for a low-frequency problem | Cascade-rebase engine; force-push safety; reviewer-loop integration |
| **B3. Shell out to a thin OSS stacking CLI (git-spice / spr)** | M | External binary dep (single static binary, not a wheel — lighter than GitButler, no FSL); GPL-3.0 (git-spice) acceptable for shell-out; still low current demand | Install path; map runner's branch/PR model onto the tool's |
| **C. Native oplog-style snapshot recovery** | M | Overlaps existing commit history; gain may not earn the machinery | A second surface wanting snapshots |
| **D. Virtual-branch diff-splitting (single agent, multi-concern)** | M | **High** — same-file races on `hot_files`; needs GitButler dep | GitButler `but` in sandboxed `_ALLOWED_TOOLS` |
| **E. Adopt `but` CLI as a runtime dependency** | L–XL | **High** — FSL, pre-1.0, not-a-wheel (breaks ADR-0002), tool-owned `virtual_branches.toml` vs file-based state (ADR-0001) | Headless reliability proven; install path solved |
| **F. Replace worktrees with virtual branches** | XL | **Rejected (time-boxed)** — no filesystem isolation in the 0.19.x architecture; vendor won't vouch for concurrency; rewrites ADR-0004/0005, `cortex init` auth, resolver/cleanup, ~25 tests | Would need #10677 (native worktrees) to ship first |

## Architecture

No build is recommended now (see Decision Records). The shape below is documented **only** so a future revisit has a starting point — it is not a current proposal. If stacking is ever pursued, the honest minimum is **B3 (shell out to git-spice/spr)** because it inherits the cascade-rebase the naive native design cannot safely own unattended.

### Pieces (for a future stacked-PR handoff, not built now)
- **Stack planner** — *inverts* round-assignment so a chain co-dispatches in one round instead of deferring dependents to later rounds. (This is a change to the BFS at `[backlog.py:1051-1094]`, not free reuse.)
- **Stacked dispatch base-resolver** — bases a stacked worker's branch on its blocker's `pipeline/{feature}` branch. (Change to the worktree base-resolution chokepoint `[worktree.py:119-167]`, must compose with `-2/-3` suffixes.)
- **Stacked-PR emitter** — bottom `--base main`, each higher `--base <branch-below>`. (The only piece that is genuinely a `gh` flag change.)
- **Cascade owner** — handles re-basing upper branches when a lower one is squash/edit-merged. This is the hard part; either deferred to a human (then the "one-night landing" benefit is lost) or delegated to git-spice/spr (B3).
- **Morning-review presentation + unattended-safety policy** — ordered bottom-up chain in the report; no autonomous force-push at night.

### How they connect
The planner consumes the existing DAG `[plan.py:421]` and emits a stack descriptor; the base-resolver threads it into worktree creation; the emitter sets `--base` bottom-up; the cascade owner (human or git-spice/spr) reconciles after each merge; the report renders the chain. The whole thing is opt-in, with exclude-until-merged as the default — but note that opt-in/fallback is a *pre-night* switch, not a runtime recovery, so a stacked night whose bottom PR is rejected strands the upper branches.

## Decision Records

- **Keep git worktrees for parallel isolation (reject Approach F — time-boxed).** Virtual branches share one tree with no OS-level isolation in the current (0.19.x) architecture, and the vendor will not vouch for concurrent agents. This answers the user's "reconsider worktrees?" question **no, for now** — not permanently. Re-open the question on a named trigger: GitButler ships native worktree support (#10677) **or** reaches 1.0. The architectural *fact* is multi-sourced (docs + Trigger.dev); only the vendor-posture rests on a single comment, so treat the verdict as durable-but-revisitable, not closed.
- **Do not adopt GitButler the tool now (reject Approaches D/E).** FSL license, pre-1.0 preview, out-of-band binary that breaks the lean-wheel distribution (ADR-0002), tool-owned `virtual_branches.toml` colliding with file-based state (ADR-0001).
- **Defer stacked PRs — do not build now (was "highest value"; demoted).** The frequency measurement (1/260 backlog items with any dependency; 0 intra-session) shows the problem is near-nonexistent today, and the naive native design (B1) does not land a chain cleanly under squash/edit merges. The "complexity must earn its place" standard that rejected GitButler applies equally here: a 5-piece build (or an XL cascade engine, B2) for a ~1/260 problem does not earn its place. **If** demand appears, prefer **B3 (shell out to git-spice/spr)** over hand-rolling, since those tools already own the cascade-rebase that is the genuine hard part.
- **Defer oplog-style recovery (Approach C).** Real gap (forward-only, lossy recovery) but the gain overlaps commit history; build only if a second consumer wants snapshots.
- **Net:** the durable value of this discovery is the *negative* result — a sourced, measured rationale for **not** changing course, plus a clear set of triggers and a preferred path (B3) for if the calculus changes.

## Open Questions

- **Revisit triggers for stacked PRs:** what would make this worth building? Candidates — intra-session dependency chains exceed N/quarter, or `gh`-native `gh-stack` reaches GA with its agent skill. (Decompose should consider filing a single low-priority *watch* ticket keyed to these triggers rather than a build epic.)
- **Worktree re-open trigger:** confirm the trigger for re-opening Approach F — #10677 landing and/or GitButler 1.0 — and whether anyone should track it.
- **Squash vs merge-commit policy:** if stacking is ever built naive (B1), it requires a merge-commit-only policy on stacked bottoms; is that acceptable given repo conventions?
- **B3 viability:** would shelling out to git-spice (GPL-3.0) or spr (MIT) clear the dependency bar that GitButler failed, given they are single static binaries with no GUI/FSL? (A focused spike, not a build.)
- **Unmeasured worktree tax:** is the disk-blowup/re-install cost Trigger.dev reported actually material for our overnight workloads? (Measurable from session worktree sizes if it ever bites.)
