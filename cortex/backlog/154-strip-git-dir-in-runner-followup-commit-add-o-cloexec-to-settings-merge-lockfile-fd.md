---
schema_version: "1"
uuid: 8205b953-aa85-4129-ae6a-627244d6b071
title: "Strip GIT_DIR in runner followup-commit + add O_CLOEXEC to settings_merge lockfile fd"
status: complete
priority: medium
type: bug
created: 2026-04-29
updated: 2026-04-29
---

## Problem

Two latent bugs surfaced during the research for #135 (now `wontfix`). Both are independent of the parallel-`/commit` race that #135 chose not to fix.

### 1. `runner.py:_commit_followup_in_worktree` does not strip `GIT_DIR`

`cortex_command/overnight/runner.py:406-448` invokes `subprocess.run(["git", ...], cwd=str(worktree_path), ...)` without filtering the inherited environment. If the parent process inherits a stuck `GIT_DIR=<home-repo>/.git` (from a hook env, a developer's shell var, a misconfigured cron entry), the worktree-scoped commit lands in the home repo despite `cwd`. Same failure class as `lefthook#1265`, already cited at `lifecycle/archive/route-python-layer-backlog-writes-through-worktree-checkout/research.md:92`.

`cortex_command/overnight/outcome_router.py:177-178` already strips `GIT_DIR` for exactly this reason; the followup-commit path is missing the same hardening.

### 2. `settings_merge.py:_acquire_lock` does not set `O_CLOEXEC` on the lockfile fd

`cortex_command/init/settings_merge.py:79`:

```python
lock_fd = os.open(lockfile_path, os.O_RDWR | os.O_CREAT, 0o600)
```

`fcntl.flock` is shared across `fork()`. Without `O_CLOEXEC` (or `os.set_inheritable(fd, False)`), a long-lived background subprocess inherits the fd and the lock. If the parent exits (e.g., a daemonized child), the lock outlives the parent and subsequent `cortex init` invocations block indefinitely on a lock held by an unrelated process.

## Fix

Both fixes are 1–2 lines:

```python
# runner.py:_commit_followup_in_worktree (lines 421, 435)
env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}
subprocess.run([...], cwd=str(worktree_path), env=env, ...)
```

```python
# settings_merge.py:79
lock_fd = os.open(lockfile_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
```

## Acceptance criteria

- `_commit_followup_in_worktree` invocations explicitly strip `GIT_DIR` from the subprocess env.
- `settings_merge._acquire_lock` opens the lockfile with `O_CLOEXEC`.
- Existing tests pass; targeted new test for each fix is nice-to-have but not required (these are guard-class fixes).

## Related

- Surfaced during research for #135 (`wontfix`); see `lifecycle/shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits/research.md` Adversarial Review section.
