---
schema_version: "1"
uuid: 0c55c734-c8ce-43c8-a188-ca841d787549
title: Get the orchestrator out of the agent payload path (dispatch prompts, review envelopes, return contracts)
status: complete
priority: low
type: feature
created: 2026-07-16
updated: 2026-07-16
tags: ['token-efficiency', 'critical-review', 'research', 'dispatch']
areas: ['skills', 'lifecycle']
---
## Why

> **RESCOPED 2026-07-16 after measurement. Read this box before the rest of the ticket.**
>
> This was written as a token-efficiency ticket. Measured against ~95 real sessions, **all four mechanisms together are worth ~5%**, and the ticket's framing is wrong in three ways:
>
> - **The premise mis-locates the cost.** Agent-return payload is ~11% of orchestrator context. The actual law is `cache_read ∝ turns^1.68` (r=0.98, n=126) — cost is *how many times context is re-read*, not what's in it. This ticket attacks what's **in** the context; the expensive term is **turns**. That's an honest error and a structural one: payloads are visible (you can read a prompt, count a template), turns are invisible until you fit a curve.
> - **Mechanism 4 mis-cites its contract.** `skills/lifecycle/SKILL.md:78` ("Reference-path propagation") is a **path-string substitution** rule — *"Wherever a reference contains a `${CLAUDE_SKILL_DIR}/…` path, substitute the body-resolved absolute path"* — **not** a mandate to read-and-reinline template content. The inlining behavior is real but is sanctioned by ADR-0009 ("propagates the absolute path — **or inlines the reference content**"), not by the named heading. Mechanism 4 also substantially double-counts mechanism 1 (same inlining pattern).
> - **Mechanism 5 was already rejected, correctly.** ADR-0009 rejected a structurally similar "route reference loads through a `cortex-*` console script" for pr-review, citing *"zero token saving and no reliability gain"*. Measurement vindicates that call: rubric-by-path is worth **~0.7%**.
>
> **Mechanism 3 (return budgets) has moved to #389**, where it belongs — it is the same "nothing is bounded" defect as runaway agents.
>
> **What survives is mechanism 2, and it is a correctness defect, not a token one** (see below). Priority dropped to `low` and the ticket should be worked as a quality fix. Sizing caveat for whoever picks this up: any dollar figure in the original text below is unreliable — a naive line-sum over the transcripts overcounts 2.66x (dedup by billed `message.id`), and Opus 4.8 is $5/$25 per Mtok, not $15/$75. See #392.

The orchestrator is a switchboard: bytes that only ever need to travel **agent to agent** are routed through its context, where they are retained permanently. It is a relay that never forgets what it relayed. Four distinct instances of this were observed in one interactive `/cortex-core:lifecycle` run (wild-light #362, 2026-07-16, ~15 subagents, 366k message tokens — see #381 for the measurement gap that let this go unnoticed).

**1. The synthesizer prompt makes the orchestrator pay for everything twice.** `skills/critical-review/references/synthesizer-prompt.md` requires substituting `{a_to_b_rubric}` and the reviewer-findings payload verbatim:

> Read `references/a-to-b-downgrade-rubric.md` and substitute its full content into `{a_to_b_rubric}`, then dispatch one synthesizer agent ... with `{artifact_path}`, `{artifact_sha256}`, `{a_to_b_rubric}`, and the reviewer-findings payload substituted at runtime.

So each reviewer envelope costs the orchestrator once arriving and once departing, and the rubric — a **static file in this repo** — costs it once to Read and once to paste. In the observed run that single prompt was ~10k tokens. The synthesizer has `Read`; it could open the rubric itself. Nothing about either payload requires the orchestrator to see it: what the orchestrator needs is the synthesis, not the raw envelopes.

**2. Every reviewer emits its findings twice.** `skills/critical-review/references/reviewer-prompt.md` asks for prose sections (`### What is wrong`, `### Assumptions at risk`, `### Convergence signal`) **and then** a JSON envelope whose `finding` / `evidence_quote` fields restate the same content. Step 2c.5 extracts the JSON and the orchestrator dispositions from it — the prose is vestigial on the machine path. Roughly 40% of every reviewer report is redundant, x4 reviewers, x2 gates (spec + plan).

**Do not simply delete the prose.** In the observed run the highest-value content lived *only* in the prose — the in-engine measurement tables (`ToggleRow (62,24) -> (55,24)`; a corrected `606 vs 636` figure that overturned an owner scope decision). The envelope has no field for that evidence. The duplication is the waste; either format can be the survivor, but the envelope needs somewhere to put measurements.

> **THIS IS THE SURVIVING ITEM, AND IT IS A CORRECTNESS DEFECT — NOT A TOKEN SAVING.**
>
> Verified 2026-07-16: the JSON envelope's fields are exactly `class`, `finding`, `evidence_quote`, `fix_invalidation_argument`, `straddle_rationale`. **There is no `measurement` / `probe` / `evidence` field.** Step 2c.5 extracts the JSON; the machine path reads the JSON. So the best evidence a reviewer can produce — live probe output, in-engine measurements — **has nowhere to go and is invisible to the machine path**. In the observed run that content overturned an owner scope decision, and it survived only because a human read the prose.
>
> This loses findings. Fix it regardless of what it costs in tokens: **add a `measurement` (or `evidence`) field to the envelope, then collapse the duplication.** The token saving is incidental and small; the defect is that the highest-value reviewer output can't be represented in the format the orchestrator actually reads.
>
> Note the observed behaviour this protects: reviewers running live `godot --headless` probes instead of speculating is the single most valuable agent behaviour recorded, it is nearly free (it happens inside agent context, which is ~15x cheaper per token than orchestrator context), and the return contract currently gives it no home.

**3. No return budget exists.** Neither `reviewer-prompt.md`, `angle-templates.md`, nor the core angle prompts in `skills/research/SKILL.md` bound the size of the return value. Observed reports ran 3-5k words each. Meanwhile the single most valuable agent behaviour in that run — reviewers running live `godot --headless` probes instead of speculating — happens **inside** agent context and is free to the orchestrator. The prompts currently incentivise the opposite of what is wanted: verbose prose, unbounded; empirical probing, unrewarded.

**4. The orchestrator is a template engine.** The "Reference-path propagation (load-bearing)" contract has it Read a template, substitute absolute paths, and re-emit the result into a prompt — paying for the template twice and retaining it. ~18 reference docs were read this way in one run.

## Proposed direction

Principle to encode: **push work into agent context; pull only conclusions out.** The orchestrator should handle *paths and conclusions*, never payloads.

- **Rubric by path.** Replace `{a_to_b_rubric}` inlining with the rubric absolute path; the synthesizer Reads it. Removes a double cost for zero behaviour change.
- **Envelopes to disk.** Reviewers write their envelope to `cortex/lifecycle/{feature}/review/{angle}.json`; the synthesizer is handed the directory and reads them. The orchestrator passes paths and receives only the synthesis. The Step 2c.5 sentinel/drift gate keeps working — it can stat/hash files instead of scraping stdout.
- **One format, with room for evidence.** Make the envelope the sole return; add a `measurement` (or `evidence`) field so probe output has a home. Drop the duplicated prose sections.
- **Return budgets.** Give every dispatched agent an explicit return budget ("<= 600 words; the envelope is the deliverable"), while stating that internal probing is unbounded and encouraged. Applies to `reviewer-prompt.md`, `angle-templates.md`, and the research core-angle prompts.
- **Render prompts via a verb.** `cortex-critical-review render-prompt --angle <a> --artifact <p>` (and equivalents) emits the fully-substituted prompt so the orchestrator never loads the template. Separable from the rest — decompose may split it.

## Role

The transient-axis counterpart to #340 (which trims **resident** skill prose). This ticket targets **runtime payload volume**, the axis #340 cost model never measured. Together they cover both halves.

## Integration

- Depends (advisory, non-blocking): #381 supplies the telemetry to rank these four mechanisms against each other. The wins here are self-evident enough to start without it, but #381 is what proves the size.
- Sibling: #340 — same goal, different axis; its discipline ("rank by hot-path resident-tokens and clarity-harm, not bytes-on-disk") is the resident-side analogue of this ticket transient-side rule.
- The research fan-out return path is **not** a switchboard case — the orchestrator authors `research.md` from those reports, so they must come back. Only the budget lever applies there.

## Edges

- **Not** the declined phase-isolation rewrite (`cortex/research/skill-efficiency-remaining-work/research.md:59`). That was L/XL, fought interactive human-in-the-loop steering, and aimed at shedding *instruction prose*. Every mechanism here is a prompt-contract or file-handoff change with no architectural risk.
- **Fan-out breadth is a tunable, not a fixed point — this ticket takes no position on it.** The original text here said "do not cut fan-out breadth to save tokens", on the strength of one observed run where four independent reviewers found four *different* fatal defects in one spec (two vacuous leak guards, a test that would assert `4 == 16`, a font change that reduced legibility while buying zero density, and a transposed measurement that had driven an owner scope decision). That is **n=1** — the same single-anecdote standard #383 correctly declines to act on, and it should not have been stated as doctrine. Measured, halving reviewers is worth **~4.7%** of total spend, which is real money and comparable to this entire ticket. A modest trim may well be right. **Decide it from yield data** (dispatches vs A-class findings across real runs — #392 + #383), not from either this ticket's original assertion or its correction.
- Envelope-to-disk changes the reviewer contract from "return text" to "write file + return nothing much" — the malformed-envelope / untagged-prose fallback in Step 2c.5 must be re-specified for a file that is missing or unparseable, not merely a garbled stdout.
- `reviewer-prompt.md` is touched by three of the four mechanisms; sequence them in one pass rather than racing.
- The `READ_OK` attestation is already declared advisory ("not the drift gate — the orchestrator re-hashes the pinned artifact itself"). If envelopes move to disk, re-check whether it earns its place at all.

## Touch points

- skills/critical-review/references/synthesizer-prompt.md (rubric + envelope inlining)
- skills/critical-review/references/reviewer-prompt.md (prose/JSON duplication; no return budget)
- skills/critical-review/references/a-to-b-downgrade-rubric.md (inlined; should be Read by path)
- skills/critical-review/references/verification-gates.md (Step 2c.5 envelope extraction, if envelopes move to disk)
- skills/critical-review/SKILL.md (Step 2c/2d dispatch + synthesis)
- skills/research/SKILL.md, skills/research/references/angle-templates.md (return budgets)
- cortex/backlog/340-core-skill-efficiency-survivors-of-the-post-336-adversarial-audit.md