---
name: critical-review
description: Adversarial review — 1–2 fresh reviewer agents on distinct angles, consolidated here. Pressure-tests a plan, spec, or research artifact.
argument-hint: "[<artifact-path>]"
---

# Critical Review

One new reviewer per angle. A reviewer has not seen the reasoning that produced the artifact. You then combine the findings and decide on each one.

## 1. Artifact

With an active lifecycle, take the most relevant of `cortex/lifecycle/{feature}/plan.md` → `spec.md` → `research.md`. Otherwise use the conversation. If nothing is clear enough to challenge, ask "What should I critically review?" Resolve it to an absolute path — reviewers read that exact path.

## 2. Angles

Derive **1 or 2** angles from this artifact, never more. Lean toward 2 at `high`/`critical` criticality. Each angle cites a specific section, claim, assumption, or design choice, and the two must not restate one concern. "Fragile assumptions" is not an angle; "the retry logic in §3 assumes idempotent endpoints, which breaks for the payment webhook in §5" is. Architectural, integration, and scope-creep risk are hints to vary the angles, not a checklist — favor the artifact's domain. More weaknesses than slots → take the most severe.

## 3. Project context

Build a `## Project Context` block for the reviewer prompts:

- the Overview from `cortex/requirements/project.md` (~250 words);
- a `**Project type:** {type}` prefix when `cortex/lifecycle.config.md` has a valid `type:`;
- the `## Language` section of `cortex/requirements/glossary.md`, word for word. Only that section: it defines words, and more context would tell the reviewer the earlier reasoning.

None available → omit the block.

## 4. Reviewers

Start one general-purpose agent per angle, in parallel. Send `${CLAUDE_SKILL_DIR}/references/reviewer-prompt.md` exactly, with `{artifact_path}`, `{angle name}`, `{angle description}`, and the context block filled in.

Parse each reply: split on the **last** `<!--findings-json-->` line and `json.loads` the rest. Require top-level `angle: str` and `findings: list`, each finding with `class ∈ {A,B,C}`, `finding`, `evidence_quote`. Malformed → warn `⚠ Reviewer {angle} emitted malformed JSON envelope ({reason})`, use its prose as `unstructured` findings, and leave the angle out of §6.

One of two fails → work from the other, prefixed "1 of 2 reviewer angles completed." Never wait on a silent agent. All fail → one general-purpose agent derives 1–2 angles itself, same output shape, prefixed `Note: reviewer dispatch failed, falling back to single reviewer`.

## 5. Consolidate

Do this yourself — the artifact is in your context. Check every `evidence_quote` against the artifact before you accept its class. Count any `measurement` as evidence.

**Downgrade A→B** when the `fix_invalidation_argument` is missing, repeats the finding with no causal link, names an adjacent gap, or hedges with no concrete failure path. Exception: a present `straddle_rationale` keeps it A. Report each class change as `Re-classified finding N from B→A: <rationale>` (or A→B).

Merge concerns that repeat across angles **within the same class** into one through-line. Note tensions where angles conflict. With two reviewers, write one coherent challenge, not a list per angle.

Output sections `## Objections` (A), `## Through-lines`, `## Tensions`, `## Concerns` (B and C). Use bullets that cite exact artifact text; skip empty sections. No A-class left → no `## Objections`, and open with: `No fix-invalidating objections after evidence re-examination. The concerns below are adjacent gaps or framing notes — do not read as verdict.`

## 6. B-class residue

With ≥1 B-class finding, write the file the morning report reads. The command finds the feature from the session id:

```bash
cortex-critical-review-write-residue --session-id "$LIFECYCLE_SESSION_ID" <<< "$PAYLOAD_JSON"
```

Payload: `ts`, `feature`, `artifact`, `synthesis_status: "ok"`, `reviewers: {completed, dispatched}`, `findings` (each `{class: "B", finding, reviewer_angle, evidence_quote}`). No B-class → skip. `state: no-context` / `unowned` / `ambiguous` → nothing was written; show the returned `note`.

## 7. Present and apply

Output the challenge unchanged. Then decide on each objection without waiting:

- **Apply** — the fix is unambiguous and confidence is high.
- **Dismiss** — the artifact already addresses it, or it misreads a stated constraint. Point at the artifact text.
- **Ask** — it turns on preference, scope, or real uncertainty. The default when unsure.

A resolution needs new evidence. For any empirical claim (latency, size, blast radius, baseline behavior) run the measurement; re-reading is not evidence.

Re-read the whole artifact. Write the updated version with every Apply included and everything else kept. Then summarize: Apply bullets that name the *direction* of change (strengthened / narrowed / clarified / added / removed / inverted), one **Dismiss: N objections** line (omit at zero), and all Asks in a single message.
