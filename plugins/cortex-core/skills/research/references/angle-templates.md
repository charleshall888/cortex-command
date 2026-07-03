# Conditional angle-prompt templates

These two angle templates fire conditionally, so they live here rather than inline in `SKILL.md`. The orchestrator reads this file at dispatch time (Step 3) to obtain the body, then substitutes the template's own placeholders before dispatching.

- **Tradeoffs & Alternatives** — orchestrator-chosen (the canonical example of a chosen angle). Placeholders: `{topic}`, `{INJECTION_RESISTANCE_INSTRUCTION}`.
- **Adversarial** — high/critical only, always last. Placeholders: `{topic}`, `{summarized_findings_from_other_agents}`, `{INJECTION_RESISTANCE_INSTRUCTION}`.

Per the considerations-injection contract (`SKILL.md` Step 3), the considerations-bullets placeholder is **core-only** and is deliberately absent from both templates below — do not add it.

## Tradeoffs & Alternatives (canonical example of an orchestrator-chosen angle)
Tools: Read, Glob, Grep, WebSearch
Prompt:
```
You are the Tradeoffs & Alternatives research agent for the topic: {topic}.

Your job: identify alternative approaches to implementing this topic and weigh the tradeoffs between them on four dimensions: implementation complexity, maintainability, performance, and alignment with existing patterns.

{INJECTION_RESISTANCE_INSTRUCTION}

Output format:
## Tradeoffs & Alternatives
- Alternative approach A: [description, pros, cons]
- Alternative approach B: [description, pros, cons]
- Recommended approach: [rationale]
```

## Adversarial (always last for high/critical)
Tools: Read, Glob, Grep, WebSearch
Prompt (inject the summarized findings of the completed angles before dispatch):
```
You are the Adversarial research agent for the topic: {topic}.

The following is a summary of findings from the other research agents:

{summarized_findings_from_other_agents}

Your job: challenge these findings. Identify failure modes, anti-patterns, security concerns, and edge cases that would invalidate the proposed approach. Do not simply validate what the other agents found — actively look for what they missed or got wrong.

{INJECTION_RESISTANCE_INSTRUCTION}

Output format:
## Adversarial Review
- Failure modes and edge cases
- Security concerns or anti-patterns
- Assumptions that may not hold
- Recommended mitigations
```
