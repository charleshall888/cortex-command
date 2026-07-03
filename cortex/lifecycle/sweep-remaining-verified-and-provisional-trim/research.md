# Research: Batch 1 — Verified Lifecycle-Cluster Trim Sweep (#353)

## Epic Reference

Epic research: [`cortex/research/skill-value-scorecard/report.html`](../../research/skill-value-scorecard/report.html) (audit #347). The epic is a per-section value-vs-cost audit of the lifecycle / refine / discovery / critical-review skill clusters and their transitive loads; this ticket (#353) sweeps the remainder no sibling ticket (#348–#352) owns. **This run is scoped to Batch 1 only** — the verified lifecycle-cluster remainder — per the ticket's "one lifecycle per batch" granularity.

## Why the research is already done

This is not a discovery task. The 415-agent audit already scored, adversarially verified (multi-lens skeptic voting), and pin-scanned every candidate in these files. The authoritative per-candidate instruction — trim action, **keep-list**, and dual-source mirror precondition — lives in `cortex/research/skill-value-scorecard/master_candidates.json` under each candidate's `verdict_summaries[].revised_claim`. This artifact synthesizes that verified evidence into an executable scope; it does not re-open the analysis.

## Batch scope: 50 verified candidates, 19 files, ~8.6k weighted tokens

All candidates are `status: verified_survives`, unflagged (no `applied_in_commit` / `overlaps_ticket` / `reproposal_of`), and in files no sibling ticket owns. Grouped by file, largest first:

| File | Cand | wtok | Notable |
|------|------|------|---------|
| skills/lifecycle/SKILL.md | 4 | 2166 | s8 phase-detection, s5 mode table, s12 refine-deleg, s16 kept-pauses (MERGE_DEDUP) |
| skills/lifecycle/references/complete.md | 3 | 765 | s14 finalize-artifacts, s12 index-sync, s4 push/PR |
| skills/critical-review/references/reviewer-prompt.md | 1 | 732 | s9 JSON-envelope spec — **asymmetric keep** (see Edges) |
| skills/lifecycle/references/criticality-matrix.md | 4 | 702 | s2/s3/s4 COMPRESS, s5 LAZY_REF |
| skills/lifecycle/references/backlog-writeback.md | 2 | 700 | s3 status-check, s5 exit-2 |
| skills/lifecycle/references/orchestrator-review.md | 5 | 637 | s7 fix-agent LAZY_REF, s13 Constraints DELETE, s12 cycle-cap MERGE_DEDUP |
| skills/lifecycle/references/plan.md | 5 | 556 | s14 code-budget, s9 task-complexity, file-compress, s19 hard-gate, s5 |
| skills/lifecycle/references/competing-plans.md | 4 | 527 | s4 plan-agent template, s8/s6/s3 |
| skills/lifecycle/references/review.md | 4 | 408 | s9 drift, s8 verdict, s3, s2 |
| skills/lifecycle/references/critical-review-gate.md | 2 | 313 | s3 seed-tier rule, s4 run/skip matrix |
| skills/lifecycle/references/discovery-bootstrap.md | 2 | 252 | s2 create-index, s4 epic-injection |
| skills/lifecycle/references/load-requirements.md | 2 | 209 | s2 protocol, s1 intro |
| skills/lifecycle/references/refine-delegation.md | 3 | 204 | s5 event-logging, s2, s3 |
| skills/lifecycle/references/complexity-escalation.md | 2 | 131 | s2 gate, s1 intro |
| skills/lifecycle/references/post-refine-commit.md | 2 | 105 | s2 flag-check, s6 constraints |
| skills/lifecycle/references/parallel-execution.md | 2 | 63 | s1 intro, file-compress invariant |
| skills/lifecycle/references/kept-pauses.md | 1 | 46 | s1 preamble |
| skills/lifecycle/references/wontfix.md | 1 | 32 | s2 how |
| skills/lifecycle/references/concurrent-sessions.md | 1 | 18 | file-compress (s1–s3 aggregate) |

Categories: mostly COMPRESS; a few LAZY_REF (orchestrator s7, criticality-matrix s5), DELETE (orchestrator s13 Constraints), MERGE_DEDUP (kept-pauses s16, orchestrator s12, plan s19, concurrent-sessions aggregate).

## Constraints & Edges

- **Dual-source mirror (load-bearing).** `skills/lifecycle/` and `skills/critical-review/` both mirror to `plugins/cortex-core/`. Every edit must regenerate the mirror and commit canonical + mirror **together** — the drift pre-commit hook rejects a split. On `main`, run the plugin build with the canonical-edit commit.
- **Stale line anchors.** `start_line`/`end_line` in the JSON predate the 8 inline-applied trims. **Locate every section by heading + pinned tokens, never by line number.**
- **Keep-lists are load-bearing.** Each `revised_claim` names exactly what to keep verbatim (verb+flag invocations, exit-code routing, gate names). Honor them; the audit verified these are the pinned/consumed surfaces.
- **reviewer-prompt s9 — asymmetric precondition.** The straddle-rationale population instruction is the *sole* one repo-wide and must be **kept or relocated**, not dropped. The JSON-envelope compression must be verified against the critical-review synthesizer's parsing expectations before trimming (prompt-template files multiply by reviewer count).
- **dup_groups single-sourcing is opportunistic.** `dup_groups.json` groups span files; three groups touch `implement.md` (owned by #348) — those are **out of Batch 1** and deferred to the #348 seam. Only single-source a group when both its files are already open in this batch.
- **Concurrent session on `main`.** Another session is active (untracked `cortex/backlog/346-*.md` present). Commit with explicit pathspecs so foreign staged files don't leak in.
- **Editorial, not mechanical.** These are prose compressions; verify each keep-list survives and pinned tests stay green rather than blind find/replace.

## Explicitly out of scope (later batches / other tickets)

- Provisional tail (162 candidates) — refine/discovery/critical-review SKILL.md bodies + the 64-candidate transitive-file slice. Needs per-candidate verification against pin hits; **not** in this run.
- Sibling-owned files: implement.md (#348), commit SKILL (#349), research SKILL (#350), project.md (#351), lifecycle.config.md (#352).
- The 8 already-inline-applied candidates (`applied_in_commit` set) and 21 overlap/reproposal-flagged candidates.

## Approach

Sequential, direct-orchestrator edits on `main` (no worktree — dual-source mirror + concurrent-session on trunk make worktree dispatch riskier than the mechanical gain warrants). One commit per file (canonical + regenerated mirror together), ordered largest-saving first. After each file, confirm the keep-list tokens survive and run the pinned tests; a full `just test` gate before advancing to Review.
