---
schema_version: "1"
uuid: 783a90bb-5426-4cc3-9556-71a9405755f2
title: "Address verification_passed dead code in exit reports"
status: complete
priority: medium
type: chore
created: 2026-04-04
updated: 2026-04-06
tags: [overnight, reliability, verification]
session_id: null
lifecycle_phase: review
lifecycle_slug: address-verification-passed-dead-code-in-exit-reports
complexity: simple
criticality: high
spec: lifecycle/address-verification-passed-dead-code-in-exit-reports/spec.md
areas: [overnight-runner]
---

# Address verification_passed dead code in exit reports

## Problem

The `verification_passed` boolean field is written by every builder agent in their exit reports (`cortex_command/pipeline/prompts/implement.md` lines 81, 93, 104), but `_read_exit_report()` in `batch_runner.py` (lines 404-446) extracts only `action`, `reason`, and `question`. The field is never read by any Python code. This means an agent can report `verification_passed: false` while reporting `action: "complete"`, and the pipeline will mark the task as done regardless.

This creates a false impression that verification status is tracked when it is not. The field is dead code that looks like a safety gate.

## What to investigate

1. **Read and act on the field**: Add ~10 lines of Python to `_read_exit_report()` to extract `verification_passed`. In `execute_feature()`, if `verification_passed` is false but `action` is "complete", log a `WORKER_VERIFICATION_FAILED` event and consider pausing the task rather than proceeding.

2. **Remove the field**: If reading `verification_passed` is not worth the complexity, remove it from the builder prompt template and exit report schema. This eliminates the false confidence without adding runtime logic.

3. **Relationship to self-sealing**: Even if `verification_passed` is read, a self-sealing verification step would still produce `true` (the tautological check passes). This field addresses "did the agent run verification?" — a different trust layer than "is the verification meaningful?" (addressed by ticket 025).

## Context

Discovered during research for ticket 025 (prevent agents from writing their own completion evidence). The adversarial review identified this as the primary runtime trust gap: the pipeline trusts the `action` field from exit reports unconditionally, and `verification_passed` — the one existing signal that could catch verification failures — goes unread.
