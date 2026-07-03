# Research: Sweep provisional tail — critical-review cluster (#360)

Trim the 26 unverified provisional trim candidates under `skills/critical-review/` (SKILL.md + 6 reference files), each gated by single-pass pin-hit verification, plus complete the `cortex-resolve-model` failure-cause parity trim in `critical-review/SKILL.md`. Child batch of #357's provisional-tail decomposition; sibling of #358/#359/#361; predecessor #353 (complete).

Research was run at complex/high fan-out (8 agents: Codebase, Web, Requirements, Pin-Verification, Synthesizer-Parsing, Handoff, Mirror, Adversarial). The headline result: **the 26-candidate scoping and hard-constraint inventory are accurate, but two candidates in verification-gates.md are prior-adjudicated landmines that single-pass pin-hit cannot safely clear, and one of them sits on a factual error that proves the verification method is blind to prose correctness.**

## Codebase Analysis

**The 26-candidate work-list** (filter: `file` under `skills/critical-review/`, `status: unverified`, no `overlaps_ticket`, no `reproposal_of`). All headings were located by text; none stale, none missing.

| id | file | heading | tok | pins? |
|----|------|---------|-----|-------|
| s5 | SKILL.md | ### Step 2a: Load Domain Context | 337 | no |
| s6 | SKILL.md | blockquote "Requirements loading: deliberately exempt" | 193 | yes (test_load_requirements_protocol.py:134) |
| s3 | SKILL.md | ## Contents (TOC) | 59 | **none** |
| s8 | SKILL.md | ### Step 2b: Derive Angles | 148 | **none** |
| s9 | SKILL.md | ### Step 2c: Dispatch Parallel Reviewers | 214 | yes (READ_OK literal) |
| s12 | SKILL.md | ### Step 2d: Opus Synthesis | 499 | yes (SYNTH_READ_OK, placeholder counts) |
| s14 | SKILL.md | ### Step 2e: Residue Write | 172 | mech_pins only |
| s16 | SKILL.md | ## Step 4: Apply Feedback | 339 | **none** |
| s2 | verification-gates.md | ## Step 2a.5: Pre-Dispatch | 336 | yes (exit-2 literal in span) |
| s3 | verification-gates.md | ## Step 2c.5: Sentinel-First Gate (intro) | 118 | yes (Step 2c.5 designator) |
| s2 | residue-write.md | ## Feature Resolution | 236 | yes |
| s3 | residue-write.md | ## Atomic Write | 98 | yes |
| s1–s5,s7 | angle-menu.md | intro + example sections | ~380 | mirror-parity pins |
| s1,s3,s5,s8 | synthesizer-prompt.md | header / Artifact / Instructions / Output Format | ~783 | yes (sentinels, reclassify note) |
| file-compress | fallback-reviewer-prompt.md | preamble + closing note only | 145 | yes |
| s1,s8,file-compress | reviewer-prompt.md | header / Instructions / intra-file dedup | ~271 | yes |

Note candidate IDs are **per-file** — there are two distinct "s3" candidates (SKILL.md Contents-TOC vs verification-gates.md Step 2c.5 intro) and two "s2"s. Always disambiguate by file.

**Count reconciliation** (two agents initially reported 29): `skills/critical-review/*` has 38 `unverified` rows → minus 9 `overlaps_ticket:#300` → 29 → minus 3 `reproposal_of` (s6a/s4a/s6b, **all in verification-gates.md**) = **26**. The 3 reproposal_of rows re-litigate #300 refutations and are excluded from #360 but sit inside a file this batch edits.

**Parity trim target — concretely pinned.** SKILL.md:76 currently reads `"...halt and escalate rather than guessing or substituting a model"` prefixed with the gloss **`(the verb is absent or broken)`**. The parity reference set already dropped that gloss: `review.md:22`, `orchestrator-review.md:45`, `competing-plans.md:16` all read the bare form (review.md adds "to the user"; the other two omit it — parity is only ~2/3 uniform among siblings). `implement.md:165` carries a *different* two-cause enumeration (its model resolution genuinely reads `cortex-lifecycle-state` criticality; critical-review's explicitly does not) — genuinely divergent, owned by #348, out of scope. The gloss is **not** test-pinned.

**Mirror**: canonical `skills/critical-review/**` + mirror `plugins/cortex-core/skills/critical-review/**`, byte-identical now. Edit canonical only; `just build-plugin` (rsync) regenerates the mirror; commit both together.

## Web Research

No direct prior art for "pin-hit verification of prose trims" (the term collides with certificate PIN-pinning). Closest real analogs: golden-file/snapshot testing with `contains` substring assertions (promptfoo), and consumer-driven contract testing (Pact) applied by analogy to prompt→parser coupling. **Load-bearing takeaway: substring/pin assertions prove the anchor *survived*, not that the surrounding prose still carries equivalent meaning — a trim can pass pin-hit while degrading behavior.** Anthropic's own skill-authoring guidance favors **empirical (run-and-observe) verification over static string checks** — a philosophical tension with a purely pin-hit-gated process. The "Format Tax" line of work suggests even whitespace/structure changes a "safe" trim introduces can measurably affect downstream structured-output reliability. This directly motivates upgrading verification for behaviorally-load-bearing candidates (see Adversarial, s12).

## Requirements & Constraints

**Authorizing**: project.md "Maintainability through simplicity: iteratively trimming skills/workflows"; Optional → "Workflow trimming". A scoped phase of a multi-phase lifecycle is not a stop-gap (Solution horizon).

**Hard content pins** (`tests/test_critical_review_reference_pins.py` — cannot be removed): the total-failure literal `"All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source."` (in BOTH SKILL.md and verification-gates.md); the Step designators `## Step 2a.5:`, `## Step 2c.5:`, `## Step 2d.5:` verbatim (4 SKILL.md pointers depend on them); the exit-2 reaction `"surface its stderr verbatim to the user and stop"`; per-section `- **Exit 0/3/4**` markers. The tempfile-guard paragraph, write-guard prose, exit-4 rationale, and Phase-2 split instruction are **NOT** pinned — a cut into them stays grep-green.

**Ratchet/size**: SKILL.md size cap 500 lines (currently 115 — safe). **L1 surface ratchet: critical-review frontmatter at 795B against a 795 budget — ZERO headroom.** Equal-or-lower passes, so body trims are safe, but **do not touch the frontmatter** (description/when_to_use) on any candidate.

**Other gates that react to skill edits** (pre-commit): `cortex-check-parity`, `cortex-check-contract` (note `bin/.contract-lint-exceptions.md:32` already carries an intentional-omission exception for critical-review/SKILL.md — preserve or re-justify), `cortex-check-events-registry`, `cortex-check-skill-path`, `cortex-check-bare-python-import`, the dual-source drift loop, and `test_plugin_mirror_parity.py` / `test_dual_source_reference_parity.py`. Additional critical-review test family to run near dispatch/sentinel/classifier logic: `test_critical_review_sentinel_window.py`, `test_dispatch_template_placeholders.py`, `test_critical_review_classifier.py`.

**Blast radius**: critical-review is invoked/gated by `skills/lifecycle/SKILL.md:153` and lifecycle references (auto-triggers for Complex + medium/high/critical before spec/plan approval) — an over-trim has lifecycle-wide impact, grounding the high criticality.

**Governance**: CLAUDE.md "identify the user-facing affordance a boundary protects before classifying it ceremonial"; "prescribe What and Why, not How" (trim *How* narration, preserve decision criteria and *Why*); MUST-escalation policy governs *adding* MUST language (carry "no new MUST" as an acceptance check). Commit only via `/cortex-core:commit`.

## Pin-Verification Methodology

**`pins`** = a named automated test asserting a literal substring exists verbatim. Check: read the constant/line in the named test, grep it before/after the trim, then **run the pinned pytest** (ground truth — some pins assert positional/section slicing, not flat containment).

**`mech_pins`** = cross-site grep hits (`` `TOKEN`->path ``), no enforcement. Check: confirm TOKEN falls inside the trimmed span; confirm each listed site is still live; classify pointer (safe if TOKEN survives anywhere) vs independent copy (dup-group drift risk).

**Keep-list — resolved.** No `keep*` field exists in the JSON; the ticket language is shorthand. The referent is the prose inside `claim` (pre-verify) and `verdict_summaries[].revised_claim` (post-verify), evidenced by #353's `research.md:43` ("Keep-lists are load-bearing. Each revised_claim names exactly what to keep verbatim") and `spec.md:3`. **For all 26 critical-review rows `verdict_summaries` is empty — there is no pre-authored keep-list.** The verifying agent constructs it during the pass from (1) keep-language already in `claim`, (2) every `pins` literal (mandatory), (3) every `mech_pins` token inside the span, and records it in the verdict.

**No-pin fallback (s3-TOC / s8 / s16)** — mirror #353 rigor: extract every literal the span defines; fresh repo-wide grep across `skills/ tests/ cortex/ docs/ cortex_command/` **and the mirror** (not reliance on the audit's stale mech_pins absence); for s3-TOC diff the TOC entries against actual `^#` headings; for s8 content-diff the retained `angle-menu.md` copy for semantic equivalence; run the pin-test family + full suite post-trim as ground truth; record the negative result in the verdict.

**#353 procedure to mirror**: locate by heading+token (never stored line numbers); two-sided verification (keep-token still greps present **AND** removed-phrase count dropped / file net-shrinks); grep (fast pre-check) + pinned pytest (ground truth); one commit per file with the regenerated mirror staged together; an integration gate before Review that re-runs the suite and re-greps every applied keep-list token; **isolate the highest-coupling candidates (prompt templates) and verify them first**.

## Synthesizer-Parsing & Template Coupling

Two parse regimes: **code-hard** regexes `_REVIEWER_OK_RE`/`_REVIEWER_FAILED_RE`/`_SYNTH_RE` (READ_OK / READ_FAILED / SYNTH_READ_OK sentinels) in `cortex_command/critical_review/__init__.py` (tested by `test_critical_review_sentinel_window.py`); and **LLM-soft** — the `<!--findings-json-->` envelope extraction is performed by the **orchestrator LLM** per prose instruction, **not backed by any Python function** (grepped the package; no `parse_findings_envelope` exists). So "the synthesizer's parsing" is two soft hops with no machine schema enforcement at either.

**Dispatch multipliers**: `reviewer-prompt.md` body renders **3–4× per run** (biggest per-token leverage); `synthesizer-prompt.md` 1× (Opus); `fallback-reviewer-prompt.md` 1× (total-failure path only); `angle-menu.md` / `residue-write.md` / `verification-gates.md` are **never dispatched** — orchestrator-only, 1×.

**Highest-care candidates**: `reviewer-prompt.md` JSON-envelope field names/delimiter (feed the soft Phase-2 schema assertion); `synthesizer-prompt.md` s5 reclassify-note format (pinned by a live regex in `test_critical_review_classifier.py`); s8 four section headers. The prior adversarial lifecycle **deliberately excluded** reviewer/synthesizer/fallback-reviewer prompts from its scope ("cannot be pointer-replaced — a fresh subagent cannot resolve a skill-dir path"). #360 includes them — its highest-coupling, highest-multiplier territory.

**dup_groups**: fallback-reviewer ↔ synthesizer (~86 tok, the Output Format block) and fallback-reviewer ↔ reviewer (~45 tok, the READ_FAILED sentinel line) are both **deliberate** cross-path alignments, not incidental. **Literal single-sourcing is unsafe** — all three files render verbatim into separately-dispatched agents that cannot resolve `${CLAUDE_SKILL_DIR}` pointers. A fragment inlined by the SKILL.md body (like `{a_to_b_rubric}`) is possible but marginal ROI at 45–86 tokens — **defer** (dedup-in-place at most).

## Handoff & Reconciliation

master_candidates.json is hand-edited (no script reads/writes it). It carries a live `status` enum — **96 rows already `verified_survives`, 5 `verified_refuted`** — so verdict write-back is an existing, working mechanism. #353's `applied_in_commit` provenance is the part that went unfilled (a free-text placeholder on only 8/265 rows; the 14 real trim commits never touched the ledger). Neither #357 nor any sibling defines a handoff *format*; #357 designates the mechanism as "the single reconciliation pass that folds every child's verify outcomes back into master_candidates.json" with touch-points `master_candidates.json` + `dup_groups.json` only. The Adversarial angle overturns the initial "new reconcile/ dir" proposal — see below.

## Adversarial Review

**Method blind spot, proven.** Candidate **s3 (verification-gates.md, Step 2c.5, line 33)** correctly flags that line 33 names `check-synth-stable` as the "canonical SHA computation path" — but `prepare_dispatch()` computes the SHA (`__init__.py:335,339`); `check_synth_stable()` takes `expected_sha` as an arg and only *compares* (`:349-385`). **Line 33 is factually wrong, and it is the applied, refuter-certified residue of the prior lifecycle's P5 downgrade.** A two-pass adversarial process certified a factual error as minimum-safe. s3's pins are only the `## Step 2c.5:` heading and the `SKILL.md:72` pointer — grep passes whether the surviving prose names the right subcommand, the wrong one, or none. **Single-pass pin-hit is orthogonal to prose correctness.**

**Prior-verdict landmines** (verdicts live in `cortex/lifecycle/adversarially-verified-trim-of-critical-review/{research.md,trim-map.md}`, NOT in the JSON `verdict_summaries` field):
- **s2 (verification-gates.md, Step 2a.5)** — prior research **lean-refuted this exact cut** (research.md:128, 174c: the `--feature` restatement is a cross-reference, orphan risk). Its declared span (lines 9–28) also over-reaches its claim: cutting line 18 wholesale removes the load-bearing routing rule *"Pass `--feature <name>` only on auto-trigger flows… the `<path>`-arg form omits `--feature`"* that lines 49 and 80 back-reference. This is **not** residue-write.md's territory (that owns the resolver, not the when-to-pass rule).
- **s3 (verification-gates.md)** — re-cuts P5's refuter-certified residue and embeds the factual error above.
- Both live inside the prior research's named "dangerous zone" (exit-3/4 route prose, markdown-only and untested).

**Excluded-span adjacency**: the 3 excluded `reproposal_of` rows target write-guard prose (lines 49/80) and exit-4 rationales (55/86) — the same two sections as in-scope s3. The `- **Exit 4**` markers are pinned per-section, but the write-guard/tempfile-guard prose is not, so an over-cut into lines 37/49 stays grep-green. Prose-only "exclusion discipline" is the pattern CLAUDE.md says to avoid for sequential gates → recommend a **diff-hunk line-range lock**: the verification-gates.md diff may touch only lines 17-18 and 31-33; auto-reject any hunk overlapping 37/49/55/80/86.

**s3 (SKILL.md Contents-TOC)** — grep-green but **reverses spec-approved #178 R1** (commit `87251441` added the TOC). Deletion is defensible on merits (a TOC in an always-fully-loaded file has no navigation value) but that judgment is not what pin-hit performs — tag the verdict "reverses #178 R1" for human confirmation, don't silent-pass.

**s12 (SKILL.md line 78)** — line 78 is the only statement of the rubric's "8 worked examples (4 ratify / 4 downgrade across absent/restates/adjacent/vague)" trigger structure, which prior research flagged as must-gate-on-behavioral-eval. Trimming it degrades the reader's model of the rubric even though the `SYNTH_READ_OK` literal survives → **run-and-observe candidate, not a grep candidate.**

**Keep-list conflict of interest**: #360's keep-list is constructed by the same agent proposing the trim, with no fresh refuter (unlike #353's separately-authored verdict_summaries). Mitigation: for any candidate whose span overlaps a prior lifecycle's adjudicated span, **seed the keep-list from the prior `verifier_reason`/`downgrade_to`**, not a fresh same-agent reconstruction.

**Handoff-ledger complexity challenge (overturns the Handoff angle's proposal)**: a new `cortex/research/skill-value-scorecard/reconcile/` dir **fails complexity-earns-its-place** — it duplicates the `status` enum 101 rows already use (two sources of truth for the same verdict), and #357 designates master_candidates.json as the fold-in target with no reconcile/ dir in its touch-points. Correct staging: record verdicts as `verified_survives`/`verified_refuted` + the trim-commit SHA in **the child lifecycle's own artifacts** (spec.md verdict block or events.log) — which the umbrella close already opens per child — and require the umbrella pass to fill `applied_in_commit` (the field #353 dropped). No new dir, no new consumer to teach.

**Parity nuance**: harmonizing SKILL.md *down* to the bare form achieves only partial parity (siblings themselves disagree on "to the user"). The gloss `(the verb is absent or broken)` is a genuine *Why* clause; per "prescribe What and Why, not How," harmonizing *up* (keep/propagate the gloss) is a legitimate alternative to trimming it. A real judgment call.

## Open Questions

1. **s2 and s3 (verification-gates.md) disposition — Deferred: resolved in Spec, and re-adjudicated by the Step-5 critical-review gate.** Both overlap prior-adjudicated spans that single-pass pin-hit cannot safely clear. Because #360 is Complex + high criticality, refine's Spec phase auto-triggers `/cortex-core:critical-review` before approval — that IS the fresh-refuter pass the adversarial angle recommends. Candidate resolutions to weigh there: (a) auto-refute both (record refuted, do not re-propose); (b) convert s3 to a **correctness fix** (`check-synth-stable`→`prepare-dispatch`) recorded as a correction, not a trim; (c) drop s2 as lean-refuted + span-overreaching. Default lean: refute s2, correctness-fix-or-refute s3.
2. **s3 (SKILL.md Contents-TOC) — Deferred: resolved in Spec with the user.** Delete (reversing approved #178 R1, with an explicit "reverses #178 R1" verdict note) vs keep. The deletion is defensible but reverses a prior spec decision, so it warrants explicit human sign-off at the approval surface.
3. **s12 verification bar — Deferred: resolved in Spec.** Whether the batch upgrades s12 (SKILL.md line 78) to run-and-observe/behavioral verification, defers it, or narrows its trim to avoid the trigger-structure enumeration. Interacts with the general method-sufficiency finding (pin-hit ≠ behavioral equivalence).
4. **Parity direction — Deferred: resolved in Spec.** Harmonize SKILL.md:76 *down* (trim the gloss to match siblings) vs *up* (retain the `(the verb is absent or broken)` Why-clause per the What/Why principle; optionally propagate to siblings). Low-stakes, not test-pinned.
5. **Handoff record location — Resolved.** Record per-candidate verdicts (`verified_survives`/`verified_refuted` + evidence + trim-commit SHA) in the child lifecycle's own artifacts using the existing status enum; the #357 umbrella close folds them into master_candidates.json and fills `applied_in_commit`. Do **not** create a new `reconcile/` dir.
6. **In-file exclusion enforcement — Resolved.** Scope-lock the verification-gates.md diff to lines 17-18 and 31-33 (structural line-range assertion), not prose-only discipline; the 3 `reproposal_of` spans (s6a/s4a/s6b) and the unpinned guard prose (37/49/55/80/86) stay untouched.
7. **dup_groups single-sourcing — Resolved.** Defer; literal extraction is unsafe (verbatim-into-separately-dispatched-agents), and a body-inlined fragment is marginal ROI at 45–86 tokens.
