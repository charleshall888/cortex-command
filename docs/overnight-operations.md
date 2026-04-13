[← Back to overnight.md](overnight.md)

# Overnight: Operations and Architecture

**For:** operators and contributors debugging overnight. **Assumes:** familiarity with how to run overnight.

> **Jump to:** [Architecture](#architecture) | [Code Layout](#code-layout) | [Tuning](#tuning) | [Observability](#observability) | [Security and Trust Boundaries](#security-and-trust-boundaries) | [Internal APIs](#internal-apis)

---

## Architecture

### The Round Loop and orchestrator_io

### Post-Merge Review (review_dispatch)

### Per-Task Agent Capabilities (allowed_tools)

### brain.py — post-retry triage (SKIP/DEFER/PAUSE)

### Conflict Recovery (trivial fast-path and repair fallback)

### Cycle-breaking for repeated escalations

### Test Gate and integration_health

### Startup Recovery (interrupt.py)

### Runner Lock (.runner.lock)

### Scheduled Launch subsystem

---

## Code Layout

### claude/pipeline/prompts — per-task dispatched prompts

### claude/overnight/prompts — orchestrator/session-level prompts

---

## Tuning

### --tier concurrency (Concurrency Tuning)

### lifecycle.config.md fields and absence behavior

### overnight-strategy.json contents and mutators

---

## Observability

### Log Disambiguation (events.log, pipeline-events.log, agent-activity.jsonl)

### Escalation System (escalations.jsonl)

### Morning Report Generation (report.py)

### Dashboard Polling and dashboard state

### Session Hooks (SessionStart, SessionEnd, notification hooks)

---

## Security and Trust Boundaries

### --dangerously-skip-permissions and sandbox surface

### Tool bound at the SDK level (_ALLOWED_TOOLS)

### Dashboard binds 0.0.0.0, unauthenticated

### Keychain prompt as session-blocking failure mode

### Auth Resolution (apiKeyHelper and env-var fallback order)

---

## Internal APIs

### orchestrator_io re-export surface
