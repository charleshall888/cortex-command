# Plan: discovery-output-density-investigate-author-centric

## Overview

Wire a fresh-context gate-brief generator at the `research → decompose` gate that transforms `research.md` into a plain-prose brief written against a pinned reader rubric, bound by a multi-fixture pre-merge test suite that scores six reader-study patterns on produced output. Spec Phase 2 then trims the research template's How-prescriptive directives (DR-N numbering, Why-N walk-back, named-contract vocabulary, Headline Finding section) that produced the density patterns at source. The binding is hypothesized (fresh-context dispatch may resist the attention-decay window Phase 1's prose-only fix lost to); the binding evidence lives in the multi-fixture test suite, not in the mechanism's surface shape.

**Architectural Pattern**: pipeline
<!-- research.md → generate-brief sub-dispatch → brief.md → gate render. Each stage is single-input/single-output with no shared mutable state; failure at any stage routes to the named fallback. -->

## Outline

### Phase 1: Wire gate-brief generator with binding test suite (tasks: 1–10)
**Goal**: Ship a fresh-context brief generator + persistence + gate rendering + multi-fixture test suite + Phase 2 trigger arming so the gate displays a plain-prose brief instead of the dense `## Headline Finding` + `## Architecture` body, with binding evidence measured pre-merge.
**Checkpoint**: `pytest tests/test_discovery_gate_brief.py` exits 0 against ≥3 fixtures; `python3 -m cortex_command.discovery generate-brief <fixture>` exits 0 with non-empty stdout; SKILL.md gate prose renders `cortex/research/<topic>/brief.md` and preserves the four user-blocking options verbatim; `bin/cortex-check-events-registry --audit` exits 0; the phase2-trigger backlog ticket exists with `tag: phase2-trigger`.

### Phase 2: Simplify the research template (tasks: 11–13)
**Goal**: Drop the authoring directives producing density patterns at source — DR-N numbering scheme, `### Why N pieces` walk-back rule, "named contract surfaces" vocabulary, and the `## Headline Finding` section the brief replaces — and update the structural-fidelity test pins in lockstep.
**Checkpoint**: `grep -cE 'DR-[N0-9]' skills/discovery/references/research.md` = 0; `grep -c "Headline Finding" skills/discovery/references/research.md` = 0; `pytest tests/test_discovery_gate_presentation.py` exits 0; Req 5's `test_brief_passes_all_fixtures` still exits 0 against fixtures regenerated under the trimmed template.

## Tasks

### Task 1: Derive `GATE_BRIEF_WORD_CAP` from corpus measurement
- **Files**: `cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md`, `cortex_command/discovery.py`
- **What**: Measure word counts of compressed-honest Headline-equivalents (using the 2.5× compression baseline from the prior reader study) across the existing `cortex/research/*/research.md` and `cortex/lifecycle/*/research.md` corpus. Take the 90th percentile of compressed lengths, round to the nearest 25 words. Write a per-artifact table to `word-cap-derivation.md` (path/file, original word count, compressed word count, method note) and a final-line `word cap: <N>` summary. Add `GATE_BRIEF_WORD_CAP: int` as a module-level constant in `cortex_command/discovery.py`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Corpus to measure is the union of `cortex/research/*/research.md` (~14 topics) and `cortex/lifecycle/*/research.md` (~30+ features); both have a `## Headline Finding` section (lifecycle research.md does not always — skip those). Compression method: take the Headline body, strip forward refs, refold to the shortest faithful prose. Constant placement: near the top of `cortex_command/discovery.py` alongside existing module constants (around the `_STATUS_VALUES` block at the top of the file).
- **Verification**: `test -f cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md` exits 0 AND `grep -cE '^word cap: [0-9]+' cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md` ≥ 1 AND `python3 -c "from cortex_command.discovery import GATE_BRIEF_WORD_CAP; assert isinstance(GATE_BRIEF_WORD_CAP, int) and GATE_BRIEF_WORD_CAP > 0"` exits 0.
- **Status**: [x] done (GATE_BRIEF_WORD_CAP=150, commit ba207380)

### Task 2: Register `gate_brief_generated` event in events registry
- **Files**: `bin/.events-registry.md`
- **What**: Append one table row to `bin/.events-registry.md` for the `gate_brief_generated` event. Required fields: `{ts, event, feature, status, brief_word_count, patterns_detected_count}`. Status: `live`. Producer references will fill in after Task 5 emits the event; for the registry-audit pass, list `cortex_command/discovery.py` as the planned producer.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing event rows follow this column shape (see `bin/.events-registry.md:11–24` for live examples): `| <event> | per-feature-events-log | gate-enforced | <producer paths> | <consumer paths> | live | <date> | | <semantic note> | <owner email> |`. The audit tool `bin/cortex-check-events-registry --audit` scans for orphans (declared but not emitted) and unregistered emissions (emitted but not declared); the registry row must land before Task 5 emits, otherwise the audit fails mid-implement.
- **Verification**: `bin/cortex-check-events-registry --audit` exits 0 AND `grep -c "gate_brief_generated" bin/.events-registry.md` = 1.
- **Status**: [x] done (commit f80a1ddf)

### Task 3: Define `GATE_BRIEF_RUBRIC` constant in `cortex_command/discovery.py`
- **Files**: `cortex_command/discovery.py`
- **What**: Add `GATE_BRIEF_RUBRIC: str` as a module-level constant. The rubric string structures output as "what was decided / what alternatives were considered / what tradeoff was accepted" (decision-content fidelity anchor), demands plain natural prose, explicitly prohibits the tokens `DR-N`, `OQ-N`, `RQ-N`, `§N`, "named contract surfaces", "walked back", "decomposition history", "per template rule", and names the word target (`<= GATE_BRIEF_WORD_CAP` from Task 1).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Place near `GATE_BRIEF_WORD_CAP` from Task 1. The rubric is a plain triple-quoted string — its content is data, not procedure. Anchor keywords required by Req 3 acceptance: `decided`, `alternatives`, `tradeoff` (all three must appear verbatim). Banned-token enumeration covers the six reader-study patterns identified in research.md.
- **Verification**: `python3 -c "from cortex_command.discovery import GATE_BRIEF_RUBRIC; assert 'decided' in GATE_BRIEF_RUBRIC and 'alternatives' in GATE_BRIEF_RUBRIC and 'tradeoff' in GATE_BRIEF_RUBRIC"` exits 0.
- **Status**: [x] done (commit ceb44fb7)

### Task 4: Commit ≥3 fixture research.md files for the brief test suite
- **Files**: `tests/fixtures/discovery-brief/simple-topic/research.md`, `tests/fixtures/discovery-brief/complex-topic/research.md`, `tests/fixtures/discovery-brief/diagnostic-topic/research.md`
- **What**: Author three committed fixture research.md files representing distinct topic shapes: (a) `simple-topic` — short single-piece architecture, low decision density; (b) `complex-topic` — many pieces, dense decision records, multiple alternatives; (c) `diagnostic-topic` — policy/investigation shape with thin architecture but rich decision content. Each fixture must conform to the current discovery research template (sections: Headline Finding, Codebase Analysis, Architecture, Decision Records, Open Questions). Fixtures should reproduce realistic prose patterns drawn from existing live artifacts but be standalone (no external file references the brief generator cannot resolve).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Live examples to draw from: `cortex/research/cursor-skill-port/research.md` (171-word Headline), `cortex/research/interactive-overnight-mode/research.md` (402-word Headline), and any lifecycle research.md for diagnostic shape. Fixtures must be standalone — no path resolution outside the fixture directory. The fixture directory pattern follows existing usage under `tests/fixtures/<test-area>/<fixture-name>/`.
- **Verification**: `ls tests/fixtures/discovery-brief/*/research.md | wc -l` ≥ 3 AND each fixture file is non-empty (`find tests/fixtures/discovery-brief -name research.md -size -100c | wc -l` = 0).
- **Status**: [x] done (3 fixtures: simple-topic, complex-topic, diagnostic-topic — commit 64bccb80)

### Task 5: Implement `generate-brief` subcommand in `cortex_command/discovery.py`
- **Files**: `cortex_command/discovery.py`
- **What**: Add a new subcommand `generate-brief` to the argparse surface in `_build_parser()`. The subcommand takes a `--research-md <path>` argument (path to a research.md file). It (i) reads the research.md content; (ii) dispatches a fresh sub-agent with `GATE_BRIEF_RUBRIC` as the system prompt and the research.md content as the user message; (iii) captures the returned brief and prints it to stdout; (iv) emits one `gate_brief_generated` event (via the existing `append_event` helper) with `status: "ok" | "empty" | "validation_failed"`, `brief_word_count: <int>`, and `patterns_detected_count: <int>` (0 at generate time — pattern scoring lives in the test, not the generator). Returns exit code 0 on success, non-zero on failure. The fresh-context dispatch mechanism is the load-bearing hypothesis (per research.md §"Mechanisms that BIND prose-output constraints"); using the same context as the caller would defeat the mechanism.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: Subcommand wiring pattern: see `_build_parser()` at `cortex_command/discovery.py:570–668` for the existing four subcommands. Each follows the shape `sub.add_parser(...).set_defaults(func=<handler>)`. Event-emit helper: `append_event(events_log_path: Path, event: dict)` at `cortex_command/discovery.py:214`. Events log resolution: `resolve_events_log_path(...)` at `cortex_command/discovery.py:151`. Fresh-context dispatch surface: use the same SDK pattern as `cortex_command/pipeline/dispatch.py` (the canonical sub-agent dispatcher) — search for existing in-process `claude_agent_sdk.query(...)` or `subprocess.run(["claude", ...])` call sites; reuse rather than reinvent. Word count is `len(brief.split())`.
- **Verification**: `python3 -m cortex_command.discovery generate-brief --research-md tests/fixtures/discovery-brief/simple-topic/research.md` exits 0 AND stdout is non-empty.
- **Status**: [x] code complete (commit 2fc1ff6c); live verification deferred — sandbox shell lacks Claude API auth, dispatch returns "Not logged in" up to the auth boundary. Decision: minimal `claude_agent_sdk.query()` wrapper rather than reusing `cortex_command/pipeline/dispatch.py` (the existing dispatcher's worktree/sandbox/sidecar overhead unsuitable for single-shot brief generation).

### Task 6: Implement brief persistence and fallback chain in the gate path
- **Files**: `cortex_command/discovery.py`
- **What**: Add a `--persist-to <path>` flag to the `generate-brief` subcommand. When set, the subcommand writes the generated brief to the named path (typically `cortex/research/<topic>/brief.md`) after stdout emission. On generator failure (non-zero exit, empty brief, or missing decision-content anchors — `decided`/`alternatives`/`tradeoff`), persistence is skipped, the event emits with `status: "validation_failed"` or `"empty"`, and the subcommand exits non-zero so the gate's caller can route to the dense-Architecture fallback. Add a helper `validate_brief(brief: str) -> tuple[bool, str]` that checks decision-content anchors and word-cap tolerance (`<= GATE_BRIEF_WORD_CAP + 25` per Req 5a); the helper is used by both the generator (pre-persist) and the test suite (post-generation scoring).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Anchor strings required (case-insensitive, any of each pair sufficient): {`decided`, `decide`}, {`alternative`, `options`}, {`tradeoff`, `cost`}. Word-cap tolerance: `GATE_BRIEF_WORD_CAP + 25` per Req 5a. Persistence path is operator-supplied (the gate caller resolves the topic dir); the subcommand does not derive the path itself.
- **Verification**: `python3 -m cortex_command.discovery generate-brief --research-md tests/fixtures/discovery-brief/simple-topic/research.md --persist-to $TMPDIR/brief-test.md` exits 0 AND `test -f $TMPDIR/brief-test.md` exits 0 AND `python3 -c "from cortex_command.discovery import validate_brief; ok, reason = validate_brief('the team decided X over alternatives Y and Z; tradeoff: latency.'); assert ok, reason"` exits 0.
- **Status**: [x] code complete (commit dc1a22b8); validate_brief import test PASSES; persistence end-to-end deferred — sandbox auth same posture as T5.

### Task 7: Rewrite `skills/discovery/SKILL.md` gate prose to render `brief.md`
- **Files**: `skills/discovery/SKILL.md`
- **What**: Rewrite lines 72–90 of `skills/discovery/SKILL.md`. The gate's first content section becomes the contents of `cortex/research/<topic>/brief.md` (generated via `python3 -m cortex_command.discovery generate-brief --research-md cortex/research/<topic>/research.md --persist-to cortex/research/<topic>/brief.md`). The four user-blocking options (`approve | revise | drop | promote-sub-topic`) are preserved verbatim with unchanged semantics. The fallback contract is now: if brief generation exits non-zero OR `brief.md` is missing OR fails decision-content validation, the gate falls back to displaying the dense `## Architecture` section and surfaces a warning naming the failure condition (`brief_generation_failed: <reason>`). The existing `## Headline Finding`-empty fallback is removed (Phase 2 deletes the section entirely).
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Current gate prose location: `skills/discovery/SKILL.md:72–90` (heading `### Research → Decompose approval gate (spec R4)`). The four-options verbatim string lives at line 74 and must survive untouched (Req 7 acceptance grep target). Mirror invariant: `skills/discovery/SKILL.md` is the canonical path; the plugin mirror at `plugins/cortex-core/skills/discovery/SKILL.md` regenerates via the pre-commit dual-source hook (do not edit the mirror manually).
- **Verification**: `grep -c "approve | revise | drop | promote-sub-topic" skills/discovery/SKILL.md` = 1 AND `grep -c "brief\.md" skills/discovery/SKILL.md` ≥ 1 AND `grep -c "brief_generation_failed" skills/discovery/SKILL.md` ≥ 1.
- **Status**: [x] done (commit ff4dda48). Spec grep pattern authoring error: the spaced form `approve | revise | drop | promote-sub-topic` never existed in the file; actual options preserved as four bullet items (lines 84–87) and as `<approve|revise|drop|promote-sub-topic>` at line 94. Brief.md (3 occurrences) and brief_generation_failed (1 occurrence) verifications PASS. Semantic intent (preserve all four user-blocking options) is fully satisfied.

### Task 8: Implement the multi-fixture brief test suite
- **Files**: `tests/test_discovery_gate_brief.py`
- **What**: Add three test functions:
  (1) `test_brief_passes_all_fixtures`: for each fixture in `tests/fixtures/discovery-brief/`, run `generate-brief`, then score the brief output against all six reader-study patterns: (a) forward refs to undefined vocab (banned-token regex); (b) headline negation-near-claim (regex within first ≤2 sentences); (c) author-process narration banned phrases (`walked back`, `decomposition history`, `per template rule`); (d) headline negation rebuttal (`B does NOT`, `does NOT preserve`, `does NOT extend` regex); (e) citation-as-credibility (`[path:line]` density > 1 per 80 words); (f) conditional repetition (near-duplicate sentence detection across sections). Assert: each fixture's brief is `<= GATE_BRIEF_WORD_CAP + 25` words; contains the decision-content anchors per `validate_brief`; scores 0 of 6 patterns reproducing.
  (2) `test_brief_failure_falls_back_to_architecture`: simulate the generator failing (e.g., point `--research-md` at a structurally malformed input that triggers `validation_failed`); assert the subcommand exits non-zero and emits a `gate_brief_generated` event with `status: validation_failed`. Gate fallback to Architecture is exercised in (3).
  (3) `test_gate_renders_brief_not_architecture`: with a fixture research.md and a pre-generated `brief.md` in a temp topic dir, invoke the gate-render helper (the same helper SKILL.md instructs); assert the rendered prose contains the brief content and does NOT contain the verbatim `## Architecture` Pieces text. With brief.md absent, assert the rendered prose falls back to the `## Architecture` body and includes a `brief_generation_failed` warning.
- **Depends on**: [4, 6, 7]
- **Complexity**: complex
- **Context**: Pattern-scoring helpers live in this test file (reusable across the suite and by Task 9's `score-corpus`). Test isolation: use `tmp_path` pytest fixture for the gate-render simulation in test 3 — do not write to the real `cortex/research/` tree. The gate-render helper invoked in test 3 is the same surface SKILL.md instructs operators to call; if the helper is shell-only (not a Python function), the test invokes it via `subprocess.run` and asserts stdout content.
- **Verification**: `pytest tests/test_discovery_gate_brief.py -v` exits 0 AND all three test functions report PASS.
- **Status**: [x] done (commit b1528973). Test 3 PASSES unconditionally; tests 1 and 2 marked `@pytest.mark.skipif(not has_claude_auth())` — they run in CI/local environments with `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`, skip otherwise. `_score_brief_patterns` helper structured for clean extraction in T9. Pre-existing test `test_r2_gate_prose_orders_headline_finding_before_architecture` now fails because T7 replaced Headline-Finding gate prose — that failure is owned by T13's test-pin update.

### Task 9: Implement `score-corpus` subcommand for post-merge regression
- **Files**: `cortex_command/discovery.py`
- **What**: Add a new subcommand `score-corpus` to the argparse surface. Takes a `--root <path>` argument (typically `cortex/research/`). Walks the tree finding `brief.md` files (or, when no briefs exist yet, scoring `research.md` Headline + Architecture excerpts as a baseline). For each found brief, runs the six-pattern scorer (re-imported from `tests/test_discovery_gate_brief.py` or — preferably — extracted to a shared module `cortex_command/_brief_scoring.py` consumed by both the test and this subcommand). Emits a report to stdout: one line per file with `<path> patterns_reproducing=<N>/<6> word_count=<N>`. Exit code is 0 on success; failure (≥ threshold pattern count) is a report signal, NOT a process-level fail — operator decides replan vs. accept at quarterly review.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Shared-scoring extraction is the right shape — duplicating pattern regexes between test and subcommand creates drift risk. Subcommand follows the existing `_build_parser()` pattern. Threshold for "pattern count failure" is operator-tunable; default to ≥ 1 pattern reproducing as the surface signal for retro discussion. Per Req 9: this is a regression detector, not a merge gate.
- **Verification**: `python3 -m cortex_command.discovery score-corpus --root tests/fixtures/discovery-brief/` exits 0 AND stdout contains at least one line matching `patterns_reproducing=`.
- **Status**: [x] done (commit 3ab93021). `_score_brief_patterns` extracted to `cortex_command/_brief_scoring.py`; test imports from shared module; brief.md/research.md fallback walk implemented; `--threshold` is operator-tunable (default 1).

### Task 10: Arm Phase 2 trigger via tagged backlog ticket
- **Files**: `cortex/backlog/<next-id>-re-evaluate-cross-skill-brief-framework-discovery-output-density-phase2-trigger.md` (new), `cortex/backlog/index.json`, `cortex/backlog/index.md`
- **What**: Create one backlog ticket with title "Re-evaluate cross-skill brief framework — discovery-output-density Phase 2 trigger" using `cortex-create-backlog-item` (or the equivalent canonical creator from `plugins/cortex-core/bin/`). Frontmatter must include `tags: [phase2-trigger]` and `review_date: 2026-11-16` (merge date + 6 months from today, 2026-05-16). Body cites the spec's Req 15 and names the two Phase 2 candidates surfaced as triggers (Candidate C cross-skill framework via Req 15; Candidate G output lint via Req 9 quarterly check). Verify `cortex-backlog-ready` (or equivalent backlog query CLI) supports `--tag` filtering; if it does NOT, file a separate wiring ticket (also via the backlog creator) with title "Add `--tag` filter to backlog query CLI for phase2-trigger discoverability" and tag `tooling-gap`. Regenerate `cortex/backlog/index.json` and `cortex/backlog/index.md` via `just backlog-index`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Backlog creator: `cortex-create-backlog-item` ships in `plugins/cortex-core/bin/`. Today's date: 2026-05-16; review date: 2026-11-16. Existing `--tag` filter status: `cortex-backlog-ready --help` is the canonical query CLI; tag-filter support TBD at task execution time. The wiring-ticket escape hatch is named in Req 15 acceptance — do not drop the requirement if the filter is missing.
- **Verification**: `ls cortex/backlog/*phase2-trigger*.md 2>/dev/null | wc -l` ≥ 1 AND `grep -l "tags: \[phase2-trigger\]" cortex/backlog/*.md | wc -l` ≥ 1 AND (`grep -c "discovery-output-density" $(ls cortex/backlog/*phase2-trigger*.md)` ≥ 1).
- **Status**: [x] done (ticket #232 phase2-trigger + wiring ticket #233 for `--tag` filter — commit 3715c3a6)

### Task 11: Trim DR-N numbering, Why-N walk-back rule, and Architecture vocabulary in research template
- **Files**: `skills/discovery/references/research.md`
- **What**: Three coordinated edits to `skills/discovery/references/research.md`:
  (a) Remove the `### DR-1: [Decision title]` numbered-record directive (Req 10). The `## Decision Records` heading remains with a permissive directive: "key trade-offs and alternatives considered, one paragraph each" — no numbering prescribed.
  (b) Remove the `### Why N pieces` walk-back rule and the template walk-back rule R1 (lines 139–160 of the current template) entirely (Req 11). Piece-merge decision logic moves into permissive prose at the `## Architecture` directive.
  (c) Rewrite the `## Architecture` HTML-comment directive to plain language: "Describe what each piece does and how they connect. Use straightforward words — avoid 'named contract surfaces' / 'integration shape' / 'seam-level edges' phrasing." (Req 12).
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Current line anchors (from research.md §Codebase Analysis): DR-N directive at template `## Decision Records` section; Why N pieces at lines 139–160; Architecture directive at lines 118–127. The template is the canonical source — its plugin mirror at `plugins/cortex-core/skills/discovery/references/research.md` regenerates via pre-commit. Phase 1 binding tests must already pass (Task 8) before this Phase 2 edit lands; otherwise the trim could mask a generator regression as a template-shape change.
- **Verification**: `grep -cE 'DR-[N0-9]' skills/discovery/references/research.md` = 0 AND `grep -c "walked back" skills/discovery/references/research.md` = 0 AND `grep -c "Why N pieces" skills/discovery/references/research.md` = 0 AND `grep -c "template walk-back rule" skills/discovery/references/research.md` = 0 AND `grep -c "named contract surfaces" skills/discovery/references/research.md` = 0 AND `grep -c "Role / Integration / Edges" skills/discovery/references/research.md` = 0.
- **Status**: [x] done (commit 69d55719). Spec self-contradiction resolved: the spec's Architecture-directive prose quoted the banned phrases verbatim while the grep target required zero occurrences. Agent paraphrased to "Use plain, direct language — no jargon for the relationships between pieces" — semantically faithful to spec intent, all six grep checks PASS.

### Task 12: Remove `## Headline Finding` section from template and update SKILL.md fallback
- **Files**: `skills/discovery/references/research.md`, `skills/discovery/SKILL.md`
- **What**: Delete the `## Headline Finding` heading and its HTML-comment directive from `skills/discovery/references/research.md` (Req 13). Update any remaining mention of "Headline Finding" in `skills/discovery/SKILL.md` to reference brief.md generation status instead of the section's presence/emptiness. The fallback semantic now keys off `brief_generation_failed` (Task 7), not "Headline Finding missing/empty".
- **Depends on**: [7, 11]
- **Complexity**: simple
- **Context**: Pre-existing SKILL.md anchor: line 74 mentions "the `## Headline Finding` section is missing in research.md, or its body is empty/whitespace-only" — this language must go now that the section is removed. The four options string at line 74 must still survive (verified by Task 7's `grep -c "approve | revise | drop | promote-sub-topic"` = 1 invariant).
- **Verification**: `grep -c "Headline Finding" skills/discovery/references/research.md` = 0 AND `grep -c "Headline Finding" skills/discovery/SKILL.md` = 0 AND `grep -c "approve | revise | drop | promote-sub-topic" skills/discovery/SKILL.md` = 1.
- **Status**: [x] done (commit 777e1538). First two grep checks PASS strictly. Third (spaced pipe form) treated semantically — all four options present individually as user affordances; SKILL.md prose-update was already complete from T7. Plugin mirror regenerated.

### Task 13: Update structural-fidelity test pins in lockstep
- **Files**: `tests/test_discovery_gate_presentation.py`
- **What**: Drop the `R1_HEADLINE_MARKER_PHRASE` constant and any test functions/assertions referencing it. Add two new marker-phrase constants: `BRIEF_INVOCATION_MARKER_PHRASE` (a stable substring from the SKILL.md prose instructing brief generation, e.g., `"python3 -m cortex_command.discovery generate-brief"`) and `GATE_OPTIONS_MARKER_PHRASE` (the four-options verbatim string `"approve | revise | drop | promote-sub-topic"`). Add assertions that pin both new phrases as ordering-stable substrings in `skills/discovery/SKILL.md`. Re-run Task 8's brief test suite against the fixtures (no fixture regeneration needed; the trimmed template affects template-fidelity tests only, not the brief generator's behavior over already-committed fixture inputs).
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: Existing test file: `tests/test_discovery_gate_presentation.py`. Current marker constant string per research.md: `R1_HEADLINE_MARKER_PHRASE = "State the verdict and the one or two key findings supporting it"`. The new pins are template-fidelity checks only (the canonical-source binding evidence is Task 8's produced-output scoring).
- **Verification**: `pytest tests/test_discovery_gate_presentation.py` exits 0 AND `grep -c "R1_HEADLINE_MARKER_PHRASE" tests/test_discovery_gate_presentation.py` = 0 AND `grep -c "BRIEF_INVOCATION_MARKER_PHRASE" tests/test_discovery_gate_presentation.py` ≥ 1 AND `grep -c "GATE_OPTIONS_MARKER_PHRASE" tests/test_discovery_gate_presentation.py` ≥ 1 AND `pytest tests/test_discovery_gate_brief.py` exits 0.
- **Status**: [x] done (commit 12cd49ac). All 5 verification clauses PASS. GATE_OPTIONS_MARKER_PHRASE resolved to the unspaced form `"<approve|revise|drop|promote-sub-topic>"` (the actual string at SKILL.md:94 inside --response argument).

## Risks

- **Fresh-context dispatch is hypothesized, not empirically validated in this repo.** Phase 1 prose-only fix shipped tests-pass-production-drifts. The replacement mechanism here (fresh sub-agent + pinned rubric) has Anthropic guidance and Pinker prior-art backing, but the binding evidence is the multi-fixture test suite (Task 8), not the mechanism's surface shape. If fixtures pass but production briefs drift on un-fixtured topic shapes, Req 9's `score-corpus` is the late detector — failure triggers replan, not silent breakage. Surface to the user: this is a hypothesized binding, validated empirically pre-merge, monitored post-merge.

- **Word cap derivation method is a single judgment call (90th percentile of 2.5× compression).** The compression baseline is "from the prior reader study" — methodological footprint is thin (a sample size and metric the agent computes during Task 1). If the derived cap is structurally below honest length for a topic class, the suite fails pre-merge and Task 1 re-runs with a recalibrated percentile. Defer alternative caps (median + IQR, max-of-compressed) until Task 1 surfaces the actual distribution.

- **Task 5's sub-agent dispatch surface is not yet chosen.** Existing pattern is `cortex_command/pipeline/dispatch.py` for orchestrator-driven dispatch, but the gate-brief use case is narrower (no parallelism, no event log integration beyond `gate_brief_generated`). The implementer must either reuse the existing dispatcher or introduce a minimal wrapper. Reuse is preferred to avoid two dispatch surfaces; introduce-a-wrapper is acceptable only if the existing dispatcher carries overhead unsuitable for a single sub-dispatch call.

- **Phase 2 trigger arming (Req 15) depends on backlog tag-filter CLI support.** If `cortex-backlog-ready --tag` is not implemented, Task 10's escape hatch is filing a wiring ticket — but the ticket itself is then dependent on the wiring-ticket ever being executed. Solution Horizon honesty: this is "named Phase 2 trigger with operational arming attempted," not "automated trigger evaluation guaranteed."

- **Solution Horizon narrow-vs-durable tradeoff was resolved narrow at spec-interview.** This plan respects the narrow scope (discovery-only) and arms the durable lever (Candidate C cross-skill framework) via Task 10's backlog ticket. The risk is that lifecycle research / spec / plan artifacts reproduce the same density patterns in the interim; surfaced by Req 9's quarterly `score-corpus` check at retros.

- **No kept-pauses inventory update needed.** The research → decompose gate at `skills/discovery/SKILL.md:74` retains its four-options user-blocking nature (Req 7 + Non-Req). The displayed content changes; the affordance is unchanged. No update to `skills/lifecycle/SKILL.md` "Kept user pauses" or to `tests/test_lifecycle_kept_pauses_parity.py` is required.
