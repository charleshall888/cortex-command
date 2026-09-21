---
schema_version: "1"
uuid: 1a171889-8217-423c-a0e5-f3a218d0d5d6
title: Requirements skill should require plain English and fewer jargon words, so docs say more in fewer tokens
status: complete
priority: medium
type: feature
created: 2026-09-21
updated: 2026-09-21
tags: ['requirements', 'token-cost', 'writing', 'filed-from-wild-light']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-09-21, during a trim of its agent docs.

## Why

Requirements docs are read by agents at every lifecycle step, so every extra word costs tokens many times. The requirements skill says what sections to write but nothing about how to write them. In wild-light the docs drifted into dense agent jargon ("load-bearing", "falsifier", "instrument", "self-sealing", "discharged", "seam", "arm") and stacked emphasis (bold + CAPS + warning signs). The jargon costs tokens and hides the idea; a new reader must decode it before they can use the rule. Halving the corpus was mostly removing this, plus history, without losing a single rule.

The package already has the pattern: `skills/hmm/SKILL.md` asks for ASD-STE100 Simplified Technical English and glossary terms.

## What to change

Add a short writing section to `skills/requirements/SKILL.md` (Synthesize step), and use the same text for drift content (#507) and the compact mode (#509):

- Plain English. Short, active sentences. One idea per sentence or bullet.
- Use common words that carry the idea. Prefer "a test that can fail" over "a demonstrated falsifier".
- Use the project's own terms from `cortex/requirements/glossary.md`. Define any other term once.
- State the rule, then at most one clause of why. No history, no dates, no "amended".
- No emphasis stacking: bold marks the rule lead only.
- Name constants and files; do not quote values that live in code.

## Edges

- Plain does not mean vague. Keep exact names, numbers that are the rule, and commands.
- Do not rewrite H2/H3 anchors or bold rule leads for style; tools read them.

## Touch points

`skills/requirements/SKILL.md`; `cortex_command/lifecycle/review_brief.py` (drift content text); the plugin mirror under `plugins/cortex-core/`.
