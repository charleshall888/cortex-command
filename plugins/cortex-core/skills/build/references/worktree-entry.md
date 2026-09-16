# Interactive Worktree Entry

Loaded from implement.md §1 on the worktree arm (`resolved` with `worktree-interactive`, or `prompt` when the picker selection is the worktree option). §1 hands off one thing: the **entry mode** — `selected` (user picked it) or `suppressed` (`branch-mode: worktree-interactive` bypassed the picker). Follow to completion, then return to §2 — the session stays inside the worktree, so same-file tasks dispatch concurrently instead of serializing.

### 1a. Create

One call composes the overnight guard, `cortex-interactive-lock acquire`, and worktree creation, for both entry modes:

```bash
cortex-lifecycle-prepare-worktree --feature {slug}
```

`overnight-active` / `lock-held` → surface `message` verbatim; return to §1 without a worktree. `create-failed` → surface `message`; the verb already released the lock. `ok` → `worktree_path` is set; relay any `warning` (a stale runner.pid) in one line.

### 1b. Enter

1. `_origin_pwd=$(pwd)`; hold it for the session.
2. **`suppressed`** → skip the probe and auto-enter: `cd $(cortex-worktree-resolve interactive-{slug})`, surface the stable literal `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, continue to §2.
3. **`selected`** → `cortex-worktree-precondition`: exit 0 = not inside a worktree, proceed to 4; exit 1 = already inside → fallback, naming the detected worktree.
4. `EnterWorktree(path=<resolved-path>)` with the path from `cortex-worktree-resolve interactive-{slug}`, never a hardcoded prefix. Sets session CWD for later Bash calls and clears CWD-dependent caches. Any error → fallback.

**Fallback** — cd-shim `cd $(cortex-worktree-resolve interactive-{slug})` with a one-line diagnostic beginning `EnterWorktree skipped` naming the failure mode. Auto-enter affects only orchestrator Bash calls; §2's `Agent(isolation: "worktree")` dispatch and §2e merge-back are unaffected.

Surface the worktree path with a one-line warning: on session exit the harness asks keep-or-remove, and "remove" discards uncommitted work — commit or push first. Mid-session, `ExitWorktree action="keep"` clears state cleanly, or `cd $(git rev-parse --show-toplevel)` navigates back deferring the prompt. Do not exit `/cortex-core:build`; proceed to §2.
