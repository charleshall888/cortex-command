# Wontfix

An operator ends a lifecycle without shipping: the premise was rejected, it was superseded, or it is no longer worth the cost.

```bash
cortex-lifecycle-wontfix <slug> --reason "<short rationale>"
```

One command that, in order, moves the lifecycle to `cortex/lifecycle/archive/<slug>`, appends the final `feature_wontfix` event there, then closes the backlog item (status `wontfix`, lifecycle-phase `wontfix`, session released). If a later step fails, the lifecycle is still cleanly ended. The backlog target comes from `index.md`'s parent fields; pass `--backlog-slug <slug>` when `index.md` is absent or the match is ambiguous (exit 2, candidates on stderr). An ad-hoc lifecycle with no parent closes no backlog item.
