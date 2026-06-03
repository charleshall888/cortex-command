---
status: accepted
---

# Picker selection authorizes `EnterWorktree`; cortex writes no consumer `CLAUDE.md` fence

## Context

[ADR-0006](0006-cortex-init-consumer-claude-md-authorization-surface.md) had `cortex init` append a cortex-managed authorization fence to consumer `CLAUDE.md` so that the picker-suppressed worktree path (per-repo `branch-mode: worktree-interactive`) could satisfy the live `EnterWorktree` schema, which gates the tool on *"explicit instruction [...] either by the user directly, or by project instructions (CLAUDE.md / memory)."* That made `cortex init` write outside its own tree into consumer `CLAUDE.md` — a second outside-tree write beyond the `~/.claude/settings.local.json` grant ADR-0003 named as "the only write cortex-command makes outside its own tree." The fence apparatus (scaffold functions, a template, two CLI verbs `--revoke-worktree-auth`/`--verify-worktree-auth`, and a §1a verify probe) was contested as scope creep on ADR-0003's invariant.

The research session for backlog #288 ran the load-bearing empirical test live: it revoked this repo's own fence and confirmed that the `EnterWorktree` gate is **soft** — the harness accepted a fence-free `EnterWorktree` call that followed a live picker selection of the worktree-labeled option; only the `path=` argument is hard-checked against `git worktree list`. The user's live selection of the worktree picker option *is* the user-direct "worktree" mention the schema requires, so no persisted clause is needed on the path where the picker fires.

## Decision

`cortex init` writes **no** authorization clause to any `CLAUDE.md`. Authorization for `EnterWorktree` comes from the lifecycle implement phase's two entry modes:

- **Picker-fired path** (the user selects "Implement on feature branch with worktree", or `branch-mode: prompt`): the live selection is the user-direct "worktree" mention, so the implement phase calls `EnterWorktree(path=...)` directly. This is the steady-state path.
- **Suppressed-picker path** (`branch-mode: worktree-interactive`, where the picker does not fire): there is no per-invocation user mention and no persisted authorization, so the implement phase routes **structurally** to the cd-shim (`cd $(cortex-worktree-resolve interactive/{slug})`) instead of calling `EnterWorktree`. The worktree is still created and used; only the orchestrator re-root is skipped.

The structural routing is a carried entry-mode signal threaded from §1's branch-mode preflight into §1a, not a runtime soft-gate decline — a test pins the suppressed branch so a soft-gate-only implementation (one that keeps the `EnterWorktree` call and relies on the runtime fallback) fails the suite.

## Trade-off

The suppressed-picker path loses the `EnterWorktree` orchestrator re-root (its CWD reset and cache-clear side effect), degrading to the cd-shim. This is accepted because that path is a never-fired power-user opt-in — no repo sets `branch-mode: worktree-interactive` in practice — and the cd-shim is a deterministic floor: the interactive worktree is still materialized and the session still operates from inside it. The high-value auto-enter benefit is preserved exactly where users actually are (the picker-fired path).

## Three-criteria gate clearance

- **Hard to reverse**: restoring the fence model would require coordinated changes across the scaffold fence functions, the template, the two CLI verbs, the init-ensure namespace, the §1a verify probe, and a re-supersession of this ADR — the same coupled surface ADR-0006 named, now removed in one PR.
- **Surprising without context**: a contributor reading `implement.md` §1a calls `EnterWorktree` with no preceding authorization write would reasonably assume an authorization step is missing and propose restoring the fence. This ADR records that the picker selection *is* the authorization, grounded in the empirical gate test.
- **Real trade-off**: the persisted-fence alternative is the superseded predecessor (ADR-0006); the picker-fires-only model it rejected is the model adopted here, and the suppressed-picker path's loss of re-root is the accepted cost.

## Relation to ADR-0003

Removing the consumer-`CLAUDE.md` fence write restores ADR-0003's invariant for consumers: the only write cortex-command makes outside its own tree is `~/.claude/settings.local.json`. The tension the fence introduced lived inside ADR-0006; this ADR resolves it.

## Alternatives considered

- **Persisted consumer-`CLAUDE.md` fence (rejected — was [ADR-0006](0006-cortex-init-consumer-claude-md-authorization-surface.md))**: keep the versioned fence so the suppressed-picker path retains `EnterWorktree` re-root. Rejected because it is a second outside-tree write that the empirical gate test showed is unnecessary on the picker-fired path, and because the suppressed-picker path it served has never fired in practice.
- **Soft-gate runtime decline (rejected)**: keep a single `EnterWorktree` call site in §1a and rely on the runtime fallback to decline it on the suppressed path. Rejected because it is not structurally enforceable — a model could invoke the tool anyway — and a documentation-parity test could not pin the intended skip. The decision routes the suppressed path structurally instead.
