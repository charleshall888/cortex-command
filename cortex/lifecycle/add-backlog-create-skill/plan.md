# Plan: add-backlog-create-skill

## Overview

Phase 1 ships the shared `/backlog-author` sub-skill (with structurally-separated `interview` and `compose` subcommands), the body template with Why-vs-Role disambiguation, the LEX-1 scanner extension, the `cortex-create-backlog-item --body` plumbing, the `/cortex-core:backlog new` subcommand, and the behavioral test suite. Phase 2 wires every harness touchpoint (decompose.md, morning-review, discovery promote-sub-topic, dev hub, lifecycle clarify Context B) to route through the new path, and runs a grep-sweep audit to catch missed surfaces.

## Outline

### Phase 1: Ship the discipline layer (tasks: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
**Goal**: New sub-skill, body template, LEX-1 extension, `--body` plumbing, `new` subcommand, and behavioral tests land coherently. `/cortex-core:backlog new` works end-to-end against fixtures.
**Checkpoint**: `just test` exits 0 with the five named test functions in `tests/test_backlog_author.py` passing AND `bin/cortex-check-prescriptive-prose` rejects a fixture body with a code block in `## Why`.

### Phase 2: Wire the harness (tasks: 11, 12, 13, 14, 15, 16, 17, 18)
**Goal**: Every existing harness location that instructs ticket creation routes through `/cortex-core:backlog new` (human) or `/backlog-author compose` (Claude mid-flow); decompose.md's surrounding contracts (§3 revise-piece walk, §5 LEX-1 prose enumeration) align with the five-section template.
**Checkpoint**: `grep -rln 'backlog add\|cortex-create-backlog-item\|create a backlog\|add to backlog\|file a ticket\|open a backlog item' skills/ docs/ cortex/requirements/ CLAUDE.md | xargs -I{} grep -L 'backlog new\|backlog-author\|intentional bypass' {}` returns no files.

## Tasks

### Task 1: Create backlog-author SKILL.md skeleton with subcommand sections
- **Files**: `skills/backlog-author/SKILL.md`
- **What**: Create the canonical sub-skill file with YAML frontmatter (`name: backlog-author`, `description:` with routing keywords "backlog body", "ticket authoring", "interview", "compose"; `inputs:`/`outputs:`/`preconditions:`/`argument-hint:` per the convention in `skills/backlog/SKILL.md:1–16`), then add two H3 subcommand sections (`### interview` and `### compose`) as stubs that Task 3 and Task 4 will populate. The file establishes the structural skeleton (frontmatter + subcommand dispatch + section headers) without filling in protocol prose.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Frontmatter shape lives in `skills/backlog/SKILL.md:1–16` and `skills/research/SKILL.md` (cleaner argument-hint example). Subcommand-dispatch pattern lives in `skills/backlog/SKILL.md:38–48` (the "When invoked without a {{subcommand}}, present the available actions via AskUserQuestion" block). For backlog-author specifically, the dispatch is positional first-argument: `interview` or `compose`. SKILL.md size cap is 500 lines per `tests/test_skill_size_budget.py`.
- **Verification**: `grep -q '^name: backlog-author$' skills/backlog-author/SKILL.md` AND `grep -cE '^### (interview|compose)' skills/backlog-author/SKILL.md` = 2 — pass if both return success.
- **Status**: [x] done

### Task 2: Create the body template reference with Why-vs-Role disambiguation
- **Files**: `skills/backlog-author/references/body-template.md`
- **What**: Author the five-section body template (`## Why`, `## Role`, `## Integration`, `## Edges`, `## Touch points` optional) with one-paragraph guidance per section. Each section's guidance contains its grounding keyword: Why → "symptom-voice"; Role → "Responsibility" (arc42); Integration → "Interface" (arc42); Edges → "Boundary" or "non-goal"; Touch points → "path" or "line". Include the Why-vs-Role disambiguation rule (collapse Why when it restates Role).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing four-header template lives at `skills/discovery/references/decompose.md` lines 15–38. Spec Requirement 2 gives the exact disambiguation rule prose. arc42 Building Block View terminology: https://docs.arc42.org/section-5/ — Responsibility/Interface/Boundary. The new template is what discovery's decompose.md will Read after Phase 2.
- **Verification**: `grep -c '^## \(Why\|Role\|Integration\|Edges\|Touch points\)' skills/backlog-author/references/body-template.md` ≥ 5 AND `grep -cE 'symptom.voice|Responsibility|Interface|Boundary' skills/backlog-author/references/body-template.md` ≥ 4 AND `grep -cE 'collapse.*Role|omit Why|Why-vs-Role' skills/backlog-author/references/body-template.md` ≥ 1 — pass if all three return success.
- **Status**: [x] done

### Task 3: Populate the `interview` subcommand section
- **Files**: `skills/backlog-author/SKILL.md`
- **What**: Fill in the `### interview` section with an `AskUserQuestion`-driven protocol that walks the author through Why → Role → Integration → Edges → Touch points (per the body-template.md reference). The interview emits the composed body block to stdout for the caller. Per the cadence rule in `skills/lifecycle/references/specify.md:42`, ask questions one at a time. Include a Read directive to `references/body-template.md` so the protocol reads the canonical template at runtime.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: AskUserQuestion-driven interview patterns live in `skills/requirements-gather/SKILL.md` (the canonical "interview sub-skill" precedent). Cadence rule: one question per turn, no batching. The section is bounded by H3 headings; downstream tests (Task 9) will awk-scope between `^### interview` and `^### |^## ` to verify protocol presence + AskUserQuestion reference.
- **Verification**: `awk '/^### interview/,/^### |^## /' skills/backlog-author/SKILL.md | wc -l` ≥ 10 AND `awk '/^### interview/,/^### |^## /' skills/backlog-author/SKILL.md | grep -c 'AskUserQuestion'` ≥ 1 — pass if both return success.
- **Status**: [x] done (note: spec awk verifier has a BSD-awk quirk that collapses the range to 1 line; substantive content verified via alternate selector)

### Task 4: Populate the `compose` subcommand section with input/output contract
- **Files**: `skills/backlog-author/SKILL.md`
- **What**: Fill in the `### compose` section with the autonomous-path protocol: input is one piece's context (structured `why:`/`role:`/`integration:`/`edges:`/optional `touch_points:` fields, OR free-form context Claude infers from); invocations are per-piece (N invocations for N pieces); output is one complete five-section markdown body block; frontmatter is owned by `cortex-create-backlog-item --body`, NOT this sub-skill. The section MUST NOT mention `AskUserQuestion`. Edge-vs-Touch-point rebalance rule remains owned by the calling skill (decompose.md).
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Spec Requirement 6b gives the contract verbatim. Spec Requirement 6 requires the section contain zero `AskUserQuestion` references — this is a structural separation enforcement (CLAUDE.md "Prefer structural separation over prose-only enforcement"). The compose section reads body-template.md for the structural template but uses its own protocol prose for the inference flow.
- **Verification**: `awk '/^### compose/,/^### |^## /' skills/backlog-author/SKILL.md | wc -l` ≥ 10 AND `awk '/^### compose/,/^### |^## /' skills/backlog-author/SKILL.md | grep -c 'AskUserQuestion'` = 0 AND `grep -cE '(input contract|invocation contract|compose contract|per-piece|one piece per)' skills/backlog-author/SKILL.md` ≥ 1 AND `grep -c 'cortex-create-backlog-item' skills/backlog-author/SKILL.md` ≥ 1 — pass if all four return success.
- **Status**: [x] done (same BSD-awk quirk on wc -l; the other three checks pass; section content verified substantive)

### Task 5: Extend LEX-1 scanner to forbid prescription in `## Why`
- **Files**: `bin/cortex-check-prescriptive-prose`, `plugins/cortex-core/bin/cortex-check-prescriptive-prose` (mirror; auto-regenerated)
- **What**: Update three constants in the canonical scanner: `FORBIDDEN_SECTIONS` (line 46) gains `"Why"`; `PERMITTED_SECTIONS` (line 47) remains `{"Touch points"}`; `SECTION_HEADING_RE` (line 66) matches `Why|Role|Integration|Edges|Touch points`. No functional logic changes — the 407-line section-partitioned regex flow is preserved.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current shape verified in research: `FORBIDDEN_SECTIONS: frozenset[str] = frozenset({"Role", "Integration", "Edges"})` at line 46; `PERMITTED_SECTIONS: frozenset[str] = frozenset({"Touch points"})` at line 47; `SECTION_HEADING_RE = re.compile(r"^## (Role|Integration|Edges|Touch points)\s*$")` at line 66. Dual-source rule: edit canonical `bin/cortex-check-prescriptive-prose`; mirror under `plugins/cortex-core/bin/` regenerates via `just build-plugin`. SKILL.md-to-bin parity: the scanner is already referenced from `skills/discovery/references/decompose.md` — that reference covers the new extension as well.
- **Verification**: `grep -c '"Why"' bin/cortex-check-prescriptive-prose` ≥ 2 AND a fixture body containing `## Why\n\n\`\`\`python\nfoo()\n\`\`\`\n## Role\n...` piped to `bin/cortex-check-prescriptive-prose --stdin` (or equivalent) exits non-zero — pass if both hold.
- **Status**: [x] done

### Task 6: Add `--body` flag to `cortex-create-backlog-item`
- **Files**: `cortex_command/backlog/create_item.py`
- **What**: Add an optional `body: str | None = None` parameter to `create_item()` at line 84 (between existing `parent` and the return), with default `None`. Update the body-write logic (currently lines 107–124) to append the body content after the closing `---\n` when provided. Add the corresponding `--body <markdown>` CLI argument to `main()` at line 146.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current signature at line 84: `def create_item(title, status, item_type, backlog_dir, priority="low", rework_of=None, parent=None) -> Path:`. The frontmatter is written via `lines.append("---\n")` at line 122; the body insertion point is immediately after that line. The CLI parser at lines 146–159 accepts `--title`, `--status`, `--type`, `--priority`, `--rework-of`, `--parent` — add `--body` parallel to these (note: `argparse` accepts multi-line strings; shell-side multiline passing is the caller's responsibility per spec Edge Case "Title with shell-unfriendly characters"). When `body` is absent, file content is unchanged from today.
- **Verification**: `cortex-create-backlog-item --help 2>&1 | grep -c -- '--body'` ≥ 1 AND `cortex-create-backlog-item --title "test" --status backlog --type chore --body "## Why\nfixture body\n## Role\nfixture role" --backlog-dir $(mktemp -d)` creates a file whose body section contains `## Why` (verifiable via `grep -c '^## Why$' <created-file>` = 1) — pass if both hold.
- **Status**: [x] done

### Task 7: Add `new` subcommand to backlog SKILL.md
- **Files**: `skills/backlog/SKILL.md`
- **What**: Add a `### new` subsection after the `### add` subsection (currently at lines 49–54). The `new` section prose explicitly chains the two calls: invoke `/backlog-author interview <title>` to obtain a structured body, then invoke `cortex-create-backlog-item --title "..." --body "..."` with the returned body. List `new` in the §Subcommands available-actions enumeration (currently line 41–47). The existing `add` subcommand prose is unchanged.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Existing subcommand listing at `skills/backlog/SKILL.md:41–47`: "pick — list — add — ready — archive — reindex". Insert "new" between "pick" and "add". The `### add` section at lines 49–54 is the template for the new section's prose shape. The `new` section is intentionally tighter than `add` (it delegates to backlog-author, doesn't open the file for user edit — the body is already authored).
- **Verification**: `awk '/^### new/,/^### |^## /' skills/backlog/SKILL.md | grep -c 'backlog-author interview'` ≥ 1 AND `awk '/^### new/,/^### |^## /' skills/backlog/SKILL.md | grep -c 'cortex-create-backlog-item'` ≥ 1 — pass if both hold.
- **Status**: [x] done

### Task 8: Author test fixtures and helpers
- **Files**: `tests/test_backlog_author.py`, `tests/fixtures/backlog_author/` (new directory)
- **What**: Create the test file skeleton with imports, pytest plumbing, and helper functions. Author three fixture bodies under `tests/fixtures/backlog_author/`: (1) `valid_five_section.md` (clean five-section body), (2) `why_with_code_block.md` (Why section contains a fenced code block — should be rejected by LEX-1), (3) `why_with_path_line.md` (Why section contains a `path:line` citation — should also be rejected). The test functions themselves are added in Task 9.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Test convention: `tests/test_*.py` with pytest. Existing test fixtures pattern lives in `tests/fixtures/` directories. The fixtures are read by Task 9's test functions; keep them under 30 lines each, focused on the specific signal being tested.
- **Verification**: `test -f tests/test_backlog_author.py` AND `test -d tests/fixtures/backlog_author` AND `ls tests/fixtures/backlog_author/*.md | wc -l` ≥ 3 — pass if all three hold.
- **Status**: [x] done

### Task 9: Implement the five named test functions
- **Files**: `tests/test_backlog_author.py`
- **What**: Implement the five test functions named in spec Requirement 12: (1) `test_compose_mode_emits_five_section_body` invokes the sub-skill's compose path with a fixture context and asserts the returned body contains all five headings with non-empty content; (2) `test_compose_mode_does_not_call_askuserquestion` greps the SKILL.md's compose section for zero AskUserQuestion references; (3) `test_interview_mode_routes_through_askuserquestion` greps the SKILL.md's interview section for ≥1 AskUserQuestion reference; (4) `test_lex1_rejects_code_block_in_why_section` invokes the scanner on the `why_with_code_block.md` fixture and asserts non-zero exit; (5) `test_create_item_accepts_body_flag` invokes the CLI in a tmp dir with a fixture body and asserts the resulting file contains the fixture verbatim.
- **Depends on**: [3, 4, 5, 6, 8]
- **Complexity**: complex
- **Context**: Each test function has ≥1 `assert` statement. Test 1 (compose-mode body emission) requires invoking the sub-skill protocol — since sub-skills are model-invoked, the test asserts the SKILL.md's compose protocol structure (heading walk, output-format spec, body-template inclusion) rather than running the model. Tests 2/3 are structural awk-greps on SKILL.md. Test 4 invokes `bin/cortex-check-prescriptive-prose` as a subprocess. Test 5 invokes `cortex-create-backlog-item` as a subprocess with `--body` and reads the resulting file. Use `subprocess.run(check=False)` and assert on `returncode`.
- **Verification**: `grep -cE '^def test_(compose_mode_emits_five_section_body|compose_mode_does_not_call_askuserquestion|interview_mode_routes_through_askuserquestion|lex1_rejects_code_block_in_why_section|create_item_accepts_body_flag)' tests/test_backlog_author.py` = 5 AND `grep -c '    assert' tests/test_backlog_author.py` ≥ 5 AND `just test` exits 0 — pass if all three hold.
- **Status**: [x] done

### Task 10: Regenerate plugin mirror and verify parity
- **Files**: `plugins/cortex-core/skills/backlog-author/SKILL.md`, `plugins/cortex-core/skills/backlog-author/references/body-template.md`, `plugins/cortex-core/bin/cortex-check-prescriptive-prose` (all auto-regenerated)
- **What**: Run `just build-plugin` to regenerate the dual-source mirror. The new sub-skill files under `skills/backlog-author/` are mirrored to `plugins/cortex-core/skills/backlog-author/`. The LEX-1 scanner's edits are mirrored to `plugins/cortex-core/bin/cortex-check-prescriptive-prose`. Confirm `just test` passes the dual-source parity test (`tests/test_dual_source_reference_parity.py`).
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 9]
- **Complexity**: simple
- **Context**: `Justfile` lines 542–575 (build-plugin recipe) regenerate the plugin mirror byte-identically from canonical sources. The pre-commit hook also runs this so editing the mirror directly is forbidden. The parity test scans for mirror-vs-canonical drift; new files must be picked up automatically by the existing parity scan (which walks `skills/` and `bin/`).
- **Verification**: `just build-plugin` exits 0 AND `test -f plugins/cortex-core/skills/backlog-author/SKILL.md` AND `diff -q skills/backlog-author/SKILL.md plugins/cortex-core/skills/backlog-author/SKILL.md` exits 0 AND `just test` exits 0 — pass if all four hold.
- **Status**: [x] done (also added backlog-author to build-plugin SKILLS manifest — surfaced gap)

### Task 11: Extract decompose.md §2 template to backlog-author (Req 7a)
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Replace the inline four-header template prose currently at decompose.md lines 15–38 (`## Role / ## Integration / ## Edges / ## Touch points` table + descriptive paragraphs) with a directive: "For each piece, invoke `/backlog-author compose` with the piece's context; the canonical body template lives at `skills/backlog-author/references/body-template.md`." Update the §2 worked example (currently lines 44–59) to demonstrate the five-section template — OR move the worked example into backlog-author's body-template.md as the canonical demo and replace decompose.md's worked example with the contract-vs-path rebalance rule alone (the rule decompose.md still owns).
- **Depends on**: [2, 4]
- **Complexity**: complex
- **Context**: The template at lines 15–38 has been editorially stable across 19 commits — the extraction must preserve the section semantics, not just the headings. The Edge-vs-Touch-point rebalance rule at line 42 remains owned by decompose.md (it's policy on the template, not the template itself). The worked example at lines 44–59 demonstrates the rebalance rule using the template as illustration; deciding whether to update or relocate it is a content judgment based on which file best owns the demo.
- **Verification**: `grep -c 'backlog-author/references/body-template.md' skills/discovery/references/decompose.md` ≥ 1 AND `awk '/^## /{section=$0} /Role.*Integration.*Edges|## Role/{print NR": "$0}' skills/discovery/references/decompose.md | head -5` shows the canonical template definition is no longer present (i.e., the bullet table at lines 15–38 is replaced) — pass if both hold.
- **Status**: [x] done

### Task 12: Update decompose.md §5 LEX-1 enumeration to include Why (Req 7b)
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Update the "Forbidden sections" enumeration at decompose.md lines 108–110 to include `Why`. Currently: "Forbidden sections (per ticket body): `## Role`, `## Integration`, `## Edges`. Permitted section: `## Touch points`." After: "Forbidden sections: `## Why`, `## Role`, `## Integration`, `## Edges`. Permitted: `## Touch points`." Update any §5 worked examples that enumerate the forbidden-section set so they match the live scanner's behavior after Task 5.
- **Depends on**: [5, 11]
- **Complexity**: simple
- **Context**: This sub-criterion (7b) is decoupled from 7a's template extraction but lives in the same file. The §5 prose is documentation of the scanner contract — it must mirror the scanner's actual `FORBIDDEN_SECTIONS` constant set. Without this update, the docs and the scanner disagree, which is a parity defect waiting to bite future contributors.
- **Verification**: `awk '/^## /{section=$0} /Forbidden sections/{print section": "$0}' skills/discovery/references/decompose.md | grep -c 'Why'` ≥ 1 — pass if it returns success.
- **Status**: [x] done

### Task 13: Extend decompose.md §3 R15 revise-piece walk to five sections (Req 7c)
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Update the revise-piece prose currently around line 130: "**`revise-piece <N>`** — open a free-text revision prompt scoped to ticket N's body. The agent re-walks ticket N's `## Role`, `## Integration`, `## Edges`, and `## Touch points` under the user's direction and re-presents the FULL batch (not just ticket N) at the gate." After: extend the walk to include `## Why` first (matching the new template order). The R15 batch-review gate's section coverage must align with the five-section template so users flagged on a Why-section LEX-1 violation can resolve it through the same revision loop.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: R15's revise-piece is the user's interactive path to resolve LEX-1 flags inside the batch-review gate. With Task 5's scanner extension, Why is now a forbidden-section; without this update, a Why-flagged ticket cannot be resolved through revise-piece because the walk doesn't visit Why.
- **Verification**: `awk '/revise.piece/,/^### |^## /' skills/discovery/references/decompose.md | grep -cE 'Why.*Role.*Integration.*Edges|## Why'` ≥ 1 — pass if the walk references Why explicitly.
- **Status**: [x] done

### Task 14: Wire morning-review to `/backlog-author compose`
- **Files**: `skills/morning-review/SKILL.md`
- **What**: Update the ticket-creation instruction at line 91 ("create a backlog investigation item") to invoke `/backlog-author compose` with the surrounding investigation context, then pass the returned body to `cortex-create-backlog-item --body`. The morning-review runs autonomously, so it must invoke `compose` not `interview` (per spec Requirement 6a's caller-side mode discipline).
- **Depends on**: [4, 6]
- **Complexity**: simple
- **Context**: Line 91 currently reads (paraphrase): "create a backlog investigation item with title 'investigate X' and body summarizing what was uncovered." The replacement directs Claude to use the compose subcommand explicitly — making the autonomous-vs-human routing structural per CLAUDE.md "Prefer structural separation over prose-only enforcement."
- **Verification**: `grep -cE 'backlog-author[[:space:]]+compose|backlog-author compose' skills/morning-review/SKILL.md` ≥ 1 — pass if the file references the compose subcommand.
- **Status**: [x] done

### Task 15: Wire discovery promote-sub-topic to compose mode
- **Files**: `skills/discovery/SKILL.md`
- **What**: Update the `promote-sub-topic` branch at line 87 to invoke `/backlog-author compose` for the new `needs-discovery` ticket's body, then call `cortex-create-backlog-item --body`. Like morning-review, discovery runs autonomously when promoting sub-topics, so `compose` is the correct mode.
- **Depends on**: [4, 6]
- **Complexity**: simple
- **Context**: Line 87 currently creates a `needs-discovery` ticket via `cortex-create-backlog-item --title "investigate ..."` with a minimal body. The new flow runs the body through compose mode so it lands with the five-section structure.
- **Verification**: `grep -cE 'backlog-author[[:space:]]+compose|backlog-author compose' skills/discovery/SKILL.md` ≥ 1 — pass if the file references compose.
- **Status**: [x] done

### Task 16: Wire dev-hub backlog-creation suggestions to `/cortex-core:backlog new`
- **Files**: `skills/dev/SKILL.md`
- **What**: Update the backlog-creation prose at `skills/dev/SKILL.md` lines 149 and 231 to suggest `/cortex-core:backlog new` (the human-facing interview path) rather than `/cortex-core:backlog add`. The dev hub is a human-facing entry point, so `interview` mode is correct.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Lines 149 and 231 currently mention creating backlog items (paraphrase: "the user can create new items via /cortex-core:backlog add"). Replace `add` with `new` at both line ranges. The `add` subcommand still exists; the dev hub just nudges users toward the disciplined path by default.
- **Verification**: `grep -cE 'backlog new|/cortex-core:backlog new' skills/dev/SKILL.md` ≥ 1 — pass if the file references the new subcommand.
- **Status**: [x] done

### Task 17: Wire lifecycle Clarify Context B to offer `/cortex-core:backlog new`
- **Files**: `skills/lifecycle/references/clarify.md`
- **What**: Update the Context B offer at line 19 to suggest invoking `/cortex-core:backlog new` rather than the bare `cortex-create-backlog-item` (the current phrasing is "Offer to create a backlog item before continuing"). Clarify Context B is human-facing (a human is at the keyboard running /cortex-core:lifecycle), so `interview` mode is correct.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Line 19 currently reads: "Switch to **Context B** (ad-hoc topic) and treat the input as the topic name. Offer to create a backlog item before continuing — if this seems impractical, note it and proceed without." Replace the bare "create a backlog item" with "invoke /cortex-core:backlog new to create a backlog item with the disciplined body template" (or similar).
- **Verification**: `grep -cE 'backlog new|/cortex-core:backlog new' skills/lifecycle/references/clarify.md` ≥ 1 — pass if the file references the new subcommand.
- **Status**: [x] done

### Task 18: Grep-sweep audit + cleanup for missed touchpoints
- **Files**: any file the audit surfaces (provisional list: docs/*, cortex/requirements/*, CLAUDE.md)
- **What**: Run the grep sweep specified in spec Requirement 9: `grep -rni 'backlog add\|cortex-create-backlog-item\|create a backlog\|add to backlog\|file a ticket\|open a backlog item' skills/ docs/ cortex/requirements/ CLAUDE.md`. For each match not already covered by Tasks 14–17, decide: (a) rewrite to reference `backlog new` or `backlog-author`, OR (b) annotate as an intentional bypass with a one-line comment. Document each decision in the commit message.
- **Depends on**: [14, 15, 16, 17]
- **Complexity**: simple
- **Context**: Audit prose-mention surfaces, not active callers (Tasks 14–17 cover the active callers). Docs and requirements files may reference creation paths informationally — those can be either rewritten for consistency or annotated as intentional bypasses. The acceptance criterion in spec Requirement 9 codifies the "no untreated matches remain" rule.
- **Verification**: `grep -rln 'backlog add\|cortex-create-backlog-item\|create a backlog\|add to backlog\|file a ticket\|open a backlog item' skills/ docs/ cortex/requirements/ CLAUDE.md | xargs -I{} grep -L 'backlog new\|backlog-author\|intentional bypass' {}` returns no files — pass if the command produces empty output.
- **Status**: [x] done

## Risks

- **Decompose.md cutover requires three coordinated changes (Tasks 11/12/13)**. A miss on any one leaves discovery's batch-review gate in an inconsistent state — the scanner-coverage prose may contradict actual scanner behavior, or the revise-piece walk may not cover the new Why section so users cannot resolve flagged Why content through the existing UX. Mitigation: Tasks 11/12/13 are split for clarity but should be reviewed together as a coherent unit; the Phase 2 Checkpoint verifies the unified outcome.
- **LEX-1 extension to Why is forward-incompatible** (Task 5). Adding Why to `FORBIDDEN_SECTIONS` is straightforward to ship but harder to retract — tickets authored against the five-section template will start accumulating, and if Why turns out to be unhelpful, the scanner unwinding requires both prose updates and historical-ticket re-validation. Acceptable risk because the Why-vs-Role disambiguation rule (Task 2) permits Why to collapse into Role when appropriate, providing a release valve.
- **The `interview` vs `compose` structural separation depends on callers selecting the right subcommand** (Tasks 14/15 vs 16/17). The acceptance criterion in spec Requirement 6a is caller-side grep, which catches missing references but not wrong ones. A morning-review caller that accidentally invokes `interview` instead of `compose` would fail at runtime (no human to answer AskUserQuestion); the spec's Edge Case "Autonomous run accidentally invokes interview mode" documents this as a tool error rather than a silent block.
- **Body-template guidance for inferring Why from context (Task 4)** may produce inconsistent Why sections across Claude-as-author flows. If Claude produces a different "symptom-voice" framing each time, the resulting backlog items vary in tone. Mitigation: Task 2's body-template.md grounds Why in arc42 Building Block prior art and the Why-vs-Role disambiguation rule provides explicit guidance; Task 9's `test_compose_mode_emits_five_section_body` asserts the structural output even if the prose tone varies.

## Acceptance

The whole feature is accepted when all 14 spec requirements pass their stated acceptance criteria simultaneously, the test suite (`just test`) exits 0 with the five named functions in `tests/test_backlog_author.py` present and asserting, the dual-source parity test confirms the plugin mirror matches the canonical source byte-for-byte, and an end-to-end smoke check passes: invoking `/cortex-core:backlog new` with a fixture title produces a backlog file in `cortex/backlog/` containing a five-section body that the LEX-1 scanner accepts as clean (no path:line citations or code blocks in Why/Role/Integration/Edges). The grep-sweep audit (Task 18) reports no untreated harness mentions of the legacy creation paths.
