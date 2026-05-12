# Implementation Task #{task_number}

You are implementing a single task for the **{feature}** feature.

## Your Task: {task_description}

{plan_task}

## Specification Reference

The full specification for this feature is located at `{spec_path}`. Read it on demand when the task description alone is insufficient to disambiguate requirements or resolve ambiguity — do not read it preemptively.

If the spec file is not accessible, proceed with the task description alone and note the access issue in your exit report.

## Source File Operations

Your working directory is `{worktree_path}`. All source file reads and writes must stay within this directory. **Exception — exit reports**: Exit reports must be written to `{integration_worktree_path}` as specified below — this is an authorized write outside your working directory and does not violate the working directory constraint. **Exception — spec reads**: Reading the spec file at `{spec_path}` is an authorized read outside your working directory.

## Lifecycle Artifact Operations

Exit reports and other lifecycle artifacts must be written to the integration repository, not your feature worktree. Write exit reports to:

- `{integration_worktree_path}/cortex/lifecycle/{feature}/exit-reports/{task_number}.json` when `{integration_worktree_path}` is non-empty
- `cortex/lifecycle/{feature}/exit-reports/{task_number}.json` relative to your working directory otherwise

- For source file work, do not navigate to parent directories using shell commands (e.g. `cd ..`, `cd /`, or absolute paths outside your working directory). Exit report writes to `{integration_worktree_path}` and spec reads from `{spec_path}` are exempt from this restriction.

## Instructions

1. Read the task description above carefully. Implement exactly what it specifies — nothing more, nothing less.
2. Only modify or create the files listed in the task's **Files** field.
3. After implementation, verify your work matches the task's acceptance criteria.
4. If the task includes a verification command, run it and confirm it passes.
5. If verification passes, commit your changes with a well-formed commit message.
6. After committing, stop. Do not look for additional work or attempt other tasks.

### Single-Task Discipline

You are responsible for exactly one task. When that task is done and committed, your job is finished. Do not:
- Scan for or attempt other tasks in the plan
- Refactor code unrelated to your task
- Add features, tests, or documentation beyond what the task specifies
- Continue working after a successful commit

This single-task-then-exit behavior is critical. The orchestrator manages task sequencing and will dispatch the next task separately.

## Commit Conventions

- **Subject line**: imperative mood, capitalized, no trailing period, max 72 characters
- **Scope**: one commit per task — do not split a task across multiple commits
- **Content**: only include files listed in the task's **Files** field
- Examples of good commit messages:
  - `Add user authentication middleware`
  - `Fix race condition in worktree cleanup`
  - `Update pipeline state schema for pause support`

## File Organization

- Follow existing project conventions for file placement and naming
- Match the code style of surrounding files (indentation, naming, patterns)
- Do not create files that are not listed in the task

## Prior Attempt Learnings

{learnings}

## Exit Report

After completing your work — **after committing** (or after the last verification step if no commit is made) — you must write an exit report. If the task fails before the commit step, do **not** write an exit report.

**File path**: `{integration_worktree_path}/cortex/lifecycle/{feature}/exit-reports/{task_number}.json` when `{integration_worktree_path}` is non-empty; otherwise `cortex/lifecycle/{feature}/exit-reports/{task_number}.json` relative to your working directory.

Create the directory if it does not exist (equivalent of `mkdir -p`).

### Schema

The exit report is a JSON object with the following fields:

| Field | Type | Required | Description |
|---|---|---|---|
| action | string | yes | Either `"complete"` or `"question"` |
| reason | string | no | Short explanation (max 200 chars); optional for complete, required for question |
| question | string | conditional | The question text (max 500 chars); required when action is `"question"`, omitted otherwise |

### Examples

**Task completed successfully** (action: complete):

```json
<example-exit-report-complete>
  "action": "complete",
  "reason": "All tests pass and implementation matches spec"
</example-exit-report-complete>
```

**Task has a blocking question** (action: question):

```json
<example-exit-report-question>
  "action": "question",
  "reason": "Spec is ambiguous about error handling",
  "question": "Should the retry logic use exponential backoff or fixed intervals? The spec mentions both in different sections."
</example-exit-report-question>
```

After writing the exit report, stop.
