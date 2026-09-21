---
schema_version: "1"
uuid: f6f82fcb-6682-4767-b91b-12a27fddc337
title: Requirements skill has no compact mode, and its template sends operational detail to CLAUDE.md
status: complete
priority: medium
type: feature
created: 2026-09-21
updated: 2026-09-21
tags: ['requirements', 'token-cost', 'filed-from-wild-light']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-09-21, during a trim of its agent docs.

## Why

The requirements skill can gather and refine a doc, but it has no way to **consolidate** one. Docs grow by accretion (Review drift appends, agents add findings), so every repo eventually needs a manual trim. wild-light's trim of its 22 requirements docs took a fan-out of subagents and hit a weekly usage limit.

Also, the project template tells authors to put operational detail in CLAUDE.md: "`## Architectural Constraints` (strategic only; operational detail lives in CLAUDE.md)". CLAUDE.md is loaded into every request of every session, so this points detail at the most expensive place. wild-light's CLAUDE.md had reached 72 KB at one point.

## What to change

- Add `/cortex-core:requirements compact <area>`. It rewrites one doc under its budget: current rules only; keep H2/H3 anchors, `**State:**` tags and bold rule leads verbatim; drop dated history, retraction narrative and restated rules; put a one-line `git show <sha>:<path>` pointer under the H1 for the pre-compact text. It validates, shows the diff, and commits on approval.
- Change the template line to "operational detail lives in a routed doc, not CLAUDE.md". Suggest a pattern: a short CLAUDE.md that points to an index of trigger -> doc routes.

## Edges

- Compaction must not change what any rule means. A checker that diffs headings, State-tag counts and dropped identifiers against the base commit caught most mistakes in wild-light's trim.
- Section-level anchors are cited from code comments; renaming one breaks citations silently.

## Touch points

`skills/requirements/SKILL.md` (scope parsing, a new Compact step, the Project template line); `cortex-validate-requirements-doc`.
