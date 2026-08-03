---
schema_version: "1"
uuid: 7e90d5be-df19-4f60-87b2-d0adbb86c61a
title: "Discovery clarify.md has a self-referential 'skip to §4' and two missing sections, so the confidence gate has no exit"
status: complete
priority: low
type: bug
created: 2026-08-03
updated: 2026-08-03
tags: ['discovery', 'clarify', 'docs', 'routing']
areas: ['skills']
---
## Why

`skills/discovery/references/clarify.md` §4 (Confidence Assessment) ends with:

> All four high → skip to §4. Any low → ask ≤4 targeted questions covering only what's genuinely
> unclear, and wait for answers.

**That instruction is inside §4.** "Skip to §4" from §4 is a no-op at best and a loop at worst — the
happy path (all four confidence dimensions high) is told to jump to the section it is already in, so
the gate has no stated exit. The intended target is almost certainly **§6 Produce Clarify Output**,
which is the next substantive step and the only thing that consumes the assessment.

The likely cause is visible in the same file: **the section numbering is not contiguous**. It runs

```
### 1. Load Requirements Context
### 3. Check Existing Backlog Coverage
### 4. Confidence Assessment
### 6. Produce Clarify Output
### 7. Persist the Research-Sizing Assessment
```

§2 and §5 are absent. So sections were deleted or merged at some point without renumbering, and the
cross-reference was left pointing at a number whose meaning moved out from under it. Worth checking
whether the "skip to" was written when the current §4 was numbered §3 and the current §6 was §4 —
if so, the *other* surviving cross-references in the discovery skill deserve the same sweep rather
than a one-line patch here.

Found while running `/cortex-core:discovery` on wild-light (2026-08-03). Low severity because the
correct destination is inferable from context — an agent reading the whole file will do the right
thing — but it is exactly the class of instruction that misroutes a literal reader, and the fix is
a few characters.

## Role

Make the clarify phase's happy path terminate where it means to, and make the file's own section
numbers trustworthy enough to cross-reference.

## Integration

`skills/discovery/references/clarify.md` only. No CLI, no verb, no event surface. If the renumber is
taken (rather than only repointing the one reference), grep the discovery skill and any sibling that
cites `clarify.md` by section number before shifting anything, so the fix does not create the same
defect one level up.

## Edges

- **Decide between two fixes, do not do both blindly.** Either (a) minimally repoint `skip to §4` →
  `skip to §6` and leave the gaps, or (b) renumber 1–5 contiguously and update every inbound
  reference. (a) is safe and immediate; (b) removes the underlying cause but has a blast radius.
- The gaps may be deliberate — if §2/§5 were dropped because their steps moved to another phase, a
  renumber could erase a useful signal that something used to live there. Check git history for the
  deletions before renumbering.

## Touch points

- `skills/discovery/references/clarify.md` (§4's closing line; the `### N.` headings)
- `skills/discovery/SKILL.md` (Step 2 phase table — confirm it cites no clarify.md section numbers)
