---
name: critical-review
description: Dispatches parallel reviewer agents — each focused on a single challenge angle — then synthesizes findings with an Opus agent to deeply challenge a plan, spec, or research artifact from multiple angles before you commit. Domain context from project requirements is injected so reviewers can surface domain-specific failure modes even when the artifact doesn't mention them. Use when the user says "critical review", "pressure test", "adversarial review", "pre-commit challenge", "deeply question", or "challenge from multiple angles". More thorough than a single sequential pass because parallel agents remove anchoring bias and produce deeper per-angle coverage. Also auto-triggers in the lifecycle for Complex + medium/high/critical features after plan approval.
when_to_use: "Use when you want to stress-test a plan, spec, or research artifact before committing (\"poke holes in the plan\", \"stress test the spec\", \"is this actually a good idea\", \"review before I commit\"). Different from /devils-advocate — devils-advocate runs inline in the current agent's context for a lightweight solo deliberation; critical-review dispatches parallel sub-agents and synthesizes the findings."
argument-hint: "[<artifact-path>]"
inputs:
  - "artifact-path: string (optional) — path to plan.md, spec.md, or research.md to review; if omitted, auto-detect from current lifecycle"
outputs:
  - "Synthesis prose presented in conversation"
  - "Optional residue write at lifecycle/{feature}/critical-review-residue.json"
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

If a lifecycle is active, read the most relevant artifact (`lifecycle/{feature}/plan.md` → `spec.md` → `research.md`, in that order). Otherwise use conversation context. If nothing is clear enough to challenge, ask: "What should I critically review?" before proceeding.

## Step 2: Review Setup and Dispatch

### Step 2a: Load Domain Context

Before dispatching any reviewer agent, load project context for injection into reviewer prompts:

1. If `requirements/project.md` exists, read it and extract the **Overview** section (or the first top-level summary section if none is labeled "Overview") — up to ~250 words.
2. If `lifecycle.config.md` exists, read it and check for a `type:` field. Only use the value if it is present, non-empty, and not commented out (i.e., the line is not prefixed with `#`). If the value is valid, include it as a one-line prefix: `**Project type:** {type}` before the project overview text.
3. Construct a `## Project Context` block from these inputs. **If neither file exists** (or `requirements/project.md` is absent and `lifecycle.config.md` has no valid `type:` value), **omit the `## Project Context` section entirely** — do not inject an empty placeholder into reviewer prompts.

#### Step 2a.5: Pre-Dispatch (atomic path + SHA pin)

Before deriving angles or dispatching any agent, fuse path validation and SHA-256 computation into a single subprocess call. The orchestrator MUST NOT shell out to `git rev-parse`, `realpath`, or `sha256sum` directly — and MUST NOT instruct dispatched reviewers to do so either. All path resolution happens here.

Invoke:

```bash
python3 -m cortex_command.critical_review prepare-dispatch <artifact-path> [--feature <name>]
```

- `<artifact-path>` is the candidate artifact path resolved in Step 1 (e.g. `lifecycle/{feature}/plan.md` or the explicit `<path>` argument from `/cortex-core:critical-review <path>`).
- Pass `--feature <name>` only on auto-trigger flows (the lifecycle resolved `{feature}` from `$LIFECYCLE_SESSION_ID` against `lifecycle/*/.session` — see Step 2e for the canonical resolver). The `<path>`-arg invocation form (`/cortex-core:critical-review <path>`) omits `--feature`.

Capture the single-line JSON object printed to stdout. Schema: `{"resolved_path": "<absolute-path>", "sha256": "<64-hex>"}`. Bind:

- `{artifact_path}` ← `resolved_path`
- `{artifact_sha256}` ← `sha256`

Substitute both into every dispatch site that follows: the per-angle reviewer template (Step 2c), the total-failure fallback reviewer template (Step 2c "(b) Total failure"), and the synthesizer template (Step 2d).

If `prepare-dispatch` exits non-zero, surface its stderr verbatim to the user and stop — do not dispatch any agent. Exit-2 messages name the offending path and the violated rule (symlink, prefix mismatch, non-file).

### Step 2b: Derive Angles

The orchestrator (in main conversation context) derives 3-4 challenge angles from the artifact. Each angle must be **distinct** (no two angles are re-phrasings of each other) and must **reference specific sections or claims in the artifact** (not generic category labels).

#### Angle Menu

The menu below lists representative angle examples — not an exhaustive set. Pick angles most likely to reveal real problems for this specific artifact, choosing from the menu or inventing new angles that fit the artifact better. If domain context was loaded in Step 2a, weight domain-specific examples more heavily — but domain detection is optional, not required for angle derivation.

**General examples:**
- Architectural risk
- Unexamined alternatives
- Fragile assumptions
- Integration risk
- Scope creep
- Real-world failure modes

**Domain-specific examples (games):**
- Performance budget
- Game loop coupling
- Save/load state
- Platform store compliance

**Domain-specific examples (mobile):**
- Platform API constraints
- Offline behavior
- Haptic/accessibility
- Background execution limits

**Domain-specific examples (workflow/tooling):**
- Agent isolation
- Prompt injection
- State file corruption
- Failure propagation

#### Angle Count

- If the artifact is very short (< 10 lines): minimum 2 angles.
- Otherwise: target 3-4 angles.

#### Acceptance Criteria

- **Distinctness**: No two derived angles may be re-phrasings of the same concern. Each must probe a different failure surface.
- **Artifact-specificity**: Each angle must cite a specific section, claim, assumption, or design choice in the artifact — not a generic category label. "Fragile assumptions" alone is not an angle; "The retry logic in section 3 assumes idempotent endpoints, which breaks for the payment webhook described in section 5" is.

### Step 2c: Dispatch Parallel Reviewers

For each angle derived in Step 2b, dispatch one general-purpose agent as a parallel Task tool sub-task. All agents run simultaneously — do not wait for one to finish before launching the next.

Each agent receives the following prompt template verbatim, with bracketed variables substituted at runtime:

---

You are conducting an adversarial review of one specific angle.

## Artifact

- Path: `{artifact_path}`
- Expected SHA-256: `{artifact_sha256}`

Read the literal absolute path provided above before beginning analysis. Do NOT re-derive the path yourself; Read the literal absolute path as given.

When the Read succeeds AND the computed SHA-256 of the Read result matches `{artifact_sha256}`, emit `READ_OK: <absolute-path> <sha256-of-Read-result>` as the first line of output, then continue with the analysis below.

When the Read fails or returns empty content, emit `READ_FAILED: <absolute-path> <one-word-reason>` as the first line of output and stop — do not proceed with analysis.

Example success first-line shape: `READ_OK: <path> <sha>`

## Project Context
{## Project Context block from Step 2a, omit this entire section if no context was loaded}

## Your Angle
**{angle name}**: {angle description — 1-2 sentences describing what this angle investigates}

## Finding Classes

Each finding must be tagged with exactly one class. Multi-class tags are prohibited.

- **A — fix-invalidating**: the artifact's proposed change does not work as described, or makes the situation worse. Worked example: "the refactor removes a null check the caller depends on."
- **B — adjacent-gap**: the proposed change is internally correct but an adjacent code path, callsite, or contract is left misaligned. Worked example: "the fix is correct but the analytics event a layer up still fires on the old path."
- **C — framing**: the artifact's narrative or framing misrepresents the change, scope, or motivation. Worked example: "the commit message misrepresents the change scope."

For any A-class finding, include a `fix_invalidation_argument` — one sentence explaining why the proposed change as written would fail to produce its stated outcome (not merely that an adjacent concern exists).

### Straddle Protocol

If one observed problem decomposes into both an A-class and a B-class concern, **split** into two separate findings. If the concerns cannot be cleanly split, **bias up to A** — the conservative class wins on unsplittable cases. Multi-class tags on a single finding are prohibited.

## Instructions
1. Read the artifact focusing exclusively on your assigned angle.
2. Be specific — cite exact artifact text. "This might not scale" is not acceptable.
3. Return findings in this exact format:

## Findings: {angle name}

### What's wrong
[Specific problems, each citing exact artifact text in quotes]

### Assumptions at risk
[Assumptions this angle reveals as fragile]

### Convergence signal
[One line: whether this angle's concerns likely overlap with other possible review angles, and which]

Do not cover other angles. Do not be balanced.

After the prose findings above, emit a JSON envelope so the orchestrator can extract structured class tags. Place the `<!--findings-json-->` delimiter on a line by itself, then the JSON object on subsequent lines:

<!--findings-json-->
{
  "angle": "<angle name>",
  "findings": [
    {
      "class": "A" | "B" | "C",
      "finding": "<text>",
      "evidence_quote": "<verbatim quote from the artifact>",
      "fix_invalidation_argument": "<optional: for A-class findings, one sentence explaining why the proposed change as written would fail to produce its stated outcome>",
      "straddle_rationale": "<optional: rationale when splitting per Straddle Protocol, or when biasing up to A on an unsplittable case>"
    }
  ]
}

---

#### Failure Handling

**(a) Partial failure** — some agents succeed, some fail: Collect all successful results. Unconditionally note "N of M reviewer angles completed (K excluded for drift/Read failure)" at the top of the synthesis output (Step 2d), where K is the count of reviewers excluded by Step 2c.5's sentinel-first gate (drift or Read-failure exclusions recorded via `record-exclusion`). When K = 0 the parenthetical is OMITTED entirely — emit only "N of M reviewer angles completed" to preserve existing behavior for clean runs. Proceed to Step 2d with the successful findings only.

**(b) Total failure** — all agents fail: Fall back to a single-agent approach. Dispatch one general-purpose agent with this fallback prompt verbatim:

---

You are conducting an adversarial review. Your job is to find what's wrong, risky, or overlooked — not to be balanced.

## Artifact

- Path: `{artifact_path}`
- Expected SHA-256: `{artifact_sha256}`

Read the literal absolute path provided above before beginning analysis. Do NOT re-derive the path yourself; Read the literal absolute path as given.

When the Read succeeds AND the computed SHA-256 of the Read result matches `{artifact_sha256}`, emit `READ_OK: <absolute-path> <sha256-of-Read-result>` as the first line of output, then continue with the analysis below.

When the Read fails or returns empty content, emit `READ_FAILED: <absolute-path> <one-word-reason>` as the first line of output and stop — do not proceed with analysis.

## Instructions

1. Read the artifact carefully.
2. Derive 3-4 distinct challenge angles from its content. Pick the angles most likely to reveal real problems for this specific artifact, not generic critiques. Examples: architectural risk, unexamined alternatives, fragile assumptions, integration risk, scope creep, real-world failure modes. Use what fits.
3. Work through each angle. Be specific — cite exact parts of the artifact, not vague generalities. "This might not scale" is useless. "This approach requires X, but the artifact assumes Y, which breaks when Z" is useful.
4. Synthesize into one coherent challenge — not a per-angle dump. Find the through-lines. Flag anything multiple angles agree on as high-confidence. Surface tensions where angles conflict.
5. End with: "These are the strongest objections. Proceed as you see fit."

## Output Format

Use the following named sections:

## Objections
## Through-lines
## Tensions
## Concerns

Use bullets, not prose paragraphs. Each finding is a discrete bullet. Bullets may be multi-sentence when quoting artifact text as evidence. Skip sections where the agent returned no findings — do not emit empty section headers. Do not include balanced or endorsement sections — no "## What Went Well", no "## Strengths", no "## Recommendation".

Do not be balanced. Do not reassure. Find the problems.

---

Output the fallback agent's result directly (no synthesis step). Prefix the output with this one-line note: "Note: parallel dispatch failed, falling back to single reviewer" before proceeding to Step 3.

#### Step 2c.5: Sentinel-First Verification Gate

After parallel reviewers (or the surviving subset) return, run a two-phase verification gate before Step 2d synthesis. Phase 1 verifies each reviewer's read-sentinel; Phase 2 extracts the JSON envelope only for reviewers that pass Phase 1.

The orchestrator captures the pre-dispatch SHA-256 of the artifact into orchestrator context before fan-out (see the `verify-synth-output` subcommand for the canonical computation path used in Task 7). That captured SHA is the expected value compared against each reviewer's sentinel here.

**Phase 1 — Sentinel verification (per reviewer):**

1. Read the reviewer's first output line. Expected form: `READ_OK: <absolute-path> <sha256>` (success sentinel) or `READ_FAILED: <absolute-path> <reason>` (read-failure sentinel).
2. Classify the reviewer's status using these routes:
   - **Pass** — first line is `READ_OK: <path> <sha>` AND `<sha>` equals the orchestrator's pre-dispatch SHA. Proceed to Phase 2 for this reviewer.
   - **Exclude (SHA drift)** — first line is `READ_OK: <path> <sha>` but `<sha>` differs from the orchestrator's pre-dispatch SHA. Emit warning with reason `SHA drift detected (expected <expected-sha>, got <reviewer-sha>)`.
   - **Exclude (sentinel absent)** — first line is neither a `READ_OK:` nor a `READ_FAILED:` line. Emit warning with reason `sentinel absent`.
   - **Exclude (read failure)** — first line is `READ_FAILED: <path> <reason>`. Emit warning with reason `Read failed: <reason>`.
3. Excluded reviewers drop from ALL downstream tallies (A-class, B-class, C-class) AND from the untagged-prose pathway. Their output is not parsed for envelope JSON and not surfaced to the synthesizer as prose. Emit the standardized warning `⚠ Reviewer {angle} excluded: {reason}` to the orchestrator log, and include the same warning line in the synthesizer prompt preamble (Step 2d) so the synthesizer sees the partial reviewer set explicitly rather than silently working from a reduced count.
4. **Atomic exclusion telemetry (per excluded reviewer).** For each reviewer classified Exclude in step 2 above, invoke `record-exclusion` exactly once. This is the only sanctioned way to log a sentinel_absence event — do NOT append to `events.log` inline:

   ```bash
   python3 -m cortex_command.critical_review record-exclusion \
     --feature <name> \
     --reviewer-angle <angle> \
     --reason <absent|sha_mismatch|read_failed> \
     --model-tier <haiku|sonnet|opus> \
     --expected-sha <hex> \
     [--observed-sha <hex>]
   ```

   - `--reason` maps from the exclusion route: `sentinel absent` → `absent`; `SHA drift detected` → `sha_mismatch`; `Read failed` → `read_failed`.
   - `--observed-sha` is supplied only on the `sha_mismatch` route (the reviewer's emitted SHA from its `READ_OK:` first line). Omit for `absent` and `read_failed`.
   - `--feature` is the same value passed to `prepare-dispatch` in Step 2a.5; on the `<path>`-arg invocation form (no feature in scope), skip the call — sentinel_absence telemetry requires a lifecycle feature directory to write into.
   - The subcommand performs an atomic tempfile + rename append to `lifecycle/{feature}/events.log`. Exit 0 = appended.

5. **Total-failure path (all reviewers excluded).** When every dispatched reviewer is classified Exclude in step 2 (zero pass through Phase 2), surface verbatim to the user — do NOT proceed to Step 2d synthesis:

   `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.`

**Phase 2 — Envelope extraction (only for reviewers that passed Phase 1):**

1. Locate the `<!--findings-json-->` delimiter using the LAST occurrence anchor — `re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)`, then split at the last match (tolerates prose quoting the delimiter).
2. `json.loads` the post-delimiter tail. Assert schema: top-level `angle: str`, `findings: list`; each finding has `class ∈ {"A","B","C"}`, `finding: str`, `evidence_quote: str`, optional `straddle_rationale: str`, optional `"fix_invalidation_argument": str`.
3. On any extraction or validation failure (no delimiter, JSON decode error, missing required field, invalid `class` enum), emit `⚠ Reviewer {angle} emitted malformed JSON envelope ({reason}) — class tags for this angle are UNAVAILABLE. Prose findings presented as-is; the B→A refusal gate will EXCLUDE this reviewer's findings from its count rather than treating them as C-class.` and pass the reviewer's prose findings to the synthesizer as an untagged block. Step 2d renders untagged prose under `## Concerns` and excludes it from the A-class tally. Do NOT silently coerce malformed envelopes to C-class. This malformed-envelope handler applies only AFTER Phase 1 sentinel verification has passed — a reviewer with a missing or drifted sentinel never reaches this path.

### Step 2d: Opus Synthesis

After all parallel reviewer agents from Step 2c complete (or the successful subset), dispatch one `opus` model agent with the following prompt template verbatim, with bracketed variables substituted at runtime:

---

You are synthesizing findings from multiple independent adversarial reviewers into a single coherent challenge.

## Artifact

- Path: `{artifact_path}`
- Expected SHA-256: `{artifact_sha256}`

Read the literal absolute path provided above once at the START of synthesis, before the per-finding loop in the Instructions section. Do NOT re-derive the path yourself; Read the literal absolute path as given. Treat the in-context Read result as the source of truth for evidence-quote re-validation throughout the remainder of synthesis.

When the Read succeeds AND the computed SHA-256 of the Read result matches `{artifact_sha256}`, emit `SYNTH_READ_OK: <path> <sha>` (substituting the absolute path you Read and the SHA-256 of the Read result) as a line in your output before any per-finding analysis, then continue with the synthesis below.

When the Read fails or returns empty content, emit `SYNTH_READ_FAILED: <absolute-path> <one-word-reason>` as a line in your output before any per-finding analysis and stop — do not proceed with synthesis.

## Reviewer Findings
{all reviewer findings — class-tagged JSON envelopes from well-formed reviewers, plus any untagged prose blocks from reviewers whose envelopes were malformed per Step 2c.5}

## Instructions
1. Read all reviewer findings carefully.
2. Find the through-lines — claims or concerns that appear across multiple angles **within the same class**. A-class through-lines, B-class through-lines, and C-class through-lines are distinct; do not merge them.
3. Before accepting any finding's class tag, re-read its `evidence_quote` field against the in-context Read result of `{artifact_path}` performed at the start of synthesis. For A-class findings, also re-read the `"fix_invalidation_argument"` field — apply the A→B downgrade rubric below. If the evidence supports a different class, re-classify and surface a note: `Synthesizer re-classified finding N from B→A: <rationale>` (upgrade) or `Synthesizer re-classified finding N from A→B: <rationale>` (downgrade). Downgrades commonly fire on straddle-rationale findings where the evidence only supports the adjacent concern.

   **A→B downgrade rubric.** A-class status requires a credible `"fix_invalidation_argument"` — a concrete causal link from the cited evidence to a failure of the proposed change. Downgrade A→B when any of the following triggers fires (using the reclassification note `Synthesizer re-classified finding N from A→B: <rationale>`):

   - **Trigger 1 (absent)**: the `"fix_invalidation_argument"` field is absent or empty.
   - **Trigger 2 (restates)**: the argument restates the finding text without adding a causal link from evidence to fix-failure.
   - **Trigger 3 (adjacent)**: the argument identifies an adjacent issue (B-class material) rather than fix-invalidation. **Straddle exemption**: when the finding's `straddle_rationale` field is present, Straddle Protocol bias-up takes precedence and trigger 3 does NOT fire — ratify as A.
   - **Trigger 4 (vague)**: the argument is vague or speculative ("might cause", "could break") without a concrete failure path.

   Conversely, ratify as A when the `"fix_invalidation_argument"` names a concrete mechanism by which the proposed change, as written, would fail to produce its stated outcome.

### Worked example 1 (absent): ratify

- Candidate `"fix_invalidation_argument"`: "the patch sets `retries=0` but leaves `retry_on_timeout=True`, so the loop in `client.py:142` still re-enters on timeout — the documented fix never takes effect."
- Trigger applies: none — argument is present and names a concrete mechanism.
- Disposition: ratify as A. The argument carries a concrete causal link from evidence (`retry_on_timeout=True`) to a fix-failure (loop still re-enters).

### Worked example 2 (absent): downgrade

- Candidate `"fix_invalidation_argument"`: (field omitted from envelope).
- Trigger applies: 1 (absent). The reviewer tagged the finding A but supplied no fix-invalidation argument.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument absent; A-class requires a concrete failure path.`

### Worked example 3 (restates): ratify

- Candidate `"fix_invalidation_argument"`: "the proposed null-check guards `user.email` but the crash trace at `auth.py:88` shows the NPE originates from `user.profile.email`, two attribute hops up — the guard is on the wrong object."
- Trigger applies: none — argument adds a causal link (wrong object guarded → NPE persists), not a restatement.
- Disposition: ratify as A.

### Worked example 4 (restates): downgrade

- Candidate `"fix_invalidation_argument"`: "the fix does not work because the bug is not actually fixed by this change."
- Trigger applies: 2 (restates). The argument restates the finding ("does not work") without a causal mechanism linking evidence to fix-failure.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument restates the finding without a causal link.`

### Worked example 5 (adjacent): ratify

- Candidate `"fix_invalidation_argument"`: "the patch updates the validator but the cache layer at `cache.py:55` still serves the pre-fix payload for 1h — within the documented 'effective immediately' window the fix is invisible to callers."
- `straddle_rationale`: "splits between fix-invalidation (cache window swallows the fix) and adjacent cache-invalidation gap; biasing up because the cache window collapses the documented outcome."
- Trigger applies: 3 would fire on adjacency grounds, BUT `straddle_rationale` is populated — Straddle exemption activates and trigger 3 does NOT fire.
- Disposition: ratify as A.

### Worked example 6 (adjacent): downgrade

- Candidate `"fix_invalidation_argument"`: "the analytics event one layer up still fires on the old code path, so downstream dashboards will be wrong."
- `straddle_rationale`: (absent).
- Trigger applies: 3 (adjacent). The argument describes a B-class adjacent gap (analytics misalignment) rather than fix-invalidation of the proposed change itself; no Straddle exemption because `straddle_rationale` is not set.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument describes an adjacent gap, not fix-invalidation; no straddle_rationale present.`

### Worked example 7 (vague): ratify

- Candidate `"fix_invalidation_argument"`: "the migration drops the index before backfilling the new column, so the backfill query at `migrate.py:212` will table-scan a 40M-row table and time out under the 30s statement timeout — the migration aborts mid-fix."
- Trigger applies: none — argument names a concrete failure path (index drop → table scan → statement timeout → abort).
- Disposition: ratify as A.

### Worked example 8 (vague): downgrade

- Candidate `"fix_invalidation_argument"`: "this might cause performance issues and could break things under load."
- Trigger applies: 4 (vague). Hedged language ("might cause", "could break") with no concrete failure path.
- Disposition: downgrade A→B. Note: `Synthesizer re-classified finding N from A→B: fix_invalidation_argument is speculative ("might cause", "could break") with no concrete failure path.`
4. After evidence re-examination, count A-class findings from well-formed envelopes only — untagged prose blocks (from malformed envelopes per Step 2c.5) do NOT count toward the A-class tally. If the count is zero, do NOT emit an `## Objections` section. B-class findings in the absence of any A-class finding surface under `## Concerns` at most.
5. Surface tensions where angles conflict or pull in different directions.
6. Synthesize into a single coherent challenge. Do not produce a per-angle dump.
7. Be specific — cite exact parts of the artifact.
8. End with: "These are the strongest objections. Proceed as you see fit." If no A-class findings remained after evidence re-examination, also open the synthesis with: `No fix-invalidating objections after evidence re-examination. The concerns below are adjacent gaps or framing notes — do not read as verdict.`

## Output Format

Use the following named sections:

## Objections
## Through-lines
## Tensions
## Concerns

Use bullets, not prose paragraphs. Each finding is a discrete bullet. Bullets may be multi-sentence when quoting artifact text as evidence. Skip sections where the agent returned no findings — do not emit empty section headers. Do not include balanced or endorsement sections — no "## What Went Well", no "## Strengths", no "## Recommendation".

Untagged prose from malformed-envelope reviewers (per Step 2c.5) renders under `## Concerns` and is excluded from the A-class tally that gates whether `## Objections` is emitted.

Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.

---

#### Partial Coverage

If partial coverage occurred in Step 2c (some agents succeeded, some failed), unconditionally prefix the synthesis output with "N of M reviewer angles completed (K excluded for drift/Read failure)." before the synthesis narrative, where K is the count of reviewers excluded by Step 2c.5's sentinel-first gate (drift or Read-failure exclusions recorded via `record-exclusion`). When K = 0 the parenthetical is OMITTED entirely — emit only "N of M reviewer angles completed." to preserve existing behavior for clean runs.

#### Synthesis Failure

If the synthesis agent fails, skip synthesis and present the raw per-angle findings from Step 2c directly. Step 3 and Step 4 (Apply Feedback) then operate on the raw findings instead of a synthesized narrative.

**Note:** Step 2d is skipped entirely when Step 2c's total-failure fallback was used — that path proceeds directly to Step 3.

#### Step 2d.5: Post-Synthesis (atomic SHA verification)

After the synthesizer agent returns, pipe its **full output** through the `verify-synth-output` subcommand before surfacing anything to the user or proceeding to Step 2e. This fuses sentinel-parse + SHA-match + drift-event append into one subprocess call; do NOT parse `SYNTH_READ_OK:` lines inline or append to `events.log` directly.

Invoke:

```bash
printf '%s' "$SYNTH_OUTPUT" | python3 -m cortex_command.critical_review verify-synth-output \
    --feature <name> \
    --expected-sha <hex>
```

- `<hex>` is the same `{artifact_sha256}` captured in Step 2a.5 from `prepare-dispatch`.
- `<name>` is the same `--feature` argument used in Step 2a.5; on the `<path>`-arg invocation form (no feature in scope), skip this verification step — drift telemetry requires a lifecycle feature directory.

Routes based on exit code:

- **Exit 0** — synthesizer's `SYNTH_READ_OK:` sentinel present and SHA matches. Surface the synthesizer's prose output to the user normally, then proceed to Step 2e.
- **Exit 3** — sentinel absent OR SHA mismatch (drift). **Do NOT surface the synthesizer's prose output.** Instead, relay `verify-synth-output`'s own stdout verbatim to the user — its top-level diagnostic carries the `Critical-review pass invalidated` phrasing and the resolution instruction. The subcommand has already appended the `synthesizer_drift` event to `lifecycle/{feature}/events.log` atomically; the orchestrator must not duplicate that append.

On Exit 3, do NOT proceed to Step 2e (residue write) — the critical-review pass is invalidated and a stale residue write would compound the drift.

### Step 2e: Residue Write

After synthesis (or Step 2c.5 pass-through), atomically write any B-class findings to a sidecar JSON for the morning report. Skip silently when zero B-class findings remain.

Resolve `{feature}` from `$LIFECYCLE_SESSION_ID` against `lifecycle/*/.session` files (whitespace-stripped match):

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
[ -z "$REPO_ROOT" ] || MATCHES=$(python3 -c "
import os, glob
sid = os.environ.get('LIFECYCLE_SESSION_ID', '')
print('\n'.join(p for p in glob.glob(os.path.join('$REPO_ROOT','lifecycle','*','.session')) if open(p).read().strip()==sid))")
```

- **One match**: `{feature}` = parent dir of matched `.session`; proceed to atomic write.
- **Zero matches** (or no `REPO_ROOT`): ad-hoc mode — if B-class findings exist, emit `Note: B-class residue not written — no active lifecycle context.`; skip write.
- **Multiple matches**: emit `Note: multiple active lifecycle sessions matched $LIFECYCLE_SESSION_ID; B-class residue write skipped.`; skip write.

Atomic write (only when `{feature}` resolved AND ≥1 B-class finding) — inline `python3 -c` performing a tempfile + `os.replace` atomic rename to `lifecycle/{feature}/critical-review-residue.json`:

```bash
python3 -c "
import json, os, sys, tempfile
from pathlib import Path
final = Path('$REPO_ROOT')/'lifecycle'/'$FEATURE'/'critical-review-residue.json'
final.parent.mkdir(parents=True, exist_ok=True)
data = json.dumps(json.loads(sys.stdin.read()), indent=2)+'\n'
with tempfile.NamedTemporaryFile('w', dir=str(final.parent), delete=False) as tmp:
    tmp.write(data)
    tmp_path = tmp.name
os.replace(tmp_path, final)
" <<< "$PAYLOAD_JSON"
```

Payload schema (R4): `{"ts":"<ISO 8601>","feature":"<slug>","artifact":"<path>","synthesis_status":"ok|failed","reviewers":{"completed":N,"dispatched":M},"findings":[{"class":"B","finding":"<text>","reviewer_angle":"<angle>","evidence_quote":"<text>"}]}`.

Gates: zero B-class → no file, no note. Synthesis failure → write `synthesis_status:"failed"` with B-class findings from Step 2c reviewers' envelopes. Path-argument (`/cortex-core:critical-review <path>`) and auto-trigger invocations (specify.md §3b / plan.md) both obey session-bound resolution — the argument path does not re-bind `{feature}`.

## Step 3: Present

Output the review result directly. Do not soften or editorialize.

## Step 4: Apply Feedback

Immediately after presenting the synthesis, work through each objection independently. Do not wait for the user.

**Apply** when the fix is unambiguous and confidence is high.
**Dismiss** when the artifact already addresses the objection or the objection misreads stated constraints.
**Ask** when the fix involves user preference, scope decision, or genuine uncertainty.
Default ambiguous to Ask. Anchor-checks: dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning.

After classifying all objections:

1. Re-read the artifact in full.
2. Write the updated artifact with all "Apply" fixes incorporated. Preserve everything not touched by an accepted objection.
3. Present a compact summary:
   - **Apply bullets describe the direction of the change**, not the objection text. Use one of these verbs as the first word of each bullet: strengthened, narrowed, clarified, added, removed, inverted.
   - **Dismiss: N objections** — a single count line. Omit when N = 0.
   - **Ask items consolidate into a single message when any remain.**
