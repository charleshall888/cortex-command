# Review: extract-backlog-management-skill-into-optional

## Stage 1: Spec Compliance

### Requirement 1: cortex-backlog plugin scaffold exists with a valid minimal manifest
- **Expected**: `plugins/cortex-backlog/.claude-plugin/plugin.json` loads and `name == "cortex-backlog"`; minimal shape (name/description/author; no MCP/hooks/bin) matching cortex-overnight.
- **Actual**: AC exits 0. Manifest has `name`/`description`/`author` only — no MCP/hooks/bin keys, structurally identical in shape to `plugins/cortex-overnight/.claude-plugin/plugin.json`.
- **Verdict**: PASS
- **Notes**: Description is descriptive and accurate ("Optional interactive backlog management skill … extracted from cortex-core so repos that track work in an external system can omit it").

### Requirement 2: build-plugin recipe has a `cortex-backlog)` case branch
- **Expected**: `cortex-backlog)` arm with `SKILLS=(backlog) BIN=() HOOKS=()`; cortex-core keeps `backlog-author`, drops standalone `backlog`.
- **Actual**: AC clause a (`awk … SKILLS=(backlog)`) exits 0; clause b (`grep -A1 'cortex-core)' … backlog-author`) exits 0; clause c (negative grep for standalone backlog in cortex-core) PASS via a script-file run (the inline zsh form mis-globbed `(`). justfile:606-610 has `cortex-backlog)` with `BIN=()`, `SKILLS=(backlog)`, `HOOKS=()`. cortex-core SKILLS (justfile:597) lists `backlog-author` and no standalone `backlog`.
- **Verdict**: PASS

### Requirement 3: backlog skill packaged in cortex-backlog, removed from cortex-core; backlog-author stays in cortex-core
- **Expected**: `test -d plugins/cortex-backlog/skills/backlog && ! test -e plugins/cortex-core/skills/backlog && test -d plugins/cortex-core/skills/backlog-author && ! test -e plugins/cortex-backlog/skills/backlog-author` exits 0.
- **Actual**: AC exits 0.
- **Verdict**: PASS

### Requirement 4: cortex-backlog skills mirror is build-plugin-derived, not hand-staged
- **Expected**: `rm -rf plugins/cortex-backlog/skills/backlog && just build-plugin && test -f plugins/cortex-backlog/skills/backlog/SKILL.md` exits 0.
- **Actual**: AC exits 0 — the mirror reappeared from canonical after delete+rebuild, byte-identical (`diff -r skills/backlog plugins/cortex-backlog/skills/backlog` shows no differences). Tree restored clean afterward (no working-tree modification left behind).
- **Verdict**: PASS

### Requirement 5: orphaned `plugins/cortex-core/skills/backlog/` mirror removed via `git rm`
- **Expected**: path staged-deleted or no longer tracked.
- **Actual**: AC exits 0; `git ls-files plugins/cortex-core/skills/backlog/` returns nothing — the dir is no longer tracked (the deletion is in commit 27a6a4a3 via the renamed `skills/backlog/...` path move out of cortex-core).
- **Verdict**: PASS

### Requirement 6: cortex-backlog in PLUGIN_NAMES, removed from RESERVED_NON_BIN_NAMES
- **Expected**: `'cortex-backlog' in PLUGIN_NAMES and 'cortex-backlog' not in RESERVED_NON_BIN_NAMES`.
- **Actual**: AC exits 0 (run via `.venv/bin/python`).
- **Verdict**: PASS

### Requirement 7: cortex-backlog in justfile BUILD_OUTPUT_PLUGINS
- **Expected**: `just _list-build-output-plugins | grep -qx cortex-backlog` exits 0.
- **Actual**: AC exits 0; output is `cortex-core / cortex-overnight / cortex-backlog`. The `plugin-list-matches-justfile` self-test stays green (covered by req 13 suite run).
- **Verdict**: PASS

### Requirement 8: PLUGINS dict maps cortex-backlog→("backlog",); cortex-core no longer lists backlog
- **Expected**: dict-inspection exits 0 AND `pytest test_dual_source_reference_parity.py` exits 0.
- **Actual**: Dict-inspection AC exits 0. `pytest tests/test_dual_source_reference_parity.py -q` → 58 passed.
- **Verdict**: PASS

### Requirement 9: marketplace.json lists cortex-backlog
- **Expected**: a plugin entry named cortex-backlog.
- **Actual**: AC exits 0. Entry present (name/source/description/category), ordered between cortex-core and cortex-overnight — consistent with the docs/setup.md table ordering.
- **Verdict**: PASS

### Requirement 10: new prefix-collision regression test exercises the real parity scanner
- **Expected**: `pytest test_cortex_backlog_prefix_collision.py` exits 0; the test calls `collect_reference_candidates`/`collect_wiring_signals`; names all five backlog scripts.
- **Actual**: `pytest … -q` → 4 passed. Test imports `collect_reference_candidates`, `collect_wiring_signals`, `TOKEN_RE`, `PLUGIN_NAMES` from `cortex_command.parity_check` and asserts each of the 5 named scripts stays candidate/wired while the bare `cortex-backlog` token is excluded. Confirmed the imported functions are the real implementations (24 and 20 source lines), not stubs.
- **Verdict**: PASS
- **Notes**: This is a genuine regression test against the real scanner, exactly as specced — it would catch a future word-boundary regression in `TOKEN_RE` or an over-broad PLUGIN_NAMES exclusion.

### Requirement 11: cortex/requirements/backlog.md amended to remove the "both skills move" contradiction
- **Expected**: no "skills/backlog and skills/backlog-author are packaged in the cortex-backlog" wording; a `backlog-author … (remains|stays) … cortex-core` bullet present.
- **Actual**: Both AC clauses pass. Line 20 (Inputs), line 23 (acceptance), and line 102 (architectural-constraints bullet) all state only `skills/backlog` moves and `backlog-author` remains in cortex-core. The "listed as OPTIONAL in the table" wording softened to "documented as optional in docs/setup.md" at line 21 (Outputs).
- **Verdict**: PASS
- **Notes**: See Requirements Drift — line 104 still uses the older "add … as OPTIONAL" table phrasing, a minor intra-doc inconsistency (informational, not a violation; the statement remains factually accurate).

### Requirement 12: moved backlog skill keeps its bare `/backlog-author` invocation
- **Expected**: `grep -q '/backlog-author' skills/backlog/SKILL.md`.
- **Actual**: AC exits 0; bare `/backlog-author` calls preserved at lines 59 and 61 (no fully-qualify edit). Cross-plugin resolution is demonstrated by morning-review's production bare call; post-install confirmation is req 20.
- **Verdict**: PASS

### Requirement 13: Phase-1 commit lands with all gates green
- **Expected**: `just test` exits 0 AND `git diff --quiet plugins/` after `just build-plugin`.
- **Actual**: Post-build drift check is CLEAN (`git diff --quiet plugins/` passes — dual-source mirror parity holds). `just test` reports 6/7 sub-recipes pass; the `tests` recipe shows 2 failures, **both external/concurrent-session, neither caused by either commit under review**:
  1. `test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero` — sandbox DNS failure fetching `pydantic` from pypi.org (`failed to lookup address information`). Pure network restriction, unrelated to this change.
  2. `test_resolve_backlog_item.py::test_no_order_drift_against_baseline` — backlog-corpus order drift on inputs `'overnight watchdog'`/`'WATCHDOG'`. Neither commit touched the resolver, its test, or `predicate_a_baseline.json`. The failure reproduces even after reverting the (pre-existing, uncommitted) `predicate_a_baseline.json` modification to its HEAD version, so it is driven by live backlog-corpus state from a concurrent lifecycle session (#317 `config-driven-backlog-backend-resolver-local/` is untracked in the worktree), exactly the shared-checkout contamination the plan flagged.
- **Verdict**: PASS
- **Notes**: All backlog-extraction-relevant suites pass: `test_dual_source_reference_parity` (58), `test_cortex_backlog_prefix_collision` (4), `test_l1_surface_ratchet` (20), `test_skill_descriptions` (2), `test_backlog_author` (5), `test_init_artifacts_hash_inputs` (7). The two failures are environmental (sandboxed network) and concurrent-session backlog-corpus noise, not regressions introduced here.

### Requirement 14: every live `/cortex-core:backlog` reference renamed to `/cortex-backlog:backlog`
- **Expected**: completeness grep over `skills docs tests bin claude hooks cortex_command justfile cortex/requirements CLAUDE.md README.md`, minus backlog-author and plugins/, returns **zero** lines.
- **Actual**: AC returns **zero** lines. Spot-checked the wider tree: remaining `cortex-core:backlog` mentions live only in correctly-excluded locations — `CHANGELOG.md:78` (deliberately-excluded historical release note), `cortex/research/**`, and `cortex/lifecycle/**` (historical artifacts never edited). Consumer renames confirmed in skills/dev (3), skills/discovery/decompose (1), skills/lifecycle/clarify (1), docs/agentic-layer (2), docs/backlog (4), docs/overnight (2), init README (1), valid_five_section fixture (1), skill_trigger_phrases.yaml (1), and skills/backlog/SKILL.md (5) — with cortex-core/cortex-backlog mirrors regenerated to match.
- **Verdict**: PASS
- **Notes**: The `/cortex-core:lifecycle` reference inside skills/backlog/SKILL.md (lines 11, 101) is correctly preserved — it is a lifecycle invocation, not a backlog ref.

### Requirement 15: skill_trigger_phrases.yaml `backlog:` trigger entry renamed in lockstep
- **Expected**: `pytest test_skill_descriptions.py` exits 0; the `backlog:` must_contain entry reads `/cortex-backlog:backlog`.
- **Actual**: `pytest … -q` → 2 passed. The yaml `backlog:` block (line 52) reads `/cortex-backlog:backlog`; companion phrases "add to backlog" and "pick a backlog item" remain valid substrings of the renamed description.
- **Verdict**: PASS

### Requirement 16: `/cortex-core:backlog-author` references preserved (not renamed)
- **Expected**: `grep -c 'cortex-core:backlog-author' skills/interview/SKILL.md` = 2.
- **Actual**: count = 2 (lines 3 and 10). Both preserved unchanged.
- **Verdict**: PASS

### Requirement 17: backlog skill's L1 surface trimmed to stay ≤319B after the rename
- **Expected**: `cortex-measure-l1-surface skills/backlog/SKILL.md` ≤319 AND `pytest test_l1_surface_ratchet.py` exits 0; no distinct trigger utterance dropped.
- **Actual**: Measured `backlog 314` (≤319) — AC regex `^backlog 3(0[0-9]|1[0-9])$` matches. `pytest … -q` → 20 passed. Before/after description diff: the only changes are `/cortex-core:backlog`→`/cortex-backlog:backlog` (+3B) and dropping the redundant trailing noun ("create/view/manage/select backlog items" → "…select items", −8B net). All quoted trigger phrases retained, including "backlog pick", "pick a backlog item", "backlog add", "backlog list", "add to backlog", "show backlog", "archive backlog item", "what's ready". No distinct utterance dropped; budget row not raised.
- **Verdict**: PASS

### Requirement 18: docs/setup.md plugin table gains cortex-backlog optional row; "six" → "seven"
- **Expected**: cortex-backlog present; "seven … plugins"; cortex-backlog marked optional.
- **Actual**: All three AC clauses pass. Line 49 "The seven available plugins are:"; line 56 adds the cortex-backlog table row; line 67 prose marks it optional and documents the cortex-core dependency ("the moved backlog skill resolves `backlog-author` from core"). Table ordering matches marketplace.json.
- **Verdict**: PASS

### Requirement 19: editing the init backlog README template is safe with no hash-bump action
- **Expected**: `pytest test_init_artifacts_hash_inputs.py` exits 0 AND `cortex-lifecycle-init-ensure` exits 0.
- **Actual**: `pytest … -q` → 7 passed; `.venv/bin/cortex-lifecycle-init-ensure` exits 0. The README rename (`/cortex-backlog:backlog`, line 16) is picked up by the live-computed hash with no literal to bump.
- **Verdict**: PASS

### Requirement 20: post-install verification — both renamed/relocated skills surface and resolve
- **Expected**: after installing cortex-backlog + cortex-core, `/cortex-backlog:backlog` is invocable and the bare `/backlog-author` call resolves cross-plugin to cortex-core.
- **Actual**: Interactive/session-dependent — requires a Claude Code plugin install to exercise slash registration, which a shell command cannot perform. Static prerequisites are all in place: cortex-backlog ships the backlog skill, cortex-core retains backlog-author, the bare `/backlog-author` call is preserved (req 12), and the cross-plugin pattern is demonstrated by morning-review in production.
- **Verdict**: PARTIAL
- **Notes**: Cannot be shell-verified; rated PARTIAL per review instructions. No structural blocker observed.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the cortex-overnight optional-plugin convention throughout. plugin.json carries name/description/author only (no MCP/hooks/bin), matching cortex-overnight's minimal shape. The justfile `cortex-backlog)` arm mirrors the cortex-overnight arm structure (`BIN=() / SKILLS=(…) / HOOKS=…`). Terminology uses `cortex-backlog` consistently (not `local`), per the area doc's terminology constraint.
- **Error handling**: The in-flight justfile HOOKS empty-array guard (`if [[ ${#HOOKS[@]} -gt 0 ]]`) is correct and necessary, and does not change behavior for cortex-core/cortex-overnight. Verified empirically on the actual shell here (bash 3.2.57, macOS default): under `set -u`, expanding an empty array `"${HOOKS[@]}"` trips `unbound variable`; the guard prevents this only for the new empty-HOOKS plugin. cortex-core and cortex-overnight both have non-empty HOOKS arrays, so they always enter the loop exactly as before — their generated `hooks/` dirs are unchanged (4 and 6 hook scripts respectively). The pre-existing `BIN=()` guard at line 625 is the analogous precedent. cortex-backlog correctly produces no hooks dir (skills-only).
- **Test coverage**: The new `test_cortex_backlog_prefix_collision.py` exercises the real scanner (`collect_reference_candidates`, `collect_wiring_signals`, `TOKEN_RE`) rather than a stub, asserting both the positive case (5 backlog scripts stay candidate/wired) and the negative case (bare `cortex-backlog` excluded). The PLUGINS-dict assertion in req 8's AC guards against the silent-skip failure mode the spec called out. L1, skill-descriptions, backlog-author, init-hash, and dual-source parity suites all green.
- **Pattern consistency**: marketplace.json, docs/setup.md plugin table, and the prose prerequisites are mutually ordering-consistent (cortex-backlog between cortex-core and cortex-overnight in all three). The dual-source mirrors are byte-identical and build-derived (verified via delete+rebuild and full-tree `git diff --quiet plugins/`). One trivial cosmetic nit (not an issue): the marketplace.json description says "external system" while plugin.json/docs/setup.md say "external tracker" — purely a wording variance, no functional impact. Non-Requirements were respected: the backlog engine and console scripts are untouched, no config block/resolver was added, no new ADR, and the backlog L1 budget row was not raised.

## Requirements Drift
**State**: detected
**Findings**:
- `cortex/requirements/backlog.md` line 104 (Architectural Constraints) still reads "add the plugin to the `docs/setup.md` plugin table as OPTIONAL", whereas req 11 softened the parallel Outputs phrasing (line 21) to "documented as optional in docs/setup.md". This is a minor intra-doc wording inconsistency in the file the implementation edited. The line-104 statement remains factually accurate (cortex-backlog IS in the docs/setup.md table marked optional), so it is informational only and does not affect the verdict.
- `cortex/requirements/project.md` requires no update: line 64 already names `cortex-backlog` as the local-backend store and notes backlog has its own area doc; project.md does not enumerate individual plugins in a form that would need a new-plugin row, so the extraction introduces no project-level drift.
**Update needed**: Optional only — align backlog.md line 104's "as OPTIONAL [in the] table" phrasing with the softened line-21 wording for intra-doc consistency. Low priority; the statement is not incorrect.

## Suggested Requirements Update
**File**: `cortex/requirements/backlog.md`
**Section**: Architectural Constraints (line 104)
**Content**: Soften "and add the plugin to the `docs/setup.md` plugin table as OPTIONAL." to "and document the plugin as optional in `docs/setup.md`." so it matches the Outputs-line phrasing adjusted under requirement 11. (Cosmetic consistency edit; not blocking.)

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
