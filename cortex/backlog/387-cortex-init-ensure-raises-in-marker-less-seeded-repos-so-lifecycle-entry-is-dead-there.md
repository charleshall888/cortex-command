---
schema_version: "1"
uuid: 490a98ee-5d44-4bd4-88b0-0eb4969ed707
title: cortex init --ensure raises in marker-less seeded repos, so lifecycle entry is dead there
status: complete
priority: medium
type: bug
created: 2026-07-16
updated: 2026-07-17
tags: ['init', 'lifecycle', 'consumer-repos']
areas: ['lifecycle']
---
> **SHIPPED (2026-07-17).** The open provenance question resolved first: the marker is gitignored by init's own `_GITIGNORE_TARGETS`, so it never survives a clone — every fresh checkout of a cortex-initialized repo is seeded-but-marker-less, and both named repos are exactly that (each carries all four committed signature templates). Fix: `_run_ensure`'s case (iv) now discriminates by those signature templates (`scaffold.find_signature_content`) and **adopts** — additive scaffold + first-time marker write, nothing overwritten, one-time stderr notice naming the marker — while signature-less content still hits R19, whose message now names the marker and both remedies so the two cases are tellable apart. Tests cover adoption (customized files byte-untouched, second run silent no-op) and the decline. `gaggimate-barista` / `Team-Builder-Bot` become usable at the next lifecycle entry once the fix releases (or today via terminal `cortex init --update`).

## Why

Two of the four cortex-using repos on this machine carry a populated `cortex/` tree but no `cortex/.cortex-init` marker. `cortex init --ensure` routes a marker-absent repo to the content-aware decline gate, which raises rather than returning — and `--ensure` is invoked automatically from lifecycle entry, in-process, on every `/cortex-core:lifecycle` run. So in those repos lifecycle entry errors before it begins, and the framework is effectively unusable there while looking installed.

Found incidentally during lifecycle 380 while inventorying seeded configs across `~/Workspaces`: `gaggimate-barista` and `Team-Builder-Bot` are both in this state, while `cortex-command` and `wild-light` carry markers and behave normally. How the two lost (or never got) their markers is not established — they may predate the marker, or have been seeded by copy rather than by `cortex init`. That question is part of the work: a repo that reaches this state silently, and only fails much later at an unrelated entry point, is the actual defect.

The decline gate is doing its job — it exists to refuse writing cortex artifacts into a populated repo that cortex did not author. The problem is the collision between a protection designed for a hostile-foreign-content case and the benign case of a real cortex repo whose marker is missing.

## Role

After this lands, a seeded repo without a marker either resolves to a usable state or fails with a message naming the marker and the remedy, at the moment the condition is detectable rather than at an unrelated later entry. The decline gate keeps refusing genuine foreign content. An operator can tell the two apart without reading the scaffold source.

## Integration

Touches the ensure dispatch's marker-absent branch and the content-decline gate it routes to, plus the marker-provenance read that already has a documented fallback for older markers lacking a hash field — an adjacent precedent for tolerating a marker that is absent rather than merely stale. Whatever resolves this must not weaken that refusal for the case it was built for, and must not clobber a consumer's customized files: the no-overwrite property of the additive scaffold pass is what makes ensure safe today.

## Edges

- The decline gate must keep refusing to write into a populated non-cortex repo — that protection is the point, not the bug.
- `CORTEX_AUTO_ENSURE=0` already silences ensure entirely; that is an opt-out, not a fix, and does not make lifecycle entry work.
- Adopting an unmarked repo must not overwrite existing files; the additive no-overwrite pass is the safe path and stays.

## Touch points

- `cortex_command/init/handler.py` — `_run_ensure`'s five-case dispatch; the marker-absent branch routes to the decline gate.
- `cortex_command/init/scaffold.py` — `check_content_decline` and `_CONTENT_DECLINE_TARGETS` (the R19 gate); also `_read_marker_provenance`'s R8 fallback for markers lacking `init_artifacts_hash`, the adjacent tolerance precedent.
- `cortex_command/lifecycle/enter.py` — calls `init_ensure.main([])` in-process on every lifecycle entry.
- `cortex_command/lifecycle/init_ensure.py` — the skill-helper that delegates to the handler with `ensure=True`.
- `cortex/requirements/project.md` — the `CORTEX_AUTO_ENSURE=0` opt-out and the R19 structural-protection note (R19 is the gate's id).
- Affected repos on this machine: `~/Workspaces/gaggimate-barista`, `~/Workspaces/Team-Builder-Bot`.
