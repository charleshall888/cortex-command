# Review Phase

Two-stage review: spec compliance, then code quality. Stage 1 runs at complex tier, or any tier once criticality is `high`/`critical`; Stage 2 is complex-only. The reviewer must NOT modify any files.

## 1. Gather inputs

Read `spec.md` and `plan.md`, and identify the files changed during implementation (git log since the lifecycle started, or plan.md's file lists).

Load requirements: `cortex-load-requirements --feature {feature}`, read every listed non-skipped path, record the printed list for the reviewer prompt. Its no-match note (`no area docs matched`) is a **warning, not a routine fallback** — the drift check narrows to project.md, leaving any area doc governing this feature unassessed. Surface it before dispatching; the usual cause is an index.md that never received its backlog tags, repaired by re-running `cortex-lifecycle-enter` with the served backlog filename.

**Test baseline** — run the configured `test-command` once, capturing a pass/fail summary and a log path, never the full transcript. If commits land after the baseline, re-run once and replace it. The reviewer and anything it spawns consume this baseline and never re-run the suite. On a rework the §2 brief states its own reuse/re-run decision — refresh the baseline before dispatch when it says re-run.

## 2. Dispatch

```bash
cortex-lifecycle-review-brief --feature {feature}
```

It archives the prior cycle's `review.md`, selects full or rework-scoped mode, records the dispatch baseline, and emits the brief — hand it to the reviewer verbatim. Non-zero exit or no output → run a **full** review against the Verdict contract below and report the degradation; never dispatch a scoped review on a missing or empty checklist.

Dispatch one read-only reviewer, choosing its model yourself. Hand it the brief, the absolute spec path to read, §1's requirements path list (or its no-match note), the changed-file list, and §1's test baseline.

**Single-writer rule** — only the reviewer role writes `review.md`: this sub-task plus §3's missing-drift re-dispatch and §3a's cap-2 re-dispatches. Any sub-agent the reviewer spawns is read-only and returns findings as a message envelope.

**Verdict contract** — the brief prescribes the rest of the output shape, but this block is prose because §3 parses it. Hand it along with the brief; the review ends with it:

```
{"verdict": "APPROVED"|"CHANGES_REQUESTED"|"REJECTED", "cycle": <int>, "issues": [<strings>], "requirements_drift": "none"|"detected"}
```

## 3. Process the verdict

Downstream parsing depends only on the Verdict JSON block. If review.md lacks `## Requirements Drift` (the reviewer ran out of context), re-dispatch once — "review.md is missing the ## Requirements Drift section; read the existing file and append it in the correct format, modifying nothing else." Still absent → escalate.

Register it: `cortex-lifecycle-register-artifact --feature {feature} --artifact review`.

Read `verdict`, `cycle`, and `requirements_drift` — the discriminants §3a and §4 route on. The verb resolves verdict × cycle: APPROVED → Complete; CHANGES_REQUESTED cycle 1 → re-enter Implement for the flagged tasks; CHANGES_REQUESTED cycle ≥2 → escalate (the rework cap); REJECTED → escalate immediately, recommending a return to plan or spec.

## 3a. Auto-apply requirements drift

When drift is `"detected"`, before §4: parse `## Suggested Requirements Update` (`File` / `Section` / `Content`), append `Content` at the end of the named `Section` in the target file, and report what changed.

Section missing or unparseable → re-dispatch the reviewer to append it in the brief's format without touching anything else, cap 2 retries. Still failing → the drift-apply has **breached**: do **not** block verdict processing. Carry `--breach --retries 2` into §4 so it surfaces in the morning report rather than vanishing, without applying the unparseable update.

## 4. Transition

```bash
cortex-lifecycle-advance review-verdict --feature <name> --verdict <APPROVED|CHANGES_REQUESTED|REJECTED> --cycle <N> --drift <none|detected> [--breach --retries <N>]
```

The verb owns this arm's ordered emissions (verdict record, breach row when `--breach`, then the routed transition) and their idempotent replay. Add `--breach` only when §3a exhausted its retries. Route on the returned `state` per SKILL.md § Advance-verb routing:

- **`approved`** → Complete: announce briefly and auto-advance.
- **`rework`** → Implement: re-enter for the flagged tasks with reviewer feedback.
- **`escalated`** → present the findings and await direction; do not auto-advance.
