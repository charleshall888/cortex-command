---
name: critical-review
description: Parallel adversarial review — dispatches reviewer agents on distinct challenge angles, then synthesizes their findings. Use when user says "critical review", "pressure test", "adversarial review", or "challenge from multiple angles". Auto-triggers in the lifecycle for Complex + medium/high/critical features before spec approval.
when_to_use: "Use when you want to stress-test a plan, spec, or research artifact before committing (\"poke holes in the plan\"). Different from /devils-advocate — devils-advocate runs inline in the current agent context for a lightweight solo deliberation; critical-review dispatches parallel sub-agents and synthesizes findings."
argument-hint: "[<artifact-path>]"
---

# Critical Review

One fresh reviewer agent per angle, dispatched in parallel — no anchoring to the reasoning that produced the artifact — then a synthesis pass.

## Step 1: Find the artifact

If a lifecycle is active, take the most relevant of `cortex/lifecycle/{feature}/plan.md` → `spec.md` → `research.md`, in that order; otherwise use conversation context. Nothing clear enough to challenge → ask "What should I critically review?" first. Resolve it to an absolute path — reviewers read that literal path.

## Step 2: Derive angles

Derive the challenge angles from the artifact yourself, in this conversation. **Default 2**; escalate to 3–4 only when criticality is `high`/`critical`, or the artifact introduces claims its inputs lacked (mechanisms, measured figures, or verification approaches absent from the spec or research it derives from).

Each angle must cite a specific section, claim, assumption, or design choice in *this* artifact, and no two may re-phrase the same concern. "Fragile assumptions" alone is not an angle; "the retry logic in §3 assumes idempotent endpoints, which breaks for the payment webhook in §5" is. Architectural risk, integration risk, and scope creep are a diversity nudge, not a checklist — weight toward the failure modes of whatever domain the artifact lives in.

## Step 3: Assemble project context

Build a `## Project Context` block for the reviewer prompts from `cortex/requirements/project.md`'s Overview (~250 words), a `**Project type:** {type}` prefix from `cortex/lifecycle.config.md` when it carries a valid `type:`, and `cortex/requirements/glossary.md`'s `## Language` section verbatim. None available → omit the section entirely, no placeholder.

> **Deliberately narrow.** Critical-review skips the tag-based requirements-loading protocol other skills use — broader project context (priorities, area tags, decisions) would dilute the fresh-eyes stance. Vocabulary is admitted because it's definitional, not reasoning-shaped. Read only `## Language`, not `## Relationships`, `## Example dialogue`, or `## Flagged ambiguities`. Do not "fix" this by wiring tag-based loading into the dispatch path.

## Step 4: Dispatch reviewers

One general-purpose agent per angle, all in parallel, using `${CLAUDE_SKILL_DIR}/references/reviewer-prompt.md` verbatim with `{artifact_path}`, `{angle name}`, `{angle description}`, and the Step 3 context block substituted.

Extract each reviewer's envelope: split on the **last** `<!--findings-json-->` line, `json.loads` the tail, and assert top-level `angle: str` and `findings: list`, each finding carrying `class ∈ {A,B,C}`, `finding`, and `evidence_quote`. The envelope is the reviewer's whole deliverable, so a malformed one leaves nothing to salvage — warn `⚠ Reviewer {angle} emitted malformed JSON envelope ({reason})` and drop it.

Some reviewers failing → synthesize from the rest and prefix "N of M reviewer angles completed." Never wait on a silent agent. *All* failing → dispatch a single general-purpose agent to derive 3–4 angles itself and produce the same output shape, prefix `Note: parallel dispatch failed, falling back to single reviewer`, and skip synthesis.

## Step 5: Synthesize

Dispatch one synthesizer with `${CLAUDE_SKILL_DIR}/references/synthesizer-prompt.md` verbatim, with the reviewer findings substituted. Synthesis is the judgment step of this skill — weigh the model accordingly.

## Step 6: Write B-class residue

With ≥1 B-class finding, write the sidecar the morning report reads — the verb resolves the feature from the session id itself:

```bash
cortex-critical-review-write-residue --session-id "$LIFECYCLE_SESSION_ID" <<< "$PAYLOAD_JSON"
```

Payload: `ts`, `feature`, `artifact`, `synthesis_status` (`ok`|`failed`), `reviewers: {completed, dispatched}`, and `findings` — each `{class: "B", finding, reviewer_angle, evidence_quote}`. Zero B-class findings → skip the call, no file, no note. `state: no-context` (no lifecycle at all), `state: unowned` (lifecycles exist, none owned by this session — the findings are NOT persisted), or `state: ambiguous` (several matched) → nothing written; relay the returned `note` verbatim. Synthesis failure still writes, with `synthesis_status: "failed"` and the B-class findings from the reviewers' own envelopes.

## Step 7: Present and apply

Output the synthesis directly. Do not soften or editorialize.

Then work through each objection independently, without waiting for the user: **Apply** when the fix is unambiguous and confidence is high, **Dismiss** when the artifact already addresses it or it misreads a stated constraint, **Ask** when it turns on user preference, a scope decision, or genuine uncertainty. Default ambiguous to Ask.

Dismissals must point at artifact text, not memory; resolutions must rest on new evidence, not prior reasoning. For any empirical claim — latency, file size, blast radius, baseline behavior — run the actual measurement before classifying; re-reading the artifact is not new evidence.

Then re-read the artifact in full, write the updated version with every Apply incorporated and everything else preserved, and present a compact summary: Apply bullets describing the *direction* of change (each opening with strengthened / narrowed / clarified / added / removed / inverted), one **Dismiss: N objections** line (omitted at zero), and all Ask items consolidated into a single message.
