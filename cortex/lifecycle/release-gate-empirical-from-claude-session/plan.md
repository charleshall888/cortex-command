# Plan: Release-gate empirical from-Claude-session smoke test for #228 daytime dispatch

## Overview
Four tasks across three spec phases: rewrite the #230 ticket body (procedure + Results template), propagate the same fix into #228 spec R16, add a pytest lint that catches event-name hallucinations in backlog grep targets, and cross-reference the procedure from `docs/release-process.md`. Task 1 carries the bulk of the doc edits; Tasks 3–4 land the recurrence-prevention and discoverability pieces.

## Outline

### Phase 1: Procedure corrections (tasks: 1, 2)
**Goal**: Fix the hallucinated `feature_dispatched`/`events.log` references in both #230 and the parent #228 spec R16; codify the corrected procedure (paired events, Step 0 version-pinning, archive-then-cleanup ordering with timeout, 12-field Results template).
**Checkpoint**: `grep -c "feature_dispatched" cortex/backlog/230-*.md cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` returns 0; `grep -c "pipeline-events.log" cortex/backlog/230-*.md` returns ≥ 1.

### Phase 2: Recurrence-prevention lint (tasks: 3)
**Goal**: Add a pytest test that walks `cortex/backlog/*.md`, extracts `grep -c "<token>"` patterns, and fails when a token that looks like an event name (`^[a-z_]+$`) appears neither in `bin/.events-registry.md` nor as a string literal under `cortex_command/`. Catches the bug class at CI time.
**Checkpoint**: `just test -- tests/test_backlog_grep_targets_resolve.py` exits 0 against the post-Task-1 corpus.

### Phase 3: Doc cross-reference (tasks: 4)
**Goal**: One paragraph in `docs/release-process.md` under the "Cut a new release" section pointing to #230 as the canonical release-gated-ticket pattern.
**Checkpoint**: `grep -c "230-release-gate-empirical-from-claude-session" docs/release-process.md` returns ≥ 1.

## Tasks

### Task 1: Rewrite #230 ticket body (procedure + Results template)
- **Files**: `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md`
- **What**: Rewrite §Procedure, §Release-tag handshake, §Acceptance, and §Results in line with spec requirements R1, R3, R4, R5. Single file edit; four sections updated together because they cross-reference one another (e.g., §Acceptance gates on §Results field presence).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Spec at `cortex/lifecycle/release-gate-empirical-from-claude-session/spec.md` is the contract. Apply R1, R3, R4, R5 verbatim per their acceptance criteria.
  - **§Procedure structure** (in order): Step 0 (version-pinning per R3) → Step 1 (MCP tool invocation, unchanged) → Step 2 (wait with 5-min wall-clock timeout per R4) → Step 3 (assertions per R1: paired `dispatch_start` + `dispatch_complete` in `pipeline-events.log` with feature slug match + ts-after check, plus EPERM=0 and "Sandbox failed to initialize"=0 against the same file) → Step 4 (record per R4: initials, UTC date, paired event lines, captured `git rev-parse HEAD`) → Step 4.5 (archive per R4: `mkdir -p cortex/lifecycle/release-gate-empirical-from-claude-session/archive/`, `cp` pipeline-events.log to `smoke-pipeline-events-<UTC>.log`, `git add` the archive file) → Step 5 (terminate-then-poll-then-clean per R4: `cortex daytime cancel --feature smoke-release-gate`, poll `cortex daytime status --feature smoke-release-gate` at 5-second intervals until no active dispatch or 30 seconds elapse, then `git clean -fd cortex/lifecycle/smoke-release-gate/`).
  - **§Release-tag handshake**: keep the existing `[release-type: minor]`/`[release-type: major]` empty-commit pattern; add a pre-push check (`git log <latest-tag>..HEAD --grep='\[release-type:' --oneline` to confirm no concurrent marker pending, per spec §Edge Cases).
  - **§Acceptance**: gate on §Results 12-field presence (all populated, including SHA match between captured `cortex --version` and #228 merge commit SHA on main).
  - **§Results 12 fields** (blank, not pre-filled): `#228 merge commit SHA on main`, `CLI version captured before Step 1`, `Plugin version captured before Step 1`, `Dispatch ID`, `Pipeline-events.log absolute path`, `EPERM count`, `Sandbox-init-failure count`, `Paired dispatch event lines` (with `dispatch_start:` and `dispatch_complete:` sub-rows in a fenced code block), `git rev-parse HEAD`, `Archive path`, `Operator initials`, `UTC date` (ISO 8601).
  - Frontmatter is already correct (status=in_progress, complexity=simple, criticality=high, areas=[overnight-runner], spec field present). Do not modify frontmatter in this task.
  - §References block already lists parent feature, Spec R16 path, and Plan reference parenthetical. Update only the Plan reference parenthetical to remove the now-stale "Task 17 split out" reference (Task 17 was deleted from plan.md per research finding); replace with a pointer to the HTML comment at plan.md line 206.
- **Verification**: (a) `grep -c "feature_dispatched" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns 0 (pass if count = 0); (b) `grep -c "pipeline-events.log" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns ≥ 1; (c) `grep -c "uv tool install --reinstall" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns ≥ 1; (d) `grep -c "cortex daytime status" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns ≥ 1; (e) `grep -c "git add" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns ≥ 1; (f) `grep -c "#228 merge commit SHA on main" cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` returns ≥ 1.
- **Status**: [ ] pending

### Task 2: Update #228 spec R16 to remove the same hallucination
- **Files**: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md`
- **What**: Edit R16 (line 53) to replace `feature_dispatched` and `events.log` references with the paired `dispatch_start` + `dispatch_complete` against `pipeline-events.log` framing. Preserve R16's other claims (tier-enum rationale, release-tag handshake framing, `[release-type: skip]` then `[release-type: minor]` flow, the in-lifecycle verification check on the backlog item's presence + `blocked_by: [228]`).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current R16 has exactly one occurrence of `feature_dispatched` and one occurrence of `events.log` in the prose that must change (verified: `grep -c feature_dispatched cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` = 1).
  - The replacement clause should read approximately: "empirical verification that `daytime_start_run` invoked from a real Claude session emits paired `dispatch_start` and `dispatch_complete` events in `cortex/lifecycle/<feature>/pipeline-events.log` (matching feature slug; `dispatch_complete.ts > dispatch_start.ts`) with zero EPERM and zero sandbox-init-failure events."
  - Preserve the cross-reference to #230 (the backlog filename + the verification clause `test -f cortex/backlog/230-...md && grep -c "blocked_by: \[228\]"`).
  - Do NOT modify R15 or any other requirement in the file.
- **Verification**: (a) `grep -c "feature_dispatched" cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` returns 0; (b) `grep -c "dispatch_start" cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` returns ≥ 1; (c) `grep -c "pipeline-events.log" cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` returns ≥ 1; (d) `grep -c "blocked_by: \[228\]" cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` returns ≥ 1 (preservation check — the in-lifecycle verification clause for R16 must survive the edit).
- **Status**: [ ] pending

### Task 3: Add pytest lint that catches event-name hallucinations in backlog grep targets
- **Files**: `tests/test_backlog_grep_targets_resolve.py`
- **What**: Create a single pytest test file that walks `cortex/backlog/*.md` (skipping `cortex/backlog/archive/`), extracts every `grep -c "<token>"` and `grep -c '<token>'` pattern from the file's content (both fenced code blocks and inline prose `grep -c` invocations), filters for tokens that look like event names (regex `^[a-z_]+$`), and for each such token verifies that it appears in EITHER `bin/.events-registry.md` OR in any file under `cortex_command/` as a literal string (via `git grep -F`). Failure message format: `UNREGISTERED_GREP_TARGET: <ticket-path>:<line> references "<token>" which is neither a registered event nor an emitted string`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Existing precedent pattern: `tests/test_check_events_registry.py` is the closest sibling — it uses `subprocess` to invoke a `bin/` script. THIS task does NOT add a `bin/` script — the lint is pure-python inside the test file, simpler. Use `subprocess.run(["git", "grep", "-lF", token, "cortex_command/"], cwd=REPO_ROOT, capture_output=True, text=True)` for the codebase string-literal check; check `returncode == 0` and non-empty stdout.
  - REPO_ROOT pattern: `REPO_ROOT = Path(__file__).resolve().parent.parent` (matches `tests/test_check_events_registry.py:36`).
  - Backlog directory: `REPO_ROOT / "cortex" / "backlog"`. Iterate files matching `glob("[0-9]*-*.md")` to skip non-numbered files; explicitly exclude any file path containing `/archive/`.
  - Grep-pattern extraction regex (capture the token inside the quotes): `r'grep\s+-c\s+["\']([^"\']+)["\']'` applied via `re.finditer` line-by-line so the failure message can name the line number.
  - Event-name-shape filter: only check tokens matching `re.fullmatch(r'[a-z_]+', token)`. This excludes file paths (contain `/` or `.`), uppercase identifiers (EPERM), quoted prose (contains spaces), and regex patterns (contain metachars). Verified against current corpus: this filter targets `feature_dispatched`-class tokens and the only existing OK token `complexity_override` (verified to be present in `cortex_command/` so passes the lint).
  - Events registry: `REPO_ROOT / "bin" / ".events-registry.md"`. Read the full file and use `token in text` for the registered-event check (the registry uses inline `<event-name>` markdown rather than a structured format; substring match is sufficient).
  - Allowlist for known-non-event tokens that happen to match `^[a-z_]+$` but are NOT event-shaped (e.g., common pytest parametric values, language keywords): keep this list narrow — start with `["true", "false", "none", "null"]` and expand only if false positives surface. The pre-#228 corpus survey found no such tokens already in backlog grep targets, so this allowlist is precautionary.
  - **Self-test guidance**: include at least two test cases in the file's body: (1) a positive case (registered-event token in a temp fixture passes), (2) a negative case (hallucinated-event token in a temp fixture fails). Use pytest's `tmp_path` fixture; mirror the helper functions `_write_registry` and `_write_skill_prompt` from `tests/test_check_events_registry.py:45-55` but adapted to backlog markdown.
  - **Live-corpus assertion**: include one terminal test that runs the lint against the actual `cortex/backlog/` corpus (not a tmp_path fixture) and asserts no unregistered targets. After Task 1 lands, this test passes; before Task 1 lands, this test would fail on #230. The dependency on [1] is therefore load-bearing.
- **Verification**: (a) `pytest tests/test_backlog_grep_targets_resolve.py -v` exits 0 (pass if exit code = 0 — both the fixture-based test cases and the live-corpus assertion pass after Task 1 lands); (b) `grep -c "UNREGISTERED_GREP_TARGET" tests/test_backlog_grep_targets_resolve.py` returns ≥ 1 (verifies the failure-message convention is implemented).
- **Status**: [ ] pending

### Task 4: Cross-reference the release-gate pattern from `docs/release-process.md`
- **Files**: `docs/release-process.md`
- **What**: Add one paragraph (≤6 sentences) under the existing "Cut a new release" section pointing to #230 as the canonical example of a release-gated ticket where a manual smoke procedure precedes the `[release-type: minor]` push. The paragraph describes the pattern (use a chore ticket with `type: chore`, `tags: [..., release-gate, manual-verification]`, populate §Results before pushing the release-cut commit), not the specific #230 procedure (procedure stays in the ticket per spec Tradeoffs §D1).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - File exists at `docs/release-process.md` (referenced from research findings). Locate the "Cut a new release" section by `grep -n "Cut a new release\|## Cut" docs/release-process.md` and insert the new paragraph at the end of that section (before the next H2/H3 heading).
  - Paragraph content shape: opening sentence names #230 as the canonical example; second sentence describes WHEN to use the pattern (release-blocking property that pytest cannot verify, e.g., MCP-host-required behavior); third sentence describes the §Procedure → §Results → `[release-type: minor]` empty-commit flow; fourth sentence names the conventions (chore ticket with `release-gate` + `manual-verification` tags, populated §Results gates the release commit).
  - Reference #230 by its full filename `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` in the paragraph (the grep-c acceptance check expects the prefix `230-release-gate-empirical-from-claude-session`).
  - The cross-reference depends on [1] because the paragraph describes the procedure shape that Task 1 lands — landing the cross-reference first would point at the pre-fix #230 procedure.
- **Verification**: (a) `grep -c "230-release-gate-empirical-from-claude-session" docs/release-process.md` returns ≥ 1; (b) `grep -c "release-gate" docs/release-process.md` returns ≥ 2 (the new paragraph plus any prior mentions); (c) the paragraph appears in the "Cut a new release" section — verify by `awk` from "Cut a new release" to next H2 and `grep` within that range, e.g., `awk '/^## Cut a new release/,/^## [^C]/' docs/release-process.md | grep -c "230-release-gate-empirical-from-claude-session"` returns ≥ 1.
- **Status**: [ ] pending

## Risks

- **Lint may surface other latent hallucinations in the backlog corpus.** The corpus survey before plan-write found `feature_dispatched` (in #230, fixed by Task 1) and `complexity_override` (in #177, verified emitted in `cortex_command/`, will pass the lint). If a third token surfaces during Task 3's live-corpus assertion, that ticket needs a follow-up fix before Task 3 can land green. Mitigation: Task 3's context calls out the live-corpus assertion; if it fails on tickets other than #230, the implementer should open follow-up tickets rather than gut the assertion.
- **Task 2's edit to #228 spec R16 is concurrent with #228's in-flight implementation.** #228 status is `refined`, not `merged` — its spec is stable, but if #228 lands an implementation PR that touches spec.md before #230 merges, there's a small merge-conflict surface on R16. Mitigation: Task 2 is small (single requirement, well-bounded section); resolve by re-applying the prose edit on top of any concurrent #228 spec changes.
- **The `^[a-z_]+$` event-name heuristic is a deliberate approximation.** It catches all snake_case identifiers in backlog grep targets, not strictly events. Mitigation: the OR-clause "token appears as a string literal in `cortex_command/`" provides an escape valve — any token that's a real emitted string (event or otherwise) passes. The narrow allowlist (`true/false/none/null`) handles common parametric values. If false positives surface, expand the allowlist; don't expand the heuristic.
- **The `cortex daytime status` semantics referenced from Task 1's §Procedure step 5 depend on #228 R13.** Until #228 ships, `cortex daytime status --feature` is unimplemented. The §Procedure prose is correct against the #228 spec contract; if #228 implementation drifts from R13 during build, this lifecycle's spec note flags the requirement to update Task 1's prose before the procedure is executed.
