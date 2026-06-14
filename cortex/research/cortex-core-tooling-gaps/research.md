---
discovery_phase: research
topic: cortex-core-tooling-gaps
---

# Research: cortex-core tooling gaps

Verification + dedup + decomposition pass over a set of candidate cortex-core
tooling gaps surfaced by an external progressive-disclosure audit and real
friction in a consumer game project (Wild Light). The candidates were
pre-researched; this pass verifies each against **current** source and the
**live** backlog, drops anything already shipped, re-confirms the
adversarially-dropped set is genuinely complete, and decomposes the survivors
into tickets grouped by epic A/B/C.

## Research Questions

1. For each candidate gap (A1, B1–B5, C1–C2), does the capability already exist
   in current source — ABSENT, PARTIAL, or ALREADY-SHIPPED? → **All ten confirmed
   ABSENT. None is already shipped or trivially achievable with an existing tool.**
2. For each confirmed-absent gap, what existing tool/convention should its ticket
   model on? → **Resolved per piece (see Codebase Analysis): events-registry and
   requirements-parity-audit for A1; `generate_index.py` for B1/B2; the
   measure-l1-surface + ratchet-test pair for B3; the wontfix `git mv` flow for B4;
   `_is_stale` scaffolding for B5.**
3. Are the specific call-sites cited in the brief accurate against current source?
   → **Yes, with two exceptions:** the brief's C1 workaround citation is wrong
   (the documented park is `status: abandoned`, not an index.json/git-checkout
   dance), and the brief's "OPEN tickets" list is stale (three of six are
   `complete`, one `deferred`). All file:line anchors otherwise verified.
4. Are the 8 adversarially-dropped items genuinely complete at their *fixed
   call-sites* — especially #291–294 given the documented false-complete bug?
   → **Yes. #291–294 are all CONFIRMED-FIXED at real call-sites** (not
   false-completes); the other dropped items (#207/#221/#222, #298/#302, #259,
   #272, #224) all show `status: complete` and none reappears as an open gap.
5. For the two maintainer-confirm items (B3 ownership, B5 enforcement point), what
   does current source/doctrine say about where the fix belongs? → **B3: ADR-0008
   supersedes ADR-0006 — cortex writes no clause into a consumer's root
   `CLAUDE.md`/`MEMORY.md`; the established seam scaffolds templates UNDER
   `cortex/` (e.g. #289's `cortex/.gitignore`). B5: precedent is report-not-block
   (`scan_lifecycle` diagnostics), and a blocking gate would trip the
   MUST-escalation evidence bar.**
6. Is there external prior art for the tool patterns worth modeling on, plus known
   pitfalls? → **Yes** (see Web & Documentation Research): mature ecosystems split
   authoring/generation from a thin validator; CODEOWNERS is canonical glob→owner
   prior art; the regenerate-and-diff CI gate is standard; semantic
   status-vs-reality drift is **not** done deterministically off-the-shelf.

## Codebase Analysis

### Epic A — ADR tooling (A1)

- **No `bin/` tool touches `cortex/adr/`.** `NOT_FOUND(query="cortex/adr",
  scope="bin/ + plugins/cortex-core/bin/")`. The ADR README itself states the
  discipline is prose-only and argues the case — `[cortex/adr/README.md:11-17]`.
- **134 files cite `ADR-NNNN`** (incl. production modules `[cortex_command/common.py]`,
  `[cortex_command/init/settings_merge.py]`, `[cortex_command/pipeline/parser.py]`);
  **142 occurrences** of `adr/[0-9]{3,4}` paths (incl. `[CLAUDE.md:75]`). Nothing
  validates that any of these resolve.
- **Existing ADRs are contiguous 0001–0010, no gaps, no collisions.** So the
  next-free-number helper sub-piece has **no current defect** — it is preventive only.
- **Model-on for a report-only auditor:** `cortex-requirements-parity-audit`
  ("Informational; never fails the gate") `[bin/cortex-requirements-parity-audit:1-9]`.
  **Model-on for a blocking gate (NOT recommended here):**
  `cortex-check-events-registry` (`return 1 on errors`, `--staged`/`--audit` modes,
  registry file) `[bin/cortex-check-events-registry:473-535,648-655]`,
  pre-commit-wired at `[.githooks/pre-commit:171-195]`.
- **Proposals-mode source:** the `## Proposed ADR` template and the bare
  `<NNNN-slug>` placeholder are at `[skills/lifecycle/references/specify.md:149-155]`
  (placeholder at `:153`, restated at `:178`).
- **Area-frontmatter defer-note:** `[cortex/adr/README.md:45]` — "Area tagging is
  intentionally deferred to a backfill ticket; do not invent one ad hoc." **The
  promised backfill ticket was never filed.** `NOT_FOUND(query="adr area|backfill
  OPEN ticket", scope="cortex/backlog/*.md")`. The original `area:` enum
  (`project, pipeline, multi-agent, observability, remote-access, skills`) was
  spec'd in `[cortex/backlog/224-...md:29]` but the shipped README dropped it to
  v1-deferred — so this is a kept-promise loose end, not a net-new idea.

### Epic B — progressive-disclosure generators

- **B1 (requirements file→section index):** `load-requirements.md` routes by the
  `tags:` array against `project.md`'s Conditional Loading phrases at the
  **area-doc** level — `[skills/lifecycle/references/load-requirements.md:11-13,23]`
  — never file-path→requirement-section. No generator exists:
  `NOT_FOUND(query="cortex-generate-requirements-index | glob→section INDEX",
  scope="bin/ + plugins/cortex-core/bin/ + cortex_command/")`; no INDEX file under
  `cortex/requirements/`. Model-on: `generate_index.py` `collect_items()`
  `[cortex_command/backlog/generate_index.py:85-212,327-331]` (atomic_write,
  sorted input, byte-stable).
- **B2 (cross-lifecycle index):** `cortex-lifecycle-state` and
  `cortex-lifecycle-counters` are **per-slug** (`--feature` required)
  `[cortex_command/lifecycle/state_cli.py:133-146]`,
  `[cortex_command/lifecycle/counters.py:97-102]`. **124 lifecycle dirs** exist.
  No cross-lifecycle index: `NOT_FOUND(query="cortex-generate-lifecycle-index |
  phase-inference index", scope="bin/ + cortex_command/")`. The phase-inference
  reducer **already exists** — `detect_lifecycle_phase()` in `common.py`, invoked
  per-candidate by the SessionStart scanner `[cortex_command/hooks/scan_lifecycle.py:943]`
  and already reused by `generate_index.py:176-184` — but is never written out as
  a queryable index. #259's SessionStart fix is **incomplete-features-only** and
  ephemeral (`additionalContext` string) `[scan_lifecycle.py:980-989,1084-1097]`.
  The dashboard does **not** make B2 redundant — `data.py` renders overnight-session
  + backlog views `[cortex_command/.../data.py:722,987]`, never sweeping the 124 dirs.
- **B3 (consumer always-loaded ratchet):** `cortex-measure-l1-surface` measures
  **cortex's own** `skills/*/SKILL.md` frontmatter only `[bin/cortex-measure-l1-surface:80-100]`,
  has **no argparse** and no `--check-always-loaded` mode
  `[bin/cortex-measure-l1-surface:31]`; `tests/test_l1_surface_ratchet.py` enforces
  per-skill byte baselines against cortex's own repo `[tests/test_l1_surface_ratchet.py:53-83]`.
  Nothing measures a consumer's `CLAUDE.md`/`MEMORY.md`. **Ownership (verified):**
  ADR-0006 (which spliced a fence into consumer `CLAUDE.md`) is **superseded by
  ADR-0008** — "cortex init writes no clause to consumer CLAUDE.md"
  `[cortex/adr/0008-...md]`, `[cortex/requirements/project.md:41]`. cortex-init
  writes only under `cortex/` plus two narrow exceptions (`.gitignore` append, the
  `~/.claude/settings.local.json` grant) `[cortex_command/init/scaffold.py:67-73]`,
  `[cortex_command/init/handler.py:425-429]`. #289's `cortex/.gitignore` template
  (versioned, idempotent, no-clobber, dual-source-mirrored) `[cortex/backlog/289-...md:17-19]`
  is the positive scaffolding precedent.
- **B4 (opt-in archive):** `complete.md` Step 12 forbids it — "Do not delete or
  archive the directory" `[skills/lifecycle/references/complete.md:274]`.
  `wontfix.md` does `git mv ... cortex/lifecycle/archive/...`
  `[skills/lifecycle/references/wontfix.md:12]`; the scanner skips `archive`/`sessions`
  `[scan_lifecycle.py:907]`. No archive command exists:
  `NOT_FOUND(query="cortex lifecycle archive", scope="bin/ + cortex_command/")`.
  Constraint: destructive ops must skip on uncommitted state `[cortex/requirements/project.md:56]`.
- **B5 (stale-status detection):** `_is_stale` is **30-day time-based, lifecycle-only**
  `[cortex_command/hooks/scan_lifecycle.py:398-450]` (default at `:883`). **No
  `status:` frontmatter convention exists** on research/decision docs today — **0 of
  48 `research.md` files** carry one; status words appear only as free-text body
  prose. `NOT_FOUND(query="^status: in research.md frontmatter",
  scope="cortex/research/*/research.md")`. This is a hard **precondition gap**: a
  semantic status-vs-reality detector cannot be built until the convention exists
  and is populated.

### Epic C — ops conveniences

- **C1 (overnight per-run exclude):** `select_overnight_batch(backlog_dir,
  batch_size_cap)` has no skip/exclude parameter and no per-item gate for it
  `[cortex_command/overnight/backlog.py:1020-1047]`; the CLI subparser exposes no
  `--exclude`/`--skip` `[cortex_command/cli.py:418-497]`; the MCP `start_run` has
  none either. No per-item "never overnight" frontmatter field exists on
  `BacklogItem` `[backlog.py:81-102]`. **The brief's cited workaround (edit
  index.json + `git checkout`) is NOT in the docs** — `NOT_FOUND(query="edit
  index.json status / git checkout restore for overnight exclude",
  scope="docs/overnight-operations.md, docs/internals/pipeline.md")`; the real park
  mechanisms are `status: abandoned` (permanent, execution-park)
  `[skills/backlog/references/schema.md:18]` and the `deferred` tag (index-VIEW
  only, does not affect selection) `[cortex_command/backlog/generate_index.py:74-76,235]`.
  Neither is a one-night transient exclude.
- **C2 (spec-column hyperlink):** `[cortex_command/backlog/generate_index.py:234]`
  `spec_display = "✓" if item["spec"] else "—"` renders a bare checkmark;
  the path is already in `item["spec"]` (populated at `:200`). True one-line fix.
  #272 touched the **status** column (`:235`), not `spec_display` — no overlap.

### Spot-verification of the adversarially-dropped set (#291–294)

All four carry `status: complete`; per the false-complete caveat I verified the
**fixed call-sites**, not frontmatter:

- **#291** CONFIRMED-FIXED — app-owned starlette cap `[pyproject.toml:19]`
  `"starlette>=0.49.1,<2.0"` with rationale comment `[pyproject.toml:18]`.
- **#292** CONFIRMED-FIXED — `revert_merge` imported `[cortex_command/overnight/outcome_router.py:60]`
  and called on the deferred/crash paths `[outcome_router.py:1088,1170]`; cycle-0
  ERROR handled as a blocking deferral `[cortex_command/pipeline/review_dispatch.py:310-329]`.
- **#293** CONFIRMED-FIXED — `FeatureTask` carries first-class `files`/`depends_on`
  `[cortex_command/pipeline/parser.py:60-61]`, parsed per task `[parser.py:391-412,463-593]`.
- **#294** CONFIRMED-FIXED — scoped scan `[cortex_command/overnight/report.py:687,718-719]`
  and YAML-quoted titles via `_yaml_safe_title_value` `[report.py:238-264,338]`.

## Web & Documentation Research

- **ADR reference linting:** Mature ADR toolchains split authoring (adr-tools,
  log4brains: numbering, supersession, lifecycle) from **reference validation**,
  which they delegate to generic link checkers — `md-dead-link-check` validates
  relative file links + fragment anchors, exactly the `ADR-NNNN → file` case.
  Building a bespoke resolver is considered overkill.
  (https://github.com/npryce/adr-tools, https://pypi.org/project/md-dead-link-check/)
  Pitfall: don't bake validation into an authoring tool; keep it a thin separate layer.
- **Glob→section routing:** CODEOWNERS is canonical prior art (path globs → owners,
  **last-match-wins** precedence); `codeowners-generator` is the generated-index
  variant. (https://docs.github.com/.../about-code-owners,
  https://github.com/gagoar/codeowners-generator) Pitfall: glob precedence and
  **silent no-match** are the dominant failure modes — mandate a global fallback
  rule and test the matcher against fixtures.
- **Deterministic generated index + CI diff gate:** standard pattern
  (`go generate && git diff --exit-code`). Pitfall: **nondeterministic ordering**
  produces spurious diffs and merge-conflict magnets (jOOQ #7303) — mandate a stable
  sort key and stable serialization *before* relying on the diff gate.
- **Stale-status / doc-rot:** existing tools (Fiberplane Drift, Dosu freshness)
  detect **code-vs-doc** drift and **age**, NOT **semantic status-vs-reality**
  drift; both explicitly punt the semantic case to manual review or an LLM. The
  durable deterministic substitute is an explicit machine-checkable status field
  tied to a lifecycle event (e.g. "no doc may remain `Proposed` once its lifecycle
  is `Complete`"). (https://fiberplane.com/blog/drift-documentation-linter/,
  https://dosu.dev/blog/score-documentation-freshness-in-ci) Pitfall: never infer
  "status is wrong" from age/git-delta alone — a doc can be old-and-correct or
  fresh-and-lying.

## Domain & Prior Art

The cortex repo already embodies the cross-cutting external takeaway — a thin
deterministic generator (`generate_index.py`) plus separate validators
(`cortex-check-*` gates) — so every new generator should mirror its byte-stable,
atomic-write, sorted-input discipline, and every new validator should pick the
two-mode (`--staged` blocking vs `--audit`/report-only) posture deliberately. The
events-registry pattern (a registry file that every emitted name must back) is the
local analogue for A1's "every `ADR-NNNN` citation must back to a real file."

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A1 ADR citation+proposals auditor (report-only) | S | Scope-creep against the prose-only posture if made blocking | Clone `cortex-requirements-parity-audit` shape; wire `--audit` only |
| A1.iv ADR area-tag backfill (data chore) | S | Low; touches frontmatter of 10 ADR files | Decide the `area:` enum (already drafted in #224) |
| B1 requirements file→section index generator | M | Glob precedence / silent no-match; consumer-config ownership smell | Define glob→section schema; consumer-owns-config clause |
| B2 cross-lifecycle phase index generator | M | Ordering nondeterminism; index staleness | Reuse `detect_lifecycle_phase()`; byte-stable like `generate_index.py` |
| B3 consumer always-loaded ratchet template | M | Overstep into consumer root docs (ADR-0008) | Maintainer decision on destination (under `cortex/` vs root) |
| B4 opt-in lifecycle archive verb | S/M | Destructive op on uncommitted state | Skip-on-dirty guard; soften `complete.md:274`; scanner already skips `archive/` |
| B5a research/decision-doc status convention | M | Touches authoring discipline + backfill across many docs | Schema + authoring-skill update; the precondition for any detector |
| B5b stale-status detector | M/L | Semantic drift is hard; high false-positive risk | **Blocked-by B5a** (convention must exist + be populated first) |
| C1 overnight per-run `--exclude` flag | S | Footgun if persisted; keep transient | Thread a per-invocation exclude set through `select_overnight_batch` |
| C2 backlog index spec-column hyperlink | XS | None material | One-line edit at `generate_index.py:234` |

## Architecture

<!--
Pieces are named by role. Each piece maps to exactly one backlog ticket in the
Decompose phase, grouped under its epic. The dropped candidate (A1 next-free-number
helper) is recorded under Decision Records, not as a piece.
-->

### Pieces

- **ADR citation+proposals auditor** (Epic A) — a report-only `cortex-check-adr-citations`
  that verifies every `ADR-NNNN`/`adr/NNNN` reference resolves to a real
  `cortex/adr/NNNN-*.md`, flags numbering gaps/collisions, and (proposals sub-mode)
  scans `specify.md`'s `### Proposed ADR: <NNNN-slug>` entries for unfiled/colliding
  numbers. Informational, never blocking — modeled on `cortex-requirements-parity-audit`.
- **ADR area-tag backfill** (Epic A) — the never-filed data chore the ADR README's
  defer-note promises: define the `area:` enum and backfill it across the 10 existing
  ADR frontmatters. Standalone; does not depend on the auditor.
- **Requirements file→section index generator** (Epic B) — a byte-deterministic
  `cortex-generate-requirements-index` emitting INDEX.json/INDEX.md from a
  consumer-owned glob→section config; cortex ships the schema + generator only.
- **Cross-lifecycle phase index generator** (Epic B) — a byte-deterministic
  `cortex-generate-lifecycle-index` that sweeps all lifecycle dirs, infers each
  phase via the existing `detect_lifecycle_phase()`, and emits a phase-grouped index
  that morning-review/dashboard can consume.
- **Consumer always-loaded budget ratchet template** (Epic B, MAINTAINER-CONFIRM) —
  a ratchet (measurement + baseline test) for a consumer's always-loaded surface,
  scaffolded as a template UNDER `cortex/` per the ADR-0008 seam.
- **Opt-in lifecycle archive verb** (Epic B) — an explicit `cortex lifecycle archive
  <slug>` plus a softening of `complete.md` to "do not AUTO-archive unless requested";
  skip-on-dirty.
- **Research/decision-doc status convention** (Epic B) — establish a machine-checkable
  `status:` frontmatter convention on research/decision docs, set at Complete. The
  precondition for any drift detection.
- **Stale-status detector** (Epic B, blocked-by the status convention) — a
  report-only cross-reference of doc `status:` against ship reality (backlog/lifecycle);
  low priority, deferred until the convention has adoption.
- **Overnight per-run exclude flag** (Epic C) — a transient `--exclude <slug>`
  per-invocation CLI flag threaded through `select_overnight_batch`; no new
  persistent frontmatter field.
- **Backlog index spec-column hyperlink** (Epic C) — render the spec column as a
  markdown link to `item["spec"]` instead of a bare checkmark.

### How they connect

The two Epic-A pieces share only the word "ADR": the auditor is a validator over
existing references; the area-backfill is a one-time data chore. They are
independent tickets with no blocked-by edge.

The Epic-B generators (requirements index, lifecycle index) are siblings that both
clone `generate_index.py`'s byte-stable discipline but read different corpora and
are otherwise independent. The **opt-in archive verb pairs with the cross-lifecycle
index** (pairs-with, not blocked-by): archiving changes which dirs the index should
sweep, so they interact but neither strictly blocks the other. The **status
convention blocks the stale-status detector** (hard blocked-by): the detector has
nothing to compare against until the convention exists and is populated. The
**consumer ratchet template** stands alone but its destination is a maintainer
decision (under `cortex/` fits the seam; root docs overstep ADR-0008).

The two Epic-C pieces are independent one-file fixes. C1's boundary depends on
staying transient (a per-run flag), deliberately NOT recreating the persistent-park
footgun the existing `status: abandoned` / `deferred`-tag split already handles.

## Decision Records

- **A1 stays report-only, not blocking.** The ADR README makes a deliberate,
  three-ground argued case for prose-only enforcement `[cortex/adr/README.md:11-17]`,
  invoking the CLAUDE.md low-cost-deviation carve-out. A blocking ADR linter would
  contradict a ratified decision and trip the MUST-escalation evidence bar. A
  report-only auditor over dangling references is an observability check that does
  not touch the prose-only emission posture, so it is in-bounds; a blocking gate is
  out-of-bounds unless a maintainer explicitly overturns the README rationale.
- **The next-free-ADR-number helper is DROPPED.** ADRs are contiguous 0001–0010
  with no gaps or collisions, so the helper solves a problem that has never occurred
  in a directory that grows a few files a year — speculative gold-plating against the
  Solution-horizon principle. (The auditor already flags gaps/collisions if they
  ever appear, which covers the real risk.) Recorded here rather than as a piece.
- **A1.iv is its own ticket, not part of the auditor.** The area-backfill is a data
  chore with a different risk class; bundling it into the linter would couple a
  one-time migration to an ongoing validator for no reason.
- **B5 is split.** The original "stale-status detection" candidate conflates
  establishing a status convention (a schema + authoring-discipline + backfill change)
  with detecting drift off it (a scanner that cannot exist until the convention does).
  Filed as two tickets with a hard blocked-by edge; the detector is low-priority and
  may stay deferred given external prior art shows semantic status-drift is not done
  deterministically off-the-shelf.
- **B1/B3 carry an explicit consumer-ownership clause.** Both risk the "cortex
  governs consumer repos" overreach. B1 is filed as "cortex ships generator+schema,
  consumer opts in by providing config"; B3 is flagged maintainer-confirm with the
  evidence that ADR-0008 keeps cortex out of consumer root docs.
- **C1 is a transient CLI flag, not persistent frontmatter.** The codebase already
  distinguishes execution-park (`status: abandoned`) from view-park (`deferred` tag);
  a per-run exclude is the simpler, footgun-free fit per Solution-horizon. Persistent
  frontmatter is reserved only for a permanently-never-overnight need, which is not
  evidenced.

## Open Questions

- **B3 destination (maintainer-confirm):** scaffold the ratchet template strictly
  UNDER `cortex/` (fits the ADR-0008 seam, like #289's `cortex/.gitignore`), or also
  add a `--check-always-loaded` mode to `cortex-measure-l1-surface` that *reads* (but
  never writes) a consumer's `CLAUDE.md`/`MEMORY.md`? The read-only measurement mode
  may be a defensible middle path that doesn't write consumer docs.
- **B5 enforcement point (maintainer-confirm):** is the stale-status detector wanted
  at all once it's clear it must be report-only and semantic drift is hard, or should
  only the status convention (B5a) be filed and the detector left as a documented
  "inherently manual" note?
- **B2 consumer:** does the cross-lifecycle index feed morning-review, the dashboard,
  or both — and does that consumer choice change the emitted schema? (Not blocking for
  filing; sizes the ticket.)
- Brief-provenance corrections to carry forward: the brief's "OPEN tickets" list is
  stale (#270/#273/#271 are `complete`, #156 `deferred`), and its C1 workaround
  citation conflates archive-abort `git checkout -- .` with batch exclusion. Neither
  changes a filing decision, but downstream tickets must not cite them as fact.
