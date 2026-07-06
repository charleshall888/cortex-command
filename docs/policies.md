# Cortex-Command Policies

Contributor-facing governance for changing the harness itself — skills, hooks, phase templates, and docs. Runtime conventions (commit flow, protected paths, repo structure) live in `CLAUDE.md`; read the section here that matches your task before authoring.

## Skill / phase authoring guidelines

Before classifying a phase boundary or gate as ceremonial, identify the user-facing affordance that boundary protects. A pause that looks redundant from the agent's perspective may be the only point where a human can redirect, reject, or reshape the work before the lifecycle advances. If the affordance genuinely provides no blocking value — because internals already enforce the constraint — document that reasoning explicitly rather than silently removing the boundary.

The concrete inventory of kept user pauses lives in `skills/lifecycle/references/kept-pauses.md`. The parity test at `tests/test_lifecycle_kept_pauses_parity.py` verifies that the implementation matches that inventory. When modifying phase sequencing, update both the kept-pauses.md inventory and the parity test together.

Prefer structural separation over prose-only enforcement for sequential gates (`CLAUDE.md` carries the one-line statement of this rule; this is the elaboration). A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction. Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low.

New skills go in `skills/` with `name` and `description` frontmatter; `when_to_use:` is optional and concatenated to `description:` for routing. A new skill's `description` + `when_to_use` SUM is bounded by the L1 surface budget — default ≤400B for non-cluster skills, enforced by `tests/test_l1_surface_ratchet.py`; see the "SKILL.md L1 surface ratchet" constraint in `cortex/requirements/project.md` for the cluster exemption and re-cap rule.

New global utilities ship via the `cortex-core` plugin's `bin/` directory; canonical source lives in the repo-root `bin/` and mirrors via dual-source enforcement.

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

## Tone/voice policy (Opus 4.7)

Cortex does not ship a tone directive; the Opus 4.7 voice regression is documented (Anthropic 4.7 release notes) but accepted, and tone is a personal-preference dimension that belongs in user-owned files per the cortex rules-only deployment convention. If you want a warmer Claude tone, try adding `Use a warm, collaborative tone. Acknowledge the user's framing before answering.` to your personal `~/.claude/CLAUDE.md` (which cortex never writes to per the rules-only deployment convention). Be aware: per the support.tools 'Claude Code System Prompt Architecture' analysis cited in research.md, CLAUDE.md tone overrides have inconsistent leverage against Claude Code's built-in system-prompt tone section — the structurally strongest remediation is at the system-prompt layer (output styles or `--system-prompt` flag), which cortex does not currently ship. The user-self-action recommendation is offered as a low-cost attempt with documented uncertainty about efficacy; if it fails to shift tone for you, the cited claim is empirically supported and the structurally-strong path remains unbuilt.

Re-evaluation triggers: (a) Anthropic ships a model release that further regresses tone; (b) an empirical test of rules-file tone leverage under 4.7+ returns a positive result (i.e., a tone directive in `~/.claude/rules/*.md` measurably shifts user-facing output); (c) Anthropic ships an officially-supported tone-control mechanism (e.g., output-style modes shipped to Claude Code) that makes Alternatives F/G/J structurally feasible. Cross-refs: ticket #91, epic #82, support.tools article cited in research.md.
