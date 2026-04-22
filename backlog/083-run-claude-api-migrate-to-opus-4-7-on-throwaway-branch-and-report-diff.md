---
schema_version: "1"
uuid: c9e64818-a84e-4d6f-96d4-bd2c86f12d39
title: "Run /claude-api migrate to opus-4-7 on throwaway branch and report diff"
status: complete
priority: high
type: spike
created: 2026-04-18
updated: 2026-04-21
parent: "82"
tags: [opus-4-7-harness-adaptation, spike]
discovery_source: research/opus-4-7-harness-adaptation/research.md
session_id: 8461c4c8-0ac6-44b0-bc40-344b81200a05
lifecycle_phase: research
lifecycle_slug: run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff
complexity: simple
criticality: medium
spec: lifecycle/run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff/spec.md
areas: [skills]
---

# Run /claude-api migrate to opus-4-7 on throwaway branch and report diff

## Motivation

Per DR-7 in the research artifact, Anthropic ships `/claude-api migrate this project to claude-opus-4-7` as a built-in Claude Code command. Before hand-editing prompts in #085, we should see what the official automation changes. Its output may absorb most of #085's scope, part of it, or none — we don't know.

## Research context

Open Question 1 from discovery:

> Does `/claude-api migrate this project to claude-opus-4-7` operate on SKILL.md prompts or only on Anthropic SDK/API Python code? Answering requires running the command on a throwaway branch and diffing. This determines whether DR-7 absorbs most of DR-2+DR-5 or is narrower.

## Deliverable

A written report committed to `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` (exact path — #085 consumes this) covering:
- Which files the command touched (SKILL.md prompts? Python SDK code? both?)
- What kinds of changes it made (model ID updates, parameter removals, prefill migration, prompt rewrites?)
- Whether its output is usable as-is for #085, partially usable, or irrelevant to the prompt-audit scope

## Scope

- Exploratory only — no changes merged from the throwaway branch without review
- Report informs the scope and approach of #085 (prompt audit)
