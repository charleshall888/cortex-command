# Critical Review Gate

Skip-path protocol for Specify's §3b Critical Review gate — consulted after the inline state read has run, only when the skip branch applies. The gate runs at spec only; the plan phase dispatches no critical-review (the end-of-implementation review is the backstop).

## Corrupted State Rule

If the `cortex-lifecycle-state` read contains `"corrupted": true`, follow the canonical corrupted-state rule in `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` — treat the feature as requiring review rather than skipping.

## Non-Local Seed-Tier Rule

Same "untrustworthy tier → review, don't skip" posture for a second seed-tier hole: when the backend (`cortex-read-backlog-backend`) ≠ `cortex-backlog` AND the §3b decision would skip-silent at `tier = simple` AND `cortex/lifecycle/{feature}/research.md` exists (Clarify may have been bypassed, leaving state stuck at the `simple/medium` seed), require review instead. The local (`cortex-backlog`) path is exempt — its `reconcile-clarify --backlog-slug` re-sources tier/criticality from backlog frontmatter on resume, so its seed is trustworthy.

## Run/Skip Matrix

- **Skip** when `tier = simple` (any criticality), or when `tier = complex` AND `criticality = low`: proceed directly to user approval.
