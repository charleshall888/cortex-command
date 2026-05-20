# Specification: revert-tmpdir-worktree-placement-and-restore

## Problem Statement

Interactive lifecycle execution silently fails to enter Variant-A worktrees when the Claude Code session's `TMPDIR` differs from the shell that ran `cortex init`. On macOS this divergence is the default: terminal shells get `/var/folders/.../T/` while Claude Code sessions get `/tmp/claude-$UID/`. The root cause is structural — worktree path resolution depends on a per-process environment variable while sandbox registration is per-user. This ticket reverts `resolve_worktree_root()` branch (c) to return `<repo>/.claude/worktrees/<feature>` (repo-relative, deterministic across all shells and sessions), removes the `cortex init` step that registered the now-unnecessary TMPDIR worktree base, deletes the dead branch-(b) sentinel machinery, and sweeps all code/docs/tests/requirements that assert TMPDIR placement. The change aligns cortex with Anthropic's own native worktree convention and eliminates the entire class of TMPDIR-divergence failures.

## Phases

- **Phase 1: Core code and critical fixes** — Python resolver change, init step removal, sentinel deletion, scaffold gitignore fix, seatbelt probe update, archive rewriter exclusion, complete.md prefix fix, and all tests
- **Phase 2: Docs and requirements sweep** — Update all prose, skill references, docs, requirements, and legacy lifecycle annotations to reflect the new placement

## Requirements

1. **Revert branch (c) of `resolve_worktree_root()`**: branch (c) returns `(repo_root / ".claude" / "worktrees" / feature).resolve()`. The module docstring and branch-(c) inline comments that assert "worktrees go to TMPDIR to escape `.mcp.json` deny" are replaced with the correct rationale (Anthropic-aligned repo-relative default; project trust covers the path). **Acceptance**: `grep -c "cortex-worktrees" cortex_command/pipeline/worktree.py` = 0; `python3 -m cortex_command.pipeline.worktree` (or equivalent invocation) with a real repo root returns a path under `.claude/worktrees/`; `just test` exits 0. **Phase**: Phase 1

2. **Delete `_registered_worktree_root()` and branch-(b) call site**: the sentinel-suffix reader (`_registered_worktree_root()` at `worktree.py:119–161`) and its call site in `resolve_worktree_root()` are deleted entirely. Branch (b) code is gone; no fallback to `settings.local.json` parsing survives. **Acceptance**: `grep -c "_registered_worktree_root\|cortex-worktree-root" cortex_command/pipeline/worktree.py` = 0; `just test` exits 0. **Phase**: Phase 1

3. **Delete Step 7b and `_resolve_worktree_base()` from `init/handler.py`**: the worktree-base registration block (lines 200–211) and the `_resolve_worktree_base()` helper (lines 216–234) are deleted. `cortex init` no longer writes a TMPDIR-based entry to `allowWrite` or `additionalDirectories`. `cortex init --update` gains a migration step that removes orphaned entries: any value containing `cortex-worktrees` from `sandbox.filesystem.allowWrite` and `additionalDirectories` in `~/.claude/settings.local.json`. Migration is idempotent. **Implementation note**: The existing `unregister()` in `settings_merge.py` uses exact-string equality and only covers `allowWrite` — it cannot serve as the migration mechanism. This requirement adds a new helper (e.g., `unregister_matching(predicate, settings)`) to `settings_merge.py` that removes entries containing `predicate` as a substring from both `allowWrite` and `additionalDirectories`, and wires it into the `--update` branch in `handler.py`. **Acceptance**: `grep -c "_resolve_worktree_base\|cortex-worktrees" cortex_command/init/handler.py` = 0 (excluding comments explaining what was removed); a new integration test verifies that `cortex init --update` on a settings file containing a `cortex-worktrees`-prefixed path in both `allowWrite` and `additionalDirectories` removes both entries and that a second `--update` run on the cleaned file is a no-op; `just test` exits 0. **Phase**: Phase 1

4. **Add `.claude/worktrees/` to `scaffold.py` gitignore targets**: `_GITIGNORE_TARGETS` gains `.claude/worktrees/` so `cortex init` appends the pattern to user repos' `.gitignore`. Without this, overnight-created worktrees appear as untracked directories in user repo `git status`. **Acceptance**: `grep -c "claude/worktrees" cortex_command/init/scaffold.py` ≥ 1; running `cortex init` on a repo appends `.claude/worktrees/` to its `.gitignore`. **Phase**: Phase 1

5. **Fix `cortex_command/overnight/seatbelt_probe.py` allow-set** (`seatbelt_probe.py:164`): `allow_paths=[str(tmpdir_resolved)]` is updated to also include the repo's `.claude/worktrees/` path (or restructured so the probe doesn't need an explicit grant since `.claude/worktrees/` is project-trust covered). After the revert, `resolve_worktree_root()` returns a repo-relative path outside `$TMPDIR`; without this fix the probe will always report failure. **Acceptance**: The probe's `allow_paths` covers both `.claude/worktrees/` for branch (c) worktree creation AND retains `$TMPDIR` coverage for probe output files (lines 156–157 of `seatbelt_probe.py`); `grep -c "claude/worktrees\|repo_root\|project_root" cortex_command/overnight/seatbelt_probe.py` ≥ 1 in the allow_paths construction; `just test` exits 0. **Phase**: Phase 1

6. **Fix `bin/cortex-archive-rewrite-paths` functional exclusion**: Add `.claude/worktrees/` (or `.claude/`) to `EXCLUDED_DIR_NAMES` in the archive path-rewriter. After the revert, worktrees are inside the repo tree; without exclusion the rewriter walks into worktree copies of lifecycle docs and mutates them. The comment at line 62 is also updated to reflect the new placement. **Acceptance**: `grep -c "claude/worktrees\|claude" bin/cortex-archive-rewrite-paths` ≥ 1 in `EXCLUDED_DIR_NAMES`; running the archive rewriter on a repo with `.claude/worktrees/feature/some-lifecycle.md` does not modify files in the worktree. **Phase**: Phase 1

7. **Fix `skills/lifecycle/references/complete.md` cleanup prefix check** (`complete.md:183`): the substring match `cortex-worktrees/interactive-{slug}` in `git worktree list --porcelain` is updated to `.claude/worktrees/interactive-{slug}`. Without this fix the Complete phase silently skips cleanup on every interactive lifecycle, permanently leaking worktrees. **Acceptance**: `grep -c "claude/worktrees/interactive" skills/lifecycle/references/complete.md` ≥ 1; `grep -c "cortex-worktrees/interactive" skills/lifecycle/references/complete.md` = 0. **Phase**: Phase 1

8. **Update `tests/test_worktree.py` and `tests/test_worktree_seatbelt.py`**: revert branch-(c) assertions in both files to expect `.claude/worktrees/`; delete branch-(b) sentinel tests; delete `TestVerifyR5NegativeProperty` (which asserts the branch-(c) result is NOT under `<repo>/.claude/` — the opposite of post-revert behavior, so it will fail after the revert); add a new integration test (`test_mcp_json_propagation_and_deny_invariant`) that creates a worktree via `git worktree add .claude/worktrees/<probe>`, asserts `.mcp.json` is present in the worktree (propagation success), and asserts a direct write to `.mcp.json` in the worktree is denied by the sandbox. Update `tests/test_worktree_seatbelt.py` module docstring: replace the stale `$TMPDIR/cortex-worktrees/<feature>` placement language with `.claude/worktrees/<feature>`. Update test mocking: branch (c) now calls `_repo_root()` (subprocess), so tests that call `resolve_worktree_root()` in non-git contexts must patch `_repo_root` or `subprocess.run`. **Acceptance**: `grep -c "cortex-worktrees" tests/test_worktree.py` = 0; `grep -c "_registered_worktree_root\|cortex-worktree-root" tests/test_worktree.py` = 0; `grep -c "cortex-worktrees\|TMPDIR/cortex" tests/test_worktree_seatbelt.py` = 0; `just test` exits 0. **Phase**: Phase 1

9. **Update `tests/test_settings_merge.py`**: delete the three `test_worktree_base_*` integration tests (lines ~1067–1156) that call `init_main()` and assert TMPDIR paths in `allowWrite`/`additionalDirectories`. The `register_additional_directories` function itself is not deleted — only the init-flow integration tests that exercised the now-removed Step 7b. **Acceptance**: `grep -c "cortex-worktrees\|test_worktree_base" tests/test_settings_merge.py` = 0; `just test` exits 0. **Phase**: Phase 1

10. **Update `tests/test_hooks.sh`**: update resolver output path assertions at lines 164, 189, 199, 220, 224, 235 from TMPDIR-based paths to `.claude/worktrees/`-based paths. **Acceptance**: `grep -c "cortex-worktrees" tests/test_hooks.sh` = 0; `just test` exits 0. **Phase**: Phase 1

11. **Update `cortex/requirements/multi-agent.md` lines 30 and 77**: replace `$TMPDIR/cortex-worktrees/{feature}/` with `<repo>/.claude/worktrees/{feature}/`; rewrite the line-77 rationale from "Seatbelt mandatory deny blocks `git worktree add`" to "Anthropic-aligned repo-relative default; project trust covers the path; no per-shell registration needed." Remove the reference to `restore-worktree-root-env-prefix/` as an empirical probe source (annotate it as superseded instead). **Acceptance**: `grep -c "TMPDIR/cortex-worktrees" cortex/requirements/multi-agent.md` = 0. **Phase**: Phase 2

12. **Update `cortex/requirements/pipeline.md` lines 165–167**: update hardcoded-deny constraint text to clarify that `.mcp.json` deny is filename-scoped (blocks agent writes to `.mcp.json`) and does NOT block `git worktree add` creating the worktree directory or checking out other files. **Acceptance**: `grep -c "blocks.*git worktree add\|git worktree add.*block" cortex/requirements/pipeline.md` = 0; `grep -c "filename-scoped\|file-scoped" cortex/requirements/pipeline.md` ≥ 1. **Phase**: Phase 2

13. **Update skill references**: rewrite TMPDIR-placement assertions in `skills/lifecycle/references/parallel-execution.md` (lines 14, 17), `skills/lifecycle/references/implement.md` (pre-flight check lines 132–182 + path references lines 200, 202), and `skills/overnight/SKILL.md` (line 133). The pre-flight check in `implement.md` is updated to verify the worktree path is inside the project root rather than checking for an `additionalDirectories` registration. **Acceptance**: `grep -rn "cortex-worktrees" skills/` = no matches; `just test` exits 0. **Phase**: Phase 2

14. **Update operational docs**: rewrite worktree-placement text in `docs/internals/pipeline.md` (line 139) and `docs/internals/sdk.md` (lines 29, 144, 160). **Acceptance**: `grep -rn "cortex-worktrees" docs/` = no matches. **Phase**: Phase 2

15. **Update utility scripts and hooks**: update comment in `bin/cortex-check-parity` (line 69) from `$TMPDIR/cortex-worktrees/<feature>` to `.claude/worktrees/<feature>`; add a short comment to `claude/hooks/cortex-worktree-create.sh` (lines 39–42) naming `.claude/worktrees/` as the new default for grep-discoverability. **Acceptance**: `grep -c "TMPDIR/cortex-worktrees" bin/cortex-check-parity` = 0; hook file contains `.claude/worktrees` in a comment. **Phase**: Phase 2

16. **Annotate superseded lifecycle artifacts**: prepend a supersedes callout to `cortex/lifecycle/restore-worktree-root-env-prefix/research.md` and `spec.md` with a back-link to ticket #260. The `.mcp.json` Seatbelt deny mechanism sections are preserved as historical misdiagnosis records — not deleted. **Acceptance**: both files contain "superseded by #260"; `grep -c "superseded" cortex/lifecycle/restore-worktree-root-env-prefix/research.md` ≥ 1; `grep -c "superseded" cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` ≥ 1. **Phase**: Phase 2

## Non-Requirements

- Migration of existing TMPDIR-based worktrees from prior runs — they retain ephemeral semantics and age out naturally
- Any change to the `.mcp.json` sandbox deny — it is correct security policy and must not be weakened
- Cross-repo overnight worktree placement (branch d of `resolve_worktree_root()`) — remains TMPDIR-based and is out of scope; a follow-up ticket should move cross-repo worktrees to `~/.cortex/overnight-worktrees/`
- Adding `team_name` to any `Agent(isolation: "worktree")` call — Anthropic issue #33045 documents this silently fails; cortex does not use `team_name` anywhere
- Restoring `tests/test_init_worktree_registration.py` — deleted in the previous lifecycle; Step 7b removal makes registration tests permanently moot
- Repair of unrelated seatbelt probe failures (`claude exit nonzero: 1`) — the allow-set fix in R5 addresses only the path-coverage mismatch; broader probe repair is a separate ticket

## Edge Cases

- **Non-git-repo context**: branch (c) now calls `_repo_root()` (subprocess). In contexts without a git repo, this raises `subprocess.CalledProcessError`. Existing behavior — tests that call `resolve_worktree_root()` without a real git repo must patch `_repo_root`.
- **`cortex init --update` idempotency**: removing orphaned `cortex-worktrees` entries from `settings.local.json` must be idempotent; running `--update` twice on a clean settings file must be a no-op.
- **Worktree directory creation**: `git worktree add .claude/worktrees/<feature>` creates the directory if it doesn't exist. No pre-creation of `.claude/worktrees/` is needed; git handles it.
- **Concurrent `cortex init` calls**: the existing `fcntl.flock` serialization in ADR-0003 already covers concurrent init calls — no change needed.
- **`.claude/worktrees/` gitignore in the worktree itself**: the committed `.gitignore` in this repo already includes `.claude/worktrees/`. Sibling worktrees will not appear as untracked in each other's `git status`.
- **`cortex-archive-rewrite-paths` on a repo with active worktrees**: excluding `.claude/worktrees/` from the walk prevents mutation; existing lifecycle docs under `.claude/worktrees/` are untouched.
- **Existing users with `#cortex-worktree-root` sentinel in `settings.local.json`**: after branch-(b) deletion, the sentinel entry is dead (not read). The `cortex init --update` migration removes it.

## Changes to Existing Behavior

- **MODIFIED**: `resolve_worktree_root()` branch (c) path → from `$TMPDIR/cortex-worktrees/<feature>` to `<repo>/.claude/worktrees/<feature>`
- **REMOVED**: `_registered_worktree_root()` — branch-(b) sentinel-suffix reader for `settings.local.json`
- **REMOVED**: `cortex init` Step 7b — no longer registers a TMPDIR-based `allowWrite`/`additionalDirectories` entry
- **REMOVED**: `_resolve_worktree_base()` helper in `init/handler.py` — dead code after Step 7b deletion
- **ADDED**: `cortex init --update` migration step removes orphaned `cortex-worktrees` entries from `settings.local.json` (requires new `unregister_matching` helper in `settings_merge.py` — see R3 implementation note)
- **ADDED**: `.claude/worktrees/` appended by `cortex init` to user repos' `.gitignore`

## Technical Constraints

- **`.mcp.json` deny must be preserved unmodified.** It is intentional defense-in-depth preventing a compromised session from writing to `.mcp.json` (which auto-executes on every session start). The deny is file-scoped — it does NOT block `git worktree add` creating the worktree directory or checking out other files. The new integration test in R8 pins this three-way invariant.
- **`resolve_worktree_root()` is the single chokepoint.** create_worktree, daytime_pipeline, readiness, and the worktree-create hook all route through it — branch (c) change propagates to these paths automatically. The `cleanup_worktree()` fallback calls `resolve_worktree_root(feature, session_id=None)`, meaning branch-(d) overnight callers that created worktrees with a `session_id` must supply `worktree_path=` explicitly at cleanup time; this is a pre-existing constraint unchanged by this ticket.
- **Branch (c) must call `.resolve()`** on the repo-relative path for macOS symlink canonicalization (`/tmp` → `/private/tmp`). Downstream sandbox path comparisons depend on the resolved form.
- **Branch (c) adds a `_repo_root()` subprocess call.** Tests invoking `resolve_worktree_root()` without a real git repo (or without patching `_repo_root`) will get `subprocess.CalledProcessError`. Update test mocking strategy accordingly.
- **`team_name` must not be added** to any `Agent(isolation: "worktree")` call — the combination silently fails per Anthropic issue #33045.
- **Phase 1 lands as a single atomic commit**; Phase 2 lands as a single atomic commit. Intermediate states must not leave tests red.
- **`cortex init --update` migration uses `fcntl.flock` serialization** (per ADR-0003) when modifying `settings.local.json`. Removal of entries matching `cortex-worktrees` in `allowWrite` and `additionalDirectories` is the migration predicate.

## Open Decisions

None — all decisions resolved at spec time.

## Proposed ADR

### Proposed ADR: 0005-repo-relative-worktree-placement

**Context**: Same-repo worktree placement has been debated twice. The first placement (`<repo>/.claude/worktrees/`) was replaced in lifecycle `restore-worktree-root-env-prefix` by `$TMPDIR/cortex-worktrees/` based on the (empirically false) premise that the `.mcp.json` Seatbelt deny blocks `git worktree add` into `.claude/`. This ticket reverts to the repo-relative placement after an empirical probe (May 20, 2026) confirmed that `git worktree add .claude/worktrees/<name>` succeeds, `.mcp.json` propagates correctly, and agent writes to `.mcp.json` remain denied.

**Decision**: Same-repo worktrees live at `<repo>/.claude/worktrees/<feature>/`, computed as a pure function of the repo root with no environment-variable participation. Cross-repo overnight worktrees (branch d) remain TMPDIR-based pending a separate follow-up.

**Trade-off**: TMPDIR placement enables OS-managed ephemeral cleanup but requires a per-shell registration step that creates inherent divergence between terminal `TMPDIR` and Claude Code session `TMPDIR`. Repo-relative placement requires no registration, is stable across all shells and sessions, aligns with Anthropic's own native worktree convention (`agent-a<hex>/` directories), and is gitignored at the project level. The cost is that worktrees persist until explicitly cleaned (no OS eviction) — acceptable given that `cleanup_worktree()` handles this and git manages the administrative references.
