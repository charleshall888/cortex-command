---
status: accepted
---

# ADR-0005: Repo-relative worktree placement

## Context

Same-repo worktree placement has been debated twice. The first placement (`<repo>/.claude/worktrees/`) was replaced in lifecycle `restore-worktree-root-env-prefix` by `$TMPDIR/cortex-worktrees/` based on the (empirically false) premise that the `.mcp.json` Seatbelt deny blocks `git worktree add` into `.claude/`. This ticket (#260) reverts to the repo-relative placement after an empirical probe (2026-05-20) confirmed that `git worktree add .claude/worktrees/<name>` succeeds, `.mcp.json` propagates correctly into the worktree, and agent writes to `.mcp.json` remain denied (the deny is filename-scoped and blocks agent writes; it does not block `git worktree add` from creating the worktree directory or checking out other files).

The TMPDIR placement also produced a class of latent failures: terminal shells on macOS get `/var/folders/.../T/` while Claude Code sessions get `/tmp/claude-$UID/`, so worktrees created by `cortex init` in one shell were not findable by sessions in the other. The per-shell registration step in `cortex init` Step 7b registered a TMPDIR-base path in user settings, but the path was specific to the registering shell and silently mismatched any other session's `TMPDIR`. Repo-relative placement eliminates this divergence entirely.

## Decision

Same-repo worktrees live at `<repo>/.claude/worktrees/<feature>/`, computed as a pure function of the repo root with no environment-variable participation. Resolution is centralized in `resolve_worktree_root()` in `cortex_command/pipeline/worktree.py` (the single chokepoint consumed by the `WorktreeCreate` hook, interactive lifecycle dispatch, and overnight pipeline dispatch). The `cortex init` Step 7b worktree-base registration is deleted; `cortex init --update` gains a migration that expunges stale `cortex-worktrees`-prefixed entries from prior versions. Cross-repo overnight worktrees (branch d) remain TMPDIR-based pending a separate follow-up.

## Trade-offs

TMPDIR placement enables OS-managed ephemeral cleanup but requires a per-shell registration step that creates inherent divergence between terminal `TMPDIR` and Claude Code session `TMPDIR`. Repo-relative placement requires no registration, is stable across all shells and sessions, aligns with Anthropic's own native worktree convention (`agent-a<hex>/` directories under `.claude/`), and is gitignored at the project level. The cost is that worktrees persist until explicitly cleaned (no OS eviction) — acceptable given that `cleanup_worktree()` handles this and git manages the administrative references via `git worktree prune`.

## Alternatives considered

- **Keep TMPDIR placement and fix the divergence with a shell-agnostic registration mechanism.** Rejected: the divergence is structural (Claude Code's `TMPDIR` is forced by the launcher and cannot be aligned with the user's terminal shell without invasive launchd modification on macOS). Any registration scheme would still leak across shells the registration step never ran in.
- **Keep TMPDIR placement and use a sentinel-suffix marker in `allowWrite` (branch b).** Rejected: this was the prior implementation; it adds a parallel resolution path and a fragile marker-string contract, and it doesn't address the underlying `TMPDIR` divergence. Removed in this ticket.
- **Place worktrees outside both `.claude/` and `TMPDIR` (e.g., `~/.cache/cortex/worktrees/<repo>/<feature>`).** Rejected: introduces a new sandbox grant requirement, fragments worktree state across repos, and doesn't align with Anthropic's own convention.
