# Research: Remove single-agent worktree dispatch and flip recommended default to current branch

**Ticket**: `backlog/097-remove-single-agent-worktree-dispatch-and-flip-recommended-default.md` (complex / high).

## Epic Reference

- Decomposition research: `research/revisit-lifecycle-implement-preflight-options/research.md` — DR-1 recommended *demote*; user overrode to *remove* (documented in ticket 097 body, "Findings from discovery").
- Epic whose DR-2 is being reversed: `research/implement-in-autonomous-worktree-overnight-component-reuse/` — this epic originally ratified co-existence of the single-agent worktree path with the autonomous daytime pipeline. The DR-2 reversal applies only to DR-2; the epic's modularization decisions (DR-1, DR-3 onward and children #075–#078) are unaffected.

This ticket's scope is option-1 removal + promoted default + scaffolding audit + DR-2 drift note. Adjacent tickets (#094, #095, #096, #110, #123) are referenced only for boundary checking.

## Codebase Analysis

### Files that will change

| File | Section / lines | Change |
|---|---|---|
| `skills/lifecycle/references/implement.md` | §1 pre-flight (lines 11–28) | Delete option 1 description (line 13), delete routing dispatch for option 1 (line 23), update "four options" → "three options" (line 11), rename "Implement on main" → "Implement on current branch" (line 15), update post-selection routing-match substring in lock-step |
| `skills/lifecycle/references/implement.md` | §1a (lines 32–108) | Delete in full (~77 lines) |
| `skills/lifecycle/references/implement.md` | worktree-agent context guard (line 18) | Delete — becomes dead code once `worktree/agent-*` branches are no longer created by any live path (see adversarial #5) |
| `skills/lifecycle/SKILL.md` | Step 2 "Dispatching Marker Check" sub-section | Delete — `.dispatching` marker is §1a-exclusive; §1b explicitly forgoes it (implement.md line 114) |
| `skills/lifecycle/SKILL.md` | Step 2 "Worktree-Aware Phase Detection" sub-section | Delete — scoped exclusively to the `worktree/agent-*` branch pattern; §1b uses `pipeline/{feature}-N` and has separate detection via `daytime-dispatch.json` |
| `hooks/cortex-cleanup-session.sh` | worktree-prune block (lines 36–60) | Delete — the `worktree/agent-*` prefix is not used by any surviving live caller (`cortex-worktree-create.sh` creates `worktree/{task-name}` without `agent-` prefix). No tests cover this branch (`tests/test_hooks.sh` covers only `.session` cleanup) |
| `research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md` | Inline annotation after line 65 (DR-2 statement) | Append dated reversal note citing ticket 097; do NOT amend the research.md top-level because that file is cited by 7+ downstream tickets unaffected by this reversal |
| `backlog/110-unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception.md` | Scope amendment | Append a note: ticket 110's "retain `.dispatching` marker check" scope assumption is invalidated by ticket 097 — the marker code will not exist at the time #110 runs |

### Patterns, integration points, and conventions

- **Per-task `worktree/{task-name}` is a separate concern** from `worktree/agent-{slug}`. §2b Worktree Integration is unaffected. The cleanup hook's `worktree/agent-*` pattern does NOT match `worktree/{task-name}` so these per-task branches have never depended on the hook — they are handled by the orchestrator's own `git worktree remove` / `git branch -d` calls at implement.md:272–275.
- **Collision risk in hook** (adversarial #6): the cleanup hook regex `worktree/agent-*` is a prefix match. If any surviving caller (or future caller) passes `name: "agent-..."` to `Agent(isolation: "worktree")` — plausible given §1a's literal pattern was `agent-{lifecycle-slug}` — the hook would delete the branch. Removing the hook removes this latent footgun.
- **Drift-note precedent in-repo** (adversarial #3): this repo does not use formal ADR files; design decisions live as inline bullets inside research-artifact files (e.g., `decomposed.md`'s DR-N pattern). Web-research's "canonical ADR practice (new DR file with superseded-by linkage)" does not match the repo's convention and should be ignored.
- **Worktree registry verification**: `git worktree list` shows one active non-default worktree (`worktree/outer-probe`, branch `worktree/outer-probe`). No `worktree/agent-*` branches exist on disk. The "remnant `.claude/worktrees/agent-*` directories" that Agent 1 initially reported are actually nested subdirectories *inside* the `outer-probe` worktree — the cleanup hook regex would never have matched them. The `outer-probe` worktree is unrelated to §1a and should be addressed separately from #097.
- **Option-rename is a routing-string change**, not cosmetic (adversarial #12): the AskUserQuestion option-label is also the dispatch-match substring at implement.md:25. #096's spec R8 explicitly states the rename will happen in #097 and routing must update in lock-step. The rename must touch both the option text (line 15) AND the post-selection dispatch string (line 25).
- **Tests are unaffected**: no test in `tests/` references §1a, `.dispatching`, `implementation_dispatch`, `dispatch_complete`, or the 4-option pre-flight shape. `tests/test_hooks.sh` does not cover the hook's worktree-prune branch. No test updates required; no new tests needed to preserve behavior (nothing is being preserved — all the behavior is being removed).

### Answers to the Clarify-phase open questions

1. **`hooks/cortex-cleanup-session.sh` `worktree/agent-*` handling**: safe to remove immediately. No live state uses the `agent-` prefix. The adversarial angle confirms the block is untested, has never cleaned live state, and could latently catch future unrelated `agent-*` callers.
2. **`.dispatching` marker usage**: exclusively §1a; §1b explicitly forgoes it (implement.md:114); removing the SKILL.md Step 2 "Dispatching Marker Check" sub-section is safe.
3. **"Worktree-Aware Phase Detection" scope**: exclusively `worktree/agent-*` pattern (implement.md:60-type pattern in SKILL.md Step 2); §1b uses `pipeline/{feature}` and has its own detection via `daytime-dispatch.json`. Safe to remove.
4. **DR-2 reversal note location**: `research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md:65` (inline annotation adjacent to DR-2). A top-level "Superseded-by" on the epic's `research.md` would incorrectly imply reversal of DR-1 and the modularization children (#075–#078), which stand.

## Web Research

Key prior-art findings that inform the approach:

- **Chesterton's Fence + Scream Test** (`fs.blog`, `thoughtbot`): before removing, surface *why it was built*; time-box proportional to stakes, then act. The **user is the only known consumer** and has ratified the removal — no need for indefinite preservation.
- **Lava Flow anti-pattern** (`sourcemaking.com`, Higginbotham): kept-but-unreachable code is explicitly called a smell. "Either live or gone from VCS-present state. Git history is the archive." This directly rejects Agent 1's "keep belt-and-suspenders" stance.
- **Feature-flag cleanup checklist** (DevCycle, Unleash, Moments Log): simplify conditional → remove functions called only from dead branch → remove imports unique to it → delete tests for dead branch → deepen coverage of kept path. Rule of thumb: "if removing the cleanup still leaves every live path covered, remove the cleanup." Applied here: removing the hook's worktree-prune block leaves every live path covered (no live path creates `worktree/agent-*` branches).
- **Kubernetes deprecation policy** (`kubernetes.io/docs/reference/using-api/deprecation-policy`): deprecate-with-warning is load-bearing when there are *external* users on a stable release train. For an internal single-user framework, hard-remove + rationale note is acceptable. Applies here.
- **ADR reversal canonical pattern** (AWS Prescriptive Guidance, Fowler, Microsoft Learn, adr.github.io): write a NEW ADR with Superseded-by linkage to old one. **Not applicable to this repo** — there are no formal ADRs; decisions live as inline DR bullets inside research artifacts. In-repo precedent is inline annotation.
- **Hyrum's Law** (`hyrumslaw.com`): observable behavior gets depended on regardless of contract. Mitigation: preserve rationale, not code.
- **GitHub anthropics/claude-code issue #39886**: `Agent(isolation: "worktree")` may silently fail — agent runs in main repo without isolation. Closed as duplicate (root cause tracked elsewhere). **Important re-read** (see adversarial #8): the one observed §1a success may have silently run without isolation; thin usage is not necessarily evidence of abandonment but may be evidence of silent noop. This affects framing in the drift note but does NOT change the decision.

## Requirements & Constraints

- **`requirements/multi-agent.md`** (quoted): Worktree Isolation outputs "Git worktree at `.claude/worktrees/{feature}/` … branch `pipeline/{feature}`"; Parallel Dispatch scopes concurrency "within an overnight session"; Agent Spawning says "Permission mode is always `bypassPermissions` for overnight agents." No requirement describes an interactive single-agent daytime `Agent(isolation: "worktree")` path. **Removal does not conflict.**
- **`requirements/project.md`**: "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct" and "Maintainability through simplicity" directly support removal.
- **`requirements/pipeline.md`**: entirely overnight-focused; silent on daytime interactive dispatch. No conflict.
- **`requirements/observability.md`**: references `events.log` but does not enumerate event types. Removing `implementation_dispatch (mode: "worktree")` and `dispatch_complete (mode: "worktree")` does not conflict with documented requirements.
- **`requirements/remote-access.md`**: neutral.

No blocking requirements. Alignment is strong with `project.md`'s simplicity and handoff-readiness principles.

## Tradeoffs & Alternatives

Within the settled "remove option 1" consensus, four dimensions are open:

### Dimension 1 — Scaffolding cleanup depth

- **A (Immediate full cleanup)**: delete §1a, delete hook's worktree-prune block, delete both SKILL.md Step 2 sub-sections, delete worktree-agent context guard at implement.md:18. **Recommended** — feature-flag cleanup rule ("if every live path is still covered, remove the cleanup"), Lava-Flow anti-pattern rejects kept-but-unreachable code, no live caller uses `worktree/agent-*`, hook block is untested and has latent collision risk with future `agent-*` callers.
- B (Staged — hook stays): delete §1a and routing, keep hook. **Rejected**: introduces exactly the "broken-but-reachable" state the Lava-Flow rule warns against.
- C (Delete §1a only, leave all scaffolding): minimal diff but leaves dead code. **Rejected** for the same reason.

### Dimension 2 — New recommended default

- **X ("Implement on current branch")**: #096 guard is designed for this choice; uncommitted-changes warning is in place. **Recommended** — ticket's proposed default; aligns with day/night split (daytime = close, trunk-safe for small scope).
- Y ("Create feature branch"): safer-by-ceremony but doesn't actually gain safety (git checkout also risks corruption); the #096 guard wasn't designed for it.
- Z (No recommended tag): abandons the research's evidence base.

### Dimension 3 — DR-2 reversal drift note location

- **T (Inline dated annotation at `decomposed.md:65`)**: where DR-2 literally lives; adjacent to the original decision; does not imply reversal of DR-1 or modularization children. **Recommended** — matches in-repo precedent of inline DR bullets; adversarial agent's verification confirmed this is the only location that doesn't mislead future readers.
- P (Backlog 074 amendment): retcons a closed epic's backlog item; brittle and non-idiomatic.
- Q (Top-level note on epic `research.md`): misleads — that file is cited by 7+ downstream tickets unaffected by this reversal.
- R/S (new drift-notes file or directory): over-engineers for a single reversal; no precedent in-repo.

### Dimension 4 — Rollout shape

- **M (Single PR)**: everything lands atomically. **Recommended** — reviewers see full delta; no intermediate state where SKILL.md's "Worktree-Aware Phase Detection" can still fire against events.log entries from an in-flight §1a dispatch.
- N (Two PRs): Agent 4 recommended this for risk-staging, but adversarial #4 identified that the intermediate state (routing gone, §1a body still exists, Worktree-Aware Phase Detection still fires) could trigger a `continue-in-worktree` / `dispatch-fresh` / `exit` prompt for a feature with no re-dispatch path. Worse than either endpoint.

### Cross-dimensional recommendation

**A + X + T + M**: single-PR atomic removal. One PR that (a) deletes §1a in full, (b) rewrites §1 pre-flight as three options with "Implement on current branch" recommended and label renamed in lock-step with the routing-match substring, (c) deletes both SKILL.md Step 2 sub-sections, (d) deletes the worktree-agent context guard at implement.md:18, (e) deletes the hook's worktree-prune block, (f) appends an inline dated annotation at `decomposed.md:65` citing ticket #097 and the rationale (thin-usage + maintenance-cost + #39886 silent-noop possibility), (g) appends a scope-amendment note to `backlog/110-...md` recording that `.dispatching` no longer exists.

## Adversarial Review

The critic challenged the 4-agent synthesis and surfaced these material corrections:

- **Agent 1's "remnant directories" claim was wrong**: `.claude/worktrees/outer-probe/*` subdirectories are inside the `outer-probe` worktree (a live git-registered worktree, branch `worktree/outer-probe`), not `worktree/agent-*` prefix siblings. The hook regex would not match them. The hook has therefore never cleaned live state — strengthens the case for removal, contradicts Agent 1's "keep it" recommendation.
- **Agent 4's drift-note location was wrong**: `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md` is referenced by 7+ downstream tickets (074, 075, 076, 077, 078, 079, 080) — a top-level "Superseded-by" note would falsely imply the entire epic is reversed. Inline annotation at `decomposed.md:65` (where DR-2 physically lives) is the correct location.
- **Agent 2's canonical ADR pattern doesn't apply**: this repo uses inline DR bullets, not formal ADR files.
- **Two-PR rollout has a worse intermediate state than Agent 4 realized**: between PR 1 (routing change) and PR 2 (§1a body delete), SKILL.md's "Worktree-Aware Phase Detection" block still fires on events.log with `dispatch_complete` but no subsequent `feature_complete`. Any resumed in-flight session would hit an AskUserQuestion prompt for a feature whose dispatch path no longer exists, with no path to re-invoke. Single-PR is safer.
- **Worktree-agent context guard at implement.md:18 becomes dead code**: no live path creates `worktree/agent-*` after §1a is gone. The guard's continued existence is a hidden admission that the cleanup hook should also stay — Agent 1's "keep guard + keep hook" stance is internally consistent but wrong; Agent 4's "remove both" is internally consistent and right.
- **SKILL.md Parallel Execution block at lines 392–406** still uses `Agent(isolation: "worktree")` for per-feature parallel dispatch. If any consumer passes `name: "agent-..."` (plausible — §1a used that literal pattern), the hook could delete the wrong branch. Another reason to remove the hook.
- **#39886 re-read**: the one observed §1a "success" (`devils-advocate-smart-feedback-application` 2026-04-12) may have silently run without isolation per #39886. Thin usage may be silent noop, not abandonment. Framing implication: the drift note at `decomposed.md:65` should explicitly reference #39886 so future readers understand the reversal is not "we removed a working feature" but "we removed a feature whose intended behavior was likely never delivered."
- **Porcelain guard doesn't catch gitignored dirty state** (stashes, `.env`, `.claude/settings.local.json`). Minor; the #096 spec acknowledged this.
- **Cross-ticket dependencies**: `backlog/110-...md` line 41 says "retain `.dispatching` marker check" — scope amendment needed after #097 lands. `backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md` should be verified for forward-dep compatibility before #097 lands.
- **Label rename is a routing-string change, not cosmetic**: #096's spec R8 says the routing match substring must be updated in lock-step. Adversarial flagged this explicit coupling (implement.md:25).
- **`outer-probe` worktree is active state unrelated to #097**: should be tracked in a separate ticket, not conflated with this removal.

### Mitigations incorporated into the recommendation

- Single-PR rollout (rejects Agent 4's N in favor of M).
- Inline annotation at `decomposed.md:65` only (rejects Agent 4's top-level research.md note).
- Delete the hook's worktree-prune block (overrides Agent 1's "keep it").
- Delete the worktree-agent context guard at implement.md:18 (Agent 1 said keep; adversarial shows it's entangled with hook deletion).
- Rename routing substring in lock-step with option label.
- Drift note must explicitly cite #39886 so the historical "1 success" event is reframed accurately.
- Append scope-amendment note to `backlog/110-...md`.
- Verify `backlog/123-...md` forward-dep before landing.

## Open Questions

All Clarify-phase open questions were resolved during research. Three questions remain open for Spec to resolve:

- **Scope of §1b renumber**: after §1a is deleted, should §1b (Daytime Dispatch) be renumbered to §1a? The document structure currently numbers the routing-condition alternate paths (§1a, §1b) with the numeric task-dispatch body following as §2–§4. Renumbering §1b → §1a is pure-text churn and could affect cross-references elsewhere (the skill itself is the only consumer; grep for §1b references). Spec should decide whether to renumber or leave the gap.
- **Ticket 123 forward-dep verification**: `backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md` — does this ticket assume option 1 still exists, or already plan for its removal? Spec must read the ticket and confirm #097 is compatible before landing.
- **Drift-note framing** — how much of the "#39886 silent-noop" framing should land in the `decomposed.md:65` annotation? Options: (a) terse note, one sentence, reversal-only; (b) two-sentence note including #39886 as reframe; (c) short paragraph with full context including #39886 + maintenance-cost + thin-usage. Spec decides narrative depth.

No contradictions remain between agents after adversarial synthesis. The hook-delete-vs-keep contradiction (Agent 1 vs Agent 4) was resolved via adversarial verification (outer-probe is live, not `agent-*` — hook has never cleaned what it was supposed to catch, so removal is correct).
