# Skill-Path Lint — Positive Fixtures

Each section below contains a case that SHOULD produce at least one violation
(SP001 for D1, SP002 for D2). The token strings are the literal pre-fix
production forms extracted from the eight Req-5 files and the three Class-1
files this lifecycle converted — not hand-invented strings. The surrounding
fixture scaffolding (the prompt fences, the `Read` directives) places each real
literal in the detector-triggering context it was bugged in.

## D1 — raw token / bare consult-ref inside a subagent prompt

### D1-pr-review-protocol-prompt-block

<!-- BEGIN SUBAGENT PROMPT -->

Score each surviving finding along the three axes defined in `rubric.md`:

Then apply the per-finding-type gate thresholds from `rubric.md`:

Drop-reason taxonomy (from `rubric.md`):

After the Verdict header, emit a flat list of Conventional Comments-labeled findings —
one per surviving finding. Each finding uses the labels defined in
`${CLAUDE_SKILL_DIR}/references/output-format.md`:

Follow the voice rules in `output-format.md`: no em-dashes, no AI-tell vocabulary, no
validation openers, no closing fluff.

<!-- END SUBAGENT PROMPT -->

### D1-critical-review-synthesizer-prompt

Before accepting any finding's class tag, re-read its `evidence_quote` field against the in-context Read result of `{artifact_path}` performed at the start of synthesis. For A-class findings, also re-read the `"fix_invalidation_argument"` field — apply the A→B downgrade rubric in `${CLAUDE_SKILL_DIR}/references/a-to-b-downgrade-rubric.md`. If the evidence supports a different class, re-classify and surface a note.

### D1-diagnose-phase-1-techniques-ref

<!-- BEGIN SUBAGENT PROMPT -->

See `${CLAUDE_SKILL_DIR}/references/techniques.md` (Backward Root-Cause Tracing).

<!-- END SUBAGENT PROMPT -->

## D2 — bare-relative Read/execute target

### D2-refine-clarify-ref

Read `../lifecycle/references/clarify.md` and follow its full protocol (§2–§7). Requirements loading within Clarify uses the shared tag-based loading protocol at `../lifecycle/references/load-requirements.md` (the citation chain is refine SKILL.md → lifecycle clarify.md → load-requirements.md).

### D2-discovery-load-requirements-ref

Load requirements using the shared tag-based loading protocol — read `../../lifecycle/references/load-requirements.md` and follow it. If no `cortex/requirements/` directory or files exist, note this and skip to §3.

### D2-lifecycle-clarify-critic-ref

Read `../../refine/references/clarify-critic.md` and follow its protocol. After the critic completes, the orchestrator writes the `clarify_critic` event to `cortex/lifecycle/{feature}/events.log` with the post-critic status.

### D2-lifecycle-overnight-check-cat-bash

```
cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active for this repo — wait for it to complete before creating an interactive worktree." "$(pwd)"
```
