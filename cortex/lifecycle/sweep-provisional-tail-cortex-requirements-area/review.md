# Review: sweep-provisional-tail-cortex-requirements-area

## Stage 1: Spec Compliance

### Requirement 1: Candidate set is exactly the 32 filtered rows
- **Expected**: Filtering `master_candidates.json` on `status=="unverified"` AND `file` startswith `cortex/requirements/` AND no `overlaps_ticket` AND no `reproposal_of` yields exactly 32 rows split backlog 11 / pipeline 6 / observability 6 / remote-access 5 / multi-agent 4.
- **Actual**: Re-ran the exact filter against the pre-implementation ledger (`git show 9e14791e:cortex/research/skill-value-scorecard/master_candidates.json`): 32 rows, split `{'multi-agent.md': 4, 'pipeline.md': 6, 'backlog.md': 11, 'remote-access.md': 5, 'observability.md': 6}` — matches exactly.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 2: Per-candidate verification by an independent checkable signal
- **Expected**: Every applied trim cites signal (a) structural-substitution, (b) informative-only, or (c) preserved-elsewhere in `verify-outcomes.md`, not a bare self-authored reason.
- **Actual**: All 31 `survives` rows carry a typed signal with a location or quoted span. Spot-checked ~15 pins directly against the repo: `justfile:575` (`BUILD_OUTPUT_PLUGINS` includes cortex-backlog — confirmed), `tests/test_dual_source_reference_parity.py` (exists), `cortex_command/lifecycle_config.py:97` (`resolve_backlog_backend` — confirmed), `tests/test_overnight_backlog_backend_guard.py` (exists), ADR-0016/ADR-0019 (exist), ADR-0015 + `docs/internals/pipeline.md:178` ("the contract" language literally present), `STALL_TIMEOUT_SECONDS`/`ABSOLUTE_CEILING_SECONDS`/`WEDGED_STALENESS_SECONDS` constants (1800/14400/2700, all confirmed in code and still stated in the trimmed pipeline.md prose), `tests/test_runner_threading.py` `stall_reason` assertions (confirmed), ADR-0005 (exists), issue `anthropics/claude-code#39886` (confirmed cited in multi-agent.md). All checked pins substantiate their claim. One self-correction inside the verification itself is worth noting positively: observability s8's claim that the legacy-shim note was "owned by `pipeline.md:28`" was checked and found false by the verifier (full git-history grep for "shim" in `docs/internals/pipeline.md` returns nothing), and the row was honestly reclassified from signal (a) to (b) rather than left as an unverified assertion — this is exactly the anti-self-attestation behavior Req 2 is designed to produce.
- **Verdict**: PASS
- **Notes**: The backlog Edge Cases trim (s13) leans on signal (b) for three bullets whose informative-only classification is defensible but non-trivial — see the Stage-1 over-trim discussion under Requirement 6 below.

### Requirement 3: Anchor each candidate by heading + pinned token, never by stored line number
- **Expected**: Outcomes file records `##`/`###` heading text + pinned token per candidate; every applied span's heading exists verbatim post-trim.
- **Actual**: All 32 rows in `verify-outcomes.md` carry non-empty `heading` and `anchor_token` columns. Spot-checked several headings against the current files (e.g. "### Consumer backend routing (skill layer)", "### Post-Merge Review", "### Overnight Kill/Stall Telemetry", "## Non-Functional Requirements" for remote-access s6) — all present verbatim post-trim.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 4: Correct the two drifted claims before trimming
- **Expected**: (a) backlog s14 trims only the 2 Recommendation-bearing Open-Questions bullets, leaving the 2 genuinely-open bullets untouched. (b) backlog s8 preserves distinct NFR nuance rather than erasing it after confirming the three cited instances are truly equivalent.
- **Actual**: Current `cortex/requirements/backlog.md` Open Questions section has 4 bullets: Jira best-effort (untouched, still open), "Ticket-ref persistence: resolved — ..." (trimmed to a one-line decision record), "Interactive init prompt: resolved — ..." (trimmed to a one-line decision record), concrete-adapter (untouched, still open) — exactly 2-of-4 trimmed, matching the corrected scope. NFR Safety bullet (L89, "External-tracker writes occur only on interactive... never on the unattended overnight path...") is completely untouched by the s8 diff — the NFR nuance was preserved by not touching it at all, rather than folding it into the collapsed Edge-Case/FR pointer.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 5: Apply the four coordinated same-text clusters as single edits
- **Expected**: (a) observability s9↔s13 collapse the triplicated "arrays replace, not merge" gotcha to one canonical statement. (b) remote-access s2↔s6↔file-compress consolidate the tmux tool-agnostic framing and macOS/Ghostty constraint to one canonical home each. (c) backlog s3/s5/s6/s7 — s6's enum stays at FR, s7's decisions stay at FR/OQ, only s3/s5 fold into AC. (d) pipeline s13 folds the three restated constraints into Architectural Constraints pointers.
- **Actual**: Verified directly against post-trim files:
  - observability.md: the gotcha is now stated once (the Note at "Sandbox Socket Access," "arrays replace (not merge with)...write a self-contained array") with the AC bullet and Edge-Case bullet both pointing at it via "(see Note below on array-replace semantics)" / "(see the Sandbox Socket Access Note...)". Matches (a).
  - remote-access.md: Overview retains the tool-agnostic framing prose; Dependencies and Open Questions now cross-reference it. NFR "Platform" retains the macOS/Ghostty statement; Architectural Constraints and Dependencies now cross-reference it. Matches (b).
  - backlog.md: AC now carries the s3/s5 dedupe (skills/backlog-author/engine-in-wheel, config-authoritative resolution). The three-behavior enum ("local-engine call, LLM best-effort against an external tracker, or skip") is still present verbatim in the "Consumer backend routing" FR's Outputs line (not folded into AC). The round-trip decision ("re-resolve the target item by searching the tracker...rather than relying on a persisted ID map") is still present verbatim in the "External backend via LLM best-effort" FR's acceptance criteria. Matches (c) exactly, including the sharp case the spec called out.
  - pipeline.md: Concurrency-safety NFR now points to Architectural Constraints → "State file locking"; both Repair-attempt-cap AC bullets now point to Architectural Constraints → "Repair attempt cap"; the Branch-persistence bullet in Session Orchestration now points to the same section. The canonical `## Architectural Constraints` bullets themselves are untouched. Matches (d).
  - The s7↔s14 coupling (backlog): confirmed — s14 trimmed the OQ persist-ticket-ref bullet only after the round-trip decision remains independently stated at the FR home (verified above); neither edit deleted the last surviving copy.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 6: Two mechanical content-preservation gates — G1 (H2-set) and G2 (normative-line survival)
- **Expected**: G1 — `^## `/`^### ` heading set byte-identical pre/post for all 5 files. G2 — every removed normative line either grep-provable at a surviving location or classified informative-only with the span quoted.
- **Actual (G1)**: Ran the actual diff myself (not trusting the commit-message claims): `diff` of `git show 9e14791e:cortex/requirements/<file>.md | grep -E '^#{2,3} '` against the current file's `grep -E '^#{2,3} '`, for all 5 files. All 5 diffs are empty — G1 holds exactly as claimed, independently verified.
- **Actual (G2)**: Spot-checked a representative sample of removed normative lines against their cited surviving location or informative-only classification (see Requirement 2 above) — all confirmed. One genuine editorial judgment call surfaced during review: backlog.md's Edge Cases section thinned from 6 bullets to 3 (dropping "Round-trip ambiguity...the LLM disambiguates or asks the user rather than guessing," "Empty instructions...falls back to general knowledge," and "Backend names a tool the LLM can't drive...best-effort fails gracefully and surfaces the error"), classified signal (b) informative-only on the grounds that these are default LLM behaviors, not project-specific decisions. The implementer flagged this itself as a REVIEW-FLAG rather than silently landing it. I assessed this judgment: the three dropped bullets describe fallback behavior for the explicitly-labeled "best-effort... unverified... not promised as parity" external-tracker pathway (NFR "Honest support claims"), a domain the file itself frames as LLM-judgment-driven rather than code-enforced, and the removed content is generic agentic-system guidance ("ask rather than guess", "fail loud rather than silently drop work") rather than cortex-specific institutional knowledge — consistent with the project's own "prescribe What and Why, not How" principle (CLAUDE.md, cited in this very file's Overview). This is a closer call than the file's other trims but a defensible one, and it was surfaced transparently rather than hidden. By contrast, the remote-access.md acceptance-criteria over-trim that the orchestrator caught and restored (session detach-without-interrupting, reattach-from-different-device, mosh-survives-roaming) involved testable Acceptance Criteria — the definition-of-done form of a requirement — which is a stronger content class than Edge Cases prose; restoring those was the right call, and I found no further over-trim of that class in any of the 5 files.
- **Verdict**: PASS
- **Notes**: The backlog Edge Cases thinning is judged an acceptable (if debatable) trim, not a gate failure — flagging it here for visibility since the task itself flagged it and did not act further.

### Requirement 7: Refresh live code + docs line-anchor citers — scoped, matching all three citation forms
- **Expected**: Pre/post enumeration of all three citation forms across `cortex_command/**`+`docs/**` only (sibling lifecycle specs and archive excluded); every hit resolved to a post-trim line or converted to a heading reference; post-batch re-run shows zero stale citers.
- **Actual**: Independently re-ran the broad baseline (`grep -rEn '(backlog|pipeline|observability|remote-access|multi-agent)\.md' cortex_command docs`) against the current tree myself and reconciled every hit: `lifecycle_event.py:15` (L143/146/151, all three lines match current content), `cli.py:90` (now a durable heading reference to "In-Session Status CLI," no longer a numeric anchor), `orchestrator_context.py:8` (`pipeline.md:127,134` — L127 is the `### Post-Session Sync` heading, L134 matches the sync-allowlist text), `fill_prompt.py:7` (`multi-agent.md:51` — matches the substitution-contract bullet, off-by-one fixed from :50), `overnight-operations.md:212` (`pipeline.md:28` — matches), `overnight-operations.md:655` (`multi-agent.md:77` — matches the worktree-placement bullet). Every other baseline hit is a by-name/prose mention of a sibling doc (not a line-anchored citation of the 5 target files) and correctly excluded. Zero unaccounted or stale citers found.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 8: Capture per-candidate outcomes in a structured, (file,id)-keyed file
- **Expected**: `verify-outcomes.md` with 32 rows (31 survives + 1 deferred), each keyed `(file,id)` and carrying a Req 2 signal.
- **Actual**: Confirmed 32 rows total, correctly split by file, each survivor typed a/b/c, observability s14 recorded `deferred`.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 9: Pull observability.md s14 from the editorial batch
- **Expected**: s14 not applied; recorded `deferred: out-of-editorial-scope`; a follow-up backlog item filed; Install-mutation section untouched.
- **Actual**: `verify-outcomes.md` records s14 as `deferred`. The `## Install-mutation invocations` H2 (and its full body) is byte-identical pre/post (confirmed by the G1 heading diff and by direct inspection of the section content). Backlog item #362 filed, correctly scoped to evaluate the relocation as a real lifecycle change, keyed on `(file=cortex/requirements/observability.md, id=s14)`.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 10: Install a discharge mechanism for the reconciliation debt
- **Expected**: A tracked follow-up naming `verify-outcomes.md` as the `(file,id)`-keyed delta, keyed on the composite `(file,id)`; if OQ3 resolves to direct-write, this batch discharges its own rows in-commit.
- **Actual**: `events.log` records `{"event": "plan_approved", ..., "oq3_decision": "direct-write"}`. Diffed `master_candidates.json` pre/post: exactly 31 rows changed (0 added, 0 removed, total count unchanged at 265), and the 31 changed rows are precisely the 31 `survives` `(file,id)` pairs from `verify-outcomes.md` — no churn elsewhere. Each changed row's `status` flipped to `verified_survives`, gained a `verdict_summaries` entry citing batch `#358`, commit hash, and `verify-outcomes.md` as source, and `applied_in_commit` was populated with the correct per-file commit hash (cross-checked against the actual `git log` commit for each file — all match). `dup_groups.json` is untouched (confirmed via `git diff --stat`). Observability s14 was correctly left `unverified` (not touched by the direct-write). Backlog item #363 filed, correctly scoped to the *remaining* siblings (#359/#360/#361, #353) and explicitly calling out the `(file,id)` keying requirement with the `id`-non-unique rationale.
- **Verdict**: PASS
- **Notes**: This is a clean, scoped, independently-verified ledger write — one of the strongest parts of the implementation.

## Stage 2: Code Quality

- **Editorial quality**: The trims are genuine dedup, not gutting. In every file, content removed from one location was either (a) demonstrably enforced/derivable elsewhere in code+tests, (b) template-filler boilerplate (Inputs/Outputs restating the Description), or (c) moved to a single canonical prose location with the other copies converted to cross-references. Cross-references consistently point at real, currently-accurate canonical homes (verified by reading the target sections, not just trusting the pointer text) — e.g. remote-access.md's "Local notifications" line now points to `observability.md` (Notifications), which was confirmed to carry the equivalent listing. The one clean editorial catch of note: observability s8's stale `pipeline.md:28` self-citation (which never actually documented shim retirement, confirmed via full git history) was corrected to informative-only rather than silently trusted as structural-substitution.
- **Naming conventions**: N/A (prose-only requirements docs; no code identifiers introduced).
- **Error handling**: N/A for the 5 requirements-doc trims. The two code citer edits are non-functional docstring/comment changes with zero runtime behavior change.
- **Test coverage**: N/A — this is prose-only content with no test backstop (as the spec itself notes); G1/G2 are the only mechanical gates, and both were independently re-verified above (G1 fully mechanically; G2 by spot-check).
- **Pattern consistency**: Matches the #351/#353 editorial precedent (one-commit-per-file grain, user-facing content trimmed only at spec/PR review, not silently). The two code citer edits (`cli.py:90`→heading reference, `fill_prompt.py:7` `:50`→`:51`) are minimal, correct, single-line changes scoped exactly to the stale anchor — no incidental changes. The `master_candidates.json` direct-write is scoped to exactly the 31 target `(file,id)` rows (independently diff-verified above), valid JSON (`python3 -m json.load` succeeds), and introduces no churn on the other 234 rows.

## Requirements Drift
**State**: none
**Findings**:
- None. This implementation is a purely editorial content-trim of already-established `cortex/requirements/*.md` area docs (backlog, pipeline, observability, remote-access, multi-agent), governed entirely by this feature's own lifecycle spec/plan and by the existing #351/#353 editorial precedent already established in the codebase's practice. `cortex/requirements/project.md`'s `## Conditional Loading` section already lists all 5 files as selectively-loaded area docs, consistent with the spec's Technical Constraints. No new policy, architecture, or behavior surface was introduced that project.md would need to reflect — the OQ3 direct-write mechanism and the G1/G2 gate discipline are lifecycle-batch-scoped verification techniques, not project-level architectural decisions.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
