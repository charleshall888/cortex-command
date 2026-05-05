# Decomposition: repo-spring-cleaning

## Epic
- **Backlog ID**: 165
- **Title**: Repo spring cleaning: share-readiness for installer audience

## Work Items
| ID  | Title                                                                                                | Priority | Size | Depends On |
|-----|------------------------------------------------------------------------------------------------------|----------|------|------------|
| 166 | Rewrite README, migrate content to docs/setup.md, reorganize docs/, and fix stale paths              | high     | L    | —          |
| 168 | Delete post-shift orphan code/scripts/hooks and retire paired requirements                           | medium   | M    | —          |
| 169 | Fix archive predicate and sweep lifecycle/ and research/ dirs                                        | medium   | M    | #166, #168 (soft — sequence last to minimize cortex-archive-rewrite-paths churn against in-flight lifecycle artifacts) |

Soft dependencies expressed as suggested ordering rather than `blocked-by` to avoid hard-stalling parallelizable cleanup work. The lifecycle plan phase for #169 should reference the soft dependency and coordinate sequencing within the epic.

## Suggested Implementation Order

**Phase 1 (parallel)**: #166 + #168. Different file domains (docs vs code/scripts/hooks); run in parallel.

**Phase 2**: #169. Lands last because `bin/cortex-archive-rewrite-paths` walks every `*.md` outside excluded dirs and would rewrite path references in the in-flight lifecycle artifacts of #166/#168.

## Key Design Decisions

**User decisions ratified during research → decompose handoff** (post-critical-review):

- **DR-1 = Option B** (aggressive README cut). What's Inside cut entirely per OQ §6 — installer pre-install evaluation does not need a repo-structure tour; CLI-bin row is a recurring drift vector unenforced by parity check.
- **DR-2 = Option C** (leave lifecycle/research dir top-level visibility alone post-archive-run). Earlier `.gitignore`-only proposal was mechanically inert on already-tracked files. Corrected mechanisms (`git rm --cached` + `.gitignore`, structural relocation) deferred until post-archive-run signal.
- **DR-3 = Option B** (move strict-internals `pipeline.md`/`sdk.md`/`mcp-contract.md` to `docs/internals/`; leave `plugin-development.md` + `release-process.md` at `docs/` root).
- **DR-4 = Option A with parallel requirements retirement**. Delete unwired hooks AND retire `requirements/project.md:36` `output-filters.conf` mention in same commit, OR keep implementation. Either path; no spec/code drift.
- **OQ §7 = P-A** (forker affordances stay unless they cause user-facing noise). Maintainer's own development workflow IS clone-and-commit forker workflow; `CLAUDE.md:18`/`L48`, `install.sh:25`, statusline manual-wire path stay.

**Ticket consolidation history**:
- Original work-item enumeration produced 7 candidates: README rewrite, setup.md trim, docs/internals/ move, skill-table merge, stale-path fixes, junk deletion, archive sweep.
- First-pass consolidation (post-research) → 4 child tickets.
- Second-pass consolidation (user-requested) → 3 child tickets. Merged #167 (doc reorg + skill-table dedup + stale-path fixes) into #166 (README + setup.md). Rationale:
  - Shared file domain: all docs-cleanup changes live under `docs/`, `README.md`, `requirements/`, `CHANGELOG.md`.
  - Atomic-landing benefit: the README's Documentation index needs the new `docs/internals/` paths in the same commit as the README rewrite — avoids transient state where the index points at relocated docs that haven't moved yet.
  - Maintainer preference for fewer larger tickets at maintenance scale (per #147/#148 prior decomposition rationale).
- Per #147/#148 decomposition rationale: maintainer prefers fewer, larger tickets at this maintenance scale.

**No-cap-fire**: All 3 work items passed R2 grounding/premise checks (each Value claim cites a specific `[file:line]` anchor and has supporting research.md citation). 0 of 3 flagged. R4 cap not engaged.

## Created Files

- `backlog/165-repo-spring-cleaning-share-readiness-epic.md` — Epic
- `backlog/166-rewrite-readme-aggressively-and-migrate-content-to-setupmd.md` — README + setup.md content migration + docs/ reorg + skill-table dedup + stale-path fixes (consolidated post-decompose)
- `backlog/168-delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements.md` — Code/script/hook deletion + paired requirements retirement
- `backlog/169-fix-archive-predicate-and-sweep-lifecycle-and-research-dirs.md` — Archive predicate fix + lifecycle/research sweep

## Removed Files (during consolidation)

- `backlog/167-reorganize-docs-merge-skill-tables-and-fix-stale-paths.md` — folded into #166.
