# Review: auto-derive-lifecycle-slug-from-prose-style-invocation-args

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```

## Stage 1: Spec Compliance

### R1 — Prose branch in `skills/lifecycle/SKILL.md` Step 1: **PASS**

The new paragraph at `skills/lifecycle/SKILL.md:47` lands between the existing first-word/empty-arguments parse rule (line 45) and the "Determine the feature name" sentence (line 49). It:

- Names the invalid-slug trigger condition with the canonical regex `^[a-z0-9]+(-[a-z0-9]+)*$`.
- Instructs the agent to derive a 3–6 word kebab-case slug summarizing the prose's intent.
- Prescribes announcing the chosen slug as `cortex/lifecycle/{slug}/` is created.
- Prescribes using the derived slug as `{feature}` for the rest of Step 1 and Step 2.
- Handles the edge case where a derived slug collides with an existing directory (routes to Step 2 resume rather than disambiguating).

Acceptance grep checks:

- `awk '/^## Step 1:/,/^## Step 2:/' skills/lifecycle/SKILL.md | grep -ci 'derive.*slug\|prose-style\|not a valid.*slug'` → `1` (≥1 required).
- `sed -n '47p' skills/lifecycle/SKILL.md | grep -ciE '\b(MUST|NEVER|REQUIRED|CRITICAL)\b'` → `0` (required).

### R2 — Prose branch in `skills/refine/SKILL.md` Step 1 exit-3 path: **PASS**

The exit-3 bullet at `skills/refine/SKILL.md:39` is augmented with a single trailing sentence that:

- Names the prose vs. valid-kebab-case trigger condition with the same canonical regex.
- Cross-points to `../lifecycle/SKILL.md` Step 1 rather than duplicating the full rule (satisfies the "reference by inline pointer" requirement).
- Restates the three load-bearing actions (derive, announce, proceed) tersely.
- Re-states the no-confirmation rule inline (no reliance on the cross-pointer alone for R3 surface).

Acceptance grep checks:

- `awk '/Exit 3.*no match/,/Exit 64/' skills/refine/SKILL.md | grep -ci 'derive.*slug\|prose'` → `1` (≥1 required).
- `sed -n '39p' skills/refine/SKILL.md | grep -ciE '\b(MUST|NEVER|REQUIRED|CRITICAL)\b'` → `0` (required).

### R3 — No-confirmation rule: **PASS**

Both surfaces contain the exact phrase "Do not ask the user to confirm the derived slug":

- `awk '/^## Step 1:/,/^## Step 2:/' skills/lifecycle/SKILL.md | grep -ci 'do not ask\|without.*confirm\|do not.*confirm'` → `1` (≥1 required).
- `awk '/Exit 3.*no match/,/Exit 64/' skills/refine/SKILL.md | grep -ci 'do not ask\|without.*confirm\|do not.*confirm'` → `1` (≥1 required).

The lifecycle paragraph additionally specifies the inline-correction path ("let the user correct via re-invocation"), which directly addresses the failure mode the ticket targets — gratuitous round-trip confirmation.

## Stage 2: Code Quality

- **Prose clarity**: The new lifecycle paragraph reads cleanly within Step 1. It opens with the conditional anchor ("When `$ARGUMENTS` is non-empty but its first word is prose...") matching the existing "When `$ARGUMENTS` is empty" pattern already in the same step (line 67). The refine sentence is a natural extension of the existing exit-3 bullet rather than a separate paragraph, which preserves the bullet's single-thought structure.
- **Soft positive-routing compliance**: No MUST/NEVER/REQUIRED/CRITICAL appears in either new prose block. The phrase "Do not ask" is a negative directive without escalation vocabulary — and R3 explicitly accepts "do not ask the user to confirm" as the canonical phrasing for the no-confirmation rule, so this is in-policy.
- **Pattern consistency**: The lifecycle branch's "When X, derive Y, announce Z, use it as W. Do not ask..." cadence mirrors the conditional-branch templates already in Step 1 ("When `$ARGUMENTS` is non-empty, invoke..." at line 51; "When `$ARGUMENTS` is empty, skip..." at line 67). The refine bullet preserves the existing exit-bullet pattern (Exit code → action → branch detail).
- **Cross-pointer integrity (refine → lifecycle)**: The refine sentence cites `../lifecycle/SKILL.md` Step 1; the full prescription lives at `skills/lifecycle/SKILL.md:47`, which is inside Step 1. Pointer is accurate. The refine sentence includes the load-bearing actions inline so a reader who does not follow the pointer still gets the correct behavior — the pointer adds detail, not load-bearing semantics.
- **Mirror parity**: `diff skills/lifecycle/SKILL.md plugins/cortex-core/skills/lifecycle/SKILL.md` and `diff skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` both return empty — the mirrors are byte-for-byte identical to the canonical sources.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None
