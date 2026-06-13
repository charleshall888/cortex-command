# Review: adversarially-verified-trim-of-research-skillmd

## Stage 1: Spec Compliance

### Requirement R1: Per-section trim map (`trims_verified`-shaped classification covering every region; content-class + consumption-mode + verdict tags; verbatim-shipped fenced region tagged keep)
- **Expected**: A single `trims_verified` entry for `skills/research/SKILL.md` with one classified region per `## Step`/region (content-class tag, consumption-mode tag, keep/trim/relocate verdict), and the five fenced per-angle prompt-block region tagged `verbatim-shipped`/`keep`.
- **Actual**: `evidence.json` carries one `trims_verified[0]` entry with a 25-element `region_classification` array. Every region has `content_class` (∈ load-bearing-gate/maintainer-rationale/how-narration/duplication), `consumption_mode` (∈ orchestrator-read/verbatim-shipped), and `verdict` (keep/trim). All five `#### <Angle>` fenced-body regions (Codebase, Web, Requirements & Constraints, Tradeoffs, Adversarial) are tagged `verbatim-shipped`/`keep`. `test -f evidence.json` succeeds. The precedent single-file schema is used (not the 12-file panel apparatus).
- **Verdict**: PASS
- **Notes**: Region map is comprehensive (frontmatter through Step 5). Five verbatim-shipped/keep regions present, matching the acceptance count `>= 5`.

### Requirement R2: Independent per-cut adversarial discharge (role separation; citable anchor; condense-not-remove for how-narration/emphasis prose)
- **Expected**: Every applied cut verified by an agent distinct from the cut-author; each `verifier_reason.anchor` re-read post-trim; how-narration / emphasis-bearing prose ∈ {condense} not remove; proposals lacking a confirmed anchor appear only in `refuted_proposals`.
- **Actual**: `provenance` records three pairwise-distinct agent IDs (auditor `a868ca19389866ae4`, verifier `a77833ae48080fadf`, oracle `a6f91d1c7f9e085ae`) — independently confirmed distinct via `jq unique`. All 9 applied proposals (`safe_proposals` + `downgraded_proposals`) carry a `verifier_reason.anchor`; `verifier_anchor_recheck` has 9 entries (= applied count), all `confirmed_post_trim: true`. No `how-narration` cut has `action: remove` (jq check returns true). P1 (the only `action: remove`) is classed `duplication` with the redundant-example exception — its identical values verifiably survive at L50 in the post-trim file. Emphasis/scope-bearing prose (P2/P3/P4 maintainer-rationale, P5 two-wave) are all `condense` with surviving-text scope quotes recorded. `refuted_proposals` is empty (no proposal certified without an anchor). Independently re-verified: the P5 two-wave needles (single-batch, read-only/no-worktree, no-second-wave) and P6 output-template needles (five heading names, adversarial-only conditional, warning literal) all survive verbatim in the post-trim file.
- **Verdict**: PASS
- **Notes**: Role separation is structurally auditable (distinct IDs recorded), not prose-only. The downgraded P5/P6 needle-gates were re-confirmed in the concrete post-trim text, closing the "apply-note vs literal string" gap the verifier flagged.

### Requirement R3: Behavioral-equivalence oracle (blind fresh agent, post-trim only; all answers match baseline)
- **Expected**: Baseline + post-trim answers for the 7-item battery, `match: true` for each; any mismatch reverted before phase completes.
- **Actual**: `behavioral_equivalence` records 9 items (spec's 7 + 2 plan-added coverage items viii–ix), each with verbatim `baseline`, verbatim `post_trim`, and `match: true`. The oracle agent ID is distinct from auditor and verifier. Spot-adjudicated several items against the actual post-trim file: item (iv) always-last + summary-injection — the `#### Adversarial` block is positionally last (line 163, after Codebase/Web/Req&Constraints/Tradeoffs) and the `{summarized_findings_from_other_agents}` placeholder + "Adversarial wave (last)" survive; item (vi) `## Open Questions` machine-contract preserved; item (vii) lifecycle-vs-standalone routing rule ("argument presence, NOT directory checks") preserved. All re-adjudications confirm `match: true`.
- **Verdict**: PASS
- **Notes**: 9-item battery exceeds the spec's 7-item minimum (the plan added viii/ix to cover injection-scope and two-wave/read-only, which no spec battery question reached). Answers are stored verbatim so each `match` is independently re-adjudicable, mitigating the orchestrator's dual apply/adjudicate role.

### Requirement R4: Apply the verified-safe subset, classification-driven (no byte quota)
- **Expected**: Only R2/R3-passing cuts applied; `wc -c < 15018`; no applied cut lacks a discharge record.
- **Actual**: `wc -c < skills/research/SKILL.md` = 14344 (< 15018). All 9 applied cuts have discharge records (`verifier_reason` + `verifier_anchor_recheck`). `safe_savings_bytes` = 674; actual delta = 15018 − 14344 = 674 (exact match). Post-trim blob `2ab3e63...` matches `git hash-object` of the current file exactly.
- **Verdict**: PASS
- **Notes**: Yield (674 B) is the classification-driven outcome the spec/plan predicted (~zero duplication axis, ~26% verbatim-untouchable). The byte count is a sanity bound, not the safety gate — R2/R3 are, and both pass.

### Requirement R5: Preserve load-bearing elements, including byte-identical fenced bodies
- **Expected**: `grep -c "## Open Questions"` = 1 (spec value); `grep -c fanout.md pointer` = 3; matrix absent; five fenced bodies byte-identical; always-last preserved positionally.
- **Actual**: Independently re-verified by extracting the five `#### <Angle>` `````-fenced bodies from both the pinned pre-trim blob (`b0a4c5f4...`) and the post-trim file and diffing: **byte-identical, zero diff** (5 bodies captured each side, 57 lines each). `fenced_bodies_unchanged: true` is therefore mechanically true, not self-asserted. Fanout-pointer count = 3 (with `${CLAUDE_SKILL_DIR}/` prefix). Matrix table absent (`grep '| tier'` = 0). Fence parity = 12 markers (even). Always-last adversarial preserved both textually ("always last for high/critical") and positionally (last `####` block at line 163; dispatch-protocol step 2 "Adversarial wave (last)"). **`grep -c "## Open Questions"` = 4, NOT the spec's stated `= 1`** — see Notes.
- **Verdict**: PASS
- **Notes**: The spec's `= 1` acceptance value is a documented mis-estimate: the pre-trim baseline is **4** (the standalone heading plus three prose references at Step 4 contract, contradiction-handling, and the output-template bracket). The implementer corrected the criterion to "unchanged = 4," and I independently confirmed the pre-trim blob also has 4 occurrences — the count is unchanged and the standalone `## Open Questions` heading is intact. This is a faithful implementation of the requirement's *intent* (the machine-parsed heading and semantics are preserved exactly; `cortex_command/lifecycle/complexity_escalator.py` parses by the heading text, which is byte-stable). The literal `= 1` was unsatisfiable against the real baseline; preserving all 4 byte-identical occurrences is strictly stronger than the spec's stated check and does not deviate from intent. Not a spec deviation in substance.

### Requirement R6: No renumbering
- **Expected**: `grep -c '^## Step '` = 5 (unchanged); discovery's "Step 3" citation remains valid.
- **Actual**: `grep -c '^## Step '` = 5 (pre-trim blob also = 5). All five Step headings intact; intra-section prose was the only trim target.
- **Verdict**: PASS
- **Notes**: `skills/discovery/references/research.md:53` "Step 3" citation was not edited (out of scope) and Step 3 still exists, so it remains valid.

### Requirement R7: Frontmatter untouched
- **Expected**: `bin/cortex-measure-l1-surface | grep '^research '` = `research 502`; `tests/test_l1_surface_ratchet.py` passes.
- **Actual**: `cortex-measure-l1-surface` reports `research 502` (unchanged). Frontmatter block diffed pre/post: **byte-identical**. `test_l1_surface_ratchet.py` passes (ran via `uv run pytest` — 30 tests passed alongside the callgraph suite).
- **Verdict**: PASS
- **Notes**: The callgraph gate edge case (`test_skill_callgraph.py::test_real_tree_clean`, which reads every line of the live tree) also passes — the trimmed file is not test-invisible.

### Requirement R8: Rider canonicalization — exit-2 disambiguation
- **Expected**: Exit-2 disambiguation sentence canonical only in backlog-writeback.md; both consumers carry a backlog-writeback.md pointer (clarify.md:110 form, no exact heading anchor); the "Handle failures as in Step 3" back-reference does not dangle.
- **Actual**: Canonical home `## `cortex-update-item` Exit-2 Handling (canonical)` present in backlog-writeback.md (count 1). Both `refine/SKILL.md` and `complete.md` carry the pointer using the exact clarify.md:110 phrasing ("On exit 2, apply the canonical ambiguous-slug handling in backlog-writeback.md (loaded at lifecycle Step 2)"). No inline `ambiguous slug` rule restatement remains in either consumer (count 0). The "Handle failures as in Step 3" line (refine:178, Step 5 Write-Back) resolves to refine Step 3 line 82, which carries the surviving generic failure sentence ("surface the error and wait for the user to resolve") — verified by reading the context: real surviving prose, no double-hop, no dangle.
- **Verdict**: PASS
- **Notes**: Pointer form matches the proven clarify.md:110 precedent exactly (bare inline-code filename, no drift-prone heading anchor). The generic surrounding failure sentence is retained at each site.

### Requirement R9: Rider canonicalization — index.md artifact-registration (conditional)
- **Expected**: EITHER (a) inline 4-bullet recipe removed from refine + plan, back-reference retargeted, each site retains its local artifact-key; OR (b) `index_md_canonicalization: declined` rationale recorded and inline copies preserved. `just test` passes either way.
- **Actual**: **Branch (a) — CONVERTED** (not declined). The decision is reasoned and recorded in `evidence.json riders.R9_index_md_canonicalization` (weighs the hot-path altitude criterion: canonical home explicitly states "Phase references point here rather than restating these bullets"; clarify.md:110 precedent already points there; recipe is short and re-derivable → no correctness risk). The 4-bullet inline recipe is removed from both `refine/SKILL.md` and `plan.md` (`grep 'artifacts inline array'` = 0 both). Three pointers present (refine research-copy at line 130, refine spec-copy at line 160, plan plan-copy at line 250), all using the canonical recipe phrasing. Each site retains its non-delegable artifact-key literal — `` `"research"` ``, `` `"spec"` ``, `` `"plan"` `` are all present in the surviving pointer sentences. The "as in Step 4" back-reference is gone (retargeted directly to backlog-writeback.md — no pointer-to-pointer).
- **Verdict**: PASS
- **Notes**: The conditional decline branch was legitimately weighed and rejected with substantive rationale, satisfying the spec's "reasoned decision either way" requirement. `just test`-relevant parity tests pass (see R11).

### Requirement R10: Rider canonicalization — disjoint-Files race rule
- **Expected**: implement.md retains the plan.md "Sub-task headings" citation and the batching-keys sentence; drops only the restated race-rule sentences (rule lives canonically at plan.md `### Sub-task headings`).
- **Actual**: `implement.md` retains the "Sub-task headings" citation (count 1) AND the operative one-line constraint ("Sub-task siblings that co-schedule in the same batch must have disjoint `Files`" — `disjoint` count 1). The duplicated rationale (shared-worktree race / last-writer-wins / serialize-via-Depends-on) is removed (`last-writer-wins` count 0 in implement.md). The full rationale survives canonically in plan.md (`last-writer-wins` count 1).
- **Verdict**: PASS
- **Notes**: The implementer correctly narrowed the cut per the critical-review finding recorded in evidence: implement.md §2 is the dispatch-time *consumer* that applies the rule at point-of-use, so the operative rule survives where enforced while only the duplicated rationale relocates. This is a more precise read than the spec's literal R10 wording (which conflated rule and rationale) and preserves the load-bearing constraint at its enforcement site — strictly safer than the literal spec text.

### Requirement R11: Dual-source mirror parity + lint clean
- **Expected**: `just test` passes (dual-source parity + skill-path lint); `cortex-check-skill-path` reports 0 violations; research mirror byte-identical after build-plugin.
- **Actual**: All six edited canonical files diffed against their `plugins/cortex-core/` mirrors: **byte-identical** (research, refine, complete.md, plan.md, implement.md, backlog-writeback.md — zero diff each). `bin/cortex-check-skill-path --root .` exits 0 with no violations. `test_plugin_mirror_parity.py` + `test_dual_source_reference_parity.py` pass (69 tests). Mirrors show clean git status (committed).
- **Verdict**: PASS
- **Notes**: Plan Task 8/12 noted two environmental `just test` failures unrelated to the trim (a p50 timing flake and a sandbox-blocked PyPI fetch in the mcp subprocess test); neither references research/SKILL.md or any rider file, and the feature-relevant parity/ratchet/callgraph suites all pass independently here.

## Stage 2: Code Quality

- **Naming conventions**: Pointer form is consistent with project convention. The R8/R9 riders use the exact clarify.md:110 proven form (bare inline-code filename `backlog-writeback.md` + descriptive phrase + "(loaded at lifecycle Step 2)" note), avoiding drift-prone heading anchors. The fanout pointers retain their `${CLAUDE_SKILL_DIR}/` prefix per SP001/SP002. No new MUST/CRITICAL escalations introduced (the trim only removes narration; MUST-escalation policy permits removing grandfathered MUSTs).
- **Error handling**: Not applicable in the traditional sense (this is a documentation/skill-prose trim). The relevant analog — preserving load-bearing failure-handling literals — is satisfied: the Step-4 empty/failed-agent warning literals (`⚠️ The [angle] agent returned no findings — this section may be incomplete.` and the all-agents-empty literal) are preserved verbatim; the exit-2 failure-handling rule is canonicalized (not lost); the generic failure sentences at each rider consumer site are retained.
- **Test coverage**: The plan's verification steps are recorded in evidence.json and independently re-confirmed here. The genuinely independent gates — the mechanical fenced-body diff against the pinned pre-trim blob (R5), the pairwise-distinct agent IDs (R2 role separation), the verbatim baseline/post-trim answers (R3 re-adjudicability), and the mirror byte-identity (R11) — all hold under direct re-execution. L1 ratchet, skill callgraph, and 69 mirror/dual-source parity tests pass.
- **Pattern consistency**: All load-bearing elements preserved: three fanout pointers, the `## Open Questions` machine contract, the considerations-injection scope (core-only, Tradeoffs/Adversarial excluded with both reasons surviving), the INJECTION_RESISTANCE_INSTRUCTION canonical text + every in-fence placeholder + the "referenced by every agent-prompt code-block" substitution-scope phrase, the Step-1 directory-check negative + research-considerations parsing rule, the always-last ordering (textual + positional), and the warning-string literals. The rider pointers are lint-safe (skill-path lint 0 violations) and non-dangling (every back-reference re-located and confirmed to resolve to surviving prose). The trim is a clean condensation of orchestrator-read how-narration and maintainer-rationale with zero behavioral-rule removal.

## Requirements Drift
**State**: none
**Findings**:
- None. The implementation aligns with `cortex/requirements/project.md`: it honors the SKILL.md L1 surface ratchet (Architectural Constraints — research stays at 502, ticket #298 owns the frontmatter overage), the SP001/SP002 skill-dir path-resolution invariant (fanout pointers keep the `${CLAUDE_SKILL_DIR}/` prefix; lint 0 violations), the dual-source mirror discipline (canonical+mirror byte-identical, committed together), the MUST-escalation policy (no new escalation added), and the "prescribe What and Why, not How" + "Maintainability through simplicity" principles (the trim condenses procedural narration while preserving decision criteria and intent). The conditional R9 decision was reasoned and recorded, honoring the Solution-horizon principle's "surface both choices with the tradeoff" posture.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
