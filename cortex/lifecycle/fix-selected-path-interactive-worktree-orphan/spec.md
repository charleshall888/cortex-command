# Specification: fix-selected-path-interactive-worktree-orphan

> Precedent: this completes ticket #348's guard-then-acquire pattern (which fixed the symmetric `suppressed`-path orphan). #348's spec/plan live at `cortex/lifecycle/deep-trim-implementmd-hot-sections-and/`. Full five-angle analysis + critical-review corrections: `research.md` and the critical-review synthesis in this lifecycle.

## Problem Statement

On the picker-`selected` entry mode of the interactive-worktree implement flow (`skills/lifecycle/references/implement.md`), §1 **Step B** acquires the per-feature interactive lock *before* §1a.i's second overnight guard runs. If the overnight runner goes live in that window, §1a.i rejects and exits §1a while the Step-B lock is never released (`release_lock` is unused in the skill flow), orphaning a lock for a worktree that was never created. The session then self-blocks on retry, and concurrent sessions read the lock as LIVE until stale recovery reclaims it. The fix brings the selected path's acquire ordering into line with the `suppressed` path #348 already corrected: acquire *after* the overnight guard, so a rejecting guard can never hold a lock to orphan. Beneficiaries: developers running interactive worktree implements, who stop self-blocking on the overnight-guard-reject race.

## Phases
- **Phase 1: Discriminating test (TDD, red-first)** — author the structural regression test and confirm it FAILS against the current (pre-fix) `implement.md`, so its discriminating power is observed on the live buggy tree, not reconstructed.
- **Phase 2: Reorder + scrub + mirror** — apply the reorder (the Phase-1 test flips to green), scrub every dangling Step B reference while preserving the `Step A` label and the entry-mode marker, regenerate the mirror, and land test + fix + mirror in one green commit.

## Requirements

<!-- MoSCoW: R1–R7 are all Must-have — the reorder (R2–R5) is the fix, the discriminating test (R1) is required because verification-vacuity is this project's recurring review failure, and preserving existing contracts (R6) + marker (R4) is non-negotiable. No Should-haves for this scoped bug fix. Won't-do items are in Non-Requirements (chief: the deferred §1a.iii orphan). -->

1. **Author a discriminating structural regression test and confirm it reds on the current tree.** Add a test to `tests/test_implement_worktree_interactive_contract.py` (mirroring the section-extraction style of `test_gate_and_gated_path_use_same_binary`) that extracts §1 (`### 1\. Pre-Flight Check` → `### 1a\.`), §1a (`### 1a\.` → `### 2\.` — bounded at the next real heading, **not** `\Z`/EOF), and the §1a.ii interactive-lock step (within §1a, `**ii.` → `**iii.`). It makes three assertions:
   - **(i) [discriminator]** the §1 substring contains no `cortex-interactive-lock acquire`;
   - **(ii) [forward-guard, not a discriminator for this bug]** within §1a, the earliest `cortex-interactive-lock acquire` index is after the last `_interactive_overnight_check.sh` index (guards a *future* edit that re-introduces an acquire before the guard; already green pre-fix);
   - **(iii) [discriminator — positive unification check]** the §1a.ii step contains `cortex-interactive-lock acquire` **and** does not contain the dead-arm label `` Entry mode `selected` `` (after unification the acquire is unconditional; a paraphrased dead `selected` arm such as "Entry mode `selected`: proceed to iii" still carries that label and is therefore caught — this replaces the paraphrase-defeatable "do not acquire again" negative check. The specific arm-label form, not bare "Entry mode", is used so a correct unified rewrite that mentions "both entry modes" does not false-red).

   Indices in (ii)/(iii) are measured within the §1a substring; (i) is measured in the §1 substring — these are **separate coordinate origins**, asserted independently (no cross-origin comparison). Acceptance (a): running the new test against the **current unmodified** `implement.md` **FAILS** — structurally guaranteed because pre-fix §1 contains the acquire (violates (i)) and pre-fix §1a.ii contains `Entry mode` (violates (iii)); capture the failing run as Phase 1's checkpoint. **Phase**: Discriminating test.

2. **Reorder the selected-path acquire into §1a.ii.** Remove `cortex-interactive-lock acquire {slug}` from §1 Step B; make §1a.ii acquire **unconditionally** for both entry modes — remove the per-entry-mode split (the `Entry mode \`selected\``/`Entry mode \`suppressed\`` branch) around the acquire, including the `selected`-arm skip. Acceptance (b, observable state in `skills/lifecycle/references/implement.md`): the §1 section contains no `cortex-interactive-lock acquire`; the §1a section contains exactly one `cortex-interactive-lock acquire` after the last `_interactive_overnight_check.sh` index; the §1a.ii step contains no `` Entry mode `selected` `` dead-arm label. (i.e., the R1 test passes.) **Phase**: Reorder.

3. **Scrub every dangling Step B / two-guard reference so the prose reads coherently.** The reorder falsifies more than the literal token "Step B": §1 retains **one** preflight guard, so the picker-dispatch prose that claims two must change. Enumerated sites: line ~19 (recorded-choice branch "run Step A … and Step B … below"), line ~63 ("run the **two interactive preflight guards** below (Steps A and B) … If **either guard** rejects"), line ~73 (Step A exit-0 "proceed to Step B"), line ~104 (§1a.ii `selected` arm). Acceptance (b): `grep -niE "step b|steps a and b|two interactive preflight guards|either guard rejects" skills/lifecycle/references/implement.md` = **0** (the token AND the two-guard prose are gone). **Phase**: Reorder.

4. **Preserve the `Step A` label, the entry-mode marker, and Step v branching.** Keep §1's overnight pre-check labeled `Step A` (do **not** relabel it) so §1a.i's back-reference "semantics as §1 Step A" (line ~100) still resolves; de-conditionalize only the §1a.ii *acquire*; keep the marker recording ("record entry mode `selected`" / "`suppressed`") and Step v's marker branch (cd-shim vs `EnterWorktree` — ADR-0008 ties EnterWorktree authorization to the `selected` marker, not the acquire). Acceptance (b): `grep -c "§1 Step A" skills/lifecycle/references/implement.md` ≥ 1 (line ~100 back-ref intact) and both `record entry mode \`selected\`` and `record entry mode \`suppressed\`` still present; (a) `just test` exits 0 with `tests/test_lifecycle_step_v_ordering.py` passing. **Phase**: Reorder.

5. **Regenerate and stage the mirror in the same commit as the canonical edit.** Acceptance (a): after `just build-plugin`, `diff skills/lifecycle/references/implement.md plugins/cortex-core/skills/lifecycle/references/implement.md` exits 0 (byte-identical) and `tests/test_dual_source_reference_parity.py` passes. **Phase**: Reorder.

6. **Preserve the existing tested contracts.** Acceptance (a): `just test` exits 0 with `test_sidecar_invocation_form_bash_s_count` (exactly 2 `bash -s --` — Step A stays), `test_overnight_guard_sidecar_called_at_least_twice` (≥2), and `test_gate_and_gated_path_use_same_binary` (its `**iii.` step-marker extraction still resolves) all passing. **Phase**: Reorder.

7. **The Phase-1 test passes after the reorder.** Acceptance (a): after Phase 2, the R1 test (unchanged) now PASSES; `just test` exits 0. Test + reorder + mirror land in one commit so the committed tree is always green while the red-on-pre-fix is observed in-session at Phase 1. **Phase**: Reorder.

## Non-Requirements
- **Does NOT fix the §1a.iii `cortex-worktree-create`-failure orphan** (a post-acquire abort that leaks the lock on **both** entry modes, pre-existing, not fixed by #348). Deferred to a follow-up ticket — **not because the ticket couldn't, but because the safe fix is more than one call**: the shipping `cortex-interactive-lock release {slug}` subcommand has **no owner check** (`release_lock(feature_slug)` unlinks unconditionally — verified), so a naive release-on-abort at §1a.iii would delete *another* session's lock under the non-atomic-`acquire_lock` double-pass (see Edge Cases). Closing §1a.iii safely needs an **owner-checked release** — a genuine design task for its own ticket, covering both entry modes symmetrically. Re-surfaced at §4 approval for the user to confirm (defer) or override (include a scoped version now). The reorder *technique* cannot fix §1a.iii (the acquire must precede worktree creation), but that is a statement about the technique, not the reason for deferral.
- **Does NOT add hard mutual exclusion** to `acquire_lock` (its read→`os.replace` best-effort behavior, lacking `O_CREAT|O_EXCL`, is pre-existing and unchanged — this fix is about orphan-on-abort, not two-session atomicity).
- **Does NOT remove §1 Step A** (the overnight pre-check) — it is a tested contract (exactly-2 sidecar count) and provides fail-fast UX; the resulting two-overnight-check asymmetry on `selected` is by design.
- **Does NOT touch** `cortex_command/lifecycle_implement.py` (its `§1a-i` docstrings anchor to `scan_live_locks` liveness, which does not move) or `cortex_command/interactive_lock.py` (no code change needed).

## Edge Cases
- **Concurrent same-slug `selected` sessions after the reorder**: the interactive lock is **not** a hard mutex — `acquire_lock` is a non-atomic read→`os.replace` with no `O_CREAT|O_EXCL`, so two sessions can both pass §1a.ii. What prevents a double worktree is **git's own worktree-path/branch exclusivity** downstream (the second `cortex-worktree-create --feature interactive-{slug}` fails), **not** the lock. Consequence: the losing racer fails at §1a.iii holding/last-writing the on-disk lock while the winner's worktree is live — the §1a.iii orphan (below). The reorder **widens** the pre-acquire window (picker → Step A → §1a.i → §1a.ii vs. today's picker → Step B), so it marginally *increases* the probability of this concurrent double-pass on the `selected` path. Severity remains low (two concurrent same-slug interactive implements is operator error), but it is a probability increase, not merely a fairness delta — and it is one reason the §1a.iii follow-up must use an owner-checked release.
- **Crash between picker-select and §1a.ii acquire**: no lock file is written (strictly cleaner than today's Step-B early acquire, which leaves a stale lock for the next session to recover). Expected: no orphan.
- **§1a.iii worktree-create failure after the §1a.ii acquire**: lock remains held — the deferred §1a.iii hazard, unchanged by this fix. Expected: documented residual, tracked by the follow-up ticket.

## Changes to Existing Behavior
- MODIFIED: selected-path lock acquisition moves from §1 Step B (pre-overnight-guard) → §1a.ii (post-overnight-guard), matching the `suppressed` path.
- REMOVED: §1a.ii's per-entry-mode acquire split (the `selected`-arm skip case); §1's "Step B" and the "two preflight guards" prose.
- ADDED: a discriminating structural regression test with a positive unification assertion, red on the pre-fix tree.

## Technical Constraints
- Canonical `skills/lifecycle/references/implement.md` edit + `just build-plugin` mirror regen must land in the **same commit** (dual-source drift pre-commit gate + `tests/test_dual_source_reference_parity.py`).
- `cortex_command/` is not part of the mirror system; no Python edit is in scope.
- **Concurrent-edit hazard**: #353 (and any other `implement.md`-editing ticket) must run sequential-after, not concurrent (mirror-parity collision). Commit #355 with **explicit pathspec** — the working tree currently carries unrelated uncommitted #350 changes (`skills/research/SKILL.md`, its mirror, `cortex/lifecycle/single-source-research-skill-fan-out/plan.md`) that must NOT be captured.
- Test command: `just test` (from `cortex/lifecycle.config.md`).
- Review runs (config `skip-review: false`; also forced by complex + high).

## Open Decisions
None require implementation-level context unavailable at spec time. (The §1a.iii-failure scope is a Non-Requirement resolved to "defer," re-confirmed by the user at §4 approval — not implementation-blocked.)

## Proposed ADR
None considered. This fix extends #348's already-decided guard-then-acquire pattern to the selected path; no new hard-to-reverse decision is introduced. ADR-0008 (EnterWorktree authorization via the `selected` marker) is a constraint to preserve, not a new decision.
