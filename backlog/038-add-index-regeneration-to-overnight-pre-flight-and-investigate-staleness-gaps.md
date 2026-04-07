---
schema_version: "1"
uuid: c40893c6-e57a-4fd3-b861-3bb504ed7160
title: "Add index regeneration to overnight pre-flight and investigate staleness gaps"
status: complete
priority: high
type: chore
tags: [overnight, backlog, reliability]
areas: [overnight-runner,backlog]
blocked-by: []
created: 2026-04-06
updated: 2026-04-07
session_id: null
lifecycle_phase: research
lifecycle_slug: add-index-regeneration-to-overnight-pre-flight-and-investigate-staleness-gaps
complexity: complex
criticality: high
spec: lifecycle/add-index-regeneration-to-overnight-pre-flight-and-investigate-staleness-gaps/spec.md
---

The backlog index (`index.json`) can silently go stale when backlog `.md` files are edited directly (bypassing `update_item.py`). `select_overnight_batch()` prefers `load_from_index()` and only falls back to `parse_backlog_dir()` on structural errors — semantic staleness passes through silently. This caused a real bug during overnight planning where a renamed lifecycle directory wasn't picked up.

**Quick win**: Add `generate_index.py` to the overnight skill's Step 7 pre-flight, right before the uncommitted-files check. This is the critical consumer.

**Investigate further**:
- Whether a pre-commit hook on `backlog/` changes should auto-regenerate the index
- Whether `select_overnight_batch()` should validate index freshness (mtime comparison, field presence checks) before trusting it
- Whether `load_from_index()` should detect missing/new fields and trigger a regeneration rather than silently using stale data
- Deprecate `generate-index.sh` (bash, only produces `index.md`) in favor of `generate_index.py` (python, produces both `index.json` and `index.md`)
