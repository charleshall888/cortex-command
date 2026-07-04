# Kept user pauses

Canonical inventory of the deliberate, in-scope user-facing `AskUserQuestion` pauses across the lifecycle and refine skills (the lifecycle SKILL.md Phase Transition rule points here). `tests/test_lifecycle_kept_pauses_parity.py` enforces bidirectional parity: every entry below resolves to a real `AskUserQuestion` site, and every such site under `skills/lifecycle/` and `skills/refine/` has an entry here.

- `skills/lifecycle/SKILL.md:42` — ambiguous backlog match needs operator disambiguation.
- `skills/refine/references/clarify.md:42` — low-confidence clarify question batch surfaces unknowns the model cannot resolve alone.
- `skills/refine/references/specify.md:26` — structured-interview gap-fill: model needs user input for unstated requirements.
- `skills/refine/references/specify.md:55` — §2a cycle-2 confidence-check: user decides whether to loop back to research or proceed with gaps.
- `skills/refine/references/specify.md:140` — spec approval surface (Approve / Request changes / Cancel). Substantive user decision.
- `skills/lifecycle/references/plan.md:126` — plan approval surface, merged with branch/dispatch selection (branch modes + "Approve plan but wait to implement" imply approval; Request changes / Cancel via the "Other" free-text escape). Substantive user decision.
- `skills/lifecycle/references/implement.md:21` — conditional pause: fallback branch-selection picker on main (the `cortex-lifecycle-branch-decision` verb's `prompt` state), used only when no plan-time `dispatch_choice` was recorded (trunk vs feature-branch-with-worktree vs feature branch). Suppressed when `lifecycle.config.md::branch-mode` is set AND the working tree is clean AND no concurrent live interactive worktree exists for the feature slug.
- `skills/lifecycle/references/backlog-writeback.md:22` — backlog write-back complete-lifecycle prompt on a backlog item already marked complete.
- `skills/lifecycle/references/complete.md:46` — phase-exit pause: merge-wait pause inside the multi-step Complete phase; user re-invokes /cortex-core:lifecycle complete <slug> after merging on GitHub.
- `skills/refine/SKILL.md:120` — refine §4 complexity-value gate pick-menu — renders only when the orchestrator's recommendation diverges from full scope or confidence is low; otherwise the announcement folds into the regular approval surface.
