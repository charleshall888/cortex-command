---
id: 51
title: Add hook-based preprocessing for test/build output
status: complete
priority: high
type: feature
parent: 49
tags: [output-efficiency, hooks]
created: 2026-04-09
updated: 2026-04-09
discovery_source: research/agent-output-efficiency/research.md
session_id: null
lifecycle_phase: implement
lifecycle_slug: add-hook-based-preprocessing-for-test-build-output
complexity: complex
criticality: high
spec: lifecycle/add-hook-based-preprocessing-for-test-build-output/spec.md
areas: [hooks]
---

# Add hook-based preprocessing for test/build output

## Context from discovery

Anthropic's cost documentation demonstrates a PreToolUse hook that intercepts test runner commands and filters output to failures only — `grep -A 5 -E '(FAIL|ERROR|error:)' | head -100`. This reduces thousands of lines to relevant failures before tokens enter the context window. Deterministic, no model judgment, guaranteed reduction.

Hook-based preprocessing handles the easy cases (test output, linter output, build logs) where the filtering criteria are known and stable. This is independent of all other tickets — it works regardless of output floor definitions or skill prompt changes. Hook output enters context without truncation ("keep output concise since it enters context without truncation" — Claude Code docs), so the hook must be the truncation point.
