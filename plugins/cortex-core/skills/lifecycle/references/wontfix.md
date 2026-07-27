# Wontfix

Use when an operator terminates a lifecycle without shipping — premise rejected, superseded, or the cost/value gate flipped.

```bash
cortex-lifecycle-wontfix <slug> --reason "<short rationale>"
```

As one fail-forward operation the verb archives the lifecycle directory to `cortex/lifecycle/archive/<slug>`, appends the terminal `feature_wontfix` event to the archived `events.log`, and terminalizes the originating backlog item (status `wontfix`, lifecycle-phase `wontfix`, session released). The **move → append → terminalize order is a code invariant**: archiving first drops the lifecycle from SessionStart's incomplete-lifecycle enumeration immediately, so a later-step failure still leaves a coherent terminal state.

The backlog target comes from the lifecycle's `index.md` parent fields by default; pass `--backlog-slug <slug>` to override when `index.md` is absent or the resolver is ambiguous. An ad-hoc lifecycle with no backlog parent terminalizes nothing — a clean no-op. Ambiguous slug → exit `2` with candidates on stderr; re-invoke with `--backlog-slug`.
