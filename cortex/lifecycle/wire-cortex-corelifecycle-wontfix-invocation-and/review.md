# Review: wire-cortex-corelifecycle-wontfix-invocation-and

Reviewed commits c5643846..8028e1c1 on `main` (READ-ONLY). All three new test
files pass (35 tests, 0.17s); dual-source parity (59), phase-parity / L1-ratchet
/ size-budget / kept-pauses (78) all green; `just check-parity` clean. The
`--audit`-mode failures observed (events-registry STALE_DEPRECATION rows and
`python3 -m` callsites in `__pycache__`/historical tests) are pre-existing
repo-wide drift unrelated to #329 — none reference `feature_wontfix`,
`parse-args`, or `wontfix`.

## Stage 1: Spec Compliance

### Requirement 1: Structural parse helper exists and is unit-tested
- **Expected**: `cortex_command/lifecycle/parse_args.py` emitting one JSON `{mode,feature,phase}`; console-script; `wontfix add-foo` → mode=wontfix, feature=add-foo; test file exits 0.
- **Actual**: Module present; `main` writes `json.dumps(parse(...))`. Smoke: `wontfix add-foo` → `{"mode":"wontfix","feature":"add-foo","phase":""}`. `pyproject.toml:56` registers the console-script. Tests pass.
- **Verdict**: PASS
- **Notes**: feature is `add-foo`, not `wontfix` — the inversion is correct.

### Requirement 2: Canonical grammar covers the full reserved set
- **Expected**: reserved {wontfix,resume,complete} + phase tokens {research,specify,plan,implement,review} (+complete as phase); closed `mode` set enumerated as a module constant.
- **Actual**: `KNOWN_MODES`, `RESERVED_WORDS`, `PHASE_TOKENS` constants present (lines 34/46/51). Parametrized `test_grammar_reserved_and_default` asserts each reserved word + numeric/default forms; `-k grammar` passes.
- **Verdict**: PASS

### Requirement 3: Parse order is correct and edge-safe
- **Expected**: empty → `#`-sigil → reserved match → slug/prose; `#wontfix` not routed to verb; `wontfix` alone is error; prose first word → needs-derivation.
- **Actual**: `parse()` follows that exact order. `#wontfix` → `feature/wontfix`; `wontfix` alone → `error`; `resume` alone → `empty` (scan fallback); prose → `needs-derivation`. `-k edge` tests pass.
- **Verdict**: PASS

### Requirement 4: SKILL.md Step 1 routes via the helper
- **Expected**: Step 1 invokes `cortex-lifecycle-parse-args "$ARGUMENTS"` and acts on `mode`; old first-word prose removed; `wontfix` terminal/short-circuiting.
- **Actual**: Step 1 (lines 36-55) calls the helper + an 8-row act-on-`mode` table. `wontfix` row says "**halt** … do not fall through to Step 2." grep: parse-args=1, "first word = feature name"=0. The preserved explicit-phase-override route (line 55) handles `complete` + `<feature> <phase>`.
- **Verdict**: PASS

### Requirement 5: `resume <feature>` requires an existing lifecycle
- **Expected**: resume binds word #2, routes to Step 2 detection, refuses (no-create) when dir absent; resume-no-slug → scan fallback.
- **Actual**: parse `resume foo` → `mode=resume, feature=foo`; `resume` alone → `empty`. SKILL.md resume row (line 47): "if `cortex/lifecycle/<feature>/` does not exist, report 'no such lifecycle to resume' and stop — do not create it."
- **Verdict**: PASS
- **Notes**: absent-dir refusal is model-executed prose, as the spec acknowledges.

### Requirement 6: `complete <slug>` routes to the Complete phase
- **Expected**: `complete <slug>` → feature=slug, phase=complete; routes into Complete.
- **Actual**: parse `complete my-feature` → `feature=my-feature, phase=complete`. SKILL.md complete row (line 48) routes via the explicit-phase-override route. Fixes the previously-broken `complete.md:72/80` re-invocation.
- **Verdict**: PASS

### Requirement 7: Bare phase tokens get a non-broken fallback
- **Expected**: bare `plan` classifies as phase token (not feature=plan); SKILL.md surfaces feature-required message.
- **Actual**: parse `plan` → `{mode:phase, phase:plan}`. SKILL.md phase row (line 49) + line 188 surface "specify a feature … does not resolve to an active feature."
- **Verdict**: PASS

### Requirement 8: Drift-guard test — docs-derived, oracle + bidirectional control
- **Expected**: scrape live doc bytes for `/cortex-core:lifecycle <…>`, normalize placeholders, classify via independent shape→mode oracle; two negative controls incl. doc-form-without-parser-support.
- **Actual**: `_FORM_RE` with `{1,2}` capture keeps reserved two-token forms intact (`test_grammar_reserved_two_token_forms_captured_intact`); `_NORMALIZE` map; independent `_expected_mode` oracle; vacuous-pass guard (`>= 8`). Two negative controls present: (i) broken `complete`→`feature` parser raises; (ii) `abandon <slug>` advertised-as-wontfix raises (the docs→parser recurrence vector). All pass.
- **Verdict**: PASS

### Requirement 9: Every advertised surface reconciled to the implemented grammar
- **Expected**: argument-hint/inputs, Invocation block (incl. line 25), honor-phase line 169, complete.md reconciled; `wontfix <slug>` added; no doc advertises behavior the parser does not produce.
- **Actual**: Invocation block (lines 24-28) updated, `wontfix {{slug}}` added; honor-phase region (lines 169/188) reworded to feature-required ("does not resolve to an active feature"); complete.md already advertised the now-correct `complete <slug>`/`wontfix <slug>` forms (so the parser change reconciles it — no edit needed; mirror identical). grep: "honor the request"=0, wontfix=4. Drift-guard passes against live docs.
- **Verdict**: PASS

### Requirement 10: Mode→branch coverage (glue guard)
- **Expected**: every enumerated `mode` literal has a routing row in Step 1.
- **Actual**: `test_mode_coverage_every_known_mode_has_a_routing_row` requires each `KNOWN_MODES` literal as a table cell (`` | `mode` ``) — discriminating against incidental English words. Step 1 table has all 8 rows. Passes.
- **Verdict**: PASS

### Requirement 11: Order-enforcing verb exists
- **Expected**: `wontfix_cli.py` + console-script; argparse positional `slug` + `--reason` + optional `--backlog-slug` (no required flags); three gated steps in one function.
- **Actual**: Module present; `pyproject.toml:59` registers it. `_build_parser` is positional-`slug` + two optional flags. `_run` performs (a) move → (b) append → (c) terminalize sequentially. `--help` exits 0; test file passes.
- **Verdict**: PASS

### Requirement 12: Archive-move uses os.rename, named main-root resolver, 4-case guard
- **Expected**: `os.rename` (fallback `shutil.move`) anchored to `_resolve_user_project_root()` (NOT `_from_cwd`); `mkdir(archive/)`; 4-case guard; worktree-without-env refusal.
- **Actual**: `_archive_move` does the 4-case guard (dst&!src→no-op, both→error-no-nest, neither→unknown-slug, src&!dst→move) then `dst.parent.mkdir(parents=True)` + `os.rename`/`shutil.move`. Root via `_resolve_user_project_root()` (line 172). Worktree guard (line 177): `not env_root and (root/".git").is_file()` → refuse. Tests cover untracked-archive, rerun-no-op, both-exist-no-nest, worktree-refuses, env-bypass. All pass.
- **Verdict**: PASS

### Requirement 13: Byte-faithful feature_wontfix row via atomic append
- **Expected**: default json separators, insertion-ordered keys, `Z`-suffixed strftime, written to the archived events.log via reused `flock`+tempfile+`os.replace` (NOT log_event); idempotent via parsed event-field match; semantic detector parity test + template regression.
- **Actual**: `_append_wontfix_row` uses `datetime.now(tz=utc).strftime("%Y-%m-%dT%H:%M:%SZ")`, default `json.dumps`, key order ts/event/feature/reason, calls imported `_append_event_atomic` (confirmed flock+tempfile+os.replace) on `dst/"events.log"`. `_has_wontfix_row` parses each line and matches `obj.get("event") == "feature_wontfix"` (not substring grep). Test asserts `detect_lifecycle_phase`→complete, `"feature_wontfix"` statusline grep, template equality, trailing newline, clean second append.
- **Verdict**: PASS

### Requirement 14: Backlog terminalization with a real producer, verified, slug-validated
- **Expected**: shell `cortex-update-item --status wontfix --lifecycle-phase wontfix --session-id null`; target from index.md parent (read before move) + `--backlog-slug` override; ad-hoc→documented no-op; zero-match→non-zero; slug-validated pre-move; exit codes 0/1/2 with `cortex-lifecycle-wontfix:` stderr prefix.
- **Actual**: `_terminalize_backlog` shells the exact command; `_read_backlog_target` prefers `parent_backlog_uuid` then `parent_backlog_id`, read before the move (line 193 reads src-or-dst). `None` target → no-op. returncode 0→ok, 2→exit-2 propagate (+child stderr), other→`WontfixError(1)` (zero-match non-zero). `_SLUG_RE` validates before any fs op → `WontfixError(2)`. `main` prefixes stderr `cortex-lifecycle-wontfix:`. Five tests cover all cases; pass.
- **Verdict**: PASS
- **Notes**: invalid-slug maps to exit 2 (usage-class), consistent with argparse-usage=2; pinned by `test_traversal_slug_rejected_pre_move`. Defensible reading of the exit-code table.

### Requirement 15: Fail-forward recovery re-asserts each postcondition idempotently
- **Expected**: never rolls back the move; re-invocation independently re-asserts each step (move-if-not-archived, append-if-no-row, terminalize-if-not-terminal); (a)-success/(b)-failure repaired on re-run.
- **Actual**: No rollback path exists. Each of the three step helpers is independently guarded/idempotent. `test_fail_forward_repairs_partial_run_on_reinvocation` simulates step-(b) `OSError` after a successful move, then re-runs and asserts the row present + item terminalized.
- **Verdict**: PASS

### Requirement 16: `wontfix` route wired to the verb
- **Expected**: SKILL.md wontfix mode invokes `cortex-lifecycle-wontfix <slug> --reason …`, requires the slug, does not fall through; `just check-parity` W003 satisfied.
- **Actual**: SKILL.md line 46 names `cortex-lifecycle-wontfix <feature> --reason "<short rationale>"` + halt + exit-2 handling. Both new console-scripts referenced from in-scope skills files (W003). `just check-parity` clean.
- **Verdict**: PASS

### Requirement 17: `references/wontfix.md` thinned (B2)
- **Expected**: keep WHEN/WHY + exit-2 + detector-belt note; replace 3 bash snippets with single verb call noting code-invariant order; correct stale citation to `scan_lifecycle.py:907`; remove "Step order is load-bearing" prose-gate.
- **Actual**: wontfix.md keeps use-case triage, exit-2 ambiguity, detector-belt note; one `cortex-lifecycle-wontfix <slug> --reason …` call; "move → append → terminalize order is now a code invariant." grep: git mv=0, cortex-lifecycle-wontfix=1. Citation corrected to `cortex_command/hooks/scan_lifecycle.py:907` — verified line 907 holds `if feature in ("archive", "sessions"): continue`.
- **Verdict**: PASS

### Requirement 18: Registry hygiene, ADR back-pointer, mirrors regenerated
- **Expected**: events-registry producer names the Python module (+`scan_coverage`→`manual`); verb back-points ADR-0004; parser/grammar decision = ADR-0018; edited mirrors regenerated + committed.
- **Actual**: registry row producer = `cortex_command/lifecycle/wontfix_cli.py`, scan_coverage `manual`. Verb docstring + wontfix.md back-point ADR-0004. ADR-0018 created (status: proposed). Mirrors: SKILL.md, references/wontfix.md, references/complete.md all byte-identical to canonical. dual-source parity test passes (59).
- **Verdict**: PASS
- **Notes**: ADR-0018 has no on-disk collision (0017 is #335's config-reconcile). Cross-ticket coordination only: MEMORY records #330's spec also proposed 0018 — since #329 shipped 0018 first, #330 will need to bump to 0019 at build time. Not a #329 defect.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with sibling lifecycle CLIs. `wontfix_cli.py` follows the `*_cli.py` convention (branch_mode_cli/dispatch_choice_cli/state_cli/picker_decision_cli). `parse_args.py` drops the `_cli` suffix, but so do `counters.py`/`complexity_escalator.py`/`init_ensure.py`; acceptable for a pure classifier. Module constants (`KNOWN_MODES`/`RESERVED_WORDS`/`PHASE_TOKENS`) are clear and single-sourced.
- **Error handling**: `WontfixError(exit_code, message)` → `main` writes `cortex-lifecycle-wontfix: {message}` and returns the code; exit codes 0/1/2 as specced; argparse usage=2; worktree guard fails loud. Minor observation (non-blocking): a step-(b) `OSError` propagates uncaught from `main` as a raw traceback rather than a prefixed message — this is the intended fail-forward design (move already landed the safe end-state; re-run repairs, pinned by the fail-forward test), so it is consistent with Req 15, just not a clean stderr line.
- **Test coverage**: Strong and discriminating. parse_args covers reserved/default/numeric/sigil/prose/empty + every-mode-known. wontfix_cli covers all four guard branches, both worktree arms, the full row contract (detector + statusline + template + newline + second-append), all five terminalization cases, and the fail-forward repair. The drift-guard oracle is genuinely independent of `parse()`, has a vacuous-pass guard, a capture-width assertion, a table-cell-discriminating mode-coverage check, and two negative controls that demonstrably bite. No self-sealing or tautological tests found.
- **Pattern consistency**: telemetry first-line `_telemetry.log_invocation(...)` matches all sibling CLIs; `_build_parser()` + `main(argv)` shape matches; atomic-append reused via import-as-name so tests patch the verb's own binding (and the template regression pins the bytes). Backlog target resolved before the move so a partial-archive re-run still finds index.md under `archive/`.

## Requirements Drift

**State**: none
**Findings**:
- None. The new console-scripts follow the existing "Skill-helper modules" architectural constraint (SKILL.md ceremony → `cortex_command/<skill>` console-scripts); `feature_wontfix` is already registered and `wontfix` is already a `TERMINAL_STATUS`; ADR-0018 fits the `cortex/adr/` constraint; no new event/status/kept-pause; resolver + worktree-refusal behavior is already governed by the resolver/worktree-containment constraints in project.md.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
