# Plan: disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape

## Overview

Test-first mechanical repair across two files. Write a unit test that invokes the real `fill_prompt()` via subprocess (establishing executable acceptance criteria), then make surgical edits to `claude/overnight/prompts/orchestrator-round.md` (rename session-level `{plan_path}` → `{session_plan_path}`; convert per-feature tokens to `{{feature_X}}` double-brace; add `<substitution_contract>` instruction block) and `claude/overnight/runner.sh` (update one `str.replace` key). R6 contract block is isolated as its own task for clean review surface. Atomic single-commit gate is an explicit task with pre-merge R8b operator check.

## Tasks

### Task 1: Write `tests/test_fill_prompt.py` invoking real `fill_prompt()` via subprocess

- **Files**: `tests/test_fill_prompt.py`
- **What**: Create a pytest module that sources `claude/overnight/runner.sh` and calls `fill_prompt 1` with realistic stub env vars, then asserts on the output against R7c–R7f. Writing the test first makes acceptance criteria machine-executable and anchors the later edits to exact token strings.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Pattern reference: `tests/test_runner_signal.py` — uses `REAL_REPO_ROOT = Path(__file__).resolve().parent.parent`, `subprocess.run` with an env dict.
  - `fill_prompt()` definition: `claude/overnight/runner.sh:379-394`. The function reads `$TEMPLATE` (the prompt template path, set by the caller site at `runner.sh:381-383`) and substitutes six tokens.
  - Required env vars for the subprocess (per R7b, must be realistic session-shaped values):
    - `PLAN_PATH="/tmp/overnight-2026-04-21-stub/overnight-plan.md"`
    - `STATE_PATH="/tmp/overnight-2026-04-21-stub/overnight-state.json"`
    - `SESSION_DIR="/tmp/overnight-2026-04-21-stub"`
    - `EVENTS_PATH="/tmp/overnight-2026-04-21-stub/overnight-events.log"`
    - `ROUND_NUM=1`
    - `TIER=simple`
    - `TEMPLATE` must point to `<REAL_REPO_ROOT>/claude/overnight/prompts/orchestrator-round.md`.
  - Invocation shape: `subprocess.run(["bash", "-c", "source claude/overnight/runner.sh; fill_prompt 1"], env=stub_env, cwd=REAL_REPO_ROOT, capture_output=True, text=True, check=True)`. Stub dirs need not exist on disk — `fill_prompt()` treats env values as opaque strings.
  - **Assertions required** (all will initially fail — pass only after Tasks 2–5 land):
    - (7c) `{session_plan_path}` not in output AND `{plan_path}` not in output
    - (7d) output contains the stub `PLAN_PATH` value (`/tmp/overnight-2026-04-21-stub/overnight-plan.md`) at least 3 times
    - (7e) `{{feature_slug}}` appears at least once in output
    - (7f) `<substitution_contract>` appears at least once in output
    - (7h, plan-level hardening beyond spec R7) `{slug}` not in output AND `{spec_path}` not in output AND `"{feature}"` not in output — negative assertions that catch a partial rename where one or more single-brace tokens survive. Critical review surfaced that R7e's positive-only check can pass green while 3–4 sites still hold the pre-rename shape; these negative assertions close that gap.
  - Python-helper copy of the substitution logic is prohibited per R7a — the test must exercise the real shell function body.
- **Verification**: `.venv/bin/pytest tests/test_fill_prompt.py -q` — the test module must import and invoke cleanly (no collection or subprocess errors); assertion failures are expected at this stage and gated by Task 6.
- **Status**: [x] complete

---

### Task 2: Rename session-level `{plan_path}` → `{session_plan_path}` in orchestrator-round.md

- **Files**: `claude/overnight/prompts/orchestrator-round.md`
- **What**: Replace the three session-level occurrences of `{plan_path}` (lines 14, 110, 216 — all pre-filled by `fill_prompt()`) with `{session_plan_path}`. The fourth occurrence at line 269 is the per-feature token and is handled in Task 3.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Line 14: `- **Session plan**: \`{plan_path}\`` → `- **Session plan**: \`{session_plan_path}\``
  - Line 110: `- \`{plan_path}\` — the session overnight plan.` → `- \`{session_plan_path}\` — the session overnight plan.`
  - Line 216: `Read \`{plan_path}\` to understand batch assignments...` → `Read \`{session_plan_path}\` to understand batch assignments...`
  - After this task, line 269's `{plan_path}` remains — Task 3 handles it.
- **Verification**: `grep -c '{plan_path}' claude/overnight/prompts/orchestrator-round.md` → `1` (only line 269 remains, per-feature). `grep -c '{session_plan_path}' claude/overnight/prompts/orchestrator-round.md` → `3`.
- **Status**: [x] complete

---

### Task 3: Convert per-feature dispatch-block tokens to `{{feature_X}}` double-brace syntax

- **Files**: `claude/overnight/prompts/orchestrator-round.md`
- **What**: Inside the Step 3b dispatch template (lines 260–285) AND the deferral filename example at line 291, replace single-brace per-feature tokens with double-brace `{{feature_X}}` counterparts per R3, R4, R5. Covers the `{feature}` → `{{feature_slug}}` collapse on line 261, `{spec_path}` → `{{feature_spec_path}}` on line 264, `{slug}` → `{{feature_slug}}` on lines 265/266/291, and the remaining `{plan_path}` → `{{feature_plan_path}}` on line 269.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Line 261: `"{feature}"` → `"{{feature_slug}}"` (R5)
  - Line 264: `{spec_path}` → `{{feature_spec_path}}` (R3)
  - Line 265: `lifecycle/{slug}/research.md` → `lifecycle/{{feature_slug}}/research.md` (R3)
  - Line 266: `lifecycle/{slug}/learnings/recovery-log.md` → `lifecycle/{{feature_slug}}/learnings/recovery-log.md` (R3)
  - Line 269: `{plan_path}` → `{{feature_plan_path}}` (R4)
  - Line 291 (deferral filename `deferred/{slug}-plan-q001.md`): `{slug}` → `{{feature_slug}}` per spec's Changes-to-Existing-Behavior. This occurrence sits outside the fenced dispatch template but the spec explicitly lists it.
  - **Not touched**: `{feature}` Python-dict-access occurrences at lines 89, 102, 108, 109, 115, 136, 148 — these are `entry["feature"]` expressions in Step 0 example code, not template tokens. Must remain unchanged.
- **Verification**:
  - `grep -cE '\{\{feature_(slug|spec_path|plan_path)\}\}' claude/overnight/prompts/orchestrator-round.md` → `≥5` (stronger than spec's `≥3` floor — catches the path-embedded `{{feature_slug}}` at lines 265/266/291 in addition to the bare token occurrences at 261 and elsewhere)
  - `grep -c '{plan_path}' claude/overnight/prompts/orchestrator-round.md` → `0` (the last single-brace occurrence is gone)
  - `grep -c '{spec_path}' claude/overnight/prompts/orchestrator-round.md` → `0`
  - **Negative assertions (added from critical review)**: `grep -c '{slug}' claude/overnight/prompts/orchestrator-round.md` → `0` (catches line 291 and any missed dispatch-block occurrence); `grep -cF '"{feature}"' claude/overnight/prompts/orchestrator-round.md` → `0` (catches line 261's quoted `{feature}` specifically; the unquoted `entry["feature"]` dict-access occurrences are not matched because they lack the outer quotes around `{feature}`).
- **Status**: [x] complete

---

### Task 4: Add `<substitution_contract>` XML-tagged instruction block before dispatch template

- **Files**: `claude/overnight/prompts/orchestrator-round.md`
- **What**: Insert an XML-tagged `<substitution_contract>` block immediately after the "Each sub-agent receives:" prose line and before the opening ```-fence of the Step 3b dispatch template. The block enumerates per-feature tokens the orchestrator must substitute from `state.features[<slug>]` and explicitly prohibits re-substituting pre-filled session-level tokens.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Placement: between the narrative line ending "Each sub-agent receives:" and the opening ``` fence of the dispatch template. The block must sit adjacent to the dispatch template per Anthropic's XML-tag guidance.
  - Block must satisfy all six R6 sub-checks:
    - (6a) Opens with `<substitution_contract>` and closes with `</substitution_contract>`.
    - (6b) Located after Step 3b narrative, before the ```-fenced dispatch template.
    - (6c) Contains literal strings `{{feature_slug}}`, `{{feature_spec_path}}`, `{{feature_plan_path}}` AND references `state.features` (case-sensitive).
    - (6d) Contains imperative markers: the exact phrase `MUST NOT` (uppercase) AND `YOU substitute` (or `YOU MUST substitute`); warns not to copy absolute-path pattern from session-level `{token}` literals earlier in the prompt.
    - (6e) States that per-feature `{{feature_X}}` tokens are substituted by the orchestrator agent from `state.features[<slug>]` at dispatch time, and that session-level single-brace `{token}` values (e.g., `{session_plan_path}`, `{state_path}`, `{events_path}`, `{session_dir}`) are **already pre-filled by `fill_prompt()`** and MUST NOT be re-substituted. Must contain the literal phrase `pre-filled by fill_prompt` (case-insensitive).
    - (6f) First line inside the opening tag begins with `CRITICAL:`, `IMPORTANT:`, or `YOU MUST:`.
- **Verification**:
  - `grep -c '<substitution_contract>' claude/overnight/prompts/orchestrator-round.md` → `1`
  - `grep -c '</substitution_contract>' claude/overnight/prompts/orchestrator-round.md` → `1`
  - `grep -ci 'pre-filled by fill_prompt' claude/overnight/prompts/orchestrator-round.md` → `≥1`
  - `awk '/<substitution_contract>/,/<\/substitution_contract>/' claude/overnight/prompts/orchestrator-round.md | grep -c 'MUST NOT'` → `≥1` (checks MUST NOT falls inside the block, not elsewhere)
  - `awk '/<substitution_contract>/,/<\/substitution_contract>/' claude/overnight/prompts/orchestrator-round.md | grep -cE 'YOU (MUST )?substitute'` → `≥1`
  - `awk '/<substitution_contract>/,/<\/substitution_contract>/' claude/overnight/prompts/orchestrator-round.md | grep -c 'state.features'` → `≥1`
  - First line of the block matches `^(CRITICAL|IMPORTANT|YOU MUST):` — verify by reading the line immediately after the opening tag.
- **Status**: [x] complete

---

### Task 5: Update `fill_prompt()` in runner.sh to substitute `{session_plan_path}`

- **Files**: `claude/overnight/runner.sh`
- **What**: Change the single `str.replace` call on `runner.sh:387` that substitutes the session-plan token. The key string changes from `{plan_path}` to `{session_plan_path}`; the `os.environ['PLAN_PATH']` value side and all five other token substitutions (state_path, events_path, session_dir, round_number, tier) remain unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current line 387: `t = t.replace('{plan_path}', os.environ['PLAN_PATH'])`
  - Target: `t = t.replace('{session_plan_path}', os.environ['PLAN_PATH'])`
  - `PLAN_PATH` env var assignments at lines 99, 239, 278 and exports at lines 381, 387 are unchanged.
  - Runs as independent of Tasks 2–4 at the file level, but must land in the same commit per R8a.
- **Verification**:
  - `grep -c "'{session_plan_path}'" claude/overnight/runner.sh` → `≥1`
  - `grep -c "'{plan_path}'" claude/overnight/runner.sh` → `0`
- **Status**: [x] complete

---

### Task 6: Run `just test`, verify preconditions, and commit atomically

- **Files**: `claude/overnight/prompts/orchestrator-round.md`, `claude/overnight/runner.sh`, `tests/test_fill_prompt.py`
- **What**: Execute the full test suite and then enforce two pre-commit preconditions as explicit sequenced steps before `/commit` runs — (a) R8b no-active-session check, and (b) staged-file-list check — so the atomic-commit requirement is gated by independent assertions rather than by post-commit self-inspection. Only after both preconditions pass, invoke `/commit` per R8a. Order of operations:
  1. Run `just test` — must exit 0 with `test_fill_prompt.py` included.
  2. Run `ls ~/.local/share/overnight-sessions/active-session.json 2>/dev/null` — must return empty output (R8b). If a file is returned, run `ps -p $(jq -r .pid ~/.local/share/overnight-sessions/active-session.json)` — must exit non-zero (dead PID). If either gate fails, STOP — do not commit until the runner has exited.
  3. Stage the three target files explicitly: `git add claude/overnight/prompts/orchestrator-round.md claude/overnight/runner.sh tests/test_fill_prompt.py`.
  4. Run `git diff --name-only --cached` — output must list exactly those three paths (one per line). If any path is missing or any extra path appears, STOP — do not commit until staging is correct.
  5. Invoke `/commit` per project convention (the `/commit` skill runs the actual `git commit`).
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: simple
- **Context**:
  - `just test` runs `.venv/bin/pytest tests/ -q` as its unit-test suite (pytest auto-discovers `tests/test_fill_prompt.py`).
  - The R8b check was previously listed under Verification as a post-hoc note; critical review surfaced that this gave R8b the appearance of a gate without enforcement weight. Step 2 above promotes R8b to a precondition — if active, the task halts before any commit is attempted.
  - The `git diff --name-only --cached` check is an independent pre-commit assertion of atomicity: it runs before `/commit` creates HEAD, so it cannot self-seal. This replaces the post-commit `git show --name-only HEAD` check from the prior plan version (which was self-sealing by the plan's own P7 standard — the task created HEAD then inspected it).
  - Caveat R8c (documented, not enforced): bash sources `runner.sh` once at session start; a mid-session `git pull` leaves the old `{plan_path}` substitution in the in-memory function body. The R8b precondition in step 2 is the only defense — do not deploy while a session is running.
  - Commit via `/commit` skill per project convention. The commit must touch both `claude/overnight/prompts/orchestrator-round.md` AND `claude/overnight/runner.sh` in a single atomic commit per R8a; `tests/test_fill_prompt.py` ships in the same commit.
- **Verification**:
  - `just test` exits 0 (step 1 output).
  - `ls ~/.local/share/overnight-sessions/active-session.json 2>/dev/null` returns no output (step 2 output).
  - `git diff --name-only --cached` output, captured after step 3 and before step 5, equals exactly the three target paths (step 4 output).
- **Status**: [x] complete

---

## Verification Strategy

After all tasks complete and the atomic commit lands:

1. **Token removal** (R1, R4): `grep -c '{plan_path}' claude/overnight/prompts/orchestrator-round.md` → `0`.
2. **Session rename** (R1): `grep -c '{session_plan_path}' claude/overnight/prompts/orchestrator-round.md` → `3`.
3. **Per-feature double-brace** (R3, R5): `grep -cE '\{\{feature_(slug|spec_path|plan_path)\}\}' claude/overnight/prompts/orchestrator-round.md` → `≥5`.
4. **Runner substitution key** (R2): `grep -c "'{session_plan_path}'" claude/overnight/runner.sh` → `≥1`; `grep -c "'{plan_path}'" claude/overnight/runner.sh` → `0`.
5. **Contract block present** (R6): `grep -c '<substitution_contract>' claude/overnight/prompts/orchestrator-round.md` → `1`; `grep -ci 'pre-filled by fill_prompt' claude/overnight/prompts/orchestrator-round.md` → `≥1`.
6. **Unit test passes** (R7): `.venv/bin/pytest tests/test_fill_prompt.py -v` exits 0 with all assertions (7c–7f) green.
7. **Full suite passes** (R7g): `just test` exits 0.
8. **Atomic single commit** (R8a): `git diff --name-only --cached` output captured pre-commit in Task 6 step 4 equals exactly the three target paths. (Independent pre-commit check; replaces the prior self-sealing `git show --name-only HEAD` post-commit inspection.)
9. **No active runner** (R8b): `ls ~/.local/share/overnight-sessions/active-session.json 2>/dev/null` returned empty during Task 6 step 2, verified as a precondition before commit.

## Veto Surface

- **Test-first ordering (Task 1 before Tasks 2–5)**: The test will fail its assertions until Tasks 2–5 all land. If the implementing agent interprets red-on-fresh-run as a task-1 bug and starts debugging the test rather than proceeding to Task 2, the plan stalls. The user may prefer reordering Task 1 to run after Task 5 (source-first), trading away the executable-acceptance-criteria gate for smoother execution.
- **R6 block placement precision**: "Immediately before the dispatch template" is still interpretive. If the block lands 3–5 lines earlier (e.g., before the "Each sub-agent receives:" prose), adjacency is weaker but acceptance grep still passes. A strict reviewer may reject; a lenient one may accept.
- **Agent-layer silent regression is undefended**: The spec's Technical Constraints explicitly names "a silent regression of the session-1708 bug is possible and would cost one overnight cycle to detect." Task 4 verifies the `<substitution_contract>` block exists with imperative markers, but nothing in the plan verifies those markers actually change orchestrator behavior. The plan has no task that inspects a first post-deploy overnight session for mis-substitution, and does not propose or rule out a cheaper synthetic pre-deploy evaluation (e.g., a canned stub `state.json` fed to the orchestrator in dry-run asserting the first-round dispatch payload resolves `{{feature_plan_path}}` to a concrete path). This is the highest-cost failure mode of the fix; the user should decide whether to accept it as-is, add a post-deploy observation task, or add a synthetic pre-deploy evaluation. **This question belongs to the user, not the plan.**

## Scope Boundaries

Excluded per spec Non-Requirements:
- **`BacklogItem.plan` override pipeline fix** — pre-existing bug across 7+ sites (`feature_executor.py:238/518/686/755`, `report.py:734`, `daytime_pipeline.py:208/325/328/331`, `dashboard/seed.py:101`). Not introduced by this ticket, not fixed here.
- **State-field injection validation** for `state.features[<slug>]` values flowing into sub-agent prompts.
- **Other prompt templates** (`batch-brain.md`, `repair-agent.md`, `claude/pipeline/prompts/*.md`) — single-layer, no priming vulnerability.
- **Env-var / constant / schema renames** — `PLAN_PATH`, `DEFAULT_PLAN_PATH`, `BATCH_PLAN_PATH`, `state.features[<slug>].plan_path` are all unchanged.
- **Live/integration test harness for orchestrator runtime behavior** — agent-layer substitution validation is informal (first post-deploy overnight session).
- **Prompt-linter or pre-commit hook** for dual-layer token collision detection.
- **Pre-merge hook for active-session check (R8b automation)** — operator discipline only.
