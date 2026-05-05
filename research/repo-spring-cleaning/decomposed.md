# Decomposition: repo-spring-cleaning

## Epic
- **Backlog ID**: 165
- **Title**: Repo spring cleaning: share-readiness for installer audience

## Work Items
| ID  | Title                                                                                  | Priority | Size | Depends On |
|-----|----------------------------------------------------------------------------------------|----------|------|------------|
| 166 | Rewrite README aggressively and migrate content to docs/setup.md                       | high     | M–L  | #167 (soft — for Documentation index updates) |
| 167 | Reorganize docs/, merge skill tables, and fix stale paths                              | medium   | M    | —          |
| 168 | Delete post-shift orphan code/scripts/hooks and retire paired requirements             | medium   | M    | —          |
| 169 | Fix archive predicate and sweep lifecycle/ and research/ dirs                          | medium   | M    | #166, #167, #168 (soft — sequence last to minimize cortex-archive-rewrite-paths churn against in-flight lifecycle artifacts) |

Soft dependencies expressed as suggested ordering rather than `blocked-by` to avoid hard-stalling parallelizable cleanup work. The lifecycle plan phase for #166 and #169 should reference the soft dependencies and coordinate sequencing within the epic.

## Suggested Implementation Order

**Phase 1 (parallel)**: #167 + #168. Independent file sets; run in parallel.

**Phase 2**: #166. Lands after #167 so the README's Documentation index can point at the new `docs/internals/` paths in one commit. Hard prerequisite within #166: setup.md content additions (uv run semantics, uv-self-uninstall foot-gun, fork-install URL pattern, Upgrade & maintenance subsection, Customization, Commands subsection) must land BEFORE the README cut commit, or the cut deletes content rather than relocating it. Lifecycle plan phase will sequence: setup.md edits → README cuts.

**Phase 3**: #169. Lands last because `bin/cortex-archive-rewrite-paths` walks every `*.md` outside excluded dirs and would rewrite path references in the in-flight lifecycle artifacts of #166/#167/#168.

## Key Design Decisions

**User decisions ratified during research → decompose handoff** (post-critical-review):

- **DR-1 = Option B** (aggressive README cut). What's Inside cut entirely per OQ §6 — installer pre-install evaluation does not need a repo-structure tour; CLI-bin row is a recurring drift vector unenforced by parity check.
- **DR-2 = Option C** (leave lifecycle/research dir top-level visibility alone post-archive-run). Earlier `.gitignore`-only proposal was mechanically inert on already-tracked files. Corrected mechanisms (`git rm --cached` + `.gitignore`, structural relocation) deferred until post-archive-run signal.
- **DR-3 = Option B** (move strict-internals `pipeline.md`/`sdk.md`/`mcp-contract.md` to `docs/internals/`; leave `plugin-development.md` + `release-process.md` at `docs/` root).
- **DR-4 = Option A with parallel requirements retirement**. Delete unwired hooks AND retire `requirements/project.md:36` `output-filters.conf` mention in same commit, OR keep implementation. Either path; no spec/code drift.
- **OQ §7 = P-A** (forker affordances stay unless they cause user-facing noise). Maintainer's own development workflow IS clone-and-commit forker workflow; `CLAUDE.md:18`/`L48`, `install.sh:25`, statusline manual-wire path stay.

**Ticket consolidation**:
- Original work-item enumeration produced 7 candidates: README rewrite, setup.md trim, docs/internals/ move, skill-table merge, stale-path fixes, junk deletion, archive sweep.
- Consolidated to 4: setup.md content migration merged into #166 (no-standalone-value prerequisite for the cut); skill-table merge + stale-path fixes folded into #167 (same-file overlap on docs/agentic-layer.md and shared docs-reorg context).
- Per #147/#148 decomposition rationale: maintainer prefers fewer, larger tickets at this maintenance scale.

**No-cap-fire**: All 4 work items passed R2 grounding/premise checks (each Value claim cites a specific `[file:line]` anchor and has supporting research.md citation). 0 of 4 flagged. R4 cap not engaged.

## Created Files

- `backlog/165-repo-spring-cleaning-share-readiness-epic.md` — Epic
- `backlog/166-rewrite-readme-aggressively-and-migrate-content-to-setupmd.md` — README + setup.md content migration
- `backlog/167-reorganize-docs-merge-skill-tables-and-fix-stale-paths.md` — Doc reorg + skill-table dedup + stale-path fixes
- `backlog/168-delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements.md` — Code/script/hook deletion + paired requirements retirement
- `backlog/169-fix-archive-predicate-and-sweep-lifecycle-and-research-dirs.md` — Archive predicate fix + lifecycle/research sweep
