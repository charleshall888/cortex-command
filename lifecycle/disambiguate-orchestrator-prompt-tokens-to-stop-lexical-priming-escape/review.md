# Review: disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape

## Stage 1: Spec Compliance

### Requirement 1: Rename session-level `{plan_path}` → `{session_plan_path}` in orchestrator-round.md
- **Expected**: `grep -c '{plan_path}' claude/overnight/prompts/orchestrator-round.md` returns 0; session occurrences at lines 14, 110, 216 become `{session_plan_path}`.
- **Actual**: `grep -c '{plan_path}' …` → 0. `grep -n '{session_plan_path}' …` shows matches at lines 14, 110, 216 (plus a mention inside the substitution_contract block at 263, which is expected).
- **Verdict**: PASS
- **Notes**: Three session-level rename sites match spec line numbers exactly.

### Requirement 2: Update `fill_prompt()` in runner.sh to substitute `{session_plan_path}`
- **Expected**: `grep -n "'{session_plan_path}'" claude/overnight/runner.sh` returns ≥1; `grep -n "'{plan_path}'" claude/overnight/runner.sh` returns 0; `$PLAN_PATH` env var preserved.
- **Actual**: runner.sh:387 reads `t = t.replace('{session_plan_path}', os.environ['PLAN_PATH'])`. `'{plan_path}'` grep returns 0. Env-var name `PLAN_PATH` preserved.
- **Verdict**: PASS
- **Notes**: Only the template-facing token string changed; env-var name preserved per spec.

### Requirement 3: Convert per-feature tokens in Step 3b dispatch block to `{{feature_X}}` double-brace syntax
- **Expected**: `grep -cE '\{\{feature_(slug|spec_path|plan_path)\}\}' …` ≥ 3; zero `{slug}` or `{spec_path}` single-brace inside the dispatch block.
- **Actual**: count = 7 (well above threshold). `grep -nE '\{slug\}|\{spec_path\}|\{feature\}'` filtered to lines 260-285 → no matches inside the dispatch block.
- **Verdict**: PASS
- **Notes**: Every per-feature token in the dispatch block uses the double-brace form.

### Requirement 4: Replace per-feature plan-path reference with `{{feature_plan_path}}`
- **Expected**: Dispatch template sentence reads `write a complete plan to {{feature_plan_path}}`; post-change `grep -c '{plan_path}' …` = 0 and `grep -c '{{feature_plan_path}}' …` ≥ 1.
- **Actual**: Line 275: `write a complete plan to {{feature_plan_path}} using the standard plan.md format…`. Both grep counts satisfy the bounds.
- **Verdict**: PASS

### Requirement 5: Collapse `{feature}` → `{{feature_slug}}` on line 261
- **Expected**: Dispatch-template sentence on line 267 (post-insertion) reads `…overnight feature "{{feature_slug}}"`. `{feature}` occurrences inside Step 0 Python examples remain unchanged.
- **Actual**: Line 267: `You are generating an implementation plan for the overnight feature "{{feature_slug}}".`. `{feature}` remains only at lines 89, 102, 108, 109, 115, 136, 148 (all inside Step 0 Python-dict-access expressions, as the spec intends). None inside the dispatch block (260-285).
- **Verdict**: PASS

### Requirement 6: Add `<substitution_contract>` XML-tagged instruction block before the dispatch template
- (6a) **Open/close tag counts**: `grep -c '<substitution_contract>'` = 1; `grep -c '</substitution_contract>'` = 1. **PASS**.
- (6b) **Block location**: "Each sub-agent receives:" at line 258; `<substitution_contract>` opens at line 260; `</substitution_contract>` closes at line 264; the dispatch code fence opens at line 266. Block sits strictly between the narrative sentinel and the fenced template. **PASS**.
- (6c) **Content tokens + state.features reference**: Block (lines 260-264) contains the literal strings `{{feature_slug}}`, `{{feature_spec_path}}`, `{{feature_plan_path}}`, and `state.features[<slug>]`. `grep -c 'state.features'` repo-wide returns 3 with at least two inside the block line range. **PASS**.
- (6d) **Imperative prohibition language**: Block contains `MUST NOT` (on line 263: "YOU MUST NOT re-substitute them…") and `YOU MUST substitute` (line 261: "CRITICAL: YOU MUST substitute the per-feature tokens…"). Both phrasings are directly addressed to the agent, not passive. The block also warns explicitly not to "copy the absolute-path pattern from earlier in this prompt when filling in per-feature double-brace tokens." **PASS**.
- (6e) **Pre-filled framing**: Block states session-level tokens `{session_plan_path}, {state_path}, {events_path}, {session_dir}` are "already pre-filled by fill_prompt() before you receive this prompt" — satisfies the `pre-filled by fill_prompt` phrase check. **PASS**.
- (6f) **Salience marker on first inner line**: First line after `<substitution_contract>` begins `CRITICAL: YOU MUST substitute…`. Both `CRITICAL:` and `YOU MUST:`-ish openers are present. **PASS**.
- **Verdict**: PASS
- **Notes**: All six sub-checks satisfied. The block is high-salience, imperative, and correctly positioned between narrative and fenced template.

### Requirement 7: Add unit test `tests/test_fill_prompt.py`
- (7a) **Invokes real `fill_prompt()` from runner.sh, not a Python copy**: The test's `_extract_fill_prompt` helper scans `runner.sh` for the `fill_prompt() {` start and the next `}` on its own line, extracts the verbatim shell-function body, and sources that body into `bash -c`. The spec's literal wording ("source claude/overnight/runner.sh; fill_prompt 1") is unworkable because top-level runner.sh initialization (arg parsing, state-JSON reads at lines 218/229) runs on source. The extraction approach preserves R7a's stated *intent* ("exercise the same code path that runs at session time" and "not a Python copy of the substitution logic") — the test exercises the identical shell bytes from the real file, not a Python reimplementation. The implementer's deviation note was clear about this. **PARTIAL** (literal wording deviation; intent fully satisfied).
- (7b) **Realistic stubbed env vars**: Test sets `PLAN_PATH=/tmp/overnight-2026-04-21-stub/overnight-plan.md`, `STATE_PATH=.../overnight-state.json`, `SESSION_DIR=/tmp/overnight-2026-04-21-stub`, `EVENTS_PATH=.../overnight-events.log`, `TIER=simple`; `fill_prompt 1` supplies ROUND_NUM=1. All session-shape paths present. Additionally sets `PROMPT_TEMPLATE` (required by the extracted body's `TEMPLATE="$PROMPT_TEMPLATE"` command-line variable assignment) and redundantly `TEMPLATE`. **PASS** (R7b contents satisfied; `TEMPLATE`/`PROMPT_TEMPLATE` duality noted in implementer deviation #2 and is benign).
- (7c) **No `{session_plan_path}` or `{plan_path}` in output**: `test_fill_prompt_substitutes_session_plan_path` asserts both literal absences. **PASS**.
- (7d) **≥3 occurrences of stub PLAN_PATH value**: `test_fill_prompt_substitutes_plan_path_value` asserts `out.count(plan_path_value) >= 3`. Satisfies the spec's three-site check (lines 14, 110, 216). **PASS**.
- (7e) **≥1 occurrence of `{{feature_slug}}`**: `test_fill_prompt_preserves_per_feature_double_brace` asserts presence. **PASS**.
- (7f) **≥1 occurrence of `<substitution_contract>`**: `test_fill_prompt_contains_substitution_contract` asserts presence. **PASS**.
- (7g) **Full test suite exits 0 with new test included**: `.venv/bin/pytest tests/test_fill_prompt.py -v` → `5 passed in 0.36s`. Implementer reports `just test` exited 0 pre-commit. **PASS**.
- Bonus (7h, negative assertions): `test_fill_prompt_no_single_brace_per_feature_tokens` asserts no `{slug}`, `{spec_path}`, or quoted `"{feature}"` leaks through — defends against partial renames.
- **Verdict**: PASS
- **Notes**: R7a's literal `source runner.sh` is unworkable (the script has exit-on-source initialization); the implementer's function-extraction sources the real shell-function body from the real file. This is a sound engineering interpretation — the test exercises the same shell code that runs at session time, Python-copy is not substituted. Treating this as compliant with R7a's intent. Test passed locally.

### Requirement 8: Deploy atomicity (single commit + no-active-runner check)
- (8a) **Single commit touches both files**: `git show 516cf95 --stat` shows 3 files (orchestrator-round.md, runner.sh, test_fill_prompt.py) in one commit. The prompt + shell edits are in the same commit. **PASS**.
- (8b) **No active runner pre-merge**: `~/.local/share/overnight-sessions/active-session.json` shows `"phase": "complete"` for session `overnight-2026-04-21-1708`. No `pid` field is present (the implementer reports it was null/absent), so `ps -p $(jq -r .pid …)` gracefully resolves to "no live process" (jq → null, ps → exit 127). No active overnight runner at commit time. **PASS**.
- (8c) **Residual risk documented**: Not code-enforceable; the spec explicitly documents that operator discipline is the only mitigation against a mid-session `git pull` skew. No implementation artifact required. **PASS**.
- **Verdict**: PASS

## Requirements Drift
**State**: detected
**Findings**:
- The `<substitution_contract>` XML-block convention and the `{{double_brace}}` per-feature-token syntax, combined with single-brace session-level tokens pre-filled by `fill_prompt()`, codify a *two-tier substitution contract* that is new multi-agent/pipeline behavior. This dual-layer prompt shape is orchestrator-specific today (single-layer prompts like `batch-brain.md`/`repair-agent.md` remain single-brace per the spec's Technical Constraints), but the convention is load-bearing for the dispatch contract and is not documented in any requirements file.
- The R8b pre-merge no-active-runner discipline (`~/.local/share/overnight-sessions/active-session.json` consultation before merging prompt/runner edits) is new operator discipline with no automated enforcement. It is not recorded in `requirements/pipeline.md` or `requirements/multi-agent.md`.
- `requirements/pipeline.md` documents the orchestrator's rationale convention at line 127 as an orchestrator-prompt convention; the substitution-contract addition is analogous and would fit that style of "convention defined in prompt; enforcement via prompt+test" note.

**Update needed**: `requirements/multi-agent.md` (primary — dispatch-contract behavior) and/or `requirements/pipeline.md` (secondary — operator deploy discipline)

## Suggested Requirements Update
**File**: `requirements/multi-agent.md`
**Section**: The dispatch / parallel-feature-execution section (around the "Features with `intra_session_blocked_by` dependencies are excluded from dispatch…" block near line 48)
**Content**:
```
- **Orchestrator dispatch-template substitution contract**: Dual-layer prompts (orchestrator-round.md) use two token tiers — session-level single-brace `{token}` pre-filled by `fill_prompt()` in `runner.sh`, and per-feature double-brace `{{feature_X}}` substituted by the orchestrator agent at dispatch time from `state.features[<slug>]`. An XML-tagged `<substitution_contract>` block in the prompt demarcates the contract; the two tiers are also visually distinct (brace-count + name prefix) to defeat lexical priming. Single-layer prompts (`batch-brain.md`, `repair-agent.md`, pipeline prompts) remain single-brace — the double-brace convention applies only to dual-layer dispatch templates. Enforced by `tests/test_fill_prompt.py` at the shell layer; agent-layer substitution is a convention and not independently validated.
- **Pre-deploy no-active-runner check**: Edits that couple `runner.sh` and the orchestrator prompt must be deployed as a single commit AND merged only when no overnight runner is active (consult `~/.local/share/overnight-sessions/active-session.json`: absent, or `phase` not `running`, or PID not alive). `runner.sh` is sourced once per session and its `fill_prompt()` body is held in memory for the full session lifetime; a mid-session prompt/runner skew is silently mis-substituting. Operator discipline only; no automated gate today.
```

## Stage 2: Code Quality
- **Naming conventions**: Double-brace `{{feature_slug}}`, `{{feature_spec_path}}`, `{{feature_plan_path}}` match Anthropic's documented template convention cited in the spec. Single-brace session tokens (`{session_plan_path}`, `{state_path}`, `{events_path}`, `{session_dir}`, `{round_number}`, `{tier}`) match runner.sh's `fill_prompt()` substitution whitelist exactly. The `session_` / `feature_` name-prefix split provides a second axis of disambiguation beyond brace count. Test function names follow the `test_<function>_<behavior>` pattern used elsewhere in `tests/` (e.g., `test_fill_prompt_substitutes_session_plan_path`).
- **Error handling**: No new error paths introduced. The test's `_extract_fill_prompt` uses assertions for structural invariants, which is appropriate for unit-test scope. `subprocess.run(..., check=True)` will surface shell-layer errors as CalledProcessError rather than silently producing empty output.
- **Test coverage**: R7c-R7f positive assertions plus R7h negative assertions (`{slug}`, `{spec_path}`, quoted `"{feature}"`) are executed. The negative set catches partial-rename regressions — a thoughtful defensive addition beyond the spec's minimum. `just test` exited 0 per implementer pre-commit confirmation; local `.venv/bin/pytest tests/test_fill_prompt.py -v` → 5 passed. Function-extraction approach (deviation #1) is a sound engineering interpretation of R7a's intent.
- **Pattern consistency**: Test file layout (module docstring, constants at top, helper `_extract_fill_prompt`, shared `_run_fill_prompt` driver, five focused test functions) matches the idiom of existing `tests/` files. The commit message conforms to repo style (subject under 72 chars, imperative mood, bullet body, no trailing period on subject). Atomic three-file commit per R8a. Per-feature and session-level token naming consistency is maintained throughout (prompt, tests, and runner.sh agree).

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
