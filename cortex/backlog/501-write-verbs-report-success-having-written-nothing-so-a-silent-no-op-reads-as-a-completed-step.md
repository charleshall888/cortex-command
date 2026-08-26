---
schema_version: "1"
uuid: 5f1d55c6-4c9b-4faa-8787-2d97808bc214
title: Write verbs report success having written nothing, so a silent no-op reads as a completed step
status: backlog
priority: medium
type: bug
created: 2026-08-25
updated: 2026-08-25
tags: ['tooling', 'lifecycle', 'silent-failure']
areas: ['tooling']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-25, during a memory audit that asked which recorded traps should be tool fixes instead.

## Why

Five separate wild-light memories exist for one shape: **a write verb prints success and writes nothing.**
Each cost a session at least one round, and each is currently mitigated only by a human remembering to
re-read the file afterwards.

| verb | what it reported | what it wrote |
|---|---|---|
| `cortex-update-item <full-slug> --complexity …` | `Updated: /…/445-….md`, exit 0 | no `complexity:`, no `criticality:` key at all (the numeric-id form worked) |
| `cortex-refine reconcile-clarify` | exit 0, no output | seed tier/criticality left in place, even with a correct `--backlog-slug` |
| `cortex-complexity-escalator --gate …` | escalation announced, event appended | backlog `complexity:` frontmatter untouched, so the next Context-A read re-sources the OLD tier |
| `cortex-lifecycle-stage-artifacts --phase complete` | staged set reported | the requirements file §3a auto-applied review drift into is not staged |
| `cortex-load-requirements` | `loaded project.md only` | under-loads on four distinct causes, all reported identically |

## Measured consequence

The failure is invisible at the call site and only surfaces downstream, usually as a *wrong* decision
rather than an error: a silently-downgraded tier skips the critical-review gate; an unstaged
requirements edit is left uncommitted and lost at merge; an under-loaded requirements set means the
build reviews against `project.md` alone.

## Suggested fix

Give every write verb a **`changed:` discriminant in its JSON envelope**, and make "reported success,
wrote nothing" impossible to state. Two concrete options, not exclusive:

1. Emit `{"state": "...", "changed": false, "reason": "..."}` whenever a verb's write is a no-op, and
   make the human-readable line say so (`No change: …` rather than `Updated: …`).
2. Exit non-zero on an argument form the verb cannot honour, instead of accepting it and doing nothing
   (the `--full-slug` vs numeric-id split in `cortex-update-item` is the clearest case).

Related existing work: #477 (clarify writes the tier but reconcile-clarify emits the event), #417 and
#428 (stage-artifacts reporting and omission defects) are the same family seen from other angles.

---

## 2026-08-25 — one row landed, row 1 refuted, three rows still open

**Row 1 is false here.** `cortex-update-item <full-slug> --complexity …` was
re-run against this repo's code: `--complexity` is in `_SCALAR_FLAGS`, maps to
the `complexity` frontmatter key, and `_set_frontmatter_value` **inserts** a key
that is absent rather than skipping it. The full-slug and numeric-id forms both
route through the same 5-step resolver. Whatever wild-light saw, it was not this.

**A real instance of the same shape was found and fixed** in the course of
checking: a file whose frontmatter block does not parse — no `---` at all, or an
opening `---` with no closing one — took every field write as a no-op.
`_set_frontmatter_value` returned the text unchanged, `update_item` rewrote it
byte-identically, `UpdateResult.changed_paths` still named it, and the CLI still
printed `Updated: <path>` at exit 0. It now raises `FrontmatterMissingError`;
the CLI prints `No change: …` to stderr and exits 1, and both cascade call
sites (blocked-by removal, parent auto-close) warn per-file rather than skipping
silently. Tests: `tests/test_update_item_cli.py`, section (g).

**Still open, unverified against this repo** — the remaining three rows:
`cortex-refine reconcile-clarify`, `cortex-complexity-escalator --gate`, and
`cortex-lifecycle-stage-artifacts --phase complete`. `cortex-load-requirements`
is off the list: it already emits one of four distinct `COVERAGE:<state>`
markers per run (`loaded` / `doc-missing` / `unmapped` / `no-area`) with a
separate note for the no-index case, which is the discriminant the row asks for.

Re-measure each remaining row before building it — one of the five was already
false, and the same could be true of the rest.
