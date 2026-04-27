# Plan: Audit skill prompts and remove verbose instructions above the floor

## Overview

Small documentation-only plan that closes #052 as the DR-6 stress-test gate answer. The deliverable is a short completion note in the lifecycle directory and a new backlog ticket filed for the orthogonal imperative-intensity rewrite axis. No skill files are edited. Task 1 creates the new ticket first so Task 2 can cross-link its ID from the DR-6 note; Task 3 adds the new artifacts to index.md via targeted Edit operations that read current state; Task 4 verifies working-tree scope compliance.

## Tasks

### Task 1: Create new backlog ticket for imperative-intensity rewrite axis
- **Files**: `backlog/NNN-apply-anthropic-migration-rewrite-table-to-skill-prompts.md` (NNN auto-assigned by `create-backlog-item`), its sidecar `backlog/NNN-....events.jsonl`, and regenerated `backlog/index.json` + `backlog/index.md`.
- **What**: Create a new backlog item for the imperative-intensity rewrite axis and augment it with tags, body, and `blocked-by` via `update-item` and direct file edits. Task 1 produces the filename that Task 2 cross-references.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `create-backlog-item` is at `~/.local/bin/create-backlog-item` (symlinks to `backlog/create_item.py`). Known import bug: requires `PYTHONPATH=/Users/charlie.hall/Workspaces/cortex-command` on invocation. Argument set is limited to `--title`, `--status`, `--type`, `--priority`, `--parent` — NOT `--tags` and NOT body content.
  - Creation command:
    ```
    PYTHONPATH=/Users/charlie.hall/Workspaces/cortex-command create-backlog-item \
      --title "Apply Anthropic migration rewrite table to skill prompts" \
      --status draft \
      --type chore \
      --priority low \
      --parent 49
    ```
  - Immediately after creation, locate the new file via `ls backlog/[0-9]*-apply-anthropic-migration-rewrite-table*.md | sort | tail -1`. Capture the full path for use in subsequent sub-steps and for Task 2.
  - Append tags via `update-item <backlog-filename-slug> "tags=[output-efficiency,skills]"` (where `<backlog-filename-slug>` is the filename without `.md`).
  - Append `blocked-by` via `update-item <backlog-filename-slug> "blocked-by=[]"` — explicitly empty; this ticket does not depend on #052 completion.
  - Write body content via the `Write` tool (overwriting the empty body while preserving the frontmatter that `create-backlog-item` wrote). Body must include the following substrings so verification can confirm content landed:
    - `Anthropic migration rewrite table` (exact phrase, used by spec R2 verification)
    - `imperative-intensity` (exact phrase, used by spec R2 verification)
    - The scope statement naming all 9 audited skills by directory: `skills/lifecycle`, `skills/discovery`, `skills/critical-review`, `skills/research`, `skills/pr-review`, `skills/overnight`, `skills/dev`, `skills/backlog`, `skills/diagnose`.
    - A note: "orthogonal to #050 output floor compliance" (or equivalent phrase including the literal substring `orthogonal` and `#050`).
    - A note: "verification strategy to be resolved during refine" (or equivalent — the literal substring `refine` must appear in the verification-TBD context).
    - An optional flag that `dev` DV1/DV2 are bonus candidates for consideration during the new ticket's refine phase.
- **Verification**: Four binary checks, all must pass.
  - (a) **File exists with expected pattern**: `ls backlog/[0-9]*-apply-anthropic-migration-rewrite-table*.md | wc -l | tr -d ' '` returns a value ≥ 1. (Use `≥ 1` rather than `= 1` so prior attempts do not permanently trip verification; Task 1 should still target exactly one new ticket but any residual files from aborted prior runs do not block progress.)
  - (b) **Frontmatter fields set**: On the new file, all four of the following greps return ≥ 1:
    - `grep -cE '^type: chore' <new-file>`
    - `grep -cE '^priority: low' <new-file>`
    - `grep -cE '^parent: "?49"?' <new-file>` (create-backlog-item writes parent values as quoted strings)
    - `grep -cE 'output-efficiency' <new-file>` (tag present — anywhere in the file is acceptable; the `update-item` call puts it in frontmatter)
  - (c) **Body content landed**: On the new file, both of these greps return ≥ 1:
    - `grep -c 'Anthropic migration rewrite table' <new-file>`
    - `grep -c 'imperative-intensity' <new-file>`
  - (d) **Index regenerated**: `grep -c 'Apply Anthropic migration' backlog/index.md` returns ≥ 1 (the `create-backlog-item` script regenerates the index as a side effect; index.md is keyed by title, not filename slug, so we grep the title).
- **Status**: [x] complete — created #059, commit bc5289c. Verification bugs fixed post-hoc: (b3) `^parent: "49"` quoted form; (d) grep by title not slug. All underlying state correct.

### Task 2: Write the DR-6 answer note
- **Files**: `lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md`
- **What**: Create the DR-6 completion note documenting the stress-test answer with a pointer to `research.md` (no duplication), a record of deferred items (`dev` DV1/DV2), and a cross-link to the new backlog ticket from Task 1.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Structure:
    1. `# DR-6 Stress-Test Gate: Answer`
    2. `## Question` — quote the DR-6 question from `research/agent-output-efficiency/research.md` DR-6 section (near line 189). Verbatim quote: "Before adding output constraints, stress-test each skill by removing verbose-by-default instructions and measuring whether Opus 4.6 produces acceptable output on its own. Some skills may need subtraction (removing verbose instructions), not addition (adding brevity constraints)."
    3. `## Empirical Answer` — one short paragraph stating the result. Required key phrase (must appear verbatim for spec R1 verification): `zero high-confidence removal candidates`. The paragraph should explain that this audit applied #052's original rubric against 9 skills across codebase, web, requirements, tradeoffs, and adversarial review, and every initial "remove" verdict was overturned by the adversarial pass identifying load-bearing value the grep-based analysis missed — defense-in-depth disclosures, output-channel directives, control flow gates, sub-agent targeting for Sonnet/Haiku, Opus 4.6 warmth counter-weight, and human-facing morning-review consumers.
    4. `## Pointer to Rationale` — reference `lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/research.md` per-skill candidate sections (L1-L4, D1, CR1-CR2, R1-R3, PR1, O1-O2, DG1-DG3) and the adversarial review findings. Quote the supporting phrase from research.md: "*None with high confidence.*" Explicitly state: research.md is the authoritative rationale archive — the DR-6 note is a pointer, not a duplicate.
    5. `## Deferred Candidates` — record BOTH `dev` DV1 (lines 89-90) AND `dev` DV2 (lines 116-118) as moderate-confidence candidates that survived adversarial review. Explain they are deferred to the new imperative-intensity rewrite ticket as bonus candidates. The section must mention both `DV1` and `DV2` by name so verification can confirm both were documented.
    6. `## Implication for Epic` — state that this closes the DR-6 gate with a negative result: removing verbose-by-default instructions alone is NOT sufficient to control Opus 4.6 skill prompt output. Downstream tickets (#053 subagent output formats, #054+ compression) remain necessary. The epic intervention roadmap should proceed with those.
    7. `## Follow-Up Ticket` — link to the new backlog ticket from Task 1 using the exact filename captured during Task 1. The link should be a wikilink or filename reference — the literal filename must appear.
  - Writing style: prose, compact, no bullet sprawl. Target ~60-100 lines of markdown.
  - Do NOT duplicate content from research.md. When in doubt, point.
- **Verification**: Four binary checks, all must pass.
  - (a) **File exists**: `test -f lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` exits 0.
  - (b) **Key phrase present**: `grep -c 'zero high-confidence' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns ≥ 1. (Previously `= 1` — relaxed per critical-review finding on brittle thresholds.)
  - (c) **Both deferred candidates documented**: `grep -c 'DV1' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns ≥ 1 AND `grep -c 'DV2' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns ≥ 1. (Both must pass — the single-grep `DV1|DV2` check from the prior plan only caught one of them.)
  - (d) **Research.md pointer + exact cross-link to Task 1 filename**: `grep -c 'research\.md' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns ≥ 1 AND the filename captured during Task 1 appears verbatim in `dr6-answer.md` (checked via `grep -F "<task-1-filename-basename>" lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns a non-empty result). The `-F` flag ensures exact filename matching, not regex.
- **Status**: [x] complete — dr6-answer.md written, commit 259fc06. All four verifications pass.

### Task 3: Add plan and dr6-answer artifacts to lifecycle index.md
- **Files**: `lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/index.md`
- **What**: Update the lifecycle index to include both the `plan` and `dr6-answer` artifacts (plan was skipped by the prior plan-phase protocol step; dr6-answer is new from Task 2). Use targeted Edit operations that read the current state of index.md rather than assuming it.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - **Read-before-edit**: Use the `Read` tool on `lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/index.md` before any Edit operation. The current `artifacts` array state at plan time may be `[research, spec]` or may already contain `plan` if a prior run partially executed. Do not assume — read and branch on actual state.
  - **Edit strategy**: Use the `Edit` tool with targeted old_string/new_string pairs:
    - Update `artifacts: [...]` line to include both `plan` and `dr6-answer` in whatever order preserves existing entries. Skip entries already present.
    - Append body wikilink `- Plan: [[audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/plan|plan.md]]` if not already present.
    - Append body wikilink `- DR-6 Answer: [[audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer|dr6-answer.md]]` if not already present.
    - Update `updated: YYYY-MM-DD` to today's date.
  - Do NOT rewrite the file wholesale unless targeted Edit is not possible.
- **Verification**: Three binary checks, all must pass.
  - (a) **artifacts array includes both new entries**: `grep -cE '^artifacts:.*plan.*dr6-answer|^artifacts:.*dr6-answer.*plan' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/index.md` returns 1 (both tokens appear on the artifacts line).
  - (b) **Wikilinks present in body**: `grep -c 'plan|plan\.md' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/index.md` returns ≥ 1 AND `grep -c 'dr6-answer|dr6-answer\.md' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/index.md` returns ≥ 1.
  - (c) **`updated` field bumped**: `grep -c '^updated: 2026-04-10' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/index.md` returns 1.
- **Status**: [x] complete — index.md updated with dr6-answer artifact and wikilink, commit 2e0b70e. All three verifications pass.

### Task 4: Scope compliance verification (working tree + staged + committed)
- **Files**: (read-only — no file modifications)
- **What**: Verify that no source files outside the permitted paths have been modified by the implementation, across all three git states (working tree, staged, committed). Produces a pass/fail signal for the review phase.
- **Depends on**: [1, 2, 3]
- **Complexity**: trivial
- **Context**:
  - The prior plan used `git diff --name-only main..HEAD` which only covers committed changes. Per critical-review finding, this misses staged-but-uncommitted and unstaged modifications that sit in the working tree during implementation. Use `git status --porcelain` instead — it covers all three states.
  - Allowed path prefixes (any of these is OK):
    - `lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/`
    - `backlog/`
  - Any path outside those prefixes is a scope violation per spec R3.
  - `git status --porcelain` output format: first two characters are status codes (e.g., `??` untracked, ` M` unstaged-modified, `M ` staged-modified, `A ` staged-added), then a space, then the path. Strip the status prefix before path-matching.
- **Verification**: `git status --porcelain | awk '{print $2}' | grep -vE '^(lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/|backlog/)' | wc -l | tr -d ' '` returns 0 — pass if the count is 0 (no out-of-scope modifications). If the count is > 0, list the offending paths by running `git status --porcelain | awk '{print $2}' | grep -vE '^(lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/|backlog/)'` and surface them to the user.
- **Status**: [x] complete — verification passed inline (0 out-of-scope paths). Read-only task with no commit artifact; executed by orchestrator as the scope gate before phase transition.

## Verification Strategy

After all 4 tasks complete, a whole-feature end-to-end check:

1. **Deliverable exists**: `test -f lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` exits 0.
2. **New backlog ticket exists with correct frontmatter**: There exists at least one file matching `backlog/[0-9]*-apply-anthropic-migration-rewrite-table*.md` AND that file has `type: chore`, `priority: low`, and `parent: 49` in its frontmatter (all three greps return ≥ 1).
3. **Scope compliance (all git states)**: `git status --porcelain | awk '{print $2}' | grep -vE '^(lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/|backlog/)' | wc -l | tr -d ' '` returns 0.
4. **Index.md reflects deliverables**: `grep -cE 'plan.*dr6-answer|dr6-answer.*plan' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/index.md` returns 1 (both artifacts on the artifacts line).
5. **DR-6 answer contains required content**: `grep -c 'zero high-confidence' lifecycle/archive/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns ≥ 1; `grep -c 'DV1' ...dr6-answer.md` returns ≥ 1; `grep -c 'DV2' ...dr6-answer.md` returns ≥ 1; the Task 1 filename appears verbatim in dr6-answer.md.
