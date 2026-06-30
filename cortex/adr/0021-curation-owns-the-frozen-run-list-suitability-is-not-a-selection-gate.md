---
status: proposed
---

# Curation owns the frozen run list; suitability is not a selection gate

## Context

Overnight `launch` historically re-ran `select_overnight_batch` on every invocation, so the operator's interactive Step 6 curation never reached execution — a latent gap where `[R]emove` did not stick, because `launch` re-selected the removed item from scratch. Separately, overnight-suitability ("is this spec fit to run unattended?") was judged early in `/refine`, at spec-writing time and inferring its run-mode by counting `phase_transition` rows — a brittle proxy that fired too early to act on for the overnight decision (#323).

## Decision

The interactive curation gate becomes the single owner of "what runs unattended":

- `launch` executes the operator's **frozen curated set** supplied via `--only` (full re-selection remains the default only when no curated set is supplied). The active list approved at the Step 6 gate is exactly the set bootstrapped and run — there is no re-selection between approval and execution.
- **Suitability is judged by the LLM at curation time**, where the spec bodies are in hand and a human is present. Poor unattended candidates are set aside (excluded by default) with per-item reasons, surfaced at the gate, and re-addable before the list is frozen. The unattended harness makes no suitability calls and never re-selects.
- The frozen set must be **dependency-closed**: `launch` refuses fail-loud when a kept feature's in-session blocker is excluded, naming the missing blocker, so a dangling `intra_session_blocked_by` never reaches state.
- `/refine` no longer reasons about overnight execution at all; its Step 6 overnight-candidate advisory and run-mode detection are removed.

## Consequences / Trade-off

- `launch` is no longer a pure idempotent re-select; its contract now depends on the caller-supplied curated set. The only live consumer of `launch`'s selection is the `/overnight` skill (plus direct CLI use). `cortex overnight start` / `schedule` and the MCP `overnight_start_run` / `overnight_schedule_run` tools consume the already-bootstrapped state via `--state` and are unaffected — confirmed by inspection (those paths build `start`/`schedule` argv with `--state` and never invoke `launch`) and guarded by their existing test suites.
- Suitability is judged by prose-guided LLM rather than a deterministic Python gate. Accepted because every set-aside is surfaced and re-addable at a human gate and a missed flag is a recoverable overnight failure (surfaced in the morning report), not data loss; the deterministically-checkable signals couple to fragile spec-template markers, so a Python matcher would be brittle. The structural guarantee is applied at the approval→execution boundary (what is approved is what runs), not on the judgment itself.
- For the standalone-`/refine`→interactive-build (or never-overnight) population, the removed refine heads-up is a genuine loss with no replacement — a deletion, not a relocation, for that path. It is accepted because removing the advisory severs refine's only dependency on inferring run-mode from the event stream, and that population builds interactively and verifies throughout, so the heads-up's protective value is lowest exactly there. The protection is preserved at overnight curation for the path where unattended execution actually happens.

This decision is hard to reverse (it changes `launch`'s contract), surprising without context (why doesn't `launch` just re-select?), and a real trade-off (honor-curation vs. always-fresh-select; prose-judgment-with-human-backstop vs. structural gate) — meeting the three-criteria ADR gate.
