---
name: critical-review
description: Parallel adversarial review — dispatches reviewer agents on distinct challenge angles, then synthesizes findings with an Opus agent. Use when user says "critical review", "pressure test", "adversarial review", or "challenge from multiple angles". Auto-triggers in the lifecycle for Complex + medium/high/critical features before spec and plan approval.
when_to_use: "Use when you want to stress-test a plan, spec, or research artifact before committing (\"poke holes in the plan\"). Different from /devils-advocate — devils-advocate runs inline in the current agent context for a lightweight solo deliberation; critical-review dispatches parallel sub-agents and synthesizes findings."
argument-hint: "[<artifact-path>]"
inputs:
  - "artifact-path: string (optional) — path to plan.md, spec.md, or research.md to review; if omitted, auto-detect from current lifecycle"
outputs:
  - "Synthesis prose presented in conversation"
  - "Optional residue write at cortex/lifecycle/{feature}/critical-review-residue.json"
preconditions:
  - "Run from project root"
  - "Artifact path resolves to an existing markdown file"
---

# Critical Review

Derives challenge angles from the artifact and domain context, dispatches one fresh reviewer agent per angle in parallel, then synthesizes with an Opus agent. Each reviewer works **fresh-eyes** — full independence, no anchoring to the reasoning that produced the artifact.

## Step 1: Find the Artifact

If a lifecycle is active, read the most relevant artifact (`cortex/lifecycle/{feature}/plan.md` → `spec.md` → `research.md`, in that order); otherwise use conversation context. If nothing is clear enough to challenge, ask "What should I critically review?" first.

## Step 2: Review Setup and Dispatch

### Step 2a: Load Domain Context

Assemble a `## Project Context` block for the reviewer prompts from:

1. `cortex/requirements/project.md` — the **Overview** section (or the first top-level section if none is labeled Overview), up to ~250 words.
2. `cortex/lifecycle.config.md` — a valid `type:` field (present, non-empty, uncommented) as a one-line prefix `**Project type:** {type}` before the overview.
3. `cortex/requirements/glossary.md` — the `## Language` section verbatim, inline. Read **only** that section — NOT `## Relationships`, `## Example dialogue`, or `## Flagged ambiguities` (those approach existing-reasoning territory). Skip silently when absent.

None of these available → **omit the `## Project Context` section entirely** — no empty placeholder.

> **Requirements loading: deliberately exempt.** Critical-review narrows its context to `cortex/requirements/project.md`'s Overview (~250 words) and the glossary `## Language` section, and does NOT participate in the tag-based requirements-loading protocol other skills use. This keeps reviewers on adversarial challenge — broader project context (priorities, area tags, decisions) would dilute that focus and break the **fresh-eyes** stance. Vocabulary is admitted because it is definitional, not reasoning-shaped. Do not "fix" this exemption by wiring tag-based loading into the dispatch path.

### Step 2a.5: Pre-Dispatch (atomic path + SHA pin)

Fuse path validation and SHA-256 computation before any dispatch: `cortex-critical-review prepare-dispatch <artifact-path> [--feature <name>]`. Bind `{artifact_path}` and `{artifact_sha256}` from the stdout JSON and substitute both into every downstream dispatch site. Non-zero exit → surface its stderr verbatim and stop, dispatching no agent. Full invocation contract and exit-code routing: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2b: Derive Angles

The orchestrator (in main conversation context) derives the challenge angles from the artifact (typically 3-4; count per the angle-menu rule). Each must be **distinct** (no two are re-phrasings of each other) and **reference specific sections or claims in the artifact** (not generic category labels). Pick angles most likely to reveal real problems for this specific artifact. Representative examples + the angle-count rule: `${CLAUDE_SKILL_DIR}/references/angle-menu.md`.

### Step 2c: Dispatch Parallel Reviewers

Dispatch one general-purpose agent per angle as a parallel Task sub-task — all simultaneously, don't wait for one before launching the next. Each receives the canonical reviewer prompt from `${CLAUDE_SKILL_DIR}/references/reviewer-prompt.md` verbatim, with `{artifact_path}`, `{artifact_sha256}`, `{angle name}`, `{angle description}`, and the Step 2a Project Context block substituted at runtime. That prompt directs the reviewer to emit `READ_OK: <path> <sha>` before findings, then class-tagged findings with a `<!--findings-json-->` JSON envelope.

#### Failure Handling

- **Partial** (some agents succeed, some fail) → proceed to Step 2d with the successful findings only, prefixing the synthesis per the partial-coverage rule in `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.
- **Total** (all fail) → fall back to one general-purpose agent with the canonical fallback prompt from `${CLAUDE_SKILL_DIR}/references/fallback-reviewer-prompt.md` (substituting `{artifact_path}`, `{artifact_sha256}`). Output its result directly with no Step 2d synthesis, prefixed `Note: parallel dispatch failed, falling back to single reviewer`, then proceed to Step 3.

### Step 2c.5: Sentinel-First Verification Gate

After parallel reviewers return, run a two-phase gate before Step 2d synthesis: Phase 1 verifies each reviewer's sentinel via `cortex-critical-review check-artifact-stable`; Phase 2 extracts the `<!--findings-json-->` envelope only for Phase-1 passers. If every reviewer is excluded (all exit-3), surface verbatim and do NOT synthesize: `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.` Full route table, `record-exclusion` contract, and Phase 2 schema assertions: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2d: Opus Synthesis

After parallel reviewers (or the successful subset) clear Step 2c.5, resolve the synthesizer model by running `cortex-resolve-model --role synthesizer` (no `--criticality` flag and no lifecycle-state read — the standalone critical-review path may have no lifecycle session, so a missing state must never block synthesis); on nonzero exit, halt and escalate rather than guessing or substituting a model. Read `${CLAUDE_SKILL_DIR}/references/a-to-b-downgrade-rubric.md` and substitute its full content into `{a_to_b_rubric}`, then dispatch one synthesizer agent with the resolved model and the canonical prompt from `${CLAUDE_SKILL_DIR}/references/synthesizer-prompt.md` verbatim, with `{artifact_path}`, `{artifact_sha256}`, `{a_to_b_rubric}`, and the reviewer-findings payload substituted at runtime. The prompt directs the synthesizer to Read the artifact once at start and emit `SYNTH_READ_OK: <path> <sha>` in output before per-finding analysis.

The synthesizer applies the **A→B downgrade rubric** to each A-class finding's `"fix_invalidation_argument"` field — definitions, trigger semantics, and 8 worked examples (4 ratify / 4 downgrade across the absent/restates/adjacent/vague triggers) are inlined via `{a_to_b_rubric}`. Decision gates: count A-class from well-formed envelopes only (untagged prose excluded from the A tally); zero A-class → no `## Objections` section. Output sections: `## Objections`, `## Through-lines`, `## Tensions`, `## Concerns` — bullets only, skip empty sections, no balanced/endorsement sections.

### Step 2d.5: Post-Synthesis (atomic SHA verification)

Pipe the synthesizer's full output through `cortex-critical-review check-synth-stable --feature <name> --expected-sha <hex>` before surfacing anything. On exit 3 (sentinel absent or SHA mismatch), do NOT surface the prose — relay the subcommand's stdout verbatim and do NOT proceed to Step 2e. Full contract and resolution instructions: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2e: Residue Write

After synthesis (or a Step 2c.5 pass-through), atomically write any B-class findings to a sidecar JSON for the morning report; skip silently when zero B-class remain. Resolve `{feature}` from `$LIFECYCLE_SESSION_ID` against `cortex/lifecycle/*/.session`; on zero- or multiple-match, emit the documented note and skip. The `cortex-critical-review-write-residue` console-script does the tempfile + `os.replace` write to `cortex/lifecycle/{feature}/critical-review-residue.json`. Resolver, payload schema (R4), and gating: `${CLAUDE_SKILL_DIR}/references/residue-write.md`.

## Step 3: Present

Output the review result directly. Do not soften or editorialize.

## Step 4: Apply Feedback

Immediately after presenting the synthesis, work through each objection independently — do not wait for the user.

- **Apply** when the fix is unambiguous and confidence is high.
- **Dismiss** when the artifact already addresses the objection or it misreads stated constraints.
- **Ask** when the fix involves user preference, a scope decision, or genuine uncertainty.

Default ambiguous to Ask. Anchor-checks: dismissals must point to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning. For any empirical claim (latency, file size, blast radius, baseline behavior), run the actual measurement (`time`, `wc -c`, grep) before classifying Apply/Dismiss — re-reading the artifact text is not new evidence.

Then: (1) re-read the artifact in full; (2) write the updated artifact with all Apply fixes incorporated, preserving everything untouched; (3) present a compact summary — Apply bullets describe the direction of change (not the objection text), each opening with one of strengthened / narrowed / clarified / added / removed / inverted; a single **Dismiss: N objections** line (omit when N = 0); and any Ask items consolidated into one message.
