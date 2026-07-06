# Critical Review Gate

Shared skip-path protocol for the §3b Critical Review gate in Specify and Plan phases — consulted after the inline command pair has run, only when the skip branch applies.

## Corrupted State Rule

If either `cortex-lifecycle-state` read contains `"corrupted": true`, follow the canonical corrupted-state rule in `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` — treat the feature as requiring review rather than skipping.

## Non-Local Seed-Tier Rule

Same "untrustworthy tier → review, don't skip" posture for a second seed-tier hole: when the backend (`cortex-read-backlog-backend`) ≠ `cortex-backlog` AND the §3b decision would skip-silent at `tier = simple` AND `cortex/lifecycle/{feature}/research.md` exists (Clarify may have been bypassed, leaving state stuck at the `simple/medium` seed), require review instead. The local (`cortex-backlog`) path is exempt — its `reconcile-clarify --backlog-slug` re-sources tier/criticality from backlog frontmatter on resume, so its seed is trustworthy.

## Run/Skip Matrix

- **Skip-silent** when `tier = simple` (any criticality): proceed directly to user approval, no event logged.
- **Log+skip** when `tier = complex` AND `criticality = low`: append the event below so the skip rate is observable, then proceed to user approval: `cortex-lifecycle-event critical-review-skipped --feature <name> --phase <phase> --tier complex --criticality low`
  Substitute `<phase>` with the active phase (`specify` or `plan`).
