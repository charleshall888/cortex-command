# Output Patterns

Reference for the three output types produced by skills: markdown artifacts, structured JSON, and in-conversation status messages. Use the pattern that matches how the output will be consumed.

## Pattern 1: Markdown Artifact

**When to use**: Durable outputs intended for human reading, future agent consumption, or version control. Examples: research.md, spec.md, plan.md, report.md.

**Structure**:

```markdown
# Title: {feature or subject}

## Section One
[Content]

## Section Two
[Content]

## Open Questions
- [Question that requires future resolution]
```

**Conventions**:
- H1 (`#`) for the document title only — one per file
- H2 (`##`) for major sections
- H3 (`###`) for subsections within a section
- Tables for comparative or structured data (e.g., requirement lists, decision matrices)
- Bullet lists for unordered items; numbered lists only for sequences that must be followed in order

**Bootstrapped artifact header**: When a skill creates an artifact by copying or deriving from another source, prepend a blockquote identifying the origin:

```markdown
> Source: backlog/042-my-feature.md (bootstrapped from discovery)
```

This preserves provenance without cluttering the main content.

**Outputs contract entry** (in SKILL.md frontmatter):

```yaml
outputs:
  - "lifecycle/{{feature}}/research.md — research findings and codebase analysis"
```

---

## Pattern 2: Structured JSON Output

**When to use**: Machine-readable results that will be consumed by other skills, scripts, or CI. Examples: `ui-check-results/lint.json`, `ui-check-results/summary.json`, pipeline state files.

**Schema conventions**:

```json
{
  "status": "pass | fail | skip | warning",
  "summary": "One-line human-readable summary",
  "details": [
    {
      "id": "unique-identifier",
      "severity": "error | warning | info",
      "message": "Description of the finding",
      "file": "path/to/relevant/file (if applicable)",
      "line": 42
    }
  ],
  "ts": "2026-01-15T10:30:00Z"
}
```

**Field conventions**:
- `status` — top-level verdict; always present; use `skip` when the layer did not run
- `summary` — one sentence suitable for display in a dashboard or summary table
- `details` — array of individual findings; empty array `[]` on pass, never `null`
- `ts` — ISO 8601 timestamp of when the output was written

**File location**: Write to a predictable, documented path. Prefer a dedicated results directory (`ui-check-results/`, `lifecycle/{feature}/`) over ad-hoc paths.

**Exit behavior**: Skills that write JSON output should always exit cleanly. Failures are represented in `status` and `details`, not as process errors that block downstream callers.

**Outputs contract entry**:

```yaml
outputs:
  - "ui-check-results/lint.json — ESLint and Stylelint results with per-file violations"
```

---

## Pattern 3: In-Conversation Status Messages

**When to use**: Feedback to the user at the end of a phase or after a significant step. Not written to disk — this is the live message in the conversation.

**Structure**: One-line verdict, then a short bullet list of what changed or was found. Do not repeat the full artifact content.

```
Research complete: found 3 existing patterns, 2 integration points, no external dependencies.

- Existing auth pattern: JWT tokens in `src/lib/auth.ts`, validated on every request
- Files affected: `src/middleware/auth.ts`, `src/routes/api.ts`, `src/lib/tokens.ts`
- No web research needed — no external API dependencies
```

**Verdict line format**: "[Phase/action] [result]: [key finding in one clause]."

Examples:
- "Research solid: all questions answered, feasibility grounded in codebase analysis."
- "Plan approved: 8 tasks, dependency graph complete, all verification steps actionable."
- "Lint passed: 0 errors, 3 auto-fixed warnings."
- "Validation failed: 2 required fields missing in spec.md."

**What not to include**: Do not repeat the full artifact, do not list every finding, do not add caveats or hedges. The artifact is available for detailed reading — the status message is a signal, not a summary.

---

## Choosing the Right Pattern

| Output consumer | Pattern |
|----------------|---------|
| Human reading a markdown file | Markdown artifact |
| Another skill or script reading output | Structured JSON |
| User in the current conversation | In-conversation status message |
| Both human and script | Markdown artifact + JSON summary |

When a result needs to be both human-readable and machine-parseable, write a markdown artifact for the narrative and a JSON file for the structured data. Reference the JSON path in the markdown: "Full results: `ui-check-results/lint.json`."
