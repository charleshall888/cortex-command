# PR Review Rubric

Scoring and gating rules for the pr-review synthesizer. Apply every finding against the three axes below, then route it through the gate thresholds to decide whether it survives and which Conventional Comments label it takes.

## Philosophy

- Findings are grounded by evidence or they are not findings — there is no "observation" category. If a claim cannot cite a concrete diff hunk, file path, or behavior trace, drop it. Affirmed by the `/ultrareview` verification philosophy: speculation without grounding is noise.

## Axes

Score every candidate finding on three orthogonal axes. All three must be assigned before the finding reaches the gate.

### severity

Buckets: `must-fix | should-fix | nit | unknown`

- `must-fix` — correctness, security, data loss, or contract break. Merging as-is ships a defect.
- `should-fix` — quality, maintainability, or clarity regression that a reasonable reviewer would block on in most teams.
- `nit` — style, taste, or micro-optimization. Ignorable without harm.
- `unknown` — the reviewer cannot classify severity without author input (ambiguous intent, missing context). Routes to `question:`, never to `issue:`.

### solidness

Buckets: `solid | plausible | thin`

- `solid` — evidence is unambiguous AND the finding names a concrete next action (specific edit, file, or behavior change). `solid` is the only bucket that carries an actionable fix; a finding without a concrete next action cannot be `solid` no matter how strong the evidence.
- `plausible` — evidence supports the finding but the fix shape is uncertain, or the finding is a well-posed question rather than a prescription.
- `thin` — evidence is weak, indirect, or relies on pattern-matching without a grounded quote. Drop unless re-grounded.

### signal

Buckets: `high | medium | low`

- `high` — the finding changes the reviewer's decision or the author's next commit. Worth the reader's attention even in a dense review.
- `medium` — useful context or a real improvement, but would not block merge on its own.
- `low` — true but trivial; the reader gains little by seeing it called out.

## Gate thresholds

One rule per Conventional Comments label. A finding that does not match any rule below is dropped.

- `issue (blocking):` — severity = `must-fix` AND solidness ≥ `plausible`. Blocking by construction.
- `suggestion:` — severity = `should-fix` AND solidness = `solid` AND signal ≥ `medium`. Non-blocking by default.
- `nitpick (non-blocking):` — severity = `nit` AND solidness = `solid` AND signal = `high`. Spec-canonical label is `nitpick:`, never `nit:`.
- `question:` — severity = `unknown` AND solidness ≥ `plausible`. Never blocking, never paired with a prescriptive fix.
- `praise:` — solidness = `solid` AND signal = `high`. Orthogonal to severity; praise is earned by strong evidence and real impact, not by tone.
- `cross-cutting:` — solidness ≥ `plausible` AND signal = `high`. Bypasses locality (may reference multiple files or the PR as a whole).
- Everything else → drop.

## Caps and tie-break

Per-label ceilings on the number of findings that may survive after gating. Apply caps after the gate thresholds; findings beyond the cap are dropped with reason `over-cap`.

- `nitpick:` cap = 3
- `praise:` cap = 2
- `cross-cutting:` cap = 1

Tie-break for `nitpick:` overflow: sort surviving candidates by file path alphabetical, then by line ascending; keep the first three. The same tie-break applies to any label where more candidates survive than the cap allows.

## Drop-reason taxonomy

Every dropped finding carries exactly one reason from the list below. Reasons determine whether the drop is silent or visible in the footer.

- `evidence-not-found` — silent drop (hallucinated evidence); not shown in footer. The `quoted_text` does not match any line in the diff on any side.
- `evidence-context-mismatch` — visible drop; the quoted text is present in the diff but on the wrong side (e.g., quoted as added but only exists on the `-` side) or the multi-line quote spans a hunk boundary.
- `low-signal` — rubric-gate drop; the finding fails a threshold such as a nit without `signal = high`, or a suggestion without `signal ≥ medium`.
- `linter-class` — style, formatting, or linter-enforced issue filtered by design so the review does not duplicate tooling output.
- `over-cap` — exceeded the per-label cap after tie-break; the finding was otherwise eligible.

## Normalization rules

Evidence-grounding normalization applied before matching `quoted_text` against diff lines. Stage 4's synthesizer relies on these rules to compare against the evidence-grounding pre-step output.

- Apply NFC (Normalization Form C) Unicode normalization to both the `quoted_text` and each candidate diff line before comparison.
- Strip the leading diff prefix `^[+\- ]` from each diff line (the `+`, `-`, or space marker) before comparison.
- Normalize `\r\n` line endings to `\n` (CRLF → LF) in both inputs.
- Collapse whitespace runs (spaces, tabs) to a single space in both inputs before comparison; this whitespace-collapse step runs after CRLF normalization.
- For a multi-line `quoted_text`, split on `\n` and require each line to match a consecutive diff line within the same hunk. Reject cross-hunk quotes (quotes that would span a hunk boundary) with `evidence-context-mismatch`.
- Record the matched side (`+`, `-`, or ` `) in `evidence.matched_side` on the finding.

Note: `matched_side` is a rubric-input diagnostic consumed by the Stage 4 synthesizer to decide demotion (e.g., a `-` side match typically demotes an `issue:` to a `question:` or drops it). It is distinct from ticket 005's renderer `side` / `start_side` fields, which map to GitHub's Reviews API request payload.

## Stability test protocol

The rewrite ships only if it produces consistent labels and Verdicts across repeated runs on a fixed PR set. This section defines the methodology; calibration run data itself lives in `calibration-log.md`.

### PR selection criteria

Choose three PRs that span the failure modes the rubric must distinguish:

- One recent merged PR with known nits — exercises the `nitpick:` cap, tie-break, and `signal = high` gating for nits.
- One recent PR with a real bug (caught in review or post-merge) — exercises `issue (blocking):` detection under `severity = must-fix` AND `solidness ≥ plausible`.
- One pure refactor PR (no behavior change) — exercises restraint: the rubric should not manufacture `issue:` or `suggestion:` findings when the diff is semantics-preserving.

### 9-run methodology

Run the synthesizer three times per PR across the three selected PRs, for 9 total runs (3 PRs × 3 runs). Each run is independent (fresh context, same inputs). Record the emitted labels and the per-PR Verdict for each run.

### Metrics

- **Label exact-match** — for each PR, count runs where the full set of emitted `(label, quoted_text)` pairs is identical. Reported per PR and aggregated.
- **Krippendorff's α** — compute on the 3×3 matrix of per-run label assignments (3 runs × 3 PRs), treating labels as nominal categories. α ranges from 0 (chance agreement) to 1 (perfect agreement).
- **Verdict per-PR exact-match** — for each PR, does the Verdict (approve / request-changes / comment) match across all 3 runs? Reported as `n/3 PRs` with all-3-runs-identical Verdict.

### Ship thresholds

- **Ships**: Krippendorff's α ≥ 0.6 AND Verdict exact-match = 3/3 on ≥ 2/3 PRs.
- **Blocks**: Krippendorff's α < 0.5 OR majority Verdict exact-match ≤ 1/3 PRs (i.e., 2 or more PRs show Verdict drift across their 3 runs).
- **Ambiguous (neither ships nor blocks)**: falls between the two — enter the exit ramp below.

### 3-iteration exit ramp

If the first 9-run calibration lands in the ambiguous band, iterate on the rubric (tighten thresholds, clarify axes, adjust caps) and re-run the full 9-run protocol. Allow up to 3 iterations total. Exit conditions:

- **Ship** on any iteration that clears the ship threshold.
- **Ship-with-warning** after 3 iterations if α ≥ 0.5 AND majority-Verdict-stable (Verdict exact-match = 3/3 on ≥ 2/3 PRs). Record the warning in `calibration-log.md` with the residual instability noted.
- **Block** after 3 iterations if neither ship nor ship-with-warning conditions hold. Do not ship; return the rewrite to spec.
