# Prompt Contract Patterns

Reference for the optional contract fields in SKILL.md frontmatter. These fields
declare what a skill needs, what it produces, and what must be true before it runs.

## Schema

Three optional YAML list fields, added alongside `name` and `description`:

```yaml
---
name: skill-name
description: What the skill does and when to trigger it
inputs:
  - "feature: string (required) — the feature slug"
  - "priority: enum (optional) — critical|high|medium|low"
outputs:
  - "lifecycle/{{feature}}/research.md — research findings"
  - "lifecycle/{{feature}}/spec.md — feature specification"
preconditions:
  - "Must be run from the project root"
  - "backlog/ directory must exist with at least one item"
---
```

### Field definitions

| Field | Purpose | When to use |
|-------|---------|-------------|
| `inputs` | What the skill needs at invocation time | When the skill requires caller-provided values |
| `outputs` | What the skill produces (files, artifacts, side effects) | When the skill creates or modifies artifacts |
| `preconditions` | Environment conditions that must be true before invocation | When the skill depends on external state |

All three fields are optional. A simple skill with no parameters and no meaningful
file output (like `commit`) can omit all three. A complex skill (like `lifecycle`)
will typically declare all three.

### Entry format

Each entry is a flat string with a consistent structure:

```
inputs:    "name: type (required|optional) — description"
outputs:   "path-or-artifact — description"
preconditions: "Plain-language condition statement"
```

**inputs** entries follow `name: type (qualifier) — description`:
- `name` — the parameter name, matching what the body references
- `type` — `string`, `enum`, `path`, `integer`, or `list`
- `(required)` or `(optional)` — whether invocation fails without it
- `— description` — brief explanation, including allowed values for enums

**outputs** entries follow `artifact — description`:
- `artifact` — a file path, directory, or named side effect
- `— description` — what the artifact contains or represents

**preconditions** entries are plain-language condition statements. They describe
what must be true in the environment, not what the skill checks programmatically.

## Variable Syntax: `{{double}}` vs `{single}` Braces

Two distinct substitution conventions exist across skills. Confusing them causes
either runtime errors or silent mis-rendering.

### `{{variable}}` — Agent substitutes at invocation time

Used in **SKILL.md frontmatter and body**. The agent reads the template, resolves
the variable from context (user input, conversation state, environment), and
substitutes before acting.

```yaml
outputs:
  - "lifecycle/{{feature}}/research.md — research findings"
  - "lifecycle/{{feature}}/spec.md — feature specification"
```

When the user invokes `/lifecycle auth-tokens`, the agent substitutes `{{feature}}`
→ `auth-tokens` and knows the skill will produce `lifecycle/auth-tokens/research.md`.

### `{variable}` — Python/bash renders before the agent sees it

Used in **pipeline prompts, overnight runner templates, and scripts** — anywhere
Python `str.format()` or bash variable expansion fills values before the prompt
reaches the agent. By the time the agent reads the text, single-brace variables
are already resolved.

```python
prompt = "Implement {feature} following the plan in lifecycle/{feature}/plan.md"
rendered = prompt.format(feature="auth-tokens")
# Agent sees: "Implement auth-tokens following the plan in lifecycle/auth-tokens/plan.md"
```

### When each appears

| Context | Syntax | Who substitutes | When |
|---------|--------|----------------|------|
| SKILL.md frontmatter (`inputs`, `outputs`) | `{{var}}` | Agent | At skill invocation |
| SKILL.md body instructions | `{{var}}` | Agent | While following the skill |
| Pipeline/overnight Python prompts | `{var}` | Python `str.format()` | Before agent receives prompt |
| Bash runner templates | `{var}` or `$VAR` | Bash/envsubst | Before agent receives prompt |

**Rule of thumb**: If the text lives in a SKILL.md file that an agent reads directly,
use `{{double braces}}`. If the text is a template that code renders before passing
to an agent, use `{single braces}`.

## Examples

### Simple skill: commit (no contracts needed)

The `commit` skill takes no explicit inputs (it reads the working tree), produces
a git commit (not a file artifact), and has no meaningful preconditions beyond
"there are changes to commit." Contracts add no value here.

**Before** (current — no contract fields):

```yaml
---
name: commit
description: Create git commits with consistent, well-formatted messages. Use when
  user says "commit", "/commit", "make a commit", "commit these changes", or asks
  to save/checkpoint their work as a git commit.
---
```

**After** (unchanged — contracts omitted intentionally):

```yaml
---
name: commit
description: Create git commits with consistent, well-formatted messages. Use when
  user says "commit", "/commit", "make a commit", "commit these changes", or asks
  to save/checkpoint their work as a git commit.
---
```

The commit skill demonstrates that **contracts are opt-in**. When a skill's interface
is implicit and self-evident, adding empty contract fields would be noise.

### Complex skill: lifecycle (full contracts with `{{feature}}`)

The `lifecycle` skill requires a feature name, produces multiple phase artifacts
in a predictable directory structure, and depends on the project having specific
configuration.

**Before** (current — no contract fields):

```yaml
---
name: lifecycle
description: Structured feature development lifecycle with phases for research,
  specification, planning, implementation, review, and completion. Use when user
  says "/lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/
  review/complete", or wants to build a non-trivial feature with structured phases.
---
```

**After** (with contracts):

```yaml
---
name: lifecycle
description: Structured feature development lifecycle with phases for research,
  specification, planning, implementation, review, and completion. Use when user
  says "/lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/
  review/complete", or wants to build a non-trivial feature with structured phases.
inputs:
  - "feature: string (required) — lowercase-kebab-case feature slug"
  - "phase: enum (optional) — research|specify|plan|implement|review|complete"
outputs:
  - "lifecycle/{{feature}}/research.md — research findings and analysis"
  - "lifecycle/{{feature}}/spec.md — feature specification"
  - "lifecycle/{{feature}}/plan.md — implementation plan with task breakdown"
  - "lifecycle/{{feature}}/review.md — review verdict and feedback"
  - "lifecycle/{{feature}}/events.log — phase transition event log (JSONL)"
preconditions:
  - "Must be run from the project root"
  - "lifecycle/ directory must be writable"
---
```

The `{{feature}}` variable in outputs tells both agents and tooling that these paths
are parameterized — the actual directory depends on the invocation argument.

### Preconditions example: overnight

The `overnight` skill has the richest preconditions because it depends on artifacts
produced by other skills and external infrastructure.

```yaml
---
name: overnight
description: Plan and launch autonomous overnight development sessions...
inputs:
  - name: time-limit
    type: string
    required: false
    description: "Maximum wall-clock duration for the overnight session (e.g. '6h'). Passed as --time-limit to the runner."
outputs:
  - "lifecycle/overnight-plan.md — selected session plan with feature list (active during session)"
  - "lifecycle/overnight-state.json — execution state for the runner (active during session)"
  - "lifecycle/sessions/{SESSION_ID}/ — session archive dir written by runner.sh (plan, state, events log)"
  - "lifecycle/morning-report.md — canonical symlink to the latest session's morning report"
  - "lifecycle/overnight-events.log — canonical symlink to the latest session's events log"
preconditions:
  - "lifecycle/{slug}/spec.md exists for each candidate feature"
  - "backlog/NNN-slug.md files exist with status: refined"
  - "Run from project root"
---
```

Note that preconditions for overnight use `{slug}` (single braces) in the
`lifecycle/{slug}/spec.md` entry because this is a description of a path pattern
where the slug is computed by Python code at runtime — not a template the agent
substitutes. In contrast, the outputs use literal fixed paths because they do not
vary per feature.

## Guidelines for Writing Contracts

1. **Omit contracts when they add no value.** A skill with no parameters and no file
   outputs does not need empty `inputs: []` fields.

2. **Mark required vs optional.** Every input should declare `(required)` or
   `(optional)` so callers know what must be provided.

3. **Use `{{var}}` in outputs for parameterized paths.** This signals that the path
   depends on an input value and helps tooling validate path patterns.

4. **Keep preconditions actionable.** Each precondition should tell the caller what
   to do if it is not met. "backlog/ must contain items" is better than "backlog
   must be ready."

5. **List the primary artifacts, not every intermediate file.** The outputs field
   should capture the durable artifacts a caller cares about, not scratch files or
   internal state.

6. **Match input names to body references.** If the body says "determine the feature
   name from the invocation," the input should be named `feature`, not `name` or
   `slug`.
