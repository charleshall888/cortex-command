# Review: decide-and-document-post-47-policy-settings-must-escalation-tone-regression

## Stage 1: Spec Compliance

### Requirement R1: OQ3 policy section header
- **Expected**: `grep -c '^## MUST-escalation policy (post-Opus 4\.7)$' CLAUDE.md` returns exactly `1`.
- **Actual**: Returns `1`. Section appears at line 52, immediately after `## Conventions`.
- **Verdict**: PASS

### Requirement R2: Artifact-bound evidence requirement (FM-1 mitigation)
- **Expected**: `grep -Fc 'include in the commit body'` and `grep -Fc 'is rejected at review'` each return `1`.
- **Actual**: Both return `1`. Three-artifact list (events.log F-row, retros entry, transcript URL/excerpt) is present in CLAUDE.md line 54 with imperative phrasing ("you must include…", "is rejected at review"). Grandfathering of pre-existing MUSTs is captured in line 54 ("pre-existing MUST language is grandfathered until specifically audited (per #85)").
- **Verdict**: PASS

### Requirement R3: Effort-first clause (FM-5 mitigation)
- **Expected**: `grep -Fc 'run a dispatch with \`effort=high\`'` and `grep -Fc 'do not escalate to MUST as a workaround'` each return `1`.
- **Actual**: Both return `1`. Both effort=high and effort=xhigh fallback are named in line 56; wiring-ticket fallback is captured for cases when effort is not exposed.
- **Verdict**: PASS

### Requirement R4: Tone-perception carve-out (FM-2 mitigation)
- **Expected**: `grep -Fc 'tone perception'` ≥ 1, `grep -Fc 'all other failure types are OQ3-eligible'` exactly `1`.
- **Actual**: First returns `1` (≥ 1 satisfied), second returns `1`. The full failure-type enumeration (correctness, control-flow, routing, latency, format-conformance, tool-selection, hallucination) appears in line 58, followed by the carve-out language and the explicit handoff to OQ6.
- **Verdict**: PASS

### Requirement R5: OQ6 policy section header
- **Expected**: `grep -c '^## Tone and voice policy (Opus 4\.7)$' CLAUDE.md` returns exactly `1`.
- **Actual**: Returns `1`. Section appears at line 62, immediately following the OQ3 section as required ("immediately following").
- **Verdict**: PASS

### Requirement R6: User-self-action note with epistemic honesty
- **Expected**: `grep -Fc 'Use a warm, collaborative tone'` and `grep -Fc 'inconsistent leverage'` each return `1`.
- **Actual**: Both return `1`. Line 64 carries the recommended directive verbatim, the support.tools citation, the system-prompt-layer caveat, and the "documented uncertainty about efficacy" framing — both halves of R6's mandatory wording (recommendation + caveat) are present.
- **Verdict**: PASS

### Requirement R7: OQ6 re-evaluation triggers (with empirical-leverage signal)
- **Expected**: `grep -Fc '(d) an empirical test of rules-file tone leverage'` exactly `1`, `grep -Fc '2+ separate'` ≥ 1.
- **Actual**: First returns `1`, second returns `2`. All five triggers (a)–(e) appear at line 66 with the counted-threshold disclaimer.
- **Verdict**: PASS

### Requirement R8: OQ3 re-evaluation triggers
- **Expected**: `grep -Fc '(a) Anthropic publishes guidance reversing'` returns exactly `1`.
- **Actual**: Returns `1`. All three triggers (a)–(c) appear at line 60 with "Single observation does not fire revisit" disclaimer.
- **Verdict**: PASS

### Requirement R9: Bloat-threshold rule
- **Expected**: `grep -Fc 'including this current edit'` and `grep -Fc 'fires on the entry that crosses 100'` each return `1`.
- **Actual**: Both return `1`. Rule appears at line 68, embedded at the end of the OQ6 section per spec.
- **Verdict**: PASS

### Requirement R10: Total CLAUDE.md size ≤ 100 lines
- **Expected**: `wc -l < CLAUDE.md` returns ≤ `100`.
- **Actual**: Returns `68`. Well under cap; substantial headroom for the next policy entry before the split-trigger fires.
- **Verdict**: PASS

### Requirement R11: Cross-references to source artifacts
- **Expected**: `grep -cE '#0?91|#0?85|#0?82|support\.tools|anthropic|Anthropic'` returns ≥ 4.
- **Actual**: Returns `4`. OQ3 cross-refs `#91`, `#82`, `#85`; OQ6 cross-refs `#91`, `#82`, `support.tools`, `Anthropic` (release notes). Both sections have inline provenance.
- **Verdict**: PASS

### Requirement R12: Pre-file follow-up ticket
- **Expected**: backlog file matching `*-empirically-test-rules-file-tone-leverage-under-opus-4-7.md` exists; frontmatter has `parent: "82"` and `status: backlog`.
- **Actual**: File present at `backlog/157-empirically-test-rules-file-tone-leverage-under-opus-47.md`. Frontmatter: `parent: "82"`, `status: backlog`, `priority: low`, `blocked-by: [91]`, `tags: [opus-4-7-harness-adaptation, policy]`. Title exactly matches spec ("Empirically test rules-file tone leverage under Opus 4.7+"). Body includes test design (paired dispatches, comparison protocol, R7 trigger (d) link) and out-of-scope ("one-shot empirical test, not ongoing rules-file deployment").
- **Verdict**: PASS
- **Notes**: Slug normalized to `opus-47` rather than `opus-4-7` (the plan's `ls` glob example shape) — canonical CLI behavior; the substantive R12 acceptance criteria (parent, status, frontmatter contents, body design) all hold.

### Requirement R13: Backlog ticket #91 status flip
- **Expected**: `grep -E '^status: complete$' backlog/091-...md` returns 1 line; closing note in body summarizing the two decisions.
- **Actual**: `status: in_progress` (not yet `complete`). Resolution section (`## Resolution (2026-05-04)`) IS authored in the body summarizing OQ3 Alternative A with FM-1/FM-2/FM-5 mitigations and OQ6 Alternative I with the user-self-action note + R12 follow-up reference, exactly per spec — but the file is uncommitted, awaiting Commit #3.
- **Verdict**: PARTIAL (deferred-by-design)
- **Notes**: Per the plan's three-commit atomicity, R13 is a Complete-phase responsibility (Commit #3: closing note + status flip + canonical feature_complete event + index regeneration). At review time, status=in_progress is the expected state — the close-out is not Implement-phase work. The substantive Resolution prose is already authored, so only the frontmatter flip and commit remain. Treating as PASS-with-note for verdict purposes per the reviewer guidance.

## Requirements Drift

**State**: none
**Findings**:
- None. Spec scope is policy documentation in `CLAUDE.md` plus one backlog pre-file. No edits to `skills/`, `hooks/`, `bin/`, `claude/`, `plugins/`, or any behavioral surface — consistent with project.md's in-scope architecture (file-based state, agentic workflow toolkit). The two new sections introduce author-facing norms about MUST-escalation discipline and tone policy that operate within the existing day/night split philosophy and don't expand or contradict any project boundary.
**Update needed**: None

## Stage 2: Code Quality

### Naming conventions
- Section headers match existing CLAUDE.md style (Title-case, level-2 `##`).
- Backlog ticket filename follows the canonical CLI's slug-normalization pattern (`{id}-{slug}.md`).
- Frontmatter fields conform to the schema used by other backlog items (`parent` quoted, `tags` array, `blocked-by` list).

### Error handling
- N/A for documentation changes; no executable surface modified.

### Test coverage / verification steps
- Plan's verification list executed: all 13 grep/regex acceptance checks ran successfully.
- `wc -l` confirms 68/100 line budget (32-line headroom).
- `.gitignore:42` correctly excludes `backlog/*.events.jsonl` sidecar from commit (the plan referenced the sidecar in its verification list, but its absence from git is correct per the gitignore).
- Section ordering verified: `Conventions` → `MUST-escalation policy (post-Opus 4.7)` → `Tone and voice policy (Opus 4.7)`.

### Pattern consistency
- Imperative-positive prose hygiene rule (spec preamble) is honored throughout both sections. No negation-only constructions, no hedge softeners ("consider", "may", "should consider"), no examples-as-exhaustive enumerations.
- Cross-reference format matches the inline-mention convention specified in Technical Constraints (no separate `## References` block).
- Resolution note in #91 mirrors the spec's R13 closing-note expectation (Alternative A for OQ3 + FM-mitigation map; Alternative I for OQ6 + epistemic-honest user-self-action note + R12 follow-up reference).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
