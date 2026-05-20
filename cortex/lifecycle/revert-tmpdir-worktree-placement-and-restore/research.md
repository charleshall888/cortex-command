# Research: Revert resolve_worktree_root branch (c) from TMPDIR-based placement to repo-relative .claude/worktrees/ default, remove cortex init Step 7b registration, delete dead branch-(b) sentinel machinery, and update all code/docs/tests/requirements asserting TMPDIR placement

## Codebase Analysis

### Files that will change

**Core implementation (2 files):**
- `cortex_command/pipeline/worktree.py` — branch (c) lines 217–223 (revert path), module docstring lines 5–17 (update rationale), function docstrings lines 183–186 and 218–222 (remove false deny-blocks-git assertion), delete `_registered_worktree_root()` lines 119–161 and its branch-(b) call site in `resolve_worktree_root()`
- `cortex_command/init/handler.py` — delete Step 7b lines 200–211 and `_resolve_worktree_base()` helper lines 216–234

**Tests (2 files + test_settings_merge.py):**
- `tests/test_worktree.py` — revert branch-(c) assertions in `test_branch_c_default_same_repo` (lines 330–344), update `TestVerifyR1BranchCTmpdirDefault` class (lines 447–461), update `TestVerifyR5NegativeProperty` (line 652), delete branch-(b) sentinel tests, add new integration test for `.mcp.json` propagation + deny invariant. Note: `_repo_root()` is now called from branch (c)'s happy path — test mocking must patch `_repo_root` (or `subprocess.run`) for non-git-repo contexts.
- `tests/test_hooks.sh` — update resolver output path assertions at lines 164, 189, 199, 220, 224, 235
- `tests/test_settings_merge.py` — delete three `test_worktree_base_*` integration tests that call `init_main()` and assert TMPDIR in `allowWrite`/`additionalDirectories` (lines ~1067–1156). The `register_additional_directories` function itself is not dead code; only the init-flow integration tests are removed.

**Skills and references (3 files):**
- `skills/lifecycle/references/parallel-execution.md` — lines 14, 17: rewrite "creates the worktree outside the sandbox write path" to describe repo-relative placement and project-trust coverage
- `skills/lifecycle/references/implement.md` — lines 200, 202: restore `git worktree remove .claude/worktrees/<task-name>`; also update pre-flight check (lines 132–182) that currently validates TMPDIR-based `additionalDirectories` — replace with a check appropriate for repo-relative location
- `skills/lifecycle/references/complete.md` — line 183: update worktree-path substring from `cortex-worktrees/interactive-{slug}` to `.claude/worktrees/interactive-{slug}`; otherwise cleanup silently skips all interactive lifecycle completions
- `skills/overnight/SKILL.md` — line 133: verify any same-repo path assertions (overnight cross-repo stays TMPDIR-based)

**Operational docs (2 files):**
- `docs/internals/pipeline.md` — line 139: rewrite worktree-placement paragraph
- `docs/internals/sdk.md` — lines 29, 144, 160: align worktree references

**Requirements (2 files):**
- `cortex/requirements/multi-agent.md` — lines 30 and 77: update from `$TMPDIR/cortex-worktrees/{feature}/` to `<repo>/.claude/worktrees/{feature}/`; rewrite line 77's rationale from "Seatbelt deny blocks git worktree add" to "Anthropic-aligned repo-relative default, project trust covers the path"
- `cortex/requirements/pipeline.md` — lines 165–167: update deny-constraint text to reflect `.mcp.json` deny is filename-scoped, not directory-scoped, and does not block `git worktree add`

**Utility scripts (3 files):**
- `claude/hooks/cortex-worktree-create.sh` — lines 39–42: add comment naming `.claude/worktrees/` as new default for grep-discoverability
- `bin/cortex-archive-rewrite-paths` — line 62: comment AND functional fix — must add `.claude/worktrees/` (or `.claude/`) to `EXCLUDED_DIR_NAMES` so the path-rewriter doesn't walk into worktree copies of lifecycle docs (the worktrees now live inside the repo tree)
- `bin/cortex-check-parity` — line 69: update comment from `$TMPDIR/cortex-worktrees/<feature>` to `.claude/worktrees/<feature>`

**Infrastructure (1 file):**
- `cortex_command/init/scaffold.py` — `ensure_gitignore()` / `_GITIGNORE_TARGETS`: add `.claude/worktrees/` so `cortex init` appends the pattern to user repos' `.gitignore`. Without this, overnight-target repos will show worktrees as untracked in `git status`.

**Historical artifacts (2 files, annotated not deleted):**
- `cortex/lifecycle/restore-worktree-root-env-prefix/research.md` — annotate as superseded by ticket #260 with a back-link; preserve the `.mcp.json` Seatbelt deny section as historical misdiagnosis record
- `cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` — same supersedes annotation

**Seatbelt probe (1 file):**
- `cortex_command/pipeline/seatbelt_probe.py` — line 164: `allow_paths=[str(tmpdir_resolved)]` currently only allows `$TMPDIR`. After the revert, `resolve_worktree_root()` returns `<repo>/.claude/worktrees/<feature>` which is NOT under `$TMPDIR`. The probe will report failure on every overnight session. Must add the repo's `.claude/worktrees/` path, or restructure the test since the path is project-trust covered rather than needing an explicit sandbox grant.

### Relevant existing patterns

- **Resolver chokepoint pattern**: `resolve_worktree_root()` is the single source of truth for all 5 dispatch paths (create_worktree, daytime_pipeline, readiness, cleanup_worktree fallback, worktree-create hook). `cleanup_worktree()` already routes through it — no code change needed there.
- **Branch (a)/(d) precedence unchanged**: `CORTEX_WORKTREE_ROOT` env-var override (branch a) and cross-repo overnight worktrees (branch d) are unaffected.
- **`.resolve()` canonicalization**: branch (c) must call `.resolve()` on the repo-relative path for consistency with Seatbelt path comparisons (macOS symlinks: `/private/var/folders/...` vs `/var/folders/...`).
- **Test isolation**: tests use `monkeypatch.setenv("TMPDIR", ...)` and `patch` for `_repo_root`. After revert, branch (c) calls `_repo_root()` — tests that call `resolve_worktree_root()` without a real git repo need `_repo_root` patched.

### Integration points and dependencies

- `create_worktree()` at line 257 calls `resolve_worktree_root()` — inherits new path automatically
- `cleanup_worktree()` at line 386 calls `resolve_worktree_root()` — already routed through chokepoint
- `claude/hooks/cortex-worktree-create.sh` shells out to `cortex-worktree-resolve` — hook body unchanged; resolver output changes underneath
- `sandbox_settings.py:156` `build_dispatch_allow_paths()` uses `str(worktree_path)` and `str(worktree_path.resolve())` — will work correctly with repo-relative paths; no collision with orchestrator deny entries

## Web Research

The ecosystem has converged strongly on repo-relative hidden-directory worktree placement.

**Anthropic native**: Claude Code's `Agent(isolation: "worktree")` and `claude --worktree` use `<repo>/.claude/worktrees/<name>/` by default. The Claude Code docs explicitly recommend adding `.claude/worktrees/` to `.gitignore`. No TMPDIR involvement.

**Gemini CLI**: uses `.gemini/worktrees/` — identical pattern, different namespace.

**claude-squad**: places worktrees at `.claude/worktrees/[name]/`.

**TMPDIR anti-pattern**: macOS aggressively cleans TMPDIR; git retains `.git/worktrees/<name>/` references even after the directory is deleted, requiring `git worktree prune`. Git 2.46 introduced `worktree.useRelativePaths` — signal the ecosystem is moving toward relative paths. Long-running branches are unsuitable for TMPDIR placement.

**Sandbox + git worktree interaction** (confirmed from Claude Code GitHub issues):
- `sandbox.filesystem.denyWrite` DOES block `git worktree add` mid-checkout for files in denied paths (issues #51303, #53891). `git checkout` and `git worktree add` are intercepted at the filesystem layer — the sandbox does not distinguish "git checkout" from "agent write."
- `.claude/commands/` has a hardcoded deny. `.claude/skills/`, `.claude/docs/`, and `.claude/worktrees/` are NOT on the hardcoded deny list. Claude Code's own native worktree feature writes to `.claude/worktrees/` daily — it cannot be hardcoded-blocked.
- `.mcp.json` deny is real, intentional, and file-scoped (not directory-scoped). It does NOT block `git worktree add` creating the worktree directory or checking out other files. It blocks agent writes to `.mcp.json` after the worktree exists — which is the correct security property.
- `allowWrite` does NOT override hardcoded binary-level denies. User-level `allowWrite` only covers paths not on the hardcoded deny list.

**Registration step**: no other tool requires a registration step in an init command to add a worktree base to `allowWrite`. Claude Code native writes to `.claude/worktrees/` without registration because the repo root is already in the allowed write scope for interactive sessions.

Sources: Claude Code docs (worktrees, settings), GitHub issues #51303, #53891, #2841, #28242, #34437, #32287.

## Requirements & Constraints

**`cortex/requirements/multi-agent.md:30` and `:77-78`**: Currently encodes TMPDIR as canonical with the rationale "Seatbelt mandatory deny on `.mcp.json` blocks `git worktree add` from checking out `.mcp.json` into any path under the `.claude/` deny scope." This is the primary target of the revert. Both lines must be updated. The rationale at line 77 references `restore-worktree-root-env-prefix/` for the empirical probe — after this ticket, the reference chain must still be traceable via the supersession annotation.

**`cortex/requirements/pipeline.md:165-167`**: Documents hardcoded `.vscode`/`.idea` sandbox denies as `allowWrite`-proof. Update to clarify that the `.mcp.json` deny is filename-scoped (not directory-scoped) and does not block `git worktree add` to `.claude/worktrees/`.

**ADR-0003 (per-repo sandbox registration)**: `cortex init` is the only `~/.claude/` writer outside cortex's own tree. Step 7b was added to this single-write contract; removing it restores the ADR's minimal footprint. Step 7 (umbrella `cortex/` registration) is unaffected.

**ADR-0004 (multi-step complete and interactive worktree lifecycle)**: Interactive lifecycle worktrees bypass Claude Code's native `--worktree` flag intentionally; `create_worktree()` is the single chokepoint. This ADR is still correct after the revert.

**`cortex/requirements/project.md` — defense-in-depth constraint**: `.mcp.json` deny must be preserved unmodified. This ticket explicitly affirms it. The deny is correct security policy preventing a compromised session from writing to `.mcp.json` (which auto-executes on every session start).

**Existing `settings.local.json` state**: User's settings currently has `/private/var/folders/.../T/cortex-worktrees/` in `allowWrite` and `additionalDirectories`. These orphaned entries have no automated cleanup path in this ticket. They are harmless (the TMPDIR path is just an `allowWrite` entry that grants write access to a path no code uses anymore), but operators should manually remove them or `cortex init --update` should clean them.

## Tradeoffs & Alternatives

### Alternative A: Full revert (proposed) — `.claude/worktrees/` + delete all TMPDIR code + delete branch-(b) sentinel

**Pros:** Eliminates TMPDIR-divergence class of failures entirely. Aligns with Anthropic native convention. Removes dead branch-(b) code with misleading affordance. `.claude/worktrees/` already gitignored in this repo. Sandbox already covers via project-trust (no new registration). `additionalDirectories` no longer needed (path is inside repo root).

**Cons:** Requires sweeping ~18 files (more than the ticket originally listed). Does not address cross-repo overnight worktrees (branch d) — that divergence remains. Future contributors may re-diagnose `git worktree add` failures incorrectly; supersession annotation + new integration test mitigate. Branch (c) now calls `_repo_root()` subprocess — adds subprocess dependency to what was previously pure-env-var branch.

### Alternative B: Partial revert — change branch (c) default but keep branch-(b) sentinel

**Pros:** Lower diff surface.

**Cons:** Branch-(b) has zero active writers after Step 7b deletion — dead code with misleading affordance. Sentinel scheme was designed specifically for TMPDIR-placement problems; with TMPDIR gone, it has no purpose and will confuse future contributors.

### Alternative C: Home-dotdir `~/.cortex/worktrees/<feature>/`

**Pros:** Stable across machines and sessions. No env-var dependency.

**Cons:** Diverges from Anthropic native convention. Per-repo slug collision requires namespacing (additional complexity). New user-visible global directory. Still requires `additionalDirectories` registration.

### Alternative D: Keep TMPDIR, fix divergence in cortex init

**Pros:** No path migration.

**Cons:** TMPDIR Claude Code uses is not a documented API. Registration captures a snapshot that may be stale by next session. The prior lifecycle attempted this and proved it structurally fails. Root cause analysis in ticket #260 confirms divergence is inherent.

**Recommended: Alternative A.** Branch-(b) is dead code post-Step-7b-deletion; deleting it is cleaner than keeping it. `.claude/worktrees/` is the convergent industry placement — Anthropic native, Gemini CLI, claude-squad all use it. No registration step needed. Eliminates the entire TMPDIR-divergence class of failures.

## Adversarial Review

### Genuine failure modes requiring pre-implementation mitigation

**1. Seatbelt probe allow-set mismatch** (`cortex_command/pipeline/seatbelt_probe.py:164`): The probe passes `allow_paths=[str(tmpdir_resolved)]`. After the revert, `resolve_worktree_root()` returns `<repo>/.claude/worktrees/<feature>` — outside `$TMPDIR`. The probe will report failure on every overnight session. Must update `allow_paths` to include the repo's `.claude/worktrees/` path, or restructure the probe since `.claude/worktrees/` is project-trust covered rather than needing an explicit sandbox grant. (Note: the seatbelt probe is already failing for unrelated reasons in the current log — all entries show `claude exit nonzero: 1`. This change would add a second failure mode on top of an already-broken probe. The probe fix should be coordinated with the broader seatbelt probe repair.)

**2. `cortex-archive-rewrite-paths` functional exclusion gap** (`bin/cortex-archive-rewrite-paths`): The comment at line 62 claims worktrees are outside the repo tree and need no exclusion. After the revert they ARE inside the repo tree at `.claude/worktrees/<feature>/`. The path-rewriter will walk into worktree copies of lifecycle docs and mutate them. Must add `.claude/worktrees/` (or `.claude/`) to `EXCLUDED_DIR_NAMES`. This is a functional bug, not just a comment fix.

**3. Variant A pre-flight check in `implement.md`** (lines 132–182): The pre-flight check validates that `additionalDirectories` contains the worktree base. After Step 7b deletion there is no `additionalDirectories` entry for worktrees. Since `.claude/worktrees/` is inside the repo root (covered by project-trust), `additionalDirectories` is no longer needed — but the pre-flight check will fail with a confusing error. Replace with a check that verifies the worktree path is inside the project root (and therefore needs no explicit registration).

**4. `complete.md` cleanup prefix check** (`skills/lifecycle/references/complete.md:183`): Checks for `cortex-worktrees/interactive-{slug}` in `git worktree list --porcelain` output. After revert, interactive worktrees are at `.claude/worktrees/interactive-{slug}` — no `cortex-worktrees` in path. Cleanup silently skips all interactive lifecycle completions, permanently leaking worktrees. Must update the substring match.

**5. `ensure_gitignore()` in scaffold.py** (`_GITIGNORE_TARGETS`): Only appends `.cortex-init` and `.cortex-init-backup/`. Does not include `.claude/worktrees/`. User repos that run `cortex init` will show overnight worktrees as untracked in `git status`. Must add `.claude/worktrees/` to the gitignore targets.

**6. `_repo_root()` subprocess call in branch (c) after revert**: Branch (c) currently reads `os.environ.get("TMPDIR")` — no subprocess. After revert, branch (c) needs `repo_root` to compute `<repo>/.claude/worktrees/<feature>`. It will call `_repo_root()` (subprocess) when `repo_root` is not passed. Tests that call `resolve_worktree_root()` in non-git contexts (e.g., isolated temp dirs) will get `subprocess.CalledProcessError` instead of a path. Review and update test mocking strategy.

**7. Orphaned settings entries**: TMPDIR-based `allowWrite` and `additionalDirectories` entries from the previous lifecycle have no automated cleanup path. Consider adding a migration step in `cortex init --update` to detect and remove `#cortex-worktree-root`-suffixed entries and the TMPDIR-based `allowWrite`/`additionalDirectories` entries. Or document the one-time manual cleanup in release notes.

### Other findings (informational, not blocking)

- The `.gitignore` at `.claude/worktrees/` is already committed in this repo — sibling worktrees won't appear as untracked in each other's `git status`. Correct behavior.
- `create_worktree()` copies `settings.local.json` into the worktree at `<worktree_path>/.claude/settings.local.json`. The copy may contain stale TMPDIR `allowWrite` entries — cosmetic, not functional.
- `test_settings_merge.py` three `test_worktree_base_*` integration tests will fail after Step 7b removal — they must be deleted. The `register_additional_directories` function itself is not dead; only those integration tests are removed.
- Branch-(b) sentinel deletion: existing `#cortex-worktree-root` entry in user's `settings.local.json` becomes dead (not read by the resolver after branch-b deletion). Harmless.

## Open Questions

1. **Seatbelt probe restructuring**: The probe's `allow_paths` update is straightforward, but the seatbelt probe is already broken (all entries in `seatbelt-probe.log` show `claude exit nonzero: 1`). Should the seatbelt probe fix be in scope for this ticket, or filed separately and the TMPDIR-path fix deferred until the probe is repaired? _Defer if not blocking; add to spec as conditional touchpoint._

2. **Empirical verification of `git worktree add .claude/worktrees/<probe>` success**: The ticket claims "verified May 20" but no citable artifact (test, events.log entry, or screenshot) exists. The new integration test in `tests/test_worktree.py` is the spec-level artifact — but it's a unit test environment, not a Claude Code session with the actual sandbox active. The three-way invariant (worktree creation succeeds, `.mcp.json` propagates, agent write to `.mcp.json` denied) should be tested in an actual Claude Code session before this ticket is marked complete. _Flag as acceptance criterion: post-merge manual verification in a live Claude Code session._
