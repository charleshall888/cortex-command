# Plan: rewrite-cortex-pr-review-from-fan

## Overview
Replace the five-stage fan-out in `plugins/cortex-pr-review/skills/pr-review/` with a thin single-reviewer skill: rewrite the four reference files to a single-pass contract, delete `evidence-ground.sh` (and its untracked output cache), de-pin the model, add a deterministic verdict-derivation unit (the fail-loud state machine) with a contract test, and align the shell + manifests. The hand-maintained plugin is edited in place (no mirror).
**Architectural Pattern**: layered — a thin policy/shell layer (SKILL.md + references) over a single reviewer-agent dispatch and a small deterministic verdict unit; no fan-out, no inter-stage message bus.

## Verdict-Helper Contract (authoritative — referenced by Tasks 3, 4, 7)
To prevent the helper, its caller, and its test from drifting, the contract is pinned here once:
- **Signature**: `derive_verdict(findings: list[dict], runtime_signals: set[str]) -> str`.
- **Finding dict keys** (the schema, owned by `output-format.md` Task 1): `severity` ∈ `{"blocking","non-blocking"}`, `grounding` ∈ `{"grounded","evidence-weak"}` (plus `label`, `file:line`, `body` for output — not read by the verdict logic).
- **Signal ownership (NOT implementer's choice)**: the helper **derives** signals 5 (`surfaced_none_grounded`) and 6 (`evidence_weak_blocking`) internally from `findings`. The caller passes ONLY the four runtime signals it detects: `runtime_signals ⊆ {"reviewer_error","diff_missing","grounding_incomplete","metadata_fetch_failed"}`. These four names are defined as a module-level constant (e.g. `RUNTIME_SIGNALS`) in `derive_verdict.py` — the single authoritative source; the test imports the constant rather than re-typing strings, and the protocol references it.
- **Verdict logic** (top-to-bottom): (1) any `grounded` finding with `severity=="blocking"` → `REQUEST_CHANGES`; (2) else if `runtime_signals` is non-empty OR `surfaced_none_grounded(findings)` (≥1 surfaced finding, zero `grounded`) OR `evidence_weak_blocking(findings)` (any `evidence-weak` finding with `severity=="blocking"`) → `REVIEW_INCONCLUSIVE`; (3) else → `APPROVE`.
- **CLI shape** (`__main__`): reads one JSON object from stdin with exactly `{"findings": [...], "runtime_signals": [...]}`, prints the verdict string to stdout. This is the exact shape `protocol.md`'s invocation writes.

## Outline

### Phase 1: Rewrite the review contract (tasks: 1, 2, 3, 4, 8)
**Goal**: Replace the five-stage pipeline, three-axis rubric, and external grounder with a single-pass reviewer flow, a unified severity contract, in-context grounding, and the deterministic fail-loud verdict; remove stale run artifacts.
**Checkpoint**: `protocol.md` is single-pass (no stage structure, no `claude-opus-4-7`, ≤200 lines), documents the verdict set, and INVOKES `derive_verdict.py`; `evidence-ground.sh` and `.cache/` are gone/ignored; `output-format.md` + `rubric.md` express one severity contract with positive structure present; the verdict unit exists with the pinned contract.

### Phase 2: Align the shell and lock the contract (tasks: 5, 6, 7)
**Goal**: Align SKILL.md + manifests with the single-reviewer shape (no residual fan-out vocabulary) and lock the verdict/grounding contract with a runnable test.
**Checkpoint**: SKILL.md + both manifests carry no fan-out/pipeline vocabulary; `just test` exits 0 with the new contract test asserting the five verdict cases, signal-5/6 derivation, and the stdin path.

## Tasks

### Task 1: Rewrite `output-format.md` — canonical contract + finding schema + footer
- **Files**: `plugins/cortex-pr-review/skills/pr-review/references/output-format.md`
- **What**: Make this the single source of truth for: (1) the canonical Label / Decoration / Severity / Verdict-effect table; (2) the finding schema (`severity`, `grounding`, `file:line`, `label`, `body`) per the Verdict-Helper Contract; (3) terminal-first output with a GitHub-markdown posting branch; (4) blocking-first sort; (5) the footer fields (`model`, `findings_surfaced` split grounded/evidence-weak, `findings_dropped` with reasons). Implements spec Req 6, 8, 9.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Current file is 78 lines. Use the spec `## Grounding & Verdict Vocabulary` verbatim. One blocking label form only (`issue (blocking):`); decoration rendered from `severity`. Conventional Comments decorations `(blocking)`/`(non-blocking)`/`(if-minor)`. Do not put a model id in the footer example (de-pin — Req 4).
- **Verification**: ALL must hold — (a) the canonical table is present: `grep -cE '^\|.*[Ss]everity.*\|' …/output-format.md` ≥ 1 AND the table names both `blocking` and `non-blocking`; (b) schema fields present: `grep -c 'grounding' …/output-format.md` ≥ 1 AND `grep -c 'file:line' …/output-format.md` ≥ 1 AND `grep -c 'evidence-weak' …/output-format.md` ≥ 1; (c) footer fields present: `grep -c 'findings_surfaced' …/output-format.md` ≥ 1 AND `grep -c 'findings_dropped' …/output-format.md` ≥ 1; (d) `grep -c 'suggestion (blocking)' …/output-format.md` = 0; (e) `grep -c 'claude-opus-4-7' …/output-format.md` = 0; (f) `<details>` appears only after the posting-mode heading.
- **Status**: [x] complete

### Task 2: Rewrite `rubric.md` — single severity + grounding gate
- **Files**: `plugins/cortex-pr-review/skills/pr-review/references/rubric.md`
- **What**: Collapse the three-axis rubric to one verdict-driving severity (`blocking` vs not) + a hard grounding gate (subsumes solidness); drop the signal axis, per-label caps, alphabetical tie-break, and `suggestion (blocking)`. Reference (do not duplicate) the canonical table in `output-format.md`. Implements spec Req 8.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Current file 117 lines (axes :9-37, caps :52-56, tie-break :58, unrun α-protocol). Remove the stability-protocol section.
- **Verification**: positive AND subtractive — (a) `grep -ci 'blocking' …/rubric.md` ≥ 1 AND `grep -ci 'grounding' …/rubric.md` ≥ 1 AND `grep -c 'output-format' …/rubric.md` ≥ 1 (references the canonical table); (b) `grep -c 'suggestion (blocking)' …/rubric.md` = 0 AND `grep -ci 'alphabetical' …/rubric.md` = 0 AND `grep -cEi '(nitpick|praise|cross-cutting)[^:]*(≤|<=|max|cap )' …/rubric.md` = 0 — pass if all hold.
- **Status**: [x] complete

### Task 3: Create the verdict-derivation unit (deterministic fail-loud state machine)
- **Files**: `plugins/cortex-pr-review/skills/pr-review/scripts/derive_verdict.py`
- **What**: Implement the Verdict-Helper Contract (above) exactly: the `derive_verdict(findings, runtime_signals)` function, the `RUNTIME_SIGNALS` module constant (the four runtime signal-name strings, authoritative), internal derivation of signals 5/6 from `findings`, and a `__main__` that reads the pinned stdin JSON and prints the verdict. stdlib only; no `cortex_command` import. Implements spec Req 7.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Plugin-local (not `bin/cortex-*`, so no parity wiring). Signature, key names, signal ownership, verdict logic, and CLI shape are all pinned in the Verdict-Helper Contract section — do not re-derive them. Signals 5/6 are derived internally (the caller never passes them); only the four `RUNTIME_SIGNALS` are accepted from the caller.
- **Verification**: (a) `echo '{"findings":[{"severity":"blocking","grounding":"grounded","label":"issue (blocking)","file:line":"x.py:1","body":"b"}],"runtime_signals":[]}' | python3 …/derive_verdict.py` prints `REQUEST_CHANGES`; (b) `echo '{"findings":[{"severity":"non-blocking","grounding":"evidence-weak","label":"issue","file:line":"x.py:1","body":"b"}],"runtime_signals":[]}' | python3 …/derive_verdict.py` prints `REVIEW_INCONCLUSIVE` (signal 5 derived internally, no signal passed) — pass if both stdout match exactly. (Full matrix is Task 7.)
- **Status**: [x] complete

### Task 4: Rewrite `protocol.md` to single-pass; document the verdict; invoke the helper; delete `evidence-ground.sh`; de-pin
- **Files**: `plugins/cortex-pr-review/skills/pr-review/references/protocol.md`, `plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh`
- **What**: Replace the 821-line five-stage protocol with a single-pass description: one full-context reviewer dispatch (diff + touched/related files + CLAUDE.md if present) emitting the finding schema; in-context grounding criterion (confirm each quote on `+` side, cite `file:line`; else mark `evidence-weak` and surface, never drop); model = session-default/highest-available (remove every `claude-opus-4-7`); **document the verdict set + derivation + the four runtime signals** (so `REVIEW_INCONCLUSIVE` and the signal names appear here — the reviewer-flow contract), and detect the four `RUNTIME_SIGNALS` at runtime and pass them, with the emitted findings, to `derive_verdict.py` via the pinned stdin JSON to compute the verdict. Reference `output-format.md` for the label↔severity TABLE (don't restate the table). Delete `evidence-ground.sh`. Implements spec Req 1, 2, 3, 4; wires Req 6/7.
- **Depends on**: [1, 3]
- **Complexity**: complex
- **Context**: Current `protocol.md` 821 lines; pins at :562/:572/:582/:727; fail-open at :548-557/:768-792. Prescribe What/Why, not method (CLAUDE.md). Resolve `${CLAUDE_SKILL_DIR}` only in SKILL.md (Task 5) and propagate the absolute `derive_verdict.py` path into the flow — no bare `${CLAUDE_SKILL_DIR}` / bare-relative path here (ADR-0009/SP002). Keep removal/migration narration OUT of the operative section so the structural greps read clean.
- **Verification**: ALL must hold — (a) single-pass + no pin: `grep -ciE '(^|[^a-z])(stage|step|pass|phase) [0-9]' …/protocol.md` = 0 AND `grep -c 'claude-opus-4-7' …/protocol.md` = 0; (b) verdict documented: `grep -c 'REVIEW_INCONCLUSIVE' …/protocol.md` ≥ 1; (c) helper invoked (not orphaned): `grep -c 'derive_verdict' …/protocol.md` ≥ 1; (d) single-reviewer + grounding present: `grep -ciE 'single|one (full-context )?review' …/protocol.md` ≥ 1 AND `grep -c 'evidence-weak' …/protocol.md` ≥ 1; (e) script gone: `test ! -e …/scripts/evidence-ground.sh`; (f) bounded: `[ $(wc -l < …/protocol.md) -le 200 ]`.
- **Status**: [x] complete

### Task 5: Update `SKILL.md` — shell, frontmatter, no-autopost, notes, path propagation
- **Files**: `plugins/cortex-pr-review/skills/pr-review/SKILL.md`
- **What**: Update frontmatter `description` (drop pipeline framing); update Stage-0 preconditions to the single-reviewer flow (drop `jq`/cache-dir; keep `python3` for `derive_verdict.py`); describe the single-reviewer flow (remove ALL residual fan-out vocabulary — Haiku/triage/pipeline/subagent/synthesized verdict from the body, not just the frontmatter); keep no-autopost-by-default (posting requires explicit flag/request); add the two-vocabulary distinctness note (`/pr-review` verdicts vs overnight `review_dispatch`); correct any "canonical-plus-mirror dual-source" text (hand-maintained, in place); resolve `${CLAUDE_SKILL_DIR}` in the body and propagate absolute paths (reviewer prompt, `derive_verdict.py`) per ADR-0009; remove any residual `evidence-ground.sh` reference. Implements spec Req 1, 5, 9 (no-autopost).
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: Current SKILL.md 76 lines; no-autopost at :73-74; `disable-model-invocation: true` (preserve); `${CLAUDE_SKILL_DIR}` propagation at :46-69. The body currently uses fan-out vocabulary 7× (Haiku/triage/pipeline/subagent). Size cap 500 lines (covered by `tests/test_skill_size_budget.py`).
- **Verification**: ALL must hold — (a) no fan-out vocabulary: `grep -ciE 'multi-agent|haiku|triage|fan-out|pipeline|synthesiz|each subagent|four (parallel )?critic' …/SKILL.md` = 0; (b) distinctness note: `grep -c 'review_dispatch' …/SKILL.md` ≥ 1; (c) no grounder reference: `grep -c 'evidence-ground' …/SKILL.md` = 0; (d) `[ $(wc -l < …/SKILL.md) -le 500 ]`.
- **Status**: [x] complete

### Task 6: Update plugin + marketplace manifests
- **Files**: `plugins/cortex-pr-review/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- **What**: Update BOTH `description` strings to the single-reviewer shape (drop "Multi-agent … pipeline"). Keep `plugin.json` `.name` non-empty (drift-hook classification guard). Implements spec Req 5 (manifest portion).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `plugin.json:3` and `marketplace.json:40` carry the identical stale description. Both valid JSON — preserve validity. Plugin stays `HAND_MAINTAINED` (justfile:576); do NOT run `build-plugin`.
- **Verification**: ALL must hold — (a) `grep -ciE 'multi-agent|pipeline' plugins/cortex-pr-review/.claude-plugin/plugin.json` = 0 AND `grep -ciE 'multi-agent|pipeline' .claude-plugin/marketplace.json` = 0 (BOTH files grepped); (b) JSON valid: `python3 -c "import json; json.load(open('plugins/cortex-pr-review/.claude-plugin/plugin.json'))"` exits 0 AND `python3 -c "import json; json.load(open('.claude-plugin/marketplace.json'))"` exits 0.
- **Status**: [x] complete

### Task 7: Create the contract test — verdict state machine + grounding + stdin path
- **Files**: `tests/test_pr_review_verdict.py`
- **What**: Import `derive_verdict.py` and its `RUNTIME_SIGNALS` constant from the plugin path (do NOT re-type signal-name strings) and assert: the five verdict cases (spec Req 10) — (1) grounded blocking → `REQUEST_CHANGES`; (2) all-evidence-weak (no runtime signal passed; signal 5 derived) → `REVIEW_INCONCLUSIVE`; (3) evidence-weak blocking (no runtime signal passed; signal 6 derived) → `REVIEW_INCONCLUSIVE`; (4) zero findings + a member of `RUNTIME_SIGNALS` → `REVIEW_INCONCLUSIVE`; (5) all-grounded non-blocking, empty `runtime_signals` → `APPROVE`. PLUS: (6) signals 5/6 are derived internally (cases 2/3 pass `runtime_signals=set()`); (7) the `__main__` stdin path (invoke via `python3` with the pinned `{"findings":..,"runtime_signals":..}` JSON, assert stdout). Implements spec Req 10.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Load the module via `importlib.util.spec_from_file_location` against `plugins/cortex-pr-review/skills/pr-review/scripts/derive_verdict.py`; for the stdin path use `subprocess.run([sys.executable, <path>], input=<json>, …)`. Follow existing `tests/` pytest conventions. Importing `RUNTIME_SIGNALS` (rather than hard-coding strings) is what prevents helper/test signal-name drift.
- **Verification**: `uv run pytest tests/test_pr_review_verdict.py` exits 0 with all seven assertions (five verdict cases + signal-5/6-derivation + stdin path) passing — pass if exit code = 0. (Verifies Task-3 behavior, not mere file existence.)
- **Status**: [x] complete

### Task 8: Remove stale run artifacts; gitignore `.cache/`
- **Files**: `plugins/cortex-pr-review/skills/pr-review/.cache/` (delete), `.gitignore`
- **What**: Delete the untracked `.cache/` dir (holds `critics.json` from the fan-out and `grounded.json` from the grounder — the very outputs this rewrite removes) and add `plugins/cortex-pr-review/skills/pr-review/.cache/` to the repo-root `.gitignore` so neither these nor future run caches are ever committed. Closes the "clean net deletion" gap the critical-review found.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `.cache/` is currently untracked (`git status` `??`) and NOT gitignored (`git check-ignore` confirms). Only `__pycache__/` is ignored today. Removing the dir is safe (run artifacts, regenerated on demand).
- **Verification**: `test ! -e plugins/cortex-pr-review/skills/pr-review/.cache/` AND `git check-ignore plugins/cortex-pr-review/skills/pr-review/.cache/x` exits 0 (the path is now ignored) — pass if both hold.
- **Status**: [x] complete

## Risks
- **The verdict helper is new runtime machinery in a "thin shell" rewrite.** Justified by spec Req 7/10 (structural-over-prose enforcement of the safety-critical gate) and far smaller than the deleted 553-line `evidence-ground.sh`. The signal-ownership/name/stdin contract is pinned in the Verdict-Helper Contract section to prevent Task 3/4/7 drift.
- **`evidence-ground.sh` deletion vs `tests/test_check_skill_path.py:207`.** That test references the script's invocation string as lint-fixture TEXT, not a file-existence dependency — deletion should not break it. Task 7's `just test` would surface any regression.
- **In-context grounding self-grading risk** (spec accepted-risk): the `file:line` citation + contract test are the in-scope mitigations; the natural-bug fixture is the deferred tripwire.
- **Doc-behavior is not unit-tested.** The reviewer's judgment, the in-context grounding behavior, and footer population are LLM-runtime behaviors gated by structural greps (now with positive checks) + the Task-7 verdict-helper test, not behavioral fixtures — an accepted limit of a prose-driven skill; the verdict gate (the safety-critical part) IS behaviorally tested.
- **Cross-PR lookup deferred** (operator-approved at spec): the first cut ships no cross-PR capability.

## Acceptance
Running `/pr-review <PR>` in the terminal performs one full-context reviewer pass that grounds each finding in-context with a `file:line` citation, surfaces ungroundable findings as `evidence-weak` (never silently dropped), and emits a deterministic verdict (`APPROVE`/`REQUEST_CHANGES`/`REVIEW_INCONCLUSIVE`) computed by `derive_verdict.py` and invoked from `protocol.md` — never a silent approve on degradation. The plugin contains no five-stage pipeline, no `evidence-ground.sh`, no `.cache/` run artifacts, and no `claude-opus-4-7` pin; SKILL.md and both manifests carry no fan-out vocabulary; `just test` passes including the new `tests/test_pr_review_verdict.py` asserting the five verdict cases, signal-5/6 derivation, and the stdin path; default output is terminal plain-text with the observability footer reporting the model that ran and the grounded/evidence-weak split.
