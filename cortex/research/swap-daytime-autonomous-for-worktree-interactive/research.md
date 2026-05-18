# Research: swap-daytime-autonomous-for-worktree-interactive

Reshape the lifecycle implement-phase preflight by swapping the existing
"Implement in autonomous worktree" (daytime SDK pipeline) for a new
"Implement on feature branch with worktree" option that ends with a PR.
Bare "Create feature branch" coexists; overnight pipeline is unchanged.

> **Critical-review revision** (post-§6b): renders both candidate interaction
> models (A: active session `cd`s; B: fresh `claude --worktree` session) as
> equally-weighted architectural variants. Propagates corrections from R2
> (blast-radius), R3 (#228 reconciliation), R4 (TC4 mitigation calibration).
> **User resolutions:** DR-7 → option (a), cancel #228; swap rationale
> reframed as preference-based per DR-1 (revised). DR-3 → defer to
> decompose-gate by explicit user direction; decompose must fan out both A
> and B variants with concrete ticket scopes before commitment.

## Research Questions

1. **Active-session-in-worktree mechanics** — What concretely happens when the active Claude Code session works inside a worktree? → **Partial. Path resolution and per-feature artifacts work cleanly inside a worktree (the resolver terminates on `.git` files, `cortex/` appears via base-branch checkout). But Claude Code's SessionStart hook fires only at session startup `[hooks/cortex-scan-lifecycle.sh:15-26]`, so a session that starts on main and `cd`s mid-flight retains a stale `CORTEX_REPO_ROOT` and stale phase scan. The native `claude --worktree` flag pins startup CWD to the worktree and triggers `WorktreeCreate` hooks that copy `.claude/settings.local.json` and symlink `.venv` — manual `git worktree add` from a skill bypasses all of this `[cortex_command/pipeline/worktree.py:295-304]`. Two viable models exist (Approach A: cd-mid-session; Approach B: fresh `claude --worktree` session); codebase evidence favors B but the user's clarify-phase preference is A. See DR-3 — unresolved, both architectures rendered below.**

2. **Artifact transfer scope** — What moves with the worktree? → **Resolved. `git worktree add ... -b new-branch base_branch` checks out base_branch's HEAD, so all committed lifecycle artifacts (`research.md`, `spec.md`, `plan.md`, `events.log` to date, backlog item, `cortex/requirements/*`) appear in the worktree automatically `[cortex_command/pipeline/worktree.py:276-281]`. No explicit transfer logic needed. Subsequent writes are cwd-relative — events.log, backlog frontmatter, `.session` markers all land in whichever tree the active session's cwd is in. Under Approach A this is the worktree (after `cd`); under Approach B this is the worktree from session start. Both yield the same end-state at merge time, but Approach A has a transient split where SessionStart-fired metadata still references main.**

3. **PR + worktree-cleanup end-to-end flow** — When does the PR open? Who merges? How is the worktree cleaned up? → **Partial. PR opens in the Complete phase today via `/cortex-core:pr` `[skills/lifecycle/references/complete.md:70-81]`, not in Implement or Review. `/cortex-core:pr` assumes current cwd is a checkout with the feature branch — it has no `--worktree` or `-C` affordance `[skills/pr/SKILL.md:93]`. Under Approach A the lifecycle skill must `cd` into the worktree before invoking `/cortex-core:pr`; under Approach B the user is already in the worktree and `/cortex-core:pr` works unmodified. User merges (no auto-merge in skill layer). `NOT_FOUND(query="PR-merge worktree cleanup", scope="skills/+claude/hooks/+hooks/")` — no automatic cleanup exists. `cortex-worktree-remove.sh` is notification-only `[claude/hooks/cortex-worktree-remove.sh:1-25]`. Long-lived feature worktree needs a cleanup contract distinct from the existing `worktree/agent-*` sub-agent prefix.**

4. **Daytime-autonomous removal blast radius** — What gets deleted? → **Resolved (corrected post-§6b).** Pure deletes (~12 files): three daytime modules (`daytime_pipeline.py`, `daytime_dispatch_writer.py`, `daytime_result_reader.py`), **`readiness.py` (the artifact previously misclassified this as a runner.py dependency; runner.py imports `auth.resolve_and_probe` directly, not `readiness` — confirmed via `grep "from cortex_command.overnight.readiness" cortex_command/`)**, six test files, and `tests/test_dispatch_parity.py`. Pure unregisters: three console-scripts in `pyproject.toml:32-34`. State fragments: `DaytimeResult` + `save_daytime_result` from `state.py`. Skill prose: `implement.md` §1 menu (lines 16-50) and §1a (lines 54-160) — ~140 lines net. Modifications (~17 files): dashboard surfaces (`data.py`, `poller.py`, `seed.py`, `feature_cards.html` — multiple sites per file), `justfile` (`test-dispatch-parity-launchd-real` recipe), docs (`docs/setup.md:121`, `docs/overnight-operations.md`), audit/registry files (`bin/.audit-bare-python-m-allowlist.md`, `bin/.events-registry.md`), `cortex/requirements/observability.md:144`, **`.gitignore:31-33` (daytime tempfile patterns)**, **`cortex_command/overnight/auth.py` (module docstring, function docstrings, CLI argparse description all reference daytime)**, **`cortex_command/overnight/cli_handler.py:61` (Sphinx `:func:` xref to `daytime_pipeline._read_test_command`)**, **`cortex_command/pipeline/metrics.py:324-414` and `pipeline/tests/test_metrics.py:216-246` (`_DAYTIME_DISPATCH_FIELDS` filter + test, dead code post-removal — explicit decision to delete the filter or carry as graveyard prose)**. Production overnight runtime code (`feature_executor.py`, `outcome_router.py`, `orchestrator.py`, `runner.py`'s logic, `report.py`) does NOT import daytime — confirmed via `grep "from cortex_command.overnight.daytime"`. **Behavioral overnight is untouched; code-hygiene overnight has multiple touchpoints that the original framing obscured.**

5. **Adversarial: what is lost? what failure modes does the new path inherit?** → **Unresolved (deliberate). Three material concerns flagged by adversarial agent that the user must explicitly accept or mitigate before decompose. (a) **TC4 / context-window exhaustion**: daytime's per-task fresh-context SDK `query()` is the architectural answer to a ceiling the interactive replacement may re-create. **Critical caveat (post-§6b)**: `skills/lifecycle/references/implement.md` §2 already uses per-task sub-agent dispatch from the orchestrator session; if that dispatch isolates per-task context regardless of orchestrator CWD, the interactive worktree path inherits that isolation and TC4 may not apply at all. **This claim is unverified in the codebase**; surface as Open Question 8. (b) **Pricing claim** is unsubstantiated; see DR-6. (c) **Sandbox `.mcp.json`** failure mode is mitigated by the existing `$TMPDIR/cortex-worktrees/{feature}` default — not inherited.**

6. **Concurrent-session guards** — What guards does the new path need? → **Resolved with carry-forward. Ticket #135 (shared-git-index race, wontfix) explicitly names the proposed direction as the architectural answer to that race `[cortex/backlog/135-...md:62-63]`. Required guards: (i) per-feature single-owner lock equivalent to `daytime.pid`+`kill -0`; (ii) overnight-active rejection mirror of `§1a.iii` on the interactive path; (iii) inverse — overnight preflight scans for live interactive feature worktrees before claiming features (today: `NOT_FOUND(query="active feature scan in overnight preflight", scope="cortex_command/overnight")`); (iv) uncommitted-state preservation per `cortex/requirements/project.md:42`. Nice-to-have: abandoned-session detection at SessionStart, verify-before-push, distinct long-lived feature-worktree prefix.**

## Codebase Analysis

### Existing infrastructure

- **Worktree primitives are mature** — `cortex_command/pipeline/worktree.py:128-188` exposes `resolve_worktree_root(name, session_id)` (single chokepoint), `create_worktree()` (copies `.claude/settings.local.json`, symlinks `.venv`), and `CORTEX_WORKTREE_ROOT` env-var override. Default same-repo path is `$TMPDIR/cortex-worktrees/{feature}`, deliberately outside Seatbelt's mandatory `.mcp.json` deny under `.claude/` `[cortex_command/pipeline/worktree.py:1-17]`.
- **Path resolution handles worktrees** — `cortex_command/common.py:55-103` resolves project root by walking up from cwd; terminates on `(current / ".git").exists()` which handles a worktree's file-shape `.git`. Resolver is invoked at call time, so `cd` semantics work `[cortex_command/common.py:66-70]`.
- **`claude --worktree` integration** — `plugins/cortex-core/hooks/hooks.json:14-33` registers `WorktreeCreate`/`WorktreeRemove` to `claude/hooks/cortex-worktree-create.sh` and `cortex-worktree-remove.sh`. These fire only when Claude Code itself manages the worktree (via `--worktree` flag or sub-agent `Agent(isolation: "worktree")` dispatch). Manual `git worktree add` from a skill does not trigger them — **this is a direct argument for Approach B** since `claude --worktree` triggers the existing hook infrastructure while `cd`-mid-session bypasses it.

### Critical gap (Approach A only): SessionStart-only env injection

`hooks/cortex-scan-lifecycle.sh:22-24` injects `CORTEX_REPO_ROOT=$CWD` into `CLAUDE_ENV_FILE` only when `$CWD/.git` exists and the env var is unset. The hook fires only on SessionStart. **A session that starts in main and `cd`s into a worktree retains the stale env value and the stale phase-scan output from the SessionStart firing.** Under Approach B, the session starts in the worktree so `CORTEX_REPO_ROOT` is fresh. This is the dominant technical risk for Approach A and has no equivalent risk under Approach B.

### cwd-relative write sites (Approach A code-layer risk)

All identified writers use relative `Path("cortex/lifecycle")` rather than `_resolve_user_project_root()`. Under Approach A, a worktree-resident session writes to the worktree's copies; main never sees those events until merge. Under Approach B, all writes are worktree-scoped from session start — no transient split. **The "skill prose discipline" mitigation referenced in earlier framing is in tension with prior tickets #126 and #130, which fixed analogous home-vs-worktree drift via code-layer refactor, not prose:**

- `cortex_command/refine.py:117` — events.log append
- `cortex_command/critical_review.py` — events.log append (same pattern)
- `bin/cortex-complexity-escalator:296` — events.log path
- `cortex_command/discovery.py:189-197` — events.log resolution helper
- `cortex_command/backlog/update_item.py:445` — backlog dir via `_resolve_user_project_root()` (worktree-aware, so updates target worktree's backlog copy)
- `cortex_command/backlog/update_item.py:169` — sidecar `.events.jsonl` next to item
- `claude/statusline.sh:244-247` — reads cwd-resolved `current_dir/lifecycle`
- `cortex_command/overnight/report.py:52,125` — morning report reads `_resolve_user_project_root() / "cortex/lifecycle"`

Under Approach A, these eight sites would need either explicit absolute-path injection or a per-tool-call CWD-refresh mechanism — a code-layer surface. Under Approach B they need nothing.

### Preflight today (3 options after epic #093)

`skills/lifecycle/references/implement.md:14-50`:
1. **Implement on current branch** (recommended; guarded against dirty tree by `git status --porcelain` demotion at line 22)
2. **Implement in autonomous worktree** — daytime pipeline subprocess
3. **Create feature branch** — bare `git checkout -b feature/{slug}`, known sharp edge for parallel sessions

`§1a` (lines 54-160) — 107-line "Daytime Dispatch (Alternate Path)" block. Deletes wholesale on this swap.

### Production overnight code does not import daytime (behavior-only claim)

Confirmed via `grep "from cortex_command.overnight.daytime"`: `feature_executor.py`, `outcome_router.py`, `orchestrator.py`, `runner.py`, `report.py` have no daytime imports. **This is a behavior-only claim; code-hygiene touchpoints remain** (per RQ4 corrected inventory): `auth.py` docstrings, `cli_handler.py:61` Sphinx xref, `pipeline/metrics.py` `_DAYTIME_DISPATCH_FIELDS` filter become dead code post-removal. Daytime is a true behavioral leaf, not a code-hygiene leaf.

### Worktree prefix conventions

- `worktree/agent-*` — sub-agent dispatch worktrees (short-lived; per-task)
- `pipeline/{feature}` — autonomous-daytime worktrees (lifetime: subprocess duration)
- `feature/{slug}` — bare `git checkout -b` from current "Create feature branch" option (no worktree)
- **Proposed new prefix** — long-lived feature worktree distinct from above. Specific value is a decompose-time decision.

## Web & Documentation Research

### Active editor session inside a worktree (external pattern)

The dominant industry pattern is **one task → one branch → one worktree → one agent session** ([nrmitchi.com/2025/10/using-git-worktrees-for-multi-feature-development-with-ai-agents](https://www.nrmitchi.com/2025/10/using-git-worktrees-for-multi-feature-development-with-ai-agents/); [cursor.com/docs/configuration/worktrees](https://cursor.com/docs/configuration/worktrees); [code.claude.com/docs/en/worktrees](https://code.claude.com/docs/en/worktrees)). Both Cursor and Claude Code implement a managed "launch agent in worktree" primitive: Cursor's `/apply-worktree` brings changes back; Claude Code's `claude --worktree <name>` defaults to `.claude/worktrees/<name>/` on a new `worktree-<name>` branch.

### PR opening point

Late-PR-after-implementation is the documented majority pattern (Cursor docs; [mindstudio.ai/blog/parallel-agentic-development-git-worktrees](https://www.mindstudio.ai/blog/parallel-agentic-development-git-worktrees)). Draft-PR-first as a coordination signal is rising in background-agent setups but not dominant.

### Worktree cleanup canonical rules

- **Always use `git worktree remove`, never `rm -rf`** — `remove` cleans both the directory and `$GIT_DIR/worktrees/<name>` metadata atomically.
- **`gh pr merge --delete-branch` does NOT delete the local worktree** ([cli/cli#13380](https://github.com/cli/cli/issues/13380)).
- Claude Code's exit-time cleanup: **`--worktree` sessions are NOT swept by the background cleanup job** ([code.claude.com/docs/en/worktrees](https://code.claude.com/docs/en/worktrees)). Both Approach A and Approach B inherit this gap.

### Claude Code specifics

- Official `claude --worktree <name>` documented: startup CWD pinned to worktree, `worktree.baseRef: "fresh"|"head"`, `.worktreeinclude` for copying gitignored files, `WorktreeCreate`/`WorktreeRemove` hooks.
- **No `--cwd` flag** — request is open and stale ([anthropics/claude-code#47017](https://github.com/anthropics/claude-code/issues/47017)). Standard launch pattern is `cd <worktree> && claude` (Approach B's shape).
- **Mid-session `cd` reliability for hooks/sandbox is documented-unclear**; one related bug confirms hooks can fire with the wrong CWD ([anthropics/claude-code#22343](https://github.com/anthropics/claude-code/issues/22343)). **This is the cited evidence that Approach A's mitigation cost may exceed "skill prose discipline."**

## Domain & Prior Art

### Directly relevant tickets

- **#135** (shared-git-index race, **wontfix**) — names the proposed direction as the architectural answer: "daytime-worktree isolation (extending the existing per-feature worktree pattern from overnight to interactive sessions)" `[cortex/backlog/135-...md:62-63]`. This discovery resolves an open wontfix.
- **#093 / #097** (modernize implement preflight; remove single-agent worktree dispatch, complete) — removed an earlier `Agent(isolation: "worktree")` sub-agent worktree path. The proposed option is **not** a re-introduction of that path — different shape, different lifetime, different blast radius.
- **#074-#077** (autonomous worktree epic, complete) — established `feature_executor.py`, `outcome_router.py`, `orchestrator.py` as shared overnight primitives. Daytime pipeline is a thin consumer; removal is a behavioral leaf operation.
- **#126** (eliminate home-repo-vs-worktree context drift, complete) — established invariant that operations meant for the worktree must not execute against home repo. **Crucial precedent for DR-3**: the original drift was fixed at the code layer (refactor of write-site path resolution), not at the prose layer. Approach A would re-open this risk class without code-layer fixes.
- **#130** (route python-layer backlog writes through worktree-checkout, complete) — concrete prior failure: `report.py` writes landed as untracked home-repo files; `/discovery` later reused those IDs and silently overwrote `[cortex/backlog/130-...md:30]`. **Backlog frontmatter mutations from a `cd`-mid-session worktree-interactive session face the same vector unless the write-site refactor pattern is extended.**
- **#208** (harden autonomous-dispatch path for interactive Claude Code sessions, complete) — fixed three sandbox/auth/env-resolution failures that broke daytime when invoked from interactive context. **Code-layer fixes**, not prose.
- **#228** (wire daytime dispatch through CLI+MCP with launchd detachment, status:refined, plan-complete, 43KB plan.md + 33KB spec.md, with downstream blocker #230 also plan-complete) — proposes wiring daytime through MCP + launchd detachment to close the session-parentage `EPERM` root cause of daytime brittleness. **#228 is materially advanced — not just "near-complete." If #228 ships, the "daytime is brittle" leg of DR-1 collapses; combined with DR-6 striking the pricing leg, DR-1's brittleness rationale is structurally challenged.** See DR-7 (revised) for reconciliation framing.

### Existing skill prose for PR creation

`/cortex-core:pr` (`skills/pr/SKILL.md`) is mature but worktree-naive: assumes current cwd is the checkout, uses `git push -u origin HEAD`, no `--worktree`/`-C`, explicitly forbids `--draft` by default `[skills/pr/SKILL.md:88-92]`. **Under Approach A**, either teach `/cortex-core:pr` worktree-awareness (`-C <worktree>` plumbing — code-layer) or have the lifecycle skill `cd` into the worktree before invoking. **Under Approach B**, the user is already in the worktree session and `/cortex-core:pr` works unmodified — zero PR-skill changes.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Active session `cd`s into worktree mid-flight (user-stated model)** | **M-L (revised)** | SessionStart hook staleness (`CORTEX_REPO_ROOT` pinned to startup CWD); events.log split between main and worktree until merge; eight cwd-relative writer sites that historically required code-layer refactor (#126/#130 precedent), not prose; statusline drift; hook re-fire semantics not guaranteed ([anthropics/claude-code#22343](https://github.com/anthropics/claude-code/issues/22343)); sandbox path resolution may not refresh; no documented Claude Code support for mid-session CWD switch ([anthropics/claude-code#47017](https://github.com/anthropics/claude-code/issues/47017)). **Adversarial assessment**: "fixable with skill prose discipline" understates the cost given precedent — #126/#130/#208 were all code-layer fixes for analogous problem classes. | Either a per-tool-call CWD-refresh mechanism (new SessionStart-equivalent that re-fires on `cd`), OR a code-layer refactor of the eight cwd-relative writer sites to absolutize through an explicit worktree-path param; PR-skill (`/cortex-core:pr`) plumbing for `-C <worktree>` or skill-level `cd` before invoke; explicit policy for which writers absolutize vs. stay cwd-relative; test that `.mcp.json` resolves correctly post-`cd` |
| **B. Lifecycle creates worktree, exits, prompts user to open `claude --worktree <name>`** | **S** | Two-session UX discontinuity: the current `/cortex-core:lifecycle` session ends and the user opens a new one in the worktree. Conversation context resets at the seam. User must remember to `claude --worktree <name>` rather than `claude` (workspace-trust must already be accepted in the dir). | None — leverages native Claude Code primitive end-to-end; `WorktreeCreate` hook fires (vs. silently bypassed in A); `cd` semantics not relied on |
| **C. Hybrid — lifecycle creates worktree, current session continues but all subsequent skill writes use explicit worktree path (no `cd`)** | L | Refactor of ~8 write sites to accept explicit worktree-root param; high coordination cost; statusline still pinned to session CWD (shows wrong feature); morning report path resolution drifts | Refactor of events.log/backlog write APIs to take explicit base path; skill prose audit for all `cortex/lifecycle/{slug}/` references; per-call CWD discipline |
| **D. Build a fresh-context-per-task primitive within interactive Claude Code (Task tool with worktree CWD)** | XL | Re-implements daytime's architectural advantage inside Claude Code's Task tool surface; unclear if Task tool supports per-spawn CWD; loses the conversational steering benefit | Investigation of Task tool's CWD parameter (`NOT_FOUND` in this research's scope); spec for fresh-context dispatch contract |

**Approach selection (not committed; pending DR-3 resolution by user)**: Codebase evidence pulls toward B (native primitive, no `cd`-mid-session risk, zero PR-skill changes); user's clarify-phase preference is A (continuity of session). The critical-review pass identified this asymmetry as the artifact's central unresolved tension. The post-§6b revision renders both A and B symmetrically; DR-3 stays open.

## Architecture

### Pieces

- **Preflight menu shape** — three implement options, with "Implement on feature branch with worktree" replacing "Implement in autonomous worktree" in option-2 slot. Bare "Create feature branch" (option 3) stays. `Implement on current branch` (option 1, recommended) stays.
- **Worktree-creation step** — invoked when the user selects the new option. Reuses `cortex-worktree-resolve` for canonical sandbox-safe path; reuses `create_worktree()` semantics for `.claude/settings.local.json` copy and `.venv` symlink. Worktree prefix is a new convention (e.g. `interactive/{slug}`) distinct from `worktree/agent-*`, `pipeline/{feature}`, and bare `feature/{slug}`.
- **Interaction model (DR-3 — both variants rendered)**:
  - **Variant A — Active session `cd`s**: Worktree creation completes, the lifecycle skill issues `cd $(cortex-worktree-resolve interactive/{slug})`, and continues §2 task dispatch from the new CWD. Requires per-tool-call CWD-refresh OR write-site refactor (see Feasibility row A).
  - **Variant B — Fresh `claude --worktree` session**: Worktree creation completes, the lifecycle skill emits `claude --worktree interactive/{slug}` as a copy-paste instruction and the explicit `cortex/lifecycle/{slug}/.session.handoff` marker, then exits `/cortex-core:lifecycle`. User opens the new session; SessionStart hook fires in the worktree (fresh `CORTEX_REPO_ROOT`); user re-invokes `/cortex-core:lifecycle implement` which detects the handoff marker and resumes at §2 task dispatch.
- **Per-feature single-owner guard** — a `.session-owner.pid` or `interactive.pid` file under `cortex/lifecycle/{slug}/` with `kill -0` liveness check. Equivalent shape to existing `daytime.pid` in §1a.ii. Applies identically under A and B.
- **Overnight-active rejection (mirror)** — pre-flight check on the interactive option that reads `~/.local/share/overnight-sessions/active-session.json` and rejects with the same wording as today's §1a.iii. Applies identically under A and B.
- **Inverse-direction guard (new)** — overnight preflight scans `cortex/lifecycle/*/.session` or new interactive PID files before claiming features. Today: `NOT_FOUND`. Applies identically under A and B.
- **PR-creation hook**:
  - **Under Variant A**: Lifecycle's Complete phase issues `cd $(cortex-worktree-resolve interactive/{slug}) && /cortex-core:pr` (skill-level `cd`), OR `/cortex-core:pr` is taught a `--worktree <slug>` flag (code-layer refactor). PR opens at Complete time.
  - **Under Variant B**: User is already in the worktree session; `/cortex-core:pr` runs unmodified. Zero PR-skill changes needed.
- **Worktree cleanup contract** — long-lived feature worktree distinct from short-lived sub-agent worktrees. Options: (a) Complete-phase auto-cleanup gated on PR-merged-and-clean status, (b) manual via a `cortex-cleanup-feature-worktree <slug>` recipe, (c) SessionEnd hook with dirty-state preservation per `cortex/requirements/project.md:42`. Applies identically under A and B; decompose-time decision.
- **Daytime-autonomous removal sweep** — single epic spanning skill prose (§1 menu + §1a), four module deletes (including `readiness.py` per RQ4 correction), three console-script unregisters, dashboard parser+template trim, test deletes including `tests/test_dispatch_parity.py`, justfile recipe drop, `.gitignore` patterns, docs/registry/requirements updates, code-hygiene touchpoints in `auth.py`/`cli_handler.py`/`pipeline/metrics.py`. Per RQ4 corrected inventory.

### How they connect

The Implement-phase preflight (`§1`) is the single decision point that routes by user selection. The new option triggers worktree creation, then either continues in-session (Variant A) or hands off to a fresh session (Variant B). Per-feature guards run before worktree creation (reject if another interactive or overnight owner is alive). Task dispatch (§2) and Rework (§3) execute identically to today's `Implement on current branch` flow once the active context is inside the worktree — they are CWD-bound and don't care whether the CWD is main or a worktree. Complete (§4) detects the worktree state, invokes `/cortex-core:pr` (with `cd` or `--worktree` plumbing under A, unmodified under B), and surfaces the PR URL. Worktree cleanup is decoupled from PR creation — it fires later, gated on merge state, to preserve uncommitted work.

The daytime-autonomous removal is a parallel concern that touches the same `implement.md` file but doesn't share runtime semantics with the new option. They land in one epic for operational clarity (the menu changes are coupled) but the implementation tickets split cleanly.

## Decision Records

**DR-1 (User direction — preference-based after §6b reconciliation)** — Replace daytime autonomous with worktree-interactive rather than coexist. **Original rationale (as stated by user):** daytime is brittle and Anthropic's SDK pricing direction makes it unviable to maintain. **Post-§6b status:** DR-6 struck the pricing leg as unsubstantiated; DR-7 originally challenged the brittleness leg via #228. **User resolved DR-7 with option (a) — cancel #228 and proceed with the swap.** This makes the swap an explicit *preference* choice (user wants interactive driving over autonomous SDK subprocess) rather than an evidentiary necessity. The user accepted the cost of cancelling #228's plan-complete work as the price of the swap. This is a valid load-bearing input on its own — preference is sufficient justification when the alternative is preserving infrastructure the user does not want to maintain.

**DR-2 (User direction)** — Bare `Create feature branch` coexists with worktree-interactive; not replaced. **Why:** preserves PR-based flow for users whose tooling assumes a single checkout. **Tradeoff:** preflight has three options, not two; the known sharp edge (`git checkout` corrupting parallel sessions in same repo) stays.

**DR-3 (Deferred to decompose by explicit user direction)** — Interaction model: Variant A (active session `cd`s) vs. Variant B (fresh `claude --worktree` session). **User stated preference in clarify:** A. **Codebase evidence (per critical review):** favors B — native Claude Code primitive (`claude --worktree`) is documented and supported; mid-session `cd` reliability is documented-unclear; the eight cwd-relative writer sites would require code-layer refactor under A (#126/#130/#208 precedent); manual `git worktree add` from a skill bypasses `WorktreeCreate` hooks that `claude --worktree` triggers. **Post-§6b resolution:** user explicitly deferred this decision to decompose-gate where concrete ticket scopes can be evaluated side-by-side. Both variants stay rendered symmetrically in the architecture section. **Decompose must produce fan-out for both A and B**, then surface the trade-off with ticket scopes (refactor surface for A; UX-discontinuity work for B) before the user commits.

**DR-4 (Architectural alignment)** — Removing daytime autonomous is *aligned* with `cortex/requirements/project.md:11` ("daytime is iterative collaboration; overnight is handoff"), not in conflict. The autonomous north star (line 7) is overnight-scoped.

**DR-5 (Adversarial carry-forward — TC4, revised)** — TC4 / context-window exhaustion was originally framed as a real cost of replacing daytime. **Post-§6b correction:** the framing assumed the interactive worktree path is "a single session implementing N tasks," but `skills/lifecycle/references/implement.md` §2 already uses per-task sub-agent dispatch from the orchestrator session. **If §2's sub-agent dispatch isolates per-task context regardless of orchestrator CWD, the interactive worktree path inherits that isolation and TC4 does not apply at the per-task layer** — the residual concern is orchestrator-session context growth from review/orchestration overhead, which is qualitatively smaller. This must be verified before committing to a task-count cap. **The "≤5 tasks" threshold in the prior framing was uncalibrated**: the only prior in-repo threshold is `>10 tasks` (`cortex/lifecycle/archive/lifecycle-implement-worktree-dispatch/plan.md:112`) and "typical" feature size is 5-10 per `cortex/lifecycle/archive/add-cortex-init.../plan.md:286`. **Mitigation options if TC4 *is* a residual concern:** (a) accept a calibrated ceiling (e.g., `>10 tasks` based on in-repo prior, not `≤5`); (b) build a fresh-context Task-tool primitive within Claude Code (Approach D in feasibility — XL); (c) push large features to overnight — but **this mitigation is operationally narrow**: overnight is a *handoff* modality per project.md:11, not a same-day overflow path; a user with a too-large feature at mid-day has no same-day route under (c). **No single mitigation closes the gap cleanly**; the path forward is to verify §2's per-task isolation first, then revisit mitigations only if needed. See Open Question 8.

**DR-6 (Adversarial carry-forward — pricing claim)** — The "Anthropic SDK pricing changes" rationale is unsubstantiated in repo evidence. Either cite a specific change (link to Anthropic docs or quoted policy) or strike that rationale and rest the decision on the brittleness + day/night-split arguments alone. **Recommend strike unless cited.** Combined with DR-7's challenge to the brittleness leg, DR-1's stated rationale is structurally weakened — see DR-1 (revised).

**DR-7 (Resolved post-§6b — option (a), cancel #228)** — Ticket #228 (status:refined; 43KB plan.md, 33KB spec.md; downstream blocker #230 also through plan) proposed wiring daytime through MCP + launchd detachment to close the session-parentage `EPERM` root cause of daytime brittleness. §6b surfaced that #228 was plan-complete (not "near-complete") and offered three reconciliation paths. **User selected option (a): cancel #228 as part of this swap.** Rationale (preserved from user direction): the swap is committed-to on preference grounds — the user does not want to maintain autonomous daytime infrastructure regardless of how hardened it becomes. The plan-complete state of #228 is acknowledged as accepted cost. **Downstream implication:** decompose tickets include an explicit "cancel #228 (and downstream #230 dependency)" step alongside the removal-sweep work. The cancellation closes #228 and #230 with documentation pointing to this discovery as the supersedence record.

## Open Questions

1. **DR-3 — Interaction model**: Variant A (active session `cd`s) vs. Variant B (fresh `claude --worktree` session)? Codebase evidence favors B; user preference in clarify was A. **Post-§6b user direction: defer to decompose-gate where concrete ticket scopes for both variants are visible side-by-side. Decompose must fan out both A and B and surface the trade-off before the user commits.**
2. ~~**DR-7 reconciliation**~~ — Resolved post-§6b: user selected option (a), cancel #228. See DR-7 (revised).
3. **PR-creation pattern**: Worktree-aware `/cortex-core:pr` (`-C` / explicit worktree path) vs. lifecycle skill `cd`s before invoking? Bundle with DR-3 — same answer wins both. **Under Variant B, this collapses (no PR-skill changes needed).**
4. **Worktree cleanup ownership and trigger**: Complete-phase auto-cleanup gated on PR-merged-and-clean, manual recipe, or SessionEnd hook? `cortex/requirements/project.md:42` (uncommitted-state preservation) constrains the cleanup contract.
5. **Worktree prefix**: `interactive/{slug}`, `feature/{slug}` (collides with bare option 3), or something else? Affects existing cleanup logic and morning report scans.
6. **TC4 mitigation calibration**: First verify whether §2's per-task sub-agent dispatch isolates context (per DR-5 revision). If yes, TC4 doesn't apply; no cap needed. If no, calibrate threshold to in-repo prior (`>10 tasks`) not the prior `≤5` guess, AND surface that "push to overnight" is a same-day-gap mitigation.
7. **Removal-sweep test coverage**: Six-plus test files delete entirely (corrected count per §6b); what regression risk remains? Recommend a smoke test that exercises the new option end-to-end before removing the daytime tests, to avoid a test-coverage gap during the transition.
8. **§2 per-task isolation verification (new, blocking DR-5)**: Confirm by reading `skills/lifecycle/references/implement.md:162-205` whether sub-agent dispatch isolates context per task regardless of orchestrator CWD. If isolated, TC4 is resolved (does not apply); if not, the artifact's "execute identically to today's `Implement on current branch` flow" claim needs revision and TC4 mitigation becomes load-bearing.
