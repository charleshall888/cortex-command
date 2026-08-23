---
schema_version: "1"
uuid: 8ad0e15c-194f-4280-a4f1-6dd4683e714e
title: lifecycle_staleness is resume-only, spec-anchored and whole-HEAD, so a fresh backlog pickup gets no premise-drift signal at all
status: backlog
priority: low
type: feature
created: 2026-08-23
updated: 2026-08-23
tags: ['backlog', 'lifecycle', 'staleness', 'build', 'cli']
areas: ['tooling']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-23, during a retro on why backlog tickets go stale
(`cortex/retros/2026-08-23-0738-ticket-rot.md` in that repo).

## Why

`common.py:1513 lifecycle_staleness()` already computes the right *kind* of signal — but three
scoping choices together mean it never reaches the moment where staleness actually bites, and the one
number it does report is the variant that measurement says carries no information.

1. **It is resume-only.** Its own docstring says "Intended for the lifecycle resume offer only", and
   `skills/build/SKILL.md:41` consumes it that way ("When resuming ... surface `staleness` tersely
   (non-blocking; default continue)"). A **fresh pickup** of a backlog ticket — the common case, and
   the one where a stale premise costs the most — gets no signal at all. Nothing in `build` verifies
   that the ticket's premise is still true before planning against it.
2. **It measures from `spec.md`'s mtime**, so a ticket that has been sitting in the backlog for a week
   with no lifecycle directory has no age at all. The ticket's own `created:` is the available anchor.
3. **`commits_since_spec` counts all of HEAD** (`git rev-list --count --since=@<mtime> HEAD`).

## The measurement

Over the 36 backlog tickets a 39-agent unattended run triaged on 2026-08-22, 12 turned out to carry a
false premise (33 % base rate). Contingency tables against that outcome:

| candidate signal | rotted | healthy |
|---|---|---|
| ticket age >= 9 days | 4/10 (40 %) | 8/26 (31 %) |
| the four OLDEST tickets (15-62 days) | 0 of 4 rotted | - |
| a later code commit names the ticket | 6/12 (50 %) | 11/24 (46 %) |
| **commits touching the paths the ticket cites >= 15** | **7/12 (58 %)** | **5/24 (21 %)** |

So a **whole-HEAD** commit count — what `lifecycle_staleness` reports — is the variant with **no**
discriminative power in this corpus (the repo lands ~100 non-merge commits/day, so every artifact
older than a few hours has a large count and they are all equally large). The **path-scoped** count is
the only measured signal.

It is still not gate-worthy: 58 % precision against a 33 % base is a noise generator if it is scored,
and it is structurally blind to the largest class the retro found — **seven of the twelve tickets were
already false on the day they were filed** (by 102 minutes in one case, by two months in another), so
no since-filing window can see them.

## What I would suggest, given that

Not a score, and not a verdict. A **no-claim briefing** at pickup — the same shape as
`ignored_tokens`, printed once:

- extend `lifecycle_staleness` (or add a sibling) to take a backlog item as well as a feature dir,
  anchoring on the item's `created:` when there is no `spec.md`;
- report `commits_touching_cited_paths` — commits since that anchor over the repo-relative paths the
  ticket body cites — as a **list of commit subjects**, not a count and not a threshold. Commit
  subjects in a busy repo often name the discharge outright: the retro's #550 case reads
  *"Give the --simulate-reconnect arms a real identity oracle (#550, partial)"*, filed seven days
  before anyone noticed four of that ticket's five requirements had landed;
- alongside it, the commits whose message names the item id;
- and have `build` print it at the point it currently prints nothing, with a required one-line verdict
  from the agent (`Premise: HELD | FALSE | PARTIAL - <how established>, <date>`) before the plan
  phase. In the run this retro measures, that required output line is the entire reason twelve false
  premises were counted rather than quietly worked around one agent at a time.

## Edges

- Ticket ids are not stable in a multi-worktree repo (wild-light renumbered seven duplicated ids on
  2026-08-20 alone), so an id-keyed grep silently loses history across a renumber. `uuid:` is the
  stable key, but commit messages carry `#N`. Worth stating the limit rather than pretending recall.
- The path extraction has to tolerate paths that no longer exist; a deleted cited path is itself a
  signal and should be reported, not dropped.
- Anything that prints a *number* here will be read as a verdict. The measurement above says a verdict
  is not available at usable precision, which is the main reason to keep this a list.
