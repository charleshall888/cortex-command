# Review: sweep-provisional-tail-discovery-backlog-author (Cycle 2)

Cycle 1 returned CHANGES_REQUESTED with Req 3 (extractive-only) PARTIAL, pinned to three spans:
backlog-author `s10` (step-merge with authored connective prose), clarify `s5` (table→inline-list
restructure), and clarify `s7` output-3 (bullets→paraphrase). Rework commit `9b05f8e6` claims s10 is
now a pure deletion, s5 is REFUTED (table byte-restored), and s7 output-3 is byte-restored (output-1
deletion stays applied). This cycle re-verifies those three spans adversarially against the pre-sweep
original and re-confirms no regressions. The other 11 requirements were PASS in cycle 1 and are
unaffected by the rework (which touches only `skills/backlog-author/SKILL.md`,
`skills/discovery/references/clarify.md`, `outcomes.md`, and the regenerated mirrors); Req 9 is
re-verified because the tally changed to 31/12.

## Stage 1: Spec Compliance

### Requirement 3: Extractive-only trims + per-trim keep-list (THE CENTRAL CHECK — re-reviewed)
- **Expected**: Every applied trim is a pure span deletion — surviving prose a literal byte-subset of
  the original (a bare leftover numbering gap or a single `:`→`.` boundary char is acceptable; any new
  or reworded word is a fail). The three cycle-1-flagged spans must be corrected: s10 to a pure
  deletion, s5 either deleted outright or restored, s7 output-3 restored.
- **Actual**: All three findings are resolved, verified against `git show 0fec0123^:<path>`:
  - **backlog-author `s10`** — Now a pure span deletion. `git diff 0fec0123^ HEAD -- skills/backlog-author/SKILL.md`
    shows step 1 (`Read ${CLAUDE_SKILL_DIR}/references/body-template.md…`) and step 4 (`Compose the
    five-section body. Emit it to stdout as a markdown block for the caller to pass to
    cortex-create-backlog-item --body`) as UNCHANGED context lines — byte-identical to the original —
    with only steps 2–3 (`Parse the provided {{context-block}}…` / `Apply the Why-vs-Role disambiguation
    rule…`) removed. The cycle-1 authored clause "from the provided `{{context-block}}` (applying the
    Why-vs-Role disambiguation rule)" is gone. The bare leftover `1.`→`4.` numbering gap is the only
    residue and is acceptable (no words added).
  - **clarify `s5`** — REFUTED and byte-restored. The `### 4. Confidence Assessment` 4-row table does
    not appear anywhere in `git diff 0fec0123^ HEAD -- skills/discovery/references/clarify.md`, which is
    definitive proof it is byte-identical to the pre-sweep original. The authored "and" and the
    table→inline-list collapse are gone.
  - **clarify `s7` output-3** — Bullets byte-restored. The `3. **Requirements alignment note**` block
    (the four "Aligned…/Partial…/No requirements files found…/Conflict detected…" bullets) does not
    appear in the diff — byte-identical to the original. The candidate stays APPLIED on the strength of
    its output-1 deletion only: `1. **Clarified topic statement**…` drops the trailing `Example: "Explore
    options for replacing the pipeline orchestrator…"` sentence and nothing else — a clean pure deletion.
  - **Full-file diff scan (adversarial)**: `git diff 0fec0123^ HEAD` for both files was inspected in
    full for any added or reworded word across ALL still-applied trims. None found. clarify `s3`
    (deleted glossary-absence sentence), `s9` (deleted scope-envelope in/out bullets + trailing
    "Fire when boundaries are tractable…" sentence, with a single `:`→`.` boundary char on the surviving
    line — acceptable), and `s11` (deleted `## Constraints` Thought/Reality table) are all pure
    deletions. backlog-author `s1` (frontmatter fields), `s3` (`## Invocation` + `## Body Template`
    sections), and `s7` (interview enumeration + compose restatements) are all pure deletions. No smuggled
    paraphrase in any surviving trim.
  - Part (a) suites green: `tests/test_backlog_author.py`, `tests/test_load_requirements_protocol.py`,
    `tests/test_discovery_module.py`, `tests/test_l1_surface_ratchet.py` = 45 passed. Keep-list tokens
    present; refuted spans still in-file.
- **Verdict**: PASS
- **Notes**: The net diff is now a literal auditable subset of the original for both edited files —
  the property the spec sold. The extractive-fidelity inconsistency cycle 1 flagged (Task 3/Task 6
  applying the same restructure class Task 8 refused) is resolved: s5 was reclassified REFUTED alongside
  the other non-extractive candidates, and s10/s7 were reduced to clean deletions.

### Requirements 1, 2, 4, 5, 6, 7, 8, 10, 11, 12 — PASS (carried from cycle 1)
These were PASS in cycle 1 and the rework does not touch their subject matter (preflight worksheet,
ledger read-only, interacting clusters, section-boundary invariants, s1 frontmatter gate, zero-pin
adversarial re-check, mirror regeneration, parity tuple, commit-time lints, full-suite gate). Re-confirmed
this cycle: ledger `git status --porcelain cortex/research/skill-value-scorecard/` is empty (Req 2);
`just build-plugin && git diff --quiet -- plugins/cortex-core/` exits 0 — mirrors byte-clean including
the reworked s10/s5/s7 spans (Req 8). No regression.

### Requirement 9: Every candidate's outcome recorded (re-verified — tally changed)
- **Expected**: `outcomes.md` with exactly one REFUTED/APPLIED line per in-scope candidate, 43 total;
  after the rework the tally is 31 APPLIED / 12 REFUTED with s5 (clarify.md) flipped to REFUTED and
  s10/s7 (clarify.md) still APPLIED with corrected action text.
- **Actual**: `grep -c '^- \(REFUTED\|APPLIED\) '` == 43; APPLIED == 31, REFUTED == 12. The clarify.md
  `s5` line now reads REFUTED ("§4 table→inline-list collapse is a non-extractive restructure… the 4-row
  table is restored"). The clarify.md `s7` line stays APPLIED with corrected text ("dropped output-1
  worked example as pure deletion; output-3 template paraphrase reverted… per extractive-only review").
  The backlog-author `s10` line stays APPLIED with corrected text ("deleted parse/rule-restatement compose
  steps as pure span deletion (kept step 1 read + step 4 output-contract verbatim)"). Both corrected
  APPLIED lines cite the rework commit subject. Markers match the fixed format.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Extractive-fidelity**: Now consistent across the corpus. The three cycle-1 fidelity violations are
  eliminated — s5 joined the REFUTED non-extractive set (same standard Task 8 applied to body-template
  s2/s3), and s10/s7 are reduced to pure deletions with the surviving prose byte-verbatim. The net diff
  for both edited files is a literal subset of the original.
- **Behavior preservation**: Unchanged from cycle 1 — no routing/gate/interview/recovery path dropped.
  The s5 refutation restores the full confidence-assessment table (more conservative than cycle 1); s7
  output-3 restoration reinstates the verbatim alignment-note template. Neither reduces behavior; both
  increase fidelity.
- **Test coverage**: Sweep-relevant suites green (45 passed on the four re-run files). Mirror byte-clean.
- **Pattern consistency**: Commits self-documenting; the rework commit names the three candidate ids and
  the exact correction per candidate. No `--no-verify`.

## Requirements Drift
**State**: none
**Findings**:
- None. The rework tightens three prose trims to the extractive-only discipline the spec already
  mandates; it introduces no new behavior, contract, or requirement change. The extractive-only property
  is a constraint of this feature's own spec, not a project-requirements shift.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
