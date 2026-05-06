---
schema_version: "1"
uuid: 2e617623-49e0-4eba-bbad-615af65dbbd3
title: "Fix pre-existing scan-lifecycle test failures in tests/test_hooks.sh"
status: backlog
priority: medium
type: bug
tags: [tests, hooks, scan-lifecycle, flake]
created: 2026-05-05
updated: 2026-05-05
---

# Fix pre-existing scan-lifecycle test failures in tests/test_hooks.sh

## Context

Surfaced during lifecycle 168 review (commits aa3c044..00cf886). Two tests in `bash tests/test_hooks.sh` fail and have failed since at least `c019e97` (the commit before the lifecycle 168 scaffold):

- `scan-lifecycle/single-incomplete-feature`: expected exit 0 with test-feature in additionalContext; got exit 0, context=''
- `scan-lifecycle/claude-output-format`: expected exit 0 with hookSpecificOutput key; got exit 0, has_key=false

(The third historical failure, `scan-lifecycle/fresh-resume-fires`, was closed in lifecycle 171 by deleting the test along with the `/fresh` skill it exercised.)

## Evidence

Lifecycle 168 verified the failures pre-exist at `c019e97`:

```
git checkout c019e97 -- .
bash tests/test_hooks.sh
# 15 passed, 3 failed (out of 18) -- same 3 scan-lifecycle tests fail
```

The failures test the `cortex-scan-lifecycle.sh` hook's behavior. None of the deleted hooks in #168 (output-filter, sync-permissions, bell.ps1) are touched by these tests.

## Investigation needed

- When did the scan-lifecycle tests start failing? `git log --follow tests/test_hooks.sh` + bisect against passing/failing point.
- Is the hook itself broken, or have the tests' expectations drifted?
- Does the hook work correctly when invoked manually outside the test harness?

## Acceptance

- All three `scan-lifecycle/*` tests in `bash tests/test_hooks.sh` exit 0
- `bash tests/test_hooks.sh` reports zero failures (all 16 PASS post-#168 deletion of sync-permissions block)
