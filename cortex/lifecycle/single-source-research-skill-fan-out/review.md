# Review: single-source-research-skill-fan-out

## Stage 1: Spec Compliance

Cross-cutting setup checks (run once, apply to every phase):
- `just test` → **7/7 passed**.
- `diff skills/research/SKILL.md plugins/cortex-core/skills/research/SKILL.md` → exit 0 (mirror byte-identical).
- `git diff 929e75ff^ -- skills/research/references/fanout.md` → empty (fanout.md unchanged since feature base).
- All 6 impl commits (db5e3190, da3de440, 809a1b56, 14560120, ed773e8c, 79a92cac) touch exactly the two SKILL.md files (2 files changed each); no fanout.md and no frontmatter `description`/`when_to_use` lines appear in the base..final diff.

### Requirement 1: s3 — Step 1 dedup
- **Expected**: Delete the two example-invocation bullets; merge the Step-1 reader-contract paragraph with Step 3's considerations paragraph into one canonical statement (L45 wording verbatim as survivor). Greps: `substitutes its literal content` = 1, `no considerations injection occurs` = 1.
- **Actual**: Example-invocation bullets removed, replaced with "See `argument-hint` for the invocation shape." The L45 reader-contract paragraph is kept verbatim as the survivor. `substitutes its literal content` = 1, `no considerations injection occurs` = 1. `just test` exits 0.
- **Verdict**: PASS
- **Notes**: Edge case (merge must not adopt L63's "injects its content"/"inject nothing" wording) is respected — the survivor is the L45 phrasing.

### Requirement 2: s6 — Considerations-injection dedup
- **Expected**: Keep both per-angle applicability arms with their *why* (not Tradeoffs; not Adversarial); cut the content-not-path/empty-file clauses and the h3-nesting/placement How. Greps: `not Tradeoffs` ≥ 1, `not Adversarial` ≥ 1, `{research_considerations_bullets}` = 3.
- **Actual**: Both arms survive on L65 with their rationale ("keep its orthogonal evaluation unnarrowed" / "it works on summarized findings"); the content-not-path + empty-file clauses and the h3-nesting How are cut and replaced with a "defined in Step 1" pointer. `not Tradeoffs` = 1, `not Adversarial` = 1, `{research_considerations_bullets}` = 3. `just test` exits 0.
- **Verdict**: PASS

### Requirement 3: Reader-contract halt clause preserved (manual)
- **Expected**: `do not halt on a missing` = 1 (the "on a missing" qualifier is unique to the reader-contract clause; the test is non-discriminating).
- **Actual**: `do not halt on a missing` = 1.
- **Verdict**: PASS

### Requirement 4: s4 — Step 2 grid collapse
- **Expected**: Cut the inline floor(3)/corner(10)/monotonic restatement; keep the fanout.md pointer and exactly one upper-bound rider. Greps: `floor cell` = 0, `upper bound on investigation breadth, not a quota` ≥ 1.
- **Actual**: The floor/corner/monotonic sentence is removed, replaced with "Read that grid to size the fan-out." The upper-bound rider is retained (L53). `floor cell` = 0, `upper bound on investigation breadth, not a quota` = 1. Rider wording mirrors the sibling `skills/discovery/references/research.md` L43. `just test` exits 0.
- **Verdict**: PASS

### Requirement 5: s7 — Angle-selection collapse
- **Expected**: Cut the restated core-roster/adversarial-last/no-keyword-router rules; keep count arithmetic, template index, the fanout.md authority pointer, and the `(core)` / `(always last for high/critical)` h4 tags. Greps: `hybrid-angle-selection` ≥ 1, `(core)` = 3.
- **Actual**: The "Mandatory core (always dispatched…)" and "Adversarial (always last…)" restatement bullets and the inlined keep-distinct/no-keyword-router list are removed; the hybrid pointer, count arithmetic, and template index survive. `hybrid-angle-selection` = 1 (the L69 authority pointer), `(core)` = 3, and the `#### Adversarial (always last for high/critical)` template tag is intact (L158). `just test` exits 0.
- **Verdict**: PASS

### Requirement 6: s7 residual — no-keyword-router removal (disclosed residual risk)
- **Expected**: Reviewer confirms the R5(b) pointer grep passes and accepts that no automated pin enforces the rule's runtime application (interactive/session-dependent; acceptable under What/Why-not-How for a low-deviation-cost guideline).
- **Actual**: The R5(b) `hybrid-angle-selection` pointer passes (= 1), so the sole surviving in-repo reference to the fanout.md angle-selection authority is intact. The no-keyword-router rule now lives solely in fanout.md; s4's removal of the inline grid forces the Step-2 fanout.md consult that provides the residency backstop. No automated pin enforces it — accepted as the disclosed residual risk the spec calls out.
- **Verdict**: PASS

### Requirement 7: s13 — Dispatch-protocol trim
- **Expected**: Keep every ADR-0023 mechanism (runnable resolve line, core-wave `model:` bind, read-only/no-worktree, wave ordering, full degrade-loud fallback); cut both the "error-correction layer" clause and the "judgment-inherit contract" rationale and the "no second wave" closer. Greps: `cortex-resolve-model --role searcher` ≥ 1, `fall back to dispatching the core wave` ≥ 1, `judgment-inherit contract` = 0, `error-correction layer` = 0.
- **Actual**: The runnable `model=$(cortex-resolve-model --role searcher)` line, the core-wave `passing the captured $model … as each core-wave Agent's model: parameter` bind, the `No isolation: "worktree"; agents are read-only` note, wave ordering, and the full degrade-loud fallback all survive. Both rationale clauses and the "no second wave" closer are cut. `cortex-resolve-model --role searcher` = 1, `fall back to dispatching the core wave` = 1, `judgment-inherit contract` = 0, `error-correction layer` = 0. `just test` exits 0.
- **Verdict**: PASS

### Requirement 8: s17 — Output-structure strip
- **Expected**: Keep the skeleton and the `## Considerations Addressed` definition; strip the bracketed roster/empty-agent/escalator-parse annotations; retain the `## Open Questions` "omit if no open questions exist" note. Greps: `Omit this section if no open questions exist` = 1, `One bullet per input consideration` = 1.
- **Actual**: The bracketed annotations under `## <Angle name>` and `## Open Questions` are stripped to one-line forms; the `## Considerations Addressed` definition body survives intact. `Omit this section if no open questions exist` = 1, `One bullet per input consideration` = 1. The load-bearing escalator machine-parse contract that the bracket restated is not lost — it survives in Step 4 prose (L195: "machine-parsed by `cortex-complexity-escalator`"). `just test` exits 0.
- **Verdict**: PASS

### Requirement 9: s18 — Step 5 fold into Step 1
- **Expected**: Fold Step 5 into Step 1's mode-detection block; the capital-S `**Standalone mode**` anchor placed AFTER Step 1's considerations-file paragraph; keep the existing lowercase `**standalone mode**` bullet lowercase; no `## Step 5`. Greps: `^\*\*Standalone mode\*\*` = 1, `^## Step 5` = 0.
- **Actual**: Step 5 removed; a "Mode routing (applied after synthesis in Step 4)" block with `**Lifecycle mode**` and `**Standalone mode**` anchors is folded in after the L41 considerations-file paragraph (L47). The lowercase `**standalone mode**` bullet at L34 is preserved. `^\*\*Standalone mode\*\*` = 1, `^## Step 5` = 0. `test_standalone_reads_nothing` passes (the capital-S anchor→next-H2 span contains no `research-considerations-file` / `read (that|the) file`). `just test` exits 0.
- **Verdict**: PASS

### Requirement 10: fanout.md untouched (cross-cutting invariant)
- **Expected**: fanout.md byte-identical to its pre-#350 baseline, verified against the feature-base commit (not working-tree-only).
- **Actual**: `git diff 929e75ff^ -- skills/research/references/fanout.md` is empty, and the base..final commit-span stat for fanout.md is empty. No impl commit touched it.
- **Verdict**: PASS

### Requirement 11: Mirror parity + pointer form + frontmatter untouched (cross-cutting invariant)
- **Expected**: `just test` exits 0; mirror `diff` exits 0; `bin/cortex-measure-l1-surface research` unchanged from true baseline (379, per the review note correcting the spec's stale 502); every retained fanout.md pointer keeps its full `${CLAUDE_SKILL_DIR}/` URL-target form — fixed-string grep = 3.
- **Actual**: `just test` 7/7; mirror `diff` exit 0; `bin/cortex-measure-l1-surface research` = **379** (frontmatter untouched — the base..final diff shows no `description:`/`when_to_use:` change, and the L1 ratchet test is green inside `just test`); `grep -Fc '](${CLAUDE_SKILL_DIR}/references/fanout.md)'` = 3 (URL-side prefixes intact on all three pointers).
- **Verdict**: PASS
- **Notes**: Judged against the true baseline of 379 per the reviewer instruction; the spec's literal "502" is the known-stale figure the plan corrected.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the rest of SKILL.md and the sibling `skills/discovery/references/research.md`. The retained upper-bound rider matches the sibling's wording ("upper bound on investigation breadth, not a quota — dispatch fewer…"), and the fanout.md pointers keep the established `[…](${CLAUDE_SKILL_DIR}/references/fanout.md)` link form used elsewhere in the file. Mode-routing anchors reuse the existing `**Lifecycle mode**` / `**Standalone mode**` bold-anchor convention.
- **Error handling**: The degrade-loud fallback path (resolve-nonzero → dispatch core wave with no `model:`, surface one-line warning, do not halt) is preserved verbatim, so the ADR-0023 resilience contract is intact. The reader contract's "do not halt on a missing file" clause survives.
- **Test coverage**: `just test` 7/7. Where the suite regexes are file-wide/non-discriminating (R3, R6, R7b-fallback, R8c, R11d), the spec's manual greps were run directly rather than assumed; all pass. The position-sensitive `test_standalone_reads_nothing` and the exactly-3 `test_three_placeholders_retained` pins hold ({research_considerations_bullets} = 3).
- **Pattern consistency**: Every load-bearing string is preserved: the escalator-parsed `## Open Questions` heading (= 1) plus its Step-4 machine-parse prose (L195), the ADR-0023 resolve+bind mechanism, the `## Considerations Addressed` definition body (sole repo definition), and all three URL-target fanout.md pointers. No stale bare `research-considerations file`/`research-considerations bullets` token was introduced (edge-case grep clean). The plan's per-phase verification (build-plugin → stage both trees → `just test` → R10/R11 recheck) is evidenced by the 6 paired-file commits.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
