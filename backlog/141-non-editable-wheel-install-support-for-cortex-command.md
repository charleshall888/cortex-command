---
schema_version: "1"
uuid: afb7fd7b-d127-46d1-a126-34c77e33b3da
title: "Non-editable wheel install support for cortex-command"
status: backlog
priority: medium
type: feature
tags: [distribution, packaging]
created: 2026-04-24
updated: 2026-04-24
blocks: []
blocked-by: []
---

# Non-editable wheel install support for cortex-command

## Context

Filed per R27 follow-up from lifecycle 115 (rebuild overnight runner under cortex CLI). 115 replaced `$_SCRIPT_DIR/../..` and `REPO_ROOT`-style path assumptions with explicit CLI path injection and `importlib.resources.files()` lookups, so packages and prompt resources are now package-internal. This ticket defers — but tracks — the remaining work to ensure those resolutions keep working under a non-editable wheel build backend.

## Problem

Today cortex-command is installed via `uv tool install -e .` (editable), which leaves package files on-disk at their source paths. Under a non-editable wheel install (`uv tool install cortex-command`), package resources are resolved through `importlib.resources` against the installed wheel layout rather than the source tree. R21 accepted the editable-install assumption for 115's scope; this ticket is the follow-up to verify non-editable installs work end-to-end.

## Scope

- Verify `importlib.resources.files("cortex_command.overnight.prompts")` and equivalent resource lookups return a usable `Traversable` under a non-editable wheel install.
- Add a smoke test that installs cortex-command from a built wheel (not editable) and exercises at least `cortex overnight start`'s prompt-template loading path end-to-end.
- Identify any remaining on-disk path assumptions (e.g., `Path(__file__).parent / "..."`) that would break under a zipped / non-editable layout, and convert them to `importlib.resources` usage.

## Out of scope

- Packaging the project for PyPI / Homebrew (tracked in 125 and the 113 distribution epic).

## References

- Lifecycle 115 review.md (R21 deferral)
- `cortex_command/overnight/prompts/` — the primary package-resource surface that must stay resolvable
