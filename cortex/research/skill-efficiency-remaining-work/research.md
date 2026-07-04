# Research: skill-efficiency-remaining-work

Investigates which core-skill token-efficiency / structural changes are worth doing,
*after* adversarial validation and *after* accounting for the completed offload epic #336.
The line-item findings were produced and adversarially verified across a 9-agent audit in
the originating conversation (six opportunity-finders, then a symmetric trio —
defense-of-current, mechanism-failure, neutral-cost-model — plus a focused architecture probe).
This artifact records the survivors and kills, with the reasoning, so decompose can act.

## Research Questions

1. Which of the audit's candidate cuts survive adversarial review as genuine net wins? → **Three: plan.md §1b lazy-extraction (R3), morning-review close-ordering fix (R7), dev-router triage relocation (R5). R1/R4-§2a/R6 are killed; R2 is contested.**
2. Does deduping the repeated backend-routing prose (R1) save tokens? → **No — net negative. The ~12 blocks route different actions (read/create/close/index-regen/gate) with load-bearing site-specific arms; the canonical block is write-back-specific; and the standalone skills (`/dev`, `/discovery`, `/refine`, `/morning-review`) don't load `backlog-writeback.md`, so a pointer forces a 6.7KB Read to recover ≤1.5KB inline [skills/lifecycle/references/backlog-writeback.md:7].**
3. Is plan.md §1b actually dead weight on most plans? → **Yes, decisively. §1b is ~10.9KB / 43% of plan.md, loaded on every Plan read but gated to `criticality=critical` only [skills/lifecycle/references/plan.md:18]. Measured criticality across 257 features: 149 high, 98 medium, 5 low, **5 critical** (≤7 with overrides) — §1b fires on ~2% of plans.**
4. Is the morning-review Step-4 auto-close a real bug? → **Yes. `SKILL.md` Step 4 runs a full pre-merge auto-close [skills/morning-review/SKILL.md:95], but `walkthrough.md` §5 states closure "moved to §6b… closing tickets before confirming the PR has merged was a bug" [skills/morning-review/references/walkthrough.md:435]. The model receives two contradictory orderings of a destructive action.**
5. Is the dev-router "hot path" claim correct, and is offloading Step 3c to a verb viable? → **Half-correct, and the offload is wrong. Step 3c *executes* only on Branch 1 (triage), but its ~5KB *loads* on all five routing branches — the waste is dilution on the 4 branches that never use it. The 3c recommendation tree is presentation/routing judgment, not deterministic logic (`build_epic_map` emits only id/title/status/spec [cortex_command/backlog/build_epic_map.py:159]); the right move is RESTRUCTURE-to-lazy-ref, not verb-offload.**
6. Would isolating lifecycle phases into fresh contexts (the strategic claim) be high-leverage? → **No — spike/wontfix. See Architecture Piece 4 and Decision Records.**

## Codebase Analysis

- **plan.md §1b** spans lines 21–127 (~10,915 B) and sits physically *before* §2 (line 128), so a top-to-bottom reader loads it on every Plan phase even though §1a routes non-critical plans straight to §2 [skills/lifecycle/references/plan.md:18]. The whole file enters context on `Read` regardless of internal order, so the win requires physical extraction to a separately-Read-gated file, not reordering.
- **§1b coupling is citation-only, not functional.** The overnight orchestrator carries its own inline competing-plans reimplementation and only *cites* plan.md §1b as a documentation anchor [cortex_command/overnight/prompts/orchestrator-round.md:302]; it does not Read-extract §1b at runtime. The heading is also pinned by a test [tests/test_skill_section_citations.py:64] and a #332 guardrail preserves `### 1b. Competing Plans` verbatim "because overnight prompts cite them by designator" [cortex/backlog/332-consolidate-implementmd-branch-worktree-dispatch-and-remove-the-inline-python-heredoc.md]. All three are satisfiable by leaving a stub heading + a one-line pointer to the extracted ref.
- **morning-review** Step 4 (`SKILL.md:95`) is ordered before Step 5 commit and Step 6 PR-merge, while §6b is the post-merge closer the protocol moved to [skills/morning-review/references/walkthrough.md:435]. §6b's own skip-guard means a pre-merge Step-4 close reintroduces the exact bug §5 says was fixed — Step 4 is stale, not a fallback.
- **dev/SKILL.md** Step 1 classifies into five first-match branches; only Branch 1 ("what's next") reaches Step 3 triage, yet the entire ~18KB SKILL.md — including the ~5KB Step-3 triage logic and the Step-2 criticality heuristic table [skills/dev/SKILL.md:93] — loads on all five branches.
- **Prior art already consumed the deterministic-offload category.** Epic #336 (complete) and children #330/#331/#332/#333/#326 offloaded event emission, PR-state routing, worktree dispatch (incl. removing a Python heredoc), and requirements selection to CLI verbs [cortex/backlog/336-offload-deterministic-lifecycle-mechanics-to-cli-verbs.md]. #072 shipped "agent-reasoned demo selection" as an intentional feature [cortex/backlog/072-agent-reasoned-demo-selection-from-configured-command-list-at-morning-review.md], which is why R4-§2a (offload the demo-selection prose) is dead — it is a deliberate model-judgment affordance.
- **The audited corpus** is ~127K tokens of skill prose; the lifecycle cluster alone is ~35K. The interactive lifecycle accumulates a worst-case ~51K tokens of resident phase-reference prose in a single unbroken session [skills/lifecycle/SKILL.md:91].

## Domain & Prior Art

- This discovery is the next link in a long token-efficiency lineage: #172, #187, #191 (boot-context surface), #298–302 (L1 cap policy + adversarial trims), and #336 (deterministic offloads). It deliberately starts where #336 stopped: #336 harvested the *deterministic-procedure → verb* category; what remains are a *structural lazy-load*, a *cross-skill correctness bug*, and a *router restructure* — none of which #336 scoped.
- The overnight runner is the prior-art proof that fresh-per-task isolation works (`feature_executor` renders a fresh ~5–10KB system prompt per task [cortex_command/overnight/feature_executor.py:628]) — but it is autonomous by construction (zero `AskUserQuestion`), which is precisely why it can isolate and the interactive lifecycle cannot cheaply (see Piece 4).

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| R3 — extract plan.md §1b to lazy `competing-plans.md` | S–M | Repoint 1 test assertion + 1 overnight citation + the #332 guardrail (keep stub heading); critical-branch gains one Read round-trip on ~2% of plans | Confirm the `### 1b` heading stays in plan.md as a real pointer; identify the §1a stub insertion point |
| R7 — remove stale pre-merge auto-close in morning-review Step 4 | S | Must ensure §6b remains the *sole* closer and no flow silently skips closure when there is no PR | Trace the no-PR / declined-merge path through §6b's skip-guard |
| R5 — relocate dev Step-3 triage block to a Branch-1-gated reference | S–M | Keep the Step-3b exit-2 safety routing and Step-2 criticality table as model-judgment criteria (lazy-load, do not delete or verb-offload) | Confirm no test greps the triage table inline |
| Phase-isolation (architectural) | L–XL | Fights interactive's human-in-the-loop property; full-blast rewrite of the most safety-critical skill | — (declined; see Decision Records) |
| R2 — migrate `clarify_critic`/`plan_comparison` events to the verb | M | Contested — see Open Questions | Decide the dual-producer parity question first |

## Architecture

### Pieces

- **Plan-phase reference slimming** — extract the critical-only "Competing Plans" block (plan.md §1b, ~10.9KB) into a lazily-Read `competing-plans.md`, leaving a stub `### 1b` heading + pointer in plan.md; non-critical plans (~98%) stop loading it. The single highest-value item: largest resident-byte reduction, on the hottest interactive path, low effort, and it is the no-architectural-risk version of the resident-prose reduction that the phase-isolation probe recommends.
- **Morning-review close-ordering correctness fix** — collapse the stale pre-merge auto-close (SKILL.md Step 4) to a pointer at the post-merge §6b closer, removing a live contradiction between two destructive-action orderings. A correctness fix, not a token cut; highest priority despite ~zero bytes saved because a contradiction misleads the model on every read.
- **Dev-router triage relocation** — move the Step-3 backlog-triage block (recommendation tree + Step-2 criticality table) into a Branch-1-gated reference so its ~5KB stops diluting the four routing branches that never execute it; keep the exit-2 safety routing and criticality criteria as judgment, lazily loaded. Not a verb-offload — the recommendation logic is presentation judgment.
- **Phase-isolation decision record (no build)** — record the verified ~51K-token accumulation ceiling, the harness "context only grows, no shed API" constraint that kills selective ref-shedding, and the conclusion that full isolation fights interactive's human-in-the-loop property; redirect resident-prose-reduction effort to phase-ref trimming (of which Piece 1 is the first instance). Ships as a spike note / wontfix, not an epic.

### How they connect

The three build Pieces are independent core-skill efficiency changes with no build-order dependency on each other; they cohere only as "the post-#336 survivors of an adversarial efficiency audit." The correctness fix (morning-review) is the priority because it removes active misdirection; the plan-phase slimming is the highest token-value; the dev-router relocation is the smallest. The decision-record Piece is the boundary marker: it states why the obvious "big architectural win" (isolate phases) is declined and points future resident-prose work at the trimming lever the build Pieces exemplify — so the four Pieces together draw the line between what is worth doing (targeted, low-risk reductions) and what is not (a context-architecture rewrite).

## Decision Records

- **Rank by hot-path resident-tokens and clarity-harm, not bytes-on-disk.** The neutral cost-model showed the three runtime paths share almost no files, prompt caching makes resident tokens cheap in dollars, and the real cost is attention-dilution — which caching cannot relieve. That inverts a pure-byte ranking at both ends: it elevates the morning-review contradiction (near-zero bytes, maximum clarity-harm) and demotes decompose.md (2nd-largest file, but rarest path and test-anchored).
- **Phase-isolation declined.** The accumulation ceiling is real, but the heavy *work* is already dispatched to fresh sub-agents (research fan-out, builders, reviewer, critical-review, competing plans); only instruction-prose accumulates, the mandatory pauses + the Complete process-split already shed it in the normal flow, and auto-compaction caps the rest at zero design cost. Selective ref-shedding doesn't exist in the harness; full isolation is L/XL and degrades interactive's single-thread human steering. Verdict held at high confidence.
- **Grouping for decompose.** The three build Pieces share a theme but the correctness fix is arguably standalone. A thin epic ("post-#336 core-skill efficiency survivors") is reasonable but optional; decompose may file them as independent tickets. Left to the decompose gate.

## Open Questions

- **R2 (event-migration of `clarify_critic` / `plan_comparison`) is contested — likely declined.** #330's body listed `plan_comparison`'s `disposition` field as a migration target [cortex/backlog/330-add-field-to-cortex-lifecycle-event-and-route-the-hand-written-event-sites-through-it.md], yet the site still hand-writes JSONL, and the defense agent found `plan_comparison` has *two* deliberately parity-visible producers (plan.md + orchestrator-round.md) — migrating only one severs the visible schema parity a shared metrics consumer relies on. Net byte win is ~1 line. Resolve before any ticket: was the site a deliberate #330 omission or a miss? Default disposition: drop, unless the parity argument is found not to apply.
- Does the morning-review no-PR / declined-merge path still close tickets somewhere after Step 4 is removed, or does closure silently vanish in that branch? Must be answered during the R7 fix, not before.
