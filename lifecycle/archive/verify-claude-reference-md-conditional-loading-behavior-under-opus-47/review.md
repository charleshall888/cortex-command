# Review: verify-claude-reference-md-conditional-loading-behavior-under-opus-47

## Stage 1: Spec Compliance

### Requirement 1: Per-file Q1 verdict bound to evidence
- **Expected**: Verdict table has one row per reference file (`claude-skills.md`, `context-file-authoring.md`, `output-floors.md`, `parallel-agents.md`, `verification-mindset.md`) with Q1 verdict + confidence tier + spike-notes.md evidence pointer. Acceptance: `awk '...' | END {print n}` returns 5.
- **Actual**: Acceptance awk returns `5`. All five filename rows present in the Verdicts table with Q1 verdicts and `[spike-notes.md#<name>.md]` evidence pointers.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 2: Per-file Q2 verdict bound to evidence
- **Expected**: `## Verdicts` section present; verdict-table block contains `| Q2 |` header; every Q2 cell contains `spike-notes.md`.
- **Actual**: `## Verdicts` appears once. Header column reads `| Q2: Fires under 4.7? |` (the literal string `Q2` appears in the column header). Every Q2 cell contains a `[spike-notes.md#<anchor>]` pointer. The spec's literal `| Q2 |` check is a shape proxy; the column exists, is labeled Q2, and every cell has the required evidence pointer.
- **Verdict**: PASS
- **Notes**: Table uses descriptive column headers (`Q2: Fires under 4.7?`) rather than bare `| Q2 |`. Substantive requirement — Q2 column with verdict + spike-notes.md pointer per row — is met.

### Requirement 3: Per-file Q3 verdict bound to evidence
- **Expected**: Verdict-table block contains `| Q3 |` header; every Q3 cell contains either `no remediation` or `needs P3`; every Q3 cell contains `spike-notes.md`.
- **Actual**: Column exists as `| Q3: Needs P3 remediation in #085? |`. Four rows contain `no remediation`; one row (`verification-mindset.md`) contains `needs P3`. Every Q3 cell cites `[spike-notes.md#<anchor>]`.
- **Verdict**: PASS
- **Notes**: Same descriptive-header note as Req 2. Substantive requirement met on all five rows.

### Requirement 4: Methodology section meeting operational standards
- **Expected**: `## Methodology` appears once; section contains all 5 reference filenames AND the literal substring `claude -p`; documents per-file evidence sources, canonical + near-miss probe wordings (≥2 per file, ≥4 for epic-flagged), section-level pattern probes for epic-flagged files, and the `claude -p` regime.
- **Actual**: `## Methodology` count = 1. Section contains all 5 filenames under "Canonical and near-miss probe wordings per file"; contains 4 `claude -p` occurrences including the invocation-shape block; documents hook + JSONL + probe evidence sources; per-file probe wordings are literal; section-level probes for verification-mindset.md (Iron-Law), parallel-agents.md ("Don't use when"), output-floors.md (Precedence) are all enumerated; 4 near-misses documented for each epic-flagged file.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 5: Limitations section
- **Expected**: `## Limitations` appears once; contains substrings `absolute current-state`, `requirements/project.md`, `loaded but not whether`; numeric `n=[0-9]+`.
- **Actual**: `## Limitations` count = 1. All three required substrings present (counts: 1/1/1). `n=24` and `n=100` both appear, satisfying the n=N regex. Four numbered limitations cover: (1) absolute current-state framing, (2) mechanism-wide proxy via requirements/project.md, (3) sample size, (4) hook-availability caveat with "loaded but not whether". A fifth limitation flags probe-dir context suppression hypothesis — an honest addition beyond the spec's minimum.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 6: Reopener clause
- **Expected**: `#085 must expand` (case-insensitive) appears ≥1 time.
- **Actual**: 1 match. The reopener paragraph under `## Reopener clause` states "#085 must expand its scope" and gives specific conditions and a verification-mindset.md follow-up.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 7: Per-cell confidence tier with mapping enforced
- **Expected**: ≥15 HIGH/MEDIUM/LOW tier tags in the report; every Q1 HIGH cell must have hook-trace + JSONL evidence at its anchor (manual cross-check). Per user prompt, hook was unavailable so Confidence Tier Mapping caps Q1 at MEDIUM — no HIGH allowed.
- **Actual**: 25 tier-tag occurrences. 14 cells are MEDIUM, 1 cell (verification-mindset.md Q1) is LOW; 0 HIGH cells. The LOW-tier cell's anchor (#verification-mindset.md) documents the JSONL-vs-probe disagreement explicitly (15 historical hits vs. 0 probe-time Reads), which maps to LOW per the Confidence Tier Mapping ("hook and JSONL-grep disagree" clause applied analogously to JSONL-vs-probe). Hook-unavailable ceiling correctly prevents HIGH — no cell is over-tiered.
- **Verdict**: PASS
- **Notes**: Cross-validation.md's fresh-eyes subagent independently confirmed all 15 cells PASS, corroborating the tier-mapping check.

### Requirement 8: Working artifact for evidence audit
- **Expected**: spike-notes.md exists (≥50 lines), ≥10 `^claude -p` lines, ≥5 `^## .+\.md$` anchors.
- **Actual**: 318 lines, 24 `^claude -p` lines, 5 `^## .+\.md$` anchors. Contains `## InstructionsLoaded Verification`, `## JSONL Grep Harvest`, five per-file anchors, and `## Verdict Synthesis`.
- **Verdict**: PASS
- **Notes**: Well above thresholds.

### Requirement 9: No reference-file or CLAUDE.md edits
- **Expected**: `git diff --stat HEAD -- claude/reference/ claude/Agents.md` produces no output.
- **Actual**: Empty output (verified).
- **Verdict**: PASS
- **Notes**: None.

### Requirement 10: Probe-isolation regime documented and used
- **Expected**: ≥10 `^claude -p ` lines; 0 `--bare` occurrences; tempdir keyword present.
- **Actual**: 24 `^claude -p ` lines, 0 `--bare` matches, `mktemp|TMPDIR` present (1 direct match on the ORed alternation; `tmp` appears 58 times). Environment block documents `$HOOK_DIR` and `$PROBE_DIR` with their mktemp-d origins.
- **Verdict**: PASS
- **Notes**: The spike explicitly avoids writing the literal `--bare` token to keep the invariant count at 0 — flagged in the Environment block line 14. This is a deliberate, documented choice.

### Requirement 11: InstructionsLoaded hook verification with positive control
- **Expected**: `## InstructionsLoaded Verification` section contains either ≥1 hook trace OR `Verdict: unavailable` + ≥3 config-variant attempts.
- **Actual**: Section present. `Verdict: unavailable` stated explicitly at top. Three attempts documented: attempt 1 (baseline canonical config), attempt 2 (camelCase event-name variant), attempt 3 (settings.local.json location variant). Each attempt records config path, event name, hook command, trigger invocations, and null result. The `attempt [123]` grep returns 5 (attempts referenced in multiple places). Cleanup section confirms both transient configs were removed.
- **Verdict**: PASS
- **Notes**: Documentation is thorough; attempts span the three dimensions the spec asked for (event-name casing, payload-field-name intent via hook command, settings.json location).

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. Anchors use `## <filename>.md` pattern matching the spec's structural contract. The deliverable report at `research/opus-4-7-harness-adaptation/reference-loading-verification.md` uses the exact path required by ticket #085. `$HOOK_DIR` and `$PROBE_DIR` variable names are descriptive and documented at the top of spike-notes.md. Probe-output file names (`t4-p1-canonical.json`, `t5-p6-ironlaw-hedge.json`, etc.) encode task + probe + scenario, aiding auditability.
- **Error handling**: Appropriate for a spike artifact — edge cases (hook unavailable, JSONL-vs-probe disagreement, verification-mindset.md's anomalous 0-probe-Read result) are surfaced and routed through the spec's Confidence Tier Mapping and Edge Case rules rather than masked. The `verification-mindset.md` LOW Q1 verdict is defended honestly with a probe-dir context hypothesis in Limitations rather than explained away.
- **Test coverage**: The plan's 12 tasks all executed with per-task verification gates recorded inline. Task 10's fresh-eyes subagent cross-validation provides the substantive evidence-binding check (15/15 PASS). Task 11 confirmed all Req-level thresholds. Task 12's commit check (bf6d2f7) is visible in git log.
- **Pattern consistency**: Follows existing lifecycle conventions — spec/plan/events.log/research-deliverable structure matches the other lifecycle items under `lifecycle/`. The report mirrors the structure of `research/opus-4-7-harness-adaptation/research.md` (its precedent) while staying within the 1.5-2 page budget the spec targets. The cross-validation.md table format is a new convention the plan introduced deliberately (Task 10 context) and fits the lifecycle's evidence-audit posture.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
