---
status: superseded
superseded_by: 0008
---

# `cortex init` consumer `CLAUDE.md` authorization surface

> **Superseded by [ADR-0008](0008-picker-selection-authorizes-enterworktree.md).** The consumer-`CLAUDE.md` authorization fence described below was removed: `cortex init` no longer writes any fence, and the lifecycle implement phase authorizes `EnterWorktree` via the user's live selection of the worktree picker option instead. The decision body is retained verbatim as historical record.

## Context

ADR-0003 declares `~/.claude/settings.local.json::sandbox.filesystem.allowWrite` as "the only write cortex-command makes outside its own tree." Approach A's auto-enter wiring requires `EnterWorktree(path=...)` authorization in the picker-suppressed path (per-repo `branch-mode: worktree-interactive` default). The live `EnterWorktree` schema gates the tool on *"explicit instruction [...] either by the user directly, or by project instructions (CLAUDE.md / memory)."* — the picker-suppressed path has no per-invocation user instruction, so authorization must come from a CLAUDE.md or memory file. A `.claude/cortex-authorizations.md` sibling file (considered) is neither CLAUDE.md nor user-scope memory and would silently fail the gate (Adversarial F5 in `research.md`).

## Decision

`cortex init` additively appends a fenced cortex-managed authorization clause to consumer `CLAUDE.md`. The fence carries a `version=N` attribute; replacement is gated on `fence-version < canonical-version` ("latest writer wins, no in-fence user edits respected"). The clause names the lifecycle skill, the `EnterWorktree` tool, and the `interactive/{slug}` path scope. Three subcommands manage the clause lifetime: `cortex init` (write/replace per stale predicate), `cortex init --revoke-worktree-auth` (remove; refuses on live session without `--force`), `cortex init --verify-worktree-auth` (probe with exit 0 OK / 1 absent / 2 stale). The `ensure_claude_md_authorization()` function mirrors `ensure_gitignore()`'s additive-idempotent shape.

## Three-criteria gate clearance

- **Hard to reverse**: existing installs that have run the new `cortex init` need backfill via `--revoke-worktree-auth` + re-init. The clause persists across `cortex init` runs (versioned-replace, not delete-on-next-run), so users carrying a stale or hand-edited fence must explicitly revoke before the new canonical body lands. Coordinated changes across `ensure_claude_md_authorization`, the `--revoke-worktree-auth` and `--verify-worktree-auth` subcommands, the lifecycle skill's §1a probe, and the canonical clause template would all have to move together to unwind the decision.
- **Surprising without context**: contributors expect `cortex init` to touch only `~/.claude/settings.local.json` per ADR-0003; extending to consumer `CLAUDE.md` is a real surface change. A contributor encountering the new write surface without this ADR would reasonably propose removing it as a scope creep on ADR-0003's "only write" claim.
- **Real trade-off**: the picker-fires-only alternative was considered and rejected because it degrades the Approach C convergence target (the suppressed-picker default loses the high-value auto-enter benefit); a sibling-file alternative was considered and rejected because the live schema names only `CLAUDE.md / memory`. See Alternatives section below.

## Fenced-block shape

The cortex-managed clause is wrapped in HTML comment sigils that carry a `version=N` attribute:

```
<!-- cortex-managed: lifecycle-worktree-auth version=N -->
<canonical clause body — names lifecycle skill, EnterWorktree tool, interactive/{slug} path scope; contains the literal word "worktree" per R6>
<!-- cortex-managed end -->
```

`N` is the canonical-clause version, incremented in cortex-command source whenever the canonical body changes. The "stale" predicate is `fence-version < current-canonical-version` — NOT byte-equality of body content. In-fence user edits do not change `version`, so they are silently overwritten on the next `cortex init` invocation by design. This is the "latest writer wins, no in-fence user edits respected" policy: users who need persistent customization should add prose outside the fence, which `ensure_claude_md_authorization` never touches. The canonical version starts at `1` and is incremented per release whenever the clause body changes (R5).

## Lifecycle of the clause

- **Write**: `cortex init` writes the canonical fence (with `version=N`) when absent, or replaces the fence body atomically when present-and-stale (`fence-version < canonical-version`). Present-and-current is a no-op. User-authored prose outside the fence sigils is never touched.
- **Verify**: the lifecycle skill's `implement.md` §1a path calls `cortex init --verify-worktree-auth` before each `EnterWorktree` invocation. Exit 0 means the fence is present at the current canonical version; exit 1 means absent; exit 2 means stale (`version` mismatch). On non-zero exit, the skill skips `EnterWorktree` and routes to the `cd`-shim fallback with a single-line diagnostic naming the probe result and pointing to `cortex init` to restore or refresh the clause. This makes the verify subcommand the canonical fix for upgrade-drift: existing installs running a newer lifecycle skill against an older clause text catch the mismatch on every §1a entry without requiring users to re-run `cortex init` manually.
- **Revoke**: `cortex init --revoke-worktree-auth` removes the fenced block from consumer `CLAUDE.md` idempotently (no-op if absent). If a live `cortex/lifecycle/sessions/*.interactive.pid` file exists in the consumer repo, the subcommand refuses with exit code 2 and a diagnostic listing the live session(s) unless `--force` is passed. With `--force`, the subcommand proceeds and the next `EnterWorktree` call in the live session will fail closed via the `--verify-worktree-auth` probe routing through the fallback path.
- **Uninstall**: `uv tool uninstall cortex-command` removes the CLI but does NOT touch consumer `CLAUDE.md`. The cortex-managed fence remains stranded as harmless prose: no active skill exists to act on it. The recommended pre-uninstall workflow is to run `cortex init --revoke-worktree-auth` first so the consumer's `CLAUDE.md` is clean. If the user skips that step, the post-uninstall dead-clause state is accepted as part of this decision — the stranded fence has no runtime effect because no consumer of the clause survives the uninstall, and a future re-install can re-add the fence via `cortex init` (versioned-replace policy applies if the fence was edited in the interim).

## Alternatives considered

- **`.claude/cortex-authorizations.md` sibling file (rejected)**: a separate authorization manifest in `.claude/` rather than appending to `CLAUDE.md`. Rejected because the live `EnterWorktree` schema names only `CLAUDE.md / memory` as eligible "project instructions" surfaces (verbatim: *"Never use this tool unless 'worktree' is explicitly mentioned by the user or in CLAUDE.md / memory instructions"*). A sibling file would silently fail the gate at runtime — Claude would have no documented obligation to treat it as authorization. This was surfaced as Adversarial F5 in `research.md`.
- **Picker-fires-only path (rejected)**: skip the suppressed-picker default entirely and require users to select "feature branch with worktree" from the picker on every implement invocation, providing the user-direct "worktree" mention each time. Rejected because it degrades Approach C's convergence target — the per-repo `branch-mode: worktree-interactive` default exists precisely so users who have settled on the worktree workflow stop re-confirming the same choice. Forcing the picker to fire defeats the purpose of the per-repo default and eliminates the high-value auto-enter benefit for the steady-state case.
- **Pure `memory/` file write rather than `CLAUDE.md` append (deferred)**: write authorization to a `.claude/memory/` file rather than appending to `CLAUDE.md`. Not formally rejected; deferred because the live schema names `CLAUDE.md / memory` as alternatives and either surface satisfies the gate. `CLAUDE.md` was selected for the first implementation because it is the canonical project-instructions surface a contributor will read first; memory files are session-scoped and less discoverable. A future variant landing the clause in `memory/` instead can be considered if `CLAUDE.md` appendation produces unexpected friction.
