# Research: Relax over-firing positional check in critical-review sentinel gate (Step 2c.5)

## Codebase Analysis

### Where the "first-line" semantics live today

There is **no code-level parser** for `READ_OK`. The Step 2c.5 Phase 1 check is enforced entirely by orchestrator-following prose. The synthesizer side has a working code parallel that the reviewer side does not.

Prose-driven enforcement sites (the lines the fix will touch):

- `skills/critical-review/references/verification-gates.md:37` — *"Read the reviewer's first output line. Expected form: `READ_OK: <path> <sha>` ... or `READ_FAILED: <absolute-path> <reason>` ..."*
- `skills/critical-review/references/verification-gates.md:39` — *"**Pass** — first line is `READ_OK: <path> <sha>` AND `<sha>` equals the orchestrator's pre-dispatch SHA."*
- `skills/critical-review/references/verification-gates.md:40` — *"**Exclude (SHA drift)** — first line is `READ_OK: <path> <sha>` but `<sha>` differs ..."*
- `skills/critical-review/references/verification-gates.md:41` — *"**Exclude (sentinel absent)** — first line is neither a `READ_OK:` nor a `READ_FAILED:` line."*
- `skills/critical-review/references/verification-gates.md:42` — *"**Exclude (read failure)** — first line is `READ_FAILED: <path> <reason>`."*
- `skills/critical-review/SKILL.md:60` — reviewer-prompt summary that paraphrases "first line."
- `skills/critical-review/SKILL.md:70` — Step 2c.5 summary that paraphrases "first-line sentinel."

Reviewer-side prompts that instruct the sentinel emission position:

- `skills/critical-review/references/reviewer-prompt.md:20` — *"...emit `READ_OK: <path> <sha>` as the first line of output ..."*
- `skills/critical-review/references/reviewer-prompt.md:22` — *"...emit `READ_FAILED: ...` as the first line of output ..."*
- `skills/critical-review/references/fallback-reviewer-prompt.md:19,21` — identical positional wording.

### Synthesizer-side parallel (the mirror model)

The fix can directly mirror an existing pattern at `cortex_command/critical_review.py:189-216`:

```python
_SYNTH_RE = re.compile(r"^SYNTH_READ_OK: (\S+) ([0-9a-f]{64})$", re.MULTILINE)

def verify_synth_output(output: str, expected_sha: str) -> tuple[str, str | None]:
    m = _SYNTH_RE.search(output)
    if not m:
        return ("absent", None)
    observed = m.group(2)
    if observed != expected_sha:
        return ("mismatch", observed)
    return ("ok", observed)
```

Crucially, the synthesizer side **already uses `re.MULTILINE` with an `^...$` anchor and accepts the sentinel on any line** — it has no positional constraint. The synthesizer prompt at `synthesizer-prompt.md` correspondingly says "emit `SYNTH_READ_OK: <path> <sha>` as a line in your output" (not "first line"). The reviewer-side strict-first-line rule is an asymmetry, not a project-wide pattern.

Subcommand wiring (`_cmd_verify_synth_output` at `:346`, argparse at `:454-463`) is the template for the proposed new `verify-reviewer-output` subcommand.

### `record-exclusion` contract (must be preserved)

At `cortex_command/critical_review.py:396-419`. Argument schema: `--feature`, `--reviewer-angle`, `--reason ∈ {absent, sha_mismatch, read_failed}`, `--model-tier ∈ {haiku, sonnet, opus}`, `--expected-sha`, `--observed-sha`. Event payload schema (eight fields): `{ts, event: "sentinel_absence", feature, reviewer_angle, reason, model_tier, expected_sha, observed_sha_or_null}`. Exit codes: 0 on success, 2 on OSError. The fix changes only which reviewers route into `record-exclusion`; it does not change the subcommand contract.

Events-registry row at `bin/.events-registry.md:112` lists producer line range `cortex_command/critical_review.py:354-363` (already stale; actual emit is `:403-413`). Consumer column: `(future per-tier compliance audit)` — no live consumer.

### MUST-anchor inventory in `skills/critical-review/`

Only two locations contain MUST/MUST NOT, both anchoring the no-inline-events.log / canonical-subcommand routing invariant:

- `skills/critical-review/SKILL.md:46` — *"The orchestrator MUST NOT shell out to `git rev-parse`, `realpath`, or `sha256sum` directly, and MUST NOT instruct dispatched reviewers to do so."*
- `skills/critical-review/references/verification-gates.md:4-7` — *"The orchestrator MUST route through the canonical `cortex_command.critical_review` subcommands ... and MUST NOT append to `events.log` inline."*

Neither encodes positional first-line semantics. The Phase 1 rule at lines 35-58 of `verification-gates.md` is prose-only (no MUST language). The fix does not need to touch any MUST. The post-Opus-4.7 MUST-escalation policy at CLAUDE.md:72-80 is **not triggered**.

### Voice-anchor inventory (preserve per #082 / #085)

- `skills/critical-review/SKILL.md:97` — *"Do not soften or editorialize."* (Note: ticket #229 Out of Scope cited line 97; actual line may shift slightly, exact text preserved.)
- `skills/critical-review/SKILL.md:52` — distinct-angle rule.
- `skills/critical-review/references/reviewer-prompt.md:60` — *"Do not cover other angles. Do not be balanced."*
- `skills/critical-review/references/synthesizer-prompt.md:50` — *"Do not be balanced. Do not reassure."*

All four anchors are out of the editing range for both candidate fix-shapes.

### Existing test coverage (gaps)

Exists:
- `tests/test_critical_review_path_validation.py` — covers `prepare_dispatch` / `validate_artifact_path` (Step 2a.5). 14 cases. **No Phase 1 coverage.**
- `tests/test_dispatch_template_placeholders.py:157-181` — asserts `READ_OK: <path> <sha>` and `SYNTH_READ_OK: <path> <sha>` substrings appear in SKILL.md. Static-text only.
- `tests/test_critical_review_classifier.py` — exercises the synthesizer A→B rubric via live `claude -p`. Marked `@pytest.mark.slow`.

Does not exist:
- No unit test for `verify_synth_output` (indirect coverage only).
- No unit test for `record-exclusion`.
- No fixture saving lifecycle-109 reviewer outputs as a regression corpus.

The reviewer-side Phase 1 verification has **zero automated coverage today**.

### False-positive risk surface

The reviewer prompt at `reviewer-prompt.md:60-76` requires each finding to carry an `evidence_quote` with verbatim artifact text. When the artifact under review names `READ_OK:` (e.g., this ticket's own spec, `verification-gates.md` itself, `bin/.events-registry.md` row), a reviewer can legitimately emit prose lines or JSON envelope strings containing the literal pattern. Mitigations identified by the tradeoffs and adversarial agents:

1. Tight regex: `re.compile(r"^READ_OK: (\S+) ([0-9a-f]{64})\s*$", re.MULTILINE)`. `^...$` rejects blockquote-prefixed (`> READ_OK:`) lines. The 64-hex-char SHA group rejects the literal prompt example (which uses `<sha>` placeholder).
2. **First-match-whose-SHA-equals-expected** (not just first-match): if multiple `READ_OK:` lines appear in the window, classify against the first one whose `group(2) == expected_sha`. If none match, classify as `mismatch` against the first observed SHA. This is materially different from the synth-side `verify_synth_output`'s "first match" logic — see Adversarial F2.
3. Window cap on lines scanned (recommended 50, ticket suggested 20).
4. Open: code-fence-aware parsing (strip ` ``` ` blocks before regex). Not load-bearing if (1)+(2)+(3) hold; spec-phase decision pending empirical evidence from fixtures.

### Plugin-mirror parity gap

`tests/test_plugin_mirror_parity.py:28-32` defines `MIRRORED_FILENAMES = ("plan.md", "specify.md", "orchestrator-review.md")` — lifecycle references only. **No CI parity test covers `skills/critical-review/` against its mirror at `plugins/cortex-core/skills/critical-review/`.** A `--no-verify` commit could drift the mirror.

### Files that will change

Recommended approach (P-CODE × S-WINDOW with first-match-matching-SHA):

**Canonical sources to edit:**
1. `cortex_command/critical_review.py` — add `_REVIEWER_RE` constant, `verify_reviewer_output(output, expected_sha, window_lines=N) -> tuple[str, str|None]` function, `_cmd_verify_reviewer_output` argparse subcommand mirroring `_cmd_verify_synth_output`.
2. `skills/critical-review/references/verification-gates.md` — rewrite Phase 1 prose at lines 35-58 to invoke `cortex-critical-review verify-reviewer-output --feature <name> --expected-sha <hex> --input-file <path>` (the same idiom as the synth-side `verify-synth-output` callout at lines 73-79). Do NOT touch lines 1-7 (the preamble MUSTs).
3. `skills/critical-review/SKILL.md` — update the Step 2c.5 summary at line 70 to match the new prose. Do NOT touch the voice anchor at line 97.
4. `skills/critical-review/references/reviewer-prompt.md:20,22` — soften "as the first line of output" to "on its own line before the first `## ` heading; preceding preamble is acceptable." (Adversarial F6: in-scope as a prompt/parser truth alignment.)
5. `skills/critical-review/references/fallback-reviewer-prompt.md:19,21` — same edit as #4.
6. `tests/test_critical_review_sentinel_window.py` (new) — unit tests for `verify_reviewer_output` covering positive (lines 1/3/5/15/20), negative (absent, sha_mismatch, sentinel-in-evidence-quote at line 25 out of window), adversarial (multiple sentinels with one matching SHA, blockquoted sentinel, BOM, CRLF, fenced-code sentinel).
7. `tests/fixtures/critical-review/reviewer-outputs/` (new directory) — named fixtures with `.meta.json` describing expected classifications.
8. `tests/test_plugin_mirror_parity.py:28-32` — extend `MIRRORED_FILENAMES` to also cover `skills/critical-review/{SKILL.md, references/*.md}` against their `plugins/cortex-core/...` mirrors. (Adversarial F10.)
9. `bin/.events-registry.md:112` — update producer line range; add rationale note for the over-fire-bug fix as a discontinuity marker for future audit consumers. (Adversarial F4.)

**Not edited (mirror-managed):** `plugins/cortex-core/skills/critical-review/...` regenerates via pre-commit hook.

## Web Research

### Critical finding — prefilling is deprecated on Opus 4.7 / 4.6 / Sonnet 4.6

Anthropic's `platform.claude.com/docs/en/build-with-claude/prompt-engineering/prefill-claudes-response` documents that prefilling assistant messages is **no longer supported** on Claude Opus 4.7, Opus 4.6, or Sonnet 4.6. The 400 error is reproduced in `livekit/agents#4907`. Anthropic's migration guidance points to structured outputs and system-prompt format examples; the only mechanism that reliably forced literal-first-line output is gone.

### Anthropic's positive recommendation: XML-tag fencing

`platform.claude.com/docs/en/build-with-claude/prompt-engineering/use-xml-tags` — structure outputs with named XML tags (`<sentinel>...</sentinel>`) so downstream parsers extract by tag name, not position. Cited drop in hallucinations from 19% to <4% when responses cite verbatim from inside tags. Position-agnostic by design.

### Opus 4.7 calibrates verbosity to perceived task complexity

`platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices` — when the reviewer is asked for substantive review, the model produces a paragraph of framing before getting to the marker because that *is* literally following "do a thorough review." The recommended counter is an explicit format example, not a "must be first line" imperative.

### Community precedents

- **`kourgeorge/prompt-sentinel`** (GitHub) — uses BEGIN/END markers anchored to their own lines (not to first-line), `re.MULTILINE` scan over the full response. Direct precedent for window-tolerant sentinel matching.
- **`dev.to/pockit_tools` (2026 structured-output guide)** — survey of regex-on-prose failure modes: leading whitespace, model-introduced markdown fences, accidental sentinel echoes inside quoted reasoning. Recommends multi-character delimiters parsed as a window, not a strict prefix.
- **`dev.to/moonrunnerkc` (outcome-based verification)** — pattern-matching narration ("committed 3 files") is the failure mode; SHA / git diff / test results are the load-bearing checks. Reinforces that the SHA-match leg of the current gate is the substantive defense.
- **OWASP LLM Prompt Injection Prevention Cheat Sheet** — common delimiters (triple backticks, `BEGIN:`) can appear inside quoted user content; recommend uniqueness or position-on-its-own-line constraints.

### Anti-patterns documented

- "Must be the first line" as a prose imperative under Opus 4.7+: with prefilling deprecated and verbosity calibrated to complexity, the model satisfies "include the sentinel" without satisfying "exactly at position zero."
- Prefix-only regex on free-text agent output: first thing to break when models change verbosity calibration.
- Delimiter strategies without uniqueness or position-on-its-own-line constraints.
- Pattern-matching narration as proof of action (without SHA / outcome verification).

### Net implication

Relaxing the position check from "first line" to "anywhere in the response on its own line, with SHA still enforced" aligns with current Anthropic guidance and published community practice. SHA-match remains the substantive proof-of-read; marker presence is the participation probe; position-zero strictness is the part that breaks under post-prefill Claude behavior with no documented justification to keep it.

## Requirements & Constraints

### Tag-load result

Backlog item tags: `[critical-review, skills, verification-gate]`. Case-insensitive substring match against `cortex/requirements/project.md` Conditional Loading phrases (lines 66-69) — **zero matches**. The fallback per `skills/lifecycle/references/load-requirements.md` step 5 applies: `project.md` only (plus Global Context: `glossary.md`, recorded as skipped — file absent). No area-doc constraints from `multi-agent.md` / `pipeline.md` / `observability.md` / `remote-access.md` formally in scope.

### Applicable architectural constraints

1. **Skill-helper modules** (`cortex/requirements/project.md:31`): *"when a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry."* The current Phase 1 prose check is exactly the paraphrase-prone ceremony the constraint says to collapse. Pulls strongly toward P-CODE.
2. **Structural separation over prose-only enforcement** (`CLAUDE.md:58`): *"Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction."*
3. **Design principle: prescribe What and Why, not How** (`CLAUDE.md:64-70`): "First line" is a How specification; "emit somewhere in your output" is a What specification.
4. **Solution horizon** (`cortex/requirements/project.md:21`): future `READ_PARTIAL` or similar new sentinel types are on the horizon (Out of Scope on #229 today, but mentioned). P-CODE makes the extensible answer; P-PROSE perpetuates paraphrase drift across two mirror files + per-run agent paraphrase.
5. **Events.log schema stability** (`bin/.events-registry.md:112`): the eight-field `sentinel_absence` payload is a contract; cannot change. Fix changes only which reviewers route into `record-exclusion`.
6. **MUST-escalation policy preconditions** (`CLAUDE.md:72-80`): adding new MUSTs requires evidence artifact + effort=high failure. Fix does not add new MUSTs; existing MUSTs grandfathered.
7. **SKILL.md size cap** (500 lines): SKILL.md is 116 lines, verification-gates.md is 97 lines. Comfortable headroom.

### Backlog #082 / #085 voice-anchor requirement

#085 (Scope exclusions / Preservation rules from #053) explicitly lists:
- `critical-review/SKILL.md` "Do not soften or editorialize" (fights Opus warmth training) — currently SKILL.md:97.
- `critical-review/SKILL.md` distinct-angle rule (load-bearing for parallel-anchoring-free differentiator) — currently SKILL.md:52.
- `reviewer-prompt.md:60` ("Do not cover other angles. Do not be balanced.")
- `synthesizer-prompt.md:50` ("Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.")

Backlog #229's Out of Scope restates this. The fix must not touch these specific anchored lines.

### Auto-trigger blast radius

Critical-review is invoked from:
- **Lifecycle spec pre-approval** when tier=complex AND criticality ∈ {medium, high, critical} (spec.md ⇒ critical-review).
- **Lifecycle plan pre-approval** under the same gating (plan.md ⇒ critical-review).
- **Manual** invocation: `/cortex-core:critical-review [<artifact-path>]`.

When skipped (tier=complex AND criticality=low), `lifecycle_critical_review_skipped` is emitted (distinct event, not affected).

### No live `sentinel_absence` consumers

Searched `cortex_command/overnight/report.py` and `cortex_command/dashboard/` for `sentinel_absence` — zero hits. The events-registry consumer column reads `(future per-tier compliance audit)`. No current code computes a rate or alarm. **However**, the fix introduces a historical-baseline discontinuity at the fix-commit date — any future audit comparing pre-fix and post-fix `sentinel_absence` volume will see a step change driven by the over-fire correction. Mitigation: append a rationale entry to the events-registry row noting the over-fire bug fix and date.

### Critical-review's deliberate requirements-loading exemption

`skills/critical-review/SKILL.md:42`: *"Critical-review intentionally narrows its context to the parent `cortex/requirements/project.md` Overview only (~250 words) and does NOT participate in the tag-based requirements-loading protocol... Do not 'fix' this exemption by wiring tag-based loading into the dispatch path."* Out of scope for #229.

## Tradeoffs & Alternatives

Evaluated a 2×4 matrix:
- **Axis 1 (parser location)**: P-PROSE (orchestrator-following prose) vs P-CODE (new `verify-reviewer-output` subcommand).
- **Axis 2 (match strategy)**: S-WINDOW (first N lines), S-HEADING (before first `## `), S-STRUCTURED (`<sentinel>...</sentinel>`), S-LAST (last occurrence anywhere).

### Cell verdicts

- **(P-PROSE × S-WINDOW)**: Lowest immediate effort but architecturally regressive — moves away from the established `_SYNTH_RE` / `verify_synth_output` trajectory while editing the very file that documents it. Violates Skill-helper modules constraint.
- **(P-PROSE × S-HEADING)**: Dominated by S-WINDOW under P-PROSE; brittle to fenced code, blockquoted `## `, and reviewer preambles that themselves start with `## `.
- **(P-PROSE × S-STRUCTURED)**: Pushes failure mode upstream into reviewer compliance — same evidence (agents preamble despite emphatic instructions) predicts they will preamble before `<sentinel>` tags too. Breaks the lifecycle-109 corpus as test input.
- **(P-PROSE × S-LAST)**: Semantically wrong — last `READ_OK:` is most likely inside a paraphrasing block.
- **(P-CODE × S-WINDOW)**: **Recommended.** Direct mirror of `_SYNTH_RE` / `verify_synth_output`. Satisfies Skill-helper modules constraint. Test-translatable (corpus → pytest cases). MUST-anchor proximity strictly lower than prose edits. More reversible (single `git revert`). More extensible (future `READ_PARTIAL` is a one-function extension).
- **(P-CODE × S-HEADING)**: Dominated by S-WINDOW — heading rule is harder to express robustly in code (fenced code, indented headings, reviewer preambles containing `## `).
- **(P-CODE × S-STRUCTURED)**: Code parser trivial but still requires reviewer prompt changes, still depends on reviewer compliance, breaks the corpus as test input.
- **(P-CODE × S-LAST)**: Same semantic mis-fit as P-PROSE × S-LAST.

### Recommended: P-CODE × S-WINDOW with first-match-matching-SHA

Adversarial F2 escalates the match strategy from naive first-match to **first-match-whose-group(2)-equals-expected-SHA**. Implementation: iterate all matches in the window; return the first whose extracted SHA equals `expected_sha`. If no match has the expected SHA but at least one was found, classify as `mismatch` against the first observed SHA. If no match at all, classify as `absent`. This defeats the self-defeating-loop attack where a reviewer reviewing this fix's own spec.md quotes literal `READ_OK: <path> <real-sha>` patterns in evidence quotes.

### False-positive defense composition

1. `^...$` with `re.MULTILINE` rejects leading prose (e.g., `> READ_OK:` blockquoted lines, indented code).
2. 64-hex-char SHA group rejects the literal `<sha>` placeholder in `reviewer-prompt.md:20`.
3. Window cap bounds scan and excludes deep-buried evidence quotes (recommended 50, ticket suggested 20 — spec-phase decision).
4. First-match-matching-SHA semantics defeat self-defeating loop where artifact text contains literal `READ_OK:` with real SHA.
5. Open: code-fence-aware parsing — defer pending fixture evidence (Adversarial A4).

### Belt-and-suspenders verdict

Rejected. Adding a prompt-side structured-sentinel change (Approach 3) pays the prompt-change cost without buying real parser determinism (agents will preamble before `<sentinel>` tags the same way they preamble before `READ_OK:`), and invalidates the corpus as test input. The one prompt-side change that IS defensible is non-routing: aligning `reviewer-prompt.md:20` "first line" → "on its own line before the first `## ` heading; preceding preamble is acceptable" so prompt and parser tell the same story. This is documentation-truth alignment, not a defensive layer, and is in scope.

## Adversarial Review

Severity legend: showstopper / serious / minor / informational.

### F1. Per-reviewer subprocess I/O contract is undocumented (serious)

The fix-proposal says "subprocess call" but does not specify how 4 reviewer outputs (each containing backticks, `$()`-shaped content, quoted markdown, JSON envelopes with embedded quotes) get to the helper. Heredoc-style `printf '%s' "$REVIEWER_OUTPUT" | cortex-critical-review verify-reviewer-output ...` is a shell-quoting hazard and an injection vector. **Mitigation:** Specify `--input-file <path>` over stdin. Orchestrator writes each reviewer's output to `$TMPDIR/reviewer-<angle>.txt` (via the `Write` tool, not Bash heredoc), passes `--input-file`, unlinks after. Avoids quoting entirely.

### F2. First-match semantics admit false positives via self-defeating loop (serious — showstopper-blocking)

A reviewer reviewing this fix's own spec.md (or `verification-gates.md` itself) will emit `evidence_quote` strings containing literal `READ_OK: <path> <real-sha>` patterns. The artifact under review contains real 64-hex SHAs (the wild-light events.log SHAs cited in the verification corpus). Naive first-match returns whichever `READ_OK:` line appears earliest in the window — which can be a quoted-artifact line, not the reviewer's own sentinel. **Mitigation:** Change parser semantics to "first match whose `group(2) == expected_sha`." Implementation: iterate `_REVIEWER_RE.finditer(window)`, return the first match whose SHA equals expected. If none, classify as `mismatch` against the first observed SHA. If no matches at all, classify as `absent`.

### F3. Lifecycle 109 corpus is unverifiable from this repo (serious)

Acceptance criterion 5 ("seven sentinel_absence events flip to pass under the new rule") requires retrieving saved reviewer outputs from another repo's transcripts. Anthropic transcript retention duration is not confirmed. The wild-light repo is external to this repo's CI. **Recommended spec-phase decision: re-create synthetically.** Schedule one or two `/critical-review` runs against an in-repo lifecycle artifact, capture raw reviewer outputs to `tests/fixtures/critical-review/reviewer-outputs/`, use as regression fixtures. Frame the lifecycle-109 evidence as motivating context, not validation surface. Rewrite acceptance criterion 5 to point at in-repo fixtures.

### F4. Historical-baseline discontinuity at the fix-commit date (minor → informational)

Relaxing the gate drops `sentinel_absence` volume substantially (mostly `reason: absent` events). A future per-tier compliance audit comparing pre- and post-fix volumes will see a step change. **Mitigation:** One-line entry in `bin/.events-registry.md:112` rationale column noting the over-fire bug fix date as a discontinuity marker. No new event type.

### F5. SHA-match check is the load-bearing defense, not position (informational)

The bar against true hallucination is SHA collision (~1 in 2^256). Lowering the position constraint does not lower this bar. The realistic attack is a reviewer that "remembers" the expected SHA from its prompt (`reviewer-prompt.md:16` says "Expected SHA-256: {artifact_sha256}") and emits a fabricated `READ_OK: <path> <expected-sha>` line without actually Reading. **The current strict-first-line rule does not defend against this either.** Trust model relies on reviewer incentive-compatibility — findings without Read produce nothing useful. Document explicitly in the spec's "Why this is safe" subsection.

### F6. Prompt-side update IS in scope, not optional (serious)

If `reviewer-prompt.md:20` keeps saying "as the first line" while the parser accepts anywhere in N lines: (1) documentation lies about implementation; (2) behavioral drift over future model versions (a stricter-following model would emit at line 1, but a prompt change might be required to make Opus 4.7 emit at all without preamble); (3) violates CLAUDE.md:64-70 "prescribe What and Why, not How." **Mitigation:** Update `reviewer-prompt.md:20,22` and `fallback-reviewer-prompt.md:19,21` to "emit `READ_OK: <path> <sha>` on its own line before producing any findings (preceding preamble exposition is acceptable, but the sentinel must appear before the first `## ` heading)." A 2-line edit; in scope. Do NOT touch `synthesizer-prompt.md` — its prompt is already loose-positional and matches its parser.

### F7. Test surface must expand to ~12-15 cases (serious)

Positive: sentinel at lines 1/3/5/15/20. Negative: absent, SHA-mismatch, sentinel-in-evidence-quote at line 25 (out of window). Adversarial: multiple `READ_OK:` lines in window with one matching expected SHA, blockquoted `> READ_OK:` (regex correctly excludes), BOM-prefixed first line, CRLF line endings, sentinel inside ` ``` ` fence (current regex would match — defer or mitigate per A4). Each as a named fixture at `tests/fixtures/critical-review/reviewer-outputs/<case-name>.txt` with `.meta.json` describing expected classification.

### F8. MUST-anchor edit-boundary risk under P-CODE is minor but real (minor)

The new prose lands at `verification-gates.md:35-58`. The MUSTs at lines 4-7 are in the file preamble. Spec-phase author could accidentally re-flow the preamble. **Mitigation:** Pin edit boundary in spec.md — explicitly forbid touching `verification-gates.md:1-7` (preamble paragraph + MUST sentence), `SKILL.md:46` (no-shell-out MUST), `SKILL.md:97` (voice anchor), `SKILL.md:52` (distinct-angle rule), `synthesizer-prompt.md:50` (voice anchor), `reviewer-prompt.md:60` (voice anchor).

### F9. Synth-side cleanliness is informational, not predictive (informational)

The synthesizer is one Opus agent emitting one sentinel in a structured-findings context. The reviewer side is 4 agents (Sonnet or general-purpose) emitting sentinels in less-structured contexts with evidence_quote fields. The structural difference is large. **Better evidence anchor:** the synthesizer prompt at `synthesizer-prompt.md` already says "as a line in your output before any per-finding analysis" (loose-positional), and that prompt-parser pair has been stable in production — that's the load-bearing precedent, not anecdata about false-positive counts.

### F10. Plugin-mirror parity gap is real (minor)

`tests/test_plugin_mirror_parity.py:28-32` `MIRRORED_FILENAMES` covers `("plan.md", "specify.md", "orchestrator-review.md")` — lifecycle references only, NOT critical-review references. A `--no-verify` commit could drift the mirror. **Mitigation:** Extend the test to cover `skills/critical-review/SKILL.md` and `skills/critical-review/references/*.md` against `plugins/cortex-core/skills/critical-review/` mirrors. In scope for this ticket.

### Security concerns

- **S1 (heredoc injection)**: Mitigated by F1 — use `--input-file` not stdin/heredoc.
- **S2 (artifact-embedded SHA attack)**: Empty surface — an adversarial artifact author cannot make their embedded SHA equal the SHA of the file they're authoring (chicken-and-egg).

### Assumptions that may not hold

- **A1**: Reviewer outputs are UTF-8. Mitigation: open `--input-file` with `encoding='utf-8'`, errors='strict' (fail loud on mixed encodings).
- **A2**: 20-line window suffices. Recommend bumping to 50 — first-match-matching-SHA semantics make window size non-load-bearing; 50 is empirically safer for Opus 4.7's verbosity calibration.
- **A3**: Naive first-match works. It doesn't — see F2.
- **A4**: Code-fence-aware parsing is necessary. Unverified. Defer pending fixture evidence; document as known limitation if synthetic fixtures show no fenced false positives.

## Open Questions

The following are spec-phase user decisions, not investigation-resolvable:

1. **Corpus access — synthetic re-creation vs external retrieval?** Adversarial F3 recommends rewriting acceptance criterion 5 to point at in-repo synthetic fixtures rather than the unverifiable lifecycle-109 corpus. Confirm at spec time: (a) re-create synthetically (recommended), (b) attempt external retrieval, or (c) drop the criterion to design-only motivation. *Deferred: will be resolved in Spec by asking the user.*

2. **Window size — 20 lines (ticket) vs 50 lines (adversarial)?** Adversarial A2 recommends 50 for robustness to Opus 4.7's verbosity calibration; ticket suggested 20. First-match-matching-SHA semantics make window size a secondary defense rather than load-bearing. *Deferred: will be resolved in Spec by asking the user.*

3. **Code-fence-aware parsing — in-scope or deferred-as-known-limitation?** Adversarial A4 recommends deferring pending fixture-corpus evidence. *Deferred: will be resolved in Spec by asking the user, after fixture survey.*

4. **Prompt-side update scope — in this ticket or carved out?** Adversarial F6 recommends including `reviewer-prompt.md:20,22` + `fallback-reviewer-prompt.md:19,21` updates in scope (2-line edit, documentation-truth alignment). Ticket's Out of Scope did not explicitly include or exclude these. *Deferred: will be resolved in Spec by asking the user.*

5. **Plugin-mirror parity test scope — extend in this ticket or separate ticket?** Adversarial F10 recommends extending `tests/test_plugin_mirror_parity.py` to cover critical-review references in this ticket. Independent of the gate fix but identified by the research. *Deferred: will be resolved in Spec by asking the user.*
