---
schema_version: "1"
uuid: 1eade404-b107-4779-b4ad-fbb8e32467ae
title: Fix morning-review pre-merge auto-close ordering bug
status: complete
priority: high
type: chore
created: 2026-06-30
updated: 2026-07-01
parent: "340"
tags: ['skill-efficiency-remaining-work']
discovery_source: cortex/research/skill-efficiency-remaining-work/research.md
lifecycle_phase: research
lifecycle_slug: fix-morning-review-pre-merge-auto
complexity: complex
criticality: high
---
## Why
The morning-review skill body runs a full backlog auto-close step before the PR is merged, while a later walkthrough section is the post-merge closer the protocol deliberately moved closure to — and the walkthrough explicitly calls the pre-merge close "a bug." The model therefore receives two contradictory orderings of a destructive action (closing tickets) on every morning-review run. Because a contradiction misleads the model on every read regardless of caching, this is higher value than its near-zero byte count suggests: it is a correctness fix, not a token trim.

## Role
Remove the stale pre-merge auto-close from the skill body and collapse it to a pointer at the post-merge closer, so closure happens in exactly one place, after merge is confirmed. Ensure the no-PR and declined-merge paths still close their tickets somewhere rather than silently losing closure once the pre-merge step is gone.

## Integration
The post-merge closer already owns slug resolution, zero-padding, and the close-path exit handling; the skill-body step duplicates and pre-dates it. The fix routes the skill body to the single post-merge closer and verifies the closer's skip-guard does not leave a no-PR run with no closure path. The ordering the fix restores is the one the status-close ordering test already enforces.

## Edges
- Breaks if removing the pre-merge step drops closure entirely on the no-PR or declined-merge branch — closure must stay reachable post-merge for those cases.
- Must keep the post-merge closer as the sole closer; reintroducing any pre-merge close re-creates the bug.
- The status-close ordering test encodes the correct sequence and must stay green.

## Touch points
- skills/morning-review/SKILL.md:95-99 (stale pre-merge auto-close step to collapse to a pointer)
- skills/morning-review/references/walkthrough.md:435-438 (the §5 note declaring the pre-merge close a bug)
- skills/morning-review/references/walkthrough.md §6b (the post-merge closer — sole closer)
- tests/test_morning_review_status_close_ordering.py (ordering guard)
- plugins/cortex-core/skills/morning-review/ (auto-generated mirror)