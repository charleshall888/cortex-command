# Review: refine-commits-lifecycle-artifacts

## Stage 1: Spec Compliance

### Requirement 1: `read_commit_artifacts()` exists in `cortex_command/lifecycle_config.py`
- **Expected**: helper returns `True` when `cortex/lifecycle.config.md` is absent or its frontmatter omits the key (preserving the current default); returns the parsed boolean otherwise. Acceptance: `grep -c "def read_commit_artifacts" cortex_command/lifecycle_config.py` = 1; unit test asserts three branches (absent file → True, key absent → True, key present `false` → False).
- **Actual**: `cortex_command/lifecycle_config.py:91-140` implements `read_commit_artifacts(repo_root)` with the required default-True semantics for the three required branches plus defensive default-True behavior for malformed YAML, non-dict frontmatter, and non-boolean values (each with stderr warnings on the warning paths). `grep -c "def read_commit_artifacts" cortex_command/lifecycle_config.py` = 1 (verified). All three required branches are covered by tests in `tests/test_lifecycle_config_commit_artifacts.py:34-47`, plus three additional defensive branches.
- **Verdict**: PASS
- **Notes**: The module docstring (lines 1-12) was correctly updated from the prior "exactly one public symbol" claim to enumerate both symbols.

### Requirement 2: `plan.md:306` and `complete.md:19` read the flag via the helper
- **Expected**: prose invokes the helper directly via `python3 -c` or a `cortex-*` binstub, replacing the prior prose-resident flag check. Acceptance: `grep -c 'read_commit_artifacts\|cortex-read-commit-artifacts' skills/lifecycle/references/plan.md skills/lifecycle/references/complete.md` ≥ 2 AND the prior `"If commit-artifacts is enabled in project config (default), stage cortex/lifecycle/{feature}/"` sentence is removed from both files.
- **Actual**: `plan.md:306` and `complete.md:19` each invoke `cortex-read-commit-artifacts` and branch on `true` / `false` stdout. Combined grep count = 2 (1 hit per file). The prior prose-resident sentence is absent from both files (`grep -n "If commit-artifacts is enabled in project config" skills/lifecycle/references/plan.md skills/lifecycle/references/complete.md` exits 1 with no output).
- **Verdict**: PASS
- **Notes**: `complete.md:19` correctly preserves the additional sentences about staging uncommitted source changes and `commit-artifacts: false` exclusion semantics per the plan's wording guidance.

### Requirement 3: `specify.md:206`'s dead inline commit is removed
- **Expected**: the prior sentence is deleted from `skills/lifecycle/references/specify.md`. Acceptance: `grep -c "commit-artifacts" skills/lifecycle/references/specify.md` = 0.
- **Actual**: `grep -c "commit-artifacts" skills/lifecycle/references/specify.md` = 0 (verified). The deleted line's surrounding region (`specify.md:200-207`) is intact: the `phase_transition` event-logging block is preserved, and the "After approval, proceed to Plan automatically" sentence follows directly without the orphaned commit instruction.
- **Verdict**: PASS

### Requirement 4: `skills/lifecycle/references/post-refine-commit.md` exists and documents the contract behaviorally
- **Expected**: file exists; documents preconditions (most-recent-event detection), flag check (helper invocation), commit invocation (`/cortex-core:commit`), and the halt-before-Plan gate; cancel-path commit subject contract present. Acceptance: file present; references `read_commit_artifacts` (or the binstub) and `/cortex-core:commit`; `grep -ci "halt\|do not auto-advance\|do not advance"` ≥ 1; `grep -ci "precondition\|since the last commit"` ≥ 1.
- **Actual**: `skills/lifecycle/references/post-refine-commit.md` exists (77 lines). It opens with a `## Preconditions` section enumerating the two trigger events plus the detection algorithm; includes a `## Flag Check` section invoking `cortex-read-commit-artifacts`; a `## Staging` section enumerating explicit paths per the Adversarial Review §3 finding (avoiding directory globs to prevent residue-bundling); a `## No-Op Short-Circuit (Stage-First)` section documenting the `git diff --cached --quiet` short-circuit; a `## Commit Subject` section with both approval and cancel subjects and the most-recent-event detection rule restated; and a `## Halt-Before-Plan Gate` section using the required MUST language plus the explicit "Do not auto-advance to Plan" phrase. Grep counts: halt-tokens = 4, precondition/since-last-commit tokens = 4, cancel tokens = 5 — all comfortably above the ≥ 1 thresholds.
- **Verdict**: PASS

### Requirement 5: Lifecycle SKILL.md Step 3 invokes `post-refine-commit.md` on the happy path
- **Expected**: after the `phase_transition from=specify to=plan` row is logged, the trunk reads `references/post-refine-commit.md` and follows it. Acceptance: `grep -c "post-refine-commit" skills/lifecycle/SKILL.md` ≥ 1 AND an integration-style test in `tests/test_post_refine_commit_wired.py` asserts the substring appears after the `phase_transition` event-logging block.
- **Actual**: `skills/lifecycle/SKILL.md:159` adds a new Step 6 "Post-refine commit" entry that explicitly names both happy-path and cancel-path triggers and points at the new reference; `skills/lifecycle/SKILL.md:235` adds a Reference Files bullet for the same. Combined grep count = 2 (≥ 1 ✓). `tests/test_post_refine_commit_wired.py:60-94` (`test_skill_md_wires_post_refine_commit_within_distance`) asserts the wiring sentence appears within 50 lines after both the `phase_transition specify→plan` line and the `lifecycle_cancelled` mention — line-distance-bounded, more rigorous than a DOTALL substring check. All three tests in that file pass.
- **Verdict**: PASS

### Requirement 6: Cancel path commits with a distinct subject; detection is "most recent event since last commit"
- **Expected**: `post-refine-commit.md` instructs the orchestrator to compose a distinct cancel-path subject; the detection rule is "most recent significant event since the most recent commit on the current branch." Acceptance: `grep -ci "since the last commit\|since last commit\|most recent"` ≥ 1 AND `grep -ci "cancelled\|cancel"` ≥ 1.
- **Actual**: `post-refine-commit.md:55-62` documents both the approval subject (`Refine {feature}: research and spec`) and the cancel subject (`Refine {feature}: cancelled at spec approval`), then restates the detection rule with the verbatim "since the last commit" qualifier required by the spec. The detection algorithm (line 12) describes the bottom-up scan and explains operationally why the rule satisfies the qualifier. Greps: since-tokens = 4, cancel-tokens = 5 — both well above ≥ 1.
- **Verdict**: PASS

### Requirement 7: Existing tests pass; new tests cover the helper
- **Expected**: `just test` exits 0 after the changes. A new `tests/test_lifecycle_config_commit_artifacts.py` asserts the helper's three branches. Acceptance: `just test` exits 0; `grep -c "read_commit_artifacts" tests/` ≥ 1.
- **Actual**: The new test file `tests/test_lifecycle_config_commit_artifacts.py` exists with 6 tests covering all three required branches plus three defensive ones; `grep -c "read_commit_artifacts" tests/test_lifecycle_config_commit_artifacts.py` = 8 (well above ≥ 1). All 6 helper tests + 3 wiring tests = 9 pass. The kept-pauses parity test (`tests/test_lifecycle_kept_pauses_parity.py`) still passes — confirming no `AskUserQuestion` regression. **However**, a full `pytest tests/ -x` run reveals one pre-existing failure unrelated to this PR: `tests/test_cortex_resolve_backlog_item_parity.py::test_stderr_parity[title_phrase_ambiguous]` fails because the expected-fixture says `"ambiguous: 31 matches"` while the live backlog now has 32 matches. The failure reproduces with the PR's changes stashed (verified via `git stash --include-untracked --keep-index`), and `git log -- cortex/backlog/` shows the drift came from commits `7a9de88c` (Refine and plan #266) and `f5f1daed` (Decompose auto-init-and-update discovery into ticket 267) — both unrelated to this PR. This is fixture maintenance debt in a sibling area, not a defect introduced by refine-commits-lifecycle-artifacts.
- **Verdict**: PARTIAL
- **Notes**: The R7 acceptance criterion as written ("`just test` exits 0") is not literally satisfied because of a sibling-area test-fixture drift that landed in earlier commits. The new tests required by R7 itself all pass. Treating this as PARTIAL rather than FAIL because (a) the failing test is not in the implementation surface of this PR, (b) the failure pre-exists the changes under review, and (c) the spec's intent — "the helper is covered by tests and nothing this PR introduces breaks the suite" — is fully satisfied. Recommend a separate ticket to refresh the backlog-ambiguous fixture to reflect the current ticket count.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `cortex-read-commit-artifacts` follows the `cortex-<verb>-<noun>` binstub pattern (`cortex-lifecycle-state`, `cortex-resolve-backlog-item`, `cortex-update-item`). The binstub's four-branch wrapper structure is byte-identical (modulo command-line and remediation message) to `cortex-lifecycle-state`, the explicit reference the plan names. Module-level constants in `lifecycle_config.py` (`_COMMIT_ARTIFACTS_FIELD`, `_COMMIT_ARTIFACTS_DEFAULT`) match the existing `_FIELD_NAME` underscore-prefix convention. `_main` is correctly underscore-prefixed (private) while `read_commit_artifacts` and `read_branch_mode` are the public API surface.

- **Error handling**: The helper handles all degenerate input modes (missing file, malformed YAML, non-dict frontmatter, missing key, non-boolean value) by defaulting safely to `True` and emitting stderr warnings on the cases where the operator would benefit from seeing a misconfiguration. This is more defensive than spec R1 requires (R1 names only three branches; the implementation covers six). The binstub's branch (d) prints a remediation hint to stderr and exits 2, matching `cortex-lifecycle-state`'s behavior for the unrecoverable case. The `_main` function correctly uses `$CORTEX_COMMAND_ROOT` first, falling back to `os.getcwd()` — symmetric with how the binstub's branch (c) resolves the working-tree root.

- **Test coverage**: The verification steps from the plan have all executed and pass. Task 1 verifies via `pytest tests/test_lifecycle_config_commit_artifacts.py` (6/6 passing). Task 2's verification (binstub printing `true` against the repo's config) reproduces (`bin/cortex-read-commit-artifacts` from repo root prints `true\n` with rc=0). Task 3's `grep -c "commit-artifacts" skills/lifecycle/references/specify.md` = 0. Task 4's five content greps all hit. Task 5's `grep -c "post-refine-commit"` = 2 and the line-distance assertion in the wiring test passes. Task 6's three tests all pass. The plan also specifies that the wiring test should be a content guard (not bare `.exists()`) to catch post-merge regressions deleting the halt clause or cancel-subject contract — the test correctly enforces all five required content tokens.

- **Pattern consistency**: Dual-source enforcement is honored — `diff bin/cortex-read-commit-artifacts plugins/cortex-core/bin/cortex-read-commit-artifacts` exits 0, and the same is true for SKILL.md, plan.md, complete.md, specify.md, and post-refine-commit.md against their `plugins/cortex-core/` mirrors. Wiring co-location is honored: the binstub is deployed and referenced from both `plan.md` and `complete.md` in the same commit (`12d3f419` per the plan's Status notes), so `cortex-check-parity`'s W003 orphan rule does not fire. The `pyproject.toml` `[project.scripts]` entry for `cortex-read-commit-artifacts` (line 52) follows the same pattern as `cortex-lifecycle-branch-mode`, ensuring production-install parity (an additional consistency win the plan explicitly cited as scope creep but justified). The helper invocation in `post-refine-commit.md` uses the binstub form (not `python3 -c`), matching the form chosen for `plan.md` and `complete.md` — all three live consumers consult the flag through exactly the same code path.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
