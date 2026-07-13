# Review: critical-review-sentinel-gate-excludes-async (cycle 1)

Read-only review against `spec.md` + `plan.md`. Canonical sources reviewed; `plugins/cortex-core/**` mirrors confirmed in-sync but not independently audited (auto-regenerated).

## Stage 1 — Spec Compliance

| Req | Rating | Evidence |
| --- | --- | --- |
| R1 — `--artifact-path` optional/backward-compat on both subcommands; pure verifier signatures unchanged; `_VERIFIER_SITE_RE` untouched | PASS | `add_argument("--artifact-path", default=None, ...)` at `__init__.py:942` (check-synth-stable) and `:983` (check-artifact-stable). Pure verifiers `check_synth_stable(output, expected_sha)` (`:350`) and `check_artifact_stable(output, expected_sha, window_lines=50)` (`:398`) carry no path param. `_VERIFIER_SITE_RE` lives only in `tests/test_critical_review_gate_class_parity.py:264` — untouched. Backward-compat exit-3 verified by `test_absent_no_artifact_path_exit3_backcompat` on both wrappers. |
| R2 — absent + provably-stable → advisory pass (exit 0), folds into existing pass code | PASS | Advisory branch `if status == "absent" and args.artifact_path is not None` at `:781` (artifact) / `:677` (synth); on re-hash match calls `_emit_sentinel_advisory` (`:582`) which returns 0. Sits before the exit-4 write-guard. Verified by `test_absent_stable_path_advisory_pass` on both wrappers (rc==0, `sentinel_advisory` row, no `sentinel_absence`). |
| R3 — absent + drift/unreadable → exit 3, unchanged severity; deliberate artifact-vs-synth asymmetry | PASS | Re-hash `OSError` → `rehashed=None` → `!= expected` → falls through. Artifact wrapper emits `sentinel_absence` (exit 3, `:848`); synth wrapper preserves EXISTING `synthesizer_drift` (exit 3, `:703/:743`) — the asymmetry the prompt flagged, correctly preserving prior behavior. Verified by `test_absent_drifted_path_*` and `test_absent_unreadable_path_exit3` on both wrappers. |
| R4 — `mismatch`/`read_failed` branches untouched; 3 `("absent", None)` unit tests + existing CLI tests green unmodified | PASS | Re-hash gated on `status == "absent"` only; `mismatch`/`read_failed` never enter it. `test_sentinel_absent_returns_absent`, `test_sentinel_in_evidence_quote_past_window_returns_absent`, `test_window_size_default_is_50` all green. `test_critical_review_phantom_guard.py` + `test_variant_a_writer_sites_baseline.py` green unmodified. |
| R5 — distinct event NAME + added to `_TELEMETRY_ONLY_EVENT_TYPES`; registry row + rebaseline note; phantom consumer in lock-step | PASS | `sentinel_advisory` is a distinct event name (not a `reason` on `sentinel_absence`); added to `_TELEMETRY_ONLY_EVENT_TYPES` frozenset at `common.py:607`. Registry row present + dated (2026-07-13) `sentinel_absence` narrowed-meaning note at `bin/.events-registry.md:103,105`. `test_lone_sentinel_advisory_is_phantom` asserts `is_phantom_lifecycle_dir` True for an advisory-only dir. |
| R6 — verification-gates re-hash rows + `--artifact-path` in both blocks + SKILL.md inline; "raw stdout" gone; total-failure literal byte-identical | PASS | Steps 2c.5 (`:43-44`) and 2d.5 (`:74-75`) describe the advisory-vs-exclusion split; both invocation blocks carry `--artifact-path <resolved_path>` (`:34`, `:67`); SKILL.md inline synth call carries it (`:67`). `grep -c "raw stdout"` = 0 (replaced by "the final message the Agent tool returns"). Total-failure literal byte-identical; `test_critical_review_reference_pins.py` green. |
| R7 — no new pure-verifier status literal; gate-class + mirror parity intact | PASS | No new return literal (re-hash lives in wrappers); wrapper decision sites carry `# gate-class: advisory` annotations. `test_critical_review_gate_class_parity.py` and `test_plugin_mirror_parity.py` green; the three `references/*.md` + SKILL.md mirrors diff-clean. |
| R8 — delete bug-seeding prose; reframe as advisory (MUST-escalation compliant) | PASS | `grep -c "preamble prose before it is fine"` = 0; both prompts reframe the sentinel as "an advisory read-attestation, not the drift gate" (`reviewer-prompt.md:17`, `synthesizer-prompt.md:16`). Pure prose removal — no new MUST language added. |
| R9 — ADR-0028 conforming to `cortex/adr/README.md` | PASS | `cortex/adr/0028-gate-time-rehash-is-authoritative-drift-check.md` present with `status: proposed` frontmatter and `## Context` / `## Decision` / `## Consequences` (+ `## Trade-off`); cites ADR-0015 as precedent; explicitly walks the three-criteria gate. `grep -rl "0028"` resolves. |

No FAIL → Stage 2 assessed.

## Stage 2 — Code Quality

- **Naming / structure**: consistent. New `_emit_sentinel_advisory` helper mirrors the existing `_build_sentinel_absence_event` centralization pattern; event token `sentinel_advisory` and `gate-class: advisory` annotations align with the sibling wrappers. Advisory-decision blocks are placed identically in both `_cmd_check_artifact_stable` and `_cmd_check_synth_stable`, before the exit-4 write-guard as the plan required.
- **Error handling**: fail-closed throughout. Unreadable/deleted re-hash path (`sha256_of_path` → `OSError` → `rehashed=None`) degrades to today's exit-3 exclusion, never a false pass. The advisory helper retains the dir-existence write-guard (returns 0 either way, correct since advisory-clean is a pass, not a suppressed-write exit-4). Omitting `--artifact-path` preserves exact prior behavior.
- **Test coverage**: the plan's verification steps were executed. Both artifact AND synth paths covered across advisory-pass / drift / unreadable / no-arg-backcompat (8 wrapper tests), the phantom discriminator gained a `sentinel_advisory` case, and the new `case-sentinel-absent-but-stable` fixture was ADDED (not substituted) with a sibling `.meta.json`; fixture `pinned_artifact_content` re-hashes to its declared `expected_sha` (verified in-test and independently here).
- **Pattern consistency**: dual-source canonical-only edits (mirrors regenerated, diff-clean); new event registered per the events-registry convention with an owner; MUST-escalation policy honored (prose deletion, no new MUST). Fail-closed total-failure contract preserved with the drift authority moved to gate-time re-hash, documented in ADR-0028.

Minor, non-blocking: the phantom-dir test fixture `_sentinel_advisory_event` (`tests/test_phantom_dir_discriminator.py:81-90`) includes a `reason: "absent_rehash_stable"` field that the real emitter never writes (the emitted advisory event has no `reason` key — see `__init__.py:788-796` / the registry schema). Harmless — the discriminator only reads the `event` field, so the test stays valid — but the fixture models a schema shape the producer does not emit.

## Requirements Drift

**State**: none
**Findings**: None
**Update needed**: None

The change operates entirely within existing architectural constraints already framed in `cortex/requirements/project.md`: the ADR framework ("`cortex/adr/` holds load-bearing decisions … Skills back-point to ADRs"), the events-registry registration convention ("New events register in `bin/.events-registry.md`"), dual-source canonical-only editing, and the MUST-escalation policy. ADR-0028 is the canonical home for the decision per that ADR constraint; no new capability or boundary is introduced that the requirements fail to capture.

## Verdict

{"verdict": "APPROVED", "cycle": 1, "issues": ["Non-blocking: phantom-dir test fixture _sentinel_advisory_event carries a reason field the real emitter never writes (harmless schema-shape divergence in the test fixture only)."], "requirements_drift": "none"}
