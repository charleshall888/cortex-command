## Why

The current ticket-authoring flow lacks a shared discipline layer, so authors
inadvertently prescribe implementation details at intake, boxing the research
phase into a single solution path rather than exploring alternatives.

## Role

A shared body-authoring sub-skill that enforces the symptom-voice Responsibility
discipline at the moment of authoring, ensuring every ticket body captures
observable problem state rather than prescribed remedies.

## Integration

The sub-skill exposes an Interface consumed by `/cortex-core:backlog new` (human
path) and `/backlog-author compose` (autonomous path). It delegates file creation
to `cortex-create-backlog-item --body`.

## Edges

Out of scope: modifying the existing `add` subcommand, extending LEX-1 to catch
English prescriptive patterns, or altering the backlog frontmatter schema. The
Boundary is the body content only — frontmatter is owned by the CLI.

## Touch points

skills/backlog-author/SKILL.md:1
skills/backlog-author/references/body-template.md:1
bin/cortex-check-prescriptive-prose:46
