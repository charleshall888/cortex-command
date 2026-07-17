# Interactive Worktree Entry

Loaded from implement.md §1 whenever the worktree arm is entered — on the `resolved` state with `worktree-interactive`, or on the `prompt` state when the picker selection is the worktree option (the branch-decision verb returns `prompt` before the choice exists, so the load keys on the selection, not the verb state). §1 hands off one thing: the **entry mode** marker. Follow this file to completion, then return to implement.md §2 — the session stays inside the worktree.

Route on the carried entry mode:

- **`selected`** — the user picked the worktree option (or `prompt` → worktree). Run **Step A** first; a Step A rejection returns to §1 without creating a worktree. On pass, continue to §1a.
- **`suppressed`** — `branch-mode: worktree-interactive` bypassed the picker. Skip Step A and go straight to §1a; its own overnight guard runs there (step v routes to the cd-shim).

**Step A — Overnight-active rejection**: source the overnight-probe sidecar; on exit 1 surface interactive-tailored wording:

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to complete (`cortex overnight status`), or open a different feature." "$(_resolve_user_project_root)"
```

Exit codes: `0` = none active, proceed to §1a; `1` = overnight live, surface the wording and return to §1 without creating a worktree; `2` = stale runner, warn-and-continue to §1a.

### 1a. Interactive Worktree Creation (Alternate Path)

Two entry modes: `selected` (user picked the worktree option) or `suppressed` (`branch-mode: worktree-interactive` bypassed the picker). Step v branches on the carried marker; either way the orchestrator session continues into §2.

**i. Prepare** — one call composes the overnight guard, `cortex-interactive-lock acquire`, and `create_worktree`, running unconditionally for both entry modes:

```bash
cortex-lifecycle-prepare-worktree --feature {slug}
```

Act on `state`:

- **`overnight-active`** — surface `message` verbatim and exit §1a without creating a worktree.
- **`lock-held`** — a live same-slug session holds the lock; surface `message` verbatim and exit §1a without creating a worktree.
- **`create-failed`** — surface `message` (`repr(exc)`) and exit §1a; the verb already released the lock if this session owned it.
- **`ok`** — `worktree_path` is set; relay any `warning` (a stale runner.pid) as a one-line diagnostic, then continue to Step v.

**Step v — Auto-enter sequence** (steps ii–iv were absorbed into `cortex-lifecycle-prepare-worktree`; the i→v gap is intentional — do not renumber, tests and cross-refs anchor on these labels)

After `state: ok`, run in this order:

1. **Capture origin pwd** — `_origin_pwd=$(pwd)`; hold it for the session (restore at Complete or on fallback).
2. **Suppressed-picker structural branch** — `suppressed` skips the `cortex-worktree-precondition` probe AND the auto-enter, routing structurally to the cd-shim: `cd $(cortex-worktree-resolve interactive-{slug})`, surfacing the stable literal `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, then continuing to §2. `selected` skips this branch and continues to op 3.
3. **Already-in-worktree probe** (`selected`) — `cortex-worktree-precondition`. Exit 0 = not inside a worktree (proceed); exit 1 = already inside (skip op 4, route to fallback naming the detected worktree).
4. **Auto-enter** (`selected`, probe returned 0) — `EnterWorktree(path=<resolved-path>)` where `<resolved-path>` is `cortex-worktree-resolve interactive-{slug}`'s output (never a hardcoded prefix — R3). Sets session CWD to the worktree for all subsequent Bash calls and clears CWD-dependent caches. Error (path not in `git worktree list`, schema rejection, "Must not already be in a worktree" race) → fallback.

**Fallback — `EnterWorktree skipped`.** On the `selected` path (op-3 probe non-zero, op-4 `EnterWorktree` error, or the skill declines the tool): cd-shim handoff `cd $(cortex-worktree-resolve interactive-{slug})`, with a one-line diagnostic beginning `EnterWorktree skipped` naming the failure mode. Auto-enter affects only orchestrator-session Bash calls; §2 sub-agent `Agent(isolation: "worktree")` dispatch and §2(e) merge-back are unaffected.

**vi.** On `suppressed`, `cd $(git rev-parse --show-toplevel)` is the only restoration needed. Surface the worktree path with a one-line warning: on session exit the harness prompts to keep/remove — "remove" discards uncommitted work, so commit or push first. Mid-session, `ExitWorktree action="keep"` clears state cleanly, or `cd $(git rev-parse --show-toplevel)` navigates back deferring the prompt.

**vii.** Do not exit `/cortex-core:lifecycle` — the session is inside the worktree; proceed to §2.
