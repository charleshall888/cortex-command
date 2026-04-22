# Specification: Classify /critical-review findings by class and add B-class action surface

> **Epic reference**: FP1 (reviewer classification) + FP2 (synthesizer restructure) + B-class action surface, scoped from parent epic `research/critical-review-scope-expansion-bias/research.md`. FP5 (pattern anchor) and FP3/FP4 (operator-interface guardrails) are out of scope per epic DR-6.

## Problem Statement

`/critical-review` has one documented failure (Kotlin Android bug, protein-grams merge mapper). Four reviewers raised legitimate B-class adjacent-gap findings; the synthesizer aggregated them into a C-class "upstream defect" verdict, which the operator read as authoritative and flipped to a wrong-layer fix. The skill's job is to surface the strongest coherent challenge — when that challenge is a prosecution-reading of adjacent gaps, the skill's ROI inverts: it actively causes a worse outcome than running no critic at all.

The load-bearing fix is two prompt-template changes in `skills/critical-review/SKILL.md` (reviewer + synthesizer, R1 + R3). Supporting surfaces added by this spec: straddle-split protocol (R2), lifecycle-feature resolution contract + sidecar JSON residue artifact (R4), ad-hoc operator-note (R5), `render_critical_review_residue` function in `claude/overnight/report.py` with degraded-mode annotation (R6), Step 4 C-class → Ask routing tightening (R7, from ticket AC6), and V2 classifier-validation fixtures + pytest (R8). Eight requirements total; R1–R3 directly address the documented failure, R4–R6 form the audit-surface per ticket AC3, R7 implements ticket AC6, R8 is pre-ship validation per ticket AC4.

## Requirements

1. **Per-finding class tagging via structured JSON envelope (Step 2c reviewer prompt)** — The reviewer prompt block at `skills/critical-review/SKILL.md` lines 76–105 is updated so each reviewer returns a JSON envelope at the end of its output, in addition to the existing prose findings used for human-facing Step 3 presentation. The JSON envelope schema:

   ```json
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

   `class` is enum-constrained to `"A"` (fix-invalidating), `"B"` (adjacent-gap), `"C"` (framing). The reviewer prompt provides a taxonomy block with at least one worked example per class and explicit instructions to emit the JSON envelope after the prose block, delimited by a line containing only `<!--findings-json-->` for robust extraction. The orchestrator parses the JSON envelope for R3 counting and R4 residue writes; it parses the prose for Step 3 presentation rendering. Findings appearing in prose must be represented in the JSON envelope (the prose is human-facing; the JSON is the authoritative classification artifact).
   - AC: `grep -cE 'fix-invalidating|adjacent-gap|framing' skills/critical-review/SKILL.md` ≥ 3 (one per class name).
   - AC: `grep -c "findings-json\|JSON envelope\|enum" skills/critical-review/SKILL.md` ≥ 1 in the Step 2c reviewer prompt block.
   - AC: Reviewer prompt contains the exact JSON schema example shown above (verified by grep for `"class": "A" | "B" | "C"` or equivalent enum union).
   - AC: Orchestrator-side extraction raises/flags on (a) missing JSON envelope when findings exist in prose, (b) class tag outside the `A|B|C` enum, (c) JSON that fails to parse. Unit test exercises each failure mode.

2. **Straddle-case protocol: split-preferred + bias-up-to-A for unsplittable cases** — When a concern cleanly separates into two distinct findings (one core, one adjacent pattern), the reviewer emits two separate findings in the JSON envelope — one with `class: "A"`, one with `class: "B"`. Multi-class tags on a single finding are prohibited.

   When a concern is genuinely unsplittable (single evidence body that straddles the A/B boundary and cannot be decomposed without distorting the evidence), the reviewer emits **one** finding tagged `class: "A"` with a required `straddle_rationale` field explaining why the split was infeasible and what the B-facet of the concern is. R3's synthesizer evidence-based re-examination (below) is authoritative over this tag — if the evidence only supports adjacent concerns, the synthesizer downgrades to B with a re-classification note.
   - AC: `grep -cE "split|separate findings" skills/critical-review/SKILL.md` ≥ 1 within the reviewer prompt block.
   - AC: `grep -c "straddle_rationale\|unsplittable" skills/critical-review/SKILL.md` ≥ 1.
   - AC: Reviewer prompt explicitly forbids multi-class tags AND explicitly directs bias-up-to-A on unsplittable cases (both patterns present).

3. **Synthesizer: through-lines scoped to same class + evidence-based B→A refusal (Step 2d)** — The synthesis prompt at `skills/critical-review/SKILL.md` lines 148–181 is updated so the synthesizer receives the concatenated JSON envelopes from all Step 2c reviewers and applies the following rules:

   (a) Through-line aggregation runs within same-class cohorts only (A-through-lines, B-through-lines, C-through-lines are distinct).

   (b) **Evidence-based re-examination** — before accepting any finding's class tag, the synthesizer re-reads the `evidence_quote` field (and any `straddle_rationale`) against the artifact. If the evidence body reads differently from the tag, it re-classifies and surfaces an explicit note:
   - `Synthesizer re-classified finding N from B→A: <rationale>` (upgrade)
   - `Synthesizer re-classified finding N from A→B: <rationale>` (downgrade — commonly fires on straddle-rationale findings where the evidence only supports adjacent concerns)

   (c) **B→A refusal gate** — after re-examination, if zero findings are tagged (or re-classified to) `A`, the synthesizer refuses to emit a verdict-framing A-class `## Objections` narrative ("these block the approach"). B-class findings in the absence of any A-class findings surface in `## Concerns` at most.

   The tag-count gate fires AFTER evidence re-examination, not in place of it. This keeps the refusal rule grounded in evidence even if upstream class tags are noisy (research line 108: refusal is "defensible only if the synthesizer actually re-examines evidence").
   - AC: `grep -c "same class\|within class\|same-class" skills/critical-review/SKILL.md` ≥ 1 in the synthesis prompt.
   - AC: Synthesis prompt contains an explicit refusal instruction: no-A-findings-after-re-examination → no A-class verdict.
   - AC: `grep -cE "re-examine|re-classif|evidence_quote" skills/critical-review/SKILL.md` ≥ 1 in the synthesis prompt block.
   - AC: Synthesizer output includes re-classification notes when they fire (structural check in V2 fixture test — straddle fixture must surface a downgrade note in the `A→B` form on at least 1-of-3 runs when the reviewer tagged via straddle_rationale).

4. **Lifecycle feature resolution and B-class residue file** — Feature name resolution is explicit. The skill resolves `{feature}` via the canonical `LIFECYCLE_SESSION_ID` environment variable (set by the SessionStart hook) paired with a scan of `lifecycle/*/.session` files:

   - **Exactly one matching `.session` file**: that directory's name is `{feature}`; residue write proceeds.
   - **Zero matches** (no active lifecycle): ad-hoc mode. No residue written (see R5).
   - **Multiple matches**: emit operator note `Note: multiple active lifecycle sessions matched $LIFECYCLE_SESSION_ID; B-class residue write skipped.` Do not write to any candidate.
   - **Worktree context**: the scan runs against the current working tree's `lifecycle/` directory, which on a `worktree/agent-*` branch is the worktree's own artifacts — not stale main. No special worktree logic beyond this.
   - **Path-argument invocations** (`/critical-review <path>`): the path does NOT re-bind `{feature}`. The session-bound feature from `.session` always wins. If the user invokes the skill against a file in a different lifecycle's directory, residue still targets the session-bound feature's directory (never the path's directory). Step 1's artifact-discovery logic is unaffected — it reads the path the user gave; feature resolution is independent.
   - **Auto-trigger post-plan** invocations (from `specify.md §3b` / `plan.md`): inherit `LIFECYCLE_SESSION_ID` via the parent process environment. No explicit feature argument is required; the same `.session` scan applies.

   When feature resolution succeeds, B-class findings produced by the parallel reviewers in Step 2c are serialized atomically to `lifecycle/{feature}/critical-review-residue.json` via tempfile + `os.replace()`. Schema:

   ```json
   {
     "ts": "<ISO 8601>",
     "feature": "<lifecycle slug>",
     "artifact": "<path reviewed>",
     "synthesis_status": "ok | failed",
     "reviewers": {"completed": <int>, "dispatched": <int>},
     "findings": [
       {
         "class": "B",
         "finding": "<text>",
         "reviewer_angle": "<angle name>",
         "evidence_quote": "<text>"
       }
     ]
   }
   ```

   `synthesis_status` is `"ok"` when Step 2d completed; `"failed"` when Step 2d errored and the skill fell back to presenting raw per-angle findings (per existing SKILL.md Step 2d synthesis-failure handling). `reviewers` reflects the partial-coverage accounting from Step 2c: `dispatched` is the derived angle count; `completed` is the survivor count. Only B-class findings are written (A is surfaced in the synthesis; C routes to Ask). The file is overwritten on each `/critical-review` run — no history.
   - AC: `grep -c "LIFECYCLE_SESSION_ID\|\\.session" skills/critical-review/SKILL.md` ≥ 2 (env-var reference + `.session` scan reference).
   - AC: After a lifecycle-context run producing ≥1 B-class finding, `test -f lifecycle/{feature}/critical-review-residue.json` exits 0 and the file parses as valid JSON containing required fields `ts`, `feature`, `artifact`, `synthesis_status`, `reviewers`, `findings` (validated by a new unit test).
   - AC: Run produces zero B-class findings → no residue file written: `test ! -f lifecycle/{feature}/critical-review-residue.json` exits 0.
   - AC: Synthesis-failure path writes `synthesis_status: "failed"` to the residue (unit test exercises this path).
   - AC: Multiple-match case surfaces the operator note and writes no residue (unit test).

5. **Ad-hoc /critical-review — no residue, one-line operator note** — When `/critical-review` runs without a lifecycle context (no `lifecycle/{feature}/` directory inferable from conversation), the residue file is NOT written. The skill emits a single line to the operator output: `Note: B-class residue not written — no active lifecycle context.` Only emitted when B-class findings exist; suppressed otherwise.
   - AC: `grep -c "B-class residue not written" skills/critical-review/SKILL.md` ≥ 1.
   - AC: Ad-hoc fixture run producing B-class findings → operator output contains the note, and `find . -name critical-review-residue.json` returns nothing.

6. **Morning report: `render_critical_review_residue` section with degraded-mode annotation** — New function `render_critical_review_residue(data: ReportData) -> str` in `claude/overnight/report.py` reads `lifecycle/*/critical-review-residue.json` files, renders a `## Critical Review Residue (N)` section listing each file's feature, finding count, per-finding one-line summary (`reviewer_angle: finding`), and a degraded-mode annotation line when applicable. Registered in the main `render_sections` list (around line 1340). Rendering follows the existing `render_deferred_questions` pattern (report.py:834–881).

   Degraded-mode annotation fires when the residue file indicates either: (a) `synthesis_status != "ok"`, or (b) `reviewers.completed < reviewers.dispatched`. Rendered as an indented `> ⚠ degraded: synthesis failed` or `> ⚠ degraded: partial reviewer coverage (N of M)` line directly beneath the feature header. Both may apply simultaneously.

   Empty-state semantics: when no residue files exist anywhere under `lifecycle/`, the section header still renders (`## Critical Review Residue (0)`) followed by: `No residue files this cycle. Absence may indicate: zero B-class findings, no lifecycle-context runs, or total reviewer failure (which does not write a residue file).` This literal deliberately does NOT claim "no B-class findings recorded" — that claim is factually wrong in the total-failure case.
   - AC: `grep -c "render_critical_review_residue" claude/overnight/report.py` ≥ 2 (function definition + invocation in `render_sections`).
   - AC: `just test` passes, including tests that exercise: (i) clean `synthesis_status: "ok"` residue rendering, (ii) `synthesis_status: "failed"` annotation, (iii) partial-coverage annotation, (iv) both annotations simultaneously, (v) empty-state literal.
   - AC: Empty-state literal text appears verbatim in the rendered section: `grep -c "no lifecycle-context runs\|total reviewer failure" claude/overnight/report.py` ≥ 1.

7. **Step 4 Apply/Dismiss/Ask: C-class defaults to Ask** — Step 4 logic at `skills/critical-review/SKILL.md` lines 201–226 is updated so C-class (framing) findings default to Ask. A- and B-class findings continue to route through existing Apply/Dismiss/Ask logic (including the existing self-resolution + anchor checks). The Step 4 compact-summary format and Apply-bar direction-verb requirement from ticket 067 must not regress.
   - AC: `grep -c "C-class\|framing.*Ask\|C.*default.*Ask" skills/critical-review/SKILL.md` ≥ 1 in the Step 4 block.
   - AC: `grep -cE '^Dismiss: 0' docs/overnight-operations.md` = 0 (sanity — no documented counter-example where the Dismiss-0 line was re-introduced; the ticket-067 invariant is preserved).
   - AC: Step 4 text retains the six Apply direction verbs (`strengthened`, `narrowed`, `clarified`, `added`, `removed`, `inverted`) verbatim.

8. **Pre-ship classifier validation via V2 synthetic fixtures** — At least two synthetic fixtures are authored and landed at `tests/fixtures/critical-review/`: (a) one pure-B aggregation case that replicates the Kotlin failure pattern (four B findings — each tagged with the specific concern it represents in the fixture metadata — where the synthesizer must not emit an A verdict); (b) one straddle case where a single concern legitimately has both A and B components (reviewer must emit two separate findings: one A finding on a named core defect, one B finding on a named adjacent pattern).

   Fixture authorship is separated from the prompt authorship — either fixtures are written first, before the updated prompts exist, or they are authored by a different subagent/session than the one writing the prompts.

   The pytest test invokes the updated Step 2c + 2d prompts against the fixtures via the `sonnet` model used in production reviewer dispatch. Methodology:

   - **Run count**: 3 runs per fixture at the default reviewer-dispatch temperature.
   - **Fixture (a) pass criterion**: 3-of-3 runs emit zero A-class findings AND the synthesis narrative does not frame the concerns as verdict-blocking. Asserts: `synthesis.count('class: A') == 0` and `synthesis.count('blocks') + synthesis.count('invalidates') == 0` across all three runs.
   - **Fixture (b) pass criterion**: 3-of-3 runs emit exactly one A-class finding whose text matches the named core defect identifier (fixture metadata supplies expected substring) AND exactly one B-class finding whose text matches the named adjacent-pattern identifier. A test that only asserts "emits both classes" is insufficient — the test asserts which concern got which class.
   - **Stochastic-variance accounting**: if 2-of-3 runs pass the above criteria, the test fails with a warning surface noting the inconsistency. Only 3-of-3 is a pass.
   - AC: `ls tests/fixtures/critical-review/*.{md,json} 2>/dev/null | wc -l` ≥ 2.
   - AC: `just test -k critical_review_classifier` exits 0.
   - AC: Test file asserts the "3-of-3 runs" and "named-concern-to-class" properties (grep the test for those assertion patterns).
   - AC: Git log shows fixture commits precede the Step 2c/2d prompt-update commits, OR the fixture-authorship commit is authored by a different dispatched subagent (captured in its Task-tool prompt).

## Non-Requirements

- **Step 2c fallback prompt is NOT updated.** The total-failure fallback at `skills/critical-review/SKILL.md` lines 113–142 retains its existing `## Objections / ## Through-lines / ## Tensions / ## Concerns` output shape without class tagging. Rationale: fallback is a degraded path; taxonomy maintenance there doubles the surface area for the same n=1 failure mode that the primary path addresses.
- **No V1 Kotlin-session retest.** User has confirmed the Kotlin session logs are not required as validation input.
- **No V3 held-out pilot on live `/critical-review` runs.** Validation is V2-only.
- **No opt-in flag, env var, or feature gate.** Direct merge as the new default.
- **No binary-blocking + orthogonal type axis.** Ternary A/B/C is the committed taxonomy.
- **No de-dup logic for duplicate B-class findings across reviewers.** Each reviewer's B-class findings are recorded independently in the residue file.
- **No dashboard card for residue files.** Morning-report surfacing is the only consumer added in this ticket.
- **`skills/lifecycle/references/clarify-critic.md` is NOT updated.** Taxonomy fix stays scoped to `/critical-review`. A follow-up backlog item may extend to `clarify-critic` once V2 fixtures validate.
- **H2 (no pattern anchor) and FP5 (pattern-anchor epic) remain deferred** per epic DR-6.
- **`skills/output-floors.md` applicability block is not revisited** in this ticket (backlog 086 follow-up).
- **Spec 067 R8 (zero events.log references in `critical-review/SKILL.md`) is preserved.** The sidecar JSON choice intentionally avoids the events.log channel so the R8 invariant is NOT rewritten.

## Edge Cases

- **Zero B-class findings**: No residue file written. Morning-report per-feature list omits the feature; empty-state literal (per R6) is emitted only when the `lifecycle/*/critical-review-residue.json` glob matches zero files across ALL features.
- **Ad-hoc run (no active lifecycle session)**: `.session` scan matches zero files → residue skipped. Operator note emitted once if B-class findings exist (R5).
- **Multiple active lifecycle sessions match `$LIFECYCLE_SESSION_ID`**: `.session` scan matches ≥2 files → abort residue write, emit operator note `Note: multiple active lifecycle sessions matched; B-class residue write skipped.` (R4 resolution rules).
- **Path-argument points into a non-session feature**: `/critical-review lifecycle/other-feature/spec.md` invoked from a session bound to `my-feature`. Step 1 reads the artifact at the given path; feature resolution still uses the session binding → residue targets `lifecycle/my-feature/critical-review-residue.json`, not `lifecycle/other-feature/`. The `artifact` field in the residue schema records the path actually reviewed.
- **Worktree session with stale main artifacts**: `/critical-review` on branch `worktree/agent-X` scans the worktree's local `lifecycle/*/.session` files (not main's). The worktree's `.session` is the authoritative binding for this invocation — no special-case worktree logic is required in /critical-review itself.
- **Partial reviewer failure (Step 2c partial)**: Surviving reviewers class-tag. Synthesizer applies evidence-based B→A refusal (R3) using only surviving findings. Residue written with `reviewers.completed < reviewers.dispatched` — morning report renders degraded annotation per R6.
- **Total reviewer failure (Step 2c total → fallback)**: Fallback path emits the untagged Objections/Through-lines/Tensions/Concerns shape. No class tags, no residue file. Morning-report empty-state literal acknowledges this possibility explicitly (per R6).
- **Synthesis agent failure (Step 2d)**: Raw per-angle findings from Step 2c are presented directly to the user. Residue IS written, with `synthesis_status: "failed"` — morning report renders degraded annotation per R6. The R3 refusal check did not run; the degraded flag is the operator's signal not to treat the residue as synthesis-vetted.
- **Multiple `/critical-review` runs on the same feature**: Each run overwrites `lifecycle/{feature}/critical-review-residue.json` atomically. No history. Morning-report reflects the most recent run only. When a clean run is followed by a degraded run, the `synthesis_status` / `reviewers` fields reflect the degraded run; when a total-failure run follows a clean run, the clean residue **persists** because total-failure writes nothing — documented trade-off per overwrite-atomicity limits.
- **Malformed residue JSON**: `render_critical_review_residue` catches `json.JSONDecodeError` and emits a single line (`Feature X: residue file malformed, skipped.`) consistent with observability.md line 37's graceful-degradation requirement.
- **Missing required schema fields**: `render_critical_review_residue` tolerates legacy/truncated files missing `synthesis_status` or `reviewers`: degraded annotation defaults to "unknown" for missing fields but rendering does not raise.
- **Concurrent `/critical-review` runs on the same feature**: Not prevented; atomic `os.replace()` ensures file state is either the previous run's content or the new run's content, never partial. Last-write-wins is acceptable given overwrite semantic.
- **Lifecycle directory exists but is gitignored**: Residue file writes still succeed (gitignore affects git's view, not filesystem writes). Morning-report reads the file directly from disk.

## Changes to Existing Behavior

- MODIFIED: `skills/critical-review/SKILL.md` Step 2c reviewer prompt → adds taxonomy block, worked examples per class, straddle-split + bias-up-to-A protocol, and a trailing JSON envelope (enum-constrained class field) delimited by `<!--findings-json-->`. Prose findings shape is preserved for Step 3 presentation.
- MODIFIED: `skills/critical-review/SKILL.md` Step 2d synthesis prompt → consumes concatenated JSON envelopes from reviewers; through-line aggregation scoped to same-class cohorts; evidence-based re-examination before tag-count refusal; explicit re-classification notes when synthesizer overrides a reviewer tag.
- MODIFIED: `skills/critical-review/SKILL.md` Step 4 Apply/Dismiss/Ask → C-class findings default to Ask (existing self-resolution + anchor checks preserved).
- MODIFIED: `skills/critical-review/SKILL.md` Step 1 (implicitly via R4) — feature resolution now uses `LIFECYCLE_SESSION_ID` + `.session` scan. Step 1's artifact-discovery behavior is unchanged; feature resolution is a new parallel responsibility.
- ADDED: Orchestrator-side JSON envelope extraction + validation logic in `skills/critical-review/SKILL.md` (raises on malformed JSON, non-enum class values, prose/JSON finding-count mismatch).
- ADDED: `lifecycle/{feature}/critical-review-residue.json` sidecar artifact (new runtime file type; schema documented in SKILL.md with `synthesis_status` and `reviewers` degraded-mode fields).
- ADDED: `render_critical_review_residue` function in `claude/overnight/report.py` with degraded-mode annotation; registered in the main `render_sections` list.
- ADDED: `tests/fixtures/critical-review/` directory containing at minimum a pure-B aggregation fixture and a straddle fixture; each fixture supplies metadata naming the expected class-per-concern for assertion purposes.
- ADDED: New pytest tests covering (a) `render_critical_review_residue` rendering including degraded-mode paths, (b) classifier behavior across 3 runs per V2 fixture with named-concern-to-class assertions, (c) orchestrator-side JSON extraction failure modes.

## Technical Constraints

- **Atomic writes** for `critical-review-residue.json`: tempfile + `os.replace()` (convention: `requirements/pipeline.md` line 121).
- **Gated write**: Residue file is written only when `lifecycle/{feature}/` is resolvable from the current context. Ad-hoc invocation paths must not write.
- **Graceful degradation in morning report**: Missing, unreadable, or malformed residue JSON files are skipped with a single-line notice, not an exception (`requirements/observability.md` line 37).
- **Preserve load-bearing /critical-review prompt patterns** (from research's "Conventions to follow"):
  - `"Do not soften or editorialize"` (Step 3 line 195) — backlog 053/082/085.
  - Distinct-angle rule in Step 2b — backlog 053.
  - Step 4 Dismiss line N=0 omission — backlog 067.
  - Apply-bar direction verb list — backlog 067.
  - Zero `events.log` references in `critical-review/SKILL.md` — spec 067 R8.
- **Interactive reviewer dispatch** remains on `sonnet` (backlog 046). Ticket 132 is `complex+medium` and is NOT governed by the overnight model-selection matrix (`requirements/multi-agent.md` lines 51–62).
- **Context efficiency**: Reviewer prompt token delta from taxonomy + worked examples must be measured during Plan-phase scaffolding; no hard budget is declared here, but Plan must report the delta and flag if it exceeds the existing Step 2c block by more than 2× line count.
- **Reviewer model output contract**: Reviewer agents return the existing prose findings (for Step 3 human-facing presentation) followed by a JSON envelope (for orchestrator R3 counting and R4 residue writes). The envelope is delimited by `<!--findings-json-->` on its own line. Class tag is an enum-constrained field (`"A" | "B" | "C"`) on each finding object, per research line 119's structured-output recommendation. The orchestrator-side extraction layer raises on malformed JSON, non-enum class values, or mismatched prose/JSON finding counts. This deviates from the pure-prose pattern in `clarify-critic.md` by adding a structured tail; the prose surface is preserved so Step 3 presentation is unchanged for the operator.

## Open Decisions

None. All design questions raised in research have been resolved in the interview above.
