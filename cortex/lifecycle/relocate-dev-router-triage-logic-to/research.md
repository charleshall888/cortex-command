# Research: Relocate dev-router triage logic to a branch-gated reference (#343)

## Epic Reference

Epic research: [`cortex/research/skill-efficiency-remaining-work/research.md`](../../research/skill-efficiency-remaining-work/research.md). #343 is **R5** — the smallest of three adversarially-validated "post-#336 core-skill efficiency survivors." Scope this ticket to the dev-router relocation only; the plan-phase §1b extraction (#341, shipped) and the morning-review close-ordering fix are sibling tickets, not this one's concern. The epic's shared discipline: **rank by hot-path resident-tokens and clarity-harm, not bytes-on-disk; preserve test-pinned/overnight-cited headings verbatim as pointer stubs.**

## Codebase Analysis

`skills/dev/SKILL.md` (274 lines, 18,336 B) classifies each request into five first-match branches (Step 1), each routing to a downstream step:

| Branch | Lines | Downstream |
|---|---|---|
| 1 Backlog Triage | 29–35 | **Step 3** (triage, 131–242) — the only branch that reaches Step 3 |
| 2 Multi-Feature/Batch | 37–49 | external `/overnight`, or Step 4 (trivial/mixed arms) |
| 3 Vague/Uncertain | 51–57 | external `/discovery` |
| 4 Trivial Change | 59–65 | **Step 4** (241) |
| 5 Default (Single Feature) | 67–71 | **Step 2** (criticality pre-assess, 85–129), then external `/lifecycle` |

**Consuming-branch fact (the central design driver):** Step 2's heuristic table is reached only by **Branch 5** (L71) and the **Step-4 decline path** (L260, itself reached from Branch 4 / Branch-2-trivial). **Branch 1 never reaches Step 2.** So the two relocation candidates have *disjoint* consumers — the ticket's "a reference the triage branch reads" phrasing is imprecise for the criticality table.

**Relocation candidates (measured):**
- **Step 3c presentation** — Block 1 per-epic recommendation rendering (182–213, ~3,022 B) + Block 2 flat-list dedup (215–236, ~1,542 B); combined 178–236 ≈ **4,765 B**. Branch 1 only. Both blocks always render together ("Build both before displaying either").
- **Step 2 heuristic table + "Forming the Suggestion"** (89–120, ~1,433 B). Branch 5 + Step-4-decline.

**Stays in the body wholesale (deterministic mechanics / safety routing):**
- Step 3 Backend gate (135–142), 3a index regen (144–150).
- Step 3b (152–176): ready-set read, `cortex-build-epic-map` invocation (L164), output-schema note, ready-intersection, exit-1 fallback / exit-2 halt.
- Step 2 `### Resumed Lifecycle` guard (122–129) — control-flow, not presentation.
- `cortex_command/backlog/build_epic_map.py` (~L159) emits `{id, spec, status, title}` under `{"schema_version":"1","epics":{…}}` — **contract unchanged**; matches SKILL.md L168.

**Net-new for this skill:** `skills/dev/` has **no `references/` dir** and **zero `${CLAUDE_SKILL_DIR}` usages** today. Both facts are firsts for dev.

## Web Research

Anthropic's own **Agent Skills** architecture is the canonical prior art for this refactor (three-tier progressive-disclosure loading: metadata → SKILL.md body → reference files loaded only when a branch needs them; "no context penalty for bundled content that isn't used"). Directly applicable best-practices:
- **"Domain-specific organization"** — scope reference files *by actual consumer*, so a branch that doesn't need a block never loads it, rather than bundling under one label. This is the decisive external endorsement of consumer-keyed splitting.
- **Counter-check**: "don't split what's small and always-used" — extraction should clear a cost/benefit bar (large enough + genuinely branch-conditional).
- Attention-dilution is a *measured* cost, not just token waste: Chroma "Context Rot" (~7.9% degradation from input length alone, distractor-free) and lost-in-the-middle (attention is zero-sum). This is the mechanistic basis for the epic's "resident-tokens and clarity-harm" thesis.

**Documented failure modes for on-demand references** (load-bearing for risk assessment): missed reads / ignored references (agent doesn't follow a pointer — fix by making the link imperative/prominent); partial reads on nested references (keep refs one hop from the body, add a ToC if >100 lines); bare-relative path resolution failure (GH #56325 — exactly what ADR-0009 guards); and **"read-but-not-applied"** (agent reads a ref but skips instructions in it later — argues for keeping must-always-fire logic in the body).

## Requirements & Constraints

- **L1-neutral, structurally.** The L1 ratchet (`tests/test_l1_surface_ratchet.py`, dev budget 285 B) measures only frontmatter `description`+`when_to_use`. Body relocation cannot change it. dev is in the routing-pressure cluster, but that governs L1 only. No re-cap implicated.
- **Size cap not triggered.** 500-line cap (`test_skill_size_budget.py`); dev is 274 lines. Extraction to `references/` is the *supported pattern* here, not a compelled fix.
- **Parity survives** (`bin/cortex-check-parity`, corpus-wide token presence over `skills/**/*.md`): a `cortex-*` token moved into `skills/dev/references/*.md` stays in scope. **R6 carve-out**: keep a narrative mention — a token reduced to a bare flat-table cell can be dropped. (Adversarial confirmed zero binstub tokens actually move; `cortex-build-epic-map` stays in Step 3b.)
- **SP001/SP002 (`cortex-check-skill-path`, ADR-0009):** D1/SP001 fires only inside `<!-- BEGIN/END SUBAGENT PROMPT -->` fences or `*-prompt.md` files → **inert** for a plain prose-Read reference. D2/SP002 fires on bare-relative `Read`/`bash` targets → **the body pointer MUST be `${CLAUDE_SKILL_DIR}/references/<file>.md`**, never bare. If a new ref itself contains further Read/execute pointers, those must carry a propagated absolute prefix too.
- **L201 (`cortex-check-bare-python-import`)**: applies to the new ref identically; no Python in the moving content today.
- **Contract lint E101/E103 + callgraph** rescan `cortex-*` invocations and slash-invocation strings wherever they land — **preserve invocation lines verbatim, do not paraphrase** during the move.
- **Auto-mirror**: `plugins/cortex-core/skills/dev/` regenerates from canonical via pre-commit; edit canonical only; commit canonical+mirror together.

## Ref-Structure Design & Token Cost

Three placements evaluated against a per-branch resident-load model (baseline 18,336 B/branch today, since the whole file loads before Step 1 classifies):

- **Option A — one combined ref** (both blocks): **REGRESSES** the consuming branches. Read is all-or-nothing, so Branch 1 → ~19,098 B (over-reads the unused criticality table) and Branch 5 → ~19,098 B (over-reads the unused triage rendering) — both *above* baseline. Rejected.
- **Option B — two consumer-keyed refs** (`triage-rendering.md` for Branch 1; `criticality-heuristics.md` for Branch 5 + decline): no branch exceeds baseline. Branch 1 −6%, Branch 5/decline −24%, Branches 2/3/4-accept −32%. Each branch pays only its own block + a fixed ~160–200 B pointer tax. Matches the repo's `critical-review` per-purpose reference granularity and the Web "domain-specific organization" pattern.
- **Option C — relocate Step 3c only, criticality inline**: Branch 1 ~+224 B (worse than baseline — the removed block was the only content that mattered there); leaves a fixed ~1,274 B/call on the 3 non-Step-2 branches.

**On the byte model's validity (adversarial):** these figures are a computed metric — *no test enforces body byte count* (L1 is frontmatter-only; size cap is lines and far off). The justification is the epic's attention-dilution thesis (Web-backed), not a failing gate. Real, but untestable.

## Mirror & Path-Resolution Feasibility

**Feasible as-is — no build/hook/test change required.** `just build-plugin` (justfile ~589–628) copies each skill with `rsync -a --delete skills/dev/ plugins/cortex-core/skills/dev/` — archive-mode recursion sweeps a new `references/` subdir automatically (`dev` is already in the SKILLS list). The pre-commit drift hook (`.githooks/pre-commit`) rebuilds the whole mirror on any staged `skills/` change and **blocks the commit** if the staged mirror diverges. `tests/test_dual_source_reference_parity.py` globs `skills/*/references/*.md` and auto-routes dev→cortex-core (dev in the PLUGINS dict) — a new ref is auto-discovered and byte-parity-asserted with no test edit. `tests/test_skill_callgraph.py` rglobs recursively — auto-covered.

**Required authoring discipline:** introduce the `${CLAUDE_SKILL_DIR}/references/<file>.md` resolve-in-body pointer (dev has none today; own-dir form suffices — no sibling `../`); run `build-plugin` *with* the canonical-edit commit; `git add` all new canonical + mirror files explicitly.

## Test / Citation-Pin & Regression Surface

**Citation-clean move.** No test greps the dev triage table, criticality table, or any Step 2/3c heading inline; `tests/test_skill_section_citations.py` pins only `skills/lifecycle/references/{plan,complete,review}.md` (no dev scope); no `.parity-exceptions.md` dev entry; no overnight-prompt citation; the sole historical hit is an archived research doc (not test-enforced). `build_epic_map.py`'s docstring cites "dev Step 3b" generically, and Step 3b isn't moving. **This retires the epic's feasibility prerequisite ("confirm no test greps the triage table inline").** Recommend adding a standing wiring guard (modeled on `tests/test_competing_plans_wired.py`) — file+mirror exist, body pointer resolves, directive is a distinct line — but note it covers static wiring only.

## Sibling Precedent (#341 §1b extraction)

Direct template, same epic (#340), shipped. Reusable checklist:
1. **Leave the pinned heading verbatim as a stub + one-line pointer**; keep the **routing directive line distinct** from the stub heading (a wiring test can then catch a revert that aliases them).
2. **Body resolves `${CLAUDE_SKILL_DIR}` and propagates**; #341 added a bullet to lifecycle SKILL.md's "Reference-path propagation" manifest. **dev has no such manifest — introduce it from scratch**, sized to 1–2 targets.
3. **Repoint any test/overnight citation** — none exist for dev (lighter than #341's three sites).
4. **Commit canonical + mirror together**; `git add` untracked new files explicitly (trunk `git commit -- <pathspec>` / `--only` drops untracked files otherwise).
5. **Token-leak gotcha**: if any acceptance check greps for absence of a token, even a *prose mention* of the extracted token in the stub can fail it (#341's `plan_comparison` grep==0 rework). Word stubs to name the *target file*, not the extracted content's tokens.

## Adversarial Review

- **The optimization targets an unenforced, self-invented metric.** Nothing regresses if we do nothing; nothing tests that the relocation improved anything. Weigh against the epic's deliberate (Web-backed but untestable) attention-dilution thesis.
- **Hot-path round-trip.** Branch 1 (bare `/dev` → triage) is the most common invocation; relocating Step 3c inserts an extra assistant→tool→result Read turn at the moment the user waits for triage output. The −6% byte "saving" for Branch 1 is a micro-optimization the token model prices at zero latency.
- **Step 3c is routing logic, not inert presentation.** Its decision tree (all-refined→overnight, any-unrefined→refine-list, no-children→discovery, blocked-note prepend, "evaluate using only non-blocked/non-in_progress/non-review children") is what the user is told to do next. Relocating it one hop from the child-map it operates on invites the "read-but-not-applied" failure — a correctness risk, not just a token trade.
- **Step 2 split creates an ordering inversion.** `### Resumed Lifecycle` (122–129) guards "*this assessment*" — whose referent is the moved table. If the body's heuristics-ref pointer precedes the resume-guard (current top-down order), the model Reads the ref even on the resume path where the guard says skip → wasted Read, making the resume path *worse*. **Mitigation: invert block order — guard clause first, ref-Read only on the non-resume path — and rewrite "this assessment" to name the ref explicitly.**
- **The wiring-guard cannot cover the main new risk.** `test_competing_plans_wired.py` itself documents that runtime cold-read under-trigger is untestable in a static check. The guard gives static-wiring coverage, not missed-read coverage — say so plainly.
- **Second caller of Step 2.** The Step-4 decline path (L260) is a *second* inbound edge to the criticality block — wire it as a two-caller ref, not Branch-5-only.
- **Pre-existing unrelated mislabel (do not fix here):** Step 4 (L246) says "trivial (Branch 5)" — Branch 5 is the non-trivial default; the trivial branch is Branch 4. Out of scope; noted so the plan doesn't wire on the wrong branch label.

## Open Questions

1. **[Scope/value — needs user decision at exit gate] How much to relocate, given the adversarial cost.** Research converges that *if* relocating, the **structure** is Option B (two consumer-keyed refs). But the byte win is against an unenforced metric, while relocating **Step 3c** puts a Read round-trip + a "read-but-not-applied" correctness risk on the hottest path (Branch 1 triage), where inline-adjacency to the child-map arguably *lowers* clarity-harm. The three coherent scopes:
   - **(a) Full Option B** — relocate both blocks (matches epic scope; max dilution cut; accepts the Step 3c hot-path round-trip, mitigated by an imperative "Read before rendering" signal; requires the Step 2 order inversion).
   - **(b) Criticality-heuristics only** — relocate Step 2's table (89–120) to `criticality-heuristics.md`; **leave Step 3c inline** so triage routing logic stays adjacent to its data on the hot path. Still cuts dilution on the branches that never hit Step 2; requires the order inversion.
   - **(c) Triage-rendering only** — relocate Step 3c; leave Step 2 inline (sidesteps the ordering inversion) but concentrates the round-trip/correctness risk on the hottest path.
   *Recommendation to carry into the exit-gate question: (a) full Option B, because it honors the epic's committed scope and the consumer-keyed structure is provably non-regressing, provided the Step 2 order is inverted and both Read pointers use imperative "Read X before producing output" phrasing to counter missed-reads.*
   **RESOLVED (user, exit gate 2026-07-01): (a) Full Option B.** Relocate both blocks to two consumer-keyed references (`triage-rendering.md` for Branch 1, `criticality-heuristics.md` for Branch 5 + Step-4-decline). Mandatory plan requirements carried from this decision: (i) invert Step 2 block order so `### Resumed Lifecycle` fires before the criticality-heuristics ref-Read, and rewrite its "this assessment" referent to name the ref; (ii) both body pointers use imperative "Read X before producing output" gate phrasing (not a bare link) to counter missed-reads; (iii) wire `criticality-heuristics.md` as a two-caller ref (Branch 5 + L260 decline path); (iv) the runtime missed-read / read-but-not-applied risk is untestable — the wiring guard covers static wiring only.

2. **[Resolve in Spec] Imperative Read-signal wording.** Given the missed-read / read-but-not-applied failure modes, the body pointers should be hard gate lines ("Step 3c renders from `${CLAUDE_SKILL_DIR}/references/triage-rendering.md` — Read it before producing any triage output"), matching lifecycle's imperative phrasing, not a bare bracketed link. Confirm final wording at Spec.

## Considerations Addressed

- **Alignment consideration (criticality table's consuming branch):** *Confirmed and resolved.* Three independent agents (Codebase, Requirements, Ref-structure) verified the Step 2 heuristic table is consumed by Branch 5 + the Step-4-decline path, **not** the triage branch — so the ticket's single-triage-reference phrasing is imprecise. Resolution: gate the criticality block to its *actual* consumers via its own reference (or leave it inline), never behind the Branch-1 triage read. This is exactly Open Question 1's scope fork.
