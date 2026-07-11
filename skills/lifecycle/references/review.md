# Review Phase

Two-stage review: spec compliance first, then code quality. Complex tier only. The reviewer must NOT modify any files.

## Protocol

### 1. Gather Review Inputs

Read `cortex/lifecycle/{feature}/spec.md` (requirements) and `plan.md` (verification strategy), and identify the files changed during implementation (git log since the lifecycle started, or plan.md's file lists). Load requirements per the shared protocol (`${CLAUDE_SKILL_DIR}/references/load-requirements.md`): run `cortex-load-requirements --feature {feature}`, read every listed non-skipped path, and record the printed path list for the reviewer prompt. On the verb's no-match fallback note, the drift check covers project.md only.

### 2. Launch Review Sub-Task

**Model** — resolve at dispatch, never hardcode:

```bash
model=$(cortex-resolve-model --role review --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
```

Pass `$model` to the reviewer sub-task. On nonzero exit, halt and escalate rather than guessing. Dispatch the sub-task read-only with the prompt below, substituting `{spec_path}` with the absolute spec path.

### Reviewer Prompt Template

```
You are reviewing the {feature} implementation against its specification. Read-only — do NOT modify any source file.

## Specification
Read `{spec_path}`.

## Project Requirements
{the path list cortex-load-requirements printed in §1, one per line; if the verb emitted its no-match fallback note, relay that instead}

## Changed Files
{files modified during implementation}

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

### 3. Review Artifact Format

Downstream parsing depends only on the Verdict JSON block (exact field names and values from §2).

### 4. Process Verdict

After the sub-task completes and review.md is on disk: if it lacks a `## Requirements Drift` section (the reviewer ran out of context), re-dispatch once — "review.md is missing the ## Requirements Drift section; read the existing file and append it in the correct format, modifying nothing else." Still absent after one retry → escalate.

Register the artifact: `cortex-lifecycle-register-artifact --feature {feature} --artifact review`.

Read the Verdict JSON's `verdict`, `cycle`, and `requirements_drift` fields — the discriminants §4a's drift loop and §5's verb call route on. The verb resolves verdict×cycle to the outcome:

| Verdict | Cycle | Outcome |
|---------|-------|---------|
| APPROVED | any | Proceed to Complete |
| CHANGES_REQUESTED | 1 | Re-enter Implement for flagged tasks with reviewer feedback |
| CHANGES_REQUESTED | ≥2 | Escalate — present the analysis, ask for direction |
| REJECTED | any | Escalate immediately — recommend revisiting plan or spec |

The `≥2` row caps rework: cycle 2 and any later cycle escalates. §5 hands verdict/cycle/drift to the verb, which records the routing — do not emit it here.

### 4a. Auto-Apply Requirements Drift

If `requirements_drift` is `"detected"`, run this judgment loop BEFORE the §5 verb call:

1. **Parse** the `## Suggested Requirements Update` section (`File` / `Section` / `Content`) from review.md.
2. **Apply**: append `Content` at the end of the named `Section` in the target file, then report to the user what changed (file, section, first line of the appended content).

Section missing or unparseable → re-dispatch the reviewer to append it in the §2 format without touching other sections (cap 2 retries). Still failing after the cap → the drift-apply has **breached**: do **not** block verdict processing. Carry `--breach --retries 2` into §5's verb call so the breach is recorded (positioned between the verdict record and the transition) — it surfaces in the morning report so the gap is visible rather than silent, without applying the unparseable update.

When `requirements_drift` is `"none"`, or the apply succeeded, carry no breach.

### 5. Transition

Hand the verdict, its cycle, the drift observation, and any §4a breach to the review-verdict verb — it owns this arm's exact ordered emissions (the `review_verdict` record, the `drift_protocol_breach` row when `--breach`, then the routed `review→{complete|implement-rework|escalated}` transition) and their idempotent replay, so you route on the returned `state`, you do not re-derive it:

```bash
cortex-lifecycle-review-verdict --feature <name> --verdict <APPROVED|CHANGES_REQUESTED|REJECTED> --cycle <N> --drift <none|detected> [--breach --retries <N>]
```

Add `--breach --retries <N>` only when §4a's drift-apply exhausted its retries. Act on the returned `state`:

- **`approved`** (APPROVED, any cycle) → Complete: announce briefly and auto-advance.
- **`rework`** (CHANGES_REQUESTED cycle 1) → Implement: re-enter for the flagged tasks with reviewer feedback; announce briefly and continue.
- **`escalated`** (cycle ≥2 or REJECTED) → present the findings and await direction; do not auto-advance.
- **`error`** → surface the verb's `message` and halt without transitioning.

**Command not found** (`cortex-lifecycle-review-verdict` not on `PATH`) → halt and instruct the operator to install/upgrade the cortex-command CLI, then re-invoke. Do NOT record the verdict or transition by hand. <!-- Halt-arm convention: this arm names ONLY the verb and the install remedy — never a raw event-emission surface, which would defeat the per-file zero-sweep (tests/test_lifecycle_event_roundtrip.py) that keeps this cluster's emissions inside the verb. -->

## Constraints

- Flag minor code-quality issues as PARTIAL with notes — minor issues compound.
- If uncertain about requirements drift, log `detected` with a note — a false positive auto-applies a small update; a false negative silently hides drift.
