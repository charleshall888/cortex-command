---
schema_version: "1"
uuid: f2ff13f3-bd84-4274-8633-d757c9d4148a
title: A tier can be written into backlog frontmatter at filing time, bypassing the Clarify assessment entirely
status: backlog
priority: low
type: bug
created: 2026-08-04
updated: 2026-08-04
tags: ['lifecycle', 'tiering', 'backlog-verbs']
areas: ['backlog']
---
## Why

A ticket can acquire a complexity and criticality without ever passing through the Clarify assessment that is supposed to set them, leaving an unearned tier in the record with no reasoning trail.

Observed live on one ticket in a consumer corpus: frontmatter carries `complexity: complex` / `criticality: high`, but there is **no lifecycle directory**, **no `events.jsonl`**, and **no `complexity_override` event**. `git log -S` shows both values were introduced by that ticket's own filing commit. Its sibling tickets show the intended shape by contrast — `lifecycle_start` seeded, then `complexity_override ... gate: clarify_reconcile` after research.

The filing path does not obviously permit this: `cortex-create-backlog-item --help` exposes only `--title/--status/--type/--priority/--rework-of/--parent/--tags/--areas/--body`, with no `--complexity` or `--criticality`, and `skills/backlog-author/SKILL.md` explicitly disclaims frontmatter ("frontmatter belongs to `cortex-create-backlog-item --body`"). So the values arrived through a path neither of those owns — most likely hand-authored frontmatter in the `--body` payload, or a direct file write. **Identifying the actual channel is the first task; the fix follows from it.**

Impact is small per occurrence but lands squarely on the measurement this repo is about to rely on: a tier assigned without assessment is indistinguishable, downstream, from one the escalator earned. the distribution-instrument and override-rationale tickets both degrade if unearned tiers are in the corpus.

## Role

Close the path by which tier values reach backlog frontmatter without an assessment, so a recorded tier always means an assessed one.

## Integration

The intended writers are Clarify's write-back (refine SKILL.md Step 2) and the `complexity-override` / `criticality-override` verbs. `create_item.py` builds frontmatter from its argparse fields and appends `--body` verbatim after it — so a `--body` payload that itself opens with frontmatter-shaped lines is a candidate channel worth checking first.

## Edges

- Reproduce before fixing. The current filing code may not permit this at all, in which case the defect is historical or lives in a hand-edit path, and a guard is the right shape rather than a code change.
- A validating guard is cheap and self-reporting: reject (or warn on) a create whose body introduces frontmatter keys the verb owns.
- Do not simply add `--complexity`/`--criticality` flags to the filing verb. That would legitimise the bypass rather than close it — the whole point is that the tier is Clarify's output, not the filer's input.
- Some tickets legitimately carry a tier at `status: backlog` — one that was clarified and then parked will have both a tier and a matching `complexity_override` event. Presence of a tier at `backlog` status is therefore **not** the detector; absence of a corresponding event is.

## Touch points

- `cortex_command/backlog/create_item.py` — frontmatter construction and `--body` append
- `plugins/cortex-core/skills/backlog-author/SKILL.md` — disclaims frontmatter ownership
- `plugins/cortex-core/skills/refine/SKILL.md` Step 2 — the canonical write-back that should be the only source
- `cortex_command/lifecycle_event.py` — `complexity_override` / `criticality_override`, the other legitimate writers
