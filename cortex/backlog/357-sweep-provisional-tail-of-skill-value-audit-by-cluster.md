---
schema_version: "1"
uuid: 1d39f37f-9d9a-4245-898c-ac881f413363
title: Sweep the provisional tail of the skill-value audit by cluster
status: backlog
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: [skills]
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
---
## Decomposition
This ticket is the parent umbrella for the provisional tail; the 143 eligible candidates are split into four file-disjoint child batches, refinable and executable in parallel sessions (the lifecycle state machine is per-ticket, so parallelism needs separate tickets). The children partition the candidate set with no overlap:

- **#358** — cortex/requirements/ area files: 32 candidates, editorial mode.
- **#359** — discovery + backlog-author clusters: 43 candidates, pin-verify (holds the sole L1-ratchet frontmatter candidate).
- **#360** — critical-review cluster: 26 candidates, pin-verify (carries the SKILL.md cross-site parity residual).
- **#361** — refine cluster + transitive tail: 42 candidates, pin-verify.

Verification bar across all four: pin-hit verification, single-pass (read each candidate's pins/mech_pins, confirm the trimmed span is not load-bearing, apply honoring the keep-list, record refuted). master_candidates.json status write-back is deferred out of the children to avoid concurrent writes; closing this umbrella includes the single reconciliation pass that folds every child's verify outcomes back into master_candidates.json. **Reconciliation input contract**: each child lifecycle records its per-candidate outcomes in a dedicated `cortex/lifecycle/<child>/verdicts.md` (per candidate: `id`, `file`, `disposition` ∈ {`verified_survives`,`verified_refuted`,`correction`}, one-line evidence, and — for applied candidates — the trim-commit SHA). The umbrella-close reconciliation **reads those child `verdicts.md` files as its authoritative input** and folds them into `master_candidates.json` — direction: **child `verdicts.md` → `master_candidates.json`** — writing each row's `status` and filling the `applied_in_commit` provenance that #353 left unfilled. (First such record: `cortex/lifecycle/sweep-provisional-tail-critical-review-cluster/verdicts.md`, 26 candidates.)

## Why
Follow-up to #353, which completed Batch 1 — the verified lifecycle-cluster remainder (50 adversarially-verified candidates applied across 22 files, ~10k net bytes / ~8.6k weighted tokens). This ticket carries the **provisional tail** that #353 scoped but deliberately did not execute: 143 candidates (~23k weighted tokens) that are scored and mechanically pin-scanned but **never adversarially verified**. Unlike the verified batch, each provisional candidate must be verified against its listed pin hits before trimming — recording refuted ones so they are not re-proposed. The largest concentrations: the `cortex/requirements/` area files (backlog.md ~11, pipeline.md, observability.md, multi-agent, remote-access), the backlog-author SKILL (~9) + its body-template reference, and the refine (~8) / discovery (~7) / critical-review (~8) cluster SKILL.md bodies + references (e.g. discovery/references/research.md ~7).

## Role
Work through the provisional remainder in batches by cluster or file family — one lifecycle per batch, as #353 established. For each candidate: verify against its listed pin hits (`pins`/`mech_pins`) first, apply honoring the keep-list, and record refuted candidates so they are not re-proposed. The `cortex/requirements/` area files load via the load-requirements selection path — trims there are editorial (like #351), not mechanical.

Also carries two **cross-site parity residuals** from #353 Batch 1: the `cortex-resolve-model` failure-cause enumeration ("the verb rejected the input or the `cortex-lifecycle-state` read returned corrupt/absent criticality") was trimmed from review.md, orchestrator-review.md, and competing-plans.md for cross-site parity, but the intentionally-parallel copies in `skills/lifecycle/references/implement.md` (owned by #348) and `skills/critical-review/SKILL.md` still carry it. Complete the parity when those files are next touched.

## Integration
`master_candidates.json` carries per-candidate `status: unverified`, `pins`/`mech_pins` (grep starting points), keep-lists, and `weighted_cost`. `dup_groups.json` lists cross-file duplication groups that can be single-sourced opportunistically when their files are already open in a batch. One lifecycle per batch is the intended granularity — not one per candidate, not one for everything.

## Edges
- Provisional candidates flagged as overlapping open tickets or reproposals are already excluded from the 143.
- Prompt-template files in critical-review multiply by reviewer count; verify against the synthesizer's parsing expectations before trimming.
- The transitive-file slice spans files no verified-batch ticket owned; several `cortex/requirements/` files load selectively, not always.

## Touch points
- cortex/requirements/ area files, skills/backlog-author/, skills/refine/, skills/discovery/, skills/critical-review/ (SKILL.md + references)
- plugins/cortex-core mirrors (same commits)
- cortex/research/skill-value-scorecard/master_candidates.json and dup_groups.json (reconciliation target)
- cortex/lifecycle/<child>/verdicts.md — per-child reconciliation input, folded into master_candidates.json at umbrella close (child verdicts.md → master_candidates.json)
