# Plan: Classify /critical-review findings by class and add B-class action surface

## Overview
The load-bearing work is two prompt rewrites in `skills/critical-review/SKILL.md` (Step 2c reviewer + Step 2d synthesizer). Residue writes go through an inline `python3 -c` invocation in the new Step 2e that calls `claude.common.atomic_write` directly — no deploy-bin helper. A baseline-stability measurement runs before the classifier-validation test to set its retry policy empirically. Fixtures are authored by separately-dispatched subagents (R8), the overnight report gains a new `render_critical_review_residue` section registered after `render_deferred_questions`, and Step 4 routes C-class findings to Ask.

### Reviewer prompt budget measurement

Current Step 2c block (`skills/critical-review/SKILL.md` lines 74–105): **30 content lines** (`sed -n '74,105p' skills/critical-review/SKILL.md | wc -l`). Spec Technical Constraint sets the declared budget at 2× = **60 lines**. Task 3 must report the post-edit line count; if it exceeds 60, the plan requires the taxonomy examples to be compressed before proceeding.

## Tasks

### Task 1: Author V2 fixture — pure-B aggregation (Kotlin-analog)
- **Files**: `tests/fixtures/critical-review/pure_b_aggregation.md`, `tests/fixtures/critical-review/pure_b_aggregation.meta.json`
- **What**: Produce a fixture artifact (`.md`) that four distinct reviewer angles can legitimately raise adjacent-gap findings against — no angle can produce a fix-invalidating defect, the concerns must all be about untouched adjacent code paths. The `.meta.json` records each expected concern identifier plus its expected class (`B`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Dispatch via `Agent(subagent_type="general-purpose", description="V2 pure-B fixture author")` to isolate authorship from prompt editors (R8 AC). Agent prompt must explicitly state: (1) you are authoring a fixture; you will NOT be shown the reviewer/synthesizer prompts; (2) produce an artifact that resembles the protein-grams Kotlin failure pattern (four structurally-independent adjacent-gap concerns); (3) metadata JSON schema: `{"fixture_type": "pure_b", "concerns": [{"id": "<slug>", "expected_class": "B", "description": "<summary>"}]}` — at least 4 concerns. Reference the research discussion of the Kotlin failure in `lifecycle/classify-critical-review-findings-by-class-and-add-b-class-action-surface/research.md` §Codebase Analysis for shape guidance. Fixture must compile as valid Markdown and valid JSON.
- **Verification**: `test -f tests/fixtures/critical-review/pure_b_aggregation.md && test -f tests/fixtures/critical-review/pure_b_aggregation.meta.json && python3 -c "import json; j=json.load(open('tests/fixtures/critical-review/pure_b_aggregation.meta.json')); assert j['fixture_type']=='pure_b'; assert len(j['concerns'])>=4; assert all(c['expected_class']=='B' for c in j['concerns'])"` — pass if exit 0.
- **Status**: [x] completed (commit 80dd148; verified 4 concerns, all class B)

### Task 2: Author V2 fixture — straddle case
- **Files**: `tests/fixtures/critical-review/straddle_case.md`, `tests/fixtures/critical-review/straddle_case.meta.json`
- **What**: Produce a fixture artifact where a single concern legitimately decomposes into one A-class (core fix-invalidating defect) and one B-class (adjacent pattern) finding. Metadata records both expected concern IDs with their expected classes.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Dispatch via a **second, separate** `Agent(subagent_type="general-purpose", ...)` call (not the same agent as Task 1 — separate isolation is required for R8 AC). Agent prompt states: (1) author a fixture that demonstrates R2's split-preferred protocol; (2) the artifact text must contain one defect in the fix's core logic AND one adjacent pattern that is also concerning; (3) metadata JSON schema: `{"fixture_type": "straddle", "concerns": [{"id": "<core-slug>", "expected_class": "A", "description": "<core defect>"}, {"id": "<adjacent-slug>", "expected_class": "B", "description": "<adjacent pattern>"}]}` — exactly 2 concerns, one A, one B.
- **Verification**: `test -f tests/fixtures/critical-review/straddle_case.md && python3 -c "import json; j=json.load(open('tests/fixtures/critical-review/straddle_case.meta.json')); assert j['fixture_type']=='straddle'; classes=sorted(c['expected_class'] for c in j['concerns']); assert classes==['A','B']"` — pass if exit 0.
- **Status**: [x] completed (commit ef5511b — note: commit subject is mislabeled "pure-B" due to git index race; files are correct)

### Task 3: Update Step 2c reviewer prompt — taxonomy, JSON envelope, straddle protocol (R1 + R2)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Rewrite the reviewer prompt template at lines 74–105 to include (a) an A/B/C taxonomy block with one worked example per class, (b) a straddle-split protocol with bias-up-to-A for unsplittable cases, (c) explicit multi-class prohibition, (d) trailing JSON envelope schema delimited by `<!--findings-json-->` with enum-constrained `class` field. Prose findings (`### What's wrong` / `### Assumptions at risk` / `### Convergence signal`) are preserved for Step 3 presentation — the JSON envelope is additive, not a replacement.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Edit scope is lines 74–105 plus any surrounding text that describes the reviewer output contract. Taxonomy block: `A = fix-invalidating` (worked example: "the refactor removes a null check the caller depends on"), `B = adjacent-gap` (worked example: "the fix is correct but the analytics event a layer up still fires on the old path"), `C = framing` (worked example: "the commit message misrepresents the change scope"). JSON envelope schema (verbatim, matches spec R1):
  ```
  {
    "angle": "<angle name>",
    "findings": [
      {
        "class": "A" | "B" | "C",
        "finding": "<text>",
        "evidence_quote": "<verbatim quote from the artifact>",
        "straddle_rationale": "<optional: see R2>"
      }
    ]
  }
  ```
  Straddle protocol text must include both "split into separate findings" AND "bias up to A on unsplittable" AND explicit "multi-class tags are prohibited." The `<!--findings-json-->` delimiter instruction appears after the prose format so the reviewer emits prose first, then the delimiter, then JSON. Preserve existing load-bearing text: `"Do not soften or editorialize"` (from Step 3), `"Do not cover other angles. Do not be balanced."` (line 103). **Fallback prompt at lines 113–142 is NOT updated** per spec Non-Requirements.
- **Verification**: `grep -cE 'fix-invalidating|adjacent-gap|framing' skills/critical-review/SKILL.md` ≥ 3 AND `grep -cE 'findings-json|JSON envelope' skills/critical-review/SKILL.md` ≥ 1 AND `grep -cE 'split|separate findings' skills/critical-review/SKILL.md` ≥ 1 AND `grep -cE 'straddle_rationale|unsplittable' skills/critical-review/SKILL.md` ≥ 1 AND the reviewer-prompt block line count (re-measure with `sed -n '<start>,<end>p' skills/critical-review/SKILL.md | wc -l`) ≤ 60. If line count > 60, compress worked examples before committing.
- **Status**: [ ] pending

### Task 4: Add orchestrator-side JSON envelope extraction instructions (R1 validation surface)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add a new `#### Step 2c.5: Envelope Extraction` subsection immediately after Step 2c fallback (before Step 2d) with **loud operator note + prose-only pass-through** for malformed-envelope reviewers, NOT silent C-class coercion.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Insert between the existing Step 2c fallback block (ends line 144) and Step 2d synthesis (starts line 146). Instruction body: scan each reviewer's output for the `<!--findings-json-->` delimiter using the LAST occurrence anchor (`re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)` — split at the last match to tolerate prose quoting the delimiter); `json.loads` the tail; assert schema (`angle` str, `findings` list, each finding has `class ∈ {"A","B","C"}`, `finding` str, `evidence_quote` str, optional `straddle_rationale` str). On any failure, the orchestrator:
  1. Emits an operator-facing line: `⚠ Reviewer {angle} emitted malformed JSON envelope ({reason}) — class tags for this angle are UNAVAILABLE. Prose findings presented as-is; the B→A refusal gate will EXCLUDE this reviewer's findings from its count rather than treating them as C-class.`
  2. Passes the reviewer's prose findings to the synthesizer as an untagged block (distinct from class-tagged JSON envelopes of well-formed reviewers).
  3. In Step 2d, the synthesizer includes the untagged prose in final presentation under `## Concerns` but does NOT count it toward the A-class tally that gates verdict-framing.
- **Verification**: `sed -n '/^#### Step 2c.5/,/^### Step 2d/p' skills/critical-review/SKILL.md | grep -cE 'findings-json|envelope|malformed'` ≥ 3 (anchored heading patterns; the original `/Step 2c.5/,/Step 2d/` form stopped at the first body mention of "Step 2d") AND `grep -cE 'UNAVAILABLE|EXCLUDE this reviewer' skills/critical-review/SKILL.md` ≥ 1.
- **Status**: [x] completed (commit pending; Step 2c.5 inserted between Step 2c fallback and Step 2d, anchored AC: 5 lines, UNAVAILABLE+EXCLUDE: 1 line)

### Task 5: Update Step 2d synthesis prompt — same-class through-lines + evidence-based re-examination + B→A refusal (R3)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Rewrite the Step 2d synthesis prompt template at lines 148–181 so the synthesizer (a) receives concatenated JSON envelopes from all surviving reviewers, (b) applies through-line aggregation within same-class cohorts only, (c) re-examines each finding's `evidence_quote` against the artifact before accepting its tag and emits explicit re-classification notes when tags change, (d) refuses to emit a verdict-framing `## Objections` narrative when zero findings are A-class after re-examination.

  **Note on artifact access**: SKILL.md line 154–155 of the synthesis prompt template already contains `## Artifact\n{artifact content}` — the synthesizer has the full artifact text in context. "Evidence-based re-examination" is grounded in that artifact content, not a self-consistency check against reviewer-produced strings.
- **Depends on**: [3, 4]
- **Complexity**: simple
- **Context**: Edit scope is lines 148–181. Keep `## Objections / ## Through-lines / ## Tensions / ## Concerns` headers and load-bearing guardrails (research §Conventions — backlog 053, 082, 085). Add new synthesis instructions:
  - Instruction #2 replacement: "Find the through-lines — claims or concerns that appear across multiple angles **within the same class**. A-class through-lines, B-class through-lines, and C-class through-lines are distinct; do not merge them."
  - New instruction: "Before accepting any finding's class tag, re-read its `evidence_quote` field against the artifact content provided above. If the evidence supports a different class, re-classify and surface a note: `Synthesizer re-classified finding N from B→A: <rationale>` (upgrade) or `Synthesizer re-classified finding N from A→B: <rationale>` (downgrade). Downgrades commonly fire on straddle-rationale findings where the evidence only supports the adjacent concern."
  - New instruction: "After evidence re-examination, count A-class findings from well-formed envelopes only (untagged prose from malformed envelopes per Step 2c.5 does NOT count). If the count is zero, do NOT emit an `## Objections` section. B-class findings in the absence of any A-class finding surface under `## Concerns` at most."
  - Closing: keep "These are the strongest objections. Proceed as you see fit." but add preceding: "If no A-class findings remained after evidence re-examination, open the synthesis with: `No fix-invalidating objections after evidence re-examination. The concerns below are adjacent gaps or framing notes — do not read as verdict.`"
- **Verification**: `grep -cE 'same class|within class|same-class' skills/critical-review/SKILL.md` ≥ 1 AND `grep -cE 're-examine|re-classif|evidence_quote' skills/critical-review/SKILL.md` ≥ 1 AND the synthesis block contains an explicit refusal clause (grep `no.*A-class|zero.*A-class|no.*Objections`).
- **Status**: [ ] pending

### Task 6: Update Step 4 — C-class findings default to Ask (R7)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Update the Apply/Dismiss/Ask block at lines 201–226 so C-class (framing) findings route to Ask by default. A- and B-class continue through the existing logic. Ticket 067 invariants (Dismiss-N=0 omission, six direction verbs, Apply-bar text) must not regress.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Insert a one-sentence clause in the Ask definition (around line 207): "**C-class (framing) findings default to Ask unless self-resolution yields a verifiable fix** — framing concerns often depend on operator intent the orchestrator cannot verify unilaterally." Do NOT modify lines 217, 218, 226.
- **Verification**: `grep -cE 'C-class|framing.*Ask|C.*default.*Ask' skills/critical-review/SKILL.md` ≥ 1 AND `grep -cE '^Dismiss: 0' docs/overnight-operations.md` = 0 AND `grep -oE 'strengthened|narrowed|clarified|added|removed|inverted' skills/critical-review/SKILL.md | wc -l` ≥ 6 (occurrence count of direction verbs; original `-c` formula counted lines and was unsatisfiable).
- **Status**: [x] completed (commit pending; C-class clause appended to Ask definition, all 6 verbs preserved with 8 total occurrences)

### Task 7: Add Step 2e residue write — inline python3 atomic write + session resolution + ad-hoc note (R4 + R5)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Insert a new `### Step 2e: Residue Write` subsection between Step 2d synthesis (ends line 191) and Step 3 (starts line 193) that (a) resolves `{feature}` via `$LIFECYCLE_SESSION_ID` + whitespace-stripped match against `lifecycle/*/.session`, (b) atomically writes `lifecycle/{feature}/critical-review-residue.json` via an **inline `python3 -c` invocation** calling `claude.common.atomic_write` (no deploy-bin helper), (c) emits ad-hoc operator note when no lifecycle context is resolvable but B-class findings exist.
- **Depends on**: [4, 5]
- **Complexity**: simple
- **Context**: Feature-resolution logic embedded as shell + inline Python:
  ```
  REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
  if [ -z "$REPO_ROOT" ]; then
    # ad-hoc mode — no git repo; if B-class findings exist, emit the ad-hoc note and skip write
    ...
  fi
  MATCHES=$(python3 -c "
  import os,glob,sys
  sid=os.environ.get('LIFECYCLE_SESSION_ID','')
  hits=[p for p in glob.glob(os.path.join('$REPO_ROOT','lifecycle','*','.session')) if open(p).read().strip()==sid]
  print('\n'.join(hits))
  ")
  case "$(echo "$MATCHES" | wc -l)" in
    0|*) ... # single, zero, multi resolution branches
  esac
  ```
  Resolution rules:
  - **Exactly one match**: `{feature}` = parent-directory name of the match; proceed to atomic write.
  - **Zero matches (or empty REPO_ROOT)**: ad-hoc mode; if B-class findings exist, emit exactly `Note: B-class residue not written — no active lifecycle context.` to operator output; no file write.
  - **Multiple matches**: emit `Note: multiple active lifecycle sessions matched $LIFECYCLE_SESSION_ID; B-class residue write skipped.`; no file write.

  Atomic write invocation (inline, single call site):
  ```
  python3 -c "
  import json, sys, os
  sys.path.insert(0, '$REPO_ROOT')
  from claude.common import atomic_write
  from pathlib import Path
  payload = json.loads(sys.stdin.read())
  target = Path('$REPO_ROOT') / 'lifecycle' / '$FEATURE' / 'critical-review-residue.json'
  atomic_write(target, json.dumps(payload, indent=2) + '\n')
  " <<< "$PAYLOAD_JSON"
  ```

  Residue payload schema (spec R4): `{"ts": "<ISO 8601>", "feature": "<slug>", "artifact": "<path reviewed>", "synthesis_status": "ok|failed", "reviewers": {"completed": <int>, "dispatched": <int>}, "findings": [{"class": "B", "finding": "<text>", "reviewer_angle": "<angle>", "evidence_quote": "<text>"}]}`.

  Gates:
  - Zero B-class findings → NO residue file written (short-circuit before the python3 invocation).
  - Synthesis-failure path writes `synthesis_status: "failed"` with whatever B-class findings surfaced from Step 2c.
  - Path-argument invocations (`/critical-review <path>`) and auto-trigger invocations (from `specify.md §3b` / `plan.md`) both obey session-bound resolution — the argument path does not re-bind `{feature}`.
- **Verification**: `grep -cE 'LIFECYCLE_SESSION_ID|\.session' skills/critical-review/SKILL.md` ≥ 2 AND `grep -c 'B-class residue not written' skills/critical-review/SKILL.md` ≥ 1 AND `grep -c 'critical-review-residue' skills/critical-review/SKILL.md` ≥ 1 AND `grep -c 'git rev-parse --show-toplevel' skills/critical-review/SKILL.md` ≥ 1 AND `grep -cE 'strip\(\)|whitespace' skills/critical-review/SKILL.md` ≥ 1 AND `grep -c 'atomic_write' skills/critical-review/SKILL.md` ≥ 1 (inline helper invocation reference). Integration tested by Task 10 fixtures.
- **Status**: [ ] pending

### Task 8: Implement `render_critical_review_residue` in the morning report (R6)
- **Files**: `claude/overnight/report.py`
- **What**: Add new function `render_critical_review_residue(data: ReportData) -> str` that reads all `lifecycle/*/critical-review-residue.json` files, renders a `## Critical Review Residue (N)` section listing per-feature residue summaries with degraded-mode annotations. Register in `generate_report`'s sections list between `render_deferred_questions` and `render_failed_features`. Empty-state literal spelled out per spec R6.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Follow `render_deferred_questions` pattern (report.py:834–881). Signature: `def render_critical_review_residue(data: ReportData) -> str`. Implementation outline:
  - Glob `data.repo_root / "lifecycle" / "*/critical-review-residue.json"` (inspect report.py for existing repo-root field; add one if needed, matching ReportData construction sites).
  - For each file: `json.load` inside try/except JSONDecodeError → malformed handling (emit `Feature {slug}: residue file malformed, skipped.`); missing required fields default degraded annotation to `"unknown"` but do not raise.
  - Section header: `## Critical Review Residue ({N})` where N is file count (clean + malformed both counted).
  - Per-feature body: `### {feature} ({len(findings)})`, per-finding one-liners `- {reviewer_angle}: {finding}`.
  - Degraded annotation (indented `> ⚠ degraded: ...` line beneath feature header) when `synthesis_status != "ok"` (renders `synthesis failed`) and/or `reviewers.completed < reviewers.dispatched` (renders `partial reviewer coverage (N of M)`). Both may apply simultaneously.
  - Empty state (zero matching files): header `## Critical Review Residue (0)` + verbatim body `No residue files this cycle. Absence may indicate: zero B-class findings, no lifecycle-context runs, or total reviewer failure (which does not write a residue file).`
  - Register in `generate_report` sections list (line 1340) between `render_deferred_questions(data)` and `render_failed_features(data)`.
- **Verification**: `grep -c render_critical_review_residue claude/overnight/report.py` ≥ 2 AND `grep -cE 'no lifecycle-context runs|total reviewer failure' claude/overnight/report.py` ≥ 1 AND `just test` passes (new tests added in Task 9).
- **Status**: [x] completed (commit 31a35b4; grep counts 2 + 1)

### Task 9: Write `render_critical_review_residue` + residue-generation unit tests (R4 + R5 + R6 ACs)
- **Files**: `tests/test_report.py` (extension) or new `tests/test_critical_review_report.py`
- **What**: Pytest module covering both the render path (R6) and the residue-generation semantics (R4 + R5) — residue generation is now inline in SKILL.md, so integration-level ACs are tested by constructing residue files directly and asserting downstream behavior. Cases:
  - **Render (R6)**: (i) clean `synthesis_status: "ok"` residue, (ii) `synthesis_status: "failed"` annotation, (iii) partial-coverage annotation, (iv) both annotations simultaneously, (v) empty-state literal, (vi) malformed JSON graceful skip, (vii) missing required fields defaulting to "unknown", (viii) **placement assertion**: `generate_report` output contains `## Critical Review Residue` between `## Deferred Questions` and `## Failed Features` (string-index comparison).
  - **Residue-write invariants (R4 + R5)**: (ix) a residue file written via `claude.common.atomic_write` with the R4 schema parses as valid JSON and contains required fields; (x) zero-B-class short-circuit path produces no file (simulated by not calling the write); (xi) `synthesis_status: "failed"` pass-through semantics round-trip through the renderer correctly; (xii) operator-note literal strings (`B-class residue not written — no active lifecycle context.`, `multiple active lifecycle sessions matched`, `⚠ Reviewer {angle} emitted malformed JSON envelope`) appear verbatim in SKILL.md — these are string-presence checks on SKILL.md (already covered by Tasks 4 + 7 verification greps; consolidated here as a single test for regression detection).
- **Depends on**: [4, 7, 8]
- **Complexity**: simple
- **Context**: Prefer extension of `tests/test_report.py` (follows `TestMergedFeatureAnnotations` pattern). Each render test constructs a minimal `ReportData` with a mocked `lifecycle/` path holding a crafted residue file (use `tmp_path` + monkeypatched path resolver). Residue-invariant tests (ix–xii) use the Python `atomic_write` helper directly, skipping the SKILL.md-orchestrated invocation path (that path is integration-tested in Task 11 fixture runs).
- **Verification**: `just test -k critical_review_residue` — pass if exit 0, all twelve cases pass. Follow-up confirms AC6 literal: `grep -cE 'no lifecycle-context runs|total reviewer failure' claude/overnight/report.py` ≥ 1.
- **Status**: [ ] pending

### Task 10: Baseline-stability measurement — 5 runs per fixture with updated prompts
- **Files**: `tests/fixtures/critical-review/baseline-stability.json`, `tests/baseline_critical_review.py` (measurement script — lives in `tests/` but is invoked manually, not in the `just test` default suite)
- **What**: Before committing to a 3-of-3 pass criterion in Task 11, measure actual per-run pass probability of the updated Step 2c + 2d prompts against the V2 fixtures. Invoke `/critical-review` 5× per fixture, record per-run pass/fail outcomes, compute estimated per-run probability, and commit `baseline-stability.json` with the measurement. If per-run probability is < 0.90 for either fixture, escalate to the user — either (a) tighten the prompts before proceeding, or (b) relax Task 11's pass criterion to 2-of-3 majority.
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: complex
- **Context**: The measurement script mirrors Task 11's test logic but records probability, not pass/fail. Output schema:
  ```json
  {
    "measured_at": "<ISO 8601>",
    "skill_version_commit": "<git sha of HEAD>",
    "fixtures": {
      "pure_b_aggregation": {"runs": 5, "passed": <int>, "per_run_probability": <float>},
      "straddle_case": {"runs": 5, "passed": <int>, "per_run_probability": <float>}
    },
    "retry_policy": "single-retry | no-retry | escalate",
    "pass_criterion_recommendation": "3-of-3 | 2-of-3 | escalate"
  }
  ```
  `per_run_probability = passed / runs`. `retry_policy` is computed: if both fixtures ≥ 0.90 → "single-retry" (3-of-3 stays with one CI retry on transient failure); if either fixture 0.80–0.90 → "escalate" to user; if either < 0.80 → "escalate + tighten prompts." Commit `baseline-stability.json` to the repo as provenance; Task 11's retry policy reads from this file. The measurement script is NOT part of `just test` default — it runs once per prompt revision, manually, via `python3 tests/baseline_critical_review.py`.
- **Verification**: `test -f tests/fixtures/critical-review/baseline-stability.json && python3 -c "import json; j=json.load(open('tests/fixtures/critical-review/baseline-stability.json')); assert j['fixtures']['pure_b_aggregation']['runs']==5; assert j['fixtures']['straddle_case']['runs']==5; assert j['pass_criterion_recommendation'] in ['3-of-3','2-of-3','escalate']"` — pass if exit 0. If `pass_criterion_recommendation == 'escalate'`, halt and route to user before continuing to Task 11.
- **Status**: [ ] pending

### Task 11: Write classifier-validation pytest against V2 fixtures (R8)
- **Files**: `tests/test_critical_review_classifier.py`, `pytest.ini` (add `slow` marker registration), `tests/conftest.py` (add `--run-slow` opt-in, skip-unless-opted logic)
- **What**: Pytest runs the updated Step 2c + 2d prompts 3× per fixture via sonnet-model reviewer dispatch. Pass criterion is as recommended by Task 10's baseline (default 3-of-3; may be 2-of-3 if baseline measurement escalated). Fixture (a): zero A-class findings AND synthesis narrative contains neither "blocks" nor "invalidates." Fixture (b): exactly one A-class finding matching the named core concern AND exactly one B-class finding matching the named adjacent concern.
- **Depends on**: [1, 2, 3, 4, 5, 10]
- **Complexity**: complex
- **Context**: Test structure:
  - Fixture (a) loader: reads `tests/fixtures/critical-review/pure_b_aggregation.md` + `pure_b_aggregation.meta.json`; dispatches `/critical-review tests/fixtures/critical-review/pure_b_aggregation.md` three times; asserts per-run that parsed synthesis contains zero `"class": "A"` occurrences AND `synthesis.count('blocks') + synthesis.count('invalidates') == 0`.
  - Fixture (b) loader: loads `straddle_case.{md,meta.json}`; dispatches three times; per run asserts exactly one A-class finding whose text contains the core-concern substring from `meta.json` AND exactly one B-class finding whose text contains the adjacent-concern substring.
  - Reviewer-survival check per run: each of the 3 runs MUST have `reviewers.completed == reviewers.dispatched` (read from residue file if lifecycle-context, else from operator output). A run with partial reviewer failure is retried once (max 1 retry); if still partial, test fails loudly distinguishing "prompt broken" from "transient reviewer failure."
  - Read pass criterion from `tests/fixtures/critical-review/baseline-stability.json` `pass_criterion_recommendation` field. If `3-of-3`, require all 3 runs pass. If `2-of-3`, require majority. If `escalate`, skip with explicit message (shouldn't reach this state — Task 10 halts before Task 11 in the escalate case).
  - Mark test functions with `@pytest.mark.slow`. Register `slow` marker in `pytest.ini` (`markers = \n    slow: opt-in tests that invoke live models`). Default `just test` skips slow tests via `conftest.py` `pytest_collection_modifyitems` with skip-unless-`--run-slow`. Add `--run-slow` via `pytest_addoption`.
- **Verification**: `just test -k critical_review_classifier --run-slow` exits 0 AND `just test -k critical_review_classifier --run-slow -v 2>&1 | grep -cE 'PASSED|FAILED'` ≥ 2 (proves both fixture-test functions actually ran, not silently skipped) AND `grep -cE '3-of-3|named-concern-to-class' tests/test_critical_review_classifier.py` ≥ 2 (assertion comments present in source) AND `grep -c '@pytest.mark.slow' tests/test_critical_review_classifier.py` ≥ 2.
- **Status**: [ ] pending

### Task 12: Final verification sweep — spec ACs + whole-skill line budget
- **Files**: none (verification only)
- **What**: Run the full spec AC grep battery (R1–R8 AC lines from spec.md) plus `just test`. Enforce whole-skill line budget: SKILL.md total line count ≤ 300 post-edit (current 226; Task 3 reviewer-prompt block ≤ 60; Task 4 Step 2c.5 + Task 7 Step 2e combined ≤ 60).
- **Depends on**: [3, 4, 5, 6, 7, 8, 9, 10, 11]
- **Complexity**: trivial
- **Context**: Re-run every `grep -c ...` and `test -f ...` command from spec.md R1–R8 ACs in sequence; then `just test`; then `wc -l skills/critical-review/SKILL.md` ≤ 300. Single-script verification.
- **Verification**: `just test` exits 0 AND every AC command from spec.md §Requirements R1–R8 returns its expected value AND `wc -l skills/critical-review/SKILL.md | awk '{print $1}'` ≤ 300 — script the checks in a temporary shell file; pass if zero non-matching ACs.
- **Status**: [ ] pending

## Verification Strategy
End-to-end verification has four layers:

1. **Spec AC grep battery** (Task 12): every requirement in spec.md §Requirements R1–R8 has at least one binary-checkable AC. Running them in sequence confirms prompts, residue write, morning-report rendering, Step 4 routing, and fixtures are in place with correct strings.
2. **Unit tests for render + residue invariants** (Task 9): residue-rendering + write-invariant cases, including placement in `generate_report`, in the default `just test` suite.
3. **Baseline-stability measurement** (Task 10): one-time measurement before approving Task 11's 3-of-3 criterion; sets retry policy empirically rather than by decree.
4. **Classifier validation** (Task 11): model-dependent test gated behind `--run-slow`, runs the full prompts against V2 fixtures with the baseline-informed pass criterion.

A fifth layer — held-out pilot on live `/critical-review` runs (V3) — is explicitly excluded per spec Non-Requirements.

## Veto Surface

Spec R1–R8 are spec-locked — they passed the specify-phase critical-review twice (events.log cycles 1 + 2). Operator-amendable decisions in the plan phase are limited to implementation choices within the spec contract. Items below that cross the spec boundary can only be reopened by amending the spec and restarting specify-phase review.

- **[Resolved in plan-phase critical review]** Inline `python3 -c` atomic write in SKILL.md Step 2e (chosen) over a deploy-bin helper binary. Reduces single-caller-binary scope bloat; keeps atomic-write spec R4 satisfied.
- **[Resolved in plan-phase critical review]** Baseline-stability measurement (Task 10) precedes classifier validation (Task 11). Sets 3-of-3 retry policy empirically based on measured per-run pass probability, escalating to user if either fixture measures < 0.90.
- **[Plan-phase reopenable] `render_critical_review_residue` placement in `generate_report`**: placed after `render_deferred_questions`, before `render_failed_features`. Operator may prefer a different location (e.g., after `render_executive_summary`). Task 9 (viii) asserts whatever placement is chosen.
- **[Spec-locked — amend spec to reopen] Ternary A/B/C vs. binary blocking + type axis**: research flagged A2 (binary + axis) as stronger prior-art fit; spec chose A1 (ternary) in §Non-Requirements line 133.
- **[Spec-locked — amend spec to reopen] R4 atomic-write requirement**: spec Technical Constraint line 171 mandates atomicity via pipeline.md convention.
- **[Spec-locked — amend spec to reopen] R6 morning-report surface**: research line 248 flagged the "silent dismissal with extra steps" risk; spec R6 built the consumer anyway. Operator-behavior claim (reads report → acts on B-findings) is unvalidated.
- **[Spec-locked — amend spec to reopen] R8 fixture authorship separation via subagent dispatch vs. commit-order**: spec AC line 125 explicitly allows either path; plan chose the subagent-dispatch path as operator preference. Switching to commit-order is a minor plan edit.

## Scope Boundaries
Maps to spec §Non-Requirements:
- Step 2c fallback prompt unchanged (total-failure path keeps existing Objections/Through-lines/Tensions/Concerns shape with no class tagging).
- No Kotlin-session retest — V2 fixtures only.
- No V3 held-out pilot on live runs.
- No opt-in flag / env var / feature gate — direct merge.
- No binary-blocking + orthogonal type axis — A/B/C ternary committed.
- No de-dup logic for duplicate B-class findings across reviewers.
- No dashboard card for residue files — morning report is the only consumer.
- `clarify-critic.md` taxonomy unchanged.
- H2 / FP5 pattern-anchor work deferred per epic DR-6.
- `output-floors.md` applicability block untouched (backlog 086 follow-up).
- Spec 067 R8 (zero `events.log` references in critical-review SKILL.md) preserved — residue uses a sidecar JSON file, not events.log.
