# Plan: investigate-critical-review-telemetry-creating-phantom

## Overview
Implement A+C: a write-only, verdict-preserving guard at the three critical-review telemetry writers
(Phase 1) plus a content-based phantom discriminator wired into SessionStart enumeration (Phase 2). The
guard introduces a distinct exit code (`4` = "telemetry skipped: lifecycle dir absent") so a skipped
write is observably distinct from a real invalidation (`3`) and from clean/recorded (`0`). The
discriminator reads events.log as JSONL and closes only the gap `_is_stale` leaves open: a telemetry-only
dir with a *recent* timestamp.
**Architectural Pattern**: layered
<!-- The guard sits at the write layer (telemetry subcommands), the discriminator at the detection layer (scanner); each enforces the phantom invariant independently. -->

## Outline

### Phase 1: Structural write-guard (tasks: 1, 2, 3, 4)
**Goal**: telemetry writers no longer create a lifecycle dir as a side effect; the skip is observably distinct from a real invalidation; the documented prose contract is tightened to match AND its plugin mirror regenerated in the same commit.
**Checkpoint**: `tests/test_critical_review_phantom_guard.py` green AND `tests/test_plugin_mirror_parity.py` green (Task 4 regenerates the mirror in-commit, so parity stays green); a dir-absent invocation creates no dir and no events.log.

### Phase 2: Detection discriminator + housekeeping (tasks: 5, 6, 7, 8, 9)
**Goal**: a telemetry-only artifact-less dir with a recent ts is not surfaced as a "research" lifecycle, with no false-positive on legitimate fresh or legacy lifecycles; stale registry pointers (module path AND line ranges) fixed; sibling audit recorded; mirrors + suite green.
**Checkpoint**: `tests/test_phantom_dir_discriminator.py` green; `just test` exits 0; plugin mirror parity green.

## Tasks

### Task 1: Add guard helper and the exit-4 "telemetry skipped" contract
- **Files**: `cortex_command/critical_review/__init__.py`
- **What**: Add a module-level helper `_lifecycle_dir_exists(lifecycle_root: str, feature: str) -> bool` returning whether `Path(lifecycle_root) / feature` is an existing directory, and define a named constant for the skip exit code (e.g. `EXIT_TELEMETRY_SKIPPED = 4`). Carry a `# gate-class: hygiene` annotation at the guard definition.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_default_lifecycle_root()` is at `:524`; `append_event` (the unconditional `mkdir(parents=True, exist_ok=True)`) at `:455-469`. Exit codes currently in use across the handlers: `0` (clean/recorded), `2` (OSError), `3` (drift/absence); `4` is unused (verified). Do NOT put the guard inside `append_event` — it must keep creating the dir for the legitimate fresh-lifecycle first-write at Site A (`refine.py`).
- **Verification**: `grep -c 'gate-class: hygiene' cortex_command/critical_review/__init__.py` ≥ 1 increase over baseline; `python3 -c "from cortex_command.critical_review import _lifecycle_dir_exists"` exits 0.
- **Status**: [x] done

### Task 2: Wire the guard into the three telemetry writers (write-only, verdict-preserving)
- **Files**: `cortex_command/critical_review/__init__.py`
- **What**: In `_cmd_check_synth_stable` (:645, writes on the `:692` exit-3 path), `_cmd_check_artifact_stable` (:695, writes on the `:752` exit-3 path), and `_cmd_record_exclusion` (:755, always writes, returns `0` at `:778`): immediately before the `append_event` call, consult `_lifecycle_dir_exists`. If the dir is absent, emit a one-line stderr note naming the skipped feature, skip the `mkdir`+append entirely, and return `EXIT_TELEMETRY_SKIPPED` (4). When the dir exists, behavior is unchanged (exit 0/3 as today). The guard MUST NOT alter the integrity verdict otherwise.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Each writer computes `events_log = Path(lifecycle_root) / args.feature / "events.log"` with `lifecycle_root = args.lifecycle_root or _default_lifecycle_root()` (`:647/:659`, `:697/:743`, `:757/:762`). **Real consumer surface to keep consistent** (there is NO inter-subcommand internal call — each of the three `_cmd_*` calls `append_event` directly; the four registered subparsers are `prepare-dispatch`/`check-synth-stable`/`check-artifact-stable`/`record-exclusion` at `:801/:823/:834/:886`; `verify-reviewer-output` does NOT exist — it was renamed to `check-artifact-stable` by #255, so do not search for it): (a) the prose routing in `skills/critical-review/references/verification-gates.md` and `SKILL.md` (Task 4 updates these to route exit 4); (b) `tests/test_variant_a_writer_sites_baseline.py`, which asserts `rc == 3` on a synth-drift writer path and exists to pin the writers' current dir-creating side effect — confirm its assertions pre-create the feature dir (so exit 4 never fires there) and, if any assertion would otherwise observe a dir-absent path, reconcile it in Task 3.
- **Verification**: `python3 -m pytest tests/test_critical_review_phantom_guard.py -q` exits 0.
- **Status**: [x] done

### Task 3: Unit tests for the write-guard
- **Files**: `tests/test_critical_review_phantom_guard.py`
- **What**: Add tests asserting: (a) each of the three subcommands invoked with a `--feature` whose `cortex/lifecycle/{feature}/` dir does NOT exist creates no directory, writes no events.log, and returns exit 4; (b) the auto-trigger invariant — when the dir already exists, each writer appends normally and a genuine drift/absence still returns exit 3 (synth/artifact) / records and returns 0 (record-exclusion); (c) exit 4 is distinct from both 3 and 0. Confirm `tests/test_variant_a_writer_sites_baseline.py` still passes unchanged (its assertions pre-create the dir).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Use a `tmp_path` lifecycle root and pass `--lifecycle-root` to the subcommands. Mirror existing `tests/test_critical_review*` invocation idioms (call the `_cmd_*` functions or the argparse entry point).
- **Verification**: `python3 -m pytest tests/test_critical_review_phantom_guard.py tests/test_variant_a_writer_sites_baseline.py -q` exits 0; the new module reports ≥ 4 tests.
- **Status**: [x] done

### Task 4: Route exit 4 in the orchestrator gate, tighten the contract prose, and regenerate the mirror in-commit
- **Files**: `skills/critical-review/references/verification-gates.md`, `skills/critical-review/SKILL.md`, `plugins/cortex-core/skills/critical-review/references/verification-gates.md`, `plugins/cortex-core/skills/critical-review/SKILL.md`
- **What**: In `verification-gates.md` update the Phase-1 exit-code routes (the Exit-0/Exit-3 bullets at `:53-54`) and the Step 2d.5 routes (`:83-84`) so **exit 4 is treated as a benign skip** (telemetry not persisted; reviewer neither excluded-for-drift nor failed), distinct from exit 3. State that the `<path>`-arg / no-`--feature` form skips telemetry and the guard now enforces this structurally. Do NOT touch the canonical preamble MUST/MUST-NOT lines at `:1-7`. Mirror the wording in `SKILL.md`. **Then regenerate the plugin mirror and stage it in this same commit** — the pre-commit hook (`.githooks/pre-commit:583,600`) sets `BUILD_NEEDED=1` for any staged `skills/` path, runs `just build-plugin` (rsync `--delete` of `skills/critical-review` → mirror), and a Phase-4 drift loop rejects the commit if the mirror differs from the index; so the regenerated `plugins/cortex-core/skills/critical-review/` files must be staged together. (Do NOT edit `skills/discovery/references/research.md`: its `:130` line is just `Run /cortex-core:critical-review on cortex/research/{topic}/research.md` with no `--feature`/`<path>` distinction to tighten — the contract lives entirely in `verification-gates.md`.)
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Phase-1 routing bullets at `verification-gates.md:53-54`; Step 2d.5 at `:83-84`. `just build-plugin` (`justfile:574-597`) rsyncs every `skills/$s` into `plugins/$p/skills/$s`; run it (or `just setup-githooks` so the hook does) before committing. `tests/test_plugin_mirror_parity.py` byte-compares every `*.md` under `skills/critical-review/references/` against the mirror.
- **Verification**: `grep -ci 'exit 4\|skipped\|structurally' skills/critical-review/references/verification-gates.md` ≥ 1; `sed -n '1,7p' skills/critical-review/references/verification-gates.md | grep -c 'MUST'` equals baseline; `diff -r skills/critical-review/ plugins/cortex-core/skills/critical-review/` exits 0; `python3 -m pytest tests/test_plugin_mirror_parity.py -q` exits 0.
- **Status**: [x] done

### Task 5: Phantom predicate (branch (i) only; empty case delegated to `_is_stale`)
- **Files**: `cortex_command/common.py`
- **What**: Add a predicate `is_phantom_lifecycle_dir(feature_dir: Path) -> bool` returning True iff the dir has no `research.md`/`spec.md`/`plan.md` AND its JSONL-parsed event-type set is **non-empty and a subset of** `{"synthesizer_drift", "sentinel_absence"}`. Read events.log as JSONL (one `json.loads` per line, skip unparseable lines). Do NOT add an empty/absent/unparseable branch and do NOT add a whole-file `yaml.safe_load`: the empty/absent/unparseable-events.log case is already owned by `_is_stale` (see Context), and a legacy YAML-block-only file yields an empty JSONL set so the non-empty-subset test is False and it is correctly NOT classified as a phantom.
- **Depends on**: none
- **Complexity**: complex
- **Context**: `_is_stale` (`scan_lifecycle.py:398`) runs first in the candidate loop and returns True (stale → excluded) immediately for a missing/unreadable/empty events.log or one with no parseable `ts` (`:417-420` `except (OSError, ValueError): return True`; `:445-446` `latest is None: return True`) — regardless of age. So the empty/absent case needs no predicate branch. The gap `_is_stale` leaves is a telemetry-only dir whose events carry a *recent* `ts` (`synthesizer_drift`/`sentinel_absence` both carry `ts`): it passes `_is_stale` and `detect_lifecycle_phase` defaults it to "research" (`common.py:367-368`). Branch (i) closes exactly that. The existing readers are JSONL-only (`_detect_lifecycle_phase_inner:271` parses any non-empty line; `scan_lifecycle.py:302,425` gate on `startswith("{")`) — match the `json.loads`-per-line approach; do not assume a YAML-tolerant reader (none exists). Add a code comment: predicate complements `_is_stale` (which owns empty/absent) by covering the recent-ts telemetry-only window.
- **Verification**: `python3 -m pytest tests/test_phantom_dir_discriminator.py -q` exits 0.
- **Status**: [x] done

### Task 6: Wire the predicate into SessionStart enumeration, after `_is_stale`
- **Files**: `cortex_command/hooks/scan_lifecycle.py`
- **What**: In the candidate-enumeration loop, **after** the existing `_is_stale` check (so the empty/absent case is already excluded), skip surfacing any dir the predicate classifies as a phantom (do not report it as an incomplete/"research" lifecycle). Preserve the existing `archive/`/`sessions/` exclusion.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: The candidate loop is around `scan_lifecycle.py:886-980`; `_is_stale(child, stale_days)` is at `:900-903`; `detect_lifecycle_phase`'s default-to-research is `common.py:367-368`. The predicate gate must run after `_is_stale` and before the dir is surfaced. Import `is_phantom_lifecycle_dir` from `cortex_command.common`.
- **Verification**: `python3 -m pytest tests/test_phantom_dir_discriminator.py -q` exits 0.
- **Status**: [x] done

### Task 7: Discriminator tests
- **Files**: `tests/test_phantom_dir_discriminator.py`
- **What**: Add tests asserting: (a) live-phantom **birth** signatures are classified as phantoms — a lone `synthesizer_drift` JSONL event (recent ts), and 3× `sentinel_absence` JSONL events (NOT the now-`feature_wontfix`-capped archived content); (b) a freshly-started legitimate lifecycle (events.log holds `lifecycle_start`/`clarify_critic` JSONL, no artifacts yet) is NOT classified as a phantom (so it is still surfaced); (c) a real dir lacking `lifecycle_start` but containing other non-telemetry events is NOT classified; (d) a dir whose events.log is a hybrid YAML-block + JSONL file with non-telemetry JSONL events is NOT classified (its JSONL set is not a telemetry subset). Note: the empty/absent-events.log suppression is owned by `_is_stale` and is out of this predicate's scope (do not assert the predicate suppresses an empty dir).
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Build fixtures under `tmp_path`; encode synthetic JSONL fixtures rather than reading live archive paths. The `synthesizer_drift`/`sentinel_absence` JSONL shapes can be referenced from `cortex/lifecycle/archive/doc-audit-2026-05-18/events.log` but encoded synthetically with a recent ts.
- **Verification**: `python3 -m pytest tests/test_phantom_dir_discriminator.py -q` exits 0 and reports ≥ 4 tests.
- **Status**: [x] done

### Task 8: Fix stale events-registry pointers (module path AND line ranges) + record sibling-gate audit
- **Files**: `bin/.events-registry.md`
- **What**: Correct the producer code pointers for the `sentinel_absence` and `synthesizer_drift` rows: the module path (`cortex_command/critical_review.py` → the package `cortex_command/critical_review/__init__.py`) AND the now-stale line ranges (verify against the current file — e.g. `_build_sentinel_absence_event` and the `synthesizer_drift` event dict are no longer at the old `:375-416`/`:318-322` ranges; cite the actual current lines). Append a one-line note recording that the broad sibling-gate audit was performed and that `residue-write` (resolver-exit-gated), `complexity_escalator` (R11-guarded), and `lifecycle_critical_review_skipped` (fires only where the dir exists) were found already structurally protected and need no conversion.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Rows at `bin/.events-registry.md:113` (`sentinel_absence`) and `:114` (`synthesizer_drift`), `target: per-feature-events-log`, `scan_coverage: manual`. Editing `bin/.events-registry.md` does NOT trigger the plugin-mirror build (it is not under `skills/` nor a `bin/cortex-*` file), but it DOES trigger `cortex-check-events-registry` (referential event-name validation only — it does not resolve producer pointers, so the pointer fix is review-enforced, not gate-enforced). Verify the corrected line ranges by reading the current `__init__.py` before editing.
- **Verification**: `grep -c 'critical_review/__init__.py' bin/.events-registry.md` ≥ 2 (both rows); `grep -c 'critical_review.py:' bin/.events-registry.md` = 0 (no bare-module pointer remains); `grep -ci 'residue-write\|already guarded\|R11\|sibling' bin/.events-registry.md` ≥ 1; the events-registry audit recipe (if present) exits 0.
- **Status**: [x] done

### Task 9: Final suite + parity verification
- **Files**: (verification-only; no new source edits — any mirror regen already landed in Task 4)
- **What**: Run the full suite and parity checks to confirm the feature is green end-to-end. If `just setup-githooks` is not enabled in the implementer's environment, confirm the Task 4 mirror was regenerated manually and is byte-identical.
- **Depends on**: [4, 8]
- **Complexity**: simple
- **Context**: `tests/test_plugin_mirror_parity.py` enforces mirror byte-identity (Task 4 owns the critical-review mirror regen). `just test` runs the whole suite.
- **Verification**: `python3 -m pytest tests/test_plugin_mirror_parity.py -q` exits 0; `just test` exits 0.
- **Status**: [x] done

## Risks

- **Spec/reality mismatch on the events reader (resolved in this plan).** Spec Req 5 assumed an existing
  YAML-tolerant reader and a predicate-owned empty-case branch; the actual readers are JSONL-only and
  `_is_stale` already owns the empty/absent/unparseable case immediately. Task 5 reconciles by reading
  JSONL and keeping only branch (i) (telemetry-only, recent ts) — the sole gap `_is_stale` leaves. A
  legacy YAML-block-only file yields an empty JSONL set → not a phantom (conservative direction).
- **Exit-4 is a new exit code on a public CLI surface.** Verified the only programmatic consumers are the
  `verification-gates.md`/`SKILL.md` routing tables (Task 4) and `test_variant_a_writer_sites_baseline.py`
  (`rc==3`, which pre-creates the dir so exit 4 never fires there). There is no inter-subcommand internal
  call. If a future external caller checks `== 3` for "any failure," exit 4 would read as not-that-failure
  — acceptable since the documented consumer is the orchestrator gate.
- **Plugin-mirror coupling (resolved in this plan).** The pre-commit drift loop forces the
  `skills/critical-review` mirror regen into the same commit as the canonical edit; Task 4 owns both, so
  no intermediate commit strands a stale mirror.
- **Allow-set coupling.** The predicate hard-codes `{synthesizer_drift, sentinel_absence}`; a future
  telemetry-only event type would need adding. Documented as a Non-Requirement in the spec.
- **Standalone-path false-suppression (B-class, accepted residual).** A standalone critical-review writing
  only telemetry into a pre-existing operator dir before `lifecycle_start` would be classified as a
  phantom; flagged in the review residue, mitigation deferred (classify-but-report) rather than dismissed.

## Acceptance
Running `just test` exits 0 with the two new test modules and the plugin-mirror parity test green;
invoking any of the three critical-review telemetry subcommands with a `--feature` whose lifecycle dir
does not exist creates no directory and no events.log (exit 4); and a SessionStart scan over a fixture set
surfaces a freshly-started legitimate lifecycle while classifying a recent-ts telemetry-only artifact-less
dir as a phantom — demonstrating the phantom is prevented at the write site and neutralized at the
detection site without false-positiving real lifecycles.
