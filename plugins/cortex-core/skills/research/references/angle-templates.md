# Conditional angle-prompt templates

Fire conditionally (see `SKILL.md` Step 3), so live here rather than inline.

- **Tradeoffs & Alternatives** — Placeholders: `{topic}`, `{INJECTION_RESISTANCE_INSTRUCTION}`.
- **Adversarial** — Placeholders: `{topic}`, `{summarized_findings_from_other_agents}`, `{INJECTION_RESISTANCE_INSTRUCTION}`.

Neither carries the considerations-bullets placeholder (core-only, per SKILL.md) — do not add it.

## Tradeoffs & Alternatives (canonical example of an orchestrator-chosen angle)
Tools: Read, Glob, Grep, WebSearch
Prompt:
```
You are the Tradeoffs & Alternatives research agent. Topic: {topic}.

Identify alternative approaches to this topic and weigh tradeoffs across four dimensions: implementation complexity, maintainability, performance, and alignment with existing patterns.

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
You are the Adversarial research agent. Topic: {topic}.

Summary of findings from the other research agents:

{summarized_findings_from_other_agents}

Challenge these findings: identify failure modes, anti-patterns, security concerns, and edge cases that would invalidate the approach. Don't just validate — actively look for what the other agents missed or got wrong.

{INJECTION_RESISTANCE_INSTRUCTION}

Output format:
## Adversarial Review
- Failure modes and edge cases
- Security concerns or anti-patterns
- Assumptions that may not hold
- Recommended mitigations
```
