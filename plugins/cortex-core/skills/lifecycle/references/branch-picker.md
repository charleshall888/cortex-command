# Branch-Picker Decision Logic (shared)

Shared decision logic for assembling the branch/dispatch option set and routing
suppressed branch-modes. Consumed by **Plan §4** (the merged approval surface) and
**Implement §1** (the fallback picker). This reference describes *what options
result and how suppressed modes route* — the consuming phase body performs the
actual preflight reads and renders the menu. Keep the menu-render call and the
per-repo branch-mode read in the consuming phase body, not here.

## Inputs (supplied by the consuming phase body)

The phase body reads two values before consulting this reference and passes them
in:

1. **`branch_mode`** — the per-repo configured value (the phase body reads it; one
   of `worktree-interactive | trunk | feature-branch | prompt`, or empty when
   unset/invalid).
2. **`{fire, reason}`** — the picker decision from `cortex-lifecycle-picker-decision .
   {slug} {branch_mode}`, where `reason` is one of the closed set
   `branch_mode_unset_or_invalid | branch_mode_prompt | dirty_tree |
   live_interactive_worktree_session | suppressed`.

## Suppressed routing (`fire == false`, reason `suppressed`)

When the decision is `(false, "suppressed")`, do **not** render a menu — route by
the configured `branch_mode` value:

- `worktree-interactive` — record entry mode `suppressed` and proceed to Implement
  §1a (Interactive Worktree Creation); §1a step v routes structurally to the
  cd-shim (no `EnterWorktree`, per ADR-0008).
- `trunk` — proceed on the current branch to §2 Task Dispatch.
- `feature-branch` — create and check out `feature/{lifecycle-slug}`, then proceed
  to §2.

## Fall-through (`fire == true`)

When the decision is `(true, reason)` for any `reason`
(`branch_mode_unset_or_invalid`, `branch_mode_prompt`, `dirty_tree`,
`live_interactive_worktree_session`), assemble and render the option set per the
two adjustments below.

### Uncommitted-changes guard (demotion)

Immediately before rendering, run `git status --porcelain` (no path filter, no
flags). If output is non-empty, demote the stay-on-current-branch option **in
place** — do not remove it, do not gate behind a pre-question:

- (a) prepend the fixed one-line warning
  `Warning: uncommitted changes in working tree — this will mix them into the
  commit on main.` as a prefix to that option's description, and
- (b) strip the `(recommended)` suffix from that option's label if present.

If `git status --porcelain` exits non-zero (missing `.git`, corrupt index,
bisect/rebase state), the guard does not fire — surface the single-line diagnostic
`uncommitted-changes guard skipped: git status failed` alongside the menu and
continue.

### Runtime probe (3-way degrade)

Probe whether the worktree console-script is reachable on PATH:

```bash
command -v cortex-worktree-create >/dev/null 2>&1
```

Route by exit code into one of three menu dispositions:

- **exit 0** — reachable → all three options remain: current branch, feature branch
  with worktree, create feature branch.
- **exit 1** — not on PATH → silently remove the worktree option (no diagnostic).
  The post-degrade set is current branch + create feature branch.
- **execution failure, or any exit code other than 0/1** — fail open: all three
  options remain, and surface the literal diagnostic
  `runtime probe skipped: console-script probe failed` alongside the menu.

## Resulting option set

The assembled options (closed set, subject to the demotion/degrade above):

| option label | dispatch value | routes to |
|---|---|---|
| Implement on current branch | `trunk` | §2 |
| Implement on feature branch with worktree | `worktree-interactive` | §1a (entry mode `selected`) |
| Create feature branch | `feature-branch` | create+checkout `feature/{slug}`, then §2 |

The consuming phase body renders these as its menu options and maps the selected
option to its dispatch value and routing target.
