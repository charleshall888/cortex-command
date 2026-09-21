---
schema_version: "1"
uuid: fe390781-3f44-414b-877d-b102ac7b3912
title: Area requirements docs have no size budget, and every lifecycle phase reads them whole
status: complete
priority: medium
type: feature
created: 2026-09-21
updated: 2026-09-21
tags: ['requirements', 'token-cost', 'filed-from-wild-light']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-09-21, during a trim of its agent docs.

## Why

Area requirements docs have no size limit. `skills/requirements/SKILL.md` says "No token budget" for area scope. `cortex-validate-requirements-doc` checks only `project.md`'s `## Optional` section (1,200 tokens). `cortex-load-requirements` then makes the model read every matched doc whole, at every clarify, research, spec and review. So a doc's size is paid many times per lifecycle, and nothing notices it growing.

Measured in wild-light before the trim: `engineering.md` 277 KB (~70k tokens), `north-star-the-look.md` 144 KB, `engineering-rendering-perf.md` 127 KB. A feature with `areas: [gameplay]` loaded all of `engineering.md`.

## What to change

- Add a per-doc byte (or token) ceiling for area docs. It can be a default plus per-doc overrides in the doc or in config. `cortex-validate-requirements-doc --scope area` fails over the ceiling.
- `cortex-load-requirements` prints each listed doc's size on stderr and warns over the ceiling, so Review sees it.
- Give the fix, not only the alarm: see the companion ticket for a `compact` mode in the requirements skill.

## Edges

- The ceiling must be a ratchet that is easy to raise on purpose (one reviewed line), or it becomes a toll people learn to bypass.
- wild-light's local version: `scripts/tools/check_doc_size_ceilings.py` + `cortex/doc-budgets.json` (size rounded up to the next 2,000 bytes, blocking pre-commit). It is a working reference.

## Touch points

`cortex_command/lifecycle/validate_requirements_doc_cli.py`; `cortex_command/lifecycle/load_requirements_cli.py`; `skills/requirements/SKILL.md` (Area section).
