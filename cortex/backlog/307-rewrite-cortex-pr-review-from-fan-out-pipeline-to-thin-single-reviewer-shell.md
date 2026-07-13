---
schema_version: "1"
uuid: 0ec6245d-2664-4aa6-8014-5afd6579a2e3
title: Rewrite cortex-pr-review from fan-out pipeline to thin single-reviewer shell
status: complete
priority: high
type: feature
created: 2026-06-16
updated: 2026-06-16
discovery_source: cortex/research/pr-review-skill-audit/report.md
lifecycle_phase: complete
lifecycle_slug: rewrite-cortex-pr-review-from-fan
complexity: complex
criticality: high
spec: cortex/lifecycle/rewrite-cortex-pr-review-from-fan/spec.md
areas: ['skills']
---
## Why

The cortex-pr-review skill underperforms: inconsistent findings, noisy output, and a heavy flow. A full audit plus two head-to-head measurements (6 PRs, 36 runs, across solo and large multi-author PRs) showed the five-stage fan-out is the cause, not the cure. A single high-effort reviewer pass beat the pipeline on consistency everywhere and on quality nearly everywhere, including on the large multi-author PRs that were supposed to be the fan-out's best case. The skill is also an admitted fork of Anthropic's first-party code-review, so most of the machinery re-implements something maintained upstream for free. Worse, the pipeline's own components manufactured the inconsistency: the grounding step non-deterministically dropped correctly-quoted real findings (twice deleting the single best finding on line-number drift), a shared-$TMPDIR collision cross-contaminated runs, and any degradation silently collapses to APPROVE.

## Role

Replace the five-stage pipeline with a thin skill that wraps a single high-effort reviewer agent and adds only the properties bundled /code-review does not give for free: a no-autopost-by-default guarantee, a dropped-findings observability footer, and an on-demand cross-PR / prior-comment lookup for large or multi-author PRs. After it lands, /pr-review reviews a PR in the terminal with one context-investigating pass, never posts unless explicitly asked, shows what it dropped and why, and can pull "did this recur / what did prior reviews on these files say" when a PR warrants it. The skill becomes the policy-and-memory tier over /code-review (the engine); ultrareview stays the separate high-stakes pre-merge pass.

## Integration

The single reviewer agent gathers its own context (the diff, touched and related files, and CLAUDE.md if present) the way the winning baseline runs did, rather than splitting work across parallel critics. In-context grounding replaces the external script by default. The observability footer becomes a thin output layer over the single agent's findings. The prev-PR-comments lookup becomes an on-demand fetch the agent runs when a PR is large or multi-author, not a standing stage. The skill wraps the same /code-review-class capability the measurements used as baseline; model selection moves from the hard claude-opus-4-7 pin to session-default / highest-available, and the footer reports the model that actually ran.

## Edges

- Delete, do not keep: the four-way critic fan-out, the Haiku triage stage, the standing git-history `-p` firehose, the standing compliance critic (demote to "read CLAUDE.md if present" inside the single agent), the bug critic as a separate diff-only pass (fold defect-hunting into the full-context reviewer), the claude-opus-4-7 pin, and the 821-line prose protocol.
- `evidence-ground.sh` is on probation. Default to in-context grounding (the reviewer already holds the full diff). Keep the script only if a calibration run shows a measured precision edge over in-context grounding AND the silent-drop defect (evidence-not-found excluded from the footer) and the slack=10 / line_range-as-hard-filter defects are fixed first.
- Correctness fixes that ship regardless of the grounder decision: invert fail-open to fail-loud (zero findings plus any degradation signal yields REVIEW_INCONCLUSIVE, never a silent APPROVE); fix the verdict-vs-label leak so a must-fix can no longer surface while the PR shows APPROVE.
- Deterministic linter grounding (semgrep / shellcheck as ground truth) is the top borrow-idea from the external landscape and the most likely next lever on finding quality, but it is an explicit fast-follow, out of scope for the first cut to keep the rewrite bounded.
- Fallback if the cross-PR edge does not generalize in practice: collapse to pure-buy (wrap /code-review plus a tuned REVIEW.md, footer as a thin shim). The owned harness is justified only if its three differentiators are actually used; the rewrite should make that an easy retreat, not a one-way door.
- Protected lifecycle path: changes touch `plugins/cortex-pr-review/`; canonical-plus-mirror dual-source discipline applies on commit.

## Touch points

- `plugins/cortex-pr-review/skills/pr-review/SKILL.md` — collapse multi-stage orchestration to a single-reviewer flow; keep the no-autopost constraint
- `plugins/cortex-pr-review/skills/pr-review/references/protocol.md` — delete the five-stage protocol; replace with single-pass plus on-demand context and the fail-loud degraded contract
- `plugins/cortex-pr-review/skills/pr-review/references/rubric.md` — collapse the three-axis rubric to a single severity scale plus a hard grounding requirement; remove per-label caps and the alphabetical tie-break; key the verdict off severity, not an exact label string
- `plugins/cortex-pr-review/skills/pr-review/references/output-format.md` — keep Conventional Comments and the dropped-findings footer; terminal-first text by default, GitHub-markdown only when posting; sort findings blocking-first
- `plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` — probation: in-context grounding by default; delete unless a calibration run justifies keeping a fixed version
- `cortex/research/pr-review-skill-audit/report.md`, `measurement.md`, `measurement-large-prs.md` — the audit and the two measurements this ticket executes