---
schema_version: "1"
uuid: 9c60730c-dc4d-4fab-bb81-1aced8f84d17
title: Offload load-requirements.md selection to a cortex-load-requirements verb
status: backlog
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-26
parent: 336
---
## Why

`load-requirements.md` (4.8KB) narrates a deterministic selection algorithm — read `project.md`, match area docs by tag, apply the fallback when no tags match — that the model hand-executes in the Specify, Review, and Clarify phases. ~55-65% of the file is the algorithm; only "read the selected files" needs the model. Strongest un-ticketed single-file offload. Surfaced in the 2026-06-25 lifecycle reference-file audit.

## Role

A `cortex-load-requirements [--tags ...]` verb prints the resolved file list (`project.md` + matched area docs, with the no-match fallback noted); the skill reads the listed files. The reference collapses to "run it, read what it lists, inject the list into the prompt."

## Integration

New `cortex_command` verb + entry + edits to `references/load-requirements.md` (+ mirror) and the three consumers' one-line references → lifecycle-gated. The fallback note string (`"no area docs matched for tags: {tags}; drift check covers project.md only"`) is consumed by `review.md`'s reviewer prompt — preserve it (emit it from the verb).

## Edges

- No tags / no area docs → `project.md` only + fallback note, not an error.
- Tag-matching rules must reproduce the current prose exactly.
- The verb prints **paths only** — it does not read or concatenate file contents (the model still reads them, so requirements text never enters the verb's output).

## Touch-points

- new `cortex_command` module + entry + test
- `skills/lifecycle/references/load-requirements.md` + the Specify / Review / Clarify reference lines (+ mirrors)