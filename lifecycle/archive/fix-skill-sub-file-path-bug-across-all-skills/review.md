# Review: Fix skill sub-file path bug across all skills

## Stage 1: Spec Compliance

### Requirement 1: SKILL.md audit complete
**PASS**

All three acceptance checks pass:
- (a) `grep -rn 'references/' skills/*/SKILL.md` -- every match without `${CLAUDE_SKILL_DIR}` is in `skill-creator/SKILL.md` and is illustrative/structural content: directory tree diagrams (lines 67, 175), section headings (line 89), example listings (lines 94, 295), and prose describing the init script and implementation workflow (lines 317, 349, 353). No bare relative path used as a file-load instruction remains.
- (b) `grep -rn 'read \`[^$~]' skills/*/SKILL.md` -- remaining matches are runtime project-file reads that correctly resolve against project CWD: `backlog/index.md` (dev), `events.log` (lifecycle), `lifecycle/{slug}/spec.md` (overnight), `lifecycle/morning-report.md` (overnight), `requirements/project.md` (requirements). None are skill sub-file references.
- (c) `grep -rn '](references/' skills/*/SKILL.md` -- zero output.

### Requirement 2: Own-skill SKILL.md references fixed
**PASS**

Verified in all 8 skills with own-skill refs:
- `lifecycle/SKILL.md` -- 4 table links (plan, implement, review, complete) use `${CLAUDE_SKILL_DIR}/references/`
- `discovery/SKILL.md` -- 4 refs (auto-scan, clarify, research, decompose) use `${CLAUDE_SKILL_DIR}/references/`
- `skill-creator/SKILL.md` -- 6 load instructions (workflows, output-patterns, contract-patterns, orchestrator-patterns, state-patterns at lines 339-343, and contract-patterns at line 243) use `${CLAUDE_SKILL_DIR}/references/`
- `requirements/SKILL.md` -- 2 refs (gather.md at lines 84, 88) use `${CLAUDE_SKILL_DIR}/references/`
- `pr-review/SKILL.md` -- 2 refs (protocol.md at lines 43, 51) use `${CLAUDE_SKILL_DIR}/references/`
- `morning-review/SKILL.md` -- 3 refs (walkthrough.md at lines 15, 77, 125) use `${CLAUDE_SKILL_DIR}/references/`
- `backlog/SKILL.md` -- 1 ref (schema.md at line 30) uses `${CLAUDE_SKILL_DIR}/references/`
- `ui-brief/SKILL.md` -- 2 refs (design-md-template.md, theme-template.md at lines 57, 66) use `${CLAUDE_SKILL_DIR}/references/`

### Requirement 3: Cross-skill SKILL.md references fixed
**PASS**

`skills/refine/SKILL.md` uses `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` (lines 26, 60, 81) and `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` (line 126). Correct pattern for personal skills installed at one directory depth under `~/.claude/skills/`.

### Requirement 4: Markdown link display text uses filename only
**PASS**

The cycle 1 issue has been fixed. `skills/requirements/SKILL.md` lines 84 and 88 now use display text `[gather.md]` (filename only), not `[references/gather.md]` (path). All other markdown links across all SKILL.md files also use filename-only display text:
- `lifecycle/SKILL.md` lines 268-271: `[plan.md]`, `[implement.md]`, `[review.md]`, `[complete.md]`
- `discovery/SKILL.md` lines 55-57: `[clarify.md]`, `[research.md]`, `[decompose.md]`
- `skill-creator/references/workflows.md` line 127: `[output-patterns.md]`

### Requirement 5: Reference file audit complete
**PASS**

`grep -rn 'references/' skills/*/references/*.md` returns 8 matches. Seven are file-load instructions using absolute tilde paths. One (`skills/skill-creator/references/workflows.md:122`) is structural prose describing the `references/` directory convention, not a file-load instruction. No bare relative path used as a file-load instruction remains.

### Requirement 6: Reference file cross-references fixed
**PASS**

All 7 reference files listed in the spec use absolute paths with tilde:
- `skills/lifecycle/references/clarify.md:49` -- `~/.claude/skills/lifecycle/references/clarify-critic.md`
- `skills/lifecycle/references/specify.md:138` -- `~/.claude/skills/lifecycle/references/orchestrator-review.md`
- `skills/lifecycle/references/research.md:187` -- `~/.claude/skills/lifecycle/references/orchestrator-review.md`
- `skills/lifecycle/references/plan.md:226` -- `~/.claude/skills/lifecycle/references/orchestrator-review.md`
- `skills/discovery/references/research.md:124` -- `~/.claude/skills/discovery/references/orchestrator-review.md`
- `skills/skill-creator/references/orchestrator-patterns.md:64` -- `~/.claude/skills/skill-creator/references/state-patterns.md`
- `skills/skill-creator/references/workflows.md:127` -- `~/.claude/skills/skill-creator/references/output-patterns.md` with display text `[output-patterns.md]`

### Requirement 7: Convention documented in claude-skills.md
**PASS**

Common Mistakes table row at line 304 covers all required elements: mistake description (relative and repo-relative paths), fix (CLAUDE_SKILL_DIR in SKILL.md body, tilde paths in reference files), reason (CWD resolution), cross-skill pattern (with personal-skills-only caveat), scope note (not in frontmatter hooks or reference files), and `!cat` injection alternative.

### Requirement 8: Convention documented in context-file-authoring.md
**PASS**

"Skill Sub-File Paths" section at lines 79-85 covers the rule (both path patterns), reason (CWD resolution), and pointer to claude-skills.md Common Mistakes for the full pattern including cross-skill and `!cat` fallback.

### Requirements Compliance
**PASS**

No project-level constraints violated. Changes are limited to `skills/` and `claude/reference/` files within the cortex-command repo. No `${CLAUDE_SKILL_DIR}` used in reference files (confirmed via grep). No illustrative content in skill-creator/SKILL.md was changed. No fenced code block examples were modified.

## Stage 2: Code Quality

### Consistency
All own-skill references use `${CLAUDE_SKILL_DIR}/references/filename.md`. All cross-skill references use `${CLAUDE_SKILL_DIR}/../other-skill/references/filename.md`. All reference file cross-references use `~/.claude/skills/{skill}/references/filename.md`. No mixed patterns.

### Display text convention
Markdown link display text consistently uses filename-only format across all files: lifecycle table (4 links), discovery table (3 links), requirements inline (2 links), and workflows.md (1 link). No path fragments in any display text.

### Documentation completeness
Both documentation entries are concise and actionable. The claude-skills.md entry is a single table row covering all required elements without bloat. The context-file-authoring.md section is 3 lines (rule, reason, pointer) following the file's existing style.

### Non-requirements respected
- No changes to illustrative content in skill-creator/SKILL.md (directory trees, example listings, fenced code blocks all unchanged)
- No changes to example code blocks in claude-skills.md
- No changes to runtime path templates containing variables or globs
- No `${CLAUDE_SKILL_DIR}` in YAML frontmatter or reference files

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 2,
  "issues": []
}
```
