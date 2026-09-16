# Wontfix

An operator terminates a lifecycle without shipping — premise rejected, superseded, or the cost/value gate flipped.

```bash
cortex-lifecycle-wontfix <slug> --reason "<short rationale>"
```

One fail-forward operation: archives the lifecycle to `cortex/lifecycle/archive/<slug>`, appends the terminal `feature_wontfix` event there, and terminalizes the backlog item (status `wontfix`, lifecycle-phase `wontfix`, session released) — move → append → terminalize, so a later-step failure still leaves a coherent terminal state. The backlog target comes from `index.md`'s parent fields; pass `--backlog-slug <slug>` when `index.md` is absent or the resolver is ambiguous (exit 2, candidates on stderr). An ad-hoc lifecycle with no parent terminalizes nothing.
