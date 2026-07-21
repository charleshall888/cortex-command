# Review: land-dependency-pipelined-dispatch-and-close

## Test Baseline

`just test` → 8/8 suites passed (consumed from
`/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/2490ffb6-a773-4ea8-bbdc-a8ac0ef7a869/scratchpad/review-baseline.log`;
not re-run per instructions). Plugin mirror parity independently re-verified by diffing
`plugins/cortex-core/skills/lifecycle/references/{plan,orchestrator-checklist-plan,implement,worktree-entry}.md`
against their canonical sources — byte-identical.

## Stage 1 — Spec Compliance

### R1 — Write-serialization edge annotation (ordering-only semantics): **PASS**

`plan.md` "Authoring rules" gains a `**Write-serialization edges**` bullet (between
`**Dependencies**` and `**Straggler isolation**`) with the canonical parenthetical form
(`**Depends on**: [12] (write-serialization: night_rig.gd)`), the single-hyphen-fails-R4 warning,
and one sentence carrying all three semantic anchors together: *"an executor running per-task
isolation may relax the edge to not-before, no executor deletes it, and the overnight pipeline
still treats it as a real edge."* Read as prose this is coherent and unambiguous — relax,
never-delete, and real-edge are stated as three properties of the same edge, not three
independent or conflicting claims. Greps: `write-serialization`=4, `relax`(ci)=1,
`no executor deletes|never delet`=1, `real edge`=1, all ≥1 as required.

The sibling remedy sentence survives in effect at "Sub-task headings": *"give them disjoint
`Files`, or serialize with an explicit edge (`3b` depends on `[3a]`)."* — same guidance, still
scoped to same-batch siblings, unchanged in substance.

### R2 — Hub-file guidance at two writers: **PASS**

`**Hub-file seam**` now reads *"when any two tasks would edit one coordinator file..."* (was
"≥3 tasks"), stays framed as authoring guidance (no gate language), and adds the seam-resistant
caveat verbatim to spec: *"When a seam can't apply — structural rework, deletions, re-pointing —
the honest remedy is an annotated write-serialization edge, not a plain `Depends on`."*
`grep -c '≥3 tasks' plan.md` = 0.

### R3 — Graph-width authoring rule: **PASS**

New `**Graph width**` bullet beside Straggler isolation names both restructure signals (a
single-task level between multi-task levels; a level count approaching half the task count,
calibrated to #358's 11/24), the no-merge caveat cross-referenced to **Task sizing**, and the
face-value/dissolve-first rule: *"Every edge counts at face value when judging depth; annotated
write-serialization segments are the exception worth naming — they're dissolve-first candidates
(restructure, or pick isolated dispatch at approval), not a discount on the measured depth."*
This reads correctly — it does not let an author under-count depth by waving at "well it's just a
serialization edge," it explicitly forbids that discount while still naming those edges as the
first thing to look at when restructuring.

### R4 — Checklist rows: **PASS**

`orchestrator-checklist-plan.md` P13 added, wording near-verbatim to spec R4 (face-value counting,
dissolve-first-not-discount rationale). P11 restated to the 2-writer threshold with remedy wording
*"no early seam task and no serializing `Depends on` chain (an annotated write-serialization edge
qualifies as the chain)."* `grep -c 'P13'` ≥1, `grep -c '≥3'` = 0. P13 correctly appended after P12
matching the table idiom.

### R5 — Plan §4 picker protocol fix: **PASS**

On-main block now calls only `cortex-lifecycle-branch-decision --feature {feature}`; `grep`
confirms zero occurrences of `cortex-lifecycle-picker-decision` or `cortex-lifecycle-branch-mode`
in `plan.md`, and one occurrence of `cortex-lifecycle-branch-decision`. The old attribution line
("Implement §1's branch-mode preflight — it owns the picker guards") is gone, replaced with *"§4
owns rendering the guards from its payload itself, not Implement §1"* — this is an explicit
re-ownership statement, not just a deletion of the old claim.

The two `resolved` sources are distinguished by name and consequence: `branch_mode` folds into
options per ADR-0012; `dispatch_choice` is named a "stale carryover from a prior approval pass,"
still renders the full option surface with the carried mode only as a pre-selected default, and
*"its `entry_mode: selected` is not a live selection at §4 and authorizes no worktree auto-entry
(ADR-0008)"* — the no-auto-entry rule is present and correctly cited. Self-dirtying acknowledgment
is present and reads well: dirty_tree at §4 is named as expected (plan.md itself uncommitted until
§5), not a worktree blocker on its own, while the demotion warning still renders and foreign dirt
is called out as the strongest case *for* isolation. Pinned headings `### 1b. Competing Plans
(Critical Only)` and `### 5. Transition` are byte-intact (grep-confirmed exact match).

### R6a/b/c — Trunk-cost tradeoff copy at all three surfaces: **PASS**

All three files contain `serialize`. §4's note is plan-conditional as required: *"when this
plan.md already carries any (`grep -c 'write-serialization' cortex/lifecycle/{feature}/plan.md`),
cite the count in the note."* Implement §1's note is trailing text appended to the existing
current-branch bullet (not a new line-start `**`-line), preserving the
`test_lifecycle_picker_label_pins_worktree.py` block-regex contract and the worktree label.
worktree-entry.md frames the same cost as the isolation payoff being avoided, which is the
spec-intended framing variation for surface (c), not a wording mismatch.

### R7 — ADR-0031: **PASS**

ADR-0031 exists, re-affirms the batch barrier, grades the #358 evidence honestly (single mid-run
simulation, real durations for 12/24 tasks with placeholders concentrated in exactly the moved
tasks, run 54% complete, artifact off-disk — while still crediting the one structural fact that
survives: DAG depth 11→8 from one mislabeled edge). All 8 named preconditions are present
(dispatch/completion events, metrics batch-semantics, fused checkpoint+merge-back, admission
policy, commit-serialization, substrate pinnability, #39886, and the `dispatch_choice`
freshness/re-record gap). ADR-0030 is `status: accepted` with a substantive in-file "## Reaffirmed
by ADR-0031" section (not a bare frontmatter flip) that explicitly states it *"co-promotes this
ADR's Status field from `proposed` to `accepted` in the same commit"* — matching the ADR-0004
precedent's "## Approach A resolved decisions" amendment shape. Citation audit: ADR-0031
references ADR-0030 and ADR-0012 (both exist); numbering has no gap/duplicate.

Minor, non-blocking observation: the plan's Task 5 Context field anticipated ADR-0031 would also
cite ADR-0008 ("0031 references 0030/0012/0008"), but the shipped ADR-0031 does not mention
ADR-0008 — it wasn't needed (ADR-0008/worktree-auto-entry is R5's concern, not R7's), and
`test_adr_citation_audit.py` is a hermetic fixture-based test with no hard-coded expectation of
that citation, so nothing is actually missing against spec or test.

### R8 — Stale sdk.md line: **PASS**

`run_in_background` row now reads the mode-agnostic rationale citing ADR-0030;
`synchronously coupled` count = 0, `ADR-0030` count ≥ 1.

### Prose budget: **PASS, within target**

Net additions: plan.md Task 1 +4 lines, orchestrator-checklist-plan.md +1 line, plan.md Task 3 +5
lines, implement.md/worktree-entry.md 0 net new lines each (trailing text on existing lines).
Total ≈10 net lines across touched reference files, well under the ≤~25 spec target. plan.md's two
tasks sum to 9 net lines against the file; the plan's own per-task "≤~7" targets are read as
per-task (not cumulative per-file) given the file is touched by two independently-scoped tasks —
a reasonable interpretation, and immaterial either way since the aggregate is far under budget.

### bin/.parity-exceptions.md scope delta (out-of-plan): reviewed, one real defect

Confirmed by diff: `cortex-lifecycle-branch-mode` and `cortex-lifecycle-picker-decision` were
called only at plan.md §4's old raw-verb block (the plan's own Task 3 Context calls this out: "the
pair's ONLY occurrences in the file"), and a repo-wide grep post-change finds zero remaining
callers in `skills/`, `bin/`, or the console-script wrappers — so R5's fix genuinely orphans both
scripts. Two judgment calls:

- **Allowlist vs. delete**: allowlisting was the correct call. Deleting the CLI modules or their
  `pyproject.toml` `[project.scripts]` entries would be a wheel/code change, which the spec's
  Non-Requirements section explicitly forbids ("`should_fire_picker`, `branch_decision.py`... are
  untouched; no new events, no PROTOCOL_VERSION bump" — and confirmed by diff: neither
  `pipeline/parser.py` nor `branch_decision.py` nor `pyproject.toml`'s registrations were touched
  by any of the six task commits). Allowlisting is the only spec-compliant option.
- **Precedent**: the two new rows match the `cortex-lifecycle-dispatch-choice` row's category
  (`deprecated-pending-removal`) and rationale shape (superseded-by X, no remaining SKILL.md/shell
  caller) closely, satisfying the file's own reviewer instruction ("confirm category enum is
  correct and rationale is specific").
- **Defect — wrong date**: both new rows are stamped `2026-07-21`. Today is 2026-07-20, and the
  commit that added them (`24beed6c`) is timestamped `2026-07-20T20:46:03-05:00`. The `added_date`
  field is one day in the future relative to both the system date and the actual commit. This
  does not fail any test (`parity_check.py` only regex-validates `YYYY-MM-DD` shape, no
  future-date check), but it is a factual error in a governance/audit-trail field and should be
  corrected to `2026-07-20`.

This delta was not listed in Task 3's `**Files**` field (only `skills/lifecycle/references/plan.md`
was listed), a minor deviation from the plan's own "Files/Verification consistency" authoring
rule. Given it's a direct, foreseeable, correctly-handled consequence of the in-scope edit (not an
unrelated change), this is process noise rather than a scope violation — noted, not blocking.

No FAIL among R1–R8 — proceeding to Stage 2.

## Stage 2 — Code Quality

- **Naming/wording consistency**: New prose matches the surrounding file's register and
  terminology throughout — "ordering-only," "real edge," "dissolve-first," "stale carryover," and
  "trunk cost" are each introduced once and then reused identically at every other surface that
  needed them (plan.md §Authoring rules ↔ §4 ↔ orchestrator-checklist-plan.md ↔ ADR-0031). No
  synonym drift (e.g., no rogue "hard dependency" vs. "logical dependency" inconsistency).
- **What/Why-not-How**: The new authoring-rule bullets state decision criteria and consequences,
  not procedural steps (e.g., graph-width names *when* to restructure and *why* merging is wrong,
  not a numbered merge-avoidance procedure). §4's edits are necessarily procedural in parts (it's
  an operational protocol section, consistent with the rest of the file's pre-existing style), but
  the added guard/source-distinction/self-dirtying prose is decision-criteria framing, not new
  step-by-step narration.
- **MUST-escalation policy**: grepped every added `+` line across all six task commits for
  MUST/CRITICAL — all hits are ordinary lowercase "must" in descriptive prose (e.g., "the plan
  must carry write-serialization edges," "must be mitigated"), not the all-caps
  MUST/CRITICAL/REQUIRED escalation markers the policy (docs/policies.md) actually governs. No new
  escalation markers introduced; policy respected.
- **Verification steps executed**: all six tasks' per-task grep verification commands were
  re-run independently in this review and match the plan's stated expected values exactly (see
  Stage 1 grep counts above); `just test` baseline is green per the supplied log.
- **Pattern consistency**: ADR-0030's amendment section structurally matches ADR-0004's two
  precedent amendment sections ("## Approach A resolved decisions," "## Committed-iff-complete
  invariant...") — a named section, explicit co-promotion sentence, cross-reference to the
  amending ADR. The `bin/.parity-exceptions.md` rows match the existing table schema and the
  `cortex-lifecycle-dispatch-choice` row's rationale shape (aside from the date defect above).
  Kept-pause markers (`implement-branch-pick` :23, `implement-batch-failure` :81) are unmoved and
  byte-identical, consistent with the constraint that this spec adds no new pauses.

## Requirements Drift

**State**: none
**Findings**: None — this change is prose/decision-record only (plan-authoring rules, a picker
protocol's rendering ownership, one ADR promotion, one stale doc line, and a parity-allowlist
bookkeeping entry). No wheel/code path, event schema, or runtime behavior changed; `pipeline/parser.py`,
`branch_decision.py`, `should_fire_picker`, and the `REASONS` frozenset are untouched, confirmed by
diff. `cortex/requirements/project.md`, `glossary.md`, and `multi-agent.md` require no updates —
none of them enumerate ADR-0030/0031 or the plan.md authoring-rule vocabulary, and nothing here
introduces a new architectural constraint, capability, or boundary the requirements fail to
capture.
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Non-blocking: bin/.parity-exceptions.md's two new rows (cortex-lifecycle-branch-mode, cortex-lifecycle-picker-decision) are dated 2026-07-21; today is 2026-07-20 and the commit that added them is timestamped 2026-07-20. Correct added_date to 2026-07-20 on both rows."], "requirements_drift": "none"}
```
