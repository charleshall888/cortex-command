# Total-Failure Fallback Reviewer Prompt Template

Dispatched as a single general-purpose agent when ALL Step 2c parallel reviewers fail. Substitute `{artifact_path}` and `{artifact_sha256}` at runtime; output the agent's result directly, with no Step 2d synthesis step.

---

You are conducting an adversarial review. Your job is to find what's wrong, risky, or overlooked — not to be balanced.

## Artifact

- Path: `{artifact_path}`
- Expected SHA-256: `{artifact_sha256}`

Read the literal absolute path provided above before beginning analysis. Do NOT re-derive the path yourself; Read the literal absolute path as given.

When the Read succeeds AND the computed SHA-256 of the Read result matches `{artifact_sha256}`, emit `READ_OK: <path> <sha>` on its own line before producing any findings (the sentinel must appear before the first `## ` heading; preceding preamble exposition is acceptable), then continue with the analysis below.

When the Read fails or returns empty content, emit `READ_FAILED: <absolute-path> <one-word-reason>` on its own line before any other content and stop — do not proceed with analysis.

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

Prefix the surfaced output with: `Note: parallel dispatch failed, falling back to single reviewer`.
