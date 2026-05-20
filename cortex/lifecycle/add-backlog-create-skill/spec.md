# Specification: add-backlog-create-skill

## Problem Statement

Backlog ticket authoring in cortex-command relies on prose-only discipline (`skills/backlog/references/schema.md:62–71`) that has documented multi-year failure modes — authors prescribe How (specific libraries, file paths, exact fixes) and the downstream lifecycle's research phase gets boxed into the proposed solution rather than exploring alternatives. The discipline lives operationally only inside `/cortex-core:discovery`'s decompose phase, leaving every other creation path (manual `backlog add`, lifecycle Context B, morning-review autonomous flows, dev-hub suggestions) uncovered. This feature ships a shared body-authoring sub-skill that enforces the discipline at the moment of authoring, ports the Role/Integration/Edges/Touch-points template proven inside discovery's decompose phase (its labels map to arc42's Building Block View — Responsibility/Interface/Boundary), and prepends a `## Why` intent section to anchor motivation at the intake stage. The Why section is permitted to collapse into Role when the two would restate each other (Requirement 2's disambiguation rule) — the prepended section is an affordance, not a mandatory expansion. The discipline layer is wired into every harness location that currently instructs ticket creation.

## Phases

- **Phase 1: Ship the discipline layer** — Create the shared sub-skill, the body template, the LEX-1 `## Why` extension, the `backlog new` subcommand, and the `--body` plumbing on `cortex-create-backlog-item`. Tests pass with the new path exercised end-to-end.
- **Phase 2: Wire the harness** — Update all six identified touchpoints to route through `/cortex-core:backlog new` (or the shared sub-skill directly when invoked by Claude mid-flow), and run a grep sweep during Implement to catch any additional mentions.

## Requirements

1. **Shared body-authoring sub-skill exists with both subcommand sections populated**: Create `skills/backlog-author/SKILL.md` (canonical source) that exposes the `interview` and `compose` subcommands per Requirement 6, with both subcommand sections containing protocol prose (not stubs). The skill composes a structured body and emits it to stdout for the caller to pass to `cortex-create-backlog-item --body`. Acceptance: `test -f skills/backlog-author/SKILL.md` exits 0 AND `grep -q '^name: backlog-author' skills/backlog-author/SKILL.md` exits 0 AND `awk '/^### interview/,/^### |^## /' skills/backlog-author/SKILL.md | wc -l` ≥ 10 (the interview section contains ≥10 lines of protocol, not just a stub heading) AND `awk '/^### compose/,/^### |^## /' skills/backlog-author/SKILL.md | wc -l` ≥ 10 (same for compose). **Phase**: Phase 1.

2. **Body template defined with section-boundary criteria**: The sub-skill's `references/body-template.md` (or inline in SKILL.md) defines the five-section template — `## Why`, `## Role`, `## Integration`, `## Edges`, `## Touch points` (optional) — with one-paragraph guidance per section AND an explicit **Why-vs-Role disambiguation rule** stating: "Why captures the problem the ticket addresses in symptom-voice (what's broken / what's missing in observable terms). Role captures what slot this piece fills in the system after the ticket lands (arc42 Responsibility — what task it fulfills). When the Why collapses to one sentence that restates Role's lead, omit Why entirely — the section is optional in this collapse case, required otherwise." Each section's guidance must contain its grounding keywords: Why → "symptom-voice"; Role → "Responsibility"; Integration → "Interface"; Edges → "Boundary" or "non-goal"; Touch points → "path" or "line". Acceptance: `grep -c '^## \(Why\|Role\|Integration\|Edges\|Touch points\)' skills/backlog-author/references/body-template.md` ≥ 5 AND `grep -cE 'symptom.voice|Responsibility|Interface|Boundary' skills/backlog-author/references/body-template.md` ≥ 4 AND `grep -cE 'collapse.*Role|omit Why|Why-vs-Role' skills/backlog-author/references/body-template.md` ≥ 1. **Phase**: Phase 1.

3. **LEX-1 scanner extended for `Why`**: `bin/cortex-check-prescriptive-prose` is updated so that `FORBIDDEN_SECTIONS` (line 46) includes `"Why"`, `PERMITTED_SECTIONS` (line 47) remains `{"Touch points"}`, and `SECTION_HEADING_RE` (line 66) matches `Why|Role|Integration|Edges|Touch points`. Acceptance: `grep -c '"Why"' bin/cortex-check-prescriptive-prose` ≥ 2 (constant + regex) AND `bin/cortex-check-prescriptive-prose` exits non-zero when given a fixture body whose `## Why` section contains a code block or `path:line` citation. **Phase**: Phase 1.

4. **`cortex-create-backlog-item` accepts `--body`**: Add an optional `--body <markdown>` CLI flag (and a corresponding `body: str | None = None` parameter on `create_item()` at `cortex_command/backlog/create_item.py:84`). When provided, the body content is appended verbatim after the frontmatter closing `---`. When absent, behavior is unchanged from today. Acceptance: `cortex-create-backlog-item --help` shows `--body` AND a body passed via the flag appears in the created file. **Phase**: Phase 1.

5. **`/cortex-core:backlog new` subcommand exists and routes through `interview` mode**: Add a `new` subcommand to `skills/backlog/SKILL.md` whose prose explicitly invokes `/backlog-author interview <title>`, captures the returned body, and calls `cortex-create-backlog-item --title "..." --body "..."`. The existing `add` subcommand is unchanged. Acceptance: `awk '/^### new/,/^### |^## /' skills/backlog/SKILL.md | grep -c 'backlog-author interview'` ≥ 1 AND `awk '/^### new/,/^### |^## /' skills/backlog/SKILL.md | grep -c 'cortex-create-backlog-item'` ≥ 1 (the subcommand prose explicitly chains the two calls). **Phase**: Phase 1.

6. **Two structurally-separated invocation modes (`interview` and `compose`) replace prose-only routing**: The sub-skill exposes two subcommands, selected by the first positional argument: `/backlog-author interview <topic>` (human-facing path; `AskUserQuestion` prompts live exclusively under this subcommand's section in SKILL.md) and `/backlog-author compose <context-block>` (autonomous path; no `AskUserQuestion` calls; Claude composes the body from the provided context block which carries pre-resolved Why/Role/Integration/Edges fields). The SKILL.md control flow physically separates the two: the `interview` section contains the `AskUserQuestion` directive; the `compose` section does not mention `AskUserQuestion`. Callers select the mode by the subcommand they invoke. This replaces R6's prior prose-only routing per CLAUDE.md's "Prefer structural separation over prose-only enforcement for sequential gates." Acceptance: `grep -cE '^### (interview|compose)' skills/backlog-author/SKILL.md` ≥ 2 (one heading per mode) AND `awk '/^### compose/,/^### |^## /' skills/backlog-author/SKILL.md | grep -c 'AskUserQuestion'` = 0 (the compose section MUST contain zero `AskUserQuestion` references) AND `awk '/^### interview/,/^### |^## /' skills/backlog-author/SKILL.md | grep -c 'AskUserQuestion'` ≥ 1 (the interview section MUST reference `AskUserQuestion`). **Phase**: Phase 1.

6a. **Caller-side mode selection is auditable via grep**: Every autonomous caller updated under Requirement 8 invokes the `compose` subcommand specifically; every human-facing caller invokes `interview` (or routes through `/cortex-core:backlog new` which itself invokes `interview`). Acceptance: for each autonomous-caller file in {`skills/morning-review/SKILL.md`, `skills/discovery/references/decompose.md`}, `grep -cE 'backlog-author[[:space:]]+compose|backlog-author compose' <file>` ≥ 1; and `skills/backlog/SKILL.md`'s `new` subcommand section references `backlog-author interview` (verifiable via `awk '/^### new/,/^### |^## /' skills/backlog/SKILL.md | grep -c 'backlog-author interview'` ≥ 1). **Phase**: Phase 2.

6b. **Input/output contract for compose mode**: The sub-skill documents in SKILL.md the contract for the `compose` subcommand: input is one piece's context (a structured block containing pre-resolved `why:`, `role:`, `integration:`, `edges:`, and optional `touch_points:` fields, OR free-form context from which Claude infers those fields); invocations are per-piece (when a caller has N pieces to author, it invokes compose N times); output is one complete five-section markdown body block (frontmatter handled by `cortex-create-backlog-item --body`, not the sub-skill). The Edge-vs-Touch-point rebalance rule (decompose.md line 42 — "If an edge bullet would name a path or line to express its constraint, the path:line moves to `## Touch points`") remains owned by the calling skill, not by backlog-author. Acceptance: `grep -cE '(input contract|invocation contract|compose contract|per-piece|one piece per)' skills/backlog-author/SKILL.md` ≥ 1 AND `grep -c 'cortex-create-backlog-item' skills/backlog-author/SKILL.md` ≥ 1 (frontmatter ownership is documented). **Phase**: Phase 1.

7. **Discovery's decompose adopts the shared sub-skill, with surrounding contracts updated coherently**: `skills/discovery/references/decompose.md` is updated so the ticket-body authoring step invokes `/backlog-author compose` per piece (Requirement 6a) rather than carrying its own inline template. Three sub-criteria must hold simultaneously — a passing grep on one does not satisfy the others:

   7a. **Inline template prose extracted to backlog-author**: The four-header template prose in decompose.md §2 is replaced with a directive to invoke `/backlog-author compose`. The Read-target for any reference to the canonical template is `skills/backlog-author/references/body-template.md` (the template reference, not SKILL.md — decompose runs autonomously and does not need the interview prose). Acceptance: decompose.md contains the literal string `backlog-author/references/body-template.md` at least once AND the §2 worked example (currently decompose.md lines 44–59) is updated to demonstrate the five-section template (or moved into backlog-author's body-template.md as the canonical example, with decompose.md retaining only the contract-vs-path rebalance rule it owns).

   7b. **§5 LEX-1 prose enumeration aligned with the extended scanner**: decompose.md's "Forbidden sections" enumeration (currently lines 108–110) and worked examples that name section headers are updated to include `Why` so decompose.md's documented scanner contract matches the live scanner after Requirement 3. Acceptance: `awk '/^## /{section=$0} /Forbidden sections/{print section": "$0}' skills/discovery/references/decompose.md | grep -c 'Why'` ≥ 1 (the Forbidden-sections enumeration mentions Why).

   7c. **§3 R15 revise-piece walk extended to five sections**: decompose.md's revise-piece walk (currently line ~130) is updated so the user-revision loop walks all five sections (`## Why`, `## Role`, `## Integration`, `## Edges`, `## Touch points`) — Why must be included so users revising a Why-flagged piece can resolve the flag through the same gate. Acceptance: `awk '/revise.piece/,/^### |^## /' skills/discovery/references/decompose.md | grep -cE 'Why.*Role.*Integration.*Edges|## Why'` ≥ 1 (the walk references Why explicitly).

   **Phase**: Phase 2.

8. **All six harness touchpoints route through the new path**: Update each of the following to invoke `/cortex-core:backlog new` (for human-facing surfaces) or `/backlog-author` directly (for Claude-as-author mid-flow surfaces):
   - `skills/backlog/SKILL.md` (the `add` subcommand prose is unchanged per OQ4; the `new` subcommand documents the canonical disciplined path)
   - `skills/dev/SKILL.md` (lines 149 and 231)
   - `skills/morning-review/SKILL.md` (line 91)
   - `skills/lifecycle/references/clarify.md` (line 19, Context B offer)
   - `skills/discovery/SKILL.md` (line 87, `promote-sub-topic` branch)
   - `skills/discovery/references/decompose.md` (covered by Requirement 7)

   Acceptance: `grep -rc 'backlog new\|backlog-author' skills/dev/SKILL.md skills/morning-review/SKILL.md skills/lifecycle/references/clarify.md skills/discovery/SKILL.md` reports ≥1 match per file. **Phase**: Phase 2.

9. **Grep-sweep audit during Implement catches missed targets**: During Phase 2, run `grep -rni 'backlog add\|cortex-create-backlog-item\|create a backlog\|add to backlog\|file a ticket\|open a backlog item' skills/ docs/ cortex/requirements/ CLAUDE.md` and route any additional surface to the new path (or document why it was intentionally skipped, e.g., docs/internals describing the script call directly). Acceptance: `grep -rln 'backlog add\|cortex-create-backlog-item\|create a backlog\|add to backlog\|file a ticket\|open a backlog item' skills/ docs/ cortex/requirements/ CLAUDE.md | xargs -I{} grep -L 'backlog new\|backlog-author\|intentional bypass' {}` returns no files (every match either references the new path or is annotated as an intentional bypass). **Phase**: Phase 2.

10. **`/backlog-author` is registered as an invocable skill**: Frontmatter declares `name: backlog-author`, `description:` includes routing keywords (e.g., "backlog body", "ticket authoring", "interview"), and the skill appears in the agentic-layer registry such that other skills can Read it via the `${CLAUDE_SKILL_DIR}/../backlog-author/SKILL.md` pattern. Acceptance: `grep -c 'backlog-author' plugins/cortex-core/skills/backlog-author/SKILL.md` ≥1 after `just build-plugin` regenerates the mirror. **Phase**: Phase 1.

11. **Dual-source parity passes**: After Phase 1 changes, `just build-plugin` regenerates the `plugins/cortex-core/skills/backlog-author/` mirror, and `tests/test_dual_source_reference_parity.py` passes. Acceptance: `just test` exits 0 with the new skill present. **Phase**: Phase 1.

12. **Behavioral test coverage with named assertions**: Add tests under `tests/test_backlog_author.py` covering the gameable behaviors. Each named test must contain ≥1 runtime assertion (not just file-presence or string-search). Required test functions (at minimum):
    - `test_compose_mode_emits_five_section_body` — invokes the sub-skill's compose path with a fixture context, asserts the returned body contains all five `## Why|Role|Integration|Edges|Touch points` headings with non-empty content under each.
    - `test_compose_mode_does_not_call_askuserquestion` — verifies the compose path's SKILL.md section contains zero `AskUserQuestion` references (mirrors R6's grep acceptance as a regression guard).
    - `test_interview_mode_routes_through_askuserquestion` — verifies the interview path's SKILL.md section references `AskUserQuestion` at least once.
    - `test_lex1_rejects_code_block_in_why_section` — invokes `bin/cortex-check-prescriptive-prose` on a fixture body whose `## Why` section contains a fenced code block, asserts non-zero exit.
    - `test_create_item_accepts_body_flag` — invokes `cortex-create-backlog-item --title "test" --body "<five-section-fixture>"` in a tmp directory, asserts the resulting file's body matches the fixture verbatim.

    Acceptance: `grep -cE '^def test_(compose_mode_emits_five_section_body|compose_mode_does_not_call_askuserquestion|interview_mode_routes_through_askuserquestion|lex1_rejects_code_block_in_why_section|create_item_accepts_body_flag)' tests/test_backlog_author.py` = 5 AND `grep -c '    assert' tests/test_backlog_author.py` ≥ 5 (each named function contains at least one assert) AND `just test` exits 0. **Phase**: Phase 1.

## Non-Requirements

- **Not** retiring or modifying `/cortex-core:backlog add` (the raw-stub path). It remains valuable for users who want lightweight creation. The decision to route through `new` is the author's per-invocation.
- **Not** displaying an `add` → `new` nudge. Per OQ4, the stub path stays silent.
- **Not** extending LEX-1 to catch English prescriptive patterns ("we should use X", "the fix is to..."). Per OQ5, this is deferred to a follow-up ticket. This lifecycle ships only the structural `Why` section extension.
- **Not** modifying the backlog frontmatter schema (`skills/backlog/references/schema.md`'s field table is unchanged).
- **Not** changing how the overnight runner or morning-review's programmatic paths invoke `cortex-create-backlog-item`. They retain non-interactive invocation; the discipline layer applies at the SKILL.md layer, not in the underlying script's required path.

## Edge Cases

- **Title with shell-unfriendly characters**: When `--body` content contains quotes, backticks, or newlines, the SKILL.md prose must instruct callers to use heredoc-style passing or temp-file redirection. Body content is appended verbatim — no shell-escape transformation in the script.
- **Author exits the interview partway**: If a human author abandons the `AskUserQuestion` sequence mid-interview, the sub-skill exits cleanly without writing a partial ticket. No half-authored files left behind.
- **Autonomous run accidentally invokes interview mode**: If an autonomous caller (overnight runner, morning-review, etc.) mistakenly invokes `/backlog-author interview` instead of `compose`, the failure surfaces as a tool error (no human is available to answer `AskUserQuestion`) rather than a silent block. The autonomous-caller acceptance criteria in Requirement 6a (caller-side grep that asserts `backlog-author compose` is invoked) guard against this at the structural level; the runtime fallback is a hard error the runner can detect and the morning report will surface. The structural separation in Requirement 6 ensures the failure direction is observable, not silent.
- **Trivially-redundant Why** (Why ≈ Role's lead sentence): The body template's Why-vs-Role disambiguation rule (Requirement 2) permits omitting Why entirely when it would restate Role. The LEX-1 scanner does not require Why to be present — it only validates content when Why exists.
- **Claude infers a Why field that contains a code block**: The LEX-1 scanner catches it at pre-commit time. The sub-skill prose instructs Claude to compose Why as symptom-voice prose, but the scanner is the gate, not the prose.
- **Existing decompose.md flows mid-edit when Phase 2 lands**: Discovery's batch-review gate (R15) and the §5 LEX-1 prose enumeration are updated coherently with the template extraction per Requirements 7a/7b/7c — the cutover does NOT depend on prose preservation alone; the surrounding contracts are explicitly updated to match the five-section template.
- **A skill that mentions ticket creation in prose but doesn't actually invoke creation** (e.g., a docs reference): the grep-sweep surfaces it; Implementer decides whether the prose needs rewording (most likely yes, for consistency) without invoking the new skill.

## Changes to Existing Behavior

- **ADDED**: `/cortex-core:backlog new` subcommand alongside the existing `add|list|pick|ready|archive|reindex` set.
- **ADDED**: `skills/backlog-author/` sub-skill (new directory).
- **MODIFIED**: `bin/cortex-check-prescriptive-prose` accepts `## Why` as a forbidden-for-prescription section (line 46 constant, line 66 regex).
- **MODIFIED**: `cortex_command/backlog/create_item.py::create_item()` and the CLI accept an optional `body` parameter.
- **MODIFIED**: `skills/discovery/references/decompose.md` delegates body-authoring to `/backlog-author compose`; inline R/I/E/T template prose is replaced with a Read directive to `skills/backlog-author/references/body-template.md` (Req 7a); the §5 Forbidden-sections enumeration is updated to include `Why` (Req 7b); the §3 R15 revise-piece walk is extended to all five sections (Req 7c).
- **MODIFIED**: Five other harness surfaces (`skills/dev/SKILL.md`, `skills/morning-review/SKILL.md`, `skills/lifecycle/references/clarify.md`, `skills/discovery/SKILL.md`, and the new `new` subcommand prose inside `skills/backlog/SKILL.md`) reference the new path.
- **UNCHANGED**: `/cortex-core:backlog add` behavior, `cortex-create-backlog-item`'s default invocation, the backlog frontmatter schema, the overnight runner and morning-review programmatic call paths.

## Technical Constraints

- **Dual-source enforcement**: Canonical sources under `skills/backlog-author/`; mirror auto-regenerated to `plugins/cortex-core/skills/backlog-author/` via `just build-plugin`. Editing the mirror directly is forbidden.
- **SKILL.md size cap** (500 lines, per `tests/test_skill_size_budget.py`): the new SKILL.md and decompose.md changes must respect this cap. Extract to `skills/backlog-author/references/` if needed.
- **MUST-escalation policy** (CLAUDE.md): the sub-skill's prose uses soft positive-routing phrasing by default. No new MUST escalations without the documented evidence trail.
- **Programmatic-caller carve-out**: `cortex-create-backlog-item` remains usable non-interactively. The `--body` flag is optional. The overnight runner and morning-review programmatic invocations continue to work unchanged; the discipline applies at the SKILL.md layer.
- **LEX-1 scanner reuse**: `bin/cortex-check-prescriptive-prose` retains its 407-line section-partitioned regex logic; only the constants and regex are extended for `Why`. Functional logic is unchanged.
- **File-based state** (ADR-0001): the sub-skill writes markdown files with YAML frontmatter through `cortex-create-backlog-item`; no DB.
- **SKILL.md-to-bin parity** (`bin/cortex-check-parity`): the new sub-skill must reference the LEX-1 scanner in its prose so the scanner's binstub stays wired to a SKILL.md reference. The parity test runs at pre-commit; spec-time check is read-only.

## Open Decisions

None — all open questions from research were resolved during the Specify interview (see `cortex/lifecycle/add-backlog-create-skill/research.md` Open Questions section for the resolution audit trail).

## Proposed ADR

None considered.

<!-- The body-template choice is grounded in arc42/C4/DDD prior art rather than a novel decision; the rewire scope is mechanical; the human-vs-Claude routing IS structural per Req 6 (subcommand-based) and therefore no longer an ADR-shape decision. None of the design choices meet the three-criteria ADR gate (Hard to reverse + Surprising without context + Real trade-off). -->
