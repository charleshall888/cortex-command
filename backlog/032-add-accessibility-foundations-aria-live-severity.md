---
schema_version: "1"
uuid: c7d8e9f0-a1b2-3456-cdef-678901234567
id: "032"
title: "Add accessibility foundations (aria-live, multi-modal severity)"
type: chore
status: in_progress
priority: medium
parent: "033"
blocked-by: []
tags: [dashboard, ui, accessibility, a11y, aria]
created: 2026-04-03
updated: 2026-04-07
discovery_source: research/generative-ui-harness/research.md
complexity: complex
criticality: medium
spec: lifecycle/add-accessibility-foundations-aria-live-multi-modal-severity/spec.md
areas: [dashboard]
session_id: null
---

# Add accessibility foundations (aria-live, multi-modal severity)

## Context from discovery

The dashboard currently communicates state via color alone in several places (status badges, alert banner). This fails WCAG 4.1.3 and is inaccessible to color-blind users. Additionally, no live region announcements exist for dynamic content updates — screen readers receive no signal when HTMX swaps change status.

The existing DESIGN.md does not cover accessibility patterns. Ticket 035 (rubric + CONTEXT.md) adds these standards as part of the evaluation rubric. This ticket implements the foundations.

## What to produce

**1. aria-live regions for status updates**

- Status badges: add `role="status"` and `aria-live="polite"` — announced on change, non-disruptive
- Alert banner container: add `role="alert"` and `aria-live="assertive"` — announced immediately for critical failures
- Live region containers must exist in the DOM on page load (even if empty) before HTMX injects content into them; otherwise screen readers miss the first announcement

**2. Multi-modal severity indicators**

Replace color-only severity signals with icon + text + color:
- Info: ℹ️ icon + "Info" text label + blue
- Warning: ⚠️ icon + "Warning" text label + amber  
- Error/Failed: ✕ icon + "Failed" text label + red
- Alerts/critical: pulsing indicator + icon + text label

**3. ARIA labels on dynamic regions**

Add `aria-label` attributes to unlabeled interactive regions (agent fleet panel, round history table, swim-lane container). These regions currently have no semantic description for assistive technology.

## Constraints

- Implementation must reference the evaluation rubric from ticket 035 as acceptance criteria
- Icons should be `aria-hidden="true"` — the text label carries the accessible meaning
- `aria-live="assertive"` is reserved for critical failures only; routine status updates use `polite`
