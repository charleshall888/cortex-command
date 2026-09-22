# Interactive Worktree Entry

implement.md §1 sends you here for a worktree (`resolved` with `worktree-interactive`, or `prompt` when the user picks the worktree option). §1 passes one thing, the **entry mode**: `selected` (the user picked it) or `suppressed` (`branch-mode: worktree-interactive` skipped the picker). Finish this file, then return to §2. The session stays inside the worktree, so same-file tasks can run at once instead of one by one.

### 1a. Create

One call does the overnight check, `cortex-interactive-lock acquire`, and worktree creation, for both entry modes:

```bash
cortex-lifecycle-prepare-worktree --feature {slug}
```

`overnight-active` / `lock-held` → show `message` exactly; return to §1 without a worktree. `create-failed` → show `message`; the lock is already released. `ok` → `worktree_path` is set; show any `warning` (a stale runner.pid) in one line.

### 1b. Enter

1. `_origin_pwd=$(pwd)`; keep it for the session.
2. **`suppressed`** → skip step 3 and enter: `cd $(cortex-worktree-resolve interactive-{slug})`, print exactly `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, continue to §2.
3. **`selected`** → `cortex-worktree-precondition`: exit 0 = not inside a worktree, go to 4; exit 1 = already inside → fallback, naming that worktree.
4. `EnterWorktree(path=<resolved-path>)` with the path from `cortex-worktree-resolve interactive-{slug}`, never a hardcoded prefix. It sets the session CWD for later Bash calls. Any error → fallback.

**Fallback** — `cd $(cortex-worktree-resolve interactive-{slug})` and print one line that starts `EnterWorktree skipped` and names what failed. Entering changes only your own Bash calls; §2's `Agent(isolation: "worktree")` dispatch and §2e merge-back work the same.

Show the worktree path with a one-line warning: on session exit the harness asks keep or remove, and "remove" discards uncommitted work, so commit or push first. Mid-session, `ExitWorktree action="keep"` leaves cleanly, or `cd $(git rev-parse --show-toplevel)` goes back and puts off the prompt. Do not exit `/cortex-core:build`; go on to §2.
