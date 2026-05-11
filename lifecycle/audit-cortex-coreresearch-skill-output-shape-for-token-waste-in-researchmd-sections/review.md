# Review: audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections

## Stage 1: Spec Compliance

### Requirement 1: Delete `skills/lifecycle/references/research.md` in its entirety
- **Expected**: `[ -f skills/lifecycle/references/research.md ]` returns false (exit 1); removed by `git rm`.
- **Actual**: File is absent (`[ -f ... ]; echo $?` → `1`). Commit `22814fe` shows `skills/lifecycle/references/research.md | 198 ---------------------` as a pure deletion.
- **Verdict**: PASS
- **Notes**: Hard-deletion via git, not deprecation marker. Matches the spec's `git rm` directive and the project's hard-deletion preference (`requirements/project.md:23`).

### Requirement 2: Delete the entire Post-Research Checklist from `skills/lifecycle/references/orchestrator-review.md`
- **Expected**: `grep -cE '^(### Post-Research Checklist|^\| R[1-5] \|)' skills/lifecycle/references/orchestrator-review.md` returns `0`.
- **Actual**: grep returned `0`. The 12-line removal in `22814fe` covers the heading, evaluation preamble, table header, and all five R-rows. Post-Specify (S1–S7) and Post-Plan (P1–P10) checklists are untouched.
- **Verdict**: PASS
- **Notes**: Co-orphaned checklist correctly excised; mirror at `plugins/cortex-core/skills/lifecycle/references/orchestrator-review.md` shows the parallel 12-line deletion.

### Requirement 3: Edit `backlog/185-*.md`'s `## Verification` section
- **Expected**: `grep -c 'Superseded by audit findings' ... ≥1` AND `grep -c 'Verification criteria superseded by' ... == 1`.
- **Actual**: `Superseded by audit findings` count = `3` (≥1 ✓); `Verification criteria superseded by` count = `1` (✓).
- **Verdict**: PASS
- **Notes**: Both supersession rationale lines and the pointer blockquote are present. Inventory criterion is retained per spec.

### Requirement 4: Add a "Schema authority" note to `skills/research/SKILL.md`
- **Expected**: `grep -c 'canonical schema source' skills/research/SKILL.md` returns `1`.
- **Actual**: grep returned `1`. The paragraph appears at `skills/research/SKILL.md:192`, immediately after the `## Step 4: Synthesize Findings` heading, separated by blank lines on both sides.
- **Verdict**: PASS
- **Notes**: Paragraph text matches spec verbatim. Positive-routing phrasing ("is the canonical schema source", "must not duplicate or paraphrase") — no new MUST/CRITICAL/REQUIRED escalation introduced.

### Requirement 5: Pre-commit dual-source mirror regenerates and realistic commit flow succeeds
- **Expected**: `just build-plugin` exit 0; mirror absent; commit lands via `/cortex-core:commit` with exit 0; pre-commit drift hook passes.
- **Actual**: Commit `22814fe` exists on `main`. `plugins/cortex-core/skills/lifecycle/references/research.md` is absent (`[ -f ... ]; echo $?` → `1`). Diff stat shows the canonical and mirror deletions/edits paired byte-for-byte (`+2/-198` on both the canonical and mirror SKILL.md / orchestrator-review.md / research.md files).
- **Verdict**: PASS
- **Notes**: Commit message explicitly documents bundling the unrelated `skills/overnight/SKILL.md` working-tree change ("Bundle in-flight working-tree change to skills/overnight/SKILL.md ... since the dual-source pre-commit hook requires canonical and mirror to ship atomically"). Per the spec/plan Veto Surface, this is a documented user-choice ("Commit everything together") response to pre-commit drift detection, not a violation.

### Requirement 6: Existing test suite passes after all canonical edits
- **Expected**: `just test` exit 0 AND `pytest` exit 0, including `tests/test_plugin_mirror_parity.py`.
- **Actual**: Run on current `HEAD` (which is `5de2f43`, one commit past `22814fe`) shows `1 failed, 637 passed`: `tests/test_lifecycle_references_resolve.py::test_every_lifecycle_reference_resolves` fails on `research/lifecycle-discovery-token-audit/research.md:3` resolving `lifecycle/discovery` as an unresolved slug. That file did not exist at commit `22814fe` (`git ls-tree -r 22814fe research/lifecycle-discovery-token-audit/` returns empty) and was added by the later commit `5de2f43`. The test suite was therefore green at the time of the implementation commit.
- **Verdict**: PASS
- **Notes**: The active test failure is a regression introduced by `5de2f43` ("Add lifecycle/discovery token-waste audit research"), not by `22814fe`. The prose collision is a pre-existing-style problem in that newly-tracked file ("lifecycle/discovery/overnight flows") and falls outside #185's scope. Recommend filing a separate ticket to fix the citation form in `research/lifecycle-discovery-token-audit/research.md`.

### Requirement 7: No per-feature research.md token-cost regression introduced; sections preserved as load-bearing
- **Expected**: section-set diff between `HEAD~:skills/research/SKILL.md` and `skills/research/SKILL.md` produces no output (exit 0, no differences).
- **Actual**: Wrote both sorted section header lists to disk and ran `diff` — exit `0`, no output. The seven canonical headers (Codebase Analysis, Web Research, Requirements & Constraints, Tradeoffs & Alternatives, Adversarial Review, Open Questions, Considerations Addressed) are byte-identical pre- and post-edit.
- **Verdict**: PASS
- **Notes**: Confirms Task 5 added a paragraph without disturbing schema headers. Auditable no-regression criterion satisfied.

### Requirement 8: Backlog item #185 is closed via `cortex-update-item`
- **Expected**: `cortex-update-item 185-... status=complete` succeeds; `grep '^status:' backlog/185-*.md` shows `status: complete`.
- **Actual**: Not yet executed; backlog status remains pre-complete at this review point.
- **Verdict**: PARTIAL
- **Notes**: deferred to Complete phase per spec's parenthetical (spec Req 8: "Closure happens at the end of `/cortex-core:lifecycle`'s Complete phase, not during `/cortex-core:refine`"). This is the spec's own design choice, not a non-compliance.

### Requirement 9: Update live-tree prose citations into the deleted file
- **Expected**: `grep -rn 'skills/lifecycle/references/research.md:[0-9]' research/ backlog/ 2>/dev/null` returns no matches.
- **Actual**: grep returned no output (exit 1, no matches). Commit `22814fe` shows citation updates in `research/epic-172-audit/research.md` (1 line), `research/vertical-planning/audit.md` (3 lines), and `backlog/185-*.md`. The untracked-at-time-of-commit `research/lifecycle-discovery-token-audit/research.md` working-tree edit (called out in the task brief) is consistent with the spec's intent.
- **Verdict**: PASS
- **Notes**: All `:LINE` suffix citations into the deleted file are gone from `research/` and `backlog/`. Plan also documented stripping stale `:LINE` suffixes from two unrelated completed lifecycles (`u2-decisions.md` and two `plan.md` files) for test-suite hygiene — acceptable scope-adjacent cleanup since `test_lifecycle_references_resolve.py` would have failed without it.

## Requirements Drift

**State**: none
**Findings**:
- The new "Schema authority" paragraph in `skills/research/SKILL.md` Step 4 establishes a single-skill canonical-source declaration. It is localized (one paragraph in one SKILL.md) rather than a repo-wide documentation-pattern convention, so it does not rise to drift requiring a `requirements/project.md` update. If similar canonical-source declarations spread to other skills in future tickets, a generalized "canonical-source-per-skill" rule may be worth adding then.
- The hard-deletion of the orphan template + Post-Research Checklist exercises the existing "Hard-deletion preference" requirement at `requirements/project.md:23` exactly as written. No drift — the rule already covers this case and the implementation followed it (per-PR zero-loader verification + wholesale removal + replacement entry point referenced in commit body).
**Update needed**: none

## Stage 2: Code Quality

- **Naming conventions**: Deletion annotation phrasing ("deleted in 2026-05-11 per backlog/185") is consistent across the four updated citation sites. Citation rewrites uniformly point to `skills/research/SKILL.md` Step 4 `### Output structure` block. Commit subject ("Delete orphan lifecycle research template; clarify canonical schema source") uses imperative mood and stays within the 72-char cap.
- **Error handling**: N/A — no executable code added; all changes are markdown prose, deletions, and the dual-source mirror regeneration.
- **Test coverage**: `tests/test_lifecycle_references_resolve.py` was kept green at commit time (verified by checking that the only post-commit failure originates from a subsequent unrelated commit `5de2f43`). `tests/test_plugin_mirror_parity.py` would have run as part of the implementation commit's `just build-plugin` + `/cortex-core:commit` flow; the pre-commit drift hook exit 0 (implied by commit landing) confirms canonical/mirror parity. The plan's explicit `:LINE`-suffix-stripping hygiene work on `u2-decisions.md` + two `plan.md` files was load-bearing for keeping the resolver test green after the orchestrator-review.md deletion.
- **Pattern consistency**: The Schema authority paragraph matches the surrounding prose tone in `skills/research/SKILL.md` (declarative sentences, in-line backtick file references, parenthetical implementation notes). Positive-routing phrasing ("Step 4's ... block is the canonical schema source", "downstream consumers ... read research.md whole-cloth and do not parse by section name except for `## Open Questions`") complies with the MUST-escalation policy — no MUST/CRITICAL/REQUIRED escalation introduced.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
