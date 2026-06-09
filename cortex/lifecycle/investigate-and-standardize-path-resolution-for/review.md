# Review: investigate-and-standardize-path-resolution-for

## Stage 1: Spec Compliance

### Requirement 1: pr-review evidence-grounding runs; missing/failed script fails loud and distinct
- **Expected**: Replace `${CLAUDE_SKILL_DIR:-$TMPDIR}/scripts/evidence-ground.sh` with a body-propagated absolute path; keep `2>/dev/null`; add an explicit pre-invocation existence check emitting a distinct surfaced error (not the empty-stdout→synthesis-failure path). Acceptance: raw-form grep = 0, new check grep ≥ 1, `2>/dev/null` grep ≥ 1; behavioral check pipes valid payload through `evidence-ground.sh` → exit 0 + non-empty `{"grounded":…}` JSON.
- **Actual**: `protocol.md` Stage 3.5 now uses `<skill-dir>/scripts/evidence-ground.sh` (body-propagated absolute path) with a pre-invocation guard `[ -f "<skill-dir>/scripts/evidence-ground.sh" ] || { echo "GROUNDING_SCRIPT_MISSING"; exit 0; }` emitting a distinct **stdout** sentinel. `2>/dev/null` retained on the pipeline (count 3). Failure-handling block (548–557) documents three separate branches: script-absent (distinct sentinel, loud halt) vs empty-stdout (synthesis-failure fallback) vs zero-grounded (normal). Greps: raw form = 0, `GROUNDING_SCRIPT_MISSING` = 4, `2>/dev/null` = 3. Behavioral: payload → exit 0, emits non-empty `{"grounded":…}` JSON; absent-script guard prints `GROUNDING_SCRIPT_MISSING` on stdout (exit 0).
- **Verdict**: PASS
- **Notes**: The sentinel is on stdout (the channel `2>/dev/null` does not suppress), provably distinct from the empty-stdout→synthesis-failure route — exactly the loud+distinct property the spec headlines.

### Requirement 2: pr-review SKILL.md body establishes the skill-dir constant; Stage-4 prompt receives inlined content, not consult-pointers
- **Expected**: Body states skill dir is `${CLAUDE_SKILL_DIR}` and instructs Read+inline of rubric/output-format into the Stage-4 prompt; inside the BEGIN/END prompt block, `rubric.md`/`output-format.md`/`CLAUDE_SKILL_DIR` all = 0. Body has an explicit Read-and-inline instruction.
- **Actual**: SKILL.md body (lines 46–69) states the skill dir is `${CLAUDE_SKILL_DIR}` and adds a "Two propagation steps the body owns" section: Read rubric.md + output-format.md and inline at dispatch; propagate the absolute skill-dir path into Stage 3.5. The BEGIN/END block uses `{rubric}` / `{output_format}` placeholders. Scoped greps inside the block: `rubric.md` = 0, `output-format.md` = 0, `CLAUDE_SKILL_DIR` = 0. Body `inline` grep = 4.
- **Verdict**: PASS

### Requirement 3: critical-review synthesizer-prompt raw token removed
- **Expected**: `skills/critical-review/references/synthesizer-prompt.md` no longer embeds raw `${CLAUDE_SKILL_DIR}/references/a-to-b-downgrade-rubric.md`; rubric body-propagated via a `{a_to_b_rubric}` placeholder; mirror regenerated. Acceptance: `grep -c 'CLAUDE_SKILL_DIR'` = 0.
- **Actual**: The raw literal is replaced with a `{a_to_b_rubric}` placeholder (line 37, inlined under "### A→B downgrade rubric"); the header prose documents that the body Reads the rubric file and inlines its content. `grep -c 'CLAUDE_SKILL_DIR'` = 0. Mirror byte-identical to canonical (`diff -q` clean).
- **Verdict**: PASS

### Requirement 4: diagnose phase-1 raw token removed
- **Expected**: `skills/diagnose/references/phase-1-investigation.md` no longer references `${CLAUDE_SKILL_DIR}/references/techniques.md` as an unresolvable literal; replaced with a context-appropriate form; mirror regenerated. Acceptance: `grep -c 'CLAUDE_SKILL_DIR'` = 0.
- **Actual**: Line 49 now reads "Apply the Backward Root-Cause Tracing technique." with the inline "Quick version" at line 51; the unresolvable token is gone. `grep -c 'CLAUDE_SKILL_DIR'` = 0. Mirror byte-identical to canonical.
- **Verdict**: PASS

### Requirement 5: Class-2/3 bare-relative skill-load paths converted (independent per-site greps)
- **Expected**: Each Read/execute site converted to a body-propagated robust form; per-file pre-fix-form greps = 0. Files: research, refine, discovery (clarify/research), lifecycle (clarify/implement), android r8/cli. Plus the mid-implement Task-5e sites (backlog-author, interview, lifecycle SKILL:142, lifecycle clarify/review/specify).
- **Actual**: All per-site greps for the true pre-fix bare forms return 0 (research fanout href, refine clarify/load-requirements, lifecycle implement `cat|bash`, android r8/cli hrefs all = 0). The discovery reference greps initially appeared as 1, but `grep -F` confirms the bare `../../lifecycle/...` form is gone (count 0) and the matches are the body-propagated `${CLAUDE_SKILL_DIR}/../lifecycle/...` citation form (the regex-non-`-F` count was a `.`-wildcard artifact). Discovery body propagates the sibling path (`CLAUDE_SKILL_DIR}/../lifecycle` count 3). Reference files (clarify.md:15,56; research.md:41) correctly route through the body-established absolute path rather than a bare relative path. Helper `_interactive_overnight_check.sh` still present. Real-tree lint `--audit` exits 0 (zero SP002 across the whole tree), independently confirming no bare-relative Read/execute site remains.
- **Verdict**: PASS
- **Notes**: Spec-critical point 3 (reference-file fixes route through a body-propagated absolute path) verified directly in discovery clarify.md/research.md prose.

### Requirement 6: Structural lint enforces the invariant — context-scoped, precise D2 exemption
- **Expected**: New `cortex-check-*` console script + `cortex_command/lint/` module with D1 (raw token / bare `*.md` consult-ref inside a prompt fence or `*-prompt.md`) and D2 (bare-relative `references/…`/`../…`/`skills/…` in a Read/execute context, EXEMPTING `${CLAUDE_SKILL_DIR}/`-prefixed segments). Ignore-sentinel. Fixtures = literal pre-fix forms; positives flag non-zero, post-fix tree clean, false-positives (correct body token, `${CLAUDE_SKILL_DIR}/../` Read form, "do not load", `:-$TMPDIR`) pass. `just test` exits 0.
- **Actual**: `cortex_command/lint/skill_path.py` implements D1 (SP001) and D2 (SP002) mirroring `bare_python_import.py` (sentinel, `Violation` dataclass with `format_text`/`format_json_dict`, `scan_text`, `discover_files`/`run_audit`/`run_staged_gate`, argparse `--staged`/`--audit`, `main`). The D2 exemption is PRECISE: `_d2_exempt` matches `${CLAUDE_SKILL_DIR}/(../)*` only when it immediately precedes the captured path (anchored `$` lookback on `line[:match_start]`), NOT "any line mentioning the token" — the dedicated test `test_d2_exemption_is_precise_not_line_wide` proves a bare `../` still flags when the token appears elsewhere on the line. Fixtures carry the literal pre-fix production forms (positive.md) and the four false-positive cases (negative.md) including `Read ${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md`. `tests/test_check_skill_path.py` passes (positive ≥1 with both SP001 and SP002; negative = 0). Real-tree `--audit` exits 0.
- **Verdict**: PASS
- **Notes**: Spec-critical point 2 verified: the D2 exemption does not broaden to "any line mentioning `${CLAUDE_SKILL_DIR}`", and the `Read ${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` false-positive fixture passes (grep -F confirms it is present verbatim in negative.md).

### Requirement 7: Authoring convention in CLAUDE.md (positive-routing, mechanically checked)
- **Expected**: 2–4 sentence principle stating the invariant, pointing at the lint and ADR-0009. `grep -c 'CLAUDE_SKILL_DIR'` ≥ 1 AND no new `MUST`/`REQUIRED`/`CRITICAL` in the added hunk.
- **Actual**: New section "## Design principle: resolve `${CLAUDE_SKILL_DIR}` in the body, then propagate" added; soft positive-routing tone; points at `cortex-check-skill-path` and `cortex/adr/0009-…`. `grep -c 'CLAUDE_SKILL_DIR' CLAUDE.md` = 2. Added-hunk `grep -cE 'MUST|REQUIRED|CRITICAL'` = 0.
- **Verdict**: PASS
- **Notes**: Spec-critical point 5 verified: no new escalation token introduced.

### Requirement 8: Canonical/mirror parity preserved
- **Expected**: cortex-core-family edits land in `skills/`; `plugins/cortex-core/` mirror regenerated and clean; `just test` exits 0.
- **Actual**: All checked mirrors (critical-review synthesizer-prompt, diagnose phase-1, discovery SKILL + clarify, lifecycle implement, research SKILL, refine SKILL, bin/cortex-check-skill-path) are byte-identical to their canonical sources (`diff -q` clean). `just test`: 1793 passed, 27 skipped, 1 xfailed, 1 failed — the single failure (`test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`) is a sandbox-network artifact (`uv run --script` cannot reach pypi.org to resolve PEP 723 deps; DNS error before the server guard runs). It passes with network access (re-run confirmed) and touches zero files changed by this implementation.
- **Verdict**: PASS
- **Notes**: Spec-critical point 6 verified: body-propagation edits present in both canonical and mirror.

### Requirement 9: ADR-0009 records the decision
- **Expected**: `cortex/adr/0009-*.md` exists with `status: proposed`; a "rejected alternatives" section names CLI and injection. Acceptance: `status: proposed` ≥ 1, `grep -ci 'rejected'` ≥ 1.
- **Actual**: `cortex/adr/0009-skill-path-resolution-for-plugin-distributed-skills.md` exists with `status: proposed` frontmatter; records body-propagation as chosen mechanism, the invariant, three-criteria gate clearance, and a "## Rejected alternatives" section naming pure-CLI for pr-review, load-time `!`-injection, and recreating a standalone `claude/reference/` doc. `status: proposed` = 1; `rejected` (case-insensitive) = 5.
- **Verdict**: PASS

## Requirements Drift
**State**: detected
**Findings**:
- The implementation adds a new structural authoring invariant and pre-commit lint (`cortex-check-skill-path` / SP001+SP002: body-propagation for `${CLAUDE_SKILL_DIR}`; no raw token or bare consult-ref in a subagent prompt; no bare-relative Read/execute path). This is the same class of enumerated structural constraint that `project.md` documents for the bare-Python prohibition (L201) at line 45 and the two-mode gate pattern at line 92, but `project.md` has no corresponding entry for the skill-path invariant. The convention now exists (CLAUDE.md principle + ADR-0009 + lint) without being reflected in the project requirements inventory.
**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: ## Constraints (alongside the "Bare-Python skill-invocation prohibition (L201)" entry)
**Content**:
```markdown
- **Skill-dir path-resolution invariant (SP001/SP002)**: `${CLAUDE_SKILL_DIR}` resolves only in a SKILL.md body; reference files, shells, and composed subagent prompts cannot resolve it, and bare relative paths resolve against CWD off-repo. Author skills so the owning body resolves the token and propagates the absolute path (own dir, or a sibling via `${CLAUDE_SKILL_DIR}/../<sibling>`) or inlines the content. Enforced at pre-commit by `cortex-check-skill-path` (D1: raw token / bare `*.md` consult-ref inside a subagent prompt; D2: bare-relative Read/execute path not carried by a `${CLAUDE_SKILL_DIR}/` prefix); rationale in ADR-0009. Suppress an intentional illustrative form with `<!-- skill-path-lint:ignore-next -->`.
```

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The lint module mirrors `cortex_command/lint/bare_python_import.py` (sentinel regex, frozen `Violation` dataclass with `format_text`/`format_json_dict`, `scan_text`/`discover_files`/`run_audit`/`run_staged_gate`/`main`, argparse `--staged`/`--audit`/`--root`/`--json`). Violation codes `SP001`/`SP002` follow the sibling `L201` lettered-code convention. The bin wrapper `cortex-check-skill-path` is structurally identical to `cortex-check-bare-python-import` after normalizing the module/name tokens (verified via normalized diff).
- **Error handling**: Sound. The bin wrapper's dual-channel fallback (force-source → wheel-probe → working-tree-pyproject → exit 2 with remediation) matches the sibling. The lint tolerates `OSError`/`UnicodeDecodeError` on read and `CalledProcessError`/`FileNotFoundError` on git subprocess calls. The pr-review absent-script guard emits a distinct non-empty stdout sentinel and halts, kept on a separate failure branch from empty-stdout and zero-findings — the load-bearing loud+distinct property.
- **Test coverage**: Strong. `tests/test_check_skill_path.py` (15 tests) covers fixture-based positive/negative, individual D1 (raw token + bare consult-ref in fence; whole-file `*-prompt.md`; body token NOT flagged), individual D2 (Read/cat|bash flags; owndir + sibling exemptions pass; precise-not-line-wide), "do not load" citation, `:-$TMPDIR`, and sentinel suppression (incl. across blank line). Fixtures are real pre-fix literals extracted from production files (positive.md header documents provenance), not strings reverse-engineered to pass a buggy detector. The plan's verification commands (lint `--audit`, parity, kept-pauses parity, size budget, behavioral `evidence-ground.sh`) all execute clean.
- **Pattern consistency**: Good. Body-propagation is applied uniformly across discovery/lifecycle/refine/research (body resolves own or sibling dir; reference files cite the body-established absolute path). Console-script wiring matches the sibling (pyproject `[project.scripts]` entry, justfile recipe, pre-commit trigger, `plugins/cortex-core/bin/` mirror). ADR back-pointed by CLAUDE.md rather than restating rationale, per the project's ADR convention.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
