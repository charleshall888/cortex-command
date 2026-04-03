# Workflow Patterns

Reference for structuring multi-step skill bodies. These conventions are used consistently across existing skills — follow them so agents can navigate any skill with the same mental model.

## Pattern 1: Numbered Step Format

**Structure**: Each major step gets a `### Step N: Name` header. Action items are bullets beneath the header. Keep step names short and imperative.

```markdown
## Step 1: Load Context

Read the relevant files before taking any action:
- `path/to/config.md` — project configuration
- `path/to/state.json` — current phase (if exists)

## Step 2: Determine Action

Based on what was loaded, decide what to do next.
[...]

## Step 3: Execute

[...]
```

**When to use numbered steps**: Any skill with 3+ distinct phases of work. Numbering makes it easy for the agent to report progress ("completing Step 2") and for users to resume ("start from Step 3").

**Step granularity**: One step = one coherent unit of work with a clear entry condition and a clear output. Steps should not be so fine-grained that every bullet becomes its own step, nor so coarse that a single step covers unrelated work.

---

## Pattern 2: Substep Notation

**When to use**: A step has two or more mutually exclusive paths. Rather than a nested if/else block in prose, use lettered substeps.

```markdown
## Step 2: Process Request

### Step 2a: New request

If no prior state exists, initialize from scratch:
- Create the state file with default values
- Set phase = "start"

### Step 2b: Resume existing request

If a state file exists, read it and resume:
- Detect current phase from the "phase" field
- Announce: "Resuming from [phase]"
```

**Labeling**: Use `Step Na`, `Step Nb`, etc. At the top of the parent step, describe the branch condition: "If X, follow Step 2a. Otherwise, follow Step 2b."

**Limit nesting**: Substeps go one level deep (`Step 2a`). Do not nest further (`Step 2a-i`). If the logic requires deeper nesting, split into separate top-level steps.

---

## Pattern 3: Conditional Branching

**Pseudocode for deterministic conditions**: When the branch condition is an exact check (file existence, field value, count), write it as pseudocode inside a code block. This eliminates ambiguity about what "if X" means.

```
if lifecycle/{feature}/spec.md exists:
    phase = plan
elif lifecycle/{feature}/research.md exists:
    phase = specify
else:
    phase = research
```

**Prose for judgment-dependent conditions**: When the agent must use judgment to evaluate the condition, write in plain prose. Reserve pseudocode for conditions the agent can evaluate mechanically.

```
If the request is clearly about an existing feature (the user names it, references prior work,
or a matching lifecycle directory exists), resume that feature. If the request describes a
new capability with no prior context, start a new lifecycle.
```

**Avoid hybrid prose-code**: Don't write `if the file "spec.md" exists then...` in prose when a pseudocode block would be clearer. The code block signals "evaluate this exactly"; prose signals "use judgment."

---

## Pattern 4: Pseudocode vs. Prose

| Use pseudocode when | Use prose when |
|---------------------|---------------|
| Checking file existence | Writing a summary or narrative |
| Reading a field value | Evaluating quality or completeness |
| Counting items | Making a routing decision based on intent |
| Conditional dispatch to a named sub-skill | Deciding how much detail to include |
| Appending to a log file | Responding to ambiguous user input |

**Keep pseudocode minimal**: Pseudocode in SKILL.md is not executable code — it is structured notation for the agent. Use it to convey logic precisely, not to write a full algorithm. If a pseudocode block exceeds 15 lines, consider whether it belongs in a script instead.

---

## Pattern 5: Failure and Recovery Paths

**Document failure paths at the point of failure**: When a step can fail in a meaningful way, document the failure path within that step — not in a separate "error handling" section at the end.

```markdown
## Step 3: Validate Result

Check that the output file was written and is non-empty.

If validation fails:
- Report what was attempted and what was missing
- Do not proceed to Step 4
- Ask the user whether to retry or skip this step
```

**Explicit vs. implicit failure**: Skills should be explicit about what counts as a failure. "The file doesn't exist" is a clear failure condition. "The output seems wrong" is not — describe what "wrong" means concretely.

**Recovery options**: For recoverable failures, offer the user concrete choices (retry, skip, abort) rather than stopping silently or proceeding blindly.

**Non-recoverable failures**: If a failure makes the rest of the skill meaningless (e.g., a required input is completely missing), stop immediately, explain clearly, and tell the user what to fix before re-invoking.

---

## Skill Body Length

Keep the SKILL.md body under 500 non-blank lines. When approaching this limit, move detailed reference material to a `references/` file and link from the step that needs it:

```markdown
## Step 4: Write the Artifact

Follow the output conventions in [output-patterns.md](~/.claude/skills/skill-creator/references/output-patterns.md).
```

Reference links should appear at the point of use, not in a separate "References" section at the end. Agents load reference files on demand — a link at the point of use signals "read this now."
