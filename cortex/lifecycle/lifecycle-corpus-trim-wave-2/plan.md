# Plan: lifecycle-corpus-trim-wave-2

## Overview
Three-phase execution: build the wrapper verbs first (in-process composition of existing module functions, envelope conventions from prepare_worktree), then the structural wave (route-conditional extractions, splits, merges, prose rewiring onto the verbs, test re-anchoring in the same tasks as the moves), then compression and closeout gated by a clause-parity adversarial review and route-table recompute. Spec: `cortex/lifecycle/lifecycle-corpus-trim-wave-2/spec.md`; load-path baselines and pin ledger: `research.md`.

## Outline

### Phase 1: Wrapper verbs (tasks: 1, 2, 3, 4)
**Goal**: Three new console-scripts built, tested, registered, and adversarially reviewed.
**Checkpoint**: `pytest cortex_command/lifecycle/tests/ tests/test_lifecycle_event_roundtrip.py` green; `just validate-commit` lint set passes.

### Phase 2: Structural wave (tasks: 5, 6, 7, 8)
**Goal**: Route-conditional topology in place; prose rewired onto the verbs; every moved pin re-anchored.
**Checkpoint**: full `just test` green modulo the documented pollution baseline; delegation route reads 1 file, trunk route skips worktree machinery.

### Phase 3: Compression and closeout (tasks: 9, 10, 11, 12, 13)
**Goal**: Checklist split+compression, situational trims, sub-skill safe cuts — all clause-parity-verified; targets measured.
**Checkpoint**: R13 funded targets met (route table recompute); two end-to-end drives pass; mirrors clean.

## Tasks

### Task 1: Build cortex-lifecycle-register-artifact
- **Files**: cortex_command/lifecycle/register_artifact.py, cortex_command/lifecycle/tests/test_register_artifact.py, pyproject.toml, bin/cortex-lifecycle-register-artifact
- **What**: New verb `--feature X --artifact {research|spec|plan|review}`: skip-if-present append to index.md `artifacts:` inline array + `updated:` date bump, regex capture-rewrite + atomic_write (spec R3). This task adds ONLY its own `[project.scripts]` row and wires it via the tests surface (a real assertion naming the literal `cortex-lifecycle-register-artifact`) so the W003 parity gate passes without exception rows — Tasks 2/3 each do the same for their own verb, serialized by dependencies so pyproject.toml never has two same-batch writers.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Model the array rewrite on `cortex_command/backlog/update_item.py::_remove_uuid_from_blocked_by` (re.MULTILINE capture groups) and `atomic_write` from `cortex_command/common.py`. Index format: unquoted inline flow list, hand-rendered like `create_index.py::_render_tags` — PyYAML cannot round-trip it. Root resolution: `_resolve_user_project_root_from_cwd` flavor (Complete-phase sibling); tests use `monkeypatch.chdir(tmp_path)` + delenv CORTEX_REPO_ROOT. Envelope: `{state, ...}` compact json.dumps, KNOWN_STATES tuple, never-crash main per `prepare_worktree.py`. bin wrapper copied from `bin/cortex-lifecycle-counters` (dual-channel + cortex-log-invocation shim).
- **Verification**: (a) `pytest cortex_command/lifecycle/tests/test_register_artifact.py -q` exits 0; includes a byte-format round-trip test and a double-register no-op test.
- **Status**: [x] complete

### Task 2: Build cortex-lifecycle-enter
- **Files**: cortex_command/lifecycle/enter.py, cortex_command/lifecycle/tests/test_enter.py, pyproject.toml, bin/cortex-lifecycle-enter
- **What**: Compose create_index + start_sync + init_ensure + `.session` write in-process; return `{state, backlog_status}` envelope; all discriminants caller-passed (spec R1). Adds its own pyproject row; wires via a tests-surface assertion naming `cortex-lifecycle-enter` (W003).
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: `create_index(feature, backlog_file, root)` from `cortex_command/lifecycle/create_index.py` (skip-if-exists; OSError → exit 1). `sync(...)` from `start_sync.py` (raises `_Exit2` → exit 2; only writes lifecycle-slug association when `--phase none`). `init_ensure.main([])` is exit-code-shaped — wrap its int return into the envelope. `.session`: `Path("cortex/lifecycle/{feature}/.session").write_text(session_id)`. Flags: `--feature --session-id --backend --phase --backlog-file` (ADR-0019: never self-resolve backend or re-derive new-vs-resume — Adversarial #3 in research.md). `backlog_status`: empty `--backlog-file` → `no_match`; else read `cortex/backlog/{backlog-file}` and regex the frontmatter scalar `^status:\s*(\S+)` (re.MULTILINE, first match wins) — `complete` → `already_complete`, anything else → `open`; never auto-close. Root: env-var flavor (`_resolve_user_project_root`), tests `monkeypatch.setenv("CORTEX_REPO_ROOT", tmp_path)`. Monkeypatch composed primitives on the verb's own module namespace (test_prepare_worktree.py pattern).
- **Verification**: (a) `pytest cortex_command/lifecycle/tests/test_enter.py -q` exits 0; every KNOWN_STATES member reachable; exception-to-JSON test present; named tests for `backlog_status` = `no_match` (empty backlog-file) and `already_complete`; (b) `grep -c 'cortex-lifecycle-enter' pyproject.toml` = 1.
- **Status**: [x] complete

### Task 3: Build cortex-lifecycle-finalize
- **Files**: cortex_command/lifecycle/finalize.py, cortex_command/lifecycle/tests/test_finalize.py, pyproject.toml, bin/cortex-lifecycle-finalize
- **What**: Compose backend-gated update_item(status=complete) + counters read + idempotent feature_complete emission with `merge_anchor: "merge"` (spec R2). Adds its own pyproject row; wires via a tests-surface assertion naming `cortex-lifecycle-finalize` (W003).
- **Depends on**: [1, 2]
- **Complexity**: complex
- **Context**: `update_item(item_path, fields, backlog_dir, session_id)` from `cortex_command/backlog/update_item.py` (its tail already regens the index via subprocess — do NOT add a second regen; Step 10's fallback is retired). Counters: `count_tasks(plan_path)`, `count_rework_cycles(events_log)` from `cortex_command/lifecycle/counters.py`, called with resolved Paths. Emission: `log_event` from `cortex_command/lifecycle_event.py` behind a new events.log scan matching parsed `{"event": "feature_complete"}` rows (no substring match). CRITICAL: emit `merge_anchor: "merge"` — `cortex_command/pipeline/metrics.py:237,998` segments interactive vs legacy-overnight on it; `overnight/advance_lifecycle.py` deliberately omits it and is NOT a template (research.md Adversarial #5). Backend gate: `--backend` caller-passed; `none` → skip update_item, still emit the event; external → return `state: external-backend` for the skill's best-effort arm. Root: chdir flavor. No new event names; no schema_version-first shape (ADR-0020). EXIT-2 CARVE-OUT: ambiguous-slug from update_item propagates as exit 2 with candidates on stderr (mirror start_sync's `_Exit2`) — this error class is exempt from the never-crash JSON envelope; only unexpected exceptions JSON-encode.
- **Verification**: (a) `pytest cortex_command/lifecycle/tests/test_finalize.py -q` exits 0; asserts emitted row contains `"merge_anchor": "merge"`; second-invocation no-duplicate test present; ambiguous-slug exit-2 propagation test present; (b) `grep -c 'cortex-lifecycle-finalize' pyproject.toml` = 1.
- **Status**: [x] complete

### Task 4: Register verbs and adversarially review verb code
- **Files**: bin/.events-registry.md, tests/test_lifecycle_event_roundtrip.py
- **What**: Update the feature_complete producers row (Python emitter, scan_coverage manual); dispatch a fresh adversarial-review agent over the three landed verb commits (b2f4db15, 28df4dce, 1f87008a: fail-open guards, exit-contract escapes, hardcoded branches, swallowed exit codes — the prior campaign's verb-bug classes) and fix confirmed findings. NOTE: the W003 exception rows for create-index/start-sync are DECIDED but land with Tasks 7/8 (the commits that remove their prose wiring) — adding them earlier trips W005 allowlist-superfluous while prose still references the binaries. The three new verbs need no exception rows (wired via tests/test_lifecycle_verb_deployment.py).
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: Registry gate only fails on unregistered names appearing, so the edit is documentation-accuracy; FILE_EVENTS edits for prose files land with the prose tasks (6, 7), not here. The R10a init-ensure literal pin (`cortex_command/lifecycle/tests/test_init_ensure.py`) is updated in Task 7 alongside the SKILL.md edit.
- **Verification**: (a) `just validate-commit` exits 0 on the staged Phase-1 set; adversarial-review findings list resolved (each fixed or explicitly dismissed in the task report); (b) `grep -c 'cortex-lifecycle-\(enter\|finalize\|register-artifact\)' pyproject.toml` = 3 (all entries survived).
- **Status**: [x] complete

### Task 5: Extract worktree-entry.md from implement.md
- **Files**: skills/lifecycle/references/implement.md, skills/lifecycle/references/worktree-entry.md, tests/test_lifecycle_step_v_ordering.py, tests/test_implement_worktree_interactive_contract.py, tests/test_lifecycle_enterworktree_callsites.py, tests/test_lifecycle_picker_label_pins_worktree.py, skills/lifecycle/references/kept-pauses.md
- **What**: Move §1a + Step A + fallback + vi (~4.6K) to worktree-entry.md loaded on both worktree entry seams (`resolved`:worktree-interactive AND picker-selection); re-anchor the four contract tests to the new file (spec R5).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Load trigger keys on the SELECTION, not the verb state (`prompt` precedes the choice — critical-review objection 2). The extracted file carries the full selected/suppressed branch; implement.md §1 hands off the entry-mode marker at both routing points with imperative "Read … and follow" links. Preserve verbatim: `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, step labels i–vii ("do not renumber"), `bash -s --` exactly once per file, `cortex-lifecycle-prepare-worktree` absent from §1 / present unconditionally in the i→v block (no `selected`/`suppressed` tokens inside that block), picker labels in §1. `${CLAUDE_SKILL_DIR}` propagation per ADR-0009; SP002-compliant paths. kept-pauses.md `implement.md:21` anchor moves with the picker (stays in implement.md §1) — update line number only.
- **Verification**: (a) `pytest tests/test_lifecycle_step_v_ordering.py tests/test_implement_worktree_interactive_contract.py tests/test_lifecycle_enterworktree_callsites.py tests/test_lifecycle_picker_label_pins_worktree.py tests/test_lifecycle_kept_pauses_parity.py -q` exits 0; (b) `wc -c skills/lifecycle/references/implement.md` ≤ 7400 (≥4KB drop from 11,471 baseline).
- **Status**: [x] complete

### Task 6: Split complete.md and rewire finalize
- **Files**: skills/lifecycle/references/complete.md, skills/lifecycle/references/complete-first-run.md, cortex_command/lifecycle_config.py, tests/test_skill_section_citations.py, tests/test_lifecycle_event_roundtrip.py, skills/lifecycle/references/kept-pauses.md
- **What**: Extract Steps 1–6 to complete-first-run.md; retained file keeps Step 7 router + Steps 8–12 + first-run on-main short-circuit note; replace Steps 9–11 prose with one `cortex-lifecycle-finalize` call (spec R6, R8-complete side).
- **Depends on**: [3, 7]
- **Complexity**: complex
- **Context**: on_main semantics per corrected spec edge case: first-run short-circuit in the retained note; re-invocations through Step 7 (verb unchanged, `on_main → Step 9` continue_to already exists). Preserve: `finalization-commit-step` fence + its positive/negative token set (Step 11a is NOT absorbed by finalize); `### Step 7` region contract (verb invocation present, nine terminal strings absent); `### Step 2 — Commit Lifecycle Artifacts` heading — moves to complete-first-run.md, so co-update the `lifecycle_config.py:8-9` citation and the citation test (the test docstring's `95-96` pairing is stale — lines 95-96 are blank; correct the docstring in the same edit). Complete.md's Step 11 prose event invocation disappears — the merge_anchor pin now lives in Task 3's Python test (closes the FILE_EVENTS gap without a stale entry). kept-pauses `complete.md:38` phase-exit anchor: Step 6 moves to complete-first-run.md — update the inventory entry's file:line.
- **Verification**: (a) `pytest tests/test_lifecycle_complete_state_routing.py tests/test_complete_md_finalization_commit.py tests/test_skill_section_citations.py tests/test_lifecycle_kept_pauses_parity.py -q` exits 0; (b) `wc -c skills/lifecycle/references/complete.md` ≤ 5200.
- **Status**: [ ] pending

### Task 7: Rewire SKILL.md Step 2 + backlog-writeback onto verbs
- **Files**: skills/lifecycle/SKILL.md, skills/lifecycle/references/backlog-writeback.md, skills/lifecycle/references/plan.md, skills/lifecycle/references/review.md, skills/refine/SKILL.md, cortex_command/lifecycle/tests/test_init_ensure.py, tests/test_lifecycle_event_roundtrip.py, skills/lifecycle/references/kept-pauses.md
- **What**: SKILL.md Step 2 collapses to one `cortex-lifecycle-enter` call + the close/continue decision; backlog-writeback.md keeps status-check + exit-2 rule, drops start-sync/create-index prose and the artifact-registration recipe; plan/review/refine call sites use `cortex-lifecycle-register-artifact` one-liners (spec R1, R3, R8).
- **Depends on**: [1, 2, 4]
- **Complexity**: complex
- **Context**: Delete `FILE_EVENTS["skills/lifecycle/references/backlog-writeback.md"]["feature_complete"]` (close-lifecycle branch now names the finalize verb). DECIDED (plan-phase resolution of the spec's Open Decision, init-ensure half): re-pin `test_init_ensure.py::test_r10a/r10b` to the literal `cortex-lifecycle-enter` in canonical + mirror SKILL.md; the `cortex-lifecycle-init-ensure` binary and its module tests are retained unchanged. W003 timing: add the DECIDED bin/.parity-exceptions.md row for `cortex-lifecycle-start-sync` in this same commit (its last prose wiring vanishes here); `cortex-lifecycle-create-index`'s row lands with Task 8 (discovery-bootstrap deletion) if check-parity fires. SKILL.md Step 1 KNOWN_STATES backtick list and invocation-grammar forms untouched; L1 frontmatter untouched. kept-pauses `backlog-writeback.md:16` and `SKILL.md:34` anchors re-lined. E101: prose invocation flags must match the new argparse surfaces exactly.
- **Verification**: (a) `pytest tests/test_lifecycle_event_roundtrip.py tests/test_lifecycle_kept_pauses_parity.py tests/test_lifecycle_invocation_grammar_parity.py cortex_command/lifecycle/tests/test_init_ensure.py -q` exits 0; (b) `wc -c skills/lifecycle/SKILL.md skills/lifecycle/references/backlog-writeback.md` total ≤ 9000.
- **Status**: [ ] pending

### Task 8: Merge delegation references
- **Files**: skills/lifecycle/references/refine-delegation.md, skills/lifecycle/references/complexity-escalation.md, skills/lifecycle/references/post-refine-commit.md, skills/lifecycle/references/discovery-bootstrap.md, skills/lifecycle/SKILL.md, tests/test_lifecycle_event_roundtrip.py
- **What**: refine-delegation.md absorbs complexity-escalation, post-refine-commit, and discovery-bootstrap's three refine-facing sections (Epic Research Detection, Epic Context Injection, Refine Starting-Point Rules); delete the three absorbed files; delete the stale post-Clarify `lifecycle_start` bullet; shrink SKILL.md's placeholder block (spec R7, R12).
- **Depends on**: [6, 7]
- **Complexity**: complex
- **Context**: The stale bullet is a verified duplicate: `cortex-refine emit-lifecycle-start` (idempotent seed, refine SKILL Step 2) + `reconcile-clarify` own the lifecycle_start row; `cortex-lifecycle-event lifecycle-start` appends unconditionally → duplicate row per delegated run. FILE_EVENTS: refine-delegation.md loses `lifecycle_start` (×1→0), keeps `phase_transition`; move rows for events whose text migrates files. Merged file ≤ sum of absorbed sections (spec R7 honesty clause). `<DISCOVERY_BOOTSTRAP_MD>`/`<COMPLEXITY_ESCALATION_MD>`/`<POST_REFINE_COMMIT_MD>` placeholders collapse; `<REFINE_SKILL_MD>` stays. events-registry `lifecycle_start` producers row updated.
- **Verification**: (a) `pytest tests/test_lifecycle_event_roundtrip.py -q` exits 0; (b) `ls skills/lifecycle/references/ | grep -c 'complexity-escalation\|post-refine-commit\|discovery-bootstrap'` = 0; `grep -c 'lifecycle-start' skills/lifecycle/references/refine-delegation.md` = 0; `wc -c` of merged refine-delegation.md ≤ sum of absorbed source sections (record both numbers in the task report).
- **Status**: [ ] pending

### Task 9: Split and compress orchestrator-review checklists
- **Files**: skills/lifecycle/references/orchestrator-review.md, skills/lifecycle/references/orchestrator-checklist-specify.md, skills/lifecycle/references/orchestrator-checklist-plan.md, skills/refine/references/specify.md, skills/lifecycle/references/plan.md
- **What**: Post-Specify and Post-Plan checklists become two phase-loaded references; shared protocol stays in orchestrator-review.md; compress criteria phrasing across all 17 items preserving every condition/skip/gating clause (spec R9).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Preserve in orchestrator-review.md: `--role orchestrator-fix --criticality "$(cortex-lifecycle-state` + "halt and escalate" within its 900-char window, criticality-matrix.md citation (single-source rule — never restate "tier/criticality are unknowable"). Callers (specify.md §3a via refine, plan.md §3a) point at their phase checklist. Named untouchables: S7/P8/P10 skip rules, P7 benign-vs-harmful, S1/P4 binary-checkable definitions; every other item keeps its condition set — Task 12 verifies clause parity.
- **Verification**: (a) `pytest tests/test_model_resolution_wiring.py tests/test_plugin_mirror_parity.py -q` exits 0 (mirror rebuilt in Task 13); (b) `wc -c` of shared file + one checklist ≤ 4300.
- **Status**: [x] complete

### Task 10: Situational trims and SKILL.md dedup
- **Files**: skills/lifecycle/SKILL.md, skills/lifecycle/references/kept-pauses.md, skills/lifecycle/references/competing-plans.md, skills/lifecycle/references/review.md, skills/lifecycle/references/criticality-matrix.md, skills/lifecycle/references/plan.md
- **What**: kept-pauses pointer marked tests-only; competing-plans fallback middle-trim (~1K); review.md drift prose-trim (~0.5–0.8K, protocol intact); plan.md §4 picker-restatement cut; SKILL.md per-phase completion-rule collapse + word-level pass (spec R10, C6/C7 audit items).
- **Depends on**: [7, 8]
- **Complexity**: complex
- **Context**: competing-plans keeps: both model-resolution contracts (competing-plan criticality-keyed AND synthesizer no-criticality + rationale phrase within 600 chars), `plan_comparison` literal + v2 event schema, structured fallback table + graft recording. review.md keeps: reviewer-prompt Verdict JSON contract, §4a parse/apply/2-retry/breach protocol, `### 4a. Auto-Apply Requirements Drift` heading, FILE_EVENTS counts (review_verdict×1, drift_protocol_breach×1, phase_transition×3). plan.md keeps `### 1a./### 1b./### 5.` headings, `**Files**:`/`**Depends on**:` labels (parser-load-bearing, no automated guard), critical-arm wire line (single line containing critical+read+competing-plans). Also retarget plan.md §4's "see Implement §1" cross-references for suppressed-routing/probe-degrade to the content's post-Task-5 home (worktree-entry.md) — no test pins this destination, so verify by grep. Load-bearing rules to section edges (lost-in-the-middle).
- **Verification**: (a) `pytest tests/test_model_resolution_wiring.py tests/test_competing_plans_wired.py tests/test_skill_section_citations.py tests/test_lifecycle_event_roundtrip.py tests/test_lifecycle_kept_pauses_parity.py -q` exits 0.
- **Status**: [ ] pending

### Task 11: Sub-skill safe cuts
- **Files**: skills/refine/SKILL.md, skills/refine/references/clarify-critic.md, skills/refine/references/research-phase.md, skills/refine/references/specify.md, skills/critical-review/SKILL.md, skills/critical-review/references/a-to-b-downgrade-rubric.md, skills/research/SKILL.md, skills/research/references/angle-templates.md
- **What**: Apply the audited safe/probably-safe cuts only: refine ~1.1K, critical-review ~0.4K (rubric cut = the duplicate opening sentence only), research ~600B dedup (spec R11).
- **Depends on**: [7, 9]
- **Complexity**: simple
- **Context**: Byte-preserve: clarify-critic's five injection-defense strings + placeholders + heading anchors (`## Confidence Assessment` → `{IF parent_epic_loaded:` → `## Parent Epic Alignment` → `## Instructions` order), unreadable-parent warning template; critical-review total-failure literal (both copies), synthesizer sentinel opener, `{a_to_b_rubric}`/`{artifact_path}`/`{artifact_sha256}` placeholders, `---` template delimiter; research `cortex-resolve-model --role searcher` + "do not halt" (SKILL) and fanout pins/table; refine SKILL's reconcile-before-delegation ordering anchor (``specify.md` and follow it``), backend-gated write-back literals, `--areas` quirk sentence, specify.md §3b/§4 gate blocks (`"corrupted": true` + "run the gate", Complexity/value gate anchor + `(Recommended)` + rationale ordering + no "MUST decide"). L1 ratchet: research description drop keeps the three trigger phrases.
- **Verification**: (a) `pytest tests/test_clarify_critic_alignment_integration.py tests/test_critical_review_reference_pins.py tests/test_model_resolution_wiring.py tests/test_refine_reconcile_wiring.py tests/test_refine_lifecycle_start_wiring.py tests/test_refine_skill.py tests/test_research_fanout_matrix.py tests/test_l1_surface_ratchet.py tests/test_skill_descriptions.py -q` exits 0.
- **Status**: [ ] pending

### Task 12: Compression-diff adversarial review
- **Files**: cortex/lifecycle/lifecycle-corpus-trim-wave-2/compression-diff-review.md
- **What**: Fresh adversarial agent compares old→new text of every file touched by Tasks 9–11 clause-by-clause; confirms no condition, gate, cap, retry limit, or pinned literal changed meaning; findings fixed or dismissed with rationale (spec R13 constraint-compliance check).
- **Depends on**: [9, 10, 11]
- **Complexity**: simple
- **Context**: Old text from `git show HEAD:<path>`; the reviewer's brief lists the named untouchables from Tasks 9–11 Context fields and asks it to hunt dropped conditions (the research finding: procedural-constraint compliance degrades before task success — check conditions specifically, not gist). Write the verdict artifact to the lifecycle dir.
- **Verification**: (b) `grep -c 'VERDICT: parity-confirmed' cortex/lifecycle/lifecycle-corpus-trim-wave-2/compression-diff-review.md` = 1 (issued only after all findings are resolved).
- **Status**: [ ] pending

### Task 13: Route-table recompute, drives, mirrors, full suite
- **Files**: cortex/lifecycle/lifecycle-corpus-trim-wave-2/route-table-after.md, plugins/cortex-core/ (regenerated)
- **What**: Recompute per-route loaded bytes; verify funded targets (A ≤84KB, C ≤21KB, D ≤16KB, F ≤12KB, always-on ≤9KB); run the two end-to-end drives; rebuild mirrors; full suite (spec R13).
- **Depends on**: [4, 5, 6, 8, 12]
- **Complexity**: complex
- **Context**: Byte script per research.md method (sum unique files per route). Drives: (1) worktree route through both entry seams (`resolved` + picker-`prompt`), confirming worktree-entry.md is read fully and Step v order holds; (2) complete re-invocation through Step 7 → finalize verb, confirming the emitted row carries merge_anchor merge. `just build-plugin` then `just test`; the order-dependent pollution baseline (test_templates + feature_cards) and sandbox mcp_subprocess DNS failure are pre-existing, not regressions.
- **Verification**: (a) route-table-after.md shows every funded target met, `just test` exit 0 modulo documented baseline; (b) `git status --porcelain plugins/` empty after rebuild.
- **Status**: [ ] pending

## Risks
- Batch order ≠ phase narrative: Task 9 (Phase 3) runs in batch 0 by design; its Files are disjoint from all batch-0 siblings — the Outline's phase grouping does not drive execution order.
- Task file counts exceed the 1–5 guideline on Tasks 5–7 because each structural move must re-anchor its test pins in the same change (atomicity beats sizing here); the What of each task remains single-concern.
- Route-A ceiling (≤84KB) has ~2–3KB of slack in the funding arithmetic; if word-level yields land low, the ceiling holds but the "−15%" narrative thins — surfaced at Complete, not silently absorbed.
- The picker-`prompt` load seam (Task 5) is model-behavioral; the Task 13 drive is the real gate, and the fallback (re-inline §1a) is pre-agreed in the spec.
- Task 7/8 touch SKILL.md sequentially by design (`Depends on`) to avoid same-file races.

## Acceptance
All five funded route targets in spec R13 measured and met in `route-table-after.md`; both end-to-end drives pass (Step v order on the worktree route; `merge_anchor: "merge"` on the finalize route); full suite + lint gates green with mirrors clean; compression-diff review verdict `parity-confirmed` with zero unresolved findings.
