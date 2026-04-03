---
schema_version: "1"
uuid: b7c8d9e0-f1a2-3456-bcde-678901234567
id: "024"
title: "Reconcile judgment.md with batch-brain.md"
type: chore
status: complete
priority: high
parent: "018"
blocked-by: []
tags: [overnight, prompts, quality, triage]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/harness-design-long-running-apps/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: reconcile-judgment-md-with-batch-brain-md
complexity: complex
criticality: high
spec: lifecycle/reconcile-judgment-md-with-batch-brain-md/spec.md
areas: [overnight-runner,tests]
---

# Reconcile judgment.md with batch-brain.md

## Context from discovery

The overnight runner has two prompt files that cover the same skip/defer/pause triage decision with materially different signal quality — and neither acknowledges the other exists.

**`batch-brain.md`** (~109 lines): Provides the full triage context including downstream-dependency awareness (`has_dependents`), complete learnings file, full spec excerpt, and last attempt output. Has structured field definitions, calibrated decision criteria for skip vs. defer vs. pause, and worked examples. Dispatched via `brain.py` after retry budget exhaustion.

**`judgment.md`** (~32 lines): Covers the same SKIP/DEFER/PAUSE decision with `{learnings}`, `{spec_excerpt}`, and `{error_summary}` only — no `has_dependents` field, no last attempt output, no structured calibration. "A reasonable chance" is the sole signal for when to PAUSE. No documentation of when this prompt is used vs. `batch-brain.md`, or that `batch-brain.md` exists.

A model invoked through `judgment.md` makes the same consequential triage call — which directly affects whether a feature is skipped, deferred to the human, or paused for the next overnight session — with a fraction of the relevant signal.

## What to investigate

1. When is `judgment.md` actually invoked? Find every call site in the codebase. Is it called in a path where `batch-brain.md` is not available, or is it a legacy prompt that predates `batch-brain.md`?
2. Are both still in use, or has one become dead code?
3. What is the right resolution? Options:
   - **Remove `judgment.md`** if it's unreachable or superseded — every invocation should go through `batch-brain.md`
   - **Reconcile `judgment.md`** to match `batch-brain.md`'s signal level, and document explicitly when each is invoked
   - **Document the relationship** if the split is intentional — e.g., `judgment.md` is a lightweight fallback for specific contexts, but both files should acknowledge that

## Why this matters

The brain agent's triage decision determines whether failed features become human interrupts (defer), silently skip overnight, or re-queue for the next session. A triage made with half the signal produces systematically worse decisions than one made with full context — specifically, `judgment.md` cannot factor in downstream dependency impact (`has_dependents`) or the final attempt output when calibrating the decision.
