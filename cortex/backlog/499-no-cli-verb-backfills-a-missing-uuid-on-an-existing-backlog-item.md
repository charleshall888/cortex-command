---
schema_version: "1"
uuid: 1cba0874-f1f8-4756-a82e-45c1b214cd44
title: No CLI verb backfills a missing uuid on an existing backlog item
status: backlog
priority: low
type: feature
created: 2026-08-19
updated: 2026-08-19
tags: ['backlog', 'uuid', 'frontmatter', 'cli']
areas: ['tooling']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-19, during #593 (two backlog tickets created on 2026-08-13 carry no
`uuid:` field).

## Why

`create_item.py` mints `uuid: str(uuid4())` for every item it creates, and the wild-light corpus
relies on that: the ratified mitigation for an id collision is *"cite by slug or by uuid, not by bare
`#N`"*. But an item that predates the field, or that was hand-authored, has no `uuid:` and there is
**no CLI verb to backfill one**.

The wild-light ticket that surfaced this says explicitly: *"Do not hand-write a `uuid:` value. Mint it
the way `cortex-create-backlog-item` does, so the format and any registry expectations hold. If the
CLI has no 'backfill uuid' verb, that is itself the finding, and adding one is the fix."*

There is no such verb. `cortex-lifecycle-backfill-index-areas` is the only backfill-shaped command and
it does something else.

## What was done instead

Two files were backfilled locally with `str(uuid4())` — the same call `create_item.py` makes — which
is correct on format but bypasses whatever else the tool would do (registry expectations, index
regeneration ordering, any future validation).

## Suggested fix

A `cortex-backfill-item-uuid <slug>` verb, or a `--backfill-uuid` mode on `cortex-update-item`, that
mints and inserts the field in the canonical frontmatter position and refuses to overwrite an existing
one. A whole-directory sweep mode would also be useful — wild-light's items `008`-`070` predate the
field entirely.
