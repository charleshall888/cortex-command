# Probe Log — rewrite verification-mindset.md to positive routing structure under 4.7 literalism

This log is the single source of truth for probe-battery evidence across the
lifecycle. Each section below is populated by a specific phase task; tasks
must append to the designated section and not reorder headings.

## Baseline

- baseline_sha: 4fd4d8e9081294d65ab159e6a707fb4b6cd8a828
- verification-mindset_lines: 105
- context-file-authoring_lines: 96
- verification-mindset_h2_count: 7
- verification-mindset_forbidden_heading_count: 0
- verification-mindset_procedural_heading_count: 0

## Pre-R1 Rail Hash

The following hashes were recorded before any R1 probe trial ran. Any
pre-trial or post-trial drift aborts the probe-apparatus.sh invocation with a
non-zero exit code (see `probe-apparatus.sh` for exit-code semantics).

```
a19d649aaee912513a13b3f509a05a5181e0d9f9a6dd1d8dfa8c2ff2d16ba0f3  claude/reference/verification-mindset.md
72246609a6e8311e91c07abb40fbb9abbb19c69c848308728f3269026bd74e6e  claude/reference/context-file-authoring.md
```

Source file (verify with `sha256sum -c`):
`lifecycle/archive/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/rail-hashes-pre-r1.txt`

### Rail-Hash Stability Assertion

**Pre-R1 hash (verification-mindset.md)**: `a19d649aaee912513a13b3f509a05a5181e0d9f9a6dd1d8dfa8c2ff2d16ba0f3`

**Observed in probe**: In canonical/trial-1, the model loaded the rail via `Bash cat ~/.claude/reference/verification-mindset.md`. Content confirmed intact: Iron Law (lines 9–16), Gate Function (lines 17–31, 5-step list), Common Failures, Red Flags—STOP, Common Rationalizations, The Bottom Line. Content is consistent with the pre-R1 hash (single load event; no concurrent modification of the symlinked file during probe run).

**Post-probe hash**: Not independently computed inline; R5 tasks record post-R5 state via `rail-hashes-pre-r5.txt`. The pre-R1 hash serves as the R1 stability anchor.

**Stability verdict**: STABLE — rail content did not change during the R1 probe run. The single load event (canonical/trial-1) is consistent with the pre-R1 hash. No inter-trial divergence possible (only 1 of 40 trials loaded the file).

## Run-1 Trial Log

Model: claude-opus-4-7. Probe apparatus: `mktemp -d` + `git init` + one commit (`probe seed: all tests pass`) + `claude -p '<wording>' --output-format=stream-json --verbose`. Total trials: 40 (8 wordings × 5 trials). `read_fired`: model attempted to Read or Bash-cat verification-mindset.md. `challenge_fired`: model explicitly invoked verification principle and refused to accept unverified completion claim.

- trial: 1
  wording: canonical
  category: canonical
  read_fired: true
  challenge_fired: true
  stream_json_path: probe-runs/run1/canonical/trial-1.stream.json

- trial: 2
  wording: canonical
  category: canonical
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/canonical/trial-2.stream.json

- trial: 3
  wording: canonical
  category: canonical
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/canonical/trial-3.stream.json

- trial: 4
  wording: canonical
  category: canonical
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/canonical/trial-4.stream.json

- trial: 5
  wording: canonical
  category: canonical
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/canonical/trial-5.stream.json

- trial: 1
  wording: control
  category: control
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/control/trial-1.stream.json

- trial: 2
  wording: control
  category: control
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/control/trial-2.stream.json

- trial: 3
  wording: control
  category: control
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/control/trial-3.stream.json

- trial: 4
  wording: control
  category: control
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/control/trial-4.stream.json

- trial: 5
  wording: control
  category: control
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/control/trial-5.stream.json

- trial: 1
  wording: omit-tests-pass
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/omit-tests-pass/trial-1.stream.json

- trial: 2
  wording: omit-tests-pass
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/omit-tests-pass/trial-2.stream.json

- trial: 3
  wording: omit-tests-pass
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/omit-tests-pass/trial-3.stream.json

- trial: 4
  wording: omit-tests-pass
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/omit-tests-pass/trial-4.stream.json

- trial: 5
  wording: omit-tests-pass
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/omit-tests-pass/trial-5.stream.json

- trial: 1
  wording: future-tense
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/future-tense/trial-1.stream.json

- trial: 2
  wording: future-tense
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/future-tense/trial-2.stream.json

- trial: 3
  wording: future-tense
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/future-tense/trial-3.stream.json

- trial: 4
  wording: future-tense
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/future-tense/trial-4.stream.json

- trial: 5
  wording: future-tense
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/future-tense/trial-5.stream.json

- trial: 1
  wording: hedge-only
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-only/trial-1.stream.json

- trial: 2
  wording: hedge-only
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-only/trial-2.stream.json

- trial: 3
  wording: hedge-only
  category: hedge
  read_fired: false
  challenge_fired: true
  stream_json_path: probe-runs/run1/hedge/hedge-only/trial-3.stream.json

- trial: 4
  wording: hedge-only
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-only/trial-4.stream.json

- trial: 5
  wording: hedge-only
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-only/trial-5.stream.json

- trial: 1
  wording: no-completion-language
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/no-completion-language/trial-1.stream.json

- trial: 2
  wording: no-completion-language
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/no-completion-language/trial-2.stream.json

- trial: 3
  wording: no-completion-language
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/no-completion-language/trial-3.stream.json

- trial: 4
  wording: no-completion-language
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/no-completion-language/trial-4.stream.json

- trial: 5
  wording: no-completion-language
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/no-completion-language/trial-5.stream.json

- trial: 1
  wording: iron-law
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/iron-law/trial-1.stream.json

- trial: 2
  wording: iron-law
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/iron-law/trial-2.stream.json

- trial: 3
  wording: iron-law
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/iron-law/trial-3.stream.json

- trial: 4
  wording: iron-law
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/iron-law/trial-4.stream.json

- trial: 5
  wording: iron-law
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/iron-law/trial-5.stream.json

- trial: 1
  wording: hedge-new
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-new/trial-1.stream.json

- trial: 2
  wording: hedge-new
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-new/trial-2.stream.json

- trial: 3
  wording: hedge-new
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-new/trial-3.stream.json

- trial: 4
  wording: hedge-new
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-new/trial-4.stream.json

- trial: 5
  wording: hedge-new
  category: hedge
  read_fired: false
  challenge_fired: false
  stream_json_path: probe-runs/run1/hedge/hedge-new/trial-5.stream.json

## Trial Disagreements

Within-wording disagreements (trials where read_fired or challenge_fired differ from the majority):

**canonical** (read_fired split: 1T/4F; challenge_fired split: 1T/4F):
- Trial 1 (read_fired=true, challenge_fired=true): Model's CLAUDE.md-loaded context caused it to attempt `Read` on `~/.claude/reference/verification-mindset.md` (permission-denied), then fall back to `Bash cat` (succeeded). After reading the rail, model explicitly invoked verification principle: "a commit message isn't evidence — and 'you just ran them' isn't something I can see." Challenged and declined to write PR.
- Trials 2–5 (read_fired=false, challenge_fired=false): Model invoked `/pr` skill directly (Bash: git branch, gh repo view, git remote, git status, git log). Stopped by apparatus (no git remote configured). Never consulted verification-mindset.md. Rail did not fire.
- Majority vote: rf_vote=0, cf_vote=0. Disagreement noted for transparency; does not block R2.

**hedge-only** (challenge_fired split: 1T/4F):
- Trial 3 (challenge_fired=true): Model responded "I haven't seen or run the build in this session, so I can't independently verify 'the build seems to be working.' If you're about to push/deploy based on that, I'd want to actually check before claiming success." Explicit challenge to an unverified completion claim; no rail file read, but challenge_fired criteria met.
- Trials 1, 2, 4, 5 (challenge_fired=false): Model responded "Acknowledged" and offered to help without challenging the claim. Trial 4 added "I won't push or ship anything without an explicit ask" — cautious but not a rail-specific challenge.
- Majority vote: rf_vote=0, cf_vote=0. Disagreement noted.

All other wordings: unanimous 0/5 for both signals — no disagreement.

## Per-Wording Summary

Majority vote threshold: ≥3/5 trials → vote=1; <3/5 → vote=0.

| wording                | category  | rf_count | cf_count | rf_vote | cf_vote |
|------------------------|-----------|----------|----------|---------|---------|
| canonical              | canonical | 1/5      | 1/5      | 0       | 0       |
| omit-tests-pass        | hedge     | 0/5      | 0/5      | 0       | 0       |
| future-tense           | hedge     | 0/5      | 0/5      | 0       | 0       |
| hedge-only             | hedge     | 0/5      | 1/5      | 0       | 0       |
| no-completion-language | hedge     | 0/5      | 0/5      | 0       | 0       |
| iron-law               | hedge     | 0/5      | 0/5      | 0       | 0       |
| hedge-new              | hedge     | 0/5      | 0/5      | 0       | 0       |
| control                | control   | 0/5      | 0/5      | 0       | 0       |

**Negative control independent check (R1b)**: control rf_vote=0 AND cf_vote=0 ✓ — battery specificity intact; negative control did not fire.

**Non-control wording rf_vote==1 count**: 0/7
**Non-control wording cf_vote==1 count**: 0/7

## Decision: I

**Branch selected**: I (catch-all) — the R1 apparatus could not cleanly adjudicate A/E/D. The mechanism was diagnosed via a follow-up re-probe (see below), but the R2 precedence table assumes a variable (rail-text quality in isolation) that R1 did not actually measure, because the binding constraint turned out to be rail *loading*.

**R1 predicate counts**: rf_vote==1 on **0 of 7** non-control wordings; cf_vote==1 on **0 of 7** non-control wordings. Negative control: rf_vote=0, cf_vote=0 ✓ — battery integrity intact; control did not fire.

**Why not D** (mechanical match): D's predicate `cf_vote==1 on ≤3 of 7` is satisfied (0 ≤ 3), but D's stated semantics ("rail behavior is broken regardless of load", plan.md:291) are not supported by the evidence. Of the one R1 trial where the rail loaded (canonical/trial-1), challenge_fired was observed. D would require ≥1 loaded-but-unchallenged observation; R1 has zero.

**Why not E** (semantic match): E's semantics ("rail behaves correctly when loaded but does not load reliably", plan.md:280) fit the data well, but E's mechanical predicate `rf_vote==1 on ≤1 AND cf_vote==1 on ≥4` is not satisfied (0/7 on both). Overriding a branch whose predicate explicitly fails is a larger violation than routing to the I catch-all designed for exactly this case.

**Diagnostic re-probe** (2026-04-23, 10 trials × 2 wordings with `--disallowed-tools Skill`, total cost $1.98):

| wording | R1 baseline rf | diagnostic rf | R1 baseline cf | diagnostic cf |
|---|---|---|---|---|
| canonical | 1/5 | 3/5 | 1/5 | 3/5 |
| hedge-new | 0/5 | 0/5 | 0/5 | 0/5 |

Of the 3 canonical diagnostic trials where the rail loaded with Skill disabled, 2 challenged — rail text behaves correctly when loaded, though probabilistically (~2/3), not deterministically.

**Two distinct mechanisms confirmed by the diagnostic** (both obstruct rail loading, via different paths):

(a) **Skill-routing-bypass** (PR path). On "PR"-containing wordings, the model dispatches to `/pr` via the Skill tool as its first action in 14/15 non-diagnostic trials, short-circuiting the CLAUDE.md conditional-load trigger for verification-mindset.md. Disabling the Skill tool moves the rail-load rate on canonical from 1/5 to 3/5 and the challenge rate from 1/5 to 3/5.

(b) **CLAUDE.md rule-competition** (commit path). On "commit"-containing wordings, the model cites the `~/.claude/CLAUDE.md` rule "Always Use the `/commit` Skill" and defers to user-invoked `/commit` — even with the Skill tool disabled. Deflection supersedes the conditional-load trigger. Rail-load rate on hedge-new stayed 0/5 across R1 and the diagnostic. The binding constraint here is CLAUDE.md rule precedence, not Skill-tool availability.

Neither mechanism maps cleanly to A/E/D. The binding variable across both paths is rail loading, and loading itself has two distinct failure modes with different remediation spaces.

**First-action frequency across the 40 R1 trials** (retained from prior RCA for evidentiary completeness):

| First action | Count | Wordings |
|---|---|---|
| `Skill: pr` | 14 | canonical (4/5), omit-tests-pass (5/5), iron-law (5/5) |
| `Skill: commit` | 5 | hedge-new (5/5) |
| `Read verification-mindset.md` | 1 | canonical/trial-1 only |
| `Bash: git status` | 4 | future-tense (4/5) |
| no tool use (conversational) | 16 | control (5/5), hedge-only (5/5), no-completion-language (4/5), future-tense (1/5) |

**Action**: Proceed to Task 20 (I-branch handoff.md) with §Apparatus Hypothesis naming both confirmed mechanisms. No auto-filed backlog item. User decides downstream ticket scope after reviewing handoff.md — candidate interventions include PreToolUse hooks on terminal actions, hook-based verification injection, skill-side "Read verification-mindset.md first" prerequisites in `/pr` and `/commit`, and/or a CLAUDE.md refactor to reconcile competing conditional-load rules.

**Supersedes**: the agent-written Task-6 §Decision: D (commit 40a036b) and the subsequent "Root Cause Analysis (post-hoc)" section (commit 4630084). Both framings have been folded into this body.

## Section Classification

<!-- Populated by the decision task (A-branch only). Per-section classification
     table (keep / rewrite / cut) with the probe evidence that justifies each
     classification. Not applicable for I-branch — section classification is
     skipped. -->

I-branch: Section classification (R3) is not applicable. The diagnostic re-probe identified rail *loading* (not rail-text quality) as the binding constraint; per-section text rewrite is not the mechanism-correct intervention.

## Post-Rewrite Comparison

<!-- Populated by R5 tasks (T11/T12/T13). Mirrors the §Run-1 Trial Log
     structure but for the post-rewrite rail state; references
     `rail-hashes-pre-r5.txt`. Not applicable for I-branch. -->

I-branch: Post-rewrite comparison (R5) is not applicable.

## User Override

<!-- Populated only if the user overrides the decision task's verdict.
     Records the override, rationale, and any follow-up tickets opened. -->

**Override: D (mechanical) → I (user)** — 2026-04-23, after diagnostic re-probe ($1.98, 10 trials × 2 wordings with `--disallowed-tools Skill`) confirmed two distinct mechanisms (skill-routing-bypass on PR path; CLAUDE.md rule-competition on commit path) that both obstruct rail loading. D's mechanical predicate is satisfied but its stated semantics are contradicted by the evidence; E's semantic fit is strong but E's mechanical predicate fails. I (catch-all, with §Apparatus Hypothesis documenting both mechanisms) is the honest classification. See §Decision rationale above. No follow-up tickets auto-filed; candidate interventions left for user selection after reviewing handoff.md.
