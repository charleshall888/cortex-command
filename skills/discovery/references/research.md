# Research Phase

Multi-dimensional investigation to build deep understanding of a topic. Read-only — no code changes, no decisions yet.

## Contents

1. [Define Research Questions](#1-define-research-questions)
2. [Codebase Analysis](#2-codebase-analysis)
3. [Web & Documentation Research](#3-web--documentation-research)
4. [Domain & Prior Art Analysis](#4-domain--prior-art-analysis)
5. [Feasibility Assessment](#5-feasibility-assessment)
6. [Write Research Artifact](#6-write-research-artifact)
6a. [Orchestrator Review](#6a-orchestrator-review)
6b. [Critical Review](#6b-critical-review)
7. [Transition](#7-transition)

## Protocol

### 1. Define Research Questions

Before investigating, articulate 3-7 specific questions this research needs to answer. These become the acceptance criteria — research isn't done until each question has a confident answer or is explicitly marked as unanswerable.

Present questions to the user for review. Add any questions they raise.

### 1a. Load Requirements Context

Check for a `requirements/` directory at the project root. If it exists:

- Read `requirements/project.md` for project-level context.
- Scan for area docs relevant to this topic and read those too.
- Use requirements to inform research — identify where this topic intersects with established requirements and constraints.

If no requirements directory exists, skip this step.

### 2. Codebase Analysis

Launch a focused codebase exploration to investigate:

- Existing patterns and conventions relevant to this topic
- Files, modules, and boundaries that would be affected
- Dependencies and integration points
- Technical constraints and architectural patterns

### 3. Web & Documentation Research

Investigate external context:

- Current best practices and recommended approaches
- Library/API documentation for any external dependencies
- Known pitfalls, common mistakes, and failure modes
- Verify that specific capabilities needed actually exist and aren't deprecated

Skip only if the topic is purely internal with no external dependencies or patterns to learn from. Ask the user if unsure.

### 4. Domain & Prior Art Analysis

Investigate how others have solved similar problems:

- Competing or analogous implementations
- Industry patterns and standards
- Trade-offs others have encountered
- Lessons from prior art that apply here

Skip if the topic is narrow/tactical and doesn't benefit from broader domain analysis. Ask the user if unsure.

### 5. Feasibility Assessment

For each viable approach surfaced during research:

- What are the technical risks?
- What unknowns could derail implementation?
- What dependencies or prerequisites must be in place?
- Rough effort estimate (S/M/L/XL)

Prerequisites entries describing codebase-state checks (e.g., 'Identify pattern X in {file}') must be resolved during §2 Codebase Analysis — findings move to §2 with citations, or are reported as `NOT_FOUND(query, scope)`. Entries remaining in the §5 Prerequisites column are implementation-sequencing only (work to be done after the approach is committed).

### 6. Write Research Artifact

Combine findings into `research/{topic}/research.md`:

```markdown
# Research: {topic}

## Research Questions
1. [Question] → **[Answer or "Unresolved: reason"]**
2. ...

## Codebase Analysis
- [Existing patterns]
- [Files/modules affected]
- [Integration points]
- [Constraints]

## Web & Documentation Research
<!-- Omit section if skipped -->
- [Best practices]
- [Library/API findings]
- [Pitfalls]

## Domain & Prior Art
<!-- Omit section if skipped -->
- [Similar implementations]
- [Industry patterns]
- [Lessons learned]

## Feasibility Assessment
| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| [A] | S/M/L/XL | [risks] | [prereqs] |

## Decision Records
<!-- Key trade-offs and alternatives considered -->

### DR-1: [Decision title]
- **Context**: [Why this decision matters]
- **Options considered**: [List alternatives]
- **Recommendation**: [Recommended option and why]
- **Trade-offs**: [What you give up]

## Open Questions
- [Questions that need answers before spec or implementation]
```

### 6a. Orchestrator Review

Before committing, read and follow `~/.claude/skills/discovery/references/orchestrator-review.md` for the `research` phase. The orchestrator review must pass before proceeding to §6b (Critical Review).

### 6b. Critical Review

Run `/critical-review` on `research/{topic}/research.md`. Address any significant challenges raised before proceeding.

### 7. Transition

Stage and commit `research/{topic}/` using `/commit`. Summarize key findings for the user and proceed to Specify.

## Constraints

- **Read-only**: Do not modify project files except the research artifact
- **All findings in the artifact**: They won't survive in context alone
- **Scope**: Research the topic as described, not adjacent topics
- **Citations**: codebase-pointing claims must carry an inline `[file:line]` citation traceable to codebase-agent findings, OR an explicit inline `[premise-unverified: not-searched]` marker when the author did not investigate the claim.
- **Empty-corpus reporting**: searches that returned no results must be reported inline as `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)` — distinct from the `premise-unverified: not-searched` marker used when no investigation was attempted.

### Signal formats

The following literal markers are stable contract for downstream consumers (e.g., `/discovery decompose`):

- `[file:line]` — inline citation, e.g., `[skills/discovery/references/research.md:42]`
- `[premise-unverified: not-searched]` — marker indicating the author did not attempt investigation
- `NOT_FOUND(query=<string>, scope=<path-or-glob>)` — marker indicating a search was performed and returned no results
