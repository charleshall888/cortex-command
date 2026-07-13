# Review: 378 — 374 follow-ups (lifecycle_slug coercion, spec-approve routing, CLI_PIN dedup)

Cycle 1. Read-only review of the 11-task implementation against `spec.md`. All acceptance
greps/pytests below were executed. Two plan-time decisions (req-9 re-scope; req-8 prose form)
are assessed against the guidance supplied and noted honestly where they diverge from the
literal spec text.

## Stage 1 — Spec Compliance

| Req | Rating | Evidence |
|-----|--------|----------|
| 1. Key-scoped YAML-safe scalar writer | **PASS** | `frontmatter_quote.py`: `STRING_INTENDED_KEYS = {lifecycle_slug, feature, parent, spec}`; None sentinel (`null/Null/NULL/~`) excluded even on allowlisted keys; empty string correctly NOT a null token (quoted to `""`); `_mis_resolves` defers to `yaml.safe_load` for the ambiguous class + forces short bool variants (`y/n/ON/…`) + metachar/control detection; `_double_quote` escapes `\ " \n \r \t \0` and `\xHH` for other C0/0x7F. `test_frontmatter_quoting.py` green (25 assertions incl. round-trip). `grep -c safe_dump update_item.py` = 0. All three writers route through `quote_scalar` (update_item:67, create_index:119, report.py:461). |
| 2. Backfill 4 malformed files | **PASS** | `grep -rnE '^(lifecycle_slug\|feature): [0-9]+$' cortex/backlog cortex/lifecycle` = 0. |
| 3. Defensive reader coercion | **PASS** | `resolve_item.py:142` `return str(slug)` (None falsy → falls through, never `"None"`); `resolve.py:186-187` coerces before `lifecycle_base / slug`. `test_resolve_numeric_slug_coercion.py` green. |
| 4. Green the existing gate | **PASS** | `test_every_lifecycle_reference_resolves` green. |
| 5. Close lifecycle_phase write-omission | **PASS** | `finalize.py:165` + `close_tickets.py:152` pair `lifecycle_phase: complete` with the status write; `advance.py` `_project_status_inner` (:730-732) advances phase via `_STATE_TO_PHASE` (only `complete` mapped — a cancel/wontfix `to_state` is NOT mislabelled `complete`). `test_lifecycle_phase_tracks_status.py` green. |
| 6. Backfill 60 stale items | **PASS** | `grep -lE '^status: complete' cortex/backlog/*.md \| xargs grep -lE '^lifecycle_phase: research$'` = 0 files (327 complete items, none frozen). |
| 7. Extend spec-approve arm (spec/areas ONLY) | **PASS** | `_project_spec_areas_inner` (:773-822) writes ONLY `spec` + preserve-on-omit `areas` — **never status**; self-resolves backend via `resolve_backlog_backend(root)` (not the caller `--backend` flag) + archive-shadow guard, matching `_project_status`. `test_advance_spec_approve_writeback.py` green: (a) status:refined+spec+areas; (b) a `complete` item is NOT demoted yet still gains spec/areas; (c) emission-only caller unchanged. |
| 8. Reroute prose off legacy verb | **PASS** | `grep -rn 'cortex-lifecycle-spec-approve' skills/` = 0; `cortex-lifecycle-advance spec-approve` present at `specify.md:149`; `bin/cortex-lifecycle-spec-approve` binary retained (ADR-0024); `git diff plugins/cortex-core/` clean (mirror synced, no legacy verb in mirror). SKILL.md:90 + refine-delegation.md:7,55 use the bare `cortex-lifecycle-advance` binary + "spec-approve" in prose — the sanctioned E101-avoidance house convention, not an omission. |
| 9. Absorbed-verb prose guard | **PARTIAL** | Intent MET, literal form diverges (accepted at plan Task 8). The standalone `bin/cortex-check-absorbed-verbs --staged/--audit` scanner + `just check-absorbed-verbs` recipe were deliberately NOT built (would false-flag sanctioned mentions + the live `cortex-lifecycle-event phase-transition` verb). Instead `test_lifecycle_event_roundtrip.py::test_refine_prose_off_legacy_spec_approve_verb` (:585) is a genuine per-file regression guard — zero-legacy-verb sweep over `skills/refine/` + a served-form-present assertion. Catches re-introduction. Rated PARTIAL only for the literal-acceptance divergence per review guidance. |
| 10. Converge CLI_PIN to v2.35.0 | **PASS** | Both pins = `("v2.35.0", "2.0")`. |
| 11. Multi-target release/parity + target-set invariant | **PASS** | `DEFAULT_TARGETS` names both pin files; `auto-release.yml:135/143` runs+`git add`s both; `release.yml` drift lint iterates both; `test_cli_pin_target_set.py` binds membership (i) + guard discrimination (iii) + behavioural end-to-end rewrite-both; `test_release_artifact_invariants.py` reads both paths. Not a point-in-time equality check. All green. |
| 12. Wire regression guards into CI | **PASS** | `grep -Ec 'test_lifecycle_references_resolve\|test_cli_pin_target_set\|test_lifecycle_event_roundtrip' validate.yml` = 3. |

No hard FAIL on any Must requirement (1-8, 10-11). req-9 is a Should, rated PARTIAL (intent met).
Proceeding to Stage 2.

## Stage 2 — Code Quality

**(a) frontmatter_quote.py vs req-1** — Correct. The key allowlist carries intent that the
value-erasing writer boundary cannot (`str(value)`). None-sentinel exclusion is applied on BOTH
the allowlisted and non-allowlisted paths; empty string is deliberately kept out of the null-token
set so it quotes to `""`. `_mis_resolves` delegates the ambiguity class to the actual reader
(`yaml.safe_load`) rather than re-implementing YAML 1.1 resolution — robust — while force-quoting
the short bool variants PyYAML reads as strings. Escaping (`_double_quote`) round-trips exactly
(`test_quote_backslash_colon_round_trips`, `test_control_chars_round_trip`).

**(b) advance.py `_project_spec_areas` NOT writing status (hazard-4)** — Confirmed safe. The seam's
`fields` dict is `{"spec": ...}` (+ optional `areas`) only; status is never in it. Backend gate and
archive-shadow guard mirror `_project_status` exactly, so the two writes cannot disagree on
writability. The non-demotion test (b) exercises a `complete` item and proves status stays
`complete` while spec/areas still project — the events-first ownership boundary holds.

**(c) rewriter absent-target skip (Task 9) not masking a missing pin** — Acceptable. `main()`
skips an absent target with a stderr note (for single-file test fixtures over the default set). A
GENUINELY missing pin is backstopped: `release.yml`'s drift lint opens both pin paths
unconditionally and would hard-fail (unhandled `open()`), and the target-set test binds membership.
Minor: `test_cli_pin_target_set` checks `DEFAULT_TARGETS` membership, not on-disk existence, so the
release-time drift lint is the true missing-file guard — adequate, since a deleted pin file is a
structural breakage that surfaces at install/import time regardless.

**(d) test_finalize.py companion edit** — Correct. Updates the expected `update_item` call to
`{"status": "complete", "lifecycle_phase": "complete"}`, exactly matching the finalize.py change.
Asserts the full field dict (not a subset), so it is a real companion assertion, not self-sealing.

**Test execution genuineness** — The per-task Verification steps were genuinely run: every
378-authored test file is green, and the tests drive the REAL CLI entrypoints (`adv.main` over the
real subparser; the rewriter as a subprocess over real fixtures) rather than mocking the logic under
test. Back-compat (emission-only) and hazard (non-demotion) cases are both covered.

**Pattern consistency** — Per-key line-editor discipline preserved (`safe_dump` = 0); events-first
status ownership in advance.py preserved (status stays `_project_status`-projected); dual-source
mirror clean (`git diff plugins/cortex-core/` empty).

**Minor observation (non-blocking)** — `resolve_item.py:237`
(`_resolve_lifecycle_slug_frontmatter`) still gates on `isinstance(slug_val, str)`, so a raw numeric
int slug on disk would be skipped there rather than coerced. This is not a gap: it is tolerant (no
crash), the two crash paths req-3 names ARE coerced, and backfill + quote-on-write make all on-disk
slugs strings. Noted for completeness only.

**Full-suite note** — A monolithic `.venv/bin/pytest -q` run reports 32 failures, but `just test`
(the specced command) runs each suite in a SEPARATE process (justfile:528-532). Replicating that:
the dashboard suite is 157 passed / 0 failed in isolation, and `tests/` shows exactly the 4 known
pre-existing reds (`test_absent_glossary_literal_resolution` — concurrent untracked glossary.md;
`test_plugin_path_mismatch_exits_nonzero` — DNS/network; two `test_model_resolution_wiring`
writeback-prose reds). The extra monolithic-run failures are cross-suite test-ordering pollution
that `just test`'s process isolation avoids (they pass in isolation) — NOT 378 regressions. 378
touched no dashboard code. Every 378-authored test is green.

## Requirements Drift

**State**: detected

**Findings**:
- The implementation establishes a new load-bearing architectural contract — a single, key-scoped
  frontmatter-scalar write path (`cortex_command/backlog/frontmatter_quote.py`) that all frontmatter
  scalar writers must route through, carrying a standing maintenance obligation (the
  `STRING_INTENDED_KEYS` allowlist must be extended as new string-intended fields are added; flagged
  as a project Risk in plan.md). The spec proposes ADR-0027 (frontmatter-scalar-write-contract) to
  govern it, but `cortex/requirements/project.md` has no reference to this contract, whereas it
  enumerates comparable single-source contracts (e.g. "Backlog status vocabulary", "Install-state
  shared-constant contract"). ADR-0027 itself is not yet a committed file under `cortex/adr/`.

**Update needed**: cortex/requirements/project.md (contingent on ADR-0027 being committed)

## Suggested Requirements Update

**File**: cortex/requirements/project.md

**Section**: Architectural Constraints

**Content**:
```markdown
- **Frontmatter-scalar write contract**: Hand-rolled backlog/lifecycle frontmatter scalars are emitted through the single key-scoped quoter `cortex_command/backlog/frontmatter_quote.py` (`STRING_INTENDED_KEYS` allowlist; None sentinel and dates stay bare). A new string-intended, numeric-looking field left off the allowlist re-exposes the type-leak; `tests/test_lifecycle_references_resolve.py` (CI-wired) is the backstop. → ADR-0027.
```

(Land the `→ ADR-0027` back-pointer only once `cortex/adr/0027-frontmatter-scalar-write-contract.md`
is committed; the spec currently carries it as a Proposed ADR.)

## Verdict

{"verdict": "APPROVED", "cycle": 1, "issues": ["req-9 satisfied via re-scoped test-based guard (test_lifecycle_event_roundtrip.py), not the literal bin/cortex-check-absorbed-verbs scanner + just recipe named in the spec — intent (prevent legacy-verb re-introduction) is met; recorded as an accepted plan-time re-scope, non-blocking", "requirements drift detected: new frontmatter-scalar write contract (ADR-0027, proposed) is not referenced in project.md — observation only, does not affect the verdict"], "requirements_drift": "detected"}
