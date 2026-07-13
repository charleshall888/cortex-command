---
schema_version: "1"
uuid: ce0be7d3-669a-44e7-b1bd-3c1c89ec072a
title: "Revert TMPDIR worktree placement and restore .claude/worktrees/ default"
status: complete
priority: high
type: bug
created: 2026-05-20
updated: 2026-05-25
session_id: null
lifecycle_phase: complete
lifecycle_slug: revert-tmpdir-worktree-placement-and-restore
complexity: complex
criticality: high
spec: cortex/lifecycle/revert-tmpdir-worktree-placement-and-restore/spec.md
areas: [pipeline,tests]
---
## Why

Interactive lifecycle execution silently fails to enter Variant-A worktrees whenever the Claude Code session's `TMPDIR` differs from the shell that ran `cortex init`. The user-visible symptom is `§1a:iv preflight check failed — settings.local.json registration not found`, even after a fresh `cortex init --update`. On macOS this divergence is the default: terminal shells get `/var/folders/.../T/` and Claude Code sessions get `/tmp/claude-$UID/`. Operators are forced into ad-hoc workarounds (`TMPDIR=… cortex init`, manual settings edits) on every machine, every install. The root cause is that worktree path resolution depends on a per-process environment variable while sandbox registration is per-user — divergence is inherent, not a configuration bug.

## Role

Restore same-repo worktree placement to `<repo>/.claude/worktrees/<feature>/` — the location Anthropic's own native subagent isolation uses — and remove the `cortex init` step that registers a worktree base in `allowWrite` and `additionalDirectories`. Once this piece lands, the worktree path is computed identically in every shell, every session, every install, because no environment variable participates in its computation; and the sandbox already covers the path via the existing project-trust grant on `.claude/`. The piece eliminates the entire class of "registration in shell A does not match creation in shell B" failures, and aligns cortex with the convergent industry pattern (Anthropic native, claude-squad, agentinterviews, Aider tutorials all use repo-relative or home-dotdir stable paths).

## Integration

Lands on the `resolve_worktree_root` chokepoint: branch (c) (same-repo default) returns `<repo>/.claude/worktrees/<feature>` instead of the current `$TMPDIR/cortex-worktrees/<feature>`. The `WorktreeCreate` hook contract is unchanged — the hook continues to route through `cortex-worktree-resolve` and that resolver is the single source of truth. The `cortex init` registration contract loses one step entirely (worktree-base registration); the umbrella `cortex/` registration is unaffected. The `.mcp.json` sandbox-deny invariant is explicitly preserved as correct security policy — the previous lifecycle's premise that the deny blocks `git worktree add` was empirically refuted (verified May 20: `git worktree add .claude/worktrees/<name>` succeeds, the resulting worktree contains `.mcp.json`, and Anthropic's native `agent-a<hex>/` worktrees demonstrate the same behavior daily). Overnight cross-repo worktrees (branch (d) of the resolver) remain TMPDIR-rooted and are out of scope for this ticket — they need a separate home-dotdir destination because no single-repo trust grant applies to them.

## Edges

- The `.mcp.json` sandbox deny must be preserved unmodified. It is intentional defense-in-depth against prompt-injection persistence: `.mcp.json` registers MCP server invocation commands that auto-execute on every session, so the deny prevents a compromised session from escalating to persistent code execution. The previous lifecycle misread the deny's scope; this ticket explicitly affirms the deny is correct and does not attempt to bypass it.
- Must not break Anthropic's native `Agent(isolation: "worktree")` dispatch path, which already lands worktrees at `.claude/worktrees/agent-a<hex>/` without cortex involvement.
- Out of scope: overnight cross-repo worktree placement (branch (d) of the resolver). A follow-up ticket should move cross-repo worktrees to a stable home-dotdir like `~/.cortex/overnight-worktrees/` with a one-time `additionalDirectories` registration owned by overnight setup, not `cortex init`.
- Out of scope: migration of existing TMPDIR-based worktrees. They retain their original ephemeral semantics — let them age out via reboot or explicit cleanup.
- Out of scope: any change that would let cortex write through the `.mcp.json` deny. If a future task legitimately needs to modify `.mcp.json`, it goes through user-approved `dangerouslyDisableSandbox` or an explicit `excludedCommands` carve-out — not a cortex code path.
- Supersedes `restore-worktree-root-env-prefix` (closed May 15). That lifecycle's research artifact contains the false assertion that `.mcp.json` deny structurally blocks `git worktree add`; this ticket's empirical probe refutes it. The lifecycle dir must be marked superseded with a back-link to this ticket so the misdiagnosis is preserved in history rather than silently overwritten.
- Must not introduce a `team_name` parameter on any `Agent(isolation: "worktree")` call. Anthropic GitHub #33045 documents that the combination silently fails; cortex currently does not use `team_name` anywhere and that invariant is load-bearing.
- Skill prose and documentation that asserts "same-repo worktrees go to TMPDIR to escape the `.mcp.json` deny" is now misleading — every such assertion is updated in lockstep with the code change so future contributors are not led back to the same misdiagnosis.

## Touch points

- `cortex_command/pipeline/worktree.py:213-223` — branch (c) currently returns `Path(os.environ.get("TMPDIR", "/tmp")).resolve() / "cortex-worktrees" / feature`; revert to `(repo_root / ".claude" / "worktrees" / feature).resolve()`.
- `cortex_command/pipeline/worktree.py:5-17` — module docstring claims same-repo worktrees live in TMPDIR "to escape `.mcp.json` deny"; rewrite to reflect repo-relative placement.
- `cortex_command/pipeline/worktree.py:183-186, 218-222` — branch-(c) docstring and inline comment assert ".mcp.json deny blocks git worktree add" — empirically false; remove and replace with the correct rationale (Anthropic-aligned default, project trust covers the path).
- `cortex_command/init/handler.py:200-211` — Step 7b: `worktree_base = _resolve_worktree_base(); settings_merge.register(...); settings_merge.register_additional_directories(...)`. Delete entirely.
- `cortex_command/init/handler.py:216-234` — `_resolve_worktree_base()` helper becomes dead code after Step 7b removal; delete.
- `cortex/lifecycle/restore-worktree-root-env-prefix/research.md` — `.mcp.json Seatbelt deny mechanism` section asserts the deny is structurally unavoidable; annotate the artifact as superseded with a back-link to this ticket. Do not delete — preserve as historical record.
- `cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` — same supersedes annotation.
- `cortex/requirements/multi-agent.md:30,77` — requirement-level statement "same-repo worktrees go to `.claude/worktrees/` by design"; this becomes true again after the revert. No edit needed beyond verifying alignment.
- `cortex/requirements/pipeline.md:165-167` — hardcoded-deny constraint text; update to reflect that the deny is filename-scoped to `.mcp.json` and does not block `git worktree add`.
- `skills/lifecycle/references/parallel-execution.md:14,17` — text "creates the worktree outside the sandbox write path"; rewrite to describe the repo-relative placement and the project-trust coverage.
- `skills/lifecycle/references/implement.md:200,202` — operator instructions reference `git worktree remove .claude/worktrees/<task-name>`; restored to correct after revert.
- `skills/overnight/SKILL.md:133` — verify any same-repo path assertions; overnight cross-repo path is unchanged in scope.
- `docs/internals/pipeline.md:139` — pipeline internals worktree-placement paragraph; rewrite.
- `docs/internals/sdk.md:29,144,160` — SDK doc worktree references; align with new placement.
- `claude/hooks/cortex-worktree-create.sh:39-42` — calls `cortex-worktree-resolve <NAME>`; hook body needs no edit because the resolver chokepoint changes underneath it. Add a short comment naming the new default for grep-discoverability.
- `bin/cortex-archive-rewrite-paths:62` — path-rewriter logic recognizes TMPDIR placement; update to recognize `.claude/worktrees/` as the canonical same-repo location.
- `tests/test_worktree.py:309-322` — `test_branch_c_default_same_repo` and adjacent fallthrough tests assert TMPDIR path; revert assertions to `<repo>/.claude/worktrees/`.
- `tests/test_worktree.py` (new) — add an integration test that creates a worktree via `git worktree add .claude/worktrees/<probe>` and asserts both `.mcp.json` propagation success and direct-write deny on `.mcp.json` afterwards. Pins the empirical invariant so future contributors cannot regress to the misdiagnosis without a red test.
- `tests/test_init_worktree_registration.py` — was deleted in the previous lifecycle; do not restore. Step 7b removal makes registration tests permanently moot.
- `tests/test_hooks.sh:164,199,220,235` — assertions on resolver output path; update.
- `bin/cortex-check-parity:69` — comment references `$TMPDIR/cortex-worktrees/<feature>`; update.