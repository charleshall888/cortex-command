<!-- generated — do not hand-edit; re-run `cortex-generate-kept-pauses` -->

# Kept user pauses

Canonical inventory of the deliberate, in-scope user-facing pauses across the lifecycle and refine skills. Generated from `skills/lifecycle/references/kept-pauses-data.toml` — one row per `<!-- pause: <slug> <kind> -->` marker. The `suppressed_by` column names a `lifecycle.config.md` key or `judgment` (model-conditional rendering), orthogonal to kind.

| Pause | Kind | Suppressed by | Location | Rationale |
|-------|------|---------------|----------|-----------|
| `ambiguous-backlog-pick` | question | — | `skills/lifecycle/SKILL.md` — Step 1: Resolve the Invocation (resolver `ambiguous-backlog` state) | Backlog match is ambiguous: present candidates for the operator to disambiguate, then re-run. |
| `empty-lifecycle-offer` | question | — | `skills/lifecycle/SKILL.md` — Step 1: Resolve the Invocation (resolver `empty` state) | No topic given and incomplete lifecycles exist: offer them for the operator to pick, then re-run. |
| `backlog-already-complete-pick` | config-conditional | `backlog.backend` | `skills/lifecycle/references/backlog-writeback.md` — Backlog Status Check | Item already marked complete: ask Close vs Continue; the backend arm gates the write-back (none skips it) and overnight defaults to Continue without asking. |
| `backlog-ambiguous-slug-reinvoke` | question | — | `skills/lifecycle/references/backlog-writeback.md` — Exit-2 (ambiguous slug, canonical) | Ambiguous slug on write-back: present the stderr candidates and ask the operator to re-invoke disambiguated. |
| `complete-merge-wait` | phase-exit-wait | — | `skills/lifecycle/references/complete-first-run.md` — Step 6 — Phase-Exit Pause (Handoff Message) | Hand off after opening the PR: operator merges on GitHub then re-invokes complete; manual re-invocation is the gate. |
| `complete-test-command-ask` | question | `test-command` | `skills/lifecycle/references/complete-first-run.md` — Step 1 — Run Tests | Config present but without test-command: ask whether tests exist; suppressed when test-command is set (just run it). |
| `complete-orphan-pr-pick` | question | — | `skills/lifecycle/references/complete.md` — Route the verdict (`orphan_ambiguous`) | Multiple orphan PRs match interactive/<slug>: ask which PR to finalize before writing pr.json. |
| `resume-feature-pick` | question | — | `skills/lifecycle/references/concurrent-sessions.md` — Listing incomplete features | Multiple incomplete features and none specified: list them and ask which to resume. |
| `implement-batch-failure` | question | — | `skills/lifecycle/references/implement.md` — Failure Handling | A batch task failed: ask retry / skip / abort before continuing non-dependent tasks. |
| `implement-branch-pick` | config-conditional | `branch-mode` | `skills/lifecycle/references/implement.md` — §1 branch selection (`prompt` state picker) | Fallback branch picker on main; suppressed when branch-mode is set, the tree is clean, and no live worktree exists for the slug. |
| `plan-approval` | relayed-consent | — | `skills/lifecycle/references/plan.md` — Plan approval surface | Substantive plan approval merged with branch/dispatch selection; overnight relays the operator's pre-authorized consent. |
| `refine-empty-topic-prompt` | question | — | `skills/refine/SKILL.md` — Topic resolution (empty $ARGUMENTS) | Empty $ARGUMENTS: prompt the operator for a topic before resolving the backlog item. |
| `clarify-question-batch` | question | `judgment` | `skills/refine/references/clarify.md` — 4. Question Threshold | Clarify question batch; suppressed by model judgment when all confidence dimensions are high and the critic raised no Ask items. |
| `spec-approval` | relayed-consent | — | `skills/refine/references/specify.md` — 4. User Approval (approval surface) | Substantive spec approval surface (Approve / Request changes / Cancel); overnight relays the operator's pre-authorized consent. |
| `spec-complexity-value-gate` | question | `judgment` | `skills/refine/references/specify.md` — 4. User Approval (complexity/value gate) | Complexity/value proportionality pick-menu; renders only when the recommendation is not full scope or confidence is low, else folds into the approval surface. |
| `spec-confidence-loopback` | question | `judgment` | `skills/refine/references/specify.md` — 2a. Research Confidence Check (cycle >= 2) | On flagged confidence signals at cycle >= 2, ask whether to loop back to Research or proceed; rendered on the model's signal assessment. |
| `spec-interview-gapfill` | question | — | `skills/refine/references/specify.md` — §2 Structured interview | Structured spec interview: probe one question at a time via AskUserQuestion until ambiguities resolve. |
| `spec-open-decision-ask` | question | `judgment` | `skills/refine/references/specify.md` — 2b. Pre-Write Checks (Open Decision resolution) | Ask the operator to resolve an open decision when it cannot be resolved from research or safely deferred; model judgment gates rendering. |
