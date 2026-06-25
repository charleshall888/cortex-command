---
schema_version: "1"
uuid: 30a44a35-ca12-4889-845a-b3ffee453d78
title: 'Criticality/dispatch reference cleanup: relocate fanout.md, resolve model-selection.md, reconcile model thresholds'
status: backlog
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-25
---
## Why

A cluster of misfiled / duplicated / stale criticality-and-dispatch references, surfaced in the 2026-06-25 lifecycle reference-file audit:

1. **`fanout.md` is research-owned** (cited by `research/SKILL.md` ×5 + discovery) but lives in `lifecycle/references/`, reached only transitively via `criticality-matrix.md:26` — the same coupling inversion #328 fixed for clarify/specify.
2. **`assets/model-selection.md` has zero live citations** yet declares itself "the canonical source" for the inline model values; its Pipeline Matrix duplicates `docs/internals/sdk.md` and its model profiles (Sonnet 4.6, SWE-bench %) are staleness-prone.
3. **`review.md` and `orchestrator-review.md` encode different model thresholds** (review: sonnet low/med, opus high/crit; orchestrator: sonnet low/med/high, opus crit) as two silent variants.
4. **`criticality-matrix.md:24`** re-reads its own table back in prose and cites implementation-history ticket numbers (023/024/025).

## Role

- Relocate `fanout.md` → `research/references/`; lifecycle's two pointers chase it there. Do **not** fold it into `criticality-matrix.md` (that couples research/discovery to a lifecycle file).
- Decide `model-selection.md`'s fate: either keep it as the single consistency anchor with the inline values referencing it, OR offload model selection to a `cortex-*` resolver verb and delete the asset — but **do not blind-delete**: a prior trim audit deliberately kept it as the de-dup anchor, so name that affordance and confirm the inline values are self-consistent before removing.
- Reconcile the two model-threshold tables into one source, noting the difference is deliberate (reviewer escalates at high; fix-agent at critical).
- Delete the `criticality-matrix.md:24` narration paragraph.

## Integration

File move across skills + edits to `research/SKILL.md`, discovery refs, `criticality-matrix.md`, `review.md`, `orchestrator-review.md`, `assets/model-selection.md` (+ mirrors) → lifecycle-gated. `${CLAUDE_SKILL_DIR}` body-resolution per ADR-0009 for any moved-file references. Sibling of #328.

## Edges

- `fanout.md` has its own second-level references (`model-selection.md` cites it too) — repoint all.
- If `model-selection.md` is deleted, every inline model value must be confirmed self-consistent first (the anchor's whole job).
- Keep the criticality behavior matrix itself — the decisions are load-bearing; only the line-24 narration and the duplicate model trivia are fat.

## Touch-points

- move `skills/lifecycle/references/fanout.md` → `skills/research/references/`
- `skills/lifecycle/references/criticality-matrix.md`, `review.md`, `orchestrator-review.md`, `assets/model-selection.md`
- `skills/research/SKILL.md`, discovery references (+ mirrors)
- tests