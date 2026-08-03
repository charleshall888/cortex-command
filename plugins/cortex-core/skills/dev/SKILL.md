---
name: dev
description: Development entry point that analyzes requests and routes to the appropriate workflow. Use when user says "/cortex-core:dev", "what should I work on", "start working on", "dev hub", "where do I start", "next task", "what's next", or describes a feature without naming a specific skill.
---

# Dev

Route a development request to the right workflow. A named skill in the request is a strong signal, not a pass-through — analyze independently and surface any discrepancy.

## Step 1: Route

First match wins.

1. **No arguments, or "what should I work on" / "what's next"** → backlog triage (Step 3).
2. **Three or more distinct features, or a batch** → classify each as trivial or non-trivial. All non-trivial → `/cortex-overnight:overnight` with the feature list. All trivial → implement each in this conversation. Mixed → present a table of task/routing/justification and confirm before proceeding.
3. **Vague topic** ("not sure how to approach", "explore", "investigate") → `/cortex-core:discovery <topic>`.
4. **Trivial change** (single file, existing pattern, one obvious approach) → implement it here, commit, and close any backlog item it resolved: `cortex-update-item {slug} --status complete` (skip when there's no item or the backend is external).
5. **Otherwise** → assess criticality (Step 2), then route by the ticket's readiness: no `spec:` field (or no ticket at all) → `/cortex-core:refine <feature-name>` with the criticality context; `status: refined` with a `spec:` → `/cortex-core:build <feature-name>`. When unsure, `cortex-lifecycle-next <feature>` reports the served phase — `research`/`specify` means refine, anything later means build.

Never use built-in `EnterPlanMode` as a substitute for `/cortex-core:build`.

## Step 2: Criticality Pre-Assessment

If `cortex/lifecycle/<feature>/` exists, read `cortex-lifecycle-state --feature <feature> --field criticality` and ask whether to resume at its served phase. Resuming skips the suggestion below; a fresh start needs confirmation that existing artifacts are discarded.

Otherwise suggest a level from the feature description: **critical** for security, financial, or data-loss surfaces; **high** for shared libraries, CI/CD, migrations, foundational tooling, or broad hard-to-reverse blast radius; **low** for docs and formatting; **medium** otherwise and when uncertain. Present as **Criticality suggestion: `<level>`** — `<one-sentence justification>`.

## Step 3: Backlog triage

```bash
cortex-backlog-triage
```

One call resolves the backend, regenerates the index, builds the epic map, and renders both triage blocks. Act on `state`:

- **`ok`** → print `blocks` verbatim, then ask which item to pick up. Once picked,
  route it from Step 1 (first match wins) — the item's `type` and readiness are what
  rules 3-5 need.
- **`external-backend`** → relay `message`; the local index isn't authoritative, so route through `/cortex-core:refine` or `/cortex-core:discovery` without touching it.
- **`no-index`** / **`error`** → relay `message` and stop.

If the user overrides any suggested route, honor it immediately without re-arguing. If they change the scope, re-classify from Step 1.
