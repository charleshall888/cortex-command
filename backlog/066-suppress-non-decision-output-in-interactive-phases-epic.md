---
id: 66
title: "Suppress non-decision output in interactive lifecycle phases"
type: epic
status: complete
priority: high
tags: [output-signal-noise, interactive-phases]
discovery_source: research/audit-interactive-phase-output-for-decision-signal/research.md
created: 2026-04-11
updated: 2026-04-17
---

Interactive lifecycle phases — `/critical-review`, lifecycle clarify, and lifecycle specify — produce output that the user does not need to make decisions. The noise comes from agents surfacing internal work: disposition walkthroughs, critic pass/fail internals, pre-write verification narration, and fix-agent reports. The user's decision points in these phases are: answering questions (clarify §4), reviewing the synthesis (critical-review Step 3), and approving the spec (specify §4). Everything else is internal.

This epic tracks three targeted reductions across four skill files. The prior epic (#049–#053) addressed subagent output format and approval surface structure (the floor). This epic addresses what should be omitted from in-phase narration (the ceiling).

See `research/audit-interactive-phase-output-for-decision-signal/research.md` for full findings and decision records.
