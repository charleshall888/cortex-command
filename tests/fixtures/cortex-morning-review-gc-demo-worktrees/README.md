# cortex-morning-review-gc-demo-worktrees golden-replay fixtures

This directory holds synthetic-state fixtures for the parity test that guards
the Python port of `bin/cortex-morning-review-gc-demo-worktrees`
(`cortex_command.overnight.gc_demo_worktrees`).

## Fixture format

Each test case is stored as five flat sibling files:

```
<case>.argv      one argv element per line (line 1 is the active-session-id)
<case>.stdin     literal bytes piped to stdin (empty for all cases)
<case>.stdout    literal bytes captured from stdout (empty for all cases)
<case>.stderr    expected tagged stderr lines; path tokens use <WT_PATH> placeholder
<case>.exitcode  the exit status as a single decimal integer + trailing newline
```

Unlike scripts that read static stdin, `gc_demo_worktrees` operates on real
git worktree state. Fixtures therefore use a `<WT_PATH>` placeholder for the
dynamic worktree path in expected `.stderr` content. The parity test builds
synthetic git state in `tmp_path`, runs the Python module, filters stderr to
tagged `[gc-demo-worktrees]` lines, replaces the actual worktree path with
`<WT_PATH>`, and compares against the fixture's `.stderr` content.

## Cases captured

| Case                      | Scenario                                                        | Session ID                  | Worktree state                           | Expected behaviour          |
|---------------------------|-----------------------------------------------------------------|-----------------------------|------------------------------------------|-----------------------------|
| `clean_worktree_removed`  | matching clean worktree is GC'd                                 | `other-session`             | one `demo-overnight-*` worktree, clean   | removed + pruning           |
| `dirty_worktree_skipped`  | matching dirty worktree (untracked file) is preserved           | `other-session`             | one `demo-overnight-*` with untracked    | skipped + pruning           |
| `active_session_excluded` | active-session worktree is silently excluded before state check | `overnight-2026-04-28-0900` | one `demo-<active_id>-*` worktree, clean | only pruning                |
| `no_tmpdir`               | `$TMPDIR` unset → silent early exit 0                          | `any-session`               | N/A (TMPDIR unset)                       | empty stdout/stderr, exit 0 |

Cases cover the primary control-flow paths:
- Happy-path removal (clean matching worktree swept).
- R9 skip (uncommitted state preserved).
- Active-session exclusion (fires before R9 check).
- TMPDIR-unset early-exit (silent, non-fatal).

## Determinism harness

- **jq version**: `jq-1.8.1` (pinned for cross-test consistency; this script
  does not invoke jq itself).
- **`LC_ALL=C`**: set during synthetic capture to force deterministic
  collation in any sub-process git output.
- **`TZ=UTC`**: set during synthetic capture; no timestamps are emitted by
  the script so this is belt-and-suspenders.
- **Timestamp handling**: this script emits no timestamps on stdout or stderr.
  The `<WT_PATH>` placeholder substitution is the only dynamic-content
  normalization required.
- **Synthetic state**: fixtures are not captured from live `$TMPDIR/cortex-worktrees/`
  state. Instead, the parity test builds a parent git repo and real git
  worktrees in `tmp_path` per case, then invokes the Python module with
  `TMPDIR` set to the synthetic tmpdir. This prevents flaky assertions from
  ambient runner state.
- **Path normalization**: on macOS, `realpath` resolves `/tmp` →
  `/private/tmp`; git's porcelain output reflects the resolved path. The
  `<WT_PATH>` placeholder absorbs this platform difference.

## Named-tolerance categories the parity test consumes

- **`error-formatter-shape`** (stderr): for cases where the Python port and
  bash original produce semantically equivalent tagged log lines (same
  prefixes, same exit codes), but the literal path bytes differ due to
  platform resolution. The parity test substitutes `<WT_PATH>` before
  comparison, reducing this to a structural equivalence check on the prefix
  pattern.

`key-reorder`, `unicode-escape`, `number-format`, and `trailing-newline` are
NOT opted into: this script emits no JSON and stdout is always empty.

## How to recapture

If the bash script is restored from history and re-captured, run from the
worktree root:

```bash
LC_ALL=C TZ=UTC bash -c '
    # For each scenario, build the synthetic state, then:
    # bin/cortex-morning-review-gc-demo-worktrees <active-session-id> \
    #     > <case>.stdout 2> <case>.stderr
    # echo $? > <case>.exitcode
    # Replace the worktree path in <case>.stderr with <WT_PATH>
'
```

For `clean_worktree_removed`, the expected tagged stderr after path substitution:
```
[gc-demo-worktrees] removing <WT_PATH>
[gc-demo-worktrees] pruning
```

For `dirty_worktree_skipped`, the expected tagged stderr after path substitution:
```
[gc-demo-worktrees] skipping <WT_PATH>: uncommitted state
[gc-demo-worktrees] pruning
```

For `active_session_excluded`, the expected tagged stderr (no path needed):
```
[gc-demo-worktrees] pruning
```

For `no_tmpdir`, expected stdout and stderr are empty; exit 0.
