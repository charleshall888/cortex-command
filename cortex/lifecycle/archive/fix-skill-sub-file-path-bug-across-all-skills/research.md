# Research: fix-skill-sub-file-path-bug-across-all-skills

## Epic Reference

Background context from `research/requirements-audit/research.md` (§ "Current skill defects"). This ticket is scoped to the sub-file path bug only — not to the broader requirements accuracy work.

---

## Clarified Intent

Audit all skills in `skills/` for static sub-file references; replace them with the portable `${CLAUDE_SKILL_DIR}` form so they work correctly from any repo; document the convention in `claude/reference/claude-skills.md` and `claude/reference/context-file-authoring.md`.

---

## How Skill Sub-File Path Resolution Actually Works

When a SKILL.md contains an instruction like `Read references/plan.md`, Claude resolves the path **relative to the current working directory** (the project being worked on), not relative to the skill's own directory. This is confirmed by GitHub issue #17741 (filed against v2.1.5, confirmed on v2.1.69), which was closed as "not planned" by Anthropic.

**Actual failure mode**: `references/plan.md` from `wild-light` → tries to read `{wild-light-cwd}/references/plan.md` → file not found. Not a permission prompt — a silent failure or error. The file simply doesn't exist in the invoking project.

**From cortex-command**: `references/plan.md` → tries to read `{cortex-command-cwd}/references/plan.md` → also doesn't exist at the project root. Sub-files live under `skills/lifecycle/references/`, not at the project root. This means the bug likely affects cortex-command too, not just other repos.

## The Correct Fix: `${CLAUDE_SKILL_DIR}`

Introduced in **Claude Code v2.1.69** (March 4, 2026) specifically for this problem. `${CLAUDE_SKILL_DIR}` is a **string substitution** (not a shell/bash environment variable) that Claude Code replaces in SKILL.md content before Claude sees it. It expands to the absolute path of the directory containing the skill's SKILL.md file.

```markdown
Read `${CLAUDE_SKILL_DIR}/references/plan.md`
```
→ becomes at load time →
```markdown
Read `/Users/charlie.hall/.claude/skills/lifecycle/references/plan.md`
```

This absolute path works from any repo. It is the officially documented mechanism for referencing bundled sub-files portably.

**Important caveats:**
- `${CLAUDE_SKILL_DIR}` only works in the SKILL.md **markdown body** — not in YAML frontmatter hook commands (issue #36135, open). Frontmatter substitution is not performed.
- It is not a real shell environment variable. Running `echo $CLAUDE_SKILL_DIR` in a Bash command returns empty.
- Also works with dynamic injection: `` !`cat ${CLAUDE_SKILL_DIR}/references/plan.md` `` inlines the file content directly at load time.

## Cross-Skill References

For skills that reference sub-files from *another* skill (e.g., `refine` referencing `lifecycle`'s `clarify.md`), use path traversal:

```markdown
Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md`
```

`${CLAUDE_SKILL_DIR}` expands to `/Users/charlie.hall/.claude/skills/refine/`, so `/../lifecycle/references/clarify.md` resolves to `/Users/charlie.hall/.claude/skills/lifecycle/references/clarify.md` — the correct absolute path, portable across machines (since `~/.claude/skills/` is the standard skill location).

## Codebase Analysis

### Audit: skills with sub-file load instructions

All occurrences of `references/` in `skills/*/SKILL.md` that are file-load instructions (not illustrative content):

| File | Current reference(s) | Fix |
|------|-----------------------|-----|
| `skills/requirements/SKILL.md` | `references/gather.md` (×2) | `${CLAUDE_SKILL_DIR}/references/gather.md` |
| `skills/pr-review/SKILL.md` | `references/protocol.md` (×2) | `${CLAUDE_SKILL_DIR}/references/protocol.md` |
| `skills/morning-review/SKILL.md` | `references/walkthrough.md` (×3) | `${CLAUDE_SKILL_DIR}/references/walkthrough.md` |
| `skills/lifecycle/SKILL.md` | `references/plan.md`, `references/implement.md`, `references/review.md`, `references/complete.md` (×1 each in table) | `${CLAUDE_SKILL_DIR}/references/{name}.md` |
| `skills/skill-creator/SKILL.md` | `references/workflows.md`, `references/output-patterns.md`, `references/contract-patterns.md` (×2), `references/orchestrator-patterns.md`, `references/state-patterns.md` (×6 load instructions) | `${CLAUDE_SKILL_DIR}/references/{name}.md` |
| `skills/backlog/SKILL.md` | `references/schema.md` (×1) | `${CLAUDE_SKILL_DIR}/references/schema.md` |
| `skills/discovery/SKILL.md` | `references/auto-scan.md`, `references/clarify.md`, `references/research.md`, `references/decompose.md` (×4) | `${CLAUDE_SKILL_DIR}/references/{name}.md` |
| `skills/ui-brief/SKILL.md` | `references/design-md-template.md`, `references/theme-template.md` (×2) | `${CLAUDE_SKILL_DIR}/references/{name}.md` |
| `skills/refine/SKILL.md` | `skills/lifecycle/references/clarify.md` (×2), `skills/lifecycle/references/specify.md` (×1) — cross-skill refs, previously thought compliant but wrong | `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md`, `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` |

**9 files need changes** (including `refine`, previously assessed as compliant — that assessment was incorrect; repo-relative paths also fail from other repos since they resolve against CWD).

### Contextual mentions (no change needed)

`skills/skill-creator/SKILL.md` mentions `references/` as a directory pattern in structural examples — descriptions of convention, not file-load instructions. Leave as-is.

`claude/reference/claude-skills.md` contains a hypothetical example code block with `[reference.md](reference.md)` — documentation text, not an instruction. Leave as-is.

### Where to add the convention

- `claude/reference/claude-skills.md` "Common Mistakes" table — primary, most discoverable by skill authors
- `claude/reference/context-file-authoring.md` — per backlog item, add a brief section

The convention text must include: the rule (`${CLAUDE_SKILL_DIR}` required), the reason (paths resolve against CWD, not skill dir), the cross-skill pattern (`${CLAUDE_SKILL_DIR}/../other-skill/references/foo.md`), and the `!cat` injection alternative.

---

## Open Questions

None.

---

## Reference File Audit

The bug exists at two levels. After fixing SKILL.md, reference files that Claude loads via those fixed paths can themselves contain bare path references to other reference files. `${CLAUDE_SKILL_DIR}` is not substituted in reference file content — only in SKILL.md bodies. The fix for reference files is absolute paths with tilde: `~/.claude/skills/{skill}/references/{file}.md`.

| File | Line | Current (broken) | Fix |
|------|------|------------------|-----|
| `skills/lifecycle/references/clarify.md` | 49 | `` `skills/lifecycle/references/clarify-critic.md` `` | `` `~/.claude/skills/lifecycle/references/clarify-critic.md` `` |
| `skills/lifecycle/references/specify.md` | 138 | `` `references/orchestrator-review.md` `` | `` `~/.claude/skills/lifecycle/references/orchestrator-review.md` `` |
| `skills/lifecycle/references/research.md` | 187 | `` `references/orchestrator-review.md` `` | `` `~/.claude/skills/lifecycle/references/orchestrator-review.md` `` |
| `skills/lifecycle/references/plan.md` | 226 | `` `references/orchestrator-review.md` `` | `` `~/.claude/skills/lifecycle/references/orchestrator-review.md` `` |
| `skills/discovery/references/research.md` | 124 | `` `references/orchestrator-review.md` `` | `` `~/.claude/skills/discovery/references/orchestrator-review.md` `` |
| `skills/skill-creator/references/orchestrator-patterns.md` | 64 | `` `references/state-patterns.md` `` | `` `~/.claude/skills/skill-creator/references/state-patterns.md` `` |
| `skills/skill-creator/references/workflows.md` | 127 | `[references/output-patterns.md](references/output-patterns.md)` | `[output-patterns.md](~/.claude/skills/skill-creator/references/output-patterns.md)` |

---

## Summary

**9 SKILL.md files** and **7 reference files** need path fixes. SKILL.md files use `${CLAUDE_SKILL_DIR}` (substituted at load time). Reference files use `~/.claude/skills/{skill}/references/{file}.md` (absolute paths). `refine/SKILL.md` uses cross-skill traversal (`${CLAUDE_SKILL_DIR}/../lifecycle/references/…`). Convention documentation goes into both `claude/reference/claude-skills.md` and `claude/reference/context-file-authoring.md`. No behavioral changes to any skill — only the path strings used to load sub-files.
