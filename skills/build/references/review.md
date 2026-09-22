# Review Phase

Two stages: spec compliance, then code quality. Stage 1 runs at complex tier, or at any tier when criticality is `high`/`critical`. Stage 2 is complex-only. The reviewer changes no files.

## 1. Gather inputs

Read `spec.md` and `plan.md`. List the files changed during implementation (git log since the lifecycle started, or plan.md's file lists).

Run `cortex-load-requirements --feature {feature}`. Read every listed non-skipped path and keep the list for the reviewer. Its stderr `COVERAGE:` marker is one of `loaded`, `doc-missing`, `unmapped`, `no-area`. Anything but `loaded` is a **warning**: the drift check covers only project.md, so no area doc is checked. Tell the user before dispatch and pass it to the reviewer.

**Test baseline** — run the configured `test-command` once. Keep a pass/fail summary and a log path, never the full output. If commits land after the baseline, re-run once and replace it. The reviewer and any agent it starts use this baseline and never re-run the suite. On rework, the §2 brief says whether to reuse or re-run.

## 2. Dispatch

```bash
cortex-lifecycle-review-brief --feature {feature}
```

It archives the last cycle's `review.md`, picks full or rework-only mode, records the dispatch baseline, and prints the brief. Give it to the reviewer word for word. Non-zero exit or empty output → run a **full** review against the Verdict contract and report the problem. Never run a rework-only review without its checklist.

Dispatch one read-only reviewer (model your call) with the brief, the absolute spec path, §1's requirements path list (or its no-match note), the changed-file list, and the test baseline.

**Single-writer rule** — only the reviewer role writes `review.md`: this sub-task, its resumption, and the §3/§3a re-dispatches. Any agent the reviewer starts is read-only and returns findings as a message.

**Verdict contract** — the brief sets the rest of the review's shape. It is here because §3 parses it. Hand it over with the brief; the review ends with it:

```json
{"verdict": "APPROVED"|"CHANGES_REQUESTED"|"REJECTED", "cycle": <int>, "issues": [<strings>], "requirements_drift": "none"|"detected"}
```

## 3. Process the verdict

Parsing needs only the Verdict JSON. No review.md → resume the original reviewer and wait for it. Still nothing → re-dispatch under §3a's cap, then escalate. Missing `## Requirements Drift` (the reviewer ran out of context) → re-dispatch once: "review.md is missing the ## Requirements Drift section; append it in the correct format, modifying nothing else." Still missing → escalate.

Read `verdict`, `cycle`, `requirements_drift`. The §4 command decides the outcome: APPROVED → Complete. CHANGES_REQUESTED cycle 1 → Implement again for the flagged tasks. CHANGES_REQUESTED cycle ≥2 → escalate (rework cap). REJECTED → escalate; recommend a return to plan or spec.

## 3a. Auto-apply requirements drift

`"detected"` → before §4, run `cortex-lifecycle-apply-drift --feature <name>` and report its `entries`. Any state but `applied` → re-dispatch the reviewer with the command's `message` to fix the section in the brief's format, at most 2 retries. Still failing → the drift-apply has **breached**. Do not block the verdict; add `--breach --retries 2` in §4 so the morning report shows it.

## 4. Transition

```bash
cortex-lifecycle-advance review-verdict --feature <name> --verdict <APPROVED|CHANGES_REQUESTED|REJECTED> --cycle <N> --drift <none|detected> [--breach --retries <N>]
```

The command logs this step's events in order and is safe to run again. Add `--breach` only when §3a used up its retries. Route per SKILL.md § Advance-verb routing: `approved` → Complete, announce and continue; `rework` → Implement for the flagged tasks with the reviewer's feedback; `escalated` → show the findings and wait for direction.
