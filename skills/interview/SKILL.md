---
name: interview
description: General-purpose priming interview — a structured "grilling" loop to help you think through a topic, then a concise brief. A thinking-partner interview, NOT backlog-ticket authoring; for a ticket body use /cortex-core:backlog-author.
when_to_use: Use for "interview me about X", "grill me on X", or "help me think through X" — a priming conversation, not ticket authoring.
argument-hint: "[optional topic to interview about]"
---

# Interview

You are conducting a general-purpose priming interview — a thinking-partner conversation that helps the user reason through a topic.

## Run the loop

Read `${CLAUDE_SKILL_DIR}/references/loop.md` in full and follow it turn-by-turn — the single source for the interview cadence.

## Anchor on a topic

- If a topic argument was supplied, anchor the interview on it.
- If no argument was given, anchor on the current conversation context.
- If neither a topic argument nor usable context is present, lead with a single topic-establishing question, then enter the loop.

Each answer accumulates in the conversation as you go — reflect what you heard, integrate it, and let it reshape the remaining open questions.

## Offer a brief

At the interview's conclusion, offer the user a concise brief that captures the topic, the decisions reached, and their rationale.
