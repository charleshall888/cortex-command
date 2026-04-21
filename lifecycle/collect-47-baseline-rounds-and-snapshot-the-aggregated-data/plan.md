# Plan: collect-47-baseline-rounds-and-snapshot-the-aggregated-data

## Overview

Two-commit sequence gated by a user-driven measurement window. Commit A (Tasks 1–5) lands `model_resolved` instrumentation on `dispatch_complete` so the baseline window runs on post-R1 code. The user then runs ≥2 clean overnight rounds (Task 6, operator-driven). Commit B (Tasks 7–10) composes and commits the snapshot artifact at `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md`, embedding the verbatim `tier-dispatch` CLI report and a raw-JSON fence lifted from `lifecycle/metrics.json`.

## Tasks

### Task 1: Capture `model_resolved` in `dispatch_complete`

- **Files**: `claude/pipeline/dispatch.py`
- **What**: Implement spec R1. Initialize `resolved_model: str | None = None` alongside `cost_usd` (lines 455–459 region). Inside the `isinstance(message, AssistantMessage)` branch at line 462, after the existing content-block loop, assign `resolved_model = getattr(message, 'model', None)` only if `resolved_model is None` (first-observed semantic — never reassign). Extend the `dispatch_complete` `log_event` payload at lines 510–516 to include `"model_resolved": resolved_model`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The async iteration loop over `query(...)` is at `dispatch.py:461`. `AssistantMessage` is imported from `claude_agent_sdk`; in `claude_agent_sdk==0.1.41` it exposes `.content: list[ContentBlock]` and `.model: str`. `ResultMessage` at `dispatch.py:502` has no `.model` attribute — do not use it. The defensive `getattr(message, 'model', None)` pattern is mandated by spec Technical Constraints so future SDK renames fall through to `None` instead of raising. The field is additive — `metrics.py:296` (`_DAYTIME_DISPATCH_COMPLETE_FIELDS`) uses presence-based schema detection, not strict whitelisting, so extra keys are ignored downstream.
- **Verification**: `grep -cE '"model_resolved"' claude/pipeline/dispatch.py` = 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 2: Add unit tests for `model_resolved` emission (including "never reassign" invariant)

- **Files**: `claude/pipeline/tests/test_dispatch_instrumentation.py`
- **What**: Implement spec R2 plus an additional invariant test. Add **two** tests: (a) single-AssistantMessage happy path — patch `claude_agent_sdk.query` to yield `AssistantMessage(content=[], model="claude-opus-4-7-test")` followed by a `ResultMessage(...)`; assert the written JSONL log contains a `dispatch_complete` entry with `model_resolved == "claude-opus-4-7-test"`. (b) First-observed invariant — patch `query` to yield TWO `AssistantMessage` objects with distinct `.model` values in order (`AssistantMessage(content=[], model="first-model-id")` then `AssistantMessage(content=[], model="second-model-id")`) followed by a `ResultMessage(...)`; assert the written `dispatch_complete` entry has `model_resolved == "first-model-id"` (NOT `"second-model-id"`). Test (b) exercises Task 1's `if resolved_model is None` guard — a regression that drops the guard would silently convert the semantic to last-observed and pass test (a) but fail test (b).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Follow the scaffolding already in the file — `_install_sdk_stub()` runs at import time, SDK types (`AssistantMessage`, `ResultMessage`, etc.) are pulled off `sys.modules["claude_agent_sdk"]`, and `_async_gen(*items)` at the top of the file constructs scripted streams. `_read_jsonl(path)` parses emitted JSONL events with `ts` stripped. Use `unittest.mock.patch` on the module-level `query` symbol inside `claude.pipeline.dispatch` (consistent with existing tests in this file).
- **Verification**: `pytest claude/pipeline/tests/test_dispatch_instrumentation.py -q` — pass if exit 0 AND output shows ≥ 2 new tests passing.
- **Status**: [ ] pending

### Task 3: Verify metrics tests and fixtures accept the new field

- **Files**: `claude/pipeline/tests/test_metrics.py`, `claude/pipeline/tests/fixtures/dispatch_over_cap.jsonl`, `claude/pipeline/tests/fixtures/dispatch_since_boundary.jsonl`
- **What**: Implement spec R2's inspection clause. Search for any assertion that pins `dispatch_complete` to an exact field set (e.g., `assertEqual(event, {...})` over the whole dict, or key-set equality checks against `_DAYTIME_DISPATCH_COMPLETE_FIELDS`). If found, relax the check to allow the new `model_resolved` key (prefer key-subset or field-by-field assertions over whole-dict equality). Fixture JSONL files carry data only — no changes needed unless a test asserts their exact content round-trip.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Spec cites `test_metrics.py:80` (the `_complete()` helper builds fixture dicts) and `test_metrics.py:217-230` (a daytime-schema test constructing exact dicts). These are fixture *builders*, not assertions — if tests only feed them to `compute_model_tier_dispatch_aggregates()` and assert on its output, they remain valid. Confirm by running the test file after the inspection. The frozenset at `metrics.py:296` is presence-based, not exclusive — adding keys is safe.
- **Verification**: `pytest claude/pipeline/tests/test_metrics.py -q` — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Run full pipeline test suite

- **Files**: (none created) — runs existing tests
- **What**: Execute the entire `claude/pipeline/tests/` suite to confirm no regressions from the dispatch change.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: Invocation: `pytest claude/pipeline/tests/ -q`. The suite covers dispatch, metrics, merge recovery, escalation, parser, repair agent, review dispatch. `conftest.py` installs the SDK stub at module-scope.
- **Verification**: `pytest claude/pipeline/tests/ -q` — pass if exit 0, 0 failures, 0 errors.
- **Status**: [ ] pending

### Task 5: Commit A — pipeline instrumentation

- **Files**: `claude/pipeline/dispatch.py`, `claude/pipeline/tests/test_dispatch_instrumentation.py`, optionally `claude/pipeline/tests/test_metrics.py` (only if Task 3 required edits), plus `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/{events.log, research.md, spec.md, plan.md, index.md}`.
- **What**: Invoke the `/commit` skill to create Commit A. Commit message must reference `#088 (pipeline instrumentation, pre-window)` per spec R14. This commit MUST land and be on `main` before any round of the measurement window runs.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Global instructions mandate `/commit` skill over manual `git commit`. The commit must be scoped to the files enumerated above — do not include `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` (that is Commit B) nor any `sha-round-*.txt` files (those land with Commit B per R14). The resulting SHA (12-char prefix) is what will be recorded as `git_sha_window_start` for the first clean round.
- **Verification**: `git log --oneline -1 -- claude/pipeline/dispatch.py` — pass if the top entry's message matches regex `/088.*pipeline instrumentation/i` AND `git status` shows no staged changes.
- **Status**: [ ] pending

### Task 6: Measurement window — user runs ≥2 clean overnight rounds

- **Files**: `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-{session_id}.txt` (one per attempted round)
- **What**: Implement spec R5, R6, R13. Before each overnight round's first dispatch, the operator runs `git rev-parse HEAD > lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-{session_id}.txt`. The operator executes overnight rounds on the Commit-A codebase with prompts frozen (no edits during the window to files matching the spec R5 path list). After each round, the operator applies the R6 clean-round rule by grepping the round's `pipeline-events.log` for `api_rate_limit` errors (condition a) and the session's `overnight-events.log` for `SESSION_COMPLETE` (condition b). A round failing either condition is discarded and an additional round is run. The window closes when ≥ 2 clean rounds are in the bag.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**: Per-round SHA-capture files live at exactly `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-{session_id}.txt`. Clean-round condition (a) is checked by `grep -c '"error_type":"api_rate_limit"' lifecycle/sessions/{session_id}/pipeline-events.log` == 0. Clean-round condition (b) is checked by `grep -c '"event":"SESSION_COMPLETE"' lifecycle/sessions/{session_id}/overnight-events.log` ≥ 1 and `lifecycle/sessions/{session_id}/.runner.lock` absent or matches session PID at SESSION_COMPLETE time. Prompt-surface path list for frozen-prompts voluntary discipline: `skills/**/*.md`, `claude/reference/**/*.md`, `claude/pipeline/prompts/**/*.md`, `claude/overnight/prompts/**/*.md`, `CLAUDE.md`, `claude/Agents.md`.
- **Verification**: Interactive/session-dependent: the measurement window is driven by the operator running overnight rounds over multiple calendar days and cannot be executed by an implementing agent. The gating artifacts (≥2 `sha-round-*.txt` files AND ≥2 sessions passing the R6 rule) are the continuation condition for Task 7.
- **Status**: [ ] pending

### Task 7: Regenerate the tier-dispatch CLI report

- **Files**: `/tmp/088-tier-dispatch-report.txt` (scratch — not committed)
- **What**: Run `python3 -m claude.pipeline.metrics --since 2026-04-20 --report tier-dispatch > /tmp/088-tier-dispatch-report.txt`. Also confirm `lifecycle/metrics.json` was written with `model_tier_dispatch_aggregates` and `model_tier_dispatch_aggregates_window` top-level keys (both are side-effects of the same invocation per `metrics.py:1093–1097, 1104–1114`).
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Invocation recipe: `python3 -m claude.pipeline.metrics --since 2026-04-20 --report tier-dispatch`. CLI flag handling is at `metrics.py:1042`. The verbatim stdout is what gets pasted into the snapshot's `## Aggregates` fenced block per R9. `lifecycle/metrics.json` is updated as a side effect; the embedded JSON in the snapshot is lifted verbatim from that file per R10.
- **Verification**: `test -s /tmp/088-tier-dispatch-report.txt && python3 -c "import json; d=json.load(open('lifecycle/metrics.json')); assert 'model_tier_dispatch_aggregates' in d and 'model_tier_dispatch_aggregates_window' in d"` — pass if exit 0.
- **Status**: [ ] pending

### Task 8: Compose the snapshot markdown

- **Files**: `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md`, `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-*.txt` (read, not modified)
- **What**: Create the snapshot file with (a) YAML frontmatter per R11 containing all 13 required keys with the exact value-types specified, (b) body sections in order: the five R12 sections (`## Overview`, `## Clean rounds included`, `## Aggregates`, `## Raw data`, `## Limitations`) PLUS a new `## Prompt-surface diff over window` section inserted between `## Raw data` and `## Limitations` (added from critical review — see sub-step (f) below), (c) the verbatim CLI report from Task 7 pasted inside a fenced code block under `## Aggregates` per R9, (d) the `model_tier_dispatch_aggregates` and `model_tier_dispatch_aggregates_window` objects lifted verbatim from `lifecycle/metrics.json` inside a ```json fence under `## Raw data` per R10, (e) the `## Limitations` list containing the six R12 bullets (cost-estimate, small-n, bare-family-name, cross-version-invalid, R1-must-stay-active, inline-literal-residual-risk) PLUS a seventh bullet: **`model_resolved` is first-observed per dispatch stream and is not filtered on `parent_tool_use_id`; in streams where a subagent's `AssistantMessage` arrives before the parent's first message (e.g., parent opens with a `Task`-tool `ToolUseBlock`), the captured `model_resolved` may be the subagent's model, not the dispatch's nominal model. #092's comparison must treat per-stream `model_resolved` as evidence of what ran, not as a pin on what was requested.** (R12 acceptance requires ≥ 6 bullets; seven is allowed.), (f) the new `## Prompt-surface diff over window` section contains the verbatim stdout of `git log --oneline <git_sha_window_start>..<git_sha_window_end> -- skills/ claude/reference/ claude/pipeline/prompts/ claude/overnight/prompts/ CLAUDE.md claude/Agents.md` captured inside a fenced code block. If the command returns zero lines, the fence contains a single line reading `(no commits — prompt surface unchanged during window)`. If non-empty, the fence contains the raw `git log` output; a brief prose sentence above the fence states: "These commits touched prompt-surface paths during the measurement window. Downstream consumers (#092, #090) MUST decide whether each round remains a valid comparison anchor given the listed edits; rounds occurring after a listed commit may need partitioning or re-run."
- **Depends on**: [7]
- **Complexity**: complex
- **Context**: Frontmatter keys and types per R11 (verbatim): `snapshot: "4-7-baseline"`, `ticket: 88` (int), `epic: 82` (int), `generated_at: <ISO 8601 UTC>`, `window_start: 2026-04-20` (YYYY-MM-DD), `window_end: <YYYY-MM-DD>`, `since_flag: "2026-04-20"` (quoted string), `rounds_included: <int ≥ 2>`, `git_sha_window_start: <12-char lowercase hex>`, `git_sha_window_end: <12-char lowercase hex>`, `aggregator_invocation: "python3 -m claude.pipeline.metrics --since 2026-04-20 --report tier-dispatch"`, `cost_caveat: "All cost values are SDK client-side estimates (ResultMessage.total_cost_usd), not authoritative billing data"`, `sample_size_caveat: "At n<30 per bucket this baseline is directional only, not conclusive evidence for prompt-change attribution"`. Clean rounds table columns per R6: `session_id | round | clean | reason_if_discarded`. SHA values come from reading `sha-round-{session_id}.txt` files and truncating to 12 chars; `git_sha_window_start` is the file for the *first* clean round, `git_sha_window_end` is the file for the *last* included clean round. Do not create any new `bin/` script — composition is manual per spec Non-Requirements.
- **Verification**: `grep -cE "^## (Overview|Clean rounds included|Aggregates|Raw data|Prompt-surface diff over window|Limitations)$" research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` = 6 — pass if exact count is 6.
- **Status**: [ ] pending

### Task 9: Run all snapshot acceptance checks

- **Files**: (none created) — runs acceptance checks
- **What**: Execute seven acceptance checks inline — the five spec checks plus two commit-ordering / per-event content checks added from critical review:
  (a) **R9 verbatim-match**: `diff -u /tmp/088-tier-dispatch-report.txt <(awk '/^## Aggregates$/,/^## Raw data$/' research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md | sed -n '/^```/,/^```/{/^```/d;p;}')` expected empty.
  (b) **R10 JSON-match**: the Python one-liner from spec Requirement 10's acceptance block.
  (c) **R11 frontmatter type-check**: the Python one-liner from spec Requirement 11's acceptance block.
  (d) **Section-count (extends R12)**: `grep -cE "^## (Overview|Clean rounds included|Aggregates|Raw data|Prompt-surface diff over window|Limitations)$" research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` = 6 AND `## Limitations` contains ≥ 6 bullet lines. Extends R12's five-section requirement with the `## Prompt-surface diff over window` section added in Task 8(f).
  (e) **R13 SHA-file existence + match**: `ls lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-*.txt | wc -l` ≥ 2 AND the frontmatter SHA values match file contents (truncated to 12 chars).
  (f) **Per-round ancestry against Commit A (NEW, from critical review)**: Let `COMMIT_A_SHA` be the SHA from Task 5's commit (captured via `git log --oneline -1 -- claude/pipeline/dispatch.py | awk '{print $1}'` — the most recent commit touching that file). For each file `sha-round-*.txt` that corresponds to a clean round (per the snapshot's Clean rounds table), `git merge-base --is-ancestor $COMMIT_A_SHA $(cat <file>)` must exit 0. This asserts every clean round ran on a codebase descending from Commit A — closing the "round ran before Commit A landed" gap.
  (g) **In-window `model_resolved` presence (NEW, from critical review)**: `python3 -c "import json; events = [json.loads(l) for l in open('lifecycle/pipeline-events.log') if l.strip()]; window = [e for e in events if e.get('event') == 'dispatch_complete' and e.get('ts','') >= '2026-04-20']; assert len(window) > 0, 'no dispatch_complete events in window'; missing = [e for e in window if e.get('model_resolved') is None]; assert not missing, f'{len(missing)} in-window dispatch_complete events lack non-null model_resolved (pre-R1 contamination)'"` exits 0. This asserts every `dispatch_complete` event in the window carries a non-null `model_resolved` — closing the "aggregator-exists is not field-presence" gap.
  (h) **Prompt-surface diff section present and well-formed (NEW, from critical review)**: `grep -c "^## Prompt-surface diff over window$" research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` = 1 AND the section contains a fenced code block whose first line is either `(no commits — prompt surface unchanged during window)` OR one or more `git log --oneline` format lines. This is a structural check only — non-empty diff output is NOT a hard fail (soft-surface decision per Q2); it is disclosed in the committed artifact so downstream consumers can decide whether to trust the comparison.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Checks (a)–(e) are from spec Requirements 9, 10, 11, 12, 13. Checks (f), (g), (h) were added after critical review surfaced that the spec's own R14 intent ("R1 landed before any round runs"), R1 intent ("captures `model_resolved` in every dispatch_complete"), and R5 intent ("no prompt-surface commits during window") were not mechanically verified anywhere in the plan. If any check fails, the snapshot is invalid: (f) failing means a clean round ran on pre-R1 code — discard and re-run; (g) failing means at least one in-window dispatch predates R1 — discard and re-run; (h) failing means the snapshot does not structurally disclose the prompt-surface diff — fix composition and retry Task 8.
- **Verification**: All eight check commands listed in the `What` field above exit 0 — pass only if all eight pass.
- **Status**: [ ] pending

### Task 10: Commit B — baseline snapshot

- **Files**: `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md`, `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/sha-round-*.txt`
- **What**: Invoke the `/commit` skill to create Commit B. Commit message must reference `#088 (baseline snapshot)` per spec R14. The commit is scoped to exactly the snapshot file plus all `sha-round-*.txt` files — no other files.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Spec R14 requires this commit's parent chain to be a descendant of Commit A — the measurement window ran on the post-R1 codebase, so this is already true provided no rebase happened between A and B. Use `/commit`.
- **Verification**: `git log --oneline -1 -- research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` — pass if the top entry's message matches regex `/088.*(baseline )?snapshot/i` AND `git merge-base --is-ancestor <Commit-A-sha> HEAD` exits 0.
- **Status**: [ ] pending

## Verification Strategy

Two-phase verification matches the two-commit structure:

1. **Post-Commit-A** (after Task 5): `pytest claude/pipeline/tests/` exits 0; `grep '"model_resolved"' claude/pipeline/dispatch.py` returns a match inside the `dispatch_complete` event block; `git log --oneline main -- claude/pipeline/dispatch.py | head -1` matches `/088.*pipeline instrumentation/i`. Commit A is revertable independently of Commit B.

2. **Post-Commit-B** (after Task 10): `ls research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` exits 0; Task 9's eight acceptance checks all pass; the frontmatter's `rounds_included` is ≥ 2 and matches the row count in the Clean rounds table; `update-item 088-collect-47-baseline-rounds-then-remove-progress-update-scaffolding status=complete` succeeds. The snapshot is self-contained — downstream tickets (#092, #090) read it without needing to regenerate, and the `## Prompt-surface diff over window` section gives them mechanical evidence of window cleanliness.

Additional cross-check: `git merge-base --is-ancestor <Commit-A-sha> <Commit-B-sha>` exits 0 (enforces R14 ordering invariant).

## Veto Surface

- **Overnight dispatch gate is wired via `backlog/099-operator-gate-088-measurement-window-complete.md`.** Backlog #088 now has `blocked-by: [99]`. While #099 is in non-terminal status (`backlog`), `_is_eligible_for_overnight()` (`claude/overnight/backlog.py:504–512`) marks #088 ineligible for `/overnight` auto-selection. This closes the critical-review gap where overnight would have dispatched Task 6 as a normal worker task, either self-forging `sha-round-*.txt` files or landing Commit A on a session integration branch (breaking R14). **Clearance**: after Task 6 produces ≥ 2 clean rounds AND the operator confirms per-round SHAs descend from Commit A, run `update-item 099-operator-gate-088-measurement-window-complete status=complete` to unblock #088 before proceeding to Task 7.
- **Task 6 is user-driven and multi-day.** The implementing agent cannot proceed from Task 5 to Task 7 without operator action. Confirm before starting that the user is ready to commit Commit A *now* and then run ≥2 overnight rounds over the next several days.
- **Commit ordering is load-bearing (R14).** Collapsing Tasks 1–5 and 7–10 into a single commit would violate the spec and produce either a contaminated baseline (R1 landed mid-window) or a snapshot without `model_resolved` evidence. Any request to "just commit everything at once" must be refused — point the requester back to the critical review that forced this split.
- **Snapshot composition is manual (no `bin/` script).** Spec Non-Requirements explicitly forbid a generator script. If the composition feels error-prone, the remedy is to re-run the acceptance checks in Task 9, not to automate it.
- **First-observed `AssistantMessage.model` semantic.** If mid-stream model changes become empirically observable (e.g., subagent dispatches yielding a different resolved version), that is a future ticket, not a scope-expansion here.

## Scope Boundaries

From spec Non-Requirements:
- No new `bin/` script for snapshot generation — the existing `python3 -m claude.pipeline.metrics --since YYYY-MM-DD --report tier-dispatch` CLI plus R9's verbatim-capture rule is sufficient.
- No JSON sidecar file — raw data lives in the embedded fenced JSON block inside the markdown.
- No tier-only collapsed view — per-(model, tier) is the primary and only view.
- No manifest hashing of prompt-surfacing paths at round-start — voluntary discipline + git-SHA attribution is the mechanism.
- No version-aware aggregation in `metrics.py` — `#087`'s aggregator is unchanged; `model_resolved` is persisted but not bucketed on.
- No rate-limit-incidents field in the snapshot — #087 Non-Requirement #2 excluded it.
- No hypothesis block in the snapshot.
- No extended measurement window beyond 2–3 rounds; clean-rule failures trigger additional rounds but the window is not chased to n≥30.
- No per-tier minimum-n enforcement at ticket closure; `p95_suppressed:true` labels low-n buckets; downstream tickets open follow-ups on empty buckets.
- No mid-stream model-resolution handling in R1 — first-observed is the semantic.
- No automated prompt-surface manifest check — R5 is a `git log` command the reviewer runs manually.
