# Verification Gates (Step 2c.5 and Step 2d.5) — Implementation Detail

These gates wrap per-reviewer envelope extraction and post-synthesis SHA verification. The orchestrator must route through the canonical `cortex_command.critical_review` subcommands rather than shelling out to `git rev-parse`, `realpath`, or `sha256sum` directly, and must not append to `events.log` inline.

**Telemetry write-guard and exit 4 (shared by Steps 2c.5 and 2d.5).** Pass `--feature <name>` only on auto-trigger flows; the `<path>`-arg invocation form has no lifecycle feature directory to write telemetry into, so it skips verification entirely. Both `check-*` subcommands enforce this structurally: a `--feature` whose `cortex/lifecycle/{feature}/` directory is absent suppresses the event append and returns **exit 4** rather than creating a phantom directory — a benign skip, verdict otherwise clean. Distinct from exit 3 (directory present, drift/absence — the subcommand has already appended its event; don't duplicate the append or call `record-exclusion` separately). Each gate's `**Exit 4**` row below carries only its section-specific reaction.

## Step 2a.5: Pre-Dispatch (atomic path + SHA pin)

Before deriving angles or dispatching any agent, fuse path validation and SHA-256 computation into one subprocess call:

```bash
cortex-critical-review prepare-dispatch <artifact-path> [--feature <name>]
```

Pass `--feature <name>` only on auto-trigger flows (the lifecycle resolved `{feature}` from `$LIFECYCLE_SESSION_ID` against `cortex/lifecycle/*/.session` — see the Step 2e residue-write reference for the canonical resolver); the `<path>`-arg form omits it.

Capture the single-line JSON object printed to stdout. Schema: `{"resolved_path": "<absolute-path>", "sha256": "<64-hex>"}`. Bind `{artifact_path}` ← `resolved_path` and `{artifact_sha256}` ← `sha256`, and substitute both into every dispatch site that follows — including the conditionally-used total-failure fallback reviewer template.

If `prepare-dispatch` exits non-zero, surface its stderr verbatim to the user and stop — do not dispatch any agent. Exit-2 messages name the offending path and the violated rule (symlink, prefix mismatch, non-file).

## Step 2c.5: Sentinel-First Verification Gate

After parallel reviewers (or the surviving subset) return, run a two-phase gate before Step 2d synthesis: Phase 1 verifies each reviewer's read-sentinel; Phase 2 extracts the JSON envelope only for reviewers that pass Phase 1. The expected SHA is the one captured in Step 2a.5.

**Phase 1 — Sentinel verification (per reviewer):**

Write each reviewer's output — the final message the Agent tool returns — to a tempfile unique to this invocation (not stdin — shell-quoting hazards across parallel outputs; not a shared path — concurrent runs would corrupt each other's output, and stale leftovers trip the Write tool's read-before-overwrite guard). Derive the path from `$LIFECYCLE_SESSION_ID` or `mktemp -d`. Then invoke:

```bash
cortex-critical-review check-artifact-stable \
    --feature <name> \
    --reviewer-angle <angle> \
    --expected-sha <hex> \
    --artifact-path <resolved_path> \
    --model-tier <haiku|sonnet|opus> \
    --input-file <tmpfile-path>
```

`<hex>` and `<name>` are the same `{artifact_sha256}` and `--feature` bound in Step 2a.5.

Routes based on exit code:

- **Exit 0** — sentinel present on its own line (anywhere in the first 50 lines) AND SHA matches; OR sentinel absent but a re-hash of the pinned artifact at `--artifact-path` still matches `--expected-sha` (stable → advisory pass, tagged `sentinel_advisory`). Pass — proceed to Phase 2 for this reviewer.
- **Exit 3** — SHA mismatch (drift), or sentinel absent with a re-hash confirming drift or an unreadable artifact, or `READ_FAILED` route — event already appended (do not duplicate; see the shared write-guard note above). Emit `⚠ Reviewer {angle} excluded: {reason}` to the orchestrator log; reason maps from stdout (`EXCLUDED absent | EXCLUDED sha_mismatch | EXCLUDED read_failed`).
- **Exit 4** — telemetry skipped (see the shared write-guard note above). Treat as a normal pass — proceed to Phase 2; no exclusion warning, and don't count it toward the total-failure path.

Excluded reviewers drop from ALL downstream tallies (A-class, B-class, C-class) and from the untagged-prose pathway; their output is not parsed or surfaced to the synthesizer. Carry the exclusion warning into the Step 2d synthesizer preamble so the synthesizer sees the reduced reviewer set explicitly.

**Total-failure path (all reviewers excluded)**: when every reviewer returns exit 3, surface verbatim to the user — do NOT proceed to Step 2d synthesis:

`All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.`

**Phase 2 — Envelope extraction (only for reviewers that passed Phase 1):**

1. Locate the `<!--findings-json-->` delimiter using the LAST occurrence (`re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)`, split at the last match — tolerates prose that quotes the delimiter).
2. `json.loads` the post-delimiter tail. Assert schema: top-level `angle: str`, `findings: list`; each finding has `class ∈ {"A","B","C"}`, `finding: str`, `evidence_quote: str`, optional `straddle_rationale`, optional `fix_invalidation_argument`.
3. On any extraction or validation failure, emit `⚠ Reviewer {angle} emitted malformed JSON envelope ({reason}) — class tags UNAVAILABLE. Prose findings presented as-is; excluded from the A-class count rather than treated as C-class.`, then pass the reviewer's prose to the synthesizer as an untagged block. Step 2d renders it under `## Concerns`, excluded from the A-class tally — never silently coerced to C-class. This handler applies only after Phase 1 has passed; a reviewer with a missing or drifted sentinel never reaches it.

## Step 2d.5: Post-Synthesis (atomic SHA verification)

After the synthesizer returns, pipe its **full output** through `check-synth-stable` before surfacing anything or proceeding to Step 2e — fusing sentinel-parse + SHA-match + drift-event append into one subprocess call. Do not parse `SYNTH_READ_OK:` lines inline or append to `events.log` directly.

```bash
printf '%s' "$SYNTH_OUTPUT" | cortex-critical-review check-synth-stable \
    --feature <name> \
    --expected-sha <hex> \
    --artifact-path <resolved_path>
```

`<hex>` and `<name>` are the same `{artifact_sha256}` and `--feature` bound in Step 2a.5.

Routes based on exit code:

- **Exit 0** — `SYNTH_READ_OK:` sentinel present and SHA matches; OR sentinel absent but a re-hash of the pinned artifact at `--artifact-path` still matches `--expected-sha` (stable → advisory pass, tagged `sentinel_advisory`). Surface the synthesizer's prose normally, then proceed to Step 2e.
- **Exit 3** — SHA mismatch, or sentinel absent with a re-hash confirming drift or an unreadable artifact — event already appended (do not duplicate; see the shared write-guard note above). Do NOT surface the synthesizer's prose — relay `check-synth-stable`'s own stdout verbatim; it carries the `Critical-review pass invalidated` phrasing and the resolution instruction.
- **Exit 4** — telemetry skipped (see the shared write-guard note above). Surface the synthesizer's prose normally and proceed to Step 2e.

On Exit 3, do NOT proceed to Step 2e — the pass is invalidated and a stale residue write would compound the drift. Exit 4 doesn't invalidate the pass, so Step 2e proceeds as on Exit 0.

## Partial Coverage / Synthesis Failure Handling

If Step 2c had partial coverage, prefix the synthesis output with "N of M reviewer angles completed (K excluded for drift/Read failure)." before the narrative, where K is the count excluded by Step 2c.5. When K = 0, omit the parenthetical — emit only "N of M reviewer angles completed." to preserve existing behavior for clean runs.

If the synthesis agent fails, skip synthesis and present the raw per-angle findings from Step 2c directly; Step 3 and Step 4 then operate on those findings instead of a synthesized narrative.

**Note:** Step 2d is skipped entirely when Step 2c's total-failure fallback was used — that path proceeds directly to Step 3.
