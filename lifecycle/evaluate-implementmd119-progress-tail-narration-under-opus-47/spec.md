# Specification: evaluate-implementmd119-progress-tail-narration-under-opus-47

## Problem Statement

The daytime-dispatch polling loop's "(b) Progress tail" step at `skills/lifecycle/references/implement.md:119` directs the orchestrator to "surface a brief summary of the 5 most recent events to the user" every 120 seconds for up to 4 hours. This is a forced-cadence narration directive — the pattern Anthropic's Opus 4.7 migration guide (item 4) recommends removing. With observed event spacing of ~12–60 minutes during lifecycle 100's daytime dispatches, the same 5 events get re-narrated 6–30 times in a row. The user watches the terminal during daytime dispatches but accepts loss of in-terminal progress narration in exchange for operational simplicity. When real-time visibility is needed, the dashboard and direct `tail -f lifecycle/{feature}/events.log` in another terminal are available out-of-band channels.

A prior spec attempt replaced the directive with "event-change-triggered narration" but was rejected during critical review: the proposed shape required cross-poll comparison primitives the agent cannot reliably perform under Opus 4.7's documented long-context regressions, and shipped a step-3 remedy (per Anthropic's guidance) without the step-2 empirical predicate that licenses it. Approach B (this spec) sidesteps those faults by deleting the directive entirely rather than replacing it.

## Requirements

1. **[MUST] Delete the entire (b) Progress tail step** at `skills/lifecycle/references/implement.md:119`. The forced-cadence narration directive, the `tail -n 5 lifecycle/{feature}/events.log` Bash call, and the "tail is capped at 5 (not 20)" rationale are all removed together.
   - Acceptance: `grep -c "Progress tail" skills/lifecycle/references/implement.md` outputs `0` (pass when output = `0`).
   - Acceptance: `grep -c "tail -n 5" skills/lifecycle/references/implement.md` outputs `0` (pass when output = `0`).
   - Acceptance: `grep -c "surface a brief summary of the 5 most recent events" skills/lifecycle/references/implement.md` outputs `0` (pass when output = `0`; verbatim 9-word substring of the original directive, paired with the "Progress tail" and "tail -n 5" greps above for redundancy against partial-deletion residue).

2. **[MUST] Renumber the inter-iteration sleep step from (c) to (b).** With the prior (b) removed, the per-iteration block becomes a coherent (a)/(b) pair — (a) liveness check, (b) inter-iteration sleep.
   - Acceptance: `grep -c "(c) Inter-iteration sleep" skills/lifecycle/references/implement.md` outputs `0` (pass when output = `0`; the original `(c)` label is gone).
   - Acceptance: `grep -c "(b) Inter-iteration sleep" skills/lifecycle/references/implement.md` outputs `1` (pass when output = `1`; the renumbered `(b)` label is present).

3. **[MUST] Step (a) liveness check semantics preserved verbatim.** The `kill -0 $pid 2>/dev/null` invocation and its semantics ("Non-zero exit means the process has exited — break out of the polling loop and proceed to result surfacing") retain their current text. (Note: `kill -0 $pid 2>/dev/null` also appears in §1a.ii's double-dispatch guard at line ~60; that occurrence is out of scope and must be preserved.)
   - Acceptance: `grep -c "^- (a) Liveness:" skills/lifecycle/references/implement.md` outputs `1` (pass when output = `1`; line-anchored to the polling-loop bullet — verifies the (a) bullet exists with its expected prefix and label).
   - Acceptance: `grep -cF 'kill -0 $pid 2>/dev/null' skills/lifecycle/references/implement.md` outputs `2` (pass when output = `2`; both polling-loop liveness step and §1a.ii double-dispatch guard preserve this exact substring; deletion of line 119 affects neither).

4. **[MUST] Step (b)/renumbered inter-iteration sleep semantics preserved.** The `sleep 120` Bash call with `timeout: 130000` framing is retained — only the bullet label changes from `(c)` to `(b)`.
   - Acceptance: `grep -c "^- (b) Inter-iteration sleep:" skills/lifecycle/references/implement.md` outputs `1` (pass when output = `1`; line-anchored to the renumbered polling-loop bullet — verifies the renumber landed AND the bullet is well-formed).
   - Acceptance: `grep -cF 'sleep 120' skills/lifecycle/references/implement.md` outputs `1` (pass when output = `1`; `sleep 120` appears only in this step in implement.md §1b).

5. **[MUST] Plugin mirror regenerated in lockstep.** The auto-generated mirror at `plugins/cortex-interactive/skills/lifecycle/references/implement.md` must be byte-identical to the canonical source AND must reflect the deletion (i.e., parity must hold AND the deletion must have actually landed in both files — not just that they agree).
   - Acceptance (parity): `diff skills/lifecycle/references/implement.md plugins/cortex-interactive/skills/lifecycle/references/implement.md` exits `0` (pass when exit code = 0).
   - Acceptance (deletion landed in mirror): `grep -c "Progress tail" plugins/cortex-interactive/skills/lifecycle/references/implement.md` outputs `0` (pass when output = `0`; verifies the deletion is reflected in the mirror, defending against the trivial pass mode where both files remain at their pre-edit state).

6. **[MUST] Existing `test_skill_contracts` assertions continue to pass.** The 5 invariants in `tests/test_daytime_preflight.py::test_skill_contracts` (lines 315–397) check the §1b invocation string, flag absence, plan.md/daytime.pid ordering, `"mode": "daytime"` count, and §1b.vii result-reader+outcome enumeration. None reference the (b) Progress tail wording or the (c) Inter-iteration sleep label.
   - Acceptance: `pytest tests/test_daytime_preflight.py::test_skill_contracts -q` exits `0` (pass when exit code = 0).

## Non-Requirements

- Does NOT migrate the polling loop to the Claude Code Monitor tool. The polling architecture (§1b vi iteration loop + §vii result-surfacing handoff) remains unchanged. Monitor's notification-as-async-event model does not auto-trigger the §vii synchronous result-surfacing handoff that #074/#094/#140 stabilized.
- Does NOT touch adjacent narration directives elsewhere in implement.md (lines ~47, 122, 134, 138, 140, 217, 244, 291). Those are structural one-shot directives, explicitly out of scope per ticket #133's Scope bounds.
- Does NOT add a replacement narration mechanism (event-change-triggered, structural-event-triggered, or otherwise). The cycle-1 spec attempt at "event-change-triggered narration" was rejected during critical review for grounding the comparison primitive in agent in-context memory, which 4.7's documented long-context regression makes unreliable. Approach B avoids the comparison-primitive class of fault entirely by removing the step.
- Does NOT add a stall/hang detector. The implicit hang signal that the deleted directive carried (repeated narration of the same 5 events as a "no progress" signal) is removed without replacement. The 30-iteration human-prompt at line 122 remains unchanged but does NOT function as a hang detector — it is a forced-cadence checkpoint that fires regardless of subprocess state. This is an acknowledged regression in implicit hang signal; the dashboard and direct `tail -f` are the available out-of-band mitigations.
- Does NOT execute Anthropic's step 2 (observation across 1–2 daytime dispatches) or step 3 (conditional shaped-example reinstatement) as the original ticket prescribed. Approach B implements the guide's step 1 ("try removing") as a terminal action — observation and step-3 considerations are explicitly out of scope for this lifecycle. If user observation in subsequent dispatches reveals concrete pain (e.g., the user routinely needs in-terminal progress visibility and finds the dashboard insufficient), a follow-up ticket can scope the corresponding intervention with empirical grounding.
- Does NOT add tests asserting on the deletion. The grep-based acceptance criteria above plus existing `test_skill_contracts` are sufficient regression coverage for this scope.
- Does NOT rename ticket #133's title. Title rename is deferrable to commit-message description or a separate housekeeping pass.

## Edge Cases

- **Subprocess running, no events firing**: User sees no narration in-terminal during the dispatch. Intentional. Real-time visibility, when needed, is via the dashboard or out-of-band `tail -f lifecycle/{feature}/events.log` in another terminal.
- **Subprocess emits events at a moderate pace**: User still sees no narration in-terminal during the polling loop. Same out-of-band channels apply.
- **Subprocess hangs (alive but emitting no events for extended period)**: User notices via out-of-band `tail -f` (if they think to look), via the dashboard (if open), or not at all until §vii surfacing fires (subprocess exit) or the session ends. The 30-iteration human-prompt at line 122 fires at ~60 minutes regardless of subprocess state — it is a session-cost checkpoint, not a hang detector, so it is intentionally not listed as a mitigation path here. The implicit hang signal that the prior directive carried (repeated narration of unchanged tails) is gone. Acknowledged regression.
- **Subprocess exits**: Step (a) `kill -0` fails; loop breaks; §vii result-surfacing fires. Behavior unchanged from current.
- **Subprocess exits with no events at all**: Same as above — step (a) handles this; the deleted (b) step never narrated anything in this case anyway.
- **Compaction recovery mid-dispatch**: Orchestrator re-enters via `daytime-dispatch.json` + PID file (existing pattern, unchanged). Re-enters the polling loop without any "previous poll" memory issue because there is no comparison being made — the loop is now stateless on the orchestrator side, with state living entirely in the subprocess + PID file + events.log.
- **Adjacent narration sites in implement.md fire as today**: Lines ~47 (initial dispatch announcement), ~122 (30-iteration prompt), ~134/138/140 (§vii outcome surfacing), etc. — these are structural one-shot directives unaffected by this change. Polling-loop deletion does not cascade to them.

## Changes to Existing Behavior

- **REMOVED**: `skills/lifecycle/references/implement.md:119` — the (b) Progress tail step in the daytime-dispatch polling loop. Removes the forced-cadence narration directive, the `tail -n 5 lifecycle/{feature}/events.log` Bash call, and the "(not 20) to limit context accumulation over long runs" annotation as one atomic deletion.
- **MODIFIED**: `skills/lifecycle/references/implement.md` — the previous step (c) Inter-iteration sleep is renumbered to step (b); the per-iteration block now contains exactly two bullet items.
- **REMOVED + MODIFIED** (mirror): `plugins/cortex-interactive/skills/lifecycle/references/implement.md` — auto-regenerated by `just build-plugin` to match the canonical source. The mirror's line 119 deletion + (c)→(b) renumber are byproducts of the canonical change.

## Technical Constraints

- **Canonical + plugin mirror parity** is enforced by `.githooks/pre-commit:174–202` (drift hook). Edits land in the canonical source; the mirror is regenerated via `just build-plugin` (rsync-based, see `justfile:475`). Both files must be staged in the same commit.
- **No staged rollout** for skill prompt changes — once the canonical+mirror commit lands and the user re-invokes `/cortex-interactive:lifecycle implement` with "Implement in autonomous worktree", the new behavior takes effect.
- **Anthropic Opus 4.7 migration guide item 4** (`https://platform.claude.com/docs/en/about-claude/models/migration-guide`) is the load-bearing source. Approach B implements step 1 ("try removing") literally; steps 2 (observation) and 3 (provide examples on mis-calibration) are out of scope for this lifecycle and would be a follow-up ticket if empirically motivated.
- **Statelessness on the orchestrator side**: with (b) deleted, the polling loop's per-iteration steps are now (a) liveness check + (b) sleep — neither requires cross-iteration agent memory. Compaction-resilience pattern (PID file + `daytime-dispatch.json` + `daytime_result_reader` 3-tier fallback) is unaffected because there is no in-context state to lose.

## Open Decisions

(None — all decisions resolved during refine + critical review.)
