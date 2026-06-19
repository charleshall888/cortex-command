# Review: combine-plan-approval-and-dispatch

## Stage 1: Spec Compliance

### Requirement 1: Shared branch-picker reference (Should-have)
- **Expected**: The branch-option-assembly decision logic lives in one shared reference file (`skills/lifecycle/references/branch-picker.md`) containing no `AskUserQuestion` literal and not invoking `cortex-lifecycle-branch-mode`.
- **Actual**: `branch-picker.md` was created (commit 47269601) then **reverted** (commit 30905d17) because the extraction broke implement.md content-pinning tests. The decision logic stays self-contained in implement.md §1; plan.md §4 names the same preflight CLIs inline (`cortex-lifecycle-branch-mode .` / `cortex-lifecycle-picker-decision`) and points the reader to "Implement §1 'Branch-mode dispatch preflight'" as the authoritative routing rules.
- **Verdict**: PARTIAL
- **Notes**: The literal file-existence acceptance grep fails (file absent). R1 is **Should-have**, explicitly admitting "the merge could technically function with the prose referenced from one phase." That is exactly what shipped: implement.md §1 is the single source of the decision-logic prose, and plan.md §4 references it rather than re-deriving the routing rules. The deviation is sound — the revert was forced by a real test-pinning constraint, not negligence, and is documented in the spec's review brief and the ADR omits the branch-picker.md path from its decision text. This is acceptable for a Should-have requirement whose stated intent (avoid duplicating the decision logic across both phases) is met: there is one authoritative copy, not two.

### Requirement 2: Both phases consult the shared reference, not inline copies (Should-have)
- **Expected**: After extraction, the decision-logic prose appears once and is referenced by both plan.md §4 and implement.md §1, each retaining its own `AskUserQuestion` call site and `cortex-lifecycle-branch-mode` marker.
- **Actual**: With the extraction reverted, the prose appears once in implement.md §1 (the authoritative copy). plan.md §4 references it by name ("see Implement §1 'Branch-mode dispatch preflight' for the authoritative routing rules") and re-states only the CLI invocation lines it needs to assemble its own surface, while keeping its own `cortex-lifecycle-branch-mode .` invocation in-body. implement.md §1 keeps its own `AskUserQuestion` site (line 22) and `cortex-lifecycle-branch-mode` marker (lines 28/35/38).
- **Verdict**: PARTIAL
- **Notes**: The "appears once, referenced by both" intent is met via implement.md-as-source rather than a third shared file. The duplication-liability the requirement guards against — two independently-maintained copies of the routing logic — does not exist: implement.md §1 is canonical and plan.md §4 defers to it. Both phases keep their own call site + marker (verified: plan.md:281 AskUserQuestion, implement.md:22/50 AskUserQuestion + branch-mode marker at :28/:35/:38). Soundness confirmed; the parity test passes against this arrangement.

### Requirement 3: Merged plan-approval surface
- **Expected**: plan.md §4 assembles a single `AskUserQuestion` of (a) adaptive branch modes + (b) "Approve plan but wait to implement"; worst case 3 modes + wait = 4 (the cap); "Other" is auto-appended outside the cap; Request-changes/Cancel route via "Other"; each revision round re-assembles and re-presents.
- **Actual**: plan.md §4 (lines 265–292) instructs assembling the ≤4-option merged set, explicitly states "Other" is appended "by the platform *outside* the 4-option `options` cap and carries Request-changes and Cancel," routes cancel-intent → `lifecycle_cancelled`+halt and other text → Request-changes revise loop, and directs "re-assemble and re-present this merged surface (re-running the branch-picker assembly)" on each revision round. The off-`main` collapse to `[current branch, wait]` is documented.
- **Verdict**: PASS
- **Notes**: Arithmetic is correct (3 branch modes max + wait = 4; "Other" outside the cap). All edge cases from the spec (off-main collapse, config-suppressed, dirty-tree demotion, worktree-absent) are reachable via the referenced Implement §1 preflight rules.

### Requirement 4: `plan_approved` records the choice
- **Expected**: On a branch-mode selection, emit `plan_approved` carrying `dispatch_choice ∈ {trunk, worktree-interactive, feature-branch}`, then `phase_transition plan→implement`, then auto-advance. `grep -c dispatch_choice plan.md ≥ 1`.
- **Actual**: plan.md §4 emits the documented `plan_approved` JSON with `dispatch_choice: "<trunk|worktree-interactive|feature-branch>"`, then the §5 `phase_transition`, then auto-advances. `grep -c dispatch_choice plan.md` = 4.
- **Verdict**: PASS
- **Notes**: Vocabulary mirrors `_VALID_BRANCH_MODES` minus `prompt`, as specified. §5 correctly requires `plan_approved` to precede `phase_transition` in the log.

### Requirement 5: "Wait to implement" halts, paused and visible
- **Expected**: Selecting "wait" emits `plan_approved{dispatch_choice:"wait"}`, then `feature_paused`, then halts; Context-A (backlog-linked) features get a wait-time overnight warning. `grep -c feature_paused plan.md ≥ 1`.
- **Actual**: plan.md §4's "Approve plan but wait to implement" branch emits both events in order and halts (no auto-advance, no dispatch), notes re-invocation routes to `implement` with the fallback picker, and includes the Context-A warning ("When the feature is backlog-linked (Context A), warn now that the overnight runner may still execute the item unless it is paused"). `grep -c feature_paused plan.md` = 2.
- **Verdict**: PASS
- **Notes**: The §5 transition correctly fires the durability commit on the wait path (commit makes approval durable, then halt) while skipping the `phase_transition` event (only emitted on a branch-mode selection).

### Requirement 6: Implement consumes the recorded choice (line-position-last, with explicit fallback)
- **Expected**: implement.md §1 reads the line-position-last `plan_approved` `dispatch_choice`; valid branch mode → skip picker, route to matching path; `wait`/absent-field/no-`plan_approved` → fallback picker. Unit test asserts line-position-last + three-way fallback; `grep -c dispatch_choice implement.md ≥ 1`.
- **Actual**: implement.md §1 (lines 11–21) reads via `cortex-lifecycle-dispatch-choice --feature {slug}`, gated on `main`/`master`. Valid branch mode → "do not render the picker," substitute as the picker result, run identical post-selection routing (`worktree-interactive` → entry mode `selected` + Step A/B + §1a; `trunk` → §2; `feature-branch` → inline create + §2). `wait`/empty/command-not-found → fallback picker. The resolver `read_dispatch_choice` (lifecycle_implement.py:144) scans line order, keeps the last `plan_approved`, reassigns on every match including the field-absent case (resets to None). Tests cover all five shapes plus the later-fieldless-supersedes case. `grep -c dispatch_choice implement.md` = 1; 9/9 resolver tests pass.
- **Verdict**: PASS
- **Notes**: The line-position-last reset logic is correct — `result = choice if isinstance(choice, str) else None` runs on every `plan_approved` row, so a later field-less row correctly supersedes an earlier recorded choice (verified by `test_later_fieldless_supersedes_earlier_choice`). The worktree path is pinned to `selected` (not `suppressed`), preserving the ADR-0008 `EnterWorktree` authorization and Step A/B guards.

### Requirement 7: Kept-pauses inventory + parity test stay green (multi-site)
- **Expected**: SKILL.md inventory updated — plan.md entry reflects the merged surface at its new anchor (unconditional pause); implement.md entry remains (now fallback) with its conditional-pause marker within ±35 lines of its `AskUserQuestion` site. Parity test enforces both directions over every site. `pytest test_lifecycle_kept_pauses_parity.py` exits 0.
- **Actual**: SKILL.md:189 anchors plan.md:281 (the merged surface, no "conditional pause" tag → unconditional). SKILL.md:190 anchors implement.md:50, tagged "conditional pause" with the marker note; the `cortex-lifecycle-branch-mode` marker is at implement.md:28/35/38 (within ±35 of :50). Parity test: 2 passed.
- **Verdict**: PASS
- **Notes**: The plan.md entry is correctly kept unconditional despite plan.md retaining a `cortex-lifecycle-branch-mode` invocation in-body — plan approval always fires, so no spurious conditional-marker match. Both-direction parity holds across all `AskUserQuestion` sites under skills/lifecycle and skills/refine.

### Requirement 8: Events-registry coherence
- **Expected**: `plan_approved` row updated to note the new `dispatch_choice` field (no new event type). `just check-events-registry` exits 0.
- **Actual**: bin/.events-registry.md:21 `plan_approved` rationale now documents the merged surface, the optional `dispatch_choice` field with its closed value set (`trunk / worktree-interactive / feature-branch / wait`), the line-position-last read by `read_dispatch_choice`, and the picker-skip behavior. No new row. The events-registry gate (`--audit`) parses the registry and exits 0 (the STALE_DEPRECATION warnings it surfaces are pre-existing rows from epic 172 with deprecation_date 2026-06-10, unrelated to this feature).
- **Verdict**: PASS
- **Notes**: Table column structure preserved; description-only edit satisfies the gate's emitted-name scan.

### Requirement 9: SKILL.md prose reconciled
- **Expected**: SKILL.md Phase-Transition text describing Plan approval as "Approve / Request changes / Cancel" updated to describe the merged surface.
- **Actual**: SKILL.md:178 (per-phase completion rule) now reads "Plan's §4 is **merged with the Implement branch/dispatch selection**: the branch modes plus an 'Approve plan but wait to implement' option are the surface (selecting a branch mode implies plan approval; Request changes / Cancel ride the 'Other' free-text escape)," and describes `plan_approved` + `dispatch_choice` + the wait→`feature_paused` halt. SKILL.md:189 inventory entry matches.
- **Verdict**: PASS
- **Notes**: Specify's surface is correctly left as "Approve / Request changes / Cancel" (unchanged per Non-Requirements).

### Requirement 10: SKILL-to-bin parity for any new helper
- **Expected**: If the resolver is a new `bin/cortex-*`/console-script it must wire through an in-scope reference; `cortex-check-parity` exits 0 (W003 orphan check).
- **Actual**: The resolver ships as a `[project.scripts]` console-script (`cortex-lifecycle-dispatch-choice = "cortex_command.lifecycle.dispatch_choice_cli:main"` in pyproject.toml:54), not a `bin/cortex-*` script, so W003 does not apply. It is nonetheless wired into implement.md §1 (consumer reference) and exercised by the test suite. The console-script resolves and exits 0 (`.venv/bin/cortex-lifecycle-dispatch-choice --feature combine-plan-approval-and-dispatch` → exit 0).
- **Verdict**: PASS
- **Notes**: The full suite (which includes parity gates) passes apart from one network-only test (see R11).

### Requirement 11: Full test suite passes
- **Expected**: `just test` exits 0.
- **Actual**: `just test` reports 6/7 groups pass; the single failure is `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`, which fails with a DNS/network error fetching `https://pypi.org/simple/mcp/` — the sandbox network allowlist excludes pypi.org. With that one network-dependent test deselected, the full `tests/` group passes: **1989 passed, 27 skipped, 1 xfailed**.
- **Verdict**: PASS
- **Notes**: The lone failure is an environment/sandbox artifact (no network to pypi.org), entirely unrelated to this feature. The feature introduces no test regressions. R11's intent — the feature does not break the suite — is satisfied.

### Requirement 12: Follow-up ticket filed for overnight-honors-pause
- **Expected**: A `cortex/backlog/NNN-*.md` exists referencing the overnight `filter_ready` / `feature_paused` interaction.
- **Actual**: `cortex/backlog/310-overnight-runner-honors-feature-paused-wait.md` exists; its body references `filter_ready` (`cortex_command/overnight/backlog.py`), the no-`plan.md`-requirement gap, `feature_paused`, and ADR-0012. Both grep tokens present.
- **Verdict**: PASS
- **Notes**: Body correctly frames the gap (overnight eligibility blind to the pause signal) and the non-goal (not changing the interactive surface).

## Stage 2: Code Quality

- **Naming conventions**: `read_dispatch_choice` follows the module's public-symbol naming and is documented in the updated module docstring ("exactly three public symbols"). `dispatch_choice_cli.py` mirrors `state_cli.py` conventions: argparse with `prog`/`description`, `--feature` arg (not `branch_mode_cli.py`'s positional path, as the spec requires), `_telemetry.log_invocation`, `main(argv)`, CWD-relative `cortex/lifecycle/{feature}/events.log` resolution. Console-script name parallels `cortex-lifecycle-state`. Consistent throughout.
- **Error handling**: `read_dispatch_choice` degrades gracefully — `FileNotFoundError`/`OSError` → `None`; torn/non-object JSON lines skipped (not collapsing the scan, verified by `test_torn_line_skipped_not_collapsed`); `errors="replace"` on read tolerates encoding damage. The line-position-last reset (`result = choice if isinstance(choice, str) else None` on every `plan_approved` match) correctly handles the later-fieldless-supersedes case. The CLI prints empty string + newline and exits 0 for the no-choice case (consumer treats empty as fallback). The implement.md consumer handles command-not-found as a fallback trigger, and the read is gated on main/master so it always runs in the main-repo CWD (the worktree carries its own events.log) — sound.
- **Test coverage**: Eight unit cases plus a subprocess smoke cover all three absent-field fallback shapes, the line-position-last rework cycle, the later-fieldless-supersedes reset, the wait verbatim case, the missing-file case, and torn-line resilience. The CLI smoke asserts exit 0 and correct stdout. Coverage matches the R6 contract exactly.
- **Pattern consistency**: Skill prose follows "prescribe What and Why, not How" — plan.md §4 and implement.md §1 describe decisions and routing intent, not procedure. The consumer correctly substitutes the recorded choice for the picker result and runs identical post-selection routing (worktree → `selected` entry mode + Step A/B + §1a; feature-branch → inline create via §2; trunk → §2), preserving every guard rather than jumping past them. There is no phantom "§1b" reference (feature-branch is the inline §2-reachable path, consistent with the actual file structure). The dual-source mirror is in sync (plan.md, implement.md, SKILL.md mirrors all match canonical; bin/.events-registry.md is canonical-only, not mirrored, consistent with it being static-gate data). The "Other"→cancel-vs-request-changes classification is model judgment (flagged as a soft surface in the plan Risks), acceptable under the design principle.

## Requirements Drift
**State**: none
**Findings**: None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
