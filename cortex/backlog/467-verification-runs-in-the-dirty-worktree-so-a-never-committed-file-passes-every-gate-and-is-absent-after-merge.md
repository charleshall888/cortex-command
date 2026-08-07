---
schema_version: "1"
uuid: 9589303b-4ce4-43b6-9841-aa432b068550
title: Verification runs in the dirty worktree, so a never-committed file passes every gate and is absent after merge
status: should-have
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-07
---
## Why

A feature's Verification step runs against the **working tree**, which includes untracked
files. A newly authored file therefore passes verification in the worktree and is **absent
from the committed tree** if it was never `git add`ed. Both are true at once, and nothing
in the gate chain compares them.

wild-light #479 (`no-gate-anywhere-runs-pytest-so`) shipped exactly this. The feature's
whole purpose was to make the Python suite run inside a gate. It landed:

- the `test-command` wiring (`uv run scripts/tools/run_python_tests.py`),
- an ADR ratifying the decision,
- the docs row in the check-ownership inventory,
- **243 lines of `tests/python/test_run_python_tests.py`** — tests *for* the script,

and never added `scripts/tools/run_python_tests.py` itself. `git log --all --
'**/run_python_tests.py'` returned nothing. The file existed only as
`?? scripts/tools/run_python_tests.py` in the feature's own worktree.

Result after merge: `test-command` died with `error: Failed to spawn ... No such file or
directory (os error 2)` at **every Review and Complete in that repo**, and the ticket's own
goal was still unmet — pytest still never ran. Strictly worse than before the ticket
landed. It went unnoticed until a Lifecycle Review was run by hand two days later.

**Every gate was green, and each for a defensible reason:**

- the pre-commit hook cannot see an unstaged new file;
- `git commit --only <paths>` does not pick one up;
- the SubagentStop tripwire runs `validate_project.py` over the **dirty** tree by design
  (wild-light ADR-0045), so the untracked file was present when it ran;
- the feature's own Verification ran the script successfully — from the worktree.

No gate is individually wrong. The gap is that **nothing asserts the committed tree can do
what the worktree just proved.**

This generalises past new scripts to anything referenced *by path* rather than imported: a
gate command, a config value pointing at a file, a fixture path, a scene reference. The
same repo already carries a narrower instance of the pattern — a new `.gd` file whose
`.uid` sidecar is authored but not staged.

## Role

Close the gap between "verified in the worktree" and "works after merge". Cheapest
sufficient version first — this does not need a clean-checkout re-run to be worth shipping.

Options worth weighing at plan time:

- **Tracked-ness assertion at implement exit.** For each path the change references from a
  gate/config surface, `git ls-files --error-unmatch <path>`. Fails loudly, costs
  milliseconds, and would have caught #479 exactly.
- **Untracked-file report at the batch checkpoint.** Surface `git status --short` `??`
  entries in the feature worktree before the merge, so an unstaged new file is visible
  rather than silent.
- **Verify against the committed tree.** Strongest and most expensive: re-run Verification
  from a clean checkout of the feature branch. Catches the whole class, not just
  path-referenced files.

## Integration

- The implement-phase exit path and its batch checkpoint (where an untracked-file sweep
  would sit)
- Whatever consumes a lifecycle's `test-command` — it is the surface most likely to name a
  path that must exist post-merge
- The pre-merge step in `cortex_command/overnight/` — a merge is the moment the worktree
  stops being the source of truth

## Edges

- **Non-goal**: recovering wild-light #479. Already repaired by hand (wild-light
  `9cde2d0f`).
- **Non-goal**: making the SubagentStop tripwire run over a clean tree. Its dirty-tree
  scope is deliberate (ADR-0045) and correct for what it does.
- A guard must not fire on legitimately-untracked files — build output, `.venv`,
  gitignored artifacts. Scoping it to *referenced* paths avoids most of that.
- The failure is silent and delayed: the cost lands on whoever runs the next gate, not on
  the author, so "the author would notice" is not a mitigation.

## Touch-points

- Source incident: wild-light `overnight-2026-08-07-0252`, feature
  `no-gate-anywhere-runs-pytest-so`; the wiring change is `7f8e2d9c` (touches
  `lifecycle.config.md` only); the repair is `9cde2d0f`
- Same-session siblings: #464 (number collisions), #465 ($TMPDIR worktree purge), #466
  (residue durability)
