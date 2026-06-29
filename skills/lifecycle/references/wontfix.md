# Wontfix workflow

Use when an operator decides a lifecycle should be terminated without shipping — typically because the premise has been rejected, the work is superseded by another lifecycle, or the cost/value gate has flipped against the feature. The goal is twofold: drop the lifecycle from SessionStart's "incomplete lifecycles" enumeration immediately, and leave a terminal-state marker that both `cortex_command.common.detect_lifecycle_phase` and `claude/statusline.sh` recognize as `phase=complete`.

## How

Run the order-enforcing verb:

```bash
cortex-lifecycle-wontfix <slug> --reason "<short rationale>"
```

It performs, as a single fail-forward operation, the three steps that used to be a hand-run bash sequence: (a) archive the lifecycle directory to `cortex/lifecycle/archive/<slug>`, (b) append the `feature_wontfix` terminal-state event to the archived `events.log`, and (c) terminalize the originating backlog item (status `wontfix`, lifecycle-phase `wontfix`, session released). The **move → append → terminalize order is now a code invariant** inside the verb — it is no longer prose you must follow by hand. The rationale (and the partial-failure safety reasoning) lives as comments in `cortex_command/lifecycle/wontfix_cli.py` and back-points to ADR-0004.

By default the verb reads the backlog target from the lifecycle's `index.md` parent fields. Pass `--backlog-slug <slug>` to override (e.g. when `index.md` is absent or the resolver is ambiguous). An ad-hoc lifecycle with no backlog parent terminalizes nothing — that step is a clean no-op, not an error.

**Ambiguous backlog slug**: if backlog resolution is ambiguous the verb exits `2` with the candidate list on stderr; re-invoke with `--backlog-slug` naming the intended item.

## Why it lands as it does

The archive move is first because it is the desired safe end-state: the name-based archive-skip at `cortex_command/hooks/scan_lifecycle.py:907` (`if feature in ("archive", "sessions"): continue`) drops the lifecycle from SessionStart enumeration immediately, so even a later-step failure leaves a coherent terminal state. The detector belt in `cortex_command/common.py` is defense-in-depth: it returns `phase=complete` whenever it sees the `{"event": "feature_wontfix"}` marker — covering archive-internal phase queries that inspect an archived `events.log` directly.
