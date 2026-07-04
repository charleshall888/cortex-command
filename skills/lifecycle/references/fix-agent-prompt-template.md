# Fix Agent Prompt Template

Read at orchestrator-review step 3 (Fix Dispatch), on a flag verdict, when dispatching a fresh fix sub-agent.

```
You are fixing a flagged issue in the {phase} artifact for the {feature} feature.

## Issue
{description of the flagged checklist item and what is wrong}

## Current Artifact
Read cortex/lifecycle/{feature}/{artifact} for the current content.

## Phase-Specific Checklist
{paste the relevant checklist from the canonical protocol's Checklists section}

## Instructions
1. Rewrite the ENTIRE artifact to address the flagged issue, preserving all correct existing content — rewrite the full file, don't patch sections, to keep internal coherence.
2. Write the revised artifact to cortex/lifecycle/{feature}/{artifact}.
3. End your return with a YAML-style envelope using these three fields, and emit no prose before or after it:
   verdict: revised | failed
   files_changed: [<path>, ...]
   rationale: <≤15 words>

The artifact must still conform to the format defined in the {phase} phase reference.
Do not add content beyond what the phase requires.
```
