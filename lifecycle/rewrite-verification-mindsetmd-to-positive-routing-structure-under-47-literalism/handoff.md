# Handoff — rewrite verification-mindset.md to positive routing structure under 4.7 literalism

**Branch**: I (catch-all). Populated by Task 20; the §User Decision section
below is left blank for the user to fill in after reviewing this handoff and
`probe-log.md`.

## Decision Rationale

The R1 probe battery (40 trials, 8 wordings × 5 trials) produced `rf_vote=0` on
all 7 non-control wordings and `cf_vote=0` on all 7 non-control wordings. The
negative control also voted `rf=0, cf=0`, so battery specificity is intact —
the result is not a control-failure artifact. See `probe-log.md §Per-Wording
Summary` for the full count table and `§Decision: I` for the full argument.

D was mechanically matched — its predicate `cf_vote==1 on ≤3 of 7` is trivially
satisfied by `0 ≤ 3` — but D's stated semantics ("rail behavior is broken
regardless of load", plan.md:291) are contradicted by the evidence. In the one
R1 trial where the rail loaded (canonical/trial-1), challenge_fired was
observed; the rail text did challenge when it actually loaded. D would require
at least one loaded-but-unchallenged observation and R1 has zero such
observations, so routing to D would assert a semantic claim the data
refutes. E was the converse problem: E's semantics ("rail behaves correctly
when loaded but does not load reliably") fit the observed pattern almost
exactly, but E's mechanical predicate requires `cf_vote==1 on ≥4 of 7` and
only 0/7 was observed. Overriding a branch whose mechanical predicate
explicitly fails is a larger procedural violation than routing to the I
catch-all, which exists for exactly this mismatch.

I is the honest choice: a 2026-04-23 diagnostic re-probe (see §Apparatus
Hypothesis) identified two distinct rail-loading obstructions that the R2
precedence table was not designed to discriminate. The binding constraint in
both paths is rail *loading*, not rail text quality in isolation — so the R2
branches (which scope interventions to rail-text rewrites vs. generic
hook-based loading) cannot cleanly map the observed mechanisms.

## Apparatus Hypothesis

The 2026-04-23 diagnostic re-probe (10 trials × 2 wordings with
`--disallowed-tools Skill`, total cost $1.98) confirmed two independent
mechanisms that both obstruct loading of `claude/reference/verification-mindset.md`,
via different paths:

1. **Skill-routing-bypass** (PR path). Wordings containing "PR" cause the
   model to dispatch to `/pr` via the Skill tool as its first action in 14 of
   15 non-diagnostic PR-containing trials, short-circuiting the
   `~/.claude/CLAUDE.md` conditional-load trigger for verification-mindset.md
   before it has a chance to fire. Evidence: with `--disallowed-tools Skill`
   applied, the canonical wording's rail-load rate moved from 1/5 (R1
   baseline) to 3/5 (diagnostic), and the challenge rate moved from 1/5 to
   3/5. Of the 3 canonical diagnostic trials where the rail loaded, 2
   challenged — rail text behaves correctly when loaded, though
   probabilistically (~2/3), not deterministically.

2. **CLAUDE.md rule-competition** (commit path). Wordings containing "commit"
   trigger the `~/.claude/CLAUDE.md` rule "Always Use the `/commit` Skill",
   which wins over the conditional-load trigger even with the Skill tool
   blocked — the model deflects to user-invoked `/commit` rather than loading
   the rail first. Evidence: hedge-new rail-load rate stayed at 0/5 across
   both R1 and the diagnostic, i.e. blocking the Skill tool was
   insufficient. The binding constraint here is CLAUDE.md rule precedence,
   not Skill-tool availability.

These findings refine spec §Edge Cases, which framed the risk as "the
single-shot `claude -p` regime may not fully exercise a rail whose trigger is
'about to claim success' in the agent's own voice." The empirical binding
constraint turned out not to be claim-in-agent-voice specifically but rather
CLAUDE.md rule precedence and skill-routing-bypass — two concrete loading-layer
obstructions that route around the conditional-load trigger before any voice
or completion-language heuristic gets to run.

## Probe Evidence Pointer

All evidence paths below are relative to this handoff's directory (`lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/`):

- `probe-log.md` — full R1 trial log (§Run-1 Trial Log), per-wording counts
  (§Per-Wording Summary), the §Decision: I body with diagnostic re-probe
  table and first-action frequency table, and the §User Override entry.
- `probe-runs/run1/` — 40 stream-json files from the R1 battery (8 wordings
  × 5 trials; subdirectories: `canonical/`, `control/`, `hedge/{omit-tests-pass,future-tense,hedge-only,no-completion-language,iron-law,hedge-new}/`).
- `probe-runs/run-diagnostic/` — 10 stream-json files from the 2026-04-23
  diagnostic re-probe (2 wordings × 5 trials with `--disallowed-tools Skill`).
- `run-diagnostic.sh` — driver script for the diagnostic re-probe.
- `events.log` — lifecycle event log for this feature.

## User Decision

*This section is left blank by Task 20. The user writes their decision directly
below after reviewing this handoff and `probe-log.md`.*

Candidate interventions (not pre-selected — for reference only; the user picks
among these, combines them, or names a different path):

- **PreToolUse hook** on terminal actions (`gh pr create` / `git commit` /
  `git push`) that gates on fresh verification evidence — addresses both
  mechanisms at the action layer; mechanism-independent (does not rely on the
  conditional-load trigger firing at all).
- **Hook-based verification injection** — force-load verification-mindset.md
  before terminal actions via a hook that prepends the rail to the agent's
  context; addresses the loading layer directly and bypasses the skill /
  CLAUDE.md rule race entirely.
- **Skill-side "Read verification-mindset.md first" prerequisite** added to
  `/pr`, `/commit`, and other terminal-action skills — moves the load into
  the skill bodies themselves, so skill-routing-bypass becomes
  skill-routing-*through* the rail rather than around it.
- **CLAUDE.md rule-competition refactor** — reconcile the competing "Always
  Use /commit" rule with the conditional-load trigger, e.g. have
  terminal-action rules in CLAUDE.md explicitly cite verification-mindset.md
  as a precondition for invoking `/commit` or `/pr`.

---

**User decision**:

<!-- User: write your decision here, including which intervention(s) you are
     adopting (if any), scope, and any follow-up ticket identifiers you open. -->
