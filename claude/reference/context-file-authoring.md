---
audience: agent
---

# Context File Authoring Rules

Agent-facing reference. Loaded when modifying CLAUDE.md, AGENTS.md, `.mdc`, or knowledge base files.

## Decision Rule

Before adding any line to a context file:

> **Does this name a specific tool, command, path, or constraint unique to this repository that the agent would get wrong without it?**

If no → delete it.

## What to Include / Exclude

| Include | Exclude |
|---------|---------|
| Repo-specific tool commands (`uv run pytest`, `mage testProject`) | Codebase overviews ("This is a Go monorepo...") |
| Non-obvious constraints agents get wrong without | Philosophy ("We value clean code...") |
| Critical path/config that's invisible from code | Generic coding guidelines ("Use meaningful names") |
| Proprietary library APIs (zero training data) | File/directory structure listings |
| Version-gated features or breaking changes | README duplication |
| Debugging/test commands with exact flags | Motivation/rationale blocks |
| Conditional loading triggers to reference files | "When to use this tool" preambles |

**Paper evidence:** Repo-specific tool mentions → 2.5x agent usage. Codebase overviews → 100% included in LLM files, 0% improvement.

## Progressive Disclosure Structure

**Core file** (~50-70 lines, always loaded):
- Commands: exact build/test/lint invocations
- Constraints: things agents get wrong without these
- Conditional loading: trigger table pointing to reference files

**Reference files** (~200-400 lines each, loaded on demand):
- Detailed patterns for one topic
- Org-specific code examples
- Internal library usage

Token cost scales with task scope. Simple tasks load ~70 lines; complex tasks load ~70 + one reference file.

## CLAUDE.md Template

```markdown
## Commands
<exact build/test/lint commands>

## Constraints
<things agents get wrong without these>

## Conditional Loading
<trigger → reference file path>
```

Nothing else. No overview, no philosophy, no file structure map.

## Prose vs Code Examples

- **Known pattern** → prose rule: `Always use %w (not %v) in fmt.Errorf`
- **Org-specific / novel pattern** → code example showing exact API usage

## Verbosity Tax

Context files caused **14-22% increase in reasoning tokens** per task. Broad instructions like "read the codebase first" or "run the full test suite" multiply cost without improving success.

## Modifying Existing Knowledge Base Files

When trimming or restructuring AGENTS.md, CLAUDE.md, reference files, or skills:

1. **Safe to remove**: Motivational preambles ("why this exists"), rationale blocks ("Real-World Impact"), codebase overviews, philosophy sections, todo list templates
2. **Safe to remove from skills**: "Why use this?" sections, verbose process explanations agents don't need, duplicate content already in CLAUDE.md
3. **Keep**: Actual steps/instructions, behavioral guardrails (red flags, "stop and think" triggers), conditional loading triggers, tool commands, non-obvious constraints
4. **For non-Python languages (Go, Java, React)**: The paper only tested Python — be conservative about removing code examples and pattern explanations. Subtle gotchas agents get wrong should stay even if they're "generic" knowledge
5. **Don't confuse human docs with agent docs**: READMEs, onboarding guides, and setup instructions are for humans — the paper's token optimization findings don't apply to them

## Red Flags — STOP if you're about to:

- Add a "Project Overview" or "Architecture" section
- Write "We value..." or "Our philosophy..."
- List the directory structure
- Duplicate content from README.md
- Add generic language patterns the agent already knows
- Include a section explaining what CLAUDE.md / AGENTS.md is
- Add motivation or rationale blocks explaining *why* a rule exists
- Create a context file longer than 70 lines without using progressive disclosure
