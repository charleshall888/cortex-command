---
status: proposed
---

# Skill-helper verb backend structural guard

## Context

[ADR-0016](0016-configurable-backlog-backend-and-llm-as-adapter.md) draws a clean line for the configurable-backlog-backend work: the `cortex-*` backlog-*engine* CLIs (`cortex-create-backlog-item`, `cortex-update-item`, …) **gain no backend awareness**, and all backend branching lives in the consumer skills, with external-tracker adaptation done LLM-best-effort. That rule is stated without qualification and the capability it governs is released (v2.29.0).

`/cortex-core:refine` Step 2 and Step 5 invoke two skill-helper verbs — `cortex-refine emit-lifecycle-start` and `cortex-refine reconcile-clarify` — that seed and reconcile the lifecycle's local `events.log`. Before #322 the skill encoded a prose-only invariant in two places: *"on a non-`cortex-backlog` backend, omit `--backlog-slug` so no local backlog file is read."* That rule protected a real silent-corruption footgun: a stale local `cortex/backlog/{slug}.md` left on disk after a backend migration would be read and its `complexity`/`criticality` seeded, even though the local backend is no longer authoritative. The rule lived only as model-remembered prose, which CLAUDE.md's "prefer structural separation over prose-only enforcement for sequential gates" warns against.

#322 needed to convert that invariant into a structural guard. The question this ADR records: may a `cortex-*` skill-helper verb carry a `--backend` flag at all, given ADR-0016's unqualified "no backend awareness" rule?

## Decision

A skill-helper verb may act on a **caller-passed** `--backend` value purely as a structural guard, provided it does **not** resolve the backend itself and contains **no** external-tracker adapter logic.

Concretely, `emit-lifecycle-start` and `reconcile-clarify` accept an optional `--backend` flag (default `cortex-backlog`). When the stripped value is not `cortex-backlog` and a `--backlog-slug` was passed, the verb coerces the slug to `None` (so no local backlog file is read) and emits a path-accurate stderr diagnostic naming the ignored slug and backend. The skill still resolves the backend once via `cortex-read-backlog-backend` and passes the resolved value in; the verb never reads config or calls `resolve_backlog_backend`. This keeps the verb a dumb arg-actor while moving the slug-omission invariant from prose into fail-loud code.

## Trade-off / rejected alternatives

This brushes ADR-0016's letter ("branching lives in the skills") in exchange for converting a prose-only, model-remembered invariant into a structural, fail-loud guard. It is deliberately bounded to skill-helper verbs operating over the local `events.log`, distinct from both the backend-blind backlog-engine CLIs and the judgment-bearing external write-back (which stays skill-side and LLM-best-effort).

**Scope extension (#326).** `cortex-lifecycle-start-sync` (the lifecycle Step 2 write-back offload) applies this same caller-passed-`--backend` structural-guard principle but stretches the bounded scope stated above: it writes backlog *frontmatter* via `cortex-update-item` rather than the local `events.log`, and its `--backend` guard gates the verb's *entire* primary action (on `none`/external it makes zero local `cortex-update-item` calls) — unlike `emit-lifecycle-start`, where the events.log write always runs and only the `--backlog-slug` parameter is guarded. This boundary crossing is taken knowingly (recorded here per the operator's plan-approval choice), not silently.

**Scope extension (#371).** `cortex-lifecycle-spec-approve` (the verb-completion-composition spec-approval verb) follows this same recorded precedent: on the `approved` arm its `--backend` guard gates the verb's *entire* primary backlog action — zero local `cortex-update-item` calls on `none`/external, and on `cortex-backlog` an in-process `update_item` write of backlog *frontmatter* (`status:refined` + `spec` + `areas`) rather than only the local `events.log`. Taken knowingly, not silently.

**Hard-to-reverse (criterion 1) is the precedent, not the code.** The `--backend` flag itself is a near-trivial revert — delete the flag, the guard, and two skill call-sites. What is hard to reverse is the **boundary precedent**: once a `cortex-*` skill-helper verb is sanctioned to carry a backend-shaped flag, the next contributor cites this decision to add backend logic to `cortex-update-item` or another verb. Reverting then means re-litigating every verb that adopted the pattern and re-drawing the line ADR-0016 drew — a coordinated, multi-call-site change, not a one-file edit. That is why this is recorded as an ADR rather than a code comment.

Rejected alternatives:

- **Full backend internalization** (import `resolve_backlog_backend` into the verbs). Rejected: it gives the `cortex-refine` verbs genuine backend awareness — a sharper break with ADR-0016 — and introduces a `Path.cwd()`-vs-`_resolve_user_project_root()` resolver-divergence footgun under subdir/worktree/`CORTEX_REPO_ROOT` runs. The caller-passed-flag design avoids both.
- **Leave the rule as skill prose.** Rejected: the silent-corruption footgun is real and the invariant is exactly the kind of sequential gate CLAUDE.md says to encode structurally rather than rely on the model to remember.
- **Amend ADR-0016 in place.** Rejected: ADRs are immutable notes; this is a distinct decision with its own trade-off, so it is recorded standalone and back-points to ADR-0016 rather than editing it.
