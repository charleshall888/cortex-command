# Session Retro: 2026-04-15 11:21

## Problems

**Problem**: Initial research synthesis cited GitHub issue #40789 as a current bug and pushed a "ship anyway / latent value" framing before verifying the bug's empirical status. **Consequence**: User had to challenge "Are you sure that is still a real bug today?" — lost a cycle to verification work that should have happened before the finding was presented as load-bearing evidence.

**Problem**: After the first empirical check (disabled `code-review` plugin's command absent from my session) showed the bug was not manifesting, I added an over-cautious caveat that #40789 was "specifically about skills, not commands" and proposed a second redundant test. **Consequence**: User had to challenge "Didn't we already test this?" — the caveat was manufacturing uncertainty where the evidence (both commands and skills from the enabled plugin appeared in the same unified catalog) already answered the question.

**Problem**: Specify-phase Q&A did not include a question distinguishing "moves to plugin" vs. "demote to project-local" — user had to volunteer on their own that `harness-review` should be project-local-to-cortex-command, not extracted at all. **Consequence**: The clarify/specify interview missed a scope-shaping decision that would have been cheap to prompt for.

**Problem**: Spec passed orchestrator review (S6 = Behavioral changes documented) despite omitting documentation-file moves — `docs/ui-tooling.md` (127-line dedicated UI-tooling reference), `docs/setup.md` UI-bundle instructions, and `docs/dashboard.md` ui-judge/ui-a11y references were all missing from the spec. **Consequence**: User had to ask "Did you make sure documentation is included in the move?" to surface the gap; three spec revisions later than it should have happened.

**Problem**: Orchestrator review's S6 checklist treated "Changes to Existing Behavior section present with entries" as sufficient, without verifying the section was complete relative to the codebase surface the spec touches. **Consequence**: An incomplete change inventory passed the quality gate; the auto-applied MoSCoW-only fix did not catch the broader doc omission.

**Problem**: Three scope-pivot cycles within one specify phase (in-repo plugin → separate repo after complexity gate → additional scope cuts after `/critical-review` challenged Option C dominance). **Consequence**: Churn that should have been avoided by surfacing the in-repo-vs-separate-repo and Option-A-vs-Option-C tradeoffs once, upfront, rather than letting each pass introduce a new scope reconsideration.

**Problem**: First critical-review pass dispositioned Finding 3 (`cortex-dev-extras` as 1-skill plugin) as "Ask" but then /critical-review later flagged the same named-bundle tension as dominating the whole spec. **Consequence**: The earlier pass under-escalated a concern that grew to scope-pivot magnitude — I treated it as a local decision when it was a symptom of the broader "does plugin infrastructure earn its place" question.

**Problem**: R10 then R7 renumbering across spec revisions (post-scope-pivot) — references in /critical-review findings and events.log entries cite the same requirement under different numbers. **Consequence**: Audit trail is harder to read; future lifecycle mining will need to reconcile number changes.

**Problem**: Used the Agent tool's general-purpose dispatch for the ad-hoc critical review instead of invoking `/critical-review` skill per the lifecycle specify.md §3b protocol ("invoke the `critical-review` skill"). **Consequence**: Deviation from the documented protocol. The later `/critical-review` invocation (user-initiated) produced stronger findings than my single-agent version — suggests the skill's parallel+Opus-synthesis structure would have caught Option C dominance in the first pass.

**Problem**: Dispatched 4 research agents + 4 critical-review reviewers + 1 adversarial research agent + 1 critical review agent + 1 Opus synthesis — heavy agent use for a feature that the critical review eventually argued could collapse to ~5 lines of bash in `justfile`. **Consequence**: High compute cost relative to the (arguable) delivered scope-value at the end of the specify phase.
