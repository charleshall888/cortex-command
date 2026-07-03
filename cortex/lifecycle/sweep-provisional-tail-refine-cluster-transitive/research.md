# Research: Verify & apply the 42 provisional token-trim candidates for #361 (refine cluster + transitive tail)

> Scope anchor: the clarified intent from Clarify — verify each of the 42 provisional candidates via single-pass pin-hit verification, apply honoring a derived keep-list, record refuted candidates; ledger write-back deferred to a shared #357 reconciliation. Not the raw ticket body.
>
> Candidate set (verified against `cortex/research/skill-value-scorecard/master_candidates.json`): `status==unverified` ∧ file ∈ the 12-file set ∧ no `overlaps_ticket` ∧ no `reproposal_of` → **exactly 42** (32 COMPRESS + 9 MERGE_DEDUP + 1 LAZY_REF). ~7910 weighted tokens. No candidate carries `needs_user_input`.

## Codebase Analysis

**Dual-source mirror mechanism.** `just build-plugin` rsyncs each canonical `skills/<name>/` tree into `plugins/<plugin>/skills/<name>/`. The `.githooks/pre-commit` hook self-verifies: when a staged path touches `skills/`, it re-runs `just build-plugin` then `git diff --quiet plugins/$p/` and **fails the commit** if the staged mirror differs (forgotten mirror update fails closed). Workflow: edit canonical → `just build-plugin` → `git add` canonical + regenerated mirror → commit via `/cortex-core:commit` with an explicit pathspec (drift hook fails a split commit).

**Mirror map for the 12 files** (verified, zero current drift):
- → `plugins/cortex-core/` (9): `refine/SKILL.md`, `refine/references/{specify,clarify,clarify-critic}.md`, `research/SKILL.md`, `research/references/fanout.md`, `pr/SKILL.md`, `commit/SKILL.md`, `interview/references/loop.md`.
- → `plugins/cortex-backlog/` (1): `skills/backlog/SKILL.md` (backlog ships only in cortex-backlog).
- **No mirror** (2): `cortex/adr/README.md` (not under `skills/`); `cortex_command/overnight/prompts/plan-synthesizer.md` (`importlib.resources` package data — a trim takes effect on next wheel build, not via plugin sync).

**Test / lint gate surface** (what trips on a prose trim):
- `tests/test_lifecycle_kept_pauses_parity.py` — scans `skills/lifecycle/` + `skills/refine/` `AskUserQuestion` sites; validates `kept-pauses.md` anchors resolve within **±35 lines** (`LINE_TOLERANCE = 35`). Directly covers `refine/SKILL.md`, `clarify.md`, `specify.md`, `clarify-critic.md`. **This is the batch's primary systemic risk — see Adversarial.**
- `tests/test_research_fanout_matrix.py` — parses the fanout count-matrix table (floor 3 / corner 10 / monotone / cap). Real gate for `fanout.md` s2, not grep.
- `cortex_command/pipeline/tests/test_plan_synthesizer.py` — pins two verbatim phrases in plan-synthesizer.md (`"Avoid any position biases"`, `"Run the comparison twice with variant order swapped"`) and validates the envelope fields. Under `test-pipeline` in `just test`.
- `tests/test_l1_surface_ratchet.py` — **frontmatter `description`/`when_to_use` byte sum only**. Verified: none of the 42 candidates touch frontmatter (every span starts past its file's closing `---`), so not implicated. Keep as a cheap post-trim acceptance gate.
- `tests/test_skill_size_budget.py` (500-line SKILL.md cap — trims only help), `tests/test_skill_callgraph.py` (trips only on mangled `Invoke`/`Delegate to`/`dispatch` invocation lines).
- Lints: `bin/cortex-check-skill-path` (SP001/SP002 — do not strip a `${CLAUDE_SKILL_DIR}/` prefix or leave a bare-relative Read path; `refine/SKILL.md` has 7 refs, `research/SKILL.md` 3), `bin/cortex-check-prescriptive-prose` (LEX-1), `bin/cortex-check-bare-python-import` (L201), `bin/cortex-check-parity` (SKILL-to-bin).
- **`cortex/adr/README.md` is matched by NO pre-commit trigger** and has no mirror and no test pinning its prose — the least-gated file in the batch; only the commit-message hook applies.

**mech_pin semantics.** `mech_pins` (format `` `<token>`->path ``) have **no automated validator** — verification is manual grep. Critically, they are a **file-level keyword-cooccurrence pool, not span-scoped**: many are vacuous (e.g. plan-synthesizer s15's 25 mech_pins are every file containing the enum value `"medium"`). See Adversarial mitigation 1.

**Commit discipline.** Commits go through `/cortex-core:commit` (never manual `git commit`); the `PreToolUse` hook denies non-capitalized / period-ending / <10-char / non-imperative subjects and non-blank second lines.

## Web Research — instruction-compression safety

Published methodology converges on findings that directly shape the verification bar:
- **"Not referenced by a test" ≠ "not load-bearing."** Compression harm concentrates in **edge cases / ambiguity resolution** that a test suite does not exercise (canonical example: an unreferenced "regulated financial services" role line that only changes behavior on *ambiguous* input). Test-suite-clean is necessary, not sufficient.
- **Restated / duplicated instructions near a document boundary can be functionally load-bearing** (recency/emphasis; the "lost in the middle" mitigation) — a MERGE_DEDUP that drops the trailing copy is not automatically safe.
- **"Why" prose does generalization work a bare rule cannot** (Anthropic context-engineering: motivation lets the model generalize to unseen cases) — matches CLAUDE.md's "prescribe What and Why, not How."
- Instruction/decision-criteria text deserves **lower compression aggressiveness** than reference material (LLMLingua budget-controller precedent). Credible behavior-neutrality verification = eval-regression + semantic-diff + **explicit edge-case probing**, not merely "existing tests still pass."

Implication: the single-pass pin-hit bar (parent-set, not reopened here) is a *floor*; the "non-load-bearing" predicate must be judged against What/Why intent, weighting/emphasis, and user-affordance prose — not just whether a token still greps.

## Requirements & Constraints

**Mandate:** project.md "Maintainability through simplicity: Complexity is managed by iteratively trimming skills/workflows" + the "Workflow trimming" optional item.

**Guardrails that bound the trim** (all must be honored by the "non-load-bearing" call):
- CLAUDE.md "prescribe What and Why, not How" — intent/decision-criteria prose survives even if untested.
- CLAUDE.md skill-authoring guideline — identify the user-facing affordance a boundary protects before removing it; document reasoning if removing.
- `skills/lifecycle/references/kept-pauses.md` + parity test cover these in-scope sites: `refine/SKILL.md:159` (§4 complexity/value gate; inventory anchor `:166`), `clarify.md:57`, `specify.md:36/67/155`. `clarify-critic.md` has no `AskUserQuestion` (not a parity subject).
- `backlog/SKILL.md` has 4 `AskUserQuestion` sites **not** covered by the parity test (no automated backstop) — the step-7 lifecycle-routing menu is a real affordance.
- SP001/SP002 `${CLAUDE_SKILL_DIR}` path-resolution invariant; dual-source parity.
- `cortex/adr/README.md` **is** the policy doc other files back-point to (project.md Architectural Constraints) and carries the MUST/MUST NOT/SHOULD ADR-consumer contract — deleting that prose is a semantic change, not a density change. (MUST-escalation policy governs *adding* MUSTs; these are grandfathered pre-existing MUSTs, so no evidence-artifact is required to reword — but removing the semantics is out of a pure trim's bar.)

**Scope boundaries** (quoted/confirmed): four #357 children partition the 143 candidates with zero overlap (verified: 32+43+26+42=143); write-back to `master_candidates.json` deferred to a shared reconciliation; the cross-child `clarify.md`↔`discovery/references/clarify.md` dedup (~86 tokens) is **opportunistic-only and out of scope** for this child (single-sourcing it would edit a sibling-#359-owned file); locate spans by heading + pinned token, never by ledger line number.

**Per-file risk (Requirements lens):** HIGH — `refine/SKILL.md` (kept-pause + 7 path refs), `cortex/adr/README.md` (hub doc + MUST semantics + least-gated), `specify.md` (3 kept-pauses), `interview/loop.md` (dense What/Why + affordances). MEDIUM — `clarify.md`, `clarify-critic.md`, `fanout.md`, `backlog/SKILL.md`, `plan-synthesizer.md`. LOW — `pr/SKILL.md`, `commit/SKILL.md`, `research/SKILL.md`.

## Candidate Map — Refine Cluster (20 candidates, ~4547 weighted)

Per-candidate anchor / derived keep-list / verify-greps produced during research (available in the mapping outputs; summarized here by risk + preliminary verdict). Locate every span by heading + pinned token — several ledger line numbers have drifted.

| id | file | risk | prelim verdict | note |
|---|---|---|---|---|
| s10c | refine/SKILL.md (§4 complexity/value gate bullet) | **HIGH** | lean REFUTE | kept-pause boundary; dense simultaneous +/− pins ((Recommended), rationale-first ordering, AskUserQuestion, no "MUST decide"); collapsing risks killing the "when the pause fires" conditional |
| s7 | refine/SKILL.md (Alignment-Considerations Propagation) | **HIGH** | lean REFUTE | 6+ simultaneous pins (heading uniqueness, write/overwrite, coupled arg, ordering, negative guard, `origin: "alignment"`); "no-escaping" line states a fact, not rationale |
| s8 | refine/SKILL.md (Research Execution) | MEDIUM | APPLY | keep dispatch-arg shape, alternative-exploration criteria, halt-on-missing-artifact gate |
| s10a | refine/SKILL.md (Step 5 reconcile-clarify) | MEDIUM | APPLY | MERGE_DEDUP vs Step 2; keep both `reconcile-clarify` command lines byte-identical; preserve seed→reconcile→gate rationale |
| s6 | refine/SKILL.md (Sufficiency Check) | MEDIUM | APPLY (narrow) | collapsed form MUST retain "regardless of path" (observed-failure provenance) |
| s3 | refine/SKILL.md (Step 1 Resolve Input) | LOW | APPLY | keep 4 JSON field names + 4 result arms + clarify.md §1 xref |
| s13 | refine/SKILL.md (Constraints table) | LOW | APPLY | no pins; keep the slug-vs-slug gotcha row if reduced |
| s12 | refine/SKILL.md (Completion) | LOW | APPLY | fully redundant summary |
| s7 | clarify-critic.md (Disposition Framework) | HIGH | lean APPLY | partner form at critical-review/SKILL.md verified terse; needs partner text in hand, keep Apply/Dismiss/Ask + anchor-check |
| s12b | clarify-critic.md (Constraints table) | LOW | APPLY | ledger end_line 177 off-by-one (file is 176 lines) |
| s6 | specify.md (2b Pre-Write Checks) | MEDIUM | lean REFUTE | already survived a prior trim; names distinct failure modes incl. "state ownership" — don't collapse to one generic rule |
| s9 | specify.md (3b Critical Review) | **HIGH** | lean REFUTE | protected by `tests/test_critical_review_gate_nonlocal_failsafe.py` ordering test; `cortex-read-backlog-backend` must precede "critical-review gate protocol"; previously-killed similar proposal R1 |
| s3 | specify.md (2 Structured Interview) | MEDIUM | APPLY | keep AskUserQuestion line (:38) untouched; total shift < parity tolerance |
| s7a | specify.md (declined-loop-back callout) | LOW | APPLY | keep `"action": "declined"` trigger + `## Problem Statement` anchor |
| s5a | specify.md (2a missing-research guard) | LOW | APPLY | preserve `"action": "loop_back"`, `research.md missing` verbatim |
| s8 | clarify.md (5 Produce Clarify Output) | MEDIUM | APPLY | **hard constraint: do NOT touch criticality high/medium calibration language** (sole repo source feeding the critical-review gate) |
| s3 | clarify.md (1 Resolve Input) | MEDIUM | APPLY | §1 is procedurally unreachable (SKILL.md follows §2–§7); keep heading + Context A/B stub for xref |
| s10 | clarify.md (7 Write-Backs) | MEDIUM | APPLY | keep heading; pointer target must resolve to SKILL.md Step 3; cross-check with s3 if same pass |
| s5 | clarify.md (3 Confidence Assessment) | LOW | APPLY | keep the prescriptive-ticket-body note (observed-failure-driven) |
| s4 | clarify.md (2 Load Requirements) | LOW | APPLY | protected by regex test `load-requirements\.md\|tag-based.*loading` |

## Candidate Map — Transitive Tail (22 candidates, ~2757 weighted)

| id | file | risk | prelim verdict | note |
|---|---|---|---|---|
| s3 | fanout.md (Hybrid angle selection) | HIGH | APPLY (careful) | em-dash fuses ordering-contract (KEEP) with cut target; respect the boundary |
| s4 | fanout.md (Dispatch protocol) | HIGH | APPLY (careful) | ordering-contract adjacency; runnable copy at research/SKILL.md:184-191 confirms dedup safe |
| s2 | fanout.md (Count matrix) | MEDIUM | APPLY | keep 8-cell table byte-verbatim; **real gate = test_research_fanout_matrix.py** |
| s5 | fanout.md (Why this protocol) | LOW | APPLY | pure rationale; grid invariants pinned by test |
| s1 | fanout.md (intro) | LOW | APPLY | keep consumer-inventory fact + both `/cortex-core:*` tokens |
| s3a | pr/SKILL.md (steps 1-7) | MEDIUM | APPLY | preserve 2 stop-conditions + 4 template-path forms (control flow) |
| s3b | pr/SKILL.md (step 8, LAZY_REF) | MED-HIGH | APPLY (ADR-0009) | extract-to-reference must resolve `${CLAUDE_SKILL_DIR}` in body (SP lint); template branch never fires (no repo PR template) → low-visibility if botched |
| s3c | pr/SKILL.md (steps 9-11) | MEDIUM | APPLY | keep two-Bash `--body-file` + "no conversational output"; **stale pin: commit/SKILL.md:52 → now line 31** |
| file-compress | pr/SKILL.md (PR Body Format) | LOW | APPLY | clean duplicate of workflow step 10 |
| s6 | commit/SKILL.md (Validation) | N/A | **REFUTE — MOOT** | `## Validation` section removed in commit 8c3a00b9; file now 31 lines; nothing to trim |
| file-compress | plan-synthesizer.md (Anti-Sway/Constraints, L3-121) | **HIGH** | MIXED — decompose | **contains s15 (nested)**; keep injection-defense block L20-22 + 2 test-pinned phrases (L30/32/34); do NOT trim as one motion |
| s15 | plan-synthesizer.md (Field-by-field envelope) | MED-HIGH | APPLY iff re-anchored | keep letter-token verdict rule (A/B/C, L108) + schema fields; governs machine-parsed JSON; verify via pipeline test not grep |
| s15 | research/SKILL.md (Empty/failed agent handling) | LOW-MED | PARTIAL REFUTE | **drifted: live L199-206 vs ledger 203-211**; "duplicated in Output-structure" justification is FALSE on live file |
| file-compress | interview/loop.md (whole-file Why compression) | MED-HIGH | APPLY (exclude affordances) | keep "ask one at a time" (externally cited) + early-exit + soft-cap check-in sentences (affordances, not rationale) |
| s3 | adr/README.md (Why prose-only enforcement) | **HIGH** | **lean REFUTE/surface** | breaks live #304 citation to adr/README.md:11-17; keep verbatim CLAUDE.md prose-only sentence (only drop brittle line-number) |
| s7 | adr/README.md (Consumer-rule prose) | HIGH | APPLY (careful) | keep MUST/MUST-NOT/SHOULD names + status-keying + "Together:" synthesis; ADR-0002 example is generalization-carrying |
| s5 | adr/README.md (Frontmatter convention) | HIGH | APPLY (re-scope) | keep 4 status enum values + `superseded_by` MUST-pairing bullet; **drop mis-scoped "no-index posture" keep-item** (belongs to already-removed section) |
| s6 | adr/README.md (No-content-duplication) | MED | APPLY | genuine triplication; keep heading + project.md token + 1 bidirectional sentence |
| s2 | adr/README.md (Purpose) | LOW | APPLY | keep `cortex/adr/` token + Pocock attribution |
| s1 | adr/README.md (Title+intro) | LOW | APPLY | keep "inlines policy, nothing external to fetch" fact |
| s11 | backlog/SKILL.md (pick) | MEDIUM | APPLY | **contained by file-compress (nested)**; keep step-7 routing affordance; mirror = cortex-backlog |
| file-compress | backlog/SKILL.md (Invocation aggregate, L24-111) | HIGH | APPLY (coord w/ s11) | keep contract-lint invocation shape; hoist pick/ready error-hint as shared, don't delete from one; mirror = cortex-backlog |

## Precedent & Process

**#353 execution recipe** (the established pattern, from `cortex/lifecycle/sweep-remaining-verified-and-provisional-trim/`): sequential direct-orchestrator edits on `main` (no worktree); **one commit per file, ordered largest-saving first**, with the smallest 1–2-candidate files batched into trailing commits; after each edit `just build-plugin` then stage canonical + regenerated mirror together and commit via `/cortex-core:commit` with explicit pathspec; **two-sided verify** — keep-list token still greps present AND removed-phrase count dropped; savings tally + full `just test` once at the end as the integration gate. #353 recorded per-candidate outcomes as free-text prose in `plan.md` Status lines and never wrote to `master_candidates.json` (a human did that later, out of band).

**Reconciliation handoff must be INVENTED.** No sibling (#358/#359/#360 — all currently only `events.log` stubs) has defined an outcomes-record format; there is **no `cortex-update-candidate` script** (the ledger has been hand-edited across 3 commits). `applied_in_commit` in existing rows is the **commit subject string, not a hash** (8 rows share one identical subject). Fields a reconciliation needs per candidate (keyed by `file` + `id`): `status` (`verified_survives` applied / `verified_refuted` kept), `applied_in_commit`, `votes`/`survive_votes` bookkeeping, a `verdict_summaries[]` entry (`lens`, `survives`, `confidence`, `revised_category`, `revised_claim`, `evidence`). The polarity of `votes`/`survive_votes` for a refute should be cross-checked against the 5 existing `verified_refuted` rows before writing.

## Tradeoffs & Alternatives

**Execution granularity → one commit per file (Alt A), following #353.** Per-file maps 1:1 to a keep-list check (trivial bisect/revert); small 1–2-candidate files (`commit/SKILL.md`, `research/SKILL.md`, `interview/loop.md`) may batch into a trailing commit. Cluster-commit (Alt B) is rejected: the transitive tail is a grab-bag with no shared blast radius/mirror/revert story — one regression would force reverting six correct trims. Per-candidate (Alt C) is 42× ceremony for no revert scenario that wants sub-file granularity. Order highest-risk/largest-saving first (canary).

**Reconciliation record → per-child `verify-outcomes.json` (Alt A).** Only zero-contention option (each child owns its `cortex/lifecycle/{slug}/` dir); machine-consumable by a keyed merge; survives rebase/squash (committed artifact, not commit-history-derived); nearly isomorphic to the ledger schema. Commit-message encoding (Alt B) is fragile to parse + rebase-sensitive; direct ledger edit on a branch (Alt C) is the exact concurrent-write hazard #357 rules out. Schema (frozen, shared across all four children, keyed by `id`): `{id, file, status ∈ {verified_survives, verified_refuted}, applied_in_commit: <hash>, revised_claim/reason, evidence_pin}` — `reason` required when refuted.

**Verification rigor for hot-path files:** don't reopen the parent-set single-pass default; apply a narrow #353-style bump — **category is a better risk signal than file traffic**. Order the 9 MERGE_DEDUP + 1 LAZY_REF candidates early (canary) and, for those, read the actual fold/pointer target before applying (confirm the surviving copy carries every pinned token; confirm a LAZY_REF pointer resolves) — within the same single pass, not a second agent.

## Adversarial Review — findings that change the spec

1. **Cumulative line-shift blows the kept-pauses parity tolerance in `refine/SKILL.md`.** `LINE_TOLERANCE = 35`; inventory anchors `:166`; the §4-gate `AskUserQuestion` is already at live line 159 (7 above → 28 lines of budget left). Five candidates (s3, s6, s7, s8, s10a) trim ~75 combined lines **above** line 159; a typical ~40% compression removes ~30 lines, pushing the site to ~129 → `|166−129| = 37 > 35` → **parity test FAILS**. Each candidate individually shifts <35 (invisible to per-candidate single-pass verification); together they exceed it. **Mitigation:** either cap cumulative above-159 removal at <28 lines OR bump `kept-pauses.md:166` in the same `refine/SKILL.md` commit (this child does not own kept-pauses.md — coordination step), and run the parity test per-file, not only at end.
2. **`mech_pins` are vacuous keyword-cooccurrence noise, not curated references.** Verification must rest on the human `pins[]` field + named test greps; treat mech_pin token-resolution as advisory-only (it is vacuous for enum-value / slash-command tokens).
3. **`adr/README.md` = biggest single risk concentration** (least-gated: no trigger, no mirror, no prose test; highest fan-out: 16+ back-pointers). Treat all 6 candidates HIGH. **s3 should REFUTE-or-surface**, not auto-apply: it breaks live ticket **#304**'s citation to `adr/README.md:11-17` and drops the `CLAUDE.md:58` anchor grounding the prose-only posture (pure What/Why prose). s7 and s5 trim generalization-carrying example/contract prose — careful.
4. **plan-synthesizer:** the `## Untrusted Variant Data` block (L20-22) is an **active prompt-injection defense** mischaracterized as "inert meta" — keep verbatim. The letter-token verdict rule (L108) governs machine-parsed JSON no test exercises end-to-end (canned envelopes only). Edit file-compress + s15 as **one coordinated edit** (nested spans). Same for `backlog/SKILL.md` file-compress ⊃ s11.
5. **Reconciliation:** record the actual commit **hash** in `applied_in_commit` (not the non-unique subject string) so the deferred reconciliation can validate the trim is still present on `main` and detect a revert-divergence. During the deferral window the ledger still shows these `unverified` — the `verify-outcomes.json` is the *sole* record of a refute; losing/malforming it re-opens an already-refuted candidate (e.g. the moot commit/SKILL.md s6).
6. **Two same-file spans owned by OTHER tickets must be left untouched** even though this child edits their files: `clarify.md` s9 (`overlaps_ticket: #340`, `### 6 Research Sufficiency Criteria`) and `clarify-critic.md` s3 (`overlaps_ticket: #186`). A naive grep-the-file pass steps on them. This child's trims will shift their (un-applied, deferred) ledger line anchors — tolerable only because location is by heading+token.
7. **Process:** the pre-commit hook does NOT run `just test` (only drift + lint), and `adr/README.md` trims get no gate at all. Run `just test` after each risky file commit (at minimum after `refine/SKILL.md`, `plan-synthesizer.md`, and the full `refine/references/` set), not only once at the very end.

## Open Questions

- **Reconciliation-record format (provisionally resolved — user to confirm at Spec §4).** Deferred: the working design is a per-child `cortex/lifecycle/sweep-provisional-tail-refine-cluster-transitive/verify-outcomes.json` keyed by candidate `id`, carrying `{file, status, applied_in_commit: <hash>, revised_claim/reason, evidence_pin}`, isomorphic to the `master_candidates.json` fields the #357 reconciliation folds in. This is Tradeoffs' Alt A and the Precedent-agent's schema recommendation. It must be **invented by this child** (no sibling convention exists) and ideally frozen as the shared shape for all four #357 children. The user was asked during Clarify but was away; this will be re-surfaced on the Spec approval surface for confirmation. Resolution requires a user preference call, not further code investigation.
- **kept-pauses.md:166 anchor bump vs. trim-budget cap** — resolvable at implementation time by measuring the actual cumulative line delta above `refine/SKILL.md:159` after the refine-cluster trims are drafted; both mitigations (bump the anchor in-commit, or cap the trim) are viable and the choice is a mechanical measurement, not a design question. Deferred to Plan/implement with the constraint recorded as a hard acceptance gate (parity test green).

## Considerations Addressed

_None — no `research-considerations-file` was supplied (parent #357 is `type: chore`, so the clarify-critic ran with no Parent Epic Alignment sub-rubric; there were zero `origin: "alignment"` findings to propagate)._
