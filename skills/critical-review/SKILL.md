---
name: critical-review
description: Adversarial review — dispatches 1–2 reviewer agents on distinct angles, then synthesizes. Pressure-tests a plan, spec, or research artifact.
argument-hint: "[<artifact-path>]"
---

# Critical Review

One fresh reviewer per angle — no anchoring to the reasoning that produced the artifact — then a synthesis pass.

## 1. Artifact

An active lifecycle → the most relevant of `cortex/lifecycle/{feature}/plan.md` → `spec.md` → `research.md`; otherwise conversation context. Nothing clear enough to challenge → ask "What should I critically review?" Resolve to an absolute path — reviewers read that literal path.

## 2. Angles

Derive them here, from this artifact. **1 or 2** — a hard ceiling; weight toward 2 at `high`/`critical` criticality. Each angle cites a specific section, claim, assumption, or design choice, and no two rephrase one concern. "Fragile assumptions" is not an angle; "the retry logic in §3 assumes idempotent endpoints, which breaks for the payment webhook in §5" is. Architectural, integration, and scope-creep risk are a diversity nudge, not a checklist — weight toward the artifact's domain. More weaknesses than slots → highest severity wins.

## 3. Project context

A `## Project Context` block for the reviewer prompts: `cortex/requirements/project.md`'s Overview (~250 words), a `**Project type:** {type}` prefix from `cortex/lifecycle.config.md` when it carries a valid `type:`, and `cortex/requirements/glossary.md`'s `## Language` section verbatim (only that section — vocabulary is definitional, broader context would dilute the fresh-eyes stance). None available → omit the block.

## 4. Reviewers

One general-purpose agent per angle, in parallel, with `${CLAUDE_SKILL_DIR}/references/reviewer-prompt.md` verbatim (`{artifact_path}`, `{angle name}`, `{angle description}`, and the context block substituted).

Extract each envelope: split on the **last** `<!--findings-json-->` line, `json.loads` the tail, require top-level `angle: str` and `findings: list` with each finding carrying `class ∈ {A,B,C}`, `finding`, `evidence_quote`. Malformed → warn `⚠ Reviewer {angle} emitted malformed JSON envelope ({reason})`, pass its prose to the synthesizer marked `unstructured`, leave the angle out of §6.

One of two fails → synthesize from the survivor, prefixed "1 of 2 reviewer angles completed." Never wait on a silent agent. All fail → one general-purpose agent derives 1–2 angles itself, same output shape, prefixed `Note: reviewer dispatch failed, falling back to single reviewer`; skip synthesis.

## 5. Synthesize

One synthesizer with `${CLAUDE_SKILL_DIR}/references/synthesizer-prompt.md` verbatim, findings substituted. This is the judgment step — weigh the model accordingly.

## 6. B-class residue

With ≥1 B-class finding, write the sidecar the morning report reads (the verb resolves the feature from the session id):

```bash
cortex-critical-review-write-residue --session-id "$LIFECYCLE_SESSION_ID" <<< "$PAYLOAD_JSON"
```

Payload: `ts`, `feature`, `artifact`, `synthesis_status` (`ok`|`failed`), `reviewers: {completed, dispatched}`, `findings` (each `{class: "B", finding, reviewer_angle, evidence_quote}`). Zero B-class → skip. `state: no-context` / `unowned` / `ambiguous` → nothing written; relay the returned `note`. Synthesis failure still writes, with `synthesis_status: "failed"` and the reviewers' own B-class findings.

## 7. Present and apply

Output the synthesis as-is. Then disposition each objection without waiting: **Apply** when the fix is unambiguous and confidence high, **Dismiss** when the artifact already addresses it or it misreads a stated constraint, **Ask** when it turns on preference, scope, or real uncertainty (default for ambiguity). Dismissals point at artifact text; resolutions rest on new evidence — for any empirical claim (latency, size, blast radius, baseline behavior) run the measurement; re-reading is not evidence.

Re-read the artifact in full, write the updated version with every Apply incorporated and everything else preserved, and summarize: Apply bullets naming the *direction* of change (strengthened / narrowed / clarified / added / removed / inverted), one **Dismiss: N objections** line (omit at zero), and all Asks in a single message.
