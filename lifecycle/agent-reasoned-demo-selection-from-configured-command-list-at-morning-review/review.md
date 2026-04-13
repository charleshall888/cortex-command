# Review: agent-reasoned-demo-selection-from-configured-command-list-at-morning-review

## Stage 1: Spec Compliance

### Requirement R1: demo-commands list in lifecycle.config.md
- **Expected**: Commented `demo-commands:` block inserted after `# demo-command:` line with exactly the two-entry example (Godot gameplay, FastAPI dashboard).
- **Actual**: Lines 5-9 of `skills/lifecycle/assets/lifecycle.config.md` contain the block verbatim as specified, directly after `# demo-command:` (line 4).
- **Verdict**: PASS
- **Notes**: Acceptance greps: `^# demo-commands:` = 1; `label:` = 2; `command:` = 4 (counts the `# demo-command:`, `# test-command:`, and two `command:` entries — comfortably ≥ 2).

### Requirement R2: Guard 1 routing between demo-commands: list and demo-command: single-string
- **Expected**: Guard 1 routes between the two schemas; all 7 parsing rules present as greppable phrases.
- **Actual**: `skills/morning-review/references/walkthrough.md` Guard 1 (lines 86-123) describes routing: `demo-commands:` tried first, falls back to `demo-command:` single-string, else silent skip. All 7 parsing rules are present as explicitly numbered list items (lines 92-100), including the "after the first" colon extraction rule, control-character rejection, empty-value rejection, block-boundary rule ("stopping at the first non-indented, non-blank line"), and do-not-strip-inline-`#` rule.
- **Verdict**: PASS
- **Notes**: All 7 acceptance greps pass: `demo-commands:` = 19; `first.*colon\|after the first` = 2; `control character` = 6; `inline.*comments\|inline.*#` = 2; `non-indented\|indented.*entries\|stop.*non-indented` = 1; `empty.*command\|command.*empty\|whitespace-only` = 5; `no valid entries\|fall.*through.*demo-command\|fall.*back.*demo-command` = 5.

### Requirement R3: Guard 3 extended with zero-merged-features check (demo-commands: path only)
- **Expected**: Guard 3 extends with check 3 (no merged features → skip), demo-commands: path only. Check order 1→2→3.
- **Actual**: Lines 129-133 extend Guard 3. Checks 1 (state file missing / branch absent) and 2 (`git rev-parse --verify` non-zero) apply to both paths. Check 3 (zero merged features) explicitly gated to `demo-commands:` list path only ("this third check does NOT apply to the `demo-command:` single-string path"). Missing `features` key treated as zero merged.
- **Verdict**: PASS
- **Notes**: Acceptance: `"status".*merged` = 3 hits; `zero.*features\|no.*merged\|no completed features` = 3 hits.

### Requirement R4: Agent reasons from Section 2 context with absolute suppression
- **Expected**: Agent Reasoning section after Guard 3; uses "Key files changed" context; no additional git commands; absolute suppression when none relevant.
- **Actual**: Lines 135-144 comprise the Agent Reasoning section, positioned after Guard 3 and before Demo offer. Explicitly states no additional git commands ("No additional git commands are run for this step"; "Do NOT re-read `git log`, `git diff`, or any file tree — everything needed is already in context"). Uses the Section 2 "Key files changed" data. The "none relevant" branch (§4) explicitly states suppression is absolute: "do NOT fall back to the `demo-command:` single-string path even if that field is also configured".
- **Verdict**: PASS
- **Notes**: Acceptance: `Key files changed\|key files changed` = 5 (Section 2 line 67 "Key files changed" source; Section 2a Agent Reasoning lines 141, 142); `no additional git\|already in context\|already processed` = 5.

### Requirement R5: Demo offer with {selected-label} and {selected-command}
- **Expected**: Demo offer includes `{selected-label}` and `{selected-command}` for demo-commands: path; single-string path offer preserved unchanged.
- **Actual**: Lines 150-156 show the demo-commands: list path variant with both placeholders. Lines 158-162 preserve the unchanged single-string path offer ("Spin up a demo worktree of `{integration_branch}` at `$TMPDIR/demo-{session_id}-{timestamp}` and print the launch command? [y / n]"). Explicit "Use this variant only if..." conditional framing precedes each.
- **Verdict**: PASS
- **Notes**: Acceptance: `{selected-label}` = 5; `{selected-command}` = 5.

### Requirement R6: Print template for demo-commands: path
- **Expected**: Demo-commands: path print template uses `To start the demo ({selected-label})` and `{selected-command}`; after Worktree creation section.
- **Actual**: Lines 199-211 show the demo-commands: list path print variant with the exact header `To start the demo ({selected-label}), run this in a separate terminal or shell:` and `{selected-command}` on the following line. The legacy single-string variant (lines 185-197) is preserved with `{demo-command}`. Print template section follows Worktree creation (lines 168-179).
- **Verdict**: PASS
- **Notes**: Acceptance: `To start the demo \(\{selected-label\}\)` = 1; `{selected-command}` = 5.

### Requirement R7: Security boundary mentions "selected command"
- **Expected**: Security boundary prose updated to mention "selected command".
- **Actual**: Line 219: "The agent MUST NOT execute the **selected command** (or the `demo-command:` value) itself; it is printed for the user to run manually in a separate terminal session."
- **Verdict**: PASS
- **Notes**: Acceptance: `selected command\|selected.*demo` = 1.

### Requirement R8: SKILL.md Step 3 item 2 updated
- **Expected**: Step 3 item 2 references `demo-commands:` list and agent-reasoned selection.
- **Actual**: Line 101 of `skills/morning-review/SKILL.md`: "**Demo Setup** — if `demo-commands:` (list) or `demo-command:` (single string) is configured and the session is local, offer to spin up a demo worktree from the overnight branch; for `demo-commands:`, the agent reasons from Section 2 context to select the most relevant entry (or skips if none is relevant)."
- **Verdict**: PASS
- **Notes**: Acceptance: `demo-commands\|demo-command` = 2.

### Requirement R9: docs/overnight.md updated
- **Expected**: `demo-commands:` documented alongside `demo-command:`.
- **Actual**: Template (lines 53-57) shows the new `demo-commands:` block commented out. Narrative bullet (line 70) documents both `demo-command` single-string behavior and the new `demo-commands:` list with agent-reasoned selection from "Key files changed", including the silent-skip behavior when none is relevant.
- **Verdict**: PASS
- **Notes**: Acceptance: `demo-commands:` = 2 in docs/overnight.md.

### Structural invariant (Section 2a outline)
Verified order in walkthrough.md Section 2a:
1. Guard 1 (routing between paths) — lines 86-123
2. Guard 2 (SSH, shared) — lines 125-127
3. Guard 3 (extended for demo-commands: only) — lines 129-133
4. Agent Reasoning (conditional on demo-commands: path) — lines 135-144
5. Demo offer (two path-conditional variants with explicit conditional framing) — lines 146-166
6. Worktree creation (shared) — lines 168-179
7. Print template (two path-conditional variants with explicit conditional framing) — lines 181-211
8. Auto-advance — lines 213-215
9. Security boundary — lines 217-219

Guard 2 is a shared gate (not nested under either branch). Each path-conditional section carries explicit framing prose ("Use this variant only if the active path is..."). R4 suppression is absolute by explicit prose, not implicit.

## Requirements Drift

**State**: none
**Findings**:
- None. The change is scoped to morning-review skill surface (walkthrough protocol, SKILL.md, lifecycle.config.md template, docs/overnight.md narrative). It does not touch the overnight runner, state file schema, pipeline dispatch, deferral system, or any other behavior captured in `requirements/project.md` or `requirements/pipeline.md`. The agent-reasoned selection is an interactive morning-review behavior; morning-review protocol details live in the walkthrough doc, not in pipeline requirements.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `{selected-label}` / `{selected-command}` placeholders mirror the existing `{integration_branch}`, `{demo-command}`, `{resolved-target-path}` convention in the same doc (literal braces, substituted at runtime). Consistent with #071.
- **Error handling**: Parsing rules specify silent discard for malformed entries (control chars, empty command), silent fallthrough when no valid entries remain, and absolute silent skip when agent selects "none relevant". Matches the "skip silently on malformed config" pattern used throughout Section 2a's existing guards. The worktree-creation failure path (non-zero exit → print stderr, advance) is unchanged and inherited.
- **Test coverage**: Acceptance is exclusively mechanical grep-based (no code to unit-test; the artifact is prompt text). All 15+ acceptance greps from the spec pass with counts at or above the required thresholds. R4 selection quality is intentionally untestable mechanically (agent judgment), consistent with the "agent judgment accepted for bounded outputs" memory principle.
- **Pattern consistency**: The two-path conditional structure (demo-commands: list vs demo-command: single-string) preserves #071 behavior exactly where the single-string path is active — unchanged offer wording, unchanged print template, unchanged Guard 3 (two-condition). New behavior is additive on the list path only. Matches project philosophy of "proportional behavioral changes" — prompt edits only, no new infrastructure, no shared YAML parser module (NR5), no pipeline changes (NR4).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
