# Specification: discovery-output-density-investigate-author-centric

## Problem Statement

The `/cortex-core:discovery` research→decompose gate displays the dense `## Headline Finding` and `## Architecture` sections from research.md verbatim. Production artifacts show 171–402 word Headline Findings against a "one paragraph" directive, 243-word `### Pieces` bullets densely citing line numbers, forward references to undefined vocabulary (`DR-N`, `OQ-N`, named-contract compounds), and walked-back author-process narration ("decomposition history: original was 7 pieces, walked back per template rule R1 across three iterations"). The user reads the gate output as the discovery orchestrator and cannot scan it efficiently — making worse approve/revise/drop/promote-sub-topic decisions. A prior fix (`improve-discovery-gate-presentation`, shipped 2026-05-12) tightened the Headline directive prose and did not bind: production drifted to 402 words. The Phase 1 fix's tests pinned template-directive fidelity (the directive contained the expected marker phrase); the tests passed; production artifacts still drifted.

This spec hypothesizes that decoupling brief generation from the dense artifact via a fresh-context sub-dispatch — combined with multi-fixture, multi-pattern pre-merge tests over produced output — will bind where the prior fix did not. The binding is not architecturally enforced (markdown grammar is not load-bearing structural separation); it is hypothesized and validated empirically. The acceptance suite must therefore measure the spec's stated failure class (produced-output drift across topics) pre-merge, not assume the mechanism class binds because of its surface shape.

## Phases

- **Phase 1: Wire gate-brief generator with binding test suite** — A fresh-context sub-dispatch at the research→decompose gate transforms research.md into a plain-prose brief written by an agent given a pinned reader rubric. Ships with a multi-fixture, multi-pattern pre-merge test suite that exercises the brief generator across topic shapes and scores all six reader-study patterns on produced output.
- **Phase 2: Simplify the research template** — Drop the authoring directives producing the density patterns at source (DR-N numbering scheme, `### Why N pieces` walk-back rule, contract-surface vocabulary, the `## Headline Finding` section the brief replaces).

## Requirements

1. **Gate-brief helper exists**. A new subcommand `generate-brief` lives at `cortex_command/discovery.py`, taking a research.md path and returning a plain-prose brief on stdout. **Acceptance**: `python3 -m cortex_command.discovery generate-brief tests/fixtures/discovery-brief/cursor-skill-port/research.md` exits 0 and emits a non-empty brief to stdout. **Phase**: Phase 1.

2. **Brief is persisted alongside research.md**. After the gate fires and brief generation succeeds, the brief is written to `cortex/research/<topic>/brief.md`. **Acceptance**: After a discovery run reaches the research→decompose gate, `test -f cortex/research/<topic>/brief.md` exits 0. **Phase**: Phase 1.

3. **Reader rubric is pinned as a code constant**. The rubric driving brief generation lives as a string constant in `cortex_command/discovery.py`, exported as `GATE_BRIEF_RUBRIC`. The rubric structures output as "what was decided / what alternatives were considered / what tradeoff was accepted" (decision-content fidelity anchor), demands plain natural prose with explicit prohibitions for `DR-N`/`OQ-N`/`RQ-N`/`§N` labels and "named contract surfaces" / "walked back" / "decomposition history" vocabulary, and names a word target derived from corpus measurement (Req 4). Decoupling the rubric from template HTML comments is a hypothesis (fresh-context dispatch may resist the attention-decay window that drove Phase 1 drift), not an architectural guarantee — the binding evidence lives in Req 5's multi-fixture suite. **Acceptance**: `python3 -c "from cortex_command.discovery import GATE_BRIEF_RUBRIC; assert 'decided' in GATE_BRIEF_RUBRIC and 'alternatives' in GATE_BRIEF_RUBRIC and 'tradeoff' in GATE_BRIEF_RUBRIC"` exits 0 (semantic anchor verification — not a behavioral test). **Phase**: Phase 1.

4. **Word cap derived from corpus measurement**. The Plan phase measures word counts of compressed-honest Headline equivalents from the existing `cortex/research/*/research.md` and `cortex/lifecycle/*/research.md` corpus (using the 2.5× compression baseline from the prior reader study as a guide). The derived cap is set at the 90th percentile of compressed lengths, rounded to the nearest 25 words; rationale and per-artifact measurement table are committed to `cortex/lifecycle/<feature>/word-cap-derivation.md`. **Acceptance**: `test -f cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md` exits 0 AND the file contains a per-artifact table with measured word counts AND `grep -cE 'word cap: [0-9]+' cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md` ≥ 1. The derived cap is then encoded as a module constant `GATE_BRIEF_WORD_CAP` in `cortex_command/discovery.py` referenced by Req 5's tests. **Phase**: Phase 1.

5. **Multi-fixture brief-output test suite passes pre-merge**. A test exercises `generate-brief` against **≥ 3 committed fixture research.md files** representing distinct topic shapes (e.g., simple-topic, complex-topic with many pieces, diagnostic/policy topic). For each fixture's brief, the test scores all six reader-study patterns (forward refs to undefined vocab; headlines arguing with themselves via negation-near-claim regex; author-process narration via banned-phrase grep including "walked back" / "decomposition history" / "per template rule"; headline negation rebuttal via "B does NOT" / "does NOT preserve" / "does NOT extend" regex within the first ≤2 sentences; citation-as-credibility-signal via `[path:line]` density >1 per 80 words; conditional repetition via near-duplicate sentence detection across sections). Each fixture's brief must also (a) be ≤ `GATE_BRIEF_WORD_CAP + 25` words tolerance, (b) contain the strings "decided" or "decide" AND "alternative" or "options" AND "tradeoff" or "cost" (decision-content fidelity check), (c) score 0 of 6 patterns reproducing. **Acceptance**: `pytest tests/test_discovery_gate_brief.py::test_brief_passes_all_fixtures` exits 0. **Phase**: Phase 1.

6. **Brief-generation failure falls back to existing dense display**. When `generate-brief` exits non-zero, returns an empty brief, or returns a brief that fails pre-render structural validation (missing decision-content anchor keywords), the gate prose falls back to displaying the dense `## Architecture` section from research.md and surfaces a warning naming the failure condition. **Acceptance**: `pytest tests/test_discovery_gate_brief.py::test_brief_failure_falls_back_to_architecture` exits 0. **Phase**: Phase 1.

7. **Gate prose displays the brief and preserves the four user-blocking options**. `skills/discovery/SKILL.md` lines 72–90 are rewritten so the gate's first content section is the contents of `cortex/research/<topic>/brief.md`. The four options (`approve | revise | drop | promote-sub-topic`) are preserved verbatim. The rendering callsite — not just the string mention — is exercised by a test fixture that simulates a gate firing on a fixture research.md and asserts the gate-render helper returns the brief content (not the Headline Finding or Architecture sections). **Acceptance**: `pytest tests/test_discovery_gate_brief.py::test_gate_renders_brief_not_architecture` exits 0 AND `grep -c "approve | revise | drop | promote-sub-topic" skills/discovery/SKILL.md` = 1. **Phase**: Phase 1.

8. **Event `gate_brief_generated` registered and emitted**. `bin/.events-registry.md` registers a new event `gate_brief_generated` with required fields `{ts, event, feature, status, brief_word_count, patterns_detected_count}`. `cortex_command/discovery.py` emits this event after every brief generation attempt. **Acceptance**: `bin/cortex-check-events-registry --audit` exits 0 AND `grep -c "gate_brief_generated" bin/.events-registry.md` = 1. **Phase**: Phase 1.

9. **Post-merge corpus regression check**. After Phase 1 + Phase 2 merge, an additional post-merge check runs over real produced briefs (the live `cortex/research/*/brief.md` set, not the fixture set) on a quarterly cadence and reports pattern counts. **Acceptance**: Interactive/session-dependent — operator runs `python3 -m cortex_command.discovery score-corpus cortex/research/` at quarterly review, reports counts in retro. This is a regression detector, not a merge gate (the merge gate is Req 5). Failure (≥ pattern count threshold) triggers replan, not silent breakage. **Phase**: Phase 1.

10. **Template trim: drop the DR-N numbering scheme**. `skills/discovery/references/research.md` removes the `### DR-1: [Decision title]` numbered-record directive. The `## Decision Records` heading remains with a permissive directive ("key trade-offs and alternatives considered, one paragraph each") — no numbering prescribed. **Acceptance**: `grep -cE 'DR-[N0-9]' skills/discovery/references/research.md` = 0. Note: this is a template-fidelity check; the binding evidence that template trim reduces drift in produced output lives in Req 5's fixtures (the Phase 2 fixtures replace the Phase 1 fixtures and re-run the same scoring). **Phase**: Phase 2.

11. **Template trim: drop the `### Why N pieces` walk-back rule**. Lines 139–160 of `skills/discovery/references/research.md` removed entirely. Piece-merge decision logic moves into permissive prose at the `## Architecture` directive. **Acceptance**: `grep -c "walked back" skills/discovery/references/research.md` = 0 AND `grep -c "Why N pieces" skills/discovery/references/research.md` = 0 AND `grep -c "template walk-back rule" skills/discovery/references/research.md` = 0 AND Req 5 fixtures re-run post-trim with the same `score=0/6` threshold (same caveat as Req 10). **Phase**: Phase 2.

12. **Template trim: rewrite Architecture directive vocabulary**. The `## Architecture` HTML-comment directive rewritten to plain language: "Describe what each piece does and how they connect. Use straightforward words — avoid 'named contract surfaces' / 'integration shape' / 'seam-level edges' phrasing." **Acceptance**: `grep -c "named contract surfaces" skills/discovery/references/research.md` = 0 AND `grep -c "Role / Integration / Edges" skills/discovery/references/research.md` = 0. **Phase**: Phase 2.

13. **Template removes the `## Headline Finding` section**. `skills/discovery/references/research.md` deletes the `## Headline Finding` heading and its directive. SKILL.md fallback updated to reference brief.md generation status, not Headline Finding presence/emptiness. **Acceptance**: `grep -c "Headline Finding" skills/discovery/references/research.md` = 0. **Phase**: Phase 2.

14. **Test pins updated in lockstep**. `tests/test_discovery_gate_presentation.py` drops `R1_HEADLINE_MARKER_PHRASE`. Adds `BRIEF_INVOCATION_MARKER_PHRASE` and `GATE_OPTIONS_MARKER_PHRASE`. **Acceptance**: `pytest tests/test_discovery_gate_presentation.py` exits 0 AND `grep -c "R1_HEADLINE_MARKER_PHRASE" tests/test_discovery_gate_presentation.py` = 0. **Phase**: Phase 2.

15. **Phase 2 trigger has an operational arming mechanism**. To distinguish "named Phase 2 trigger" from silent deferral per CLAUDE.md Solution Horizon: at merge time, a backlog ticket is auto-created (or manually added) with title "Re-evaluate cross-skill brief framework — discovery-output-density Phase 2 trigger" and a frontmatter field `review_date: <merge_date + 6 months>` plus tag `phase2-trigger`. This makes the trigger appear in `cortex-backlog list --tag phase2-trigger` queries and surfaces in any periodic backlog review. **Acceptance**: After merge, `cortex-backlog list --tag phase2-trigger | grep -c "discovery-output-density"` ≥ 1 (resolved by the implementer at Plan phase; if `cortex-backlog` does not currently support `--tag` filtering, file a separate wiring ticket rather than dropping this requirement). **Phase**: Phase 1.

## Non-Requirements

- **Does NOT introduce a lint over produced research artifacts** (Candidate G). Brief generator with multi-fixture pre-merge test is the binding mechanism this phase; lint over the underlying research.md is named as a Phase 2 trigger condition.
- **Does NOT split the artifact into two separately-authored files for the decompose audience** (Candidate B, audience split). The decompose contract is preserved; the dense research.md continues to feed decompose. brief.md is a derived secondary artifact, not an audience split.
- **Does NOT apply the fix cross-skill** to lifecycle research / spec / plan artifacts (Candidate C, cross-skill framework). Named as a Phase 2 trigger with operational arming (Req 15).
- **Does NOT codify "explain like I am 5" literally**. Spirit captured via decision-content structural anchor + banned-vocabulary list + multi-fixture pattern scoring.
- **Does NOT remove the research→decompose gate's user-blocking nature**. Four options preserved (Req 7).
- **Does NOT enforce brief word-cap via truncation**. The cap (derived in Req 4) is asserted at the rubric level and validated by Req 5's tests; truncation risks decision-content loss caught by Req 5's fidelity check.
- **Does NOT cache brief.md across runs**. Regenerated on every gate firing.
- **Does NOT claim the binding mechanism is architecturally enforced**. The fresh-context dispatch is a hypothesis. The binding evidence is Req 5's multi-fixture test suite; the hypothesis is falsified if Req 9's post-merge corpus check shows pattern regression.

## Edge Cases

- **Brief generation fails (agent error, timeout, malformed output, missing decision-content anchor)**: Gate falls back to displaying the dense `## Architecture` section. Four gate options remain. (Req 6)
- **Research.md structurally malformed (no `## Architecture` section)**: Brief generator input is degraded; if non-empty output produced, gate displays it; else fallback applies.
- **User re-runs `/cortex-core:discovery` on a topic with an existing brief.md**: Regenerate, overwrite. Derived artifact, no atomicity concern.
- **Generated brief exceeds word-cap tolerance**: Req 5's test fails pre-merge. The tuning loop in Plan must preserve decision-content fidelity (Req 5b semantic-anchor check); if the cap is structurally below the honest length needed for a topic class, Req 4's corpus-derivation revisits and tunes the cap upward. **Tuning does not silently delete decision content**.
- **Brief drifts toward author-centric prose on inputs not represented in fixtures**: Req 9's post-merge corpus check detects this on real produced output; failure triggers replan, not silent breakage. The fixtures in Req 5 must be expanded if Req 9 surfaces a topic class the fixtures didn't cover.
- **Phase 2 trigger arming mechanism (Req 15) fails**: `cortex-backlog list --tag` not supported. Implementer files wiring ticket; spec is honest that the operational arming requires a working tag filter, not "trigger named in spec.md sentence."

## Changes to Existing Behavior

- **MODIFIED**: `skills/discovery/SKILL.md` lines 72–90 gate prose. Previously displayed `## Headline Finding` + `## Architecture` verbatim. Now displays `cortex/research/<topic>/brief.md`. Fallback triggers on brief-generation failure or missing decision-content anchor, not Headline-Finding-missing.
- **REMOVED**: `## Headline Finding` section from research template.
- **REMOVED**: `### Why N pieces` template walk-back rule R1.
- **REMOVED**: `### DR-N: [Decision title]` numbered-record directive.
- **MODIFIED**: `## Architecture` directive vocabulary.
- **ADDED**: `cortex_command/discovery.py` subcommands `generate-brief` and `score-corpus`; pinned `GATE_BRIEF_RUBRIC` and `GATE_BRIEF_WORD_CAP` constants.
- **ADDED**: `cortex/research/<topic>/brief.md` persistent derived artifact.
- **ADDED**: `gate_brief_generated` event in `bin/.events-registry.md` with `patterns_detected_count` field.
- **ADDED**: `cortex/lifecycle/discovery-output-density-investigate-author-centric/word-cap-derivation.md` with corpus measurements.
- **ADDED**: Backlog ticket tagged `phase2-trigger` at merge time (Req 15).
- **MODIFIED**: `tests/test_discovery_gate_presentation.py` marker phrases; new `tests/test_discovery_gate_brief.py` with ≥ 3 committed fixtures.

## Technical Constraints

- **The binding mechanism is hypothesized, not architecturally enforced**. Markdown grammar is not load-bearing structural separation (per the original ticket's own caveat); the spec's binding claim rests on (a) fresh-context dispatch resetting the attention window, and (b) multi-fixture pre-merge tests that score the failure class. If (a) fails to bind, (b) catches it pre-merge. The risk is that fixture coverage is incomplete relative to the production input distribution — mitigated by Req 9's post-merge corpus regression check.
- **Rubric lives in code, not template prose**. The hypothesis: rubric injected into a fresh sub-dispatch prompt may resist attention-decay over a long parent generation in a way the original template directive (read during a long discovery run) did not. This is a hypothesis not previously empirically tested in this repo; Req 5's fixtures provide the test.
- **Helper module follows the established skill-helper pattern** (`cortex/requirements/project.md:31`).
- **MUST-escalation policy alignment**. The spec adds no new MUST/CRITICAL/REQUIRED language. Binding lives in test fixtures + a hypothesized fresh-context mechanism; the test failure mode is observable in CI without requiring MUST language. Per `CLAUDE.md` MUST-escalation policy: no MUST escalation triggered.
- **Dual-source mirror discipline preserved**. Template + SKILL.md edits land on canonical sources only.
- **Solution Horizon framing — honest**. The user chose narrow scope at spec-interview. Req 15 provides an operational arming mechanism for the Phase 2 trigger so it is queryable, not just named in spec prose. The cadence of trigger evaluation is the operator's responsibility (via periodic `cortex-backlog list --tag phase2-trigger`), not an automated guarantee. This is "named Phase 2 trigger with discoverable arming," not "automatically-evaluated trigger."

## Phase 2 triggers (Solution Horizon — narrow scope chosen)

Per `CLAUDE.md` Solution Horizon: tradeoff between narrow (this spec) and durable (cross-skill framework) surfaced at spec-interview; user chose narrow. To distinguish from silent deferral, each Phase 2 trigger is named here AND arms an operational mechanism (Req 15).

- **Cross-skill framework (Candidate C)**: Trigger arms via Req 15 backlog ticket with `review_date: <merge_date + 6 months>`. Re-evaluation conditions surfacing for the operator at that review date: documented complaints about lifecycle research / spec / plan artifact density (any channel — backlog ticket, retro note, conversation transcript) — operator decides if cross-skill ships.
- **Output lint over research artifacts (Candidate G)**: Trigger arms via Req 9 quarterly corpus check. If quarterly check shows ≥ 1 pattern reproducing across the live corpus (not the fixture set), the operator considers Candidate G as Phase 2 work.
- **Audience split (Candidate B, full version)**: Not on the deferred list. The brief.md + research.md split is the lightweight version.

## Open Decisions

- None at spec time. Plan phase resolves: exact entrypoint name for the helper, exact rubric phrasing, model/effort parameters, fixture topic selection.
