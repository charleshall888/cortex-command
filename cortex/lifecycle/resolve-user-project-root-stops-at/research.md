# Research: interactive-lock worktree-boundary resolution (#271)

> Scope anchor (from Clarify): make the interactive lock resolve to the **main repo root** when a cortex CLI runs from inside a git worktree (the documented #241 contract), so `test_lock_write_from_worktree_cwd` passes on vanilla macOS CI — **without** flipping `_resolve_user_project_root`'s deliberately worktree-local resolution for its other consumers (#198).

## Codebase Analysis

### The two bugs (one symptom, two mechanisms)

`_resolve_user_project_root()` (`cortex_command/common.py:56-104`) and its twin `_resolve_user_project_root_from_cwd()` (`:107-148`) walk upward from `Path.cwd()` for an ancestor whose `cortex/` child is a dir, breaking the walk at `(current / ".git").exists()` — **file or directory**. From a worktree, `.git` is a *file* (`gitdir: <main>/.git/worktrees/<id>`); the walk breaks there instead of following the pointer.

Because `cortex/` is **git-tracked** (≈2031 tracked files; verified `git ls-files cortex/`), there are two distinct failure modes:

- **(1) Synthetic crash — test-only.** The failing test builds a worktree with **no `cortex/`** and `CORTEX_REPO_ROOT` unset. The walk finds no `cortex/`, hits the `.git` *file*, breaks → `CortexProjectRootError`. This exact crash is reachable **only** in the test fixture.
- **(2) Silent wrong-location — production-reachable.** A *real* `interactive/{slug}` worktree (a checkout of `main`) **contains its own `cortex/`**, so the walk returns the **worktree** root on iteration 1 (before the `.git` check ever runs). The lock then resolves to `<worktree>/cortex/...` rather than `<main>/cortex/...`.

### Reachability — the real bug is a writer/reader root **divergence** on `read_lock`

Tracing every live (non-test) lock invocation:

- **`acquire_lock`** — invoked only via `cortex-interactive-lock acquire {slug}` at `skills/lifecycle/references/implement.md:83` (**§1 Step B**), which runs **before** §1a worktree creation and **before** the §1a `EnterWorktree` call (`:177-183`). At acquire time **CWD is the main repo** and `CORTEX_REPO_ROOT` is unset → walk finds `cortex/` at the main root on iteration 1 → lock written to `<main>/cortex/lifecycle/{slug}/interactive.pid`. **Correct today.**
- **`read_lock`** — `complete.md:29` (Step 3, **Variant-A detection**) reads the lock on **re-invocation after the phase-exit pause**. If the session is still inside the interactive worktree (auto-enter state persists; the cd-out hard guard is Step 8, *after* Step 3), CWD = worktree, `CORTEX_REPO_ROOT` unset → resolver finds the worktree's own tracked `cortex/` on iteration 1 → reads `<worktree>/cortex/.../interactive.pid` → **no lock there → returns `None`** → **false-negative Variant-A detection → the `cd-in-then-out` PR-creation wrapper is silently skipped.** Production-reachable correctness bug, not a crash.
- **`scan_live_locks`** — takes `project_root` as an explicit arg; the overnight caller (`overnight/orchestrator.py:~94/318`) passes `_resolve_user_project_root()` while `overnight/runner.py:2024` has set `CORTEX_REPO_ROOT = repo_path` (main) → env-first short-circuit → resolves to **main**. Correct; CWD-independent.
- **`release_lock`** — **never invoked anywhere in the skill flow** (grep of `skills/lifecycle/` shows only `acquire` and a `read_lock` reference). The lock is acquired but not explicitly released by the lifecycle. *Earlier framing that pinned reachability on `release_lock` is factually wrong — re-anchor to `read_lock`.*

**Net:** the literal crash is test-only; the live bug is writer(main)/reader(worktree) divergence on `read_lock`, plus the latent fact that the acquire path's correctness is **prose-ordering-dependent** (it only works because Step B precedes `EnterWorktree` — a future reorder would break the writer too). This argues for a resolver that is **correct regardless of CWD**.

### Resolver call-site inventory

`_resolve_user_project_root` — ~30 live (non-test) call sites across ~12 modules (the ticket's "87/17" counts docstring/test lines too): backlog (`create_item`, `generate_index`, `update_item`), dashboard (`app`, `seed`), overnight (`events`, `orchestrator`, `outcome_router`, `plan`, `report`, `state`, `status`), `cli.py`, and the lock. The **overnight** category is the sensitivity hotspot — `dispatch.py:560` pins `CORTEX_REPO_ROOT` to the **worktree** path (#198) and `runner.py:2024` to the repo path, so these deliberately depend on env-first short-circuit behavior; a *global* flip of the walk to resolve-to-main would regress them.

`_resolve_user_project_root_from_cwd` — **1 live call site**: `lifecycle_event.py:65` (the `cortex-lifecycle-event log` CLI), which is *deliberately* CWD-following so worktree event rows land in the worktree's `events.log` (`implement.md:191`). **This twin wants the opposite semantics from the lock and must not change.**

### Locus feasibility — lock-scoped fix, no `common.py` walk change

Inside `interactive_lock.py` the resolver is used in exactly two places — `_lock_path` (`:77`) and `_events_log_path` (`:83`), via the single import at `:53`. `scan_live_locks` (`:358`) is already decoupled (takes `project_root`). So a dedicated main-repo resolver can replace those two calls without touching `common.py`'s walk.

### Existing patterns to reuse

- `cortex_command/worktree_precondition.py:35-71` — `_git_output()` (returncode-tolerant `subprocess.run`, `None` on failure) + `is_in_worktree()` comparing `--show-toplevel` vs `--git-common-dir`.parent. Reusable shape.
- `cortex_command/init/handler.py:59-105` / `:255-284` — `git rev-parse --show-toplevel` / `--git-common-dir` with `check=False`.
- `cortex_command/pipeline/worktree.py:48-84` — `_repo_root` (`--show-toplevel`) and `_main_worktree_root` (`git worktree list --porcelain` first entry); `:610-625` `_find_git_repo` (pure-Python `.git` upward walk, capped at 64 iterations).

### Conventions / guardrails

- `cortex_command/common.py` is lifecycle-gated (listed in `skills/lifecycle/SKILL.md` description) — already satisfied (this lifecycle). **No dual-source plugin mirror** for `cortex_command/` (wheel-only), so `cortex-check-parity` does not gate this edit.
- **Wheel-binstub vs working-tree**: the `cortex-interactive-lock` binstub executes the **installed wheel**, not the working tree. Acceptance tests that shell out to the console script must use `python3 -m cortex_command.interactive_lock`, set `CORTEX_COMMAND_FORCE_SOURCE=1`, or reinstall the tool — otherwise they exercise stale code.
- `tests/test_common_utils.py:460` (`test_resolve_user_project_root_git_file_boundary_terminates_walk`) **pins the current `.git`-file-terminates-walk behavior** → a guardrail confirming `common.py` must not change.

## Web Research

### Resolving the MAIN repo root from a worktree

"Find the *enclosing* worktree root" (stop at `.git` file-or-dir) is a **different problem** from "find the *MAIN* repo root" (must follow `gitdir:` → `commondir`). Flag semantics from a *linked worktree*:

- `--show-toplevel` → the **current** worktree's own root (wrong answer here).
- `--git-dir` → worktree-private admin dir `<main>/.git/worktrees/<id>`.
- `--git-common-dir` → the **shared** git dir `<main>/.git` (the load-bearing primitive for crossing back to main).
- Robust route to the main *working tree*: `git worktree list --porcelain -z` → **first** entry is the main worktree (a `bare` line marks no working tree). Avoids the fragile `dirname(.git)` assumption for bare / `core.worktree` setups.

### Worktree `.git` file + commondir spec (gitrepository-layout)

- `.git` gitfile content: `gitdir: <path>` (literal prefix `gitdir: ` with a space). Path is **absolute by default**, but can be **relative** (`--relative` / `worktree.useRelativePaths`) — relative to the `.git` file's directory.
- `<main>/.git/worktrees/<id>/commondir` points at the shared repo dir (sets `$GIT_COMMON_DIR`); **if relative, it is relative to `$GIT_DIR`** (i.e. to `worktrees/<id>/`). This is the file a pure-Python parser reads to find `<main>/.git` without shelling out.
- Edge cases: trailing newline (strip), missing `.git`, malformed/relative pointer, deleted admin dir, submodule `.git` files (also `gitdir:` — distinguish via the `worktrees/<id>` structure), bare repos, `core.worktree`/separate-git-dir.

### Prior art (upward-walk finders)

- **Black** (`find_project_root`) and **Netlify CLI** both treat `.git` as a stop boundary; their bugs (psf/black#1083, netlify/cli#7868) were about file-vs-dir detection, not pointer-following — they find the *worktree* root, never the main repo.
- **pre-commit** (`get_root`) shells out to git (`--show-cdup` + `--is-inside-git-dir`), scrubs `GIT_*` env (`no_git_env()`), and avoids `--show-toplevel` due to a Git 2.25 Windows SUBST regression.
- **ripgrep** (#1445) has a linked-worktree bug from *not* following the commondir indirection. **No mainstream upward-walk finder parses `gitdir:` to reach the main repo** — those needing cross-worktree resolution shell out (pre-commit) or use GitPython.

### Shell-out vs parse-directly

- **Shell-out** (`git rev-parse`): authoritative for bare/`core.worktree`/relative pointers; but fails when git is absent (catch `FileNotFoundError`/non-zero), can be denied/odd under Seatbelt, and incurs fork cost (~6ms). Env contamination (`GIT_DIR`) must be scrubbed.
- **Parse `.git` + `commondir` directly**: no subprocess, sandbox/git-absent safe, sub-ms; but reimplements git's path logic (absolute-vs-relative, the `worktrees/<id>`→`commondir` hop, bare/submodule distinctions).

Docs: git-rev-parse, gitrepository-layout, git-worktree man pages; psf/black#1083; netlify/cli#7868; pre-commit `git.py`; BurntSushi/ripgrep#1445.

## Requirements & Constraints

### The documented #241 contract — and its **false** premise

`cortex/lifecycle/add-bidirectional-concurrency-guards-for-interactive/spec.md`:
- **R2 (line 24):** *"Lock file path resolved against main repo root, never worktree CWD"* … "MUST use this resolver and MUST NOT use bare `Path("cortex/lifecycle/...")` (which would be CWD-relative and resolve to the worktree's cortex tree under Variant A)." Acceptance: `grep -c '_resolve_user_project_root' cortex_command/interactive_lock.py` **≥ 2**.
- **Line 142 (Technical Constraints) — the flawed assumption, verbatim:** *"`_resolve_user_project_root()` terminates on `.git` (file or dir), so worktree CWD resolves up to the main repo."* This is **false**: the resolver terminates *at* `.git` without ascending. The test encodes the author's intended-but-false belief — this is a spec/test-vs-implementation mismatch, not purely a code bug. **The fix must correct line 142 and reconcile R2's acceptance grep** if the lock stops calling `_resolve_user_project_root()` directly.

### What prior tickets decided about worktree project-root resolution

- **#201** introduced the upward walk bounded by `.git` (file or dir); its worktree edge-case reasoning assumed the worktree itself *contained* the marker (`lifecycle/`/`backlog/` at the time).
- **#202 / epic #200** switched the marker to a single `cortex/` dir — invalidating #201's worktree assumption for the no-`cortex/` case.
- **#198 / `restore-worktree-root-env-prefix`** (superseded by **#260**) concerned worktree *placement*, not root resolution.
- **#237** (worktree-interactive / Variant A) places long-lived sessions *inside* per-feature worktrees — the trigger condition.
- **#260 / ADR-0005** cemented worktree placement at `<repo>/.claude/worktrees/<feature>/` — the geometry (worktree under main, `.git` *file* at its root) that exposes the gap.
- **Net:** no prior ticket decided the *global* resolver should resolve to main from a worktree. #241 line 142 is the **only** place asserting that (now-false) behavior, and it applies to the lock specifically.

### Hard constraints (what must NOT change)

- **Do not weaken `.git`-boundary protection for the non-worktree case** (#201 Non-Requirements): an unrelated nested git repo with no `cortex/` must still stop the walk and raise (no leaking into an ancestor cortex project).
- **Keep `_resolve_user_project_root` pure-Python** — #201 explicitly rejected a `git rev-parse` subprocess inside it (silent-failure risk + library/CLI separation). *(This constraint is strongest for `common.py`'s shared resolver; a lock-scoped resolver in `interactive_lock.py` is a different locus, but the pure-Python preference still informs the mechanism choice.)*
- **Preserve the `CORTEX_REPO_ROOT` env-first short-circuit verbatim** (overnight + several tests rely on it).
- **Do not touch `_resolve_user_project_root_from_cwd`'s worktree-local behavior** (`lifecycle_event.py` event routing depends on it).
- **ADR-0003 sandbox grant:** `cortex init` registers the **main** repo's `cortex/` path as writable. The lock MUST land in `<main>/cortex/` — a worktree-local `cortex/` is outside the grant (the #241 R14 sandbox probe exists to verify this).
- **Out of scope** (#241 Non-Requirements): shared `pid_lock.py` extraction, cross-checkout concurrency, sub-agent lock participation, the `Agent(isolation:"worktree")` silent-failure mitigation.

## Tradeoffs & Alternatives

| Approach | Fixes the test? | Fixes the live `read_lock` bug? | Blast radius | Verdict |
|---|---|---|---|---|
| **A — fix the `common.py` walk** (follow `gitdir:` when `.git` is a file) | Yes (synthetic only) | **No** — real worktrees find `cortex/` on iteration 1, so the new branch is dead code for them | Widest (~30 callers of both twins; the two twins want *opposite* semantics) | **Reject** |
| **B — lock-scoped resolver in `interactive_lock.py`** | Yes (mechanism-dependent) | **Yes** (resolver prefers main regardless of CWD) | 1 file, 2-3 fns | **Candidate** |
| **C — new `_resolve_main_repo_root()` in `common.py`, lock-only consumer** | Yes | Yes | 1 new fn + 1 consumer; existing resolvers untouched | **Candidate** (B-equivalent; differs only in *where* the helper lives) |
| **D — explicit `project_root` param to lock primitives** (mirror `scan_live_locks`) | Only if the test passes the new flag | Yes (structural agreement) | lock module + skill call sites (`implement.md`, `complete.md`) | **Strong candidate** (simplest correctness model, but distributes resolution into skill prose + needs test change) |

**Critical mechanism finding (empirically verified by the adversarial pass):**

- A *real* `git worktree add` writes `gitdir: <main>/.git/worktrees/<id>`. The **test hand-writes** `gitdir: <main>/.git` (direct, skipping the `worktrees/<id>` hop).
- **`git rev-parse --git-common-dir` returns exit 128 (`fatal: not a git repository`) against the hand-built fixture** (git needs the registered `worktrees/<id>/{commondir,gitdir}` backlink). So a shell-out mechanism would **force rewriting the failing test** to use a real `git worktree add`.
- A **naive "parse `gitdir:`, take `.parent`"** works on the synthetic fixture but is **wrong for real worktrees** (`.parent` = `<main>/.git/worktrees`).
- **Only a `commondir`-aware pure-Python parse** passes the **existing fixture unchanged** AND is correct for real worktrees: read `gitdir:` → if a sibling `commondir` exists, resolve it (relative-to-`$GIT_DIR`) to get `<main>/.git` → `.parent` = `<main>`; if no `commondir` (synthetic direct pointer), `.parent` of the gitdir already = `<main>`.

**Mechanism recommendation:** `commondir`-aware **pure-Python** parse, with **`CORTEX_REPO_ROOT` env-first preserved** and a **fall-back to the existing `cortex/`-walk on any parse/git failure** (protects the legitimate non-git `cortex/` project case, where shell-out would crash exit 128).

**Recommended approach:** **B or C** (lock-scoped main-repo resolver, pure-Python commondir-aware) — it fixes both the test and the live `read_lock` divergence, is correct regardless of CWD (robust against the prose-ordering dependency in the acquire path), keeps the existing test fixture unchanged, and has near-zero blast radius. **D** (explicit `project_root` param) is the runner-up: structurally cleanest agreement model and matches `scan_live_locks`, but it pushes correctness into skill prose (which CLAUDE.md discourages for sequential gates), requires modifying the failing test to pass the root, and spreads the responsibility across `implement.md` + `complete.md`. **A is rejected.**

## Adversarial Review

- **Reachability re-anchored (verified):** `release_lock` is dead code in the skill flow; the real bug is the `read_lock` writer/reader root **divergence** in `complete.md` Step 3 (false-negative Variant-A → PR wrapper skipped). The durable-fix justification survives but must cite `read_lock`, not `release_lock`.
- **Shell-out refuted (verified):** `git rev-parse --git-common-dir` → exit 128 on the hand-built fixture, and exit 128 in a no-`.git` `cortex/` project. Any shell-out resolver MUST `check=False` + fall back to the walk, and would force a test-fixture rewrite.
- **"Prefer main over local `cortex/`" regression vector (verified):** standalone `cortex/` dir with no git + `CORTEX_REPO_ROOT` unset → git resolution fails; the resolver MUST fall back to the `cortex/`-walk (pure-Python parse handles this naturally; the existing `test_detects_cortex_subdir` path must stay green). Plain clones and nested repos degrade gracefully. **Env-first ordering must be preserved.**
- **Writer/scanner/reader agreement:** writer (acquire) = main; scanner (overnight, env-pinned) = main; reader (`read_lock` from worktree) = **worktree (the bug)**. A lock-scoped resolver that always yields main makes all three converge. `scan_live_locks` need not change (overnight env-pins it to main) — but the spec should *document* that env-set as the load-bearing guarantee, or have the scanner derive its root via the same helper as defense.
- **Test fixture verdict:** keep the hand-built fixture + pure-Python parse (passes unchanged). If stronger coverage is wanted, add a **separate** real-`git worktree add` test rather than mutating the sandbox-write probe — a `git worktree add` inside the test risks the known **worktree editable-`.pth` rewrite** hazard and changes the sandbox process footprint.
- **Assumptions checked:** "real worktree contains `cortex/`" = TRUE (2031 tracked files); "acquire is safe" = TRUE but prose-ordering-dependent; R2's grep + `interactive_lock.py:77,83` must be updated in lockstep; binstub reads the installed wheel (use `python3 -m` / `CORTEX_COMMAND_FORCE_SOURCE=1` in tests).
- **Simpler alternative surfaced:** Approach D (explicit `project_root` param) — captured in Tradeoffs above.

## Open Questions

- **[Deferred — resolved in Spec by user decision] Fix locus/shape: lock-scoped pure-Python commondir-aware resolver (Approaches B/C, *recommended*) vs explicit `project_root` parameter threaded from the skill (Approach D).** Both are durable and fix the live `read_lock` bug. Research recommends B/C because it makes the lock correct regardless of CWD and keeps the existing test fixture unchanged; D is the structurally-cleaner-but-more-distributed alternative. This is a design choice for the Spec interview / §4 complexity-value gate — *not* a blocking unknown, so it is explicitly deferred to Spec.
- **[Resolved — by evidence, not open] Mechanism `git rev-parse` shell-out vs pure-Python parse:** the Tradeoffs agent initially favored shell-out (in-repo precedent); the Adversarial agent **empirically refuted** it (exit 128 on the hand-built test fixture). Resolution: **pure-Python commondir-aware parse** (passes the existing fixture, sandbox/git-absent safe, with env-first + walk-fallback). Recorded here per the contradiction-handling rule; the contradiction is settled by the adversarial agent's direct command execution.
- **[Deferred — minor, resolved in Spec] Should `scan_live_locks` derive its own root via the new helper, or continue relying on the overnight orchestrator's `CORTEX_REPO_ROOT=main` env-pin?** Research recommends leaving `scan_live_locks` as-is (overnight pins env to main) and documenting that guarantee; revisit only if a non-overnight scanner caller appears. Deferred to Spec as a small scope confirmation.
