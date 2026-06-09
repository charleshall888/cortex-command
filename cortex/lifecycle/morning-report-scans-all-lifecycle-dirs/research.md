---
feature: morning-report-scans-all-lifecycle-dirs
backlog_id: 294
tier: complex
criticality: high
created: 2026-06-09
---

# Research: Morning report scans all lifecycle dirs + retry-ticket titles are unquoted YAML

Two defects in `cortex_command/overnight/report.py`, both observed in wild-light run `overnight-2026-06-09-0222`:
- **Bug A** — the morning report's "Critical Review Residue" and "Requirements Drift Flags" sections glob the entire `cortex/lifecycle` tree instead of the session feature set, so the report fills with noise from unrelated historical lifecycles (13 residue entries in the run, none from the 4 session features).
- **Bug B** — session-finalization auto-filed tickets (`Retry deferred: {slug}`, `Follow up: {name}`) write an unquoted `title:` into YAML frontmatter; the embedded `: ` is invalid YAML and aborts the whole-backlog scan in `cortex-update-item` / `cortex-resolve-backlog-item`.

## Codebase Analysis

**Files that change (primary):** `cortex_command/overnight/report.py`
- Bug A — residue: `render_critical_review_residue` (lines 1028–1080). Glob at **1031**: `lifecycle_root.glob("*/critical-review-residue.json")` where `lifecycle_root = _resolve_user_project_root() / "cortex/lifecycle"` (1030, correctly root-anchored). `total = len(residue_paths)` (**1032**) feeds header `## Critical Review Residue ({total})` (1033) and the `if total == 0` empty-state branch (1035). Per-entry: `slug = path.parent.name` (1044), displayed key `payload.get("feature", slug)` (1052), per-feature subheader `### {feature} ({len(findings)})` (1059). **No `data.state is None` guard today.**
- Bug A — drift: `render_pending_drift` (lines 634–712). Two globs at **655**/**671**: bare-relative `Path("cortex/lifecycle").glob("*/review.md")`; key `review_path.parent.name`. Header is the literal `## Requirements Drift Flags` (687) — **no `(N)` count to recompute**; the gate is the early-return when `not drift_features and not breach_features` (683–684). The 655 loop is a "re-implementing features" stale-review sub-scan; the 671 loop is the drift/breach scan.
- Bug B — `create_followup_backlog_items`: titles built at **280** (`f"Follow up: {name}"`, failed/paused path) and **290** (`f"Retry deferred: {name}"`, deferred path); both funnel into one hand-built frontmatter f-string at **305–321**, offending line **307**: `f"title: {title}\n"`.

**`data.state.features` shape (the scoping key):** `data.state` is `Optional[OvernightState]` (report.py:86), populated in `collect_report_data` via `load_state(_default_state_path())` (124,131). `OvernightState.features` is `dict[str, OvernightFeatureStatus]` (state.py:233) keyed by **kebab-case feature slug**; values carry `status`, `error`, `repo_path`, `recoverable_branch`, etc. (state.py:96–109) but **not** their own slug. Canonical "iterate the session set" pattern already in use: `render_completed_features` (503), `for name, fs in data.state.features.items()` (263, 503, 649).

**How titles ARE serialized correctly elsewhere (Bug B pattern):**
- `cortex_command/backlog/create_item.py:112` — `f'title: "{title}"\n'` (quoted but **NOT escaped** — latent bug on a title containing `"`).
- `cortex_command/dashboard/seed.py:1050–1057` — `title_escaped = title.replace('"', '\\"')` then `f"title: \"{title_escaped}\"\n"`, with a rationale comment. The most-correct existing precedent, but still escapes only `"` (not backslash).

**Conventions:** lifecycle paths anchor on `_resolve_user_project_root()`; deferral/ticket writes use `atomic_write`; PyYAML is a direct dep and already imported in report.py (line 1421, `yaml.safe_load_all` at 1484).

## Web Research

Authoritative YAML scalar rules: a value containing `: ` (colon-space) **cannot** be a plain scalar — it must be quoted (the exact bug). Single-quoted style escapes `'` by doubling; double-quoted style is the only one with escape sequences and must escape `"` as `\"` and `\` as `\\`.

Empirically verified (PyYAML 6):
- `yaml.safe_dump({'title': 'Retry deferred: some-slug'})` → `title: 'Retry deferred: some-slug'\n` — **auto-quotes** the colon-space value (single quotes by default), handles embedded `"`/`'`/`\`/type-looking values correctly. Controls: pass `sort_keys=False` to preserve field order; do **not** set `explicit_end=True` (adds a `...` marker inside the fence); pass `allow_unicode=True` for non-ASCII; do **not** use `default_style='"'` (it also quotes keys).
- The naive `f'title: "{title}"'` (the create_item.py form) is itself broken: with `title = 'He said "hi"'` PyYAML raises `ParserError`. A hand-rolled fix MUST escape the quote char (and backslash for double quotes); single-quote-with-doubling is the lowest-risk minimal form.

Reference: `python-frontmatter` builds a dict and dumps via `yaml.SafeDumper`. Community guidance (Real Python, Reorx) is uniform: **serialize via `yaml.safe_dump`, never string-concatenate YAML.**

## Requirements & Constraints

- **`pipeline.md:24`**: the morning report is written to two paths — `cortex/lifecycle/sessions/{session_id}/morning-report.md` (gitignored archive) and `cortex/lifecycle/morning-report.md` (tracked latest copy). Both receive the **same** per-session report; "session-scoped" is the documented intent (`pipeline.md:9,15`). No requirement scans the whole tree → Bug A's fix is aligned.
- **`project.md:46` (SP001/SP002) + ADR-0009**: bare relative paths resolve against CWD. The lint is scoped to `skills/**/*.md`, **not** Python — but the same hazard is live at report.py:655/671's bare `Path("cortex/lifecycle")`. Repo convention is to anchor on `_resolve_user_project_root()`.
- **Backlog YAML contract** (`skills/backlog/references/schema.md`): `title` is a required string; frontmatter must be valid YAML — Bug B violates this. ADR-0001 (file-based state) premises diffable/parseable files.
- **Dependencies**: `pyproject.toml:17` declares `pyyaml>=6.0` as a **direct** runtime dep; `import yaml` in `cortex_command/overnight/` is permitted — no new dependency needed.
- **Scope**: both fixes land in "Overnight execution … morning report" (in scope). Out of scope: tickets 292 (review-gate cycle-0 crash) and 293 (plan-parser metadata) from the same run. No MUST-escalation concern (pure-Python, no skill prose).
- **Solution-horizon flag**: the title-serialization bug recurs in **three** named places (report.py:307, create_item.py:112 latent, seed.py:1052) — the "applies in multiple known places you can name" test argues for a shared serializer over a one-line local patch.

## Tradeoffs & Alternatives

**Bug A — scoping the globs.** State keys == lifecycle dir name == residue/review.md `parent.name` for the normal slugify path (plan.py:418–419; residue written to `cortex/lifecycle/<slug>/` per write_residue_cli.py:72).
- **A1 — keep the glob, post-filter results by `parent.name in session_features`.** Smallest diff (~3 lines/site); preserves the malformed-residue and dir-only cases existing tests exercise; robust to slug divergence and cross-repo (see Adversarial). Still walks the full tree (O(history)), acceptable once/session.
- **A2 — iterate `data.state.features`, build each path directly (no glob).** Cleaner intent and O(session) I/O, and the research originally recommended it — **but the Adversarial pass disqualified it**: it synthesizes a home-repo path for cross-repo features (repo_path) and breaks on verbatim `lifecycle_slug` keys that diverge from the (validated, clean) residue dir name. **Not recommended.**
- **A3 — glob a known filename inside each feature dir.** A2 with a pointless glob wrapper; rejected.
- **Recommendation: A1 (glob-then-filter on `parent.name`).** Intersect glob results with the **full** `data.state.features` keyset (NOT merged-only — paused/deferred/failed features still carry actionable residue). Recompute `total` from the filtered list. Filter on the directory name `path.parent.name`, not the writer-controlled `payload["feature"]` field.

**Bug B — quoting the title.** Two title sites, one frontmatter serializer (report.py:307).
- **B1 — spot-quote inline at line 307.** Smallest, but re-encodes the escaping rule inline and a future third writer re-introduces the bug.
- **B2 — small in-module escape helper mirroring seed.py.** Centralizes the rule; must escape **backslash before quote**, or it reintroduces a create_item-style bug.
- **B3 — `yaml.safe_dump` the frontmatter dict (sort_keys=False).** Drops the whole bug class for *every* field, parser-symmetric; larger diff and changes the emitted quoting style (must be tolerated by readers — see Adversarial #6, where safe_dump is the only option correct for both readers). PyYAML already imported.
- **Recommendation: B3 (`yaml.safe_dump`).** The Adversarial pass showed `json.dumps(title)` (a tempting alternative) **corrupts the tolerant index parser**, and a bespoke helper must get backslash escaping exactly right; `safe_dump` is the only strategy correct against **both** the strict (`resolve_item`) and tolerant (`generate_index`) readers.

## Session Feature-Set & Data-Flow

- `data.state.features`: `dict[str, OvernightFeatureStatus]`, keyed by the kebab slug from `BacklogItem.resolve_slug()` (backlog.py:104–130; priority: explicit `lifecycle_slug` frontmatter → spec/research parent-dir → capped `slugify(title)`). `plan_path = cortex/lifecycle/{slug}/plan.md` (plan.py:423) ties the key to the dir name by construction.
- **Membership is session-only.** Top-level `overnight-state.json` is a single-active-session pointer overwritten every bootstrap (plan.py:579–589); `map_results.update_state_from_results` only upserts this session's batch names (map_results.py:90–129); resume is read-only over in-session state. Carryover deferred/paused items re-enter a *new* session only as freshly-selected keys. **Consequence:** filtering residue/drift by `data.state.features` will not hide carryover the runner is actually acting on this session.
- **Residue key == dir name == state key** for the normal path: residue written to `cortex/lifecycle/<--feature>/...` where `--feature` is the dir name (write_residue_cli.py:72, resolve_feature_cli.py:50–69), validated against `^[a-z0-9][a-z0-9-]*$`. review.md `parent.name` == feature key (feature_executor.py reads `lifecycle_base/feature/...`). **Use `path.parent.name` as the join key**, not the display-only `payload["feature"]`.
- **(N) counts:** only the residue header has a `(N)` (report.py:1032–1033) — recompute from the filtered list. Drift has no header count; just scope the two loops.
- **No mapping helper needed** — the mapping is identity; a membership test suffices. Do not reuse `_find_backlog_id` (loose substring matcher, wrong direction).

## Blast-Radius & Existing-Pattern

- **Bug B blast radius CONFIRMED (abort-all).** `resolve_item.py:412–430` eagerly `yaml.safe_load`s **every** `[0-9]*-*.md` in the backlog dir and raises `ResolutionError` on the first parse failure — so one malformed retry ticket blocks `cortex-update-item` AND `cortex-resolve-backlog-item` for the **whole** backlog (the error even names the bad file, not the targeted one). `cortex-load-parent-epic` (`yaml.safe_load`, load_parent_epic.py:118) also breaks.
- **Two parser families, opposite failure modes.** Strict (`yaml.safe_load`, raises): `resolve_item.py`, `load_parent_epic.py`. Tolerant (line-based first-colon split, never raises): `generate_index.py:46–60` and `overnight/backlog.py:232` — these *degrade* (the tolerant split mis-handles but doesn't crash). There is **no** single shared parser in `common.py`. **This split is why the Bug B fix's output must satisfy both readers.**
- **Only three hand-written `title:` frontmatter sites exist:** report.py:307 (the bug, unescaped), create_item.py:112 (quoted, unescaped — latent), seed.py:1057 (quoted+escaped). 

## Testing & Verification

- **Run:** `just test` (full); targeted: `.venv/bin/pytest cortex_command/overnight/tests/test_report.py -q`, `.venv/bin/pytest tests/test_report.py -q`, `.venv/bin/pytest tests/test_resolve_backlog_item.py -q`. Config in pyproject `[tool.pytest.ini_options]`, `xfail_strict = true`.
- **Fixtures to reuse:** `cortex_command/overnight/tests/test_report.py` — `_pytest_make_state(features,...)` / `_pytest_make_data(features,...)` (16–28), `_write_plan`/`_write_events_log` (397–416), and `test_recoverable_no_rebuild_followup` (826–849) as the Bug B template. `tests/test_report.py` — `Test_critical_review_residue` (166–386) writes residue JSON under `tmp_path/cortex/lifecycle/{feature}/` and sets `CORTEX_REPO_ROOT`; `_make_residue` (140–163). `tests/test_resolve_backlog_item.py:test_drift_corpus_equivalence` (132–168) is the canonical extract-fence-then-`yaml.safe_load` round-trip pattern.
- **Bug A test:** build a session feature set `{feat-a}`, drop residue+review.md into BOTH `feat-a/` and an unrelated `old-unrelated/` dir, render; assert `old-unrelated` absent and header reads `(1)` not `(2)`. Set BOTH `CORTEX_REPO_ROOT` and (because drift uses bare-relative) `monkeypatch.chdir(tmp_path)`. Add a negative-control with `{feat-a, feat-b}` → `(2)`.
- **Bug B test:** generate retry + follow-up tickets, then assert the written file's frontmatter `yaml.safe_load`s without raising AND round-trips the title; cross-check via `resolve_item._parse_frontmatter`. **Must assert through a `yaml.safe_load`-backed parser — the tolerant `generate_index` parser does NOT catch the bug.** Edge cases: titles with embedded `"`, `\`, and multiple colons.
- **Pre-commit gates:** changes touch only `cortex_command/overnight/report.py` + tests → no dual-source/parity/events-registry/grep-target regeneration required; only `just test` must pass. `report.py` is not on the lifecycle-gated edit list.

## Adversarial Review

The adversarial pass overturned two research recommendations and surfaced load-bearing risks:
- **A2 is wrong (use A1).** Direct-path-build from state keys breaks **cross-repo features** (`OvernightFeatureStatus.repo_path`, state.py:107 — residue lives in another repo's worktree; A2 synthesizes a home-repo path and silently finds nothing) and the **verbatim-slug divergence** (`lifecycle_slug` is read raw at backlog.py:335 with no validation, so a state key can diverge from the validated, clean residue dir name). Glob-then-filter on `parent.name` survives both.
- **`state is None` → render UNFILTERED, not nothing.** All existing residue tests pass `state=None` and assert residue renders from disk (tests/test_report.py:185–244) — "render nothing when state is None" *inverts* that contract. Worse, if `overnight-state.json` is corrupt/missing but residue exists, rendering nothing hides actionable B-class findings exactly when state is broken. Bias toward over-showing. Filter only when state is present and non-empty.
- **`json.dumps(title)` is disqualified.** It satisfies the strict reader but its backslash escapes **leak literally into the backlog index** via the tolerant `generate_index` parser (first-colon split + `.strip("\"'")`, generate_index.py:56,162). `yaml.safe_dump` was verified correct against **both** readers — the decisive reason to prefer B3.
- **Root-resolution mismatch is unaddressed by the ticket.** Residue renderer uses `_resolve_user_project_root()` (1030); drift renderer uses bare-relative `Path("cortex/lifecycle")` (655/671); the residue **writer** is bare-CWD-relative from the *feature* worktree (write_residue_cli.py:72) while the report runs from the integration worktree / home repo. The spec must confirm residue actually reaches the scanned dir (the wild-light run's 13 entries prove it does for home-repo features) and unify the two renderers' root resolution.
- **`render_pending_drift` has ZERO test coverage** — scoping it in means adding a regression net, not relying on parity with the residue path.
- **Residue accumulates on disk (gitignored).** Keyset-filtering hides unrelated history (the fix) but shows *stale prior-session* residue for a **re-entered** carryover feature — session-scoping by keyset alone doesn't distinguish fresh-this-session from stale-on-disk residue.
- **create_item.py:112 is the same bug class** — fix in this change or explicitly defer with a ticket reference (solution-horizon).

## Open Questions

1. **Cross-repo residue handling.** Does the morning report intend to surface critical-review residue for cross-repo features at all (their residue is written CWD-relative in the other repo, gitignored, and never reaches the home-repo scanned dir)? *Deferred: resolve in Spec — decide whether cross-repo residue is in scope for this fix or explicitly out of scope; A1 glob-then-filter preserves current (home-repo-only) behavior either way.*

2. **`state is None` fallback behavior.** Render unfiltered (preserves existing test contract + avoids hiding blockers on broken state) vs render nothing. *Recommended answer: render unfiltered when state is None/empty; filter only when state is present and non-empty. Deferred: confirm in Spec as the chosen contract.*

3. **Root-resolution unification.** Should `render_pending_drift` be re-anchored from bare-relative `Path("cortex/lifecycle")` to `_resolve_user_project_root()` to match the residue renderer (and is residue reaching the scanned dir confirmed beyond the wild-light home-repo evidence)? *Deferred: resolve in Spec — likely yes (align both renderers), pending confirmation the change doesn't alter the worktree-CWD run context.*

4. **Residue staleness across sessions.** For a carryover feature re-entered this session, keyset-filtering will show its *prior-session* residue. Is half-session-scoping (hide unrelated history, but stale residue for re-entered features can persist) acceptable for this ticket, or must residue be cleared at bootstrap / stamped with `session_id`? *Deferred: resolve in Spec — recommend accepting the keyset filter as the scoped fix and filing session-stamping as a separate follow-up if the staleness proves real, per solution-horizon.*

5. **create_item.py:112 latent quote bug.** Fix it in this same change (it is the same bug class, a named second site) or defer with an explicit follow-up ticket? *Deferred: resolve in Spec with the user — solution-horizon argues for fixing the named second site or a shared serializer now.*

6. **Bug B fix shape.** `yaml.safe_dump` the whole frontmatter dict (recommended, correct for both readers, larger diff) vs a backslash-and-quote-escaping helper (smaller diff, must get escaping exactly right). *Deferred: resolve in Spec — research recommends `yaml.safe_dump(sort_keys=False)`; the residual decision is whether to also route create_item.py through it (ties to OQ5).*
