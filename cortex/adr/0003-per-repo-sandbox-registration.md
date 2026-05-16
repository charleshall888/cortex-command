---
status: accepted
---

# Per-repo sandbox registration

`cortex init` additively registers the current repo's `cortex/` umbrella path into the `sandbox.filesystem.allowWrite` array of `~/.claude/settings.local.json` — the only write cortex-command makes outside its own tree — using `fcntl.flock` to serialize concurrent inits and avoid corrupting that array. We chose per-repo additive registration because interactive Claude Code sessions and the overnight runner both need to write under `cortex/` without per-call sandbox prompts, and additive merging lets multiple cortex-command checkouts coexist in one user account without clobbering each other's entries.

## Considered Options

- **Machine-wide setup script** (rejected): a one-time installer could pre-authorize a global path pattern, but that breaks portability across machines and across users who clone into different parent directories, and it hides the carve-out from the per-repo lifecycle that actually depends on it.
- **No sandbox carve-out** (rejected): leaving `cortex/` outside `allowWrite` would force interactive sessions and overnight runs to either prompt on every write (defeating overnight autonomy) or run with `--dangerously-skip-permissions` for ordinary work (eroding the defense-in-depth posture that makes sandbox the critical surface).
