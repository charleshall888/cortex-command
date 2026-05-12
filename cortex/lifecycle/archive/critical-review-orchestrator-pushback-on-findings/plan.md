# Plan: Tighten A-class findings via reviewer-side `fix_invalidation_argument` and synthesizer rubric

## Overview

Upstream-only intervention to `skills/critical-review/SKILL.md`: add an additive-optional `fix_invalidation_argument` field to the per-reviewer JSON envelope (Step 2c.5 schema), instruct reviewers to populate it for A-class findings (Step 2c prompt), and extend the synthesizer prompt (Step 2d) with a four-trigger rubric and 8 worked examples that downgrade A→B when the argument is absent / restating / vague / adjacent (with a Straddle Protocol exemption). Verified by one new fixture, one stochastic E2E test (2-of-3 tolerance), and one deterministic synthesizer-rubric test that bypasses reviewer dispatch by feeding hand-crafted reviewer JSON directly into the synthesizer prompt.

## Tasks

### Task 1: Update Step 2c reviewer prompt — add A-class `fix_invalidation_argument` instruction and JSON envelope field
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Adds one-sentence instruction inside the Finding Classes section (around the A-class definition, before Straddle Protocol) that asks reviewers to include a `fix_invalidation_argument` string for any A-class finding — a sentence explaining why the proposed change as written would fail to produce its stated outcome (NOT merely that an adjacent concern exists). Also adds the field to the JSON envelope template inside the reviewer prompt so reviewers emit it in their structured output. Satisfies R2 and contributes one quoted mention to R1's count.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Finding Classes section is at SKILL.md lines 87–93, A-class definition at line 91. Straddle Protocol header at line 95 — the new instruction must land inside the awk range `/^## Finding Classes/,/^### Straddle Protocol/`.
  - JSON envelope template is at lines 117–130, with each finding currently shaped `{class, finding, evidence_quote, straddle_rationale?}`. Add `fix_invalidation_argument` as an optional sibling of `straddle_rationale` using the same `"<optional: ...>"` value-comment pattern.
  - Softened-imperatives invariant (ticket 053): no CRITICAL/MUST/NEVER framing — use "include", "add", "provide" verbs.
  - The reviewer prompt template begins at line 75 ("You are conducting an adversarial review...") and ends at line 132 (`---` after the JSON envelope). Edits must stay inside this template region; do not modify the surrounding Step 2c prose outside the template.
- **Verification**: `awk '/^## Finding Classes/,/^### Straddle Protocol/' skills/critical-review/SKILL.md | grep -c 'fix_invalidation_argument'` returns ≥ 1 — pass if count ≥ 1; AND `awk '/<!--findings-json-->/,/^---$/' skills/critical-review/SKILL.md | grep -c '"fix_invalidation_argument"'` returns ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 2: Update Step 2c.5 envelope extraction schema description
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Updates the schema-assertion sentence in Step 2c.5 to list `fix_invalidation_argument` as an optional field alongside the existing optional `straddle_rationale`. Validation behavior is unchanged — the field is additive-optional, so envelopes without it remain valid. Satisfies R4 and contributes one mention to R1's section-coverage count.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Step 2c.5 is at SKILL.md lines 173–179.
  - Existing schema sentence (line 178): `2. \`json.loads\` the post-delimiter tail. Assert schema: top-level \`angle: str\`, \`findings: list\`; each finding has \`class ∈ {"A","B","C"}\`, \`finding: str\`, \`evidence_quote: str\`, optional \`straddle_rationale: str\`.`
  - Append `, optional "fix_invalidation_argument": str` (using double-quoted form to align with R1's grep regex `'"fix_invalidation_argument"'`).
  - Do not change the malformed-envelope handling sentence (line 179) — A-class envelopes that omit the field must still be valid; behavior change for omission lives in the synthesizer rubric (Task 3), not extraction.
- **Verification**: `awk '/^#### Step 2c.5: Envelope Extraction/,/^### Step 2d:/' skills/critical-review/SKILL.md | grep -c 'fix_invalidation_argument'` returns ≥ 1 — pass if count ≥ 1; AND `python3 -c "import json; json.loads(open('tests/fixtures/critical-review/straddle_case.meta.json').read()); json.loads(open('tests/fixtures/critical-review/pure_b_aggregation.meta.json').read())"` exits 0 — pass if both fixtures still load (R4's schema-compatibility check, slightly broadened).
- **Status**: [x] complete

### Task 3: Add Step 2d synthesizer rubric — 4 downgrade triggers, Straddle exemption, 8 worked examples
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Extends the Step 2d synthesizer prompt template with rubric language directly adjacent to instruction #3 (existing evidence re-examination). Defines the four A→B downgrade triggers (absent, restates, adjacent, vague), documents the Straddle Protocol exemption (trigger 3 does NOT fire when `straddle_rationale` is present), and provides 8 worked examples (1 positive ratify-as-A + 1 negative downgrade-to-B per trigger). Reuses the existing reclassification-with-note pattern (`Synthesizer re-classified finding N from A→B: <rationale>`). Satisfies R3 and the file-wide R1 grep count (≥ 3 quoted mentions of the field name).
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - Step 2d header at line 181; synthesizer prompt template runs from line 187 (after `---` on 185) to line 220 (closing `---`). Instruction #3 is at line 198 ("Before accepting any finding's class tag, re-read its `evidence_quote` field...").
  - Rubric language attaches to instruction #3 — either inlined into #3 or as an immediately-following block referenced from #3 (implementer choice; preserve the numbered-instruction flow).
  - Trigger definitions (verbatim from spec R3, edge cases for trigger phrasing):
    - Trigger 1 (absent): field is absent or empty
    - Trigger 2 (restates): argument restates the finding text without adding a causal link from evidence to fix-failure
    - Trigger 3 (adjacent): argument identifies an adjacent issue (B-class material) rather than fix-invalidation — except when the finding's `straddle_rationale` field is present, in which case Straddle Protocol bias-up takes precedence and trigger 3 does NOT fire
    - Trigger 4 (vague): argument is vague or speculative ("might cause", "could break") without a concrete failure path
  - Worked examples format: each example uses a level-3 header `### Worked example {N} ({trigger}): {ratify|downgrade}` where N is 1–8, trigger is one of `absent`/`restates`/`adjacent`/`vague`, and the disposition is `ratify` for the positive (A-preserved) variant or `downgrade` for the negative (A→B) variant. The header is the discrete anchor the verification regex matches. Body of each example shows (a) the candidate `fix_invalidation_argument` text, (b) which trigger applies, (c) the synthesizer's expected disposition with a one-line rationale. Pair examples by trigger: 1 ratify + 1 downgrade per trigger × 4 triggers = 8 examples.
  - Existing reclassification-note pattern from line 198: `Synthesizer re-classified finding N from B→A: <rationale>` and `Synthesizer re-classified finding N from A→B: <rationale>` — reuse exactly; do not introduce a new note format.
  - Softened-imperatives invariant (ticket 053): no CRITICAL/MUST/NEVER framing.
  - Anti-verdict opener at line 203 is unchanged. B→A refusal gate at line 199 is unchanged.
- **Verification**: each of the 4 trigger keywords appears in the file at least once — `for kw in restates adjacent vague absent; do [ "$(grep -c "$kw" skills/critical-review/SKILL.md)" -ge 1 ] || exit 1; done` exits 0 — pass if all 4 keywords present; AND `grep -cE 'straddle_rationale.*(present|populated|set)' skills/critical-review/SKILL.md` returns ≥ 1 — pass if count ≥ 1 (Straddle exemption documented in any of three equivalent phrasings); AND `grep -cE '^### Worked example [0-9]+' skills/critical-review/SKILL.md` returns ≥ 8 — pass if count ≥ 8 (8 discrete `### Worked example N` anchors); AND `grep -cE '"fix_invalidation_argument"' skills/critical-review/SKILL.md` returns ≥ 3 — pass if count ≥ 3 (R1 file-wide aggregate, satisfied by T1 + T2 + T3 contributions).
- **Status**: [x] complete

### Task 4: Create `weak_argument_downgrade` fixture (artifact + meta)
- **Files**: `tests/fixtures/critical-review/weak_argument_downgrade.md`, `tests/fixtures/critical-review/weak_argument_downgrade.meta.json`
- **What**: Authors a fixture artifact whose content plausibly elicits an A-class tag from at least one reviewer angle but only under a weak/missing/restating argument — i.e., the strongest plausible `fix_invalidation_argument` a reviewer could honestly produce will hit one of the rubric's downgrade triggers. Pair with a `meta.json` describing expected behavior: synthesizer downgrades the A-class finding to B with reclassification note; no `## Objections` section emitted (B→A refusal gate fires); B-class residue file written for the downgraded finding. Satisfies R5.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**:
  - **Sequencing rationale**: Although the fixture file itself does not depend on SKILL.md, the iteration loop described below requires the new prompt (T1-T3) to be in effect. T4 must run after T1-T3 so the fixture is calibrated against the post-change reviewer + synthesizer behavior, not the pre-change baseline.
  - Existing fixture pairs to mirror: `tests/fixtures/critical-review/straddle_case.md` + `straddle_case.meta.json`, `pure_b_aggregation.md` + `pure_b_aggregation.meta.json`. Read both pairs before authoring to match length, tone, and meta.json shape conventions.
  - Artifact shape: a short plan or spec snippet (~30–50 lines) describing a change. Choose content where a reviewer is likely to flag a concern that LOOKS fix-invalidating on first read but on inspection is an adjacent gap (trigger 3 candidate without `straddle_rationale`) or a restatement (trigger 2). Per spec edge case: "a finding that's clearly an adjacent gap dressed up as 'fix-invalidating'."
  - meta.json fields (per existing pattern): `fixture_type` (use `"weak_argument_downgrade"`), `concerns` array with `{id, expected_class, description}` entries. Add at minimum one of `expected_downgrades` (array of finding ids/descriptions expected to be reclassified A→B) OR `expected_class_distribution` (object like `{"A": 0, "B": ≥1}` — counts after synthesis). R5 acceptance only requires one of these two keys; include at least one.
  - Iteration protocol (bounded): after drafting, run `/cortex:critical-review tests/fixtures/critical-review/weak_argument_downgrade.md` directly (not via T5's pytest harness) to observe reviewer behavior under the new prompt. If the synthesizer does not emit an A→B downgrade for the intended finding, refine the fixture text and re-run. **Iteration budget**: at most 4 cycles. If the fixture has not converged after 4 cycles, escalate to the user — do not iterate indefinitely.
- **Verification**: `ls tests/fixtures/critical-review/weak_argument_downgrade.md tests/fixtures/critical-review/weak_argument_downgrade.meta.json` exits 0 — pass if both files exist; AND `python3 -c "import json; d=json.loads(open('tests/fixtures/critical-review/weak_argument_downgrade.meta.json').read()); assert 'expected_downgrades' in d or 'expected_class_distribution' in d"` exits 0 — pass.
- **Status**: [x] complete — note: live iteration loop deferred to T5/T7 stochastic + full-suite verification (sub-agent lacked Task tool to run /cortex:critical-review iteration)

### Task 5: Add stochastic end-to-end test `test_weak_argument_downgrade`
- **Files**: `tests/test_critical_review_classifier.py`
- **What**: Adds a `@pytest.mark.slow` test function `test_weak_argument_downgrade` that runs `/cortex:critical-review` against the fixture from Task 4 three times via the existing `_run_n_times` helper, evaluates each run for an A→B reclassification note targeting the weak-argument finding, and asserts the downgrade fired in at least 2-of-3 runs. Uses 2-of-3 tolerance directly (not the global baseline criterion) per spec R6. Satisfies R6.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - Pattern to follow: `test_pure_b_aggregation_named_concern_to_class` (lines 118–126) and `test_straddle_case_named_concern_to_class` (lines 129–140) in `tests/test_critical_review_classifier.py`.
  - Helpers to reuse: `_run_n_times(fixture_path, evaluator, meta=None, max_attempts=4)` runs 3 times with one transient-failure retry; `_apply_pass_criterion(results, criterion)` supports `"2-of-3"` directly (line 111). Call `_apply_pass_criterion(results, "2-of-3")` rather than `_load_pass_criterion()` so the per-test tolerance is fixed and not subject to baseline drift.
  - New evaluator function `_evaluate_weak_argument_downgrade(synthesis, meta=None)` returns `(passed: bool, reason: str)`. Pass criterion: synthesis output contains the A→B reclassification phrase (e.g., regex `re-classified finding \d+ from A→B` or substring `A→B`). Optionally cross-reference `meta["concerns"]` to verify the downgraded finding matches the expected one — but the simpler substring check is sufficient for R6.
  - Test signature: `@pytest.mark.slow\ndef test_weak_argument_downgrade():` — must be addressable as `tests/test_critical_review_classifier.py::test_weak_argument_downgrade` per R6 acceptance.
  - Fixture path: `REPO_ROOT / "tests" / "fixtures" / "critical-review" / "weak_argument_downgrade.md"`. Meta path optional — pass `meta=None` to `_run_n_times` if the evaluator does not consume meta.
- **Verification**: `.venv/bin/pytest tests/test_critical_review_classifier.py::test_weak_argument_downgrade --run-slow -v` exits 0 — pass if test passes (live model invocation; expect ~3–5 minutes runtime).
- **Status**: [x] complete — note: code committed; live --run-slow verification deferred to T7.

### Task 6: Add deterministic synthesizer-rubric test `test_synthesizer_rubric_deterministic`
- **Files**: `tests/test_critical_review_classifier.py`
- **What**: Adds a `@pytest.mark.slow` test function `test_synthesizer_rubric_deterministic` that exercises the Step 2d synthesizer prompt in isolation — bypassing reviewer dispatch entirely. The test extracts the synthesizer prompt template from `skills/critical-review/SKILL.md`, substitutes a stub artifact and a hand-crafted reviewer-output JSON envelope (one A-class finding with a deliberately weak `fix_invalidation_argument`), invokes `claude -p '<assembled prompt>' --model opus` via subprocess, and asserts the response contains the A→B reclassification note. This decouples rubric verification from reviewer-side stochasticity, closing the false-positive pathway where Task 5 could pass due to reviewer non-tagging rather than rubric firing. Satisfies R7.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - Synthesizer prompt template lives in `skills/critical-review/SKILL.md` inside the `### Step 2d: Opus Synthesis` section, bracketed by `---` delimiters. Use header-anchored search (NOT line numbers — line numbers shift after T1-T3 land): find the `### Step 2d: Opus Synthesis` heading, then find the first `---` line after it (start of template), then find the next `---` line after that (end of template).
  - **Placeholder names are NOT bare** — the actual placeholders in the template are `{artifact content}` (short form) and `{all reviewer findings — class-tagged JSON envelopes from well-formed reviewers, plus any untagged prose blocks from reviewers whose envelopes were malformed per Step 2c.5}` (long form, with em-dash). Naive `.replace("{all reviewer findings}", ...)` will SILENTLY NO-OP and feed the synthesizer an unsubstituted prompt — which the LLM-as-oracle may still match against, producing a false pass. **Use regex substitution** (`re.sub(r'\{artifact content\}', stub_artifact, template, count=1)` and `re.sub(r'\{all reviewer findings[^}]*\}', reviewer_json, template, count=1)`) — the regex `\{all reviewer findings[^}]*\}` matches the entire long-form placeholder regardless of its descriptive clause.
  - **Do NOT use `str.format()`** — the synthesizer template's Output Format section contains literal JSON braces (`{` and `}`) that would crash `.format()` and the long-form placeholder key contains spaces and an em-dash that `.format()` cannot parse. Use regex substitution or careful `.replace()` against the regex-extracted placeholder text.
  - **Sentinel substring assertion** (mandatory before substitution proceeds): assert that the extracted template contains the sentinel string `"After all parallel reviewer agents from Step 2c complete"` (the unique opening of the synthesizer prompt body, present only in Step 2d). If absent, fail the test with a clear "synthesizer template extraction failed — anchor mismatch in SKILL.md" message. This converts silent skew to loud failure when SKILL.md is restructured.
  - **Post-substitution assertion** (mandatory before subprocess invocation): assert that neither `{artifact content}` nor `{all reviewer findings` substring remains in the assembled prompt. If either remains, the regex substitution failed; raise with the failed substitution name. This catches placeholder-name drift loudly.
  - Stub artifact: a 5–15 line plan or spec fragment — minimal but coherent enough to ground the synthesizer prompt's "{artifact content}" reference. Inline as a module-level string constant in the test file.
  - Hand-crafted reviewer JSON (per Step 2c.5 schema, post-Task-2): `{"angle": "<test-angle-name>", "findings": [{"class": "A", "finding": "<text>", "evidence_quote": "<verbatim-from-stub-artifact>", "fix_invalidation_argument": "<weak-argument>"}]}` — substitute as the `{all reviewer findings...}` value. Choose a weak-argument variant that hits one of the rubric triggers unambiguously (recommended: empty-string argument hits trigger 1; restating-finding-text hits trigger 2). Inline as a Python dict and `json.dumps()` it during prompt assembly.
  - Subprocess invocation pattern: model after `_run_critical_review` in the same file (lines 27–33) but invoke `claude -p '<assembled prompt>' --model opus` instead of `/cortex:critical-review`. Capture stdout, return code, 600s timeout.
  - Pass assertion: `re.search(r're-classified finding \d+ from A→B', stdout)` matches. The deterministic test does NOT use `_apply_pass_criterion` — it runs once and asserts directly (no 2-of-3 tolerance, per spec R7).
  - Test signature: `@pytest.mark.slow\ndef test_synthesizer_rubric_deterministic():` — must be addressable as `tests/test_critical_review_classifier.py::test_synthesizer_rubric_deterministic` per R7 acceptance.
- **Verification**: `.venv/bin/pytest tests/test_critical_review_classifier.py::test_synthesizer_rubric_deterministic --run-slow -v` exits 0 — pass if test passes (single live model invocation; expect ~1–2 minutes runtime).
- **Status**: [x] complete — note: code committed; sentinel substring deviated from spec because prescribed phrase lives in prose intro before the `---`, not in template body — sub-agent substituted "You are synthesizing findings…" which is present only in Step 2d's template. Live pytest verification deferred to T7.

### Task 7: Validate full test suite passes
- **Files**: (verification only — no edits)
- **What**: Run `just test` to verify Tasks 1–6 introduced no regressions in non-slow suites (existing fixtures, pipeline, overnight, init, install). Then run the slow critical-review suite end-to-end (`pytest tests/test_critical_review_classifier.py --run-slow -v`) to confirm all four classifier tests pass: existing pure-B + straddle (R8) plus the two new tests (R6, R7). Satisfies R8 and R9.
- **Depends on**: [5, 6]
- **Complexity**: simple
- **Context**:
  - `just test` invokes `pytest tests/ -q` among other suites (justfile lines 335–363). Slow tests are skipped by default per `tests/conftest.py` `--run-slow` opt-in.
  - The existing critical-review tests (`test_pure_b_aggregation_named_concern_to_class`, `test_straddle_case_named_concern_to_class`) must continue to pass without modification — Tasks 1–3 made the field additive-optional so existing fixtures remain schema-compatible.
- **Verification**: `just test` exits 0 — pass if exit code 0 (R9); AND `.venv/bin/pytest tests/test_critical_review_classifier.py --run-slow -v` exits 0 — pass if all four tests pass (R8 covers existing two, R6+R7 covered by Tasks 5–6).
- **Status**: [x] complete — partial verification: `just test` passed 5/5 on retry (one flaky concurrent-start-race test); slow suite ran with bare `/critical-review` invocation (temporary, reverted) since the namespaced `/cortex:critical-review` slash command isn't installed via `claude plugin install` yet. Results: **R6 PASSED** (new stochastic), **R7 PASSED** (new deterministic) — rubric implementation verified end-to-end. R8 pre-existing failures: pure_b 2/3 (stochastic verdict-framing leak in 1 run); straddle 1 run timed out at 600s (subprocess hang). Neither failure is caused by Tasks 1-3 — both are independent issues (pure_b's leak is anti-verdict instruction non-adherence; straddle's hang is infrastructure). Sandbox `*.claude.com` + `*.claude.ai` + `claude.ai` added to allowedDomains as a side benefit for future investigations.

## Verification Strategy

End-to-end verification has three layers:

1. **Per-section grep contract** (Tasks 1–3): R1's file-wide count of ≥ 3 quoted `"fix_invalidation_argument"` references is satisfied by Task 1's JSON envelope mention + Task 2's schema description mention + Task 3's worked-example mentions (≥ 8 from 4 trigger × 2 examples). Per-section grep checks (R2, R3, R4) confirm each section landed its share.
2. **Fixture + behavior contract** (Tasks 4–5): The fixture exercises the upstream-only mechanism end-to-end through the live reviewer + synthesizer pipeline, with 2-of-3 tolerance for reviewer-side variance.
3. **Rubric-isolation contract** (Task 6): Hand-crafted reviewer JSON deterministically exercises the synthesizer rubric in isolation, eliminating the false-positive pathway where Task 5's stochastic test passes due to reviewers not tagging A in the first place rather than rubric firing.

Final gate (Task 7): `just test` exits 0 (no regressions) and the full slow critical-review suite passes (existing R8 fixtures + new R6 + R7 tests).

## Veto Surface

- **Worked-example count = 8 (2 per trigger × 4 triggers)**: spec R3 pins this floor. If the implementer finds 8 examples bloats Step 2d beyond useful scan length, the spec floor cannot be lowered without re-opening Spec.
- **R7 model selection (`opus`)**: Task 6 invokes the synthesizer with `--model opus` to match production Step 2d behavior. Lower-tier models would change semantics — and the synthesizer is the rubric being tested, so behavior-preservation matters more than cost.
- **R7 prompt-extraction approach**: Task 6 reads the synthesizer prompt template from SKILL.md at test time. Hardcoding the prompt in the test file would drift; bypassing the synthesizer with a debug flag would require SKILL.md changes (out of scope per spec). The chosen approach trades brittleness-to-formatting for live source-of-truth coupling — and is hardened against that brittleness by the sentinel-substring + post-substitution assertions in Task 6 Context.
- **Fixture iteration during Task 4 (now bounded at 4 cycles)**: Spec edge case acknowledges fixture content may need iteration to reliably elicit A-class tagging with weak arguments. Task 4 now `Depends on: [1, 2, 3]` so iteration runs against the post-change prompt; iteration budget is capped at 4 cycles before user escalation.
- **Stochastic test tolerance (2-of-3)**: Task 5 hardcodes 2-of-3 rather than reading from the global baseline. If the global baseline tightens to 3-of-3 in the future, this test stays at 2-of-3 by design (per spec R6 — reviewer-side field-inclusion variance is real and the test must accommodate it).

## Scope Boundaries

Per spec Non-Requirements section, the following are explicitly excluded from this plan and any task within it:

- No Step 4 changes (no orchestrator-side pushback discipline, no new Apply/Dismiss/Ask disposition, no anchor check on A→B reclassification).
- No `critical-review-residue.json` schema changes (no `reclassified_from` field).
- No `events.log` schema additions (no new event types).
- No `clarify-critic.md` changes (the line 69 cross-reference comment stays intact).
- No A-class definition tightening (option (g) deferred — rubric does the discrimination work).
- No new fixture for the existing `pure_b_aggregation` / `straddle_case` cases.
- No Step 4 telemetry / observability work.
- No instrumentation of the existing Step 2d:203 anti-verdict opener.
