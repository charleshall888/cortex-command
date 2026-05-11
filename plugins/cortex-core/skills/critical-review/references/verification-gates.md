# Verification Gates (Step 2c.5 and Step 2d.5) — Implementation Detail

These gates wrap the per-reviewer envelope extraction and the post-synthesis
SHA verification. The orchestrator MUST route through the canonical
`cortex_command.critical_review` subcommands rather than shell out to
`git rev-parse`, `realpath`, or `sha256sum` directly, and MUST NOT append
to `events.log` inline.

## Step 2a.5: Pre-Dispatch (atomic path + SHA pin)

Before deriving angles or dispatching any agent, fuse path validation and SHA-256 computation into a single subprocess call:

```bash
python3 -m cortex_command.critical_review prepare-dispatch <artifact-path> [--feature <name>]
```

- `<artifact-path>` is the candidate artifact path resolved in Step 1 (e.g. `lifecycle/{feature}/plan.md` or the explicit `<path>` argument from `/cortex-core:critical-review <path>`).
- Pass `--feature <name>` only on auto-trigger flows (the lifecycle resolved `{feature}` from `$LIFECYCLE_SESSION_ID` against `lifecycle/*/.session` — see the Step 2e residue-write reference for the canonical resolver). The `<path>`-arg invocation form (`/cortex-core:critical-review <path>`) omits `--feature`.

Capture the single-line JSON object printed to stdout. Schema: `{"resolved_path": "<absolute-path>", "sha256": "<64-hex>"}`. Bind:

- `{artifact_path}` ← `resolved_path`
- `{artifact_sha256}` ← `sha256`

Substitute both into every dispatch site that follows: the per-angle reviewer template, the total-failure fallback reviewer template, and the synthesizer template.

If `prepare-dispatch` exits non-zero, surface its stderr verbatim to the user and stop — do not dispatch any agent. Exit-2 messages name the offending path and the violated rule (symlink, prefix mismatch, non-file).

## Step 2c.5: Sentinel-First Verification Gate

After parallel reviewers (or the surviving subset) return, run a two-phase verification gate before Step 2d synthesis. Phase 1 verifies each reviewer's read-sentinel; Phase 2 extracts the JSON envelope only for reviewers that pass Phase 1.

The orchestrator captures the pre-dispatch SHA-256 of the artifact into orchestrator context before fan-out (see the `verify-synth-output` subcommand for the canonical computation path). That captured SHA is the expected value compared against each reviewer's sentinel here.

**Phase 1 — Sentinel verification (per reviewer):**

1. Read the reviewer's first output line. Expected form: `READ_OK: <path> <sha>` (success sentinel) or `READ_FAILED: <absolute-path> <reason>` (read-failure sentinel).
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

## Step 2d.5: Post-Synthesis (atomic SHA verification)

After the synthesizer agent returns, pipe its **full output** through the `verify-synth-output` subcommand before surfacing anything to the user or proceeding to Step 2e. This fuses sentinel-parse + SHA-match + drift-event append into one subprocess call; do NOT parse `SYNTH_READ_OK:` lines inline or append to `events.log` directly.

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

## Partial Coverage / Synthesis Failure Handling

If partial coverage occurred in Step 2c (some agents succeeded, some failed), unconditionally prefix the synthesis output with "N of M reviewer angles completed (K excluded for drift/Read failure)." before the synthesis narrative, where K is the count of reviewers excluded by Step 2c.5's sentinel-first gate (drift or Read-failure exclusions recorded via `record-exclusion`). When K = 0 the parenthetical is OMITTED entirely — emit only "N of M reviewer angles completed." to preserve existing behavior for clean runs.

If the synthesis agent fails, skip synthesis and present the raw per-angle findings from Step 2c directly. Step 3 and Step 4 (Apply Feedback) then operate on the raw findings instead of a synthesized narrative.

**Note:** Step 2d is skipped entirely when Step 2c's total-failure fallback was used — that path proceeds directly to Step 3.
