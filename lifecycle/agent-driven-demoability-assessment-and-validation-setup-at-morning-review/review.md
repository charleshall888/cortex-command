# Review: Agent-driven demoability assessment and validation setup at morning review

## Stage 1: Spec Compliance

### R1 — `demo-command` field added to `lifecycle.config.md` template — PASS
- `grep -c '^# demo-command:' skills/lifecycle/assets/lifecycle.config.md` = 1
- `grep -c -- '--play' skills/lifecycle/assets/lifecycle.config.md` = 0
- Example text uses `godot res://main.tscn` (correct positional form).

### R2 — New `## Section 2a — Demo Setup` in walkthrough.md — PASS
- `grep -c '^## Section 2a — Demo Setup$'` = 1
- `grep -c 'proceed immediately to Section 2a'` = 1 (line 76)
- `grep -c 'Run immediately after Section 2a'` = 1 (line 161)
- Section ordering: Section 2 at line 35, Section 2a at line 82, Section 2b at line 159 — a<b<c holds.

### R3 — Section 2a guard: skip when `demo-command` is not configured — PASS
- All six parsing-rule greps ≥1 (`comment line`=1, `after the first`=1, `leading and trailing whitespace`=1, `control character`=4, `treat the field as unset`=1, `inline.*comments`=1).
- All four guard-condition greps ≥1 (`lifecycle.config.md.*missing`=2, `demo-command.*absent`=2, `value.*empty`=3, `control character`=4).
- Parser uses `sed -n 's/^[[:space:]]*demo-command:[[:space:]]*//p'` (correct first-colon-safe form), explicitly warning against `awk -F:` split.

### R4 — Section 2a guard: skip on remote sessions — PASS
- `grep -c 'SSH_CONNECTION'` = 2 (guard block + edge-case row).

### R5 — Section 2a guard: skip when overnight branch is missing — PASS
- `grep -c 'rev-parse --verify'` = 2.
- Guard block references `jq -r '.integration_branch'` pattern consistent with Section 6.

### R6 — Exactly one yes/no offer — PASS
- Smoke test `awk ... | grep -c '?'` within Section 2a returns 1 (cap was ≤2).
- Offer text matches suggested form including `{integration_branch}` and path preview.

### R7 — Worktree creation on accept — PASS
- `grep -c 'realpath'` ≥1
- `grep -c 'core.hooksPath=/dev/null'` = 2
- `grep -c 'git worktree add'` = 3
- `grep -c 'NOT use --force'` = 1
- Single-command invocation (no shell chaining), no `--force`, no `git -C`.

### R8 — Launch command printed on success — PASS
- "Demo worktree created at:" appears once in Section 2a.
- "git worktree remove" appears 4 times (Section 2a printed template + Section 6 existing worktree removal + Section 6 reminder + edge case) — meets ≥2.

### R9 — Immediate auto-advance — PASS
- `grep -c 'Do not wait'` ≥1. Explicit text "After this section completes (skipped, declined, or accepted), proceed immediately to Section 2b. Do not wait for the user to report demo completion."

### R10 — Agent MUST NOT execute `demo-command` itself — PASS
- `grep -c 'MUST NOT execute the demo-command'` = 1. Security-boundary subsection present.

### R11 — Section 6 step 5 cleanup reminder — PASS
- `grep -c 'If you spun up a demo earlier'` = 1.
- Reminder is placed inside the success path after the existing worktree-removal report (line 462).

### R12 — Step 0 garbage sweep for stale demo worktrees — PASS
- All six SKILL.md greps pass: `Garbage sweep`=1, `git worktree list --porcelain`=1, `demo-overnight-`=2, `git worktree remove`=1, `no .--force`=2, `git worktree prune`=1.
- Regex construction documented (ERE, shell-variable substitution), ordering of steps 4 and 5 explicitly marked load-bearing, `--force` omission documented.

### R13 — SKILL.md Step 3 outline mentions Demo Setup — PASS
- Line 100 Completed Features, line 101 Demo Setup, line 102 Lifecycle Advancement — correct insertion point.

### R14 — Edge cases table updated — PASS
- All 14 rows present (lines 536–549). Every spec grep returns ≥1 (or ≥2 for "Stale demo worktree from prior session").

## Stage 2: Code Quality

- **Naming**: `demo-command` mirrors existing `test-command` convention; `Section 2a` label follows existing `2b`/`2c`/`6a` conditional-subsection pattern.
- **Error handling**: non-zero worktree-add exits print stderr and advance (graceful partial failure). Sweep failures are non-fatal and continue. `realpath` failure handled for the sweep.
- **Pattern consistency**: jq-with-fallback pattern reused from Section 6 step 1; guard-clause "Skip this section entirely if …" matches Sections 2b/2c/6a conventions; `${CLAUDE_SKILL_DIR}` / skill-asset layout untouched; hooks path neutralization via `git -c core.hooksPath=/dev/null` documented with rationale.
- **Security**: R3 control-character rejection + R7 hook neutralization + R10 explicit "agent does not execute" forms coherent defense-in-depth; NR14 explicitly declines a warning toast to avoid habituation.
- **Sandbox constraints**: single `git worktree add` invocation (no compound chaining); no `git -C`; skill uses `git -c` (config flag) which is distinct and authorized.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
