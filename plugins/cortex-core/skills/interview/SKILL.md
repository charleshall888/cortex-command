---
name: interview
description: General-purpose priming interview — a structured "grilling" loop to help you think through a topic, then a concise brief. A thinking-partner interview, NOT backlog-ticket authoring; for a ticket body use /cortex-core:backlog-author.
when_to_use: Use for "interview me about X", "grill me on X", or "help me think through X" — a priming conversation, not ticket authoring.
argument-hint: "[optional topic to interview about]"
---

# Interview

A thinking-partner conversation that helps the user reason through a topic. Anchor on the topic argument; absent one, on the current conversation; absent both, ask one topic-establishing question first.

## The loop

**Ask in prose, and let each answer shape what follows.** Group questions that stand independent of each other; hold back any question whose shape or existence depends on an answer you don't have yet. A list fixed up front commits to later questions before earlier answers arrive.

**Recommend before asking.** Lead with your defensible default and reasoning, then ask them to confirm or redirect. Suppress this on taste questions, where recommending contaminates the preference you meant to elicit.

**Let the codebase trump the interview.** When code or on-disk context already answers something, confirm what you found rather than asking cold. Reserve live questions for intent, priorities, scope boundaries, and the bars judgment sets.

**Funnel broad to narrow.** Map the territory before closing in.

**Stop at saturation** — when new answers stop changing the picture, not at template coverage. Honor an early stop immediately; once substantial ground is covered, offer a "keep going or wrap up?" check.

Close with a concise brief: the topic, the decisions reached, and their rationale.
