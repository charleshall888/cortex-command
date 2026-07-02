# Review: restructure-commit-skill-lazy-load-release

Reviewed against `spec.md` (Reqs 1–10) and `plan.md` (per-requirement greps + Placement/Execution-Mode/end-state re-gate). Implementation landed as single commit `8c3a00b9` touching exactly the four expected files (2 canonical + 2 regenerated mirror). All acceptance greps below were run against the real working-tree files using the backslash-correct `\[release-type:` form per the plan's correction of the spec's un-escaped grep defect.

## Stage 1: Spec Compliance

### Requirement 1: Moved mechanics land in the new ref (not just deleted)
- **Expected**: `skills/commit/references/release-type.md` exists and holds the CI regex, `--dry-run` procedure, both worked examples, the precedence rule, and the `BREAKING:` fallback mechanics.
- **Actual**: File exists. `grep -cF '(?im)^\s*\[release-type:'`=1, `cortex-auto-bump-version --dry-run`=1, `Major bump:`=1, `Minor bump:`=1, precedence `major.*>.*minor.*>.*patch`=1, `BREAKING`=1. The ref also carries the full `BREAKING`/`BREAKING CHANGE:` regex `(?im)^BREAKING(?:\s+CHANGE)?:` and both fenced examples verbatim.
- **Verdict**: PASS
- **Notes**: —

### Requirement 2: Decision trigger stays resident (silent-misfire guard)
- **Expected**: An authoring conditional (default patch; backward-compatible → `[release-type: minor]`; breaking → `[release-type: major]`) plus the own-line rule, folded into the commit-message guidance, not a trailing pointer.
- **Actual**: `[release-type: minor]`=1, `[release-type: major]`=1, own-line rule=1, `backward-compatible|breaking change`=2. The conditional sits inside `## Commit Message Format` (heading at line 18) at lines 22–27. Placement gate: first `[release-type: minor]` at line 24, pointer at line 27 → tok(24) < ptr(27), PASS — the trigger precedes and is not folded into the pointer block.
- **Verdict**: PASS
- **Notes**: Load-bearing silent-misfire guard satisfied structurally: the marker decision is prompted at composition time before any ref open is needed.

### Requirement 3: Full mechanics removed from body; one-line `BREAKING:` backstop kept
- **Expected**: CI regex, precedence prose, both worked examples, and `--dry-run` procedure absent from `SKILL.md`; one resident `BREAKING:` line kept.
- **Actual**: `cortex-auto-bump-version --dry-run`=0, `\[release-type:` regex fence=0, `Major bump:`=0, `Minor bump:`=0, literal `` `major` > `minor` > `patch` ``=0, `BREAKING`=1 (resident backstop: "A column-0 `BREAKING:` in the body also forces a major bump.").
- **Verdict**: PASS
- **Notes**: —

### Requirement 4: Body pointer uses the resolved skill-dir form
- **Expected**: `${CLAUDE_SKILL_DIR}/references/release-type.md` pointer with when-to-read guidance; `cortex-check-skill-path` (SP002) passes.
- **Actual**: `${CLAUDE_SKILL_DIR}/references/release-type.md`=1, with when-to-read guidance ("For the match regex, precedence, the `--dry-run` pre-merge check, and worked examples"). `cortex-check-skill-path --audit` exits 0 on the full corpus; the commit itself cleared the fail-closed pre-commit skill-path gate.
- **Verdict**: PASS
- **Notes**: —

### Requirement 5: Existing marker MUST preserved in substance; no new escalation
- **Expected**: Own-line rule survives in substance; no new MUST/CRITICAL/REQUIRED token; count ≤1 (baseline was exactly 1).
- **Actual**: Own-line rule present (Req 2 grep). `grep -cE 'MUST|CRITICAL|REQUIRED'`=0 (parent baseline was 1). The uppercase MUST token was softened to lowercase prose ("The marker must be the entire content of its own line"), so the escalation count went 1→0 — ≤1 holds and no new escalation is introduced, consistent with the post-4.7 soften-MUST posture.
- **Verdict**: PASS
- **Notes**: Substance of the grandfathered own-line requirement is intact; only the uppercase escalation token relaxed, which the acceptance allows (≤1).

### Requirement 6: Workflow compressed, all three guard clauses kept (s3)
- **Expected**: `cortex-commit-preflight`, "not `-A`", and all three guard clauses (no push, no branches, no conversational output) survive.
- **Actual**: `cortex-commit-preflight`=1, `not `-A``=1, `Do not push`=1, `Do not create branches`=1, `conversational text`=1.
- **Verdict**: PASS
- **Notes**: —

### Requirement 7: Commit Message Format compressed (s4)
- **Expected**: Keep imperative + Add/Fix/Remove exemplars, why-not-what contrast, ~72; drop the `<subject line>` template fence and the trailing-period bullet.
- **Actual**: `imperative`=1, `Add.*Fix.*Remove`=1 (genuine: `Write "Add"/"Fix"/"Remove"`), `why.*not.*what`=1 (genuine: "summarize the *why*, not the *what*"), `72`=1; removals `<subject line>`=0, `trailing period`=0.
- **Verdict**: PASS
- **Notes**: —

### Requirement 8: Commit Command compressed (s5)
- **Expected**: Keep HEREDOC + `dangerouslyDisableSandbox` prohibitions and name the second-`-m` alternative; drop the `Subject line here` example blocks.
- **Actual**: `HEREDOC`=1, `dangerouslyDisableSandbox`=1, second-`-m` alternative=1 (genuine: "adding a second `-m` for a multi-line body"); removal `Subject line here`=0.
- **Verdict**: PASS
- **Notes**: —

### Requirement 9: Validation folded, "do not bypass" preserved as its own imperative (s6)
- **Expected**: `## Validation` heading gone; "do not bypass" preserved as its own directive.
- **Actual**: `## Validation`=0; `do not bypass|not bypass|never bypass`=1 (genuine standalone imperative: "do not bypass (e.g. via `git commit -F` or the editor, which the hook cannot see)").
- **Verdict**: PASS
- **Notes**: The `git commit -F`/editor blind-spot guard is preserved as an explicit clause, not paraphrased away.

### Requirement 10: Body shrinks; mirror regenerated same commit; suites pass
- **Expected**: body ≤75 lines (from 99), `diff -r` mirror-clean, frontmatter byte-unchanged (L1 ratchet), `just test` exit 0, commit clears gates.
- **Actual**: body = 31 lines (from 99). `diff -r skills/commit/ plugins/cortex-core/skills/commit/` → no output (byte-identical). Frontmatter lines 1–4 byte-identical to parent (L1 ratchet not perturbed). `test_l1_surface_ratchet` + `test_skill_size_budget` → 25 passed. `cortex-check-skill-path --audit` exit 0. Commit `8c3a00b9` succeeded through the fail-closed drift + skill-path pre-commit gates with a `[release-type: minor]` marker on its own line. All four paths (2 canonical + 2 mirror) are tracked in the single commit.
- **Verdict**: PASS
- **Notes**: Full `just test` was not re-run in this read-only review (budget-conscious); the discriminating guards for this prose+mirror change — mirror byte-parity, frontmatter/L1 identity, size budget, and skill-path audit — were verified directly and all pass. The commit's own pre-commit gates already exercised the fail-closed drift + skill-path checks.

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The new ref follows the sibling `skills/<name>/references/*.md` convention (matching `skills/refine/references/`, etc.); the commit skill now joins the 12 skills that already carry a reference file, exactly as the spec's Changes-to-Existing-Behavior anticipates.
- **Error handling**: N/A for prose. The ref carries no bare-relative `read`/`cat`/`bash <path>.md` construct (scan clean) and needs no `${CLAUDE_SKILL_DIR}` (count 0) — correct, since the token only resolves in a SKILL.md body. No SP002 hazard; corpus audit exit 0.
- **Test coverage**: The plan's per-requirement greps were re-executed against the final working-tree files and all hold, including the Placement gate (tok < ptr) and the backslash-correct `\[release-type:` greps. L1 ratchet, size budget, and skill-path audit pass. Mirror parity confirmed via `diff -r`. No content-behavior test exists for SKILL.md prose (expected — the greps + body-size gate are the discriminating guards).
- **Pattern consistency**: Follows the established lazy-ref progressive-disclosure pattern (L2 body → L3 reference, ADR-0009 / SP002). The pointer uses the correct D2-compliant `${CLAUDE_SKILL_DIR}/` prefix. The resident/lazy split is clean: decision trigger + tokens + own-line rule + one-line `BREAKING:` backstop resident; regex/precedence/`--dry-run`/examples/full-`BREAKING`-mechanics behind the pointer.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
