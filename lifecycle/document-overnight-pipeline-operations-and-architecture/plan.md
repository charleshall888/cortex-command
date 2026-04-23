# Plan: document-overnight-pipeline-operations-and-architecture

## Overview

Produce `docs/overnight-operations.md` in writing-order (outline → skeleton → per-section content) after a bounded retros mining pass, then execute the doc-level refactors (overnight.md extraction, pipeline.md dedup, CLAUDE.md rule, cross-link updates), then add and verify the `_ALLOWED_TOOLS` pytest. Content sections and refactors are gated behind the outline so all 21 gaps are assigned before prose starts.

## Tasks

### Task 1: Retros mining pass (req 8)
- **Files**: `lifecycle/document-overnight-pipeline-operations-and-architecture/learnings/retros-mining.md` (new)
- **What**: Grep up to 10 most recent `retros/*.md` files for the terms in spec req 8; for each surfaced pain-point, record a disposition (will be slotted into the doc, filed as a backlog ticket, or dismissed with rationale). This output feeds tasks 4–7 and the PR body for req 8 acceptance.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `retros/` contains dated problem-only logs; `ls retros/*.md | sort -r | head -10` yields the scan set. Search terms per spec req 8: "2am", "couldn't find", "unclear", "surprising", "stuck". Output format: a `## Scanned retros` section listing each retro filename scanned (one per line); a `## Findings` table `| source-retro | quote | disposition (added|filed|dismissed) | target subsection or rationale |`.
- **Verification**: (b) file exists AND `awk '/^## Scanned retros/,/^## /' learnings/retros-mining.md | grep -cE '^- retros/' ≥ 3` (at least 3 retros scanned per spec req 8 floor) AND `grep -c '^| ' learnings/retros-mining.md` ≥ 2 (table header + separator, findings section present even if empty); pass if both counts meet thresholds.
- **Status**: [x] complete

### Task 2: Content outline (all 21 gaps slotted)
- **Files**: `lifecycle/document-overnight-pipeline-operations-and-architecture/learnings/outline.md` (new)
- **What**: Produce a subsection-level outline for `docs/overnight-operations.md`. Every one of the 21 required gaps (13 original + 8 research-added per spec req 2) has an assigned H2/H3 heading. Retros-mining findings with disposition "added" are assigned a heading here too.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Use the extraction table from `lifecycle/{feature}/research.md` §Sections to move and the 21-keyword list from `lifecycle/{feature}/spec.md` req 2. Output is a heading tree with one-line purpose per subsection. Keywords must appear in heading text to satisfy req 2's grep check.
- **Verification**: (b) every one of the 21 spec req 2 keyword strings appears in a heading line of the outline. Checked by the shell loop `ok=1; for kw in "review_dispatch" "allowed_tools" "pipeline/prompts" "overnight/prompts" "escalations.jsonl" "overnight-strategy.json" "Conflict Recovery" "Cycle-breaking" "Test Gate" "--tier" "brain.py" "lifecycle.config.md" "apiKeyHelper" "orchestrator_io" ".runner.lock" "report.py" "agent-activity.jsonl" "Dashboard Polling" "Session Hooks" "Scheduled Launch" "interrupt.py"; do grep -q -iE "^#.*$kw" learnings/outline.md || { echo MISSING $kw; ok=0; }; done; exit $((1-ok))` — pass if exit code = 0. Each regex uses case-insensitive and allows the keyword OR a documented synonym from spec req 2 (e.g., "Post-Merge Review" for review_dispatch) in the heading.
- **Status**: [x] complete

### Task 3: Create `docs/overnight-operations.md` skeleton
- **Files**: `docs/overnight-operations.md` (new)
- **What**: Create the doc with breadcrumb (`[← Back to overnight.md](overnight.md)`), audience header (`**For:** operators and contributors debugging overnight. **Assumes:** familiarity with how to run overnight.`), jump-to blockquote nav, H1, and H2 skeleton matching the outline from task 2. Each H2/H3 present but body empty.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Mirror the breadcrumb/audience/jump-nav pattern from `docs/overnight.md` line 1–15, `docs/pipeline.md` line 1–15. H2 sections: `## Architecture`, `## Tuning`, `## Observability`, `## Security and Trust Boundaries`, `## Internal APIs` (orchestrator_io + lifecycle.config.md). Optional H2: `## Code Layout` for prompts-dir split if outline puts it at H2.
- **Verification**: (b) `test -f docs/overnight-operations.md && grep -c '^## ' docs/overnight-operations.md` ≥ 5 — pass if count ≥ 5.
- **Status**: [x] complete

### Task 4a: Write Architecture (dispatch + escalation half)
- **Files**: `docs/overnight-operations.md`
- **What**: Fill the first half of the Architecture H2: post-merge review + rework cycle (req 2 "review_dispatch"); per-task agent capabilities with the literal `_ALLOWED_TOOLS` list (req 2 "allowed_tools", req 10); prompts-dir split (req 2 "pipeline/prompts" + "overnight/prompts"); escalation system (req 2 "escalations.jsonl") with cycle-breaking (req 2 "Cycle-breaking").
- **Depends on**: [3]
- **Complexity**: complex
- **Context**: Research.md Codebase Analysis items 1–4, 7. Preserve exact-phrase constraints from spec Technical Constraints (forward-only phases, atomic writes). Follow `**Files**` / `**Inputs**` bolded run-in head pattern. No line numbers in code cross-refs. `_ALLOWED_TOOLS` list is documented literally (req 10).
- **Verification**: (b) `grep -c -E "review_dispatch|Post-Merge Review" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "allowed_tools|Per-Task Agent Capabilit" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "pipeline/prompts" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "overnight/prompts" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "escalations\.jsonl|Escalation System" docs/overnight-operations.md` ≥ 1 AND `grep -c -i "cycle-breaking" docs/overnight-operations.md` ≥ 1 — pass if every count is ≥ 1.
- **Status**: [x] complete

### Task 4b: Write Architecture (strategy + recovery + loop half)
- **Files**: `docs/overnight-operations.md`
- **What**: Fill the second half of the Architecture H2: strategy file (req 2 "overnight-strategy.json"); conflict recovery policy (req 2 "Conflict Recovery"); round loop; circuit breakers; signal handling; module reference table; interrupt.py startup recovery (req 2 "interrupt.py").
- **Depends on**: [4a]
- **Complexity**: complex
- **Context**: Research.md Codebase Analysis items 5, 6 + the round-loop/breakers/signals/modules content from `docs/overnight.md` lines 299-362 (extracted per task 8). Preserve exact-phrase constraints from spec Technical Constraints (repair cap numbers — do NOT unify). Module reference table uses `| Module | Role |` two-column format matching existing docs.
- **Verification**: (b) `grep -c -E "overnight-strategy\.json|Strategy File" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Conflict Recovery|trivial fast-path" docs/overnight-operations.md` ≥ 1 AND `grep -c "interrupt\.py" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Round Loop" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Circuit Breaker" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Module Reference|\| Module \| Role \|" docs/overnight-operations.md` ≥ 1 — pass if every count is ≥ 1.
- **Status**: [x] complete

### Task 5: Write Tuning section
- **Files**: `docs/overnight-operations.md`
- **What**: Fill Tuning H2. Covers: `--tier` concurrency (req 2 "--tier"); test gate + integration health flow (req 2 "Test Gate"); model selection matrix (tier × criticality → role); repair caps (two different numbers, DO NOT UNIFY — spec Technical Constraints).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Research.md Codebase Analysis items 8, 9. Model selection matrix should point to `docs/sdk.md` for detailed SDK model config (source-of-truth rule — req 6); this doc owns tier × criticality → role dispatch only. Repair caps: "single Sonnet→Opus escalation for merge conflicts" vs. "max 2 attempts for test-failure repair" — keep them as two distinct items with one-sentence rationale each.
- **Verification**: (b) `grep -c -E "\-\-tier|Concurrency Tuning" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Test Gate|integration_health" docs/overnight-operations.md` ≥ 1 — pass if each ≥ 1. Manual reviewer-check during task 15 confirms the two repair caps are documented as distinct with no unifying language.
- **Status**: [x] complete

### Task 6a: Write Observability (state files + schemas + report + logs)
- **Files**: `docs/overnight-operations.md`
- **What**: Fill first half of Observability H2: state file locations; escalations.jsonl schema; strategy.json schema; morning report generation (`report.py` — req 2 "report.py"); `agent-activity.jsonl` (req 2); log disambiguation table (`events.log` vs `pipeline-events.log` vs `agent-activity.jsonl`).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Research.md Codebase Analysis items for state files + the adversarial-identified gaps related to logs. Log disambiguation table: for each log, one-sentence "grep this when X." Schemas use fenced `json` blocks per existing doc convention.
- **Verification**: (b) `grep -c -E "report\.py|Morning Report Generation" docs/overnight-operations.md` ≥ 1 AND `grep -c "agent-activity\.jsonl" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Log Disambiguation" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "State File" docs/overnight-operations.md` ≥ 1 — pass if every count ≥ 1.
- **Status**: [x] complete

### Task 6b: Write Observability (lock + hooks + scheduled + dashboard + brain)
- **Files**: `docs/overnight-operations.md`
- **What**: Fill second half of Observability H2: `.runner.lock` PID mechanics (req 2); session hooks (SessionStart/End/notification) (req 2); scheduled-launch (req 2); dashboard state polling (req 2); `brain.py` with the disambiguation lede (req 12).
- **Depends on**: [6a]
- **Complexity**: simple
- **Context**: `brain.py` subsection's opening must disambiguate it from a "repair" agent before any other content — spec req 12. Dashboard polling: call out `claude/dashboard/poller.py` read-vs-atomic-replace behavior (research.md adversarial). Hooks: note the silent-failure mode (no log mechanism) per requirements/remote-access.md.
- **Verification**: (b) `grep -c -E "\.runner\.lock|Runner Lock" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Dashboard Polling|dashboard state" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Session Hooks|SessionStart|notification hooks" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "Scheduled Launch|scheduled-launch" docs/overnight-operations.md` ≥ 1 AND `grep -c "brain\.py" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "SKIP/DEFER/PAUSE" docs/overnight-operations.md` ≥ 1 — pass if every count ≥ 1.
- **Status**: [x] complete

### Task 7: Write Security, Internal APIs, and progressive-disclosure rationale
- **Files**: `docs/overnight-operations.md`
- **What**: Fill `## Security and Trust Boundaries` H2 (req 9): enumerate `--dangerously-skip-permissions`, `_ALLOWED_TOOLS` SDK-level bound, dashboard `0.0.0.0` unauthenticated, keychain prompt as session-blocking failure, "local network" ≠ "home network". Fill `## Internal APIs` H2: `orchestrator_io` (req 2, 13), `lifecycle.config.md` (req 2) + `apiKeyHelper` auth resolution (req 2). Add the progressive-disclosure rationale paragraph (req 13) in the preamble OR cross-reference to CLAUDE.md's rule.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Security section: one bullet per boundary, one-sentence threat model each, no scattered safety notes elsewhere. Internal APIs: `orchestrator_io` documented as a POINTER ("see `__all__` for sanctioned surface"), NOT an enumeration — spec Edge Cases "Appendix is justified only when the content is a reference lookup." `lifecycle.config.md`: document absence behavior per consumer (morning-review skips Section 2a; lifecycle complete skips test step). `apiKeyHelper`: the 4-step fallback from research.md. Progressive-disclosure paragraph: must contain the phrase "progressive disclosure" AND ≥3 sentences of rationale explaining how the agent-loading concept generalizes to human reader access patterns — spec req 13 (b). If placed in CLAUDE.md (per task 10 coordination), leave a one-line cross-link in the operations doc preamble and satisfy the ≥3 sentences in CLAUDE.md.
- **Verification**: (b) `grep -c "^## Security" docs/overnight-operations.md` = 1 AND `grep -c "orchestrator_io" docs/overnight-operations.md` ≥ 1 AND `grep -c "lifecycle\.config\.md" docs/overnight-operations.md` ≥ 1 AND `grep -c -E "apiKeyHelper|Auth Resolution" docs/overnight-operations.md` ≥ 1 AND the progressive-disclosure paragraph has ≥3 sentences (checked via `python3 -c "import re,sys; t=open('docs/overnight-operations.md').read()+open('CLAUDE.md').read(); m=re.search(r'(?is)progressive disclosure.{0,2000}', t); sys.exit(0 if m and m.group().count('.') >= 3 else 1)"` — pass if exit 0) — pass if every check holds.
- **Status**: [x] complete

### Task 8: Refactor `docs/overnight.md` (extraction + pointer paragraph + caller update)
- **Files**: `docs/overnight.md`, `README.md`, `docs/pipeline.md`, `docs/dashboard.md`, `docs/agentic-layer.md`, `CLAUDE.md`, any caller discovered by the comprehensive grep below
- **What**: Remove the extracted sections per spec req 3 (Authentication, Execution Phase/Round Loop/Circuit Breakers/Signal Handling/Module Reference, State Files, Conflict avoidance, Recovery: corrupt state, Recovery: merge conflict). Add one short paragraph near the top: "For mechanics, state files, recovery, and debugging procedures, see [overnight-operations.md](overnight-operations.md)." Prune the jump-to nav to list only what remains. Update every caller that references a removed anchor, discovered by the comprehensive grep in Context. Within `docs/overnight.md` itself, locate original cross-links by content (breadcrumb, jump-nav, in-text pointers) — do NOT rely on line numbers since they shift mid-edit. Every removed anchor that had callers gets updated to point at the new `overnight-operations.md#...` slug; the new slug must be read from the actual headings in `docs/overnight-operations.md` after tasks 4a/4b/5/6a/6b/7 have written it.
- **Depends on**: [4b, 5, 6b, 7]
- **Complexity**: complex
- **Context**: Extraction targets per research.md §Sections to move. Comprehensive caller enumeration: `grep -rn "overnight.md#" README.md CLAUDE.md docs/ skills/ retros/ backlog/ lifecycle/ requirements/ claude/reference/ claude/rules/ .github/ bin/ 2>/dev/null | grep -v "overnight-operations"`. Old anchors that disappear: `#authentication`, `#the-execution-phase`, `#the-round-loop`, `#circuit-breakers`, `#signal-handling`, `#module-reference`, `#state-files-and-artifacts`, `#conflict-avoidance-and-resource-protection`, `#recovery-corrupt-or-inconsistent-state`, `#recovery-merge-conflict-on-integration-branch`. For each hit, determine the new target slug by reading the corresponding heading in `docs/overnight-operations.md` (slug is GitHub-style: lowercase, spaces→hyphens, drop punctuation). If a new heading has merged or split versus the old (e.g., Round Loop + Circuit Breakers under one H3), exercise judgment to route the old anchor to the most specific match.
- **Verification**: (b) three conditions: (i) `grep -cE "^## Authentication|^## State Files|^### Module Reference|^### The Round Loop|^### Circuit Breakers|^### Signal Handling|^## The Execution Phase|^### Recovery: corrupt|^### Recovery: merge conflict|^### Conflict avoidance" docs/overnight.md` = 0; (ii) `grep -c "overnight-operations.md" docs/overnight.md` ≥ 1; (iii) `grep -rnE "overnight\.md#(authentication|the-execution-phase|the-round-loop|circuit-breakers|signal-handling|module-reference|state-files|conflict-avoidance|recovery-corrupt|recovery-merge)" README.md CLAUDE.md docs/ skills/ retros/ backlog/ lifecycle/ requirements/ claude/reference/ claude/rules/ .github/ bin/ 2>/dev/null | grep -v "overnight-operations" | wc -l` = 0 — pass if all three conditions hold.
- **Status**: [x] complete

### Task 9: Trim `docs/pipeline.md` deduplication
- **Files**: `docs/pipeline.md`
- **What**: Replace `§Recovery Procedures` (roughly lines 107-167) with a 1-2 sentence cross-link to `docs/overnight-operations.md` for orchestrator-side recovery behavior. Retain per-module Files/Inputs/Returns entries for `conflict.py`, `merge_recovery.py`, `integration_recovery.py`.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Keep the module reference table intact. The replaced content is orchestrator-perspective recovery flow; the retained content is pipeline-module internals. Source-of-truth rule per spec req 6.
- **Verification**: (b) `grep -c "overnight-operations.md" docs/pipeline.md` ≥ 1 — pass if count ≥ 1. Manual check during task 15 confirms no behavioral claim about post-merge review or recovery appears in both pipeline.md and overnight-operations.md.
- **Status**: [x] complete

### Task 10: Add source-of-truth rule to `CLAUDE.md`
- **Files**: `CLAUDE.md`
- **What**: Add a short convention block (1-4 lines) documenting the doc-ownership boundary per spec req 6: `docs/overnight-operations.md` owns round loop + orchestrator behavior; `docs/pipeline.md` owns pipeline-module internals; `docs/sdk.md` owns SDK model-selection mechanics. Include the "source of truth" phrase.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Insert under the existing `## Conventions` subsection near the bottom of `CLAUDE.md`. Keep it concise — one sentence naming the three docs, one sentence stating the rule, optional one-sentence rationale. Progressive-disclosure paragraph (req 13) can live here or in the operations doc preamble — task 7 chose one home; this task references it if that was CLAUDE.md.
- **Verification**: (b) `grep -F "overnight-operations.md" CLAUDE.md` returns ≥1 match AND `grep -Fi "source of truth" CLAUDE.md` returns ≥1 match — pass if both hold. Interactive/session-dependent manual check: the two greps match lines within the same paragraph or bullet.
- **Status**: [x] complete

### Task 11: Add pytest guarding `_ALLOWED_TOOLS` drift (doc ↔ code)
- **Files**: `tests/test_dispatch_allowed_tools.py` (new or equivalent name — author's choice if `tests/` has a different convention), `docs/overnight-operations.md` (read at test runtime to extract the documented snippet)
- **What**: Write a pytest that parses the documented tool allowlist from `docs/overnight-operations.md` at runtime and asserts `set(parsed_from_doc) == set(claude.pipeline.dispatch._ALLOWED_TOOLS)`. This catches both code drift (tool added/removed in dispatch.py without doc update) and doc drift (tool changed in doc without code update). Follow the precedent set by `tests/test_events_contract.py`, which parses a source-of-truth markdown file at runtime and cross-checks against a Python module.
- **Depends on**: [4a]
- **Complexity**: simple
- **Context**: Existing precedent: `tests/test_events_contract.py` reads a prompt markdown file, regex-extracts constants, and asserts against a Python module. Follow that pattern. Extraction method: the documented list appears in a fenced Python list literal (e.g., ```` ```python\n_ALLOWED_TOOLS = ["Read", ...]\n``` ````) or a bulleted list under a specific H3. Author chooses format during task 4a and documents the extraction regex here. Test reads `docs/overnight-operations.md` via a module-level constant path, extracts the list, and compares to `from cortex_command.pipeline.dispatch import _ALLOWED_TOOLS`. The test fails loudly with a diff if either side drifts. Include a `test -f` style precondition so a missing doc file produces a clear error rather than a silent pass.
- **Verification**: (a) `just test` — pass if exit code = 0 and the new test is reported as passed in output. The test itself is reviewer-auditable: its source shows that the doc file is opened/parsed, not a test-file literal.
- **Status**: [x] complete

### Task 12: Add cross-links from adjacent docs to operations doc
- **Files**: `docs/sdk.md`, `docs/dashboard.md`, `docs/agentic-layer.md`
- **What**: Add one-line cross-link from each to `docs/overnight-operations.md` in the appropriate reference section. Respects the source-of-truth boundary (these docs do not reproduce operations content; they point to it).
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Places to add: `docs/sdk.md` near the overnight-pointer (exists around line 263 in overnight.md currently); `docs/dashboard.md` in its dependencies/reference section; `docs/agentic-layer.md:~290` reference list (research.md flagged this location).
- **Verification**: (b) `grep -c "overnight-operations.md" docs/sdk.md docs/dashboard.md docs/agentic-layer.md` ≥ 3 — pass if count ≥ 3.
- **Status**: [x] complete

### Task 13: Run full test suite
- **Files**: (none modified)
- **What**: Run `just test` to verify the new pytest passes and no existing tests regress.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: Test command per `lifecycle.config.md:test-command: just test`.
- **Verification**: (a) `just test` — pass if exit code = 0.
- **Status**: [x] complete

### Task 14: Final verification sweep (per-requirement)
- **Files**: (none modified — verification only)
- **What**: Execute every spec-requirement acceptance check in order and record results in `lifecycle/{feature}/learnings/verification.md`. Fail-fast on any check that returns a non-passing result.
- **Depends on**: [8, 9, 10, 12, 13]
- **Complexity**: simple
- **Context**: The 13 spec requirements' acceptance criteria form the exact checklist. Include one row per requirement 1 through 13:
  - Req 1: `test -f docs/overnight-operations.md`
  - Req 2: 21 keyword-grep checks (per task 4a/4b/5/6a/6b/7 verifications rolled up)
  - Req 3: three greps (removed sections count=0, `overnight-operations.md` ≥1 in overnight.md, no broken anchor callers across the full caller surface)
  - Req 4: anchor resolution spot-check (interactive — 5 random positive resolutions)
  - Req 5: cross-link grep + manual no-dup read
  - Req 6: two CLAUDE.md greps
  - Req 7: `just test` confirms the pytest from task 11 passes (explicit — do NOT conflate with req 10)
  - Req 8: PR-body regex runs at PR time; task 14 records "to verify in PR"
  - Req 9: `grep -c "^## Security" docs/overnight-operations.md` = 1
  - Req 10: the pytest from task 11 verifies the documented list matches code (doc is the source being parsed, not a test-file literal)
  - Req 11: negative grep for line numbers + 5 random anchor resolutions
  - Req 12: manual disambiguation lede review
  - Req 13: two greps + ≥3-sentence rationale check (per task 7 verification)
- **Verification**: (b) `lifecycle/document-overnight-pipeline-operations-and-architecture/learnings/verification.md` contains a result row for each of the 13 requirements — `grep -c '^| Req' lifecycle/document-overnight-pipeline-operations-and-architecture/learnings/verification.md` ≥ 13 — pass if count ≥ 13 and every row's result column contains "pass" or "manual-ok".
- **Status**: [x] complete

### Task 15: Manual review pass (reviewer-judged items)
- **Files**: `lifecycle/document-overnight-pipeline-operations-and-architecture/learnings/verification.md` (appended)
- **What**: Author performs the interactive checks that are not automatable: pipeline.md no-duplication read, 5 random cross-reference anchor spot-checks, brain.py disambiguation lede review, progressive-disclosure rationale paragraph review, retros mining log coherence. Record notes in the same verification.md from task 14.
- **Depends on**: [14]
- **Complexity**: simple
- **Context**: This is the reviewer-judgment gate the spec accepts in lieu of automated coverage (Non-Requirement: "No automated gap-coverage checker"). Author approves own work before PR; PR reviewer performs the same pass independently.
- **Verification**: Interactive/session-dependent: reviewer-judgment items cannot be machine-verified; verification.md rows for these items read "manual-ok" with a one-sentence observation.
- **Status**: [x] complete

## Verification Strategy

End-to-end verification runs in tasks 13, 14, 15 in that order:
1. `just test` (task 13) — pytest passes + no regressions.
2. Per-requirement acceptance grep sweep (task 14) — all 13 spec requirements have verifiable acceptance results.
3. Manual reviewer-judgment pass (task 15) — interactive checks recorded.

The PR itself provides the final end-to-end verification: the PR body contains the req 8 retros-mining disposition log (binary-checked by the `gh pr view` grep); the PR reviewer independently performs the task 15 checks.

## Veto Surface

- **Task 4/5/6 sizing**: Architecture, Tuning, and Observability sections are marked `complex` and may each run 30-45 minutes of writing. If the author wants them broken into smaller tasks, split along the 21-gap subsection boundaries — but splitting loses section-level narrative coherence. Current sizing bets coherence > granularity.
- **Task 10 placement**: `CLAUDE.md` addition is 1-4 lines. If the progressive-disclosure rationale paragraph (req 13) lives in the operations doc preamble instead (per task 7), this task shrinks to the source-of-truth rule only.
- **Task 11 test scope**: the pytest parses `docs/overnight-operations.md` at runtime (following `tests/test_events_contract.py` precedent) and asserts set-equality with `_ALLOWED_TOOLS`. The author may choose to test additional load-bearing constants (repair caps, tier limits) — spec declined to bundle those; adding them expands scope beyond what was approved.
- **Task 8 caller enumeration**: the plan's grep list covers the anchors research.md identified. If the grep surfaces additional anchor callers in unexpected places (skill files, retros, lifecycle artifacts), the author updates those too — this is inherent to a docs refactor, not a surprise.

## Scope Boundaries

Maps to spec Non-Requirements:
- No runtime/behavior changes outside `tests/test_dispatch_allowed_tools.py`.
- No automated gap-coverage checker (`just docs-audit` is out of scope).
- No reorganization of `docs/agentic-layer.md`, `docs/sdk.md`, `docs/dashboard.md`, `docs/backlog.md`, or `docs/setup.md` beyond optional cross-link additions (task 12).
- No new doc index or landing page.
- No enforcement of the orchestrator `rationale` field convention.
- No expansion of `orchestrator_io` API.
- No full rewrite of `docs/pipeline.md` — only `§Recovery Procedures` is trimmed (task 9).
- No "last validated" date headers on individual procedures.
- Drift tests for the other 16 exact-phrase constraints (forward-only phases, atomic writes, repair caps, tier limits, escalation ladder, etc.) are out of scope — convention-only enforcement via CLAUDE.md is accepted.
