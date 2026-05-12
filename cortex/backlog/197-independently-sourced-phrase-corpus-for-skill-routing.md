---
schema_version: "1"
uuid: b6f13a48-2777-43c5-8e0a-5b1a0edba201
title: "Independently-sourced phrase corpus for skill routing"
type: feature
status: closed
priority: medium
blocked-by: []
tags: [testing, skill-design, routing]
created: 2026-05-11
updated: 2026-05-12
---

# Independently-sourced phrase corpus for skill routing

## Role

Build a routing-recall test corpus whose phrases are sourced independently of the canonical `skills/<name>/SKILL.md` `description:` text. The current `tests/fixtures/skill_trigger_phrases.yaml` fixture is a content-preservation gate — its phrases are sampled FROM each canonical SKILL.md description, so it locks in known-routing substrings against silent drop during description compression, but it cannot detect routing-recall gaps for utterances that are absent from the current description. The parent lifecycle calls out this partial-coverage acknowledgment and defers the independently-sourced corpus to a follow-up (see Provenance).

## Integration

- Adds a new test surface alongside `tests/test_skill_descriptions.py` that drives an independently-sourced phrase list (sourced from user transcripts, requirements docs, intent-classification exercises, or empirical routing-failure logs — NOT from the SKILL.md description being tested)
- Each phrase is paired with an expected-skill label; the test asserts the canonical description either contains a trigger substring routing the phrase to the expected skill, or a documented routing rationale is present (e.g. a synonym pattern)
- Does not replace the content-preservation fixture; the two corpora coexist (one protects known phrases from being dropped, the other surfaces routing gaps for phrases that should be supported but aren't yet)
- Wires into the lifecycle review phase so any new skill must declare ≥3 independently-sourced phrases before merge

## Edges

- Source-of-phrases authority — must define an authoritative non-circular source policy (transcript mining? user-interview pulls? requirements-doc terms?) so the corpus does not silently re-derive from descriptions
- Failure mode — distinguishes "phrase missing from description" (routing gap) from "phrase present but model still mis-routes" (model-behavior failure outside the description surface) per OQ3 effort-first escalation policy
- Maintenance — corpus must be reviewed each time a new skill ships, with an explicit no-regression gate for previously-passing phrases

## Touch-points

- `tests/fixtures/skill_trigger_phrases.yaml` — existing content-preservation fixture (kept; this ticket adds a sibling corpus, does not modify this file)
- `tests/test_skill_descriptions.py` — existing substring-presence test; this ticket adds a parallel test file
- `skills/*/SKILL.md` — canonical skill descriptions are the indirect target of the routing-recall check

## Provenance

Filed as part of Task 3 of the `reduce-boot-context-surface-claudemd-skillmd` lifecycle (spec R2 deferred follow-up). See `lifecycle/reduce-boot-context-surface-claudemd-skillmd/spec.md` for the original anti-rationalization rationale that motivates the independently-sourced corpus.

## Closed 2026-05-12

Closed as premature. The source-of-phrases authority (the hardest part) is unresolved and the corpus risks silently re-deriving from descriptions. Empirical detector already exists via `events.log` F-rows under the MUST-escalation policy — real routing failures surface there with effort-first escalation. No evidence yet of a routing-recall failure pattern that a speculative pre-built corpus would have caught.

**Reopen trigger**: ≥5 observed routing-recall failures in `events.log` (or transcript citations) where users said a phrase no skill description captured. At that point the corpus has real evidence to source from.
