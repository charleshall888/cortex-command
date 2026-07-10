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

Dispatches one fresh reviewer agent per angle in parallel — full independence, no anchoring to the reasoning that produced the artifact — then synthesizes with an Opus agent.

## Step 1: Find the Artifact

If a lifecycle is active, read the most relevant artifact (`cortex/lifecycle/{feature}/plan.md` → `spec.md` → `research.md`, in that order); otherwise use conversation context. If nothing is clear enough to challenge, ask "What should I critically review?" first.

## Step 2: Review Setup and Dispatch

### Step 2a: Load Domain Context

Assemble a `## Project Context` block for the reviewer prompts from:

1. `cortex/requirements/project.md` — the **Overview** section (or the first top-level section if none is labeled Overview), up to ~250 words.
2. `cortex/lifecycle.config.md` — a valid `type:` field (present, non-empty, uncommented) as a one-line prefix `**Project type:** {type}` before the overview.
3. `cortex/requirements/glossary.md` — the `## Language` section verbatim, inline. Read **only** that section — NOT `## Relationships`, `## Example dialogue`, or `## Flagged ambiguities` (those approach existing-reasoning territory). Skip silently when absent.

None of these available → **omit the `## Project Context` section entirely** — no empty placeholder.

> **Requirements loading: deliberately exempt.** Critical-review narrows its context to `cortex/requirements/project.md`'s Overview and the glossary `## Language` section, skipping the tag-based requirements-loading protocol other skills use — broader project context (priorities, area tags, decisions) would dilute the **fresh-eyes** stance. Vocabulary is admitted because it's definitional, not reasoning-shaped. Do not "fix" this by wiring tag-based loading into the dispatch path.

### Step 2a.5: Pre-Dispatch (atomic path + SHA pin)

Fuse path validation and SHA-256 computation before any dispatch via `cortex-critical-review prepare-dispatch <artifact-path> [--feature <name>]`, binding `{artifact_path}`/`{artifact_sha256}` for every downstream dispatch site. Full invocation contract and exit-code routing: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2b: Derive Angles

The orchestrator (main conversation context) derives the challenge angles from the artifact — distinct, artifact-specific, and picked to reveal real problems for this artifact, not generic category labels. Count and acceptance criteria: `${CLAUDE_SKILL_DIR}/references/angle-menu.md`.

### Step 2c: Dispatch Parallel Reviewers

Dispatch one general-purpose agent per angle as a parallel Task sub-task, all simultaneously, using the canonical reviewer prompt from `${CLAUDE_SKILL_DIR}/references/reviewer-prompt.md` verbatim, substituting `{artifact_path}`, `{artifact_sha256}`, `{angle name}`, `{angle description}`, and the Step 2a Project Context block at runtime.

#### Failure Handling

- **Partial** (some agents succeed, some fail) → proceed to Step 2d with the successful findings only, prefixing the synthesis per the partial-coverage rule in `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.
- **Total** (all fail) → fall back to one general-purpose agent with the canonical fallback prompt from `${CLAUDE_SKILL_DIR}/references/fallback-reviewer-prompt.md` (substituting `{artifact_path}`, `{artifact_sha256}`). Output its result directly with no Step 2d synthesis, prefixed `Note: parallel dispatch failed, falling back to single reviewer`, then proceed to Step 3.

### Step 2c.5: Sentinel-First Verification Gate

After parallel reviewers return, run the two-phase verification gate (sentinel check, then envelope extraction) before Step 2d synthesis. If every reviewer is excluded (all exit-3), surface verbatim and do NOT synthesize: `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.` Full route table, `record-exclusion` contract, and Phase 2 schema assertions: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2d: Opus Synthesis

After parallel reviewers (or the successful subset) clear Step 2c.5, resolve the synthesizer model by running `cortex-resolve-model --role synthesizer` (no `--criticality` flag and no lifecycle-state read — the standalone path may have no lifecycle session, so a missing state must never block synthesis); on nonzero exit, halt and escalate rather than substitute a model. Read `${CLAUDE_SKILL_DIR}/references/a-to-b-downgrade-rubric.md` and substitute its full content into `{a_to_b_rubric}`, then dispatch one synthesizer agent with the resolved model and the canonical prompt from `${CLAUDE_SKILL_DIR}/references/synthesizer-prompt.md` verbatim, with `{artifact_path}`, `{artifact_sha256}`, `{a_to_b_rubric}`, and the reviewer-findings payload substituted at runtime. The prompt directs the synthesizer to Read the artifact once at start and emit `SYNTH_READ_OK: <path> <sha>` in output before per-finding analysis.

The synthesizer applies the **A→B downgrade rubric** (inlined via `{a_to_b_rubric}`) to each A-class finding's `"fix_invalidation_argument"` field.

### Step 2d.5: Post-Synthesis (atomic SHA verification)

Pipe the synthesizer's full output through `cortex-critical-review check-synth-stable --feature <name> --expected-sha <hex>` before surfacing anything or proceeding to Step 2e. Full contract and exit-code routing: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2e: Residue Write

After synthesis (or a Step 2c.5 pass-through), atomically write any B-class findings to `cortex/lifecycle/{feature}/critical-review-residue.json` via the `cortex-critical-review-write-residue` console-script; skip silently when zero B-class remain. Resolver, payload schema (R4), and zero/multiple-match gating: `${CLAUDE_SKILL_DIR}/references/residue-write.md`.

## Step 3: Present

Output the review result directly. Do not soften or editorialize.

## Step 4: Apply Feedback

Immediately after presenting the synthesis, work through each objection independently — do not wait for the user.

- **Apply** when the fix is unambiguous and confidence is high.
- **Dismiss** when the artifact already addresses the objection or it misreads stated constraints.
- **Ask** when the fix involves user preference, a scope decision, or genuine uncertainty.

Default ambiguous to Ask. Anchor-checks: dismissals must point to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning. For any empirical claim (latency, file size, blast radius, baseline behavior), run the actual measurement (`time`, `wc -c`, grep) before classifying Apply/Dismiss — re-reading the artifact text is not new evidence.

Then: (1) re-read the artifact in full; (2) write the updated artifact with all Apply fixes incorporated, preserving everything untouched; (3) present a compact summary — Apply bullets describe the direction of change (not the objection text), each opening with one of strengthened / narrowed / clarified / added / removed / inverted; a single **Dismiss: N objections** line (omit when N = 0); and any Ask items consolidated into one message.
