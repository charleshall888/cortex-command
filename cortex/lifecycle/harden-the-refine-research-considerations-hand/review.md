# Review: harden-the-refine-research-considerations-hand

Scope: the 6 implementation commits `064dc653..35e32dcb` (b538057c → 35e32dcb plus
the gitignore commit 14f51057). Read-only review; spec is the contract (R1–R14).
All named greps and pytest invocations were run.

## Stage 1: Spec Compliance

### Requirement 1: Refine writes the considerations file and emits the path arg as one coupled step
- **Expected**: Propagation block, fired only on ≥1 Apply'd finding, writes `research-considerations.md` overwriting (never appending) AND the same dispatch carries `research-considerations-file=<path>`, coupled; old value-arg gone; a prose-contract test asserts the write+overwrite wording.
- **Actual**: `skills/refine/SKILL.md` lines 102–117 — the block performs "one coupled step: **write** the surviving findings to `cortex/lifecycle/{lifecycle-slug}/research-considerations.md`, **overwriting** the file (never appending), **and** carry `research-considerations-file=...`" and states "the argument is never emitted without a same-run fresh write." `grep -c "research-considerations-file"` = 2; `grep -c 'research-considerations="'` = 0. `test_file_write_and_coupling_present` (WRITE_LINE_RE + overwrite + coupled-arg) and `test_old_value_arg_absent` pass.
- **Verdict**: PASS
- **Notes**: Write/arg coupling is explicit and inseparable ("never emitted without a same-run fresh write").

### Requirement 2: Refine's escaping caveat is removed
- **Expected**: "Strip or paraphrase away …" gone; heading still present (non-vacuity).
- **Actual**: `grep -c "Strip or paraphrase away"` = 0; `grep -c "### Alignment-Considerations Propagation"` = 1. `test_refine_escaping_caveat_removed` + `test_propagation_heading_present` pass. Old base (064dc653) carried the caveat at line 127 — confirmed red-before-green.
- **Verdict**: PASS

### Requirement 3: The file write is sequenced before the dispatch
- **Expected**: A prose-contract test asserts the `research-considerations.md` write anchor appears at a smaller line index than the fenced `/cortex-core:research topic=` dispatch line (not a "Delegate to" mention).
- **Actual**: Write instruction at line 108; fenced dispatch `/cortex-core:research topic="{clarified intent}"` at line 124. `test_write_precedes_dispatch` uses `WRITE_LINE_RE` (write-verb + `research-considerations.md`) vs. the pinned `DISPATCH_ANCHOR = "/cortex-core:research topic="`, both literals — deterministic, passes. Old file had no write line at all → red.
- **Verdict**: PASS

### Requirement 4: Research reads the file in its body and injects the content
- **Expected**: `research-considerations-file` replaces `research-considerations`; body reads the file and injects literal content into the three `{research_considerations_bullets}` placeholders; injection points/output section unchanged; test asserts read-and-substitute (not mere rename); placeholder count = 3.
- **Actual**: `skills/research/SKILL.md` line 45 — "research's orchestrator body **reads that file and substitutes its literal content** into the core-angle prompt considerations placeholders." `grep -c "research-considerations-file"` = 4; `grep -c "research_considerations_bullets"` = 3. `test_research_reads_and_substitutes_content` (specific regex `read\w*…file…substitut\w+…its literal content`) passes; old file had no such prose → red.
- **Verdict**: PASS

### Requirement 5: Research's escaping caveat is removed
- **Expected**: "Embedded `=` and `"` … are not supported in the value" gone; "Parse Arguments" heading present.
- **Actual**: `grep -c "are not supported in the value"` = 0; `## Step 1: Parse Arguments` present. `test_research_escaping_caveat_removed` + `test_step1_heading_present` pass. Old base carried the caveat at line 45 → red.
- **Verdict**: PASS

### Requirement 6: Inject content, never the bare path — guarded at the injection-prose level
- **Expected**: Positive — read-and-substitute names content/literal text; negative control — injection prose/agent-prompt fences carry only the placeholder, never the path/`.md`/read-the-file directive; negative control red against a draft that forwards the path.
- **Actual**: `test_inject_content_not_path` asserts `literal content` present (positive, line 45/63) AND iterates the 3 placeholder-bearing fenced blocks asserting none contains `research-considerations-file`, `research-considerations.md`, or a "read that/the file" directive. The negative loop is non-vacuous (3 fences execute the body) and structural — a draft injecting the path into a fence would fail it. Passes.
- **Verdict**: PASS
- **Notes**: Aligns with SP001/SP002 + ADR-0009 (inject content, not the path). The lint cannot catch the `cortex/lifecycle/...` shape, so the prose-level guard is the correct enforcement locus, exactly as the spec's Technical Constraints prescribe.

### Requirement 7: Absence = no injection, structurally — via coupling, no clear-discipline
- **Expected**: Test asserts refine's block retains conditional-fire + coupling and contains no "clear/truncate … each run" discipline (preservation + negative-control).
- **Actual**: Block retains "whose disposition is **Apply**" and "When — and **only when** — at least one Apply'd alignment finding exists". `test_conditional_fire_retained` (Apply'd + "only when") and `test_no_clear_each_run_discipline` (no `(clear|truncate).*each run` either order) pass. No clear/truncate discipline present anywhere.
- **Verdict**: PASS

### Requirement 8: Standalone research reads nothing
- **Expected**: Standalone path reads no considerations file (negative control, vacuously green today).
- **Actual**: `test_standalone_reads_nothing` slices from `**Standalone mode**` (Step 5, line 241) to next `## ` and asserts no `research-considerations-file` and no "read that/the considerations file". Passes. Standalone has no `lifecycle-slug` → no `-file` arg → no read.
- **Verdict**: PASS

### Requirement 9: Gitignore the transient considerations file
- **Expected**: `lifecycle/**/research-considerations.md` in BOTH `cortex/.gitignore` and `cortex_command/init/templates/cortex/.gitignore`; `git check-ignore` of an untracked probe exits 0.
- **Actual**: Both files carry the rule once (grep = 1 each), in the "Transient refine->research considerations hand-off input" stanza. `git check-ignore cortex/lifecycle/_probe/research-considerations.md` exits 0. `**` covers active and archive depth.
- **Verdict**: PASS

### Requirement 10: Mirror regenerated and byte-identical
- **Expected**: `plugins/cortex-core/skills/{refine,research}/SKILL.md` regenerated; parity test exits 0.
- **Actual**: `diff -q` reports both canonical/mirror pairs IDENTICAL; `tests/test_dual_source_reference_parity.py` 58 passed.
- **Verdict**: PASS

### Requirement 11: Behavioral prose-contract tests added (Phase 1)
- **Expected**: New `tests/test_*` modeled on `test_refine_skill.py`; honest red/green classification; `just test` exits 0 with new tests collected; red-before-green tests fail against unmodified files.
- **Actual**: `tests/test_refine_handoff.py` + `tests/test_research_handoff.py` (17 tests) collected and pass. Red-before-green verified against base 064dc653: old refine carried `Strip or paraphrase away` + `research-considerations="…"` with no write line; old research carried `are not supported in the value` with no read-and-substitute/`literal content` prose — every red-before-green assertion would fail against those. Preservation tests (R7/R8) green both sides. Full `just test`: 7/7 groups passed (the two noted load-dependent externals passed this run).
- **Verdict**: PASS

### Requirement 12: Hand-off field registered in the schema fixture
- **Expected**: `{name: research-considerations-file, producer: refine, consumers: [research]}` in the schema fixture; `tests/test_skill_handoff.py` exits 0.
- **Actual**: `tests/fixtures/skill_handoff_schema.yaml` carries the entry (lines 5–7). `tests/test_skill_handoff.py` 2 passed (its `pytest.raises` fixture is the built-in negative control).
- **Verdict**: PASS

### Requirement 13: Gitignore-template test case added
- **Expected**: `_IGNORED` case for `research-considerations.md` at active and archive depth; template test exits 0.
- **Actual**: `cortex_command/init/tests/test_cortex_gitignore_template.py` adds both `cortex/lifecycle/feat/research-considerations.md` and `cortex/lifecycle/archive/x/research-considerations.md` (lines 40–42). Test: 35 passed.
- **Verdict**: PASS

### Requirement 14: ADR-0022 recorded
- **Expected**: `cortex/adr/0022-*.md` recording the decision + rejected alternatives (implicit slug-derived file; full argument removal) + coupling/absence rationale; both skills back-point to it without restating; ADR gates pass.
- **Actual**: `cortex/adr/0022-explicit-path-arg-for-refine-research-considerations-handoff.md` exists with Context / Decision / Rejected alternatives (both named) / Consequences-Trade-off, including the "re-litigated three times" and borderline-ADR framing. Both skills cite `ADR-0022` (grep = 1 each) and defer rather than restate (refine line 104, research line 45). `tests/test_lifecycle_references_resolve.py` 4 passed; ADR-citation audit (`-k adr`) 14 passed. 0022 was the free number (no collision).
- **Verdict**: PASS

### Non-Requirements sanity check
- Value format (newline-delimited bullets) unchanged — refine lines 110–115, research line 45. OK.
- Injection points unchanged — 3 placeholders, core angles only. OK.
- `## Considerations Addressed` output trigger unchanged ("the considerations file was non-empty AND lifecycle mode") — research lines 230, 238. OK.
- No new CLI verb — diff touches only docs/tests/gitignore; the sole `.py` change is the template test, no `bin/` or new module. OK.
- File not committed nor registered in `index.md` — refine registers only the `research`/`spec` artifacts (lines 135, 165); the considerations file is gitignored. OK.
- No clear/truncate-each-run discipline introduced. OK.
- Clarify-critic finding production untouched (transport-only). OK.

## Stage 2: Code Quality
- **Naming conventions**: New tests follow `test_refine_skill.py` — module-level `REPO_ROOT`/`SKILL_MD`, `_read()`, anchored-slice helpers (`_propagation_block`, `_slice`), an identical `_line_of` 1-indexed helper, descriptive `test_*` names with docstrings citing the requirement. Consistent.
- **Error handling**: Slice helpers `pytest.fail` on a missing anchor rather than silently returning empty (avoids vacuous-pass on a moved heading). The gitignore-template test sources bytes from the package resource handle (`files(...)`), not a hardcoded copy — same source the scaffolder uses. Honest.
- **Test coverage**: Discriminating, not vacuous. R3 uses two pinned literal anchors and compares line indices. R4 uses a specific multi-token regex (read…file…substitute…literal content), not a bare key grep. R6's negative control structurally iterates the placeholder-bearing fences and would go red on a path-forwarding draft. `test_no_stale_bare_value_key` (both sides) uses lookaheads to exclude `-file`/`.md`, catching any dangling bare value-key. Red-before-green independently confirmed against base 064dc653.
- **Pattern consistency**: Mirror regenerated via the canonical-edit rule (parity green). No new MUST/CRITICAL/REQUIRED added (diff grep clean) — compliant with the MUST-escalation policy. L1 surface ratchet (20 passed) and skill-path lint (15 passed) green; body-only change leaves frontmatter budgets untouched. Line counts (refine 204, research 244) well under the 500 cap. Verification claims in the artifacts are honest.

## Requirements Drift
**State**: none
**Findings**:
- None. `cortex/requirements/project.md` has no reference to the considerations hand-off, escaping, or value-arg channel — the change is a localized transport migration that does not touch any documented requirement, convention, or constraint. The relevant project constraints it could brush (L1 ratchet, MUST-escalation, mirror canonical-edit, ADR-0009 path-resolution) are all satisfied.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
