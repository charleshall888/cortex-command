# Plan: compress-projectmd-sections-that-restate-adrs

## Overview

Execute the eight epic-#347 audit verdicts against `cortex/requirements/project.md` — dropping prose that restates an ADR body / CLAUDE.md / a test docstring / an enforcement-site doc, while preserving the named must-survive clauses. All edits land in one file, so tasks run **sequentially** (same-file edits race if parallelized); the orchestrator edits directly (delicate keep-preservation the critical-review flagged as human-review-dependent). Each verdict task runs its own discriminating keep+cut greps; a final task runs the whole-file gates (contract-lint, `just test`, structural invariants, net reduction, and the R12 diff-scoping guard).

## Outline

### Phase 1: Philosophy of Work (tasks: 1)
**Goal**: Compress s4 (finalization mechanics → ADR-0004 pointer) and fix the stale L27 kept-pauses pointer.
**Checkpoint**: R1 greps pass; `## Philosophy of Work` still holds its non-s4 bullets (L21 Solution-horizon verbatim).

### Phase 2: Architectural Constraints (tasks: 2, 3, 4, 5, 6)
**Goal**: Compress s6, s7, s8, s9, s10 — the five line-ranges inside `## Architectural Constraints` — to pointers + named keeps, without tripping contract-lint.
**Checkpoint**: R2–R6 greps pass; L36 and the interleaved L39/L40 bullets byte-unchanged; `cortex-check-contract` exit 0.

### Phase 3: Quality Attributes + Optional (tasks: 7, 8) + whole-file gates (task: 9)
**Goal**: Compress s11 (one bullet) and s15 (two bullets), then verify the whole-feature gates.
**Checkpoint**: R7–R8 greps pass; the five untouched QA bullets and the Optional H2/convention/Workflow-trimming bullet byte-unchanged; R9–R12 all green.

## Tasks

### Task 1: s4 — compress Philosophy-of-Work finalization mechanics + fix L27 pointer
- **Files**: `cortex/requirements/project.md`
- **What**: In the L25 "Multi-step lifecycle phases" bullet, drop the ADR-0004 finalization-tail narration (Steps 9–11a, flag-gated stage-first, three completion paths, idempotent routing, the verbose `consult cortex/adr/0004-…md`) and replace with a `→ ADR-0004` back-pointer; keep the multi-step-with-reinvocation contract, the merge-terminal + `merge_anchor:"merge"` fact, and the two-kind pause taxonomy. In L27, correct `skills/lifecycle/SKILL.md` → `skills/lifecycle/references/kept-pauses.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current L25 ends "...consult `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` for the design rationale." The ADR README §No-content-duplication (L51) requires the one-line back-pointer form. `merge_anchor` and the "two kinds" pause sentence are the philosophy-level keeps. Do NOT touch the L21 Solution-horizon bullet (CLAUDE.md cites project.md's Philosophy-of-Work Solution-horizon home by name).
- **Verification**: spec R1 — (a) cut: `grep -c "Steps 9" project.md` = 0 AND `grep -Fc "on all completion paths" project.md` = 0 AND `grep -c "adr/0004-multi-step" project.md` = 0; (b) keeps: `grep -Fc 'merge_anchor' project.md` ≥ 1 AND `grep -Fc 'ADR-0004' project.md` = 1 AND `grep -Fc 'two kinds' project.md` ≥ 1; (c) L27: `grep -Fc 'skills/lifecycle/references/kept-pauses.md' project.md` ≥ 1 AND `grep -c 'skills/lifecycle/SKILL.md' project.md` = 0. Pass if all hold.
- **Status**: [ ] pending

### Task 2: s6 — compress historical-shim + wheel-binstub bullets (medium-confidence — keep-conservative)
- **Files**: `cortex/requirements/project.md`
- **What**: Leave L36 (TERMINAL_STATUSES) byte-unchanged. Compress L37 (historical-compat shim) to a one-line policy + `pipeline/metrics.py` pointer, dropping the retitled-docstring verbatim wording and the "replaying or aggregating" tail. Compress L38 (wheel-binstub) to gotcha + remedy, dropping the "Dogfooders iterating" narration but keeping the three facts + `CORTEX_COMMAND_FORCE_SOURCE=1` remedy.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: s6 is the lone medium-confidence verdict; its keeps (shim policy sentence, FORCE_SOURCE remedy) have NO test backstop — when uncertain, keep the sentence. FORCE_SOURCE's only other home is bin-wrapper comments; the shim-retitle pattern lives at `pipeline/metrics.py:367,396`.
- **Verification**: spec R2 — (a) keeps: `grep -Fc 'CORTEX_COMMAND_FORCE_SOURCE' project.md` ≥ 1 AND `grep -Fc 'TERMINAL_STATUSES' project.md` ≥ 1; (b) cut: `grep -Fc 'replaying or aggregating' project.md` = 0 AND `grep -Fc 'Dogfooders iterating' project.md` = 0. Pass if all hold.
- **Status**: [ ] pending

### Task 3: s7 — collapse EnterWorktree / install-state / AUTO_ENSURE bullets
- **Files**: `cortex/requirements/project.md`
- **What**: Collapse L41 (EnterWorktree) to scope + `→ ADR-0008`; collapse L42 (install-state) to contract-name + the dependency-direction invariant ("the wheel never imports from `plugins/cortex-overnight/`") + the `test_install_state_path_parity.py` pointer, dropping the "vendor-style" duplication narration; L43 (AUTO_ENSURE) is already near-minimal — leave or trim lightly.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: The critical-review flagged that a bare `plugins/cortex-overnight/` path token is NOT a proxy for the directional claim — the compressed L42 must retain the word "never imports" (the invariant itself). ADR-0008 owns L41's decision; `install_core.py:763-768` + `install_state.py:7` own L42's rationale.
- **Verification**: spec R3 — (a) keeps: `grep -Fc 'ADR-0008' project.md` ≥ 1 AND `grep -Fc 'test_install_state_path_parity.py' project.md` ≥ 1 AND `grep -Fc 'never imports' project.md` ≥ 1 AND `grep -Fc 'plugins/cortex-overnight/' project.md` ≥ 1; (b) cut — **one present-today token per edited bullet** (all =1 now, so a per-bullet no-op fails): `grep -Fc 'cd-shim' project.md` = 0 (L41 EnterWorktree collapse) AND `grep -Fc 'vendor-style' project.md` = 0 (L42 install-state narration). Pass if all hold.
- **Status**: [ ] pending

### Task 4: s8 — compress the three lint bullets (grep-c / bare-python / skill-dir)
- **Files**: `cortex/requirements/project.md`
- **What**: Compress L44/L45/L46 each to gate-name + suppression-token + one-line intent + pointer. Drop the L46 skill-dir design-principle paragraph duplicated verbatim from CLAUDE.md. Keep the literal lint tokens, the two ignore-next sentinels, the parity test, the ADR-0009 pointer, and the L44 backlog-grep-c WHY clause.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: **Contract-lint constraint**: keep the existing passing inline-code form of `cortex-check-bare-python-import` and `cortex-check-skill-path` — do NOT drop the `cortex-` prefix (that zeroes R4's keep-grep) and do NOT introduce a new bare `cortex-<verb>` mention. Both binaries have zero required flags/subcommands so E101/E103 are unreachable for them; the risk is only new verb mentions. The L44 WHY ("prevents acceptance criteria passing against hallucinated event names") has no other prose home — keep it (diff-review).
- **Verification**: spec R4 — (a) keeps: `grep -Fc 'cortex-check-bare-python-import' project.md` ≥ 1 AND `grep -Fc 'cortex-check-skill-path' project.md` ≥ 1 AND `grep -Fc 'bare-python-lint:ignore-next' project.md` ≥ 1 AND `grep -Fc 'skill-path-lint:ignore-next' project.md` ≥ 1 AND `grep -Fc 'test_backlog_grep_targets_resolve.py' project.md` ≥ 1 AND `grep -Fc 'ADR-0009' project.md` ≥ 1; (b) cut — **one present-today token per edited bullet** (all =1 now): `grep -Fc 'Companion to the events-registry' project.md` = 0 (L44 grep-c narration) AND `grep -Fc 'importlib.util.find_spec' project.md` = 0 (L45 enumerated import forms) AND `grep -Fc 'resolves only in a SKILL.md body' project.md` = 0 (L46 skill-dir paragraph); (c) `cortex-check-contract --staged` (or repo-wide) exits 0. Pass if all hold.
- **Status**: [ ] pending

### Task 5: s9 — compress dependency-bounds + L1-ratchet bullets
- **Files**: `cortex/requirements/project.md`
- **What**: In L47, collapse the FastAPI/starlette example to a `pyproject.toml` pointer, keeping the two prose-only policies (uv-tool-install-ignores-lock ⇒ requires-dist is the only universal governance; promote-transitive-to-direct-capped). Cut the L48 L1-ratchet bullet to ~⅓: keep the heading token "SKILL.md L1 surface ratchet" verbatim + the cluster-exemption + re-cap-with-rationale-and-lifecycle-id policies; drop the budget-row / ≤400 default / six-cluster-member enumeration / completeness-gate narration (all re-documented in `test_l1_surface_ratchet.py`).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: CLAUDE.md:44 cites this section BY NAME "for the cluster exemption and re-cap rule" — those two policies are the load-bearing prose and must survive. `pyproject.toml:18-19` owns the starlette rationale; `ROUTING_PRESSURE_CLUSTER` owns cluster membership.
- **Verification**: spec R5 — (a) keeps: `grep -Fc 'SKILL.md L1 surface ratchet' project.md` ≥ 1 AND `grep -Fc 'exemption' project.md` ≥ 1 AND `grep -Fc 're-cap' project.md` ≥ 1 AND `grep -Fc 'requires-dist' project.md` ≥ 1 AND `grep -Fc 'promote a transitive' project.md` ≥ 1; (b) cut: `grep -Fc 'starlette' project.md` = 0 AND `grep -Fc 'membership encoded once' project.md` = 0. Pass if all hold.
- **Status**: [ ] pending

### Task 6: s10 — compress supervision + containment bullets
- **Files**: `cortex/requirements/project.md`
- **What**: Reduce L49 (runner supervision) to one line + `→ ADR-0011`. Reduce L50 (worktree containment) to the invariant + the exemption one-liner + a pointer to the `test_containment_*` block, dropping the `_is_worktree_inside_repo` / `relative_to`-not-`startswith` / check-ordering code-internals narration — but KEEP the same-repo-overnight-is-NOT-exempt clause (its only prose home).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: ADR-0011 owns L49's Decision section clause-for-clause. L50's internals are pinned by `test_worktree.py:659-816` + `worktree.py:230-231` comments. The "NOT exempt" counter-intuitive matrix cell has no ADR and no test — it is the one containment clause that must survive in prose (diff-review keep).
- **Verification**: spec R6 — (a) keeps: `grep -Fc 'ADR-0011' project.md` ≥ 1 AND `grep -Fc 'NOT exempt' project.md` ≥ 1 AND `grep -Fc 'test_containment' project.md` ≥ 1; (b) cut — **one present-today token per edited bullet** (all =1 now): `grep -Fc 'orphan reap' project.md` = 0 (L49 supervision narration) AND `grep -Fc '_is_worktree_inside_repo' project.md` = 0 AND `grep -Fc 'startswith' project.md` = 0 (L50 containment internals). Pass if all hold.
- **Status**: [ ] pending

### Task 7: s11 — trim the redaction cue-family enumeration only
- **Files**: `cortex/requirements/project.md`
- **What**: In the L58 captured-output bullet, trim ONLY the parenthetical cue-family enumeration (the `sk-ant-`/`gh?_`/`xox[bp]-`/`AKIA`/`ASIA`/`Bearer`/`password=`/PEM list) to a `pipeline/dispatch.py:_redact` pointer; keep the three design-decision clauses (scrubbed-at-source-before-brain/report; deliberately-incomplete defense-in-depth; no-prefixless-blob-matcher + `→ #309`). Leave L54–57 and L59 byte-unchanged.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: No ADR (0001–0023) covers redaction, so the three design clauses are the load-bearing residue with no other home. The cue patterns are code+test-pinned in `dispatch.py`/`test_dispatch.py`.
- **Verification**: spec R7 — (a) keeps: `grep -Fc 'scrubbed at source' project.md` ≥ 1 AND `grep -Fc 'NOT complete' project.md` ≥ 1 AND `grep -Fc 'prefixless fixed-length blob' project.md` ≥ 1 AND `grep -Fc '#309' project.md` ≥ 1; (b) cut: `grep -Fc 'ASIA' project.md` = 0 AND `grep -Fc 'xox' project.md` = 0. Pass if all hold.
- **Status**: [ ] pending

### Task 8: s15 — compress the Optional sandbox-preflight + two-mode-gate bullets
- **Files**: `cortex/requirements/project.md`
- **What**: Compress the sandbox-preflight and two-mode-gate bullets to name + one-line scope + pointer — the bullet NAMES must survive (compress, not delete). Drop the `_in_scan_scope` recursive-glob narration. Leave the `## Optional` H2, the first-line prunability-convention sentence, and the `Workflow trimming` bullet byte-unchanged.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Preflight is documented in `docs/overnight-operations.md` + `auto-update.md`; `_in_scan_scope` lives in `contract.py` with tests. The requirements-write schema (`skills/requirements-write/SKILL.md:35`) pins the Optional H2 + convention line + bold-led bullets + ≤1,200-token budget — do not violate. Do NOT introduce new bare `cortex-*` mentions (keep `bin/cortex-check-parity` / `bin/cortex-check-events-registry` path-qualified forms).
- **Verification**: spec R8 — (a) compress-not-delete: `grep -Fc 'Sandbox preflight' project.md` ≥ 1 AND `grep -Fc 'Two-mode gate' project.md` ≥ 1; (b) untouched keeps: `grep -Fc '## Optional' project.md` = 1 AND `grep -Fc 'Workflow trimming' project.md` ≥ 1; (c) cut — **one present-today token per edited bullet** (both =1 now): `grep -Fc 'claude --version' project.md` = 0 (L98 sandbox-preflight narration) AND `grep -Fc 'recursive-glob matcher safe' project.md` = 0 (L99 two-mode-gate `_in_scan_scope` narration); (d) `cortex-check-contract` exits 0. Pass if all hold.
- **Status**: [ ] pending

### Task 9: whole-file gates — contract-lint, tests, structural invariants, net reduction, diff-scoping
- **Files**: `cortex/requirements/project.md`
- **What**: Run the cross-cutting gates (spec R9–R12) against the fully-compressed file. This task modifies no content — it is the verification gate before the final commit. If any gate fails, return to the offending verdict task.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: All gates compute against the refine baseline commit `7e46ee11` via `git show 7e46ee11:<path>` (project.md is byte-identical to HEAD at that commit — verified ancestor), so they capture every edit regardless of intermediate per-phase commits. R12 is now **fully mechanical** (bullet-count invariant + non-target `diff`) — there is no "which bullet does this hunk belong to" eyeball step. Note: the `L##` line numbers in Tasks 1–8 are **baseline-relative anchors**; they drift as earlier tasks compress the file, so navigate by the bold lead-in token, not the line number.
- **Verification** (all mechanical — no eyeball step): (R9) `cortex-check-contract` repo-wide exits 0. (R10) `just test` exits 0 AND `grep -c '^## ' project.md` = 8. (R11 — **byte-reduction, not lines**; `wc -l` is pre-satisfied at 100 < 101) baseline is 17317 bytes, so require `$(git show 7e46ee11:cortex/requirements/project.md | wc -c) - $(wc -c < cortex/requirements/project.md)` ≥ 800 (a no-op yields 0; a one-token edit ≈ 13 — both fail) AND the `## Optional` section within the requirements-write ≤1,200-token budget. (R12 — **byte-identity of all untouched content, mechanical**): (a) bullet-structure invariant — `grep -c '^- ' project.md` = 45 AND `grep -c '^- \*\*' project.md` = 29 (no bullet merged, deleted, or added — catches a two-bullet merge, which no presence-grep sees); (b) non-target byte-identity — write these 17 edited-bullet lead-in substrings (each **validated to match exactly one line** in the current file, backtick-free to avoid escaping errors), one per line, to `targets.txt`:

```
**Multi-step lifecycle phases**
**Kept user pauses come in two kinds**
**Historical compatibility shim pattern**
**Wheel-binstub vs working-tree invocation**
authorization surface**
**Install-state shared-constant contract**
opt-out**: mirrors
resolution**: Backlog tickets
**Bare-Python skill-invocation prohibition
**Skill-dir path-resolution invariant
**Distributed-CLI dependency bounds**
**SKILL.md L1 surface ratchet**
**Out-of-process runner supervision**
**Worktree containment invariant**
**Defense-in-depth for captured subprocess output**
**Sandbox preflight gate**
**Two-mode gate pattern**
```

then require `diff <(git show 7e46ee11:cortex/requirements/project.md | grep -vFf targets.txt) <(grep -vFf targets.txt cortex/requirements/project.md)` to be **empty** — i.e. every line NOT part of an edited bullet is byte-identical to baseline. This catches neighbor rewording AND neighbor deletion (incl. the L39 `→ ADR-0002` bullet, which a presence-grep misses because L7 Overview also carries the token). Guard: re-confirm each lead-in still matches exactly one line before trusting the diff (a compression that alters a lead-in itself would silently drop that bullet from the filter). Pass if all hold.
- **Status**: [ ] pending

## Risks

- **Keep-sufficiency is gate-unverifiable** (critical-review through-line): presence-greps prove a token survived, not that its *clause* survived intact. The clause-level greps (Tasks 1/3/6/7) and R12 narrow this, but the final judge is the user's diff review at commit/PR. This is inherent to compressing prose whose only enforcement IS the prose.
- **s6 medium-confidence**: its keeps have the weakest backstop — Task 2 defaults to keep-conservative.
- **Line-number drift**: compression shifts line numbers, so per-task greps key on content tokens (not line numbers), and R12 diffs against the `7e46ee11` baseline.
- **Concurrent #355 session on main**: see the Commit Cadence section below — the leak defense is structural (a staged-set assertion), not prose-only.

## Commit Cadence

Three commits, one per phase (after Task 1; after Task 6; after Task 9's gates pass). Each commit:
1. Stage **only** the one file: `git add cortex/requirements/project.md` (never `-A`/`-a`).
2. **Leak backstop (structural, not prose)** — assert the staged set is exactly that one file before committing: `git diff --cached --name-only` must equal the single line `cortex/requirements/project.md`. If anything else appears (a #355 file leaked into the shared index), unstage it and re-check. This converts the concurrent-session defense from a prose reminder into a checked precondition.
3. Commit via `/cortex-core:commit`. Subjects: Phase 1 `Compress project.md Philosophy-of-Work s4 + fix kept-pauses pointer (#351)`; Phase 2 `Compress project.md Architectural-Constraints s6–s10 (#351)`; Phase 3 `Compress project.md Quality-Attributes s11 + Optional s15 (#351)`. Task 9's gates (R9–R12) run against the working tree **before** the Phase 3 commit; R11/R12 diff against `7e46ee11`, which stays the correct baseline across the intermediate commits (project.md was byte-identical to HEAD there).

## Acceptance

`cortex/requirements/project.md` is compressed across the eight verdict ranges: every keep-token present and every per-edited-bullet cut-token absent (Tasks 1–8), `just test` exits 0, `cortex-check-contract` exits 0, all eight H2s intact, bullet structure invariant (45 `- ` / 29 `- **`), every non-target line byte-identical to baseline `7e46ee11` (R12 non-target `diff` empty), and ≥ 800 bytes removed (R11) — with the user's diff review as the final arbiter of keep-*sufficiency* (which no gate can prove).
