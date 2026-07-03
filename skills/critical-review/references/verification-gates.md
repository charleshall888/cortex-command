# Verification Gates (Step 2c.5 and Step 2d.5) — Implementation Detail

These gates wrap the per-reviewer envelope extraction and the post-synthesis
SHA verification. The orchestrator MUST route through the canonical
`cortex_command.critical_review` subcommands rather than shell out to
`git rev-parse`, `realpath`, or `sha256sum` directly, and MUST NOT append
to `events.log` inline.

## Step 2a.5: Pre-Dispatch (atomic path + SHA pin)

Before deriving angles or dispatching any agent, fuse path validation and SHA-256 computation into a single subprocess call:

```bash
cortex-critical-review prepare-dispatch <artifact-path> [--feature <name>]
```

- Pass `--feature <name>` only on auto-trigger flows (the lifecycle resolved `{feature}` from `$LIFECYCLE_SESSION_ID` against `cortex/lifecycle/*/.session` — see the Step 2e residue-write reference for the canonical resolver). The `<path>`-arg invocation form (`/cortex-core:critical-review <path>`) omits `--feature`.

Capture the single-line JSON object printed to stdout. Schema: `{"resolved_path": "<absolute-path>", "sha256": "<64-hex>"}`. Bind:

- `{artifact_path}` ← `resolved_path`
- `{artifact_sha256}` ← `sha256`

Substitute both into every dispatch site that follows — including the conditionally-used total-failure fallback reviewer template.

If `prepare-dispatch` exits non-zero, surface its stderr verbatim to the user and stop — do not dispatch any agent. Exit-2 messages name the offending path and the violated rule (symlink, prefix mismatch, non-file).

## Step 2c.5: Sentinel-First Verification Gate

After parallel reviewers (or the surviving subset) return, run a two-phase verification gate before Step 2d synthesis. Phase 1 verifies each reviewer's read-sentinel; Phase 2 extracts the JSON envelope only for reviewers that pass Phase 1.

The pre-dispatch SHA captured in Step 2a.5 (canonical computation path: the `prepare-dispatch` subcommand) is the expected value compared against each reviewer's sentinel here.

**Phase 1 — Sentinel verification (per reviewer):**

For each reviewer, write the reviewer's raw stdout to a tempfile (do NOT pipe through stdin to avoid shell-quoting hazards on four parallel outputs); use a tempfile path unique to this critical-review invocation. Sharing a path across invocations causes concurrent runs to corrupt each other's stdout (silent), and stale leftovers from prior sessions trip the Write tool's read-before-overwrite guard (noisy). Derive the path from `$LIFECYCLE_SESSION_ID` or `mktemp -d`. Then invoke:

```bash
cortex-critical-review check-artifact-stable \
    --feature <name> \
    --reviewer-angle <angle> \
    --expected-sha <hex> \
    --model-tier <haiku|sonnet|opus> \
    --input-file <tmpfile-path>
```

- `<hex>` is the same `{artifact_sha256}` captured in Step 2a.5 from `prepare-dispatch`.
- `<name>` is the same `--feature` argument used in Step 2a.5. The `<path>`-arg invocation form (no `--feature` in scope) skips telemetry, and the subcommand's write-guard now enforces this structurally: if you pass a `--feature` whose `cortex/lifecycle/{feature}/` directory does not exist, the subcommand suppresses the write and returns exit 4 (see below) rather than creating a phantom directory. On the `<path>`-arg form you may skip this verification step entirely — sentinel_absence telemetry has no lifecycle feature directory to write into.

Routes based on exit code:

- **Exit 0** — sentinel present on its own line (anywhere in the first 50 lines) AND SHA matches. Pass — proceed to Phase 2 for this reviewer.
- **Exit 3** — sentinel absent, SHA mismatch (drift), or `READ_FAILED` route, with a real `cortex/lifecycle/{feature}/` directory present. The subcommand has already appended the `sentinel_absence` event to `cortex/lifecycle/{feature}/events.log` atomically; the orchestrator MUST NOT append to `events.log` inline and MUST NOT invoke `record-exclusion` separately (would cause double-emission). Emit the standardized warning `⚠ Reviewer {angle} excluded: {reason}` to the orchestrator log; reason maps from the subcommand's stdout (`EXCLUDED absent | EXCLUDED sha_mismatch | EXCLUDED read_failed`).
- **Exit 4** — telemetry skipped: the target `cortex/lifecycle/{feature}/` directory does not exist, so the structural write-guard suppressed the `sentinel_absence` append rather than creating a phantom directory. This is a benign skip, distinct from exit 3: no event was persisted, the reviewer is neither excluded-for-drift nor failed, and the stdout verdict line still reflects the genuine check result. Treat the reviewer as a normal pass — proceed to Phase 2 for this reviewer; do not emit an exclusion warning and do not count it toward the all-reviewers-excluded total-failure path.

Excluded reviewers drop from ALL downstream tallies (A-class, B-class, C-class) AND from the untagged-prose pathway. Their output is not parsed for envelope JSON and not surfaced to the synthesizer as prose. Include the warning line in the synthesizer prompt preamble (Step 2d) so the synthesizer sees the partial reviewer set explicitly rather than silently working from a reduced count.

**Total-failure path (all reviewers excluded)**: when every reviewer returns exit 3, surface verbatim to the user — do NOT proceed to Step 2d synthesis:

`All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.`

**Phase 2 — Envelope extraction (only for reviewers that passed Phase 1):**

1. Locate the `<!--findings-json-->` delimiter using the LAST occurrence anchor — `re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)`, then split at the last match (tolerates prose quoting the delimiter).
2. `json.loads` the post-delimiter tail. Assert schema: top-level `angle: str`, `findings: list`; each finding has `class ∈ {"A","B","C"}`, `finding: str`, `evidence_quote: str`, optional `straddle_rationale: str`, optional `"fix_invalidation_argument": str`.
3. On any extraction or validation failure (no delimiter, JSON decode error, missing required field, invalid `class` enum), emit `⚠ Reviewer {angle} emitted malformed JSON envelope ({reason}) — class tags for this angle are UNAVAILABLE. Prose findings presented as-is; the B→A refusal gate will EXCLUDE this reviewer's findings from its count rather than treating them as C-class.` and pass the reviewer's prose findings to the synthesizer as an untagged block. Step 2d renders untagged prose under `## Concerns` and excludes it from the A-class tally. Do NOT silently coerce malformed envelopes to C-class. This malformed-envelope handler applies only AFTER Phase 1 sentinel verification has passed — a reviewer with a missing or drifted sentinel never reaches this path.

## Step 2d.5: Post-Synthesis (atomic SHA verification)

After the synthesizer agent returns, pipe its **full output** through the `check-synth-stable` subcommand before surfacing anything to the user or proceeding to Step 2e. This fuses sentinel-parse + SHA-match + drift-event append into one subprocess call; do NOT parse `SYNTH_READ_OK:` lines inline or append to `events.log` directly.

```bash
printf '%s' "$SYNTH_OUTPUT" | cortex-critical-review check-synth-stable \
    --feature <name> \
    --expected-sha <hex>
```

- `<hex>` is the same `{artifact_sha256}` captured in Step 2a.5 from `prepare-dispatch`.
- `<name>` is the same `--feature` argument used in Step 2a.5. The `<path>`-arg invocation form (no `--feature` in scope) skips telemetry, and the subcommand's write-guard now enforces this structurally: if you pass a `--feature` whose `cortex/lifecycle/{feature}/` directory does not exist, the subcommand suppresses the write and returns exit 4 (see below) rather than creating a phantom directory. On the `<path>`-arg form you may skip this verification step entirely — drift telemetry has no lifecycle feature directory to write into.

Routes based on exit code:

- **Exit 0** — synthesizer's `SYNTH_READ_OK:` sentinel present and SHA matches. Surface the synthesizer's prose output to the user normally, then proceed to Step 2e.
- **Exit 3** — sentinel absent OR SHA mismatch (drift), with a real `cortex/lifecycle/{feature}/` directory present. **Do NOT surface the synthesizer's prose output.** Instead, relay `check-synth-stable`'s own stdout verbatim to the user — its top-level diagnostic carries the `Critical-review pass invalidated` phrasing and the resolution instruction. The subcommand has already appended the `synthesizer_drift` event to `cortex/lifecycle/{feature}/events.log` atomically; the orchestrator must not duplicate that append.
- **Exit 4** — telemetry skipped: the target `cortex/lifecycle/{feature}/` directory does not exist, so the structural write-guard suppressed the `synthesizer_drift` append rather than creating a phantom directory. This is a benign skip, distinct from exit 3: no event was persisted and the synthesizer's verdict is otherwise treated as a clean pass. Surface the synthesizer's prose output normally and proceed to Step 2e.

On Exit 3, do NOT proceed to Step 2e (residue write) — the critical-review pass is invalidated and a stale residue write would compound the drift. Exit 4 does not invalidate the pass, so Step 2e proceeds as on Exit 0.

## Partial Coverage / Synthesis Failure Handling

If partial coverage occurred in Step 2c (some agents succeeded, some failed), unconditionally prefix the synthesis output with "N of M reviewer angles completed (K excluded for drift/Read failure)." before the synthesis narrative, where K is the count of reviewers excluded by Step 2c.5's sentinel-first gate (drift or Read-failure exclusions recorded via `record-exclusion`). When K = 0 the parenthetical is OMITTED entirely — emit only "N of M reviewer angles completed." to preserve existing behavior for clean runs.

If the synthesis agent fails, skip synthesis and present the raw per-angle findings from Step 2c directly. Step 3 and Step 4 (Apply Feedback) then operate on the raw findings instead of a synthesized narrative.

**Note:** Step 2d is skipped entirely when Step 2c's total-failure fallback was used — that path proceeds directly to Step 3.
