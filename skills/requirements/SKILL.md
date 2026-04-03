---
name: requirements
description: Gather and document project-level and feature-area requirements through structured interviews. Creates a requirements directory at the project root with a master project requirements doc and area-specific requirements. Use when user says "/requirements", "gather requirements", "document requirements", "requirements for", "what are the requirements", "define project scope", "capture what we have", "document existing project", or wants to capture project scope and feature-area requirements — whether for a new project or retroactively documenting an existing codebase.
disable-model-invocation: true
argument-hint: "[area]"
inputs:
  - "area: string (optional) — area name (kebab-case) for area-level requirements; omit for project-level; 'list' to show all documented areas"
outputs:
  - "requirements/project.md — master project requirements document (project-level invocation)"
  - "requirements/{{area}}.md — area-specific requirements document (area-level invocation)"
preconditions:
  - "Run from project root"
  - "requirements/ directory will be created if it does not exist"
---

# Requirements

Structured requirements gathering through interactive interview. Produces durable requirements artifacts that downstream flows (lifecycle, discovery, pipeline) reference during research, spec, planning, and review.

Area: $ARGUMENTS (if non-empty, scope interview to this area; if empty, run full project requirements gathering).

## Invocation

- `/requirements` — start or resume project-level requirements
- `/requirements {{area}}` — start or resume area-level requirements (e.g., `/requirements multiplayer`)
- `/requirements list` — show all documented requirements areas

## Storage

Requirements live in `requirements/` at the project root:

- `requirements/project.md` — master project requirements
- `requirements/{area}.md` — area-specific requirements (e.g., `requirements/multiplayer.md`)

Area names use lowercase-kebab-case (same convention as lifecycle directories).

## Step 1: Determine Scope

Parse the invocation to determine scope:

- **No argument or "project"**: Project-level requirements
- **"list"**: Show existing requirements (Step 1a)
- **Any other argument**: Area-level requirements for that topic

### Step 1a: List

Scan `requirements/` for all `.md` files. For each, read the first heading and the Overview section. Present a summary table:

| File | Scope | Last Gathered | Requirement Count |
|------|-------|---------------|-------------------|
| project.md | Project | {date} | {count} |
| multiplayer.md | Area | {date} | {count} |

If no requirements directory exists, report: "No requirements documented yet. Run `/requirements` to start with project-level requirements."

## Step 2: Check for Existing State

Check if the target file already exists:

- **If `requirements/{scope}.md` exists**: Read it, present a summary, and ask:
  - **Update** — Run a follow-up interview to refine or extend
  - **Replace** — Start fresh (confirms overwrite)
  - **View** — Display the current requirements
- **If not**: Proceed to Step 3

## Step 3: Codebase Reconnaissance

If the project has existing source code, launch a focused codebase exploration to understand:

- Project structure, languages, and frameworks
- Existing features and capabilities already built
- Architecture patterns, conventions, and technology choices already made
- README, docs, or any existing requirements/spec/design files
- CLAUDE.md/Agents.md or equivalent project instructions — understand what operational context is already documented so the interview and artifact avoid duplicating it

**For existing codebases** (retroactive documentation): Mine the code for what's already been decided. The codebase IS the current requirements — extract them rather than asking the user to re-state what the code already shows. Focus the interview on intent, priorities, and boundaries the code can't tell you.

**For greenfield projects** (no meaningful source code): Skip this step.

For area-level requirements, also read `requirements/project.md` if it exists — area requirements should be consistent with project-level decisions.

## Step 4: Structured Interview

Read and follow [gather.md](${CLAUDE_SKILL_DIR}/references/gather.md) for the interview protocol.

## Step 5: Write Requirements Artifact

After the interview, compile answers into the requirements document following the artifact format in [gather.md](${CLAUDE_SKILL_DIR}/references/gather.md).

## Step 6: User Approval

Present the requirements document summary. The user must approve before finalizing. If the user requests changes, revise and re-present.

## Step 7: Commit

Stage `requirements/` and commit using `/commit`.

## Downstream Integration

Requirements documents are passive artifacts — they don't drive workflows directly. Instead, downstream skills consult them automatically:

- **Lifecycle research**: Loads project requirements and relevant area requirements as context for codebase exploration
- **Lifecycle specify**: References requirements during the structured interview to avoid re-asking settled questions
- **Lifecycle review**: Checks implementation against project and area requirements for compliance
- **Discovery research**: Loads relevant requirements to scope investigation
- **Pipeline**: Inherits lifecycle's requirements awareness through shared reference files

Requirements are never auto-generated by other skills. Only this skill creates and modifies requirements documents.

## Constraints

**Requirements vs specifications**: Requirements define WHAT the project or area needs at a high level. Specifications (produced by lifecycle's specify phase) define detailed acceptance criteria for a single feature. Requirements are broader and more stable; specs are narrower and feature-specific.

**Requirements vs CLAUDE.md**: CLAUDE.md provides operational context loaded every session — repo structure, commands, dependencies, conventions, and working patterns. Requirements provide strategic context loaded on-demand by downstream skills — project vision, feature priorities, quality attributes, and scope boundaries. Do not duplicate operational content from CLAUDE.md in requirements. If something is already documented in CLAUDE.md, reference it rather than restating it.

**Light "how"**: Capture architectural constraints that narrow the solution space (e.g., "must support 16 concurrent players" or "must work offline") because they shape what's feasible. Do not prescribe implementation decisions (e.g., "use WebSockets" or "use SQLite") — leave those to lifecycle's research and planning phases.
