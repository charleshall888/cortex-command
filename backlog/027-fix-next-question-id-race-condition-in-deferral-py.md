---
schema_version: "1"
uuid: ae7fb8f9-20a2-4563-b973-db3b96210270
title: "Fix next_question_id() race condition in deferral.py"
status: refined
priority: medium
type: bug
tags: [overnight, reliability, deferral, bugs]
created: 2026-04-03
updated: 2026-04-04
parent: "018"
session_id: 9f032731-414f-4302-843b-813ce5282784
lifecycle_phase: implement
lifecycle_slug: fix-next-question-id-race-condition-in-deferral-py
complexity: simple
criticality: high
spec: lifecycle/fix-next-question-id-race-condition-in-deferral-py/spec.md
areas: [overnight-runner]
---

## Context

Found during lifecycle 022 research (adversarial agent review).

`next_question_id()` in `claude/overnight/deferral.py` generates IDs by scanning the filesystem for existing deferral files and returning `max_id + 1`. Under concurrent async execution (`asyncio.gather` in batch_runner), two features can call this simultaneously, both read the same max_id, and both generate the same question ID — causing one deferral to silently overwrite the other.

The function's docstring reportedly claims it is "thread-safe via filesystem" but the glob + max pattern is not atomic.

## What to investigate

One approach might be to replace the glob-based ID generation with an atomic counter — for example, using a lock file, an OS-level `O_EXCL` create loop, or a monotonic counter persisted alongside the deferral files. Research should evaluate which approach fits the existing file-based state architecture without adding dependencies.
