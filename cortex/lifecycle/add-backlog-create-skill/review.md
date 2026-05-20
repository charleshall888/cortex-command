# Review: add-backlog-create-skill

## Stage 1: Spec Compliance

### Requirement 1: Shared body-authoring sub-skill exists with both subcommand sections populated
- **Expected**: `skills/backlog-author/SKILL.md` exists, has `name: backlog-author` frontmatter, and both `### interview` and `### compose` sections contain ≥10 lines of protocol prose (not stubs). File-presence and grep acceptance checks pass.
- **Actual**: File exists, frontmatter correct. The awk acceptance command in the spec (`awk '/^### interview/,/^### |^## /'`) produces only 1 line for each section because the start pattern (`^### interview`) also matches the end pattern (`^### `), causing immediate range closure. However, the actual section content is 23 lines for `interview` and 30 lines for `compose`, verified by direct Python extraction. The prose in both sections is substantive, not a stub.
- **Verdict**: PASS
- **Notes**: The spec's awk acceptance criterion has a self-terminating range bug — the opening heading line matches the closing pattern, so the awk command always returns 1. This is a defect in the acceptance test expression, not in the implementation. The underlying requirement (≥10 lines of protocol prose per section) is satisfied.

### Requirement 2: Body template defined with section-boundary criteria
- **Expected**: `skills/backlog-author/references/body-template.md` defines the five-section template with one-paragraph guidance per section, includes the Why-vs-Role disambiguation rule with required grounding keywords, and passes acceptance greps.
- **Actual**: `grep -c '^## \(Why\|Role\|Integration\|Edges\|Touch points\)' body-template.md` = 5 (PASS). `grep -cE 'symptom.voice|Responsibility|Interface|Boundary' body-template.md` = 5 (PASS, ≥4). `grep -cE 'collapse.*Role|omit Why|Why-vs-Role' body-template.md` = 1 (PASS). The disambiguation rule is present verbatim.
- **Verdict**: PASS

### Requirement 3: LEX-1 scanner extended for `Why`
- **Expected**: `FORBIDDEN_SECTIONS` at line 46 includes `"Why"`, `PERMITTED_SECTIONS` remains `{"Touch points"}`, `SECTION_HEADING_RE` at line 66 matches `Why|Role|Integration|Edges|Touch points`. `grep -c '"Why"' bin/cortex-check-prescriptive-prose` ≥ 2. Scanner exits non-zero for fixture with `## Why` code block.
- **Actual**: `FORBIDDEN_SECTIONS` at line 46 is `frozenset({"Why", "Role", "Integration", "Edges"})` — includes `"Why"`. `PERMITTED_SECTIONS` remains `{"Touch points"}`. `SECTION_HEADING_RE` at line 68 is `^## (Why|Role|Integration|Edges|Touch points)\s*$`. `grep -c '"Why"' bin/cortex-check-prescriptive-prose` = 2 (constant + regex). Scanner run on `tests/fixtures/backlog_author/why_with_code_block.md` exits 1 (non-zero) with `section='Why' pattern=quoted-prose-patch`. Path:line fixture (`why_with_path_line.md`) also triggers correctly.
- **Verdict**: PASS
- **Notes**: The `SECTION_HEADING_RE` is at line 68, not line 66 as the spec states, but this is an irrelevant line-number discrepancy introduced by the addition of the `"Why"` constant.

### Requirement 4: `cortex-create-backlog-item` accepts `--body`
- **Expected**: `--body <markdown>` CLI flag added. `body: str | None = None` parameter on `create_item()` at `cortex_command/backlog/create_item.py:84`. Body appended verbatim after frontmatter `---`. `cortex-create-backlog-item --help` shows `--body`.
- **Actual**: `create_item()` at line 84 has `body: str | None = None`. Body appended at line 124 with `if body is not None: lines.append(body)`. CLI parser adds `--body` at line 162. `python3 -m cortex_command.backlog.create_item --help` shows `--body BODY`. The installed binstub (`cortex-create-backlog-item` at v2.3.0) is stale and does not yet show `--body` — the working-tree source is correct, the installed wheel predates this change.
- **Verdict**: PASS
- **Notes**: The binstub staleness is an expected pattern for working-tree development per `cortex/requirements/project.md` ("Use `python3 -m` invocation to run against the working tree when wheel reinstall between phases is not feasible"). The test suite correctly uses `python3 -m` invocation. The source change is complete.

### Requirement 5: `/cortex-core:backlog new` subcommand exists and routes through `interview` mode
- **Expected**: `new` subcommand added to `skills/backlog/SKILL.md` whose prose invokes `/backlog-author interview <title>`, captures body, and calls `cortex-create-backlog-item --title "..." --body "..."`. The awk acceptance checks pass.
- **Actual**: `### new` section added. Content: "Invoke `/backlog-author interview "{{title}}"` to conduct a structured interview..." and "Run `cortex-create-backlog-item --title "{{title}}" --body "..."` with the body returned by `backlog-author interview`". Both calls are present. The awk acceptance command has the same self-terminating range bug as R1, but `grep "backlog-author interview"` and `grep "cortex-create-backlog-item"` both match in the section content. The `new` subcommand is also listed in the `AskUserQuestion` dispatch menu.
- **Verdict**: PASS
- **Notes**: Awk acceptance criterion has same bug as R1; verified via grep.

### Requirement 6: Two structurally-separated invocation modes (`interview` and `compose`)
- **Expected**: `grep -cE '^### (interview|compose)' skills/backlog-author/SKILL.md` ≥ 2. Compose section has zero `AskUserQuestion` references. Interview section has ≥1 `AskUserQuestion` reference.
- **Actual**: Two headings `### interview` and `### compose` present (count = 2). Python-extracted compose section contains 0 `AskUserQuestion` references. Python-extracted interview section contains 1 `AskUserQuestion` reference (in the "Interview sequence" protocol). Structural separation is enforced at the heading level, not just prose.
- **Verdict**: PASS

### Requirement 6a: Caller-side mode selection is auditable via grep
- **Expected**: `skills/morning-review/SKILL.md` and `skills/discovery/references/decompose.md` each contain `backlog-author compose`. `skills/backlog/SKILL.md`'s `new` section references `backlog-author interview`.
- **Actual**: `grep -cE 'backlog-author compose' skills/morning-review/SKILL.md` = 1 (line 91). `grep -cE 'backlog-author compose' skills/discovery/references/decompose.md` = 1 (line 15). `grep "backlog-author interview" skills/backlog/SKILL.md` matches at two lines in the `### new` section. Additionally, `skills/morning-review/references/walkthrough.md` and `skills/discovery/SKILL.md` also invoke `backlog-author compose`.
- **Verdict**: PASS

### Requirement 6b: Input/output contract for compose mode
- **Expected**: SKILL.md documents the per-piece invocation contract, free-form context inference, and that frontmatter is owned by `cortex-create-backlog-item --body`. `grep -cE '(input contract|invocation contract|compose contract|per-piece|one piece per)' skills/backlog-author/SKILL.md` ≥ 1. `grep -c 'cortex-create-backlog-item' skills/backlog-author/SKILL.md` ≥ 1.
- **Actual**: The `### compose` section contains "Input contract", "Output contract", "Invocation contract" (all three present). "per invocation" and "N times — one piece per invocation" are present. `cortex-create-backlog-item` appears 5 times. The Edge-vs-Touch-point rebalance rule is explicitly noted as owned by calling skills. `grep -cE 'input contract|...' = 1` (PASS). `grep -c 'cortex-create-backlog-item' = 5` (PASS).
- **Verdict**: PASS

### Requirement 7: Discovery's decompose adopts the shared sub-skill, with surrounding contracts updated coherently

#### 7a: Inline template prose extracted to backlog-author
- **Expected**: decompose.md contains `backlog-author/references/body-template.md` at least once. The §2 worked example demonstrates the five-section template or is moved to `body-template.md` with decompose.md retaining only the rebalance rule.
- **Actual**: `grep -c "backlog-author/references/body-template.md" decompose.md` = 1 (line 15). The §2 worked example was restructured: the inline template prose is replaced with a `/backlog-author compose` directive, and the fenced block example now shows only the `## Edges` / `## Touch points` semantic distinction (the rebalance rule). The five-section template definition now lives in `body-template.md`. This matches the second option: "moved into backlog-author's body-template.md... with decompose.md retaining only the contract-vs-path rebalance rule it owns." The `body-template.md` contains all five section headers with guidance.
- **Verdict**: PASS

#### 7b: §5 LEX-1 prose enumeration aligned with the extended scanner
- **Expected**: decompose.md's Forbidden sections enumeration includes `Why`. Acceptance awk command finds "Why" in the Forbidden-sections context.
- **Actual**: Line 85 of decompose.md reads: `**Forbidden sections (per ticket body)**: \`## Why\`, \`## Role\`, \`## Integration\`, \`## Edges\``. The awk acceptance command `awk '/^## /{section=$0} /Forbidden sections/{print section": "$0}' decompose.md | grep -c 'Why'` = 1 (PASS). Section-boundary detection line 87 also includes `Why` in the regex.
- **Verdict**: PASS

#### 7c: §3 R15 revise-piece walk extended to five sections
- **Expected**: The revise-piece walk references `## Why` explicitly alongside Role, Integration, Edges, Touch points. Acceptance awk finds this.
- **Actual**: Line 107 of decompose.md: "The agent re-walks ticket N's `## Why`, `## Role`, `## Integration`, `## Edges`, and `## Touch points` under the user's direction". The awk acceptance command returns ≥ 1 (PASS).
- **Verdict**: PASS

### Requirement 8: All six harness touchpoints route through the new path
- **Expected**: `grep -rc 'backlog new\|backlog-author'` over `skills/dev/SKILL.md`, `skills/morning-review/SKILL.md`, `skills/lifecycle/references/clarify.md`, `skills/discovery/SKILL.md` reports ≥1 match per file.
- **Actual**: `skills/morning-review/SKILL.md` = 1 (line 91, `backlog-author compose`). `skills/dev/SKILL.md` = 2 (lines 149 and 231, `backlog new`). `skills/discovery/SKILL.md` = 1 (line 87, `backlog-author compose`). `skills/lifecycle/references/clarify.md` = 1 (line 19, `backlog new`). All four files pass. `skills/backlog/SKILL.md` contains the `### new` subcommand. `skills/discovery/references/decompose.md` covered by R7.
- **Verdict**: PASS

### Requirement 9: Grep-sweep audit during Implement catches missed targets
- **Expected**: Running the specified grep-sweep and piping through `xargs grep -L 'backlog new\|backlog-author\|intentional bypass'` returns no files.
- **Actual**: Grep-sweep finds matches in: `skills/morning-review/references/walkthrough.md` (has `backlog-author`), `skills/backlog/SKILL.md` (has `backlog new`), `skills/discovery/references/decompose.md` (has `backlog-author`), `skills/dev/SKILL.md` (has `backlog new`). All matched files also contain at least one of the new-path tokens. The xargs filter returns no files — every match is in a file that also references the new path or was updated. Two residual uses in `skills/dev/SKILL.md` (line 141: "Use `/cortex-core:backlog add` to create items") and `skills/discovery/references/decompose.md` (line 114: "Follow the `/cortex-core:backlog add` conventions") are convention-reference uses rather than ticket-creation invocations, and both files already reference the new path.
- **Verdict**: PASS

### Requirement 10: `/backlog-author` is registered as an invocable skill
- **Expected**: Frontmatter declares `name: backlog-author`, description includes routing keywords, skill appears in plugin mirror after `just build-plugin`.
- **Actual**: Frontmatter has `name: backlog-author`. Description includes "backlog body", "ticket authoring", "interview", "compose". `plugins/cortex-core/skills/backlog-author/SKILL.md` exists. `grep -c 'backlog-author' plugins/cortex-core/skills/backlog-author/SKILL.md` = 9 (PASS, ≥1). `justfile` SKILLS manifest updated to include `backlog-author` at line 551.
- **Verdict**: PASS

### Requirement 11: Dual-source parity passes
- **Expected**: `just build-plugin` regenerates `plugins/cortex-core/skills/backlog-author/` mirror including `references/body-template.md`. `just test` exits 0 with the new skill present.
- **Actual**: `plugins/cortex-core/skills/backlog-author/SKILL.md` and `plugins/cortex-core/skills/backlog-author/references/body-template.md` both exist. `just test` exits 0 (all 6 test suites pass). `tests/test_decompose_rules.py::test_uniform_template_four_section_headers_present` now references `BODY_TEMPLATE_MD = REPO_ROOT / "skills" / "backlog-author" / "references" / "body-template.md"` and passes.
- **Verdict**: PASS

### Requirement 12: Behavioral test coverage with named assertions
- **Expected**: 5 named test functions present in `tests/test_backlog_author.py`, each with ≥1 runtime assertion (not just file-presence or string-search). `grep -cE '^def test_...'` = 5. `grep -c '    assert'` ≥ 5. `just test` exits 0.
- **Actual**: All 5 named functions present (`grep` count = 5). `grep -c '    assert'` = 9 (PASS, ≥5). `just test` exits 0 (all 19 tests in backlog_author + decompose_rules suites pass). However, `test_compose_mode_emits_five_section_body` does not invoke the compose path as the spec specifies ("invokes the sub-skill's compose path with a fixture context, asserts the returned body contains all five headings with non-empty content under each"). Instead it checks SKILL.md structural content for five heading references. All assertions in this test are string-search operations against SKILL.md content — the spec's "not just file-presence or string-search" constraint is technically not met by this function alone. The implementation's docstring acknowledges this: "Since the compose subcommand is model-invoked at runtime, this test asserts the SKILL.md compose section's structural protocol." The substitution is pragmatically sound (runtime LLM output is non-deterministic and cannot be tested statically), but it differs from the spec's stated intent for this one test function.
- **Verdict**: PARTIAL
- **Notes**: The other four named test functions fully satisfy their spec intent. `test_lex1_rejects_code_block_in_why_section` and `test_create_item_accepts_body_flag` both invoke subprocesses and make genuine runtime assertions. The only divergence is that `test_compose_mode_emits_five_section_body` uses structural proxy assertions rather than runtime invocation of the compose path.

---

## Requirements Drift

**State**: detected

**Findings**:
- `cortex/requirements/project.md` does not mention the `backlog-author` sub-skill, the `/cortex-core:backlog new` subcommand, or the structured ticket-body authoring discipline layer (Why/Role/Integration/Edges/Touch-points template). These are now wired into every harness creation path and constitute a project-level convention, but project.md's "In Scope" section only mentions "Discovery and backlog are documented inline... `skills/discovery/SKILL.md`, `cortex/backlog/index.md`" without referencing the shared authoring discipline.
- The `cortex/requirements/project.md` architectural constraints section does not mention the `SKILL.md-to-bin parity` for `bin/cortex-check-prescriptive-prose`, which now covers `## Why` as a forbidden section. The LEX-1 scanner extension is a project-level constraint but is documented only in skill prose, not in requirements.

**Update needed**: `/Users/charlie.hall/Workspaces/cortex-command/cortex/requirements/project.md`

## Suggested Requirements Update

In `cortex/requirements/project.md`, under the "In Scope" section, the inline backlog documentation note should reference the shared authoring skill:

> Discovery and backlog are documented inline (no area docs): `skills/discovery/SKILL.md`, `cortex/backlog/index.md`. Ticket body authoring is enforced via `skills/backlog-author/` (the shared sub-skill) and validated at pre-commit by `bin/cortex-check-prescriptive-prose` (LEX-1 scanner, covering `## Why`, `## Role`, `## Integration`, `## Edges`).

---

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `backlog-author` follows `kebab-case` for skill names. `create_item.py`'s `body` parameter follows existing parameter naming. The `why_with_code_block.md` and `why_with_path_line.md` fixture names follow the descriptive-fixture pattern used elsewhere in `tests/fixtures/`.

- **Error handling**: Appropriate. `create_item.py` treats `body` as optional with a `None` guard before appending. The interview subcommand explicitly instructs exiting cleanly on abandonment. The compose subcommand makes no shell-escape assumptions — SKILL.md instructs callers to use heredoc or temp-file redirection for body content with special characters, matching the spec's edge-case requirement.

- **Test coverage**: 19 tests pass across `test_backlog_author.py` (5) and `test_decompose_rules.py` (14). The four structurally-tested behaviors (AskUserQuestion routing, LEX-1 rejection, body flag, and SKILL.md section structure) are the primary gameable behaviors. The compose-mode five-section test uses a structural proxy for an inherently non-testable runtime behavior — this is an acceptable trade-off given LLM non-determinism, and is documented in the test docstring. The `valid_five_section.md` fixture used by `test_create_item_accepts_body_flag` is a realistic five-section body that exercises the verbatim-append path.

- **Pattern consistency**: The new `skills/backlog-author/` directory follows the established `skills/<name>/SKILL.md` + `skills/<name>/references/` layout. The `body-template.md` follows the same structure as other reference files (`schema.md`, `decompose.md`, `clarify.md`). The SKILL.md uses soft positive-routing phrasing throughout with no new MUST escalations, consistent with the MUST-escalation policy. Both SKILL.md files remain under the 500-line cap (backlog-author: 98 lines, decompose.md: 175 lines).

---

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["R12 test_compose_mode_emits_five_section_body uses SKILL.md structural proxy assertions rather than invoking the compose path as spec-specified; all assertions are string-searches. Pragmatically sound given LLM non-determinism, but diverges from spec intent for this one named test."], "requirements_drift": "detected"}
```
