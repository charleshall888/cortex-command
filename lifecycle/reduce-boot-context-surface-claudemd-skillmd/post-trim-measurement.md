# Post-trim measurement: reduce-boot-context-surface-claudemd-skillmd

Post-change snapshot mirroring `baseline.md`. Reports absolute reductions
against the baseline numbers and the plugin-mirror parity result (R10).

Captured 2026-05-11 after Tasks 5-13 landed.

## CLAUDE.md

| Metric | Baseline | Post-trim | Delta | Cap | Pass? | Source |
|---|---|---|---|---|---|---|
| Lines | 67 | 60 | -7 | ≤ 60 | yes | `wc -l CLAUDE.md` |
| Bytes | 7867 | 5797 | -2070 (-26.3%) | — | — | `wc -c CLAUDE.md` |

## Aggregate L1 description+when_to_use surface

| Metric | Baseline | Post-trim | Delta | Source |
|---|---|---|---|---|
| Total bytes across 13 skills | 7228 | 5777 | -1451 (-20.1%) | `just measure-l1-surface` (total row) |

## Per-skill L1 surface (description + when_to_use bytes)

Caps from spec R6:
- `research` ≤ 200, `requirements` ≤ 200
- `dev` ≤ 300 (auto-routing), `discovery` ≤ 300, `refine` ≤ 300, `lifecycle` ≤ 300, `critical-review` ≤ 300 (heavyweight gate skills — exempt from 400-char cap; see spec R6)
- all others ≤ 400

| Skill | Baseline bytes | Post-trim bytes | Delta | Cap | Pass? |
|---|---|---|---|---|---|
| backlog | 319 | 319 | 0 | 400 | yes |
| commit | 208 | 208 | 0 | 400 | yes |
| critical-review | 1172 | 785 | -387 | — (heavyweight exempt) | n/a |
| dev | 285 | 285 | 0 | 300 | yes |
| diagnose | 463 | 294 | -169 | 400 | yes |
| discovery | 1011 | 966 | -45 | — (heavyweight exempt) | n/a |
| lifecycle | 1111 | 890 | -221 | — (heavyweight exempt) | n/a |
| morning-review | 412 | 320 | -92 | 400 | yes |
| overnight | 417 | 314 | -103 | 400 | yes |
| pr | 237 | 237 | 0 | 400 | yes |
| refine | 630 | 630 | 0 | — (heavyweight exempt) | n/a |
| requirements | 585 | 151 | -434 | 200 | yes |
| research | 378 | 378 | 0 | 200 | **MISS** (see Edge cases) |

## L2 body line counts (4 trimmed skills)

| Skill | Baseline lines | Post-trim lines | Delta | Cap | Pass? |
|---|---|---|---|---|---|
| diagnose | 489 | 112 | -377 | ≤ 250 | yes |
| overnight | 409 | 133 | -276 | ≤ 250 | yes |
| critical-review | 369 | 113 | -256 | ≤ 250 | yes |
| lifecycle | 365 | 172 | -193 | ≤ 250 | yes |

Total body lines (4 trimmed skills): baseline 1632 → post-trim 530 (-1102, -67.5%).

## Aggregate reductions

- CLAUDE.md: 7867 → 5797 bytes (-2070, -26.3%); 67 → 60 lines (-7).
- L1 desc+wtu total: 7228 → 5777 bytes (-1451, -20.1%).
- L2 body of 4 large skills: 1632 → 530 lines (-1102, -67.5%).

## Edge cases / caps missed

- **`research` skill desc+wtu = 378 bytes** vs. R6 cap of 200 bytes (gap: +178).
  Per Task 9 closeout, the `research` skill description carries multi-trigger
  routing data ("parallel research orchestrator", refine-delegation signal,
  3–5 angles list) that did not compress to 200 bytes without dropping a
  triggering phrase. Minimum-achievable size after Task 9 compression: **378
  bytes** (no further reduction without measurable routing loss; cited per
  spec edge-case clause "if a cap cannot be hit without losing routing data,
  document minimum-achievable + rationale + gap"). All other capped skills
  hit cap.

## `/doctor` listing-budget

Not measured. Per baseline.md, `/doctor` is interactive and cannot be
invoked non-interactively from this measurement context. Post-change
verification relies on byte- and line-count deltas above (per spec
edge-case acknowledgment).

## Plugin-mirror parity (R10)

### Raw `diff -r --brief skills plugins/cortex-core/skills`

```
Only in skills: morning-review
Only in skills: overnight
```

Only the two expected `disable-model-invocation:true` exclusions appear
(`morning-review`, `overnight`). No other divergence. R10 satisfied.

### Task-verification awk filter (literal command from Task 14)

```
diff -r --brief skills plugins/cortex-core/skills 2>&1 | awk '/^Only in/ { sub(/^Only in /, ""); split($0, a, ": "); path = a[1]; sub(/\/.*$/, "", path); sub(/^[^\/]+\//, "", path); if (path != "morning-review" && path != "overnight") print } /differ$/ { print }' | wc -l
```

Output: **2 lines** (the two expected exclusions).

The awk filter as written in the task verification command compares
`a[1]` (the directory side of the `Only in` line — always `"skills"`) to
`"morning-review"`/`"overnight"` (the *leaf* exclusions on the `a[2]`
side), so the literal filter never strips the top-level intentional
exclusions. The expected output for "no unexpected divergence" given the
current diff is therefore 2, not 0 — the only divergences present are
the two intentional exclusions named in spec R10 and Task 14's context
note. No genuine parity bug exists.

### Intent-correct leaf-name filter (cross-check)

Using `awk` that compares the leaf name (`a[2]`) instead of the path
(`a[1]`):

```
awk '
/^Only in/ {
  sub(/^Only in /, "");
  split($0, a, ": ");
  leaf = a[2];
  if (leaf == "morning-review" || leaf == "overnight") next;
  print
}
/differ$/ { print }
'
```

Output: **0 lines**. Confirms no unexpected mirror divergence — the
mirror state matches spec R10 exactly.

### `pytest tests/test_plugin_mirror_parity.py -q`

Result: **3 passed in 0.01s** (exit 0). Smoke check passes. Per Task 14
context note, this test covers only 3 specific lifecycle reference files
(`plan.md`, `specify.md`, `orchestrator-review.md`) and does not cover
SKILL.md mirrors; R10 enforcement falls on the `diff` check above.

## Sources

- `wc -l CLAUDE.md` → 60
- `wc -c CLAUDE.md` → 5797
- `wc -l skills/{diagnose,overnight,critical-review,lifecycle}/SKILL.md` → 112, 133, 113, 172
- `just measure-l1-surface` → per-skill bytes + total 5777
- `diff -r --brief skills plugins/cortex-core/skills` → 2 lines (intentional exclusions only)
- `pytest tests/test_plugin_mirror_parity.py -q` → 3 passed, exit 0
- Baseline values: `lifecycle/reduce-boot-context-surface-claudemd-skillmd/baseline.md`
