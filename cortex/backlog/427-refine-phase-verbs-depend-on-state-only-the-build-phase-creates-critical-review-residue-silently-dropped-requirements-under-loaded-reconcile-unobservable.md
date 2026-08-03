---
schema_version: "1"
uuid: b25ab4e9-4750-4dc4-a144-963ea1845b3f
title: 'Refine-phase verbs depend on state only the build phase creates: critical-review residue silently dropped, requirements under-loaded, reconcile unobservable'
status: complete
priority: high
type: bug
created: 2026-08-03
updated: 2026-08-03
tags: ['lifecycle', 'refine', 'critical-review', 'cli', 'observability']
areas: ['lifecycle', 'skills']
---
## Why

Three refine-phase defects share one shape: **a verb invoked during Clarify/Research/Spec depends on
state that only the build phase creates**, and each fails *quietly* — exit 0, no stderr, a plausible-looking
result. They are filed as one family because fixing them separately would likely re-introduce the same
class, and because the third one masks the first two.

Found while running `/cortex-core:refine 404` end-to-end in a consumer repo (wild-light) on 2026-08-03,
against plugin cache `bbbee1a120d2` (the newest installed) and `cortex-command` installed at
`~/.local/share/uv/tools/cortex-command`.

### 1. B-class critical-review residue is silently dropped for every refine-phase review (the load-bearing one)

`cortex-critical-review-write-residue --session-id` resolves the feature by globbing
`cortex/lifecycle/*/.session` and byte-comparing contents
(`cortex_command/critical_review/write_residue_cli.py:39-57`). That marker is written in exactly one place —
`cortex_command/lifecycle/enter.py:267` `_write_session()` — reached only via `cortex-lifecycle-enter`.

`/cortex-core:refine` never calls `enter`. Its Step 1 is `cortex-refine start`, which seeds `lifecycle_start`
and writes no `.session`.

The two skills are wired so this can never work during refine:

- `refine/references/specify.md` §3b **mandates** `/cortex-core:critical-review` when
  `tier = complex AND criticality ∈ {medium, high, critical}`;
- `critical-review/SKILL.md` Step 6 **mandates** the residue write in exactly the
  `cortex-critical-review-write-residue --session-id "$LIFECYCLE_SESSION_ID"` form;
- that call returns `{"state": "no-context"}` and **exit 0**, and the findings are gone.

Observed verbatim, with `LIFECYCLE_SESSION_ID` correctly set and an active lifecycle carrying
`events.log`, `index.md`, `research.md` and `spec.md`:

```
{"state": "no-context", "note": "Note: B-class residue not written — no active lifecycle context."}
```

Four B-class findings from a four-reviewer critical review were lost. The morning report — the sidecar's only
consumer — will never see them.

**This is systemic, not local setup.** In that repo: **6 `.session` files across 221 lifecycle dirs**. The 31
`critical-review-residue.json` files that do exist all belong to lifecycles that had already reached `enter`
(build/overnight). Every spec-phase critical review dispatched from refine has been losing its residue.

The `no-context` wording compounds it: the operator is told there is *no active lifecycle context* while
standing in one.

### 2. `cortex-load-requirements` under-loads at fresh refine, indistinguishably from a correct answer

It sources tags from `cortex/lifecycle/<slug>/index.md`. Nothing creates that file before Clarify, so at a
fresh refine the verb reports `no area docs matched for tags: []` and returns `project.md` only — exit 0, no
warning that coverage is partial.

Observed on ticket #404, which carries `tags: ['render', 'perf', 'tooling', 'adr']` and
`areas: ['render', 'tooling']` in its own frontmatter — the loader saw `[]`. After
`cortex-lifecycle-create-index --feature <slug> --backlog-file <basename>.md` the same call returned four
docs (`project.md`, `engineering-rendering-perf.md`, `render-2-5d.md`, `engineering-quality-gates.md`) —
three of which carried constraints that materially changed the resulting spec.

`--help` documents the fallback, so the verb behaves as specified. The defect is that a bare `project.md`
result is **indistinguishable** from "this ticket genuinely has no area docs", at the one phase where the
index cannot yet exist. Clarify's requirements-alignment rating is then made against unverified coverage —
and that rating feeds the critical-review gate.

### 3. `cortex-refine reconcile-clarify` is unobservable in both branches

`_cmd_reconcile_clarify` (`cortex_command/refine.py:195-280`) returns 0 with no stdout when it appends
override rows **and** when it no-ops (`if not rows: return 0`). The caller cannot distinguish *ratcheted*
from *already reconciled* from *silently suppressed a downgrade*.

This matters because the call is a state ratchet whose result a later gate reads: `specify.md` §3b decides
whether to run critical-review from the tier/criticality this verb just reconciled. Observed on #404 — the
call printed nothing, and only a subsequent `cortex-lifecycle-state` read confirmed it had in fact appended
`criticality_override medium→high, gate: clarify_reconcile`.

## Role

Close the refine-phase state gap so that a verb mandated during refine cannot depend on a marker only build
writes, and so that every one of these three reports what it actually did.

## Integration

- **Residue**: either have `cortex-refine start` write `.session` (making refine a first-class session owner
  alongside `enter`), or give `write-residue` a fallback resolution path that does not require the marker.
  If neither, the two skills' mandates should not compose into an impossible call.
- **`no-context` wording**: distinguish "no lifecycle directory matched this session id" from "no lifecycle
  is active" — they are different failures and only one is the operator's problem.
- **Requirements loading**: either create the index earlier (`cortex-refine start` is the natural site — it
  already knows `lifecycle_slug` and `backlog_filename_slug`), or have the loader emit a distinguishable
  signal when it fell back because the index was absent versus because the index carried no matching tags.
- **Reconcile**: emit a one-line result (`{"state": "ratcheted"|"noop", "rows": N}`) so the caller can route
  on it rather than infer.

## Edges

- Do not make `write-residue` fail loudly on a genuinely absent lifecycle — the `no-context` arm exists so
  conversation-context reviews (no lifecycle at all) skip cleanly. The fix must separate that legitimate case
  from the refine-phase one, not collapse them.
- `.session` is gitignored per the `cortex init` template
  (`cortex/lifecycle/**/.session`, `**/.session-owner`), so any fix must keep it a local, per-machine marker
  and must not start committing it.
- `discovery.py:121` reads both `.session` and `.session-owner`; `write_residue_cli.py:46` globs `.session`
  only. Whatever resolution path is chosen should be shared rather than duplicated a third time — this
  divergence is itself a latent instance of the same class.
- `reconcile-clarify` is documented as idempotent and safe on resume; adding output must not change the
  append-only/no-downgrade guards (R3-R6 in its docstring).
- The `no-op` branch is legitimately common on resume — a `noop` result must not read as an error.

## Touch-points

`cortex_command/critical_review/write_residue_cli.py` (`_resolve_feature`, :39-57; the `no-context` note at
:52-57); `cortex_command/lifecycle/enter.py` (`_write_session`, :267-271 — the sole writer);
`cortex_command/refine.py` (`_cmd_reconcile_clarify`, :195-280; and `start`, which would be the natural
`.session` write site); `cortex_command/discovery.py` (:100-121, the parallel `.session`/`.session-owner`
resolver); `cortex_command/init/` gitignore template (keeps the marker untracked);
`skills/refine/SKILL.md` Step 1 + Step 4; `skills/refine/references/specify.md` §3b (the mandate);
`skills/critical-review/SKILL.md` Step 6 (the call form); `load_requirements_cli.py`.

**Reproduction (residue):** run `/cortex-core:refine <complex, high-criticality ticket>` in a repo with no
prior `enter` for that slug; at §3b the critical review runs, and Step 6's residue call returns
`{"state": "no-context"}` with exit 0 while `LIFECYCLE_SESSION_ID` is set and the lifecycle dir is populated.
