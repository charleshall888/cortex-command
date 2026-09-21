# Review Phase

Two stages: spec compliance, then code quality. Stage 1 runs at complex tier, or any tier once criticality is `high`/`critical`; Stage 2 is complex-only. The reviewer modifies no files.

## 1. Gather inputs

Read `spec.md` and `plan.md`; identify the files changed during implementation (git log since the lifecycle started, or plan.md's file lists).

`cortex-load-requirements --feature {feature}` — read every listed non-skipped path and record the list for the reviewer. Its stderr `COVERAGE:` marker (`loaded`, `doc-missing`, `unmapped`, `no-area`) is a **warning** when not `loaded`: the drift check narrows to project.md, leaving any area doc unassessed. Hand it to the reviewer and surface it before dispatch.

**Test baseline** — run the configured `test-command` once; capture a pass/fail summary and a log path, never the full transcript. Commits after the baseline → re-run once and replace it. The reviewer and anything it spawns consume this baseline and never re-run the suite. On rework the §2 brief states its own reuse/re-run decision.

## 2. Dispatch

```bash
cortex-lifecycle-review-brief --feature {feature}
```

It archives the prior cycle's `review.md`, selects full or rework-scoped mode, records the dispatch baseline, and emits the brief — hand it to the reviewer verbatim. Non-zero exit or empty output → run a **full** review against the Verdict contract and report the degradation; never dispatch a scoped review on a missing checklist.

Dispatch one read-only reviewer (model your call) with the brief, the absolute spec path, §1's requirements path list (or its no-match note), the changed-file list, and the test baseline.

**Single-writer rule** — only the reviewer role writes `review.md`: this sub-task, its resumption, and §3/§3a re-dispatches. Any sub-agent the reviewer spawns is read-only and returns findings as a message.

**Verdict contract** — the brief prescribes the rest of the shape; this block is prose because §3 parses it. Hand it with the brief; the review ends with it:

```json
{"verdict": "APPROVED"|"CHANGES_REQUESTED"|"REJECTED", "cycle": <int>, "issues": [<strings>], "requirements_drift": "none"|"detected"}
```

## 3. Process the verdict

Parsing depends only on the Verdict JSON. No review.md → resume the original reviewer and await it; still nothing → re-dispatch under §3a's cap, then escalate. Missing `## Requirements Drift` (reviewer ran out of context) → re-dispatch once: "review.md is missing the ## Requirements Drift section; append it in the correct format, modifying nothing else." Still absent → escalate.

Read `verdict`, `cycle`, `requirements_drift`. The verb resolves verdict × cycle: APPROVED → Complete; CHANGES_REQUESTED cycle 1 → re-enter Implement for the flagged tasks; CHANGES_REQUESTED cycle ≥2 → escalate (rework cap); REJECTED → escalate, recommending a return to plan or spec.

## 3a. Auto-apply requirements drift

`"detected"` → before §4, run `cortex-lifecycle-apply-drift --feature <name>` and report its `entries`. Any state but `applied` → re-dispatch the reviewer with the verb's `message` to fix the section in the brief's format, cap 2 retries. Still failing → the drift-apply has **breached**: do not block verdict processing; carry `--breach --retries 2` into §4 so it surfaces in the morning report.

## 4. Transition

```bash
cortex-lifecycle-advance review-verdict --feature <name> --verdict <APPROVED|CHANGES_REQUESTED|REJECTED> --cycle <N> --drift <none|detected> [--breach --retries <N>]
```

The verb owns this arm's ordered emissions and replay; add `--breach` only when §3a exhausted its retries. Route per SKILL.md § Advance-verb routing: `approved` → Complete, announce and auto-advance; `rework` → Implement for the flagged tasks with reviewer feedback; `escalated` → present the findings and await direction.
