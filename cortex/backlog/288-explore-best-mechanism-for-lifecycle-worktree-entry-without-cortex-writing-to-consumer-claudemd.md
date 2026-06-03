---
schema_version: "1"
uuid: dc4fee16-1ced-4158-98dd-d70634b71d00
title: "Explore: best mechanism for lifecycle worktree entry without cortex writing to consumer CLAUDE.md"
status: complete
priority: medium
type: feature
created: 2026-06-03
updated: 2026-06-03
tags: [cortex-init, distribution, claude-md, worktree-auth, exploration]
lifecycle_phase: research
lifecycle_slug: explore-best-mechanism-for-lifecycle-worktree
complexity: complex
criticality: high
spec: cortex/lifecycle/explore-best-mechanism-for-lifecycle-worktree/spec.md
areas: ['lifecycle']
---

> **Reconciliation (ADR-0008):** Option B was chosen and implemented under this lifecycle (`explore-best-mechanism-for-lifecycle-worktree`): cortex writes no consumer-`CLAUDE.md` fence; the user's live picker selection authorizes `EnterWorktree`; the suppressed-picker path routes structurally to the cd-shim (ADR-0008). The touch-points below that name `live_interactive_sessions`, the `claude_md_authorization.md` template, the `--verify-worktree-auth` probe, and `handler.py` steps 0b/0c/6b are **historical** — that fence apparatus was removed. The Complete phase sets this ticket's final status.

## Why

`cortex init` currently splices a cortex-managed `EnterWorktree` authorization fence into a repo's `CLAUDE.md` (ADR-0006, `accepted`). The operator's objection: cortex should not be editing **other repos'** human-curated `CLAUDE.md` files. This breaches ADR-0003's "the only write cortex makes outside its own tree is `~/.claude/settings.local.json`" invariant for consumer repos.

The deeper question underneath the objection: the *only* reason `CLAUDE.md` is involved at all is the platform `EnterWorktree` tool's authorization gate. So this is really a question about **how the lifecycle implement phase should enter an interactive worktree** — and whether it should depend on the platform tool's permission model at all. The answer determines whether cortex needs to write anywhere outside `cortex/`.

**This ticket is an EXPLORATION, not a pre-decided implementation.** Determine the genuinely best option from first principles. A prior session produced a research artifact that *leaned* toward full removal — treat that lean as one hypothesis to stress-test, not as the answer.

## What to decide

Pick the best mechanism for authorizing/performing interactive-worktree entry in the lifecycle implement phase, optimizing for: (1) cortex writes nothing into repos it does not own; (2) the implement phase stays correct and ergonomic; (3) minimal long-term maintenance burden; (4) a durable decision, not churn that gets partly reverted. Land on ONE recommendation with an explicit rationale and the rejected alternatives.

## Candidate options to evaluate (neutral — do NOT pre-rank; add others if found)

- **A. Full removal / cd-shim only.** Drop the `EnterWorktree` tool call and the entire fence apparatus; the skill owns worktrees via `git worktree add` + `cd`. Zero footprint anywhere. Cost: loses the platform tool's whole-session re-root (orchestrator CWD stays at repo root; file tools need absolute worktree paths; risk of a stray edit landing in the main checkout).
- **B. Per-invocation authorization (no standing fence anywhere).** Keep using `EnterWorktree`, but rely on a *live* user "worktree" mention to authorize it per-turn — e.g. the user typing "worktree", selecting the branch-picker "feature branch with worktree" option, or the `/lifecycle` invocation itself. If a live selection/invocation reliably satisfies the gate, this keeps `EnterWorktree`'s benefits with zero repo footprint. **Hinges entirely on the empirical gate test below.**
- **C. Relocate the standing authorization to a cortex-owned surface.** Keep `EnterWorktree`; move the clause out of `CLAUDE.md` into something cortex owns (`.claude/memory/…`, `.claude/rules/…`, etc.). Verify which of these the live `EnterWorktree` gate actually honors and whether the surface is repo-portable vs. machine-local.
- **D. Opt-in flag, default off.** Keep the fence machinery but write it only on an explicit opt-in verb/config; foreign repos are never touched by default; cortex-command's own repo (and anyone who wants auto-enter) opts in. Mirrors the `cortex-init-scope-reduction` (#273) conclusion of "write outside cortex/ only on an explicit opt-in verb."
- **E. Foreign-skip.** Keep writing the fence, but only in repos the user has consented to / cortex "owns"; skip repos it doesn't. Requires a reliable "is this a foreign repo" signal — assess whether one exists that isn't fragile.
- **F. Status quo (ADR-0006 as-is).** The null option, included for honest comparison.

## Load-bearing questions to resolve EMPIRICALLY (do not assume — test)

1. **The gate question (most important):** Does the platform `EnterWorktree` tool actually fire when authorized by (a) the user *selecting* a picker option whose label contains "worktree", (b) the user typing "worktree" in a `/lifecycle` argument, or (c) only by a standing `CLAUDE.md`/memory clause? The tool's schema says: *"Never use this tool unless 'worktree' is explicitly mentioned by the user or in CLAUDE.md / memory instructions."* Web research could not confirm whether a *click* counts. **Run a real dispatch and observe whether `EnterWorktree` is invoked** under each path. This single fact decides whether option B is viable and reshapes A/C/D/E.
2. **What does cd-shim actually cost on a real implement run?** Measure, don't theorize: does the orchestrator session reliably edit the worktree (via absolute paths) without straying into the main checkout? Is stale cached context a real problem? Does sub-agent `isolation:"worktree"` dispatch (the parallel task work) behave identically regardless of entry mechanism?
3. **Which authorization surfaces does the live gate honor, and are they repo-portable?** Confirm whether `.claude/memory/`, `.claude/rules/`, `CLAUDE.local.md`, etc. satisfy the gate, and which travel with the repo vs. are machine-local/Claude-owned.
4. **Is interactive-worktree entry even worth keeping?** The operator has reported interactive-worktree instability. Quantify how much the orchestrator-session-in-worktree behavior is actually used/valued vs. the sub-agent isolation that does the real work.

## How to research (symmetric — guard against motivated reasoning)

For each surviving option, dispatch the angle three ways, not one: (a) a strongest-advocate defense of the option, (b) a failure-mode attack that tries to kill it, (c) a neutral comparator that ranks it against the others on the decision criteria. Three agents pointing the same direction is not convergence. Explicitly challenge the prior research's lean toward full removal: have an agent argue *for* keeping `EnterWorktree`/auto-enter and surface what full-removal would lose.

## Hard constraints / context the exploration must respect

- **Auto-enter is shipped, not speculative.** #249 ("auto-enter worktree, drop the cd handoff") and #250 ("auto-enter via EnterWorktree, Approach A") are both `status: complete`, high-criticality, shipped ~2 weeks ago; ADR-0006 is `accepted`. A reversal must mark these superseded/wontfix and supersede ADR-0006 properly (`status: superseded` + `superseded_by` + new ADR). Full removal that leaves "complete" tickets describing deleted machinery is a state-integrity defect.
- **ADR-0004:** worktree *creation* is always `git worktree add` (the `--worktree`/`WorktreeCreate`-hook bypass is permanent). `EnterWorktree` is only the orchestrator's CWD-switch. The Complete phase spans sessions (exit → re-invoke after merge), and `ExitWorktree` is a cross-session no-op — assess whether the platform tool's enter/exit lifecycle even fits cortex's multi-step Complete.
- **Single call site:** the only `EnterWorktree` invocation is `skills/lifecycle/references/implement.md` §1a step-v, behind a `cortex init --verify-worktree-auth` probe that already falls back to the cd-shim on any non-zero exit. The cd-shim is therefore already the live path in any repo without the fence.
- **Dual-source:** `skills/`/`SKILL.md` edits mirror into `plugins/cortex-core/` via `just build-plugin` (commit canonical+mirror together); `cortex_command/init/*` ships in the wheel (not mirrored).
- **Kept-pauses parity:** the §1 branch-picker pause stays; `skills/lifecycle/SKILL.md` inventory and `tests/test_lifecycle_kept_pauses_parity.py` move together if the entry's conditionality changes.
- **Authoring policy:** What/Why-not-How; no new MUST without an evidence artifact.
- **Blast radius is currently clear:** only `main`, no live `*.interactive.pid` sessions — but any migration must still guard on `live_interactive_sessions` for the general consumer case.

## Required output ("done" looks like)

A decision artifact (research.md + spec if run through `/cortex-core:lifecycle`) that:
1. Reports the empirical gate-test result (Q1) — the fact the recommendation rests on.
2. Recommends ONE option with a rationale tied to the decision criteria, and states why each other option loses.
3. Specifies the blast radius / migration / test changes for the chosen option, including how existing fences (this repo + consumers) are handled and how #249/#250/ADR-0006 are reconciled.
4. Calls out explicitly whether the choice is durable or risks churn, per the Solution-Horizon principle.

## Prior art & inputs (challenge, don't inherit)

- `cortex/lifecycle/archive/init-skip-foreign-claude-md/research.md` — prior research from the originating session (8 angles + adversarial), now archived/superseded by this ticket. **Its lean toward full removal is a hypothesis to stress-test, not a conclusion.**
- `cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md` (the decision under question; note its rejected `.claude/cortex-authorizations.md` sibling-file alternative and deferred `memory/` alternative).
- `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md`, `cortex/adr/0003-*`.
- `#249`, `#250` (shipped auto-enter), `#273` (`cortex-init-scope-reduction`, the related "opt-in verb" conclusion).
- `cortex_command/init/scaffold.py` (fence functions), `cortex_command/init/handler.py` (steps 0b/0c/6b), `skills/lifecycle/references/implement.md` §1a, `cortex_command/init/templates/claude_md_authorization.md`.
