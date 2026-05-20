---
schema_version: "1"
uuid: 80dd19af-d75c-4d64-90c0-eddb18f9b2e1
title: "Skill-prose to CLI argparse contract lint"
status: backlog
priority: medium
type: feature
created: 2026-05-20
updated: 2026-05-20
parent: "251"
tags: [harness, skill-authoring, parity-lint]
discovery_source: cortex/research/harness-friction-triage/research.md
---

## Role

Pre-commit lint that parses skill prose for `cortex-*` invocations (binary names, subcommands, flags) and verifies each invocation against the argparse surface of the named binary. Complementary to the existing `cortex-check-parity` lint, which validates reference existence at file-level altitude; this new lint operates at argument-level altitude. The drift the lint must catch includes the active `--status` / `--type` required-arg failure currently breaking three skills' invocations of `cortex-create-backlog-item`, and the `python3 -m cortex_command.discovery generate-brief` invocation in the discovery skill that no longer matches the active binary surface.

## Integration

Emits the canonical "set of `cortex-*` invocations across skills" as a derived artifact consumable by downstream tooling — specifically the installation-integrity child's PATH self-test, which previously had no canonical owner for that enumeration. Pre-commit hook integration mirrors the existing `cortex-check-parity` lint's wiring; the new lint runs alongside the existing one rather than extending it in-place.

## Edges

- Breaks if `[project.scripts]` argparse signatures are not exposable in importable form per module — the lint must introspect each named binary's argparse parser to validate flags.
- Depends on stable parsing of skill-prose `cortex-*` invocations; regex parsing tolerance must be tuned to balance false-positive cost against missed-pattern risk.
- Owns the skill-prose grep enumeration surface; other consumers (notably the PATH self-test) read from this lint's emitted artifact rather than re-running the grep independently.

## Touch points

- `bin/cortex-check-parity` — sibling lint, complementary at file-level altitude; do not extend in-place. The new lint is a separate pre-commit-stage tool.
- `pyproject.toml` lines 21-43 — `[project.scripts]` table is the source of named argparse-bearing modules.
- `skills/*/SKILL.md` and `skills/*/references/*.md` — grep targets for `cortex-*` invocations.
- `cortex_command/backlog/create_item.py:155-157` — example of the argparse contract that the lint must enforce against skill prose (active failure mode: three skills missing `--status` and `--type`).
