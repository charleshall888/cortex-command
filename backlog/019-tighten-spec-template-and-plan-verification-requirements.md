---
schema_version: "1"
uuid: c2d3e4f5-a6b7-8901-cdef-012345678901
id: "019"
title: "Tighten lifecycle spec template and plan.md verification requirements"
type: chore
status: complete
priority: high
parent: "018"
blocked-by: []
tags: [overnight, specs, quality, lifecycle]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/harness-design-long-running-apps/research.md
session_id: null
lifecycle_phase: review
lifecycle_slug: tighten-spec-template-and-plan-verification-requirements
complexity: complex
criticality: high
spec: lifecycle/archive/tighten-spec-template-and-plan-verification-requirements/spec.md
areas: [lifecycle]
---

# Tighten lifecycle spec template and plan.md verification requirements

## Context from discovery

Two related gaps found in the harness design research:

**Spec template gap**: Specs are written by humans with no required structure. This causes overnight runtime deferrals — the orchestrator hits an ambiguous spec and kicks the feature back because success criteria aren't explicit. The sprint contract the article describes (explicit, pre-negotiated success criteria) is achievable without an agent-based gate — a stricter template with required sections achieves it at authoring time.

**Plan verification gap**: Verification strategies in `plan.md` are often narrative prose ("confirm the feature works correctly") rather than runnable test steps. When the feature worker self-evaluates against weak verification criteria, it passes itself too easily. The cheaper alternative to adding an evaluator agent is requiring that compliance checks be encoded as actual runnable steps.

## Gaps to close

1. The lifecycle spec template should require: explicit acceptance criteria (measurable, not narrative), explicit out-of-scope section, and concrete success conditions an agent can verify without human interpretation.
2. The plan.md verification strategy section should require: specific commands to run, specific observable outputs to verify, and explicit pass/fail criteria — not prose descriptions.

These changes reduce overnight deferrals and give the feature worker unambiguous criteria to self-check against, which reduces the surface area where an evaluator would be needed.
