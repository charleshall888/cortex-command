---
schema_version: "1"
uuid: a8a221b5-30d3-422c-9479-444d71fe4c48
title: Critical-review residue is the B-class action surface but is gitignored, so un-actioned findings do not outlive the session
status: should-have
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-07
---
## Why

Two completed tickets make incompatible assumptions about `critical-review-residue.json`:

- **#132** made it the action surface for B-class findings. Its acceptance criterion:
  "B-class findings have a defined action surface — e.g. auto-emit a follow-up backlog
  ticket stub for each B-class finding, **or a structured residue artifact that produces
  observable evidence when a B-class finding is not actioned. Silent dismissal of B-class
  findings is not a valid end state.**"
- **#289** scaffolds `cortex/.gitignore` for "umbrella transient artifacts", and line 35 is
  `lifecycle/**/critical-review-residue.json`.

So the durable evidence that a B-class finding went un-actioned is stored in a file
classified as transient and never committed. The surface exists; it just doesn't persist.

Observed in wild-light `overnight-2026-08-07-0252`. Three features were refined, their
specs approved, and none implemented. Critical review ran on each draft spec and produced
**nine class-B findings** — `synthesis_status: "ok"`, 2/2 reviewers on every feature. All
nine were written to residue correctly (so **#427's write fix held**) and all nine appeared
in the morning report (so **#132's surfacing held**). Neither ticket regressed.

What failed is what happens next. After the morning report is read once:

- the findings live only in gitignored files on one machine;
- nothing re-surfaces them at plan or implement time;
- the three specs are marked approved and carry no trace of the objections.

Sample of what was at stake (`two-uncoordinated-retry-budgets-share-the`): *"Unifying at 3
silently triples the repair leg's cap from 1 and deletes the ratified in-tree rationale
'Deterministic divergence does not benefit from retry: one re-request, then hard-fail
(§13.1.5)' without citing or arguing against it; grep '13.1.5' in spec.md returns zero
hits."* That is a design objection to an approved spec, and the next agent to plan the
feature would never see it.

The findings were only preserved because the operator asked about them during morning
review and they were hand-copied into tracked `critical-review-residue.md` files
(wild-light `b202b38e`). That is not a mechanism.

## Role

Make the B-class action surface outlive the session that produced it. #132's criterion is
satisfiable only if the artifact carrying the evidence is durable, or if the evidence is
copied somewhere durable before the session ends.

Options worth weighing at plan time:

- Drop `critical-review-residue.json` from the `.gitignore` template — simplest, but
  reverses #289's classification and commits machine-generated JSON.
- Emit a tracked Markdown companion (what was done by hand here) and keep the JSON
  transient — preserves #289's intent and puts the findings where a planner reads.
- Take #132's *other* offered mechanism: auto-emit a backlog ticket stub per un-actioned
  B-class finding, which is durable by construction.
- Re-surface unfolded residue at plan entry, so the evidence is presented when it is
  actionable rather than once at 03:48.

## Integration

- `cortex_command/init/` — the `cortex/.gitignore` template (#289); note
  `_relocation_migration.py` already rewrites `artifact` keys inside residue JSON, i.e.
  the file is treated as long-lived in one place and transient in another
- `cortex_command/critical_review/write_residue_cli.py` — the writer
- `cortex_command/overnight/report.py` — the current one-shot surfacing
- `skills/critical-review/SKILL.md` Step 6 — the mandated write
- `cortex_command/refine.py:693,899` — the residue writer's refine-phase call sites

## Edges

- **Non-goal**: re-opening #427 or #132. Both fixes held; this is the seam between them
  and #289.
- **Non-goal**: assessing the nine wild-light findings on their merits.
- A fix must not assume the operator runs `/morning-review` and reads the residue section
  — that is what happened here, and it was luck, not process.
- Whatever lands should be observable when residue is written and *not* folded, since
  "folded into the spec" is currently not recorded anywhere.

## Touch-points

- Source incident: wild-light `overnight-2026-08-07-0252`; preserved findings in
  `cortex/lifecycle/{campfire-ambience-is-still-welded-to,two-concurrent-test-palette-editorpy-runs,two-uncoordinated-retry-budgets-share-the}/critical-review-residue.md`
  at wild-light `b202b38e`
- Prior art: #132 (B-class action surface), #427 (residue silently dropped — the write
  path), #289 (`.gitignore` scaffold), #367 (`wontfix`, classifier/prose drift)
- Same-session siblings: #464 (number collisions), #465 ($TMPDIR worktree purge)
