# Research: Should cortex's ticket-body governance be reduced, and at which layer?

**Clarified intent** — Determine whether to reduce ticket-body governance at two layers: (a) the shipped five-section template (`## Why` / `## Role` / `## Integration` / `## Edges` / `## Touch points`) in `skills/backlog-author/SKILL.md`, which installs into every consumer repo via the always-installed cortex-core plugin; and (b) cortex-command's local front-door evidence bar in `CLAUDE.md`. Outcomes on the table: drop, slim, keep, or change one layer only.

**Tier** complex · **Criticality** high · Context B (no backlog item).

> **Provenance warning.** This investigation retracted **four** quantitative claims before reaching its conclusion — three from the orchestrator, one from an angle agent. Details in `## Corpus Evidence` and `## Adversarial Review`. The corrected finding **reverses** the direction the investigation started in. Treat any un-recomputed number from the original framing as suspect.

## Codebase

**The citation ban is unenforced prose.** `skills/backlog-author/SKILL.md:13` (second sentence) and `:21` forbid `path:line` / `§N` citations and code fences outside `## Touch points`. The LEX-1 prescriptive-prose scanner that enforced this was retired in `e3aef4e5`; `cortex/requirements/project.md:41` lists it under "retired without named evidence." No live gate, hook, or justfile recipe references it. `tests/test_backlog_author.py`'s module docstring still advertises `test_lex1_rejects_code_block_in_why_section` and `test_interview_mode_routes_through_askuserquestion` — **neither function exists**. The stale docstring is why the zero-enforcement state went unnoticed.

**The only machine consumer of the sections** is `cortex_command/backlog/load_parent_epic.py:73-76`, `INTENT_SECTIONS = ("## Why", "## Role")`, a tier in the extraction chain at `:232-249`: discovery-framing (`SECTION_PRIORITY`) → Why/Role concatenated → first paragraph after H1 → `PLACEHOLDER_BODY`. Its output feeds the clarify-critic's Parent Epic Alignment sub-rubric. The codebase angle characterised removal as "degrades silently, does not break" — **this was wrong by one tier**, see `## Adversarial Review` §1.

**No write-time validation exists.** `cortex_command/backlog/create_item.py:257,210-218` appends `--body` verbatim with no structural check. The template binds the model at generation time and nothing else.

**Gates and mirrors.** `SKILL.md` is 21 lines against a 500-line cap (`tests/test_skill_size_budget.py`); `references/size-pin.txt` is already `0` and the directory holds nothing else, so `just ratchet-refs` is moot unless reference *content* is added; `tests/test_l1_surface_ratchet.py:55` pins the L1 surface at 288 bytes and only ever gets lower. `tests/test_backlog_author.py:76` asserts SKILL.md literally contains all five heading strings — **breaks, needs lockstep update**. Mirror reconciliation is automatic: `.githooks/pre-commit` Phase 3 rebuilds `plugins/cortex-core/` from staged blobs and folds it into the commit; never stage mirrors by hand.

## Web & Prior Art

**Format restriction degrades LLM reasoning — conditionally.** "Let Me Speak Freely?" (EMNLP 2024, [arXiv:2408.02442](https://arxiv.org/abs/2408.02442)) measured 10–15% accuracy loss under structured-format constraints. "Capacity, Not Format" ([arXiv:2606.09410](https://arxiv.org/html/2606.09410)) reframes the cause as **premature serialization** — emitting schema-compliant tokens before reasoning completes. Structure applied *after* free reasoning carries no penalty. See `## Adversarial Review` §5 for why this citation does not reach cortex's call site.

**Post-hoc structuring is a task LLMs do well.** [arXiv:2504.18804](https://arxiv.org/abs/2504.18804): LLMs converting informal input into a structured bug template score 77% CTQRS (fine-tuned Qwen 2.5), beating GPT-4o few-shot, generalizing to unseen projects.

**Templates measurably help human-authored issues.** ACM TOSEM 2024 ([10.1145/3643673](https://dl.acm.org/doi/10.1145/3643673)): median resolution 381 → 103 days with a template, fewer comments; YAML issue *forms* beat free-text templates. Bettenburg et al. (FSE 2008) is the foundational information-mismatch study. Only ~5% of repos with >10 stars adopt structured forms.

**Documented reversal in the keep direction**: `noir-lang/noir` [PR #2736](https://github.com/noir-lang/noir/pull/2736) removed a Feature Request template and judged the removal a regression.

**arc42 misapplication.** `## Role` cites arc42 "Responsibility" — a per-*system*, per-component field documented once per architecture ([docs.arc42.org/section-5](https://docs.arc42.org/section-5/)). arc42's own FAQ says "please don't fill in everything." Per-ticket application inverts both its granularity and its guidance: a stretch, not a recognized use.

**Inverted rationale.** GitHub adopted issue forms partly as an anti-LLM-slop filter for *untrusted human* submitters. Here the filer is the trusted agent — that rationale does not transfer.

**No evidence found** (explicitly, not by omission): no study of LLM agents authoring tickets under a mandatory multi-section schema; no measurement of "N/A padding" or ritual-compliance rates; no study isolating a five-section arc42-derived schema.

## Requirements & Constraints

**The two-carrier separation is settled law.** `project.md:23`: the front-door evidence bar's carrier is "the front-door evidence bullet in this repo's `CLAUDE.md` Conventions — **not the shipped body template, which installs into consumer repos where this clause doesn't exist**." `CLAUDE.md:33-34` states the general rule. **Ticket #409 is direct precedent**: the evidence rule was originally placed inside `skills/backlog-author/references/body-template.md` and corrected out to `CLAUDE.md` the same day (commit `a86bd4c3`, 2026-07-21). **Layer (b) is a closed decision; nothing found argues to reopen it.**

**The evidence bar binds two classes, not all tickets** — "a ticket adding harness machinery" and "an efficiency-framed ticket" (`CLAUDE.md:34`, restated `project.md:23`). No third clause extends it universally.

**Deletion bias is scoped.** `project.md:23` covers "Keeps, safeguards, and measurement tooling," and names the anti-pattern it exists to stop (#382/#389/#390/#392 landing as net additions dressed as efficiency). Whether a ticket-body output schema falls inside that scope is contested — see `## Open Questions` Q3.

**ADR-0016** keeps `backlog-author` in always-installed cortex-core (`backlog.md:96`) because discovery and morning-review compose bodies through it on the external-tracker path. **Any template change ships unconditionally to every consumer repo.** **ADR-0007** backs `decompose.md`'s merged-body rule. No ADR governs the template's section count.

**This decision likely does not warrant an ADR** — `cortex/adr/README.md`'s three-criteria gate requires hard-to-reverse; #409 demonstrates a same-day single-commit revert of exactly this kind of change.

**Authoring constraints**: `docs/policies.md:19-25` What/Why-not-How — the five sections are an *output shape* (permitted) rather than a procedure (not). `CLAUDE.md:29` prefers structural separation over prose-only enforcement.

## Corpus Evidence

Era-corrected: `created:` on/after 2026-05-19 (template landing). Pre-landing conformance is 0% in every repo (140/140, 240/240, 19/19), confirming the split is sound. **Ticket-number splits are contaminated** — #298 already carries the full shape.

**No outcome advantage, either repo.** Completion (`done`+`complete` vs `abandoned`+`superseded`): cortex-command conforming 119/127 = 93.7% vs non-conforming 59/60 = 98.3% (n=140 / 65); wild-light 130/136 = 95.6% vs 110/115 = 95.7% (n=180 / 139). Lifecycle-event proxies (escalation, review rejection, phase count) differ **in opposite directions across repos**. Spec churn is absent (1 case each). `rework_of` exists on 1 ticket per repo — unusable.

**Explicitly "cannot detect," not "proven null"** — cells of 17–29.

**wild-light's natural experiment is confounded.** Conformance tracks *which epic authored the batch*: 41% of conforming tickets sit under two epics (#344, #263) vs 4% of non-conforming; 63% of non-conforming have no parent epic vs 37% of conforming. Type skew (`feature` 41.7% vs 23.0%). **Recency skew of 17 days** — conforming tickets are newer and have had less time to reach `done`, which alone could produce the small edge favouring non-conforming tickets.

**Adoption is rising, not decaying**: cortex-command 12.4% → 52.1% → 77.5% → 93.1% (May→Aug); wild-light 5.4% → 45.5% → 77.5%.

**Retracted claim (mine): the "54% ad-hoc post-filing sections" finding is false.** `## Outcome` / `## Decision` / `## Correction` / `## What shipped` appear in **4 of 447 tickets (0.9%)**. The real non-canonical sections are `Context from discovery` (95), `Scope` / `Out of Scope` (75/72), `Research Context` (44), `Acceptance` (28) — and **76.7% (234/305) were present in the file's first commit**. This is a second authoring template, not a post-filing write-back gap.

> **Method trap worth keeping.** Resolving this required `git log --follow --diff-filter=A --name-only` to find each file's path at creation. The repo was relocated wholesale in `c8110de5`, and `git show <old-commit>:<current-path>` **returns empty rather than erroring**, fabricating false "added later" results. An earlier pass without rename resolution produced the opposite, wrong answer.

**Citation ban has no measurable effect.** cortex-command cited (n=29) 78.6% done vs uncited (n=139) 96.8%; wild-light cited (n=41) 100% vs uncited (n=214) 94.6% — opposite directions, and cortex-command's cited group is confounded by a cluster of recent self-referential meta-tickets.

## Adversarial Review

**§1 — Removing `## Why`/`## Role` re-opens a closed bug, silently, with tests green.** `_first_paragraph_after_h1` (`:192-214`) returns `""` without a literal `# ` H1. **Orchestrator-verified by running the real extractor**: of epics currently served by the Why/Role tier, **9/9 in cortex-command and 7/7 in wild-light — 16 of 16 — return `(no body content)` if the headings are removed.** Tier 3 does not catch them.

The harm is a **filed, closed bug**: `cortex/backlog/375-cortex-load-parent-epic-returns-no-body-content-for-epic-with-full-body.md` (`type: bug`, `status: complete`), whose Why reads *"The critic's parent-epic alignment sub-rubric silently evaluated against an empty body — a genuinely divergent epic would have passed unchallenged."* That is precisely the "measured cost or observed failure, not a hypothetical" the front-door bar demands. **The burden of proof for keeping `## Why` and `## Role` is met.** The Requirements angle's "no ticket argues for keeping the template" searched for *advocacy of the template* rather than *bugs about its consumers*.

`tests/test_load_parent_epic.py:229` is #375's regression test and its fixtures hardcode `## Why`/`## Role` (`:240-259`) — **drop the headings and every test passes while 16/16 real epics degrade.** This is the fixture-hides-the-bug pattern already recorded from #421.

**§2 — The null result is a universal solvent, not evidence.** Every measured proxy is downstream of the whole pipeline, so *no prose surface in this harness can ever show a benefit* under them. If "no completion advantage" licenses removal it equally licenses removing the 34-ADR corpus, `cortex/requirements/`, the kept-pauses taxonomy, spec.md's structure, and research.md's `### Pieces`. A criterion that dissolves everything is being misapplied, not satisfied. Correct reading: deletion bias is a **tiebreaker under equipoise**, applied where a surface has no named consumer. `## Why`/`## Role` have one.

**§3 — Three invisible channels.** (a) **The rising-adoption confound**: non-conforming tickets are disproportionately old and therefore already terminal, so the completion gap partly measures ticket age — and it points in the direction the investigation was treating as evidence. (b) `decompose.md` §5a's batch-review gate offers `drop-piece` *before any commit*, so a template that makes a weak piece visible as weak deletes it before it becomes a countable file. (c) `tests/test_morning_review_failed_feature_gate.py:31` shows morning-review composing bodies unattended; comprehension cost on the later cold read is charged to a different session and is untraceable.

**§4 — Consumer blast radius.** ADR-0016 ships LLM-as-adapter with no per-tracker code; the five sections are the stable input distribution that mapping reads, on the unattended path where no human reviews the result. **#409 is precedent for layer (b) and precedent for nothing about layer (a)** — its logic (consumer repos lack this repo's clauses) cuts the *other* way for the template, since those repos have no local convention supplying structure either. Empirically: **17 of 24 wild-light epics already extract to nothing** — consumer drift toward unstructured bodies is already the observed failure mode.

**§5 — "Models are powerful now" is unenforceable by cortex's own decision.** ADR-0032 leaves `ClaudeAgentOptions.model` unset; cortex cannot know or guarantee which tier authors any ticket, in any consumer repo, now or after a future CLI default change or a cost-motivated `--model haiku` overnight run. ADR-0032 also *preserved* the downstream signal ("observability is preserved by reading the model back rather than dropping it") — the faithful analogue is replace the extraction path **before** deleting the headings. Separately: **"Let Me Speak Freely?" does not reach this call site.** `decompose.md:7` forbids re-deriving pieces from raw findings, so `compose` consumes a completed analysis and serializes it — the post-hoc regime that arXiv:2606.09410 says carries no penalty and arXiv:2504.18804 says LLMs do well. **The prior-art angle's strongest citation, read carefully, argues for keeping.**

**§6 — Removing the five sections worsens the coordination defect.** Four places declare heading contracts and exactly one parses them: backlog-author's five sections; `discovery/SKILL.md:51`'s `## Promoted from`, which is *"the sole linkage — no frontmatter pointer"*; `decompose.md:23`'s prose-only merged-body rule; and `load_parent_epic.py:63-67`'s `SECTION_PRIORITY`. Deleting the five sections removes the one branch that is both documented *and* test-covered, leaving the undocumented ones standing — including a machine linkage with no frontmatter backup.

**§7 — The `## Role` argument is self-undermining.** "External authority misapplied + section is thin" also takes ADR-0007's grouping, the kept-pauses `kind` taxonomy, `## Edges`, and the area docs. And `## Role` is one of only two headings any code reads — selecting it for deletion shows the operative criterion is "the justification prose reads thin," not "nothing depends on it."

**Where the emerging conclusion survives**: delete the citation ban (zero enforcement, no signal, ~3 of 21 lines); fix the stale test docstring; leave layer (b) closed; if something structural must go, the honest candidates are `## Integration` and `## Edges` — no code consumer, no measured effect — **not `## Why`, not `## Role`**.

## Open Questions

1. **Does `decompose.md`'s merged-body rule depend structurally on the five sections?** *Resolved — both angles are right at different levels.* No code or test parses it (codebase angle verified; `tests/test_decompose_index_backend_gate.py` targets §7's backend gate only), so nothing fails at runtime. But it is ADR-0007-backed prose naming the five sections as merge targets, so it needs a lockstep prose edit under any section change. It is a prose-maintenance dependency, not a runtime one.

2. **Is the completion-rate comparison interpretable at all?** *Open — carried to Spec.* The adversarial angle identified a rising-adoption confound (non-conforming ⇒ older ⇒ already terminal) that no angle controlled for. Falsifier named: recompute completion within a fixed created-date window, or with age as a covariate. **Not blocking**, because the conclusion no longer rests on this comparison — but any future argument that cites the null result must clear this first.

3. **Does deletion bias's scope reach a ticket-body output schema?** *Resolved at Spec, after critical review.* **Polarity correction:** §2 above (quoting the adversarial angle) says deletion bias is "a tiebreaker under equipoise, applied where a surface has *no named consumer*" — that is backwards, and critical review caught spec.md and research.md stating opposite polarities while both passed the spec's then-current token checks. The correct statement, now in spec.md R3: **no consumer that fails on removal ⇒ presumption of removal stands**; a build-failing consumer or a filed bug recording observed failure discharges it, and the surface is then weighed on the merits. The original fork below is retained for the record. `project.md:23` scopes it to "keeps, safeguards, and measurement tooling" and names an anti-pattern about accreted efficiency-framed additions. The adversarial angle argues an output schema with a live machine consumer is none of those, and that extending the rule there makes it a universal solvent. Spec must settle whether deletion bias applies here as burden-of-proof or only as a tiebreaker under equipoise.

4. **Is `## Promoted from` a latent fragility?** *Deferred — out of scope.* `discovery/SKILL.md:51` makes a body section "the sole linkage — no frontmatter pointer," with nothing parsing or testing it. Real, but it is a discovery-skill defect independent of this decision. Worth a separate ticket; do not fold in.

5. **Is `SECTION_PRIORITY` stale?** *Resolved — no, and a phantom finding was avoided.* The adversarial angle reported "zero current emitters" of its headings in `skills/`. Orchestrator-verified: the corpus contains 95 tickets with `## Context from discovery` in exactly the casing `_section_text` requires (it uses exact string equality at `:174`). No emitting skill prose remains, so the contract is legacy-served — stale in *source* but live in *corpus*. Not a case-sensitivity bug.

6. **What replaces heading-keyed extraction if sections ever change?** *Open — a precondition, not a question.* Per adversarial §1 and §5, no template change may ship to consumers before `load_parent_epic` gains a heading-agnostic tier **and** `tests/test_load_parent_epic.py` is de-fixtured so the #375 regression can actually fail. Spec must treat this as a gating precondition on any structural change.
