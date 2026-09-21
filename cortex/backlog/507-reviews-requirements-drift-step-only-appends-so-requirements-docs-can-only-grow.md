---
schema_version: "1"
uuid: 88842a44-8b4b-4e70-9ecc-0d8a7b5036fd
title: Review's requirements-drift step only appends, so requirements docs can only grow
status: complete
priority: medium
type: bug
created: 2026-09-21
updated: 2026-09-21
tags: ['requirements', 'review', 'filed-from-wild-light']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-09-21, during a trim of its agent docs (CLAUDE.md 18 KB -> 1.2 KB; requirements corpus ~1.4 MB, halved).

## Why

Review's requirements-drift step is a one-way ratchet. `skills/build/references/review.md` § 3a appends the reviewer's `Content` "at the end of the named `Section`". Nothing ever replaces or removes a line. `cortex_command/lifecycle/review_brief.py` also tells the reviewer "When you are uncertain, log `detected`".

Measured in wild-light: 98 of 219 review files (45%) report `requirements_drift: detected`. Each one grows a requirements doc by 1-3 lines. The appended lines often add to a rule a section already states, or narrate the change ("Amended 2026-09-14 (#656)"). `engineering.md` reached 277 KB.

## What to change

- Change the drift contract from **append** to **edit**. The reviewer names the existing rule it changes and gives the replacement (`File` / `Section` / `Replace` / `With`). A plain append is allowed only for a new rule with no existing home.
- Forbid history in drift content: no dates, no "amended", no "previously". A rule states the current behaviour.
- Reconsider "when uncertain, log detected". A false positive is not "small" when it runs every review, forever.

## Edges

- `review_verdict.py`, `stage_artifacts.py`, `complete_route.py` and `overnight/report.py` also parse the section. Keep `--drift`/`--breach` semantics.
- An edit whose `Replace` text no longer matches (a concurrent change) must breach loudly, not append.

## Touch points

`skills/build/references/review.md` § 3a; `cortex_command/lifecycle/review_brief.py` (drift format text); `review_verdict.py`; the plugin mirror under `plugins/cortex-core/`.
