---
name: requirements
description: Use /cortex-core:requirements to gather requirements or define project scope. Interviews, then writes cortex/requirements/{project|area}.md — explicit slash command only.
disable-model-invocation: true
argument-hint: "[area|project|list|compact <area>]"
---

# Requirements

Interview first. Write nothing until the interview is complete.

## Scope

Read `$ARGUMENTS`:

- **`list`** → run `cortex-list-requirements` and exit. `absent` → "No requirements documented yet. Run `/cortex-core:requirements` to start with project-level requirements." `ok` → show `rows` as a table: file, scope, last_gathered, requirement_count (`glossary.md` is excluded).
- **empty or `project`** → scope `project`.
- **`compact {scope}`** → skip to §4 for that doc.
- **any other token** → that kebab-case area slug.

The target is `cortex/requirements/{scope}.md`. When it exists, refine it; do not rewrite.

## 1. Interview

Run the `/cortex-core:interview` loop: group only independent questions, let the codebase answer first, recommend before asking. Every question has a **Recommended answer:** based on explored code, the existing doc, the parent requirements (area scope), or stated conventions. With no basis, write `none — open question` and explain the gap.

Tie each block to one section, in template order. **Project**: Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries, Conditional Loading, Optional. **Area**: Overview, Functional Requirements, Non-Functional Requirements, Architectural Constraints, Dependencies, Edge Cases, Open Questions. For an area, reuse `cortex/requirements/project.md`; do not re-ask settled positions.

```
### {Section name}
- **Q:** {question}
- **Recommended answer:** {grounded recommendation, or "none — open question" with rationale}
- **User answer:** {captured response or confirmation}
- **Code evidence:** {file paths or excerpts; omit for intent-only questions — never fabricate or write N/A}
```

A section with no open questions becomes one bullet noting the position confirmed from code.

### Glossary

The one write during the interview is a per-term entry in the `## Language` section of `cortex/requirements/glossary.md`. Check first:

```bash
cortex-append-glossary-term --term "{term}"
```

- `found` → use the definition exactly, or offer keep / replace / flag as ambiguity. "Replace" re-runs with `--definition` and `--replace`.
- `not-found` → decide whether the term belongs. Project terms ("phase transition", "kept user pauses") get an entry: write it with `--definition`. General programming terms ("timeout") do not: explain why and write nothing.

Only a term the user named or confirmed is saved; a mention inside a Recommended answer is not consent. An entry defines a word and carries no reasoning — `/cortex-core:critical-review` gives this section to reviewers who must not see earlier reasoning.

## 2. Synthesize

Keep prose the user confirms; refine it in place. Keep H2/H3 headings exact; other tools grep them. A collapsed section takes the template default. A missing answer keeps the H2 with a one-line pointer to Open Questions (area) or a `## Optional` bullet (project). Update `> Last gathered:` when any section changes.

**Writing** — agents re-read these docs at every lifecycle phase, so each word is paid for many times.

- Plain English: short active sentences, one idea per sentence or bullet.
- Common words that carry the idea ("a test that can fail", not "a demonstrated falsifier"). Use glossary terms; define any other term once.
- State the rule, then at most one clause of why. No dates, no "amended", no "previously"; history lives in git.
- Bold marks only the lead of a rule.
- Name constants and files; do not quote values that live in code. Keep exact names, commands, and numbers that are the rule.

**Size** — a doc stays under 32,000 bytes unless a `> Size budget: {N} bytes` line under its H1 raises the limit on purpose. Over it, compact (§4) before adding.

**Project** — `# Requirements: {project-name}` + `> Last gathered: {YYYY-MM-DD}`, then eight H2s in order:

- `## Overview` — 1–2 paragraph north star; distribution posture if it matters.
- `## Philosophy of Work` — cross-cutting principles, bold-led bullets.
- `## Architectural Constraints` — strategic only. Operational detail lives in a doc that CLAUDE.md routes to by trigger, never in CLAUDE.md itself, which every request loads.
- `## Quality Attributes`
- `## Project Boundaries` — `### In Scope`, `### Out of Scope`, `### Deferred`.
- `## Conditional Loading` — a many-to-one area→doc map, one `{area key}/{synonym key} → cortex/requirements/{area}.md` per line. Keys match the `areas:` of a lifecycle `index.md` by exact lookup. So every key is a real area name, and a doc reaches more lifecycles by listing more synonyms.
- `## Global Context` — bare paths under `cortex/requirements/` that every consumer loads on every run. Absent paths are skipped, so you may list one early.
- `## Optional` — prunable; the first line states the convention. Token budget ≤1,200 `cl100k_base`. Overflow goes here or into an area doc, never into new H2s.

**Area** — `# Requirements: {area-name}` + `> Last gathered:` + `**Parent doc**: [requirements/project.md](project.md)` exactly, then seven H2s: `## Overview`, `## Functional Requirements` (one H3 per capability with `**Description**`, `**Inputs**`, `**Outputs**`, nested `**Acceptance criteria**`, `**Priority**`), `## Non-Functional Requirements`, `## Architectural Constraints`, `## Dependencies`, `## Edge Cases` (`**Condition**: behavior`), `## Open Questions` (`- None` when empty).

## 3. Accept and commit

```bash
cortex-validate-requirements-doc --path {written-path} --scope {project|area}
```

`pass` → show the path for approval. `fail` → `checks` names the failing check; fix and re-run. `file-not-found`/`error` → resolve before returning. On approval, stage `cortex/requirements/` and commit. Start no consumer; downstream skills load requirements on their own schedule.

## 4. Compact

`compact {scope}` rewrites one doc to fit its size budget without changing what any rule means. No interview.

Record `git rev-parse HEAD` as `{base}`. Commit a dirty doc first, so the base holds it. Rewrite to the Writing rules: current rules only. Keep H1–H3 headings, `**State:**` tags, and bold rule leads exactly. Drop dated history, retraction stories, and any rule the doc states elsewhere. Under the H1, keep one pointer line: `> Pre-compact text: git show {base}:{path}`.

```bash
cortex-validate-requirements-doc --path {path} --scope {project|area} --compact-base {base}
```

`compact-preserves` fails → restore what `missing_headings` or `state_tags` names. Show the diff and account for every `dropped_rule_leads` and `dropped_identifiers` entry: which surviving rule covers it, or that it was history. Commit on approval as in §3.
