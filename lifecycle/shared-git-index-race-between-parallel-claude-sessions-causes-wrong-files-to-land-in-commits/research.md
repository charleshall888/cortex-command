# Research: Eliminate the race between parallel Claude Code sessions sharing the home-repo git index

**Lifecycle slug**: `shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits`
**Tier**: complex
**Criticality**: high
**Backlog item**: `135-shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits`

## Codebase Analysis

### The `/commit` skill flow today

Canonical source: `skills/commit/SKILL.md`. Plugin mirror: `plugins/cortex-interactive/skills/commit/SKILL.md`.

Step-by-step:

1. **Step 1 (line 12)**: Run `bin/cortex-commit-preflight` → JSON of `git status` + `git diff HEAD` + recent log. Read-only; no index mutation.
2. **Step 2 (line 13)**: Run `git add <explicit-files>`. **Mutates the shared home-repo index.**
3. **Step 3 (lines 14–24)**: Compose the commit message. In-process LLM work; no git operations.
4. **Step 4 (lines 54–56)**: PreToolUse hook `hooks/cortex-validate-commit.sh` validates the message string from the JSON tool input. Does **not** re-check the index.
5. **Step 5 (lines 44–50)**: Run `git commit -m "..."`. Consumes the current index and creates the commit.

**The race window is between step 2 and step 5** — non-atomic; another session's `git add` or `git commit` can intervene.

### Every harness path that calls `git add` + `git commit`

| Path | File:lines | Index | Risk |
|---|---|---|---|
| `/commit` skill | `skills/commit/SKILL.md:13`, `:44–50` | Home-repo (shared) | **HIGH** |
| Smoke-test cleanup | `cortex_command/overnight/smoke_test.py:91–101` (`git rm` + `git commit`) | Home-repo (shared) | **MEDIUM** |
| Overnight followup-commit | `cortex_command/overnight/runner.py:406–448` (`_commit_followup_in_worktree`) | Worktree-isolated via `cwd=str(worktree_path)` | LOW (with caveat — see #2 below) |
| Conflict resolution | `cortex_command/pipeline/conflict.py:600–622` (`git add`); `:625–630` (`git merge --continue`) | Worktree-isolated via `cwd=worktree_path` | LOW |
| Orchestrator plan-commit | `cortex_command/overnight/prompts/orchestrator-round.md:271` | Delegates to `/commit` skill | Inherits HIGH |

Caveats:
1. **`/commit` is the sole user-facing path** that mutates the shared home-repo index. It is the primary attack surface.
2. **`_commit_followup_in_worktree` does NOT strip `GIT_DIR` from the env** before invoking `subprocess.run(["git", "commit", ...], cwd=worktree_path, ...)`. If the runner's parent process inherits a stuck `GIT_DIR=<home-repo>/.git` (hook env, dev shell var, misconfigured cron), the `cwd=worktree_path` is overridden and the commit lands in the home repo. Compare with `cortex_command/overnight/outcome_router.py:177–178`, which already strips `GIT_DIR` for exactly this reason. This is an independent latent bug.
3. **Smoke-test cleanup `_remove_tracked_lifecycle_dir`** is invoked manually by developers (not auto-triggered by `cortex overnight start` per `cli.py:334`). The user is interacting during smoke runs, so the race with a parallel `/commit` is real.

### Existing flock pattern (precedent to follow)

`cortex_command/init/settings_merge.py:69–85`:
```python
def _acquire_lock(home: Path | None) -> int:
    claude_dir = _claude_dir(home)
    claude_dir.mkdir(parents=True, exist_ok=True)
    lockfile_path = _lockfile_path(home)  # sibling, not the settings file itself
    lock_fd = os.open(lockfile_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except BaseException:
        os.close(lock_fd)
        raise
    return lock_fd
```

Non-blocking polling variant with timeout: `plugins/cortex-overnight-integration/server.py:655–697` (`_acquire_update_flock`).

Conventions established by these:
1. Lock file is a **sibling** to the protected resource, not the resource itself — survives `os.replace()` swaps.
2. Mode `0o600` (user-only).
3. `fcntl.flock(fd, LOCK_EX)` — blocking exclusive lock.
4. Acquire at function entry; release in `try/finally` via `os.close(fd)`.
5. Latent bug in this precedent (carryover): does **not** call `os.set_inheritable(fd, False)` or pass `O_CLOEXEC`. A long-lived child subprocess could inherit the fd and outlive the parent, causing the lock to be silently held indefinitely. Audit and patch in conjunction with the fix.

### Pre-commit hook behavior

`.githooks/pre-commit` (enabled by `just setup-githooks`):

- **Line 84**: `git diff --cached --name-only --diff-filter=ACMRD` — reads the staged-files list.
- **Line 146**: `git diff --cached --name-only --diff-filter=ACMR` — reads the staged-files list again for build-trigger decisions.
- **Lines 167**: `just build-plugin >/dev/null 2>&1` — **writes files into the shared working tree** (regenerates plugin mirror sources).
- **Lines 185–191**: `git diff --quiet -- "plugins/$p/"` — compares working tree vs index.

Implications:
- A **flock-based mitigation is hook-compatible** — the hook reads the normal `.git/index` exactly as today.
- A **`GIT_INDEX_FILE`-isolation mitigation is broken**: line 167's `just build-plugin` writes the **shared working tree**, racing regardless of index isolation. Lines 185–191's drift loop compares `just build-plugin`'s output against an isolated index that lacks the other session's already-staged plugin changes — false-positive drift failures.
- A **`git commit-tree` mitigation bypasses the hook entirely** — non-starter for a project whose value proposition is hook-enforced workflow discipline.

### Test infrastructure conventions

The closest precedent is **NOT** `tests/test_runner_concurrent_start_race.py` (uses `threading.Barrier`; tests `runner.pid` claims, not git ops). The correct precedent is `cortex_command/init/tests/test_settings_merge.py:340–389` (`test_concurrent_registers_under_flock`), which uses **subprocess** to test flock serialization across true OS-level processes.

For a deterministic git-race regression test, threads alone are insufficient — git's own `.git/index.lock` retry logic masks the race in 99% of same-process thread runs. The test needs:
- **Subprocess-based** (two `subprocess.Popen` invocations).
- **Deterministic delay injection** between stage and commit in one subprocess (e.g., a flag-controlled `time.sleep` in a test-only commit wrapper) to force the race window open pre-fix.
- **Tree-hash invariant assertion** (`git show HEAD --name-only` matches the staged-tree hash recorded before commit).
- **Pre-fix proof bar**: ≥95% reproducibility over 100 runs without the lock.
- **Post-fix proof bar**: 100/100 success with the lock.

### `cortex-validate-commit.sh` (PreToolUse hook for `git commit`)

`hooks/cortex-validate-commit.sh:1–111` validates the commit message format only. It does **not** check whether any lock is held. An LLM that runs `git add foo && git commit -m "Reasonable Subject"` directly via Bash satisfies the format check and **bypasses any advisory lock** entirely.

### Conventions to follow

- Sibling-lockfile pattern with `fcntl.flock(LOCK_EX)`, `try/finally` release, mode `0o600`.
- `bin/cortex-*` parity enforcement (`requirements/project.md` line 27): any new helper script must be wired through SKILL.md / requirements / docs / hooks / justfile / tests references, or fail the `bin/cortex-check-parity` static gate.
- Atomic state writes via tempfile + `os.replace()` (per `requirements/pipeline.md:126`).

## Web Research

### Git's concurrency model for the index

Git's `.git/index.lock` is per-write only — held during a single `git add` or the `update-index` phase of `git commit`, then released by atomic rename. There is **no documented cross-command lock spanning `git add` → `git commit`**. ([git-scm.com/docs/api-lockfile](https://git-scm.com/docs/api-lockfile), [git source `lockfile.h`](https://github.com/git/git/blob/master/lockfile.h))

> "Lockfiles only block other writers. Readers do not block, but they are guaranteed to see either the old contents of the file or the new contents of the file."

### Direct prior art — GitHub Desktop (2015)

[github.blog: Git concurrency in GitHub Desktop](https://github.blog/2015-10-20-git-concurrency-in-github-desktop/) — they explicitly hit this race and built an in-process `AsyncReaderWriterLock` wrapping the **sequence**, not individual git invocations. Quote: *"Exclusive operations behave like a barrier, waiting for previously-enqueued work to complete before beginning, and themselves finishing before any further work starts."* This is the closest documented precedent for the lock-the-sequence approach proposed here.

### `GIT_INDEX_FILE` semantics

Redirects which file the current git process uses as the index. Hooks inherit the env via git itself (per [git-scm.com/docs/githooks](https://git-scm.com/docs/githooks)). **Cautionary tale**: [pre-commit/pre-commit#3492](https://github.com/pre-commit/pre-commit/issues/3492) — the env var did not propagate into Docker hook containers, silently causing wrong-index commits. Any subprocess that re-execs into a sandbox or container needs explicit env propagation.

### `git commit-tree` and hook semantics

Plumbing command per [git-scm.com/docs/git-commit-tree](https://git-scm.com/docs/git-commit-tree). **Bypasses all porcelain hooks** (pre-commit, commit-msg, post-commit) by design. Race-free at the index level but eliminates the entire hook-enforcement substrate this project relies on.

### Documented race patterns and lockfile-location tradeoffs

[mjec.blog/2019/02/16/git-locks](https://mjec.blog/2019/02/16/git-locks/) gives the canonical `flock`-wrapper pattern; locks `$GIT_DIR` itself.

| Lockfile location | Pros | Risks |
|---|---|---|
| Inside `.git/` (e.g., `.git/cortex-commit.lock`) | Always-present, repo-scoped | `git fsck --strict` reports as `dangling`; survives `git gc` but **not fresh clone**; future git versions could collide on the name; cross-uid hazards if `sudo cortex` was ever run |
| Outside `.git/` (e.g., `~/.cache/cortex-command/locks/<repo-hash>.lock` or `$XDG_RUNTIME_DIR`) | No `.git/`-hygiene risk; survives repo recreation; ownership follows the user; intentional cross-worktree coordination | Need deterministic repo→hash mapping; tmpfs may vanish across reboots (acceptable — locks are session-local) |
| Reusing `.git/index.lock` | — | **Anti-pattern.** Git uses this name with `O_CREAT | O_EXCL`; pre-creating it makes every git command in the repo fail with "Another git process seems to be running." |

### Industry consensus for AI agents: per-agent worktrees

[Cursor docs](https://cursor.com/docs/configuration/worktrees), [Augment Code guide](https://www.augmentcode.com/guides/git-worktrees-parallel-ai-agent-execution), [appxlab.io](https://blog.appxlab.io/2026/03/31/multi-agent-ai-coding-workflow-git-worktrees/), [MindStudio](https://www.mindstudio.ai/blog/git-worktrees-parallel-ai-coding-agents). All converge: give each agent its own worktree. Quote (Augment): *"Operations that depend on repository objects (fetch, gc, hooks, config) are shared; operations that depend on the working directory (add, commit, checkout) are isolated per worktree."* The cortex-command overnight pipeline already follows this pattern for feature work; it does not extend to interactive sessions.

I found **no documented case** of an AI-agent tool deploying any of the four candidate mitigations from the ticket — published consensus is worktrees. The four candidates target a constrained version of the problem (same checkout, same index, multiple sessions) which is essentially novel prior-art-wise.

### `fcntl.flock` portability anti-pattern

`fcntl.flock` (BSD whole-file lock) is **silently ignored on NFS** on Linux and behaves inconsistently on **VirtioFS / 9p inside Docker Desktop / Lima / Colima / OrbStack**. POSIX byte-range locks via `fcntl.lockf` / `F_SETLKW` are NFS-aware. The `settings_merge.py` precedent uses `flock` and is fine because `~/.claude/` is virtually never on NFS — but `.git/` of a working repo can be on a network filesystem in enterprise dev environments. Either detect via `os.statvfs` and refuse, or use `lockf`.

### Anti-patterns

- Co-opting `.git/index.lock` as the application lock.
- `flock -n` (non-blocking) without backoff — spurious failures under contention.
- Locking too narrowly (just around `git commit`) — misses the `git add`→`git commit` interleaving (the exact bug).
- Locking too broadly (all of Claude's tool calls) — defeats parallelism.
- Verify-before-commit alone — TOCTOU detection-only with no resolution mechanism. Unsafe in isolation.
- `GIT_INDEX_FILE` without env-propagation discipline.
- `git commit-tree` while expecting project hooks to fire.

## Requirements & Constraints

### Concurrency-and-locking convention

`requirements/project.md:26`:
> "`cortex init` additively registers the repo's `lifecycle/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. This is the only write cortex-command performs inside `~/.claude/`; it is serialized across concurrent invocations via `fcntl.flock` on a sibling lockfile."

This is the only existing locking precedent at the requirements level. It is the convention to extend.

### Worktree isolation

`requirements/multi-agent.md:25–36` — per-feature worktrees at `.claude/worktrees/{feature}/` with their own branch (`pipeline/{feature}`); stale `.git/worktrees/{feature}/index.lock` removal is required. Implies (but does not state) per-worktree index isolation. Home-repo index is shared across sessions; this is implicit, not documented.

### Artifact-commit path

`requirements/pipeline.md:23–24`:
> "Artifact commits (lifecycle files, backlog status updates, session data) land on the integration branch, not local `main` — they travel with the PR"
> "The morning report commit is the only runner commit that stays on local `main`"

The followup-commit at `runner.py:_commit_followup_in_worktree` lands on the worktree's integration branch, satisfying this requirement *if* `cwd` is honored (see codebase caveat #2).

### Atomicity

`requirements/pipeline.md:126`:
> "All session state writes use tempfile + `os.replace()` — no partial-write corruption"

Scope is session state; not extended to git. The mitigation is required to extend the atomicity guarantee informally to the stage→commit sequence.

### CLAUDE.md commit conventions

CLAUDE.md (project root):
> "Always commit using the `/cortex-interactive:commit` skill — never run `git commit` manually"
> "A shared hook validates commit messages automatically"

Advisory text. The "shared hook" is `hooks/cortex-validate-commit.sh`, which validates message format only — does not enforce that commits go through any wrapper or hold any lock.

### `bin/cortex-*` parity enforcement

`requirements/project.md:27`:
> "`bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference (see `bin/cortex-check-parity` for the static gate). Drift between deployed scripts and references is a pre-commit-blocking failure mode."

If the fix introduces a new `bin/cortex-commit-locked` (or similar), the parity gate applies.

### Defense-in-depth permissions

`requirements/project.md:34`:
> "The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution."

Implication: PreToolUse hooks are the only enforcement layer for autonomous overnight git operations. If hook-based enforcement is the chosen escape from advisory-lock-honor problems, it must be designed to function under `--dangerously-skip-permissions`.

## Tradeoffs & Alternatives

| # | Approach | Coverage (index race) | Coverage (working-tree race) | Hook compat | LOC | Maintainability | Recommendation |
|---|---|---|---|---|---|---|---|
| 1 | Advisory `flock` on a sibling lockfile around stage→commit | Yes (if all callers honor) | No | ✅ | ~50 + tests | High (matches `settings_merge.py`) | **Primary** |
| 2 | Verify-before-commit (re-read `git diff --cached`) | Detects subset of interleavings only | No | ✅ | ~20 | Medium | **Reject** (TOCTOU; doesn't prevent) |
| 3 | `GIT_INDEX_FILE` isolation | Yes for index | **No** — `just build-plugin` writes shared working tree; drift loop produces false-positives | ⚠️ Drift-loop breakage | ~80 | Low | **Reject** |
| 4 | `git commit-tree` on constructed tree | Yes | Yes | ❌ Bypasses pre-commit + commit-msg hooks entirely | ~150–200 | Very low | **Reject** |
| 5 | Per-session ephemeral worktree for `/commit` | Yes | **Yes** (only candidate that solves both) | ✅ | ~300+ | High once shipped (extends overnight pattern) | **Defer** as follow-up |
| 6 | Reactive post-commit revert | Detects after commit lands; doesn't prevent | No | ✅ | ~80 | Low (destructive recovery) | **Reject** (fails acceptance criterion) |

### Why Candidate 1 with augmentations

- Only candidate that prevents the index race AND is hook-compatible AND has codebase precedent (`settings_merge.py`).
- Original ticket's "#1 + #2 belt-and-suspenders" framing **does not hold**: once #1 closes the window, #2 has nothing to detect; #2 alone is TOCTOU.
- Candidate 5 is architecturally the cleanest (eliminates working-tree contention from `just build-plugin` racing too) but is an order of magnitude bigger than the bug warrants. Recommend deferring as a follow-up backlog item if working-tree contention surfaces independently.

### Required augmentations identified by adversarial review (NOT part of the ticket's "Quickest path" framing)

1. **Lockfile location must NOT be `.git/`.** Place at `~/.cache/cortex-command/locks/<repo-hash>.lock` (or `$XDG_RUNTIME_DIR`). Survives repo recreation, dodges `git fsck --strict` warnings, dodges sudo-uid hazards, intentionally enables cross-worktree-of-same-repo coordination.
2. **Lock must be acquired BEFORE staging, not just before commit.** SKILL.md step 1 (preflight) must move inside the lock; staging at step 2 must be inside the lock; commit at step 5 stays inside the lock; release after step 5.
3. **`O_CLOEXEC` on the lockfile fd.** `os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)` to prevent inheritance into long-lived child subprocesses (e.g., a backgrounded `cortex overnight start`). Audit and patch `settings_merge.py:79` simultaneously — same latent bug.
4. **Hook-side enforcement is required.** Extend `hooks/cortex-validate-commit.sh` to detect `git commit` Bash invocations and reject any that lack `CORTEX_COMMIT_LOCK_HELD=1` env (set by the wrapper that holds the lock). Without this, the lock is advisory in name only and the original bug recurs via any direct-Bash `git commit`. The original bug observation says BOTH sessions were running `/commit` — protocol-honor was not the issue; some path within `/commit` itself, or a parallel non-`/commit` path (e.g., smoke-test cleanup) was the culprit.
5. **Cover `smoke_test._remove_tracked_lifecycle_dir` (lines 91–101)** — explicit `git rm` + `git commit` on the home-repo index. The ticket evidence (session A's files unstaged after commit, foreign content landing under A's subject) is most plausibly explained by something exactly like this `git rm`-then-commit sequence intervening.
6. **Strip `GIT_DIR` in `runner.py:_commit_followup_in_worktree`** (lines 421, 435) to mirror `outcome_router.py:178`. Independent of the lock; eliminates a documented escape from worktree isolation.
7. **NFS / network-fs guard.** Detect via `os.statvfs(lockfile_path)` whether the lock filesystem is local; either refuse with a clear error or fall back to `fcntl.lockf` (POSIX byte-range, NFS-aware).
8. **EACCES on stale-uid-owned lockfile**: handle with a clear message pointing the user to remove the file.
9. **Contention visibility.** First try `LOCK_EX | LOCK_NB`; on contention, log `"waiting on cortex-commit lock held by pid {N} (held for {n}s)"` after a 2s threshold, then fall through to blocking acquire. Never `LOCK_NB` alone.
10. **Test design.** Subprocess-based (NOT same-process threads); inject a deterministic delay between stage and commit via a flag-controlled wrapper; assert tree-hash invariant pre-fix and post-fix. Pre-fix bar: ≥95% race reproduction over 100 runs. Post-fix bar: 100/100 pass. Use `cortex_command/init/tests/test_settings_merge.py:340–389` as the precedent (subprocess flock test), NOT `tests/test_runner_concurrent_start_race.py` (threads, not OS-level processes).

### Reconstructed bug walkthrough (for spec-phase verification)

The ticket says: A staged 6 files; ran `/commit` with subject "Land lifecycle 127..."; commit `053ef22` landed with that subject but containing 2 files from lifecycle #097; A's files remained **unstaged** afterward. The pure two-`/commit`-sessions interleaving doesn't explain "A's files unstaged after." The most plausible interleaving involves a `git reset` / `git rm --cached` between A's stage and A's commit:

1. A: `git add <6 files>` → index has A's 6 files.
2. **Some other process**: runs a sequence that ends with `git rm --cached` of unrelated files, OR a `git reset` then re-stages a different set, OR `git stash` (which can drop the staged area).
3. **Some other process**: `git commit` → consumes whatever the index has now (which contains #097's 2 files in the bug observation).
4. A: composes message, runs `git commit -m "..."` → no-op or adds commit on top of step 3's commit but binds A's subject to step 3's content depending on exact timing.

The smoke-test cleanup at `smoke_test.py:91–101` is the most plausible candidate because it does exactly `git rm -r --force --ignore-unmatch <lifecycle dir>` followed by `git commit -m "chore: remove smoke test artifacts"`. **The proposed `flock` mitigation prevents this only if the lock covers `smoke_test._remove_tracked_lifecycle_dir` AND `/commit`.** This argues strongly for required augmentation #5.

## Adversarial Review

### Lockfile-creation `EACCES` from stale uid ownership

If `sudo cortex ...` was ever run, the lockfile in `.git/` would be `root:root` and subsequent normal-user sessions hit `EACCES` on `os.open` and crash `/commit`. Mitigation: lockfile location outside `.git/` (in user-owned cache dir) and graceful `EACCES` recovery with clear messaging.

### Pre-commit hook deadlock vector (today: low; defensive: codify as invariant)

`.githooks/pre-commit:167` runs `just build-plugin` while `git commit` (and therefore the cortex flock) is held. Today, nothing under `just build-plugin` calls a `bin/cortex-*` script that re-acquires the cortex lock. **But the proposed lock is at a fixed path** — any future `bin/cortex-*` that wants to "do a small commit" would silently deadlock. Codify as parity-style invariant: "no subprocess invoked under the cortex commit lock may attempt to re-acquire it."

### `GIT_DIR` env escape (independent of the proposed lock)

`runner.py:_commit_followup_in_worktree` lines 421, 435 do not strip `GIT_DIR`. If the runner ever inherits a stuck `GIT_DIR=<home-repo>/.git`, the worktree-scoped commit lands in the home repo. This is the same failure class as `lefthook#1265` cited at `lifecycle/archive/route-python-layer-backlog-writes-through-worktree-checkout/research.md:92`. Patch alongside the lock work.

### `flock` portability

Silently no-ops on Linux NFS; inconsistent on VirtioFS / 9p in some Docker / Lima / Colima / OrbStack setups. `~/.claude/` is virtually never on NFS, so the existing `settings_merge.py` precedent works; `.git/` of a working repo *can* be on NFS in enterprise dev environments. Use `fcntl.lockf` (POSIX byte-range, NFS-aware) or detect-and-refuse via `os.statvfs`.

### Advisory caveat survives even with PreToolUse hook teeth

Partial-rollout case: cortex v1 (pre-fix) in one checkout, v2 (post-fix) in another, both sessions over the same repo. v1 doesn't acquire; race remains. Soft mitigation: bump a deployment-tracking marker so `cortex init` warns operators about the upgrade window.

### Subprocess fd inheritance

`fcntl.flock` is shared across `fork()`. Without `O_CLOEXEC` on the lockfile fd, a long-lived background subprocess inherits it. If the python parent exits before the subprocess (e.g., `cortex overnight start` daemonizes), the lock outlives the parent and subsequent `/commit` calls block on a lock held by an unrelated daemon. **The existing `settings_merge.py:79` precedent has this latent bug too.** Fix both with `O_CLOEXEC`.

### Test design pitfall

Same-process `threading.Barrier` + two threads will hit git's internal `.git/index.lock` retry, masking the race in 99% of runs. Subprocess + injected stage→commit delay is required. Without this, the "regression test" is non-regression (passes pre-fix and post-fix, proving nothing).

### Head-of-line blocking under heavy contention

The lock serializes all home-repo commits during overnight rounds. With pre-commit hook including `just build-plugin` (5–15s), a single slow commit pins all sessions. Surface contention via `LOCK_NB` first-try with a "waiting on lock held by pid N for {n}s" log line at 2s.

## Open Questions

1. **Lockfile location**: `~/.cache/cortex-command/locks/<repo-hash>.lock` vs `$XDG_RUNTIME_DIR/cortex-commit-<repo-hash>.lock` vs sibling-of-`.git/`?
   *Deferred: will be resolved in Spec by asking the user. Research recommends the first option (`~/.cache/`) because tmpfs can vanish across reboots and not all users have `$XDG_RUNTIME_DIR` set on macOS, but this is a user/operator preference call.*

2. **Hook-side enforcement scope**: Extend `cortex-validate-commit.sh` to deny non-locked `git commit` Bash invocations, or rely on advisory-only with the SKILL.md mandate? The original bug had both sessions running `/commit`, so the protocol-honor argument alone is insufficient.
   *Deferred: will be resolved in Spec. Research strongly recommends hook-side enforcement, but it materially expands LOC and may need its own CLAUDE.md text.*

3. **Coverage list (which paths acquire the lock)**: Definitely `/commit` skill and `smoke_test._remove_tracked_lifecycle_dir`. The two worktree-scoped paths (`runner.py:_commit_followup_in_worktree`, `pipeline/conflict.py`) are isolated by `cwd` today but not enforced via `assert worktree_path != repo_root`. Should they (a) acquire the lock defensively, (b) get the assert, or (c) neither?
   *Deferred: will be resolved in Spec.*

4. **Latent `O_CLOEXEC` bug in `settings_merge.py`**: Patch in this lifecycle alongside the new code, or split into a separate ticket?
   *Deferred: will be resolved in Spec. Both options work; the patch is one line.*

5. **NFS guard**: In-scope (detect-and-refuse via `statvfs`, or fall back to `fcntl.lockf`), or deferred to a follow-up?
   *Deferred: will be resolved in Spec. Detect-and-refuse is the lightweight path; `lockf` portability is the heavier path.*

6. **Whether to deploy Candidate 5 (per-session ephemeral worktree) as a follow-up**: This is the only mitigation that addresses the working-tree race (parallel `just build-plugin` from two sessions writing the same plugin mirror files). The lock approach does NOT address that — concurrent `/commit`s under the lock still serialize their `just build-plugin` invocations, but a `just build-plugin` invocation outside `/commit` (e.g., direct `just` run during interactive debugging) can race.
   *Deferred: will be resolved in Spec by surfacing it as a follow-up backlog item. Out of scope for this ticket per the ticket's stated acceptance criteria.*
