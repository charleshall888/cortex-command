# Wontfix workflow

Use when an operator terminates a lifecycle without shipping — premise rejected, superseded, or the cost/value gate flipped. Drops it from SessionStart's "incomplete lifecycles" enumeration immediately and leaves a terminal marker that `cortex_command.common.detect_lifecycle_phase` and `claude/statusline.sh` read as `phase=complete`.

## How

```bash
cortex-lifecycle-wontfix <slug> --reason "<short rationale>"
```

As one fail-forward operation the verb: (a) archives the lifecycle directory to `cortex/lifecycle/archive/<slug>`, (b) appends the `feature_wontfix` terminal-state event to the archived `events.log`, (c) terminalizes the originating backlog item (status `wontfix`, lifecycle-phase `wontfix`, session released). The **move → append → terminalize order is a code invariant** — archive-move goes first because the name-based archive-skip in `scan_lifecycle.py` drops the lifecycle from SessionStart enumeration immediately, so a later-step failure still leaves a coherent terminal state.

By default the backlog target comes from the lifecycle's `index.md` parent fields; pass `--backlog-slug <slug>` to override (absent `index.md`, or ambiguous resolver). An ad-hoc lifecycle with no backlog parent terminalizes nothing — a clean no-op. Ambiguous backlog slug → the verb exits `2` with candidates on stderr; re-invoke with `--backlog-slug`. The `common.py` detector (`phase=complete` on the `feature_wontfix` marker) is defense-in-depth for phase queries against an archived `events.log`.
