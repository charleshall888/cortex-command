# Specification: Fix skill sub-file path bug across all skills

## Problem Statement

Skills that include sub-files (e.g., `references/plan.md`) currently reference them with bare relative paths in SKILL.md. Claude Code resolves these paths against the **current working directory** of the project being worked in — not the skill's own directory. This means `references/plan.md` tries to read `{project-cwd}/references/plan.md`, which doesn't exist in most projects (including cortex-command itself, where sub-files live under `skills/lifecycle/references/`, not at the project root). The result is a silent file-not-found failure that breaks skill sub-file loading from any project.

The bug exists at two levels:
1. **SKILL.md → sub-file**: SKILL.md uses a relative path to load a sub-file.
2. **Sub-file → sub-file**: A reference file loaded by SKILL.md itself uses a relative path to load another reference file.

Both levels break for the same reason and must both be fixed.

## Fix Mechanisms

**For SKILL.md bodies**: Use `${CLAUDE_SKILL_DIR}` — a string substitution introduced in Claude Code v2.1.69, applied as a full-body text replacement before Claude sees the SKILL.md content (frontmatter excluded). It expands to the skill's own installation directory.
```
Read `${CLAUDE_SKILL_DIR}/references/plan.md`
→ Read `/Users/…/.claude/skills/lifecycle/references/plan.md`
```

**For reference files** (`references/*.md`): `${CLAUDE_SKILL_DIR}` is **not** substituted in files Claude reads via the Read tool — only in SKILL.md bodies. Use absolute paths with tilde expansion instead:
```
Read `~/.claude/skills/lifecycle/references/clarify-critic.md`
```
`~` expands to the home directory on any machine; `~/.claude/skills/` is the standard personal skill installation location. This is portable across machines.

## Definition: File-Load Instruction

A **file-load instruction** is any line that directs Claude to read a specific file as part of executing the skill's protocol. Includes:
- Prose: "Read `references/plan.md` and follow its protocol"
- Backtick: `` read `references/walkthrough.md` ``
- Markdown link used as instruction: `[clarify.md](references/clarify.md)` in a table or list row directing Claude to read or follow the file

**Illustrative/structural content** describes a path as an example of a directory convention without directing Claude to read that file during execution. When in doubt, treat as a file-load instruction — **except**: content inside fenced code blocks (`` ``` ... ``` ``) is always illustrative, regardless of the language used inside the block.

## Requirements

### SKILL.md files

1. **SKILL.md audit complete**: All SKILL.md files with relative file-load instructions are identified and fixed.
   - Acceptance: Run all three of the following. All must pass before the work is considered complete.
     - (a) `grep -rn 'references/' skills/*/SKILL.md` — for every match, classify per the definition above. No bare relative path used as a file-load instruction may remain.
     - (b) `grep -rn 'read \`[^$~]' skills/*/SKILL.md` — catches load instructions not starting with `${CLAUDE_SKILL_DIR}` or `~`. Fix any found.
     - (c) `grep -rn '](references/' skills/*/SKILL.md` — catches unfixed markdown link hrefs. Must return zero output.

2. **Own-skill SKILL.md references fixed**: Every file-load instruction in a SKILL.md referencing a sub-file within the same skill uses `${CLAUDE_SKILL_DIR}`:
   ```
   Read `${CLAUDE_SKILL_DIR}/references/plan.md`
   ```

3. **Cross-skill SKILL.md references fixed**: File-load instructions referencing sub-files from another skill use path traversal:
   ```
   Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md`
   ```
   **Constraint**: valid only for personal skills installed under `~/.claude/skills/` at one directory depth. In this repo, only `refine` uses cross-skill refs — both `refine` and `lifecycle` are personal skills, so this constraint is met. Do not use this pattern for plugin skills.

4. **Markdown link display text**: Display text in markdown links must not contain a bare path that could be misread as a file location. Use the filename only:
   - Correct: `[plan.md](${CLAUDE_SKILL_DIR}/references/plan.md)`
   - Incorrect: `[references/plan.md](${CLAUDE_SKILL_DIR}/references/plan.md)`

   If `${CLAUDE_SKILL_DIR}` substitution in markdown hrefs proves unreliable, use the `!cat` injection form instead (inlines file content directly at load time):
   ```
   !`cat ${CLAUDE_SKILL_DIR}/references/plan.md`
   ```

### Reference files

5. **Reference file audit complete**: All `references/*.md` files with bare relative file-load instructions are identified and fixed.
   - Acceptance: `grep -rn 'references/' skills/*/references/*.md` — for every match that is a file-load instruction, confirm it uses either `~/.claude/skills/` or `${CLAUDE_SKILL_DIR}` (the latter won't work here, but flag if found). No bare relative path used as a file-load instruction may remain.

6. **Reference file cross-references fixed**: Bare path references within reference files use absolute paths with tilde:
   ```
   Read `~/.claude/skills/lifecycle/references/clarify-critic.md`
   ```

### Documentation

7. **Convention documented in `claude/reference/claude-skills.md`**: A new entry in the "Common Mistakes" table including:
   - Mistake: `Relative sub-file path (references/foo.md) or repo-relative path (skills/X/references/foo.md)`
   - Fix: `` Use ${CLAUDE_SKILL_DIR}/references/foo.md in SKILL.md; use ~/.claude/skills/{skill}/references/foo.md in reference files ``
   - Include: the reason (paths resolve against CWD, not skill dir), the cross-skill pattern (`${CLAUDE_SKILL_DIR}/../other-skill/` — personal skills only), the note that `${CLAUDE_SKILL_DIR}` only works in SKILL.md body (not frontmatter hooks, not reference files), and the `!cat` injection alternative.

8. **Convention documented in `claude/reference/context-file-authoring.md`**: A brief section covering:
   - Rule: Use `${CLAUDE_SKILL_DIR}/references/foo.md` in SKILL.md; use `~/.claude/skills/{skill}/references/foo.md` in reference files.
   - Reason: Claude Code resolves bare paths against the project CWD. `${CLAUDE_SKILL_DIR}` substitution only applies to SKILL.md bodies.
   - Pointer to `claude/reference/claude-skills.md` Common Mistakes for the full pattern.

## Non-Requirements

- Do not use repo-relative paths (`skills/lifecycle/references/plan.md`) — only work from cortex-command's CWD.
- Do not change illustrative/structural content in `skills/skill-creator/SKILL.md` — fenced code block content is always illustrative. The real load instructions are the `See references/…` lines in Step 4 and line 243.
- Do not change example code blocks in `claude/reference/claude-skills.md` (the `[reference.md](reference.md)` example).
- Do not change runtime path templates containing variables or globs (e.g., `lifecycle/{feature}/research.md`, `backlog/*.md`).
- Do not use `${CLAUDE_SKILL_DIR}` in YAML frontmatter hook commands or in reference files — not substituted in those contexts.

## Files to Change

### SKILL.md files (9)

| File | Change type |
|------|-------------|
| `skills/requirements/SKILL.md` | Own-skill refs |
| `skills/pr-review/SKILL.md` | Own-skill refs |
| `skills/morning-review/SKILL.md` | Own-skill refs |
| `skills/lifecycle/SKILL.md` | Own-skill refs (table; use filename-only display text) |
| `skills/skill-creator/SKILL.md` | Own-skill load instructions only: Step 4 `See references/…` lines + line 243. Fenced code blocks and directory-tree prose are illustrative — do not change. |
| `skills/backlog/SKILL.md` | Own-skill refs |
| `skills/discovery/SKILL.md` | Own-skill refs |
| `skills/ui-brief/SKILL.md` | Own-skill refs |
| `skills/refine/SKILL.md` | Cross-skill refs → `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` and `…/specify.md` |

### Reference files (7)

| File | Line | Current path | Fixed path |
|------|------|--------------|------------|
| `skills/lifecycle/references/clarify.md` | 49 | `skills/lifecycle/references/clarify-critic.md` | `~/.claude/skills/lifecycle/references/clarify-critic.md` |
| `skills/lifecycle/references/specify.md` | 138 | `references/orchestrator-review.md` | `~/.claude/skills/lifecycle/references/orchestrator-review.md` |
| `skills/lifecycle/references/research.md` | 187 | `references/orchestrator-review.md` | `~/.claude/skills/lifecycle/references/orchestrator-review.md` |
| `skills/lifecycle/references/plan.md` | 226 | `references/orchestrator-review.md` | `~/.claude/skills/lifecycle/references/orchestrator-review.md` |
| `skills/discovery/references/research.md` | 124 | `references/orchestrator-review.md` | `~/.claude/skills/discovery/references/orchestrator-review.md` |
| `skills/skill-creator/references/orchestrator-patterns.md` | 64 | `references/state-patterns.md` | `~/.claude/skills/skill-creator/references/state-patterns.md` |
| `skills/skill-creator/references/workflows.md` | 127 | `[references/output-patterns.md](references/output-patterns.md)` | `[output-patterns.md](~/.claude/skills/skill-creator/references/output-patterns.md)` |

Plus documentation in `claude/reference/claude-skills.md` and `claude/reference/context-file-authoring.md`.

## Technical Constraints

- All edits are to files under `skills/` and `claude/reference/` — within the cortex-command repo.
- The symlink architecture means repo files are the canonical source; never edit `~/.claude/skills/` destinations directly.
- Run all verification commands in Requirement 1 plus Requirement 5 before declaring the work complete.

## Open Decisions

None.
