# Specification: rewrite-cortex-pr-review-from-fan

> Epic context: derived from the audit + measurements at `cortex/research/pr-review-skill-audit/` (report.md, measurement.md, measurement-large-prs.md). See `research.md` for the full angle-by-angle findings and the adversarial review that shaped the decisions below. This spec was revised after a Specify-phase critical-review pass; see `## Decision Log` for what changed and why.

## Problem Statement

The `cortex-pr-review` skill underperforms — inconsistent findings, noisy output, a heavy five-stage fan-out flow — and is an admitted fork of Anthropic's first-party code-review. A 36-run measurement study (6 PRs, solo + large multi-author) showed a single high-effort reviewer pass beat the pipeline on consistency everywhere and quality nearly everywhere; the pipeline's own components (non-deterministic grounder drops, `$TMPDIR` collisions, silent fail-open-to-APPROVE) manufactured the inconsistency. This rewrite replaces the fan-out with a thin skill wrapping one full-context reviewer agent and fixes two latent correctness defects (fail-open verdicts; the verdict-vs-label leak). It benefits anyone running `/pr-review` in the terminal: consistent findings, visible grounding, and never a silent approve. The first cut is a net deletion plus a correctness layer; the cross-PR lookup and deterministic-linter grounding are named fast-follows.

## Grounding & Verdict Vocabulary

This vocabulary is defined once here and is the single source of truth for Requirements 6–9. Every requirement and acceptance criterion uses these terms exactly.

- **Grounded finding**: the reviewer located the finding's quoted text on the added (`+`) side of the diff AND cites the concrete `file:line` where it appears.
- **Evidence-weak finding**: the reviewer could not locate the quoted text on the `+` side. The finding is still **surfaced** (shown to the user), flagged `evidence-weak` — it is NOT dropped.
- **Surfaced findings**: all findings shown to the user = grounded findings + evidence-weak findings. Counted in `findings_surfaced` (with an evidence-weak sub-count).
- **Dropped findings**: findings the reviewer removed entirely (e.g., exact duplicates). Counted in `findings_dropped` with a reason. In this design, an ungroundable finding is surfaced as evidence-weak, never silently dropped — so grounding failure is a *surface event*, not a *drop*.
- **Degradation signals** (any one fires): (1) reviewer agent errored, timed out, or returned unparseable output; (2) diff missing or empty; (3) grounding step could not complete; (4) PR metadata fetch failed; (5) the reviewer surfaced ≥1 finding but grounded NONE of them; (6) an evidence-weak finding carries `severity = blocking` (an unverifiable blocker the reviewer could neither confirm nor dismiss).
- **Verdict derivation** (deterministic, evaluated top-to-bottom; keys on *grounded* findings, never on a label string):
  1. If any **grounded** finding has `severity = blocking` → `REQUEST_CHANGES`.
  2. Else if any degradation signal fired → `REVIEW_INCONCLUSIVE`.
  3. Else (every surfaced finding is grounded, none is blocking, no degradation) → `APPROVE`.

This closes the holes the critical-review found: an all-evidence-weak review trips signal (5) → `REVIEW_INCONCLUSIVE` (not a silent APPROVE); an ungrounded blocking finding trips signal (6) → `REVIEW_INCONCLUSIVE` (neither a silent APPROVE nor a hallucinated REQUEST_CHANGES); only a *grounded* blocker forces `REQUEST_CHANGES`, so "verified blocker" and "grounded blocking finding" are the same thing.

## Phases

- **Phase 1: Structural collapse** — replace the five-stage fan-out with one full-context reviewer dispatch; delete the triage/critics/git-history/protocol/grounder script; de-pin the model; clean frontmatter/manifest/preconditions.
- **Phase 2: Correctness & output contract** — in-context grounding with falsifiable per-finding citations; the deterministic fail-loud verdict state machine; the verdict/label fix; terminal-first output + observability footer; and a contract test pinning the state machine and grounding contract.

## Requirements

### Phase 1: Structural collapse

1. **Collapse to one full-context reviewer agent.** The skill dispatches a single high-effort reviewer (Agent/Task) that gathers its own context — the diff, touched and related files, and CLAUDE.md if present — and emits the finding schema. No parallel critics, no triage, no synthesizer hop. Acceptance: (a) `grep -ciE 'haiku|triage|four[ -]|fan-out|synthesizer|parallel critic' plugins/cortex-pr-review/skills/pr-review/references/protocol.md` = 0 evaluated against the *operative reviewer-flow section only* (any removal/migration narration lives in a clearly delimited "Removed in 307" appendix or in `CHANGELOG.md`, NOT the operative section, so the grep scope is unambiguous); (b) the protocol describes exactly one reviewer dispatch — Interactive/session-dependent: the dispatch's runtime behavior is exercised by the Req 11 contract test, not this grep. **Phase**: Structural collapse

2. **Replace the 821-line five-stage protocol with a single-pass description.** Decisions/gates/output-shape, not step-by-step method (What/Why, per CLAUDE.md). Acceptance: `protocol.md` no longer contains the staged structure — `grep -ciE '(^|[^a-z])(stage|step|pass|phase) [0-9]' plugins/cortex-pr-review/skills/pr-review/references/protocol.md` = 0 — AND `wc -l < plugins/cortex-pr-review/skills/pr-review/references/protocol.md` ≤ 200 (bounded threshold replacing "a fraction of 821"). **Phase**: Structural collapse

3. **Delete `evidence-ground.sh`.** Acceptance: `test ! -e plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` (exit 0). (Grounding moves in-context — see Req 6.) **Phase**: Structural collapse

4. **De-pin the model.** Remove every `claude-opus-4-7` reference; model selection is session-default / highest-available. Acceptance: `grep -rc 'claude-opus-4-7' plugins/cortex-pr-review/` = 0. (The footer reporting the model that ran is Req 9.) **Phase**: Structural collapse

5. **Update frontmatter, manifest, preconditions; correct two doc errors.** SKILL.md `description` no longer advertises a "multi-agent pipeline"; `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` descriptions updated; Stage-0 preconditions drop `jq`/`python3`/cache-dir requirements that existed only for `evidence-ground.sh` (retain `python3` only if Req 11's test helper needs it). Correct the ticket's "canonical-plus-mirror dual-source" misstatement in any committed text — this plugin is hand-maintained, edited in place. Add a one-line note that `/pr-review`'s terminal verdicts (`APPROVE`/`REQUEST_CHANGES`/`REVIEW_INCONCLUSIVE`) are deliberately distinct from the overnight `review_dispatch` JSON contract (`APPROVED`/`CHANGES_REQUESTED`/`REJECTED`/`ERROR`). Acceptance: (a) `grep -ci 'multi-agent' plugins/cortex-pr-review/.claude-plugin/plugin.json` = 0; (b) the distinctness note is present in SKILL.md — `grep -c 'review_dispatch' plugins/cortex-pr-review/skills/pr-review/SKILL.md` ≥ 1. **Phase**: Structural collapse

### Phase 2: Correctness & output contract

6. **In-context grounding with falsifiable per-finding citations.** Grounding is a finding-schema requirement + reviewer decision criterion: for each finding, confirm its quoted text appears on the `+` side and **cite the `file:line`**; a finding whose quote cannot be located is marked `evidence-weak` and surfaced (never silently dropped). The `file:line` citation makes each grounded claim **human-checkable in the terminal output** — converting opaque self-attestation into a falsifiable claim a reader (or the footer) can spot-check. Acceptance: (a) the finding schema in `output-format.md` defines a `grounding` status field (`grounded`/`evidence-weak`) and a `file:line` citation field — `grep -c 'evidence-weak' plugins/cortex-pr-review/skills/pr-review/references/output-format.md` ≥ 1; (b) Interactive/session-dependent: the reviewer's grounding judgment is model behavior; the *contract* (every finding carries a grounding status; evidence-weak findings are surfaced not dropped) is exercised by the Req 11 test. **Phase**: Correctness & output contract

7. **Deterministic fail-loud verdict state machine.** Implement the verdict derivation from `## Grounding & Verdict Vocabulary` exactly, as a structurally-enforced gate (not prose-only): given the structured finding-set (with grounding status + severity) and the degradation-signal flags, the verdict is computed deterministically. The verdict set is `APPROVE | REQUEST_CHANGES | REVIEW_INCONCLUSIVE` (no `COMMENT`). Acceptance: (a) `grep -c 'REVIEW_INCONCLUSIVE' plugins/cortex-pr-review/skills/pr-review/references/*.md` ≥ 1; (b) the verdict derivation and all six degradation signals are documented; (c) the routing is pinned by the Req 11 test (the positive behavioral check) — including the all-evidence-weak → `REVIEW_INCONCLUSIVE` case. **Phase**: Correctness & output contract

8. **Verdict-vs-label fix via a single severity field.** Collapse the three-axis rubric to one verdict-driving severity (`blocking` vs not) plus the grounding gate; drop the signal axis. The `(blocking)` decoration is rendered *from* the severity field, so label and verdict cannot diverge. Remove `suggestion (blocking)` (exactly one blocking label form: `issue (blocking):`); delete per-label caps and the alphabetical tie-break. Acceptance: (a) `grep -c 'suggestion (blocking)' plugins/cortex-pr-review/skills/pr-review/references/*.md` = 0; (b) the per-label caps and alphabetical tie-break are gone — `grep -cE '\b(nitpick|praise|cross-cutting)[^:]*(≤|<=|max|cap)' plugins/cortex-pr-review/skills/pr-review/references/rubric.md` = 0 AND `grep -ci 'alphabetical' plugins/cortex-pr-review/skills/pr-review/references/rubric.md` = 0; (c) one canonical label↔decoration↔severity↔verdict table exists in `output-format.md`. **Phase**: Correctness & output contract

9. **Terminal-first output + observability footer.** Plain-text by default (no `<details>`/HTML/markdown table); GitHub-markdown only when posting. Findings sorted blocking-first, then `file:line`. The footer reports: the model that actually ran (captured at dispatch); `findings_surfaced` split into grounded vs evidence-weak counts; `findings_dropped` (genuinely removed, with reasons); and a per-reason breakdown. The evidence-weak count is the headline observability fix (these vanish silently today). No-autopost is the default-and-only behavior; posting requires an explicit flag/request, encoded as a presentation gate. Acceptance: (a) default output has no `<details>`/`<summary>`/markdown-table syntax (those appear only in the posting branch) — `grep -c '<details>' plugins/cortex-pr-review/skills/pr-review/references/output-format.md` shows them only under a posting-mode heading; (b) the footer field list (model-that-ran, findings_surfaced incl. evidence-weak, findings_dropped) is documented; (c) the no-autopost default at the current `SKILL.md:73` survives and posting is flag-gated. **Phase**: Correctness & output contract

10. **In-scope contract test pinning the verdict state machine and grounding contract.** A runnable test (under `tests/`) feeds synthetic finding-sets + degradation-signal combinations to the verdict-derivation logic and asserts the resulting verdict — covering at minimum: grounded blocking → `REQUEST_CHANGES`; all-evidence-weak (signal 5) → `REVIEW_INCONCLUSIVE`; evidence-weak blocking (signal 6) → `REVIEW_INCONCLUSIVE`; zero findings + degradation → `REVIEW_INCONCLUSIVE`; all-grounded non-blocking → `APPROVE`. It also asserts the grounding contract (an ungroundable finding is surfaced as evidence-weak, not dropped). This is the positive behavioral check the critical-review found missing; it requires the verdict derivation to be a testable unit (mechanism — pure helper vs fixture-driven — is a Plan decision). Acceptance: `just test` (or the targeted `uv run pytest tests/<new-test>`) exits 0 and the test asserts the five verdict cases above; pass if exit code = 0. **Phase**: Correctness & output contract

## Non-Requirements

- **On-demand cross-PR / prior-comment lookup — DEFERRED to a fast-follow (was the ticket's third differentiator).** The critical-review showed shipping it (even flag-only) re-introduces the prev-PR fetch path Phase 1 removes, bifurcates the grounding contract into a second `external` class, and adds machinery to a deletion-thesis first cut for measured value of 2/3 large PRs (n=3). It returns as its own scoped change with: a trigger design (flag-first, auto-trigger calibrated separately), the `external` grounding class for out-of-diff findings, gh-fetch failure added as a degradation signal, and de-duplication + a context-size cap. Deferring keeps the first cut a clean net deletion.
- **No auto-trigger heuristic for cross-PR** — folded into the deferred cross-PR fast-follow; thresholds need calibration (`≥2 authors` would fire near-universally).
- **No deterministic-linter grounding** (semgrep/shellcheck) — the ticket's named out-of-scope fast-follow.
- **No retention of `evidence-ground.sh`** — deleted, not kept dormant. If in-context grounding later proves to hallucinate through, a fixed+tested grounder is re-added on a quote-fidelity calibration, not retained on speculation.
- **No `COMMENT` verdict** — non-blocking nuance is carried by labels under an `APPROVE` verdict.
- **No wiring of `/pr-review` into overnight automation** — terminal-human-only; the overnight `review_dispatch` JSON contract stays separate.
- **No independent (out-of-band) hallucination verifier in the first cut** — see the accepted-risk constraint. The in-scope mitigations are the falsifiable `file:line` citation (Req 6) and the contract test (Req 10); the natural-bug regression fixture is the deferred tripwire.

## Edge Cases

- **Reviewer agent errors / times out / unparseable output** → `REVIEW_INCONCLUSIVE` (degradation signal 1).
- **Diff missing or empty** → `REVIEW_INCONCLUSIVE` (signal 2).
- **Reviewer surfaces findings but grounds none of them** → `REVIEW_INCONCLUSIVE` (signal 5) — closes the all-evidence-weak silent-approve hole.
- **A finding is `blocking` but evidence-weak (ungrounded)** → `REVIEW_INCONCLUSIVE` (signal 6) — an unverifiable blocker neither silently approves nor forces a possibly-hallucinated REQUEST_CHANGES.
- **A grounded `blocking` finding co-occurs with a degradation signal** → `REQUEST_CHANGES` (rule 1 precedes rule 2; a verified blocker dominates an incomplete review).
- **PR with only grounded non-blocking findings** → `APPROVE` with visible non-blocking comments.
- **A finding's quote cannot be located on the `+` side** → surfaced as `evidence-weak` with reason, counted in the footer's evidence-weak sub-count; never silently dropped.

## Changes to Existing Behavior

- **REMOVED**: four-way critic fan-out, Haiku triage stage, standing git-history `-p` firehose, standing prev-PR-comments critic, bug critic as a separate diff-only pass, the 821-line five-stage protocol, `evidence-ground.sh`, the `claude-opus-4-7` pin, per-label caps, the alphabetical tie-break, the three-axis rubric, the `suggestion (blocking)` label form, the unrun stability protocol.
- **MODIFIED**: verdict set gains `REVIEW_INCONCLUSIVE`; fail-open → fail-loud, derived deterministically from grounding status + severity (never a label string); ungroundable findings are surfaced as `evidence-weak` (previously silently dropped); the footer reports the model that ran and a grounded/evidence-weak split; output defaults to terminal plain-text (was GitHub-markdown); compliance checking demoted from a standing critic to "read CLAUDE.md if present" inside the single reviewer; model selection is session-default.
- **ADDED**: a single full-context reviewer dispatch; the deterministic verdict state machine as a testable unit; a contract test (`tests/`); falsifiable per-finding `file:line` citations; the two-vocabulary distinctness note.

## Technical Constraints

- **Hand-maintained plugin.** `cortex-pr-review` is in `HAND_MAINTAINED_PLUGINS` (`justfile:576`); edit `plugins/cortex-pr-review/` directly. There is NO canonical-plus-mirror — do not run `build-plugin` or look for a mirror. Keep the plugin classified hand-maintained (`.claude-plugin/plugin.json` `.name` non-empty) so `tests/test_drift_enforcement.sh` Subtest D still passes.
- **SKILL.md ≤500 lines** — the size cap (`tests/test_skill_size_budget.py`) covers this plugin SKILL.md. The L1-surface ratchet and `cortex-check-parity` do NOT. If folding protocol content threatens the cap, extract to `references/`.
- **Skill-path SP001/SP002 (ADR-0009).** The SKILL.md body resolves `${CLAUDE_SKILL_DIR}` and propagates the absolute path (or inlines content) into the dispatched reviewer prompt; no raw `${CLAUDE_SKILL_DIR}` or bare `references/*.md` consult-ref inside a subagent prompt; no bare-relative Read/execute paths. (The `cortex-check-skill-path` lint does not auto-trigger on plugin-only edits — manual authoring responsibility.)
- **Authoring discipline.** Prescribe What/Why not How; prefer structural separation over prose-only enforcement (the verdict gate is a testable unit per Req 7/10, not a prose plea); no new MUST/CRITICAL prose without the evidence artifact the MUST-escalation policy requires.
- **Model id.** Do not hardcode a model string; use session-default / highest-available. If a model id is ever needed, confirm the live id via the `claude-api` skill (current generation is Opus 4.8), do not copy the stale `claude-opus-4-7`.
- **Accepted risk (in-context grounding) — honest framing.** Deleting `evidence-ground.sh` removes the only *independent* quote-verifier; the reviewer now self-attests its own grounding (a self-grading conflict). Critically: the fail-loud contract and evidence-weak surfacing address the *false-negative / honest-miss* axis, NOT the *false-positive* axis a confidently-hallucinated-and-self-attested finding lives on — they do not mitigate hallucination, and the first cut ships **no out-of-band hallucination guard**. The in-scope mitigations that DO bear on hallucination are: (1) the falsifiable `file:line` citation (Req 6), which makes a fabricated "located" claim spot-checkable by the human reading the terminal output; (2) the contract test (Req 10), which pins the routing so a hallucinated finding cannot also corrupt the verdict logic. Accepted because the script was measured net-negative (it erased real findings), and System B's measured false-positive load was acceptable. Tripwire: a natural-bug regression fixture (fast-follow) plus a quote-fidelity calibration is the gate to re-add a fixed+tested grounder if hallucination-through is observed.

## Open Decisions

None. The four research open questions were resolved at spec time (user delegated the strategic calls): engine = bespoke owned harness; cross-PR = deferred to a fast-follow (revised from "flag-only" after the critical-review); grounder = delete + in-context with falsifiable citations and a contract test; local-`/code-review`-reads-`REVIEW.md` is moot under the owned-harness design.

## Decision Log

Revisions applied after the Specify-phase critical-review (4 parallel reviewers + Opus synthesis, 6 fix-invalidating objections, all accepted):

- **Closed the verdict fail-open hole.** Reworked the verdict derivation to key on *grounded* findings and added degradation signals (5) "surfaced findings but none grounded" and (6) "evidence-weak blocking finding," so an all-evidence-weak or ungrounded-blocker review routes to `REVIEW_INCONCLUSIVE` instead of a silent `APPROVE`.
- **Resolved the "surfaced finding" contradiction.** Defined grounded / evidence-weak / surfaced / dropped once in `## Grounding & Verdict Vocabulary`; evidence-weak findings are *surfaced* (not dropped), making the verdict deterministic.
- **Reframed the hallucination accepted-risk honestly** and added two in-scope mitigations (falsifiable `file:line` citations; the contract test), rather than deferring all hallucination handling.
- **Replaced absence-grep acceptance with positive checks** where possible: a bounded line threshold (Req 2), scoped greps (Req 1), word-boundary patterns (Req 8), and a runnable contract test (Req 10) as the positive behavioral check for the fail-loud routing.
- **Deferred Phase 2 (cross-PR lookup) entirely** to a fast-follow, removing the `external` grounding-class bifurcation and keeping the first cut a clean net deletion; re-phased the core rewrite into Structural collapse + Correctness & output contract.

## Proposed ADR

None considered. The build-vs-buy posture (own a thin single-reviewer harness over bought `/code-review`-class capability, rather than fork the upstream pipeline) is a real trade-off, but it is deliberately designed to be an easy retreat to pure-buy — it fails the "hard to reverse" criterion of the three-criteria ADR gate. The rationale is durably recorded in `cortex/research/pr-review-skill-audit/` and this lifecycle's `research.md`.
