---
schema_version: "1"
uuid: 453fa70e-0737-4245-b846-3faa03732bf7
title: 'Build cortex-session-tokens: read usage, classify nothing (corrects #381)'
status: backlog
priority: low
type: feature
created: 2026-07-16
updated: 2026-07-16
tags: ['telemetry', 'token-efficiency', 'cost-model']
areas: ['lifecycle', 'report']
---
## Why

> **DEMOTED TO LOW 2026-07-16 (requirements decision) — this verb gates nothing.** Per `cortex/requirements/project.md` (Deletion bias), the standing measurement tool is the ad-hoc prototype at `cortex/research/token-economics-2026-07-16/analyze.py` plus the dedup-by-`message.id` rule; re-measurement follows shipped cuts rather than preceding them. Corrections to this ticket's own claims from an independent re-derivation: **`isSidechain` is not dead** — it is `True` on >99.9% of subagent assistant records on this machine and is a valid orchestrator/subagent splitter (file-location splitting remains fine; the stated justification was wrong). The **$4,473 total did not reproduce** — every corpus slice measured ~$5.3k (the power laws and the subagent tail reproduced near-exactly; the dollar total is snapshot/scope-sensitive, one more reason not to trust absolute dollars). And the error class this ticket names claimed two more victims after it was written: #390/#391 shipped with undeduplicated verb counts.

**The harness can already report its own runtime cost. The data has been on disk the whole time.** #381 was written on the premise that it cannot, and proposes reconstructing estimates from `subagent_tokens`. That premise is false.

Every session transcript at `~/.claude/projects/<repo>/<session>.jsonl` carries, on each `type=="assistant"` record, a complete `usage` object: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (with a `cache_creation` sub-object breaking out `ephemeral_1h_input_tokens` / `ephemeral_5m_input_tokens`), plus `model` and `attributionSkill`. Subagents live in `<session>/subagents/*.jsonl`. Exact per-request billing is reconstructible today.

**The 2026-07-16 investigation proved why this needs to be a tool and not a person.** It produced four wrong headline numbers before landing. Total measured spend went **$29,033 → $11,054 → $4,473** — a 6.5x inflation across two independent errors — and the lever ranking inverted along the way. The errors sort perfectly:

| class | outcome |
|---|---|
| numbers read straight from `usage` | **every one held** |
| numbers requiring the analyst to *classify* content | **every one was wrong** |

Specific failures, all avoidable by a tool:
1. **No dedup.** One billed API response is logged as several JSONL records (one per content block: thinking / text / tool_use), each carrying the **same cumulative `usage`**. Summing lines overcounts **2.66x**. Verified: 382 assistant lines → 179 unique `message.id`; three consecutive lines sharing `msg_011Cd6DmrrTkD591csgMphQ7` with byte-identical usage.
2. **Wrong prices.** Opus 4.8 is **$5 / $25** per Mtok, not the $15/$75 recalled from an older Opus generation. That alone was a further 2.5x, and it collapsed the "route reviewers to Sonnet" lever from a claimed 18.5% to **4.4%** (the real Opus:Sonnet gap is 1.67x, not 5x).
3. **Regex hitting the repo path.** `cortex-[a-z-]+` matched `/Users/.../cortex-command` in every `cd`-prefixed Bash command, inflating "bookkeeping" from a true **4.7%** to a claimed 22.5% — and that fabricated number was recommended as the single biggest lever.
4. **`isSidechain` is dead.** It is `False` on every record on this machine. Any orchestrator/subagent split must come from **file separation** (`<session>.jsonl` vs `<session>/subagents/*.jsonl`), not the flag.

## Proposed direction

A verb — `cortex-session-tokens` (JSON + human) — that reads `usage` and **classifies nothing**.

Non-negotiable contract:
- **Dedup by billed `message.id`** (fall back to `requestId`) before any sum. This is the single most consequential rule.
- **Price from a table, not from memory.** Opus 4.8 $5/$25; cache-write 1.25x input at 5m TTL, 2x at 1h TTL; cache-read 0.1x input. Read the per-TTL split from `usage.cache_creation` rather than assuming.
- **Split orchestrator vs subagents by file path**, never by `isSidechain`.
- Report per session: billed requests, peak context, cache_read / cache_write / output, and cost.
- Report the **`turns^k` fit** — the one durable law the investigation found: `cache_read ∝ requests^1.68` (r=0.98, n=126 sessions), and `∝ turns^1.55` (r=0.96, n=1167) inside subagents.
- Report the **subagent tail** (p50/p90/p99 turns and cost) — where the runaways hide.
- **Emit nothing that requires interpreting a command string.** No bucketing by purpose, no verb attribution, no thinking inference. Those are exactly the numbers that were wrong. If a future version adds them, they must be labelled as estimates.

**A working prototype is checked in at `cortex/research/token-economics-2026-07-16/analyze.py`** — `scan()` with message-id dedup, the corrected per-TTL `PRICE` table, and `cost()`. It is correct on exactly the robust parts (it classifies nothing) and is roughly 40 lines from being this verb. Verified running against live transcripts on 2026-07-16.

Usage:

```python
import analyze as A, glob, os
base = os.path.expanduser("~/.claude/projects/<repo-slug>")
rows = A.scan(f"{base}/{session_id}.jsonl")          # orchestrator, deduped
subs = [r for sp in glob.glob(f"{base}/{session_id}/subagents/*.jsonl") for r in A.scan(sp)]
cost = sum(r["cost"] for r in rows + subs)
```

## Role

Measurement-first, and the corrective to #381. Once this exists, nobody has to trust a recollected magnitude again — including the next agent that proposes a 22.5% lever.

## Integration

- **Corrects/supersedes #381.** #381's core premise ("the harness cannot report its own runtime cost") is false; its estimate of agent-return payload (150k) measured at 57k (2.6x over); and its Edges claim that "prompt caching makes resident tokens cheap in dollars" is wrong — cache-read is **61% of cost-weighted** orchestrator spend (97.6% of raw tokens). #381 also explicitly forecloses phase-isolation, which measurement supports (see Edges).
- **Resizes #382.** Its mechanisms 1/2/3 verify TRUE; mechanism 4 mis-cites its contract (`skills/lifecycle/SKILL.md:78` is a path-string substitution rule, not read-and-reinline) and double-counts mechanism 1. All four together ≈ 5%. Note ADR-0009 already rejected a structurally similar "route reference loads through a `cortex-*` console script" for pr-review citing "zero token saving" — and measurement says that judgment was right (rubric-by-path ≈ 0.7%).
- **Confirms #383's claims** but its yield question needs this telemetry to answer. Gate conditions are byte-identical at `plan.md:105` and `specify.md:128`; `angle-menu.md` has no criticality/phase matrix at all — count keys only off artifact length ("<10 lines: 2; otherwise 3-4").
- Siblings: #389 (subagent turn caps), #390 (envelope compliance), #391 (zero-reader events).

## Edges

- **Scope discipline: read `usage`, classify nothing.** The temptation will be to add purpose-bucketing. That is what failed four times.
- The corpus is ~95 multi-agent sessions across two repos; the numbers above are that corpus, not a universal constant. Re-measure, don't inherit.
- **Cache is already near-perfect — there is no caching win to chase.** Measured 98.1% hit rate, 1.9% write/read ratio, all writes at 1h TTL, 0.9M raw uncached input across the whole corpus. Caching *discounts* carry ~10x; it does not remove it. The remaining lever on carry is `context x turns`, not cache tuning.
- **Metering basis is an open question that changes conclusions by 2.5x.** Under raw-token metering, carry is 97.6% of orchestrator throughput; cost-weighted it is 61%. Which basis a Claude subscription actually meters is **unknown** and was not resolved. Do not guess it — find out, then re-rank.
- **Phase-isolation is supported by evidence, contra #381's foreclosure.** Sessions already span 3+ lifecycle phases; the orchestrator already re-reads `spec.md`/`plan.md` from disk in 24% of late-session tool calls (it does not trust its own memory); human steering is 2.3% of turns; a fresh session costs ~50.7k to re-cache the floor (~0.72% of one session's read). The artifacts are already the interchange format. But this is a *habit*, already practiced by the maintainer, not a build — do not turn it into an architecture project.

## Touch points

- bin/cortex-count-tokens, bin/cortex-measure-l1-surface, bin/cortex-invocation-report (the existing static-only measurement surface)
- cortex/backlog/381-measure-runtime-agent-payload-accumulation-the-cost-model-only-sees-resident-prose.md (the ticket this corrects)
- cortex/backlog/382-get-the-orchestrator-out-of-the-agent-payload-path-dispatch-prompts-review-envelopes-return-contracts.md (resize + fix mechanism-4 citation)
- cortex/research/skill-efficiency-remaining-work/research.md (the phase-isolation decision record, amendable on evidence)