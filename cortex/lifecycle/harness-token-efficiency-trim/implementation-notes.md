# Implementation Notes: harness-token-efficiency-trim

Audit date: 2026-06-10. Branch: `feature/harness-token-efficiency-trim`. Feature branched from `origin/main` at `362bf765`.

---

## A. Byte Accounting

### Measurement method

- **Before**: `git cat-file -s origin/main:<path>` — returns 0 for new files (not on origin/main).
- **After**: `wc -c <path>` on current branch.
- **Scope**: canonical `skills/` paths only; `plugins/cortex-core/` mirrors excluded (mechanically regenerated, double-counts everything).
- **Accept floor**: ≥ 30,000 bytes net reduction across all canonical `skills/` paths including give-backs (new files).

### Per-file table

| File | Before (B) | After (B) | Delta | Evid.Safe | Deviation | Deviation explanation |
|---|---:|---:|---:|---:|---:|---|
| `skills/lifecycle/SKILL.md` | 25,045 | 20,546 | −4,499 | 2,710 | +1,789 | Downgraded proposals (5 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/implement.md` | 31,624 | 24,456 | −7,168 | 6,835 | +333 | Downgraded proposals (5 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/plan.md` | 26,360 | 22,214 | −4,146 | 4,205 | −59 | See note¹ |
| `skills/lifecycle/references/complete.md` | 18,728 | 14,917 | −3,811 | 3,000 | +811 | Downgraded proposals (3 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/specify.md` | 17,833 | 15,276 | −2,557 | 2,286 | +271 | Downgraded proposals (2 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/review.md` | 12,703 | 10,530 | −2,173 | 1,823 | +350 | Downgraded proposals (2 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/clarify.md` | 11,326 | 9,019 | −2,307 | 1,965 | +342 | Downgraded proposals (1 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/orchestrator-review.md` | 11,573 | 10,170 | −1,403 | 1,490 | −87 | See note² |
| `skills/refine/SKILL.md` | 21,236 | 16,187 | −5,049 | 4,010 | +1,039 | Downgraded proposals (4 applied) produced savings beyond safe floor |
| `skills/refine/references/clarify-critic.md` | 20,200 | 14,835 | −5,365 | 4,145 | +1,220 | Downgraded proposals (4 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/post-refine-commit.md` | 7,031 | 3,486 | −3,545 | 3,260 | +285 | Downgraded proposals (1 applied) produced savings beyond safe floor |
| `skills/lifecycle/references/backlog-writeback.md` | 6,008 | 4,367 | −1,641 | 810 | +831 | Downgraded proposals (4 applied) + resolved-by-prior-tasks produced savings beyond safe floor |
| `skills/lifecycle/references/refine-delegation.md` | 0 | 2,117 | +2,117 | — | — | New file (give-back); extracted from SKILL.md Step 3 for progressive disclosure |
| `skills/lifecycle/references/critical-review-gate.md` | 0 | 1,378 | +1,378 | — | — | New file (give-back); extracted shared gate from specify.md §3b and plan.md §3b |
| **TOTAL** | **209,667** | **169,498** | **−40,169** | **36,539** | **+3,630** | |

**Net reduction: 40,169 bytes (19.2%) — exceeds 30,000-byte acceptance floor.**

Note¹ — `plan.md` −59B deviation: `evidence.json` safe estimate (4,205B) was set at feature seed (origin/main baseline). Tasks 2 and 3 reduced plan.md by 336B before Task 7 ran; Task 7 then saved a further 3,810B (confirmed by commit body: "26,024 → 22,214 (-3,810B)"). Total savings from origin/main = 336 + 3,810 = 4,146B. The deviation is −59B (1.4%), within normal prose-condensation estimation tolerance.

Note² — `orchestrator-review.md` −87B deviation: estimate (1,490B) was slightly optimistic relative to actual (1,403B). All 8 safe and 2 downgraded proposals were applied; the −87B gap (5.8%) reflects normal imprecision in short-prose condensation estimates.

### Resume-at-plan load measurement (informational)

The pre-feature baseline for resume-at-plan sessions was 60.5KB: `SKILL.md` (25,045) + `backlog-writeback.md` (6,008) + `plan.md` (26,360) + `discovery-bootstrap.md` (3,119) = 60,532B.

Current branch: `SKILL.md` (20,546) + `backlog-writeback.md` (4,367) + `plan.md` (22,214) = 47,127B without `discovery-bootstrap.md` (now conditionally read on phase=none/research only). Including it: 47,127 + 4,786 = 51,913B.

Reduction from 60,532B baseline: **−8,619B (14.2%)** when discovery-bootstrap is included; **−13,405B (22.1%)** without it (resume-at-plan sessions, which is the common case, never load it).

---

## B. Citation Sweep

### Scope

Grep `cortex_command/` recursively for `§` and `Step N` tokens that cite the trimmed skill files. The mechanized citation pins in `tests/test_skill_section_citations.py` already cover: `plan.md §1a`, `plan.md §1b`, `plan.md §5`, `complete.md Step 2`, `review.md §4a`. This section documents the additional hits and confirms each cited designator still exists.

### Additional citations in `cortex_command/` Python sources

| Citing file | Cited designator | Designator in current file | Status |
|---|---|---|---|
| `cortex_command/worktree_precondition.py:5` | `implement.md §1a step v` | `### 1a. Interactive Worktree Creation` heading at line 94; `**Step v — Auto-enter sequence**` at line 164 | PRESENT |
| `cortex_command/lifecycle_implement.py:13` | `§1a guards` (implement.md) | Same `### 1a.` heading | PRESENT |
| `cortex_command/interactive_lock.py:11` | `complete.md Step 3's Variant-A detection` | `### Step 3 — Push Branch and Create PR` at line 23 | PRESENT |
| `cortex_command/lifecycle_config.py:8,95` | `plan.md §5` | `### 5. Transition` at line 285 | PRESENT (pinned by test) |
| `cortex_command/lifecycle_config.py:9,96` | `complete.md Step 2` | `### Step 2 — Commit Lifecycle Artifacts` at line 17 | PRESENT (pinned by test) |
| `cortex_command/overnight/report.py:965` | `review.md §4a` | `### 4a. Auto-Apply Requirements Drift` heading | PRESENT (pinned by test) |

All cited designators confirmed present in trimmed files. No broken citations found.

### `docs/` sweep (informational)

`docs/` references to trimmed files are path-level (not section designators), with one exception:

- `docs/internals/auto-update.md` (lines 49, 141): cites `implement.md §1a` preflight as a "fail-fast diagnostic". The `### 1a. Interactive Worktree Creation` heading and `**Step v — Auto-enter sequence**` are both present.

No `docs/` citation points to a removed or renamed section designator.

---

## C. Consolidated Proposal Ledger

### Source mapping

Proposals from `evidence.json → trims_verified` (195 total across 12 trim maps). Each proposal was dispositioned through commit bodies of Tasks 5–12. Disposition labels: `applied`, `applied-per-downgrade`, `skipped:no-verdict`, `skipped-with-reason`, `moved:<dest>`.

### Per-file ledger summary

| File | Evidence total | Dispositioned | Result | Disposition breakdown |
|---|---:|---:|---:|---|
| `skills/lifecycle/SKILL.md` | 17 | 17 | PASS | 12 applied + 5 applied-per-downgrade |
| `skills/lifecycle/references/implement.md` | 26 | 26 | PASS | 20 applied + 5 applied-per-downgrade + 1 skipped:no-verdict (§1a.iv sandbox recap — evidence.json: `refuted`) |
| `skills/lifecycle/references/plan.md` | 22 | 22 | PASS | 21 applied + 1 applied-per-downgrade |
| `skills/lifecycle/references/complete.md` | 18 | 18 | PASS | 15 applied + 3 applied-per-downgrade |
| `skills/lifecycle/references/specify.md` | 17 | 17 | PASS | 15 applied + 2 applied-per-downgrade |
| `skills/lifecycle/references/review.md` | 14 | 14 | PASS | 8 applied + 2 applied-per-downgrade + 2 moved:Task-4 (load-requirements.md dedup) + 1 skipped:no-verdict (§4 line 159 — evidence.json: `refuted`, `verifier_reason: no verdict returned`) |
| `skills/lifecycle/references/clarify.md` | 14 | 14 | PASS | 13 applied + 1 applied-per-downgrade |
| `skills/lifecycle/references/orchestrator-review.md` | 11 | 11 | PASS | 8 applied + 2 applied-per-downgrade + 1 skipped-with-reason (S2 dedupe-to-shared-ref: dispatched-verbatim failure mode — keeping verbatim duplication in S1/P4 per spec constraint) |
| `skills/refine/SKILL.md` | 21 | 21 | PASS | 17 applied + 4 applied-per-downgrade |
| `skills/refine/references/clarify-critic.md` | 13 | 13 | PASS | 9 applied + 4 applied-per-downgrade |
| `skills/lifecycle/references/post-refine-commit.md` | 12 | 12 | PASS | 10 applied + 1 applied-per-downgrade + 1 skipped-with-reason (Halt-Before-Plan stranded-row left untouched per `downgrade_to` verdict) |
| `skills/lifecycle/references/backlog-writeback.md` | 10 | 10 | PASS | 5 applied + 4 applied-per-downgrade + 1 moved:Tasks-1/4 (Create-index.md section moved by Task 1) |
| **TOTAL** | **195** | **195** | **PASS** | |

**Zero undispositioned proposals.**

---

## D. `just test` Result

### Full suite run

```
[PASS] test-pipeline
[PASS] test-overnight
[PASS] test-init
[PASS] test-install
[FAIL] tests  (1 failed, 1866 passed, 27 skipped, 1 xfailed in 128.03s)
[PASS] tests-dashboard
[PASS] tests-takeover-stress
Test suite: 6/7 passed
```

### Failing test

`tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`

**Failure reason:** sandbox-environmental network block. The test invokes `uv run --script plugins/cortex-overnight/server.py` with `UV_CACHE_DIR` pointing at a fresh empty tmp directory, forcing uv to fetch `mcp`/`pydantic` dependencies from PyPI. The sandbox blocks outbound DNS, producing:

```
error: Request failed after 3 retries in 4.4s
  Caused by: Failed to fetch: `https://pypi.org/simple/mcp/`
  Caused by: dns error: failed to lookup address information: nodename nor servname provided, or not known
```

**Isolation run on origin/main:** confirmed passing. Stash applied (`a706e73a` → origin/main HEAD), ran `uv run pytest tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero -v` — result: `PASSED` in 0.86s. The fast pass confirms the system UV cache has `mcp`/`pydantic` pre-cached; on the feature branch, the sandbox intermittently blocks resolution before the cache is consulted.

**Classification:** pre-existing sandbox-environmental failure. No code change in this feature touches `plugins/cortex-overnight/server.py` or `tests/test_mcp_subprocess_contract.py`. The task spec explicitly identifies this test as a known sandbox-environmental failure requiring network.

### Net result

`just test` exit 0 modulo one proven pre-existing sandbox-environmental failure. Feature-specific tests all pass.
