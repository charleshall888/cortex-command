---
schema_version: "1"
uuid: 3178e5ca-2289-4c21-a2f8-967112806956
title: "R8 should track installed-wheel-commit, not CWD-working-tree HEAD (#146 follow-up)"
status: backlog
priority: medium
type: bug
created: 2026-05-13
updated: 2026-05-13
discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md
tags: [mcp, upgrade]
---

## Problem

R8's freshness check resolves the "current" cortex-command commit from the wrong source. The `_maybe_check_upstream` helper in `plugins/cortex-overnight/server.py` calls `cortex --print-root` to obtain `head_sha`, and that command resolves the cortex repository root by running `git rev-parse --show-toplevel` from the caller's current working directory. The SHA it returns is therefore the **working tree's** HEAD in whichever cortex-command checkout the user happens to be operating inside — not the commit pinned by the installed wheel that is actually executing the MCP server code.

When CWD-context and wheel-version diverge — for example during normal dev iteration on the cortex-command repo itself, where the working tree often races ahead of origin while the installed wheel sits one or more tags behind both — R8 ends up comparing origin against the working tree, sees no gap, and reports "up to date." The wheel that is actually running can be substantially stale even as the freshness check signals all-clear. In other words, R8 can silently lie about staleness whenever the CWD-resolved HEAD and the installed-wheel pinned commit are not the same thing.

## Fix direction

R8 should compare upstream against the **installed wheel's** pinned commit/tag rather than the working tree's HEAD. The wheel's identity is recorded in the tool install metadata (e.g. `uv tool list` output, or the install-state directory uv maintains for the tool), and that is the value the freshness check needs to load. At minimum, R8 should detect the divergence case — CWD-HEAD != installed-wheel-commit — and surface a warning so the user is not misled into believing the running wheel is current when only the working tree is.

## Origin

Filed as a #146 follow-up during refine of #210 (item 5 — "R8 cwd-vs-installed-wheel divergence"). Parent ticket explicitly flagged this as a candidate to break out into its own backlog item rather than fold into the docs/hygiene-scoped #210 work.
