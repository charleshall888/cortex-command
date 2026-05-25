# Plan: make-cortex-update-item-accept-flag

## Overview

Rewrite `cortex_command/backlog/update_item.py`'s CLI parsing layer from manual `sys.argv[2:]` `key=value` extraction to an `argparse.ArgumentParser` with per-key `--flag value` flags, add an argv pre-flight that intercepts the legacy form with an actionable migration hint, and atomically migrate every in-repo caller (skill prose, justfile, docs, tests). The internal `update_item(item_path, fields_dict, backlog_dir, session_id)` Python function signature stays unchanged — this is a CLI-surface refactor that thinly wraps the existing function. One deliberate behavior delta surfaces at the CLI/Python boundary: `--session-id` becomes an event-attribution parameter passed as the dedicated `session_id` positional rather than dumped into the fields dict (see Task 1 Context); this is a fix, not a regression, but consumers must be audited.

## Outline

### Phase 1: CLI argparse rewrite (tasks: 1, 2, 3, 4)
**Goal**: `cortex_command/backlog/update_item.py` exposes a `--flag value` argparse CLI with the argv pre-flight migration hint, and `tests/test_update_item_cli.py` covers it.
**Checkpoint**: `python3 -m pytest tests/test_update_item_cli.py -v` exits 0; `python3 -m cortex_command.backlog.update_item --help` lists per-key flags and exits 0; `python3 -m cortex_command.backlog.update_item 257 status=complete` exits 2 with migration hint on stderr.

### Phase 2: Caller migration & verification (tasks: 5, 6, 7, 8, 9, 10, 11, 12)
**Goal**: every in-repo `cortex-update-item key=value` invocation migrated to `--flag value`; plugin mirrors regenerated; wheel reinstalled; full test + parity audit green.
**Checkpoint**: `grep -rnE '^[[:space:]]*cortex-update-item[^|]*[ "'\''][a-z_][a-z_-]*=' skills/ docs/ justfile tests/ bin/ hooks/ claude/ plugins/ 2>/dev/null` returns zero matches. The `^[[:space:]]*` anchor restricts matching to line-start invocations (executable code in code-fences and shell scripts), which excludes (a) the migration hint string in `cortex_command/backlog/update_item.py` (mid-line inside a print), (b) HTML attributes in `docs/index.html` (mid-line), and (c) test docstrings referencing the legacy form (mid-line). `cortex_command/` is omitted from the grep scope because the only file there that legitimately contains the legacy example string is the one being changed (the hint message). `python3 -m pytest` exits 0; `cortex-check-parity --audit` exits 0; `cortex-update-item --help` (binstub) lists per-key flags.

## Tasks

### Task 1: Rewrite update_item.py main() with argparse
- **Files**: `cortex_command/backlog/update_item.py`, `cortex_command/overnight/outcome_router.py`, `cortex_command/refine.py`
- **What**: Replace the manual `sys.argv[2:]` `key=value` parsing loop in `main()` (lines 433-471) with an `argparse.ArgumentParser` using per-key scalar flags and `nargs='*'` list flags. Preserve the existing `null`/`none`/`""` → Python `None` coercion for scalar values only. Internal `update_item(item_path, fields_dict, backlog_dir, session_id)` function signature is unchanged, but the call shape from `main()` changes: `--session-id` becomes a separate positional/kwarg passed to `update_item(... session_id=...)`, NOT a member of `fields_dict`. **Audit** `cortex_command/overnight/outcome_router.py:320,321,416` and `cortex_command/refine.py` for any consumer that previously inspected `session_id` as a frontmatter field — confirm none do (the existing internal callers already pass `session_id` positionally; the legacy `key=value` CLI was the only path that smuggled it via the fields dict).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Existing entry point at `cortex_command/backlog/update_item.py:433` (`def main():`). The current parsing reads `sys.argv[1]` (slug) and `sys.argv[2:]` (variadic `key=value` pairs split on `=`). Replace with:
  - `parser = argparse.ArgumentParser(prog="cortex-update-item", allow_abbrev=False)`
  - Positional argument: `parser.add_argument("slug")` (the slug-or-UUID)
  - Scalar flags (all `default=None`, optional, NO `choices=` — status values are open-ended across `backlog`, `refined`, `in_progress`, terminal statuses, etc., and centralizing the allowed set is out of scope for this work): `--status`, `--priority`, `--type` (dest=`item_type`), `--complexity`, `--criticality`, `--spec`, `--lifecycle-slug` (dest=`lifecycle_slug`), `--lifecycle-phase` (dest=`lifecycle_phase`), `--session-id` (dest=`session_id`), `--parent`, `--blocked-by` (dest=`blocked_by`), `--rework-of` (dest=`rework_of`)
  - List flags (`nargs='*'`, `default=None`): `--areas`, `--tags`
  - After parsing, collect non-None namespace attributes EXCEPT `session_id` into a `fields_dict`. Pull `session_id` out as a separate variable. For scalar fields where the string is `"null"`, `"none"`, or `""`, coerce to Python `None`. For list values, pass through literally (no per-element coercion).
  - Call `update_item(item_path, fields_dict, BACKLOG_DIR, session_id=session_id)` with the resolved item path. The keyword-argument form documents the boundary; the function signature accepts session_id positionally too.
  - Sibling pattern reference: `cortex_command/backlog/create_item.py:151-163` for argparse setup style.
  - Keep `_telemetry.log_invocation("cortex-update-item")` at its existing call site (line 434, before the parsing loop).
- **Verification**: `python3 -m cortex_command.backlog.update_item --help` exits 0 and stdout contains the literal substring `--status` and `--areas`. Run from repo root (uses working-tree code).
- **Status**: [x] complete

### Task 2: Add argv pre-flight migration hint to update_item.py
- **Files**: `cortex_command/backlog/update_item.py`
- **What**: Add a `_argv_preflight(argv)` helper that scans `argv[1:]` (skipping program name; positional order is not assumed) for any token matching `^[a-z_][a-z_]*=` — an unquoted underscore-or-letter prefix immediately followed by `=`. On match, print `Detected legacy positional argument '<arg>'. The CLI now requires --<key> <value>. See 'cortex-update-item --help' for the full flag list.` to stderr and call `sys.exit(2)`. The first-char anchor `[a-z_]` (no leading `-`) prevents false-firing on `--status=complete` (argparse's equals form). Call `_argv_preflight(sys.argv)` at the very top of `main()`, before argparse runs.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The helper is ~12 lines. Use `re.compile(r'^[a-z_][a-z_]*=')` for the regex. The function accepts argv as a parameter (not reading `sys.argv` directly) so the test file can call it with controlled inputs. `sys.exit(2)` raises `SystemExit` which `pytest.raises(SystemExit)` catches.
  - **Known limitation (documented, not fixed)**: the pre-flight false-fires on legitimate flag values that happen to contain a `key=value` shape (e.g., `--spec foo=bar` — `foo=bar` matches the regex). Operators currently never pass values containing `=` to scalar fields (verified: no in-repo caller does), so this is a theoretical concern. If it surfaces post-merge, address by tightening the pre-flight to skip tokens that follow a known scalar flag name. Documented here so the implementer doesn't try to over-engineer this in v1.
  - The migration hint message intentionally does NOT contain the literal phrase `key=value` adjacent to the literal phrase `cortex-update-item` — this is so the Phase 2 verification grep (anchored at `^[[:space:]]*cortex-update-item`) does not false-fire on the hint string. The hint says "Detected legacy positional argument '<arg>'" and "The CLI now requires --<key> <value>" instead.
- **Verification**: `python3 -m cortex_command.backlog.update_item 257 status=complete` exits with code 2 and stderr contains the literal substring `Detected legacy positional argument 'status=complete'`. Verify: `python3 -m cortex_command.backlog.update_item 257 status=complete 2>&1 >/dev/null | grep -c "Detected legacy positional argument" = 1`.
- **Status**: [x] complete

### Task 3: Update module docstring and remove legacy Usage string
- **Files**: `cortex_command/backlog/update_item.py`
- **What**: Update the module docstring at lines 9-14 (currently shows `Usage: cortex-update-item <slug-or-uuid> key=value [key=value ...]`) to reflect the new `--flag value` form (or replace with `See 'cortex-update-item --help' for the full flag list.`). Remove the legacy `Usage:` error string in `main()` that references positional `key=value` parsing.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: The docstring is at lines 9-14; the legacy `Usage:` error string is around line 437 (location may shift after Task 1's rewrite). The replacement docstring should briefly describe the CLI shape and reference `--help` for the full flag list. No new docstring content beyond what argparse's auto-help already provides.
- **Verification**: `grep -nE 'Usage: cortex-update-item.*<slug.*key=value' cortex_command/backlog/update_item.py` returns zero matches. The grep targets the OLD docstring template specifically (`<slug>` followed by `key=value`), not the literal substring `key=value` — which legitimately appears in Task 2's migration hint message ("Detected legacy positional argument" — wait, the new message doesn't contain `key=value` per the rewording in Task 2; but in any case the verification grep specifically targets the OLD docstring template shape).
- **Status**: [x] complete

### Task 4: Create tests/test_update_item_cli.py with ≥5 named test functions
- **Files**: `tests/test_update_item_cli.py`
- **What**: New test file covering: (a) scalar-flag parsing for representative flags (`--status`, `--lifecycle-phase`); (b) list-flag parsing including bare empty form (`--areas` alone → `[]`) and documented last-wins on duplicate (`--areas a b --areas c` → `['c']`); (c) `null`/`none`/`""` coercion for scalar fields (verify Python `None` reaches the fields dict); (d) `allow_abbrev=False` behavior (`--stat` raises `SystemExit`); (e) argv pre-flight hint for bare `key=value`; (f) argv pre-flight hint for bracket-list legacy form (`"areas=[a,b]"`); (g) argv pre-flight negative case (`--status=complete` does NOT raise); (h) automated subprocess integration test invoking `python3 -m cortex_command.backlog.update_item 257 status=complete`, asserting exit code 2 and stderr substring `Detected legacy positional argument`. Tests use pytest.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**: pytest's built-in `capsys` fixture captures stderr — see Python docs (`capsys.readouterr().err`). For subprocess-based tests, see `tests/test_backlog_worktree_routing.py` for subprocess and pytest.raises patterns (note: that file does not demonstrate `capsys`; `capsys` is a stock pytest fixture that needs no in-tree example). Use `pytest.raises(SystemExit)` to catch argparse exits and pre-flight exits. The subprocess integration test uses `subprocess.run(['python3', '-m', 'cortex_command.backlog.update_item', '257', 'status=complete'], capture_output=True, text=True, cwd=REPO_ROOT)`. Use slug `257` (it is the parent backlog of this lifecycle — it exists; the pre-flight fires before any backlog lookup, so the test passes regardless of whether the slug resolves). ≥5 named test functions (`grep -c "^def test_" tests/test_update_item_cli.py` ≥ 5). When writing test docstrings or comments, do NOT put the literal phrase `cortex-update-item` adjacent to a `key=value` example — use the module path form (`python3 -m cortex_command.backlog.update_item ... status=complete`) or quote the example separately. This keeps the test file out of the Phase 2 verification grep's match set.
- **Verification**: `python3 -m pytest tests/test_update_item_cli.py -v` exits 0; `grep -c "^def test_" tests/test_update_item_cli.py` returns a value ≥ 5.
- **Status**: [x] complete

### Task 5: Migrate skills/morning-review/ + skills/backlog/ skill prose
- **Files**: `skills/morning-review/SKILL.md`, `skills/morning-review/references/walkthrough.md`, `skills/backlog/SKILL.md`
- **What**: Replace every executable `cortex-update-item <slug> key=value [...]` invocation with `cortex-update-item <slug> --key value [...]` (space-separated form, NOT argparse equals form — the test fixture at `tests/test_morning_review_status_close_ordering.py:22` literal-matches the space form, see Task 9). Specific lines (per research.md): `skills/morning-review/SKILL.md:104`, `skills/morning-review/references/walkthrough.md:537`, `skills/backlog/SKILL.md:79,80`.
- **Depends on**: none (parallelizable with Tasks 6, 7, 8 in the implement-phase dispatch; runtime correctness depends on Task 1 shipping in the same PR, which is the spec's atomicity contract)
- **Complexity**: simple
- **Context**: Each invocation is a one-line Edit-tool call. Pattern: `cortex-update-item 078 status=complete` → `cortex-update-item 078 --status complete`. Use space form, not equals form (`--status=complete`).
- **Verification**: `grep -rnE '^[[:space:]]*cortex-update-item[^|]*[ "'\''][a-z_][a-z_-]*=' skills/morning-review/ skills/backlog/ 2>/dev/null` returns zero matches. Additionally: `grep -rnE '^[[:space:]]*cortex-update-item [0-9{][^ ]* --status=' skills/morning-review/ skills/backlog/ 2>/dev/null` returns zero matches (positive check: no argparse-equals form snuck in, preserving the space-form contract that Task 9's literal match depends on).
- **Status**: [x] complete

### Task 6: Migrate skills/lifecycle/ skill prose
- **Files**: `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/complete.md`, `skills/lifecycle/references/wontfix.md`, `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/backlog-writeback.md`
- **What**: Replace every executable `cortex-update-item` invocation with the `--flag value` form. Specific lines: `complete.md:203`, `wontfix.md:44`, `clarify.md:112`, `backlog-writeback.md:29,80,88`, plus `skills/lifecycle/SKILL.md:231` (the narrative reference `cortex-update-item status=wontfix`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Pattern examples from research.md:
  - `cortex-update-item <slug> status=complete session_id=null` → `cortex-update-item <slug> --status complete --session-id null`
  - `cortex-update-item {backlog-slug} status=wontfix lifecycle_phase=wontfix session_id=null` → `cortex-update-item {backlog-slug} --status wontfix --lifecycle-phase wontfix --session-id null`
  - `cortex-update-item {backlog-filename-slug} complexity={value} criticality={value}` → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`
  - `cortex-update-item <path> status=in_progress session_id=$LIFECYCLE_SESSION_ID lifecycle_phase=research` → `cortex-update-item <path> --status in_progress --session-id $LIFECYCLE_SESSION_ID --lifecycle-phase research`
  - `cortex-update-item <path> lifecycle_slug={lifecycle-slug}` → `cortex-update-item <path> --lifecycle-slug {lifecycle-slug}`
  - `skills/lifecycle/SKILL.md:231` is a narrative reference (not in a code fence) — rewrite to the new form for consistency.
- **Verification**: `grep -rnE '^[[:space:]]*cortex-update-item[^|]*[ "'\''][a-z_][a-z_-]*=' skills/lifecycle/ 2>/dev/null` returns zero matches.
- **Status**: [x] complete

### Task 7: Migrate skills/refine/SKILL.md including list-flag form
- **Files**: `skills/refine/SKILL.md`
- **What**: Replace `cortex-update-item` invocations at lines 84, 187, 191, 194. Lines 191 and 194 use the legacy bracket-list form (`"areas=[area1,area2]"` and `"areas=[]"`) which becomes the `nargs='*'` form. Also rewrite the in-file rationale at approximately line 196 — currently reads "split into two sequential `cortex-update-item` calls — do not combine them into one invocation to avoid argument-parsing ambiguity with list values." Argparse handles list values natively, so the cited rationale no longer applies. Either (a) delete the split-call recommendation entirely (the new CLI has no ambiguity to avoid), or (b) keep the split-call recommendation but rewrite the rationale to reference clarity-of-intent (e.g., "split into two calls for readability"). Recommended: (a) — delete the obsolete recommendation.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Specific transformations:
  - Line 84: `cortex-update-item {backlog-filename-slug} complexity={value} criticality={value}` → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`
  - Line 187: `cortex-update-item {backlog-filename-slug} status=refined spec=cortex/lifecycle/{lifecycle-slug}/spec.md` → `cortex-update-item {backlog-filename-slug} --status refined --spec cortex/lifecycle/{lifecycle-slug}/spec.md`
  - Line 191: `cortex-update-item {backlog-filename-slug} "areas=[area1,area2]"` → `cortex-update-item {backlog-filename-slug} --areas area1 area2`
  - Line 194: `cortex-update-item {backlog-filename-slug} "areas=[]"` → `cortex-update-item {backlog-filename-slug} --areas`
  - Around lines 194-196: update prose explaining the quoting (no longer needed) and the split-call recommendation (rationale no longer holds — either delete or rewrite per the **What** instruction above).
- **Verification**: `grep -rnE '^[[:space:]]*cortex-update-item[^|]*[ "'\''][a-z_][a-z_-]*=' skills/refine/ 2>/dev/null` returns zero matches. Additionally: `grep -nE 'argument-parsing ambiguity with list values' skills/refine/SKILL.md` returns zero matches (the obsolete rationale is removed).
- **Status**: [x] complete

### Task 8: Migrate justfile + docs/backlog.md
- **Files**: `justfile`, `docs/backlog.md`
- **What**: Update `justfile:131` (`cortex-update-item {{ feature }} status=complete` → `cortex-update-item {{ feature }} --status complete`) and migrate the worked `cortex-update-item key=value` examples in `docs/backlog.md`. **Distinguish two kinds of references in docs/backlog.md**: (a) worked examples showing how to invoke the CLI for a specific operation (e.g., "to mark complete, run `cortex-update-item 257 status=complete`") — these get the mechanical key=value → --key value rewrite; (b) abstract syntax-descriptions explaining the variadic shape (per research's note, line 166 currently reads `cortex-update-item <slug-or-uuid> key=value [key=value ...]`) — rewrite to show the NEW shape (`cortex-update-item <slug-or-uuid> [--flag value ...]`), not a mechanical substitution that loses the syntax-shape intent. Enumerate via `grep -nE 'cortex-update-item.*=' docs/backlog.md` first; classify each match as (a) or (b); migrate accordingly.
- **Depends on**: none
- **Complexity**: simple
- **Context**: docs/backlog.md examples are in code-fence blocks at approximate lines 104-197 (per research.md). The HTML file `docs/index.html` at line 6341 references `cortex-update-item` mid-line within HTML attributes — that's documentation, not an executable invocation, and the Phase 2 grep (anchored at `^[[:space:]]*`) does NOT match it. Leave docs/index.html alone.
- **Verification**: `grep -rnE '^[[:space:]]*cortex-update-item[^|]*[ "'\''][a-z_][a-z_-]*=' justfile docs/backlog.md 2>/dev/null` returns zero matches.
- **Status**: [x] complete

### Task 9: Migrate tests/test_morning_review_status_close_ordering.py CLOSE_ARG
- **Files**: `tests/test_morning_review_status_close_ordering.py`
- **What**: Change `CLOSE_ARG = "status=complete"` at line 22 to `CLOSE_ARG = "--status complete"` (matching the new prose form chosen for `skills/morning-review/SKILL.md:104` in Task 5 — space form, NOT argparse equals form). The assertion at line 74 (`assert CLOSE_ARG in close_line_text`) must continue to pass against the migrated skill prose. Also update any narrative `cortex-update-item status=complete` references in the test file's docstrings or comments (per research.md these exist at lines 3, 54, 59, 72, 129) so the test file is internally consistent. Use the module-path form (`python3 -m cortex_command.backlog.update_item ... --status complete`) in docstrings to keep the test file out of the Phase 2 grep's match set.
- **Depends on**: [5] (the skill prose in `skills/morning-review/SKILL.md` must already use `--status complete` for the assertion to pass)
- **Complexity**: simple
- **Context**: The test asserts a specific string appears in the migrated skill prose. The literal in the test must EXACTLY match the literal in the skill prose. Both must agree on the form `--status complete` (space-separated, not `--status=complete` equals form). Task 5's verification grep includes a positive check that the space form was used.
- **Verification**: `python3 -m pytest tests/test_morning_review_status_close_ordering.py -v` exits 0.
- **Status**: [x] complete

### Task 10: Run `just build-plugin` to regenerate plugin mirrors
- **Files**: `plugins/cortex-core/skills/`, `plugins/cortex-overnight/skills/` (regenerated by rsync, not hand-edited)
- **What**: Invoke `just build-plugin` to regenerate the mirrored skill prose under `plugins/cortex-core/skills/` and `plugins/cortex-overnight/skills/`. The `rsync -a --delete` invocation inside the recipe copies canonical `skills/` files into the mirror locations.
- **Depends on**: [5, 6, 7]
- **Complexity**: simple
- **Context**: The recipe lives in `justfile` at line 558 (recipe header `build-plugin:`); rsync invocations extend through approximately line 590. The pre-commit dual-source drift check fires on any commit where canonical and mirror copies diverge — `just build-plugin` is the only sanctioned way to align them. If the recipe fails, investigate and fix before proceeding; do NOT pass `--no-verify`.
- **Verification**: After `just build-plugin`, `git status` shows changes in `plugins/cortex-core/skills/` and `plugins/cortex-overnight/skills/` matching the canonical `skills/` edits; `grep -rnE '^[[:space:]]*cortex-update-item[^|]*[ "'\''][a-z_][a-z_-]*=' plugins/ 2>/dev/null` returns zero matches.
- **Status**: [x] complete

### Task 11: Reinstall wheel (recommended for end-to-end binstub verification)
- **Files**: none (no edits — this task runs install commands)
- **What**: Run `uv tool install --reinstall --refresh-package cortex-command .` from repo root to refresh the installed wheel with the new code. This is recommended (not strictly required) for end-to-end binstub-tier verification in Task 12. Alternatives per `cortex/requirements/project.md:38`: (a) invoke via `python3 -m cortex_command.backlog.update_item` (working tree, no reinstall needed — used throughout Tasks 1-4 and 13); (b) export `CORTEX_COMMAND_FORCE_SOURCE=1` in the environment to make the dual-channel binstub wrappers skip the wheel-import branch. The reinstall path is the canonical end-to-end check because it exercises the same wheel that ships to operators; the alternatives are valid for iteration but skip the wheel-build step.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Wheel reinstall takes ~15-30 seconds. After reinstall, the `cortex-update-item` binstub on PATH reflects the new argparse code. Prior art using the `python3 -m` alternative (which avoids reinstall): `cortex/lifecycle/remove-daytime-autonomous-pipeline-and-cancel/plan.md:199-231`. For this work, prefer the reinstall path because Task 12's binstub-tier verification is part of the acceptance contract.
- **Verification**: after reinstall, `cortex-update-item --help` (binstub on PATH) exits 0 and stdout contains the literal substring `--status` (proving the binstub reflects the new flags, not the old positional form).
- **Status**: [x] complete

### Task 12: Run final verification suite
- **Files**: none (verification commands only)
- **What**: Run the full verification suite: `python3 -m pytest` (full test suite), `cortex-check-parity --audit` (or `just`-recipe equivalent), and the Phase 2 checkpoint grep against all migration paths.
- **Depends on**: [4, 5, 6, 7, 8, 9, 10, 11]
- **Complexity**: simple
- **Context**: The full test suite includes `tests/test_update_item_cli.py` (Task 4), `tests/test_morning_review_status_close_ordering.py` (Task 9 indirectly), and the existing test suite (which exercises Python callers via the internal API, unaffected by CLI changes).
- **Verification**: `python3 -m pytest` exits 0; `cortex-check-parity --audit` exits 0; `grep -rnE '^[[:space:]]*cortex-update-item[^|]*[ "'\''][a-z_][a-z_-]*=' skills/ docs/ justfile tests/ bin/ hooks/ claude/ plugins/ 2>/dev/null` returns zero matches (Phase 2 checkpoint passes).
- **Status**: [x] complete

## Risks

- **Pre-flight regex over-trigger on values containing `=`** (Task 2 Context): theoretical, no current caller does this. If post-merge reports surface, tighten the pre-flight; in v1 leave as documented limitation.
- **`--session-id` becomes event-attribution-only, not a frontmatter field**: Task 1 audits Python callers; if any non-CLI consumer depended on the frontmatter side-effect (none found), they must be updated. Surface this in the PR description so reviewers verify the audit.
- **Wheel-vs-working-tree mismatch during local iteration**: tasks 1-4 verify via `python3 -m` (working tree); task 11 reinstalls; task 12 verifies binstub-tier. The plan handles this cleanly but the implementer should not run `cortex-update-item` between tasks 1-3 without recognizing it's reading the OLD wheel.
- **Ticket 254 collision**: ticket 254 modifies `_find_item` in the same file. Coordination is a footnote: 257 first (this work) is recommended; if 254 lands first the rebase is non-overlapping with `main()`.
- **Plugin mirror regeneration trust**: task 10 invokes `just build-plugin` explicitly. The pre-commit dual-source drift check is a defense-in-depth backstop.

## Acceptance

Every executable `cortex-update-item key=value` invocation across `skills/`, `docs/`, `justfile`, `tests/`, `bin/`, `hooks/`, `claude/`, and `plugins/` is migrated to the `--flag value` form (verified by zero-match grep at Task 12). The argparse-rewritten CLI exposes per-key flags via `cortex-update-item --help` (binstub on PATH, post-reinstall, Task 11). The argv pre-flight migration hint fires on legacy `key=value` invocations with the documented stderr message and exit code 2, verified both at source level (`python3 -m cortex_command.backlog.update_item`, Task 4's subprocess integration test) and binstub level (`cortex-update-item`, Task 11). Full test suite (`python3 -m pytest`) and parity audit (`cortex-check-parity --audit`) both exit 0 (Task 12). The Python internal API `update_item(item_path, fields_dict, backlog_dir, session_id)` signature is unchanged; `--session-id` moves from frontmatter-field semantics to event-attribution semantics at the CLI boundary (Task 1, deliberate behavior fix).
