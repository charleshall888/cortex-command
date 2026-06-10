# Plan: harness-token-efficiency-trim

## Overview

Apply the adversarially-verified token trim to the lifecycle/refine skill family in three waves: structural moves first (canonical homes and extractions, which change line geometry), then per-file prose trims (consuming `evidence.json` verdicts via a proposal ledger), then guards (ratchet + citation-pin tests, final audit). All edits are behavior-neutral by spec; every commit carries its own kept-pauses-inventory/parity updates and regenerated `plugins/cortex-core/` mirrors. Execution is strictly in task-number order (sequential dispatch in the main checkout on `feature/harness-token-efficiency-trim`); `Depends on` edges record the orderings that are load-bearing, and task-number order is the serializer for everything else.

**Proposal-ledger contract (applies to every Phase 2 task):** the task's deliverable is a per-proposal disposition for its files' `evidence.json → trims_verified` entries — each `safe_proposals` item applied as proposed, each `downgraded_proposals` item applied per its `downgrade_to`, each `refuted_proposals` item skipped, and any proposal whose target text was relocated by Phase 1 marked `moved:<destination>` (applied at the destination by the owning task, or logged-skipped with reason). The disposition list goes in the task's commit body. Byte deltas are diagnostics, not gates; the binding byte accounting happens once, in Task 13, with an explicit measurement method.

## Outline

### Phase 1: Structural moves (tasks: 1, 2, 3, 4, 5)
**Goal**: Create canonical homes and extractions (progressive disclosure, dedup targets, drift-pair sync) before prose trims, so line-geometry changes land once. Phase 1 also applies, at the destination, any verified proposal whose target text it relocates.
**Checkpoint**: New references exist (`refine-delegation.md`, `critical-review-gate.md`); every new cross-file pointer is body-resolved via the SKILL.md Reference-path propagation manifest (no bare relative paths — ADR-0009); `uv run pytest tests/test_lifecycle_kept_pauses_parity.py tests/test_post_refine_commit_wired.py` passes; pre-commit chain green on every commit.

### Phase 2: Verified prose trims (tasks: 6, 7, 8, 9, 10, 11)
**Goal**: Apply the proposal ledger file cluster by file cluster.
**Checkpoint**: Every proposal for the six clusters dispositioned (applied / applied-per-downgrade / skipped-refuted / moved); full `just test` green; pin tests named per task green.

### Phase 3: Guards and final audit (tasks: 12, 13)
**Goal**: Freeze the L1 frontmatter surface; pin the §-designators cited from `cortex_command/**`; reconcile final byte accounting with a defined measurement method.
**Checkpoint**: Both new guard tests green; citation pins mechanized (not self-certified); total net reduction across `skills/` ≥ 30KB by the Task 13 method.

## Tasks

### Task 1: Progressive disclosure structural moves (spec R4)
- **Files**: `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/refine-delegation.md` (new), `skills/lifecycle/references/backlog-writeback.md`, `skills/lifecycle/references/discovery-bootstrap.md`, `tests/test_post_refine_commit_wired.py`
- **What**: Extract SKILL.md's refine-delegation steps 1–6 (the block between the three-way spec/research gate and the phase table) into `references/refine-delegation.md`, applying the two verified proposals that travel with the block (event-logging JSON condensation, old SKILL.md:154–158; post-refine-commit sentence condensation, old :163) during extraction. Gate the discovery-bootstrap content structurally on its consumers, not on a phase list: the Epic-Context/Starting-Point read instruction lives inside `refine-delegation.md` (read exactly when delegation fires — including `phase=specify` and the spec-without-research branch), and Step 2's Discovery Bootstrap sub-procedure read becomes conditional on a new lifecycle (no existing `cortex/lifecycle/{feature}/` dir). Move backlog-writeback.md's "Create index.md (New Lifecycle Only)" section (with its traveling line-43 proposal applied) into the conditionally-read discovery-bootstrap.md. Update the body's Reference-path propagation manifest with the extracted file's four `${CLAUDE_SKILL_DIR}` targets; update the test anchors. (post-refine-commit.md's stale "lifecycle Step 3 §4" cross-references are synced in Task 11.)
- **Depends on**: none
- **Complexity**: complex
- **Context**: Spec R4 and research.md F3 define the moves; `evidence.json → disclosure.options[1]` carries the byte map. The extracted block contains 5 `${CLAUDE_SKILL_DIR}` occurrences — per ADR-0009 they cannot resolve in a reference file, so the manifest must pre-resolve refine SKILL.md, discovery-bootstrap.md, complexity-escalation.md, and post-refine-commit.md paths for the delegation reference to consume; `cortex-check-skill-path` (SP001/SP002) gates this. Resume-at-plan never delegates and never bootstraps, so it reads neither file — that is the saving; delegating paths reach discovery-bootstrap.md through refine-delegation.md, so no live path loses content. Do NOT touch Step 2's detect-phase table, the `-paused` rule, escalated handling, or staleness signals — option (c) is rejected per research.md F4. Kept-pauses inventory: the `SKILL.md:60` anchor shifts; update the inventory bullet in the same commit.
- **Verification**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py tests/test_post_refine_commit_wired.py` — pass if exit 0; `grep -c 'refine-delegation.md' skills/lifecycle/SKILL.md` ≥ 2 (gate cite + manifest entry); `grep -c 'discovery-bootstrap' skills/lifecycle/references/refine-delegation.md` ≥ 1 (delegation path retains the read); `grep -c 'Create index.md' skills/lifecycle/references/backlog-writeback.md` = 0.
- **Status**: [x] complete

### Task 2: Canonicalize the lifecycle-state read protocol (spec R2 move 3)
- **Files**: `skills/lifecycle/references/criticality-matrix.md`, `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/implement.md`
- **What**: Add a "Reading lifecycle state" section to criticality-matrix.md as the canonical statement of the `cortex-lifecycle-state` protocol (command forms, JSON output, medium/simple defaults, complexity_override supersession rule, corrupted:true → treat-as-requiring-review), collapse the protocol-explanation prose at the lifecycle-side sites in these files to bare command + short pointer, and add `criticality-matrix.md` AND `orchestrator-review.md` to SKILL.md's Reference-path propagation manifest — the latter fixes the pre-existing bare-relative `read and follow \`references/orchestrator-review.md\`` citations at specify.md §3a / plan.md §3a (a latent ADR-0009 off-repo failure this feature must not replicate). The executable `cortex-lifecycle-state --feature {feature} --field <x>` command lines stay inline at every site.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: `evidence.json → duplication.options[2]`. Remaining protocol restatements outside these five files are owned downstream: refine SKILL.md §3b collapses in Task 10; orchestrator-review.md:7–9 collapses in Task 11; Task 3's new gate file is barred from restating the protocol. E101/E103: inline `cortex-lifecycle-state` mentions keep required flags. The reachability claim from the draft plan was measured false — nothing outside `skills/lifecycle/` cites criticality-matrix.md today, which is exactly why the manifest entry (and refine/discovery body-path cites in Tasks 10/5) must be added rather than assumed.
- **Verification**: pre-commit chain green (contract lint validates flags); `grep -c 'superseded by the most recent' skills/lifecycle/references/criticality-matrix.md` = 1 AND `grep -c 'superseded by the most recent' skills/lifecycle/SKILL.md skills/lifecycle/references/specify.md skills/lifecycle/references/plan.md skills/lifecycle/references/implement.md` each = 0 (refine SKILL.md and orchestrator-review.md are excluded from this gate — owned by Tasks 10/11); `grep -c 'criticality-matrix.md' skills/lifecycle/SKILL.md` ≥ 1 (manifest entry present); `grep -c 'cortex-lifecycle-state' skills/lifecycle/references/specify.md` ≥ 1 and same for plan.md, implement.md (commands stayed inline).
- **Status**: [x] complete

### Task 3: Extract shared critical-review gate (spec R2 move 1)
- **Files**: `skills/lifecycle/references/critical-review-gate.md` (new), `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/SKILL.md` (kept-pauses inventory anchors + manifest entry)
- **What**: Create the shared phase-parameterized §3b gate reference holding the run/skip matrix, the `lifecycle_critical_review_skipped` event shape, and the skip-logging protocol — WITHOUT restating the state-read protocol (it cites Task 2's canonical section; the two `cortex-lifecycle-state` command lines and the one-line run/skip condition stay INLINE at both §3b sites so a mid-phase agent needs no hop to know what to run). Replace the remaining near-identical explanation blocks in specify.md §3b and plan.md §3b with a pointer resolved via the SKILL.md manifest (add `critical-review-gate.md` to the manifest in the same commit) — not the bare-relative §3a form.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `evidence.json → duplication.options[0]` (the 1,244B/1,241B pair). What moves is the shared explanation + event shape + skip protocol (~0.9KB/site); what stays inline is the command pair + condition line (~0.3KB/site) per Task 2's inline-command invariant — the two tasks now apply the same rule to the same command class. The event JSON shape must survive verbatim in the gate file (events-registry lint). Approval-surface anchors (`specify.md:155`, `plan.md:277`) shift; update the SKILL.md inventory bullets in the same commit.
- **Verification**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py` — pass if exit 0; `grep -c 'lifecycle_critical_review_skipped' skills/lifecycle/references/critical-review-gate.md` = 1; `grep -c 'superseded by the most recent' skills/lifecycle/references/critical-review-gate.md` = 0 (no ninth protocol copy); `grep -c 'cortex-lifecycle-state' skills/lifecycle/references/specify.md` ≥ 1 and same for plan.md (commands survived inline); `grep -c 'critical-review-gate.md' skills/lifecycle/SKILL.md` ≥ 1 (manifest entry).
- **Status**: [x] complete

### Task 4: Critical-review SKILL.md pointer-trims + micro-canonicalizations (spec R2 moves 2 + 4)
- **Files**: `skills/critical-review/SKILL.md`, `skills/lifecycle/references/load-requirements.md`, `skills/lifecycle/references/backlog-writeback.md`, `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/review.md`
- **What**: Reduce critical-review SKILL.md Steps 2a.5/2c.5/2d.5 to purpose + one-line abort condition + pointer (full exit-code contracts live in verification-gates.md, killing the SKILL.md:86 drift pair); canonicalize the glossary sentence in load-requirements.md and delete the clarify.md:35, review.md:13, and refine copies while KEEPING the specify.md:11 copy (refine's standalone resume-at-spec path skips requirements loading, so specify.md must carry the sentence itself — reachability measured, not assumed; the refine copy deletion lands in Task 10's files); canonicalize the index.md artifact-array update block and the `cortex-update-item` exit-2 handling at their natural homes.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: `evidence.json → duplication.options[1]` and `options[3]`. Do NOT touch: dispatched-verbatim READ_OK copies, reviewer/fallback/synthesizer prompt files, approval-surface skeletons, auto-advance reinforcements, model-routing inline values. The canonical glossary sentence reads "If a concept you need is not yet defined in the glossary…" — match that wording exactly; do not reword to satisfy a grep.
- **Verification**: pre-commit chain green; `grep -c 'check-artifact-stable' skills/critical-review/SKILL.md` ≥ 1 (abort conditions survive); `grep -rc 'If a concept you need is not yet defined' skills/lifecycle/references/ | grep -v ':0'` lists exactly load-requirements.md and specify.md with count 1 each, and clarify.md/review.md at 0.
- **Status**: [x] complete (deviation: tests/test_load_requirements_protocol.py carrier list retargeted; Task 10 must drop refine SKILL.md from RULE_CARRIERS)

### Task 5: Sync orchestrator-review drift pair (spec R3)
- **Files**: `skills/discovery/references/orchestrator-review.md`, `skills/discovery/SKILL.md`
- **What**: Reduce the discovery copy to its discovery-specific deltas plus a pointer to the lifecycle canonical resolved via discovery SKILL.md's body manifest (add the propagated `../lifecycle/references/orchestrator-review.md` path there — measured today: discovery's manifest carries only load-requirements and fanout).
- **Depends on**: none
- **Complexity**: simple
- **Context**: research.md F7; the pair diverges by 79 lines with shared bulk. Discovery's deltas (discovery-phase checklist rows, decompose-specific checks) stay in the discovery file; identify them by diffing the two files at edit time. `cortex-check-skill-path` gates the propagation line shape.
- **Verification**: `wc -c skills/discovery/references/orchestrator-review.md` < 3500; `grep -c 'lifecycle/references/orchestrator-review.md' skills/discovery/SKILL.md` ≥ 1 (manifest) AND `grep -c 'orchestrator-review' skills/discovery/references/orchestrator-review.md` ≥ 1 (the reduced file itself names the canonical); `grep -c -i 'decompose' skills/discovery/references/orchestrator-review.md` ≥ 1 (discovery-specific deltas survived); pre-commit green.
- **Status**: [ ] pending

### Task 6: Trim implement.md (highest pin density)
- **Files**: `skills/lifecycle/references/implement.md`, `skills/lifecycle/SKILL.md` (kept-pauses inventory anchor)
- **What**: Apply the implement.md proposal ledger (~6.8KB verified-safe).
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Heaviest test pins (`evidence.json → constraints.anchors`): step-v ordered-token block, branch-mode dispatch wiring incl. the `cortex-lifecycle-branch-mode` structural marker, daytime-free negative pin, EnterWorktree ±60-line co-location, `EnterWorktree skipped` anchor family — note line 197 packs the fallback taxonomy (three-way OR routing, selected-vs-suppressed, diagnostic strings) into one line, so a line-count grep proves nothing; the pin tests below are the real gate. Consult per-proposal `verifier_reason` notes. The `implement.md:49` inventory anchor shifts; same-commit inventory update. Builder prompt template and worktree-merge instructions are dispatched-verbatim: untouchable.
- **Verification**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py tests/test_lifecycle_phase_parity.py tests/test_lifecycle_step_v_ordering.py tests/test_lifecycle_implement_branch_mode.py tests/test_lifecycle_implement_md_daytime_free.py tests/test_lifecycle_enterworktree_callsites.py` — pass if exit 0; proposal ledger in commit body covers every implement.md proposal.
- **Status**: [ ] pending

### Task 7: Trim lifecycle SKILL.md + clarify.md
- **Files**: `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/clarify.md`
- **What**: Apply both proposal ledgers: TOC removal, staleness-signal condensation (replace the GNU-only `stat -c %Y` How-narration with the What), single-resolve restatement collapse, path-propagation parenthetical dedup, phase-boundary essay condensation per downgrade verdicts. Two SKILL.md proposals (old lines 154–158, 163) were already applied by Task 1 at extraction — mark them `moved:refine-delegation.md` in the ledger; the lines-100–102 proposal was subsumed by Task 2's collapse — mark `moved:criticality-matrix.md`.
- **Depends on**: [1, 2, 3, 4]
- **Complexity**: simple
- **Context**: The Reference-path propagation section's downgrade verdict predates Task 1–3's manifest growth — its "keep all three target→path mappings" means keep ALL mappings present at edit time (now ~9: the original three plus refine-delegation's four plus criticality-matrix, critical-review-gate, orchestrator-review). The kept-pauses inventory section itself is load-bearing — trim only its meta-prose per verdicts. `clarify.md:57` anchor shifts; same-commit inventory update. 500-line SKILL.md budget applies post-edit.
- **Verification**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py` — pass if exit 0; `wc -l skills/lifecycle/SKILL.md` ≤ 500; ledger disposition for every proposal in both files' maps.
- **Status**: [ ] pending

### Task 8: Trim plan.md + specify.md
- **Files**: `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/SKILL.md` (kept-pauses inventory anchors)
- **What**: Apply both proposal ledgers; proposals inside the old §3b blocks (specify.md lines 169–170, plan.md line 277) were relocated/absorbed by Tasks 2–3 — mark `moved`.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: plan.md §1a/§1b/§5 designators are cited normatively by `cortex_command/overnight/prompts/orchestrator-round.md:242,302,413` and `cortex_command/lifecycle_config.py:8-9,95-96` — section headings and numbering must survive; trim within sections only (Task 12 adds the mechanized pin). Plan-agent prompt template and synthesizer dispatch instructions are dispatched-verbatim. Approval-surface anchors shift; same-commit inventory update.
- **Verification**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py` — pass if exit 0; `grep -c '^### 1a\.' skills/lifecycle/references/plan.md` = 1, `grep -c '^### 1b\.' …` = 1, `grep -c '^### 5\.' …` = 1; ledger disposition complete.
- **Status**: [ ] pending

### Task 9: Trim complete.md + review.md
- **Files**: `skills/lifecycle/references/complete.md`, `skills/lifecycle/references/review.md`, `skills/lifecycle/SKILL.md` (kept-pauses inventory anchor)
- **What**: Apply both proposal ledgers (review.md's glossary-sentence copy was already deleted by Task 4 — mark `moved:load-requirements.md`).
- **Depends on**: [2, 4]
- **Complexity**: simple
- **Context**: complete.md's `**Hard guard**:` paragraph is byte-pinned to `tests/fixtures/complete_md_hard_guard.txt` — untouchable; the snapshot test (not a hand-rolled sed, which was measured to mis-extract even on the untouched file) is the gate. The `<!-- finalization-commit-step -->` marker region and ~40 verbatim substrings are pinned. review.md §4a designator cited by `report.py:965`; reviewer dispatch prompt is dispatched-verbatim. `complete.md:73` anchor shifts; same-commit inventory update.
- **Verification**: `uv run pytest tests/test_complete_md_hard_guard_snapshot.py tests/test_complete_md_finalization_commit.py tests/test_lifecycle_complete_state_routing.py tests/test_lifecycle_kept_pauses_parity.py` — pass if exit 0; ledger disposition complete.
- **Status**: [ ] pending

### Task 10: Trim refine SKILL.md + clarify-critic.md
- **Files**: `skills/refine/SKILL.md`, `skills/refine/references/clarify-critic.md`, `skills/lifecycle/SKILL.md` (kept-pauses inventory anchor)
- **What**: Apply both proposal ledgers; collapse refine SKILL.md's §3b lifecycle-state protocol prose to bare command + body-resolved pointer per Task 2's canonical (refine's body CAN resolve `${CLAUDE_SKILL_DIR}/../lifecycle/references/criticality-matrix.md`); delete refine's glossary-sentence copy per Task 4's canonicalization.
- **Depends on**: [2, 4]
- **Complexity**: simple
- **Context**: clarify-critic.md's critic dispatch prompt (between the `---` markers) is dispatched-verbatim — trim targets the orchestrator-side branch tables and warning-allowlist narration around it. refine §4 complexity-value gate text is a kept-pause anchor (`refine/SKILL.md:166`) with test-pinned CLI wiring literals (`cortex-load-parent-epic`, ordering). Same-commit inventory update.
- **Verification**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py` — pass if exit 0; `grep -c 'superseded by the most recent' skills/refine/SKILL.md` = 0 (protocol collapsed; closes the residue Task 2 deferred here); `grep -c 'cortex-lifecycle-state' skills/refine/SKILL.md` ≥ 1 (command inline); `grep -c 'cortex-load-parent-epic' skills/refine/references/clarify-critic.md` unchanged from pre-edit count; ledger disposition complete.
- **Status**: [ ] pending

### Task 11: Trim post-refine-commit.md + backlog-writeback.md + orchestrator-review.md
- **Files**: `skills/lifecycle/references/post-refine-commit.md`, `skills/lifecycle/references/backlog-writeback.md`, `skills/lifecycle/references/orchestrator-review.md`, `skills/lifecycle/SKILL.md` (kept-pauses inventory anchor)
- **What**: Apply the three proposal ledgers — backlog-writeback's "Lines 7, 39, 75" intro proposal is DOWNGRADED, not refuted: apply its `downgrade_to` (keep each section's short bolded prohibition; trim the per-section explanatory dash-clauses). Sync post-refine-commit.md's three "lifecycle Step 3 §4" cross-references to the post-Task-1 SKILL.md numbering. Collapse orchestrator-review.md's lines 7–9 state-read protocol recap to bare command + pointer per Task 2's canonical (closes the last deferred protocol copy).
- **Depends on**: [1, 2, 4, 5]
- **Complexity**: simple
- **Context**: backlog-writeback has zero refuted proposals (measured: 0 refuted, 4 downgraded) — the only verdict-missing proposals in the whole evidence set are implement.md's §1a.iv sandbox recap and review.md's §4 line-159 item, which Tasks 6/9 skip as `no-verdict` in their ledgers. orchestrator-review.md trim must preserve the section shape Task 5's discovery pointer cites. `backlog-writeback.md:11` anchor shifts; same-commit inventory update.
- **Verification**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py` — pass if exit 0; `grep -c 'superseded by the most recent' skills/lifecycle/references/orchestrator-review.md` = 0; `grep -c 'Step 3 §4' skills/lifecycle/references/post-refine-commit.md` = 0 OR the references match the renumbered SKILL.md headings (verify by reading the cited heading); ledger disposition complete.
- **Status**: [ ] pending

### Task 12: Guard tests — L1 ratchet + cited-designator pins (spec R5, R6f)
- **Files**: `tests/test_l1_surface_ratchet.py` (new), `tests/test_skill_section_citations.py` (new)
- **What**: (a) Ratchet test running `bin/cortex-measure-l1-surface` (reuse `tests/test_measure_l1_surface.py`'s `_utility_rows()` parsing), parametrized one case per skill plus the total, failing when any skill exceeds its `evidence.json → l1_surface_baseline` bytes (total 8,339), with a message pointing to the deferred cap-policy ticket. (b) Citation-pin test asserting the section designators cited from `cortex_command/**` still exist in the skill files: plan.md `### 1a.`/`### 1b.`/`### 5.`, complete.md's Step 2 heading, review.md's §4a heading — replacing self-certified grep prose with a mechanized gate.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Baselines in `evidence.json → l1_surface_baseline` (17 skills + total). Ratchet direction only — equal-or-lower passes; no description text changes in this feature. The citation-pin list is small and hardcoded with a comment naming each citing site (orchestrator-round.md:242,302,413; lifecycle_config.py:8-9,95-96; report.py:965).
- **Verification**: `uv run pytest tests/test_l1_surface_ratchet.py tests/test_skill_section_citations.py` — pass if exit 0.
- **Status**: [ ] pending

### Task 13: Final audit — citation sweep, byte accounting, full suite
- **Files**: `cortex/lifecycle/harness-token-efficiency-trim/implementation-notes.md` (new)
- **What**: (a) Byte accounting with a defined method: for every touched file plus the two new references, record `git cat-file -s origin/main:<path>` (0 for new files) vs `wc -c <path>`; report per-file deltas against `evidence.json` safe-savings figures with deviations explained, and the signed total including give-backs. (b) Full §-citation sweep: grep `cortex_command/` recursively for `§` and `Step N` tokens naming any trimmed file beyond the Task 12 pinned set; for each hit, confirm the cited designator exists (the pinned set is already mechanized). (c) Consolidated proposal ledger: every proposal across all 12 maps dispositioned applied / applied-per-downgrade / skipped-refuted / moved — no silent drops. (d) `just test`.
- **Depends on**: [6, 7, 8, 9, 10, 11, 12]
- **Complexity**: simple
- **Context**: Known citing sites in research.md F5. The ≥30KB floor accounts for measured give-backs (two new reference files, manifest growth, pointer lines) against the 36.5KB verified-safe + ~9KB dedup gross.
- **Verification**: `just test` — pass if exit 0; implementation-notes.md contains the per-file table, the signed total ≥ 30KB net reduction across `skills/`, and a ledger section with zero undispositioned proposals.
- **Status**: [ ] pending

## Risks

- **Line-shift cascades**: every Phase 1/2 task moves kept-pauses anchors; mitigated by same-commit inventory+test updates. The parity test's ±35-line tolerance is a presence check, not a pause-survival check (implement.md's six AskUserQuestion mentions all sit within one window) — the named pin tests in Tasks 6/9 carry the real semantic load.
- **Downgraded-proposal judgment**: 36 proposals apply per `downgrade_to` prose; a builder could over-trim. Mitigation: verifier `reason` travels with each proposal in the ledger; Review phase re-checks gates.
- **Execution-order dependence**: `Depends on` edges encode the load-bearing orderings only; tasks sharing SKILL.md inventory edits (6–11) are serialized by task-number-order execution, not by edges. Out-of-order execution is out of contract.
- **Pointer-hop residual risk**: Tasks 2/3 move explanation prose (never commands or run/skip conditions) behind manifest-resolved pointers. An agent that skips a hop loses explanatory context but not the gate itself — commands and conditions stay inline by construction, and Task 13(c) audits that invariant.

## Acceptance

After all tasks: `just test` green including both new guard tests; Task 13's method shows ≥ 30KB net reduction across `skills/` with zero frontmatter-description changes; the resume-at-plan load path (SKILL.md + backlog-writeback.md resume slice, with discovery-bootstrap.md and refine-delegation.md unread) totals ≤ 47KB vs 60.5KB baseline; every R6 gate (parity, fixtures, contract lints, mirror drift, citation pins) passes; no gate, pause, event shape, command-line inlining, or dispatched-verbatim template altered.
