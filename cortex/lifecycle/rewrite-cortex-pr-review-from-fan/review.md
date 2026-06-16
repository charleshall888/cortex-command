# Review: rewrite-cortex-pr-review-from-fan

## Stage 1: Spec Compliance

### Requirement 1: Collapse to one full-context reviewer agent
- **Expected**: Skill dispatches a single high-effort reviewer that gathers its own context (diff, touched/related files, CLAUDE.md) and emits the finding schema; no parallel critics, triage, or synthesizer. Operative-section grep for fan-out vocab = 0.
- **Actual**: `protocol.md` "## One full-context reviewer dispatch" describes exactly one reviewer dispatch with no intermediate hops. `grep -ciE 'haiku|triage|four[ -]|fan-out|synthesizer|parallel critic' protocol.md` = 0. SKILL.md describes the skill as "a thin shell around one reviewer." The runtime dispatch behavior is exercised by the Req 11/Task 7 contract test as specified.
- **Verdict**: PASS

### Requirement 2: Replace the 821-line five-stage protocol with a single-pass description
- **Expected**: `grep -ciE '(stage|step|pass|phase) [0-9]' protocol.md` = 0 AND `wc -l protocol.md` ≤ 200.
- **Actual**: Stage/step/pass/phase-N grep = 0; protocol.md is 148 lines (was 891 in the diff). Decisions/gates/output-shape framing, not step-by-step method.
- **Verdict**: PASS

### Requirement 3: Delete `evidence-ground.sh`
- **Expected**: `test ! -e .../scripts/evidence-ground.sh` exits 0.
- **Actual**: File absent (553-line deletion confirmed in the diff stat). Grounding moved in-context per Req 6.
- **Verdict**: PASS

### Requirement 4: De-pin the model
- **Expected**: `grep -rc 'claude-opus-4-7' plugins/cortex-pr-review/` = 0.
- **Actual**: 0 across all plugin files. protocol.md "## One full-context reviewer dispatch" states "Session-default / highest-available. Do not pin a model id"; output-format footer says "Do not pin or hardcode a model id."
- **Verdict**: PASS

### Requirement 5: Update frontmatter, manifest, preconditions; correct two doc errors
- **Expected**: `grep -ci 'multi-agent' plugin.json` = 0; distinctness note present (`grep -c 'review_dispatch' SKILL.md` ≥ 1); preconditions drop jq/cache-dir (retain python3 for the test/helper); correct the "canonical-plus-mirror dual-source" misstatement.
- **Actual**: plugin.json multi-agent = 0; both manifests reworded to "Single high-effort GitHub pull request reviewer." `review_dispatch` distinctness note present (SKILL.md:44-48). Preconditions keep only gh + python3 (for `derive_verdict.py`); jq/cache-dir dropped. SKILL.md "## Maintenance" correctly states "hand-maintained and edited in place. There is no canonical-plus-mirror dual-source... do not run build-plugin."
- **Verdict**: PASS

### Requirement 6: In-context grounding with falsifiable per-finding citations
- **Expected**: finding schema in output-format.md defines a `grounding` status (`grounded`/`evidence-weak`) and a `file:line` citation; ungroundable findings surfaced as evidence-weak, never silently dropped.
- **Actual**: output-format.md "## Finding schema" defines `grounding` ∈ {grounded, evidence-weak} and `file:line`. `grep -c 'evidence-weak'` = 10. protocol.md "## In-context grounding criterion" and rubric.md "## Grounding gate" both state an ungroundable finding is "surfaced... never silently dropped." The contract test exercises that an evidence-weak finding routes through the verdict logic rather than being dropped.
- **Verdict**: PASS

### Requirement 7: Deterministic fail-loud verdict state machine
- **Expected**: Verdict derivation implemented exactly as a structurally-enforced gate; signals 5/6 derived internally; only the four RUNTIME_SIGNALS accepted from the caller; fail-loud → REVIEW_INCONCLUSIVE not silent APPROVE; verdict set is APPROVE | REQUEST_CHANGES | REVIEW_INCONCLUSIVE (no COMMENT).
- **Actual**: `derive_verdict.py` implements the top-to-bottom derivation: grounded-blocking → REQUEST_CHANGES; else runtime-signals OR `surfaced_none_grounded` OR `evidence_weak_blocking` → REVIEW_INCONCLUSIVE; else APPROVE. `RUNTIME_SIGNALS` is a 4-tuple module constant (the only signals the caller passes); signals 5/6 derived internally from `findings`. `COMMENT` appears only in negations ("There is no `COMMENT` verdict"). Fail-loud confirmed empirically: malformed/missing-key stdin raises a traceback (non-zero exit, no stdout verdict) rather than printing APPROVE. REVIEW_INCONCLUSIVE documented in protocol.md (×5) and output-format.md (×3).
- **Verdict**: PASS

### Requirement 8: Verdict-vs-label fix via a single severity field
- **Expected**: One verdict-driving severity (`blocking` vs not) + grounding gate; signal axis dropped; `suggestion (blocking)` removed (one blocking label form); per-label caps and alphabetical tie-break deleted; one canonical label↔decoration↔severity↔verdict table in output-format.md.
- **Actual**: rubric.md collapsed to one severity axis + grounding gate ("There is no separate signal axis and no separate solidness axis"). `grep -c 'suggestion (blocking)'` = 0 across references; per-label cap grep = 0; `alphabetical` grep = 0. output-format.md "## Canonical label / decoration / severity / verdict-effect table" is the single table, decoration rendered from `severity`. Exactly one blocking label form: `issue (blocking):`.
- **Verdict**: PASS

### Requirement 9: Terminal-first output + observability footer
- **Expected**: Plain-text default (no `<details>`/HTML/markdown table); GitHub markdown only when posting; findings sorted blocking-first then file:line; footer reports model-that-ran, findings_surfaced split grounded/evidence-weak, findings_dropped with reasons; no-autopost default survives and posting is flag-gated.
- **Actual**: output-format.md "## Terminal-first output" states plain text default contains "no `<summary>` blocks, no HTML, and no markdown tables." `<details>`/`<summary>` appear only under "## Posting mode (GitHub markdown)" (lines 105-113). Footer documents `model`, `findings_surfaced` (grounded + evidence-weak split), `findings_dropped` with per-reason breakdown. Sort order = blocking-first then file:line. No-autopost is the default in SKILL.md "## Constraints" and protocol.md "## Present the result"; posting is an explicit presentation gate. The canonical-table markdown at lines 35-42 is reference documentation of the schema, not rendered output, so it does not violate the plain-text-default criterion.
- **Verdict**: PASS

### Requirement 10: In-scope contract test pinning the verdict state machine and grounding contract
- **Expected**: A runnable test asserting at minimum the five verdict cases + signal-5/6 derivation + grounding contract + stdin path; `just test` (or targeted pytest) exits 0.
- **Actual**: `tests/test_pr_review_verdict.py` loads `derive_verdict.py` via `importlib.util.spec_from_file_location` and imports `RUNTIME_SIGNALS` (not re-typed). Seven tests cover: (1) grounded blocking → REQUEST_CHANGES; (2) all-evidence-weak → REVIEW_INCONCLUSIVE; (3) evidence-weak blocking → REVIEW_INCONCLUSIVE; (4) zero findings + a RUNTIME_SIGNALS member → REVIEW_INCONCLUSIVE; (5) all-grounded non-blocking → APPROVE; (6) signals 5/6 derived internally with empty runtime_signals (and asserts they are not RUNTIME_SIGNALS members, len == 4); (7) the `__main__` stdin path via subprocess. `uv run pytest tests/test_pr_review_verdict.py` → 7 passed.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Consistent. `derive_verdict`, `surfaced_none_grounded`, `evidence_weak_blocking`, and the `RUNTIME_SIGNALS` module constant match the Verdict-Helper Contract names in plan.md verbatim, preventing helper/caller/test drift. Reference-file headings follow the existing skill prose style.
- **Error handling**: Appropriate and genuinely fail-loud. `main()` uses `json.load(sys.stdin)` and `payload["findings"]` / `payload["runtime_signals"]` directly: malformed JSON or a missing key raises and exits non-zero with no stdout, so a degraded invocation cannot be mistaken for APPROVE — the spec's central fail-loud guarantee. Verified empirically with `not json` and a missing-key payload. The pure `derive_verdict` function has no I/O and is total over well-formed inputs.
- **Test coverage**: The contract test covers all five spec verdict cases plus the two derived-signal cases and the stdin path (7 tests, all pass). It imports `RUNTIME_SIGNALS` rather than hard-coding signal strings, which is the anti-drift mechanism the plan calls for. The LLM-runtime behaviors (reviewer judgment, in-context grounding, footer population) are gated by structural greps as an accepted, spec-acknowledged limit; the safety-critical verdict gate is behaviorally tested.
- **Pattern consistency**: Follows ADR-0009 path discipline — `${CLAUDE_SKILL_DIR}` resolves only in the SKILL.md body (8 occurrences, all in SKILL.md; zero leaks into reference files), and the body propagates the absolute `derive_verdict.py` path and inlines output-format content into the reviewer prompt. `bin/cortex-check-skill-path --audit` exits 0. The plugin stays hand-maintained (`plugin.json` `.name` = "cortex-pr-review", non-empty) so the drift classification guard holds; no mirror was regenerated, matching the spec's Technical Constraints. SKILL.md (98 lines) and protocol.md (148 lines) are well within their size caps; `tests/test_skill_size_budget.py` passes. The helper is correctly plugin-local (not a `bin/cortex-*` script), so SKILL.md-to-bin parity wiring does not apply.

Note on `just test`: the full suite reports 18 failures, all confirmed unrelated to this lifecycle. They are (a) `tests/test_init_claude_md_authorization.py` and `tests/test_init_verify_worktree_auth.py` — untracked work-in-progress files from a different feature (`cortex-init-scope-reduction`) referencing `cortex_command.init.scaffold` symbols that do not exist yet; (b) two `PermissionError` on `~/.claude/.settings.local.json.lock` (sandbox write restriction); (c) one `test_mcp_subprocess_contract.py` DNS failure reaching pypi.org (sandbox network restriction). None touch `plugins/cortex-pr-review/` or `tests/test_pr_review_verdict.py`. The lifecycle's own tests and all structural/skill-path/size/manifest checks pass.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
