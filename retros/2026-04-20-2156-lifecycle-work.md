# Session Retro: 2026-04-20 21:56

## Problems

**Problem**: Manufactured off-protocol alternatives before dispatching /research — paused Clarify→Research flow to offer to hand-write research.md instead of running the multi-agent dispatch the skill protocol specifies. **Consequence**: User had to explicitly redirect ("Isn't the procedure to just do the normal multi agent dispatch?"); wasted a turn, required saving a new feedback memory about following defined procedures.

**Problem**: Presented 6 Research Exit Gate open questions without first checking concurrent lifecycles for overlap. **Consequence**: User had to prompt me to check `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/` and `lifecycle/measure-xhigh-vs-high-effort-cost-delta-on-representative-task/`; missed that #088's baseline snapshot already supplies quantitative coverage for OQ4 (preservation-rule re-validation) and missed the #088 freeze dependency entirely as a scheduling OQ.

**Problem**: Initial grep baseline in the Tradeoffs research agent was 3× undercount (~41 "do not" sites claimed vs. actual ~124 across the 12 surfaces). **Consequence**: Research.md had to document the correction; first OQ framing implied "scope is smaller than ticket claims" when the ticket's 84-work-cell estimate was closer to right.

**Problem**: Codebase agent reported "P5: zero true positives" but missed 3 canonical P5 sites in `skills/lifecycle/references/research.md:57`, `plan.md:27`, `implement.md:189` — the exact sites the epic research cites as the P5 archetype. **Consequence**: Adversarial pass had to surface them; spec's P5 handling was initially wrong; required rewriting R11 mechanism defaults to add P5=SKIP for verbatim contracts.

**Problem**: Codebase agent validated the ticket's 7-skill audit list without checking whether `overnight` actually dispatches subagents or whether `pr-review` still exists in the repo. **Consequence**: Adversarial had to catch that `overnight/SKILL.md` has zero Agent/Task calls and `pr-review` was extracted to a plugin repo in commit `9ae4a85`; scope reconciliation became a major Research Exit Gate question (OQ1) that changed the audit surface from 7+5 to 6+6.

**Problem**: First spec draft over-deferred implementation-shaping decisions to Plan — pattern signatures "may be tuned at Plan time based on first-file grep results", 30–50 site range with "Plan phase refines this number", per-site mechanism classification with only M1/M4 defaults named (for P7 only). **Consequence**: Opus critical-review synthesis flagged scope re-litigation as a through-line across 3 of 4 reviewer angles; required full spec rewrite to lock signatures in Spec, add per-pattern mechanism defaults table, and remove "Plan tunes" language.

**Problem**: First spec draft conflated PR gate with rollback mitigation — Technical Constraints claimed "The PR gate (Requirement 6) is the rollback mitigation" but a PR-merged commit has identical symlink propagation to a direct-to-main commit; rollback is `git revert` either way. **Consequence**: Required reframing R6 as pre-merge review (not rollback) and adding explicit "rollback is git revert regardless of merge path" clarification.

**Problem**: First spec draft's M4 example for P5 contradicted R11's M4 definition — R11 says "negation preserved with explicit justification" but the Edge Case example removed the negation ("preserve it exactly"). **Consequence**: Required rewriting the mechanism taxonomy section; discovering that the 3 known P5 sites are correctly-literal under 4.7 (verbatim-substitution contracts) and should be SKIPPED rather than remediated.

**Problem**: Did not reconcile overnight-execution permissiveness with PR gate in first spec draft — Non-Requirements said "Plan picks" between overnight and interactive, but overnight runs `--dangerously-skip-permissions` and cannot open/wait-for/merge PRs. **Consequence**: Critical-review surfaced the conflict; required adding explicit interactive-only constraint for commits on `claude/reference/*.md` and `claude/Agents.md`.

**Problem**: Did not add baseline-cleanliness guard to R8's post-change drift check — spec assumed #088's baseline was automatically trustworthy, but #088's own edge cases allow contaminated-window snapshots. **Consequence**: Critical-review caught the missing guard; required adding `git log` diff check between `git_sha_window_start` and `git_sha_window_end` before consuming the baseline.

**Problem**: Did not add staleness bound to R9's implement-phase gate — spec said "No forced timeout; no pre-emptive implement work" which could block #85 indefinitely if #088 stalled on rate-limits or watchdog kills. **Consequence**: Critical-review flagged the open-ended block; required adding 14-day staleness bound with AskUserQuestion escalation.

**Problem**: Did not scope R10's anchored-string `grep -F` check to specific files — first draft was implicit repo-wide, which would false-positive on preservation phrases quoted in spec.md/research.md themselves. **Consequence**: Critical-review caught the grep-mechanic issue; required scoping each anchored-string check to the specific file the anchor lives in.

**Problem**: Did not add rationale for diverging from #053's direct-to-main precedent in first spec draft. **Consequence**: Critical-review flagged the precedent-asserted-and-broken-without-justification inconsistency; required adding blast-radius-asymmetry rationale to the PROCESS CHANGE entry in Changes to Existing Behavior.
