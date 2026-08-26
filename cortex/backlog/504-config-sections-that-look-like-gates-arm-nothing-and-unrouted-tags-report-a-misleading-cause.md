---
schema_version: "1"
uuid: 2508ebfa-397d-4ce2-bb7e-fddce15698f0
title: Config sections that look like gates arm nothing, and unrouted tags report a misleading cause
status: complete
priority: low
type: bug
created: 2026-08-25
updated: 2026-08-25
tags: ['config', 'requirements', 'review-gate']
areas: ['tooling']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-25, during a memory audit that asked which recorded traps should be tool fixes instead.

## Why

Config sections that **look** like they arm a gate, but are loaded by nothing. Two confirmed in
wild-light, and both read as authoritative to a human and to an agent.

1. **`## Review Criteria` in `cortex/lifecycle.config.md` arms nothing.** Measured during #479
   (2026-08-06): `grep -rn "Review Criteria"` across the entire installed skill package returns hits
   only in the scaffolded template asset. Nothing loads the section. Only the frontmatter
   `test-command` is executed at Review. So a bullet added there — the natural place to put a new
   review requirement — is inert prose.

2. **`## Conditional Loading` in `cortex/requirements/project.md` silently drops unrouted tags.**
   `cortex-load-requirements` matches tags against that table; a tag with no bullet yields
   `no area docs matched … loaded project.md only`, which reads as an index problem and is not one.
   A `must (process)` requirement in wild-light (`visual-composition.md`'s Look Ledger) is owed by
   every windowed GO/NO-GO session and is routed by no tag, so the obligation reaches nobody.

## Measured consequence

Both fail in the same direction: **a requirement is written down, looks armed, and binds nothing.**
Nobody finds out until an audit. In wild-light this produced an un-run process obligation and at
least one proposed "gate" that was never a gate.

## Suggested fix

Make unrouted config visible rather than inert:

- Have the config loader **warn on any recognised heading it does not consume** (`## Review Criteria`
  is the reference case), or drop the heading from the scaffolded template so nobody fills it in.
- Have `cortex-load-requirements` distinguish its outcomes: "tag has no bullet in the Conditional
  Loading table" is a different, fixable condition from "index is absent or stale", and today both
  print the same line. Naming the cause turns a 20-minute diagnosis into a one-line edit.

Related: #469 (no lifecycle area requirements doc, so lifecycle tickets review against project.md
only) is the same failure seen from the requirements side.

---

## 2026-08-25 — part 1 fixed, part 2 was already done

**Part 1 confirmed and fixed.** `grep -rn "Review Criteria"` over this repo hit
only the two scaffolded template assets and this repo's own
`cortex/lifecycle.config.md`; no code path reads the section. Both halves of the
suggested fix landed:

- `lifecycle_config._warn_config_headings` warns on stderr (once per process per
  heading) for any `##` body section no consumer reads — the body-level
  counterpart to the existing `_warn_config_keys`, same fail-open contract.
- The heading is gone from both scaffolded templates, so a new repo is never
  handed the trap. This repo's own four criteria were deleted rather than moved:
  every one of them was already stated somewhere that is actually read
  (`CLAUDE.md` for the settings-JSON, `chmod +x` and no-host-symlinks rules;
  `docs/policies.md:13` for skill `name`/`description` frontmatter, which
  `tests/test_l1_surface_ratchet.py` enforces).

**Part 2 needs nothing.** `cortex-load-requirements` already emits exactly one
`COVERAGE:<state>` line per run over four distinct states — `loaded`,
`doc-missing`, `unmapped`, `no-area` — each with its own human-readable note,
including a separate `NO_INDEX_NOTE_TEMPLATE` for the fresh-refine case whose
coverage is "UNVERIFIED, not empty". "Tag has no bullet" (`unmapped`) and "index
is absent" (`no-area` with the no-index note) are already different lines.
