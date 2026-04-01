---
audience: agent
---

# Claude Code Skills Reference

Agent-facing reference for building and configuring Claude Code skills. Loaded when creating or editing skills.

Skills follow the [Agent Skills](https://agentskills.io) open standard. Claude Code extends it with invocation control, subagent execution, and dynamic context injection.

## Frontmatter Fields (Complete)

All fields are optional. `description` is strongly recommended.

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `name` | string | Display name in `/` menu. Lowercase letters, numbers, hyphens only (max 64 chars). Defaults to directory name. | `code-review` |
| `description` | string | **Most critical field.** Determines auto-triggering. Include exact trigger phrases. If omitted, uses first paragraph of markdown content. | See below |
| `argument-hint` | string | Autocomplete hint after `/skill-name` | `[issue-number]`, `<topic> [--flag]` |
| `allowed-tools` | CSV | Tools Claude can use without asking permission when skill is active | `Read, Write, Edit, Bash, Grep` |
| `disable-model-invocation` | bool | Prevents auto-triggering. Only manual `/slash` invocation. Use for side-effect-heavy workflows. | `true` |
| `user-invocable` | bool | Set `false` to hide from `/` menu. **Note:** only controls menu visibility, NOT Skill tool access. Use `disable-model-invocation: true` to block programmatic invocation. | `false` |
| `model` | string | Pin skill to a specific model | `sonnet`, `opus`, `haiku` |
| `context` | string | Set to `fork` to run in a forked subagent context | `fork` |
| `agent` | string | Subagent type when `context: fork` is set. Options: `Explore`, `Plan`, `general-purpose`, or custom from `.claude/agents/` | `Explore` |
| `hooks` | object | Hooks scoped to this skill's lifecycle | See hooks docs |

## Invocation Behavior

| Frontmatter | You can invoke | Claude can invoke | When loaded into context |
|-------------|---------------|-------------------|--------------------------|
| (default) | Yes | Yes | Description always in context, full skill loads when invoked |
| `disable-model-invocation: true` | Yes | No | Description NOT in context, full skill loads when you invoke |
| `user-invocable: false` | No | Yes | Description always in context, full skill loads when invoked |

## Description Field (CRITICAL)

The description is the **only thing Claude sees at startup** to decide whether to auto-trigger a skill. Vague descriptions = skill never fires.

### Pattern: Include Exact Trigger Phrases

```yaml
---
name: hook-management
description: This skill should be used when the user asks to "create a hook",
  "add a PreToolUse hook", "validate tool use", "implement prompt-based hooks",
  or mentions hook events (PreToolUse, PostToolUse, Stop).
---
```

### Rules for Descriptions

- Use **third-person** format: "This skill should be used when..."
- Include **exact phrases** users would say
- Include **file patterns** or **keywords** that indicate relevance
- Be **concrete and specific** — not abstract or buzzword-heavy
- Keep concise — descriptions compete for the 2% context budget

## Description Budget

- Total budget: **2% of context window** (fallback: 16,000 characters)
- Shared across ALL skills (global + project)
- Check with `/context` command for warnings
- Override: `SLASH_COMMAND_TOOL_CHAR_BUDGET` env var
- If over budget: skills silently stop loading
- **Practical limit**: ~20-30 curated skills before budget pressure

## Where Skills Live (Precedence)

Higher-priority locations win when skills share the same name:

| Priority | Location | Path | Applies to |
|----------|----------|------|------------|
| 1 (highest) | Enterprise | Via managed settings | All users in org |
| 2 | Personal | `~/.claude/skills/<name>/SKILL.md` | All your projects |
| 3 (lowest) | Project | `.claude/skills/<name>/SKILL.md` | This project only |
| — | Plugin | `<plugin>/skills/<name>/SKILL.md` | Where plugin enabled (namespaced `plugin-name:skill-name`, no conflicts) |

### Additional Discovery

- **Nested directories**: Editing files in `packages/frontend/` also discovers skills from `packages/frontend/.claude/skills/`
- **`--add-dir`**: Skills from directories added via `--add-dir` auto-load with live change detection (editable during session)

## Skills and Commands Are Unified

A file at `.claude/commands/review.md` and a skill at `.claude/skills/review/SKILL.md` both create `/review` and work the same way. Existing `.claude/commands/` files keep working. If a skill and command share the same name, the skill takes precedence. Skills are recommended since they support supporting files, auto-triggering, and frontmatter.

## Progressive Disclosure (3 Levels)

| Level | When Loaded | What | Size Target |
|-------|-------------|------|-------------|
| 1. Frontmatter | **Always** (startup) | `name` + `description` only | ~100 tokens per skill |
| 2. SKILL.md body | On trigger (auto or `/slash`) | Instructions, steps, constraints | <500 lines |
| 3. Resources | On demand (explicit `Read`) | `references/`, `examples/`, `scripts/` | No limit |

### Directory Structure

```
skills/<skill-name>/
├── SKILL.md              # Frontmatter + instructions (Level 1+2)
├── references/           # Deep-dive docs, loaded on demand (Level 3)
│   ├── api-patterns.md
│   └── gotchas.md
├── examples/             # Code examples, templates
│   └── manifest.yaml
└── scripts/              # Helper scripts
    └── validate.sh
```

Reference supporting files from SKILL.md so Claude knows when to load them:
```markdown
## Additional resources
- For complete API details, see [reference.md](reference.md)
- For usage examples, see [examples.md](examples.md)
```

## String Substitutions

| Variable | Description |
|----------|-------------|
| `$ARGUMENTS` | All arguments passed when invoking. If not in content, appended as `ARGUMENTS: <value>` |
| `$ARGUMENTS[N]` | Specific argument by 0-based index: `$ARGUMENTS[0]` for first |
| `$N` | Shorthand for `$ARGUMENTS[N]`: `$0` for first, `$1` for second |
| `${CLAUDE_SESSION_ID}` | Current session ID. Useful for logging, session-specific files |
| `${CLAUDE_SKILL_DIR}` | Directory containing the skill's SKILL.md. Use to reference bundled scripts/files regardless of cwd |

## Dynamic Context Injection

The `!`command`` syntax runs shell commands **before** skill content reaches Claude. Output replaces the placeholder.

```yaml
---
name: pr-summary
description: Summarize changes in a pull request
context: fork
agent: Explore
---

## Pull request context
- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`
- Changed files: !`gh pr diff --name-only`

Summarize this pull request...
```

This is preprocessing — Claude only sees the final rendered output.

## Extended Thinking

Include the word **"ultrathink"** anywhere in skill content to enable extended thinking mode.

## context: fork

Runs the skill in an isolated subagent. The skill content becomes the prompt. The subagent won't have conversation history.

```yaml
---
name: deep-research
description: Research a topic deeply
context: fork
agent: Explore
---
```

**Only makes sense for skills with explicit task instructions.** Guidelines without a task produce no meaningful output.

### Skills + Subagents Relationship

| Approach | System prompt | Task | Also loads |
|----------|--------------|------|------------|
| Skill with `context: fork` | From agent type (`Explore`, `Plan`, etc.) | SKILL.md content | CLAUDE.md |
| Subagent with `skills` field | Subagent's markdown body | Claude's delegation message | Preloaded skills + CLAUDE.md |

## allowed-tools Field

Restricts which tools the skill can access. If omitted, all tools are available.

```yaml
# Read-only skill
allowed-tools: Read, Glob, Grep, Bash

# Full editing skill
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent

# With MCP tools
allowed-tools: Read, Write, Edit, Bash, mcp__plugin_perplexity_perplexity__perplexity_research
```

## Permission Rules for Skills

Control which skills Claude can invoke via `/permissions`:

```text
# Allow only specific skills
Skill(commit)        # exact match
Skill(review-pr *)   # prefix match with any args

# Deny specific skills
Skill(deploy *)

# Disable all skills
Skill
```

## model Field

Pin a skill to run on a specific model:

```yaml
model: sonnet   # Implementation — speed
model: opus     # Architecture/planning — quality
model: haiku    # Simple formatting — cost
```

## Bundled Skills

Ship with Claude Code, available in every session:

- **`/simplify`**: Reviews recently changed files for reuse/quality/efficiency, spawns 3 parallel review agents, applies fixes
- **`/batch <instruction>`**: Orchestrates large-scale parallel changes across codebase, each unit in an isolated worktree with its own PR
- **`/debug [description]`**: Troubleshoots current session by reading debug log
- **`/claude-api`**: Loads Claude API + Agent SDK reference for your project's language

## Pattern: Knowledge/Action Skill Split

When a skill has both reference data (mappings, field IDs, conventions) and side-effect-heavy actions (creating tickets, deploying, sending messages), split it into two paired skills:

| Role | Frontmatter | Trigger | Purpose |
|------|------------|---------|---------|
| **Knowledge** skill | `user-invocable: false` | Auto-triggers on keywords | Injects reference data into context via `!cat` |
| **Action** skill | `disable-model-invocation: true` | Manual `/slash` only | Executes the workflow using injected knowledge |

### Why Split?

- **Knowledge auto-loads.** When the agent encounters relevant context (e.g., a ticket key), the knowledge skill fires and loads reference data — no manual invocation needed.
- **Actions stay guarded.** Side-effect-heavy workflows (creating issues, transitioning status) only run when explicitly requested.
- **Reference data is shared.** Both skills reference the same files, so knowledge stays in one place.

### Structure

```
skills/
├── my-domain-guide/          # Knowledge skill (auto-triggers)
│   └── SKILL.md              # user-invocable: false, !cat injects reference
├── my-domain/                # Action skill (manual /slash)
│   ├── SKILL.md              # disable-model-invocation: true, workflow steps
│   └── reference/            # Shared reference data
│       ├── knowledge.md      # Mappings, IDs, conventions
│       └── extras.md         # Additional reference
```

### Example Pairs

| Domain | Knowledge skill | Action skill | Reference file |
|--------|----------------|--------------|----------------|
| Hooks | `hooks-guide` | `claude-hooks` | `reference/claude-hooks.md` |
| Skills | `skills-guide` | `create-skill` | `reference/claude-skills.md` |
| Slack | `slack-app-guide` | `slack-app` | `reference/slack-apps.md` |
| Research | `learn-topic-guide` | `learn-topic` | `reference/topic-research.md` |
| Jira | `engs-jira-guide` | `engs-jira` | `skills/engs-jira/reference/engs-jira-knowledge.md` |

### When to Use This Pattern

Use the split when a skill has **both**:
1. Reference data the agent should know about passively (mappings, conventions, field IDs)
2. Actions with real-world side effects (creating resources, sending messages, modifying state)

**Don't split** when:
- The skill is purely informational (just make it a knowledge skill)
- The skill is purely action-based with no reusable reference data
- The reference data is tiny enough to not warrant a separate skill

### Knowledge Skill Template

```yaml
---
name: my-domain-guide
description: This skill provides [domain] knowledge and should auto-load when
  the user mentions [exact trigger phrases], [keywords], or [file patterns].
user-invocable: false
allowed-tools: Read, Grep, Glob
---

# [Domain] Reference

!`cat ~/.claude/path/to/reference.md`
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Vague description ("helps with stuff") | Include exact trigger phrases in third-person |
| Too many global skills (>30) | Curate to 20-30; move niche skills to project scope |
| All content in SKILL.md | Split reference material to supporting files |
| Missing `disable-model-invocation` on destructive skills | Add it for deploy, delete, reset workflows |
| Not testing auto-trigger | Test by prompting naturally, not just `/slash` |
| Duplicate descriptions across skills | Make each description unique with specific trigger phrases |
| Forgetting `allowed-tools` on sensitive skills | Restrict to minimum needed tools |
| Using `context: forked` instead of `context: fork` | The correct value is `fork` |
| Missing `argument-hint` on skills that accept arguments | Add `argument-hint: <signature>` to frontmatter so users get autocomplete hints |
| Adding `disable-model-invocation: true` to callee skills | This blocks the Skill tool entirely — do not add to skills called programmatically by other skills (commit, pr, retro, etc.) |

## Skill Description Audit Checklist

When writing or reviewing a skill description:

1. Does it include exact phrases a user would say?
2. Is it in third-person format ("This skill should be used when...")?
3. Is it specific enough to distinguish from other skills?
4. Does it mention relevant file types, tools, or keywords?
5. Is it concise enough to fit in the 2% budget with all other skills?
