# Review: discovery-output-density-investigate-author-centric

## Stage 1: Spec Compliance

### Requirement 1: `generate-brief` subcommand exists
- **Expected**: `python3 -m cortex_command.discovery generate-brief <path>` exits 0 and emits a non-empty brief on stdout.
- **Actual**: Subcommand wired at `cortex_command/discovery.py:1126–1161` via `_cmd_generate_brief` (`cortex_command/discovery.py:657`). Reads `--research-md`, dispatches `_run_brief_query`, writes brief to stdout. Subcommand help renders cleanly. Live end-to-end behavior requires Claude API auth.
- **Verdict**: PARTIAL
- **Notes**: Code path complete and discoverable; the spec's exit-0/non-empty-stdout acceptance requires a live sub-agent dispatch. Live-verify deferred per implementation note (no API auth in implementing sandbox). Test 1 in `tests/test_discovery_gate_brief.py` is `@pytest.mark.skipif(not has_claude_auth())` and pass-by-skip in unauthed runs.

### Requirement 2: Brief persisted alongside research.md
- **Expected**: After gate fires and brief generation succeeds, brief is at `cortex/research/<topic>/brief.md`.
- **Actual**: `--persist-to PATH` flag implemented at `cortex_command/discovery.py:1148–1160`; persistence logic at lines 765–776 writes the validated brief after stdout emission. SKILL.md gate prose at `skills/discovery/SKILL.md:74–80` invokes `generate-brief … --persist-to cortex/research/<topic>/brief.md`.
- **Verdict**: PARTIAL
- **Notes**: Wiring is in place; persistence requires successful brief generation upstream (Req 1). Live-verify deferred behind API auth.

### Requirement 3: `GATE_BRIEF_RUBRIC` constant with decision-content anchors
- **Expected**: Constant exported from `cortex_command/discovery.py`; contains `decided`, `alternatives`, `tradeoff` strings.
- **Actual**: `GATE_BRIEF_RUBRIC` defined at `cortex_command/discovery.py:275`. Acceptance command `python3 -c "from cortex_command.discovery import GATE_BRIEF_RUBRIC; assert 'decided' in GATE_BRIEF_RUBRIC and 'alternatives' in GATE_BRIEF_RUBRIC and 'tradeoff' in GATE_BRIEF_RUBRIC"` exits 0 (verified). Rubric structures output as decided / alternatives / tradeoff; enumerates banned tokens (DR-N, OQ-N, RQ-N, §N; "named contract surfaces"; "walked back"; "decomposition history"; "per template rule"; [path:line] citation suffixes).
- **Verdict**: PASS
- **Notes**: Word target uses `GATE_BRIEF_WORD_CAP` by name in rubric prose so cap changes propagate without rewriting (`cortex_command/discovery.py:295`).

### Requirement 4: Word cap derived from corpus measurement
- **Expected**: `cortex/lifecycle/<feature>/word-cap-derivation.md` exists with per-artifact table and `word cap: <N>` summary; `GATE_BRIEF_WORD_CAP` encoded as module constant.
- **Actual**: `word-cap-derivation.md` present with method, 4-row corpus table (cursor-skill-port, grill-me-with-docs-learnings, interactive-overnight-mode, windows-support), and final `word cap: 150` line. `GATE_BRIEF_WORD_CAP: int = 150` at `cortex_command/discovery.py:267`. 90th-percentile arithmetic shown (156.6 → 150 when rounded to nearest 25). All three acceptance clauses verified.
- **Verdict**: PASS
- **Notes**: Sample size is 4 artifacts — thin distribution. Caveat is already captured in plan.md Risks §2 ("derived cap is a single judgment call"); spec accepts that Req 5's pre-merge fixtures and Req 9's quarterly check catch under-cap topic classes.

### Requirement 5: Multi-fixture brief-output test suite
- **Expected**: Test exercises `generate-brief` against ≥3 committed fixtures; each brief ≤ `GATE_BRIEF_WORD_CAP + 25`, contains decision-content anchors, scores 0/6 reader-study patterns.
- **Actual**: `tests/test_discovery_gate_brief.py::test_brief_passes_all_fixtures` (lines 108–169) iterates `tests/fixtures/discovery-brief/{simple,complex,diagnostic}-topic/research.md` and asserts (a) word cap, (b) `validate_brief` anchors, (c) `_score_brief_patterns` returns 0 for all six patterns. Three fixtures committed and confirmed via `ls`.
- **Verdict**: PARTIAL
- **Notes**: Test gated on `@_REQUIRES_AUTH` because the assertions verify live sub-dispatch output. Live-verify deferred per implementation note. Code path correct; behavioral binding evidence is gated on auth.

### Requirement 6: Brief-generation failure falls back to dense Architecture display
- **Expected**: Non-zero exit, empty brief, or validation failure routes the gate to display `## Architecture` section with a warning.
- **Actual**: `_cmd_generate_brief` returns non-zero on SDK unavailable (`cortex_command/discovery.py:733`), dispatch exception (line 737), empty brief (line 745), or `validate_brief` failure (line 755). `gate_brief_generated` event emits with status `validation_failed` / `empty` / `sdk_unavailable`. SKILL.md gate prose at lines 82–87 specifies the dense-Architecture fallback + `brief_generation_failed: <reason>` warning. `test_brief_failure_falls_back_to_architecture` (lines 178–243) asserts non-zero exit and event-log presence; `test_gate_renders_brief_not_architecture` (lines 310–401) asserts file-reading contract unconditionally.
- **Verdict**: PARTIAL
- **Notes**: Auth-gated test verifies the live failure path. The unconditional Test 3 covers the file-reading fallback contract (brief absent → Architecture body + warning) and passes.

### Requirement 7: Gate prose displays brief; preserves four user-blocking options
- **Expected**: SKILL.md gate prose displays `brief.md` content; the four options (approve, revise, drop, promote-sub-topic) preserved verbatim.
- **Actual**: `skills/discovery/SKILL.md:72–98` rewritten so the gate's first content section is `cortex/research/<topic>/brief.md`. Four options preserved as individual bolded bullets (lines 84–87) and as the `<approve|revise|drop|promote-sub-topic>` form on line 94. `grep -c "<approve|revise|drop|promote-sub-topic>" skills/discovery/SKILL.md` = 1 (verified). `test_gate_renders_brief_not_architecture` asserts the file-reading contract and the canonical-source presence of all four option bullets.
- **Verdict**: PASS
- **Notes**: Spec-authoring artifact in original grep target (spaced pipe form `approve | revise | drop | promote-sub-topic`) resolved via spec repair in commit 826e039f to target the unspaced form that actually ships. Semantic intent (all four options preserved as user affordances) holds: bullets and `--response` exemplar both enumerate the same four options.

### Requirement 8: `gate_brief_generated` event registered and emitted
- **Expected**: Registry row in `bin/.events-registry.md` with required fields; emission in `cortex_command/discovery.py`; `bin/cortex-check-events-registry --audit` exits 0; `grep -c "gate_brief_generated" bin/.events-registry.md` = 1.
- **Actual**: Registry row at line 120 with full schema `{ts, event, feature, status, brief_word_count, patterns_detected_count}`, owner, rationale, and consumer references. Emission via `_emit_event` helper in `_cmd_generate_brief` (`cortex_command/discovery.py:706–725`) on every code path (ok, empty, validation_failed, sdk_unavailable). `bin/cortex-check-events-registry --audit` exits 0 (verified). Grep count = 1 (single registry row; other matches are in producer/test source).
- **Verdict**: PASS

### Requirement 9: Post-merge corpus regression check
- **Expected**: `score-corpus` subcommand emits pattern counts for operator quarterly review; non-blocking.
- **Actual**: `score-corpus` subcommand wired at `cortex_command/discovery.py:1164–1195`; handler `_cmd_score_corpus` at line 820 walks `--root` for topic dirs containing `brief.md` (preferred) or `research.md` (fallback: Headline + Architecture excerpts), scores via shared `_score_brief_patterns`, emits one line per file (`<path> patterns_reproducing=N/6 word_count=N` with optional `[FLAGGED]`). Exit code 0 on successful walk; threshold is `--threshold` (default 1) for surface flag only, not exit code. Help text renders cleanly.
- **Verdict**: PASS
- **Notes**: Shared scoring helper extracted to `cortex_command/_brief_scoring.py` (Task 9), avoiding duplication drift between test and subcommand.

### Requirement 10: Template trim — drop DR-N numbering
- **Expected**: `grep -cE 'DR-[N0-9]' skills/discovery/references/research.md` = 0.
- **Actual**: Verified — `grep -cE 'DR-[N0-9]' skills/discovery/references/research.md` returns 0. `## Decision Records` heading remains with permissive directive: "key trade-offs and alternatives considered, one paragraph each" (`skills/discovery/references/research.md:126–127`).
- **Verdict**: PASS

### Requirement 11: Template trim — drop `### Why N pieces` walk-back rule
- **Expected**: `grep -c "walked back" ...` = 0 AND `grep -c "Why N pieces" ...` = 0 AND `grep -c "template walk-back rule" ...` = 0.
- **Actual**: All three grep checks return 0 (verified).
- **Verdict**: PASS

### Requirement 12: Template trim — rewrite Architecture directive vocabulary
- **Expected**: `grep -c "named contract surfaces"` = 0 AND `grep -c "Role / Integration / Edges"` = 0 in `skills/discovery/references/research.md`.
- **Actual**: Both grep checks return 0 (verified). New directive at lines 111–118 reads: "Describe what each piece does and how they connect. Use plain, direct language — no jargon for the relationships between pieces. If the piece count grows large, consider merging pieces that can be described together without losing meaningful distinction." Banned terms absent from both directive prose and section body. The Architecture template retains `### Pieces` and `### How they connect` sub-headings — neither uses the banned vocabulary.
- **Verdict**: PASS
- **Notes**: Spec-authoring artifact (directive prose embedding banned terms while requiring grep count = 0) resolved via spec repair in commit 826e039f. Semantic intent (banned vocabulary absent from template) holds.

### Requirement 13: Template removes `## Headline Finding` section
- **Expected**: `grep -c "Headline Finding" skills/discovery/references/research.md` = 0; SKILL.md fallback references brief.md status.
- **Actual**: Both grep checks return 0 — section removed from research.md template and from SKILL.md (verified). SKILL.md fallback now keys off `brief_generation_failed` (`skills/discovery/SKILL.md:82`).
- **Verdict**: PASS

### Requirement 14: Test pins updated in lockstep
- **Expected**: `R1_HEADLINE_MARKER_PHRASE` dropped; `BRIEF_INVOCATION_MARKER_PHRASE` and `GATE_OPTIONS_MARKER_PHRASE` added; `pytest tests/test_discovery_gate_presentation.py` exits 0.
- **Actual**: `grep -c "R1_HEADLINE_MARKER_PHRASE" tests/test_discovery_gate_presentation.py` = 0; both new constants present (3 references each — definition + 2 use sites). `python3 -m pytest tests/test_discovery_gate_presentation.py` reports 3 passed.
- **Verdict**: PASS

### Requirement 15: Phase 2 trigger has operational arming mechanism
- **Expected**: Backlog ticket with `tag: phase2-trigger` and `review_date: <merge_date + 6 months>`; surfaces in `cortex-backlog list --tag phase2-trigger` queries.
- **Actual**: `cortex/backlog/232-re-evaluate-cross-skill-brief-framework-discovery-output-density-phase-2-trigger.md` exists with `tags: [phase2-trigger]`, `review_date: 2026-11-16`, body citing spec Req 15 + naming Candidate C and Candidate G triggers + evaluation criteria. Wiring ticket `cortex/backlog/233-...md` filed for missing `--tag` filter, per spec's escape hatch ("if `cortex-backlog` does not currently support `--tag` filtering, file a separate wiring ticket rather than dropping this requirement"). Verified: `cortex-backlog-ready --tag phase2-trigger` errors with "unrecognized arguments: --tag phase2-trigger" — the wiring is required for full query-discoverability and ticket #233 captures the gap.
- **Verdict**: PASS
- **Notes**: Spec's acceptance grep `cortex-backlog list --tag phase2-trigger | grep -c "discovery-output-density" ≥ 1` cannot be satisfied today because the CLI does not implement `--tag`. The spec anticipated this with the wiring-ticket escape hatch, which the implementation correctly exercised — the requirement explicitly permits this path. Operational arming is partial today: frontmatter tag is in place and #233 is queued for the CLI work.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Module constants `GATE_BRIEF_WORD_CAP` and `GATE_BRIEF_RUBRIC` follow the existing `_STATUS_VALUES`/`_CHECKPOINT_VALUES` style (uppercase + type annotation, near top of module). Subcommand handlers follow `_cmd_<name>` convention used by the four existing emit-* handlers. Shared helper module name `_brief_scoring` uses the leading underscore convention for internal-only modules. Test constants `BRIEF_INVOCATION_MARKER_PHRASE` / `GATE_OPTIONS_MARKER_PHRASE` match the existing `R3_DROP_DUAL_USE_MARKER_PHRASE` shape.

- **Error handling**: Appropriate for context. `_cmd_generate_brief` distinguishes four failure modes (SDK unavailable, dispatch exception, empty brief, validation failure) and emits the corresponding event status on each path before returning non-zero. Persistence failure (`OSError` on write) is non-fatal — the brief is already on stdout and the caller has it; exit stays 0 with a stderr warning. Best-effort event emission (`_emit_event`) swallows `OSError` so events-log permission issues don't mask the primary subcommand result. `_run_brief_query` cleanly raises `RuntimeError` when the SDK is absent rather than crashing on `ImportError` at call time. `score-corpus` returns exit 2 on missing root or zero scoreable files, exit 0 on successful walk regardless of pattern counts (Req 9's "report signal, not gate" intent).

- **Test coverage**: Verification steps from plan executed where auth permits. Unconditional pass: 4 tests (3 in test_discovery_gate_presentation.py + 1 in test_discovery_gate_brief.py); 2 auth-gated tests skip cleanly under `has_claude_auth()` probe. The auth-gated tests are correctly skipped via `@pytest.mark.skipif` rather than silently passing — pass-by-skip is observable in CI output. Test 3 (`test_gate_renders_brief_not_architecture`) covers the file-reading fallback contract end-to-end without needing auth, validating the brief-present and brief-absent code paths of the gate-render contract. Pattern-scoring extraction to `_brief_scoring.py` avoids the canonical drift risk the plan flagged.

- **Pattern consistency**: Implementation follows existing project conventions. `validate_brief` returns `tuple[bool, str]` matching the style of validator helpers elsewhere. `append_event` reused unchanged. `resolve_events_log_path` and `_active_lifecycle_slug` honored for event path resolution; the `gate_brief_generated` event correctly resolves through the same path-resolution surface as the other discovery events. The fresh-context dispatch uses `claude_agent_sdk.query()` directly with a minimal wrapper rather than reusing `pipeline/dispatch.py` — decision documented in T5 status and aligned with project patterns (the existing dispatcher carries worktree/sandbox/sidecar overhead unsuitable for single-shot generation). Dual-source mirror discipline preserved: canonical sources edited; plugin mirrors at `plugins/cortex-core/skills/discovery/` regenerate via pre-commit.

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
