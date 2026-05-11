# Research: Vertical-planning adoption as REPLACEMENT (#182)

Topic: Adopt CRISPY/QRSPI vertical-planning patterns as a REPLACEMENT in cortex's lifecycle artifact templates. In `skills/lifecycle/references/plan.md`: `## Outline` (text-outline of phases with goals + checkpoints) replaces `## Scope Boundaries` + `## Verification Strategy`; `## Veto Surface` is renamed `## Risks`; a `## Acceptance` section is added tier-conditional on **complexity=complex** (resolving the source contradiction in favor of complex per clarify §4 Q&A). In `skills/lifecycle/references/specify.md`: `## Phases` + per-requirement `**Phase**` tags. Three orchestrator-review gates: P9 (plan outline), S7 (spec phases), P10 (complex-tier `## Acceptance`). Harden `cortex_command/pipeline/metrics.py:221` against verdict-JSON field-name drift. Add a plan-parser regression test at `cortex_command/pipeline/parser.py:282-329`. One-line edit at `cortex_command/overnight/report.py:725` to read last-phase Checkpoint (non-complex) or `## Acceptance` (complex) instead of `## Verification Strategy`. Lands AFTER cross-skill collapse (174–176, verified complete).

## Codebase Analysis

### Files that will change

- `skills/lifecycle/references/plan.md` (canonical template) — sections to delete at lines 165–172 (`## Verification Strategy`, `## Veto Surface`, `## Scope Boundaries`); add `## Outline` above `## Tasks`; add `## Risks` (renamed from Veto Surface); add tier-conditional `## Acceptance`.
- `skills/lifecycle/references/specify.md` (canonical template) — full spec artifact template at lines 112–141; add `## Phases` section + per-requirement `**Phase**: <name>` tags inline.
- `skills/lifecycle/references/orchestrator-review.md` — gates P1–P8 at lines 152–165; S1–S6 ending at line 150; **low+simple skip rule at line 9**. Insertion points: P9/P10 after P8 (line 165); S7 after S6 (line 150).
- `cortex_command/pipeline/metrics.py:221` — currently `[e["verdict"] for e in review_events]` direct field access; harden via alias-lookup. Precedent (markdown-field): `parser.py:317` `_parse_field_string()` with fallback default.
- `cortex_command/pipeline/parser.py:282-329` — task-heading-anchored `_parse_tasks()`; H2 sweep at line 310 (`re.search(r"^##\s+", text[start:], re.MULTILINE)`). Top-of-doc `## Outline` is parser-safe because the parser scans forward from each `### Task N:` heading. **Critical caveat**: nested `## Phase N:` H2 headings INSIDE `## Tasks` cause silent body truncation (see Adversarial FM-5).
- `cortex_command/pipeline/tests/test_parser.py` — current 354-line test suite with `_make_plan()` / `_task_block()` helpers, tempfile roundtrip, separator-variant classes. New regression-test class lands after line 354.
- `cortex_command/overnight/report.py:717-731` — `_read_verification_strategy()` uses regex `r"^## Verification Strategy\s*\n(.*?)(?=\n## |\Z)"`; called from `_render_feature_block` at line 534. **Critical finding**: the ticket calls this a "one-line update" but the rendering path does NOT extract `tier`/`criticality` anywhere — this is ~40 lines of new code across new helper functions + tier extraction wiring (see Adversarial FM-1).
- Plugin mirrors at `plugins/cortex-core/skills/lifecycle/references/*` auto-regenerate via `just build-plugin` (rsync -a --delete) + pre-commit hook (`.githooks/pre-commit`).
- `skills/refine/references/specify.md` — confirmed deleted by ticket 174; no action needed.

### Existing patterns and conventions

- **Gate IDs**: single capital letter + digit (`R1`, `S7`, `P10`); cumulative; new rows appended at end of phase's table.
- **Template heading conventions**: H2 (`## Name`) for top-level sections (Overview, Tasks, Risks, Acceptance, Outline); H3 (`### Task N:`) for task definitions. **Phase headings inside `## Outline` should be H3** to avoid parser-truncation and `phase_durations` namespace collision (see Adversarial FM-4, FM-5).
- **Section reader regex pattern** (report.py): `r"^## SectionName\s*\n(.*?)(?=\n## |\Z)"` with MULTILINE|DOTALL.
- **Field-parser fallback pattern** (parser.py:317): `_parse_field_string(body, "Field") or "default"`.
- **Test patterns**: `_make_plan()` + `_task_block()` helpers; one TestCase per invariant; setUp/tearDown for tempfile lifecycle.

### Integration points

- **Templates consumed by**: `lifecycle/SKILL.md`, `refine/SKILL.md`, agent dispatch prompts (read templates and ask agents to follow verbatim), orchestrator-review.md (pasted verbatim into Fix Agent Prompt Template).
- **Parser dependencies (downstream)**: `feature_executor.py:529` (per-task dispatch); `batch_plan.py:15` (batch rendering); `metrics.py` (event-field consumption).
- **Plugin-mirror enforcement**: pre-commit hook auto-regenerates; parity linter at `bin/cortex-check-parity`.

## Web Research

### Canonical CRISPY/QRSPI v2 shape vs cortex's proposal

| Aspect | Canonical QRSPI (community) | Cortex proposal |
|---|---|---|
| Outline location | Separate artifact (`structure.md`, ~2 pages) reviewed BEFORE plan | Inline `## Outline` section in `plan.md` |
| Outline contents | Phased breakdown + vertical-slice grouping + verification/test checkpoints; "C header file" analogy (signatures + types) | Text-outline of phases + per-phase goal + per-phase checkpoint + task ID references |
| Vertical-slice convention | End-to-end testable slice (DB+API+UI) per phase | `## Phases` in spec.md with per-requirement Phase tag |
| Per-phase task IDs | Not in canonical or community samples | Novel cortex addition — no community validation |
| Heading conventions | `structure.md`, no normative field schema | `## Outline` (plan) / `## Phases` (spec) |

### Key findings on evidence quality

- **HumanLayer's own production prompts diverge from the published framework**: their `create_plan.md` and `research_codebase.md` (https://github.com/humanlayer/humanlayer/tree/main/.claude/commands) do NOT contain "structure outline," "vertical slice," or "phase checkpoint" — corroborates the audit's 1/5 evidence rating directly. Phases exist nested inside the plan; no separate outline artifact.
- **HumanLayer ACE article** (`ace-fca.md`) defines three phases (Research/Plan/Implement); checkpoints framed as human-review aids, not agent-reasoning aids.
- **Community implementations** all place structure outline as separate artifact: `matanshavit/qrspi` (≤2-page `structure.md`), `jaeyunha/QRSPI-workflow` (explicit DB+API+UI vertical slices), `dfrysinger/qrspi-plus` (most elaborated; separates Phasing from Structure). **No implementation surveyed inlines outline inside plan.md** — cortex's inline approach is a structural divergence.
- **Horthy's own framing** (Heavybit interview): structure outlines are "human-leverage" / "brain surgery on the agent" — explicitly a human-review tool, not an agent-reasoning aid. Cites anecdotal RPI replication failures and the 150–200 instruction attention-budget heuristic; no quantitative evidence for reasoning-quality improvement.
- **No quantitative study or A/B benchmark** found for vertical-slice-outline planning vs flat planning specifically for agent reasoning quality.

### Known patterns and anti-patterns

- **Pattern (well-supported)**: outline as human-skim aid (Horthy, Perez, Lavaee, htek.dev all cite the ~200-line vs 1000-line review-leverage argument).
- **Anti-pattern (well-documented)**: "plan-reading illusion" — humans read prose plans and feel aligned, but the agent has already made deep decisions.
- **Anti-pattern**: instruction-budget overflow ≥150–200 instructions causes consistency dropout.
- **Anti-pattern**: skill instruction drift — even with complete templates, agents skip prescribed sections under load.
- **No published failure mode** specific to introducing an inline `## Outline` section; however, the divergence between Horthy's framework and his production prompts is itself a signal that the structure-outline-as-separate-artifact pattern may not have survived contact with production usage.

### URLs not retrievable

- YouTube transcripts for "From RPI to QRSPI" (https://www.youtube.com/watch?v=5MWl3eRXVQk) and "Everything We Got Wrong" (https://www.youtube.com/watch?v=YwZR6tc7qYg) — WebFetch cannot retrieve YouTube transcripts; primary-source verification gap remains.
- https://lobehub.com/skills/david-kijko-david-harness-crispy — returned 403.

## Requirements & Constraints

### From `requirements/project.md`

- **Workflow trimming philosophy**: "Hard-deletion preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers (verified per-PR)." → Deletion of `## Scope Boundaries` and `## Verification Strategy` must be total (no deprecation markers).
- **SKILL.md 500-line cap**: applies to SKILL.md only; references/ files are exempt. → Template expansion in `skills/lifecycle/references/plan.md` and `specify.md` is permitted; verify the canonical `skills/lifecycle/SKILL.md` itself does not approach the cap as a side-effect.
- **SKILL.md-to-bin parity enforcement**: no new bin scripts in this ticket; parity gate inapplicable.

### From `requirements/pipeline.md`

- **Metrics field-name protection** (lines 99–108): metrics computed by parsing `feature_complete` events; per-feature metrics include `review verdicts`. The `metrics.py:221` hardening (alias-lookup or normalized-field-name parsing) protects FM-7 silent-degradation (verdict-JSON field-name drift → `review_verdicts: None` without surfacing).
- **Post-Merge Review verdict format** (lines 58–70): canonical field is `verdict` (uppercase string: APPROVED, CHANGES_REQUESTED, REJECTED) written to per-feature `events.log`. Alias-lookup must tolerate harmless drift but should NOT erode the canonical contract.

### From `requirements/observability.md`

- Morning report reads `lifecycle/sessions/{id}/overnight-state.json`, per-feature `events.log`, and plan.md.
- `report.py:725` is the surface that displays verification text in the "How to try" section of the morning report.
- The tier-conditional read change is observable to the user.

### From `requirements/multi-agent.md`

- No new dispatch surfaces or concurrency interactions; orchestrator-review gates execute in the main conversation context after artifact write, not in dispatch templates.

### From `CLAUDE.md` (MUST-escalation policy, OQ3)

- **Positive routing language required for new gates**: P9/S7/P10 descriptions must use "Plan/Spec contains…" or "verify the plan contains…" — soft positive phrasing, NOT MUST/CRITICAL/REQUIRED escalations.
- Escalating to MUST requires effort=high evidence trail per OQ3; ticket 182 has no such trail; new gates ship as soft positive.

### Architectural constraints

- **File-based state**: all new sections are markdown text; no schema database; atomic write semantics for events.log handled by existing infrastructure.
- **Binary-checkable verification**: spec-level acceptance criteria must be (a) runnable command + observable output + pass/fail, or (b) observable state + file pattern, or (c) interactive/session-dependent with explicit rationale.

## Tradeoffs & Alternatives

Six candidates evaluated:

- **Candidate A (ticket's proposal)** — Outline REPLACES Scope Boundaries + Verification Strategy; Veto Surface → Risks; tier-conditional Acceptance; P9/S7/P10 gates; metrics.py hardening; parser test. **Pros**: honors audit DR-1 net-reduction; Q-C critical-review fixes already absorbed; mappings to DR-3/DR-4/DR-6; nests within existing `low+simple` skip rule. **Cons**: 4 canonical files in flight; REPLACEMENT direction inverts cortex's additive instinct; adopts v2 of a framework whose v1 was retracted; tier-conditional branch in template-mental-model.

- **Candidate B (sibling, not replacement)** — keep Scope Boundaries + Verification Strategy AND add Outline. **Pros**: lowest blast radius; zero risk of losing signal. **Cons**: defeats DR-1 (Scope Boundaries has zero programmatic consumer); +30–50 lines per plan vs Candidate A's ~40–90 line reduction (gap is ~70–140 lines per feature, ~10k–19k accumulated); re-opens an argument already settled.

- **Candidate C (plan.md only; spec.md unchanged)** — halves canonical-file edit surface; no S7. **Cons**: loses per-requirement Phase tag (the main human-skim affordance); breaks cross-artifact vertical-slice linkage.

- **Candidate D (tier-gated adoption)** — Outline + Phases only for complex-tier; simple-tier unchanged. **Pros**: matches DR-2's "default-on for critical/complex, default-off for simple/low." **Cons**: doubles template-maintenance surface; compounds with A's tier-conditional Acceptance → three template shapes; contradicts ticket §3's "fire wherever orchestrator-review runs."

- **Candidate E (drop tier-conditional Acceptance + P10)** — single template, last-phase Checkpoint = whole-feature acceptance for ALL tiers. **Pros**: simplest template. **Cons**: re-opens the Q-C semantic argument (whole-feature ≠ per-phase Checkpoint for complex); for complex features (worst-case blast radius), drops the explicit contract.

- **Candidate F (defer the gates)** — template-only changes first; P9/S7/P10 ship in follow-up. **Pros**: smaller initial change. **Cons**: templates drift without enforcement; load-bearing structural enforcement evaporates (research.md headline #5); deferred work has high abandonment rate.

### Recommended approach: **Candidate A** (the ticket's proposal)

Rationale (ordered by weight):

1. The Q-C critical-review fixes already address the only substantive objections to A (loss of Veto Surface affordance; whole-feature ≠ per-phase Checkpoint). Candidates B/E re-open settled arguments without new evidence.
2. Only A delivers the audit's stated net-reduction (40–90 lines per feature, though see Adversarial FM-8 — this baseline needs re-measurement post-#177).
3. Candidate D's tier-gating compounds badly with A's tier-conditional Acceptance, creating 3 template shapes. The ticket's §3 explicitly accepted "fire wherever orchestrator-review runs."
4. Candidate F's defer-the-gates posture loses load-bearing structural enforcement.
5. Built-in safety nets: parser regression test (item 4) + metrics.py hardening (item 3a) make Candidate A's parser robustness *better* than the status quo, not worse.

### Sequencing hedge (revised by Adversarial FM-7 + FM-10)

Land in this order (single PR, individual commits revertible):

1. **First**: parser regression test + `metrics.py:221` hardening (pure robustness; no template change; ships value even if everything else reverts).
2. **Second** (combined to avoid false-positive window): P9/S7/P10 gate text + template changes (Outline, Risks rename, tier-conditional Acceptance) + `report.py` compatibility shim that supports BOTH old `## Verification Strategy` AND new readers (last-phase Checkpoint + `## Acceptance`).
3. **Third** (the irreversible step): delete `## Scope Boundaries` + `## Verification Strategy` from canonical template (in-flight plans remain readable because the compat shim from step 2 still handles them).

Combine gate-text and template into a single commit (Adversarial FM-10 — separating creates an in-PR false-positive window where P9 flags every plan as missing `## Outline`). `report.py` compat shim ships in step 2, not step 3, to avoid the silent-degradation window flagged in Adversarial FM-7.

## Adversarial Review

The full adversarial pass produced 10 failure modes (FM-1 through FM-10), 2 anti-patterns (AP-1, AP-2), and 3 assumptions to flag (AS-1 through AS-3). Highlights below; full list with mitigations in the spec.

### Highest-impact failure modes

- **FM-1 — `report.py:725` is NOT a one-line update**. Direct inspection: `_render_feature_block` does not extract `tier`/`criticality` anywhere. To honor the tier-conditional read mandate, the implementer must add tier extraction from `events.log`, new `_read_acceptance(feature)` reader, new `_read_last_phase_checkpoint(feature)` reader, and tier branching. ~40 lines of new code across 4 surfaces. The ticket's effort estimate is wrong.
- **FM-2 — Tier dimension still contradicts internally**. Clarify §4 Q&A resolved `## Acceptance` + P10 firing on **complexity=complex** (not criticality=critical). But the existing P8 (Architectural Pattern) gate at orchestrator-review.md uses criticality=critical semantics for similar tier-gating. Spec must commit the dimension consistently across all five sites (Section 1, P10 gate text, report.py reader, Verification bullets, touch point line) and ensure no implicit conflict with orchestrator-review's existing critical-tier gates.
- **FM-3 — Veto Surface rename has live downstream consumers**. Grep evidence: `cortex_command/pipeline/dispatch.py:271` ("Per the Veto Surface in the implementation plan…") and `cortex_command/pipeline/tests/test_dispatch.py:943` ("MUST be `raise ValueError`… per the plan's Veto Surface") — 2 live code docstrings. Also ~108 archived files reference the literal string. The rename is "cosmetic" per the ticket, but completing it means touching the docstrings; preserving it means keeping the name. Pick one explicitly in spec.
- **FM-4 — `phase_durations` namespace collision**. `metrics.py:218` and `report.py:611` already use "phase" for lifecycle-phase transitions. The new template introduces `## Phase N:` for vertical-slice phases inside plan.md. Recommended: H3 (`### Phase N:`) inside `## Outline` to avoid parser-truncation AND namespace collision; OR rename to `## Slice N:`. Spec confirms.
- **FM-5 — Parser regression test "documents the limitation" rather than fixing it**. Nested `## Phase N:` H2 inside `## Tasks` causes silent task-body truncation. The test confirms it but does not surface the failure to authoring agents. Mitigation: combine H3-headings-only convention (FM-4) with P9 sub-clause "no `## Phase` H2 heading appears between `## Tasks` and the next H2 boundary."
- **FM-7 — Silent morning-report degradation between template change and report.py update**. If template ships first, new plans show empty "How to try" in morning report (regex finds nothing → `""` → "See feature plan for verification steps"). Mitigation: report.py compatibility shim ships FIRST (dual-format support), THEN template change.
- **FM-10 — Gate-introduction sequencing creates false-positive window**. If P9/S7/P10 gate text ships before templates, orchestrator-review flags every plan. Mitigation: combine gate-text and template into single commit.
- **FM-8 — `40–90 line reduction` baseline is overstated post-#177**. Ticket 177 already trimmed `plan.md §1b.b` (~60 lines). The incremental reduction from 182 is plausibly ~20–50 lines, not 40–90. Re-baseline at spec time; don't ship the claim in the canonical plan.
- **FM-9 — "Q-C critical-review fix" provenance is anecdotal**. The term originates in `research/epic-172-audit/research.md:266,274,277,278` but no `critical-review-residue.json` artifact exists for `epic-172-audit/`. Sibling features have residue JSON files; this one does not. Mitigation: rewrite citations to point to research.md sections OR create the residue artifact.

### Anti-patterns and assumptions

- **AP-1 — Provenance-disclosure location unspecified**. The ticket mandates a DR-6 provenance note but does not say where it lives. Recommendation: as prose paragraph at top of `skills/lifecycle/references/plan.md §3`, NOT propagated into each authored plan. P9 checks Outline shape, not provenance.
- **AS-1 — "≥2 phases" forces artificial decomposition**. Trivial-tier plans (single-file docs, single-script deploys) may have 1–3 tasks that aren't naturally sliceable. The `low+simple` skip rule provides a partial out, but `medium+simple` plans still hit P9. Spec must decide: tier-gate P9 (skip on `complexity=simple`) OR allow single-phase outlines.
- **AS-3 — Plugin mirror auto-regeneration depends on `just setup-githooks`**. Add a pytest comparing canonical → plugin mirror plan.md, fail on drift, independent of pre-commit hook. Defense-in-depth.

### FM-6 — Alias-lookup scoping risk

Importing alias-lookup at `metrics.py:221` invites the pattern to generalize across `metrics.py`, eroding the strict-format contract. Mitigation: scope to a single `_VERDICT_ALIASES` constant + named function; add strict schema-validation upstream at `overnight/events.py` so alias lookup is defense-in-depth, not contract relaxation.

## Open Questions

Each item is either resolved inline or marked **Deferred to Spec** with rationale.

1. **Tier dimension for `## Acceptance` + P10 — final commitment across all five sites.** Resolved inline (Clarify §4 Q&A): **complexity=complex**. Deferred to Spec only for the rewrite step ensuring all five sites (Section 1 template, P10 gate text, report.py reader, Verification bullets, touch point) use the same dimension consistently AND that no implicit conflict exists with orchestrator-review's existing critical-tier gates (P8 Architectural Pattern). **Status: resolved on dimension; deferred on consistency rewrite.**

2. **report.py:725 effort estimate**. Resolved inline: ticket's "one-line update" is wrong. Spec must include: tier extraction helper (read `events.log` for `lifecycle_start`/`complexity_override`), `_read_acceptance(feature)` reader, `_read_last_phase_checkpoint(feature)` reader, tier branching in `_render_feature_block`. **Status: resolved.**

3. **Veto Surface rename — complete or preserve?** Deferred to Spec by asking the user. Options: (a) complete the rename including `dispatch.py:271` and `test_dispatch.py:943` docstring edits + add "Renamed from Veto Surface 2026-05-11" anchor in template prose for retro searchability; OR (b) preserve `## Veto Surface` to honor the 13-retro-mention pivotal affordance literally. The ticket calls it "cosmetic" but Adversarial FM-3 shows 2 live consumers + ~108 archived files. **Status: deferred to Spec.**

4. **Phase heading H-level — H2 or H3 inside `## Outline`?** Deferred to Spec by asking the user. Recommendation: H3 (`### Phase N:`) to avoid parser-truncation (FM-5) and `phase_durations` namespace collision (FM-4). Alternative: rename to `## Slice N:` matching CRISPY vocabulary. **Status: deferred to Spec.**

5. **Commit sequencing**. Resolved inline (Adversarial FM-7 + FM-10): (1) parser test + metrics.py hardening; (2) gate text + template + report.py compat shim combined; (3) delete legacy sections last. **Status: resolved.**

6. **Line-reduction claim baseline**. Resolved inline: do NOT ship "40–90 line reduction" claim in canonical plan; measure post-#177 baseline at implementation. **Status: resolved.**

7. **Q-C critical-review provenance**. Resolved inline: rewrite citations to point to `research/epic-172-audit/research.md:266,274,277,278` sections directly; do not require creation of a separate residue artifact. **Status: resolved.**

8. **P9 single-phase tolerance**. Deferred to Spec by asking the user. The "≥2 phases" rule forces decomposition for trivial features. Options: (a) tier-gate P9 (skip on `complexity=simple` regardless of criticality, overriding the `low+simple` skip rule for this gate); (b) widen "≥2 phases" to "≥1 phase"; (c) keep strict "≥2 phases" and accept that simple-tier features will fail the gate (treating P9 as an explicit "you should re-tier this to simpler" signal). **Status: deferred to Spec.**

9. **Provenance-note placement** (AP-1). Resolved inline: prose paragraph at top of `plan.md §3`; do NOT propagate into each authored plan; P9 checks Outline shape, not provenance. **Status: resolved.**

10. **Plugin-mirror drift test** (AS-3). Resolved inline: spec must include a pytest comparing canonical `plan.md`, `specify.md`, `orchestrator-review.md` to their plugin mirrors. **Status: resolved.**
