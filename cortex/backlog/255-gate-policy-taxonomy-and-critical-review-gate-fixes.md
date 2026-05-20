---
schema_version: "1"
uuid: 1a01b03c-38b8-4ea8-b1e9-3ebe074a38aa
title: "Gate-policy taxonomy and critical-review gate fixes"
status: complete
priority: high
type: feature
created: 2026-05-20
updated: 2026-05-20
parent: "251"
tags: [critical-review, gate-policy]
discovery_source: cortex/research/harness-friction-triage/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/gate-policy-taxonomy-and-critical-review/spec.md
areas: [skills]
session_id: null
---

## Role

Four targeted fixes to the critical-review module plus a source-level taxonomy that makes gate policy auditable from the source itself. First, annotate every gate with a comment of the form `# gate-class: security|hygiene|advisory` so the policy classification is grep-discoverable. Second, replace the ancestor-symlink check (which rejects macOS `/tmp/claude` paths the sandbox config sanctions) with an under-root scoping check that only rejects symlinks at-or-below the matched artifact root. Third, add a hygiene auto-resolve helper that copies ad-hoc input outside the lifecycle and research directories into a canonical scratch dir under `cortex/lifecycle/_adhoc/<sha-prefix>/` — gitignored, with a 7-day retention policy via a `cortex clean --adhoc` recipe and a `source_path:` field recorded in the events log. Fourth, rename `verify-reviewer-output` to `check-artifact-stable` and explicitly drop the reviewer-engagement claim — per Decision Record DR2 in the discovery research, no structural mechanism for an engagement check exists in the current architecture, and prose-only enforcement is rejected by the project's "structural separation over prose-only enforcement" principle.

## Integration

Each of the four fixes lands independently with no inter-fix ordering constraint. The auto-resolve helper restores the skill-prose contract in the critical-review skill that promises ad-hoc invocation outside a lifecycle by funneling such inputs through the `_adhoc/` scratch dir rather than relaxing allowed-dirs across the codebase.

## Edges

- Breaks if downstream consumers pin the verifier name `verify-reviewer-output`; the rename surface must include a grep audit of skill prose for the old name.
- Depends on an explicit convention for `cortex/lifecycle/_adhoc/<sha-prefix>/` cleanup ownership — the retention policy lives in a scheduled `cortex clean --adhoc` recipe.
- The taxonomy annotation surface is grep-discoverable; future gate audits read these tags rather than re-classifying from first principles.

## Touch points

- `cortex_command/critical_review.py:82-89` — ancestor-symlink check to replace with under-root scoping.
- `cortex_command/critical_review.py:113-129` — allowed-dirs strict-prefix check; auto-resolve helper attaches here.
- `cortex_command/critical_review.py:227-271` and `:499-554` — `verify-reviewer-output` verifier family; rename and rescope.
- `cortex_command/critical_review.py:195-216` and `:449-496` — `verify-synth-output` verifier family; companion rename.
- `tests/test_critical_review_path_validation.py:43-79, 92-103, 186-198` — test invariants to relax for the under-root scoping change.
- `skills/critical-review/SKILL.md:29, 70` — skill prose updates for the verifier rename and the "use conversation context if no lifecycle" contract.
