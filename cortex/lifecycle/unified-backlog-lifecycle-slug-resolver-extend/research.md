# Research: Unified backlog/lifecycle slug resolver — extend to `cortex-update-item` consumer

## Codebase Analysis

### Files in scope

**Primary modules**
- `cortex_command/backlog/resolve_item.py` (403 lines) — current 3-step resolver: `_resolve_numeric` (L116-130), `_resolve_kebab` (L133-138), `_resolve_title_phrase` (L141-165). No UUID-prefix branch. No exact `lifecycle_slug` frontmatter branch. `_resolve_lifecycle_slug` (L99-109) is a **derivation helper**, not a fuzzy-input resolver — it mirrors `BacklogItem.resolve_slug` in `cortex_command/overnight/backlog.py:104-130`. Output JSON shape (`_build_json`, L172-181) is a closed set: `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`. Candidate format (`_format_candidates`, L188-202): `ambiguous: N matches\n<filename>\t<title>\n…` capped at 5 with `… (N more)` overflow.
- `cortex_command/backlog/update_item.py` (475 lines) — `_find_item` (L115-154) is the retrofit target. Current order: exact filename stem → numeric-prefix (digit-only inputs) → filename substring → UUID prefix. The substring branch at L142-145 is the unranked-first-match footgun ("add" matches 29 items, returns first-sorted hit silently). `main()` (L433-471) exits 0 on success, 1 on missing item; no exit-2 vocabulary today.
- `cortex_command/overnight/backlog.py:104-130` — `BacklogItem.resolve_slug`. **Confirmed category mismatch in the ticket's Touch points**: this is a slug *derivation* method on an already-resolved item's frontmatter (fallback chain: `lifecycle_slug` → `spec`/`research` dirname → `slugify(title)` capped at 6 words). It is NOT a fuzzy-input-to-item resolver. `resolve_item.py:_resolve_lifecycle_slug` already mirrors this exact fallback. **Out of scope for this ticket** — no consolidation work needed beyond confirming the mirror stays in sync.

**Shared helpers**
- `cortex_command/common.py` — `slugify()` (the canonical kebab-case converter, L178-200), `TERMINAL_STATUSES` frozenset, `_resolve_user_project_root()` (walks from cwd to first `.git`/cortex ancestor; honors `CORTEX_REPO_ROOT` override).
- `cortex_command/backlog/__init__.py` — currently only re-exports `_telemetry`.

**Test surface**
- `tests/test_resolve_backlog_item.py` — extensive subprocess-driven corpus (`CURATED_INPUTS` L77-109, ~30 cases across 8 categories; `_make_item` fixture helper; sets `CORTEX_BACKLOG_DIR` env override per-test). Existing `test_predicate_a_baseline_capture` / `test_predicate_a_divergences_match_judgment` (L785-932) snapshot Predicate-A∪B behavior for the historic refine→lifecycle adoption (ticket 176).
- `tests/test_cortex_resolve_backlog_item_parity.py` — wheel-vs-working-tree parity test.
- **No existing direct tests for `update_item._find_item`** (per Codebase agent). `tests/test_backlog_worktree_routing.py` covers `update_item.update_item()` but bypasses `_find_item`.
- `pyproject.toml [project.scripts]` already declares `cortex-resolve-backlog-item = "cortex_command.backlog.resolve_item:main"` (line 53) and `cortex-update-item = "cortex_command.backlog.update_item:main"`. DR4 promotion landed via ticket 252 (complete).

**Caller surface for `cortex-update-item`** (6 skill files; raw exit-code branching only — none currently branch on exit-2):
- `skills/lifecycle/references/clarify.md:112-117` — "if it fails, surface the error and ask the user to resolve" (treats all non-zero as one failure class).
- `skills/refine/SKILL.md:84-87,187-198` — same pattern; sequential `complexity`/`criticality` then `status`/`spec` then `areas` writes; instructs operator not to silently skip on failure.
- `skills/lifecycle/references/complete.md:203-212` — handles `command not found` fallback but not exit-2.
- `skills/lifecycle/references/wontfix.md:44`, `skills/lifecycle/references/backlog-writeback.md:29,80,88`, `skills/morning-review/SKILL.md:99-109`, `skills/backlog/SKILL.md:79-80` — pass a slug + key=value pairs, expect exit 0.

### Design surfaces that have to be agreed before code is written

1. **Library API shape.** Extract a pure function `resolve(input_str, backlog_dir) -> ResolutionResult` from `resolve_item.main()`. `ResolutionResult` is a tagged dataclass with `status ∈ {ok, ambiguous, not_found}` plus `item` (Path) or `candidates` (list[Path]). IO/parse failures raise `ResolutionError` so the CLI boundary can map to exit-70 without collapsing into a generic `Exception`. `update_item._find_item` then becomes a 3-line library call that returns `None` on `not_found`, raises on `ambiguous` (or returns the unresolved candidates list so the CLI surfaces them), and returns the Path on `ok`.

2. **5-step order, locked.**
   1. **UUID prefix** — match items whose frontmatter `uuid:` starts with the input (case-insensitive). Minimum prefix length **8 hex chars** (see Open Questions §1 for justification; rejects shorter as exit-64 to avoid pathological collision explosions). Hyphens in input tolerated (UUIDs are written with hyphens in frontmatter).
   2. **Numeric ID** — input is pure-digit; match items whose `^\d+-` prefix has `int()` equal to `int(input)` (zero-padding tolerant; current `_resolve_numeric` L116-130 already implements this — reuse).
   3. **Exact filename stem (with-or-without `NNN-` prefix)** — match the filename stem either exactly as written (`stem == input`) or with the `^\d+-` prefix stripped from BOTH sides (`re.sub(r"^\d+-", "", stem) == re.sub(r"^\d+-", "", input)`). The current `_resolve_kebab` L133-138 only strips the filename side and requires the input bare; the new step extends to accept the prefixed form too. Ambiguity at this step (two items with same prefix-stripped stem, e.g., hypothetical `007-foo` and `107-foo`) surfaces as exit-2 candidate list rather than silent pick.
   4. **Exact `lifecycle_slug` frontmatter** — match items whose frontmatter `lifecycle_slug:` value equals input exactly (not prefix, not substring; see Tradeoffs decision 5). Resolver does NOT verify `cortex/lifecycle/{slug}/` directory existence (frontmatter-only; see Open Questions §4).
   5. **Ranked title-substring fallback** — `slugify(input) ⊆ slugify(title)`, deduplicated by filename (current `_resolve_title_phrase` L141-165). Ambiguity surfaces as exit-2 candidate list — no more silent first-match. Inputs that previously resolved to a silent first-of-many under `update_item._find_item:142-145` now bail; this is the substring-footgun fix the discovery research labeled "independent of unification but in the same code path." The bundling is intentional (see Tradeoffs decision 3 below) because the consumer's new contract requires the same handling for both ambiguity sources.

3. **Cascade loop is OUT of scope for the resolver retrofit.** `update_item._remove_uuid_from_blocked_by` (L191-245) iterates over all items and matches `blocked-by` entries against an *already-known* `closed_uuid`/`closed_id`. It does NOT call `_find_item`. The Adversarial agent correctly flagged that retrofitting fuzzy resolution into cascade would change exact-match semantics. Keep cascade untouched.

4. **`cortex-update-item` exit-code contract.** Adopt exit-2 + stderr candidate list for ambiguity, mirroring `cortex-resolve-backlog-item`. Exit 1 retained for "not found" and other errors. This is a behavior change for the six skill files — every one of them must be updated to recognize exit-2 in the same PR (see Tradeoffs decision 2 + Adversarial Failure Mode 5). Per OQ-1 the skill-prose updates are small (≤2 sentences per skill file, one new bullet under each existing failure-handling note).

5. **Backlog-dir discovery — divergence flagged for unification.** `resolve_item._backlog_dir()` walks from `Path.cwd()` and honors `CORTEX_BACKLOG_DIR`; `update_item.main()` uses `_resolve_user_project_root() / "cortex" / "backlog"` and honors `CORTEX_REPO_ROOT`. Two override env vars, two walk strategies. The library `resolve()` function takes `backlog_dir` as an explicit parameter (already does in spirit — `resolve_item.py` reads `_backlog_dir()` only in `main()`, not in the resolution helpers). Callers stay responsible for discovery; the library does no walking. Consolidating the two walk strategies into a single shared helper is an attractive cleanup but is **out of scope for this ticket** to keep the diff focused — surface as a follow-up (see Open Questions §5).

6. **Candidate format reuse.** `update_item.main()` uses `_format_candidates` from `resolve_item.py` directly when surfacing exit-2 — same prose, same 5-cap, same `… (N more)` overflow. No new candidate-format flavor.

### Conventions and patterns to preserve

- **Python 3.9 type-hint compat** (per existing module headers — `List[Path]`, `str | None`).
- **Subprocess-based CLI tests + direct-function library tests** (the existing test corpus uses subprocess; library tests for `resolve()` will use direct calls). Both styles coexist already.
- **`_make_item(backlog_dir, filename, title, extra="")` fixture helper** in `tests/test_resolve_backlog_item.py` — reuse / promote to `tests/conftest.py` if a new `test_update_item_resolution.py` joins.
- **Schema version on emitted events** — no new event types introduced by this ticket (resolver stays read-only on backlog files; emits stdout/stderr only).
- **`bin/.events-registry.md`** — no registry update needed; this ticket doesn't add event types.

### Files that will change (consolidated list)

- `cortex_command/backlog/resolve_item.py` — extract `resolve()` library function; add UUID-prefix branch; add lifecycle_slug-frontmatter branch; extend filename-stem branch to accept prefixed input; rework `main()` to call `resolve()`.
- `cortex_command/backlog/update_item.py` — replace `_find_item` body with `from cortex_command.backlog.resolve_item import resolve, ResolutionError`; rework `main()` for exit-2 surfacing.
- `tests/test_resolve_backlog_item.py` — extend `CURATED_INPUTS` with UUID-prefix cases, lifecycle_slug-frontmatter cases, prefix-stripped stem ambiguity cases; add the order-drift regression test (every input from the current corpus must resolve to the same item under the 5-step order).
- `tests/conftest.py` (NEW or extended) — promote `_make_item` and the shared corpus to a fixture consumed by both `test_resolve_backlog_item.py` and the new `test_update_item_resolution.py`.
- `tests/test_update_item_resolution.py` (NEW) — direct library tests for `resolve()` invoked from `update_item._find_item`, plus subprocess tests for `cortex-update-item` exit-2 behavior.
- Six skill files (one PR-coordinated update) — add an exit-2 handling sentence/bullet to each existing failure-handling note:
  - `skills/lifecycle/references/clarify.md:112-117`
  - `skills/refine/SKILL.md:84-87,187-198`
  - `skills/lifecycle/references/complete.md:203-212`
  - `skills/lifecycle/references/wontfix.md:44`
  - `skills/lifecycle/references/backlog-writeback.md:29,80,88`
  - `skills/morning-review/SKILL.md:99-109`

## Web Research

### Prior-art reference points (industry-validated)

- **Git rev-parse / gitrevisions** is the textbook precedent for ordered-ladder identifier resolution. Public docs: <https://git-scm.com/docs/gitrevisions>. Git resolves a refname by taking the first match in a fixed ordered list of 6 rules and documents the order publicly. The cortex 5-step order follows the same convention — exact rungs first, ranked fuzzy last.
- **Git short-SHA disambiguation** is a near-perfect analogue for the UUID-prefix branch. Git accepts any leading prefix of a 40-byte SHA-1 that is *unique within the repository* and errors with a candidate list on non-uniqueness (Git commit `1ffa26c4` — "get_short_sha1: list ambiguous objects on error"). Default minimum prefix is `core.abbrev = 7` chars. Tools commonly use 7-8 chars. The cortex UUID corpus is 36-char hex; an 8-char minimum prefix is conservative.
- **Linear** uses dual identity (`ENG-123` for humans, UUIDs for machine references). Mirrors the cortex pattern of `lifecycle_slug` + UUID-prefix + numeric ID coexisting.
- **Docker container/image IDs** explicitly documents the partial-matching footgun (`web-server-1` matching `web-server-10`) — the exact silent first-match-wins bug the discovery research flags at `update_item.py:142-145`.

### Exit-code conventions for ambiguity

- Industry split: exit-2 for "ambiguous / could not disambiguate," exit-1 for generic failure, exit-3 (or 64-128 sysexits.h range) for usage errors. `cortex-resolve-backlog-item` already follows this (exit 0/2/3/64/70).
- Heroku CLI style guide and "Designing CLI Tools for AI Agents" both endorse: keep `LIMIT 2`-style detection (find ≥2 matches → stop and report; don't enumerate the entire set), stderr candidate list as default, JSON payload behind `--json` if a structured client surface is needed.
- Sources: Git rev-parse docs; <https://archit15singh.github.io/posts/2026-02-28-designing-cli-tools-for-ai-agents/>; <https://devcenter.heroku.com/articles/cli-style-guide>.

### Library extraction (Click/Typer patterns)

- The dominant Python CLI pattern is: pure library function returns a tagged Result; the CLI shim translates to exit code at the boundary. Typer's `typer.Exit(code=...)` is the idiomatic exit-code surface. Click's `CliRunner.invoke()` captures `(output, exit_code, exception)` — the canonical Python test harness for the property we need to verify.
- The cortex `resolve()` function follows this exactly: library returns `ResolutionResult(status, item, candidates)`; CLI `main()` translates to exit codes (`ok → 0`, `ambiguous → 2`, `not_found → 3`); IO/parse errors raise `ResolutionError` caught at the CLI boundary and mapped to exit-70.
- Sources: <https://typer.tiangolo.com/tutorial/terminating/>; <https://click.palletsprojects.com/en/stable/exceptions/>.

### Regression-sample conventions

- pytest parametrize with a `(input, expected_status, expected_item_or_candidates)` table is the standard form. `pytest-regressions` and `pytest-golden` are production-quality snapshot frameworks (both released 2025+). The existing `tests/test_resolve_backlog_item.py:test_predicate_a_baseline_capture` already uses a manual JSON-fixture snapshot pattern (`predicate_a_baseline.json`) — no new framework dependency is needed.
- Git's own `t/t1512-rev-parse-disambiguation.sh` is a strong structural model: a flat shell-based table of `(repo state, input ref, expected resolution)` triples. Translated to pytest parametrize with `ids=` for stability.
- Sources: <https://github.com/git/git/blob/master/t/t1512-rev-parse-disambiguation.sh>; <https://docs.pytest.org/en/stable/example/parametrize.html>.

### Anti-pattern reinforcement: silent first-match-wins

- mcfly issue #183, Azure Pipelines #3180, and Git's own evolution all converge: silent first-sorted-hit fuzzy matching is a recognized footgun. Git's tightening was config-gated (`core.warnAmbiguousRefs`) rather than a hard cutover. The cortex precedent for back-compat behavior change: ticket 176 made an analogous predicate change (lifecycle adopted the refine resolver's set-theoretic union predicate) with a contract test verifying every input's resolution before deletion. The same pattern fits here.

## Requirements & Constraints

### From `cortex/requirements/project.md`

- **Skill-helper modules pattern** (Architectural Constraints): "atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry. Promoted modules expose a `[project.scripts]` console-script entry as the recommended invocation idiom." Direct fit — the resolver is already promoted (ticket 252 closed DR4); this ticket adds a second consumer (`update_item._find_item`) to the same shared module.
- **Wheel-binstub vs working-tree invocation** (Architectural Constraints): "binstubs execute against the installed wheel's `site-packages/`; `python3 -m cortex_command.<skill>` runs against the working tree." Implication: the library import from `update_item.py` to `resolve_item.py` works equally in both modes (both modules live wheel-side post-#252). No `CORTEX_COMMAND_FORCE_SOURCE` consideration applies — both modules are in the same package.
- **SKILL.md-to-bin parity enforcement** (Architectural Constraints): no new bin scripts; existing scripts unaffected. `bin/cortex-check-parity` not impacted.
- **Backlog `grep -c` resolution** (Architectural Constraints): not applicable — no new event tokens.

### From discovery research `cortex/research/harness-friction-triage/research.md`

- **Q3 verbatim**: "A deterministic resolution order (UUID prefix → numeric ID → exact filename stem → exact `lifecycle_slug` → ranked substring) unifies safely — but the new order necessarily *adds* accepted inputs to each CLI. Regression sample required: every (CLI, input) pair where the current behavior is fail-fast must be evaluated under the new order before the resolver ships." This is the contract-test obligation. The corpus simulation already shipped for ticket 176 (`test_predicate_a_baseline_capture`) is the structural template — extend with new UUID-prefix and lifecycle-slug-frontmatter cases plus the `update_item._find_item` corpus.
- **DR4 verbatim**: "the project's stated direction is 'ship CLI-first as a non-editable wheel' — preserving a bash-only resolver is design drift, not a load-bearing boundary." The wheel-side promotion landed in #252; this ticket completes the consolidation by retrofitting the remaining consumer.
- **Pre-existing footgun (slug-space inventory)**: "`update_item.py:142-145` does unranked substring matching — `'add'` matches 29 items, returns first-sorted hit silently. Independent of unification but in the same code path." This research deliberately bundles the footgun fix with the unification because the new resolver contract (ranked candidates / exit-2) requires the consumer to handle ambiguity once anyway; splitting would force two rounds of consumer-side change. See Tradeoffs decision 3.

### From CLAUDE.md

- **Solution horizon** is the load-bearing principle: "A scoped phase of a multi-phase lifecycle is not a stop-gap." This ticket is the last child of the slug-space consolidation; bundling the footgun fix is the durable version.
- **What and Why, not How** — research outputs prescribe the *shape* of the library API, the exit-code contract, and the test corpus; the *line-by-line* implementation is the plan's job.
- **MUST-escalation policy** — not triggered. No new MUSTs introduced; existing soft-positive phrasing in skill-prose updates is sufficient.

### No relevant ADRs

`cortex/adr/` was scanned. No ADR governs slug resolution or shared-module consumer extraction; the binding decisions live in DR4 of the discovery research and project.md's Skill-helper modules clause.

## Tradeoffs & Alternatives

### Decision 1 — Library-call vs subprocess for `update_item._find_item`

**A (recommended)**: `update_item._find_item` imports `cortex_command.backlog.resolve_item.resolve()` and calls it directly. Pure Python; no subprocess.

**B**: subprocess + JSON parsing.

**Why A**: Both modules ship in the same wheel; the install_guard boundary is closed (DR4 / #252). The Tradeoffs agent originally cited cascade-loop performance, but the Adversarial agent correctly noted cascade does NOT call `_find_item` (the cascade matches exact UUIDs/IDs at L225-233). The real argument for A is single-source-of-truth — the 5-step order is defined once and consumed by both consumers without subprocess drift. Subprocess (B) would add ~50-150ms per call on macOS (current `cortex-update-item` invocations are CLI-driven from skills, so this matters even though cascade doesn't). The mid-stage refactor (Tradeoffs option C, "extract a shared internal function") is what A produces; the distinction is presentational, not architectural.

### Decision 2 — Ambiguity surfacing in `cortex-update-item`

**A (recommended)**: Adopt exit-2 + stderr candidate list, mirroring `cortex-resolve-backlog-item`.

**B**: Exit-1 with a different stderr format. **C**: Silent first-match (status quo). **D**: Reject ambiguity hard with "did you mean."

**Why A**: Consistency across the backlog CLI suite (the resolver already pays the cost). The six skill files updating in the same PR (per Decision 3) absorb the contract change cleanly. C (status quo) is the footgun the discovery research targets — non-negotiable. D is too strict for valid use cases like "user paste an ambiguous string, see candidates, pick one."

### Decision 3 — Bundle vs separate the unranked-substring fix

**A (recommended)**: **Bundle**. Single PR ships resolver-extension + `update_item._find_item` retrofit + 6 skill-prose updates + corpus parametrization.

**B**: Separate — ship resolver first, then `update_item` retrofit, then skill updates.

**Why A** (the Adversarial agent and the ticket-author align; the Tradeoffs agent's "separate" recommendation is overruled by the Adversarial pushback): separation creates a state-fragility window where the resolver ships with the 5-step order but `update_item` is still on the old 3-step. Skills that call both CLIs in the same session would observe inconsistent resolution behavior. Worse, exit-2 adoption is a contract change for `cortex-update-item` — staging it separately from the skill-prose updates means six skills sit with stale failure-handling prose between PRs. Bundling forces atomic update: resolver, consumer, contract docs, and tests all flip together. The diff is larger but the risk of a partial-rollout window is zero. Git's own `core.warnAmbiguousRefs` precedent (config-gated tightening) doesn't apply here — cortex isn't shipping a multi-user release; it's a single repo with synchronous deployment.

### Decision 4 — "With-or-without leading numeric prefix" filename-stem matching

**A (recommended, with disambiguation)**: Both directions stripped symmetrically. Input `foo-bar` matches stem `007-foo-bar` (because `re.sub(r"^\d+-", "", "007-foo-bar") == "foo-bar"`). Input `007-foo-bar` matches stem `007-foo-bar` directly. If two items have the same prefix-stripped stem (`007-foo-bar` and `107-foo-bar`), input `foo-bar` produces exit-2 ambiguity (two candidates).

**Why A**: The current `_resolve_kebab` (L133-138) already does this (strips filename side, requires bare input). Extending to accept the prefixed form too is the minimal change that satisfies the ticket's "with-or-without" language. The Adversarial agent's prefix-stripped-collision case (`007-foo` and `107-foo`) is real but **already exists** under the current resolver — it's not a new regression. The order-drift test will document this behavior.

### Decision 5 — Lifecycle_slug frontmatter match: exact, prefix, or substring?

**A (recommended)**: **Exact.** `lifecycle_slug == input` only.

**Why A**: The ticket Role section says "exact `lifecycle_slug` frontmatter match." This step is ordered before the title-substring fallback for a reason — it's the high-confidence rung. Substring or prefix matching would compete with the ranked title-substring step and obscure intent. Inputs that need fuzzy matching fall through to step 5.

### Decision 6 — UUID-prefix minimum length

**A (recommended)**: **Minimum 8 hex chars**, with hyphens stripped from input before matching.

**Why A** (per Adversarial Failure Mode 1): Git's `core.abbrev` default is 7 chars for SHA-1; UUIDs have higher entropy per char but a 110+ item corpus tolerates 8 comfortably. Shorter prefixes (`<8` chars) hit exit-64 with a usage diagnostic: "UUID prefix must be at least 8 characters; got N." Inputs that look pure-hex but are < 8 chars fall through to the next step rather than producing pathological candidate lists. **Quantitative check** (Open Question §1) — a one-time scan of the live backlog UUID set should confirm 8 chars is collision-free; if not, raise to 10.

### Decision 7 — Test corpus location

**A (recommended)**: **Shared fixture in `tests/conftest.py`** (or a new `tests/backlog_resolution_corpus.py`) consumed by both `tests/test_resolve_backlog_item.py` and new `tests/test_update_item_resolution.py`.

**Why A**: DRY corpus; both CLIs are tested against the same scenarios; adding a regression case updates both suites. The corpus is a list of `ResolutionCase(input, expected_status, expected_filename, description)` dataclasses (Adversarial Failure Mode 8: no new framework dependency — `pytest-regressions` is overkill for this scale).

### Overall recommendation (the lever / bet / risk)

**Lever**: Single shared library function `resolve()` consumed by both CLIs; single shared corpus consumed by both test suites; single PR that bundles resolver-extension + consumer-retrofit + skill-prose updates.

**Bet**: The 5-step order changes no current (input → item) resolution — only adds inputs that currently fail-fast. This is verifiable by the corpus simulation (every existing `CURATED_INPUT` resolves to the same `expected_filename` under both the 3-step and 5-step orders, plus new cases added for UUID prefix, lifecycle_slug-frontmatter, and the substring-footgun exit-2 transition).

**Risk**: If the corpus simulation reveals a current input that *would* resolve to a different item under the 5-step order (e.g., a title-phrase match that's now intercepted by a lifecycle_slug-frontmatter match on a different item), that's an order-drift regression requiring step-priority adjustment OR explicit acknowledgement as an intended behavior change. The simulation is the gate; ship only after it passes.

## Adversarial Review

See `cortex/lifecycle/unified-backlog-lifecycle-slug-resolver-extend/research.md` (this file) for the full Adversarial findings inlined into the Tradeoffs section. Key concerns that flow into Open Questions and the spec phase:

- **Failure Mode 1 (UUID prefix minimum length)** — resolved as Decision 6 above. OQ §1 closes the corpus-collision empirical check.
- **Failure Mode 2 (order-dependent drift)** — resolved by the corpus simulation gate in the overall recommendation; spec must include it as a test obligation.
- **Failure Mode 3 (cascade-loop uses raw IDs)** — resolved: cascade is out of scope; only `_find_item` is retrofitted.
- **Failure Mode 4 (bundle vs separate)** — resolved as Decision 3 (bundle).
- **Failure Mode 5 (exit-2 breaks skills)** — resolved by the bundled skill-prose updates in Decision 3.
- **Failure Mode 6 (filename-stem language)** — resolved as Decision 4.
- **Failure Mode 7 (lifecycle_slug regression risk)** — resolved by Decision 5 + the order-drift simulation gate.
- **Failure Mode 8 (test-framework deps)** — resolved by Decision 7 (no new framework).
- **Failure Mode 9 (library-call exit-70 distinction)** — resolved by explicit `ResolutionError` exception type at the library boundary.
- **Failure Mode 10 (backlog-dir discovery divergence)** — flagged for follow-up; OQ §5.
- **Failure Mode 11 (lifecycle-directory existence check)** — resolved: resolver matches frontmatter only; no directory verification.
- **Failure Mode 12 (prefix-stripped stem collisions)** — covered by the corpus simulation gate.

## Open Questions

1. **What is the empirically-safe UUID prefix minimum length?** Decision 6 picked 8 chars conservatively. Resolution: at spec time, scan the current `cortex/backlog/*.md` UUID set and confirm 8 chars guarantees uniqueness; if any collision exists at 8, raise to 10. Quantitative check, not a user-answer question. **Deferred: will be resolved in Spec by running a one-off scan of frontmatter UUIDs.**

2. **Does the ticket's "with-or-without" filename-stem language imply both symmetric stripping (Decision 4A) or only one direction?** The current `_resolve_kebab` strips the filename side and requires bare input; the new step adds the prefixed-input variant. Inline answer: yes, Decision 4A. The ticket-author can override during spec approval if they intended single-direction. **Resolved (Decision 4A).**

3. **Should the 5-step order's regression sample also cover `cortex-resolve-backlog-item` inputs that are currently rejected but the new order accepts?** Yes — Q3 of the discovery research explicitly requires this. The corpus must include UUID inputs (currently exit-3 on `cortex-resolve-backlog-item`) and exact lifecycle_slug inputs (currently exit-3 on `cortex-resolve-backlog-item` for inputs that don't substring-match a title). **Resolved: yes, included.**

4. **Should the resolver verify `cortex/lifecycle/{slug}/` directory existence when matching via the lifecycle_slug frontmatter branch?** Decision: **no**. The resolver is frontmatter-only. Callers needing directory verification do it separately (lifecycle skill already does this). **Resolved.**

5. **Backlog-dir discovery divergence between `_backlog_dir()` (resolver) and `_resolve_user_project_root()` (update_item) — consolidate?** Two different walk strategies and two override env vars. **Deferred: out of scope for this ticket** to keep the diff focused on the resolver retrofit. Follow-up ticket recommended to consolidate into a single `cortex_command.common.resolve_backlog_dir()` helper used by both modules. Surface this in the PR description so a follow-up ticket can be filed.

## Considerations Addressed

- **The resolver currently lacks UUID-prefix and lifecycle_slug frontmatter branches; this is resolver-extension plus consumer-retrofit, not retrofit alone.** Addressed in §Codebase Analysis (Design surfaces #2: the 5-step order is defined as a resolver-side extension; new branches added in steps 1 and 4) and Decision 6 (UUID prefix minimum length).
- **`cortex_command/overnight/backlog.py:104-130` is `BacklogItem.resolve_slug`, NOT a fuzzy-input-to-item resolver; verify whether the ticket's listing is a category error.** Addressed in §Codebase Analysis: confirmed category mismatch. `resolve_item.py:99-109` already mirrors the same fallback chain. Out of scope for this ticket — no consolidation work needed.
- **The substring-footgun fix is research-labeled "independent of unification but in the same code path." Surface the bundling decision and its tradeoff.** Addressed in Tradeoffs Decision 3 (bundle, with the Adversarial agent's pushback overruling the original Tradeoffs-agent separation recommendation). Tradeoff: larger atomic PR vs zero-window risk of inconsistent resolution between resolver and consumer.
- **Test surface scope must cover both CLIs and may exceed `tests/test_resolve_backlog_item.py` alone.** Addressed in Tradeoffs Decision 7 (shared corpus fixture in `tests/conftest.py`, new `tests/test_update_item_resolution.py`) and the Files-that-will-change list.
