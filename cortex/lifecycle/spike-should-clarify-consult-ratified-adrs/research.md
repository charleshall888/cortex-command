# Research: Should Clarify consult recorded ADR decisions before research fan-out is sized?

**Clarified intent.** Determine whether Clarify should consult recorded ADR decisions before research fan-out is sized, by pricing a bounded selection mechanism against the saving it would have produced across a sampled corpus of closed lifecycles — and land the chosen mechanism in the refine skill if the trade is favourable, or record an explicit no-go if it isn't.

**Tier/criticality:** complex / high. **Fan-out:** 7 angles (6 core parallel + 1 adversarial last) against a cell bound of 8.

> **Headline.** The measured answer is **no on both counts, and there is nothing to build.**
>
> 1. **The ADR mechanism: no-go.** 0 DECLINES in 26 stratified samples; 24 of 26 firings would be false alarms by the ticket's own standard; and the ticket's sole evidence is wrong four separate ways (see Adversarial O1–O4).
> 2. **The relocated alternative: already shipped.** The constraint #404 missed was not in an ADR — it was in the requirements corpus Clarify already rates against, unreachable because `cortex-load-requirements` read tags from a lifecycle `index.md` that could not exist at a fresh refine. **That was fixed in `1553a379` (2026-08-03 10:42:19 EDT), 3.5 hours after #404's `lifecycle_start` (2026-08-03T11:17:04Z = 07:17:04 EDT).** `cortex-refine start` now seeds `index.md` from the backlog item before Clarify runs (`cortex_command/refine.py:617-626`), with a repair carve-out for stuck `tags: []` indexes (#400, `create_index.py`).
>
> **Verified live.** `cortex-load-requirements --feature file-attribution-checker-and-perf-probe` in wild-light today returns `project.md`, **`engineering-rendering-perf.md`** (lines 793-796: "the ADR-0006 human GO/NO-GO is the successor yardstick … not a re-derived scalar"), **`render-2-5d.md`** (lines 160-161: "GPU-visible cost verdicts remain human-owned"), and `engineering-quality-gates.md`. Both governing files now load automatically. This spike's own session reproduced the fixed behavior: `cortex-refine start 432` seeded `tags: [refine, clarify, adr, token-efficiency, skills]` and the loader read them.
>
> **Consequence.** #404 is not evidence of a standing gap. It is evidence of a gap that was independently diagnosed and closed the same day, by a different ticket, before this spike was filed. The correct outcome is to record the measurement and close.

---

## Codebase

**No runtime ADR reader exists.** A grep across `cortex_command/`, `skills/`, `hooks/`, and `bin/` for `cortex/adr` returns zero matches outside `adr_citation_audit.py` and tests. `load_corpus()` (`cortex_command/adr_citation_audit.py:91-120`) builds `dict[int, list[str]]` — ADR number → filename stem — by regex over `entry.name` against `_CORPUS_FILENAME_RE` (line 73). It never calls `read_text()`, never parses frontmatter, never reads a title. It is a citation-integrity validator (`unresolved`, `slug_mismatch`, `duplicate_number`, `gap`), not a selector. **The ticket's suggestion to reuse it comes back negative.**

**The ratchet is the binding constraint, with 5 bytes of headroom.** `skills/refine/references/size-pin.txt` = **20588**. Live contents: `clarify.md` 4329 + `clarify-critic.md` 4887 + `research-phase.md` 1995 + `specify.md` 9372 = **20583**. `scripts/ratchet_refs.py:100-106` sums the whole directory with the pin excluded; `classify()` (lines 148-163) fails when `measured > pin`. The only escape is a hand-authored `# raised: <reason ≥30 chars>, lifecycle-id=<NNN>, date=<YYYY-MM-DD>` line, regex-validated by `tests/test_reference_size_ratchet.py:93-108`. `just ratchet-refs` only ever lowers a pin.

**`load_requirements_cli.py` is the pattern to copy — and it prints paths, never content** (docstring line 8), which is why its own emission is 62 bytes. Selection substrate is `project.md`'s hand-curated `## Conditional Loading` section, matched by ASCII-casefold substring against tags read from `cortex/lifecycle/{slug}/index.md` (`_read_tags`, lines 129-150; `except OSError: return []` at line 145). The `FALLBACK_NOTE_TEMPLATE` / `NO_INDEX_NOTE_TEMPLATE` split (lines 61-73) exists because collapsing them "made a bare project.md result indistinguishable from 'this feature genuinely has no area docs' — at the one phase (a fresh refine, before the index is written) where the index cannot exist."

**`adr/README.md` already states a consumer contract for exactly this question** (lines 57-63): a skill **MUST** honor constraints an `accepted` ADR encodes; **MUST NOT** treat a `proposed` or `deprecated` ADR as binding; **SHOULD** surface relevant ADRs "in spec output, plan output, or review output" for human confirmation. Note the assigned surfaces: spec, plan, review — **not Clarify**.

**Distribution.** `skills/refine/references/clarify.md` and its `plugins/cortex-core/` mirror are byte-identical; `.githooks/pre-commit` Phase 3 rebuilds mirrors from staged blobs and folds them into the commit. A `clarify.md` edit also triggers Phase 1.55 (`check-contract`) and Phase 1.87 (`check-skill-path`, ADR-0009).

## Web & Prior Art

**Only two attested patterns exist for agent/ADR integration, and neither is dynamic selection.**

1. **Static per-ADR glob scoping** — Actual AI (`actual.ai/blog/agent-optimized-adrs`): each ADR declares `applies_to: <glob>` plus a stable ID, so "an agent editing a stylesheet has no use for the ADR that governs your database schema, so loading it only burns context." It recommends normative keywords (MUST / MUST NOT) "an agent can follow" over prose. It sidesteps retrieval entirely by making scoping declarative at authoring time.
2. **Brute-force full-corpus read** — Shing Lyu (`shinglyu.com/blog/2026/03/01/ai-adr-code-review.html`): "List all files in `docs/adr/` … Read each ADR file … Cross-reference code changes." Binary violation flagging, no bounds/adjacent tier.

Surveyed and found **no** relevance-query capability: adr-tools (TOC only), log4brains (full-text search), MADR (no topic field in stock frontmatter), adr-manager (authoring only), Structurizr (browsable log), Backstage ADR plugin (full-text + filename-substring decorators). Structured MADR (2026) adds queryable tags/technologies but is a niche fork.

**The declines/bounds/touches classification is novel ground.** No academic, tooling, or blog source classifies a decision record as forbidding vs. constraining vs. adjacent. Policy-as-code "permits/denies/flags" is rule-engine matching against structured policy — a materially easier problem. Constitutional-AI guardrail work targets runtime action safety, not design-time conflict with a past ruling.

**Retrieval at 30–70 docs.** Literature converges on lexical/full-scan over embeddings at this scale, because infrastructure cost stops binding and precision starts to. No benchmark isolates title-only retrieval precision at this size — a genuine gap. Sharpest caution (`mnemehq.com/insights/ai-coding-agent-guardrails`): "embedding similarity is fuzzy, and the one ADR that forbids this exact change may not surface for this exact phrasing," and "retrieving a decision and placing it in context does not enforce it."

**Early-gate economics — the best-evidenced finding, and it supports the ticket's premise.** arXiv 2606.01365 measured across 56 failed multi-agent runs a mean post-warning token fraction of **0.581** (median 0.611): over half the spend on a doomed run happens after failure was already detectable. A pilot early-stop intervention cut that from 0.638 to **0.304**. BAGEN/Effloow reports agents wasting 28–64% of tokens on doomed trajectories.

**Anti-pattern caveat with a scope limit.** Warning-blindness evidence is strong (neugierig.org: "informing about a problem without blocking on it at some point often leads to … 'warning blindness'"; SAST false-positive rates of 70–90%, with 33% of DevOps teams losing over half their time to false positives) — but it is drawn from high-volume, recurring, blocking-adjacent checks. It is **not established** that it transfers to a once-per-ticket advisory read. What does transfer: false positives destroy trust fast.

## Requirements & Constraints

**Token economy** (`project.md:21`): "the levers are session length, turn count, and fan-out width … anything that exists to police or observe the harness itself is presumed deletable unless it names specific evidence." A Clarify-side ADR check is machinery that polices whether a ticket complies with a governing decision — it must name evidence to survive.

**Deletion bias, both prongs** (`project.md:23`): the ticket clears prong one (names the #404 instance) and **fails prong two** — "an efficiency-framed ticket states its expected net effect on the surface it claims to shrink." Every enumerated go outcome adds prose to `skills/refine/references/`, and the ticket states no expected net effect on it. That is the literal shape of the "net additions dressed as efficiency" anti-pattern the clause names, evidenced by #382/#389/#390/#392.

**The named-evidence gate clause does not bind here.** `project.md:41` opens "a pre-commit/CI gate survives only by naming the specific, evidenced failure it prevents," and every survivor and retiree it lists is a pre-commit or CI gate. A Clarify-phase prose step is not one. **The clause in the same bullet that does bind** is the down-only reference-size ratchet.

**Short-road predicate** (`project.md:40`): `criticality ∈ {high, critical} OR tier == complex` takes the long road; "Research width follows tier the same direction." This is the mechanism the ticket's Why targets — fan-out width is sized off Clarify §5 values.

**Status is not a usable filter for "ratified".** Corpus: **18 accepted / 13 proposed / 2 superseded / 0 deprecated**. But `project.md` treats five `proposed` ADRs as currently binding: **0019** (line 49, "ADR-0019's dumb-arg-actor rule"), **0024** (lines 31, 49), **0025** (line 49), **0027** (line 58), **0029** (line 59, which has a live fail-loud enforcement point). A selector honoring `README.md:62`'s MUST NOT would silently skip the five decisions this project treats as most governing.

**ADR-0021's precedent, precisely.** It removed refine's overnight-suitability advisory because it "fired too early to act on for the overnight decision" and was "a brittle proxy," relocating judgment to "curation time, where the spec bodies are in hand and a human is present." It also accepted "a genuine loss with no replacement" for the standalone-refine population. Two transfers: the brittle-proxy warning lands squarely on any weak ADR selector; but the "too early" objection **does not transfer** — see Candidate Homes.

**Prior art.** **#161** (complex/high, complete) added the parent-epic sub-rubric to clarify-critic, choosing the critic over the Clarify worker specifically to avoid anchoring bias (worker/auditor separation, citing arXiv 2412.06593), and shipped an explicit honest-scope disclaimer of what it does *not* catch. **#187**'s audit found "small ceremonial references (`requirements-load.md`, the clarify-critic 5-branch table) cost more in indirection than inlining" — precedent against adding a further reference layer.

## Hit-Rate Measurement

**Frame repair was necessary.** The specified frame (archived lifecycles) is near-empty by construction: wild-light's first ADR is dated 2026-05-18, but **86 of 88 archived lifecycles (98%) predate it**. The frame was broadened to all completed lifecycles carrying a `feature_complete` event whose Clarify postdates the repo's first ADR — 153 eligible in wild-light, 118 in cortex-command — stratified into recency terciles, systematic random draw at `Random(seed=42)`.

**Sample: n=26** (wild-light 17: 4 early / 6 mid / 7 late; cortex-command 9: 2/3/4).

| Repo | n | DECLINES | BOUNDS | TOUCHES | NONE |
|---|---|---|---|---|---|
| wild-light | 17 | **0** | 13 | 2 | 2 |
| cortex-command | 9 | **0** | 6 | 3 | 0 |
| **combined** | **26** | **0** | **19** | **5** | **2** |

**Rule-of-three upper bound (95% one-sided): ≤~11% combined**; wild-light ≤~17%, cortex-command ≤~29%. The repos are **not poolable** — different ADR densities, ages, and citation conventions.

**Most BOUNDS cases are self-referential.** The ADR cited was frequently produced or amended *by that same ticket* (wild-light `decide-the-sprite-depth-model-before` → ADR-0055 and `magnitude-differentiated-terrace-ledge-treatment-subtle` → ADR-0059, both filed same-day after the ticket's Clarify; cortex-command `plan-parser-support-sub-task-headings` → ADR-0010, `move-overnight-suitability-judgment-from-refine` → ADR-0021), or was one the work already complied with. **In no sampled case did an ADR predating Clarify forbid or redirect what the ticket built.**

**Saving-per-hit could not be measured** — no DECLINES case arose. Illustrative ceiling from the reference case: 6 research angles + a 336-line spec + one review rework cycle.

## Selection Mechanism & Per-Clarify Cost

**Baseline measured live.** `cortex-load-requirements --feature nonexistent-test-slug` → 62 bytes of stdout, **1 turn**, fixed regardless of corpus size; the model then reads `project.md` (24,869 B) + `glossary.md` (690 B) ≈ 25.6KB / ~6,400 tok.

**Corpus, measured:**

| | cortex-command | wild-light |
|---|---|---|
| ADRs | 33 | 62 |
| Corpus bytes | 183,600 | 572,463 |
| Corpus tokens (est.) | ~45,900 | ~143,100 |
| Title list bytes | 1,804 | 4,486 |
| Title list tokens (est.) | ~450 | ~1,120 |
| Mean ADR size | 5,564 B | 9,233 B |

| Mechanism | Turns | Context @33 / @62 | Scales with N? | Classifies stance? | Silent no-op on absence? |
|---|---|---|---|---|---|
| Grep on titles/stems | 1 + 0–3 reads | ~flat | No | **No** | Needs a guard clause |
| LLM-router over titles | ≥1 | ~450 / ~1,120 tok | **Yes, linear** | **No** | Not automatic |
| Curated index file | 1 | sub-linear by curation | **No, by construction** | **Yes — only one** | Reuses existing pattern |
| `load_corpus()` reuse | — | — | — | Not a selector | n/a |
| Full-corpus read | 33–62 | ~45,900 / **~143,100** | **Worst** | Yes, prohibitively | Needs a guard clause |

**Grep must run on titles, not bodies.** Full-body grep for `model` hit **13/33** ADRs (39% false-positive rate on a one-word query); title-list grep hit exactly **1**, correctly.

Only the **curated index** both survives the corpus-scaling edge and can encode decline-vs-bound — because a human writes the relationship at curation time. Its cost is ongoing hand-curation and staleness, the same trade the requirements Conditional Loading section already accepts.

## Candidate Homes

**Home 1 — `clarify.md` §2 dimension 3.** The scope-line reconciliation is a split, not a single answer: an ADR that *declines* work is not a feasibility claim ("this is hard") but a governance one ("we ruled this out") — structurally identical to what dimension 3 already asks against `cortex/requirements/`. An ADR that *bounds* or *touches* is a technical constraint that already has a home in `fanout.md`'s mandatory Requirements & Constraints angle. So the closing scope line does not forbid the extension; it constrains what *kind* of check may be added.

**Home 2 — clarify-critic rubric. The "cheapest intervention" claim is false, twice.** The rubric names five dimensions today: intent clarity, scope boundedness, requirements alignment (`clarify-critic.md:44`), optional complexity/criticality calibration (same line), and the Parent Epic Alignment sub-rubric (lines 26-40, added by #161) — exactly the stated soft cap at line 80. A sixth requires a displacement or an extraction. The only plausible displacement is complexity/criticality calibration — **which is the input to `fanout.md`'s count matrix**, i.e. weakening the very mechanism this spike exists to protect. Structurally worse: the critic receives the confidence assessment and source material and **nothing from `cortex/adr/`**, so it can only ask "are you sure you checked?" — an unfalsifiable nudge. Home 2 is home 3's cost wearing home 2's name.

**Home 3 — a load step.** Inherits the index-timing trap (`_read_tags` returns `[]` silently when the index is absent), and there is no tag surface on ADRs to route against (`README.md:45`). Not a port of the existing algorithm — a new one. Largest blast radius: new verb, shipped to every consumer repo, most with no `cortex/adr/` at all.

**Home 4 — fanout/research-phase. Correctly ruled out, for a deeper reason than the ticket gives.** The count matrix is a pure lookup on tier/criticality, both finalized at Clarify §5 and written back at §7 before Research opens. Additionally, Research has **no human checkpoint** — Clarify §4 has `AskUserQuestion` wired to the critic's Ask disposition; an ADR-decline surfaced at Research entry could only hard-halt or silently skip.

**ADR-0021 rhymes only partially, and the direction matters.** Its advisory fired before the information it needed existed (spec bodies unwritten). The ADR check is the mirror image: ticket body and corpus are both fully in hand at Clarify, and nothing downstream produces information the check needs. ADR-0021's structural principle — judge with the material in hand, where a human is present — is closer to an argument *for* Clarify placement. Its brittle-proxy warning still lands on the selector.

**Ranked:** (1) do nothing pending hit rate; (2) if justified, home 1 scoped to declines-only, seeded from the ticket's own Touch-points; homes 2 and 3 below both; home 4 ruled out.

## Adversarial Review

**The ticket's evidence base is wrong on the merits, four ways — all verified against files.**

**O1 — ADR-0036 does not decline #404's work.** `wild-light/cortex/adr/0036-forward-plus-batching-disposition.md:120-128` retires `draw_call_ceiling: 200` — a *threshold key* — while explicitly **retaining** the census fields: "The per-chunk terrain surface census fields … are the retained structural context." The ADR's posture is *measure, don't threshold*; #404 proposes to measure. Further, the 524→514 figure the ticket quotes is `terrain_mesh.surface_total`, a **surface census**, not a draw-call count — not "exactly that number." Under the ticket's own scheme this is BOUNDS. A Clarify check firing here would have demanded the same reasoning the fan-out performed to conclude "not a conflict" — **the noise case the Edges warn about, generated by the ticket's own worked example.**

**O2 — The chronology is backwards (verified independently).** `0b50dc98` filed ticket #404 at **2026-07-27 17:10:04**. `a8be4f87`, which introduced the exact quoted sentences ("moves with terrain material-key work and is not a threshold" / "not a re-derived scalar"), landed at **18:53:23** — 103 minutes later, same session, same parent ticket. (`fbb35cab`, retiring the `draw_call_ceiling` open item, landed 17:04:06, six minutes before.) The quoted ruling was not a standing prior constraint; the ADR was in active flux that same day.

**O3 — No critical-review ran (verified).** `cortex/lifecycle/file-attribution-checker-and-perf-probe/events.log` holds five events — `lifecycle_start`, `clarify_critic`, `complexity_override`, `criticality_override`, `spec_approved` — and **no `critical_review`**. The catch was `research.md` § Adversarial review, item 6 — a research-phase angle — and `spec.md:258-259` records the camera-axis question "resolved during Specify by dropping it." **The ticket charges the detector's cost to the thing it detected.**

**O4 — "A simple/low ticket has no check at all" is falsified by the cited ticket (verified).** Its `lifecycle_start` records `tier: simple, criticality: medium`; `complexity_override` moved `simple → complex` (gate `research_open_questions`) and `criticality_override` moved `medium → high` (gate `clarify_reconcile`). The escalator engaged and carried the ticket into exactly the band §3b covers.

**O5/O6 — The problem is mislocated (verified end-to-end) — but the relocated fix had already shipped when the adversary wrote this, which the adversary did not check.** Retained in full below because the diagnosis is correct and load-bearing; only its *recommendation* is superseded. See the Headline. The supports that actually killed the camera axis (`research.md:334-338`) are three code/requirements facts and no ADR: `enemy_overlay_floor` absent from `perf_report_io.py`; `render-2-5d.md` reserving GPU-cost verdicts to a human; window-size and pose dependence; `TYPE_SHADOW` omitted. The decisive documentary constraint is `wild-light/cortex/requirements/render-2-5d.md:160-161` — "GPU-visible cost verdicts remain human-owned (headless probes are GPU-blind)" — restated at `engineering-rendering-perf.md:793-796`: "the ADR-0006 human GO/NO-GO is the successor yardstick for a ratified ceiling, not a re-derived scalar."

Confirmed by direct inspection: ticket #404 carries `tags: ['render', 'perf', 'tooling', 'adr']`; wild-light's `project.md` Conditional Loading contains the live trigger `render → cortex/requirements/engineering-rendering-perf.md`; and wild-light's `project.md` has **no `## Global Context` section**, so a fresh refine today loads `project.md` and nothing else. **The constraint was reachable through a shipped verb, via a tag the ticket already carries, if the verb were passed tags that exist at Clarify.** The ticket names the index trap only as something to "not inherit" — never as the thing to fix.

**O7 — Both status-filter branches ship a defect.** Honoring `README.md:62` misses the five `proposed` ADRs `project.md` treats as binding; ignoring status ships a documented contract violation inside a skill. The ticket evaluates neither branch.

**O8 — The cost-inversion I proposed is wrong on mechanism but right on conclusion.** (a) Prompt caching is prefix-based; an ADR list lands *after* the per-ticket body and requirements, so byte-identity buys nothing — a cache write every session, never a cross-session hit. (b) But `project.md:7` says the harness optimizes for "short sessions, few turns, and narrow fan-out — **not resident-prose micro-trims**," so ~1,120 resident tokens is noise by the repo's own law. Cost genuinely cannot discriminate between grep, index, and router — **which quietly removes the spike's stated no-go criterion "(d) an explicit no-go if (b) exceeds (c)."** (c) "1 turn" is the wrong unit: the mechanism costs `1 + p·k` turns, and since a title list cannot classify stance, every nonempty candidate list forces body reads (wild-light median 6,646 B, max 34,562 B). It buys one turn in order to buy more turns. (d) The precision result is equally an **~8% recall** result: none of `camera`, `probe`, `draw`, `perf`, `profile` appears in any wild-light ADR filename — **the target ADR-0036 is unreachable by title match from #404's own vocabulary.** (e) An LLM router is a subagent dispatch, not a `grep` turn.

**O10 — Touch-points seeding is structurally circular.** Touch-points are written by the party that missed the ADR, describing the subsystem they believe they are touching. A selector seeded from them returns ADRs about that subsystem — the TOUCHES set the Edges classify as noise — and misses DECLINES, which by definition live in a frame the author did not have. Verified on #404: its Touch-points name `perf_minspec_profile.gd`, `_window_visible_draw_calls()`, `perf_report_io.py`, #253, #112 — no term reaches ADR-0036 by title.

**O11 — Attacking the null.** (a) The strongest anti-mechanism argument is not 0/26 but **24 of 26 firings would be false alarms** by the ticket's own standard. The fire-suppression analogy defends sprinklers because their false-alarm rate is near zero; a sprinkler that sprays 24 times per fire is a leak. (b) Still, the asymmetry is real and unpriced: one avoided complex refine is a multi-hour session, and per O8b the per-Clarify cost is noise — so "measure the hit rate first" is the wrong rule; the right question is whether the false-positive tax is bounded, and (a) answers no. (c) Nothing durable is lost by declining **yet**: wild-light went 2 ADRs (2026-05-18) → 63 (2026-08-03), ~3–6/week and accelerating, so the priors-to-byproducts ratio will flip — but dating that flip is prediction, which the solution-horizon clause excludes.

**O12 — The corpus is a work byproduct with a citation habit, not a body of prior constraints.** Six wild-light ADRs landed on 2026-07-27 alone during one ticket's session; ADR-0036's entire history is authoring-and-rework by the tickets that cite it. cortex-command shows the same shape (34 ADRs in 11 weeks). This makes the 19/26 self-referential BOUNDS rate **the corpus's structure, not a sampling artifact**. "Consult ADRs at Clarify" presupposes a corpus that predates the work; where the corpus is co-produced, the useful verb is *cite* — already assigned by `README.md:63` to spec/plan/review output.

**O13 — The one mechanism with prior art is blocked by a recorded decision.** Static `applies_to:` glob scoping requires exactly the `area:`-style field `README.md:45` declined. Not fatal — the stated reason was "no consumer," and this spike would be the consumer — but it is a decision the spike must name rather than route around.

**O14 — The spike's own success criterion is unsatisfiable as written.** "(c) the hit rate over a sample of **closed lifecycles**" — a completed lifecycle is definitionally work that was not declined. BOUNDS and TOUCHES survive completion; DECLINES is excluded a priori, making 0/26 close to a tautology. The frame that would detect the phenomenon is **dropped scope**: grep specs for `## Non-Requirements` entries citing `ADR-NNNN`, then check whether the ADR predates the ticket. #404 is exactly that shape — `status: refined`, half dropped — and would never appear in a completed-lifecycle census. Running the corrected frame on the one available instance still returns negative (O1/O2), so the answer likely does not move, but the criterion should be amended.

---

## Open Questions

1. **Does the corrected (dropped-scope) frame change the 0/26 result?** — **Deferred to Spec with rationale.** O14 establishes the completed-lifecycle frame is survivorship-biased by construction, and names a cheap corrected frame (grep specs for `## Non-Requirements` citing `ADR-NNNN`, filter to ADRs predating the ticket). The adversary ran it on the one available instance (#404) and still got a negative. Deferred rather than resolved because the recommendation below does not depend on it: the decisive argument against the mechanism is the 24-of-26 false-alarm rate (O11a), which is measured on the *same* sample and is unaffected by survivorship in the DECLINES cell. Spec should decide whether to run the corrected frame as an acceptance criterion or record it as a known limitation.

2. **How many clarify-critic rubric dimensions exist today — 4 or 5?** — **Resolved: 5, at cap.** The Codebase angle counted 3 mandatory + 1 optional and reported headroom; the Requirements and Candidate-Homes angles both counted the #161 parent-epic sub-rubric (`clarify-critic.md:26-40`) as a fifth. The sub-rubric is a distinct rated axis with its own instructions and output contract, so it counts. `clarify-critic.md:80`'s "soft cap of 5" matches exactly. Consequence: home 2's "one rubric line" is false regardless of which reading is preferred, so this does not gate the recommendation.

3. **Should a selector honor `adr/README.md:62`'s MUST NOT (skip `proposed`) or match `project.md`'s practice (five `proposed` ADRs treated as binding)?** — **Deferred to Spec with rationale.** Both branches ship a defect (O7). It is deferred because the recommendation declines the ADR-selector mechanism entirely, which moots the choice; it returns only if a successor ticket revives the mechanism. If revived, the honest resolution is likely to amend `README.md` or `project.md` so the two agree, rather than to encode either side in a skill.

4. **Does the alert-fatigue literature transfer to a once-per-ticket advisory?** — **Deferred to Spec with rationale.** The Web angle established the evidence base is drawn from high-volume, recurring, blocking-adjacent checks and flagged the transfer as unproven. Deferred because O11a supplies a repo-local answer that does not need the literature: 24 of 26 firings would be false alarms on this corpus, which is a measured false-positive rate rather than an analogy.

5. **Does the tag-input fix generalize beyond the one worked example?** — **Resolved: yes, strongly in the repo that matters.** Measured over every numbered backlog item in both repos, matching each item's own frontmatter `tags:` against its repo's `## Conditional Loading` triggers with `load_requirements_cli.py`'s substring rule:

   | Repo | Triggers | Tags route to an area doc | Tagged, no match | Untagged |
   |---|---|---|---|---|
   | wild-light | 73 | **323 / 430 (75%)** | 43 (10%) | 64 (15%) |
   | cortex-command | 6 | 90 / 436 (21%) | 263 (60%) | 83 (19%) |

   At a fresh refine today every one of those routes to nothing, because the loader reads tags from a lifecycle `index.md` that cannot exist yet. So the fix lifts Clarify's area-doc coverage from 0% to ~75% in wild-light — the repo with the denser ADR corpus, the higher ticket-ADR citation rate, and the originating failure — and to ~21% in cortex-command, whose thinner trigger table (6 vs 73) is the limiter rather than the mechanism. cortex-command additionally has a `## Global Context` section (loading `glossary.md`) that wild-light lacks, so its fresh-refine baseline is slightly less bare.

## Considerations Addressed

- **ADR front-matter index foreclosed by `adr/README.md:45`.** Addressed in Web & Prior Art (the foreclosed `applies_to:` field is the *only* attested prior-art pattern), Selection Cost (priced only index variants avoiding a new field), and Adversarial O13 (the spike must name the decision rather than route around it; "no consumer" was the stated reason and this spike would be the consumer).
- **The binding constraint is the reference-size ratchet, not the named-evidence gate clause.** Addressed in Requirements (the clause is textually scoped to "a pre-commit/CI gate"; a Clarify prose step is not one) and Codebase (5 bytes of headroom; `# raised:` marker is the only escape). Every prose-bearing home was priced against it.
- **The ticket meets only prong one of the Deletion-bias front-door bar.** Addressed in Requirements. Carried into the recommendation: the recommended alternative adds ~0 reference bytes, which is the net-effect statement the ticket owed and did not give.
