# Multi-Agent PR Review — Dispatch Protocol

This document defines the complete five-stage pipeline for reviewing a pull request using
parallel subagents. Each stage is described with exact commands, verbatim prompt templates,
and failure handling instructions.

---

## Stage 1 — Fetch PR Data

Fetch structured metadata and the raw diff for the pull request. When the skill is invoked
with an explicit PR number, include it in both commands. When invoked with no argument, omit
the number so the CLI auto-detects the current branch's open PR.

**Metadata command (with number):**
```
gh pr view <number> --json title,body,author,files,additions,deletions,changedFiles,headRefName,baseRefName,latestReviews
```

**Metadata command (no number):**
```
gh pr view --json title,body,author,files,additions,deletions,changedFiles,headRefName,baseRefName,latestReviews
```

**Diff command (with number):**
```
gh pr diff <number> --patch
```

**Diff command (no number):**
```
gh pr diff --patch
```

**Failure handling:**
- If `gh pr view` fails because no PR is associated with the current branch, surface the
  error message verbatim and stop — do not proceed to later stages.
- If `gh` returns an authentication error, surface the error directly without wrapping it
  and stop — do not proceed to later stages.
- If the PR is already closed or merged, proceed normally and include a note in the final
  output that the PR is closed/merged.
- If the diff fetch fails but metadata succeeded, proceed with metadata only; note the
  missing diff in the final output and mark all code-level findings as unavailable.

---

## Stage 2 — Haiku Triage

Launch a fresh subagent using the Haiku model. Pass it the file list (from `files` in the
Stage 1 metadata) and the PR description (from `body`). The subagent must return a priority
map classifying every changed file as either `deep-review` or `skim-ignore`.

**Files classified as `skim-ignore`:**
- Generated files (e.g. `*.g.dart`, `*.pb.go`, auto-generated GraphQL schemas)
- Package lock files (`package-lock.json`, `yarn.lock`, `Cargo.lock`, `poetry.lock`, etc.)
- Test snapshots (e.g. `__snapshots__/*.snap`, `*.snap`)
- Pure formatting / whitespace-only changes

All other files default to `deep-review`.

### Haiku Triage Prompt Template

```
You are a triage agent for a pull request review pipeline.

## Your job
Classify each changed file as either `deep-review` or `skim-ignore`.

- `deep-review`: files with significant logic changes that warrant detailed review
- `skim-ignore`: generated files, lock files, test snapshots, or pure reformats

## PR Description
{pr_body}

## Changed Files
{files_list}

## Output format
Return a JSON object with a single key "triage" whose value is an object mapping
each file path to either "deep-review" or "skim-ignore". No other text.

Example:
{
  "triage": {
    "src/auth/login.ts": "deep-review",
    "package-lock.json": "skim-ignore",
    "src/__snapshots__/login.test.ts.snap": "skim-ignore"
  }
}
```

**Failure handling:** If the Haiku subagent fails or returns malformed output, proceed to
Stage 3 without triage. Pass an empty triage map to all Sonnet agents and note in the final
output that triage was unavailable — reviewers should treat all files as `deep-review`.

---

## Stage 3 — Four Parallel Sonnet Agents

Dispatch all four agents concurrently. Every agent receives: the full diff, the PR metadata
(title, body, author, file list, branch names), and the triage output from Stage 2. Each
agent also has unique data-fetching responsibilities described below.

---

### Agent 1 — CLAUDE.md Compliance

**Unique data fetching:** For each file path in the diff, walk up the directory tree and
collect all `CLAUDE.md` files found at each level. Use:
```
find <dir> -name "CLAUDE.md" -maxdepth 1
```
starting from the directory containing the changed file, then its parent, grandparent, and
so on up to the repository root. Deduplicate results (a single CLAUDE.md may cover multiple
changed files). Read each discovered CLAUDE.md in full.

**Prompt template:**

```
You are Agent 1 — CLAUDE.md Compliance — in a multi-agent PR review pipeline.

## Your job
Determine whether the changes in this pull request follow the conventions and requirements
documented in the project's CLAUDE.md files.

## Inputs

### PR Metadata
Title: {pr_title}
Author: {pr_author}
Base branch: {base_ref}  →  Head branch: {head_ref}
Description:
{pr_body}

### Triage map
{triage_output}

### CLAUDE.md files discovered for touched directories
{claude_md_contents}
(If none were found, this will say "No CLAUDE.md files found." In that case, skip
compliance checks and report that no project conventions were available.)

### Full diff
{pr_diff}

## What to check
- Commit message format (if visible in the PR description or branch name)
- File placement (do new files follow documented directory conventions?)
- Naming conventions (variables, functions, files, exports)
- Any explicit rules stated in a CLAUDE.md that the changed code may violate
- Ignore `skim-ignore` files from the triage map

## Output format
Respond in this exact structure:

### CLAUDE.md Compliance Report

**CLAUDE.md files consulted:** <list paths, or "None found">

**Violations found:**
- <violation 1: file, line range, rule violated>
- ... or "None"

**Observations (non-blocking):**
- <observation 1>
- ... or "None"

**Summary:** <one sentence>
```

**Failure handling:** If Agent 1 fails, record the error. Opus will proceed without
compliance findings; note the gap in the final output.

---

### Agent 2 — Bug Scan

**Unique data fetching:** None. Agent 2 receives only the diff and PR metadata. It does not
fetch additional context.

**Prompt template:**

```
You are Agent 2 — Bug Scan — in a multi-agent PR review pipeline.

## Your job
Perform a shallow, skeptical scan of the diff for bugs, edge cases, logic errors, and
missing error handling. Focus exclusively on code introduced or modified by this PR. Do not
flag pre-existing issues in unchanged lines.

## Inputs

### PR Metadata
Title: {pr_title}
Author: {pr_author}
Base branch: {base_ref}  →  Head branch: {head_ref}
Description:
{pr_body}

### Triage map
{triage_output}

### Full diff
{pr_diff}

## What to look for
- Off-by-one errors, null/undefined dereferences, type mismatches
- Unchecked error returns or swallowed exceptions
- Race conditions or improper use of async/await
- Logic inversions (conditions that behave opposite to intent)
- Missing boundary checks on user input or external data
- Incorrect handling of empty collections, zero values, or missing optional fields
- Ignore `skim-ignore` files from the triage map

## Output format
Respond in this exact structure:

### Bug Scan Report

**Issues found:**
- <issue 1: file, line range, description, severity: Critical | High | Medium | Low>
- ... or "None"

**Edge cases to verify manually:**
- <edge case 1>
- ... or "None"

**Summary:** <one sentence>
```

**Failure handling:** If Agent 2 fails, record the error. Opus will proceed without bug
scan findings; note the gap in the final output.

---

### Agent 3 — Git History

**Unique data fetching:** For each modified file path in the diff, run:
```
git log --follow -p -- <file>
```
and:
```
git blame -l <file>
```
The `--follow` flag tracks renames across the file's history; the `-p` flag includes the
full patch for each commit so the agent can see exactly what changed over time, not just
commit subjects. Collect the output for all modified files. If the repository history is
shallow (fewer than 5 commits visible for a file), note that limitation per file.

**Prompt template:**

```
You are Agent 3 — Git History — in a multi-agent PR review pipeline.

## Your job
Use git history and blame data to provide historical context for the changes in this PR.
Identify patterns such as reverted logic, recurring issues, or intentional design decisions
that are visible in commit messages or blame annotations.

## Constraints
- Do not pipe git commands. Issue each command separately. The full output is returned
  to you as a tool result — analyze it directly without piping or filtering with bash.

## Inputs

### PR Metadata
Title: {pr_title}
Author: {pr_author}
Base branch: {base_ref}  →  Head branch: {head_ref}
Description:
{pr_body}

### Triage map
{triage_output}

### Full diff
{pr_diff}

### Git log and blame data (per file)
{git_history_data}
(Format: for each file, a "### <filepath>" section containing the full `git log --follow -p`
output followed by the git blame output. If history was shallow, a note is included.)

## What to look for
- Code being introduced that was previously reverted — check commit messages for "revert"
- Recurring bug fixes to the same area — repeated commit messages touching the same lines
- Lines being changed that have a rich blame history suggesting intentional complexity
- Commit messages that explain why something was done a particular way, which the PR
  may be overriding
- Ignore `skim-ignore` files from the triage map

## Output format
Respond in this exact structure:

### Git History Report

**Historical patterns found:**
- <pattern 1: file, description, relevant commit hashes or blame lines>
- ... or "None"

**Cautions from history:**
- <caution 1: what to watch out for and why>
- ... or "None"

**Limitations:**
- <note any files with shallow history or missing blame data>
- ... or "None"

**Summary:** <one sentence>
```

**Failure handling:** If Agent 3 fails, record the error. Opus will proceed without
history findings; note the gap in the final output.

---

### Agent 4 — Previous PR Comments

**Unique data fetching:** Fetch a list of all recent PRs:
```
gh pr list --state all --limit 50 --json number,title,files
```
Filter this list to PRs that touched at least one file also touched by the current PR.
For each overlapping PR (up to 10), fetch its review comments:
```
gh pr view <n> --comments --json comments,reviews
```
Collect all findings. If no prior PRs touched the same files, report that directly.

**Prompt template:**

```
You are Agent 4 — Previous PR Comments — in a multi-agent PR review pipeline.

## Your job
Examine historical PR feedback on the same files touched by this PR. Determine whether
concerns raised in past reviews have been addressed, ignored, or re-introduced.

## Inputs

### PR Metadata
Title: {pr_title}
Author: {pr_author}
Base branch: {base_ref}  →  Head branch: {head_ref}
Description:
{pr_body}

### Triage map
{triage_output}

### Full diff (current PR)
{pr_diff}

### Historical PR comments (for overlapping files)
{historical_pr_data}
(Format: for each prior PR, a "### PR #{number}: {title}" section containing the
comments and reviews JSON. If no overlapping PRs were found, this will say
"No prior PRs found that touched the same files.")

## What to look for
- Feedback from past reviews that was never resolved
- The same type of issue being flagged repeatedly across multiple PRs
- Review comments that explicitly requested a refactor or architectural change that
  still has not happened
- Positive patterns: evidence that feedback was taken seriously and addressed well
- Ignore `skim-ignore` files from the triage map

## Output format
Respond in this exact structure:

### Previous PR Comments Report

**Unresolved historical feedback:**
- <item 1: prior PR number, file, original comment summary, current status>
- ... or "None found" or "No prior PRs to check"

**Recurring issues across PRs:**
- <pattern 1: description, PR numbers where it appeared>
- ... or "None"

**Positive feedback patterns:**
- <item 1>
- ... or "None"

**Summary:** <one sentence>
```

**Failure handling:** If Agent 4 fails, record the error. Opus will proceed without
historical comment findings; note the gap in the final output.

---

## Stage 4 — Opus Synthesis

Launch a fresh subagent using the Opus model. Pass it: the full diff, the PR metadata, the
triage output, and all four Sonnet review outputs (or however many succeeded).

**Prompt template:**

```
You are the synthesis agent in a multi-agent PR review pipeline.

## Your job
Cross-validate the findings from four specialist review agents and produce a single,
structured review summary with a clear verdict.

## Cross-validation rules
- An issue flagged by TWO OR MORE agents is HIGH-CONFIDENCE — include it in
  "High-Confidence Issues" with a note of which agents flagged it.
- An issue flagged by only ONE agent is an OBSERVATION — include it in "Observations"
  with a note of which agent raised it. Do not dismiss single-agent findings; they
  may be the most important.
- Contradictory findings between agents should be noted explicitly so a human can
  adjudicate.

## Verdict criteria
- **APPROVE**: No high-confidence issues; observations are minor or stylistic.
- **REQUEST CHANGES**: One or more high-confidence issues that must be addressed before
  merging, or a significant architectural concern.
- **REJECT**: Fundamental design problem, security issue, or the PR goes against
  explicitly documented project requirements in a way that cannot be patched.

## Inputs

### PR Metadata
Title: {pr_title}
Number: {pr_number}
Author: {pr_author}
Base branch: {base_ref}  →  Head branch: {head_ref}
Description:
{pr_body}

### Triage map
{triage_output}

### Full diff
{pr_diff}

### Agent 1 — CLAUDE.md Compliance
{agent1_output}
(If missing: "Agent 1 did not complete. Compliance findings unavailable.")

### Agent 2 — Bug Scan
{agent2_output}
(If missing: "Agent 2 did not complete. Bug scan findings unavailable.")

### Agent 3 — Git History
{agent3_output}
(If missing: "Agent 3 did not complete. History findings unavailable.")

### Agent 4 — Previous PR Comments
{agent4_output}
(If missing: "Agent 4 did not complete. Historical comment findings unavailable.")

## Output format
Produce the review in this exact format:

## PR Review: {pr_title} (#{pr_number})
**Verdict**: APPROVE | REQUEST CHANGES | REJECT

### High-Confidence Issues
(issues flagged by multiple agents — list each with: description, agents that flagged it,
affected file(s) and line range if known)

### Observations
(single-agent findings worth examining — list each with: description, agent that raised it,
affected file(s) if known)

### Architectural Assessment
(overall fit of the changes with the codebase architecture; note any structural concerns
even if no individual agent flagged them explicitly)

### Consensus Positives
(things multiple agents or the diff itself suggest were done well)
```

**Failure handling:** If the Opus subagent fails, skip Stage 4 and proceed directly to
Stage 5, presenting the raw Sonnet outputs with an explanation that synthesis was
unavailable.

---

## Stage 5 — Present Summary

The main agent presents the Opus synthesis output to the user. All prior agent outputs
(triage, four Sonnet reviews, Opus synthesis) remain available in context so the user can
ask follow-up questions about specific findings.

If Opus synthesis was unavailable (Stage 4 failed), present the raw Sonnet reviews directly
with this preamble:

```
Opus synthesis was unavailable due to an error. The raw findings from each specialist
agent are presented below. No cross-validation has been performed.
```

---

## Failure Handling Summary

| Failure scenario                          | Action                                                          |
|-------------------------------------------|-----------------------------------------------------------------|
| Stage 1 metadata fetch fails              | Stop; surface error verbatim                                    |
| Stage 1 diff fetch fails                  | Proceed; note missing diff; code-level findings unavailable     |
| Stage 2 Haiku triage fails                | Proceed; treat all files as `deep-review`; note in output      |
| 1–2 Sonnet agents fail                    | Opus proceeds with available reviews; notes missing inputs      |
| 3+ Sonnet agents fail                     | Skip Opus; present raw errors with explanation                  |
| Opus synthesis fails                      | Present raw Sonnet reviews with explanation                     |
