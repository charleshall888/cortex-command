---
schema_version: "1"
uuid: b4e2d9f3-8c5e-4f0b-a7d2-e3f4a5b6c7d8
title: "Verify escape hatch bypass mechanism"
status: complete
priority: high
type: spike
tags: [permissions-audit, security]
created: 2026-04-09
updated: 2026-04-09
parent: 054
discovery_source: research/permissions-audit/research.md
session_id: null
lifecycle_phase: review
lifecycle_slug: verify-escape-hatch-bypass-mechanism
complexity: simple
criticality: high
spec: lifecycle/verify-escape-hatch-bypass-mechanism/spec.md
areas: [skills]
---

# Verify escape hatch bypass mechanism

## Context from discovery

The research claims `bash -c "denied-command"` bypasses deny-list patterns because glob matching operates on the full command string (matching `Bash(bash *)` allow, not `Bash(rm -rf *)` deny). This is the foundation for removing interpreter wildcards (ticket 057). However, Claude Code already performs semantic analysis of `&&` compound commands — it may also inspect `bash -c` arguments.

## What to test

Empirically verify whether:
1. `bash -c "git push --force origin main"` is blocked by `Bash(git push --force *)` deny, or allowed by `Bash(bash *)` allow
2. `python3 -c "import os; os.system('git push --force origin main')"` — same question for Python wrapper
3. `sh -c "rm -rf /tmp/test"` — whether `Bash(rm -rf *)` deny fires through sh wrapper

## Acceptance criteria

- Each test case has a definitive pass/block result
- Findings documented in the research artifact or a brief report
- Ticket 057 priority adjusted based on results (if bypass confirmed: high priority; if blocked: lower priority or close)
