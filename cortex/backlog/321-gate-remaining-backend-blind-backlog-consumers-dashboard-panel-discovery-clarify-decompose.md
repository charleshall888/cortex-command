---
schema_version: "1"
uuid: 90afa6d5-7fb4-4923-8192-9a77e8588eed
title: Gate remaining backend-blind backlog consumers (dashboard panel, discovery clarify/decompose)
status: refined
priority: low
type: bug
created: 2026-06-24
updated: 2026-06-24
parent: "315"
tags: ['backlog-optional-plugin']
lifecycle_phase: research
lifecycle_slug: gate-remaining-backend-blind-backlog-consumers
complexity: complex
criticality: medium
spec: cortex/lifecycle/gate-remaining-backend-blind-backlog-consumers/spec.md
areas: ['backlog']
---
## Why

Epic #315 / #317 made the backlog backend config-driven (`cortex-backlog` | `none` | external). A three-angle audit — run while verifying the refine empty-backlog exit-70 fix (commit "Stop refine/lifecycle halting on a clean external-backend repo") — confirmed the reassuring part: **no consumer hard-halts** on a non-local backend, the interactive lifecycle skills and the overnight pipeline are correctly backend-gated, and the `cortex_command/` CLIs handle empty/absent states cleanly (the resolver fix was a true outlier, not the tip of an iceberg). But it found **three local-backlog operations that are still backend-blind**: they read or write `cortex/backlog/` unconditionally, with no `cortex-read-backlog-backend` check. None block, so this is #318-class hardening rather than an emergency — but it leaves the "select a different backend" experience inconsistent: under an external backend they surface stale local data as authoritative or do wasteful local writes, and under `none` (a shipped, supported backend) they still touch local backlog instead of standing down.

Relationship to #318: #318 (external-tracker best-effort *create/write-back* arm) is `wontfix`. This item is **not** that — it is about *suppressing* the wrong local behavior, which is independently relevant for the shipped `none` backend and does not depend on the external arm ever being built. Do not reflexively wontfix it alongside #318.

## Role

Make the three remaining backend-blind backlog consumers resolve the backend first and route like the already-correct consumers (dev Step 3, discovery decompose's create-routing, refine, morning-review's auto-close):

1. **Dashboard backlog panel** — `cortex_command/dashboard/poller.py:353` + `data.py:987,1047` (+ the panel template). The slow poller reads local `cortex/backlog/` (`parse_backlog_counts` / `parse_backlog_titles`) with zero backend check. Reachable via the standalone `cortex dashboard` command on any repo (not overnight-only). Resolve `resolve_backlog_backend(root)` once; when != `cortex-backlog`, skip the local reads and render a "backlog tracked externally / disabled" placeholder instead of stale local counts. NOTE: this path is in `cortex_command/dashboard/` — NOT a lifecycle-gated path, so it can be fixed without a lifecycle (like the resolver fix was); the discovery edits below ARE gated.

2. **Discovery clarify — Check Existing Backlog Coverage** — `skills/discovery/references/clarify.md:21`. The scan reads local `cortex/backlog/[0-9]*-*.md` before any backend is resolved (the cleanest true sibling of the original bug: a local-backlog assumption fired before the config that exempts it). Gate it on `cortex-read-backlog-backend` like decompose's create-routing / promote-sub-topic already do — on a non-`cortex-backlog` backend, skip the local scan with a one-line advisory (or check the external tracker best-effort per `backlog.instructions`).

3. **Discovery decompose — Update Index** — `skills/discovery/references/decompose.md:189`. `cortex-generate-backlog-index` runs unconditionally after the gated create-routing, so under `none`/external it regenerates a stale/empty local index (it does not error — `atomic_write` auto-creates dirs — so this is the mildest of the three). Move it inside the `cortex-backlog` arm, or wrap it in the same backend check.

## Integration

Reuse the established pattern with no new machinery: `cortex-read-backlog-backend` (skills) / `resolve_backlog_backend` (Python), three-arm route — `cortex-backlog` -> as-today (the regression anchor), `none` -> skip + one-line advisory, external -> best-effort per `backlog.instructions` (or simply skip the local op; the external create arm is wontfix per #318). The discovery SKILL/reference edits auto-mirror into `plugins/cortex-core/` via the dual-source pre-commit hook — edit canonical sources only.

## Edges

- Clean external repo: `cortex/backlog/` holds only the scaffolded `README.md` (zero `NNN-*.md` items), so all three already behave benignly (empty). The visible defect requires **stale leftover local items** — e.g. a repo migrated from `cortex-backlog` to an external tracker without cleanup. Tests must cover that stale-leftover case, not just the clean-empty case.
- `none` backend: dashboard placeholder shown, discovery coverage scan skipped, decompose index regen skipped — assert **no** writes land in `cortex/backlog/`.
- `cortex-backlog` default arm: behavior must stay byte-identical — this is the regression anchor.
- Defense-in-depth (consistency): morning-review's failed-feature `cortex-create-backlog-item` (`plugins/cortex-overnight/skills/morning-review/references/walkthrough.md:417`) is not backend-gated although its auto-close is. The originating audit believed it transitively unreachable under a non-local backend; this lifecycle's critical review disproved that (morning-review is interactive, not the overnight runner) — see the spec, where it is now in scope rather than deferred.

## Touch points

- `cortex_command/dashboard/poller.py`, `cortex_command/dashboard/data.py`, `cortex_command/dashboard/templates/` (backlog panel) — ungated path
- `skills/discovery/references/clarify.md` (§3), `skills/discovery/references/decompose.md` (§7) — lifecycle-gated; auto-mirrors to `plugins/cortex-core/skills/discovery/...`
- (optional, defense-in-depth) `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` (§4)
- Tests: dashboard panel + discovery clarify/decompose under `none` and external (incl. the stale-leftover-items case); `cortex-backlog` byte-identical regression
- OUT OF SCOPE: `skills/lifecycle/references/review.md:12` lacks the "no `cortex/requirements/` -> note and proceed" guard its 5 sibling load-requirements consumers carry. That is a `cortex/requirements/` robustness/consistency nit, unrelated to the backlog backend, and only reachable on a deleted/un-init'd requirements dir — file it separately if wanted, do not fold it in here.

## Audit provenance

Found via a three-agent read-only sweep (empty-state CLI conflation / consumer halt-before-config / backend-blind completeness) after the refine fix. All REAL findings independently re-verified against source. The sweep also produced an all-clear: no halt-class sibling exists anywhere, and the overnight fail-closed guard (`_refuse_unsupported_backlog_backend`) was confirmed to front both bootstrap entry points (`handle_prepare`, `handle_launch`), so no overnight/morning-review path can reach local backlog logic under a non-`cortex-backlog` backend.
