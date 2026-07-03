# Verify outcomes — #361 provisional-tail sweep (refine cluster + transitive tail)

Per-child `(file, id)`-keyed verdict record for the 42 filtered provisional-tail
candidates (spec Req 12; sibling-#358 convention). One row per **composite `(file, id)`** —
the ledger `id` alone is non-unique (42 rows carry 23 distinct ids; e.g. `s3`×5,
`file-compress`×4), so an `id`-keyed record would silently overwrite ~19 rows. This file
is the `(file,id)`-keyed delta the deferred #357 reconciliation folds into
`master_candidates.json` — this child does **not** write the ledger (spec Non-Requirements).

**Assembly**: 41 rows extracted from the fenced ```verify-outcomes``` block in the **raw**
body of each of the 11 trim commits (`git show -s --format=%B <hash>`), plus 1 row
(`skills/commit/SKILL.md` s6) authored directly (no commit — moot per Req 8). Each
`verified_survives` row's `applied_in_commit` is its file's trim-commit hash; each
`verified_refuted` row carries `—` (a refuted candidate produces no diff, so no provenance).

**Normalizations applied during assembly** (the raw blocks are slightly inconsistent):
1. Commit `6b3766e2`'s 8 rows keyed the file as the short form `refine/SKILL.md`; rewritten
   to the full ledger path `skills/refine/SKILL.md` to match `master_candidates.json`.
2. Commit `2cdbdb8f`'s row used verdict token `applied`; normalized to `verified_survives`.
3. Every `verified_refuted` row's `applied_in_commit` is `—` (even when the refute was
   recorded in a commit body that also carried applied rows).

**Tally**: 42 rows = 38 `verified_survives` + 4 `verified_refuted` + 0 `deferred`.
Refuted: `specify.md` s6 (Req-4 decision-criteria at floor), `clarify.md` s5 (Req-4
confidence-rubric gating a user pause), `adr/README.md` s3 (Req 7 — #304 cites
`README.md:11-17`), `commit/SKILL.md` s6 (Req 8 — section removed in `8c3a00b9`).

**Row schema** (6 ` | `-delimited fields, one row per line — pipe-delimited rather than a
markdown table because the `signal`/`reason` prose contains commas, colons, and regex pipes
that would break table cells):

    (file, id) | verdict | applied_in_commit | signal | anchor | reason

- `verdict` ∈ {`verified_survives`, `verified_refuted`, `deferred`}
- `applied_in_commit` = 40-hex trim-commit hash for survivors; `—` for refuted
- `signal` names its Req 3 type — (a) structural-substitution, (b) informative-only,
  (c) preserved-elsewhere — plus the enforcing/surviving location for (a)/(c)
- `anchor` = Req 2 `## Heading::pinned-token` (never a ledger line number)

---

## skills/refine/SKILL.md

(skills/refine/SKILL.md, s3) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:b:Step1-heading | anchor:## Step 1: Resolve Input::cortex-resolve-backlog-item | reason:dropped $ARGUMENTS-restatement gloss (empty-prompt directive survives at line 21 "Topic: $ARGUMENTS ... If empty, prompt user"); JSON result-handling arms kept
(skills/refine/SKILL.md, s6) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:b:Sufficiency-Check-Path-guard | anchor:### Sufficiency Check::Path guard | reason:folded 3-item numbered path guard into one prose paragraph; discovery_source/research-never-a-substitute guard + exact-path rule + run-Research-Execution all preserved
(skills/refine/SKILL.md, s7) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:a:tests/test_refine_handoff.py | anchor:### Alignment-Considerations Propagation::research-considerations-file | reason:cut ADR-0022 pointer sentence (design recorded in ADR-0022); write/overwrite/coupled-arg/ordering tokens asserted by test_refine_handoff.py all survive
(skills/refine/SKILL.md, s8) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:b:Research-Execution-verify-line | anchor:### Research Execution::/cortex-core:research topic= | reason:cut redundant "writes its output to research.md" line (path restated by the immediately-following verify-non-empty and register lines); dispatch args unchanged
(skills/refine/SKILL.md, s10a) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:c:Step2-lines-60-62 | anchor:## Step 5: Spec Phase::reconcile-clarify --backend {resolved} | reason:MERGE_DEDUP of --backend guard restatement (survives at Step 2 "guard owns the non-local slug-drop (ADR-0019)") and seed-reconcile-gate invariant (survives at Step 2 "Seed->reconcile->gate ordering invariant"); exact Context A/B invocation strings unchanged
(skills/refine/SKILL.md, s10c) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:b:test_refine_skill.py | anchor:§4 (User Approval) — Complexity/value gate::AskUserQuestion | reason:single-line in-place compression; firing criteria, recommendation-first "I recommend X because Y", (Recommended) suffix, Confirm current scope (Recommended), no "MUST decide" all preserved; AskUserQuestion stays one line
(skills/refine/SKILL.md, s12) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:b:Step6-Completion | anchor:## Step 6: Completion::/cortex-core:refine is complete | reason:folded 5-bullet completion checklist into one summary sentence; all fields retained inline, announcement-only prose
(skills/refine/SKILL.md, s13) | verified_survives | 6b3766e207daaf39c77b8adb04896c104f18373d | signal:c:in-file | anchor:## Constraints::Thought | reason:MERGE_DEDUP dropped 3 of 4 Thought/Reality rows duplicating inline prose (row1 stops-at-spec survives at when_to_use line 4 + line 19; row2 set-only-after-approval survives at "Do NOT set status: refined before user approval"; row4 fail-surface survives at "surface the error and wait" + "Handle failures as in Step 3"); kept unique backlog-filename-slug row

## skills/refine/references/specify.md

(skills/refine/references/specify.md, s3) | verified_survives | e835c11e07c0d036be3f5e627249a8013cb95aef | signal:b:formatting-only — bullet markers carry no shall/must/weighting; must-have/measurable/user-facing concepts survive inline verbatim | anchor:### 2. Structured Interview::Probe for | reason: folded three frontier-derivable probe sub-bullets into inline prose; six area names, ADR-posture cross-ref, and gap-fill AskUserQuestion pause (kept-pauses.md:15) preserved
(skills/refine/references/specify.md, s5a) | verified_survives | e835c11e07c0d036be3f5e627249a8013cb95aef | signal:b:formatting+dedup-crossref — removed bullet structure and '(same override described below)' pointer only | anchor:### 2a. Research Confidence Check::Missing research.md guard | reason: collapsed two-bullet missing-research guard to one sentence; event payload, announce, /refine Sufficiency-Check bypass, and do-not-evaluate-C1/C2/C3 all retained
(skills/refine/references/specify.md, s6) | verified_refuted | — | signal:none | anchor:### 2b. Pre-Write Checks::Verification check | reason: four sub-checks (Git command syntax/Function behavior/File paths/State ownership) are Req-4 decision-criteria kept enumerable; section already at trim floor per pinned commit d4cd8949; no clean worked-example-only cut — no edit applied
(skills/refine/references/specify.md, s7a) | verified_survives | e835c11e07c0d036be3f5e627249a8013cb95aef | signal:b:output-template — removed verbatim advisory-callout markdown, an output example carrying no behavioral determinant | anchor:### 3. Write Specification Artifact::declining to loop back | reason: replaced 3-line callout template with one-sentence instruction; declined-event trigger, prepend-before-Problem-Statement placement, and per-signal bullet retained; no test pins the callout text
(skills/refine/references/specify.md, s9) | verified_survives | e835c11e07c0d036be3f5e627249a8013cb95aef | signal:c:skills/lifecycle/references/critical-review-gate.md Non-Local Seed-Tier Rule (lines 11-13) | anchor:### 3b. Critical Review::Non-local seed-tier fail-safe | reason: deduped fail-safe rationale (seed-untrustworthy reasoning + local-path exemption) to gate ref; operative trigger backend != cortex-backlog AND tier=simple AND research.md exists -> run critical-review, plus cortex-read-backlog-backend read-before-handoff ordering, preserved

## skills/refine/references/clarify.md

(skills/refine/references/clarify.md, s3) | verified_survives | cc8e8aeb5888e86a8961655d20febbc4e20774fe | signal:c:refine/SKILL.md Step 1 (cortex-resolve-backlog-item invocation + exit-code branching) | anchor:### 1. Resolve Input::cortex-resolve-backlog-item | reason:MERGE_DEDUP — resolver invocation + exit 0/2/64/70 branching duplicated at SKILL.md Step 1 (resolution already done before clarify.md is read at Step 3); collapsed to Context A/B stub. Clarify-unique Context-B backlog-creation offer preserved (not duplicated in SKILL.md, Req 4 affordance).
(skills/refine/references/clarify.md, s4) | verified_survives | cc8e8aeb5888e86a8961655d20febbc4e20774fe | signal:a:tests/test_load_requirements_protocol.py CONSUMER_REFS + cortex-load-requirements verb | anchor:### 2. Load Requirements Context::cortex-load-requirements | reason:COMPRESS — protocol details enforced by the verb/test; kept cortex-load-requirements invocation + path-injection/fallback contract + citation match (/load-requirements.md|tag-based.*loading/ still ==1).
(skills/refine/references/clarify.md, s5) | verified_refuted | — | signal:none | anchor:### 3. Confidence Assessment::High confidence | reason:REFUTE — the High/Low gloss cells are the decision-criteria rubric for the confidence rating that gates the §4 question-threshold AskUserQuestion user pause; per Req 4 a decision-criteria/user-affordance span cannot be classified signal-(b) informative-only. No edit; §3 table left intact.
(skills/refine/references/clarify.md, s8) | verified_survives | cc8e8aeb5888e86a8961655d20febbc4e20774fe | signal:b:§5 item 4 four requirements-alignment-note template strings are format examples (rationale/example only) | anchor:### 5. Produce Clarify Output::Requirements alignment note | reason:COMPRESS — replaced the four verbatim template strings with a one-line rule; preserved the on-conflict resolve-with-user gate. KEPT (Req 4): §5 'do not ask the user to confirm' (grep==1) + 'appropriate default for most skill' (grep==1) + tier/criticality definitions untouched.
(skills/refine/references/clarify.md, s10) | verified_survives | cc8e8aeb5888e86a8961655d20febbc4e20774fe | signal:c:refine/SKILL.md Step 3 write-back block (canonical copy; SKILL.md shape pinned by tests/test_refine_reconcile_clarify.py) | anchor:### 7. Write-Backs::cortex-update-item | reason:MERGE_DEDUP — §7 body fully duplicated by SKILL.md Step 3; replaced with a one-line pointer to that canonical block.

## skills/refine/references/clarify-critic.md

(skills/refine/references/clarify-critic.md, s7) | verified_survives | 81ff11bd9c69df465e6fa1668fc6f92a86dbfff1 | signal:c:skills/critical-review/SKILL.md Step 4 (classification/self-resolution/anchor-check) | anchor:## Disposition Framework::keep the two in sync | reason:generic Apply/Dismiss/Ask + self-resolution + anchor-check machinery is self-declared reproduced-from critical-review Step 4 (terse post-#307); compressed to a pointer, all clarify-critic deltas (confidence-dimension revision, S4 Q&A routing, clarify-S2 context, Ask-to-Q&A merge, tie-break weighting, Ask (c) criterion) preserved; sync note + disposition names consumed by refine/SKILL.md retained
(skills/refine/references/clarify-critic.md, s12b) | verified_survives | 81ff11bd9c69df465e6fa1668fc6f92a86dbfff1 | signal:c:skills/refine/references/clarify-critic.md ## Input Contract + ## Parent Epic Loading + ### Dispositioning Output Contract/## Event Logging | anchor:## Constraints::Soft rubric-dimension cap | reason:Thought/Reality rows restate surviving text - Row1=Input Contract (does not read any other files)+Parent Epic Loading; Row2=Dispositioning Output Contract (disposition counts only)+Event Logging (intentionally not preserved); table removed, unique soft <=5 rubric-dimension cap kept

## cortex/adr/README.md

(cortex/adr/README.md, s1) | verified_survives | 6ce492fdf73dbfaaf16ac4c9af0c91dabd4f2d1e | signal:b:cortex/README.md:39 file-level pointer only; removed generic ADR definition + "inlined" meta restated at README.md:9 | anchor:# Architecture Decision Records (ADRs)::This directory holds | reason:cut what-an-ADR-is definition + inlined meta-sentence; no normative token in removed span
(cortex/adr/README.md, s2) | verified_survives | 6ce492fdf73dbfaaf16ac4c9af0c91dabd4f2d1e | signal:c:## Three-criteria emission gate (L19-27 carries all three criteria) | anchor:## Purpose::The purpose of `cortex/adr/` | reason:deduped bolded three-criteria preview; full gate section 12 lines below is canonical
(cortex/adr/README.md, s3) | verified_refuted | — | signal:none | anchor:## Purpose::Why prose-only enforcement | reason:#304 cites README.md:11-17 (backlog line 42) — refuted by default; span left byte-unchanged, CLAUDE.md prose-only sentence preserved verbatim (L11)
(cortex/adr/README.md, s5) | verified_survives | 6ce492fdf73dbfaaf16ac4c9af0c91dabd4f2d1e | signal:c:## Frontmatter convention Promotion gate (L47 carries promote-at-merge rule) | anchor:## Frontmatter convention::New ADRs land as `proposed` | reason:removed double statement of promote-at-merge; rule preserved at Promotion gate; **must** superseded_by clause untouched
(cortex/adr/README.md, s6) | verified_survives | 6ce492fdf73dbfaaf16ac4c9af0c91dabd4f2d1e | signal:b:back-pointer rule stated 3x; opening para + bidirectional sentence retained; rule name cited by project.md:40 | anchor:## No-content-duplication discipline rule::The discipline runs in both directions | reason:collapsed 2 bullets + reason into one bidirectional sentence; **must not** normative + heading preserved
(cortex/adr/README.md, s7) | verified_survives | 6ce492fdf73dbfaaf16ac4c9af0c91dabd4f2d1e | signal:b:deleted "Together:" restatement + informative tails of MUST NOT/SHOULD; MUST/MUST NOT/SHOULD names kept per project.md:40 | anchor:## Consumer-rule prose::three behavioral categories | reason:MUST automatic bullet tail retained (illustrative example carries a must-not token, failing signal-b purity bar); only clean tails trimmed

## skills/research/references/fanout.md

(skills/research/references/fanout.md, s1) | verified_survives | 165e8497e214ccf94be810e98210184e3bf96bc6 | signal:c:research/SKILL.md:49 + discovery/references/research.md:41 | anchor:intro::single source | reason:consumer inventory restated at both entry points; kept canonical-source + no-drift statement, dropped restated consumer enumeration
(skills/research/references/fanout.md, s2) | verified_survives | 165e8497e214ccf94be810e98210184e3bf96bc6 | signal:a:tests/test_research_fanout_matrix.py floor3/corner10/monotone/cap | anchor:## Count matrix::upper bound on investigation breadth, not a quota | reason:8-cell table kept byte-verbatim + one copy of upper-bound rule; dropped how-to-read + monotone/strict-peak narration enforced by test
(skills/research/references/fanout.md, s3) | verified_survives | 165e8497e214ccf94be810e98210184e3bf96bc6 | signal:a:cortex/adr/0023 ## Decision always-last adversarial wave | anchor:## Hybrid angle selection::always present for high and critical | reason:mandatory-core roster + always-last-adversarial ordering kept; cut error-amplification rationale + What/Why-not-How parenthetical (informative-only)
(skills/research/references/fanout.md, s4) | verified_survives | 165e8497e214ccf94be810e98210184e3bf96bc6 | signal:c:research/SKILL.md:180-195 + discovery/references/research.md:53-59 (adr/0023 pins fanout canonical) | anchor:## Dispatch protocol::binds the searcher model | reason:routing rule kept (core->searcher, degrade-loud, adversarial inherits); deduped runnable-detail narration surviving at both consumer bodies
(skills/research/references/fanout.md, s5) | verified_survives | 165e8497e214ccf94be810e98210184e3bf96bc6 | signal:a:tests/test_research_fanout_matrix.py corner-anchored invariants | anchor:## Why this protocol::corner-anchored | reason:compressed corner/cap rationale to one sentence; kept discovery-bias-upward weighting verbatim per Req 4

## skills/pr/SKILL.md

(skills/pr/SKILL.md, file-compress) | verified_survives | 87160f0e9d50a54925a9b6488ea24e4b04bccc5c | signal:c:surviving at ## Workflow step 6 (printf + gh pr create --body-file) | anchor:## PR Body Format::"Always use two separate Bash calls" | reason:verbatim duplicate of the Workflow printf/--body-file pattern; canonical form preserved at Workflow step 6, duplicate section deleted
(skills/pr/SKILL.md, s3a) | verified_survives | 87160f0e9d50a54925a9b6488ea24e4b04bccc5c | signal:b:informative-only; dirty/ahead stop-behavior retained in compressed Workflow steps 1-4 and declared in frontmatter preconditions | anchor:## Workflow::"warn the user and stop" | reason:removed span was step-by-step preflight narration only; warn-and-stop behavior and base-branch/template-detection commands kept inline, no shall/must dropped
(skills/pr/SKILL.md, s3b) | verified_survives | 87160f0e9d50a54925a9b6488ea24e4b04bccc5c | signal:c:preserved verbatim at skills/pr/references/template-filling.md, reached via body-resolved ${CLAUDE_SKILL_DIR} pointer | anchor:## Workflow::"Replace placeholder tokens" | reason:LAZY_REF extraction, template-filling block moved unchanged to a lazily-read reference read only when a template exists; no SP001/SP002
(skills/pr/SKILL.md, s3c) | verified_survives | 87160f0e9d50a54925a9b6488ea24e4b04bccc5c | signal:a:commit/SKILL.md:31 documents the sandboxed temp-file failure mode enforcing the two-Bash-call no-dollar-paren pattern | anchor:## Workflow::"gh pr create" | reason:kept the two-Bash-call/no-substitution/--body-file pattern + no-conversational-text contract; removed only the redundant sub-bullet narration

## cortex_command/overnight/prompts/plan-synthesizer.md

(cortex_command/overnight/prompts/plan-synthesizer.md, s15) | verified_survives | bafa40590e78be394f4cb79a86180df16dc9f7a9 | signal:b:worked-JSON-envelope-lines-76-98-shows-all-five-fields;-positional-order-load-bearing-note-preserved-in-Anti-Sway-rule-3 | anchor:## Output: JSON Envelope::letter token | reason:Field-by-field list only re-describes the five fields already shown verbatim in the worked JSON above; no removed sub-span carries an un-preserved shall/must, kept the sole non-derivable rule (verdict must be the letter token A/B/C).
(cortex_command/overnight/prompts/plan-synthesizer.md, file-compress) | verified_survives | bafa40590e78be394f4cb79a86180df16dc9f7a9 | signal:c:canonical-survivors-Anti-Sway-rule-1(position/length-bias),-rule-2(swap-probe-calibration),-rule-3(score-first),-rule-4-renumbered(uncertain-low) | anchor:## Anti-Sway Protections::Avoid any position biases | reason:Removed rule 4 (explicit re-state of rule 1) and the Constraints bullets duplicating rules 2/3/5; each removed imperative survives at its named canonical rule. Swap+bias verbatim phrases kept in rules 1/2 (test_plan_synthesizer.py::test_prompt_fragment_contains_swap_and_bias_instructions passes).

## skills/backlog/SKILL.md

(skills/backlog/SKILL.md, s11) | verified_survives | 4ec7692294179c092cf7c4b33068a960732c2f64 | signal:b:pick steps 3-6 presentation-case enumeration (informative-only) | anchor:### pick::Present that group's items | reason:collapsed the 0/1/2-4/5+ case-split into one sentence, keeping top-4/omissions + label id/title/priority/type; verb JSON wire format pinned by tests/test_backlog_ready_render.py not this prose; kept step-1 error-JSON/reindex, step-2 first-non-empty-group policy, step-7 lifecycle-routing affordance
(skills/backlog/SKILL.md, file-compress) | verified_survives | 4ec7692294179c092cf7c4b33068a960732c2f64 | signal:c:frontmatter inputs block (lines 4-11) + ### subcommand headings | anchor:## Subcommands::present the available actions | reason:deleted ## Invocation (verbatim restatement of frontmatter inputs block) and collapsed no-arg menu bullets duplicating the ### headings; kept the AskUserQuestion no-arg affordance; contract.py:422 cortex-* invocation lines untouched (required flags intact); applied to verified extent (Invocation+menu per task narrowing); new-fold/archive-merge/error-hoist sub-cuts refuted-as-unapplied

## skills/commit/SKILL.md

(skills/commit/SKILL.md, s6) | verified_refuted | — | signal:none | anchor:## Validation::(section removed in 8c3a00b9) | reason:section removed in 8c3a00b9 — nothing to trim (grep -c '## Validation' skills/commit/SKILL.md = 0; file now 31 lines); no edit attempted (Req 8)

## skills/research/SKILL.md

(skills/research/SKILL.md, s15) | verified_survives | 2cdbdb8fb6523d560287e0d6f1fef8c29e489ac4 | signal:b:skills/research/SKILL.md::Empty/failed-agent-handling | anchor:### Empty/failed agent handling::warning | reason:exact warning strings not machine-parsed anywhere (grep confirms no consumers); compressed narration to one sentence keeping section header+warning note, proceed never abort, all-empty retry note

## skills/interview/references/loop.md

(skills/interview/references/loop.md, file-compress) | verified_survives | 63c5e31f439114c42ea1ec9499331ecb320e1419 | signal:b:Why-rationale-paragraphs-carry-no-shall/must/weighting | anchor:## Decision rules::Why: | reason:compressed six per-rule Why paragraphs (adaptive cadence, batching, anchoring, scarce user time, funnel ordering, saturation) all derivable unaided; kept every rule What and the ask-one-at-a-time/stop-early/soft-cap affordances

---

## Integrity gate (run at assembly, recorded here)

The gate certifies row **correctness** against the EXTERNAL ledger
(`master_candidates.json`) and the commit history — not just pair membership; it is not
self-sealing (a present-but-wrong row would fail (ii) or (iii)).

**(i) Pair-set vs ledger filter — PASS.** Recomputed the 42-row filtered set from
`master_candidates.json` (`status=="unverified"` ∧ `file` ∈ the 12-file set ∧ no
`overlaps_ticket` ∧ no `reproposal_of`): 42 rows, 42 distinct `(file,id)`, 23 distinct ids.
The set of `(file,id)` pairs in this file equals it exactly — symmetric difference EMPTY.

**(ii) Hash provenance — PASS (38/38).** Every `verified_survives` row's `applied_in_commit`
is a 40-hex commit hash, and `git show --name-only <hash>` includes that row's `file`
(the 8 `skills/refine/SKILL.md` rows check against `6b3766e2`, which also touched
`kept-pauses.md` + mirror per the Req 5 anchor bump — expected). The 4 `verified_refuted`
rows carry `—` (no diff, no provenance) — correct.

**(iii) Signal correctness.**
- *signal (a)/(c) location cites* — spot-checked present: `tests/test_refine_handoff.py`,
  `tests/test_load_requirements_protocol.py`, `tests/test_refine_reconcile_clarify.py`,
  `tests/test_refine_skill.py`, `skills/critical-review/SKILL.md`,
  `skills/lifecycle/references/critical-review-gate.md`, `tests/test_research_fanout_matrix.py`,
  `cortex/adr/0023-*.md`, `skills/pr/references/template-filling.md`,
  `skills/commit/SKILL.md:31` (pr s3c's re-anchored temp-file failure-mode cite),
  `cortex_command/pipeline/tests/test_plan_synthesizer.py`, `tests/test_backlog_ready_render.py`
  — all exist and carry the cited content.
- *signal (b) normative-token scan on ACTUAL REMOVED LINES* (`git show <hash> -- <file>`,
  scanning `-`-prefixed lines with `grep -iE 'shall|must|must not|do not|always|never|only
  when|prefer|recommend|weight|default to'`). Because a commit may carry multiple candidates,
  removed lines cannot be perfectly attributed to one id — a hit is a REVIEW FLAG, resolved
  below. Per-file signal-(b) outcome:
  - `skills/backlog/SKILL.md` (s11), `skills/interview/references/loop.md` (file-compress):
    **0 hits** — clean.
  - `skills/pr/SKILL.md` (s3a): 2 hits, both on the **signal:c** rows' removed spans —
    file-compress's "Always use two separate Bash calls" (survives at Workflow step 6) and
    s3b's "Never submit … template default" (moved verbatim to `references/template-filling.md`).
    The signal-(b) row s3a's own removed span (preflight narration) is clean.
  - `skills/refine/references/clarify.md` (s8): 4 hits, all on the **signal:c/a** rows
    (s3 exit-branching, s4 load-protocol, s10 write-back — each preserved/enforced elsewhere).
    s8's removed span (four template strings) is clean.
  - `skills/refine/references/specify.md` (s3,s5a,s7a): 2 hits — s3's "Must-have vs
    nice-to-have" (a NOUN phrase; the concept survives inline verbatim per the row) and s5a's
    "research.md … Research must run" (the guard behavior is retained in the collapsed sentence).
  - `skills/refine/SKILL.md` (s3,s6,s8,s10c,s12): 1 hit on s10c's §4-gate line — an
    **in-place single-line recompression** (the line is removed AND re-added), so the token
    also appears in the re-added line; not a deletion. Multi-candidate (8) file → review flag.
  - `cortex/adr/README.md` (s1,s6,s7): 4 hits — the file's highest-risk trim. s7 is signal:b
    but its own reason DISCLOSES it kept the MUST-automatic bullet and trimmed only clean
    informative tails (the removed `MUST NOT`/`SHOULD` tokens live in illustrative example
    tails); s1's hit is the ADR-definition removal (no normative directive dropped). Multi-
    candidate (6) file → review flag, disclosed in-row.
  - **`cortex_command/overnight/prompts/plan-synthesizer.md` (s15) — few-candidate, real
    concern noted**: 5 hits. Four ("must ignore", "Do not skip", "Do not let") are on the
    **signal:c** file-compress row's removed Anti-Sway rule 4 + Constraints bullets, each of
    which survives at its canonical rule (rules 1/2/3, confirmed present at L22/36/42). The one
    hit on s15's own span is "schema_version (int, always 2)" — a field-VALUE fact, preserved
    as the literal `"schema_version": 2` in the worked JSON envelope (L77) that s15's anchor
    cites. No behavior-determining directive dropped.
  - **`skills/research/SKILL.md` (s15) — single-candidate, real concern noted**: 1 hit,
    "proceed with synthesis … do not abort". The proceed-not-abort behavior is REPHRASED, not
    dropped: current L201 reads "proceed with synthesis using available outputs — **never
    abort**. If ALL agents returned empty, … research should be retried." Behavior + all-empty
    retry note both survive; the norm token moved from "do not abort" to "never abort".

**Non-self-sealing note (Task 12 step 9)**: this file is the deliverable; its gate checks it
against `master_candidates.json` (external ledger) and `git show` provenance/diffs (commit
history) — no artifact was written to satisfy the gate. The one soft spot flagged: the
signal-(b) removed-line scan cannot attribute a multi-candidate commit's removed lines to a
single id, so per-file hits are resolved by inspection (above) rather than a fully automated
per-id verdict; the two single/few-candidate cases (research s15, plan-synthesizer s15) were
checked against the post-trim file directly and confirmed preserved-not-dropped.

---

savings: ~6920 weighted tokens across 38 applied candidates (of 42; 4 refuted) — summed from `master_candidates.json` `weighted_cost` over the `(file,id)` pairs marked `verified_survives` above.

