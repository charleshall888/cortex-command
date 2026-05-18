# Gate Brief Word Cap Derivation

## Method

Corpus: union of `cortex/research/*/research.md` and `cortex/lifecycle/*/research.md` files that contain a `## Headline Finding` section. Files without that section are skipped per task spec.

Compression baseline: 2.5× (from the prior reader study). Compressed word count = original / 2.5.

Cap derivation: 90th percentile of compressed lengths, rounded to the nearest 25 words.

## Corpus Measurement

| path | original word count | compressed word count | method note |
|---|---|---|---|
| cortex/research/cursor-skill-port/research.md | 171 | 68 | stripped forward refs (Cursor version refs, spec-section anchors), refolded to shortest faithful prose |
| cortex/research/grill-me-with-docs-learnings/research.md | 367 | 147 | stripped forward refs (layer enumeration, per-item spec anchors), refolded numbered list to dense prose |
| cortex/research/interactive-overnight-mode/research.md | 402 | 161 | stripped forward refs (DR-N, Q-N, piece citations), refolded architecture options to decision + rationale |
| cortex/research/windows-support/research.md | 317 | 127 | stripped forward refs (W6, DR-N labels, workstream enumeration), refolded five-workstream list to feasibility summary |

## Calculation

Compressed counts (sorted): 68, 127, 147, 161

90th percentile (linear interpolation, n=4): index = 0.9 × 3 = 2.7 → 147 + 0.7 × (161 − 147) = 156.6

Rounded to nearest 25: 150 (156.6 is 6.6 from 150 vs 18.4 from 175)

word cap: 150
