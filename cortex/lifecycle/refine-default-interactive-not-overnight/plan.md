# Plan: refine-default-interactive-not-overnight

## Overview
Prose edits to two shared skill files (`specify.md`, `refine/SKILL.md`) plus a ratchet
re-cap, sequenced so each canonical edit regenerates its plugin mirror in the same commit.
No new code modules; the only behavioral addition is a soft, standalone-guarded advisory in
refine's Step 6.

## Outline

### Phase 1: Reframe the interview and refine's framing (tasks: 1, 2)
**Goal**: `specify.md` assumes interactive/user-present verification (rigor preserved) and
refine's purpose/framing reads execution-agnostic, with both plugin mirrors regenerated.
**Checkpoint**: `specify.md` and `refine/SKILL.md` edited; `just build-plugin` run; both
mirrors byte-identical to canonical (drift hook clean).

### Phase 2: Add the warning, re-cap the ratchet, verify (tasks: 3, 4, 5)
**Goal**: standalone-guarded overnight-candidate warning in refine Step 6; L1 ratchet
re-capped to the new measured surface; full suite green and manual R6 walkthrough done.
**Checkpoint**: `just test` exits 0; the 3-case R6 behavioral walkthrough completed.

## Tasks

### Task 1: Reframe specify.md interview to interactive-default (R1)
- **Files**: `skills/lifecycle/references/specify.md`, `plugins/cortex-core/skills/lifecycle/references/specify.md`
- **What**: Rewrite the §2b "Open Decision Resolution" clause that assumes the user is absent at execution, and add a §2 interview-posture note that the present user verifies criteria in-session and the interview does not interrogate overnight-autonomy. Leave the (a)/(b)/(c) acceptance-criteria format unchanged.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Target the L96 line `Ask the user directly — the user is present during spec; implementation may run overnight without them.` — reframe to keep the "ask directly rather than deferring to `## Open Decisions`" intent **and its deferral-cost rationale**, while dropping only the overnight assumption. The resolve-now pressure must survive on an *execution-agnostic* reason (the implementer executes from the spec and cannot resolve an open decision mid-implementation), NOT on the weaker "verify in-session" framing — which implies the user stays reachable later and erodes resolve-now (and, with it, the handoff-readiness invariant). E.g.: "…the user is present during spec; resolve open decisions now — the implementer works from the spec and won't have the user in the loop to resolve them later." Note this is a behavior change worth flagging: the edit removes the overnight framing but must NOT silently drop the deferral-cost reason. Add a short posture note within §2 Structured Interview (around L38–46) stating the interview assumes interactive verification and does not press for overnight-autonomous verifiability. Do NOT touch the L126 (a)/(b)/(c) format or its "if a command check is not possible" wording — that preserves criteria rigor and orchestrator-review S1 consistency; the §2 posture note governs *interview posture* (don't interrogate overnight-autonomy), the (c) format governs *criteria shape* (still binary-checkable), and the two must not contradict. After editing canonical, run `just build-plugin` and stage both canonical and the regenerated mirror (drift hook requires canonical+mirror committed together).
- **Verification**: `grep -c "may run overnight without them" skills/lifecycle/references/specify.md` = `0`; `grep -c "if a command check is not possible" skills/lifecycle/references/specify.md` ≥ `1`; `diff -q skills/lifecycle/references/specify.md plugins/cortex-core/skills/lifecycle/references/specify.md` reports the files identical (exit 0); Interactive/session-dependent: read the new §2 posture note together with the kept (a)/(b)/(c) ladder (L126) and the orchestrator-review S1 checklist (`orchestrator-review.md` item S1) and confirm they give the interviewer non-contradictory guidance — the "assume interactive" posture must not read as a license to drop binary-checkability that S1 still demands (rationale: prose coherence across three distant sites is not grep-checkable, so this is a manual read).
- **Status**: [x] done

### Task 2: Reframe refine SKILL.md to execution-agnostic (R2)
- **Files**: `skills/refine/SKILL.md`, `plugins/cortex-core/skills/refine/SKILL.md`
- **What**: Change refine's purpose to "prepare a backlog item for execution"; remove the "Ready for overnight execution." completion line; soften the `outputs` line and the "overnight runner can plan and execute it without further human input" framing — without presuming overnight. Keep the four routing trigger substrings in description/when_to_use.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Frontmatter L3 `description`, L4 `when_to_use`, L9 `outputs`; body L19 purpose statement and L188 "Ready for overnight execution.". Set the purpose to read `Prepares a single backlog item for execution.` (terse). The four substrings that MUST survive (routing): `refine backlog item`, `prepare for overnight`, `prepare feature for execution`, `Clarify → Research → Spec` — keep `prepare for overnight` as a discoverability keyword even though the purpose is now execution-agnostic. Keep the combined L1 surface (description + when_to_use) ≤ 644 bytes — it should shrink, since "overnight execution" → "execution" removes bytes. After editing, run `just build-plugin`; stage canonical + regenerated mirror.
- **Verification**: `grep -c "Prepares a single backlog item for execution" skills/refine/SKILL.md` ≥ `1`; `grep -c "Ready for overnight execution." skills/refine/SKILL.md` = `0`; each of the four trigger substrings still present (`grep -c` ≥ 1 each); the L1 surface did not grow — `bin/cortex-measure-l1-surface | grep '^refine '` shows refine bytes ≤ `644` (catches an accidental rephrase that grows the surface here, not late at Task 4/5); `diff -q skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` identical (exit 0).
- **Status**: [x] done

### Task 3: Add standalone-guarded overnight-candidate warning to refine Step 6 (R6)
- **Files**: `skills/refine/SKILL.md`, `plugins/cortex-core/skills/refine/SKILL.md`
- **What**: In refine's Step 6 (Completion), add a soft-phrased instruction to assess the approved `spec.md` for overnight-suitability and surface an advisory warning ONLY when the ticket is a poor overnight candidate, listing reasons — hybrid heuristic — and ONLY on the standalone `/refine` path.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Step 6 is at L180–188 of `skills/refine/SKILL.md`. Mechanical anchor signals to name: any acceptance criterion marked `Interactive/session-dependent`; any unresolved item under `## Open Decisions`. Judgment reasons to allow: needs network/credentials, requires human-visual/judgment verification, exploratory/under-specified scope. Standalone guard: emit only when `cortex/lifecycle/{slug}/events.log` contains no `phase_transition` events — standalone `/refine` never logs them (`skills/refine/SKILL.md:155`; the CLI writes only `lifecycle_start`/`*_override`), whereas `/cortex-core:lifecycle` writes them at phase boundaries during delegation. The rows that actually guarantee suppression are the early `clarify→research` and `research→specify` transitions, written before any spec exists and therefore well before Step 6; the `specify→plan` row is emitted by `specify.md` §5 on approval — contemporaneous with Step 6 — so the guard does not depend on it. (Cite the early rows, not `refine-delegation.md` Step 4, as the suppression guarantee.) **Pin the guard as a concrete, reproducible check** rather than free-form "inspect events.log" — Step 6 should test `phase_transition`-row absence with a named check (e.g. `grep -c '"event": "phase_transition"' cortex/lifecycle/{slug}/events.log` → `0` means standalone: assess and warn; `≥ 1` means suppress). This is a deliberate exception to "prescribe What not How" because it is a discriminator gate where model variance produces a spurious lifecycle warning. Use soft positive-routing phrasing — no MUST/CRITICAL/REQUIRED (CLAUDE.md MUST-escalation policy). After editing, run `just build-plugin`; stage canonical + regenerated mirror.
- **Verification**: `grep -ci "overnight candidate" skills/refine/SKILL.md` ≥ `1`; within Step 6, `grep -c "Interactive/session-dependent" skills/refine/SKILL.md` ≥ `1` and `grep -c "phase_transition" skills/refine/SKILL.md` ≥ `1` (guard named); `grep -ci "MUST\|CRITICAL\|REQUIRED" ` of the added Step-6 lines = `0` (soft phrasing); `diff -q skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` identical (exit 0).
- **Status**: [x] done

### Task 4: Re-cap the L1 ratchet baseline for refine (R4)
- **Files**: `tests/test_l1_surface_ratchet.py`
- **Depends on**: [2, 3]
- **Complexity**: simple
- **What**: Measure refine's post-reframe L1 surface and, if it decreased from 644, lower `_BASELINES["refine"]` to the measured value and recompute `_BASELINES["total"]`.
- **Context**: `_BASELINES` dict in `tests/test_l1_surface_ratchet.py` (`"refine": 644`, `"total": 7197`). Measure via `bin/cortex-measure-l1-surface` (prints `<skill> <bytes>` rows; `total` row is the sum). Set `_BASELINES["refine"]` to the measured refine bytes and `_BASELINES["total"]` to the measured total (the test asserts both per-skill and total). Do not raise either value; lowering is the re-cap. R6 (Step 6 body) does not change the L1 surface — only R2's frontmatter does, verified against `bin/cortex-measure-l1-surface` (it sums the frontmatter `description` + `when_to_use` byte lengths only, never the body). Depend on `[2, 3]` regardless, so the measurement lands after **both** refine edits — closing the window where an incidental frontmatter touch in Task 3 would otherwise leave the lowered baseline stale-too-low and surface only at Task 5's `just test` (the ratchet is not in the pre-commit hook).
- **Verification**: `python3 -m pytest tests/test_l1_surface_ratchet.py -q` exits `0`; the `refine` and `total` rows from `bin/cortex-measure-l1-surface` equal the new `_BASELINES` values.
- **Status**: [x] done

### Task 5: Full verification — routing, parity, ratchet, manual R6 (R3, R5, R6 behavioral)
- **Files**: none (verification only; reads `spec.md`, exercises `tests/`)
- **Depends on**: [1, 3, 4]
- **Complexity**: simple
- **What**: Run the full test suite (covers routing-disambiguation, L1 ratchet, mirror parity, trigger phrases), then walk the R6 behavioral protocol against four fixture cases — including the lifecycle-suppression arm — and record the outcomes for audit.
- **Context**: `just test` runs the suite including `tests/test_skill_routing_disambiguation.py`, `tests/test_l1_surface_ratchet.py`, `tests/test_plugin_mirror_parity.py`, and the `skill_trigger_phrases.yaml` consumer. The R6 manual protocol (per spec.md R6 behavioral surface) walks four cases — the first three exercise the standalone fire/no-fire heuristic, the fourth exercises the guard's actual purpose (lifecycle suppression): (i) standalone events.log (no `phase_transition`) + a spec with an `Interactive/session-dependent` criterion + no open decisions → expect a warning citing it; (ii) standalone + all (a)/(b) command-checked criteria + no open decisions → expect silence; (iii) standalone + an unresolved `## Open Decisions` item → expect the decision cited; (iv) **lifecycle arm** — an events.log containing a `phase_transition` row + a spec that WOULD warn under (i) → expect silence (guard suppresses). This feature's own `cortex/lifecycle/refine-default-interactive-not-overnight/` is a ready fixture for case (iv): its events.log has `phase_transition` rows and its spec.md carries an `Interactive/session-dependent` criterion, so it must stay silent. Record the four outcomes in the lifecycle review notes so a later reviewer can audit the walkthrough.
- **Verification**: `just test` exits `0`. R6 behavioral — Interactive/session-dependent: the *judgment-reason* subset of Step 6 is model-interpreted prose that no command can execute; the *mechanical* subset (an `Interactive/session-dependent` criterion present, an unresolved `## Open Decisions` item, `phase_transition`-absence) is deterministic. The four-case fire/no-fire matrix (including the lifecycle-suppression arm) is walked in-session as a **one-time sanity check at Review — explicitly not a regression guard or audit trail**: a note authored by the same agent that performed the walkthrough is not independently re-runnable, so per backlog 025 it would be self-sealing if treated as the pass condition. Record the outcomes in the review notes as a human-readable record only; the pass condition is `just test` (mechanical) plus the reviewer's live observation (behavioral), not the existence of the note.
- **Status**: [x] done

## Risks
- **Mirror coupling forces sequential, not parallel, execution.** The binding reason is
  same-file contention: Tasks 2 and 3 both edit the *same* canonical file
  (`skills/refine/SKILL.md` — frontmatter for T2, Step 6 body for T3), so parallel worktrees
  would conflict on the canonical source itself, independent of the mirror tree. On top of
  that, `just build-plugin` regenerates the WHOLE plugin tree, so two worktrees invoking it
  would also conflict on the mirror tree. Recommend **trunk (sequential)** dispatch on `main`.
  (This is why the merged approval surface should lean trunk.) Backstop:
  `.githooks/pre-commit` auto-runs `build-plugin` and *fails* the commit on canonical↔mirror
  drift, but never stages the rebuild — so the manual `build-plugin`+stage in each task is
  necessary, and a forgotten mirror-stage is caught (not silently shipped). Note this backstop
  covers **mirror parity only**: the L1 ratchet test (`tests/test_l1_surface_ratchet.py`) runs
  under `just test` (Task 5), **not** in the pre-commit hook, so a forgotten or wrong ratchet
  re-cap surfaces only at Task 5, not at commit time.
- **R6's guard is a best-effort heuristic, not a hard signal — failure mode is benign.**
  Two residual cases: (a) *false-suppress* on a standalone re-run of a slug previously run
  under lifecycle (`phase_transition` rows linger) — accepted, silence-favoring; (b)
  *false-fire* under `/cortex-core:lifecycle` is effectively impossible: two `phase_transition`
  rows (`clarify→research`, `research→specify`) are on disk before the spec is even written,
  so the events.log is never zero-`phase_transition` at Step 6 time regardless of how an
  orchestrator batches its later boundary writes. Both consequences are a single benign
  advisory line, never a correctness break — so the guard is left best-effort rather than
  hardened with a structural signal.
- **R6's mechanical anchor is deterministic; only its judgment-reason subset is prose.** The
  three mechanical signals (an `Interactive/session-dependent` criterion, an unresolved
  `## Open Decisions` item, `phase_transition`-absence) are deterministic predicates over file
  state; only the judgment reasons (network/credentials, human-visual verification, exploratory
  scope) are genuinely model-discretionary. The manual four-case walkthrough (Task 5) is a
  one-time sanity check, not a regression guard — a self-recorded note is not treated as the
  pass condition (see Task 5). Whether the mechanical subset *additionally* gets executable
  coverage (a small deterministic helper the skill calls, unit-tested against the four
  fixtures) is the open scope decision resolved at plan approval; the prior critical review
  flagged that leaving the load-bearing standalone/lifecycle discriminator test-free means a
  regression in it ships green, against a benign (advisory-only) failure mode.

## Acceptance
Running standalone `/refine` produces a spec without overnight-framed interrogation during
speccing (`specify.md` no longer assumes the user is absent at execution), refine's framing
reads execution-agnostic, and refine's completion surfaces an advisory overnight-candidate
warning only for poor candidates (suppressed under `/cortex-core:lifecycle`). `just test` is
green — routing-disambiguation, L1 ratchet (re-capped), and both mirrors' parity all pass.
