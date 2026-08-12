# Cortex-Command Policies

Contributor-facing governance for changing the harness itself — skills, hooks, phase templates, and docs. Runtime conventions (commit flow, protected paths, repo structure) live in `CLAUDE.md`; read the section here that matches your task before authoring.

## Skill / phase authoring guidelines

Before classifying a phase boundary or gate as ceremonial, identify the user-facing affordance that boundary protects. A pause that looks redundant from the agent's perspective may be the only point where a human can redirect, reject, or reshape the work before the lifecycle advances. If the affordance genuinely provides no blocking value — because internals already enforce the constraint — document that reasoning explicitly rather than silently removing the boundary.

The kept-pause taxonomy's durable source of truth is `skills/build/references/kept-pauses-data.toml` — one row per `<!-- pause: <slug> <kind> -->` marker in skill prose. `cortex-generate-kept-pauses` renders the human-readable inventory `skills/build/references/kept-pauses.md` from it (never hand-edit the generated file), and the parity test at `tests/test_lifecycle_kept_pauses_parity.py` enforces marker/data set-equality, inventory freshness, and per-kind semantic anchors (the first two are structural and exemplary; the anchor check is a prose assertion, grandfathered under "No tests on skill prose" below and not a pattern to copy). When modifying phase sequencing, add or remove the `<!-- pause: -->` marker in prose, update the matching row in the data file, then re-run the generator (`just kept-pauses`) and commit the regenerated inventory.

Prefer structural separation over prose-only enforcement for sequential gates (`CLAUDE.md` carries the one-line statement of this rule; this is the elaboration). A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction. Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low.

New skills go in `skills/` with `name` and `description` frontmatter; `when_to_use:` is optional and concatenated to `description:` for routing. A new skill's `description` + `when_to_use` SUM is bounded by the L1 surface budget — default ≤400B for non-cluster skills, enforced by `tests/test_l1_surface_ratchet.py`; see the "SKILL.md L1 surface ratchet" constraint in `cortex/requirements/project.md` for the cluster exemption and re-cap rule.

Reference prose is ratcheted down-only: every `references/` directory (canonical `skills/<name>/` and hand-maintained plugin skills) carries a `size-pin.txt` byte pin, enforced by `tests/test_reference_size_ratchet.py`. Growth over the pin fails — apply verb-first (behavior moves into CLI verbs; prose keeps only control flow) rather than raising the pin. Lowering is always allowed and expected: after any trim, run `just ratchet-refs` to lock in the new floor (it seeds missing pins — the first commit of a references directory sets its pin — and lowers stale ones, never raises). Growth a correctness fix genuinely needs takes an in-file exception: hand-raise the pin with a `# raised: <reason ≥30 chars>, lifecycle-id=<NNN>, date=<YYYY-MM-DD>` line, and re-ratchet afterward.

New global utilities ship via the `cortex-core` plugin's `bin/` directory; canonical source lives in the repo-root `bin/` and mirrors via dual-source enforcement.

### No tests on skill prose

No test asserts that a phrase, sentence, or instruction is *present* in the natural-language body of `skills/**/SKILL.md` or `skills/**/references/*.md` (`CLAUDE.md` carries the one-line statement; this is the elaboration).

The reason is that such a test can only pass by keeping the words. It inverts the direction every other prose rule here points: verb-first says behavior leaves prose, the down-only size ratchet says prose shrinks, and a phrase assertion says prose must not change. Under it, the cheapest way to stay green is to add sentences rather than remove them, so the tests that claim to guard skill quality become the mechanism that grows skill bloat. It also verifies nothing — the model reading the instruction decides the behavior; the test proves only that the bytes are on disk.

So the question to ask of any assertion is which direction it pushes prose. A presence pin can only be satisfied by keeping or adding words. An **absence** assertion — `MUST decide` does not appear in the gate block, the retired verb literal is gone from `skills/refine/**`, the relocated section is no longer resident — is satisfied by deleting words, and is the enforcement arm of a trim already made. Absence assertions are permitted and encouraged: they are how a removal stays removed. Same mechanism, opposite gradient.

Still testable, because these read skill markdown as structure rather than as instructions and none of them get cheaper by adding words: presence and shape of frontmatter fields, the L1 surface budget, the SKILL.md line cap and `references/` byte pins, `${CLAUDE_SKILL_DIR}` resolution, dual-source mirror equality, that a path or file a skill names actually resolves, and freshness of generated files against their source of truth.

The line is what the assertion is *about*, not which part of the file it reads. `description:` is frontmatter, but a test requiring specific trigger phrases inside it is still a phrase assertion — it reserves a share of a capped budget that cannot be traded away, so the L1 cap can only ever be met by cutting the non-mandated words around it. Bound the description by size and require the field exist; do not pin its wording. The same reading applies to `when_to_use:` and to handoff-schema field names sourced from a fixture corpus.

This was executed on 2026-08-11: `tests/test_skill_descriptions.py`, `tests/test_skill_routing_disambiguation.py`, and `tests/fixtures/skill_trigger_phrases.yaml` are deleted. Their 34 pinned phrases were holding the model-facing description surface at 4,546B; rewriting against size alone took it to 1,353B. `tests/test_l1_surface_ratchet.py` is now the sole guard — it bounds size and fails a skill with no budget row, which is the shape this section prescribes.

Greps for a machine token in a skill body — `cortex-refine start`, `EnterWorktree(` — are the largest class of pin in this repo and split on one question: does the token's *omission* fail silently?

Usually it does not, and the pin is redundant: make the verb error when its precondition is unmet, and the deletion the grep was watching for surfaces at runtime, in the consumer repo where it matters. This is also why the contract lint (#253) survives while a presence grep does not — the lint validates the *invocation shape* of whatever callsites exist, so it costs nothing to satisfy and stays silent when a callsite is legitimately removed.

Where omission genuinely is silent, a bare **existence** assertion on the token is permitted, under the same bar as any enforcement gate: name the specific failure it prevents, in the test's docstring. Deleting the `EnterWorktree(` call from `skills/build/` is the worked example — the implement phase then runs in the main tree and nothing raises. An omission is the one failure a runtime check cannot catch, because there is no code left to run.

That licence covers existence only. **Proximity, ordering, occurrence-count, and section-placement constraints are out** — `EnterWorktree(` within ±60 lines of `create_worktree`, a token appearing exactly once, a heading positioned after another. These pin layout rather than behavior: they block reorganization, they fail on edits that change nothing a consumer sees, and no runtime failure corresponds to the arrangement they enforce. If the arrangement truly matters, the two things belong in one verb, not two paragraphs that a test staples together.

A test that *parses* a data table out of reference markdown — the research fan-out matrix, the invocation grammar — is not a prose assertion and is not banned by this rule. But the table's presence in prose is itself the defect: durable data belongs in a data file the prose renders from, per the `kept-pauses-data.toml` precedent. Move it when you next touch it, and point the test at the data.

To guarantee a behavior the prose currently describes, move the behavior into a CLI verb and test the verb's output. ADR-0035 is the worked example: the reviewer brief moved out of reference prose into `cortex-lifecycle-review-brief`, and its tests pin the verb's contract rather than the skill's sentences. Prose that cannot move into a verb is control flow, and control flow is verified by running the lifecycle, not by grepping it.

This rule is not retroactive. An audit on 2026-08-07 found ~73 test functions across 28 files asserting on skill markdown text; the share that this rule actually bans is materially smaller and was not counted, because much of that population is absence assertions, which the rule endorses. Nothing is swept out on the rule's account, and several of the pins document themselves as deliberate. But they hold no standing under it: when a trim breaks one, delete the assertion rather than restore the wording, and do not cite an existing pin as precedent for a new one. The rule is enforced at review, not by a lint — a lint over the test suite would be new machinery needing its own named evidence, and would itself be a test asserting on test source.

## Design principle: prescribe What and Why, not How

When authoring skills, hooks, lifecycle templates, or any harness instruction, describe decisions to be made, gates to enforce, output shapes required, and the intent behind each (the What and Why). Resist prescribing step-by-step method (the How).

The reasoning: capable models (Opus 4.7 and later) determine method themselves given clear decision criteria and intent. Spelling out procedure wastes tokens, constrains agent judgment on details the spec author cannot fully anticipate, and tends to produce brittle rails that break when model behavior evolves.

This principle is the conceptual partner to the MUST-escalation policy below: both protect against over-specification — the escalation policy guards against over-constraining model behavior with imperative language; this principle guards against over-constraining it with procedural narration.

## MUST-escalation policy (post-Opus 4.7)

Default to soft positive-routing phrasing for new authoring under epic #82's post-4.7 harness adaptation; pre-existing MUST language is grandfathered until specifically audited (per #85). To add a new MUST/CRITICAL/REQUIRED escalation, you must include in the commit body OR PR description a link to one evidence artifact: (a) `cortex/lifecycle/<feature>/events.log` path + line of an F-row showing Claude skipped the soft form, OR (b) a commit-linked transcript URL or quoted excerpt. Without one of these artifact links, the escalation is rejected at review.

Before adding or restoring a MUST, run a dispatch with `effort=high` (and `effort=xhigh` if effort=high also fails) on a representative case and record the result. Escalate to MUST only when effort=high (and xhigh) demonstrably fail to resolve the observed failure. Record the effort attempt in the escalation note: cite the events.log entry showing the effort=high run + outcome, OR paste the transcript excerpt. If the dispatch path does not currently expose `effort` as a tunable parameter, cite the specific dispatch path file and file a separate wiring ticket — do not escalate to MUST as a workaround.

OQ3's escalation rule applies to all observed-failure types: correctness, control-flow, routing, latency, format-conformance, tool-selection, hallucination, and any other behavior-correctness failure mode. The single exception is **tone perception** — failures where the complaint is about Claude's voice, conciliatoriness, validation phrasing, or emoji usage rather than an action Claude omitted, mis-routed, or mis-executed. Tone perception is governed by the tone/voice policy below; all other failure types are OQ3-eligible escalation triggers.

Re-evaluation triggers: (a) Anthropic publishes guidance reversing the 'soften MUST' posture for any future model; (b) the dispatch-path effort parameter exposed by the SDK changes shape such that R3's effort-first clause is no longer applicable. Cross-refs: ticket #91 (this policy), epic #82, audit #85.

## Overnight docs source of truth

`docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/internals/pipeline.md` owns pipeline-module internals, `docs/internals/sdk.md` owns SDK model-selection mechanics, and `docs/internals/auto-update.md` owns the plugin/CLI auto-update flow (two-layer architecture, component map, release ritual). When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content.

## Lifecycle served-loop docs source of truth

`docs/lifecycle-transition-table.md` is the **generated** human-readable rendering of the wheel-owned lifecycle state machine — never hand-edit it; re-run `cortex-lifecycle-describe --write` and let the CI golden diff enforce parity with `cortex_command/lifecycle/transition_table.py`. `docs/rollforward-exit.md` owns the operator-facing roll-forward exit procedure for the served `next`/`advance` loop (the standing exit that replaces the forfeited prose-side revert per ADR-0025); its trigger, named owner, and vocabulary-quarantine steps operationalize ADR-0024's coexistence policy. Both are canonical for their topic — link to them from other docs rather than restating the transition table or the exit steps.

## Dashboard docs source of truth

`docs/dashboard.md` owns dashboard behavior — the bind address, the panel inventory, the polling cadences, and the data sources the dashboard reads — while `cortex/requirements/observability.md` owns the area's requirements: what must be true of the dashboard and the acceptance criteria that verify it. A ticket that adds a panel updates the owning doc in the same phase that adds the panel, not in a follow-up. Dashboard claims appearing in overnight-owned docs such as `docs/overnight-operations.md` defer to `docs/dashboard.md` rather than to the Overnight map above; update the owner and link from the others rather than duplicating content.

## Tone/voice policy (Opus 4.7)

Cortex does not ship a tone directive; the Opus 4.7 voice regression is documented (Anthropic 4.7 release notes) but accepted, and tone is a personal-preference dimension that belongs in user-owned files per the cortex rules-only deployment convention. If you want a warmer Claude tone, try adding `Use a warm, collaborative tone. Acknowledge the user's framing before answering.` to your personal `~/.claude/CLAUDE.md` (which cortex never writes to per the rules-only deployment convention). Be aware: per the support.tools 'Claude Code System Prompt Architecture' analysis cited in research.md, CLAUDE.md tone overrides have inconsistent leverage against Claude Code's built-in system-prompt tone section — the structurally strongest remediation is at the system-prompt layer (output styles or `--system-prompt` flag), which cortex does not currently ship. The user-self-action recommendation is offered as a low-cost attempt with documented uncertainty about efficacy; if it fails to shift tone for you, the cited claim is empirically supported and the structurally-strong path remains unbuilt.

Re-evaluation triggers: (a) Anthropic ships a model release that further regresses tone; (b) an empirical test of rules-file tone leverage under 4.7+ returns a positive result (i.e., a tone directive in `~/.claude/rules/*.md` measurably shifts user-facing output); (c) Anthropic ships an officially-supported tone-control mechanism (e.g., output-style modes shipped to Claude Code) that makes Alternatives F/G/J structurally feasible. Cross-refs: ticket #91, epic #82, support.tools article cited in research.md.
