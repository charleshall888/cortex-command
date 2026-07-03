# Research: Sweep provisional tail — discovery + backlog-author clusters (#359)

**Clarified intent**: Verify the 43 provisional trim candidates across the discovery and backlog-author skill clusters, apply the surviving trims (keeping `plugins/cortex-core` mirrors in sync), and record refuted candidates for the deferred #357 reconciliation — reducing skill token weight without removing load-bearing content.

**Tier/criticality**: complex / high. Child of #357 (parent is `type: chore`, not an epic).

---

## Codebase Analysis

**In-scope set is exact — zero drift.** Filtering `master_candidates.json` (flat 265-row array) to `status == "unverified"` AND `file` under `skills/discovery/` or `skills/backlog-author/` AND no `overlaps_ticket` AND no `reproposal_of` yields **exactly 43 rows**, `weighted_cost` sum **6,987** (≈7.0k, matching the ticket). Per-file breakdown matches the ticket's claim exactly:

| file | count |
|---|---|
| `skills/backlog-author/SKILL.md` | 9 |
| `skills/backlog-author/references/body-template.md` | 6 |
| `skills/discovery/SKILL.md` | 7 |
| `skills/discovery/references/clarify.md` | 6 |
| `skills/discovery/references/decompose.md` | 6 |
| `skills/discovery/references/orchestrator-review.md` | 2 |
| `skills/discovery/references/research.md` | 7 |
| **Total** | **43** |

Category mix in scope: COMPRESS 26 / MERGE_DEDUP 14 / LAZY_REF 3 — no DELETE or OFFLOAD_CLI. The 7 excluded rows are 1 `overlaps_ticket` (#340, in research.md) + 6 `reproposal_of` in decompose.md (the "already excluded" dedup reproposals).

**Row schema**: `id`, `heading`, `start_line`/`end_line` (**stale — locate by heading + pinned token, not line number**), `tokens`, `weighted_cost`, `value`, `category`, `claim`, `pins` (curated, ~1.7/candidate median), `mech_pins` (raw grep, noise-dominated, median 25/candidate), `file`, `slug`, `status`, `votes`/`survive_votes`, `overlaps_ticket`, `reproposal_of`, `applied_in_commit`, `verdict_summaries` (array of `{lens, survives, confidence, revised_category, revised_claim, evidence, user_question}`).

**There is no separate keep-list file or JSON key.** The keep-list is embedded prose inside each row's `claim` field (and, for already-verified rows, `verdict_summaries[].revised_claim`/`.evidence`). For the 43 unverified rows `verdict_summaries` is empty, so the keep-list to honor is whatever the `claim` states plus everything named in `pins`/`mech_pins`.

**The ledger is read-only for this batch.** `master_candidates.json` and `dup_groups.json` status write-back is deferred to a single #357 reconciliation commit — do not mutate them here.

**Cross-cluster dup group** (dup_groups.json index 3): `discovery/references/clarify.md` ↔ `refine/references/clarify.md`, 86 tokens, 1 block (the "Requirements alignment note" item). The discovery-side span sits **inside** in-scope candidate `s7`. It is opportunistic-only and the `refine/` side is owned by #361 — leave alone unless coordinating.

**Target files** (each canonical file has a 1:1 `plugins/cortex-core/skills/...` mirror that must be regenerated + staged in the same commit): the 7 files above.

## Web Research

Best-practice external grounding for "trim without removing load-bearing text":

- **Extractive/subset edits only** (LLMLingua-2): never paraphrase kept text — only delete spans, so the diff stays an auditable literal subset. Directly applicable: never rewrite surviving skill prose, only delete.
- **Short skills can cost MORE** ("What Should a Skill Remember?", arXiv 2606.09421): trimming strips "sparse operational anchors" (rule/formula/workflow-guard anchors) that only matter on rare recovery/edge paths. Text that looks dead under normal-case testing can be genuinely load-bearing.
- **Single automated passes miss semantic drift** (CompressionAttack, arXiv 2510.22963): compression modules optimized for token reduction lack behavior alignment and can silently change downstream behavior; "current defenses prove ineffective." Argues for an independent second check rather than trusting one pass's own judgment.
- **Anthropic's own skill best-practices**: evaluation-driven development + behavioral observation ("does the agent ever exercise this content?"). No first-party automated dead-content verifier exists.
- **Anti-pattern — leave-one-out assuming independence**: breaks when spans interact (two individually-skippable warnings that are jointly necessary). Test the *final trimmed whole*, not just span-by-span removal in isolation.

## Requirements & Constraints

**Editing discipline** (from `cortex/requirements/project.md`, CLAUDE.md, ADR-0009):
- Edit **canonical `skills/` only**; `plugins/cortex-core` mirrors regenerate via `just build-plugin` (run automatically by `.githooks/pre-commit` when `just setup-githooks` is active) and must be staged in the same commit. Hand-editing a mirror is clobbered by rebuild or flagged as drift.
- **Extractive-only** aligns with the "prescribe What and Why, not How" principle: procedural/How narration is the safe-to-trim class; content stating a decision, gate, required output shape, or the *intent* behind a gate is load-bearing "Why" and is not the target.
- **MUST-escalation policy**: do not casually rewrite existing MUST/CRITICAL/REQUIRED language into soft phrasing (or vice versa) as a side effect of trimming — that is an audited action with its own evidence requirement. Leave those tokens as-is.
- **Commit via `/cortex-core:commit` only**; imperative, capitalized, ≤72-char subject, no trailing period.

**Gates that fire on `skills/discovery/` or `skills/backlog-author/` edits**: SKILL.md-to-bin parity (`cortex-check-parity`), prescriptive-prose LEX-1 (fires on `## Why`/`## Role`/`## Integration`/`## Edges` — present in `body-template.md`), skill-path lint SP001/SP002, bare-python L201, events-registry, size budget (500 lines — trims only lower it, safe), and the L1 surface ratchet (see below).

**Scope note**: discovery is documented inline (no area doc); `backlog-author` stays in cortex-core (not moved to cortex-backlog) because discovery/morning-review compose ticket bodies through it. A routine prose trim under existing policy does not warrant a new ADR.

## L1 Ratchet & Test Gates

**The L1 ratchet is a non-issue for this batch — the ticket misclassifies it.** The adversarial pass confirmed against `master_candidates.json`: the sole "frontmatter" candidate, backlog-author `s1`, **explicitly leaves `name`/`description`/`argument-hint` untouched** and only drops `inputs`/`outputs`/`preconditions`. Since the L1 surface = `description` + `when_to_use` byte sum, **no in-scope candidate changes the L1 surface.** The ratchet cannot fire; no budget-row edit is needed even as hygiene.

Supporting mechanics (still true, just not triggered): `tests/test_l1_surface_ratchet.py` measures via `bin/cortex-measure-l1-surface`; backlog-author's budget row is `288` and it currently measures exactly 288 (zero headroom); discovery is exactly at its cluster cap of 932. The ratchet passes **equal-or-lower**; **lowering a budget row requires NO rationale/lifecycle-id — only raising does.** So the ticket's Edges claim ("a description trim needs a budget-row update plus documented rationale and lifecycle-id") is doubly wrong: no description trim occurs, and even a lowering wouldn't require the rationale.

**The real `s1` risk** is different from the one the ticket names: dropping declared frontmatter fields (`inputs`/`outputs`/`preconditions`) can trip the contract/undeclared-variable validator (`tests/fixtures/contracts/`, `cortex_command/lint/skill_path.py`) **if** the SKILL.md body interpolates a variable those fields declared. Verify no body interpolation depends on the dropped fields before applying.

**Events-registry coupling** (flagged by adversarial, missed by others): discovery/decompose/orchestrator-review emit events (`approval_checkpoint_responded`, `decompose_flag`/`ack`/`drop`, `orchestrator_review…`), scanned by `test_check_events_registry.py` + `test_events_registry_glob_parity.py`. Gate/dispatch-shrinking candidates must preserve every emit line.

## Ledger Reconciliation & Refutation Recording

**The refutation-recording mechanism is genuinely under-specified — no convention exists yet.** There is no README/methodology/scratch-file in `cortex/research/skill-value-scorecard/` (git history confirms none ever existed). Siblings #358 (32, editorial) / #359 (43) / #360 (26) / #361 (42) are all still at early refine (only `events.log`). **No parallel-deferred-reconciliation instance has ever completed — #357's children are the first.**

**How a refutation looks in the ledger** (for the eventual reconciliation transcription): `status: "verified_refuted"`, `survive_votes: 0`, a `verdict_summaries` entry with `survives: false` + `revised_category: "KEEP"` (kept in the table, excluded from savings). The closest git precedent (`b0e8e75f`) transcribed verdicts from ephemeral session context directly into `master_candidates.json` — no committed intermediate artifact.

**Resolvable within this child** (per adversarial mitigation 7): record each refuted `id + file + reason + failing test/consumer` into this child's lifecycle `events.log`/spec, and use self-documenting commit messages (`id + file + action`, mirroring the `applied_in_commit` convention), so the deferred #357 reconciliation transcribes verbatim. No touch of the read-only ledger required.

## Mirror-Sync & Commit Workflow

- `just build-plugin` rsyncs `skills/` → `plugins/cortex-core/skills/` (full-dir `--delete`). Both `discovery` and `backlog-author` are in the justfile `SKILLS` array, so both mirror.
- The pre-commit hook rebuilds mirrors and **fails on drift but does NOT auto-stage** — the editor must `git add` the regenerated mirror files.
- **CI parity gap** (broader than first reported): `tests/test_dual_source_reference_parity.py` `PLUGINS["cortex-core"]` tuple **omits backlog-author, requirements-gather, requirements-write, AND interview** — all four are mirrored by the justfile but have no byte-parity backstop test; the test's own docstring invariant ("stay aligned with justfile SKILLS") is already violated. `discovery` IS covered. For this child, backlog-author mirror correctness rests solely on the pre-commit hook — a `--no-verify` commit or a clone without `just setup-githooks` ships a stale mirror undetected.
- **This child's commits**: skill trims + regenerated mirrors (+ optional test-infra changes if in scope). **Deferred to the shared #357 reconciliation commit**: `master_candidates.json`/`dup_groups.json` status write-back — do NOT touch here.

## Verification Methodology & Tradeoffs

**Pin-hit single-pass is not a sufficient acceptance gate for this batch.** The adversarial pass verified that several candidates self-justify with "no test greps this" claims that are **demonstrably false**:
- `tests/test_discovery_gate_presentation.py` pins verbatim markers in `discovery/SKILL.md` (`<approve|revise|drop|promote-sub-topic>`, brief-invocation string, R3 drop dual-use phrase).
- `tests/test_backlog_author.py` extracts the compose/interview **sections** of `backlog-author/SKILL.md` and asserts on their contents by section boundary (interview section ≥1 `AskUserQuestion`; compose section **zero** `AskUserQuestion`; compose section contains all five headings + `body-template.md` citation) — sensitivity invisible to grep.
- `tests/test_decompose_rules.py` parses `decompose.md` by heading and asserts the literal `backlog-author/references/body-template.md`.

11/43 candidates carry **zero curated pins** (pure prose judgment, no anchor); `mech_pins` are noise-dominated (generic headings match dozens of unrelated files). The corpus's own adversarial track record refuted **5/101** already-verified candidates (~5%) — every failure from commit provenance, production-code consumers (`common.py`), or SDK runtime behavior, all invisible to a pins/mech_pins grep by construction.

**Cross-candidate interactions within this same batch** (per-candidate passes cannot see these — no pin references a sibling candidate):
- backlog-author `s3` ("merge with s5") ↔ `s5` ("merge with s3") — **mutually referential**; applied independently → double-delete/orphan. Must be one atomic edit.
- backlog-author `s6`+`s7`+`s8` — all operate on the **same interview branch** (move it / collapse its sequence / shrink Applying-answers). Application order decides where content lands.
- backlog-author `s7` ↔ body-template `s2`–`s6` — `s7` collapses the interview list "because criteria are fully specified in body-template.md" while those body-template candidates each trim 30–50% of exactly that content. Applied together, guidance could end up thinner than intended.
- discovery `s2`/`s3`/`s5` — all restate/merge the frontmatter+Invocation+dispatch region.

**Recommended methodology (Approach C, hybrid, strengthened):** acceptance gate becomes **pin-hit triage → apply per file-family → the affected test suite passes** (implements the web agent's "test the trimmed whole"). Treat interacting candidates as atomic joint edits with a post-apply joint re-read, and single-pass the independent remainder (~34). Mandatory test targets after each file-family's trims: `test_backlog_author`, `test_discovery_gate_presentation`, `test_discovery_gate_brief`, `test_decompose_rules`, `test_discovery_module`, `test_morning_review_failed_feature_gate`, `test_check_events_registry`, `test_events_registry_glob_parity`, `test_dual_source_reference_parity`, `test_l1_surface_ratchet`, plus LEX-1 / skill-path / size gates.

## Adversarial Review

Key challenges that reshaped the plan (all verified against the repo):

1. **Candidates' embedded "no test greps this" claims are false; pin-hit grep is not a sufficient gate.** → the acceptance gate must be running the affected test suite, not a grep of the pinned sites.
2. **Section-boundary tests break invisibly** (`test_backlog_author` interview/compose split): the interview-extraction LAZY_REF (`s6`) must keep ≥1 `AskUserQuestion` in the SKILL.md interview stub and zero in the compose section; verify section-extraction boundaries, not just token presence.
3. **Same-file cross-candidate collisions** beyond the one the methodology agent found (see list above) — must be applied as atomic joint edits.
4. **L1-ratchet "sole frontmatter candidate" is a misclassification** — no candidate touches `description`/`when_to_use`; drop the L1 ceremony from scope; the real `s1` risk is dropped `inputs`/`outputs`/`preconditions` fields vs the contract/undeclared-variable lint.
5. **"43 with zero drift" is a snapshot the spec must not freeze.** The filter is `status==unverified`; the deferred #357 reconciliation and siblings #358/#360/#361 write status back into the *same* file — under overnight scheduling any could run first and shift the in-scope set. Add an execution-start re-derivation guard.
6. **Downstream consumers beyond the pinned sites** (verified): `morning-review/SKILL.md` + `references/walkthrough.md` invoke `/backlog-author compose` (pinned by `test_morning_review_failed_feature_gate.py`); the `backlog` skill invokes `/backlog-author interview`; `discovery/references/decompose.md` invokes `/backlog-author compose`. Trimming the compose/interview contracts must honor these callers.
7. **Parity gap** omits 4 skills incl. backlog-author (see Mirror-Sync). Closing it edits test infra — name it explicitly or defer, don't fold silently.

## Open Questions

- **Acceptance-gate strengthening — deferred to Spec.** Research strongly recommends replacing the ticket's literal "pin-hit, single-pass" bar with "pin-hit triage → apply per file-family → affected test suite passes," because pin-hit grep provably cannot discharge the ticket's own "confirm non-load-bearing" requirement here (false "no-test" claims, section-boundary tests, cross-skill consumers). The adversarial pass judges this the *faithful* reading of the ticket's existing requirement, not a scope expansion — but because it changes the stated verification bar, it will be surfaced to the user at Spec approval for confirmation. *Deferred: resolved in Spec by presenting the strengthened gate for user sign-off.*
- **Parity-gap fix scope — deferred to Spec.** Should this child also add `backlog-author` (and `requirements-gather`/`requirements-write`/`interview`) to `tests/test_dual_source_reference_parity.py` `PLUGINS["cortex-core"]`, closing a pre-existing CI backstop gap the batch would otherwise leave open? This edits test infrastructure beyond the trim scope. *Deferred: resolved in Spec as an explicit in-scope-or-follow-up decision by the user.*
- **Refutation-recording artifact — resolved.** Record refuted candidates in this child's lifecycle `events.log`/spec (`id + file + reason + failing test/consumer`) with self-documenting commit messages; leave the ledger untouched for the deferred #357 reconciliation. The exact artifact shape is an inference from the `b0e8e75f` precedent (no documented convention exists yet); Spec will lock it.
- **Cross-cluster dedup group (#359 ↔ #361) — resolved.** Leave alone (opportunistic-only; the `refine/references/clarify.md` side is owned by #361). Touch only if explicitly coordinating with whichever child runs second.
- **Execution-time staleness — resolved.** Spec will encode an execution-start re-derivation preflight: recompute the filter and assert `count==43`, `weighted_sum==6987`, and the 7-file histogram; assert `master_candidates.json`/`dup_groups.json` are byte-unchanged at commit time. Halt on mismatch.
