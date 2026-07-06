---
name: interview
description: General-purpose priming interview — a structured "grilling" loop to help you think through a topic, then a concise brief. A thinking-partner interview, NOT backlog-ticket authoring; for a ticket body use /cortex-core:backlog-author.
when_to_use: Use for "interview me about X", "grill me on X", or "help me think through X" — a priming conversation, not ticket authoring.
argument-hint: "[optional topic to interview about]"
---

# Interview

A general-purpose priming interview: a thinking-partner conversation that helps the user reason through a topic.

## Run the loop

Read `${CLAUDE_SKILL_DIR}/references/loop.md` in full and follow it turn-by-turn — the single source for interview cadence.

## Anchor on a topic

- Topic argument supplied: anchor on it.
- No argument: anchor on the current conversation context.
- Neither present: ask one topic-establishing question, then enter the loop.

## Offer a brief

At the interview's conclusion, offer a concise brief: the topic, the decisions reached, and their rationale.
