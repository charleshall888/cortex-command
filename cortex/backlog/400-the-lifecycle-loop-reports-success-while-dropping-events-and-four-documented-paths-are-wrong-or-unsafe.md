---
schema_version: "1"
uuid: f2a152f9-6e93-44a4-82c9-e9da2da6c737
title: A lifecycle's index.md loses its backlog tags permanently, and three documented paths are broken or unsafe
status: complete
priority: medium
type: bug
created: 2026-07-17
updated: 2026-07-17
tags: ['lifecycle', 'requirements-drift', 'silent-failure', 'documentation', 'concurrency']
areas: ['skills', 'lifecycle']
---
> **SHIPPED (2026-07-17), all four findings.** **(1)** `create_index` gained the repair carve-out: a non-empty `--backlog-file` against an existing index whose `parent_backlog_uuid`/`parent_backlog_id`/`tags` lines all byte-match the Shape-B defaults rewrites exactly those three lines (plus `updated:`) from the ticket and signals `repaired`; anything hand-edited disarms it, and `artifacts`/`created`/body are never touched — so the history problem self-heals on next entry rather than needing a retroactive sweep. `cortex-lifecycle-next` now serves the resolver's backlog match on the resume envelope (`backlog.filename`, null when none), SKILL.md §Step 2 threads it instead of instructing `""`, and review.md §1 turns the no-match note into an explicit pre-dispatch warning naming the cause and the repair. The over-load edge was accepted as-is: tags→doc mapping already gates loads via project.md's Conditional Loading table. **(2)** `cortex-lifecycle-state --field --raw` emits the bare scalar — the documented caller default when the axis was never set, exit 2 when corruption makes it unknowable (never a silently-defaulted enum) — and the broken composition was fixed at all FOUR sites (implement.md, review.md, plus the same defect found in orchestrator-review.md and competing-plans.md). **(3)** Pause refusals now carry `typed_resume` naming the typed arm first (`plan-decision` for `plan-approval`); the hand-append stays the fallback. A self-review follow-up made the recommendation executable rather than circular: the pause guard (and the from-state gate's `-paused` suffix) previously refused even the typed arm — the reason the hand-append was ever needed — so a pause's owning verb now crosses its own pause; every other verb still refuses. **(4)** The commit skill's flow is `git commit --only -m … -- <paths>` with a `git show --stat HEAD` verification; the validation hook's `-m` regex is unaffected. The stale-wheel trap in Edges was NOT addressed here — it remains open for a future ticket. Findings 1–3 are pinned by new tests (repair goldens, resume-envelope linkage, `--raw` matrix, typed-resume refusal); finding 4 is prose-only with no test surface, as filed.

## Why

Found while orchestrating an 18-task interactive lifecycle end-to-end (wild-light #350, complex/high, 20 commits, implement→review→APPROVED). Four defects, each of which **lets the loop report success while doing nothing, or steers the operator onto a path the codebase itself supersedes**. Three sit in the served/documented happy path, so following the prose exactly is what triggers them.

Filed together because they share one failure mode — *a green response not backed by an effect* — but each is independently actionable and this ticket is safe to split. **Finding 1 is the one that cost real coverage** and would stand alone.

> **Filing note on rigor.** A fifth candidate (`batch_dispatch` rows dropping without `--discriminator`) was investigated and **withdrawn**: it is #385, already SHIPPED at `2bdb750e`. It reproduced for me only because this machine's installed wheel is **stale** (`~/.local/share/uv/tools/cortex-command/.../lifecycle/advance.py` is 1168 lines and lacks the `\x1f` batch composition; the repo's is 1180 and has it). Every repro below was therefore **re-verified against the repo working tree, not the installed CLI**. See Edges — the stale-wheel trap is itself worth a look.

## Findings

### 1. A lifecycle's `index.md` loses its backlog tags permanently, silently narrowing every requirements load

**This one cost real review coverage on a live ticket.**

Backlog item `350-*.md` carries `tags: ['2-5d', 'm1']`. Its lifecycle `index.md` carries:

```yaml
parent_backlog_uuid: null
parent_backlog_id: null
tags: []
```

`create_index.py:174` **does** propagate (`tags = fm.get("tags") or []`) — but only when handed a non-empty `backlog_file`. It was handed an empty one, so the Shape-B (no-backlog) path wrote `tags: []`. And `create_index` is **skip-if-exists**, so that empty-tag index is **permanent**: the feature can never recover its tags afterwards.

Downstream, deterministically:

```
$ cortex-load-requirements --feature stand-up-the-3d-presentation-shell
no area docs matched for tags: []; loaded project.md only
```

**Consequence:** the Review phase's Requirements-Drift check assessed `project.md` **only**. `cortex/requirements/render-2-5d.md` — the doc that *governs* this feature (the 3D shell, the dual-rig, the placement convention) — was never loaded or assessed. The `2-5d` tag on the backlog item is exactly the tag that maps to it. The reviewer noticed and said so; **nothing in the loop would otherwise surface it.** A drift check that silently narrows to the default doc is a gate that cannot fail.

Contributing: `skills/lifecycle/SKILL.md` §Step 2 instructs `--backlog-file ""` **on resume** ("resume carries no `backlog`, so pass `""` on resume"), and `cortex-lifecycle-enter` then reports `{"backlog_status":"no_match","index":"skipped"}` — a success shape. So a resumed lifecycle never re-derives the linkage the resolver already performed (`cortex-lifecycle-next "350"` had resolved the ID to the slug moments earlier).

**Direction**: (a) let `create_index` **repair** a Shape-B index once the backlog match is known, rather than skip-if-exists forever; (b) have resume re-derive the backlog file from the resolver instead of passing `""`; (c) surface `cortex-load-requirements`'s no-match note as a **warning** in the loop — `review.md:9` currently treats it as an ordinary fallback line, which is how it slipped past.

### 2. `implement.md`'s documented model-resolution command exits 2

`skills/lifecycle/references/implement.md:49` documents, verbatim:

```bash
model=$(cortex-resolve-model --role builder --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
```

`state_cli.py`'s own docstring says: *"With --field: JSON containing only the requested key"* — i.e. `{"criticality":"high"}`. `cortex-resolve-model --criticality` accepts only a bare enum:

```
cortex-resolve-model: error: argument --criticality: invalid choice: '{"criticality":"high"}'
                      (choose from 'low', 'medium', 'high', 'critical')
```

Copy-pasting the skill's own line fails at the **first builder dispatch of every complex lifecycle**. Worked around with a `python3 -c 'json.load(...)'` shim. Verified against the repo tree — not a stale-wheel artifact.

**Direction**: add a bare-scalar mode (`--raw`) to `cortex-lifecycle-state --field`, or fix the documented composition to parse. Prefer the former — the doc's shape is the natural one, and every complex lifecycle runs this line.

### 3. The pause refusal recommends the hand-append over its own typed arm

On an active `feature_paused` (slug `plan-approval`, kind `relayed-consent`), `advance` refuses and names (`advance.py:126-129`):

```
"sanctioned_override": "cortex-lifecycle-event log --event <name> --feature <slug> [--set k=v ...]
                        (the sanctioned out-of-band hand-append; see bin/.events-registry.md)"
```

The typed path exists, one `--help` away:

```
cortex-lifecycle-advance plan-decision --decision {branch-mode-approved,wait-approved,cancelled,revise}
```

Following the refusal's own guidance, the operator hand-appends (I appended a `phase_transition` to supersede the pause — it works, since `feature_paused` is only "last significant event", but it is out-of-band and untyped).

**Direction**: name the typed arm in the remediation for pause states that have one; keep the generic hand-append as the fallback it is. A refusal that recommends the escape hatch over its own typed surface trains operators away from the verb layer.

### 4. The commit skill's documented flow is unsafe under concurrent lifecycles

`skills/commit/SKILL.md:12`: *"stage relevant files with `git add` (specific files, not `-A`); … commit with `git commit -m`"*.

Staging specific files does **not** bound the commit. Concurrent lifecycle sessions share **one git index**, and a bare `git commit` commits the whole index — including whatever a sibling session staged. Observed in the host repo: a #350 commit swept up #349's `plan`/`spec`/`research` (caught and reset by the other session). The advice ("specific files, not `-A`") reads as sufficient and isn't.

**Direction**: instruct `git commit --only -- <pathspec>` plus a `git show --stat HEAD` verification. This project already assumes multi-session concurrency, so the commit path should be concurrency-safe by default.

## Role

Closes the gap between what the lifecycle loop *reports* and what it *did*. Findings 1, 2 and 4 are cases where the documented path is wrong, unsafe, or silently narrows its own scope; 3 is guidance that routes around the typed surface. None fail loudly, so each is found only by someone auditing the *effect* rather than the response — the opposite of what a served, event-backed loop is for.

## Integration

- **Finding 1** spans `cortex_command/lifecycle/create_index.py` (skip-if-exists vs repair), the `cortex-lifecycle-enter` resume contract, and review.md's Gather Review Inputs section. The tag→doc bullets already exist in the host repo's `project.md` Conditional Loading table — the tags simply never reach `index.md`. Adjacent to #379 (`cortex-lifecycle-enter`/state accepting a numeric feature); both concern the enter verb's backlog linkage.
- **Finding 2** is a one-line doc fix or a one-flag CLI addition; independent of the rest.
- **Finding 3** is prose-only (the `_SANCTIONED_OVERRIDE` string plus per-pause remediation); the typed arm already exists and works.
- **Finding 4** is a prose change to `skills/commit/SKILL.md`, ideally echoed in the lifecycle's builder-dispatch prose.

## Edges

- **Finding 1's fix could over-load requirements.** Propagating backlog tags means area docs start loading that previously didn't; a broadly-tagged feature could pull several docs and lengthen every review. Check the intended `areas` vs `tags` split before wiring. Also: repairing a Shape-B index in place must not clobber one a user hand-edited.
- **Finding 1 has a silent-history problem.** Every lifecycle already created via the Shape-B path carries `tags: []` and will keep loading only `project.md` after any fix, unless the repair is retroactive.
- **Finding 3 is not cosmetic** — the hand-append it recommends composes with the known `--set` int-stringification footgun (a hand-appended `review_verdict` gets `"cycle":"1"`), so the recommended path is *also* the one with the sharpest edge.
- **Finding 4 has no test surface.** Cross-session index contention is not reproducible in a single-session suite; the mitigation is prose plus the `--only` habit, and it will regress silently.
- **The stale-wheel trap deserves its own look.** This session ran a wheel 12 lines behind the repo and reproduced #385 — a bug fixed hours earlier — convincingly enough to nearly file a duplicate. There is no version-skew signal between the installed CLI and the repo: the served envelope carries a `protocol` integer, but that guards wheel↔prose skew, not wheel↔repo. An operator debugging the harness *from* the harness cannot currently tell which code they are running.

## Touch points

- `cortex_command/lifecycle/create_index.py` — `create_index()` skip-if-exists; the Shape-B `tags: []` write
- `cortex_command/lifecycle/enter.py` / the `cortex-lifecycle-enter` verb — resume re-deriving the backlog file
- `skills/lifecycle/SKILL.md` §Step 2 — the `--backlog-file ""`-on-resume instruction
- `skills/lifecycle/references/review.md` §1 — surface `cortex-load-requirements`'s no-match as a warning
- `skills/lifecycle/references/implement.md:49` — the broken model-resolution composition
- `cortex_command/lifecycle/state_cli.py` — a `--raw`/bare-scalar mode for `--field`
- `cortex_command/lifecycle/advance.py:126` — `_SANCTIONED_OVERRIDE` and the per-pause remediation
- `skills/commit/SKILL.md` §Workflow — `git commit --only -- <pathspec>`
