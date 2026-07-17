---
schema_version: "1"
uuid: 9d91fa5d-6d62-44cd-821d-0ae574b73378
title: Make lifecycle skills consume the served envelope instead of re-fetching state
status: done
priority: low
type: chore
created: 2026-07-16
updated: 2026-07-16
tags: ['token-efficiency', 'lifecycle', 'bookkeeping']
areas: ['skills', 'lifecycle']
---
## Why

> **CORRECTED + DEMOTED TO LOW 2026-07-16.** The sizing below was computed on **undeduplicated JSONL lines** — the exact error class #392 catalogues (one billed response logs once per content block). Deduplicated by billed `message.id`: `cortex-lifecycle-state` is ~5 requests (not 160), `cortex-lifecycle-event` ~118 (not 477), `cortex-resolve-model` ~10 (not 179); requests whose only tool call is a `cortex-*` verb are 0.6–1.1% of the corpus (not 4.4%), so the modelled ~7% carry saving collapses to ~1%. Two further corrections: the served envelope does **not** carry tier/criticality as flat fields — they sit nested in `evidence_trace[1]["reduction"]` (`next_verb.py`), so consumption means indexing the trace or a one-key envelope change; and the SessionStart-hook idea is withdrawn (it trades one request for permanently carried tokens, failing the requirements Deletion-bias bar). The call-site hygiene remains correct — do it opportunistically when these files are open for other work, not as a standalone effort.

`cortex-lifecycle-next` already serves everything the orchestrator needs in one call. `skills/lifecycle/SKILL.md:28`:

> One read-only call serves the current state, its advance contract, and its pause spec.

The envelope (`cortex_command/lifecycle/next_verb.py:40-50`) returns `state`, `legacy_display_phase`, `fragment_ref`, `pause_spec`, `advance_contract`, `path_overview`, `guards`.

**And then the skills re-fetch it anyway.** The Plan phase reference calls `cortex-lifecycle-state` twice in succession — once for the `tier` field, once for `criticality` — as two separate Bash invocations, which is **two full-context API requests** to read two strings the served envelope already carried. The identical pair appears in the Specify phase reference. Worse, the **batched whole-state form already exists and is already used** roughly 40 lines away in the orchestrator-review and critical-review-gate references. This is not a missing capability; it is an inconsistent call site. Exact locations in Touch points.

Measured verb turns across the corpus (each = one full-context request):

| verb | turns |
|---|---|
| cortex-lifecycle-event | 477 |
| cortex-resolve-model | 179 |
| cortex-lifecycle-state | 160 (**re-fetching served data**) |
| cortex-read-backlog-backend | 120 |
| cortex-lifecycle-advance | 80 |
| `--help` / `help` | 17 (**the model reading CLI usage**) |

Requests whose only tool call is a `cortex-*` verb: **640 of 14,622 = 4.4%**. Because carry is superlinear in turns (`cache_read ∝ turns^1.68`, r=0.98, n=126), removing 4.4% of requests removes **~7% of carry**, not 4.4%.

`cortex-resolve-model` deserves its own mention: it is a **20-cell static dict** (`cortex_command/lifecycle/resolve_model_cli.py` — `_LIFECYCLE_MATRIX` + `_CRITICALITY_INDEPENDENT`) invoked 179 times as a full-context request. Inlined as a table it is under 500 tokens. Its only benefit is argparse fail-loud on a typo'd role — a soft benefit, obtainable as a lint on the table.

## Proposed direction

- **Consume the envelope.** Delete every `cortex-lifecycle-state --field` call whose value `cortex-lifecycle-next` already served. Start with `plan.md:101-102` and `specify.md:120-121`; where a fresh read is genuinely needed, use the batched whole-state form that already exists.
- **Inline the model matrix.** Replace the `cortex-resolve-model` call sites with the table; keep the closed-vocabulary validation as a lint/test over the table rather than a per-dispatch subprocess.
- **Fix the `--help` turns.** 17 requests were the model discovering CLI usage. Whatever invocation contract is missing from the prose, add it.
- **Consider a SessionStart hook for the rest.** `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` already injects `LIFECYCLE_SESSION_ID` + active feature state via `hookSpecificOutput.additionalContext` (`cortex_command/hooks/scan_lifecycle.py:535`). Injecting context is the documented purpose of SessionStart (`docs/agentic-layer.md:171`: *"Inject context, set up credentials, merge permissions"*). It does not currently inject tier/criticality. **Caveat:** hook output lands as a `hook_success` attachment record — ordinary context, carried and re-billed on every later request. A hook trades a *request* for *carried tokens*. The win is the request, not the tokens.

## Role

The correctly-scoped version of "only do bookkeeping at intervals that really matter". The architecture for that already exists (#374's served next/advance loop); this is an **enforcement** gap, not a build.

## Integration

- Depends on nothing. `cortex-lifecycle-next` and the batched `cortex-lifecycle-state` form both ship today.
- Sibling: #389 (bound subagent turns) — same investigation, independent.
- Related: #340 (resident-prose efficiency). This is orthogonal — #340 trims bytes in context; this removes *requests*.

## Edges

- **Do NOT condense lifecycle states to chase this.** Measured: the entire state machine is **75 of 14,622 requests (0.51%)**. Condensing Clarify+Research+Spec saves 0.3%; Review+Complete saves 0.1%. Meanwhile state boundaries are the natural *session* boundaries, and session-splitting is worth 37–61% (`cache_read ∝ turns^1.68`). Merging states to save 0.4% deletes split points worth far more. Net negative.
- **Do NOT remove the event log.** `common.py:942` — `reduce_lifecycle_state` reduces `events.log` to *the canonical lifecycle state*; consumed by `next_verb.py`, `advance.py`, `state_cli.py`, `complete_route.py`, `implement_transition.py`, `refine.py`, `review_dispatch.py`. Remove events → no served state → no `resume` → **you can no longer start a fresh session mid-lifecycle**, which is exactly the mechanism that makes the 37–61% split possible. The event log is what makes the expensive thing (the session) disposable.
- Sizing caveat: ~7% is modelled from the measured exponent, not from an A/B. The underlying request counts are read from `usage` and are reliable; the projection is not measured.
- `philosophy` (2026-07-16 review) adjudicated the verb-first convention: the ADRs justify verbs on **drift/reliability, never tokens** (ADR-0024 cites the shipped-broken `complete <slug>` parse; `docs/policies.md:11`). The philosophy is sound; only its *uniform* application to stateless lookups is over-applied. Verbs holding a flock/claim-commit lock (`cortex-lifecycle-event`, `advance` — ADR-0020) or parsing a drifted grammar (ADR-0018) are unconditionally justified and must not be touched by this ticket.

## Touch points

- skills/lifecycle/references/plan.md (101-102 — the paired `--field tier` / `--field criticality` reads, two requests for two strings)
- skills/refine/references/specify.md (120-121 — the identical pair)
- skills/lifecycle/references/orchestrator-review.md (7 — the batched form, already correct)
- skills/lifecycle/references/critical-review-gate.md (7 — the batched form, already correct)
- cortex_command/lifecycle/resolve_model_cli.py (the 20-cell matrix)
- cortex_command/lifecycle/next_verb.py (the served envelope schema)
- cortex_command/hooks/scan_lifecycle.py (the existing SessionStart injector)