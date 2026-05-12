# Specification: Reduce sub-agent dispatch artifact duplication

## Problem Statement

Three sub-agent dispatch sites in cortex-command inline the full text of `plan.md` / `spec.md` / `research.md` into every dispatched reviewer's prompt and into the synthesizer's prompt, producing N+1 or N+2 copies of the artifact per dispatch run. Per-dispatch token cost ranges ~500–15,000 tokens depending on artifact size and reviewer count. Beyond the token waste, the inline-snapshot approach lacks any structured signal for cross-reviewer drift on the critical-tier auto-trigger path, where the orchestrator writes `plan.md` immediately before fanning out reviewers and the synthesizer re-validates evidence quotes against the artifact. Switching to absolute-path Read + SHA-pin verification (applied at both reviewer-Read and synthesizer-Read windows) cuts per-dispatch token cost by N+1→0 reviewer/synthesizer copies (orchestrator retains its copy) and converts silent drift across the full reviewer-Read AND synthesizer-Read windows into an observable, exclude-or-abort signal.

## Requirements

1. **Critical-review reviewer dispatch uses path+SHA, not inline content**: `skills/critical-review/SKILL.md`'s reviewer prompt at line 96 replaces `{artifact content}` with two new placeholders `{artifact_path}` and `{artifact_sha256}`, plus a directive instructing the reviewer to Read the path and emit `READ_OK: <path> <sha>` (matching the orchestrator's SHA) as the first line of output, or `READ_FAILED: <path> <reason>` and stop on Read failure.
   - Acceptance: `grep -c '{artifact content}' skills/critical-review/SKILL.md` = 0 AND `grep -c '{artifact_path}' skills/critical-review/SKILL.md` ≥ 3 AND `grep -c '{artifact_sha256}' skills/critical-review/SKILL.md` ≥ 3.

2. **Critical-review fallback single-agent path uses path+SHA**: same substitution at `SKILL.md:166` (the single-agent fallback that today also inlines `{artifact content}`).
   - Acceptance: subsumed by Requirement 1's grep assertions.

3. **Critical-review synthesizer dispatch uses path+SHA and emits its own sentinel**: same substitution at `SKILL.md:210`. The synthesizer's evidence-quote re-validation at `SKILL.md:218` is updated to Read the artifact once at start of synthesis (before the per-finding loop), compute SHA-256 of the Read result, and emit a `SYNTH_READ_OK: <path> <sha>` line in its output before the per-finding analysis. Evidence-quote re-validation compares against the Read result.
   - Acceptance: subsumed by Requirement 1 AND `grep -n "Read.*{artifact_path}" skills/critical-review/SKILL.md` ≥ 1 in the synthesizer prompt section (lines 205–299) AND `grep -c 'SYNTH_READ_OK' skills/critical-review/SKILL.md` ≥ 1.

4. **Step 2c.5 verification gate — ordering, scope, and exclusion routing**:
   - **(4a) Ordering**: Step 2c.5 verifies each reviewer's first-line `READ_OK: <path> <sha>` BEFORE attempting envelope extraction. If the sentinel is absent or its SHA does not match the orchestrator's pre-dispatch SHA, the reviewer is marked excluded and **its envelope is not parsed at all**.
   - **(4b) Exclusion scope**: An excluded reviewer's findings are dropped from ALL tallies (A-class, B-class, C-class) AND from the untagged-prose pathway. The only surface that mentions an excluded reviewer is a structured warning of the form `Reviewer N excluded: <reason>` where `<reason>` is one of `SHA drift detected (expected <sha>, got <sha>)`, `sentinel absent`, or `Read failed: <error>`. Excluded reviewers MUST NOT contribute findings to the synthesizer's input.
   - **(4c) Synthesizer-side gate**: The orchestrator captures the post-synthesizer `SYNTH_READ_OK: <path> <sha>` line. If the synthesizer's SHA does not match the orchestrator's pre-dispatch SHA, the orchestrator emits a top-level diagnostic `Critical-review pass invalidated: synthesizer SHA drift detected (expected <sha>, got <sha>); re-run after resolving concurrent write source.` and does NOT surface the synthesis output. If `SYNTH_READ_OK` is absent, treat as drift and same handling applies.
   - **(4d) Warning channel**: All exclusion warnings (reviewer-side and synthesizer-side) prefix with `⚠` matching the existing malformed-envelope warning format at `SKILL.md:199`. Reviewer-side warnings appear in the synthesis output's preamble; synthesizer-side drift replaces the synthesis output entirely with the top-level diagnostic.
   - Acceptance: `grep -c 'SHA drift detected' skills/critical-review/SKILL.md` ≥ 2 AND `grep -c 'sentinel absent\|Read failed' skills/critical-review/SKILL.md` ≥ 2 AND `grep -c 'Critical-review pass invalidated' skills/critical-review/SKILL.md` ≥ 1.

5. **Partial-coverage banner extension**: The existing "N of M reviewer angles completed" prefix at `SKILL.md:303` is extended to surface excluded-but-completed reviewers separately: `N of M reviewer angles completed (K excluded for drift/Read failure)`. When K = 0 the parenthetical is omitted (preserves current behavior).
   - Acceptance: `grep -n 'excluded for drift/Read failure' skills/critical-review/SKILL.md` ≥ 1.

6. **Lifecycle critical-tier plan dispatch uses paths, not full contents**: `skills/lifecycle/references/plan.md` lines 43 and 46 replace `{full contents of lifecycle/{feature}/spec.md}` and `{full contents of lifecycle/{feature}/research.md}` with `{spec_path}` and `{research_path}` placeholders + a directive instructing each plan agent to Read both files and emit `READ_OK: <path> <sha>` headers for each.
   - Acceptance: `grep -c 'full contents of lifecycle' skills/lifecycle/references/plan.md` = 0 AND `grep -c '{spec_path}\|{research_path}' skills/lifecycle/references/plan.md` ≥ 2.

7. **Lifecycle review.md reviewer uses path, not contents**: `skills/lifecycle/references/review.md:30` replaces `{contents of lifecycle/{feature}/spec.md, or a summary with a path to read it}` with `{spec_path}` + an unambiguous Read directive (eliminating the existing hedge).
   - Acceptance: `grep -c 'contents of lifecycle/{feature}/spec.md, or a summary' skills/lifecycle/references/review.md` = 0 AND `grep -c '{spec_path}' skills/lifecycle/references/review.md` ≥ 1.

8. **Orchestrator-side absolute-path resolution**: at each dispatch site, the orchestrator (main session, running outside the worktree) resolves the artifact path to an absolute path before injection. The orchestrator MUST NOT instruct dispatched reviewers to invoke `git rev-parse` themselves.
   - Acceptance: `grep -n 'git rev-parse' skills/critical-review/SKILL.md skills/lifecycle/references/plan.md skills/lifecycle/references/review.md` shows resolution invocations only in orchestrator-facing instruction blocks, NOT inside reviewer/agent prompt templates.

9. **Path validation gate (security) — realpath-based**:
   - **(9a) Resolution mechanism**: The orchestrator MUST resolve the candidate artifact path via `os.path.realpath()` (NOT plain `os.path.abspath`) before validation. The resolved realpath MUST be byte-equal to `os.path.abspath()` of the input — i.e., the input path MUST NOT traverse any symlink. Paths where `realpath(p) != abspath(p)` are rejected with a clear error before any dispatch.
   - **(9b) Prefix check**: After realpath confirms no symlinks, the realpath MUST be a strict path-component prefix of `{home_repo_root}/lifecycle/` (using `Path.is_relative_to()` or equivalent). For auto-trigger flows, additionally the realpath MUST be under `{home_repo_root}/lifecycle/{session_bound_feature}/`. For `<path>`-arg invocations, the looser `lifecycle/` prefix applies.
   - **(9c) Symlink prohibition**: `lifecycle/` MUST NOT contain symlinks. The validation gate rejects any candidate path encountering a symlink during realpath resolution.
   - **(9d) Acceptance test exercises a real symlink rejection**: a new test creates a temp lifecycle-shaped tree containing a symlink to `/etc/hostname`, invokes the validation function, and asserts rejection with the appropriate error.
   - Acceptance: `grep -c 'os.path.realpath\|Path.resolve\|realpath' skills/critical-review/SKILL.md` ≥ 1 AND a new test file (e.g., `tests/test_critical_review_path_validation.py`) exists with at least one symlink-rejection assertion and is non-`@pytest.mark.slow`.

10. **Fast-path template-correctness unit test**: a new non-`@pytest.mark.slow` unit test asserts pure string properties of the three dispatch templates: (a) `{artifact content}` and `{full contents of ...}` placeholders absent, (b) `{artifact_path}` / `{spec_path}` / `{research_path}` and `{artifact_sha256}` placeholders present at expected sites, (c) reviewer prompts contain the `READ_OK: <path> <sha>` sentinel directive verbatim, (d) the synthesizer prompt contains the `SYNTH_READ_OK: <path> <sha>` directive verbatim. No live model calls.
   - Acceptance: `just test tests/test_dispatch_template_placeholders.py` exits 0; `grep -c '@pytest.mark.slow' tests/test_dispatch_template_placeholders.py` = 0.

11. **Existing slow test updated for new placeholders**: `tests/test_critical_review_classifier.py` substitutes `{artifact_path}` and `{artifact_sha256}` (not `{artifact content}`) at all five `re.sub` call sites, and asserts the new placeholders are absent post-substitution.
   - Acceptance: `grep -c '{artifact content}' tests/test_critical_review_classifier.py` = 0 AND `grep -c '{artifact_path}\|{artifact_sha256}' tests/test_critical_review_classifier.py` ≥ 2.

12. **Sentinel-absence telemetry (events.log)**: When Step 2c.5 marks a reviewer excluded for sentinel absence, SHA mismatch, or Read failure, the orchestrator appends a `sentinel_absence` event to `lifecycle/{feature}/events.log` (or the session-bound events.log) with fields `{ts, event: "sentinel_absence", feature, reviewer_angle, reason: "absent|sha_mismatch|read_failed", model_tier: "haiku|sonnet|opus", expected_sha, observed_sha_or_null}`. The synthesizer-side SHA-drift case appends an analogous `synthesizer_drift` event. This telemetry enables future per-model-tier compliance audits and unblocks the OQ3 evidence-gathering path if soft-form directives prove insufficient.
   - Acceptance: `grep -c '"event": "sentinel_absence"\|"event": "synthesizer_drift"' skills/critical-review/SKILL.md` ≥ 1.

13. **Dual-source mirrors regenerated**: `plugins/cortex-core/skills/critical-review/SKILL.md`, `plugins/cortex-core/skills/lifecycle/references/plan.md`, and `plugins/cortex-core/skills/lifecycle/references/review.md` byte-match their canonical sources after the change.
   - Acceptance: `just test tests/test_dual_source_reference_parity.py` exits 0.

## Non-Requirements

- **No size-gated hybrid**: small-artifact tool-call overhead is disclosed in implementation comments, not engineered around. Path+SHA applies uniformly at all artifact sizes (matches Reviewer-2's DR-1 commitment).
- **No filesystem locks, no advisory `flock`, no orchestrator-managed write-locks**: snapshot consistency is enforced by SHA verification at synthesis-time, not by blocking concurrent writers (per `requirements/pipeline.md:134` no-read-lock convention).
- **No `$TMPDIR` snapshot file (E3 from research)**: rejected in favor of SHA-pin; avoids sandbox-asymmetry footgun and temp-file lifecycle management.
- **No pre-sliced sections (C from research)**: rejected; defeats parallel fan-out's design intent.
- **No content-addressed storage or new helper subsystem**: orchestrator absolutifies inline at each site, matching existing `SKILL.md:318` pattern.
- **No changes to parallel multi-reviewer fan-out value question**: out of scope per source ticket.
- **No changes to angle-derivation logic in critical-review Step 2b**: out of scope.
- **No changes to the synthesizer's A→B downgrade rubric**: out of scope. The rubric continues to operate on artifact content; the change is only how the synthesizer obtains that content (Read once at synthesis start, not from inline prompt text).
- **No retroactive cleanup of archived lifecycle directories or events.log payloads**: going-forward only.
- **No new MUST/CRITICAL/REQUIRED escalations in dispatch templates**: Read-failure, SHA-mismatch, and synthesizer-drift directives are authored in positive-routing form per CLAUDE.md MUST-escalation policy. The `sentinel_absence` and `synthesizer_drift` events from Requirement 12 explicitly enable the OQ3 evidence-gathering path so a future escalation can be supported by data if the soft form proves insufficient.
- **No live-model emission test in this ticket**: deferred to a follow-up backlog item once Requirement 12's `sentinel_absence`/`synthesizer_drift` telemetry has accumulated enough data to identify which reviewer-model tiers (Haiku / Sonnet / Opus) have material compliance regression. A per-tier live-model dispatch test is the natural follow-up but adds CI cost and is not the minimum-viable safeguard given the telemetry + exclude-on-absence semantics already in this spec.

## Edge Cases

- **Reviewer Read returns empty content**: reviewer emits `READ_FAILED: <path> empty` as first output line; Step 2c.5 marks excluded (sentinel-failed); excluded from all tallies and prose pathways. `sentinel_absence` event logged.
- **Reviewer Read fails with sandbox-deny error**: reviewer emits `READ_FAILED: <path> sandbox-deny` and stops; same handling.
- **Reviewer omits the `READ_OK`/`READ_FAILED` sentinel line entirely** (fill-the-gap hallucination): absence treated as sentinel-failed; reviewer excluded from all tallies and prose pathways even if findings emitted. `sentinel_absence` event logged with `reason: "absent"`. The SHA verification + sentinel-absence telemetry is the load-bearing observability surface, not the directive itself.
- **Reviewer's SHA mismatches orchestrator's** (concurrent write between dispatch and Read): reviewer excluded with `Reviewer N excluded: SHA drift detected (expected <sha>, got <sha>)`; remaining reviewers' findings stand; `sentinel_absence` event with `reason: "sha_mismatch"` logged. Partial-coverage banner reads `N of M reviewer angles completed (1 excluded for drift/Read failure)`.
- **Synthesizer's SHA mismatches orchestrator's** (concurrent write between dispatch and synthesizer Read): orchestrator emits top-level diagnostic `Critical-review pass invalidated: synthesizer SHA drift detected (expected <sha>, got <sha>); re-run after resolving concurrent write source.` The synthesis output is NOT surfaced to the user. `synthesizer_drift` event logged. This case is structurally distinct from "all reviewers excluded" — reviewers may have succeeded individually but the synthesizer's view of the artifact diverged from theirs, so the synthesis itself is invalidated.
- **Synthesizer omits `SYNTH_READ_OK` entirely**: treated as drift; same handling as SHA mismatch.
- **All reviewers excluded for SHA drift or Read failure**: top-level diagnostic `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.` Same surfacing channel as synthesizer-drift case.
- **`/cortex-core:critical-review <path>` invocation with a path outside `lifecycle/`**: rejected by the path validation gate (Requirement 9) before any dispatch occurs. Error message names the offending path and the allowed prefix.
- **`/cortex-core:critical-review <path>` invocation with a symlink inside `lifecycle/`**: rejected by Requirement 9c (realpath != abspath). Error message names the symlink path and its realpath target.
- **Cross-repo dispatched reviewer** (worktree CWD is `state.integration_worktrees[repo_key]`): the orchestrator absolutifies the path using the home cortex repo's root, not the worktree's. Reviewer Reads the absolute path; no resolution from worktree.
- **Operator edits the artifact in their IDE during fan-out** (FM-1, ASM-1): orchestrator's pre-dispatch SHA captures the dispatch-time snapshot. If the edit lands before any reviewer Reads, that reviewer's SHA differs and they are excluded. If the edit lands AFTER all reviewers but BEFORE the synthesizer Reads, the synthesizer-side SHA gate (Requirement 4c) fires and the pass is invalidated via top-level diagnostic.
- **Critical-tier auto-trigger writes `plan.md` then immediately fans out** (FM-1): same SHA gate handles it across both reviewer and synthesizer windows.
- **Reviewer attempts to re-resolve path via `git rev-parse --show-toplevel`** (worktree CWD footgun): would resolve to the worktree root and Read the wrong file (or fail). SHA gate catches drift; the worktree-shadowed copy will have a different SHA or not exist. Reviewer prompt template explicitly instructs "Read the absolute path provided; do NOT re-resolve via `git rev-parse`."
- **Multi-stage review.md reviewer with spec change between stages** (ASM-3): each stage's reviewer Reads the spec at stage start; if the spec changed between Stage 1 and Stage 2, the Stage 2 reviewer's SHA differs from Stage 1's. The reviewer logs both SHAs in its output; the review.md consumer can detect the inter-stage drift.

## Changes to Existing Behavior

- **MODIFIED**: critical-review reviewer prompt (SKILL.md:91–152) — receives `{artifact_path}` + `{artifact_sha256}` and Read directive instead of inline content.
- **MODIFIED**: critical-review fallback single-agent prompt (SKILL.md:160–189) — same.
- **MODIFIED**: critical-review synthesizer prompt (SKILL.md:205–299) — same; evidence-quote re-validation operates on synthesizer's own Read result; synthesizer emits `SYNTH_READ_OK: <path> <sha>` for orchestrator-side verification.
- **MODIFIED**: critical-review Step 2c.5 envelope handler (SKILL.md:193–199) — runs sentinel verification BEFORE envelope extraction; excluded reviewers drop from all tallies AND prose pathways; warning channel uses standardized `⚠ Reviewer N excluded: <reason>` format.
- **MODIFIED**: critical-review Partial Coverage banner (SKILL.md:303) — extended to surface excluded-but-completed reviewers separately.
- **MODIFIED**: lifecycle critical-tier plan dispatch (`plan.md:43–46`) — receives `{spec_path}` and `{research_path}`, not full contents.
- **MODIFIED**: lifecycle review.md reviewer (`review.md:30`) — receives `{spec_path}`, not contents or hedged phrasing.
- **ADDED**: orchestrator-side realpath-based path validation gate at critical-review entry — rejects paths outside `lifecycle/` AND any path traversing a symlink.
- **ADDED**: orchestrator-side synthesizer SHA verification — top-level diagnostic on synthesizer SHA drift; synthesis output suppressed in that case.
- **ADDED**: `sentinel_absence` and `synthesizer_drift` event types in `lifecycle/{feature}/events.log` for telemetry / future-audit.
- **ADDED**: fast-path unit test for dispatch template placeholders (no live model).
- **ADDED**: path-validation test exercising symlink rejection.
- **MODIFIED**: `tests/test_critical_review_classifier.py` — substitution targets and assertions updated for new placeholders.

## Technical Constraints

- **Worktree-CWD absolute-path resolution** (`docs/overnight-operations.md:601`, `runner.py:455,559` GIT_DIR scrub): orchestrator must absolutify path before injection; dispatched reviewers must NOT re-resolve via `git rev-parse`.
- **No read-side locking** (`requirements/pipeline.md:134`): snapshot consistency uses content hash, not filesystem locks.
- **Per-spawn sandbox is denyWrite/allowWrite only, no read subtree** (`requirements/multi-agent.md:22–23`): reviewer Reads outside the worktree rely on Claude Code's user-scope `read.denyOnly` allowlist, which covers the home repo's `lifecycle/` tree by default.
- **Dual-source mirror enforcement** (`tests/test_dual_source_reference_parity.py`, `just setup-githooks` pre-commit): edits land in canonical sources only; plugin mirrors are regenerated by the pre-commit hook.
- **MUST-escalation policy** (`CLAUDE.md` post-Opus 4.7): no new MUST/CRITICAL/REQUIRED escalations; Read-failure, SHA-mismatch, and synthesizer-drift directives use positive-routing phrasing. Requirement 12's telemetry unblocks the OQ3 evidence-gathering path.
- **Critical-review auto-trigger contract** (`SKILL.md:3`): critical-review fires after plan approval for Complex + medium/high/critical features. The orchestrator writes `plan.md` immediately before fan-out (`plan.md:105`), which is the real (not hypothetical) drift trigger justifying SHA verification across both reviewer and synthesizer windows.
- **`<path>`-argument invocation contract** (`SKILL.md:347`): both auto-trigger and path-arg invocations obey session-bound resolution; path argument does not re-bind `{feature}`. The path validation gate (Requirement 9) applies to both invocation modes; auto-trigger flows additionally narrow to `lifecycle/{feature}/`.
- **`lifecycle/` no-symlinks invariant** (new — Requirement 9c): the validation gate rejects any path whose realpath differs from its abspath. This makes the SEC-1 mitigation a single equality check.
- **Evidence-quote re-validation** (`SKILL.md:218`): synthesizer Reads the artifact once at synthesis start, then iterates per-finding against the in-context Read result. No re-Read per finding (preserves the token saving). Synthesizer emits `SYNTH_READ_OK` for orchestrator-side verification.

## Open Decisions

None. All open questions from research and critical-review have been resolved at spec time:

- **Research Q1 (SHA-pin scope: all three sites or critical-review only)**: applied at all three sites uniformly.
- **Research Q2 (path-arg whitelist scope)**: under home repo's `lifecycle/` tree (auto-trigger flows narrow further to `lifecycle/{feature}/`).
- **Research Q3 (N+2 vs N+1 epic framing)**: not blocked here; flagged for future epic-level rewrite.
- **Research Q4 (SHA mismatch handling: exclude vs abort)**: reviewer-side mismatch → exclude with structured warning (matches existing malformed-envelope handler); synthesizer-side mismatch → abort with top-level diagnostic (the synthesis itself is invalidated, not just one input).
- **Critical-review A1 (parser ordering)**: sentinel check runs BEFORE envelope extraction; sentinel-failed reviewer's envelope not parsed (Requirement 4a).
- **Critical-review A2 (exclusion routing)**: excluded reviewer drops from ALL tallies AND prose channels (Requirement 4b).
- **Critical-review A3 (synthesizer-side drift)**: synthesizer emits `SYNTH_READ_OK`; orchestrator gates on mismatch with top-level diagnostic (Requirements 3 and 4c).
- **Critical-review concern: symlink hole**: realpath-based validation + lifecycle/ no-symlinks invariant (Requirement 9).
- **Critical-review concern: no sentinel-emission telemetry**: events.log `sentinel_absence` and `synthesizer_drift` event types (Requirement 12); live-model emission test deferred to a future ticket gated on telemetry showing actual compliance regression.
