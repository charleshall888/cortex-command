---
name: dev
description: Development entry point — routes a request to the right workflow. Use for "what should I work on", "what's next", or a feature described without naming a skill.
---

# Dev

Route a development request to the right workflow. A named skill in the request is a strong signal, not a pass-through — analyze independently and surface any discrepancy.

## Step 1: Route

First match wins. **Before matching an explicit ticket id**, run `cortex-lifecycle-next <id>`: `closed` or `parked` means an outcome is already recorded — relay it with its reason and ask whether to reopen or unpark; route only on a yes.

1. **No arguments, or "what should I work on" / "what's next"** → backlog triage (Step 3).
2. **Three or more features, or a batch** → classify each by rule 4. All above simple → `/cortex-overnight:overnight` with the list. All simple → implement each here. Mixed → present a task/routing/justification table and confirm.
3. **Vague topic** ("not sure how to approach", "explore", "investigate") → `/cortex-core:discovery <topic>`.
4. **`simple`** (you know the approach, or one read confirms it; nothing to decide — size is not the test) → implement here, commit, and close any backlog item it resolved with `cortex-update-item {slug} --status complete` (skip with no item or an external backend). Write no `--complexity` — a tier recorded outside Clarify has no reader.
5. **Otherwise** → assess criticality (Step 2), then route on readiness: no `spec:` (or no ticket) → `/cortex-core:refine <feature-name>` with the criticality context; `status: refined` with a `spec:` → `/cortex-core:build <feature-name>`. When unsure, `cortex-lifecycle-next <feature>` reports the served phase — `research`/`specify` means refine, later means build.

Plan mode records nothing in the lifecycle; a plan for routed work is build's plan phase.

## Step 2: Criticality

If `cortex/lifecycle/<feature>/` exists, read `cortex-lifecycle-state --feature <feature> --field criticality` and ask whether to resume at its served phase (a fresh start needs confirmation that existing artifacts are discarded). Otherwise suggest: **critical** for security, financial, or data-loss surfaces; **high** for shared libraries, CI/CD, migrations, foundational tooling, or broad hard-to-reverse blast radius; **low** for docs and formatting; **medium** otherwise or when uncertain. Present as **Criticality suggestion: `<level>`** — `<one-sentence justification>`.

## Step 3: Backlog triage

```bash
cortex-backlog-triage
```

One call resolves the backend, regenerates the index, builds the epic map, and renders both triage blocks. `ok` → print `blocks` verbatim, ask which item or parallel-safe group to pick up, then route it from Step 1 (honor the printed recommendation for an `idea` row; a multi-item pick routes through rule 2). `external-backend` → relay `message`; the local index isn't authoritative, so route through refine or discovery without touching it. `no-index` / `error` → relay `message` and stop.

A user override of any suggested route wins immediately; a scope change re-classifies from Step 1.
