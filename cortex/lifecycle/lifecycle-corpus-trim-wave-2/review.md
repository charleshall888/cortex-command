# Review: lifecycle-corpus-trim-wave-2

Reviewed against `spec.md` as amended at the Implement gate (R13 "Accepted delivered
targets"). Read-only spec-compliance + code-quality review. Cycle 1.

## Stage 1 — Spec Compliance

| Req | Summary | Rating | Evidence |
|-----|---------|--------|----------|
| R1 | `cortex-lifecycle-enter` verb | PASS | `enter.py` composes create-index/start-sync/init-ensure/`.session`; all discriminants caller-passed; `{state, backlog_status}` envelope with `backlog_status ∈ {already_complete, open, no_match}`; never auto-closes (short-circuits to `needs-decision`); exit 2 propagates `_Exit2`. `grep -c` = 1. `test_enter.py` green, every `KNOWN_STATES` member reachable, never-crash CLI test present. |
| R2 | `cortex-lifecycle-finalize` verb | PASS | `finalize.py` runs backend-gated `update_item(status=complete, session_id=None)` (relies on its internal index regen — no second regen), counters read, idempotent `feature_complete` emission `with merge_anchor: "merge"`; guard matches parsed `event` field. `grep -c` = 1. Test asserts `merge_anchor: "merge"` and no duplicate on second invocation. |
| R3 | `cortex-lifecycle-register-artifact` verb | PASS | `register_artifact.py` regex capture-rewrite + `atomic_write`, skip-if-present byte-level no-op, `updated:` bump. `grep -c` = 1. Round-trip + double-register tests green. |
| R4 | Verb conventions | PASS | All three are dumb arg-actors (ADR-0019), uniform `log_event`, always-emit-JSON, `bin/cortex-*` wrappers from the counters template, events-registry updated. `just`-lint / contract / parity tests green. |
| R5 | implement.md worktree extraction | PASS | `worktree-entry.md` carries the suppressed-picker literal + Step v order verbatim; implement.md holds neither (route-conditional, not loaded on trunk). `implement.md` = 7,154 B (≤7,400; ≥4KB drop). Four re-anchored contract tests green. |
| R6 | complete.md asymmetric split | PASS | Steps 1–6 in `complete-first-run.md` (carries `### Step 2 — Commit Lifecycle Artifacts`); complete.md keeps `### Step 7` + `finalization-commit-step` fence, = 5,166 B (≤5,200). Citation + finalization-commit + state-routing tests green. |
| R7 | Delegation merge | PASS | `complexity-escalation.md`/`post-refine-commit.md`/`discovery-bootstrap.md` deleted (grep = 0); `refine-delegation.md` = 5,285 B, below the 6,062 B four-file sum. Roundtrip green. |
| R8 | backlog-writeback rewiring | PASS* | Prose collapsed to verb one-liners; always-on set (SKILL.md + backlog-writeback.md) = 9,693 B. *R8's inline "below 9KB" is superseded by the R13 amendment's always-on ≤9.7KB ceiling, which is met. |
| R9 | orchestrator-review phase split | PASS | Two checklist files present; all 17 items (S1–S7, P1–P10) with conditions/skips/gates preserved (verified S7/P8/P10 skip rules, P7, S1/P4 in files + compression-diff review); shared-protocol `--role orchestrator-fix` pin intact. |
| R10 | Kept-pauses demotion + trims | PASS | `plan_comparison` grep = 2; review.md retains the drift verdict field, `### 4a` heading, and the parse/apply/2-retry/breach protocol (`cortex-lifecycle-event drift-protocol-breach`, "cap 2 retries"); `## Suggested Requirements Update` format intact. Kept-pauses parity green. |
| R11 | Sub-skill safe cuts | PASS | Rubric untouchables intact (`## Worked Examples`, `## Trigger Definitions` present; duplicate opening sentence removed, grep = 0); clarify-critic injection strings preserved (compression-diff review). L1 ratchet + pin tests green. |
| R12 | Correctness fixes | PASS | Stale `lifecycle-start` bullet gone (grep = 0 in refine-delegation.md); roundtrip green. |
| R13 | Target-metric verification | PASS | Against amended ceilings: A 91,721≤92,000, C 25,167≤25,200, D 18,744≤18,800, F 14,859≤14,900, always-on 9,693≤9,700 — all met (independently recomputed). Both end-to-end drives recorded (worktree static conformance + real finalize-verb run emitting `merge_anchor: "merge"`); compression-diff review verdict `parity-confirmed`. Full suite green modulo the documented sandbox/pollution baseline; mirrors clean. |

No FAIL. All 13 requirements PASS.

## Stage 2 — Code Quality

- **Naming / pattern consistency**: The three verbs follow the established `prepare_worktree`
  idiom — `KNOWN_STATES` tuple, compact `{state, ...}` envelope, never-crash `main`, telemetry
  shim, documented root-resolver flavor (env-honoring for `enter`, cwd for `finalize`/`register-artifact`,
  with the cross-verb invariant stated in each docstring). Consistent with ADR-0019/0020.
- **Error handling**: Exit 1/2 carve-outs are deliberate and documented (create-index OSError,
  start-sync/update-item `_Exit2`); every other path JSON-encodes rather than tracebacks. The
  `_backlog_status` and `_feature_complete_exists` readers fail safe (unreadable → `open` / `False`),
  correctly preserving the never-auto-close invariant.
- **Test coverage**: The plan's verification steps were executed — 144 targeted tests pass
  (verb modules, re-anchored structural contracts, complete-routing, kept-pauses), plus 134
  parity/mirror/ratchet tests. The route-table artifact records the full-suite run (6/7 clusters,
  the one failure a documented sandbox DNS baseline).
- **Regression caught in-band**: The compression-diff review found and fixed F1 — the Task-7
  rewiring had dropped the `phase=none` no-side-effects carve-out for an already-complete item.
  The fix (a `needs-decision` state + caller-passed `--acknowledge-complete`, keeping the verb a
  dumb arg-actor) is a clean structural encoding of the prior behavior with dedicated tests. Good
  defensive design; the added state is reachable and documented.

### Observations (non-blocking)

- `route-table-after.md` still displays the **original** funded ceilings as "MISSED (NO)". That is
  the honest pre-amendment measurement that drove the gate amendment, but a reader of the artifact
  alone would conclude the wave failed its targets. Consider a one-line pointer to the R13
  amendment at the top of the table so the artifact is not read out of context.
- R8's inline acceptance text ("always-on set shrinks below 9KB total") was not updated when R13's
  always-on ceiling was amended to ≤9.7KB; the delivered 9,693 B satisfies the amendment but reads
  as unmet against R8's own literal. A one-line note in R8 would remove the apparent conflict.

## Requirements Drift

**State**: none

**Findings**: None. The wave collapses SKILL.md dispatch ceremony into atomic `cortex_command/lifecycle/`
console-scripts — exactly the "Skill-helper modules" architectural constraint (project.md) — registers
new events in `bin/.events-registry.md` with no new event names, and preserves the `merge_anchor: "merge"`
terminal-event contract and the two-kinds kept-pauses inventory already codified in the requirements.
The `needs-decision`/`--acknowledge-complete` addition preserves an existing no-side-effects carve-out
rather than introducing new behavior. Corpus trimming is the "Maintainability through simplicity"
quality attribute in action. Nothing observed that the requirements do not already capture.

**Update needed**: None

## Verdict

{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
