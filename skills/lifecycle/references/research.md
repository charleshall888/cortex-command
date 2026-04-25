# Research Phase

Read-only exploration to build context before any decisions are made. No code changes during this phase.

## Protocol

### 0. Log Lifecycle Start

Append a `lifecycle_start` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "lifecycle_start", "feature": "<name>", "tier": "simple|complex", "criticality": "low|medium|high|critical"}
```

### 0a. Check Criticality

Read `lifecycle/{feature}/events.log` and find the most recent event that contains a `criticality` field (either a `lifecycle_start` or `criticality_override` event). If no criticality field is found, default to `medium`.

- **If criticality is `critical`**: Skip §1-§3 and proceed to §1a (Parallel Research).
- **Otherwise** (low, medium, high): Continue to §1 and follow the standard sequential flow through §1-§3.

### 0b. Load Requirements Context

Check for a `requirements/` directory at the project root.

- If `requirements/project.md` exists, read it for project-level context.
- Scan `requirements/` for area-specific docs. If any area names appear relevant to this feature (based on the feature name and description), read those too.
- Use requirements as context during exploration — they inform what patterns to look for, what constraints to respect, and how this feature fits into the broader project.

If no requirements directory exists, skip this step.

### 1. Codebase Exploration

Launch a focused codebase exploration task with fresh context to protect the main context window. The explorer should investigate:

**Model**: `haiku` for low/medium criticality, `sonnet` for high/critical

- Existing patterns relevant to this feature
- Files that will be affected or need modification
- Dependencies and integration points
- Conventions the feature should follow

Provide the explorer with a clear question: "For the `{feature}` feature, find: [specific things to investigate based on the feature description]."

### 1a. Parallel Research (Critical Only)

This section replaces §1-§3 when criticality is `critical`. Non-critical features skip this section entirely.

#### Derive Research Angles

Analyze the feature description and derive 2-3 distinct research angles. Each angle should explore a different dimension of the feature — for example, one angle might focus on existing codebase patterns, another on integration points, and a third on technical constraints or edge cases.

If the feature description is too vague to derive 2-3 distinct angles, ask the user for guidance on what angles to explore before dispatching.

#### Dispatch Parallel Agents

Launch all research agents concurrently as parallel Task tool sub-tasks. Use the researcher prompt template below **verbatim** for each — substitute the variables but do not omit, reorder, or paraphrase any instructions.

**Model**: `sonnet` (parallel agents always use sonnet for breadth)

##### Researcher Prompt Template

```
You are a research agent for the {feature} feature.

## Feature Description
{feature description from the backlog item or lifecycle context}

## Your Research Angle
{specific research angle assigned to this agent}

## Instructions
1. Explore the codebase and gather findings relevant to your assigned research angle
2. Focus exclusively on your angle — do not attempt to cover the entire feature
3. Investigate: existing patterns, affected files, dependencies, integration points, and conventions relevant to your angle
4. Return your findings in the following structured format:

## Findings: {angle name}

### Relevant Patterns
- [Patterns discovered related to this angle]

### Affected Files and Integration Points
- [Files and integration points relevant to this angle]

### Key Observations
- [Important observations, constraints, or risks specific to this angle]

### Open Questions
- [Questions surfaced during exploration of this angle]

Do not modify any files. This is a read-only exploration task.
```

#### Failure Handling

After all agents complete (or fail):

1. Collect results from all successful agents.
2. If some agents failed but at least one succeeded, continue with the successful results. Do not retry failed agents.
3. If **all** agents failed, fall back to the standard sequential flow: return to §1 (Codebase Exploration) and proceed through §2-§3 as if criticality were non-critical.

#### Web Research

After collecting parallel agent results, perform web research following the same criteria as §2:

- **When external dependencies exist**: Launch a research task to gather current documentation and verify capabilities.
- **When no external dependencies exist**: Ask the user if web research would be beneficial. If not, skip.

#### Synthesize Research Artifact

Combine all successful agent outputs plus any web research into a single `lifecycle/{feature}/research.md` following the standard artifact format:

```markdown
# Research: {feature}

## Codebase Analysis
<!-- Synthesized from parallel research agents -->
- [Merged findings from all angles: patterns, affected files, dependencies, conventions]
- [Note convergent findings across angles as high-confidence signals]
- [Flag divergent findings for further investigation]

## Web Research
<!-- Include only if web research was performed -->
- [Best practices found]
- [Library/API documentation findings]
- [Known pitfalls]

## Dependency Verification
<!-- Include only when the feature depends on external APIs, SDKs, CLIs, or third-party libraries -->
- **Dependencies verified**: [List each external dependency that was checked]
- **Capabilities confirmed**: [Specific endpoints, methods, options, or CLI flags confirmed to exist and not be deprecated]
- **Capabilities unverified**: [Any capabilities the feature needs that could not be confirmed through research]

## Open Questions
- [Consolidated questions from all research angles]
- [Ambiguities in requirements that need clarification]
```

After writing research.md, proceed to §4 (Transition).

### 2. Web Research

Determine whether this feature depends on external APIs, SDKs, CLIs, or third-party libraries.

**When external dependencies exist (required):** Launch a research task to gather current documentation and verify that the specific capabilities the feature needs actually exist in the current API surface. Do not assume a capability is available just because the library or service exists conceptually — confirm the exact endpoints, methods, options, or CLI flags the feature will use.

- Current best practices and recommended approaches
- Library/API documentation relevant to the feature
- Known pitfalls or common mistakes
- Verification that specific capabilities needed by this feature are present and not deprecated

**When no external dependencies exist (optional):** Ask the user if the feature involves techniques or patterns that benefit from up-to-date research. If not, skip this step.

### 3. Write Research Artifact

Combine the findings into `lifecycle/{feature}/research.md`:

```markdown
# Research: {feature}

## Codebase Analysis
- [Existing patterns relevant to this feature]
- [Files that will be affected]
- [Dependencies and integration points]
- [Conventions to follow]

## Web Research
<!-- Include only if web research was performed -->
- [Best practices found]
- [Library/API documentation findings]
- [Known pitfalls]

## Dependency Verification
<!-- Include only when the feature depends on external APIs, SDKs, CLIs, or third-party libraries -->
- **Dependencies verified**: [List each external dependency that was checked]
- **Capabilities confirmed**: [Specific endpoints, methods, options, or CLI flags confirmed to exist and not be deprecated]
- **Capabilities unverified**: [Any capabilities the feature needs that could not be confirmed through research]

## Open Questions
- [Questions surfaced during research that need answers before implementation]
- [Ambiguities in requirements that need clarification]
```

### 4. Transition

Before proceeding, read and follow `references/orchestrator-review.md` for the `research` phase. The orchestrator review must pass before logging the transition event.

Append a `phase_transition` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "research", "to": "specify"}
```

If `commit-artifacts` is enabled in project config (default), stage `lifecycle/{feature}/` and commit using `/cortex-interactive:commit`.

After writing research.md, summarize the key findings for the user and proceed to Specify.

## Constraints

- **Read-only**: Do not create, modify, or delete any project files except the research artifact
- **File-based output**: All findings must be written to `lifecycle/{feature}/research.md` — they will not survive in context alone
- **Scope**: Research the feature as described, not adjacent features or broader refactors
- **Evaluate backlog suggestions critically**: If the originating backlog item suggested an approach, treat it as one option to investigate — not a decision already made. Research should validate, challenge, or surface alternatives to suggested approaches. Only backlog items with linked research/spec artifacts represent pre-validated decisions.
