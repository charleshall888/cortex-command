# Wontfix workflow

Use when an operator terminates a lifecycle without shipping — premise rejected, superseded by another lifecycle, or the cost/value gate flipped. Goal: drop it from SessionStart's "incomplete lifecycles" enumeration immediately, and leave a terminal marker that `cortex_command.common.detect_lifecycle_phase` and `claude/statusline.sh` read as `phase=complete`.

## How

```bash
cortex-lifecycle-wontfix <slug> --reason "<short rationale>"
```

As one fail-forward operation the verb: (a) archives the lifecycle directory to `cortex/lifecycle/archive/<slug>`, (b) appends the `feature_wontfix` terminal-state event to the archived `events.log`, (c) terminalizes the originating backlog item (status `wontfix`, lifecycle-phase `wontfix`, session released). The **move → append → terminalize order is a code invariant** inside the verb.

By default the backlog target comes from the lifecycle's `index.md` parent fields; pass `--backlog-slug <slug>` to override (absent `index.md`, or ambiguous resolver). An ad-hoc lifecycle with no backlog parent terminalizes nothing — a clean no-op, not an error. Ambiguous backlog slug → the verb exits `2` with candidates on stderr; re-invoke with `--backlog-slug`.

## Why it lands as it does

Archive-move goes first because it's the safe end-state — the name-based archive-skip in `scan_lifecycle.py` drops the lifecycle from SessionStart enumeration immediately, so even a later-step failure leaves a coherent terminal state. The `common.py` detector is defense-in-depth: it returns `phase=complete` on the `feature_wontfix` marker, covering phase queries against an archived `events.log`.
