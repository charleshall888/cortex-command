---
id: 53
title: Add subagent output format specs and compress synthesis
status: draft
priority: medium
type: feature
parent: 49
blocked-by: [50, 52]
tags: [output-efficiency, multi-agent, skills]
created: 2026-04-09
updated: 2026-04-09
discovery_source: research/agent-output-efficiency/research.md
---

# Add subagent output format specs and compress synthesis

## Context from discovery

Subagent dispatch prompts in critical-review, research, pr-review, and diagnose provide no output format guidance. Anthropic's multi-agent research system: "each subagent needs an objective, an output format, guidance on tools, and clear task boundaries." Use canonical examples in dispatch prompts to demonstrate expected return format — "for an LLM, examples are the pictures worth a thousand words."

Subagent output is the parent's reasoning input — the parent cannot ask follow-ups, so omitted information is permanently lost. Format specs must meet the output floor (from #050) for whichever context the subagent runs in. Overnight subagents may need more structural markers for compaction resilience than interactive ones.

Synthesis compression: bullets not prose, skip empty/failed agent sections. The synthesis step adds value but presenting both per-agent findings and synthesis creates redundancy. Only for skills where the audit (#052) showed excessive output after verbose instruction removal.
