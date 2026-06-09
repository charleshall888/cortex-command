---
schema_version: "1"
uuid: e7baef47-a98a-4125-8ac3-9de563bff1db
title: "Morning report scans all lifecycle dirs and retry-ticket titles are unquoted YAML"
status: complete
priority: medium
type: bug
created: 2026-06-09
updated: 2026-06-09
complexity: complex
criticality: high
spec: cortex/lifecycle/morning-report-scans-all-lifecycle-dirs/spec.md
areas: ['report', 'backlog']
---
Observed in wild-light overnight run `overnight-2026-06-09-0222`.

## Bug A — report sections are not session-scoped
`overnight/report.py:1031` globs `lifecycle_root.glob("*/critical-review-residue.json")` and `:655`/`:671` glob `cortex/lifecycle/*/review.md` — the ENTIRE lifecycle tree, not the session feature set (available as `data.state.features`, already used by `render_completed_features`). In this run all 13 "Critical Review Residue" entries and the "Requirements Drift Flags" features were from unrelated historical lifecycles (the 4 session features wrote no review.md / residue), so the morning report was dominated by noise unrelated to the run; it grows worse with repo history. Fix: filter both globs by the session feature set and fix the `(N)` header counts.

## Bug B — auto-filed retry-ticket titles are unquoted (malformed YAML)
The session-finalization "Retry deferred: {slug}" backlog tickets write the title UNQUOTED into YAML frontmatter, e.g. `title: Retry deferred: climb-gated-locomotion-...`. The embedded `: ` is invalid YAML → `failed to parse frontmatter`. Worse, this then breaks `cortex-update-item` for the ENTIRE backlog (it scans every file and aborts on the bad one), blocking all status updates until the file is removed. Fix: quote/escape the title when generating retry/followup tickets (any generated title may contain a colon).