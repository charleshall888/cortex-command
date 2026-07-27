# Review Phase

Two-stage review: spec compliance, then code quality. Complex tier only. The reviewer must NOT modify any files.

## 1. Gather inputs

Read `spec.md` and `plan.md`, and identify the files changed during implementation (git log since the lifecycle started, or plan.md's file lists).

Load requirements: `cortex-load-requirements --feature {feature}`, read every listed non-skipped path, record the printed list for the reviewer prompt. Its no-match note (`no area docs matched`) is a **warning, not a routine fallback** — the drift check narrows to project.md only, leaving any area doc governing this feature unassessed. Surface it before dispatching; the usual cause is an index.md that never received its backlog tags, repaired by re-running `cortex-lifecycle-enter` with the served backlog filename.

**Test baseline** — run the configured `test-command` once, capturing a pass/fail summary and a log path, never the full transcript. If commits land after the baseline, re-run once and replace it. The reviewer and anything it spawns consume this baseline and never re-run the suite.

## 2. Dispatch

```bash
model=$(cortex-resolve-model --role review --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality --raw)")
```

On nonzero exit, halt and escalate. Dispatch read-only with the prompt below, substituting the absolute spec path.

**Single-writer rule** — only the reviewer role writes `review.md`: this sub-task plus §3's missing-drift re-dispatch and §3a's cap-2 re-dispatches. Any sub-agent the reviewer spawns is read-only and returns findings as a message envelope.

```
You are reviewing the {feature} implementation against its specification. Read-only — do NOT modify any source file.

## Specification
Read `{spec_path}`.

## Project Requirements
{the path list cortex-load-requirements printed in §1, one per line; if it emitted its no-match note, relay that instead}

## Changed Files
{files modified during implementation}

## Test Baseline
{the §1 pass/fail summary + log path — never the full transcript; do not re-run the suite}

## Stage 1 — Spec Compliance
Per requirement: read the relevant source, check acceptance criteria, rate PASS / FAIL / PARTIAL. Any FAIL → skip Stage 2 and write the verdict.

## Stage 2 — Code Quality (only when no FAIL)
Assess naming consistency, error handling, test coverage (were the plan's verification steps executed?), and pattern consistency with the project.

## Requirements Drift (observation only — does not affect the verdict)
Compare the implementation to the project requirements above: `none` if it matches all and adds no unreflected behavior; `detected` if it introduces or changes behavior the requirements don't capture.

## Write review.md
Write to `cortex/lifecycle/{feature}/review.md`, including a `## Requirements Drift` section:

**State**: none | detected
**Findings**: one bullet per drifted item, or "None"
**Update needed**: requirements file path, or "None"

When State is `detected`, add a `## Suggested Requirements Update` section (omit when `none`; one per drifted file):

**File**: e.g. cortex/requirements/project.md
**Section**: existing heading, e.g. "## Quality Attributes"
**Content**: exact 1-3 line markdown to append, as it should appear (not a description)

End with a Verdict — a JSON object using exactly these fields (not "overall"/"result"/"status"; not the Stage-1 "PASS"/"FAIL" values):
{"verdict": "APPROVED"|"CHANGES_REQUESTED"|"REJECTED", "cycle": <int>, "issues": [<strings>], "requirements_drift": "none"|"detected"}
```

Flag minor code-quality issues as PARTIAL with notes — they compound. If uncertain about drift, log `detected` with a note: a false positive auto-applies a small update, a false negative silently hides drift.

## 3. Process the verdict

Downstream parsing depends only on the Verdict JSON block. If review.md lacks `## Requirements Drift` (the reviewer ran out of context), re-dispatch once — "review.md is missing the ## Requirements Drift section; read the existing file and append it in the correct format, modifying nothing else." Still absent → escalate.

Register it: `cortex-lifecycle-register-artifact --feature {feature} --artifact review`.

Read `verdict`, `cycle`, and `requirements_drift` — the discriminants §3a and §4 route on. The verb resolves verdict × cycle: APPROVED → Complete; CHANGES_REQUESTED cycle 1 → re-enter Implement for the flagged tasks; CHANGES_REQUESTED cycle ≥2 → escalate; REJECTED → escalate immediately, recommending a return to plan or spec. Cycle 2 and later escalates — that caps rework.

## 3a. Auto-apply requirements drift

When drift is `"detected"`, before §4: parse `## Suggested Requirements Update` (`File` / `Section` / `Content`), append `Content` at the end of the named `Section` in the target file, and report what changed.

Section missing or unparseable → re-dispatch the reviewer to append it in the §2 format without touching anything else, cap 2 retries. Still failing → the drift-apply has **breached**: do **not** block verdict processing. Carry `--breach --retries 2` into §4 so it surfaces in the morning report rather than vanishing, without applying the unparseable update.

## 4. Transition

```bash
cortex-lifecycle-advance review-verdict --feature <name> --verdict <APPROVED|CHANGES_REQUESTED|REJECTED> --cycle <N> --drift <none|detected> [--breach --retries <N>]
```

The verb owns this arm's ordered emissions (verdict record, breach row when `--breach`, then the routed transition) and their idempotent replay. Add `--breach` only when §3a exhausted its retries. Route on the returned `state` (shared `error`/`refused`/command-not-found arms: SKILL.md § Advance-verb routing):

- **`approved`** → Complete: announce briefly and auto-advance.
- **`rework`** → Implement: re-enter for the flagged tasks with reviewer feedback.
- **`escalated`** → present the findings and await direction; do not auto-advance.
