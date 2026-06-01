# Review: scale-research-fanout-by-complexity

## Stage 1: Spec Compliance

### R1: 2D count matrix replaces `max()`
- **Expected**: `fanout.md` holds an 8-cell tier×criticality table (simple {3,4,5,6}, complex {5,6,8,10}); floor=3, corner=10; `research/SKILL.md` has no `max(tier_count`.
- **Actual**: `skills/lifecycle/references/fanout.md:9-12` carries exactly the spec grid (simple `3 4 5 6`, complex `5 6 8 10`). `skills/research/SKILL.md:48-54` (Step 2) does a matrix lookup pointing at fanout.md, not a `max()`. `grep -c 'max(tier_count' skills/research/SKILL.md` = 0. Repo-wide scan for `max(tier`/`max(criticality` across all changed skill/doc files returns nothing.
- **Verdict**: PASS
- **Notes**: Matrix is the resolved corner-anchored grid; SKILL.md does not re-inline it, deferring to fanout.md as canonical.

### R2: Monotonic + peak invariant is testable
- **Expected**: a new test parses the grid from the canonical reference and asserts monotonicity on both axes, floor=3, corner=10, and cap (no cell > corner); `just test` green.
- **Actual**: `tests/test_research_fanout_matrix.py` parses the markdown table out of `fanout.md` (`parse_fanout_grid`, lines 53-135) then asserts: `test_monotonic_across_criticality` (157), `test_monotonic_across_tiers` (170), `test_floor_is_three` (181), `test_corner_is_ten` (189), `test_cap_is_corner` (198). The parser raises clear assertions if the table is deleted/restructured, so it doubles as a removal guard. `uv run pytest tests/test_research_fanout_matrix.py -q` → 6 passed; `just test` → 6/6 suites pass (EXIT=0).
- **Verdict**: PASS
- **Notes**: Test parses the grid from fanout.md rather than hardcoding numbers, so a corner change to the table would fail the suite — not tautological.

### R3: Hybrid angle selection
- **Expected**: mandatory core (Codebase/Web/Requirements & Constraints), always-last adversarial for high/critical over a summary, orchestrator-chosen distinct remaining angles, no topic→angle keyword router; "mandatory core" anchor present.
- **Actual**: `fanout.md:16-28` — names the mandatory core (18-22), the always-present-for-high/critical adversarial dispatched last over a brief summary (24), orchestrator-chosen distinct/non-redundant remaining slots with subdivide-by-scope as the single illustrative example (26), and "There is **no** hardcoded topic→angle keyword router" (28). `grep -c 'mandatory core'` = 4. Two-wave dispatch protocol at 30-35.
- **Verdict**: PASS
- **Notes**: Matches the What/Why-not-How directive — angle choice is described as orchestrator judgment with intent, not a fixed lookup.

### R4: Output schema follows actual angles
- **Expected**: Step 4 emits one section per dispatched angle; `## Open Questions` preserved as the only fixed contract heading; line-194 "canonical schema source" phrase gone.
- **Actual**: `skills/research/SKILL.md:196-239` (Step 4) is now angle-driven — "Emit **one `##` section per angle actually dispatched in Step 3**" (217), with `## Open Questions` named as the only fixed contract heading parsed by `cortex-complexity-escalator` (198, 231-235). Empty/failed-agent handling (202-209) and contradiction handling (211-213) preserved. `grep -c 'canonical schema source'` = 0; `grep -c 'Open Questions'` = 4 (≥1).
- **Verdict**: PASS
- **Notes**: The former line-194 self-doc is reworded at 196-198 to state the schema is angle-driven with `## Open Questions` the sole fixed heading.

### R5: Stale single-vs-parallel docs reconciled
- **Expected**: criticality-matrix.md / model-selection.md / agentic-layer.md no longer assert research is "single" for high; skills-reference.md has no "3–5"; lifecycle clarify.md sufficiency signals don't name a fixed `## Codebase Analysis` heading.
- **Actual**: `criticality-matrix.md:17-20` all read "Parallel research (sized by fan-out matrix)" with an explicit "Research is **always parallel** at every criticality" note (24, citing fanout.md). `model-selection.md:58` cites the tier×criticality fan-out matrix. `agentic-layer.md:116-121` shows "Parallel (matrix-sized)" rows + "range 3–10" with a fanout.md link. `skills-reference.md:47` reads "3–10 agents (sized by a tier×criticality matrix)". `research/SKILL.md` frontmatter (line 7) reads "3–10 parallel agents". `lifecycle/references/clarify.md:99-100` reworded to "research.md's codebase findings (the codebase-angle content, wherever it appears in the artifact)" — no fixed heading named (`grep -c '## Codebase Analysis...'` = 0). Repo-wide scan for `3–5`/`3-5` across all changed files returns nothing.
- **Verdict**: PASS
- **Notes**: Every spec-named site reconciled; no residual "single research for high" or "3–5" claim anywhere in the changed set.

### R6: Shared fan-out reference
- **Expected**: `skills/lifecycle/references/fanout.md` exists with the matrix; research/SKILL.md cites it; discovery research.md cites the same file; dual-source mirror parity passes.
- **Actual**: `fanout.md` exists (4581 bytes) and contains the matrix. Citation graph complete — `fanout.md` is referenced by `skills/research/SKILL.md` (Step 2/3/dispatch: lines 50, 72, 189), `skills/discovery/references/research.md` (§2: line 41), `skills/discovery/references/clarify.md` (56, 60), plus the three reconciled docs. Canonical vs `plugins/cortex-core/skills/lifecycle/references/fanout.md` diff → IDENTICAL. `tests/test_dual_source_reference_parity.py` → 56 passed.
- **Verdict**: PASS
- **Notes**: SKILL.md consumes the reference rather than inlining; the matrix has a single source of truth.

### R7: Discovery Clarify assesses research-sizing complexity + criticality, biased upward
- **Expected**: clarify.md emits two named research-sizing outputs, states the upward-bias intent + `medium` criticality floor + epic-leverage rationale, and the stale "does not assess implementation complexity" row is reworded.
- **Actual**: `skills/discovery/references/clarify.md:56` (output 5, Research-sizing complexity, skews `complex` for epic-seeding/multi-faceted topics) and `:60-62` (output 6, Research-sizing criticality, "floors at `medium` — never rate a discovery topic `low`", rises to high/critical when seeding an epic, with the divergence-is-expensive rationale). The stale Thought/Reality row is reworded at `:86` to scope the research-sizing carve-out while preserving "does not assess *implementation* complexity". `grep -c 'research-sizing\|research sizing'` = 5 (≥1); `grep -ci 'epic'` = 3 (≥1). `just test` green.
- **Verdict**: PASS
- **Notes**: Upward-bias intent stated as *why* (high-leverage direction-setting), inviting judgment rather than a rigid lookup, per the authoring principle.

### R8: Discovery Research uses the shared fan-out engine, keeps its schema
- **Expected**: discovery research.md fans out via the matrix AND preserves `## Architecture`/`### Pieces`/`### How they connect`; the architecture extractor still parses the template.
- **Actual**: `skills/discovery/references/research.md` §2 (39-58) replaces the sequential single-orchestrator pass with a sized two-wave parallel fan-out citing fanout.md as authority, maps the mandatory core onto discovery's dimensions, and preserves discovery's own schema (§3:60-62 explicitly forbids adopting /research's schema). §4 template (64-122) retains `## Architecture` → `### Pieces` / `### How they connect` (102-115). `tests/test_discovery_research_sizing.py::test_architecture_extractor_accepts_task10_template` proves `_extract_headline_and_architecture` returns the Architecture body with both sub-headings intact and stops at the next section (no whole-file fallback). `tests/test_discovery_gate_brief.py` → 71 passed, 2 skipped (auth-gated live SDK).
- **Verdict**: PASS
- **Notes**: `## Headline Finding` is absent from the template, which matches the spec's explicit note that it is a pre-existing inconsistency (not currently in the discovery template) and out of scope — the rewrite correctly neither introduced nor dropped it. The extractor still scans for it when present.

### R9: Discovery research-sizing assessment persists across phase-resume
- **Expected**: persistence write at Clarify, read at Research entry; defaults to simple/MEDIUM when absent and never errors; emit/read round-trips; event registered in `bin/.events-registry.md`.
- **Actual**: Write — `clarify.md:74-80` invokes `cortex-discovery emit-research-sizing`; read — `research.md:29-37` invokes `cortex-discovery read-research-sizing`. `cortex_command/discovery.py`: `DEFAULT_RESEARCH_SIZING = {"complexity":"simple","criticality":"medium"}` (1030), `emit_research_sizing` validates+appends a `discovery_research_sizing` event (1036-1066), `read_research_sizing` scans for the latest such row and returns the floor default when absent — Tolerant Reader skips malformed JSONL, never errors (1069-1102). Event registered at `bin/.events-registry.md:143`. Tests: round-trip (`test_research_sizing_round_trips_complex_high`), most-recent-wins (`test_research_sizing_read_returns_most_recent`), default-on-missing-log + explicit medium-not-low pin (`test_research_sizing_default_on_resume_without_assessment`), and log-present-but-no-sizing-event (`test_research_sizing_default_when_log_has_no_sizing_event`) — all pass. `just check-events-registry-audit` → exit 0.
- **Verdict**: PASS
- **Notes**: The medium-not-low floor is pinned explicitly in the test so a regression to simple/low fails. Default constant matches the read-back.

## Requirements Drift
**State**: none
**Findings**:
- The feature scales an existing multi-agent dispatch mechanism. `cortex/requirements/project.md` In-Scope already covers "Multi-agent: parallel dispatch, worktrees, Haiku/Sonnet/Opus selection" and routes detail to the conditional `multi-agent.md` doc. The 2D matrix, hybrid angle selection, and discovery research-sizing are refinements of parallel dispatch behavior, not a new capability class. No model-selection change (a stated Non-Requirement). No new architectural constraint, state file, or boundary is introduced. Authoring honored the "prescribe What/Why not How" principle and the MUST-escalation policy (no new MUST). Discovery being documented inline (no area doc) is consistent with project.md's In-Scope note.
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: The new `emit-research-sizing` / `read-research-sizing` subcommands mirror the existing `emit-checkpoint-response` pattern in `cortex_command/discovery.py` exactly — `_validate_topic_slug` reuse, `resolve_events_log_path` for path resolution (never hardcoded), `append_event` atomic tempfile+`os.replace`, an importable public function plus a thin `_cmd_*` argparse wrapper, choices enumerated from module-level tuples. `fanout.md` matches the house style of sibling references (`load-requirements.md`, `orchestrator-review.md`): a one-paragraph purpose header, `##` sections, prose-with-intent. Consistent.
- **Error handling**: `read_research_sizing` is a Tolerant Reader — missing log, empty log, malformed JSONL lines, and log-without-sizing-event all fall back to `DEFAULT_RESEARCH_SIZING` without raising; only genuine validation errors (bad complexity/criticality enum, bad slug) surface as `ValueError` at emit time. `emit_research_sizing` validates both axes against frozen tuples before writing. CLI commands return exit 2 on `ValueError`/`OSError`, 0 on success. The resume-without-assessment default path is the spec's explicit safety requirement and is covered by two distinct tests.
- **Test coverage**: Both new tests exercise real invariants. `test_research_fanout_matrix.py` parses the grid from fanout.md and asserts ordering/floor/corner/cap — a corner edit or table deletion fails it (not tautological). `test_discovery_research_sizing.py` covers the parser contract against the shipped §6 template (hermetic, auth-free), round-trip, most-recent-wins, and the medium-not-low floor pinned explicitly. Full suite: 6/6 (`test-overnight` passed on first run).
- **Pattern consistency**: research/SKILL.md is coherent end-to-end — Step 2 count (matrix lookup) ↔ Step 3 dispatch (mandatory core + chosen angles + always-last adversarial, two-wave) ↔ Step 4 output (one section per dispatched angle). No dangling reference to the old fixed 5-angle roster or the old `max()` model in any changed file (repo-wide scan for `3–5`/`max(tier`/`five-angle`/`fixed five`/`five-heading` returns nothing). No new MUST/CRITICAL/REQUIRED in any changed skill file. Dual-source mirror is byte-identical. Discovery schema risk: the architecture extractor contract is regression-guarded, and §3 of discovery research.md explicitly forbids adopting /research's schema, closing the path where the rewrite could emit a research.md that breaks `generate-brief`.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
