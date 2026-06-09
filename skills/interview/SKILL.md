---
name: interview
description: General-purpose priming interview — conducts a structured "grilling" loop (recommend-before-asking, one-decision-per-turn, codebase-trumps-interview, accumulate-don't-interrogate) to help you think through a topic, then offers a concise brief. This is a thinking-partner interview, NOT backlog-ticket authoring — for composing a backlog ticket body, use /cortex-core:backlog-author's interview subcommand instead.
when_to_use: Use when you say "interview me about X", "grill me on X", "help me think through X", or want a structured priming conversation before drafting or deciding. Different from /cortex-core:backlog-author — backlog-author's interview subcommand produces a ticket body; this skill is general-purpose priming and produces an in-conversation brief.
argument-hint: "[optional topic to interview about]"
---

# Interview

You are conducting a general-purpose priming interview — a thinking-partner conversation that helps the user reason through a topic. This is distinct from backlog-ticket authoring; if the user wants a ticket body, point them to `/cortex-core:backlog-author`'s interview subcommand.

## Run the loop

Read `${CLAUDE_SKILL_DIR}/references/loop.md` in full and follow it turn-by-turn. That reference is the single source for the interview cadence — do not improvise a different loop or restate its mechanics here.

## Anchor on a topic

- If a topic argument was supplied, anchor the interview on it.
- If no argument was given, anchor on the current conversation context.
- If neither a topic argument nor usable context is present, lead with a single topic-establishing question, then enter the loop.

Each answer accumulates in the conversation as you go — reflect what you heard, integrate it, and let it reshape the remaining open questions.

## Offer a brief

At the interview's conclusion, offer the user a concise brief that captures the topic, the decisions reached, and their rationale.

The user can also ask for the brief at any point mid-interview — honor that whenever it comes up. By default the brief is an in-conversation summary. If the user would prefer it written to a file, ask where, and write it to the path they specify (there is no default location).
