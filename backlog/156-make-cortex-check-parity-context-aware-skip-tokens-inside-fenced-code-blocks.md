---
schema_version: "1"
uuid: 9cfcaf29-ad85-460c-a44b-aab95905f16b
title: "Make cortex-check-parity context-aware (skip tokens inside fenced code blocks)"
status: backlog
priority: low
type: feature
tags: [tooling, parity-linter, hooks]
areas: [tooling]
created: 2026-05-01
updated: 2026-05-01
---

# Make cortex-check-parity context-aware (skip tokens inside fenced code blocks)

## Problem

`bin/cortex-check-parity` regex-scans markdown for `cortex-[a-z][a-z0-9-]*` tokens and treats anything not in `bin/`, the 3-entry `RESERVED_NON_BIN_NAMES` set, or `bin/.parity-exceptions.md` as a missing script reference (E002). The scan is context-blind — a path-segment placeholder inside a fenced code block is treated identically to a prose script reference.

Ticket 149's lifecycle (2026-05-01) hit this: `docs/setup.md:310` had `/path/to/your/cortex-command-clone/claude/statusline.sh` inside a JSON code block. The `cortex-command-clone` token tripped E002. Worked around by rephrasing the placeholder (commit `f817c11`); the underlying linter limitation is unaddressed.

## Why it matters

Every commit during ticket 149's lifecycle hit this drift. Future docs that need `cortex-*`-shaped path placeholders (especially under the no-clone wheel-install migration where setup.md is still actively edited) will hit the same false-positive treadmill. The `.parity-exceptions.md` schema doesn't fit placeholders — its `category` enum (`maintainer-only-tool` / `library-internal` / `deprecated-pending-removal`) is for actual scripts.

## Proposed approaches (research phase)

1. **Skip fenced code blocks entirely.** Cheapest. Token references inside ` ``` ... ``` ` and inline ` `code` ` spans are excluded from the candidate set. Risk: a real script reference quoted as code (e.g., `` `cortex-pr-rollup` ``) would no longer count as a wiring signal — needs separate audit of whether code-spanned references are load-bearing for current allowlist entries.
2. **Path-segment heuristic.** Skip tokens that appear inside path-like contexts (`/cortex-foo/`, `/cortex-foo/bar`). Narrower; preserves prose code-span scanning. More fragile.
3. **Allowlist placeholder names.** Extend `RESERVED_NON_BIN_NAMES` with documented placeholder tokens. Cheapest by line count; doesn't fix the design issue.

Default recommendation pending research: (1), with a pre-flight scan to confirm code-spanned references aren't load-bearing.

## Discovery context

Surfaced during `/cortex-interactive:lifecycle 149` implementation when every commit hit E002 on `docs/setup.md:310`. Workaround landed as commit `f817c11`.
