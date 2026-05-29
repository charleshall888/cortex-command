# Research: Reconcile discovery SKILL.md Architecture vocabulary with emitted research template (#269)

> Follow-up to #268 (`auto-consolidation-pass-in-discovery-decompose`), which reconciled `decompose.md` to the emitted vocabulary and deliberately deferred the `SKILL.md` straggler (its plan Risks, "Upstream heading drift left unfixed").

## Summary of resolved questions

**Q1 — Is `### Why N pieces` a deliberately-softened mechanic or a gate that drifted out? → DROP from SKILL.md (conform down).**
The hard `### Why N pieces` falsification gate (`piece_count > 5`) lives *only* in `skills/discovery/SKILL.md:82,85`. It is an orphaned self-reference: the emitted research template (`research.md` §6) produces only `### Pieces` + `### How they connect`, expressing the piece-count concern as a soft inline comment ("If the piece count grows large, consider merging pieces"); `decompose.md` was reconciled by #268 to read only those two headings; and ADR 0007 (accepted) names only `### Pieces` + `### How they connect` as the authoritative coupling-signal input. The conform-down action is **robust regardless of whether the template-softening was deliberate or incidental**, because (a) restoring the gate to the template (Approach B) is explicitly out of #269's scope (the ticket scopes `research.md` read-only) and contradicts the #268 precedent + ADR 0007, and (b) the current authoritative contract is the emitted template.

**Q2 — What does "spec R4 GATE-2 (iii)" define; is it a competing authority? → No. It points to a superseded spec; drop the back-reference.**
The R-numbers in `SKILL.md:82,85` resolve to the `reframe-discovery-to-principal-architect-posture` lifecycle spec (R4 = research→decompose approval gate; R3 = the "Why N pieces" gate; GATE-2 = R4's `revise` clause). That spec's R1 template originally mandated four sub-sections (`### Pieces`, `### Integration shape`, `### Seam-level edges`, conditional `### Why N pieces`). The template was *subsequently* simplified (Integration shape + Seam-level edges → `### How they connect`; Why N pieces → soft inline comment), but `SKILL.md` was never updated. "spec R4 GATE-2 (iii)" is therefore a dangling pointer to drifted vocabulary, **not** a living competing authority. The live authority is the emitted template + ADR 0007.

## Codebase Analysis

**Files that will change (#269 core scope):**
- `skills/discovery/SKILL.md` — lines 82 (GATE-2 fallback sub-section list) and 85 (`revise` re-walk vocabulary + spec back-reference). Canonical edit site.
- `plugins/cortex-core/skills/discovery/SKILL.md` — auto-regenerated mirror; currently byte-identical (confirmed). Must be staged in the same commit.
- `tests/test_discovery_gate_presentation.py` — add a raw-text negative+positive assertion (see test-home note below). **Not** `tests/test_discovery_module.py` (the file the ticket named — structurally the wrong home; it tests the Python helper module, not SKILL.md text).

**Verbatim current text:**
- `SKILL.md:82`: "...the gate falls back to displaying the dense `## Architecture` section (sub-sections `### Pieces`, `### Integration shape`, `### Seam-level edges`, and optionally `### Why N pieces`) and surfaces a warning..."
- `SKILL.md:85`: "...The agent re-walks the Architecture write protocol per spec R4 GATE-2 (iii) (re-emit `### Pieces`, re-run `### Integration shape` and `### Seam-level edges`, re-run the `### Why N pieces` falsification gate if piece_count > 5), re-presents the gate, and increments `revision_round`..."

**The emitted template (source of truth) — `research.md` §6 (lines 111–124):** `## Architecture` with an HTML comment ("Describe what each piece does and how they connect... If the piece count grows large, consider merging pieces..."), then `### Pieces` and `### How they connect`. No `### Integration shape`, `### Seam-level edges`, or `### Why N pieces`.

**The #268 precedent (`decompose.md`):** §1 Load Context, §4 Determine Grouping, and the Constraints "Architecture-section-driven" bullet all now name `### Pieces` + `### How they connect` as "the headings the research template actually emits." `### Integration shape`/`### Seam-level edges` appear nowhere in decompose.md. This is the exact pattern #269 should follow for SKILL.md.

**Test pattern:** `tests/test_discovery_gate_presentation.py` already reads the `DISCOVERY_SKILL` constant and asserts marker phrases via raw-text checks. The #268 precedent (`test_decompose_rules.py::test_grouping_section_1_input_contract_omits_non_emitted_headings`) uses negative + positive assertions: `assert "Integration shape" not in body` … `assert "### Pieces" in body and "### How they connect" in body`. For SKILL.md (114 lines, self-contained gate block), a raw-text scan without section parsing is appropriate.

**Dual-source mirror mechanism:** `.githooks/pre-commit` triggers on staged `skills/` paths, runs `just build-plugin` (rsync canonical → plugin trees), then `git diff --quiet plugins/<plugin>/` to block drift. Run `just setup-githooks` to register. Edit canonical → `just build-plugin` → stage both.

**Other references to the non-emitted headings (verified):**
- `tests/fixtures/discovery-brief/{diagnostic,simple,complex}-topic/research.md` — use `### Integration shape`/`### Seam-level edges`; complex-topic also has `### Why N pieces`. These model the *old* template for `generate-brief` tests. See Open Question OQ-C.
- `cortex/adr/0007:36` — mentions "Why N pieces" in **rejected-alternatives prose** (historical record). Leave untouched.
- `tests/test_decompose_rules.py:378–388` — names the headings inside negative-assertion failure messages (intentional; explains what the test guards against). Leave.
- Historical `cortex/research/*/research.md` and `cortex/lifecycle/*/` artifacts — historical records, not living surfaces. Leave.

## Web Research

Industry consensus (Fowler's *Code as Documentation*; the docs-as-code / documentation-drift literature; Wix's 250-agent eval study; spec-driven-development sources):
- **The surface that *emits* the artifact is authoritative over any prose describing the artifact's structure.** Prose descriptions must track the emitted format, not the reverse — unless a spec *generates* the implementation under machine-enforced parity (not the case here; the superseded reframe spec generates nothing).
- **Orphaned constraints that name non-existent mechanics actively mislead LLM agents** (Wix: scaffold/instruction mismatch caused ~+94% token waste). An instruction naming section headings the emitting template no longer produces creates undefined downstream behavior.
- **Drop (don't merely soften) a control when** the mechanic no longer exists in the emitted artifact and no structural enforcement elsewhere covers its intent; "the best time to delete dead [instruction] prose is when implementing the change that renders it dead."
- This converges with CLAUDE.md's own "prefer structural separation over prose-only enforcement … prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low." A prose-only "gate with no teeth" that names a non-emitted heading is the weakest form.

No direct prior art on "falsification gate" as a named artifact or multi-surface reconciliation in AI-workflow skill systems specifically; principles transfer from adjacent fields (contract testing, docs-as-code, phase-gate processes, deprecation practice).

## Requirements & Constraints

- **ADR 0007 (accepted)** is the living authority: it names `### Pieces` + `### How they connect` as the authoritative coupling-signal input for decompose §4, and explicitly lists "the `skills/discovery/SKILL.md` gate-option inventory" as a coordinated change site. No ADR or live spec treats `### Integration shape`/`### Seam-level edges`/`### Why N pieces` as a required output contract.
- **Dual-source mirror** (`project.md`): plugin copy regenerated via `just build-plugin`, staged in the same commit (pre-commit drift hook enforces).
- **SKILL.md size cap** 500 lines (`tests/test_skill_size_budget.py`); file is 114 lines — ample headroom.
- **LEX-1 prescriptive-prose scanner** runs on `skills/**/*.md` but only triggers on backlog `## Why/## Role/## Integration/## Edges` section boundaries — none in SKILL.md; no practical constraint.
- **L201 bare-Python prohibition** applies to `skills/**/*.md`; vocabulary-only edit introduces no imports — no concern.
- **MUST-escalation policy + "prescribe What/Why not How"** (CLAUDE.md): the replacement prose must use soft positive-routing phrasing (no new MUST/CRITICAL without an evidence artifact) and describe the output shape/intent rather than enumerate step-by-step method.
- **Lifecycle-gating + commit conventions**: skills/ edits run through the lifecycle (this one); commit via `/cortex-core:commit`.

## Tradeoffs & Alternatives

- **Approach A — Conform SKILL.md down to the emitted template (RECOMMENDED).** Replace `### Integration shape`/`### Seam-level edges` with `### How they connect` (alongside `### Pieces`) in both surfaces; drop the `### Why N pieces` gate reference; replace the stale "spec R4 GATE-2 (iii)" pointer in the `revise` clause with a live reference to the `research.md` §6 template block. research.md untouched. *Pros:* zero scope creep, respects #268 precedent + ADR 0007 + the ticket's read-only scoping, lowest complexity, no behavioral regression (the piece-count concern survives as the template's soft comment). *Respects precedent: yes. Respects scope: yes.*
- **Approach B — Restore the falsification gate into the research.md template.** *Disqualified:* violates the ticket's read-only scoping of research.md, inverts the #268 precedent (which treats the emitted artifact as source of truth), and multiplies scope (template + decompose.md consumption + the discovery.py event subsystem). If the gate is ever judged to have real structural value, that is a separate ticket — see OQ-A.
- **Approach C — Hybrid (fix headings, keep piece-count intent as SKILL.md prose).** Functionally near-identical to A; the template's soft comment already carries the piece-count guidance when the agent reads the template during revise. A's cleaner excision is preferred over a prose shadow that could itself drift.

**Recommended: Approach A, with care for the `revise` re-walk under-specification** (see Adversarial Probe 5): the `revise` clause should point the agent at the `research.md` §6 template block as the re-walk reference ("re-emit `### Pieces` per the role-naming convention, then `### How they connect`"), replacing the superseded spec pointer — concrete without over-prescribing method.

## Adversarial Review

- **`has_why_n_justification` event subsystem (VERIFIED, but pre-existing and OUT OF #269 SCOPE).** `cortex_command/discovery.py` defines `emit_architecture_written(..., has_why_n_justification: bool, ...)` (`:509`), validated (`:429`), serialized into the `architecture_section_written` event (`:530`), with a required CLI flag `--has-why-n-justification` (`:1289`). The events-registry (`bin/.events-registry.md:115`) cites consumer `tests/test_discovery_events.py`, **which does not exist**. **However:** no active skill prose invokes this event (verified — zero matches in `skills/`), so the subsystem was *already* orphaned from active emission independent of #269; and it *is* in fact tested (in `tests/test_discovery_module.py`, not the registry-cited file). Dropping the SKILL.md vocabulary does **not** degrade this subsystem. Its persistence is mild evidence that the Why-N retirement was *partial* (softened in template/decompose/prose, never removed from the event schema). Decision deferred to Spec — see OQ-A.
- **GATE-2 fallback for historical artifacts.** After conforming, the fallback instruction is accurate for new research.md files. For historical `cortex/research/*/research.md` files with the old four-heading vocabulary, the agent will display the actual content correctly (no hallucination) but the fallback's described headings won't match. Acceptable residual; the spec should acknowledge it.
- **`revise` re-walk under-specification.** Dropping the spec pointer without a replacement leaves "re-walk the Architecture write protocol" pointing at prose that doesn't exist. Mitigation folded into the recommended Approach A (point at `research.md` §6).
- **Assumptions that held:** mirror is byte-identical (confirmed); no live spec mandates the four headings (confirmed); R13 (re-run `-N` slug) and R15 (`split-piece`) operate on `### Pieces` only — no residual inconsistency in those paths.

## Open Questions

- **OQ-A (scope decision — DEFERRED to Spec phase): the `has_why_n_justification` / `architecture_section_written` orphaned subsystem.** *Recommendation:* keep #269 scoped to the SKILL.md prose reconciliation (+ mirror + test) and file a **separate follow-up ticket** to fully retire (or deliberately re-establish) the Why-N concept across the remaining surfaces — the `has_why_n_justification` event field + CLI flag + validator, the `bin/.events-registry.md` row (including its dangling `tests/test_discovery_events.py` reference and the `research.md` emitter-source that emits nothing), and the test fixtures. *Rationale:* this is a schema-touching change to a registered event — a different risk class than a prose reconciliation, requiring its own `schema_version` reasoning, and touching `discovery.py` + CLI + registry, none of which are in #269's touch-points. Folding it in would violate the ticket's scope and "complexity must earn its place." The Spec §4 approval surface (and the Research→Specify complexity-escalation gate) is the place to confirm narrow-scope-plus-follow-up vs. expand.
- **OQ-B (test home — RESOLVED, Spec to confirm):** add the heading-vocabulary assertion to `tests/test_discovery_gate_presentation.py` (raw-text negative+positive), not `tests/test_discovery_module.py` (the ticket-named file, which tests the Python module). The ticket's touch-point naming is corrected here.
- **OQ-C (fixtures — DEFERRED to Spec phase):** `tests/fixtures/discovery-brief/{diagnostic,simple,complex}-topic/research.md` still use the old headings. *Recommendation:* leave for #269 and include in the OQ-A follow-up. *Rationale:* no current test negatively asserts fixture heading content, so leaving them is safe for #269's correctness; conforming them expands the blast radius and risks the `generate-brief` fixture-driven tests (`test_brief_passes_all_fixtures`, `test_gate_renders_brief_not_architecture`) which parse Architecture content. Spec confirms leave-vs-conform.
