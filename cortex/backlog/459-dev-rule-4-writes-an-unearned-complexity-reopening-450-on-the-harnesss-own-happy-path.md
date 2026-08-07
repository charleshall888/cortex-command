---
schema_version: "1"
uuid: 0440fa4a-dd66-436d-9f9f-07910e87163a
title: 'dev rule 4 writes an unearned complexity, reopening #450 on the harness''s own happy path'
status: backlog
priority: medium
type: bug
created: 2026-08-06
updated: 2026-08-06
tags: ['lifecycle', 'tiering', 'skills']
areas: ['skills']
---
## Why

`skills/dev/SKILL.md:17` (Step 1 rule 4) instructs, for any simple change: implement it here, commit, and close the item with

    cortex-update-item {slug} --status complete --complexity simple

That writes a `complexity:` into backlog frontmatter with **no lifecycle directory, no `lifecycle_start`, and no `complexity_override` event** — precisely the shape `#450` was filed about, sanctioned in shipped prose.

Measured in this repo: **154 of 303** tickets carrying an assessed `complexity:` have no `lifecycle_slug` at all (131 `complex`, 21 `simple`, 2 `moderate`). No assessment event can be located for any of them.

`#450` was closed **wontfix** having concluded the values "arrived through a path neither of those owns — most likely hand-authored frontmatter in the `--body` payload, or a direct file write." That channel hypothesis is **wrong**. The channel is dev rule 4, and it is documented, shipped, and mirrored into `plugins/cortex-core/`.

Two consequences follow. First, `#450`'s detector — "absence of a corresponding event is the detector" — currently fires on the harness's own documented happy path, so it cannot be used as written. Second, every tier-distribution figure computed over this corpus is drawn from a population half of which cannot be shown to have been assessed; the contamination has a known direction (biased toward `simple`).

Found while refining `#453`; verified against `cortex_command/backlog/create_item.py:242-258` (no complexity flag exists at creation, so rule 4 and `cortex-update-item` are the only reachable writers).

## Role

Decide whether rule 4's write is legitimate and should be recorded as such, or is a bypass that should stop — and either way make the resulting corpus attributable, so "a tier with no event" means one thing.

## Integration

Three shapes, not obviously ordered:

- **Record it.** Rule 4's assessment is real — a triage agent judged the work simple with the ticket and repo in hand. Emit a lightweight event so the value is attributable without requiring a lifecycle directory.
- **Stop writing the tier.** Close with `--status complete` and no `--complexity`, accepting that same-session simple work leaves no tier record (which is what `#447` concluded is unmeasurable anyway).
- **Reopen `#450` with the correct channel** and let its remedy cover this, since its wontfix rests on a diagnosis now known to be false.

## Edges

- The write is not illegitimate on its face — rule 4 fires *after* an agent has read the ticket and the repo, which is better-informed than a filer estimate. The defect is the missing record, not the judgment.
- Do not add `--complexity` to the filing verb. `#450`'s standing warning still applies and is unaffected by this correction.
- Whatever lands must leave `#450`'s detector usable: a tier present with no corresponding event must remain a real signal rather than the common case.
- Deletion bias: prefer the option that removes a write over the one that adds an event, unless the tier record is shown to have a consumer.

## Touch points

- `skills/dev/SKILL.md:17` — rule 4, the write
- `cortex/backlog/450-*.md` — the wontfix whose channel hypothesis this corrects
- `cortex_command/backlog/update_item.py:625-626` — the only writer of `complexity:`
- `cortex/lifecycle/the-tier-seed-is-a-placeholder/research.md` — the 154/303 measurement and full derivation
