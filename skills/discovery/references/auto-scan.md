# Auto-Scan Phase

Pre-discovery gap identification. Scans requirements, backlog, active lifecycles, and existing skills to identify undercovered areas, ranks them, and presents a numbered list for the user to select a discovery topic from.

Runs only when `/discovery` is invoked with no topic argument. Does not write any files or state — it is read-only and produces only a `{{topic}}` for the normal discovery flow.

## Protocol

### 1. Check for Requirements

Look for a `requirements/` directory at the project root.

- If it does not exist: output "No requirements docs found — cannot auto-scan for gaps. Provide a topic to start discovery: `/discovery <topic>`." and exit.
- If it exists: read all `requirements/*.md` files.

### 2. Extract Coverage Targets

From the requirements docs, extract the following as gap candidates:

- **Core feature areas**: explicitly named feature areas (e.g., "Skills & workflow engine", "Machine portability")
- **Open questions**: questions explicitly listed under an "Open Questions" section
- **Deferred items**: items explicitly listed under a "Deferred" section
- **Quality attributes**: named quality goals (e.g., "Graceful partial failure", "Fast machine setup")

Record each candidate with its type (core-feature | open-question | deferred | quality).

### 3. Load Exclusion Signals

Load the three exclusion sources to filter out already-covered candidates:

**Active backlog**: Scan `backlog/[0-9]*-*.md`. Read `status:` from each file's frontmatter. Treat any item where status is NOT `complete` or `won't-do` as active coverage. Build a list of active item titles and tags.

**In-progress lifecycles**: Scan `lifecycle/*/` directories. Any directory containing `research.md` or `plan.md` is in-progress. Build a list of lifecycle directory names (slugified feature names).

**Existing skills**: Scan `skills/*/SKILL.md`. Read each `name:` and `description:` field. Build a list of implemented skill names and their described capabilities.

### 4. Identify Gaps

For each gap candidate from §2, determine coverage:

- **Zero coverage**: no active backlog item, no in-progress lifecycle, and no existing skill clearly addresses this area
- **Partial coverage**: one or more active items exist but they address only part of the area, or are tagged for a sub-area only
- **Covered**: substantial active backlog or lifecycle work directly addresses this area

Mark candidates as covered and exclude them from the gap list. Keep zero-coverage and partial-coverage candidates.

If all candidates are covered: output a coverage summary (e.g., "All requirements areas have active backlog or lifecycle coverage.") and exit cleanly. Do not prompt for a topic — the user can call `/discovery <topic>` manually.

### 5. Rank and Present

Rank the remaining gaps in this order:

1. Core feature areas (zero coverage first, then partial)
2. Open questions (zero coverage first, then partial)
3. Deferred items (zero coverage first, then partial)
4. Quality attributes (zero coverage first, then partial)

Present as a numbered list. Each entry shows the gap candidate and a one-line rationale:

```
Gaps identified in requirements:

1. [Core feature] Remote access — no active backlog coverage
2. [Open question] Cross-repo autonomous work — no ticket addresses this
3. [Deferred] Exact shape of multi-agent orchestration — marked deferred, no active work
4. [Quality] Fast machine setup — quality attribute with no recent backlog coverage

Enter a number to start discovery on that topic, or type a custom topic:
```

Use the AskUserQuestion tool to present the selection. Include "Other" implicitly via the tool's built-in custom input option.

### 6. Handle Selection

**User selects a numbered item**: derive `{{topic}}` from the gap candidate name using lowercase-kebab-case (e.g., "Remote access" → `remote-access`). Announce: "Starting discovery on: `{{topic}}`." Proceed to Step 2 of SKILL.md (Check for Existing State) with this topic.

**User enters custom text**: treat the free text as `{{topic}}` (slugify if needed). Proceed to Step 2 of SKILL.md with this topic.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should create a research file or events log before the user picks" | No state is written until a topic is selected and the normal discovery flow begins. Auto-scan is purely read-only. |
| "I should run discovery on all the gaps I found" | The user picks one. Parallel discovery on multiple gaps is not supported by this mode. |
| "I should only check requirements/project.md" | Load all `requirements/*.md` — future area docs benefit automatically. |
| "I should filter using completed lifecycle directories too" | Filter on in-progress (has research.md or plan.md). Completed lifecycles don't block re-discovery of an area. |
| "I should present gaps that are already covered so the user can re-explore" | Covered areas are excluded. The user can always call `/discovery <topic>` directly to explore a covered area. |
