# Research: Coordinated docs cleanup for installer-audience share-readiness (#166)

## Epic Reference

Parent epic: [`backlog/165-repo-spring-cleaning-share-readiness-epic.md`](../../backlog/165-repo-spring-cleaning-share-readiness-epic.md). Discovery research: [`research/repo-spring-cleaning/research.md`](../../research/repo-spring-cleaning/research.md). #166 is one of three siblings (166/168/169) carrying out the post-plugin-shift cleanup; this ticket owns the docs/ + README + setup.md domain. The epic ratifies DR-1 Option B (aggressive README cut), DR-3 Option B (only `pipeline.md`/`sdk.md`/`mcp-contract.md` move to `docs/internals/`), and OQ §6 (cut What's Inside).

## Codebase Analysis

### README.md (132 lines) — body's line citations all verified accurate

| Range | Content | Disposition |
|-------|---------|-------------|
| L11–29 | ASCII pipeline diagram + tier/criticality legend | CUT |
| L31–35 | Prerequisites | KEEP |
| L36–50 | Quickstart 3-step block | KEEP |
| L52–54 | Plugin auto-update mechanics + extras-tier callout | CUT (move to setup.md) |
| L56 | Verification pointer to setup.md | KEEP |
| L58–71 | Plugin roster table | KEEP (trim header/footer prose) |
| L73–75 | Authentication H2 | CUT (fold into Documentation index row) |
| L77–88 | What's Inside table | CUT |
| L89–91 | Customization H2 | CUT (move to setup.md) |
| L93–100 | Distribution H2 | CUT (move to setup.md) |
| L102–115 | Commands H2 | CUT (move to setup.md) |
| L117–128 | Documentation index | KEEP (expand for Auth row + `docs/internals/` paths) |
| L130–132 | License | KEEP |

### docs/setup.md (437 lines) — gap analysis vs hard prerequisite

| Required (must land BEFORE README cut) | Status in setup.md today |
|----------------------------------------|--------------------------|
| `uv tool uninstall uv` foot-gun warning | **ABSENT** |
| `uv run` user-project semantics note | **ABSENT** |
| Forker fork-install URL pattern (`uv tool install git+https://github.com/<your-fork>/...`) | **ABSENT** (the word "forker" appears at L327 in the statusline section, not install context) |
| Top-level "Upgrade & maintenance" section | **PARTIAL** — `#### Upgrading` subsection lives at L40-47 under "Install the cortex CLI"; needs elevation |
| Customization rule (settings.json ownership) | **PRESENT** at L272 / L276 |
| Commands subsection (cortex CLI subcommand listing) | **ABSENT** — string `cortex overnight start` does not appear |
| `cortex --print-root` verification command | **PRESENT** at L52, L203, L207 |

setup.md trim targets (F-2):
- L99 Per-repo setup heading; L107–128 `cortex init` 7-step explainer (collapse)
- L130 `lifecycle.config.md` schema heading; L132–160 schema (compress / move to reference card)
- L352–388 Per-repo permission scoping § / `CLAUDE_CONFIG_DIR` (decide retain vs forker-tier section)

### docs/plugin-development.md (105 lines) — gap for backlog.md trim migration

Both target rules **ABSENT**:
- (a) `Path.cwd()` vs `Path(__file__).parent` rule for repo-local dirs — string `Path.cwd` does not appear; `Path(__file__)` does not appear.
- (b) Per-script bin-deployment mechanism — doc covers build-output plugin assembly (L12–14 references `bin/cortex-*` as top-level source) but not the per-script deployment workflow.

Natural insertion point: new `## Adding a deployable bin script` section after current `## Iterating on plugin source` (L96–105). Alternative slot: between `## Building plugins` (L43) and `## Registering the local marketplace` (L54).

### Skill-table overlap (F-4)

100% overlap confirmed across 14 skills (dev, lifecycle, refine, overnight, morning-review, discovery, backlog, research, commit, pr, critical-review, requirements, fresh, retro, evolve, diagnose).
- `docs/skills-reference.md` skill inventory spans L14–166.
- `docs/agentic-layer.md` skill tables span L17–62.
- `skills-reference.md` has a `harness-review` project-local note at L155–157 that agentic-layer.md lacks (minor extra in canonical; not a discrepancy in dedup direction).

**Migration callout text** (verbatim from agentic-layer.md:64) — must move to skills-reference.md before agentic-layer.md trim:

> **Note on `pipeline`:** `pipeline` is not a user-facing skill and has no entry in `skills/`. It is an internal Python orchestration module (`cortex_command/pipeline/`, `cortex_command/overnight/`) invoked automatically by `/overnight` to manage multi-feature batch execution. Use `/overnight` to trigger pipeline behavior; do not invoke `pipeline` directly.

### Bash-runner terminology drift sweep — verified hit list

**User-facing prose (in scope per body)**:
- `docs/overnight.md:8` — "launch a bash runner"
- `docs/agentic-layer.md:187` — "a bash runner detaches in a tmux session"
- `docs/agentic-layer.md:313` — "The bash overnight runner writes execution state"
- `docs/skills-reference.md:59, 71` — "hands off to the bash runner"
- `skills/overnight/SKILL.md:3, 22, 391, 400, 401` — description and protocol prose
- `skills/overnight/SKILL.md:198` — references `runner.sh:179` (broken pointer; runner.sh does not exist)
- `skills/diagnose/SKILL.md:62` — debugging example
- `docs/sdk.md:179` — "`runner.sh` checks both `settings.json` and `settings.local.json`" (in-scope; sdk.md is moving to docs/internals/ in same commit)

**Body's `agentic-layer.md:183` citation correction**: confirmed L183 does not contain bash-runner terminology in current state; drop from line-anchored list and rely on grep sweep.

**`docs/overnight-operations.md` (23 occurrences of `runner.sh`)** — the doc owns "round loop / orchestrator" content per CLAUDE.md:50 and uses `runner.sh` as operator-vocabulary glossary in file-and-state inventories (e.g., L81 table row, L396 file-table `lifecycle/.runner.lock | runner.sh`). **Open question for Spec**: explicit carve-out from sweep with rationale, vs include in #166's sweep scope.

**`cortex_command/overnight/prompts/orchestrator-round.md`** runtime narration at L8, L20, L486 ("bash runner will invoke `batch_runner.py`") — agent's mental model is "exit and parent process resumes batch runner"; language of parent is operationally invisible to spawned agent. Substitution low-risk.

**Internal port-provenance** (`# Mirrors runner.sh:N` comments in `cortex_command/overnight/*.py`, ~30+ sites) — historical metadata pointing to where Python code came from. Body's "out of user-facing scope (acceptable to leave)" rationale is defensible; deferred to follow-on ticket.

### Cross-reference grep `docs/{pipeline,sdk,mcp-contract}.md` (no file-glob filter) — full live-source hit list

| Path | Line | Type | Edit needed |
|------|------|------|-------------|
| `README.md` | 127 | Documentation index row | YES (atomic with cut) |
| `CLAUDE.md` | 50 | doc-ownership convention | YES (path update) |
| `bin/cortex-check-parity` | 59 | script comment | YES |
| `plugins/cortex-core/bin/cortex-check-parity` | 59 | auto-mirror | regenerates via `just build-plugin` |
| `cortex_command/cli.py` | 268 | runtime stderr (user-facing) | YES (path or canonical-URL form) |
| `docs/overnight-operations.md` | 318, 326, 339 | bareword `(sdk.md)` link | YES (`(internals/sdk.md)`) |
| `docs/overnight-operations.md` | 593, 599 | prose mention `docs/pipeline.md` | YES |
| `docs/mcp-server.md` | 9 | bareword `pipeline.md`, `sdk.md` siblings | **YES — Adversarial finding #1: this site was UNDER-enumerated in body L86** |
| `docs/pipeline.md` | 13 | bareword `(sdk.md)` link | NO (both files move together to docs/internals/) |

Out of scope: `research/repo-spring-cleaning/research.md`, `lifecycle/archive/...`, archived backlog items.

### docs/internals/ relocation context

- **Zero docs subdirs in repo currently** (verified via `find docs -mindepth 2 -type f`). This ticket establishes the precedent.
- Cross-doc reference convention inside `docs/`: bareword relative (`[label](sibling.md)`).
- From top-level (README.md, CLAUDE.md) and code/scripts: `docs/`-prefixed.
- Breadcrumb pattern at line 1 of each doc: `[← Back to README](../README.md)`; relocated docs/internals/ files need `(../../README.md)`.

### bin/cortex-check-parity SCAN_GLOBS

Verified the tuple at L69–79 includes `"docs/**/*.md"` (recursive). Python `Path('docs').glob('**/*.md')` traverses subdirs — `docs/internals/*.md` is **auto-picked-up; no SCAN_GLOBS edit needed**. The relocation is parity-gate-transparent.

### cortex_command/cli.py argparse pattern (for dashboard verb feasibility)

- `_build_parser` at L274
- Subparsers added via `subparsers.add_parser(...)` for `overnight` (L309), `mcp-server` (L588), `init` (L600), `upgrade` (L628)
- Each registers a `_dispatch_*` handler via `set_defaults(func=...)`
- A `dashboard` subcommand would slot between L598 and L600 (or after `upgrade`).

**Wraps**: `uv run uvicorn cortex_command.dashboard.app:app --host 0.0.0.0 --port {{dashboard_port}}` (justfile L100–113).

**Dashboard module**: `cortex_command/dashboard/app.py` defines the FastAPI app; deps (`fastapi`, `uvicorn[standard]`, `jinja2`) ship in `[project.dependencies]` at `pyproject.toml:11–13` — **NOT in `[dependency-groups.dev]`**. Installed wheels carry runtime deps; the dashboard CAN run from an installed wheel. Agent 5 corrected Agent 4's "structurally contributor-tier" framing on this point.

**Realistic verb LOC**: ~25–40 lines (argparse + handler with PID-file path resolution, port flag handling, signal forwarding). Agent 1's "~15 LOC" estimate is conservative.

**PID-file packaging risk**: `just dashboard` writes PID to `cortex_command/dashboard/.pid` (justfile L104) — inside the package directory. **Installed-wheel installations cannot write into the wheel's installed location.** Any `cortex dashboard` verb implementation MUST move the PID file to `~/.cache/cortex/dashboard.pid` or `$XDG_RUNTIME_DIR/cortex-dashboard.pid` (XDG-compliant). Not a follow-up — blocking for Option 1.

### Atomic-landing constraint — minimum commit-1 edit list

The README's Documentation index at L127 must point at relocated paths in the same commit as the relocations. Minimum commit-1 group:
1. `docs/pipeline.md` → `docs/internals/pipeline.md` (file move + breadcrumb update)
2. `docs/sdk.md` → `docs/internals/sdk.md` (file move + breadcrumb update)
3. `docs/mcp-contract.md` → `docs/internals/mcp-contract.md` (file move + breadcrumb update)
4. `CLAUDE.md:50` doc-ownership rule path updates
5. `cortex_command/cli.py:268` runtime stderr path update (or canonical-URL conversion — see Open Questions)
6. `bin/cortex-check-parity:59` comment update
7. `plugins/cortex-core/bin/cortex-check-parity:59` mirror regenerated by pre-commit hook
8. `docs/overnight-operations.md` L318/L326/L339 (bareword `(sdk.md)` → `(internals/sdk.md)`)
9. `docs/overnight-operations.md` L593/L599 prose mentions
10. `docs/mcp-server.md:9` bareword pipeline.md/sdk.md siblings (Adversarial finding #1 — adds to body's enumeration)
11. `docs/pipeline.md:13` (the moved file) — internal forward-link to `(sdk.md)` resolves correctly inside docs/internals/ since both move together; **no edit required**
12. README.md:127 Documentation index updated to `docs/internals/pipeline.md` etc.

### Pre-commit hook behavior for canonical → mirror regeneration

`.githooks/pre-commit` Phase 2 triggers `BUILD_NEEDED=1` when staged paths match `^(skills/|bin/cortex-|hooks/cortex-|claude/hooks/cortex-)`. Editing `bin/cortex-check-parity:59` triggers BUILD_NEEDED. Phase 3 runs `just build-plugin` and Phase 4 detects drift.

**Risk**: if user stages canonical AND plugin mirror simultaneously with inconsistent contents, Phase 3 regenerates the mirror, overwriting the manual edit. Plan-phase guidance: edit only canonical sources; let the pre-commit hook regenerate the mirror; do NOT stage `plugins/cortex-core/bin/*` manually.

## Web Research

### README target-shape benchmarks

| Project | Lines | Pitch words | Pattern |
|---------|-------|-------------|---------|
| `astral-sh/uv` | ~520 | 11 | pitch → highlights → install → docs → features → contrib → FAQ → license (outlier marketing) |
| `jdx/mise` | ~240 | 22 | pitch → demo → quickstart → docs index → community → credits |
| `cli/cli` (gh) | ~180 | 44 | pitch → docs → contrib → install → comparison |
| `digitalocean/doctl` | (with auth section) | ~12 | + dedicated auth section |
| `superfly/flyctl` | (lean) | ~10 | + one-line auth in quickstart |

**Standard pattern**: pitch → install → quickstart → docs index → contrib → license. None exceed a single-screen above-fold before linking out. Cortex's ~80-line target is well-aligned with `gh` (~180) and `mise` (~240) once narrower-coverage normalization applies.

### docs/internals/ subdir convention

- Established but uncommon. Concrete prior art: TigerBeetle's `docs/internals/` (architecture/VSR/sync/storage with explicit "if you are learning the codebase, start here" framing); HyperDbg's `docs/design/debugger-internals/`.
- Dominant convention is audience-based folders (`user/`, `admin/`, `development/`).
- `docs/dev/` is more common than `docs/internals/`, but `internals/` is semantically clearer for "implementation reference, not contributor guide."
- Filename-prefix approach (e.g., `_pipeline.md`) unseen in OSS — Python module-privacy convention does not transfer to Markdown.

### Authentication in CLI READMEs

| Tool | Auth in README | Depth |
|------|----------------|-------|
| `gh` | No | Pushes to `gh auth login` man page |
| `doctl` | Yes | ~80-line dedicated section (multi-step token flow) |
| `flyctl` | Single line | `fly auth login` in Getting Started |
| `mise` / `uv` | N/A | No auth needed |

No consistent convention. Split correlates with one-step (interactive) vs multi-step (token + config). For one-step `cortex init` flow, a single line in quickstart is sufficient and on-precedent — folding Auth into a Documentation index row matches `gh`.

### Skill-table dedup pattern

- No widely-adopted Markdown OSS solution. Three approaches surveyed:
  1. **Generated docs** (e.g., gh from cobra command definitions) — best for size; requires generator infrastructure.
  2. **Single canonical table + cross-links** (mkdocs/GitLab pattern) — most common in prose-docs OSS.
  3. **Self-contained per-doc tables with manual sync** — the trap cortex is in.
- Recommend pick a canonical home (skills-reference.md) and link from elsewhere. Generation is overkill at current scale.

### CHANGELOG broken-reference patterns

Neither keepachangelog.com nor common-changelog.org address this directly. Common Changelog FAQ permits historical edits ("a changelog is a historical record and a useful reference"). Practical conventions: silently replace broken refs (most common), trailing notes ("formerly docs/install.md, now in docs/setup.md"), strikethrough (rare). Cortex's `docs/install.md` reference (which never existed) is a "fix the typo" case.

### Documentation reorganization mid-project

For repo-only Markdown docs (cortex's case): just move and update the docs index. External-link breakage is generally accepted. Breadcrumb stubs (one-line "moved to X" files at old path) are seen but uncommon — pollute the tree.

### Dashboard verb pattern in CLI tools

**Strong convention favors CLI verb** for tools shipping a web UI:
- `mlflow ui`, `wandb server`, `prefect server start`, `airflow webserver`, `streamlit run`, `jupyter notebook`/`jupyter lab`.

Treating dashboard as contributor-only is **off-pattern** for tools that are user-facing. Per Adversarial finding #4: cortex's dashboard ships in installer wheel deps, so the technical blocker (Agent 4's "requires just / project venv" framing) is incorrect — the actual blocker is the in-package PID file location.

### README pitch length

- uv: 11 words; mise: 22; doctl: ~12; flyctl: ~10; gh: 44.
- General guidance (makeareadme.com, banesullivan/README): "2–3 paragraphs, 3–5 lines each".

Cortex's current ~120 words / 3 paragraphs is at the upper end. Lean models pair a tight tagline (~50–80 words / 1 paragraph) with a separate "What it does" bullet list. Trimming the pitch is on-precedent.

## Requirements & Constraints

### project.md L7 (audience and distribution model)

> "Distributed CLI-first as a non-editable wheel installed from a tag-pinned git URL (`uv tool install git+<url>@<tag>`); cloning or forking the repo remains a secondary path for advanced users who want to modify the source."

Already encodes installer-primary, forker-secondary. F-12 dropped post-critical-review per discovery; **no edit to L7 needed**. Epic #165 L52 quotes a stale "shared publicly for clone or fork" phrasing — that is the discovery's working interpretation, not the live L7 text. Spec must re-quote project.md directly to avoid stale-quote propagation.

### project.md L56 (out of scope)

> "Published packages or reusable modules for others — the `cortex` CLI ships as a non-editable wheel installed from a tag-pinned git URL via `uv tool install git+<url>@<tag>`; PyPI publication remains out of scope."

Reaffirms installer-primary distribution.

### CLAUDE.md L50 doc-ownership rule (verbatim)

> "Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/pipeline.md` owns pipeline-module internals, and `docs/sdk.md` owns SDK model-selection mechanics. When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content."

Path citations: `docs/overnight-operations.md`, `docs/pipeline.md`, `docs/sdk.md`. Two of three move to docs/internals/; rule's path citations must update in same commit. Body's "CLAUDE.md:34" reference in suggested-sequencing § is **stale** (round 2 corrected to L50).

### CLAUDE.md L68 — 100-line cap policy

CLAUDE.md is currently **68 non-empty lines**. The L50 path-update edit is path-substitution-only and does not increase line count. **No risk of crossing 100-line cap** from #166's planned changes. Receiver edit per policy if exceeded: extract OQ3 + OQ6 (+ new entry) to `docs/policies.md`, leave CLAUDE.md with a single pointer line. Plan-phase must re-test cap after any "while we're here" CLAUDE.md additions.

### CLAUDE.md L52 — MUST-escalation policy

Ticket plans **no new MUST/CRITICAL/REQUIRED escalations**. Body's "must" usage ("setup.md must gain", "must update or installers see broken-link error") is descriptive prerequisite/acceptance language, not normative directives added to CLAUDE.md, skills, or hooks. **Policy not engaged for this ticket.**

### Parent epic enumeration of #166 vs ticket-#166 scope

**Epic enumeration** (backlog/165-...md:29): "README rewrite + setup.md content migration + docs/ reorganization + skill-table dedup + stale-path fixes; aggressive ~80-line cut; move Customization/Distribution/Commands H2s; cut What's Inside + ASCII legend; move pipeline/sdk/mcp-contract.md to docs/internals/; merge agentic-layer skill table into skills-reference; fix `requirements/pipeline.md:130`, `CHANGELOG.md:21-22`, `docs/agentic-layer.md:183,187,313`. Hard prerequisite: setup.md must gain `uv run` semantics, uv-self-uninstall foot-gun, fork-install URL, Upgrade & maintenance subsection, Customization content, and Commands subsection BEFORE the README cut commit lands."

**Round-2 expansions in #166 NOT in epic enumeration** (ratified by user via consolidation commit c019e97 "Consolidate #166+#167 and apply round 2 audit findings"):
- Broader bash-runner sweep (skills/overnight/SKILL.md 5 sites, skills/diagnose/SKILL.md, docs/overnight.md, docs/skills-reference.md L59/71)
- Code references (`cortex_command/cli.py:268`, `bin/cortex-check-parity:59` + plugin mirror)
- Cross-references (overnight-operations.md L318/326/339/593/599, mcp-server.md:9, pipeline.md:13)
- Pipeline-not-a-skill callout migration (agentic-layer.md:64 → skills-reference.md)
- docs/backlog.md "Global Deployment" trim with substantive migration to plugin-development.md
- Stale-path additions (scripts/validate-callgraph.py:12, skills/requirements/references/gather.md:201, backlog/133-...md:56)
- docs/dashboard.md policy decision (epic L48 lists this as deferred; #166 incorporates resolution mechanics)
- docs/setup.md trim (F-2)
- CLAUDE.md L50 line-citation correction (round 2)

### Discovery research decisions ratified

- **DR-1 Option B**: Aggressive README cut to ~80 lines; cut all of L11-29 (ASCII + legend); move Customization/Distribution/Commands H2s; cut What's Inside; fold Auth into docs index. Hard prereq: setup.md must gain four pieces of content BEFORE the cut commit.
- **DR-3 Option B**: Move only `pipeline.md`/`sdk.md`/`mcp-contract.md` to `docs/internals/`. Leave `plugin-development.md` + `release-process.md` at `docs/` root (forkers/contributors do read them).
- **DR-4 Option A** (governs **#168 not #166**, but parallel-landing coordination required since DR-4 retires `requirements/project.md:36` `output-filters.conf` mention).
- **OQ §6 cut What's Inside entirely**: rationale = installer pre-install evaluation does not need a repo-structure tour; CLI-bin row drift is unenforced and recurring (itself the cut rationale).
- **OQ §7 P-A**: forker affordances stay; out-of-scope guardrails: `install.sh` `CORTEX_REPO_URL`, `setup-githooks` recipe, dual-source enforcement, statusline manual-wire path, `requirements/project.md:7` clone-or-fork language NOT to be touched.
- **OQ §4 dashboard verb policy**: NO preference recorded in research; user-decision deferred to lifecycle plan phase.
- **DR-2 Option C**: visibility cleanup deferred (governs **#169 not #166**).

### Defense-in-depth / sandbox-preflight gate

`bin/cortex-check-parity` extends sandbox-preflight validation when staged diffs touch sandbox-source files (`cortex_command/overnight/sandbox_settings.py`, `cortex_command/pipeline/dispatch.py`, `cortex_command/overnight/runner.py`, `pyproject.toml`). #166 does not touch any sandbox-source file → preflight gate not engaged. The L59 comment edit is canonical-source + plugin-mirror regenerate, governed by the dual-source pre-commit hook.

### Tags / areas conventions

- Canonical area: `areas: [docs]`
- Conventional tags: `repo-spring-cleaning`, `share-readiness`, `documentation`, `cleanup` (epic) plus `readme`, `setup`, `stale-paths` (child).

## Tradeoffs & Alternatives

### Sequencing — recommended approach

Body's 9-step order is fundamentally sound. Recommended adjustment: collapse body steps 6+7 (setup.md trim + setup.md additions) into a single setup.md commit so the file's net new shape is reviewable in one diff. **Decouple body steps 8 and 9 against an over-aggressive coupling recommendation** — atomic-landing is satisfied if commit 1 includes the README:127 index path-update; commits 8 (README rewrite) and 9 (final index polish) can be separate.

Reject mega-commit (single 500+ LOC diff) — defeats reviewability; reject 5-PR domain split — breaks atomic-landing across PR boundaries.

### Dashboard policy — the unresolved fork

Three options remain on the table per research/repo-spring-cleaning/research.md:276 and backlog/166-...md:132–138:

1. **Option 1 — ship `cortex dashboard` verb wrapping FastAPI server invocation.** Web research (Agent 2) and Adversarial review (Agent 5 finding #4) both indicate this is on-pattern: mlflow/wandb/prefect/airflow/streamlit all expose dashboard/UI as CLI verbs. fastapi+uvicorn+jinja2 ship in installer wheel deps (`pyproject.toml:11–13`) — **dashboard runs from installed wheel**, not contributor-tier as previously framed. Realistic LOC: 25–40. Blocking redesign: PID-file location must move out of `cortex_command/dashboard/.pid` to XDG-compliant path (installed-wheel writes into package dir fail).

2. **Option 2 — flag contributor-only-launchable; prose edit to docs/dashboard.md only.** Smallest immediate edit. Currently presented in body as "weakens installer-tier feature" with mirror to README L115 contributors-only marker pattern. **Adversarial review challenges this**: dashboard CAN run from installer wheel; framing dashboard as contributor-only papers over a fixable gap rather than addressing it.

3. **Option 3 — cut docs/dashboard.md from installer-facing docs index entirely; mark contributor-tier.** Cleanest installer-facing surface; orphans 137-line doc; signals contributor-tier strongly.

**Research's recommendation**: surface the dependency-fact (fastapi+uvicorn ship in installer wheel) in Spec; acknowledge the Web/Adversarial vs Tradeoffs split; user picks among the three with full information. If Option 1 is chosen, the verb implementation needs PID-file location redesign (XDG-compliant) and is ~25–40 LOC. If Option 2 is chosen, the prose edit lands in commit 6 with a contributor-only marker on the index row in commit 8.

### Skill-table dedup approach — recommended

Body's approach (Alternative E variant): keep skills-reference.md as canonical, trim agentic-layer.md to diagrams + workflow narratives + lifecycle phase map, drop skill-inventory tables. Migrate the pipeline-not-a-skill callout into skills-reference.md before trim.

**Adversarial-flagged refinement**: agentic-layer.md L21 dev-row contains "multi-feature or batch → `/pipeline`" — `/pipeline` is not a real skill (the user-facing trigger is `/overnight`). After trim, audit the dev-row routing language and replace `/pipeline` with `/overnight`. Verify with `grep '/pipeline' docs/skills-reference.md docs/agentic-layer.md` returning no live-routing hits.

**Adversarial-flagged refinement #2**: agentic-layer.md trim should add a single boilerplate "for trigger details, see [docs/skills-reference.md](skills-reference.md)" pointer near the top of the file, since diagrams (L72–117) and workflow narratives (L177–200) reference skill names without on-page definitions after the table is gone.

Programmatic generation (Alternative D) deferred to follow-on if drift recurs.

### docs/backlog.md trim approach — recommended

Body's approach: substantively migrate (a) `Path.cwd()` vs `Path(__file__).parent` rule and (b) per-script bin-deployment mechanism into `docs/plugin-development.md` (new "## Adding a deployable bin script" section after current "## Iterating on plugin source"); cut docs/backlog.md L198-234 "Global Deployment" section; drop the 3-row deployed-scripts table (drift-prone, replaceable by `ls plugins/cortex-core/bin/`).

Reject delete-without-migrate (loses load-bearing rule). Reject new-file approach (splits bin-script knowledge across two docs without clean boundary).

### Bash-runner sweep approach — recommended

Body's user-facing scope is correct for #166's primary domain. Defer broader sweep of `cortex_command/overnight/*.py` live-narration (vs port-provenance) docstrings to follow-on ticket. Don't expand #166 to chase 30+ port-provenance comments.

**Adversarial-flagged refinement**: skills/overnight/SKILL.md:198's `runner.sh:179` line citation is a **broken pointer** (file doesn't exist in live source), not provenance. Correct rewrite is "Handled by the runner on startup" — drop the line citation. Citing equivalent line in `runner.py` would re-invite line-rot.

**Open question for Spec**: explicit carve-out for `docs/overnight-operations.md` (23 occurrences of `runner.sh` in operator-vocabulary file-and-state inventory) — out-of-scope-with-rationale vs include in #166's sweep.

### README target line count — recommended

~80 lines per body / DR-1 Option B / benchmark-aligned with gh and mise.

Reject ~110 lines (keep one section): arbitrary precedent and breaks Documentation-index symmetry.
Reject ~60 lines (drop workflow narrative + plugin roster): both load-bearing for installer pre-install evaluation.

### Internals relocation strategy — recommended

Body's `docs/internals/` subdir. Matches TigerBeetle precedent and `docs/dev/`-style convention used by FastAPI/Pydantic. Establishes clean tier-of-audience signal.

Reject prefix-rename (`_pipeline.md`): not a Markdown convention; doesn't communicate "internal" to casual browsers.
Reject top-level `dev-docs/`: splits documentation surface; no precedent in benchmarks.

### Hard-prereq enforcement — recommended

Body's plan-phase commit ordering (setup.md additions land in commit 7, before README cut in commit 8) + acceptance-signal grep at PR review time (Alternative O — as listed at backlog/166-...md:171–178).

Reject pre-commit hook (Alternative N): conditional-on-README-cut detection is brittle; one-shot prereq, the hook becomes dead weight after merge.

**Adversarial caveat**: PR-review grep is purely lexical — strings inside code-block "do not run this" examples could pass the grep without preserving warning context. If formal verification is required, augment with `grep -B2 'uv tool uninstall uv' docs/setup.md | grep -i 'foot-gun\|warning\|do not\|never'` or rely on PR-review human inspection.

### Recommended overall implementation approach

8-commit single-PR sequence (collapsed slightly from body's 9; decoupled per Adversarial vs Tradeoffs):

1. **Move 3 docs to docs/internals/**: `pipeline.md`, `sdk.md`, `mcp-contract.md` (with breadcrumb updates) + cross-ref updates: CLAUDE.md:50, cortex_command/cli.py:268, bin/cortex-check-parity:59, docs/overnight-operations.md L318/326/339/593/599, docs/mcp-server.md:9 (Adversarial-added), README.md:127 path. Plugin mirror regenerated by pre-commit hook.
2. **Trim agentic-layer.md skill tables**: migrate pipeline-not-a-skill callout to skills-reference.md FIRST; rewrite `/pipeline` → `/overnight` at dev-row L21; add top-of-file pointer to skills-reference.md.
3. **Stale-path fixes** (5 sites): requirements/pipeline.md:130, CHANGELOG.md:21-22, scripts/validate-callgraph.py:12, skills/requirements/references/gather.md:201, backlog/133-evaluate-implementmd180-progress-tail-narration-under-opus-47.md:56.
4. **User-facing bash-runner terminology sweep**: docs/overnight.md:8, docs/agentic-layer.md:187/313, docs/skills-reference.md:59/71, skills/overnight/SKILL.md:3/22/198/391/400/401, skills/diagnose/SKILL.md:62. SKILL.md:198 drops the `runner.sh:179` line citation.
5. **Migrate docs/backlog.md L198-234 to docs/plugin-development.md**: substantively migrate Path.cwd() rule and bin-deployment mechanism; cut Global Deployment section from backlog.md; drop deployed-scripts table.
6. **Resolve docs/dashboard.md policy**: prose edit per chosen option (1, 2, or 3). If Option 1: implement `cortex dashboard` verb in cli.py with XDG-compliant PID file (~25–40 LOC). If Option 2: prose edit only, marker on docs index row in commit 8. If Option 3: cut from index in commit 8.
7. **docs/setup.md (combined trim + additions)**: collapse `cortex init` 7-step explainer; compress `lifecycle.config.md` schema; decide CLAUDE_CONFIG_DIR § fate; ADD: `uv run` user-project semantics, `uv tool uninstall uv` foot-gun, forker fork-URL pattern, Upgrade & maintenance subsection (elevation from #### Upgrading at L40-47), Customization content from README L89-91, Commands subsection.
8. **README rewrite to ~80 lines + Documentation index**: cut L11-29 (ASCII+legend), L52-54 (auto-update+extras), L73-75 (Authentication H2), L77-88 (What's Inside), L89-91 (Customization), L93-100 (Distribution), L102-115 (Commands); trim pitch toward ~50–80 words; expand Documentation index (Authentication row, Upgrade & maintenance row, internals/ paths, dashboard contributor-only marker if Option 2).

## Adversarial Review

### Confirmed corrections to body and prior agent findings

1. **`docs/mcp-server.md:9` was UNDER-enumerated in body L86**. Bareword sibling refs `pipeline.md` and `sdk.md` resolve to docs/-root today; after relocation they 404. Adversarial added to commit-1 edit list.
2. **Dashboard "structurally contributor-tier" claim is factually wrong** — fastapi+uvicorn+jinja2 are in `[project.dependencies]` at pyproject.toml L11–13 (NOT `[dependency-groups.dev]`). Installer wheel ships dashboard runtime deps. The actual blocker for Option 1 is the in-package PID file location (`cortex_command/dashboard/.pid`), not a missing dependency. **Recommendation**: pin Option-1-or-not decision to dependency fact, not to Agent 4's contributor-tier framing.
3. **skills/overnight/SKILL.md:198 references `runner.sh:179`** — `runner.sh` does not exist in live source. This is not provenance citation; it's broken documentation. Correct rewrite: "Handled by the runner on startup" with line-citation REMOVED.
4. **agentic-layer.md L21 dev-row "→ /pipeline"** — `/pipeline` is not a real skill. Trim must replace with `/overnight` (the user-facing trigger).
5. **CLAUDE.md 100-line cap re-test required** after any "while we're here" CLAUDE.md additions. Currently 68 lines; pure path-substitution at L50 is line-count-neutral, but additions accumulate.
6. **Pre-commit hook canonical-vs-mirror race**: do NOT stage `plugins/cortex-core/bin/*` manually; let the hook regenerate. Manual mirror edits get overwritten by Phase 3 of the hook.
7. **cli.py:268 stderr "see docs/mcp-contract.md"** — relative path is unfollowable when user runs `cortex upgrade` outside a cortex-command checkout. Open question: convert to canonical GitHub URL form rather than `docs/internals/mcp-contract.md`.
8. **docs/overnight-operations.md 23 instances of `runner.sh`** — operator-vocabulary glossary in the doc that owns runner round-loop content. Open question: explicit carve-out from #166 sweep with rationale, vs include.

### Documentation-index ordering after relocation

Body does not specify whether `docs/internals/` rows in README Documentation index sit (a) inline with an "(internal)" tag, (b) demoted to a small subtable below the main index labeled "For maintainers/forkers", or (c) dropped from index entirely (discoverable only via in-doc links). Convention check: gh's docs index doesn't separate; uv's does (small "Development" subtable). **Open question for Spec**.

### Hard-prereq grep verification — necessary not sufficient

Acceptance signals are purely lexical. Future edits could move strings into code-block "do not run this" examples, passing the grep while the warning context evaporates. Augment with co-occurrence check or rely on PR-review human inspection (recommended path).

### F-5 stale-path fix at scripts/validate-callgraph.py:12 — scope-of-edit unspecified

Body says "Update or remove the parenthetical reference" but doesn't specify which: keep rule and drop citation? Drop the rule? Cited file (`claude/reference/claude-skills.md`) was retired in #117. **Open question for Spec**: drop parenthetical, keep rule statement; file follow-up if rule re-grounding needed.

### backlog/133-...md frontmatter audit

The body fix targets line 56 markdown link target. But backlog/133 also has `lifecycle_slug: ...` frontmatter referencing the same archived path. Indexer reads frontmatter; check whether `lifecycle_slug` resolves correctly to `lifecycle/archive/...` by indexer logic, or whether the frontmatter needs an `archived:` annotation / explicit prefix.

### CLAUDE.md L50 doc-ownership rule edit must be path-substitution-only

Don't expand the rule with "see also `docs/internals/`" guidance during plan-phase — that risks crossing the 100-line cap and triggering the receiver-edit cascade (extract OQ3+OQ6 to `docs/policies.md`, leave pointer in CLAUDE.md). The edit should be 2-character-substitutions: `docs/pipeline.md` → `docs/internals/pipeline.md`, `docs/sdk.md` → `docs/internals/sdk.md`. Net line-count delta = 0.

## Open Questions

These items require decision in the Spec phase before plan-phase implementation. All are deferred-with-written-rationale, not unresolved gaps.

1. **Dashboard policy resolution** (Option 1 ship verb / Option 2 contributor-only-launchable / Option 3 cut from installer index): Web research and Adversarial review challenge Agent 4's Option 2 recommendation. Surface dependency fact (fastapi+uvicorn ship in installer wheel) in Spec; user picks with full information. **Deferred: resolved during Spec phase user interview.**
2. **`docs/overnight-operations.md` bash-runner sweep scope**: explicit carve-out from #166 sweep with rationale (operator-vocabulary glossary in doc that owns runner round-loop content per CLAUDE.md:50), vs include in scope. **Deferred: resolved during Spec phase user interview.**
3. **`cortex_command/cli.py:268` stderr message form**: relative path `docs/internals/mcp-contract.md` (current pattern), vs canonical GitHub URL form (`https://github.com/charleshall888/cortex-command/blob/main/docs/internals/mcp-contract.md`) — user runs `cortex upgrade` from arbitrary cwd, cannot resolve repo-relative paths. **Deferred: resolved during Spec phase user interview.**
4. **README Documentation index layout for `docs/internals/` rows**: (a) inline with "(internal)" tag, (b) demoted to small subtable labeled "For maintainers/forkers", (c) dropped from index entirely. Convention varies (gh inline; uv subtable). **Deferred: resolved during Spec phase user interview.**
5. **`scripts/validate-callgraph.py:12` rewrite scope**: drop parenthetical citation and keep rule statement (recommended), vs drop the rule entirely. `claude/reference/claude-skills.md` retired in #117 with no replacement. **Deferred: resolved during Spec phase user interview.**
6. **`cortex_command/overnight/prompts/orchestrator-round.md` "bash runner will invoke" prompt strings** at L8/L20/L486: sweep (low confusion risk per Agent 1's analysis) vs leave as port-provenance. **Deferred: resolved during Spec phase user interview.**
7. **`backlog/133-...md` `lifecycle_slug` frontmatter audit**: confirm whether the archive-prefixed path is needed at frontmatter level or whether body-link fix alone is sufficient. **Deferred: resolved during Spec phase user interview or research-time resolution.**

---

**Verifiable outcomes** (acceptance grep — to be validated at PR review time per backlog/166-...md:171–178):
- `grep -rn 'docs/pipeline\.md\|docs/sdk\.md\|docs/mcp-contract\.md' .` (no `--include` glob filter) returns no live-source hits.
- `grep -rn 'bash runner\|bash overnight runner' docs/ skills/` returns no hits (covers full set per #166 sweep scope).
- `docs/setup.md` contains `uv tool uninstall uv`, `cortex overnight start`, `cortex overnight status`.
- `requirements/pipeline.md` does NOT contain `claude/reference/`.
- `CHANGELOG.md` does NOT contain `docs/install.md` or `docs/migration-no-clone-install.md`.
- `docs/agentic-layer.md` Skills section line count drops by ≥40 lines.
- `plugins/cortex-core/bin/cortex-check-parity` regenerated cleanly by `just build-plugin`.
- README ≤ 90 lines.
