---
name: dev
description: Development entry point — routes a request to the right workflow. Use for "what should I work on", "what's next", or a feature described without naming a skill.
---

# Dev

Route a development request to the right workflow. A skill named in the request is a strong hint, not an order: judge the route yourself and say if you disagree.

## Step 1: Route

First match wins.

**Before matching on an explicit ticket id**, run `cortex-lifecycle-next <id>`. `closed` or `parked` means an outcome is already recorded. Show it with its reason and ask whether to reopen or unpark. Route only on a yes.

1. **No arguments, or "what should I work on" / "what's next"** → backlog triage (Step 3).
2. **Three or more features, or a batch** → classify each by rule 4. All above simple → `/cortex-overnight:overnight` with the list. All simple → implement each here. Mixed → show a task/routing/justification table and confirm.
3. **Vague topic** ("not sure how to approach", "explore", "investigate") → `/cortex-core:discovery <topic>`.
4. **`simple`** — you know the approach, or one read confirms it, and nothing needs deciding. Size is not the test. → Implement here and commit. Close any backlog item it resolved with `cortex-update-item {slug} --status complete` (skip with no item or an external backend). Do not write `--complexity`: nothing reads a tier recorded outside Clarify.
5. **Otherwise** → assess criticality (Step 2), then route on readiness:
   - no `spec:` (or no ticket) → `/cortex-core:refine <feature-name>` with the criticality context
   - `status: refined` with a `spec:` → `/cortex-core:build <feature-name>`
   - unsure → `cortex-lifecycle-next <feature>` reports the served phase: `research`/`specify` means refine, later means build

Plan mode records nothing in the lifecycle. A plan for routed work is build's plan phase.

## Step 2: Criticality

If `cortex/lifecycle/<feature>/` exists, read `cortex-lifecycle-state --feature <feature> --field criticality` and ask whether to resume at its served phase. A fresh start needs the user to confirm that existing artifacts are discarded.

Otherwise suggest:

- **critical** — security, money, or data loss
- **high** — shared libraries, CI/CD, migrations, foundational tooling, or a broad change that is hard to reverse
- **low** — docs and formatting
- **medium** — anything else, or when uncertain

Present it as **Criticality suggestion: `<level>`** — `<one-sentence justification>`.

## Step 3: Backlog triage

```bash
cortex-backlog-triage
```

This one call also rebuilds the index. By `state`:

- `ok` → print `blocks` exactly as given. Ask which item or parallel-safe group to pick up, then route it from Step 1. For an `idea` row, follow the printed recommendation. A multi-item pick goes through rule 2.
- `external-backend` → show `message`. The local index is not the source of truth, so route through refine or discovery and leave it alone.
- `no-index` / `error` → show `message` and stop.

If the user overrides a suggested route, their choice wins at once. If the scope changes, classify again from Step 1.
