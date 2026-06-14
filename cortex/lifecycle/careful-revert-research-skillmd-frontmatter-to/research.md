# Research: Careful-revert research/SKILL.md description to the ~378B #191 close-state

**Clarified intent:** Revert `skills/research/SKILL.md`'s `description` frontmatter from its current 502B to the ~378B #191 close-state by removing the +124B mechanism-narration regrowth, while preserving the three test-enforced trigger phrases (`/cortex-core:research`, `research this topic`, `investigate this feature`) and the `research.md`-vs-conversation-output disambiguation tail; then lower the `research` **and** `total` rows in `tests/test_l1_surface_ratchet.py` and regenerate the cortex-core plugin mirror.

**Complexity:** complex · **Criticality:** high · Cluster skill (`ROUTING_PRESSURE_CLUSTER`), cluster-exempt from the ≤400B default.

---

## Codebase Analysis

**Files that change:**
- `skills/research/SKILL.md` — `description` frontmatter (a `>` folded block scalar, lines ~3–8). **No `when_to_use` field exists** → the entire L1 surface *is* the `description`. Current measured surface = **502B**.
- `tests/test_l1_surface_ratchet.py` — `_BASELINES["research"] = 502` (line 69) and `_BASELINES["total"] = 7320` (line 70). Both must drop by the same delta. The docstring at lines ~22–26 ("research stays at its deliberate cluster budget of 502 until the follow-on revert (ticket 302) lands") must also be updated in the same commit.
- `plugins/cortex-core/skills/research/SKILL.md` — the mirror, **regenerated** via `just build-plugin`, never hand-edited.

**Ratchet mechanics:** `_RATCHET_CASES = sorted(_BASELINES.keys())` includes `total`, so `total` is a parametrized ratchet case. Direction is **equal-or-lower passes** (`assert actual <= baseline`). `test_budget_rows_complete` is set-equality on *keys* (changing values keeps it passing). `test_non_cluster_budgets_within_default` only checks non-cluster skills ≤400B — `research` is cluster-exempt, so any value is structurally legal.

**Measurement authority:** `bin/cortex-measure-l1-surface` parses frontmatter with `yaml.safe_load` (all scalar forms normalize), computes `len(description.utf8) + len(when_to_use.utf8)`, enumerates **canonical `skills/` only (never mirrors)**, run with `cwd=REPO_ROOT`.

**Routing guards (both must keep passing):**
- `tests/test_skill_descriptions.py` — three trigger phrases checked against `description` **alone**.
- `tests/test_skill_routing_disambiguation.py` — same three phrases against concatenated `description`+`when_to_use`; `ROUTING_PRESSURE_CLUSTER = (dev, lifecycle, refine, research, discovery, critical-review)` (imported by the ratchet test). Since `research` has no `when_to_use`, both tests see the same surface.
- Fixture: `tests/fixtures/skill_trigger_phrases.yaml` (research entry, three enforced phrases).

**Mirror coupling:** `.githooks/pre-commit` (enabled by `just setup-githooks`) runs `just build-plugin` + a parity check when staged paths touch `skills/`, failing the commit on a stale mirror. **Commit canonical + regenerated mirror together** (per the drift-hook / shared-checkout coupling).

---

## Web Research

The ticket's governing principle — a `description` is routing/triggering metadata (what + when), and how-it-works internals belong in the on-trigger body — is **strongly corroborated by Anthropic's own guidance** and cross-vendor tool-routing practice:

- **[Skill authoring best practices — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):** `description` is "Maximum 1024 characters … Should describe what the Skill does and when to use it." Verbatim: "Your description must provide enough detail for Claude to know when to select this Skill, **while the rest of SKILL.md provides the implementation details.**" Only metadata (name+description) is pre-loaded at startup; the body loads on trigger — so every byte of mechanism-narration in the description is paid every turn with no routing benefit.
- **[skill-creator/SKILL.md (anthropics/skills)](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md):** "**Focus on intent, not implementation**: describe the outcome and when to invoke it, **not how it works internally**." Nearly a verbatim statement of the principle under test. Also: "All 'when to use' info goes here, not in the body" — description bytes should buy *trigger coverage*, not internals.
- **Length vs routing accuracy:** empirical work (arXiv 2505.18135, 2505.10570) and practitioner write-ups (jentic, adaline) find selection accuracy *degrades* as tool/description length grows; over-stuffed descriptions crowd attention and compete with sibling skills' metadata. "Shortening descriptions where possible is recommended."
- **Caveat (don't over-trim):** the same guidance warns against *under-triggering*. Trigger phrases and disambiguation tails are the legitimate use of description bytes — the revert should cut internals while keeping those.

**Tension to note:** Anthropic's "not how it works internally" guidance, taken literally, argues against *any* mechanism clause — which would favor the smaller mechanism-free form (Option C below). The ticket, however, targets the #191 close-state, which itself *kept* a light mechanism one-liner. See Open Questions.

---

## Requirements & Constraints

- **`project.md:48` "SKILL.md L1 surface ratchet":** measures `description`+`when_to_use` SUM in UTF-8 bytes via `bin/cortex-measure-l1-surface`; equal-or-lower passes; default ≤400B for non-cluster skills; the **routing-pressure cluster** (`dev, lifecycle, refine, research, discovery, critical-review`) is the single exemption surface, bounded by its own higher budget rows. **Raising** a budget needs documented rationale + a lifecycle-id (the re-cap rule). **Lowering needs no lifecycle-id** — confirmed: the ticket's claim is correct.
- **CLAUDE.md:** the L1 budget rule (line 44); the "prescribe What and Why, not How" design principle; MUST-escalation policy (no new MUST/CRITICAL/REQUIRED language without an evidence artifact — relevant if any rephrase touches imperative language; the current "always-last adversarial pass for high/critical" wording is being removed anyway); lifecycle required before editing `skills/` — which is *why* #302 exists as a tracked item and is governed by this very lifecycle.
- **Parent #298 artifacts** (`cortex/lifecycle/l1-frontmatter-cap-policy-for-new/research.md`, `spec.md`): #298 **explicitly deferred** the research-frontmatter revert out of its own scope ("research's ratchet budget stays at 502 as its deliberate cluster budget until the follow-on lands" — that follow-on is #302). #298 resolved the target as a **revert to the ~378B #191 close-state**, explicitly **NOT** ~150–200B ("no routing justification … a compression stunt"). OQ10 resolved the floor contradiction: ~378B is the *author-judgment/routing-quality* floor (the right basis); ~163–200B is the bare *test-enforced* minimum (3 phrases only). The "502 vs 200 cap" headline traces to a #191 doc-classification error that #191's own review rejected (`review.md:47`, `:77`).
- **Backlog #302 boundaries:** target ~378B #191 close-state, **do NOT over-trim toward 200**; keep all three trigger phrases in `description`; keep a compact `research.md`-vs-conversation-output disambiguation tail; byte-disjoint from #299 (sequence after it); lower research + total budgets; regenerate mirror, commit canonical+mirror together. **#299 is `status: complete`** → unblocked.

---

## Historical Reconstruction & Byte Accounting

- **#191 close-state recovered** from commit `500e84640806…` ("Close #191"). The `description` measured **exactly 378B** (no `when_to_use`; confirmed against `cortex/lifecycle/reduce-boot-context-surface-claudemd-skillmd/post-trim-measurement.md`). Verbatim third sentence at #191 close: `Dispatches 3–5 parallel agents across independent angles (codebase, web, constraints, tradeoffs, adversarial), synthesizes into research.md or conversation output.` (165B).
- **The +124B regrowth** is entirely the third sentence, rewritten by commits `01cf51a8` and `fd7b71d7` (2026-05-30, hybrid-angle/fan-out rewrite) to: `Dispatches 3–10 parallel agents — sized by a tier×criticality matrix — across independent angles (core: codebase, web, constraints; plus task-chosen angles such as tradeoffs and an always-last adversarial pass for high/critical), synthesizes into research.md or conversation output.` (289B). Sentences 1+2 are byte-identical between #191 and now.
- **Candidate byte counts** (measured with the canonical tool's convention — the folded `>` scalar **clip-chomps exactly one trailing `\n` that the tool counts**, so hand-counts that omit it are off by 1; Option A reproduces the tool-verified 378B):

  | Option | Third sentence | `research` bytes | new `total` |
  |--------|----------------|------|------|
  | **A** — #191 verbatim | `…3–5 parallel agents…` (stale count) | **378** | 7196 |
  | **B** — #191 tail, count corrected | `…3–10 parallel agents across independent angles (codebase, web, constraints, tradeoffs, adversarial)…` | **379** | 7197 |
  | **C** — mechanism-free | `Synthesizes into research.md or conversation output.` | **265** | 7083 |

- **Anti-drift arithmetic:** `total` (7320) == exact sum of the 17 per-skill budgets (verified, zero slack). Lowering `research` by `D` requires lowering `total` by the same `D`: `new_total = 6818 + V` where `V` is the new measured research value. **Both rows move together**, or the budget==measured invariant rots (a stale-high total passes the equal-or-lower ratchet silently, re-opening exactly the drift channel that let research grow 378→502).
- **Implementation note:** copy the `research`/`total` rows from a fresh `bin/cortex-measure-l1-surface` run verbatim rather than hand-computing (the +1 newline subtlety produced off-by-one hand counts during research).

---

## Routing Distinctiveness

The routing-pressure cluster disambiguates primarily on **output terminus**: research stops at `research.md`-or-conversation; discovery → backlog tickets; refine → spec.md; lifecycle → plan/implement/review. **Discovery's `description` explicitly references research by name** — "Different from /cortex-core:research — research produces a research.md and stops; discovery … ends with backlog tickets" — so the `research.md`/conversation tail is genuinely load-bearing routing content, not mechanism: it encodes research's two real, user-observable output modes (lifecycle mode writes a file; standalone mode answers in conversation with no side effect).

**Load-bearing (keep):** `Parallel research orchestrator` (role identity); the three test-enforced trigger phrases + `gather research for`; `when /cortex-core:refine delegates its research phase` (the refine inbound-delegation hook, mirrored on refine's side); the `research.md or conversation output` disambiguation tail.

**Disposable mechanism (the +124B target):** `sized by a tier×criticality matrix`, the `3–10`/angle-taxonomy enumeration, and the `always-last adversarial pass for high/critical` scheduling — none distinguish research from a sibling; they describe internals a router never needs.

---

## Tradeoffs & Alternatives

- **Alternative A — verbatim #191 revert (378B):** clean reversion to a review-blessed state; both routing tests pass unchanged; minimal authoring risk. **Con:** re-states a now-stale agent count ("3–5"; the dispatcher is 3–10) — knowingly committing a factually-wrong number.
- **Alternative B — #191 tail with corrected count (379B):** honors the ticket's ~378B target, keeps the light mechanism one-liner #191 itself kept, fixes the staleness. 1 byte above the literal close-state. **Con:** "3–5"→"3–10" is technically a 1-byte edit on top of a pure revert (not strictly byte-identical), so it's a revert-in-spirit, not a literal revert.
- **Alternative C — mechanism-free (265B):** drops the entire "Dispatches N agents…" clause, keeping only the disambiguation tail. Most aligned with Anthropic's "not how it works internally" guidance. **Cons:** lands 113B *below* the ticket's ~378B target and toward the ~200 the ticket warns against; #191's own close-state *kept* a light mechanism clause, so this is a **new trim, not a revert** — a scope reinterpretation that should be ratified by the user, not inferred.
- **Rejected — ~163–200B compression:** confirmed a "compression stunt" with no routing justification; contradicts the cluster-cap intent (`research` is cluster-exempt *because* it carries irreducible disambiguation tokens).
- **Budget setting:** budget==measured, **no headroom** (the established #298 pattern; headroom is precisely what permitted the 378→502 drift). Lowering needs no lifecycle-id.

---

## Adversarial Review

- **The core-wave's initial ~265B (Option C) recommendation over-trims and was rationalized.** The ticket says "target ~378, do not over-trim toward 200"; 265B is closer to the 200 floor it warns against than to the 378 target it sets. "But it's above 200" reframes the constraint.
- **The "stale 3–5" argument is a non-sequitur for abandoning the byte target.** Staleness and the byte target are independent; the fix is to correct the count (Option B), not to drop the clause. The core wave presented a false binary (verbatim-stale-378 vs mechanism-free-265) and never costed the middle (B).
- **#191's 378B close-state itself contains a mechanism clause with a count** — the project's own reference for a "correctly-sized description" includes one. Arguing counts don't belong is arguing against the ticket's target; surface it as a scope change, not "revert-in-spirit."
- **Empirically validated** (candidate applied to the live file, full suite + lints run, then reverted): both routing tests pass; `total`==exact sum confirmed (lowering research by 237→265 needs total 7320→7083); `test_skill_size_budget.py` (line-count, safe); `test_plugin_mirror_parity.py` does **not** cover the research mirror (the pre-commit drift hook is the only mirror guard — no CI net if `just setup-githooks` was skipped); `check-skill-path`/`check-contract`/`check-prescriptive-prose` all clean. **No minimum-byte floor test exists** — over-trim passes green, so only review catches it.
- **#299 verified complete** (commit `781acd3c`), edited body only, frontmatter untouched, on-disk description still 502B — no stale-line or already-edited risk.
- **Recommendation: Option B** — the only candidate satisfying every stated constraint simultaneously (honors ~378B target, fixes staleness, keeps the disambiguation tail, passes all gates).

---

## Open Questions

1. **[Deferred to Spec — the central decision] Which target shape: B (379B, corrected count) or C (265B, mechanism-free)?** The two research waves disagreed: the core wave (Tradeoffs + Routing) recommended the mechanism-free ~265B form (C); the adversarial pass recommended the ~378B-class corrected-count form (B) and flagged C as over-trimming the ticket's explicit "do not over-trim toward 200" boundary and reinterpreting #191's scope (which kept a light mechanism clause). **Underlying tension:** the ticket's stated *principle* ("mechanism belongs in the body") and Anthropic's own guidance point toward C, while the ticket's stated *target* (~378B #191 close-state, don't over-trim) points toward A/B. **Orchestrator lean: Option B** — it honors the explicit ~378B target the ticket sets, fixes the factually-stale "3–5" count (so it's strictly better than verbatim A), keeps the load-bearing disambiguation tail, and passes every gate. Pursuing C is legitimate only as an explicit, user-ratified ticket-target amendment (the ~378B Edge cannot be silently overridden by "but 265 > 200"). This is a deliberate user/spec call — complexity is `complex` + criticality `high`, so critical-review auto-fires before spec approval to pressure-test it.
2. **[Resolved] Exact byte targets and the `total` row.** A=378 (`total` 7196), B=379 (`total` 7197), C=265 (`total` 7083); formula `new_total = 6818 + V`. Both `research` and `total` rows move together; budget==measured, no headroom. Implementation copies the tool-emitted rows verbatim (folded scalar clip-chomps +1 newline).
3. **[Resolved — carry into Spec/Plan as required scope] Docstring + mirror.** Update the ratchet docstring (lines ~22–26, the "stays at 502 until ticket 302 lands" note) in the same commit; regenerate `plugins/cortex-core/skills/research/SKILL.md` via `just build-plugin` and commit canonical+mirror together. Sequence after #299 (now complete).
4. **[Resolved] Lifecycle-id / re-cap rule.** Lowering a budget needs no lifecycle-id (only raises do); confirmed against `project.md:48` and #298's spec. `research`'s cluster exemption means ~378B (or 265B) is structurally legal regardless.
