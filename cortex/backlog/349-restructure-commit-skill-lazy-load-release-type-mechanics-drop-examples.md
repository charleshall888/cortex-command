---
schema_version: "1"
uuid: 49115a79-b56e-4200-85ed-5bcf8f4949fe
title: 'Restructure commit skill: lazy-load release-type mechanics, drop examples'
status: complete
priority: medium
type: chore
tags: ['skill-value-scorecard']
areas: ['skills']
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
complexity: complex
criticality: high
spec: cortex/lifecycle/restructure-commit-skill-lazy-load-release/spec.md
lifecycle_phase: complete
---
## Why
The commit skill body lands in context on every commit the lifecycle makes — many times per run — and the audit verified five of its sections as trim-safe. The release-type marker mechanics and their worked examples are only relevant when a release-worthy change is being committed, yet they are resident on every invocation.

## Role
Apply the verified commit-skill verdicts: move the release-type marker mechanics to a references file loaded on demand (s7), fold or drop the worked examples (s8), and compress the three narration sections (s3, s4, s5). Their rationales differ: s4 and s5 lean on the hook's loud enforcement, while s3 is What-not-How narration removal whose keep-list (stage specific files, the do-not-push directives, the verbatim preflight invocation) is NOT hook-enforced — consume the per-verdict keep-lists, not this paraphrase.

## Integration
The audit verdicts carry preconditions research should honor: the lazy-ref pointer must keep the marker tokens, the own-line rule, and the column-0 BREAKING clause visible (auto-bump misfires are silent, not hook-recoverable); the compressed style section must keep the imperative-mood guidance because the hook checks a past-tense blacklist that misses forms like Adds foo; the HEREDOC prohibition stays, with the sanctioned second -m alternative, since it counters a trained default.

## Edges
- This skill is outside the four audited clusters (transitive load) — confirm no other consumer pins the sections being moved.
- Keep the preflight invocation line verbatim.
- The file's one provisional candidate (s6, Validation) is owned here after pin verification, not by the sweep. Candidate ids are file-scoped — filter master_candidates.json by file path, not id alone.

## Touch points
- skills/commit/SKILL.md
- new skills/commit/references/ file for release-type mechanics
- plugins/cortex-core mirror (same commit)
- cortex/research/skill-value-scorecard/master_candidates.json (verdict source)