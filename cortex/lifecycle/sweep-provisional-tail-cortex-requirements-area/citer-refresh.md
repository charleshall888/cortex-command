# Citer refresh — #358 provisional-tail sweep (Req 7)

Pre-batch enumeration of live line-anchor citers of the 5 target files. **Scope: `cortex_command/**` + `docs/**` only.** Active `cortex/lifecycle/**` sibling specs and `cortex/lifecycle/archive/**` are excluded (see "Excluded-scope audit" below). Each apply task (Tasks 5–9) locates its citations **by content token, not by the stored citing-side line**, then recomputes the target line or repoints to a durable heading reference. Task 10 re-runs the broad baseline to prove zero stale citer remains.

## Enumeration method (all three citation forms + broad baseline)

Three-form union over `cortex_command/**`+`docs/**`, reconciled against the broad baseline `grep -rEn '(backlog|pipeline|observability|remote-access|multi-agent)\.md' cortex_command docs`. The broad baseline surfaced 3 line-anchored citers the per-file verification passes missed (cli.py, orchestrator_context.py, overnight-operations.md:212) — recorded below.

## In-scope citers to refresh (6)

| # | citing_file:line | target | form | current cited content (token to locate) | Phase-2 action | owning apply task |
|---|---|---|---|---|---|---|
| 1 | `cortex_command/lifecycle_event.py:15-16` | `pipeline.md` L143 / L146 / L151 | L-prefix (double-backtick ``pipeline.md`` L143/146/151) | L143 "**Atomicity**: …tempfile + `os.replace()`"; L146 "**Audit trail**: `pipeline-events.log`"; L151 "**State file locking**: …permanent architectural constraint" | s13 folds State-file-locking into AC — recompute all three L-anchors (or repoint to the "Architectural Constraints"/guarantee bullets by token) after the pipeline trim | Task 6 (pipeline) |
| 2 | `cortex_command/cli.py:90` | `observability.md:93/99` | multi (slash) | **ANOMALY — likely pre-existing drift**: L93 = "Setup prints a clear warning about granting access to all tmux sessions"; L99 = blank. Neither matches cli.py:90's cited topic ("`cortex overnight status` verb … recovery"). | Task 7 must locate where the `cortex overnight status`/recovery content actually lives in observability.md now and repoint cli.py:90 to it (prefer a durable heading reference); do NOT blind-map to shifted offsets | Task 7 (observability) |
| 3 | `cortex_command/overnight/orchestrator_context.py:8` | `pipeline.md:127,134` | multi (comma) | L127 = "### Post-Session Sync"; L134 = "Conflicts in files matching `sync-allowlist.conf` … `--theirs`" | recompute L127/L134 after pipeline trims above them (L127 is a heading — prefer converting to the `### Post-Session Sync` heading reference, durable under G1) | Task 6 (pipeline) |
| 4 | `cortex_command/overnight/fill_prompt.py:7` | `multi-agent.md:50` | colon | **STALE (pre-existing off-by-one)**: L50 = "**Priority**: must-have"; the substitution contract it cites is at L51 (`### Orchestrator dispatch-template substitution contract`), spanning L51–52 | fix to the correct post-trim line for the substitution-contract bullet (recompute after s6/other multi-agent trims) | Task 9 (multi-agent) |
| 5 | `docs/overnight-operations.md:212` | `pipeline.md:28` | colon | L28 = "The overnight runner ships as a `cortex overnight {start\|status\|cancel\|logs\|schedule\|list-sessions}` Python CLI; the legacy `runner.sh` … are retired" | recompute L28 after pipeline trims above it (s3/s4/s5 sit in early sections) | Task 6 (pipeline) |
| 6 | `docs/overnight-operations.md:655` | `multi-agent.md:77` | colon | L77 = "Worktrees for the default repo are created at `<repo>/.claude/worktrees/{feature}/` … `resolve_worktree_root()`" | recompute L77 after s9 (MERGE_DEDUP at `## Architectural Constraints`, ~L73–79) | Task 9 (multi-agent) |

**No in-scope line-anchor citers** of `backlog.md` or `remote-access.md` exist in `cortex_command/**`+`docs/**` (baseline reconciled — remote-access has one file-level citer `docs/overnight-operations.md:615` with no line number, so no recompute). Tasks 5 (backlog) and 8 (remote-access) therefore have no citer-refresh obligation beyond a Task-10 baseline re-check.

**By-name / section citations (auto-pass under G1, no action):** `docs/internals/pipeline.md` and ADR-0015 cite pipeline.md's "Post-Merge Review" by name; G1 preserves headings, so these stay valid.

## Excluded-scope audit (active `cortex/lifecycle/**`, premise validated not assumed)

The exclusion is a deliberate provenance choice, **not** an assumption that no sibling cites these files. The audit confirms the opposite: ~32 active sibling lifecycle spec/plan files carry line-anchored citations of the 5 target files (e.g. `pipeline.md:124/126/130/153/154/165`, `multi-agent.md:17/30/54/58/73/77`, `observability.md:15/29/63/144`, `remote-access.md:28/45/49`, `backlog.md:105`). These are other in-progress features' provenance records; per spec Req 7 they are **deliberately left un-repointed** (repointing them risks a sibling write race and mutates recorded evidence). They were already point-in-time snapshots subject to normal drift. Surfaced here honestly rather than silently assumed away — the operator sees that this batch's trims will further drift these sibling references, and that is an accepted tradeoff of the editorial scope.

## Post-batch re-check (Task 10)

Broad-baseline re-run (`grep -rEn '(backlog|pipeline|observability|remote-access|multi-agent)\.md' cortex_command docs`) after all 5 file commits. Every in-scope line-anchored citer was independently re-checked against current file content via `sed -n '<N>p'`. **Result: zero stale — all resolve to matching content or a durable heading reference.**

| citer | post-batch target | resolves? |
|---|---|---|
| `cortex_command/lifecycle_event.py:15-16` | `pipeline.md` L143 (Atomicity) / L146 (Audit trail) / L151 (State file locking) | OK — pipeline line count held (188) |
| `cortex_command/cli.py:90` | `observability.md` "In-Session Status CLI" **heading reference** (was stale `:93/99`) | OK — durable, heading-anchored |
| `cortex_command/overnight/orchestrator_context.py:8` | `pipeline.md:127` (Post-Session Sync) / `:134` (sync-allowlist) | OK — line held |
| `cortex_command/overnight/fill_prompt.py:7` | `multi-agent.md:51` (substitution contract) — was `:50` (off-by-one fixed) | OK |
| `docs/overnight-operations.md:212` | `pipeline.md:28` (overnight CLI) | OK — line held |
| `docs/overnight-operations.md:655` | `multi-agent.md:77` (`resolve_worktree_root`) | OK — line held |

Both files that carry the surviving line anchors (pipeline.md, multi-agent.md) were compressed in-place (line count unchanged), so numeric anchors did not shift; the two genuinely-stale anchors (cli.py:90 pre-existing, fill_prompt.py:7 off-by-one) were fixed. No unaccounted baseline hit. Req 7 acceptance satisfied.

(Out-of-scope, unchanged per Req 7: `tests/test_cli_overnight_recover.py:6` carries the same pre-existing-stale `observability.md:93/99` anchor; active `cortex/lifecycle/**` sibling specs' line-anchored citations remain as provenance records.)
