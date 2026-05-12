---
schema_version: "1"
uuid: a6b7c8d9-e0f1-2345-abc1-456789012345
id: "023"
title: "Replace spec dump with JIT loading in implement prompt"
type: chore
status: complete
priority: high
parent: "018"
blocked-by: []
tags: [overnight, context, performance, quality]
created: 2026-04-03
updated: 2026-04-04
discovery_source: cortex/research/harness-design-long-running-apps/research.md
session_id: null
lifecycle_phase: implement
lifecycle_slug: replace-spec-dump-with-jit-loading-in-implement-prompt
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/replace-spec-dump-with-jit-loading-in-implement-prompt/spec.md
areas: [overnight-runner]
---

# Replace spec dump with JIT loading in implement prompt

## Context from discovery

Deep research found that the overnight runner front-loads large amounts of context into every agent invocation that could instead be fetched on demand. This directly applies the Anthropic context engineering principle: pass identifiers, let agents retrieve what they need.

**The spec dump problem**

`cortex_command/overnight/batch_runner.py` has a function named `_read_spec_excerpt` that performs no excerpting — it reads the entire spec file unconditionally:

```python
def _read_spec_excerpt(feature: str, spec_path: Optional[str] = None) -> str:
    if spec_path:
        p = Path(spec_path)
        if p.exists():
            return p.read_text(encoding="utf-8")
```

Every task worker in a batch receives the full spec verbatim before any conversation begins. For a batch of 3 concurrent features × 4 tasks each, that is 12 separate workers all loading the same document. For batch specs shared across features, this can be 5,000–8,000 tokens per worker injected regardless of whether the task needs it.

Estimated token savings: **9,600–48,000 tokens per round** depending on spec size and batch width.

**The brain agent "untruncated" problem**

`batch-brain.md` explicitly labels three inputs as "complete, untruncated": the learnings file, the spec excerpt, and the last attempt output. A brain agent making a single SKIP/DEFER/PAUSE decision routinely receives 15,000–20,000+ tokens of context, most of which is irrelevant to the classification. The signal (why did the task fail?) is buried in noise (successful intermediate steps, full spec sections unrelated to the failure).

**The learnings accumulation problem**

`_read_learnings()` is called inside `_run_task` — every task in a feature receives the full accumulated `progress.txt` and `orchestrator-note.md`, even tasks 2–N in a feature where only task 1 had a failed attempt. Late-stage tasks in a successfully-progressing feature carry retry notes that are entirely irrelevant to them.

## What to fix

1. In `implement.md`, replace `{spec_excerpt}` with `{spec_path}` and an instruction to read the spec only if needed for the specific task. Most task descriptions are self-contained; the spec is only needed for ambiguous cases.
2. In `batch-brain.md`, replace the "complete, untruncated" labeling with truncated inputs: last attempt output capped at ~2,000 tokens (head + tail strategy), learnings capped at recent entries.
3. In `_run_task`, gate learnings injection on whether prior tasks in this feature had failures — skip for first-run tasks in a clean feature.
