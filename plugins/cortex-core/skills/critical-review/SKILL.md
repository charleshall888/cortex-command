---
name: critical-review
description: Parallel adversarial review — dispatches reviewer agents on distinct challenge angles, then synthesizes findings with an Opus agent. Use when user says "critical review", "pressure test", "adversarial review", "pre-commit challenge", "deeply question", or "challenge from multiple angles". Auto-triggers in the lifecycle for Complex + medium/high/critical features before spec and plan approval.
when_to_use: "Use when you want to stress-test a plan, spec, or research artifact before committing (\"poke holes in the plan\", \"stress test the spec\", \"is this actually a good idea\", \"review before I commit\"). Different from /devils-advocate — devils-advocate runs inline in the current agent context for a lightweight solo deliberation; critical-review dispatches parallel sub-agents and synthesizes findings."
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

Derives challenge angles from the artifact and domain context, dispatches one fresh reviewer agent per angle in parallel, then synthesizes findings with an Opus agent. Each reviewer works independently with no anchoring to the reasoning that produced the artifact.

## Contents

1. [Step 1: Find the Artifact](#step-1-find-the-artifact)
2. [Step 2: Review Setup and Dispatch](#step-2-review-setup-and-dispatch)
3. [Step 3: Present](#step-3-present)
4. [Step 4: Apply Feedback](#step-4-apply-feedback)

## Step 1: Find the Artifact

If a lifecycle is active, read the most relevant artifact (`cortex/lifecycle/{feature}/plan.md` → `spec.md` → `research.md`, in that order). Otherwise use conversation context. If nothing is clear enough to challenge, ask: "What should I critically review?" before proceeding.

## Step 2: Review Setup and Dispatch

### Step 2a: Load Domain Context

Before dispatching any reviewer agent, load project context for injection into reviewer prompts:

1. If `cortex/requirements/project.md` exists, read it and extract the **Overview** section (or the first top-level summary section if none is labeled "Overview") — up to ~250 words.
2. If `cortex/lifecycle.config.md` exists, read it and check for a `type:` field. Only use the value if it is present, non-empty, and not commented out (i.e., the line is not prefixed with `#`). If valid, include it as a one-line prefix: `**Project type:** {type}` before the project overview text.
3. Construct a `## Project Context` block from these inputs. **If neither file exists** (or `cortex/requirements/project.md` is absent and `cortex/lifecycle.config.md` has no valid `type:` value), **omit the `## Project Context` section entirely** — do not inject an empty placeholder into reviewer prompts.

> **Requirements loading: deliberately exempt.** Critical-review intentionally narrows its context to the parent `cortex/requirements/project.md` Overview only (~250 words) and does NOT participate in the tag-based requirements-loading protocol used by other skills. This is a deliberate design choice, not an oversight: reviewer agents stay focused on adversarial challenge against the artifact under review, and broader project context (priorities, area-specific tags, decisions) would dilute that focus and anchor reviewers to existing reasoning. Do not "fix" this exemption by wiring tag-based loading into the dispatch path.

### Step 2a.5: Pre-Dispatch (atomic path + SHA pin)

Before deriving angles or dispatching any agent, fuse path validation and SHA-256 computation into a single subprocess call: `cortex-critical-review prepare-dispatch <artifact-path> [--feature <name>]`. Capture the single-line JSON object printed to stdout (schema: `{"resolved_path": "<absolute-path>", "sha256": "<64-hex>"}`) and bind `{artifact_path}` ← `resolved_path` and `{artifact_sha256}` ← `sha256`. Substitute both into every dispatch site that follows. If `prepare-dispatch` exits non-zero, surface its stderr verbatim and stop — do not dispatch any agent. The orchestrator MUST NOT shell out to `git rev-parse`, `realpath`, or `sha256sum` directly, and MUST NOT instruct dispatched reviewers to do so.

Full invocation contract and exit-code routing: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2b: Derive Angles

The orchestrator (in main conversation context) derives 3-4 challenge angles from the artifact. Each angle must be **distinct** (no two angles are re-phrasings of each other) and must **reference specific sections or claims in the artifact** (not generic category labels).

Pick angles most likely to reveal real problems for this specific artifact. Representative angle examples (general, games, mobile, workflow/tooling), the angle-count rule, and the distinctness + artifact-specificity acceptance criteria: see `${CLAUDE_SKILL_DIR}/references/angle-menu.md`.

### Step 2c: Dispatch Parallel Reviewers

For each angle derived in Step 2b, dispatch one general-purpose agent as a parallel Task tool sub-task. All agents run simultaneously — do not wait for one to finish before launching the next.

Each agent receives the canonical reviewer prompt from `${CLAUDE_SKILL_DIR}/references/reviewer-prompt.md` verbatim, with `{artifact_path}`, `{artifact_sha256}`, `{angle name}`, `{angle description}`, and the Step 2a Project Context block substituted at runtime. The prompt instructs the reviewer to Read the literal absolute path and emit `READ_OK: <path> <sha>` as the first line on success (or `READ_FAILED: <path> <reason>` on failure), then to produce class-tagged findings (A — fix-invalidating, B — adjacent-gap, C — framing) with a `<!--findings-json-->` JSON envelope appended after prose findings.

#### Failure Handling

**(a) Partial failure** — some agents succeed, some fail: collect all successful results and proceed to Step 2d with the successful findings only. Prefix the Step 2d synthesis output per the partial-coverage rule in `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

**(b) Total failure** — all agents fail: fall back to a single-agent approach. Dispatch one general-purpose agent with the canonical fallback prompt from `${CLAUDE_SKILL_DIR}/references/fallback-reviewer-prompt.md` (substituting `{artifact_path}` and `{artifact_sha256}`). Output the fallback agent's result directly with no Step 2d synthesis, prefixed with `Note: parallel dispatch failed, falling back to single reviewer`, then proceed to Step 3.

### Step 2c.5: Sentinel-First Verification Gate

After parallel reviewers return, run a two-phase verification gate before Step 2d synthesis. **Phase 1** verifies each reviewer's `READ_OK: <path> <sha>` first-line sentinel against the orchestrator's pre-dispatch SHA: pass on SHA match, exclude on SHA drift, exclude on sentinel absent, exclude on `READ_FAILED`. For each excluded reviewer, invoke `cortex-critical-review record-exclusion ...` exactly once (the only sanctioned way to log sentinel_absence) — do NOT append to `events.log` inline. **Phase 2** extracts the `<!--findings-json-->` envelope only for reviewers that pass Phase 1, using LAST-occurrence delimiter anchoring; malformed envelopes drop class tags but pass prose to the synthesizer as an untagged block.

If every reviewer is excluded, surface verbatim and do NOT synthesize: `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.`

Full route table, `record-exclusion` invocation contract, and Phase 2 schema assertions: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2d: Opus Synthesis

After parallel reviewers (or the successful subset) return and pass Step 2c.5, dispatch one `opus` model agent with the canonical synthesizer prompt from `${CLAUDE_SKILL_DIR}/references/synthesizer-prompt.md` verbatim, with `{artifact_path}`, `{artifact_sha256}`, and the reviewer-findings payload substituted at runtime. The prompt instructs the synthesizer to Read the artifact once at start and emit `SYNTH_READ_OK: <path> <sha>` as a line in output before per-finding analysis.

The synthesizer applies the **A→B downgrade rubric** when evaluating each A-class finding's `"fix_invalidation_argument"` field — full rubric definitions, trigger semantics, and 8 worked examples (4 ratify / 4 downgrade across the absent/restates/adjacent/vague triggers): `${CLAUDE_SKILL_DIR}/references/a-to-b-downgrade-rubric.md`.

Decision gates: A-class count from well-formed envelopes only (untagged prose excluded from the A tally); zero A-class → no `## Objections` section. Output sections: `## Objections`, `## Through-lines`, `## Tensions`, `## Concerns` — bullets only, skip empty sections, no balanced/endorsement sections.

### Step 2d.5: Post-Synthesis (atomic SHA verification)

After the synthesizer returns, pipe its **full output** through `cortex-critical-review verify-synth-output --feature <name> --expected-sha <hex>` before surfacing anything to the user. **Exit 0** = sentinel + SHA OK → surface the synthesizer's prose and proceed to Step 2e. **Exit 3** = sentinel absent or SHA mismatch → do NOT surface the synthesizer's prose; relay the subcommand's own stdout verbatim (which carries the `Critical-review pass invalidated` phrasing). On Exit 3, do NOT proceed to Step 2e — the pass is invalidated.

Full invocation contract and resolution instructions: `${CLAUDE_SKILL_DIR}/references/verification-gates.md`.

### Step 2e: Residue Write

After synthesis (or Step 2c.5 pass-through), atomically write any B-class findings to a sidecar JSON for the morning report. Skip silently when zero B-class findings remain. Resolve `{feature}` from `$LIFECYCLE_SESSION_ID` against `cortex/lifecycle/*/.session` files; on multiple-match or zero-match, emit the documented note and skip the write. The write is an inline `python3 -c` tempfile + `os.replace` atomic rename to `cortex/lifecycle/{feature}/critical-review-residue.json`.

Resolver script, payload schema (R4), and gating rules: `${CLAUDE_SKILL_DIR}/references/residue-write.md`.

## Step 3: Present

Output the review result directly. Do not soften or editorialize.

## Step 4: Apply Feedback

Immediately after presenting the synthesis, work through each objection independently. Do not wait for the user.

**Apply** when the fix is unambiguous and confidence is high.
**Dismiss** when the artifact already addresses the objection or the objection misreads stated constraints.
**Ask** when the fix involves user preference, scope decision, or genuine uncertainty.
Default ambiguous to Ask. Anchor-checks: dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning. For any empirical claim (latency, file size, blast radius, baseline behavior), run the actual measurement (`time`, `wc -c`, grep) before classifying Apply/Dismiss — re-reading the artifact text does not count as new evidence.

After classifying all objections:

1. Re-read the artifact in full.
2. Write the updated artifact with all "Apply" fixes incorporated. Preserve everything not touched by an accepted objection.
3. Present a compact summary:
   - **Apply bullets describe the direction of the change**, not the objection text. Use one of these verbs as the first word of each bullet: strengthened, narrowed, clarified, added, removed, inverted.
   - **Dismiss: N objections** — a single count line. Omit when N = 0.
   - **Ask items consolidate into a single message when any remain.**
