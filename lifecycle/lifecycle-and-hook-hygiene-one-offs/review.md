# Review: lifecycle-and-hook-hygiene-one-offs

## Stage 1: Spec Compliance

### Requirement 1: Sub-item 1 — Lifecycle SKILL.md Step 2 single-resolve
- **Expected**: Collapse the four backlog-glob blocks in lifecycle SKILL.md Step 2 into one `cortex-resolve-backlog-item` invocation in Step 1; pass the resolved filename + a single frontmatter read forward; preserve the empty-`$ARGUMENTS` fallback; document resolver exit-code handling (0/2/3/64/70).
- **Actual**: Commit `7ee2d9c` lands the collapse. The four sub-procedures were extracted upstream by a parallel session into `skills/lifecycle/references/backlog-writeback.md` (3 sub-procedures) and `skills/lifecycle/references/discovery-bootstrap.md` (1 sub-procedure); the single-resolve refactor was applied across all three files with user-approved scope expansion (documented in `events.log` and commit body).
  - AC1 `grep -c 'backlog/\[0-9\]\*-\*' skills/lifecycle/SKILL.md` → **1** (target = 1) PASS
  - AC2 `grep -c 'cortex-resolve-backlog-item' skills/lifecycle/SKILL.md` → **2** (target ≥ 1) PASS
  - AC3 mirror grep → **2** (target ≥ 1) PASS
  - AC4 empty-args fallback preserved (`git diff main` `^-.*incomplete lifecycle dirs` = **0**) PASS
  - AC5 exit-code branches `grep -cE 'exit.*[0237]'` → **5** (target ≥ 4) PASS
  - AC6 behavioral spot-check: spec explicitly annotates this as interactive/session-dependent and not automatable; deferred per spec language.
- **Verdict**: PASS
- **Notes**: Scope expansion to references/*.md is faithful to spec intent (single-resolve attention discipline); commit body and `events.log` orchestrator_review record the expansion transparently.

### Requirement 2: Sub-item 3 — Discovery auto-scan DELETE
- **Expected**: Hard-delete `skills/discovery/references/auto-scan.md`; scrub no-topic trigger phrases from canonical + mirror SKILL.md, `docs/interactive-phases.md`, and the fixture; add a `## [Unreleased]` `### Removed` CHANGELOG entry naming the replacement entry point + recovery tag; create and push `deprecated-auto-scan-*` git tag pointing at the pre-deletion commit.
- **Actual**: Commit `ecff19b` lands all deletions and scrubs.
  - AC1 canonical auto-scan.md absent → **absent** PASS
  - AC2 mirror auto-scan.md absent → **absent** PASS
  - AC3 canonical SKILL.md trigger-text count → **0** PASS
  - AC4 mirror SKILL.md trigger-text count → **0** PASS
  - AC5 `docs/interactive-phases.md` `auto-scan` count → **0** PASS
  - AC6 fixture `find gaps in requirements` count → **0** PASS
  - AC7 CHANGELOG (corrected awk per events.log fix #4) `auto-scan|no-topic discovery` under `## [Unreleased]` → **1** PASS. The entry names `/cortex-core:dev` as the replacement entry point and the `deprecated-auto-scan-2026-05-11` git tag as the recovery affordance, with restore command.
  - AC8 local tag exists (`deprecated-auto-scan-2026-05-11`) and contains the pre-deletion `skills/discovery/references/auto-scan.md` (`git cat-file -e` exits 0) PASS
  - AC9 remote tag (`git ls-remote --tags origin | grep -c deprecated-auto-scan-2026-05-11`) → **2** (pushed) PASS
  - AC10 `uv run pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py` → **4 passed** PASS
- **Verdict**: PASS

### Requirement 3: Sub-item 4 — skill-edit-advisor scoped check
- **Expected**: Replace `just test-skills` with the two scoped sub-suites; cap captured stdout ≤500 chars on both pass and fail paths; record the `clarify_critic_amendment` waiver event; keep `tests/test_lifecycle_references_resolve.py` green; new shell test `tests/test_skill_edit_advisor_scope.sh` passes.
- **Actual**: Commits `2005168` (advisor + new shell test) and `8fa8ca8` (prose-collision unblock for pytest) land the scoped check.
  - AC1 `grep -c 'just test-skills' claude/hooks/cortex-skill-edit-advisor.sh` → **0** PASS
  - AC2 (relaxed per events.log fix #3) single-argv form `grep -cE 'just[ +].*(test-skill-contracts|test-skill-design)'` → **4** (target ≥ 1) PASS. Implementation uses single-argv `just test-skill-contracts test-skill-design` at L48, per spec mechanism.
  - AC3 byte/line cap (`head -c 500` form) → **1** explicit match plus a second non-regex-matching `head -c "$OUT_BUDGET"` usage at L61 (where `OUT_BUDGET = 500 - len(SUFFIX)`). Both pass and fail paths cap output PASS
  - AC4 `uv run pytest tests/test_lifecycle_references_resolve.py` → **4 passed** PASS
  - AC5 `bash tests/test_skill_edit_advisor_scope.sh` → **4/4 passed** (set-based recipe assertion + pass-path cap + fail-path cap) PASS
  - AC6 waiver event `clarify_critic_amendment` present in events.log with `amendment` field naming `review.md:39 backtick-wrap` (and `rationale`/`status: approved`) PASS
- **Verdict**: PASS
- **Notes**: The advisor includes graceful degradation paths for missing `just` binary and missing recipes (both exit 0 with an advisory `additionalContext` message) — clean implementation of §35 graceful partial failure.

### Requirement 4: Reframe in spec/commits/PR
- **Expected**: Per-sub-item commit bodies carry the appropriate categorization tag (`token cut|context bloat|workflow trim`); spec body and Non-Requirements acknowledge the mixed framing.
- **Actual**: `git log --format=%B 80ee899..ecff19b | grep -cE 'token cut|context bloat|workflow trim'` → **4** (target ≥ 3). Per-commit:
  - `7ee2d9c` (Sub-item 1): "This is a **token cut**: 4 separate backlog scans + 4 frontmatter reads collapse to 1 resolver call + 1 frontmatter read..."
  - `ecff19b` (Sub-item 3): "This is a **workflow trim**: ~85-line reference file removed..."
  - `2005168` (Sub-item 4): "This is a **workflow trim + context bloat** reduction: latency drops 5-6x ... agent-context cost ... shrinks from ~175-700 tokens to ≤500 chars..."
  - PR-body AC is `gh pr view`-deferred (review runs on the merged branch; PR check is verified externally in the PR-creation step).
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- §23 workflow-trimming: Sub-item 3 follows the doctrine exactly — hard delete + CHANGELOG `### Removed` entry naming replacement entry point + recovery git tag (pushed). No drift.
- §29 SKILL.md-to-bin parity: `./bin/cortex-check-parity` exit 0; no parity change required (resolver was already wired). No drift.
- §30 SKILL.md 500-line cap: `skills/lifecycle/SKILL.md` = 192 lines; `skills/discovery/SKILL.md` = 71 lines. Both well under 500. No drift.
- §19/§21/§36: implementation simplifies (4 globs→1 resolver, full umbrella→2 scoped suites, dead path deleted). No drift.
- §35 graceful partial failure: hook degrades to advisory exit 0 on missing `just` or missing recipes. No drift.

**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the existing hook/script vocabulary — `MSG_A`/`MSG_B` for branch-specific advisory messages, `CAP`/`OUT_BUDGET`/`SUFFIX_LEN` for budget arithmetic, `TEST_OUTPUT`/`TEST_EXIT`/`TRUNCATED`/`FAIL_MSG_CAPPED` for the test-execution variables. The shell test file (`tests/test_skill_edit_advisor_scope.sh`) follows the `test_*_scope.sh` naming pattern.
- **Error handling**: Strong. `set -euo pipefail` at top; explicit graceful-degradation branches (missing `just`, missing recipes) emit advisory `additionalContext` and exit 0; the test invocation uses `&& TEST_EXIT=0 || TEST_EXIT=$?` to capture non-zero exits without tripping `pipefail`. The resolver exit-code routing in lifecycle SKILL.md Step 1 covers all 5 documented codes (0/2/3/64/70). Suffix-inclusive cap arithmetic is defensive: a second `head -c $CAP` reapplies the cap after composing the FAIL_MSG prefix.
- **Test coverage**: The new `tests/test_skill_edit_advisor_scope.sh` exercises three contract surfaces — set-based recipe assertion via a PATH-shimmed `just`, pass-path cap, and fail-path cap. The shimmed-`just` design isolates the hook contract from real test latency. Existing `tests/test_lifecycle_references_resolve.py` (4 cases) remains green. Sub-items 1 and 3 ride on existing integration coverage per spec Non-Requirements.
- **Pattern consistency**: The hook follows the existing PostToolUse advisory pattern (jq-emitted `hookSpecificOutput.additionalContext`, non-blocking exit 0, basename-filtered file matching). Plugin-mirror regeneration via `just build-plugin` is recorded in commit bodies. The dual-source canonical/mirror discipline is observed for all changed skill files. Resolver invocation in SKILL.md follows the existing CLI-boundary prose pattern (positive-routing phrasing, no MUST escalation — consistent with the post-Opus-4.7 policy).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
